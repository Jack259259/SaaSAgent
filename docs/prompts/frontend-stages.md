# 前端聊天界面 · Claude Code 分段实施提示词包(内嵌·原生+Alpine 版)

> 配套:《前端聊天界面设计方案(内嵌·原生+Alpine 版)》+ 后端 `docs/dev/sse-protocol.md` + CLAUDE.md。
> 这是在**现有后端仓内**新建 `web/` 文件夹的前端,原生 HTML/CSS + Alpine.js,**与后端同仓、同部署、同源**。无独立仓、无构建、无 CORS。

---

## 使用说明(先读这页)

**前置**:① 在后端仓里把《前端设计方案》放到 `docs/design/frontend-design.md`;② 确认后端 `docs/dev/sse-protocol.md` 在仓内;③ **先定设计方案 §12 的 4 个决策点**(尤其 D2 上传端点、D4 身份),结论补进设计文档;④ 这是已有后端仓,直接在其上分支开发。

**每阶段执行流程(固定)**:① 开新 Claude Code 会话(或 `/clear`);② 整段复制该阶段提示词发送;③ 它先出计划——你只查"文件是否都在 `web/` 下(除约定的 agent-gateway 伺服改动)、验证方式是否含 selftest + 手动清单";确认回 `按计划实施`;④ 完成后**核对:`web/mock/selftest.html` 全部 PASS(贴出 通过/失败 计数)+ 页面加载无 console 报错 + 手动验收清单逐项打勾**;⑤ `git status` 干净、PROGRESS.md 勾选,提交,关会话。

**验证手段(无构建链下的纪律)**:不用 npm/打包。验证靠三样——(a) `web/mock/selftest.html`:一个极简断言运行器(纯 JS),对关键纯函数(SSE 解析、Markdown 消毒、文件校验、Repository)跑断言,页面顶部显示 `N passed / M failed`;(b) 本地静态伺服打开页面(开发期可 `cd web && python3 -m http.server 8080`,或经 agent-gateway),核对**无 console 报错**;(c) 每阶段附带的**手动验收清单**逐项确认。**铁律:selftest 有 FAIL、或 console 报错、或清单未过,即未完成。**

**Mock 优先**:开发对着 `web/mock/mock-sse.js`(拦截 `window.fetch` 的 `/chat`,按开关/URL 参数返回预设 SSE 序列)。后端就绪后关 mock,相对路径直连真实后端,前端零改动。

**知识产权红线(贯穿全程)**:对标 Claude 仅限**交互模式与信息架构**;**严禁**复制 Anthropic 商标、logo、专有字体、配色或受版权保护的图标/CSS。图标用 Lucide(ISC),字体用可自由商用字体(Inter/JetBrains Mono),品牌用自有占位名与强调色。第三方库**自托管**于 `web/vendor/`,不引公网 CDN。

**技术栈**:原生 HTML + CSS 变量 + Alpine.js + marked + highlight.js + DOMPurify(全部 vendor 自托管)。不引 React/Vue/Vite/打包器。

**阶段总览**:W0 内嵌脚手架+令牌 → W1 布局骨架+消息渲染+流式 → W2 SSE 主循环+富事件卡片 → W3 文件上传+会话历史+后端伺服与对接 → W4 Skill 管理模块。

---

## 阶段 W0:内嵌脚手架与设计令牌

