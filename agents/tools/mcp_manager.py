#!/usr/bin/env python3
"""
mcp_manager.py

MCP 服务器连接管理模块。

对外提供 MCPManager 类，负责加载配置、管理与 MCP 服务器子进程的通信。
每个 MCP 服务器对应一个 MCPServerConnection 实例，各自维护独立 asyncio event loop。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import threading
from pathlib import Path
from typing import Callable
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPServerConnection:
    """管理单个 MCP 服务器子进程连接的生命周期。

    所有异步操作在独立的 daemon 线程中运行，避免与 uvicorn 的主 event loop 冲突。
    """

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ):
        self._server_name = server_name
        self._command = command
        self._args = args
        self._env = env
        self._event_loop = asyncio.new_event_loop()
        self._event_loop_thread = threading.Thread(
            target=self._event_loop.run_forever, daemon=True
        )
        self._event_loop_thread.start()
        self._session: ClientSession | None = None
        self._stdio_context = None
        self._stdio_read = None
        self._stdio_write = None

    # ======================== public ========================

    def initialize(self) -> None:
        """启动子进程并完成 MCP 协议握手。"""
        self._run_in_event_loop(self._async_initialize())

    def list_tools(self) -> list:
        """获取服务器声明的工具列表。"""
        return self._run_in_event_loop(self._async_list_tools())

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """同步调用 MCP 工具，返回字符串结果。"""
        try:
            return self._run_in_event_loop(
                self._async_call_tool(tool_name, arguments)
            )
        except Exception as exc:
            return f"Tool mcp__{self._server_name}__{tool_name} execution error: {exc}"

    def list_resources(self) -> list:
        """获取服务器声明的资源列表。"""
        return self._run_in_event_loop(self._async_list_resources())

    def list_resource_templates(self) -> list:
        """获取服务器声明的资源模板列表（含 uriTemplate）。"""
        return self._run_in_event_loop(self._async_list_resource_templates())

    def read_resource(self, uri: str) -> str:
        """同步读取 MCP 资源，返回字符串结果。"""
        try:
            return self._run_in_event_loop(self._async_read_resource(uri))
        except Exception as exc:
            return f"MCP '{self._server_name}' read_resource error: {exc}"

    def list_prompts(self) -> list:
        """获取服务器声明的提示词模板列表。"""
        return self._run_in_event_loop(self._async_list_prompts())

    def get_prompt(self, prompt_name: str, arguments: dict | None = None) -> str:
        """同步获取 MCP 提示词模板，返回字符串结果。"""
        try:
            return self._run_in_event_loop(
                self._async_get_prompt(prompt_name, arguments or {})
            )
        except Exception as exc:
            return f"MCP '{self._server_name}' get_prompt error: {exc}"

    def shutdown(self) -> None:
        """关闭连接并终止子进程。"""
        try:
            self._run_in_event_loop(self._async_shutdown())
        except Exception:
            pass
        finally:
            try:
                self._event_loop.call_soon_threadsafe(self._event_loop.stop)
                self._event_loop_thread.join(timeout=5)
                self._event_loop.close()
            except Exception:
                pass

    # ======================== private ========================

    def _run_in_event_loop(self, coroutine):
        """将协程提交到独立线程的 event loop 中执行，阻塞等待结果。"""
        future = asyncio.run_coroutine_threadsafe(coroutine, self._event_loop)
        return future.result(timeout=300)

    # ======================== private ========================

    async def _async_initialize(self) -> None:
        """异步连接与握手。"""
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env={**os.environ, **(self._env or {})},
        )
        self._stdio_context = stdio_client(server_params)
        self._stdio_read, self._stdio_write = await self._stdio_context.__aenter__()
        self._session = ClientSession(self._stdio_read, self._stdio_write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def _async_list_tools(self) -> list:
        """异步获取工具列表。"""
        if self._session is None:
            return []
        result = await self._session.list_tools()
        return list(result.tools)

    async def _async_call_tool(self, tool_name: str, arguments: dict) -> str:
        """异步调用工具并格式化结果。"""
        if self._session is None:
            return f"MCP '{self._server_name}' error: session not initialized."

        result = await self._session.call_tool(tool_name, arguments)

        text_parts = []
        is_error = getattr(result, "isError", False)
        for block in result.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)

        if not text_parts and result.content:
            output = "(non-text content returned)."
        else:
            output = "\n".join(text_parts)
        if is_error:
            return f"Tool mcp__{self._server_name}__{tool_name} execution error: {output}."
        return output

    async def _async_list_resources(self) -> list:
        """异步获取资源列表。"""
        if self._session is None:
            return []
        result = await self._session.list_resources()
        return list(result.resources)

    async def _async_list_resource_templates(self) -> list:
        """异步获取资源模板列表。"""
        if self._session is None:
            return []
        result = await self._session.list_resource_templates()
        return list(result.resourceTemplates)

    async def _async_read_resource(self, uri: str) -> str:
        """异步读取资源内容。"""
        if self._session is None:
            return f"MCP '{self._server_name}' error: session not initialized."
        result = await self._session.read_resource(uri)
        text_parts = []
        for content_block in result.contents:
            if hasattr(content_block, "text"):
                text_parts.append(content_block.text)
        return "\n".join(text_parts) if text_parts else "(non-text content returned)."

    async def _async_list_prompts(self) -> list:
        """异步获取提示词模板列表。"""
        if self._session is None:
            return []
        result = await self._session.list_prompts()
        return list(result.prompts)

    async def _async_get_prompt(self, prompt_name: str, arguments: dict) -> str:
        """异步获取提示词模板内容。"""
        if self._session is None:
            return f"MCP '{self._server_name}' error: session not initialized."
        result = await self._session.get_prompt(prompt_name, arguments)
        text_parts = []
        for message in result.messages:
            if hasattr(message.content, "text"):
                text_parts.append(message.content.text)
            elif isinstance(message.content, str):
                text_parts.append(message.content)
            else:
                text_parts.append(str(message.content))
        return "\n".join(text_parts) if text_parts else "(empty prompt)."

    async def _async_shutdown(self) -> None:
        """异步清理会话与流。"""
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._stdio_context is not None:
            await self._stdio_context.__aexit__(None, None, None)
            self._stdio_context = None
            self._stdio_read = None
            self._stdio_write = None






class MCPManager:
    """MCP 连接管理器，负责加载配置、初始化所有服务器连接并暴露工具接口。"""

    def __init__(self, mcp_enabled: bool, mcp_servers_config_path: Path):
        self._mcp_enabled = mcp_enabled
        self._mcp_config_path = mcp_servers_config_path
        self._connections: dict[str, MCPServerConnection] = {}
        self._tool_schemas: dict[str, dict] = {}
        self._tool_handlers: dict[str, Callable] = {}

        self._initialize()
        atexit.register(self._shutdown)

    # ======================== public ========================

    def get_tool_schemas(self) -> list[dict]:
        """返回所有 MCP 工具 schema 列表。"""
        return list(self._tool_schemas.values())

    def get_tool_handlers(self) -> dict[str, Callable]:
        """返回工具名到处理函数的映射字典。"""
        return self._tool_handlers

    def shutdown(self) -> None:
        """显式关闭所有 MCP 连接（atexit 也会自动调用）。"""
        self._shutdown()

    # ======================== private ========================

    def _initialize(self) -> None:
        """从配置文件加载 MCP 服务器列表并初始化所有连接。"""
        if not self._mcp_enabled:
            return

        server_configs = self._load_servers_config()
        if not server_configs:
            print("[MCP] AGENT_MCP_ENABLED=true but no servers configured.")
            return

        for server_name, server_config in server_configs.items():
            command = server_config.get("command")
            if not command:
                print(f"[MCP] Server '{server_name}' missing 'command', skipped.")
                continue

            args = server_config.get("args", [])
            env = server_config.get("env")

            try:
                connection = MCPServerConnection(server_name, command, args, env)
                connection.initialize()
            except Exception as exc:
                print(f"[MCP] Failed to connect '{server_name}': {exc}")
                continue

            try:
                server_tools = connection.list_tools()
            except Exception as exc:
                print(f"[MCP] Failed to list tools for '{server_name}': {exc}")
                connection.shutdown()
                continue

            for mcp_tool in server_tools:
                namespaced_name = f"mcp__{server_name}__{mcp_tool.name}"
                self._tool_schemas[namespaced_name] = {
                    "name": namespaced_name,
                    "description": f"[MCP:{server_name}] {mcp_tool.description or ''}",
                    "input_schema": mcp_tool.inputSchema,
                }
                # 默认参数捕获循环变量，避免闭包延迟绑定
                self._tool_handlers[namespaced_name] = (
                    lambda connection=connection, tool_name=mcp_tool.name, **kw: connection.call_tool(
                        tool_name, kw
                    )
                )

            # 注册 resource 读取能力（含静态资源 + 参数化模板）
            try:
                resources = connection.list_resources()
            except Exception:
                resources = []
            try:
                templates = connection.list_resource_templates()
            except Exception:
                templates = []

            if resources or templates:
                resource_lines = []
                resource_uris: list[str] = []
                for r in resources:
                    resource_uris.append(str(r.uri))
                    name = getattr(r, "name", "") or str(r.uri)
                    mime = getattr(r, "mimeType", "") or ""
                    line = f"  - {name} ({r.uri})"
                    if mime:
                        line += f" [{mime}]"
                    if getattr(r, "description", ""):
                        line += f": {r.description}"
                    resource_lines.append(line)
                for t in templates:
                    resource_uris.append(str(t.uriTemplate))
                    name = getattr(t, "name", "") or str(t.uriTemplate)
                    mime = getattr(t, "mimeType", "") or ""
                    line = f"  - {name} (template: {t.uriTemplate})"
                    if mime:
                        line += f" [{mime}]"
                    if getattr(t, "description", ""):
                        line += f": {t.description}"
                    resource_lines.append(line)
                schema_name = f"mcp__{server_name}__read_resource"
                self._tool_schemas[schema_name] = {
                    "name": schema_name,
                    "description": (
                        f"[MCP:{server_name}] Read a resource by URI. "
                        "Format: name (uri|template: pattern) [mimeType]: description\n"
                        + "\n".join(resource_lines)
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "uri": {
                                "type": "string",
                                "description": "Resource URI to read. One of: "
                                + ", ".join(resource_uris),
                            },
                        },
                        "required": ["uri"],
                    },
                }
                self._tool_handlers[schema_name] = (
                    lambda connection=connection, **kw: connection.read_resource(kw["uri"])
                )

            # 注册 prompt 获取能力
            try:
                prompts = connection.list_prompts()
            except Exception:
                prompts = []
            if prompts:
                prompt_lines = []
                for p in prompts:
                    line = f"  - {p.name}"
                    if getattr(p, "description", ""):
                        line += f": {p.description}"
                    args = getattr(p, "arguments", None)
                    if args:
                        arg_parts = []
                        for a in args:
                            a_name = getattr(a, "name", "?")
                            a_req = getattr(a, "required", None)
                            part = f"{a_name}(required={a_req})"
                            if getattr(a, "description", ""):
                                part += f": {a.description}"
                            arg_parts.append(part)
                        line += " [arguments: " + ", ".join(arg_parts) + "]"
                    prompt_lines.append(line)
                schema_name = f"mcp__{server_name}__get_prompt"
                self._tool_schemas[schema_name] = {
                    "name": schema_name,
                    "description": (
                        f"[MCP:{server_name}] Get a prompt template by name. "
                        "Format: name: description [arguments: name(required=bool): description, ...]\n"
                        + "\n".join(prompt_lines)
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "prompt_name": {
                                "type": "string",
                                "description": "Prompt template name to retrieve. One of: "
                                + ", ".join(str(p.name) for p in prompts),
                            },
                        },
                        "required": ["prompt_name"],
                    },
                }
                self._tool_handlers[schema_name] = (
                    lambda connection=connection, **kw: connection.get_prompt(
                        kw["prompt_name"],
                    )
                )

            self._connections[server_name] = connection
            print(
                f"[MCP] Server '{server_name}' initialized: "
                f"{len(server_tools)} tool(s), {len(resources)} resource(s), {len(templates)} resource_template(s), {len(prompts)} prompt(s)."
            )

        if self._connections:
            print(f"[MCP] Total: {len(self._connections)} server(s), {len(self._tool_schemas)} capability(s) registered.")

    def _shutdown(self) -> None:
        """安全关闭所有 MCP 连接。"""
        for server_name, connection in self._connections.items():
            try:
                connection.shutdown()
            except Exception as exc:
                print(f"[MCP] Server '{server_name}' shutdown error: {exc}")

    def _load_servers_config(self) -> dict:
        """加载 mcp_servers.json 配置。"""
        if not self._mcp_config_path.exists():
            return {}
        try:
            config_data = json.loads(self._mcp_config_path.read_text(encoding="utf-8"))
            return config_data.get("mcp_servers", {})
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[MCP] Config parse error: {exc}")
            return {}
