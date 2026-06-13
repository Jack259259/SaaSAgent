# Quickstart(本地起网关 + curl 体验 SSE)

> 阶段 2:全内存、无外部依赖。未配置 `LLM_API_KEY` 时,真实 LLM 调用返回 NOT_CONFIGURED;
> 想看端到端跑通的确定性效果,请跑测试(`make test`,内含 MockProvider 驱动的 e2e)。
> Windows 下在 Git Bash 执行 make(见根 README / 项目约定)。

## 1. 安装依赖

```bash
make lint   # 首次会触发 uv sync 安装依赖
```

## 2. 启动网关

```bash
make dev
# 等价于:uv run uvicorn agent_gateway.app:app --host 127.0.0.1 --port 8080
```

## 3. curl 体验 SSE

`X-User-Ctx` 必填(红线 3);`-N` 关闭缓冲以实时看到流式帧:

```bash
curl -N -X POST http://127.0.0.1:8080/chat \
  -H 'Content-Type: application/json' \
  -H 'X-User-Ctx: {"tenant_id":"t1","user_id":"u1","roles":["analyst"],"data_scope":{},"permissions":["*"]}' \
  -d '{"message":"你好"}'
```

预期:依次收到 `step` / `tool_call` / `tool_result_summary` / `answer_delta` / `done` 事件
(帧格式见 `docs/dev/sse-protocol.md`)。**注**:生产态需配置 `LLM_API_KEY`(`.env`);
未配置时网关可启动、鉴权可校验,但真实回答会返回 NOT_CONFIGURED。

## 4. 鉴权负例

```bash
curl -i -X POST http://127.0.0.1:8080/chat -d '{"message":"hi"}'   # 缺 X-User-Ctx → 401
```

## 健康检查

```bash
curl http://127.0.0.1:8080/healthz   # {"status":"ok"}
```