```text
请先读 docs/design/frontend-design.md 的 §2、§4、§5、§10(只读这四节)与 docs/dev/sse-protocol.md;再读根 CLAUDE.md §3(确认前端文件夹落点,本方案用 web/)。

本阶段目标:在后端仓内建立 web/ 静态前端骨架(原生+Alpine,零构建),搭好 vendor 自托管、设计令牌、mock 与 selftest 验证手段,页面能空跑。

必须完成:
1. web/ 目录结构(按设计 §5):index.html、styles/{tokens.css,app.css}、js/{app.js,sse.js,chat.js,attachments.js,store.js,markdown.js}(本阶段多为占位骨架)、vendor/、mock/{mock-sse.js,selftest.html}。
2. vendor 自托管:把 alpine.js、marked、highlight.js、dompurify、lucide(SVG)下载置于 web/vendor/,index.html 用本地 <script>/ESM 引入(不引公网 CDN);在 web/vendor/README.md 标注各库版本与许可。
3. index.html:Alpine 根 x-data 初始化;引入 tokens.css/app.css 与 vendor;一个最简"Hello + 主题切换"可见,证明 Alpine 生效。
4. tokens.css:CSS 变量(中性灰阶 + 单一品牌强调色 + 间距/圆角/字号),明暗双主题(html[data-theme] 切换);app.css 基础重置与排版。字体接入 Inter + JetBrains Mono(自托管,标注许可)。
5. mock/mock-sse.js:导出 installMockSSE(),通过包裹 window.fetch 拦截 POST /chat,按开关(localStorage flag 或 ?mock=1)返回一个最简预设 SSE 序列(answer_delta×3 + done);默认开发态开启。
6. mock/selftest.html:极简断言运行器(纯 JS,无依赖)——提供 assert(name, cond) 与汇总 "N passed / M failed" 顶部展示;本阶段先放 1~2 个占位断言(如 tokens 变量存在、mock 能解析一条 answer_delta)。
7. 生成/更新 PROGRESS.md:W0–W3 复选清单,每项一句 DoD 摘要。
8. 不改后端业务代码;agent-gateway 的静态伺服留到 W3(本阶段用 python3 -m http.server 本地打开即可)。

禁止:引入任何构建工具/打包器/npm 框架;引用公网 CDN;编写对话业务逻辑;改动 web/ 之外的后端代码。

先以计划输出(目录树 + vendor 清单与许可 + 令牌设计 + selftest 方案 + 验证方式),确认后实施。
DoD:cd web && python3 -m http.server 打开 index.html 页面正常、主题可切、无 console 报错(贴出说明);selftest.html 全部 PASS(贴出 通过/失败 计数);PROGRESS.md 勾选 W0;给出 commit message(feat(web): scaffold)。
```

---

## 阶段 W1:布局骨架 + 消息渲染 + 流式打字(对 mock)

```text
请读 docs/design/frontend-design.md 的 §6、§7(消息渲染相关)、§11(安全/消毒)、§3(取舍——确认不做虚拟滚动)。

本阶段目标:用原生 HTML/CSS + Alpine 搭出对标 Claude 的布局,并把消息块、Markdown/代码渲染、流式打字做扎实,数据来源先用 mock 的本地增量流。

必须完成:
1. 布局(CSS Grid/Flex + Alpine x-data):Sidebar(会话列表占位 + 新建按钮 + 用户/设置入口)+ TopBar(汉堡 + 标题 + 明暗切换 + 用户菜单占位)+ 主对话区(居中,最大宽约 720–768px)+ 底部 Composer(📎 + 多行输入 + 发送按钮);空状态欢迎区 + 居中输入框,发首条后落底。
2. 响应式:≥1024px 双栏;<1024px Sidebar 抽屉化(汉堡唤出),主区全宽;用 Alpine 状态管理抽屉开合。
3. js/markdown.js:marked + highlight.js + DOMPurify 封装 renderMarkdown(text)→ 安全 HTML(严格消毒,禁 <script>/事件属性/HTML 注入);代码块语言标注 + 复制按钮。
4. 消息块:用户/助手视觉区分(对标 Claude 极轻背景);助手消息块顶部预留富卡片插槽(W2 用)。
5. 流式打字:chat.js 提供把增量 token 平滑 append 到当前助手消息的逻辑(本阶段用本地 setInterval 模拟逐字),打字光标、增量渲染不整列重绘、结束移除光标。
6. 长对话:普通滚动 + 自动滚到底 + 用户上滚时不强制拉回(不做虚拟滚动,符合 §3 取舍)。
7. selftest 扩展:renderMarkdown 消毒断言(<script>/onerror 被清除)、代码块渲染、流式 append 顺序正确。

禁止:接真实网络或真实 SSE(W2);实现富事件卡片(W2);引入构建工具。

先出计划(组件/x-data 结构 + 断点 + selftest 用例 + 手动清单),确认后实施。
DoD:页面在静态伺服下布局/响应式/主题正常、无 console 报错;selftest 全 PASS(贴计数);手动清单(空状态、发占位消息流式、代码块复制、抽屉开合)逐项过;PROGRESS.md 勾选 W1;commit(feat(web): layout + message render)。
```

---

## 阶段 W2:SSE 主循环 + 富事件卡片(对 mock-sse)

