"""code-svc 运行时模型(方案 §5.1)。所有"证据型"结果都带 file + 行号 + snippet。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")


class Definition(BaseModel):
    """一个符号定义(函数/类/方法/…)。file 为索引仓根下的相对 posix 路径。"""

    model_config = _FORBID

    name: str
    kind: str
    language: str
    file: str
    start_line: int  # 1-based
    end_line: int
    snippet: str


class Reference(BaseModel):
    """一个标识符引用出现(best-effort,按名过滤)。"""

    model_config = _FORBID

    name: str
    file: str
    line: int
    snippet: str


class CallEdge(BaseModel):
    """一条调用边:caller 定义体内调用了 callee(按名,跨文件不解析具体定义)。"""

    model_config = _FORBID

    caller: str  # 所在定义名,模块级为 "<module>"
    callee: str
    file: str
    line: int
    snippet: str


class SearchHit(BaseModel):
    """词法检索命中(Zoekt / ripgrep / python 三后端结构一致)。"""

    model_config = _FORBID

    file: str
    line: int
    snippet: str


class RepoMapEntry(BaseModel):
    model_config = _FORBID

    file: str
    name: str
    kind: str
    signature: str
    score: float


class RepoMap(BaseModel):
    """符号图度中心性排序后的仓库地图,可按 token 预算截断。"""

    model_config = _FORBID

    entries: list[RepoMapEntry] = Field(default_factory=list)
    total_symbols: int = 0
    truncated: bool = False


class FileSlice(BaseModel):
    """read_file 的行段返回(绝不返回整文件给主上下文)。"""

    model_config = _FORBID

    file: str
    start_line: int
    end_line: int
    text: str
