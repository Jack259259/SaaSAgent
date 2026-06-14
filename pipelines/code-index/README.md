# pipelines/code-index — 代码符号索引

实现位于 `services/code-svc/src/code_svc/indexer.py`(code-svc 是 workspace 包,可导入可测;
`pipelines/` 非 Python 包,管线逻辑落服务内,此处仅作入口指引)。

CLI(控制台脚本 `code-index`,见 code-svc 的 `[project.scripts]`):

```bash
uv run code-index --repos-root data/repos --db data/code-index/symbols.db
```

行为:扫描 repos_root 下受支持文件(python/js/ts/java/sql)→ tree-sitter 抽取定义/引用/调用边 →
SQLite 符号库;**空目录幂等空跑**;增量按文件 (mtime, size) 跳过未变更、删除已消失文件的符号。
仓投放与对接见 `docs/integration/code-repos.md`。CI webhook 增量重建为后续接入点。