```text
请读 docs/dev/sse-protocol.md 全部,以及 docs/design/frontend-design.md 的 §7 全部、§11。

本阶段目标:打通"输入→发送→SSE 流式→渲染→停止/错误"主循环,并把后端富事件渲染为(a)顶部任务进展区 +(b)工具调用时间线 +(c)消息内卡片;后端用 mock/mock-sse.js 的多场景序列,真实后端就绪仅关 mock。

必须完成:
1. js/sse.js:postChatStream(payload, {onEvent, signal}) —— fetch + ReadableStream 解析 text/event-stream,按 sse-protocol.md 事件名分发 onEvent;支持 AbortController 取消。严格按契约字段解析,字段对不上的代码注释标 TODO 并在回复中列出(不臆造)。
2. chat.js 发送循环(Alpine 状态):messages、当前流式助手消息、currentRun(本轮进展投影,见第 4 项)、sendStatus(idle|streaming|error);sendMessage(text, attachments?) 建用户消息 + 助手占位 → postChatStream → 按事件填充。
3. 消息内事件渲染:answer_delta(流式正文)、confirm_request(ConfirmCard:展示操作+参数+影响,确认/拒绝 → POST /chat/confirm 续跑)、ask_user(AskUserCard 选项 → 回执端点)、citation(CitationList 来源+跳转)、done(收尾、启用操作、停光标)、error(ErrorBanner+重试)。同一助手消息内卡片与正文按到达顺序有序排列。
4. 【改动①】顶部任务进展区(按设计 §7.5.1):主对话区顶部、消息列表之上的可折叠区域;仅当本轮收到 plan 时展开,简单问答(仅 answer_delta)不出现;展示计划步骤清单(plan)+ 每步实时状态(step:待执行/进行中/完成/失败)+ 当前焦点;replan 原地刷新;可折叠为一行摘要("计划 3 步 · 进行到 2/3 · 正在查询资金数据 ▸");本轮 done 后进展区收起,完整计划+工具时间线沉入该条助手消息留痕(刷新可回看);某步失败标红并保留。
5. 【改动②】工具调用可视化(按设计 §7.5.2):tool_call → 新增时间线条目(状态=进行中转圈 + 工具名翻译为友好文案 + 可选入参摘要);tool_result_summary → 条目转完成✓/失败✗,按**折叠分档**展示结果——短结果(≤3 行/≤200 字)内联不折叠;长文本结果默认折叠,只显示概览行+"展开 ▸";结构化大对象(表格/代码/JSON/长列表)一律默认折叠,展开后在限高+内部滚动的受控容器内渲染。阈值集中为可配常量;折叠状态记在每条目 expanded(默认 false)用户逐条控制,可选"展开全部/收起全部"。维护工具名→文案映射表(query_finance_data→查询资金数据、search_knowledge→检索知识库、ask_codebase→分析代码、find_sop/run_sop→查找/执行页面操作,无映射回退原名);工具结果渲染(含展开后)经 DOMPurify 消毒;多步/并行条目按到达顺序排列、并行各自更新。
6. currentRun 状态模型(§7.5.3):{ plan:{steps[]}, toolTimeline:[{id,tool,displayName,status,argsSummary,resultSummary,expanded}], collapsed };把 plan/step/tool_call/tool_result_summary 投影到 currentRun;done 时快照并入助手消息 content_blocks 后清空 currentRun。纯前端状态投影,无新网络调用。
7. Composer 行为:Enter 发送 / Shift+Enter 换行 / Esc 停止;发送中按钮变 ■ → abort 当前流;空输入禁发;失败可重试(重发上一条用户消息)。
8. 鉴权透传:按 §12-D4——开发态注入 X-User-Ctx;请求统一封装,缺 user_ctx 按约定处理。
9. mock-sse 扩展多场景:正常流、异常流(中途 error)、长延迟流(测停止)、复杂任务流(plan→多个 tool_call/step→confirm_request→answer_delta→citation→done)、并行多工具流、replan 流(plan 二次更新)。
10. selftest 扩展:SSE 解析器对每类事件正确分流;currentRun 投影正确(plan→步骤、tool_call/result→时间线条目状态流转);工具名映射回退;**结果折叠分档判定(短结果内联 / 长文本折叠 / 结构化大对象折叠)按阈值正确**;done 后留痕快照并入消息且 currentRun 清空;确认/拒绝分支;ask_user 回执构造。

禁止:在前端实现业务判断(后端职责);把工具原始大对象整段平铺;把进展区做成常驻占屏(必须可折叠且简单问答不出现);跳过工具结果消毒;引入构建工具。

先出计划(SSE 解析状态机 + 事件→进展区/时间线/卡片 的投影映射表 + currentRun 模型 + mock 场景 + selftest 用例 + 手动清单),确认后实施。
DoD:对 mock-sse 手动跑通"简单问答流(无进展区)/ 复杂任务流(顶部进展区随 step 流转 + 工具时间线状态变化 + 折叠展开 + done 后沉入留痕)/ replan / 并行工具 / 停止 / 错误重试",逐项过且无 console 报错;selftest 全 PASS(贴计数);PROGRESS.md 勾选 W2;commit(feat(web): sse loop + progress region + tool timeline + cards)。
```

