# 前端测试审计报告 — 内嵌 web/(原生 HTML/CSS + Alpine,零构建)

> 审计人:前端测试工程师(Claude Code)。日期:2026-06-20。
> 验证方式:`web/mock/selftest.html` 纯函数/投影断言(PASS/FAIL 计数)+ 手动验收清单;不引构建工具或重型测试框架。
> 依据:`docs/design/frontend-design.md`(§7.5 进展区/工具可视化、§8 上传、§8.5 Skill、§11 NFR、§12 决策 D1–D6)、`docs/prompts/frontend-stages.md`、`docs/dev/sse-protocol.md`。
> 取向:关键投影逻辑 / 边界 / **安全点(消毒与 URL 注入)** 的真实覆盖,不刷断言数。

---

## 0. 执行摘要

- **现状**:`selftest.html` 已有 **约 62 条断言**(与 PROGRESS「W4:selftest 62/0」一致;step 2 实跑复核),覆盖 W0–W4 的多数**纯函数**:`parseSSE`、`renderMarkdown`、run.js 投影助手、`classifyResult`、`validateFile`、Repository CRUD、`canManageSkills`/`validateSkill*`/`splitFrontmatter`、skill API(mock)。底子扎实。
- **核心缺口(按价值排序)**:
  1. **安全 XSS 向量偏少**:`renderMarkdown` 仅测 3 个向量(script/onerror/javascript:);iframe/svg/object/data:/form/编码绕过/外链 `rel` 未测。**工具结果消毒路径(`toolResultHtml`)未测**(任务明确要求)。
  2. **🐞 潜在注入点 citation `ref`**:`index.html:240` 以 `:href="c.ref||'#'"` 渲染,`_normCitations`(chat.js)**不校验 URL 协议** → `citation` 事件携 `ref:"javascript:..."` 可点击执行(绕过 markdown 的 DOMPurify)。**疑似 bug,待你定夺**(见 §5)。
  3. **核心事件路由 `_onEvent` / `_finishDone` 未测**:run.js 纯助手在隔离下测了,但**真实分流 + 「done→快照并入消息 + currentRun 清空」从未被断言**(现仅 mock 集成数了事件*类型*)。`createChat()` 返回 POJO,可作「DOM 投影逻辑」测。
  4. **畸形/截断 SSE 流韧性未测**(任务明确要求);且**生产解析器 `parseFrame`(sse.js)未被直接测**——selftest 测的是 mock 的 `parseSSE`(近似副本)。
  5. **未覆盖的纯函数**:`completeRunSteps`、`runSummaryLine`、replan(`applyPlan` v2 替换)、`store.clearAll`(清除本地历史,任务明确要求)、`skillAdmin()` 门控方法、`validateSkillName` 长度边界、`classifyResult` 的 JSON/长列表分支与阈值边界。
- **不变更被测逻辑**:发现的疑似 bug(citation ref)按铁律**报告等你决定**,不擅自改 chat.js/index.html。

---

## 1. 方法与范围

- 通读模块:`sse.js`、`run.js`、`markdown.js`、`store.js`、`attachments.js`、`skills.js`、`chat.js`、`app.js`、`mock/mock-sse.js`、`mock/selftest.html`、`index.html`(渲染绑定)。
- 注:`index.html`、`chat.js`、`app.css`、`vendor/lucide/icons.js` 在工作区为**已改动(未提交)**状态;本审计据当前磁盘内容,如你仍在编辑请以最终为准。
- 范围:纯函数 + 可在无浏览器下驱动的「DOM 投影逻辑」(Alpine 方法以 POJO 形态调用)。真正依赖渲染/事件/剪贴板/拖拽的交互 → 手动验收清单(step 3)。

---

## 2. 覆盖矩阵 ① — 按模块(纯函数 / 投影逻辑)

图例:**已覆盖** / **薄弱**(仅正例或单点)/ **缺失** / **不可纯测**(归手动清单)。

