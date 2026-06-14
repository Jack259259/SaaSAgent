"""make sop-validate 的实现:对 contracts/sop/_schema.yaml 做 jsonschema 校验 + 静态交叉校验。

交叉校验(超出 schema):
1. 模板占位符 {{}} 闭合,且每个 name 都在 inputs.key 或 api.calls[].capture 输出名中有定义;
2. ui 步 confirm 标记与 requires_confirmation 一致(有 confirm 步必 requires_confirmation;
   requires_confirmation 且有 ui 步时,至少一个 confirm 步);
3. api 与 ui 至少其一存在(schema anyOf 已覆盖,这里给明确报错信息)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .loader import load_raw, sop_files
from .templating import has_unbalanced_braces, placeholders_in

_SCHEMA_PATH = Path("contracts/sop/_schema.yaml")


def _load_schema(schema_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(schema_path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("schema 不是映射")
    return data


def check_sop(raw: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = [f"schema: {e.message}" for e in sorted(validator.iter_errors(raw), key=str)]
    if schema_errors:
        return schema_errors  # 结构非法,后续交叉校验依赖结构,先返回

    errors: list[str] = []
    defined: set[str] = {i["key"] for i in raw.get("inputs", [])}
    for call in (raw.get("api") or {}).get("calls", []):
        defined |= set((call.get("capture") or {}).keys())

    scope = {
        "api": raw.get("api"),
        "ui": raw.get("ui"),
        "postconditions": raw.get("postconditions"),
    }
    if has_unbalanced_braces(scope):
        errors.append("cross: 占位符 {{ }} 未闭合")
    undefined = placeholders_in(scope) - defined
    if undefined:
        errors.append(f"cross: 占位符未在 inputs/capture 定义:{sorted(undefined)}")

    ui_steps = (raw.get("ui") or {}).get("steps", [])
    any_confirm = any(s.get("confirm") for s in ui_steps)
    requires = bool(raw.get("requires_confirmation"))
    if any_confirm and not requires:
        errors.append("cross: 存在 confirm 步但 requires_confirmation=false")
    if requires and ui_steps and not any_confirm:
        errors.append("cross: requires_confirmation=true 但 ui 无任何 confirm 步")

    if "api" not in raw and "ui" not in raw:
        errors.append("cross: api 与 ui 至少其一必须存在")
    return errors


def check_dir(sops_dir: Path, schema_path: Path = _SCHEMA_PATH) -> dict[str, list[str]]:
    schema = _load_schema(schema_path)
    return {p.name: check_sop(load_raw(p), schema) for p in sop_files(sops_dir)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sop-validate", description="SOP schema + 静态交叉校验")
    parser.add_argument("sops_dir", nargs="?", default="assets/sops")
    parser.add_argument("--schema", default=str(_SCHEMA_PATH))
    args = parser.parse_args(argv)

    results = check_dir(Path(args.sops_dir), Path(args.schema))
    total = 0
    for name, errs in results.items():
        if errs:
            total += len(errs)
            for err in errs:
                print(f"FAIL {name}: {err}")
        else:
            print(f"OK   {name}")
    if not results:
        print("sop-validate: 0 SOP(空目录,空跑)")
    print(f"sop-validate: {len(results)} SOP, {total} errors")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