---

## 阶段 W3:文件上传 + 会话历史 + 后端伺服与对接

```text
请读 docs/design/frontend-design.md 的 §8、§9、§10、§12(D1/D2/D3 结论),以及 docs/dev/sse-protocol.md。

本阶段目标:补齐上传子系统与会话历史,接通后端静态伺服(同仓同部署),并对接真实后端完成 v0 验收。

必须完成:
1. 文件上传(attachments.js + Alpine):扩展名+MIME 双白名单覆盖 DOCX/ODT/RTF/EPUB/HTML/MD/TXT/XLSX/CSV/JSON/JPEG/PNG/GIF;大小上限(默认 20MB,可配)+ 条数上限 + 去重;整页拖拽遮罩 + 📎选择;上传进度;附件卡片(类型图标+文件名+大小+移除);图片缩略图;失败可重试/移除。
2. 上传 API 客户端:POST /files(multipart)→ {file_id,...};并发+取消;sendMessage 携带 attachments:[file_id,...](对齐 W2 payload),用户消息块展示附件。按 §12-D2:若后端暂无 /files,先对 mock 该端点开发并在 docs 标注后端待补。
3. 解析缺口提示(§8.3/§12-D3):对 parse_user_file 暂不支持的格式,卡片标注"已上传,解析待后端支持";后端返回未支持错误码时前端友好提示,不阻塞其他附件。
4. 会话历史(store.js,§12-D1 localStorage):Repository 接口 + localStorage 实现(IndexedDB 可选),UI 经 Repository 读写;会话 CRUD、切换、自动标题、重命名、删除(二次确认)、刷新后历史恢复(含富卡片块);Sidebar 列表按时间分组排序;done 后整条助手消息落库。**按 D1 衍生要求**:历史不写入敏感信息;用户菜单/设置提供「清除本地历史」一键清空(退出时可用)。
5. 后端伺服(唯一后端改动,§10):agent-gateway 增加 web/ 静态伺服 + SPA 回退(未匹配 API 的 GET 返回 web/index.html),确保 /chat、/files 等 API 路由优先;改动写入 docs/deploy.md(本地启动后端即可访问前端的步骤)。
6. 真实后端对接:关闭 mock,经 agent-gateway 同源访问;核对 SSE 事件字段与 sse-protocol.md 完全一致,偏差属后端的汇总到 docs/integration/backend-gaps.md;身份/user_ctx 按 §12-D4 真实接通。
7. selftest 扩展:文件校验(白名单/大小拦截)、Repository CRUD、附件随消息携带 file_id;终验对照设计 §11 NFR 与知识产权红线逐条自检,输出 docs/acceptance-web-v0.md。

禁止:在浏览器解析 DOCX/XLSX 等(后端 parse_user_file 职责);上传未通过校验的文件;为对接放宽安全消毒;引入构建工具。

先出计划(白名单表 + 上传状态机 + Repository 接口 + 后端伺服改动点 + selftest 用例 + 手动清单),确认后实施。
DoD:经 agent-gateway 同源打开页面,手动跑通"上传→随消息发送→附件展示""会话新建/切换/刷新恢复""真实后端一轮问答",逐项过且无 console 报错;selftest 全 PASS(贴计数);docs/acceptance-web-v0.md 生成;PROGRESS.md 全勾选;commit(feat(web): upload + history + serve + integrate)。
```

---

## 阶段 W4:Skill 管理模块(对 mock 开发)

