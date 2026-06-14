# pipelines/sop-replay — SOP 回放(漂移检测 / E2E 回归)

实现位于 `services/sop-executor/src/sop_executor/replay.py`(sop-executor 是 workspace 包;
`pipelines/` 非 Python 包,逻辑落服务内,此处仅作入口指引)。

```bash
uv run python -m sop_executor.replay assets/sops [--base-url <预发地址>]
make eval E=sop-replay
```

行为:回放 `assets/sops` 全量 SOP(auto-confirm,executor 跑完整状态机)→ postconditions 通过则 OK;
任一失败写 `<id>.stale` 标记并以非零码退出(Agent 侧据此下线该操作 + 告警,见方案 §5.4 漂移检测)。
**无 `--base-url`** 用内置 `demo_mock`(hermetic CI);给 `--base-url` 则对真实预发回放。
这套回放同时是 E2E 回归集;生产建议 CI 每晚执行。`.stale` 文件被 .gitignore 忽略,不入库。
