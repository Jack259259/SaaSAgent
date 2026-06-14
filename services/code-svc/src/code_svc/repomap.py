"""repo map:符号图度中心性排序 + token 预算装载(Aider 思路,§5.1)。

度中心性 = 入度(被调用 + 被引用,×2 权重)+ 出度(本体发起的调用)。按分数降序,
逐条按 token 估算(≈chars/4)装入,超预算即截断并置 truncated。
"""

from __future__ import annotations

from .models import RepoMap, RepoMapEntry
from .store import SymbolStore

_CHARS_PER_TOKEN = 4


def _est_tokens(entry: RepoMapEntry) -> int:
    return (len(entry.file) + len(entry.signature) + len(entry.name) + 8) // _CHARS_PER_TOKEN + 1


def build_repo_map(store: SymbolStore, *, token_budget: int = 1000) -> RepoMap:
    definitions = store.all_definitions()
    incoming = store.incoming_degree()
    outgoing = store.outgoing_degree()

    scored = sorted(
        ((incoming.get(d.name, 0) * 2.0 + outgoing.get(d.name, 0) * 1.0, d) for d in definitions),
        key=lambda item: (-item[0], item[1].file, item[1].start_line),
    )

    entries: list[RepoMapEntry] = []
    used = 0
    truncated = False
    for score, d in scored:
        entry = RepoMapEntry(
            file=d.file,
            name=d.name,
            kind=d.kind,
            signature=d.snippet or f"{d.kind} {d.name}",
            score=score,
        )
        cost = _est_tokens(entry)
        if entries and used + cost > token_budget:
            truncated = True
            break
        entries.append(entry)
        used += cost

    return RepoMap(entries=entries, total_symbols=len(definitions), truncated=truncated)
