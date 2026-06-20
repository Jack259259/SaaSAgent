"""红线 1 / 12:架构守卫 —— 运行时无编排框架依赖、无裸 Bash/全局 FS 原语。

红线 1:禁止引入 LangGraph/LangChain/CrewAI 等编排框架依赖(编排循环自研、薄)。
红线 12:运行时主 Agent 不持有裸 Bash / 全局文件读写 / 全局 grep;文件访问只经工作区句柄。

这两条此前只靠人评,无自动守卫。本测试把"约定"固化为门禁:新增上述依赖或裸原语工具即红。
"""

from __future__ import annotations

import importlib.util

import pytest

from orchestrator import ToolRegistry, base_tool_handlers

# 编排框架(红线 1):任一可被 import 即说明已进依赖树。
_FORBIDDEN_FRAMEWORKS = [
    "langchain",
    "langchain_core",
    "langgraph",
    "crewai",
    "llama_index",
    "autogen",
]

# 裸原语(红线 12):运行时注册表绝不应暴露这些名字。
_FORBIDDEN_TOOL_NAMES = {
    "bash",
    "shell",
    "sh",
    "exec",
    "system",
    "run_command",
    "grep",
    "read_file",
    "write_file",
    "glob",
    "open_file",
}


@pytest.mark.parametrize("module", _FORBIDDEN_FRAMEWORKS)
def test_no_orchestration_framework_installed(module: str) -> None:
    assert importlib.util.find_spec(module) is None, f"红线 1:禁止引入编排框架依赖 {module}"


def test_runtime_registry_has_no_raw_shell_or_global_fs_tool() -> None:
    registry = ToolRegistry()
    registry.register_from_contracts(base_tool_handlers())
    names = {spec.name for spec in registry.specs()}

    leaked = names & _FORBIDDEN_TOOL_NAMES
    assert not leaked, f"红线 12:运行时不得暴露裸原语:{sorted(leaked)}"
    # 文件访问只经工作区句柄(虚拟、租户隔离),不是全局读写。
    assert {"read_workspace", "write_workspace"} <= names
