"""知识库管理端点(/admin/kb):角色门控 + IT 库细 ACL + 上传/下载/ingest + 安全负例(红线 3/5/9)。

ingest 进程内后台线程(无子进程);测试以轮询 status 至 done 验证全流程。
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_gateway import kb
from agent_gateway.app import app

_INTERNAL = json.dumps(
    {
        "tenant_id": "t",
        "user_id": "u",
        "roles": ["internal_dev"],
        "data_scope": {},
        "permissions": [],
    }
)
# 管理员但**非**内部(可管业务库,不可碰 it_design)
_KB_ADMIN = json.dumps(
    {"tenant_id": "t", "user_id": "u", "roles": ["kb_admin"], "data_scope": {}, "permissions": []}
)
_USER = json.dumps(
    {
        "tenant_id": "t",
        "user_id": "u",
        "roles": ["tenant_user"],
        "data_scope": {},
        "permissions": [],
    }
)


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_KNOWLEDGE_DIR", str(tmp_path / "knowledge"))
    kb._reset_jobs()


def _docx_bytes() -> io.BytesIO:
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>文档正文</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    buf.seek(0)
    return buf


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _poll_done(client: TestClient, kb_name: str, headers: dict[str, str]) -> dict[str, object]:
    deadline = time.time() + 10.0
    while time.time() < deadline:
        st: dict[str, object] = client.get(
            f"/admin/kb/{kb_name}/ingest/status", headers=headers
        ).json()
        if st.get("status") in ("done", "failed"):
            return st
        time.sleep(0.05)
    return {"status": "timeout"}


# ---- 角色门控(安全,红线 3) -------------------------------------------------- #
def test_missing_ctx_401() -> None:
    assert TestClient(app).get("/admin/kb/business/docs").status_code == 401


def test_non_admin_403() -> None:
    r = TestClient(app).get("/admin/kb/business/docs", headers={"X-User-Ctx": _USER})
    assert r.status_code == 403


def test_admin_list_empty() -> None:
    r = TestClient(app).get("/admin/kb/business/docs", headers={"X-User-Ctx": _INTERNAL})
    assert r.status_code == 200 and r.json() == []


# ---- IT 设计库细 ACL(仅内部角色,红线 5/§9.1) ------------------------------- #
def test_it_design_non_internal_403() -> None:
    r = TestClient(app).get("/admin/kb/it_design/docs", headers={"X-User-Ctx": _KB_ADMIN})
    assert r.status_code == 403


def test_it_design_internal_ok() -> None:
    r = TestClient(app).get("/admin/kb/it_design/docs", headers={"X-User-Ctx": _INTERNAL})
    assert r.status_code == 200 and r.json() == []


# ---- 非法 kb(防注入:kb 限枚举) -------------------------------------------- #
def test_invalid_kb_docs_404() -> None:
    r = TestClient(app).get("/admin/kb/evil/docs", headers={"X-User-Ctx": _INTERNAL})
    assert r.status_code == 404 and r.json()["code"] == "INVALID_KB"


def test_invalid_kb_ingest_404() -> None:
    r = TestClient(app).post("/admin/kb/evil/ingest", headers={"X-User-Ctx": _INTERNAL})
    assert r.status_code == 404 and r.json()["code"] == "INVALID_KB"


def test_src_dir_fixed_mapping() -> None:
    # ingest 的 src 取自固定映射(非用户可控路径)——命令注入面为零。
    assert kb.kb_src_dir("business").name == "business"
    assert kb.kb_src_dir("it_design").name == "it-design"


# ---- 文件名校验 / 路径穿越(单元) -------------------------------------------- #
def test_sanitize_rejects_bad_names() -> None:
    for bad in ["../evil.md", "a/b.md", "..\\evil.md", "", "   ", "no_ext", "x.pdf"]:
        with pytest.raises(kb.KbError):
            kb.sanitize_doc_name(bad)


def test_sanitize_allows_unicode() -> None:
    assert kb.sanitize_doc_name("资金计划 v1.docx") == "资金计划 v1.docx"


# ---- 上传:类型 / MIME / 大小 ------------------------------------------------- #
def test_upload_md_happy() -> None:
    r = TestClient(app).post(
        "/admin/kb/business/upload",
        headers={"X-User-Ctx": _INTERNAL},
        files={"file": ("guide.md", io.BytesIO("# 标题\n\n正文。".encode()), "text/markdown")},
    )
    assert r.status_code == 200 and r.json()["name"] == "guide.md"
    assert (kb.kb_src_dir("business") / "guide.md").is_file()


def test_upload_docx_happy() -> None:
    r = TestClient(app).post(
        "/admin/kb/business/upload",
        headers={"X-User-Ctx": _INTERNAL},
        files={"file": ("plan.docx", _docx_bytes(), _DOCX_MIME)},
    )
    assert r.status_code == 200
    assert (kb.kb_src_dir("business") / "plan.docx").is_file()


def test_upload_bad_ext_400() -> None:
    r = TestClient(app).post(
        "/admin/kb/business/upload",
        headers={"X-User-Ctx": _INTERNAL},
        files={"file": ("evil.exe", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INPUT"


def test_upload_bad_mime_400() -> None:
    r = TestClient(app).post(
        "/admin/kb/business/upload",
        headers={"X-User-Ctx": _INTERNAL},
        files={"file": ("guide.md", io.BytesIO(b"# x"), "application/pdf")},
    )
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INPUT"


def test_upload_corrupt_docx_400() -> None:
    r = TestClient(app).post(
        "/admin/kb/business/upload",
        headers={"X-User-Ctx": _INTERNAL},
        files={"file": ("broken.docx", io.BytesIO(b"not a zip"), _DOCX_MIME)},
    )
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INPUT"


def test_upload_too_large_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kb, "MAX_DOC_BYTES", 8)  # 裁断阈值调小,避免大内存
    r = TestClient(app).post(
        "/admin/kb/business/upload",
        headers={"X-User-Ctx": _INTERNAL},
        files={"file": ("big.txt", io.BytesIO(b"0123456789"), "text/plain")},
    )
    assert r.status_code == 413 and r.json()["code"] == "TOO_LARGE"


# ---- 下载 -------------------------------------------------------------------- #
def test_download_happy_and_missing() -> None:
    client = TestClient(app)
    h = {"X-User-Ctx": _INTERNAL}
    client.post(
        "/admin/kb/business/upload",
        headers=h,
        files={"file": ("guide.md", io.BytesIO("内容X".encode()), "text/markdown")},
    )
    ok = client.get("/admin/kb/business/docs/guide.md/download", headers=h)
    assert ok.status_code == 200 and "内容X" in ok.text
    miss = client.get("/admin/kb/business/docs/nope.md/download", headers=h)
    assert miss.status_code == 404 and miss.json()["code"] == "NOT_FOUND"


# ---- ingest 全流程(上传 → 触发 → 轮询 done → 已索引) ------------------------ #
def test_ingest_flow_indexes_doc() -> None:
    client = TestClient(app)
    h = {"X-User-Ctx": _INTERNAL}
    up = client.post(
        "/admin/kb/business/upload",
        headers=h,
        files={
            "file": ("guide.md", io.BytesIO("# 标题\n\n执行率口径正文。".encode()), "text/markdown")
        },
    )
    assert up.status_code == 200
    docs = client.get("/admin/kb/business/docs", headers=h).json()
    assert docs[0]["name"] == "guide.md" and docs[0]["indexed"] is False

    ing = client.post("/admin/kb/business/ingest", headers=h)
    assert ing.status_code == 200 and ing.json()["status"] == "running" and ing.json()["task_id"]
    st = _poll_done(client, "business", h)
    assert st["status"] == "done"

    docs2 = client.get("/admin/kb/business/docs", headers=h).json()
    assert docs2[0]["indexed"] is True


def test_ingest_concurrent_same_kb_409() -> None:
    client = TestClient(app)
    h = {"X-User-Ctx": _INTERNAL}
    # 直接注入一个"运行中"job,模拟同库并发触发被拒(确定性,不依赖时序)。
    kb._jobs["business"] = kb._IngestJob("business")  # status=running
    r = client.post("/admin/kb/business/ingest", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "INGEST_RUNNING"
