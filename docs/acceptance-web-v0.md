# 内嵌前端 web/ —— v0 验收(W0–W3)

> 内嵌前端(后端仓 `web/`,原生 HTML/CSS + Alpine,零构建,同源同部署)。验证不走 make:`web/mock/selftest.html` + 无头 Chromium 实测 + 手动清单。

## 验收结论

| 阶段 | 结论 | 关键证据 |
|---|---|---|
| W0 脚手架 + 设计令牌 | ✅ | vendor 自托管(版本/许可/SHA-256)、selftest、主题切换;零 console 报错 |
| W1 布局 + 消息渲染 + 流式 | ✅ | 对标 Claude 布局/响应式/主题;markdown 消毒 + 代码块复制(真入剪贴板) |
| W2 SSE 主循环 + 进展区 + 时间线 + 卡片 | ✅ | 简单/复杂/并行/replan/停止/错误重试;confirm 暂停→/chat/confirm 续;done 留痕 |
| W3 上传 + 历史 + 伺服 + 真实对接 | ✅ | 上传(双白名单/进度/缩略图/解析待补)+ 附件发送 + 会话 CRUD/刷新恢复;agent-gateway 同源真实 `/chat` 一轮问答(mock 经 /healthz 自动关闭) |

- **selftest:50 passed / 0 failed**(令牌 / SSE 解析 / currentRun 投影 / 折叠分档 / Markdown 消毒 / 流式 / 文件校验 / Repository CRUD / 附件 payload)。
- **无头 Chromium 实测**:mock 模式(上传→发送→展示、会话新建/切换/刷新恢复/清除)+ 真实 agent-gateway 模式(`FP_DEV_STUB=1`,同源 `/chat` 真实 SSE 一轮问答)均**零 console / page 报错**。
- 后端 `agent-gateway` 改动经 `ruff` + `mypy --strict` + `pytest`(8 例)全绿。

## §11 NFR 自检

- **性能**:首 token 即上屏;流式 append 仅更新当前消息(不整列重绘);长对话普通滚动 + 贴底跟随(不做虚拟滚动,§3 取舍)。
- **健壮**:SSE 错误 → ErrorBanner + 重试;上传失败可重试/移除;空/加载/错误三态;停止用 AbortController(mock 合成流亦尊重 signal)。
- **无障碍**:Enter 发送 / Shift+Enter 换行 / Esc 停止;消息区 `aria-live="polite"`;图标按钮 `aria-label`;`:focus-visible` 焦点环。对比度以语义令牌达 WCAG AA 为目标(系统化审计【待补】)。
- **安全**:Markdown 与工具结果一律 DOMPurify 消毒(禁 script/事件属性/`javascript:`);`<template>` 惰性解析避免副作用加载;附件双白名单 + 大小/条数上限;历史脱敏(不存 File/objectURL/瞬时句柄);前端不解析业务文档、不解压 zip(归后端);不在前端日志打印敏感内容。
- **响应式**:断点 1024px;≥1024 双栏,<1024 Sidebar 抽屉 + 遮罩。
- **国际化**:文案中文为主、集中在模板,预留扩展。

## 知识产权红线自检

- 仅对标 Claude 的**交互模式与信息架构**;未复制 Anthropic 商标 / logo / 专有字体 / 配色 / 受版权图标或 CSS。
- 品牌为自有占位(「资金计划助手」+ teal 强调色);图标 Lucide(ISC,内联 SVG);字体 Inter + JetBrains Mono(SIL OFL 1.1)。
- 第三方库全部**自托管**于 `web/vendor/`,运行时不引公网 CDN(版本/许可/SHA-256 见 `web/vendor/README.md`;`.gitattributes` 锁二进制防 EOL 致哈希漂移)。

## 后端待补(不阻塞;详见 docs/integration/backend-gaps.md)

`POST /files` + `/chat` 接 `attachments`(D2);`parse_user_file` 解析器分批(DOCX/MD/JSON/HTML 优先,D3);`citation` 事件入协议;`tool_result_summary` 补成功/失败与内容类型;生产身份改网关签发短时令牌(D4);Skill 管理写 API 与安全解压(W4)。

## 运行方式

见 `docs/deploy.md`:真实后端 `FP_DEV_STUB=1 make dev` → `http://127.0.0.1:8080/`;纯前端 mock `cd web && python -m http.server 8080` → `?mock=1`;自检 `…/mock/selftest.html`。
