# 内嵌前端 web/ 手动验收清单

> 用途:覆盖无法纯函数化的交互(渲染 / 事件 / 剪贴板 / 拖拽 / 滚动 / 响应式 / 键盘)。
> 纯函数与投影逻辑已由 `web/mock/selftest.html` 覆盖(当前 **117 passed / 0 failed**,0 console 报错)。
> 勾选规则:逐项实操,**浏览器控制台(F12)全程无 error**;有偏差 → 记 `docs/integration/backend-gaps.md` 或开缺陷。

## 0. 准备

- 启动静态站:`python -m http.server 8099 --directory web`(或 agent-gateway 伺服),打开 `http://localhost:8099/`。
- **Mock 开/关**:`localStorage.fp_mock='1'` 强开 mock;`'0'` 强关(直连真实后端);未设则探测 `/healthz`。`?mock=1` 亦可强开。
- **演示角色**:`localStorage.fp_dev_roles=["analyst"]`(无 Skill 权)/ `["skill_admin"]`(有权),刷新生效(见 §8 角色门控)。
- 每次切换 localStorage 后**刷新**页面。

## 1. 简单问答(无进展区)

- [ ] 输入「你好」发送 → 助手逐字流式输出,**不出现**顶部任务进展区、不出现工具时间线。
- [ ] 流式期间显示光标;结束后光标消失,文本以 markdown 渲染(**粗体/列表/链接**正确)。
- [ ] 代码块:发「给我一段 python」类(mock 简单流无代码;可用 §12 粘贴样例)→ 代码块有语言标签 + 复制按钮,点击「复制」真入剪贴板(粘贴到别处校验),按钮短暂变「已复制」。
- [ ] **逐条消息复制**:鼠标悬停用户气泡 / 助手回答 → 浮现「复制」按钮(默认隐藏);点击真入剪贴板(粘贴校验),图标/文案短暂变「✓ 已复制」并在 ~1.5s 复原。用户取原文;助手取完整回答文本(多段 text 块换行拼接,**不含**工具卡片/引用/进展留痕);文本可手动选区(`user-select`)。

## 2. 复杂任务(进展区 + 工具时间线 + 折叠 + done 沉入留痕)

> 发送含「复杂 / 确认 / 复核」关键词(mock `complex` 场景)。

- [ ] 顶部出现**任务进展区**:计划步骤逐步 待执行→进行中→完成;焦点行(▸)更新。
- [ ] **工具时间线**:`query_finance_data`/`search_knowledge` 条目 运行中(⟳)→完成(✓);友好中文名正确。
- [ ] 折叠分档:短结果**内联**;长文本/表格/代码**默认折叠**,点「展开 ▸」可展开、「收起」可收起;结构化结果展开为渲染后的 markdown(表格/代码块)。
- [ ] 命中 `confirm_request`:**暂停**,消息内出现确认卡片(prompt + 确认/取消按钮);此时无 done。
- [ ] 点「确认」→ 续流至结论 + 引用卡片(citation)+ done;卡片显示「已确认」。
- [ ] **done 后**:顶部进展区消失,该轮进展**沉入助手消息**为可折叠留痕块(默认折叠,可展开回看计划/时间线)。
- [ ] 「取消」分支:点取消 → 续流(mock 仍给结论);卡片显示「已取消」。

## 3. 停止

- [ ] 发送较慢流(关键词「延迟/慢/停止」,mock `longdelay`)→ 流式中点**停止**(或按 `Esc`)→ 立即停止;消息末尾出现「已停止」note;已产出的进展沉入留痕;可再次发送。

## 4. 错误重试

- [ ] 发送含「错误/报错/失败」(mock `error` 场景)→ 出现错误卡片(code + message);运行中的工具条目转**失败(✗)**。
- [ ] 错误卡片可重试 / 重新发送上一问 → 重新走一轮。
- [ ] 断网模拟(DevTools Offline)发送 → 友好网络错误提示,不白屏、控制台无未捕获异常。

## 5. 文件上传 → 随消息发送

- [ ] 点回形针选文件 / **整页拖拽**文件 → 附件卡片出现,图片显示缩略图、其他显示图标 + 文件名 + 大小。
- [ ] 类型/大小拦截:选 `.exe` 或超 20MB → 卡片标红给原因;**不**进入待发送。
- [ ] 上传中显示进度;可**移除**、可**重试**失败项。
- [ ] 有「上传中」附件时发送按钮禁用;全部完成后可发送。
- [ ] 发送 → 用户气泡下方挂附件芯片;输入区附件清空。
- [ ] (mock)真实后端无 `/files` 时:卡片友好提示「待实现(D2)」,不崩(记 backend-gaps)。

## 6. 会话历史(切换 / 刷新恢复 / 重命名 / 删除 / 清除)

