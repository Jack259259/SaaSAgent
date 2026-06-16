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

LLM 的 **url / api_key / model** 集中在 `config/llm.yml`(由 agent-gateway `get_provider` 读取;路径可经 `FP_LLM_CONFIG` 覆盖)。**密钥不入库**:仓内只提交模板 `config/llm.yml.example`,真实 `config/llm.yml` 已 gitignore。

```bash
cp config/llm.yml.example config/llm.yml   # 然后填入真实值
make dev                                    # 浏览器 http://127.0.0.1:8080/
```

| 字段 | 作用 | 默认 / 回退 |
|---|---|---|
| `url` | API 链接(base URL);留空 = 官方端点 | 环境 `LLM_BASE_URL` → `ANTHROPIC_BASE_URL` |
| `api_key` | API Key(调真实模型必填) | 环境 `LLM_API_KEY` |
| `model` | 模型 id | `claude-opus-4-8`(环境 `LLM_MODEL`) |
| `dev_stub` | `true` = 离线开发桩(无需 key) | 环境 `FP_DEV_STUB=1` |

- 值支持 `${ENV_VAR}` 插值(如 `api_key: "${LLM_API_KEY}"` 让密钥走环境/密管)。
- 缺文件或缺字段 → 回退同名环境变量(向后兼容);故 `FP_DEV_STUB=1 make dev` 仍可用。
- 验证:`curl -s -X POST http://127.0.0.1:8080/chat -H 'Content-Type: application/json' -H 'X-User-Ctx: {"tenant_id":"t1","user_id":"u1","roles":["analyst"],"data_scope":{},"permissions":["*"]}' -d '{"message":"你好"}'` 见到 `event: answer_delta` 即通。

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
