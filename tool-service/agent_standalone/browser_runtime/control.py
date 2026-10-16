"""Connect to the browser source installed by the B02e scenario; no Docker mutation."""

import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = next(
    (
        parent / "seed-emulator/examples/internet/B02e_with_browser/output/browser_connection.json"
        for parent in ROOT.parents
        if (parent / "seed-emulator").is_dir()
    ),
    ROOT / "browser_connection.json",
)


# 从本地连接文件读取 B02e 地址，不在代码中固定连接凭据。
def connection_config():
    path = Path(os.environ.get("AGENT_BROWSER_CONFIG", str(DEFAULT_CONFIG)))
    try:
        data = json.loads(path.read_text())
        parsed = urlsplit(data["ws_endpoint"])
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError("Invalid browser connection settings")
        return data
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError(
            "找不到 B02e 浏览器连接配置；请先生成 B02e，"
            "或用 AGENT_BROWSER_CONFIG 指定 browser_connection.json"
        ) from error


def request_sync(method, path, payload=None):
    """Fetch generic noVNC assets; browser actions never use HTTP RPC."""
    if method != "GET" or not path.startswith("/novnc/"):
        raise ValueError("Only noVNC asset requests are supported")
    parsed = urlsplit(connection_config()["assets_url"])
    factory = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = factory(parsed.hostname, parsed.port, timeout=15)
    try:
        connection.request("GET", path.removeprefix("/novnc"))
        response = connection.getresponse()
        return response.status, response.read(4 * 1024 * 1024), dict(response.getheaders())
    finally:
        connection.close()


# 将已校验的工具请求交给 Agent 内部的浏览器运行时执行。
async def rpc(payload):
    # Lazy import keeps non-browser tools usable without starting Playwright.
    from .desktop import execute
    try:
        return await execute(payload)
    except Exception as error:
        from fastapi import HTTPException
        if isinstance(error, HTTPException):
            raise RuntimeError(error.detail) from None
        raise


def ensure_running(source=None):
    """Verify the authenticated WebSocket upgrade without creating a context."""
    config = connection_config()
    if source and source != config["source"]:
        raise ValueError("浏览器 source 与连接配置不匹配")
    parsed = urlsplit(config["ws_endpoint"])
    factory = http.client.HTTPSConnection if parsed.scheme == "wss" else http.client.HTTPConnection
    connection = factory(parsed.hostname, parsed.port, timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    expected = base64.b64encode(hashlib.sha1(
        (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
    ).digest()).decode()
    try:
        connection.request("GET", parsed.path, headers={
            "Connection": "Upgrade", "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": key,
        })
        response = connection.getresponse()
        if response.status != 101 or response.getheader("Sec-WebSocket-Accept") != expected:
            raise RuntimeError("B02e Playwright 服务鉴权失败，请重新生成场景连接配置")
    except OSError:
        raise RuntimeError("B02e 浏览器服务不可达，请确认场景已启动") from None
    finally:
        connection.close()
    return {"ready": True, "source": config["source"]}