- [ ] 发首条消息 → 侧栏出现该会话,标题取首句(超长截断);按 今天/7天内/更早 分组。
- [ ] 新建对话 → 清空主区;旧会话仍在侧栏。
- [ ] 切换会话 → 主区恢复该会话**富消息**(文本 + 进展留痕块均可见;流式态落为非流式)。
- [ ] **刷新页面**(F5)→ 自动恢复最近会话,历史可回看。
- [ ] 重命名(二次输入)、删除(二次确认)生效。
- [ ] 「清除全部本地历史」(二次确认)→ 侧栏清空、回到新对话。
- [ ] 持久化脱敏:刷新后图片附件显示为图标(blob 缩略图不持久);localStorage 内不含 `thumbUrl`/原始 File。

## 7. 角色门控(Skill 管理入口)

- [ ] `fp_dev_roles=["analyst"]` 刷新 → **不显示** Skill 管理入口。
- [ ] `fp_dev_roles=["skill_admin"]` 刷新 → 显示入口,可进面板。

## 8. Skill 管理(需有权角色;mock `/skills*`)

- [ ] 列表加载,显示 名称/描述/状态(草稿/生效)/更新时间。
- [ ] 详情:只读渲染 `SKILL.md`(经消毒);展示 frontmatter 元信息。
- [ ] 新建:实时预览(右侧渲染);名称非法(空/含空格/<2/>64)即时报错且不提交;合法提交 → 落**草稿**、提示待审。
- [ ] schema 失败(mock 「bad」无 frontmatter)→ 展示后端逐条 errors。
- [ ] 编辑保存生效;删除二次确认。
- [ ] **发布生效**:对草稿点发布 → 状态转「生效」。
- [ ] 上传 `.zip`:类型/大小前端校验;后端逐条结果(成功 ✓ / 拒绝 ✗ + 原因)友好展示;非法 zip(mock「invalid」)→ 400 提示。前端**不解压、不执行** Skill。

## 9. 主题(明暗)

- [ ] 切换按钮 明↔暗;代码高亮主题随之切换(github ↔ github-dark);刷新保持(localStorage `fp_theme`)。

## 10. 响应式 / 移动端

- [ ] 窗口 < 1024px:侧栏变**抽屉**;汉堡按钮开合;选会话/新建后抽屉自动收起。
- [ ] 移动视口(DevTools 设备模拟):布局不溢出、可滚动、按钮可点。

## 11. 键盘可达 / a11y

- [ ] `Enter` 发送、`Shift+Enter` 换行、`Esc` 停止流式。
- [ ] Tab 焦点顺序合理;图标按钮有 `aria-label`;焦点环可见。
- [ ] 输入框随内容自增高(上限约 200px)。

## 12. 安全(手动)

- [ ] **粘贴恶意 markdown**:把含 `<script>`、`<img onerror>`、`[x](javascript:alert(1))`、`<iframe>` 的文本作为「答案/工具结果」走通(mock 可临时改场景或贴入)→ 渲染区**无弹窗、无脚本执行**,危险标签/属性被清(对齐 selftest 的 xss 断言)。
- [ ] **citation 链接**(FB-1 已修复):`_normCitations` 经 `safeHref` 协议白名单。若后端返回 `citation.ref` 为 `javascript:...`/`data:...`,渲染为 `href="#"`,点击**不执行脚本**;正常 `http(s)` 引用仍可点开(新标签 `rel=noopener`)。selftest 已有绿断言,此处人工复测真实点击行为。

## 13. 真实后端联调(关 mock)+ SSE 字段核对

> `localStorage.fp_mock='0'` 刷新,经 agent-gateway 同源直连真实 `/chat`。开 DevTools Network 看 `text/event-stream`。

- [ ] 一轮真实问答跑通:`tool_call → tool_result_summary → answer_delta → done` 顺序正确;无 console error。
- [ ] 逐字段核对 `docs/dev/sse-protocol.md`,偏差记 `docs/integration/backend-gaps.md`:
  - `tool_call`:`{id, tool, arguments}`
  - `tool_result_summary`:`{id, tool, summary, workspace_ref}`
  - `plan`:`{version, steps[]}`;`step`:`{index, note}`
  - `confirm_request`:`{id, prompt, options}`;`ask_user`:`{id, questions[]}`
  - `citation`:`{items[]}`(**前端假定**,协议未定字段 → 确认)
  - `answer_delta`:`{text}`;`done`:`{stop_reason, used_steps}`;`error`:`{code, message}`
  - 响应头 `X-Session-Id`(confirm/ask 续传用)
- [ ] 已知前端假定(若后端不一致需对齐,记 backend-gaps):`ask_user` 回执 `answers` 键名(前端按 questionIndex)、`step` 无每步状态枚举(前端按到达顺序投影)、`tool_result_summary` 无成功/失败与内容类型(前端启发式折叠 + 经 `error` 转失败)。
- [ ] 鉴权:缺/错 `X-User-Ctx` → 后端 401/403,前端友好提示不白屏。

---

### 运行 selftest(纯函数 / 投影)

无构建。任一:
1. 浏览器直接打开 `http://localhost:8099/mock/selftest.html`,看顶部「N passed / M failed」(应全绿)+ F12 无报错;
2. 无头复跑(Playwright,项目已依赖):服务 `web/` 后用 Chromium 载入该页读 `window.__selftest`(见本次审计所用脚本)。
