"""浏览器工具执行与对话会话管理。"""

import asyncio
import uuid

from browser_runtime.control import ensure_running, rpc

# 同一桌面只分配给一个活动对话，避免多个 Agent 同时操作。
start_lock = asyncio.Lock()
current_owner = None


# 管理对话持有的浏览器连接、心跳与画面连接的生命周期。
class BrowserSession:
    def __init__(self, source=None):
        self.owner = uuid.uuid4().hex
        self.source = source
        self.connected = False
        self.action_lock = asyncio.Lock()
        self.viewers = set()
        self.heartbeat = None

    async def connect(self, source=None):
        global current_owner
        async with start_lock:
            if current_owner and current_owner != self.owner:
                raise RuntimeError("浏览器正在被另一个对话使用，请先关闭其浏览器")
            source = source or self.source
            if self.connected:
                if source != self.source:
                    raise ValueError("更换 source 前请关闭浏览器并新建对话")
                return self.status()
            health = await asyncio.to_thread(ensure_running, source)
            source = health["source"]
            await rpc({"owner": self.owner, "action": "acquire"})
            self.source = source
            self.connected = True
            current_owner = self.owner
            self.heartbeat = asyncio.create_task(self.keep_alive())
            return self.status()

    # 定期续租，防止模型思考期间会话因空闲而被回收。
    async def keep_alive(self):
        while True:
            await asyncio.sleep(10)
            try:
                await rpc({"owner": self.owner, "action": "heartbeat"})
            except Exception:
                # An action will surface the connection error to the user.
                pass

    def status(self):
        return {
            "type": "browser",
            "connected": self.connected,
            "token": self.owner,
            "source": self.source,
        }

    async def invoke(self, **arguments):
        async with self.action_lock:
            if not self.connected:
                await self.connect()
            return await rpc({"owner": self.owner, **arguments})

    async def disconnect_viewers(self):
        for viewer in tuple(self.viewers):
            try:
                await viewer.close(code=1000)
            except Exception:
                pass
        self.viewers.clear()

    async def close(self):
        global current_owner
        if self.heartbeat:
            self.heartbeat.cancel()
            self.heartbeat = None
        await self.disconnect_viewers()
        async with self.action_lock:
            try:
                if self.connected:
                    await rpc({"owner": self.owner, "action": "release"})
            finally:
                if current_owner == self.owner:
                    current_owner = None
                self.connected = False
