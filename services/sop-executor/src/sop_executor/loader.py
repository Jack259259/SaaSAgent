"""从 assets/sops/*.yaml 加载 SOP 资产为 Sop 模型。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Sop

_DEFAULT_SOPS_DIR = Path("assets/sops")


def load_raw(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"SOP 不是映射:{path}")
    return data


def load_sop_file(path: Path) -> Sop:
    return Sop.model_validate(load_raw(path))


def sop_files(sops_dir: Path = _DEFAULT_SOPS_DIR) -> list[Path]:
    if not sops_dir.exists():
        return []
    return sorted(p for p in sops_dir.glob("*.yaml") if not p.name.startswith("_"))


def load_sops(sops_dir: Path = _DEFAULT_SOPS_DIR) -> dict[str, Sop]:
    return {sop.id: sop for sop in (load_sop_file(p) for p in sop_files(sops_dir))}
