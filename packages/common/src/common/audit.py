"""结构化审计事件(阶段 0 空壳)。

§9.2 / 红线 4:所有工具调用与助手域副作用必须产生审计事件;
日志结构化,必带 trace_id / tenant_id / user_id,且不得打印密钥、token、SQL 结果明细(§6)。

事件 schema 见 contracts/events/(阶段 1),发射实现见编排器(阶段 2)。
"""
