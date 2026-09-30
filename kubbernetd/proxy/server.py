import asyncio
import structlog
from aiohttp import web
from kubernetes import client

from kubbernetd.proxy.buffer import RequestBuffer
from kubbernetd.proxy.forwarder import RequestForwarder
from kubbernetd.proxy.signal import GroupSignaler
from kubbernetd.proxy.discovery import EndpointDiscovery
from kubbernetd.proxy.auth import TargetAuthorizer

log = structlog.get_logger()
ACTIVE_ANNOTATION = "kubbernetd.io/active-requests"


class ProxyServer:
    def __init__(
        self,
        buffer: RequestBuffer,
        forwarder: RequestForwarder,
        signaler: GroupSignaler,
        discovery: EndpointDiscovery,
        auth: TargetAuthorizer,
        cleanup_interval: int = 60,
    ):
        self.buffer = buffer
        self.forwarder = forwarder
        self.signaler = signaler
        self.discovery = discovery
        self.auth = auth
        self.custom_api = client.CustomObjectsApi()
        self.cleanup_interval = cleanup_interval
        self.app = web.Application()
        self.app.router.add_get("/healthz", self.handle_healthz)
        self.app.router.add_route("*", "/{tail:.*}", self.handle_request)
        self._draining: set[tuple[str, str]] = set()
        self._active_counter: dict[tuple[str, str], int] = {}
        self._active_lock = asyncio.Lock()

    async def start_background_tasks(self):
        asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.cleanup_interval)
            expired = self.buffer.cleanup_expired()
            if expired:
                log.info("cleaned up expired held requests", count=expired)

    async def handle_healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "kubbernetd-proxy"})

    async def _set_active(self, namespace: str, rg_name: str, active: bool):
        key = (namespace, rg_name)
        async with self._active_lock:
            prev = self._active_counter.get(key, 0)
            if active:
                self._active_counter[key] = prev + 1
                if prev == 0:
                    try:
                        patch = {"metadata": {"annotations": {ACTIVE_ANNOTATION: "1"}}}
                        self.custom_api.patch_namespaced_custom_object(
                            group="kubbernetd.io", version="v1",
                            namespace=namespace, plural="replicagroups",
                            name=rg_name, body=patch,
                        )
                    except Exception:
                        pass
            else:
                new_val = max(0, prev - 1)
                if new_val == 0:
                    self._active_counter.pop(key, None)
                    try:
                        patch = {"metadata": {"annotations": {ACTIVE_ANNOTATION: None}}}
                        self.custom_api.patch_namespaced_custom_object(
                            group="kubbernetd.io", version="v1",
                            namespace=namespace, plural="replicagroups",
                            name=rg_name, body=patch,
                        )
                    except Exception:
                        pass
                else:
                    self._active_counter[key] = new_val

    async def _resolve_target_service(self, namespace: str, rg_name: str) -> str:
        try:
            rg = self.custom_api.get_namespaced_custom_object(
                group="kubbernetd.io", version="v1",
                namespace=namespace, plural="replicagroups",
                name=rg_name,
            )
            spec = rg.get("spec", {})
            target = spec.get("targetRef", {})
            return target.get("name", rg_name)
        except Exception:
            return rg_name

    async def handle_request(self, request: web.Request) -> web.Response:
        rg_name = request.headers.get("X-Kubbernetd-Service", "")
        namespace = request.headers.get("X-Kubbernetd-Namespace", "default")

        if not rg_name:
            return web.Response(status=400, text="missing X-Kubbernetd-Service header")

        authorized = await self.auth.authorize(namespace, rg_name)
        if not authorized:
            return web.Response(status=403, text=f"unauthorized: no ReplicaGroup '{rg_name}' in namespace '{namespace}'")

        target_service = await self._resolve_target_service(namespace, rg_name)
        try:
            await self._set_active(namespace, rg_name, True)
            target_ip = self.discovery.next_ip(namespace, target_service)
            if target_ip:
                return await self.forwarder.forward_streaming(
                    request=request,
                    target_ip=target_ip,
                )
            return await self._hold_and_wake(request, namespace, rg_name, target_service)
        finally:
            await self._set_active(namespace, rg_name, False)

    async def _hold_and_wake(self, request: web.Request, namespace: str, group: str, target_service: str) -> web.Response:
        result_future = asyncio.get_event_loop().create_future()
        body = await self._read_body(request)
        request_data = (request.method, request.path_qs or request.path, dict(request.headers), body)
        accepted = self.buffer.hold(namespace, group, result_future, request_data)
        if not accepted:
            return web.Response(status=503, text="too many queued requests, try again")

        if self.buffer.needs_scale_signal(namespace, group):
            key = (namespace, group)
            if key not in self._draining:
                self._draining.add(key)
                asyncio.create_task(self._trigger_wake(namespace, group, target_service))

        try:
            response = await asyncio.wait_for(result_future, timeout=60.0)
            return response
        except asyncio.TimeoutError:
            log.warning("wake timeout", group=group, namespace=namespace)
            return web.Response(status=504, text="replicagroup did not become ready in time")

    async def _trigger_wake(self, namespace: str, group: str, target_service: str):
        try:
            ready = await self.signaler.ensure_ready(namespace, group)
            if ready:
                entries, stored_request = self.buffer.release(namespace, group)
                target_ip = self.discovery.next_ip(namespace, target_service)
                if target_ip and entries:
                    method, path, headers, body = stored_request or ("GET", "/", {}, b"")
                    async def _dummy_read(body=body):
                        return body
                    dummy_req = web.Request(url=path, method=method, headers=headers)
                    dummy_req._cached_body = body
                    for future, _ in entries:
                        if not future.done():
                            resp = await self.forwarder.forward_streaming(
                                request=dummy_req,
                                target_ip=target_ip,
                            )
                            future.set_result(resp)
                elif not target_ip:
                    self._fail_held(namespace, group, "no ready workers after wake")
                log.info("wake complete, forwarded held requests", group=group, count=len(entries))
            else:
                self._fail_held(namespace, group, "wake failed - group not ready")
        except Exception as e:
            log.exception("wake failed", group=group, error=str(e))
            self._fail_held(namespace, group, f"wake error: {e}")
        finally:
            self._draining.discard((namespace, group))
            self.buffer.mark_signaled(namespace, group)

    def _fail_held(self, namespace: str, group: str, reason: str):
        entries = self.buffer.release(namespace, group)
        for future, _ in entries:
            if not future.done():
                future.set_exception(Exception(reason))
        log.warning("failed held requests", group=group, count=len(entries), reason=reason)

    async def _read_body(self, request: web.Request) -> bytes:
        try:
            return await request.read()
        except Exception:
            return b""


def main():
    discovery = EndpointDiscovery()
    buffer = RequestBuffer()
    forwarder = RequestForwarder(upstream_port=80)
    signaler = GroupSignaler(discovery)
    auth = TargetAuthorizer()
    server = ProxyServer(buffer, forwarder, signaler, discovery, auth)
    app = server.app

    async def on_startup(app):
        await server.start_background_tasks()

    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
