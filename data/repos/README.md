# data/repos — 代码仓上传区(人工)

此目录由**人工放入**待索引的代码仓(`git clone` 到此),供 code-svc 索引与问答。

- **真实代码不入库**:除本 README 外,本目录内容被 `.gitignore` 忽略,不进 git(避免把第三方/业务代码混入本仓)。
- 空目录索引幂等空跑;支持 python / javascript / typescript / java / sql(best-effort)。

```bash
git clone <repo-url> data/repos/<repo-name>
uv run code-index --repos-root data/repos --db data/code-index/symbols.db
```

详细对接(增量刷新、Zoekt 选用)见 `docs/integration/code-repos.md`。
