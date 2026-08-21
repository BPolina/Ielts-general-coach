#!/usr/bin/env python3
"""Local data CLI for IELTS General Coach Hybrid.

Stdlib only. It manages vocabulary SRS, error tracking, sessions,
assessments, weekly reports, validation, and a static HTML dashboard.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("IELTS_COACH_HOME", PROJECT_ROOT / "data")).expanduser()
LOG_DIR = DATA_ROOT / "logs"
BACKUP_DIR = DATA_ROOT / ".backups"
REPORT_DIR = DATA_ROOT / "reports"
VOCAB_FILE = DATA_ROOT / "vocabulary.json"
ERROR_FILE = DATA_ROOT / "errors.json"
STATE_FILE = DATA_ROOT / "current_state.json"
SESSIONS_FILE = LOG_DIR / "sessions.jsonl"
ASSESSMENTS_FILE = LOG_DIR / "assessments.jsonl"
VOCAB_REVIEWS_FILE = LOG_DIR / "vocabulary_reviews.jsonl"
EVENTS_FILE = LOG_DIR / "events.jsonl"
DASHBOARD_FILE = DATA_ROOT / "dashboard.html"
DECISIONS_FILE = LOG_DIR / "decisions.jsonl"
OPEN_VERIFICATIONS_FILE = LOG_DIR / "open_verifications.jsonl"

LOG_FILES = {
    "sessions": SESSIONS_FILE,
    "assessments": ASSESSMENTS_FILE,
    "vocabulary-reviews": VOCAB_REVIEWS_FILE,
    "decisions": DECISIONS_FILE,
    "open-verifications": OPEN_VERIFICATIONS_FILE,
    "events": EVENTS_FILE,
}

REQUIRED_PROJECT_FILES = [
    "SKILL.md",
    "README.md",
    "config/student_profile.json",
    "config/policies.json",
    "references/scoring_policy.md",
    "references/error_taxonomy.md",
    "skills/diagnostics/SKILL.md",
    "skills/vocabulary/SKILL.md",
    "skills/writing-general-task1/SKILL.md",
    "skills/writing-task2/SKILL.md",
    "skills/listening/SKILL.md",
    "skills/reading-general/SKILL.md",
    "skills/speaking/SKILL.md",
]

POLICY_FILE = PROJECT_ROOT / "config" / "policies.json"

# Запасные значения на случай отсутствия файла. Совпадают с config/policies.json:
# validate следит, чтобы конфиг не разошёлся ни с ними, ни с числами в прозе.
DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "errors": {"stable_successes": 3, "stable_unique_dates": 3, "stable_unique_contexts": 2},
    "vocabulary": {"minimum_delayed_recall_rate": 0.7, "new_items_pause_when_overdue_exceeds": 25},
    "estimation": {"minimum_conflict_band_delta": 0.5,
                   "stable_receptive_result_requires_comparable_full_tests": 3},
}

NUMBER_WORDS = {1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять"}

# Где то же число записано прозой. Тренер читает прозу, код читает конфиг —
# разойтись они не должны, поэтому validate сверяет одно с другим.
PROSE_ANCHORS: list[tuple[tuple[str, str], str, Any]] = [
    (("errors", "stable_unique_dates"), "SKILL.md", lambda v: f"минимум {NUMBER_WORDS[v]} успешных"),
    (("errors", "stable_unique_contexts"), "SKILL.md", lambda v: f"минимум {NUMBER_WORDS[v]} разных контекста"),
    (("vocabulary", "minimum_delayed_recall_rate"), "SKILL.md", lambda v: f"{v * 100:.0f}%"),
    (("vocabulary", "minimum_delayed_recall_rate"), "skills/vocabulary/SKILL.md", lambda v: f"{v * 100:.0f}%"),
    (("vocabulary", "minimum_delayed_recall_rate"), "references/adaptation_rules.md", lambda v: f"{v * 100:.0f}%"),
    (("vocabulary", "new_items_pause_when_overdue_exceeds"), "skills/vocabulary/SKILL.md", lambda v: f"> {v}"),
    (("vocabulary", "new_items_pause_when_overdue_exceeds"), "references/adaptation_rules.md", lambda v: f"> {v}"),
    (("estimation", "minimum_conflict_band_delta"), "references/source_policy.md", lambda v: f"{v} band"),
    (("estimation", "stable_receptive_result_requires_comparable_full_tests"),
     "references/scoring_policy.md", lambda v: f"минимум {NUMBER_WORDS[v]} полных"),
]

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Кириллица проходит в CLI без потерь и через PowerShell, и через bash — проверено
# 2026-08-06. Транслитерация не нужна: она делает журнал нечитаемым и неищущимся.
# Записи старше этой даты проверку не проходят и не должны: переписывать историю
# механическим обратным транслитом опаснее, чем оставить как есть.
TRANSLIT_CONVENTION_DATE = "2026-08-07"
TRANSLIT_MARKERS = re.compile(
    r"\b(?:ne|chto|eto|dlya|ochen|zhe|byla?|bylo|uzhe|tolko|esli|posle|pered|kotor\w*"
    r"|oshibk\w*|uchenits\w*|zafiksirov\w*|proverk\w*|slov\w*|nedel\w*)\b|zh|kh|shch|tsiya",
    re.IGNORECASE,
)
CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def check_transliteration(created_field: str, path: Path) -> list[str]:
    """Предупреждает о транслите в записях, созданных после принятия соглашения."""
    warnings = []
    for item in load_json(path, {"items": []}).get("items", []):
        if str(item.get(created_field, "")) < TRANSLIT_CONVENTION_DATE:
            continue
        for field, value in item.items():
            if not isinstance(value, str) or len(value) <= 25:
                continue
            if CYRILLIC.search(value) or not TRANSLIT_MARKERS.search(value):
                continue
            warnings.append(
                f"{path.name}: {item.get('id')}.{field} записано латиницей — "
                "русский текст пиши кириллицей"
            )
    return warnings


def load_policies() -> dict[str, dict[str, Any]]:
    stored = load_json(POLICY_FILE, {})
    merged = {section: dict(values) for section, values in DEFAULT_POLICIES.items()}
    for section, values in stored.items():
        if section.startswith("_") or not isinstance(values, dict):
            continue
        merged.setdefault(section, {}).update(values)
    return merged


def check_prose_drift(policies: dict[str, dict[str, Any]]) -> list[str]:
    """Ловит расхождение конфига с числами в прозе.

    Числа намеренно оставлены в тексте: тренер должен видеть порог сразу, не
    открывая второй файл. Цена — риск разъехаться, и вот он снимается здесь.
    """
    problems = []
    for (section, key), rel, render in PROSE_ANCHORS:
        value = policies.get(section, {}).get(key)
        path = PROJECT_ROOT / rel
        if value is None or not path.exists():
            continue
        try:
            expected = render(value)
        except (KeyError, TypeError, ValueError):
            problems.append(f"{rel}: не умею записать словами {section}.{key} = {value}")
            continue
        if expected not in path.read_text(encoding="utf-8"):
            problems.append(
                f"{rel}: конфиг говорит {section}.{key} = {value}, "
                f"но в тексте нет «{expected}» — проза разошлась с config/policies.json"
            )
    return problems

# Поля, которые нужны тренеру на уроке. Всё остальное (explanation, signature,
# successful_evidence, source, task) — архив: подтягивается точечно через
# show-error по конкретному id, а не грузится пачкой в контекст.
LEAN_ERROR_FIELDS = ("id", "category", "severity", "status", "recurrence_count",
                     "original", "correction", "next_review")
LEAN_VOCAB_FIELDS = ("id", "chunk", "meaning_ru", "register", "pattern", "example", "mastery")


def empty_uses() -> dict[str, list[str]]:
    """Режимы проверки словарной единицы. `register` добавлен 2026-08-06:
    модуль словаря требовал проверять регистр, а записывать его было некуда."""
    return {"meaning": [], "form": [], "register": [], "spoken": [], "written": []}


def lean_view(item: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {key: item[key] for key in fields if key in item}


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {value}") from exc


def ensure_layout() -> None:
    for directory in [DATA_ROOT, LOG_DIR, BACKUP_DIR, REPORT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    for path in LOG_FILES.values():
        path.touch(exist_ok=True)
    if not VOCAB_FILE.exists():
        atomic_write_json(VOCAB_FILE, {"schema_version": 2, "items": []}, backup=False)
    if not ERROR_FILE.exists():
        atomic_write_json(ERROR_FILE, {"schema_version": 2, "items": []}, backup=False)
    if not STATE_FILE.exists():
        atomic_write_json(STATE_FILE, {
            "schema_version": 2,
            "phase": "diagnostic_not_started",
            "week_number": 0,
            "week_start": None,
            "current_goals": [],
            "priority_error_ids": [],
            "carryover": [],
            "last_session_date": None,
            "last_control_date": None,
            "language_mix": {"english": 0.4, "russian": 0.6},
            "notes": "Start with: Начать диагностическую неделю",
        }, backup=False)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(path, BACKUP_DIR / f"{path.name}.{stamp}.bak")


def atomic_write_json(path: Path, payload: Any, backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        backup_file(path)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSONL in {path} line {line_no}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected object in {path} line {line_no}")
            result.append(value)
    return result


def load_corrections() -> tuple[dict[str, dict[str, Any]], set[str], list[str]]:
    """Собирает исправления из записей, несущих `supersedes`.

    Строки логов append-only и не переписываются. Исправление — это новая запись,
    которая называет отменяемые id и говорит, что с ними делать:

    * `corrections: {поле: значение}` — правка полей (запись остаётся, меняется поле);
    * `retract: true` — отзыв (запись выпадает из аналитики целиком).

    Нет ни того, ни другого — запись считается пояснительной и на данные не влияет.
    Умолчание намеренно безопасное: молча выбросить доказательство хуже, чем не
    применить исправление, поэтому такой случай ловит `validate`.

    Правки применяются в порядке timestamp и собираются со ВСЕХ записей, включая
    те, что сами кем-то отменены: правка — это факт о данных («здесь неверная
    дата»), а не суждение, и отмена более поздним решением её не откатывает.
    """
    decision_ids = {rec.get("id") for rec in read_jsonl(DECISIONS_FILE)}
    carriers: list[dict[str, Any]] = []
    for path in LOG_FILES.values():
        carriers.extend(rec for rec in read_jsonl(path) if rec.get("supersedes"))
    carriers.sort(key=lambda rec: str(rec.get("timestamp", "")))
    # Запись с `restates` переизлагает прозаическое исправление машиночитаемо.
    # Переизложенный оригинал больше не считается неприменённым.
    restated = {rec["restates"] for rec in carriers if rec.get("restates")}

    patches: dict[str, dict[str, Any]] = {}
    retracted: set[str] = set()
    problems: list[str] = []
    for rec in carriers:
        targets = rec.get("supersedes")
        targets = [targets] if isinstance(targets, str) else list(targets)
        patch = rec.get("corrections") or {}
        retract = bool(rec.get("retract"))
        if not patch and not retract:
            if rec.get("id") in restated:
                pass  # переизложено машиночитаемо более поздней записью
            elif all(target in decision_ids for target in targets):
                # Решение уточняет решение: меняется актуальность вывода, а не данные.
                for target in targets:
                    patches.setdefault(target, {})["superseded_by"] = rec.get("id")
            else:
                problems.append(
                    f"{rec.get('id')}: supersedes ссылается на записи-доказательства, "
                    "но не несёт ни corrections, ни retract — исправление не применяется"
                )
            continue
        for target in targets:
            if retract:
                retracted.add(target)
            if patch:
                patches.setdefault(target, {}).update(patch)
    return patches, retracted, problems


def read_log(path: Path, patches: dict[str, dict[str, Any]] | None = None,
             retracted: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Читает журнал с применёнными исправлениями. Возвращает записи и счётчики."""
    if patches is None or retracted is None:
        patches, retracted, _ = load_corrections()
    records: list[dict[str, Any]] = []
    stats = {"corrected": 0, "retracted": 0}
    for record in read_jsonl(path):
        record_id = record.get("id")
        if record_id in retracted:
            stats["retracted"] += 1
            continue
        if record_id in patches:
            patch = patches[record_id]
            record = {**record, **patch}
            if set(patch) - {"superseded_by"}:  # правка полей, а не только отметка об отмене
                record["corrected"] = True
                stats["corrected"] += 1
        records.append(record)
    return records, stats


