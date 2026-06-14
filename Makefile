# 资金计划 Agent —— 统一任务接口(CLAUDE.md §4;一律使用这些命令,不要自行发明)。
# Windows:请在 Git Bash 中执行 make(SHELL=bash)。
# 重要:Windows 版 GNU Make 向 bash 传递配方时对非 ASCII(中文)字符的引用有缺陷,
#       会造成引号失配而报错;因此**所有配方行(recipe)内的 echo 一律用英文**,
#       中文只写在注释里(注释不传给 shell,安全)。
# 尚未到实现阶段的命令打印 "NOT IMPLEMENTED (see PROGRESS.md)" 并以退出码 2 结束;
# 阶段归属:contract-test=阶段1,dev=阶段2+,sop-validate=阶段8,eval=阶段10(见 PROGRESS.md)。

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-print-directory

UV ?= uv

# 自动发现全部工作区包(packages/* + services/*),新增包无需再改此处。
PKGS := $(wildcard packages/*) $(wildcard services/*)

MYPY_PATHS := $(foreach p,$(PKGS),$(p)/src $(p)/tests)

EVAL_SETS := nl2sql rag-qa code-qa sop-replay e2e

.PHONY: help sync dev test lint contract-test eval sop-validate
.DEFAULT_GOAL := help

help:
	@echo "make dev             # start local deps (docker compose) + all services [stage 2+]"
	@echo "make test            # run all unit tests; scope: make test SVC=data-svc"
	@echo "make lint            # ruff format --check + ruff check + mypy --strict"
	@echo "make contract-test   # contract tests [stage 1]"
	@echo "make eval E=nl2sql   # eval regression (nl2sql|rag-qa|code-qa|sop-replay|e2e) [stage 10]"
	@echo "make sop-validate    # assets/sops schema + static cross-checks [stage 8]"

sync:
	$(UV) sync --all-packages

# 启动 agent-gateway(阶段 2)。本地依赖(postgres/langfuse,docker compose)后续阶段再接入。
dev: sync
	$(UV) run uvicorn agent_gateway.app:app --host 127.0.0.1 --port 8080

# 全部单测;限定单个服务:make test SVC=data-svc(未知服务以退出码 1 失败)。
test: sync
ifdef SVC
	@test -d "services/$(SVC)" || { echo "unknown service: services/$(SVC)"; exit 1; }
	$(UV) run pytest services/$(SVC)
else
	$(UV) run pytest
endif

lint: sync
	$(UV) run ruff format --check .
	$(UV) run ruff check .
	$(UV) run mypy $(MYPY_PATHS)

# contracts 契约测试(阶段 1 真实现):21 份工具规格合法 + 信封 user_ctx 负例 +
# AgentState/audit/SOP 正反例 + 模型↔schema 一致性 + docs 不漂移。
contract-test: sync
	$(UV) run pytest packages/contracts

# E 必须是 EVAL_SETS 之一;缺失/非法以退出码 1 给出 usage(尚未实现的真实 runner 以退出码 2)。
# sop-replay(阶段 8 真实现):回放 assets/sops 全量,失败标 <id>.stale。
eval: sync
ifeq ($(filter $(E),$(EVAL_SETS)),)
	@echo "usage: make eval E=<nl2sql|rag-qa|code-qa|sop-replay|e2e>"
	@exit 1
else ifeq ($(E),sop-replay)
	$(UV) run python -m sop_executor.replay assets/sops
else
	@echo "make eval E=$(E): NOT IMPLEMENTED (see PROGRESS.md)"
	@exit 2
endif

# assets/sops schema 校验 + 静态交叉校验(阶段 8 真实现)。
sop-validate: sync
	$(UV) run python -m sop_executor.sopcheck assets/sops
