"""MyAgent — 多 agent 协作编码工具。

入口：python -m agents
"""


def run_repl():
    """延迟导入 REPL 入口，避免包导入时触发重依赖初始化。"""
    from agents.core.runtime import Runtime
    return Runtime().run()


__all__ = ["run_repl"]
