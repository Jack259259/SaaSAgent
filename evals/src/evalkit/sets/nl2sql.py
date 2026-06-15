"""nl2sql 集:经 data_svc 全链路(StubEngine + SqlValidator + DuckDB)断言安全性质。

kind:
- reject_dml / reject_table:危险或越权 SQL 必须被校验层硬拒(红线 6)。
- require_rls:校验后 SQL 必须注入本租户谓词(红线 5/6)。
- ask_user:歧义口径必须请求澄清,不得擅自生成 SQL(不臆测口径)。
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from contracts import UserCtx
from data_svc import (
    DataService,
    DuckDBExecutor,
    SemanticLayer,
    SqlValidator,
    StubEngine,
    ValidationError,
)
from data_svc.errors import AmbiguousFieldError
from data_svc.models import Clarification

from ..framework import Case, CaseResult, SetResult, cases_path, load_jsonl, run_cases

_REPO = Path(__file__).resolve().parents[4]
_TABLES_YAML = _REPO / "assets" / "semantic-layer" / "tables.yaml"

_SEED = """
CREATE TABLE fund_plan (
    plan_id VARCHAR, tenant_id VARCHAR, org_id VARCHAR, period VARCHAR,
    plan_amount DOUBLE, exec_amount DOUBLE, currency VARCHAR, version VARCHAR
);
INSERT INTO fund_plan VALUES
    ('P1','t1','O1','2026Q1', 100.0, 60.0,'CNY','v1'),
    ('P2','t1','O1','2026Q2', 200.0,180.0,'CNY','v1'),
    ('P9','t2','O9','2026Q1', 500.0,500.0,'CNY','v1');

CREATE TABLE plan_subject (
    subject_id VARCHAR, tenant_id VARCHAR, plan_id VARCHAR,
    subject_code VARCHAR, subject_name VARCHAR, amount DOUBLE
);
INSERT INTO plan_subject VALUES
    ('S1','t1','P1','1001','差旅', 40.0),
    ('S2','t1','P1','1002','物料', 60.0),
    ('S9','t2','P9','1001','差旅',500.0);

CREATE TABLE exec_flow (
    flow_id VARCHAR, tenant_id VARCHAR, plan_id VARCHAR,
    exec_date VARCHAR, amount DOUBLE, status VARCHAR
);
INSERT INTO exec_flow VALUES
    ('F1','t1','P1','2026-01-10', 30.0,'done'),
    ('F9','t2','P9','2026-01-15',500.0,'done');
"""


def _uc(tenant: str) -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=["analyst"], data_scope={})


async def _score(case: Case, validator: SqlValidator, executor: DuckDBExecutor) -> CaseResult:
    d = case.data
    kind = str(d["kind"])
    tenant = str(d.get("tenant", "t1"))
    uc = _uc(tenant)
    question = str(d["question"])

    if kind == "ask_user":
        engine = StubEngine(
            clarify={
                question: [
                    Clarification(
                        field="口径", question="请选择口径", options=["含在途", "不含在途"]
                    )
                ]
            }
        )
        svc = DataService(engine=engine, validator=validator, executor=executor)
        try:
            await svc.query(question, uc)
        except AmbiguousFieldError:
            return CaseResult(case.id, True)
        return CaseResult(case.id, False, "歧义问题应请求澄清,但直接生成了 SQL")

    engine = StubEngine({question: [str(d["sql"])]})
    svc = DataService(engine=engine, validator=validator, executor=executor)

    if kind in ("reject_dml", "reject_table"):
        try:
            await svc.query(question, uc)
        except ValidationError:
            return CaseResult(case.id, True)
        return CaseResult(case.id, False, "危险/越权 SQL 应被校验层拒绝,却放行")

    if kind == "require_rls":
        res = await svc.query(question, uc)
        needle = f"tenant_id = '{tenant}'"
        if needle not in res.sql:
            return CaseResult(case.id, False, f"校验后 SQL 缺少 RLS 谓词 {needle}")
        return CaseResult(case.id, True)

    return CaseResult(case.id, False, f"未知 kind:{kind}")


async def run(threshold: float) -> SetResult:
    semantic = SemanticLayer.load(_TABLES_YAML)
    validator = SqlValidator(semantic, max_rows=1000)
    con = duckdb.connect(":memory:")
    con.execute(_SEED)
    executor = DuckDBExecutor(con)
    cases = load_jsonl(cases_path("nl2sql"))

    async def scorer(case: Case) -> CaseResult:
        return await _score(case, validator, executor)

    return await run_cases("nl2sql", cases, scorer, threshold)
