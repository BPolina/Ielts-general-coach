#!/usr/bin/env python3
"""Пересборка MANIFEST.txt.

Манифест покрывает переносимую часть скилла — инструкции, модули, референсы,
шаблоны и код. `data/` исключён намеренно: он меняется каждым уроком, и хеши
устаревали бы к следующему занятию, превращая проверку целостности в шум.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "MANIFEST.txt"
SKIP_TOP = {"data", ".git", ".claude", "__pycache__"}

HEADER = [
    "IELTS General Coach Hybrid — manifest",
    "",
    "Покрывает переносимую часть скилла: инструкции, модули, референсы, шаблоны, код.",
    "data/ намеренно не включён — он меняется каждый урок, и хеши устаревали бы сразу.",
    "История изменений — в git, манифест нужен для проверки целостности копии.",
    "",
    "Пересобрать: python scripts/build_manifest.py",
    "",
]


def covered_files() -> list[pathlib.Path]:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(ROOT).parts
        if parts[0] in SKIP_TOP or "__pycache__" in parts or path.name == MANIFEST.name:
            continue
        files.append(path)
    return files


def main() -> int:
    lines = list(HEADER)
    for path in covered_files():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MANIFEST.txt: {len(lines) - len(HEADER)} файлов")
    return 0


if __name__ == "__main__":
    sys.exit(main())
