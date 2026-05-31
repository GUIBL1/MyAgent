"""Web 服务启动 — FastAPI 应用创建、WebSocket 路由注册、前端静态文件挂载。"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agents.core.ws_handler import WsHandler


class WebServer:
    """FastAPI 服务封装。"""

    def __init__(self):
        self._ws_handler = WsHandler()

    # ======================== public ========================

    @staticmethod
    def main() -> None:
        """myagent 命令入口。"""
        WebServer()._run()

    # ======================== private ========================

    def _build_application(self) -> FastAPI:
        """构建 FastAPI 应用实例，注册 WebSocket 路由和静态文件。"""
        application = FastAPI(title="MyAgent")
        application.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        application.add_api_websocket_route("/ws/chat", self._ws_handler.handle)
        self._mount_frontend(application)
        return application

    def _run(self) -> None:
        """启动 uvicorn 服务进程。"""
        uvicorn.run(self._build_application(), host="127.0.0.1", port=8000)

    @staticmethod
    def _mount_frontend(application: FastAPI) -> None:
        """如果前端构建产物存在，挂载到根路径。"""
        frontend_dist = Path.cwd() / "frontend" / "dist"
        if frontend_dist.exists():
            application.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
