# contracts/toolspec/base — 基础工具基线 v0.2(13 件)

清单与治理见方案 §5.5。规格 YAML(一工具一文件)在**阶段 1**落地:

update_plan、ask_user、get_page_context、read_workspace、write_workspace、run_analysis、
export_file、parse_user_file、save_memory、schedule_task 系(schedule_task / list_schedules /
cancel_schedule)、notify、escalate_to_human、web_search / web_fetch(`enabled_by_default: false`)。

红线:run_analysis 沙箱强隔离(红线 11);主 Agent 不持裸 Bash / 全局文件读写 / 全局 grep(红线 12);
web_search / web_fetch 默认关闭、按角色 + 域名白名单开启(红线 13)。