| 模块 | 函数 / 逻辑 | 状态 | 备注 / 缺口 |
|---|---|---|---|
| sse.js | `buildChatBody`/`buildConfirmBody`/`buildAskBody` | 已覆盖 | 形状已断言 |
| sse.js | **`parseFrame`(生产解析器)** | **缺失** | selftest 只测 mock 的 `parseSSE`;生产路径 `postChatStream→parseFrame` 仅间接走过 |
| sse.js | `postChatStream`(集成) | 薄弱 | 测了 simple/complex/confirm;**未测 ask_user 续传、error 事件、网络异常→HttpError、abort** |
| mock-sse.js | `parseSSE` | 已覆盖 | answer_delta/done + multi 类型;**未测畸形/截断/非 JSON/多行 data** |
| mock-sse.js | `pickScenario` | 缺失 | 纯函数,关键词→场景,未测(低优) |
| run.js | `applyPlan`(v1) / `applyStep` / `applyToolCall` / `applyToolResult` / `applyErrorToRun` | 已覆盖 | 隔离投影正确 |
| run.js | **`applyPlan` replan(v2 替换 steps)** | **缺失** | 重规划投影未测 |
| run.js | **`completeRunSteps`** | **缺失** | done 时 running→done 未测 |
| run.js | **`runSummaryLine`** | **缺失** | 折叠摘要行「计划 N 步·进行到 k/N」未测 |
| run.js | `classifyResult` | 薄弱 | inline/long/表格/代码已测;**JSON 形状、长列表(>4)、阈值边界(=3 行/=200 字)未测** |
| run.js | `snapshotRun` / `toolDisplayName` | 已覆盖 | — |
| chat.js | **`_onEvent` 事件分流** | **缺失** | plan/step/tool_call/tool_result/answer_delta/confirm/ask/citation/done/error 的路由 + 产出 block 从未直接断言 |
| chat.js | **`_finishDone`(快照并入消息 + currentRun 清空)** | **缺失** | 任务核心要求,未测;`_pause`/`_finishStopped`/`_onError` 同缺 |
| chat.js | `_appendAnswer` / `_closeOpenText`(text block 开合 + 渲染) | 缺失 | 流式 text 块合并 + 关闭时 renderMarkdown 未测 |
| chat.js | `appendToken` | 已覆盖 | — |
| chat.js | `toolOverview` / `stepLabel` / `toolStatIcon` | 缺失 | 小投影纯方法(低优) |
| markdown.js | `renderMarkdown` 消毒 | 薄弱 | 见 §3 安全(向量偏少 + 工具结果路径未测) |
| markdown.js | 代码块装饰(hljs/lang/copy-btn) | 已覆盖 | — |
| store.js | create/list/get/save/rename/remove/`groupByTime` | 已覆盖 | 富 blocks 往返 + 附件脱敏 + streaming 落 false |
| store.js | **`clearAll`(清除本地历史)** | **缺失** | 任务明确要求 |
| attachments.js | `validateFile` / `fileExt` / `humanSize` | 已覆盖 | 双白名单/大小/去重/空 MIME 回退 |
| attachments.js | `isImageExt`;`addFiles` 的 `maxCount` 上限 | 缺失 | isImageExt 低优;maxCount 在 Alpine 方法内→可投影测或手动 |
| skills.js | `canManageSkills` / `validateSkillName` / `validateSkillZip` / `splitFrontmatter` | 已覆盖 | name 仅测空/空格/合法,**长度边界(<2/>64)未测** |
| skills.js | **`skillAdmin()`(经 getUserCtx 的门控)** | **缺失** | 可投影测(setUserCtx 后调用) |
| skills.js | skill API(list/create/status/upload mock) | 已覆盖 | 含 422/400 负例 |
| skills.js | `statusLabel` / `skillFmtTime` | 缺失 | 低优 |
| app.js | `applyHljsTheme` / `toggleTheme` | 不可纯测 | 主题切换 → 手动清单 |

---

## 3. 安全点专审(最高优先)

**渲染汇** —— 已核对 `index.html` 全部 `x-html` / `:href` 绑定:

| 汇点(index.html) | 来源 | 是否消毒 | 测试 |
|---|---|---|---|
| `b.html`(197) | `renderMarkdown(b.raw)` | ✅ DOMPurify | 已测(基本) |
| `toolResultHtml(t)`(117/288) | `renderMarkdown(resultSummary)` | ✅ DOMPurify | **未测**(任务要求工具结果消毒) |
| `skillContentHtml/skillPreviewHtml`(407/428) | `renderMarkdown(body)` | ✅ DOMPurify | 已测(1 个向量) |
| `icon(...)`(多处) | 自有 lucide SVG | 可信(自托管) | 不需 |
| confirm `b.prompt`(208)/error `b.message`(248)/ask `q.question`(221)/`t.resultSummary`(289)/citation `c.title`(240) | SSE 文本 | ✅ `x-text`(textContent) | 安全(建议补 1 条回归锁定不被改成 x-html) |
| **citation `:href="c.ref"`(240)** | `_normCitations`→`c.ref` | ❌ **未校验协议** | **缺失 + 疑似 bug(§5)** |

