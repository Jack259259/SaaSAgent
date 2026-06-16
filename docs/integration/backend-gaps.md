# 后端待补清单(内嵌前端对接)

> 前端(`web/`)已按设计契约实现;以下为对接真实后端前需后端补齐的端点/字段。前端均已留 mock 与降级,不阻塞开发。

## A. 文件上传(§12-D2)

- **`POST /files`(multipart)→ `{file_id, filename, mime, size, status}`**:后端暂无此端点。前端经 `fetch('/files')` 上传;mock 模式由 `web/mock/mock-sse.js` 拦截,真实模式 404 → 前端友好提示“后端 /files 待实现(D2)”。
- **`GET /files/{file_id}`**:元数据 / 下载(回看用),待补。
- **`/chat` 接受 `attachments: [file_id, ...]`**:当前 `ChatRequest` 仅 `message` + `page_context`,**无 `attachments` 字段**(pydantic 默认忽略额外键)→ 前端携带的 file_id 不会传达给 Agent。需在 `ChatRequest` 增 `attachments: list[str] | None`,并由编排器按需调 `parse_user_file(file_id)`。

## B. 解析器分批(§12-D3)

后端 `parse_user_file` 当前覆盖 **xlsx / csv / pdf 文本**。按优先级补:

- 第一批:**DOCX、MD、JSON、HTML**(覆盖多数企业文档 / 结构化数据)。
- 次之:ODT、RTF、EPUB。
- 图片(JPEG/PNG/GIF):暂不要求解析,仅上传 + 缩略图,待多模态启用输入。
- 建议:DOCX→python-docx/mammoth、MD/JSON/TXT→直读、HTML→trafilatura、ODT/RTF→pandoc、EPUB→ebooklib。
- 对未支持类型,`parse_user_file` 应返回**明确错误码**;前端据此标注“已上传,解析待后端支持”(现由 mock 的 `parse_supported` 模拟:xlsx/csv/pdf=true)。

## C. SSE 协议字段(W2 投影发现)

- **`citation` 事件未在 `docs/dev/sse-protocol.md` 冻结**:前端按设计 §7 基准实现 CitationList(假定 `{items:[{title,source,ref}]}`)。后端需在协议补 `citation` 事件,或在答案内联引用。
- **`step{index,note}` 无每步状态枚举**:前端按到达顺序投影(index 进行中、前置完成)。如需精确状态,建议 replan 时重发带 `status` 的 steps,或在 `step` 增 `status`。
- **`tool_result_summary{id,tool,summary,workspace_ref}` 无成功/失败、无内容类型/行数**:前端默认 ✓,`error` 事件转 ✗;折叠分档按 `summary` 启发式。建议补 `ok: bool` / `result_kind` / `row_count`,以精确分档与失败标记。
- **恢复语义**:`confirm_request` 用布尔 `confirmation:{confirmed}`,前端把 `options[0]` 映射为确认;**`ask_user` 恢复体 `answers:{...}` 键名未在协议定义**,前端按 `{questionIndex: 选项}` 构造,待后端明确键约定。

## D. 身份(§12-D4)

- 生产应由网关验证短时令牌并服务端构造 `user_ctx`(`agent_gateway/auth.py` 已标 TODO),前端不再注入 `X-User-Ctx`,改走同源 cookie/session。

## E. Skill 管理(W4 预告)

- `GET / POST / PUT / DELETE /skills`、`POST /skills/{id}/status`、`POST /skills/upload`(安全解压:zip slip / 解压炸弹 / 结构白名单 / SKILL.md schema 校验 / 草稿态)—— W4 阶段细化补充本节。
