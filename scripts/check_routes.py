#!/usr/bin/env python3
"""Проверка маршрутов к референсам и шаблонам.

Осиротевший файл лежит на диске, но недостижим из `SKILL.md`, `CLAUDE.md` и модулей —
тренер его не прочитает и не узнает, что он существует. Это тихая потеря: ничего не
ломается, просто часть методики перестаёт применяться.

Заодно проверяет, что каждый упомянутый путь действительно существует.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH_PATTERN = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|json|jsonl|py|html))`")


def routers() -> list[pathlib.Path]:
    return [ROOT / "SKILL.md", ROOT / "CLAUDE.md"] + sorted(ROOT.glob("skills/*/SKILL.md"))


def main() -> int:
    routed = "\n".join(p.read_text(encoding="utf-8") for p in routers() if p.exists())
    orphans = [
        target.relative_to(ROOT).as_posix()
        for target in sorted(ROOT.glob("references/*.md")) + sorted(ROOT.glob("templates/*.md"))
        if target.name not in routed
    ]

    broken: list[str] = []
    checked = 0
    for source in routers() + sorted(ROOT.glob("references/*.md")):
        if not source.exists():
            continue
        for match in PATH_PATTERN.finditer(source.read_text(encoding="utf-8")):
            target = match.group(1)
            if "*" in target:
                continue
            checked += 1
            if not (ROOT / target).exists():
                broken.append(f"{source.relative_to(ROOT).as_posix()} -> {target}")

    for item in orphans:
        print(f"ORPHAN  {item}")
    for item in broken:
        print(f"BROKEN  {item}")
    print(f"маршрутов проверено: {checked}, осиротевших файлов: {len(orphans)}, битых ссылок: {len(broken)}")
    return 1 if orphans or broken else 0


if __name__ == "__main__":
    sys.exit(main())
