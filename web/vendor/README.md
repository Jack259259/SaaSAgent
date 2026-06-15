# web/vendor — 自托管第三方库清单

> 前端红线:**第三方库一律自托管于此目录,运行时不引公网 CDN**(见根 CLAUDE.md 前端红线 / 设计 §2、§4)。
> 下方文件由 dev 期一次性下载(jsDelivr / fontsource)落库,**已纳入 git**;页面只引用本地相对路径。
> 升级步骤:重新下载 → 更新本表版本与 SHA-256 → 跑 `mock/selftest.html` 全 PASS + 页面无 console 报错 → 提交。

## JS / CSS 库

| 库 | 版本 | 许可 | 文件 | 来源(下载用,非运行时) |
|---|---|---|---|---|
| Alpine.js | 3.14.8 | MIT | `alpine/alpine.min.js` | `https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js` |
| marked | 12.0.2 | MIT | `marked/marked.min.js` | `https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js` |
| highlight.js | 11.9.0 | BSD-3-Clause | `highlight/highlight.min.js` | `https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/highlight.min.js` |
| highlight.js theme(亮) | 11.9.0 | BSD-3-Clause | `highlight/github.min.css` | `.../@highlightjs/cdn-assets@11.9.0/styles/github.min.css` |
| highlight.js theme(暗) | 11.9.0 | BSD-3-Clause | `highlight/github-dark.min.css` | `.../@highlightjs/cdn-assets@11.9.0/styles/github-dark.min.css` |
| DOMPurify | 3.1.6 | Apache-2.0 OR MPL-2.0 | `dompurify/purify.min.js` | `https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js` |
| Lucide(图标) | — | ISC | `lucide/icons.js`(内联 SVG,手工取路径) | https://lucide.dev (ISC) |

> Lucide 仅取所需图标(menu / sun / moon)的 SVG 路径数据内联到 `lucide/icons.js`,未引入其 npm 包,避免整包体积。

## 字体(自托管 woff2)

| 字族 | 字重 | 许可 | 文件 | 来源 |
|---|---|---|---|---|
| Inter | 400 / 600 / 700 | SIL OFL 1.1 | `fonts/inter/inter-latin-{400,600,700}-normal.woff2` | `https://cdn.jsdelivr.net/fontsource/fonts/inter@latest/latin-{w}-normal.woff2` |
| JetBrains Mono | 400 | SIL OFL 1.1 | `fonts/jetbrains-mono/jetbrains-mono-latin-400-normal.woff2` | `https://cdn.jsdelivr.net/fontsource/fonts/jetbrains-mono@latest/latin-400-normal.woff2` |

## 完整性校验(SHA-256)

```
alpine.min.js                          B600E363D99D95444DB54ACBFB2DEFFEC9AE792AA99A09229BCDA078E5B55643
marked.min.js                          15FABCE5B65898B32B03F5ED25E9F891A729AD4C0D6D877110A7744AA847A894
highlight.min.js                       837A6FA5B0C736B52BBDE2B2B6190F305DA3FC9ED41681DB5321507057B5C846
highlight/github.min.css               3A9A5DEF8B9C311E5AE43ABDE85C63133185EED4F0D9F67FEA4B00A8308CF066
highlight/github-dark.min.css          9F208D022102B1D0C7AEBFECD8E42CA7997D5DE636649D2B31EA63093D809019
dompurify/purify.min.js                C0845096A7C4A6741F362AC506C94C1C7D27DC603BCC1BF64A587F76F2DBE3A1
inter-latin-400-normal.woff2           8909904AB6C872EB994093482A88A28ECA2CD95912D7B6FECD72103B0DC07EDC
inter-latin-600-normal.woff2           F9A06E79CD3A2A20951C0F0E28F66DD0E6D3FDA73911D640A2125C8FCB78F21A
inter-latin-700-normal.woff2           6F56409FD3D64BB85F7D070BCE20749DB2D66B6D63CEC586CC22D1C761BE2491
jetbrains-mono-latin-400-normal.woff2  14425BA9C695763C1547F48A206B7AA60350A33AE23DE09F0407877F3FCD89EB
```

> 校验命令(PowerShell):`Get-FileHash <文件> -Algorithm SHA256`。
> 许可证全文:各库仓库根 `LICENSE`(MIT / BSD-3-Clause / Apache-2.0 / MPL-2.0 / ISC),OFL 见 https://openfontlicense.org 。
