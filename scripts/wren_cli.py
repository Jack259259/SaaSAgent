"""wren CLI 包装:`uv run python scripts/wren_cli.py <args>` 等价于 `wren <args>`。

Windows 下 uv 生成的 console-script .exe trampoline 无法 canonicalize 含非 ASCII
(中文)字符的仓库路径(Makefile 抬头有同一约定);以 python 直调 typer app 绕过。
开发期命令(语义层校验/编译),非运行时依赖 —— 运行时经 data_svc.wren_local 惰性 import。
"""

from wren.cli import app

if __name__ == "__main__":
    app()
