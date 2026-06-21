"""硬化压缩包解压(红线 11/14):防 zip-slip / 解压炸弹 / 符号链接逃逸。

支持 ``.zip`` / ``.tar`` / ``.tar.gz`` / ``.tar.bz2``。逐成员校验:
路径必须落在目标目录内(拒绝绝对路径、盘符、``..`` 穿越);拒绝符号 / 硬链接与设备等特殊文件;
并施加解压后总字节、成员数、膨胀比上限(防炸弹)。被守卫拦下即抛 :class:`UnsafeArchiveError`。

供 code-svc 代码仓上传与(未来)``/skills/upload`` 复用——单一事实源,不在各处重复造解压。
"""

from __future__ import annotations

import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_CHUNK = 64 * 1024
_TarReadMode = Literal["r:", "r:gz", "r:bz2"]


class UnsafeArchiveError(Exception):
    """压缩包被安全守卫拒绝(zip-slip / 炸弹 / 符号链接 / 非法成员 / 不支持格式)。"""


@dataclass(frozen=True)
class ExtractLimits:
    """解压上限(防炸弹)。默认对真实代码仓宽松、对炸弹收紧;部署可调。"""

    max_total_bytes: int = 500 * 1024 * 1024  # 解压后总字节
    max_files: int = 50_000  # 成员数
    max_ratio: float = 200.0  # 解压后总字节 / 压缩包字节


# tar 变体 → tarfile 打开模式(显式枚举,不接受未知后缀)。
_TAR_MODES: dict[str, _TarReadMode] = {
    ".tar": "r:",
    ".tar.gz": "r:gz",
    ".tgz": "r:gz",
    ".tar.bz2": "r:bz2",
    ".tbz2": "r:bz2",
}


def is_supported_archive(name: str) -> bool:
    n = name.lower()
    return n.endswith(".zip") or any(n.endswith(ext) for ext in _TAR_MODES)


def _tar_mode(name: str) -> _TarReadMode:
    n = name.lower()
    for ext, mode in _TAR_MODES.items():
        if n.endswith(ext):
            return mode
    raise UnsafeArchiveError(f"不支持的压缩格式: {name!r}")


def _safe_target(dest_root: Path, member_name: str) -> Path:
    """把成员名解析为 dest_root 内的安全目标路径;越界 / 绝对 / 盘符即拒。"""
    if not member_name or member_name.startswith(("/", "\\")):
        raise UnsafeArchiveError(f"非法成员路径(绝对): {member_name!r}")
    norm = member_name.replace("\\", "/")
    head = norm.split("/", 1)[0]
    if ":" in head:  # 盘符如 C: / UNC
        raise UnsafeArchiveError(f"非法成员路径(盘符): {member_name!r}")
    target = (dest_root / norm).resolve()
    root = dest_root.resolve()
    if target != root and root not in target.parents:
        raise UnsafeArchiveError(f"路径穿越(zip-slip): {member_name!r}")
    return target


class _Accountant:
    """累计成员数 / 解压字节,超限即拒(防炸弹)。"""

    def __init__(self, limits: ExtractLimits, compressed_bytes: int) -> None:
        self._limits = limits
        self._compressed = max(1, compressed_bytes)
        self.files = 0
        self.total = 0

    def add(self, declared_size: int) -> None:
        self.files += 1
        self.total += max(0, declared_size)
        if self.files > self._limits.max_files:
            raise UnsafeArchiveError(f"成员数超上限(>{self._limits.max_files})")
        if self.total > self._limits.max_total_bytes:
            raise UnsafeArchiveError(f"解压总大小超上限(>{self._limits.max_total_bytes} 字节)")
        if self.total / self._compressed > self._limits.max_ratio:
            raise UnsafeArchiveError(f"膨胀比超上限(>{self._limits.max_ratio}x,疑似炸弹)")


def _copy_member(src: object, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as dst:
        while True:
            chunk = src.read(_CHUNK)  # type: ignore[attr-defined]
            if not chunk:
                break
            dst.write(chunk)


def _extract_zip(archive: Path, dest_root: Path, acc: _Accountant) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):  # 目录项:仅校验路径
                _safe_target(dest_root, name.rstrip("/"))
                continue
            mode = (info.external_attr >> 16) & 0xFFFF  # unix mode(若有)
            if mode and (mode & 0o170000) == 0o120000:
                raise UnsafeArchiveError(f"拒绝符号链接成员: {name!r}")
            acc.add(info.file_size)
            target = _safe_target(dest_root, name)
            with zf.open(info) as src:
                _copy_member(src, target)


def _extract_tar(archive: Path, dest_root: Path, acc: _Accountant) -> None:
    with tarfile.open(archive, _tar_mode(archive.name)) as tf:
        for member in tf.getmembers():
            if member.isdir():
                _safe_target(dest_root, member.name)
                continue
            if member.issym() or member.islnk():
                raise UnsafeArchiveError(f"拒绝(符号/硬)链接成员: {member.name!r}")
            if not member.isfile():
                raise UnsafeArchiveError(f"拒绝特殊文件成员(设备/FIFO 等): {member.name!r}")
            acc.add(member.size)
            target = _safe_target(dest_root, member.name)
            src = tf.extractfile(member)
            if src is None:
                raise UnsafeArchiveError(f"无法读取成员: {member.name!r}")
            with src:
                _copy_member(src, target)


def safe_extract(archive_path: Path, dest_dir: Path, *, limits: ExtractLimits | None = None) -> int:
    """安全解压 ``archive_path`` 到 ``dest_dir``(自动创建)。

    返回解压文件数;不安全即抛 :class:`UnsafeArchiveError`。"""
    limits = limits or ExtractLimits()
    name = archive_path.name.lower()
    dest_dir.mkdir(parents=True, exist_ok=True)
    acc = _Accountant(limits, archive_path.stat().st_size)
    try:
        if name.endswith(".zip"):
            _extract_zip(archive_path, dest_dir, acc)
        elif is_supported_archive(name):
            _extract_tar(archive_path, dest_dir, acc)
        else:
            raise UnsafeArchiveError(f"不支持的压缩格式: {archive_path.name!r}")
    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        raise UnsafeArchiveError(f"压缩包损坏或无法解析: {exc}") from exc
    return acc.files
