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

PKGS := packages/common \
        services/agent-gateway services/orchestrator services/rag-svc services/data-svc \
        services/code-svc services/sop-executor services/memory-svc services/reflection-worker \
        services/sandbox-svc services/scheduler-svc

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

dev:
	@echo "make dev: NOT IMPLEMENTED (see PROGRESS.md)"
	@exit 2

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

contract-test:
	@echo "make contract-test: NOT IMPLEMENTED (see PROGRESS.md)"
	@exit 2

# E 必须是 EVAL_SETS 之一;缺失/非法以退出码 1 给出 usage(尚未实现的真实 runner 以退出码 2)。
eval:
ifeq ($(filter $(E),$(EVAL_SETS)),)
	@echo "usage: make eval E=<nl2sql|rag-qa|code-qa|sop-replay|e2e>"
	@exit 1
else
	@echo "make eval E=$(E): NOT IMPLEMENTED (see PROGRESS.md)"
	@exit 2
endif

sop-validate:
	@echo "make sop-validate: NOT IMPLEMENTED (see PROGRESS.md)"
	@exit 2
