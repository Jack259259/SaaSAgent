"""code-qa 集:CodeService(临时索引 sample_repo)逐例核对证据(file / 符号)。

kind:find_definition / find_callers / find_references / search_code;断言返回证据命中期望
文件或符号(检索正确性,不喂标准答案)。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from code_svc import CodeService, FileReader, PythonSearch, SymbolStore, index_repos

from ..framework import Case, CaseResult, SetResult, cases_path, load_jsonl, run_cases

_SAMPLE = (
    Path(__file__).resolve().parents[4]
    / "services"
    / "code-svc"
    / "tests"
    / "fixtures"
    / "sample_repo"
)


def _files(rows: list[dict[str, object]]) -> set[str]:
    return {str(r["file"]) for r in rows}


async def _score(case: Case, svc: CodeService) -> CaseResult:
    d = case.data
    kind = str(d["kind"])
    target = str(d["target"])

    if kind == "find_definition":
        rows = [x.model_dump() for x in svc.find_definition(target)]
        hit = _files(rows) & set(d["expect_files"])
        return CaseResult(case.id, bool(hit), "" if hit else f"定义未落在 {d['expect_files']}")

    if kind == "find_callers":
        rows = [x.model_dump() for x in svc.find_callers(target)]
        callers = {str(r["caller"]) for r in rows}
        missing = set(d["expect_symbols"]) - callers
        return CaseResult(case.id, not missing, "" if not missing else f"缺调用者 {missing}")

    if kind == "find_references":
        rows = [x.model_dump() for x in svc.find_references(target)]
        hit = _files(rows) & set(d["expect_files"])
        return CaseResult(case.id, bool(hit), "" if hit else f"引用未落在 {d['expect_files']}")

    if kind == "search_code":
        rows = [x.model_dump() for x in svc.search_code(target)]
        if len(rows) < int(d.get("min_hits", 1)):
            return CaseResult(case.id, False, f"命中数 {len(rows)} 不足")
        hit = _files(rows) & set(d["expect_files"])
        return CaseResult(case.id, bool(hit), "" if hit else f"命中未含 {d['expect_files']}")

    return CaseResult(case.id, False, f"未知 kind:{kind}")


async def run(threshold: float) -> SetResult:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "symbols.db"
        index_repos(repos_root=_SAMPLE, db_path=db)
        svc = CodeService(
            repos_root=_SAMPLE,
            store=SymbolStore(db),
            search=PythonSearch(_SAMPLE, [_SAMPLE]),
            reader=FileReader(_SAMPLE),
        )
        cases = load_jsonl(cases_path("code-qa"))

        async def scorer(case: Case) -> CaseResult:
            return await _score(case, svc)

        try:
            return await run_cases("code-qa", cases, scorer, threshold)
        finally:
            svc.close()
