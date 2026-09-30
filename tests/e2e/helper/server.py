import asyncio
import os
import sys
from aiohttp import web

LOG_PREFIX = "[e2e-helper]"


async def handle_normal(request: web.Request) -> web.Response:
    return web.Response(text="ok", status=200)


async def handle_readiness(request: web.Request) -> web.Response:
    return web.Response(text="ready", status=200)


async def handle_slow_readiness(request: web.Request) -> web.Response:
    delay = int(os.environ.get("READINESS_DELAY", "15"))
    elapsed = request.app.get("uptime_seconds", lambda: 0)()
    remaining = max(0, delay - elapsed)
    if remaining > 0:
        return web.Response(
            text=f"not ready yet ({remaining}s remaining)",
            status=503,
        )
    return web.Response(text="ready", status=200)


async def handle_work(request: web.Request) -> web.Response:
    seconds = int(request.query.get("seconds", "20"))
    await asyncio.sleep(seconds)
    return web.Response(text=f"completed in {seconds}s", status=200)


async def handle_stream(request: web.Request) -> web.Response:
    seconds = int(request.query.get("seconds", "10"))
    interval = float(request.query.get("interval", "0.5"))
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/plain",
            "Cache-Control": "no-cache",
        },
    )
    await resp.prepare(request)
    for i in range(int(seconds / interval)):
        await resp.write(f"chunk {i}\n".encode())
        await asyncio.sleep(interval)
    await resp.write_eof()
    return resp


async def handle_healthz(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "mode": request.app["mode"]})


async def uptime_counter(app: web.Application):
    import time
    start = time.monotonic()
    app["uptime_seconds"] = lambda: time.monotonic() - start
    yield


def build_app(mode: str) -> web.Application:
    app = web.Application()
    app["mode"] = mode
    app.cleanup_ctx.append(uptime_counter)

    if mode == "normal":
        app.router.add_get("/", handle_normal)
        app.router.add_get("/readiness", handle_readiness)

    elif mode == "slow-start":
        app.router.add_get("/", handle_normal)
        app.router.add_get("/readiness", handle_slow_readiness)

    elif mode == "long-request":
        app.router.add_get("/", handle_normal)
        app.router.add_get("/readiness", handle_readiness)
        app.router.add_get("/work", handle_work)

    elif mode == "stream":
        app.router.add_get("/", handle_normal)
        app.router.add_get("/readiness", handle_readiness)
        app.router.add_get("/stream", handle_stream)

    elif mode == "all":
        app.router.add_get("/", handle_normal)
        app.router.add_get("/readiness", handle_readiness)
        app.router.add_get("/slow-readiness", handle_slow_readiness)
        app.router.add_get("/work", handle_work)
        app.router.add_get("/stream", handle_stream)

    else:
        print(f"{LOG_PREFIX} Unknown mode: {mode}, falling back to normal", file=sys.stderr)
        app = build_app("normal")

    app.router.add_get("/healthz", handle_healthz)
    return app


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("E2E_HELPER_MODE", "normal")
    port = int(os.environ.get("E2E_HELPER_PORT", "8080"))
    app = build_app(mode)
    print(f"{LOG_PREFIX} Starting in mode={mode} port={port}", flush=True)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