**`renderMarkdown` 消毒缺口(任务:多个攻击样例)**:现仅 `<script>` / `onerror` / `javascript:[](…)`。建议补:`<iframe>`、`<svg onload>`、`<object>`/`<embed>`、`<form>`/`<input>`、`<img src=data:…>`、markdown 链接 `[x](javascript:…)` 与编码绕过(`JaVaScRiPt:`、`java&#x09;script:`)、`onclick`/`onmouseover`、`<style>` 注入、`<details ontoggle>`;并断言外链注入 `rel="noopener noreferrer"`(防 tabnabbing)。同样向 `toolResultHtml` 喂恶意工具结果断言被清。

---

## 4. 缺失清单 ② 与补强优先级 ③

> 优先级:**安全 > 核心事件投影 > SSE 韧性 > 其余纯函数/边界**。step 2 全部进 `selftest.html`(纯函数 + POJO 投影),不引框架。

### P0 — 安全(对应任务 step2·安全)
- P0-1 `renderMarkdown` 多 XSS 向量(≥8 个,含编码绕过 + 外链 rel)。
- P0-2 **工具结果消毒**:`toolResultHtml` 对恶意 `resultSummary` 清除脚本/事件属性。
- P0-3 SKILL.md 预览/详情消毒:补 ≥2 向量(现 1)。
- P0-4 `x-text` 文本汇回归哨兵(confirm/error/ask/citation title 经 textContent,锁定不退化为 x-html)。
- P0-5(**待决策**)citation `ref` 协议校验 —— 见 §5,需你定。

### P1 — 核心事件投影(对应任务 step2·SSE 分流 + currentRun)
- P1-1 `_onEvent` 分流:对 plan/step/tool_call/tool_result_summary/confirm_request/ask_user/citation/answer_delta/done/error 逐类,断言投影到 currentRun / 产出正确 block / 设置 pendingResume。
- P1-2 **`_finishDone`**:done 后 `snapshotRun` 入助手 `blocks` 且 `currentRun===null`;`_finishStopped` 入「已停止」note;`_onError`/error 事件入 error block 且 `applyErrorToRun`。
- P1-3 SSE 韧性:`parseFrame`(生产)+ `parseSSE` 对**畸形/截断/非 JSON/缺 data/多行 data/空帧**不抛、降级保留原文;`postChatStream` 末尾残帧 + abort + HttpError 路径。

### P2 — 其余纯函数与边界(对应任务 step2·折叠/上传/角色/Repository)
- P2-1 `classifyResult` 阈值边界(=3 行/=200 字/JSON 形状/长列表>4)。
- P2-2 run.js:replan(v2 替换)、`completeRunSteps`、`runSummaryLine`。
- P2-3 `store.clearAll`(清除本地历史)+ `getConversation(missing)→null`。
- P2-4 `skillAdmin()` 门控(setUserCtx 后:analyst 隐藏 / skill_admin 可见);`validateSkillName` 长度边界。
- P2-5 上传:`addFiles` maxCount 上限(投影测)、`.ZIP` 大小写、无扩展名。

### P3 — 低优补遗
`pickScenario`、`isImageExt`、`statusLabel`、`toolOverview`/`stepLabel`/`toolStatIcon`。

---

## 5. 疑似 bug(按铁律:报告,等你决定,不擅改)

**FB-1 [安全] citation `ref` 未做 URL 协议校验**
- 位置:`web/js/chat.js` `_normCitations`(`ref: c.ref || c.url || ''`)+ `web/index.html:240`(`<a :href="c.ref || '#'" target="_blank" rel="noopener noreferrer">`)。
- 影响:`citation` 事件(其来源是检索内容,按红线 7 视为**不可信**)若携 `ref:"javascript:alert(1)"`,渲染为可点击 `javascript:` 链接 → 点击执行脚本。markdown 路径有 DOMPurify 兜底,但 citation 走 Alpine `:href` 直绑,**绕过**消毒。
- 分类:**前端代码 bug(潜在 XSS)**,非测试问题。
- 建议(待你定):在 `_normCitations` 加 `safeHref(url)`(仅放行 `http(s):`/相对路径/`#`,其余归 `'#'`);我随后补**绿色**断言(`safeHref('javascript:…')==='#'`、合法 http 通过)。我不擅自改。

> 另:`x-text` 的文本汇(confirm/error/ask/citation title)当前安全;P0-4 仅加回归哨兵防回退,不涉改码。

---

## 6. 手动验收清单(step 3 预告)

