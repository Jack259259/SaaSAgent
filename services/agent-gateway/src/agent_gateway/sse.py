"""把编排器事件编码为 SSE 帧。协议见 docs/dev/sse-protocol.md。"""

from __future__ import annotations

import json

from orchestrator import OrchestratorEvent


def encode_sse(event: OrchestratorEvent) -> str:
    payload = json.dumps(event.data(), ensure_ascii=False)
    return f"event: {event.SSE_TYPE}\ndata: {payload}\n\n"
