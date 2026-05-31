#!/usr/bin/env python3
"""包入口 — python -m agents 启动 Web 服务。"""

from agents.core.web_server import WebServer

if __name__ == "__main__":
    WebServer.main()
