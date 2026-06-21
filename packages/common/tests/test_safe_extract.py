"""safe_extract 安全负例:zip-slip / 符号链接 / 解压炸弹 / 特殊文件 / 损坏包均必须被拒。"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from common.safe_extract import ExtractLimits, UnsafeArchiveError, safe_extract


def _zip(path: Path, entries: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return path


def _targz(path: Path, entries: list[tuple[str, bytes]]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in entries:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return path


# ---- 正例:正常仓解压 ---------------------------------------------------------- #
def test_zip_happy_path(tmp_path: Path) -> None:
    arc = _zip(tmp_path / "a.zip", [("repo/main.py", b"print(1)"), ("repo/sub/x.py", b"x=1")])
    dest = tmp_path / "out"
    n = safe_extract(arc, dest)
    assert n == 2
    assert (dest / "repo" / "main.py").read_bytes() == b"print(1)"
    assert (dest / "repo" / "sub" / "x.py").read_bytes() == b"x=1"


def test_targz_happy_path(tmp_path: Path) -> None:
    arc = _targz(tmp_path / "a.tar.gz", [("repo/m.py", b"ok")])
    dest = tmp_path / "out"
    assert safe_extract(arc, dest) == 1
    assert (dest / "repo" / "m.py").read_bytes() == b"ok"


# ---- zip-slip / 绝对路径 / 盘符 ----------------------------------------------- #
@pytest.mark.parametrize("evil", ["../evil.txt", "a/../../evil.txt", "/abs.txt", "C:/x.txt"])
def test_zip_path_traversal_rejected(tmp_path: Path, evil: str) -> None:
    arc = _zip(tmp_path / "e.zip", [(evil, b"x")])
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil.txt").exists()


def test_tar_path_traversal_rejected(tmp_path: Path) -> None:
    arc = _targz(tmp_path / "e.tar.gz", [("../evil.txt", b"x")])
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out")


# ---- 符号链接 / 硬链接 / 特殊文件 --------------------------------------------- #
def test_zip_symlink_member_rejected(tmp_path: Path) -> None:
    arc = tmp_path / "l.zip"
    with zipfile.ZipFile(arc, "w") as zf:
        zi = zipfile.ZipInfo("link")
        zi.external_attr = 0o120777 << 16  # S_IFLNK
        zf.writestr(zi, "/etc/passwd")
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out")


def test_tar_symlink_member_rejected(tmp_path: Path) -> None:
    arc = tmp_path / "l.tar.gz"
    with tarfile.open(arc, "w:gz") as tf:
        ti = tarfile.TarInfo("link")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/passwd"
        tf.addfile(ti)
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out")


def test_tar_special_file_rejected(tmp_path: Path) -> None:
    arc = tmp_path / "f.tar.gz"
    with tarfile.open(arc, "w:gz") as tf:
        ti = tarfile.TarInfo("fifo")
        ti.type = tarfile.FIFOTYPE
        tf.addfile(ti)
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out")


# ---- 解压炸弹:成员数 / 总字节 / 膨胀比 --------------------------------------- #
def test_bomb_max_files(tmp_path: Path) -> None:
    arc = _zip(tmp_path / "many.zip", [(f"f{i}.py", b"x") for i in range(6)])
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out", limits=ExtractLimits(max_files=3))


def test_bomb_max_total_bytes(tmp_path: Path) -> None:
    arc = _zip(tmp_path / "big.zip", [("f.py", b"a" * 1000)])
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out", limits=ExtractLimits(max_total_bytes=100))


def test_bomb_ratio(tmp_path: Path) -> None:
    # 高度可压缩负载:解压后远大于压缩包 → 膨胀比触顶。
    arc = _zip(tmp_path / "zip_bomb.zip", [("f.py", b"a" * 200_000)])
    with pytest.raises(UnsafeArchiveError):
        safe_extract(arc, tmp_path / "out", limits=ExtractLimits(max_ratio=50))


# ---- 不支持格式 / 损坏包 ------------------------------------------------------ #
def test_unsupported_format_rejected(tmp_path: Path) -> None:
    p = tmp_path / "x.rar"
    p.write_bytes(b"Rar!\x1a\x07\x00")
    with pytest.raises(UnsafeArchiveError):
        safe_extract(p, tmp_path / "out")


def test_corrupted_zip_rejected(tmp_path: Path) -> None:
    p = tmp_path / "broken.zip"
    p.write_bytes(b"PK\x03\x04 not really a zip")
    with pytest.raises(UnsafeArchiveError):
        safe_extract(p, tmp_path / "out")
