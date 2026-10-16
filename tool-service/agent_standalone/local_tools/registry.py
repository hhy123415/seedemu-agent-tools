"""Local function definitions, validation and dispatch; no tool-service dependency."""

import asyncio
import inspect
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from pydantic import BaseModel


@dataclass
class ToolDefinition:
    name: str
    domain: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


# 工具在本目录内注册；参数先经 Pydantic 校验，再调用处理函数。
class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, definition, handler, arguments_model):
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        if not issubclass(arguments_model, BaseModel):
            raise TypeError("Tool arguments must use a Pydantic model")
        definition.input_schema = arguments_model.model_json_schema()
        self._tools[definition.name] = (definition, handler, arguments_model)

    def list_tools(self):
        return [self._tools[name][0] for name in sorted(self._tools)]

    async def invoke(self, name, arguments):
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        _, handler, model = self._tools[name]
        validated = model.model_validate(arguments).model_dump()
        if inspect.iscoroutinefunction(handler):
            return await handler(**validated)
        # 同步工具移到工作线程，避免阻塞聊天和浏览器的异步连接。
        return await asyncio.to_thread(partial(handler, **validated))
