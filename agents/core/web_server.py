"""Web 服务启动 — FastAPI 应用创建、WebSocket 路由注册、前端静态文件挂载。

支持两种部署模式：
    开发：pip install -e .，前端 dist 在 {cwd}/frontend/dist
    PyInstaller：单文件二进制，前端 dist 在 sys._MEIPASS/frontend/dist
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from agents.core.container import MyAgentApp


class WebServer:
    """FastAPI 服务封装。"""

    def __init__(self):
        self._agent_app = MyAgentApp()

    # ======================== public ========================

    @staticmethod
    def main() -> None:
        """myagent 命令入口。支持 --version / -V 输出版本。"""
        if "--version" in sys.argv or "-V" in sys.argv:
            from agents import __version__
            print(f"myagent {__version__}")
            return
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

        application.add_api_websocket_route("/ws/chat", self._agent_app.handle)
        self._mount_frontend(application)
        return application

    def _run(self) -> None:
        """启动 uvicorn 服务进程。host/port 可通过环境变量覆盖。"""
        host = os.getenv("AGENT_HOST", "127.0.0.1")
        port = int(os.getenv("AGENT_PORT", "8000"))
        uvicorn.run(self._build_application(), host=host, port=port)

    @staticmethod
    def _mount_frontend(application: FastAPI) -> None:
        """按优先级查找前端构建产物并挂载到根路径。

        查找顺序：
        1. AGENT_FRONTEND_DIR 环境变量（显式覆盖）
        2. sys._MEIPASS/frontend/dist（PyInstaller 打包）
        3. {cwd}/frontend/dist（开发环境）
        """
        candidates = [
            os.getenv("AGENT_FRONTEND_DIR"),
            (Path(sys._MEIPASS) / "frontend" / "dist") if getattr(sys, "frozen", False) else None,
            Path.cwd() / "frontend" / "dist",
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                application.mount("/", StaticFiles(directory=str(candidate), html=True), name="frontend")
                return


if __name__ == "__main__":
    WebServer.main()
