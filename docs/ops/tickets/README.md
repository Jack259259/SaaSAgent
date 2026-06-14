# docs/ops/tickets —— 转人工工单(运行产物)

`escalate_to_human` 经 `FileTicketGateway` 在此落 `<ticket_id>.json`(工单 + 上下文移交,按接收方权限脱敏)。
**JSON 为运行产物,不入库**(`.gitignore: docs/ops/**/*.json`);生产应接现有工单/工作流引擎。
