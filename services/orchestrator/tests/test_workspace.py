"""工作区:put/get/分页 read,大对象只回摘要+句柄(红线 8)。"""

from __future__ import annotations

import pytest

from orchestrator import Workspace


def test_put_get_and_paginated_read() -> None:
    ws = Workspace()
    ref = ws.put(key="sql", type="sql_result", summary="3 行", raw="x" * 5000)
    assert ref.startswith("ws://sql/")
    assert ws.get(ref).summary == "3 行"

    page1 = ws.read(ref, page=1, page_size=2000)
    assert len(page1.chunk) == 2000
    assert page1.total_pages == 3
    assert page1.eof is False

    page3 = ws.read(ref, page=3, page_size=2000)
    assert page3.eof is True
    assert ws.size() == 1


def test_dict_raw_is_json_serialized() -> None:
    ws = Workspace()
    ref = ws.put(key="d", type="doc_chunks", summary="s", raw={"a": 1})
    assert '"a"' in ws.read(ref).chunk


def test_get_missing_raises() -> None:
    ws = Workspace()
    with pytest.raises(KeyError):
        ws.get("ws://nope/1")


def test_read_invalid_page_rejected() -> None:
    ws = Workspace()
    ref = ws.put(key="k", type="sql_result", summary="s", raw="abc")
    with pytest.raises(ValueError, match="≥ 1"):
        ws.read(ref, page=0)
