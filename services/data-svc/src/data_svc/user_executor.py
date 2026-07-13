"""用户执行代码的唯一接入点:run_sql(sql) -> pandas.DataFrame。

┌─────────────────────────────────────────────────────────────────────────┐
│ ★ 用户替换点 ★                                                          │
│ 把下方 run_sql 的函数体换成你自己的 GaussDB 连接/查询代码即可,           │
│ 签名不变(输入一条 SQL 字符串,返回 pandas DataFrame),其余零改动。       │
│ 启用方式:config/app.yml 设 FP_DATA_EXECUTOR: "user_func"。              │
│                                                                         │
│ 你的实现须满足(红线 6 第三保障落在执行侧):                             │
│  - 使用【只读】数据库账号连接;                                          │
│  - 会话设置 statement_timeout(本适配器的 timeout_ms 只能尽力而为);     │
│  - 原样执行传入 SQL,不拼接改写 —— 进来的 SQL 已过校验层                 │
│    (只读断言 + 表白名单 + RLS 租户谓词 + LIMIT),同时会收到             │
│    "EXPLAIN <sql>" 形式的干跑请求(GaussDB 支持 EXPLAIN)。              │
└─────────────────────────────────────────────────────────────────────────┘

当前为**占位实现**:进程内 DuckDB 内存库 + 3 张虚构表种子数据(口径与
assets/semantic-layer 示例一致),让「问句 → SQL → 执行 → DataFrame」全链路
在没有真实库的情况下可跑通(演示/联调/测试)。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import duckdb
import pandas as pd

from .executor import ExecResult, ExplainResult

# 占位种子数据(演示用,双租户 t1/t2;status 枚举与 knowledge/rules 一致)。
_DEMO_SEED = """
CREATE TABLE fund_plan (
    plan_id VARCHAR, tenant_id VARCHAR, org_id VARCHAR, period VARCHAR,
    plan_amount DECIMAL(18,2), exec_amount DECIMAL(18,2), currency VARCHAR, version VARCHAR
);
INSERT INTO fund_plan VALUES
    ('P1','t1','O1','2026Q1', 100.00,  60.00, 'CNY', 'v1'),
    ('P2','t1','O2','2026Q1', 200.00, 180.00, 'CNY', 'v1'),
    ('P3','t1','O1','2026Q2', 300.00,  90.00, 'CNY', 'v1'),
    ('P9','t2','O9','2026Q1', 500.00, 500.00, 'CNY', 'v1');

CREATE TABLE plan_subject (
    subject_id VARCHAR, tenant_id VARCHAR, plan_id VARCHAR,
    subject_code VARCHAR, subject_name VARCHAR, amount DECIMAL(18,2)
);
INSERT INTO plan_subject VALUES
    ('S1','t1','P1','1001','差旅',  40.00),
    ('S2','t1','P1','1002','物料',  60.00),
    ('S3','t1','P2','1001','差旅', 200.00),
    ('S9','t2','P9','1001','差旅', 500.00);

CREATE TABLE exec_flow (
    flow_id VARCHAR, tenant_id VARCHAR, plan_id VARCHAR,
    exec_date DATE, amount DECIMAL(18,2), status VARCHAR
);
INSERT INTO exec_flow VALUES
    ('F1','t1','P1', DATE '2026-01-10',  30.00, 'SUCCESS'),
    ('F2','t1','P1', DATE '2026-02-10',  30.00, 'SUCCESS'),
    ('F3','t1','P2', DATE '2026-01-20', 180.00, 'SUCCESS'),
    ('F4','t1','P3', DATE '2026-04-05',  90.00, 'FAILED'),
    ('F9','t2','P9', DATE '2026-01-15', 500.00, 'SUCCESS');
"""

_demo_lock = threading.Lock()
_demo_conn: duckdb.DuckDBPyConnection | None = None


def _demo_connection() -> duckdb.DuckDBPyConnection:
    global _demo_conn
    if _demo_conn is None:
        conn = duckdb.connect(":memory:")
        conn.execute(_DEMO_SEED)
        _demo_conn = conn
    return _demo_conn


def run_sql(sql: str) -> pd.DataFrame:
    """输入一条已校验 SQL,返回查询结果 DataFrame。

    ★★★ 从这里开始替换成你的 GaussDB 实现(签名不变) ★★★
    """
    with _demo_lock:  # 占位实现共享单连接;你的实现自行管理连接池/超时
        return _demo_connection().execute(sql).df()


def _to_python(value: Any) -> Any:
    """DataFrame 单元格 → JSON 可序列化的 Python 原生值(numpy 标量/日期归一)。"""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):  # 非标量(如序列)不做 isna 判定
        pass
    item = getattr(value, "item", None)  # numpy 标量
    if callable(item):
        return value.item()
    isoformat = getattr(value, "isoformat", None)  # date / datetime / Timestamp
    if callable(isoformat):
        return value.isoformat()
    return value  # Decimal 等按原样透传


class DataFrameFunctionExecutor:
    """把 run_sql(sql)->DataFrame 包装成 ReadOnlyExecutor(explain/execute)。

    explain 经同一函数执行 "EXPLAIN <sql>"(GaussDB / DuckDB 均支持),失败信息
    回流外层自纠;execute 计时并把 DataFrame 转为 ExecResult(columns/rows)。
    timeout_ms 无法对任意用户函数强制,只入文档约定(实现侧配 statement_timeout)。
    """

    def __init__(self, fn: Callable[[str], pd.DataFrame]) -> None:
        self._fn = fn

    def explain(self, sql: str) -> ExplainResult:
        try:
            self._fn(f"EXPLAIN {sql}")
        except Exception as exc:  # 干跑失败即自纠信号,取首行避免长堆栈入上下文
            message = str(exc) or type(exc).__name__
            return ExplainResult(ok=False, error=message.splitlines()[0])
        return ExplainResult(ok=True)

    def execute(self, sql: str, *, timeout_ms: int) -> ExecResult:
        start = time.perf_counter()
        df = self._fn(sql)
        columns = [str(c) for c in df.columns]
        rows = [[_to_python(v) for v in row] for row in df.itertuples(index=False, name=None)]
        return ExecResult(
            columns=columns, rows=rows, elapsed_ms=(time.perf_counter() - start) * 1000
        )
