"""脱敏(§7.3):手机号 / 金额明细入库前打码,检索返回打码值。"""

from __future__ import annotations

from contracts import UserCtx
from memory_svc import BasicRedactor, MemoryKind, MemoryService


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


def test_basic_redactor_masks_phone_and_amount() -> None:
    out = BasicRedactor().redact("联系人 13800138000,预算 ¥123456.78 元")
    assert "13800138000" not in out and "138****8000" in out
    assert "123456" not in out and "[金额]" in out


async def test_stored_content_is_redacted(memory: MemoryService) -> None:
    await memory.save_profile(_uc(), "联系人 13800138000,预算 100万元", importance=0.9)
    hits = await memory.search_memory(_uc(), "联系人 预算", kinds=[MemoryKind.profile])
    assert hits
    content = hits[0].content
    assert "13800138000" not in content and "138****8000" in content
    assert "100万元" not in content and "[金额]" in content