def next_id(items: Iterable[dict[str, Any]], prefix: str) -> str:
    highest = 0
    for item in items:
        raw = str(item.get("id", ""))
        if raw.startswith(prefix):
            try:
                highest = max(highest, int(raw[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{highest + 1:04d}"


def update_mastery(item: dict[str, Any]) -> None:
    successful = item.setdefault("successful_uses", empty_uses())
    spoken_dates = set(successful.get("spoken", []))
    written_dates = set(successful.get("written", []))
    all_review_dates = set(item.get("successful_review_dates", []))
    repetitions = int(item.get("srs", {}).get("repetitions", 0))

    if repetitions == 0:
        mastery = "new"
    elif repetitions == 1:
        mastery = "recognition"
    elif not spoken_dates or not written_dates:
        mastery = "recall"
    elif repetitions >= 4 and len(spoken_dates) >= 2 and len(written_dates) >= 2 and len(all_review_dates) >= 4:
        mastery = "stable"
    else:
        mastery = "active"
    item["mastery"] = mastery


def sm2_update(srs: dict[str, Any], quality: int, review_date: date) -> dict[str, Any]:
    repetitions = int(srs.get("repetitions", 0))
    interval = int(srs.get("interval_days", 0))
    ease = float(srs.get("ease_factor", 2.5))

    if quality < 3:
        repetitions = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = max(1, round(interval * ease))
        repetitions += 1

    ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    return {
        "repetitions": repetitions,
        "interval_days": interval,
        "ease_factor": round(ease, 3),
        "last_review": review_date.isoformat(),
        "next_review": (review_date + timedelta(days=interval)).isoformat(),
        "last_quality": quality,
    }


def cmd_init(_: argparse.Namespace) -> int:
    ensure_layout()
    print(json.dumps({"status": "ok", "data_root": str(DATA_ROOT)}, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    errors: list[str] = []
    for rel in REQUIRED_PROJECT_FILES:
        if not (PROJECT_ROOT / rel).exists():
            errors.append(f"Missing project file: {rel}")
    policies = load_policies()
    errors.extend(check_prose_drift(policies))
    try:
        ensure_layout()
        vocab = load_json(VOCAB_FILE, {})
        errs = load_json(ERROR_FILE, {})
        state = load_json(STATE_FILE, {})
        if not isinstance(vocab.get("items"), list):
            errors.append("vocabulary.json: items must be a list")
        if not isinstance(errs.get("items"), list):
            errors.append("errors.json: items must be a list")
        if not isinstance(state, dict):
            errors.append("current_state.json must be an object")
        for log in [SESSIONS_FILE, ASSESSMENTS_FILE, VOCAB_REVIEWS_FILE, EVENTS_FILE]:
            read_jsonl(log)
        patches, retracted, problems = load_corrections()
        errors.extend(problems)
        known = {rec.get("id") for path in LOG_FILES.values() for rec in read_jsonl(path)}
        for target in sorted(set(patches) | retracted):
            if target not in known:
                errors.append(f"supersedes ссылается на неизвестный id: {target}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    warnings: list[str] = []
    try:
        warnings.extend(check_transliteration("first_seen", ERROR_FILE))
        warnings.extend(check_transliteration("created", VOCAB_FILE))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    status = "ok" if not errors else "error"
    print(json.dumps({"status": status, "errors": errors, "warnings": warnings,
                      "data_root": str(DATA_ROOT), "effective_policies": policies},
                     ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def cmd_add_vocab(args: argparse.Namespace) -> int:
    ensure_layout()
    db = load_json(VOCAB_FILE, {"schema_version": 2, "items": []})
    items = db["items"]
    normalized = args.chunk.strip().casefold()
    for item in items:
        if str(item.get("chunk", "")).strip().casefold() == normalized:
            print(json.dumps({"status": "exists", "item": item}, ensure_ascii=False, indent=2))
            return 0
    item_id = next_id(items, "V")
    created = args.date or today_iso()
    item = {
        "id": item_id,
        "chunk": args.chunk.strip(),
        "meaning_ru": args.meaning.strip(),
        "topic": args.topic,
        "register": args.register,
        "pattern": args.pattern or "",
        "stress": args.stress or "",
        "example": args.example or "",
        "source": args.source,
        "source_ref": args.source_ref or "",
        "created": created,
        "mastery": "new",
        "successful_uses": empty_uses(),
        "successful_review_dates": [],
        "srs": {
            "repetitions": 0,
            "interval_days": 0,
            "ease_factor": 2.5,
            "last_review": None,
            "next_review": created,
            "last_quality": None,
        },
        "notes": args.notes or "",
    }
    items.append(item)
    atomic_write_json(VOCAB_FILE, db)
    append_jsonl(EVENTS_FILE, {"event": "vocab_added", "timestamp": now_iso(), "item_id": item_id, "source": args.source})
    print(json.dumps({"status": "ok", "item": item}, ensure_ascii=False, indent=2))
    return 0


def cmd_due_vocab(args: argparse.Namespace) -> int:
    ensure_layout()
    target_date = parse_date(args.date or today_iso())
    items = load_json(VOCAB_FILE, {"items": []})["items"]
    due = []
    for item in items:
        raw = item.get("srs", {}).get("next_review")
        if not raw or parse_date(raw) <= target_date:
            overdue = (target_date - parse_date(raw)).days if raw else 0
            due.append((item, overdue))
    due.sort(key=lambda pair: (pair[0].get("srs", {}).get("next_review") or "", pair[0].get("id", "")))
    total = len(due)
    if args.limit:
        due = due[: args.limit]
    payload = []
    for item, overdue in due:
        record = dict(item) if args.full else lean_view(item, LEAN_VOCAB_FIELDS)
        record["days_overdue"] = overdue
        payload.append(record)
    print(json.dumps({"date": target_date.isoformat(), "total": total, "returned": len(payload),
                      "items": payload}, ensure_ascii=False, indent=2))
    return 0


def cmd_due_errors(args: argparse.Namespace) -> int:
    """Просроченные ошибки — то, что журнал ошибок раньше не умел показывать."""
    ensure_layout()
    target_date = parse_date(args.date or today_iso())
    items = load_json(ERROR_FILE, {"items": []}).get("items", [])
    due = []
    for item in items:
        if item.get("status") == "stable":
            continue
        if args.severity and item.get("severity") not in args.severity:
            continue
        raw = item.get("next_review")
        review_date = parse_date(raw) if raw else target_date
        if review_date > target_date:
            continue
        due.append((item, (target_date - review_date).days))
    due.sort(key=lambda pair: (
        -SEVERITY_ORDER.get(pair[0].get("severity", "low"), 0),
        -pair[1],
        pair[0].get("id", ""),
    ))
    total = len(due)
    if args.limit:
        due = due[: args.limit]
    payload = []
    for item, overdue in due:
        record = dict(item) if args.full else lean_view(item, LEAN_ERROR_FIELDS)
        record["days_overdue"] = overdue
        payload.append(record)
    print(json.dumps({"date": target_date.isoformat(), "total": total, "returned": len(payload),
                      "items": payload}, ensure_ascii=False, indent=2))
    return 0


def cmd_show_error(args: argparse.Namespace) -> int:
    """Полная карточка по id — для тех одной-двух ошибок, которые чинятся сейчас."""
    ensure_layout()
    index = {x.get("id"): x for x in load_json(ERROR_FILE, {"items": []}).get("items", [])}
    found = [index[eid] for eid in args.id if eid in index]
    unknown = [eid for eid in args.id if eid not in index]
    print(json.dumps({"count": len(found), "items": found, "unknown": unknown}, ensure_ascii=False, indent=2))
    return 0 if not unknown else 1


def cmd_recent(args: argparse.Namespace) -> int:
    """Хвост журнала. Раздел 2 SKILL.md говорил «последние записи» без числа —
    без предела это означало чтение файла целиком."""
    ensure_layout()
    if args.raw:
        records, stats = read_jsonl(LOG_FILES[args.log]), {"corrected": 0, "retracted": 0}
    else:
        records, stats = read_log(LOG_FILES[args.log])
    tail = records[-args.limit:] if args.limit else records
    print(json.dumps({"log": args.log, "total": len(records), "returned": len(tail),
                      "corrections_applied": stats, "items": tail},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_review_vocab(args: argparse.Namespace) -> int:
    ensure_layout()
    review_date = parse_date(args.date or today_iso())
    db = load_json(VOCAB_FILE, {"schema_version": 2, "items": []})
    item = next((x for x in db["items"] if x.get("id") == args.id), None)
    if item is None:
        print(json.dumps({"status": "error", "message": f"Unknown vocab id {args.id}"}, ensure_ascii=False))
        return 1
    modes = args.mode
    qualities = args.quality * len(modes) if len(args.quality) == 1 else args.quality
    if len(qualities) != len(modes):
        print(json.dumps({"status": "error", "message":
                          f"--quality: ожидается 1 значение или {len(modes)} по числу режимов"},
                         ensure_ascii=False))
        return 1

    # Одна проверка одной единицы — один прогон SM-2, сколько бы режимов ни проверяли.
    # Интервал ведём по худшему из режимов: не вспомнил значение — единица не выучена,
    # даже если под подсказку написал её правильно.
    effective = min(qualities)
    item["srs"] = sm2_update(item.get("srs", {}), effective, review_date)

    uses = item.setdefault("successful_uses", empty_uses())
    for mode, quality in zip(modes, qualities):
        if quality >= 3:  # успех в режиме фиксируется по его собственной оценке
            dates = uses.setdefault(mode, [])
            if review_date.isoformat() not in dates:
                dates.append(review_date.isoformat())
    if effective >= 3:
        review_dates = item.setdefault("successful_review_dates", [])
        if review_date.isoformat() not in review_dates:
            review_dates.append(review_date.isoformat())
    update_mastery(item)
    atomic_write_json(VOCAB_FILE, db)
    record = {
        "id": f"VR-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": now_iso(),
        "date": review_date.isoformat(),
        "vocab_id": args.id,
        "quality": effective,
        "modes": modes,
        "qualities": qualities,
        "evidence": args.evidence or "",
        "next_review": item["srs"]["next_review"],
        "mastery": item["mastery"],
    }
    append_jsonl(VOCAB_REVIEWS_FILE, record)
    print(json.dumps({"status": "ok", "item": item, "review": record}, ensure_ascii=False, indent=2))
    return 0


def cmd_add_error(args: argparse.Namespace) -> int:
    ensure_layout()
    db = load_json(ERROR_FILE, {"schema_version": 2, "items": []})
    signature = "|".join([args.skill.casefold(), args.category.casefold(), args.correction.strip().casefold()])
    existing = next((x for x in db["items"] if x.get("signature") == signature and x.get("status") != "stable"), None)
    if existing:
        existing["recurrence_count"] = int(existing.get("recurrence_count", 1)) + 1
        existing["last_seen"] = args.date or today_iso()
        existing.setdefault("examples", []).append({"date": args.date or today_iso(), "original": args.original, "task": args.task or ""})
        atomic_write_json(ERROR_FILE, db)
        print(json.dumps({"status": "updated", "item": existing}, ensure_ascii=False, indent=2))
        return 0
    error_id = next_id(db["items"], "E")
    item = {
        "id": error_id,
        "signature": signature,
        "skill": args.skill,
        "category": args.category,
        "severity": args.severity,
        "original": args.original,
        "correction": args.correction,
        "explanation": args.explanation or "",
        "task": args.task or "",
        "first_seen": args.date or today_iso(),
        "last_seen": args.date or today_iso(),
        "recurrence_count": 1,
        "status": "new",
        "successful_evidence": [],
        "next_review": args.next_review or (date.fromisoformat(args.date or today_iso()) + timedelta(days=1)).isoformat(),
        "source": args.source,
    }
    db["items"].append(item)
    atomic_write_json(ERROR_FILE, db)
    append_jsonl(EVENTS_FILE, {"event": "error_added", "timestamp": now_iso(), "error_id": error_id, "category": args.category})
    print(json.dumps({"status": "ok", "item": item}, ensure_ascii=False, indent=2))
    return 0


def evidence_since_last_recurrence(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Успехи, полученные строго позже последнего возврата ошибки.

    Прецедент E0019: успех 03.08, затем семь возвратов до 19.08 — и двух новых
    успехов хватало на stable, после чего due-errors переставал показывать
    ошибку вовсе. Успех, отменённый последующим возвратом, устойчивости не
    доказывает. Тот же день, что и возврат, тоже не считается: 19.08 связка
    выдана 4/4 сразу после объяснения, независимым применением это не является.
    """
    evidence = item.get("successful_evidence") or []
    last_seen = item.get("last_seen")
    if not last_seen:
        return list(evidence)
    return [x for x in evidence if x.get("date") and x["date"] > last_seen]


def apply_error_progress(item: dict[str, Any], practice_date: str) -> None:
    """Статус и следующая проверка по действующим порогам устойчивости."""
    thresholds = load_policies()["errors"]
    evidence = evidence_since_last_recurrence(item)
    dates = {x.get("date") for x in evidence if x.get("date")}
    contexts = {x.get("context") for x in evidence if x.get("context")}
    if (len(evidence) >= int(thresholds["stable_successes"])
            and len(dates) >= int(thresholds["stable_unique_dates"])
            and len(contexts) >= int(thresholds["stable_unique_contexts"])):
        item["status"] = "stable"
        item["next_review"] = (parse_date(practice_date) + timedelta(days=30)).isoformat()
    elif len(dates) >= 2:
        item["status"] = "improving"
        item["next_review"] = (parse_date(practice_date) + timedelta(days=7)).isoformat()
    else:
        # relapsed не понижается до practising: возврат уже закрытой ошибки —
        # отдельный факт истории, и затирать его пересчётом нельзя.
        item["status"] = "relapsed" if item.get("status") == "relapsed" else "practising"
        item["next_review"] = (parse_date(practice_date) + timedelta(days=3)).isoformat()


def cmd_practice_error(args: argparse.Namespace) -> int:
    ensure_layout()
    practice_date = args.date or today_iso()
    db = load_json(ERROR_FILE, {"schema_version": 2, "items": []})
    item = next((x for x in db["items"] if x.get("id") == args.id), None)
    if item is None:
        print(json.dumps({"status": "error", "message": f"Unknown error id {args.id}"}, ensure_ascii=False))
        return 1
    if args.success:
        evidence = {"date": practice_date, "context": args.context or "", "note": args.evidence or ""}
        item.setdefault("successful_evidence", []).append(evidence)
        apply_error_progress(item, practice_date)
    else:
        item["recurrence_count"] = int(item.get("recurrence_count", 1)) + 1
        item["last_seen"] = practice_date
        item["status"] = "relapsed" if item.get("status") == "stable" else "practising"
        item["next_review"] = (parse_date(practice_date) + timedelta(days=1)).isoformat()
    atomic_write_json(ERROR_FILE, db)
    append_jsonl(EVENTS_FILE, {
        "event": "error_practice",
        "timestamp": now_iso(),
        "error_id": args.id,
        "success": bool(args.success),
        "context": args.context or "",
    })
    print(json.dumps({"status": "ok", "item": item}, ensure_ascii=False, indent=2))
    return 0


def cmd_recompute_errors(args: argparse.Namespace) -> int:
    """Пересчёт статусов по действующему правилу устойчивости.

    Реестр хранит статус, а не выводит его на лету, поэтому записи, повышенные
    прежней логикой, сами не откатятся после её исправления.
    """
    ensure_layout()
    db = load_json(ERROR_FILE, {"schema_version": 2, "items": []})
    changed = []
    for item in db["items"]:
        if not item.get("successful_evidence"):
            continue
        before = (item.get("status"), item.get("next_review"))
        evidence = evidence_since_last_recurrence(item)
        base = max((x["date"] for x in evidence if x.get("date")),
                   default=item.get("last_seen") or today_iso())
        apply_error_progress(item, base)
        # Пересчёт вправе только приблизить проверку. Отодвинуть её он не может:
        # дату могло поставить срабатывание ошибки, о котором evidence не знает.
        if before[1] and item.get("next_review", "") > before[1]:
            item["next_review"] = before[1]
        after = (item.get("status"), item.get("next_review"))
        if before != after:
            changed.append({"id": item.get("id"),
                            "from": {"status": before[0], "next_review": before[1]},
                            "to": {"status": after[0], "next_review": after[1]}})
    if changed and not args.dry_run:
        atomic_write_json(ERROR_FILE, db)
    print(json.dumps({"status": "ok", "dry_run": bool(args.dry_run), "changed": changed},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_log_session(args: argparse.Namespace) -> int:
    ensure_layout()
    record = {
        "id": f"S-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": now_iso(),
        "date": args.date or today_iso(),
        "lesson_type": args.lesson_type,
        "planned_minutes": args.planned,
        "completed_minutes": args.completed,
        "status": args.status,
        "carryover": args.carryover or "",
        "notes": args.notes or "",
    }
    append_jsonl(SESSIONS_FILE, record)
    state = load_json(STATE_FILE, {})
    state["last_session_date"] = record["date"]
    atomic_write_json(STATE_FILE, state)
    print(json.dumps({"status": "ok", "record": record}, ensure_ascii=False, indent=2))
    return 0


def cmd_log_assessment(args: argparse.Namespace) -> int:
    ensure_layout()
    record = {
        "id": f"A-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": now_iso(),
        "date": args.date or today_iso(),
        "skill": args.skill,
        "task": args.task,
        "score": args.score,
        "max_score": args.max_score,
        "band_low": args.band_low,
        "band_high": args.band_high,
        "confidence": args.confidence,
        "minutes": args.minutes,
        "timed": not args.untimed,
        "source": args.source,
        "comparable_group": args.comparable_group or "",
        "notes": args.notes or "",
    }
    if args.max_score and args.score is not None:
        record["accuracy"] = round(args.score / args.max_score, 4)
    append_jsonl(ASSESSMENTS_FILE, record)
    print(json.dumps({"status": "ok", "record": record}, ensure_ascii=False, indent=2))
    return 0


def in_range(raw: str, start: date, end: date) -> bool:
    try:
        d = parse_date(raw)
    except (TypeError, ValueError):
        return False
    return start <= d <= end


def build_weekly_report(start: date, end: date) -> str:
    patches, retracted, _ = load_corrections()
    applied = {"corrected": 0, "retracted": 0}
    logs = {}
    for key, path in [("sessions", SESSIONS_FILE), ("assessments", ASSESSMENTS_FILE),
                      ("reviews", VOCAB_REVIEWS_FILE)]:
        records, stats = read_log(path, patches, retracted)
        logs[key] = records
        for field in applied:
            applied[field] += stats[field]
    sessions = [x for x in logs["sessions"] if in_range(x.get("date", ""), start, end)]
    assessments = [x for x in logs["assessments"] if in_range(x.get("date", ""), start, end)]
    reviews = [x for x in logs["reviews"] if in_range(x.get("date", ""), start, end)]
    errors = load_json(ERROR_FILE, {"items": []}).get("items", [])

    planned = sum(int(x.get("planned_minutes") or 0) for x in sessions)
    completed = sum(int(x.get("completed_minutes") or 0) for x in sessions)
    completed_sessions = sum(1 for x in sessions if x.get("status") == "completed")
    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assessment in assessments:
        by_skill[str(assessment.get("skill", "unknown"))].append(assessment)
    quality_counts = Counter(int(x.get("quality", -1)) for x in reviews)
    successful_reviews = sum(v for q, v in quality_counts.items() if q >= 3)
    retention = successful_reviews / len(reviews) if reviews else None

    active_errors = [x for x in errors if x.get("status") != "stable"]
    active_errors.sort(key=lambda x: (SEVERITY_ORDER.get(x.get("severity", "low"), 0), int(x.get("recurrence_count", 0))), reverse=True)

    lines = [
        f"# Weekly Report: {start.isoformat()} — {end.isoformat()}",
        "",
        "## Attendance",
        f"- Planned minutes: {planned}",
        f"- Completed minutes: {completed}",
        f"- Completion: {(completed / planned * 100):.1f}%" if planned else "- Completion: insufficient data",
        f"- Completed sessions: {completed_sessions}/{len(sessions)}",
        "",
        "## Assessments",
    ]
    if not assessments:
        lines.append("- No assessments logged.")
    else:
        for skill, records in sorted(by_skill.items()):
            latest = records[-1]
            score_text = ""
            if latest.get("score") is not None and latest.get("max_score"):
                score_text = f"{latest['score']}/{latest['max_score']}"
            elif latest.get("band_low") is not None:
                score_text = f"{latest.get('band_low')}–{latest.get('band_high')}"
            lines.append(f"- {skill}: {score_text or 'recorded'}; source={latest.get('source')}; confidence={latest.get('confidence')}")
    lines += ["", "## Vocabulary"]
    if retention is None:
        lines.append("- No vocabulary reviews logged.")
    else:
        lines.append(f"- Delayed review success: {successful_reviews}/{len(reviews)} ({retention*100:.1f}%)")
    lines += ["", "## Priority errors"]
    if not active_errors:
        lines.append("- No active errors.")
    else:
        for item in active_errors[:5]:
            lines.append(f"- {item.get('id')} · {item.get('category')} · {item.get('severity')} · recurrence {item.get('recurrence_count')} · {item.get('status')}")
    lines += ["", "## Data corrections"]
    if not applied["corrected"] and not applied["retracted"]:
        lines.append("- None applied.")
    else:
        lines.append(f"- Field-corrected records: {applied['corrected']}")
        lines.append(f"- Retracted records: {applied['retracted']}")
        lines.append("- Source: `supersedes` entries in data/logs/decisions.jsonl. Raw lines were not rewritten.")
    lines += ["", "## Coach decision", "- Add evidence-based next-week decision here after reviewing goals and conditions.", ""]
    return "\n".join(lines)


def cmd_weekly_report(args: argparse.Namespace) -> int:
    ensure_layout()
    start = parse_date(args.start)
    end = parse_date(args.end)
    if end < start:
        print(json.dumps({"status": "error", "message": "end must be on or after start"}, ensure_ascii=False))
        return 1
    report = build_weekly_report(start, end)
    output = REPORT_DIR / f"weekly-{start.isoformat()}_{end.isoformat()}.md"
    output.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved: {output}")
    return 0


def spark_bars(values: list[float], labels: list[str], title: str) -> str:
    if not values:
        return f"<section><h2>{html.escape(title)}</h2><p>No data.</p></section>"
    max_value = max(values) or 1.0
    rows = []
    for label, value in zip(labels, values):
        width = max(2, value / max_value * 100)
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{html.escape(label)}</span>'
            f'<div class="bar"><div class="fill" style="width:{width:.1f}%"></div></div>'
            f'<span class="bar-value">{value:g}</span></div>'
        )
    return f"<section><h2>{html.escape(title)}</h2>{''.join(rows)}</section>"


def generate_dashboard_html() -> str:
    patches, retracted, _ = load_corrections()
    sessions, _ = read_log(SESSIONS_FILE, patches, retracted)
    assessments, _ = read_log(ASSESSMENTS_FILE, patches, retracted)
    vocab = load_json(VOCAB_FILE, {"items": []}).get("items", [])
    errors = load_json(ERROR_FILE, {"items": []}).get("items", [])
    total_minutes = sum(int(x.get("completed_minutes") or 0) for x in sessions)
    due = 0
    today = date.today()
    for item in vocab:
        raw = item.get("srs", {}).get("next_review")
        if not raw or parse_date(raw) <= today:
            due += 1
    active_vocab = sum(1 for x in vocab if x.get("mastery") in {"active", "stable"})
    active_errors = [x for x in errors if x.get("status") != "stable"]
    assessment_values, assessment_labels = [], []
    for record in assessments[-12:]:
        if record.get("score") is not None and record.get("max_score"):
            assessment_values.append(float(record["score"]) / float(record["max_score"]) * 100)
            assessment_labels.append(f"{record.get('date','')} {record.get('skill','')}")
        elif record.get("band_low") is not None and record.get("band_high") is not None:
            assessment_values.append((float(record["band_low"]) + float(record["band_high"])) / 2)
            assessment_labels.append(f"{record.get('date','')} {record.get('skill','')}")
    error_counts = Counter(x.get("category", "unknown") for x in active_errors)
    top_errors = error_counts.most_common(8)
    style = """
    body{font-family:Inter,Arial,sans-serif;margin:0;background:#f4f6f8;color:#17202a}main{max-width:1050px;margin:0 auto;padding:32px}
    h1{margin-bottom:6px}.muted{color:#64748b}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:24px 0}
    .card,section{background:white;border:1px solid #dfe5eb;border-radius:14px;padding:18px;box-shadow:0 2px 10px rgba(15,23,42,.04)}
    .number{font-size:30px;font-weight:700;margin-top:8px}.bar-row{display:grid;grid-template-columns:220px 1fr 70px;gap:10px;align-items:center;margin:10px 0}
    .bar{height:13px;background:#e8edf2;border-radius:999px;overflow:hidden}.fill{height:100%;background:#334155}.bar-label{font-size:13px}.bar-value{text-align:right;font-variant-numeric:tabular-nums}
    section{margin:16px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid #e7ebef;font-size:14px}
    """
    rows = "".join(
        f"<tr><td>{html.escape(str(x.get('id','')))}</td><td>{html.escape(str(x.get('category','')))}</td><td>{html.escape(str(x.get('severity','')))}</td><td>{html.escape(str(x.get('status','')))}</td><td>{int(x.get('recurrence_count',0))}</td></tr>"
        for x in sorted(active_errors, key=lambda y: int(y.get("recurrence_count", 0)), reverse=True)[:10]
    ) or '<tr><td colspan="5">No active errors.</td></tr>'
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IELTS Coach Dashboard</title><style>{style}</style></head>
    <body><main><h1>IELTS General Coach</h1><p class="muted">Updated {html.escape(now_iso())}</p>
    <div class="cards"><div class="card"><div class="muted">Completed study</div><div class="number">{total_minutes/60:.1f} h</div></div>
    <div class="card"><div class="muted">Vocabulary items</div><div class="number">{len(vocab)}</div></div>
    <div class="card"><div class="muted">Active/stable chunks</div><div class="number">{active_vocab}</div></div>
    <div class="card"><div class="muted">Due reviews</div><div class="number">{due}</div></div>
    <div class="card"><div class="muted">Active errors</div><div class="number">{len(active_errors)}</div></div></div>
    {spark_bars(assessment_values, assessment_labels, 'Recent assessments (percent or band midpoint)')}
    {spark_bars([float(v) for _, v in top_errors], [k for k, _ in top_errors], 'Recurring error categories')}
    <section><h2>Priority errors</h2><table><thead><tr><th>ID</th><th>Category</th><th>Severity</th><th>Status</th><th>Recurrence</th></tr></thead><tbody>{rows}</tbody></table></section>
    </main></body></html>"""


def cmd_prune_backups(args: argparse.Namespace) -> int:
    """Чистка снимков реестров. Ротации по расписанию здесь нет намеренно:
    ранние снимки хранят историю глубже базовой линии git, и удалять их молча нельзя."""
    ensure_layout()
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in BACKUP_DIR.glob("*.bak"):
        groups[path.name.split(".json")[0]].append(path)

    kept, doomed = [], []
    for name, paths in sorted(groups.items()):
        paths.sort(key=lambda p: p.stat().st_mtime)
        cut = len(paths) - args.keep
        doomed.extend(paths[:cut] if cut > 0 else [])
        kept.extend(paths[cut:] if cut > 0 else paths)

    freed = sum(p.stat().st_size for p in doomed)
    if not args.dry_run:
        for path in doomed:
            path.unlink()
    print(json.dumps({
        "status": "ok",
        "dry_run": bool(args.dry_run),
        "keep_per_file": args.keep,
        "kept": len(kept),
        "removed" if not args.dry_run else "would_remove": len(doomed),
        "freed_bytes": freed,
        "oldest_kept": min((p.name for p in kept), default=None),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_dashboard(_: argparse.Namespace) -> int:
    ensure_layout()
    DASHBOARD_FILE.write_text(generate_dashboard_html(), encoding="utf-8")
    print(json.dumps({"status": "ok", "dashboard": str(DASHBOARD_FILE)}, ensure_ascii=False, indent=2))
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("validate")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("add-vocab")
    p.add_argument("--chunk", required=True)
    p.add_argument("--meaning", required=True)
    p.add_argument("--topic", default="general")
    p.add_argument("--register", choices=["informal", "neutral", "formal", "mixed"], default="neutral")
    p.add_argument("--pattern")
    p.add_argument("--stress")
    p.add_argument("--example")
    p.add_argument("--source", choices=["source_of_truth", "external_teacher_review", "confirmed_user_record", "case_material", "model_inference", "open_verification"], default="model_inference")
    p.add_argument("--source-ref")
    p.add_argument("--notes")
    p.add_argument("--date")
    p.set_defaults(func=cmd_add_vocab)

    p = sub.add_parser("due-vocab")
    p.add_argument("--date")
    p.add_argument("--limit", type=int)
    p.add_argument("--full", action="store_true", help="полные карточки вместо урезанных под урок")
    p.set_defaults(func=cmd_due_vocab)

    p = sub.add_parser("due-errors")
    p.add_argument("--date")
    p.add_argument("--limit", type=int)
    p.add_argument("--severity", nargs="+", choices=["critical", "high", "medium", "low"])
    p.add_argument("--full", action="store_true", help="полные карточки вместо урезанных под урок")
    p.set_defaults(func=cmd_due_errors)

    p = sub.add_parser("show-error")
    p.add_argument("--id", nargs="+", required=True)
    p.set_defaults(func=cmd_show_error)

    p = sub.add_parser("recent")
    p.add_argument("--log", choices=sorted(LOG_FILES), required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--raw", action="store_true", help="без применения исправлений — как записано на диске")
    p.set_defaults(func=cmd_recent)

    p = sub.add_parser("review-vocab")
    p.add_argument("--id", required=True)
    p.add_argument("--quality", type=int, choices=range(0, 6), nargs="+", required=True,
                   help="одна оценка на все режимы либо по одной на каждый, в том же порядке")
    p.add_argument("--mode", choices=["meaning", "form", "register", "spoken", "written"],
                   nargs="+", required=True,
                   help="все режимы, проверенные за один подход — одним вызовом, не несколькими")
    p.add_argument("--evidence")
    p.add_argument("--date")
    p.set_defaults(func=cmd_review_vocab)

    p = sub.add_parser("add-error")
    p.add_argument("--skill", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--original", required=True)
    p.add_argument("--correction", required=True)
    p.add_argument("--explanation")
    p.add_argument("--severity", choices=["critical", "high", "medium", "low"], default="medium")
    p.add_argument("--task")
    p.add_argument("--next-review")
    p.add_argument("--source", choices=["source_of_truth", "external_teacher_review", "confirmed_user_record", "case_material", "model_inference", "open_verification"], default="model_inference")
    p.add_argument("--date")
    p.set_defaults(func=cmd_add_error)

    p = sub.add_parser("practice-error")
    p.add_argument("--id", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--success", action="store_true")
    group.add_argument("--failure", action="store_true")
    p.add_argument("--context")
    p.add_argument("--evidence")
    p.add_argument("--date")
    p.set_defaults(func=cmd_practice_error)

    p = sub.add_parser("recompute-errors",
                       help="пересчитать статусы по действующему правилу устойчивости")
    p.add_argument("--dry-run", action="store_true", help="показать расхождения, ничего не записывая")
    p.set_defaults(func=cmd_recompute_errors)

    p = sub.add_parser("log-session")
    p.add_argument("--lesson-type", required=True)
    p.add_argument("--planned", type=int, required=True)
    p.add_argument("--completed", type=int, required=True)
    p.add_argument("--status", choices=["completed", "partial", "missed"], required=True)
    p.add_argument("--carryover")
    p.add_argument("--notes")
    p.add_argument("--date")
    p.set_defaults(func=cmd_log_session)

    p = sub.add_parser("log-assessment")
    p.add_argument("--skill", choices=["listening", "reading", "writing_task1", "writing_task2", "speaking", "vocabulary", "grammar", "typing"], required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--score", type=float)
    p.add_argument("--max-score", type=float)
    p.add_argument("--band-low", type=float)
    p.add_argument("--band-high", type=float)
    p.add_argument("--confidence", choices=["low", "medium", "high", "not_applicable"], default="not_applicable")
    p.add_argument("--minutes", type=float)
    p.add_argument("--untimed", action="store_true")
    p.add_argument("--source", choices=["source_of_truth", "external_teacher_review", "confirmed_user_record", "case_material", "model_inference", "open_verification"], required=True)
    p.add_argument("--comparable-group")
    p.add_argument("--notes")
    p.add_argument("--date")
    p.set_defaults(func=cmd_log_assessment)

    p = sub.add_parser("weekly-report")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.set_defaults(func=cmd_weekly_report)

    p = sub.add_parser("prune-backups")
    p.add_argument("--keep", type=int, default=10, help="сколько последних снимков оставить на файл")
    p.add_argument("--dry-run", action="store_true", help="только показать, что будет удалено")
    p.set_defaults(func=cmd_prune_backups)

    p = sub.add_parser("dashboard")
    p.set_defaults(func=cmd_dashboard)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if getattr(args, "failure", False):
        args.success = False
    try:
        return int(args.func(args))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
