<!-- AUTO-GENERATED:由 `uv run python -m contracts.docgen` 生成,请勿手工编辑。改动工具规格后重新生成(contract-test 会校验本文件未漂移)。 -->
# 工具索引(自动生成)

汇总 `contracts/toolspec/` 下全部工具规格(CLAUDE.md §5 / DoD §7 第 4 条)。

| 工具 | 域 | side_effects | confirmation_required | enabled_by_default |
|------|----|--------------|-----------------------|--------------------|
| `search_knowledge` | rag | read | false | true |
| `query_finance_data` | data | read | false | true |
| `ask_codebase` | code | read | false | true |
| `find_sop` | sop | read | false | true |
| `run_sop` | sop | write | true | true |
| `ask_user` | base | read | false | true |
| `cancel_schedule` | base | assistant_write | false | true |
| `escalate_to_human` | base | assistant_write | false | true |
| `export_file` | base | read | false | true |
| `get_page_context` | base | read | false | true |
| `list_schedules` | base | read | false | true |
| `notify` | base | assistant_write | false | true |
| `parse_user_file` | base | read | false | true |
| `read_workspace` | base | read | false | true |
| `run_analysis` | base | read | false | true |
| `save_memory` | base | assistant_write | false | true |
| `schedule_task` | base | assistant_write | true | true |
| `update_plan` | base | read | false | true |
| `web_fetch` | base | read | false | false |
| `web_search` | base | read | false | false |
| `write_workspace` | base | assistant_write | false | true |
