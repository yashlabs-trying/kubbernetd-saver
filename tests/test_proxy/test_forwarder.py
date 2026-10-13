"""Regression tests for the proxy RequestForwarder.

The k8s-e2e proxy crash-looped because ``RequestForwarder.__init__`` built an
``aiohttp.TCPConnector`` before the event loop existed; aiohttp >= 3.14 calls
``asyncio.get_running_loop()`` and raised ``RuntimeError: no running event loop``.
The session must therefore be created lazily, inside the loop.
"""
import asyncio

from kubbernetd.proxy.forwarder import RequestForwarder


def test_forwarder_constructs_without_running_loop():
    # Must not raise outside an event loop.
    forwarder = RequestForwarder(upstream_port=80)
    assert forwarder._session is None


def test_forwarder_creates_session_inside_loop():
    forwarder = RequestForwarder(upstream_port=80)

    async def run():
        session = forwarder._get_session()
        assert session is not None
        assert not session.closed
        # Idempotent: same session reused.
        assert forwarder._get_session() is session
        await forwarder.close()

    asyncio.run(run())


def test_forwarder_close_without_session_is_safe():
    forwarder = RequestForwarder(upstream_port=80)
    asyncio.run(forwarder.close())
