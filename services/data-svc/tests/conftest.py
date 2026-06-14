"""data-svc 测试夹具:语义层(真实 tables.yaml)+ 内存 DuckDB(3 虚构表,双租户 t1/t2)。"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from data_svc import DuckDBExecutor, SemanticLayer, SqlValidator

_TABLES_YAML = Path(__file__).parents[3] / "assets" / "semantic-layer" / "tables.yaml"

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
    ('F2','t1','P1','2026-02-10', 30.0,'done'),
    ('F9','t2','P9','2026-01-15',500.0,'done');
"""


@pytest.fixture
def semantic() -> SemanticLayer:
    return SemanticLayer.load(_TABLES_YAML)


@pytest.fixture
def validator(semantic: SemanticLayer) -> SqlValidator:
    return SqlValidator(semantic, max_rows=1000)


@pytest.fixture
def duck_conn() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(_SEED)
    return con


@pytest.fixture
def executor(duck_conn: duckdb.DuckDBPyConnection) -> DuckDBExecutor:
    return DuckDBExecutor(duck_conn)