无法纯函数化的交互将列入 `docs/testing/frontend-manual-checklist.md`(可勾选):简单问答(无进展区)、复杂任务(进展区+时间线+折叠展开+done 沉入留痕)、停止、错误重试、上传→随消息发送、会话切换/刷新恢复、Skill 列表/新建/编辑/发布/上传、明暗主题、移动端(<1024 抽屉)、键盘可达(Enter 发送 / Esc 停止 / 焦点)。对**真实后端(关 mock)**跑一遍,核对 SSE 字段与 `docs/dev/sse-protocol.md` 一致,偏差记入 `docs/integration/backend-gaps.md`。

---

## 7. 待确认(进入 step 2 前)

- **D-A**:FB-1(citation ref)如何处理?(a)你修 `_normCitations` 加 `safeHref`,我补绿色断言(**推荐**);(b)我加 xfail 断言固化该 bug 待你修;(c)仅审计登记,不写测。
- **D-B**:P1 的 `_onEvent`/`_finishDone` 投影测,确认走「`createChat()` POJO + 最小 `this` 桩(stub `scrollToBottom`/`$nextTick`)」在 selftest 内驱动(浏览器已载 marked/DOMPurify);可行无需框架。确认即按此做。
- **D-C**:范围确认 —— P0+P1+P2 全做,还是先 P0+P1(安全 + 核心投影),P2 边界下一批?

> 本报告即 step 1 交付。**确认 §4 优先级与 §7 决策后**,我再改 `selftest.html`、跑出全 PASS 计数贴回,并产出 `frontend-manual-checklist.md`。

---

## 8. 执行结果(step 2 / 3 已完成)

> 经确认「继续执行」,按 §4 优先级 + §7 推荐默认(D-B POJO 投影 / D-C 全做 P0+P1+P2)补强;FB-1 按铁律**未改生产代码**,留待决策。

- **selftest:62 → 108 passed / 0 failed**,0 console 报错(无头 Chromium + Playwright 载入服务化 `web/`,读 `window.__selftest`)。
- 新增 46 条断言:
  - **P0 安全**:9 个 XSS 向量(iframe/svg onload/object·embed/form·input/大小写 `JaVaScRiPt:`/onmouseover/details ontoggle/`<style>`/外链 `rel=noopener`)+ 工具结果消毒路径(`toolResultHtml`)+ SKILL 预览多向量 + 「不可信文本不走 x-html」哨兵(fetch index.html)。
  - **P1 投影**:`createChat()` POJO 驱动 `_onEvent` 全事件分流(plan/step/tool_call/tool_result/answer_delta/confirm/ask/citation/error/未知)+ `_finishDone`(done→快照入消息 + `currentRun=null` + open text 关闭渲染)+ `_finishStopped`;`parseFrame`(生产解析器)+ `parseSSE` 畸形/截断/非 JSON 不崩。
  - **P2 边界**:`classifyResult` 阈值(=3 行/4 行/JSON/长列表)、replan(v2 替换)、`completeRunSteps`、`runSummaryLine`、`store.clearAll`、`skillAdmin()` 角色门控、`validateSkillName` 长度边界、`isImageExt`、`pickScenario`。
- **手动清单**:`docs/testing/frontend-manual-checklist.md` 生成(13 节,含真实后端 SSE 字段核对 + FB-1 手动安全项)。

### 补遗:逐条消息复制按钮(本 worktree 命名特性「优化页面复制按钮」)
- 该特性(`chat.js copyMessage` + 用户/助手消息悬浮「复制」按钮 + `user-select` 可选区 + copy/check 图标)此前**无任一断言/手动项**。本次补齐:抽出纯函数 `copyTextOf(msg)`(用户取 raw;助手拼接 text 块,跳过引用/卡片),selftest 增 **4 条**断言(用户 raw / 助手拼接 / 两类空串);手动清单 §1 增「逐条消息复制」交互项(剪贴板 / 悬浮浮现 / 已复制反馈)。
- 连同下方 FB-1 修复的 5 条绿断言,**selftest 108 → 117 passed / 0 failed**(无头 Chromium 复跑,0 console 报错)。

### 已闭环 / 未覆盖
- **FB-1(citation `ref` 未校验协议,潜在 XSS)——已修复**(经授权):`_normCitations` 改经 `safeHref(url)` 协议白名单(仅放行 http(s)/相对/锚点;`javascript:`/`data:`/`vbscript:` 及大小写/制表符绕过一律归 `'#'`)。selftest 增 **5 条**绿断言(`safeHref` 各分支 + `_normCitations` 经 `safeHref` 净化)。手动清单 §12 相应改为「已修复,复测点击 `javascript:` ref 不执行」。
- **不可纯测项**:渲染/拖拽/剪贴板/滚动/响应式/键盘 → 全部进手动清单(step 3),需人工逐项过 + 真实后端关 mock 跑一遍。
