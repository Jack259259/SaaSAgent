"""脱敏钩子(§7.3):写入前过 PII / 金额明细。接口化 + 基础规则,可替换为更强实现。"""

from __future__ import annotations

import re
from typing import Protocol

# 中国手机号(11 位,1[3-9] 开头),避免匹配更长数字串
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
# 金额明细:¥/￥ 前缀,或 数字 + 元/万元/亿元 后缀
_AMOUNT_RE = re.compile(r"[¥￥]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:亿元|万元|元)")


class Redactor(Protocol):
    def redact(self, text: str) -> str: ...


class BasicRedactor:
    def redact(self, text: str) -> str:
        text = _PHONE_RE.sub(r"\1****\2", text)  # 138****5678
        return _AMOUNT_RE.sub("[金额]", text)
