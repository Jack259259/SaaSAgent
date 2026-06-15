"""rag-qa 集:RagService(临时索引 stage-5 fixtures)断言 grounding / ACL / 无据拒答。

kind:
- grounded:检索须命中期望来源(RuleJudge 检查引用来源含关键短语)。
- acl_negative:越权来源绝不出现在引用中(红线 5/9)。
- refuse:零可见证据时必须拒答"未在知识库中找到依据",不臆造(无据不答)。
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

from contracts import UserCtx
from rag_svc import RagService, acl
from rag_svc.ingest import ingest_dir

from ..framework import Case, CaseResult, SetResult, cases_path, load_jsonl, run_cases
from ..judge import RuleJudge

_FIXTURES = (
    Path(__file__).resolve().parents[4]
    / "services"
    / "rag-svc"
    / "tests"
    / "fixtures"
    / "knowledge"
)
_NO_EVIDENCE = "未在知识库中找到依据。"


def _uc(roles: Sequence[str], tenant: str) -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=list(roles), data_scope={})


class _Fixtures:
    """两套服务:main(business+it_design 三公共片段)、acme(t_acme 私有片段)。"""

    def __init__(self, main: RagService, acme: RagService) -> None:
        self.main = main
        self.acme = acme

    def service(self, name: str) -> RagService:
        return self.main if name == "main" else self.acme


async def _build_fixtures(workdir: Path) -> _Fixtures:
    main_dir = workdir / "main"
    await ingest_dir(kb=acl.KB_BUSINESS, src=_FIXTURES, store_dir=main_dir)
    await ingest_dir(kb=acl.KB_IT_DESIGN, src=_FIXTURES, store_dir=main_dir)

    acme_src = workdir / "acme_src"
    acme_src.mkdir(parents=True)
    (acme_src / "private.md").write_text(
        "---\nsource: 客户ACME/专属口径\nacl_tags: [tenant]\n---\nACME 专属执行率口径说明。\n",
        encoding="utf-8",
    )
    acme_dir = workdir / "acme"
    await ingest_dir(kb=acl.KB_BUSINESS, src=acme_src, store_dir=acme_dir, tenant="t_acme")
    return _Fixtures(RagService.from_dir(main_dir), RagService.from_dir(acme_dir))


async def _score(case: Case, fx: _Fixtures, judge: RuleJudge) -> CaseResult:
    d = case.data
    kind = str(d["kind"])
    svc = fx.service(str(d.get("store", "main")))
    uc = _uc(d["roles"], str(d.get("tenant", "t")))
    result = await svc.search_knowledge(uc, str(d["question"]), kb=str(d["kb"]), top_k=10)
    sources = "; ".join(c.source for c in result.citations)

    if kind == "grounded":
        ok, detail = await judge.grade(answer=sources, must_include=list(d["expect_sources"]))
        return CaseResult(case.id, ok, detail)

    if kind == "acl_negative":
        leaked = [s for s in d["forbid_sources"] if s in sources]
        if leaked:
            return CaseResult(case.id, False, f"越权来源泄漏:{leaked}")
        return CaseResult(case.id, True)

    if kind == "refuse":
        if result.citations or result.summary != _NO_EVIDENCE:
            return CaseResult(case.id, False, f"零证据应拒答,却返回:{result.summary}")
        return CaseResult(case.id, True)

    return CaseResult(case.id, False, f"未知 kind:{kind}")


async def run(threshold: float) -> SetResult:
    judge = RuleJudge()
    with tempfile.TemporaryDirectory() as tmp:
        fx = await _build_fixtures(Path(tmp))
        cases = load_jsonl(cases_path("rag-qa"))

        async def scorer(case: Case) -> CaseResult:
            return await _score(case, fx, judge)

        return await run_cases("rag-qa", cases, scorer, threshold)
