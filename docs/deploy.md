# 部署与本地运行(内嵌前端 web/)

内嵌前端在后端仓 `web/`(原生 HTML/CSS + Alpine,零构建)。**同源同部署**:部署 agent-gateway 即带上前端,前端用相对路径调同源 API,无 CORS、无 baseURL 注入。

## 本地一键(真实后端 + 前端)

```bash
# Git Bash;FP_DEV_STUB=1 启用离线开发桩 provider(无需 LLM_API_KEY 即可产出真实 SSE 轮次)
FP_DEV_STUB=1 make dev
# 浏览器打开:
# http://127.0.0.1:8080/
```

- agent-gateway 在 API 路由之后挂载 `web/` 静态伺服 + SPA 回退(`app.py` 的 `serve_web`,目录穿越安全);`/chat`、`/chat/confirm`、`/healthz`、(未来)`/files` 优先于静态匹配。
- 前端通过探测 `/healthz` 发现真实后端 → **自动关闭 mock**,直连真实 `/chat`(`mock-sse.js`)。
- 身份:开发态前端注入 `X-User-Ctx`(§12-D4);生产应由网关验短时令牌签发 user_ctx(`auth.py` 已标 TODO)。

## 大模型(LLM)配置(config/llm.yml)

LLM 的 **接口格式 / url / api_key / model** 集中在 `config/llm.yml`(由 agent-gateway `get_provider` 读取;路径可经 `FP_LLM_CONFIG` 覆盖)。**密钥不入库**:仓内只提交模板 `config/llm.yml.example`,真实 `config/llm.yml` 已 gitignore。

```bash
cp config/llm.yml.example config/llm.yml   # 然后填入真实值
make dev                                    # 浏览器 http://127.0.0.1:8080/
```

| 字段 | 作用 | 默认 / 回退 |
|---|---|---|
| `LLM_Interface_Format` | 接口格式 `Anthropic` / `OpenAI`(大小写不敏感);两格式共用下面字段 | `Anthropic`(环境 `LLM_INTERFACE_FORMAT`);非法值启动即报错 |
| `url` | API 链接(base URL);留空 = 官方端点 | 环境 `LLM_BASE_URL` → `ANTHROPIC_BASE_URL`(OpenAI 格式回退 `OPENAI_BASE_URL`) |
| `api_key` | API Key(调真实模型必填) | 环境 `LLM_API_KEY` |
| `model` | 模型 id(需与所选格式匹配) | `claude-opus-4-8`(环境 `LLM_MODEL`) |
| `dev_stub` | `true` = 离线开发桩(无需 key) | 环境 `FP_DEV_STUB=1` |

- 值支持 `${ENV_VAR}` 插值(如 `api_key: "${LLM_API_KEY}"` 让密钥走环境/密管)。
- `LLM_Interface_Format` 决定按哪种协议通信:`OpenAI` 走 `/v1/chat/completions`;缺省 = `Anthropic`(向后兼容)。切换格式时记得把 `model` 换成对应厂商的模型名。
- 缺文件或缺字段 → 回退同名环境变量(向后兼容);故 `FP_DEV_STUB=1 make dev` 仍可用。
- 验证:`curl -s -X POST http://127.0.0.1:8080/chat -H 'Content-Type: application/json' -H 'X-User-Ctx: {"tenant_id":"t1","user_id":"u1","roles":["analyst"],"data_scope":{},"permissions":["*"]}' -d '{"message":"你好"}'` 见到 `event: answer_delta` 即通。

## 配置文件与优先级(config/*.yml)

除 LLM 外的环境变量集中在 `config/` 下的 yml,作为带注释、可发现的统一入口。agent-gateway 启动时(lifespan)由 `runtime_config.load_config_into_environ()` 把它们 `setdefault` 写回进程环境 —— **不覆盖已存在的真实环境变量**,故所有现有 `os.environ.get(...)` 读取点零改动。

**优先级(高→低)**:`OS 环境变量 / .env` > `config/secrets.yml` > `config/app.yml` > 代码默认。

| 文件 | 入库 | 内容 | 路径覆盖 |
|---|---|---|---|
| `config/app.yml` | 是 | 非密钥:`FP_KB_GRAPH_ENGINE` / `FP_KB_GRAPH` / `FP_KNOWLEDGE_DIR` / `FP_LLM_CONFIG` / `FP_REPOS_DIR` / `FP_CODE_INDEX_DB` / `FP_REPO_GIT_HOSTS` / `FP_REPO_ADMIN` / `WREN_API_URL` / `ZOEKT_URL` / `BUSINESS_API_URL` / `CONTRACTS_DIR` | `FP_APP_CONFIG` |
| `config/secrets.yml` | 否(gitignore;复制 `.example`) | 密钥:`LLM_API_KEY` / `DB_DSN_READONLY` / `NOTIFY_WEBHOOK_URL` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | `FP_SECRETS_CONFIG` |
| `config/llm.yml` | 否(gitignore;复制 `.example`) | LLM 接口格式 / url / api_key / model / dev_stub(见上节) | `FP_LLM_CONFIG` |

- 顶层 KEY 即环境变量名(扁平,分节靠注释);留空 = 不设 = 走代码默认。
- `secrets.yml` 的 `LLM_API_KEY` 在 `load_llm_config()` 之前写回环境,故 `llm.yml` 的 `${LLM_API_KEY}` 能解析 —— `llm.yml` 无需改动。
- `config/secrets.yml` 缺失时静默跳过(CI 常态);`make dev` 不会因此报错。

```bash
cp config/secrets.yml.example config/secrets.yml   # 然后填入真实密钥(不入库)
# config/app.yml 已入库,按需改值即可
```

**开启真实知识图谱**(默认 mock,不建图)需四者同时满足:`config/app.yml` 设 `FP_KB_GRAPH_ENGINE: lightrag` + `FP_KB_GRAPH≠0`(默认开)+ 安装可选依赖 `lightrag`(下方命令)+ 配置真实 LLM(开发桩 `dev_stub`/`MockProvider` 会跳过建图)。详见 `docs/integration/backend-gaps.md` §I。

```bash
# LightRAG 为可选生产后端(services/rag-svc 的 [project.optional-dependencies]);默认 uv sync / CI 不安装。
uv sync --all-packages --extra lightrag      # 声明式:装 pin 的 lightrag-hku==1.5.4 + 传递依赖
# 或仅装进当前 venv(不动 sync 选择集):
uv pip install "lightrag-hku==1.5.4"
```

## 纯前端 mock 开发(无后端)

```bash
cd web && python -m http.server 8080
# 浏览器:http://127.0.0.1:8080/?mock=1   (或先 localStorage.setItem('fp_mock','1'))
```

- 无 `/healthz` 响应 → 前端自动启用 mock(`mock/mock-sse.js`:/chat 多场景 + /chat/confirm 续传 + /files)。
- 自检页:`http://127.0.0.1:8080/mock/selftest.html`(顶部显示 `N passed / M failed`)。
- 触发不同 mock 场景:消息含「复杂 / 并行 / replan / 错误 / 延迟 / 澄清」关键词。

## 生产建议

- 第三方库自托管于 `web/vendor/`(不依赖公网 CDN);版本/许可/SHA-256 见 `web/vendor/README.md`。
- 关闭开发桩(不设 `FP_DEV_STUB`),按根 CLAUDE.md §12 配置 `LLM_API_KEY`、`DB_DSN_READONLY` 等真实依赖。
- `/files`、`/chat` attachments、解析器分批等后端待补见 `docs/integration/backend-gaps.md`。