```text
请读 docs/design/frontend-design.md 的 §8.5 全部、§12(D5/D6 结论)、§11(安全/消毒);再读后端 CLAUDE.md §2 红线 10(Skill 资产门禁)、§9.1 角色矩阵相关行。

本阶段目标:在 Sidebar 底部"用户/设置"上方新增「Skill 管理」入口,实现 Skill 的查看/编辑/删除/新建(弹窗)/上传压缩包。前端用原生+Alpine,管理类写操作与上传解压依赖后端 API——后端若未就绪,对 mock 这些端点开发并在 docs 标注后端待补。

必须完成:
1. 入口与权限门控:Sidebar 底部、"用户/设置"上方加「Skill 管理」项;按 user_ctx 角色控制可见性(§12-D5,默认仅管理员/内部角色可见);无权限不渲染此入口。
2. Skill 管理视图(全屏面板或大弹窗,Alpine x-data):列表展示 name / description / status(生效/草稿/待审)/ updated_at;空态与加载态。
3. 查看详情:点列表项 → 只读展示 SKILL.md 渲染(复用 markdown.js,DOMPurify 消毒)+ frontmatter 元信息。
4. 新建(弹窗):「新建 Skill」按钮 → 弹窗含 Skill 名称输入 + SKILL.md 多行文本域 + 实时 Markdown 预览(消毒);name 前端校验(非空/字符规范);提交 → POST /skills;展示后端 schema 校验结果(失败在表单内显示,不静默);成功刷新列表。
5. 编辑:详情内「编辑」→ 同结构表单(name、SKILL.md)→ PUT /skills/{id};按 §12-D5 提交为草稿待审,提交后提示"已保存为草稿,待管理员审核"(生产);开发/测试环境可配置为直接生效。
6. 发布生效(仅管理员):草稿/待审详情页提供「发布生效」→ POST /skills/{id}/status (status=active);列表与详情按状态(生效/草稿/待审)展示,操作后刷新状态。
7. 删除:列表项「删除」→ 二次确认 → DELETE /skills/{id};仅授权角色。
8. 上传压缩包:「上传 Skill 包」→ 选择 .zip(类型 + 大小上限校验)→ POST /skills/upload(multipart)→ 展示后端返回的逐条解压入库结果(成功入库哪些 Skill / 失败原因);刷新列表。前端只上传 + 展示,不在浏览器解压。
9. lib:js/skills.js 封装 Skill API 客户端(列表/详情/创建/更新/删除/状态变更/上传);所有请求经统一 http 封装,带 user_ctx 透传。
10. mock 扩展:mock/mock-sse.js 同级加 mock-skills(拦截 /skills 系列、/skills/{id}/status、/skills/upload),覆盖列表/详情/创建(含 schema 校验失败用例)/更新/删除/发布生效/上传(含成功多条、zip 非法拒绝)。
11. selftest 扩展:name 校验、SKILL.md 预览消毒(<script> 清除)、.zip 类型/大小校验、Skill API 客户端构造请求正确(含 status 变更)、状态展示(生效/草稿/待审);角色门控(无权限角色看不到入口、看不到发布生效)。
12. docs:把后端待补的 Skill 管理 API(CRUD + /skills/{id}/status + /skills/upload)与 zip 安全解压要求(zip slip / 解压炸弹 50MB·500 文件 / 白名单结构 / SKILL.md schema 校验 / 草稿态入库)写入 docs/integration/backend-gaps.md(供你转后端)。

禁止:在浏览器解压 .zip 或执行 Skill 内脚本(后端职责);跳过 SKILL.md 预览消毒;对非授权角色暴露写操作;为此模块引入构建工具或新框架。

先出计划(管理视图/弹窗的 x-data 结构 + Skill API 客户端 + mock 场景 + selftest 用例 + 手动清单 + 后端待补清单),确认后实施。
DoD:对 mock 手动跑通"列表→查看→编辑→删除""新建弹窗(含校验失败提示)""上传 zip(成功多条 + 非法拒绝)",且无权限角色看不到入口、无 console 报错;selftest 全 PASS(贴计数);backend-gaps.md 更新;PROGRESS.md 勾选 W4;commit(feat(web): skill management)。
```

---

## 附录:常用模板

**A. 修复模板(selftest FAIL 或 console 报错时,新会话粘贴)**
```text
继续本仓库 web/ 前端工作。现象:<selftest 的 FAIL 项 / console 报错全文>。
请:1) 先读相关文件定位根因(不要猜);2) 给最小修复并说明为何是根因;3) 经我确认后修复;4) 重跑 selftest 并贴 通过/失败 计数 + 确认 console 无报错。
禁止:为通过而注释断言、放宽消毒、删用例。
```

**B. 续作模板(会话中断/上下文过长后,新会话粘贴)**
```text
继续完成阶段 WN(提示词见 docs/prompts/frontend-stages.md 对应小节,先读它)。
先执行 git status、git log -5 --oneline 并读 PROGRESS.md;对照该阶段"必须完成"清单输出 已完成/未完成/不确定 三栏(不确定项先验证)。只做未完成部分,完成后按该阶段 DoD 验收。
```

**C. 契约对齐模板(SSE 字段与后端对不上时)**
```text
对照 docs/dev/sse-protocol.md 与后端实际返回,逐条列出 web/js/sse.js 解析中字段/事件名不一致处(期望 vs 实际 vs 代码位置)。属前端的直接修;属后端的汇总到 docs/integration/backend-gaps.md 待我转后端。不要为掩盖差异臆造字段默认值。
```
