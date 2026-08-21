---
name: ielts-general-vocabulary
version: 2.0.0
description: Контекстный словарь chunks с active recall, SM-2-подобными интервалами и переносом в Writing/Speaking.
---

# Vocabulary System

## Единица

Предпочтительные типы:

- collocation;
- phrasal verb;
- sentence frame;
- register-specific phrase;
- paraphrase pair;
- word family.

Для каждой единицы нужны значение, контекст, register, pattern, stress, пример, источник и типичные ошибки.

## Отбор

Добавляй только полезные выражения из:

- текущих ошибок;
- официального/учебного input;
- тем work, migration, business correspondence;
- повторяющихся IELTS functions: contrast, cause, result, request, complaint, recommendation.

Не добавляй выражение только потому, что оно «сложное».

## Повторение

Сначала due items. Проверять по очереди:

1. meaning recall;
2. form/collocation completion;
3. register choice;
4. spoken production;
5. written production.

Оценить каждый режим по quality 0–5 и записать **одним вызовом**, а не несколькими:

```bash
python scripts/coach_cli.py review-vocab --id V0001 --mode meaning written --quality 0 5
```

Интервал считается один раз, по худшему из режимов: не вспомнила значение — единица не
выучена, даже если под подсказку написала её верно. Успех в каждом режиме при этом
сохраняется отдельно. Несколько вызовов подряд по одной единице двигают интервал
дважды и завышают его — так делать нельзя.

Режимы `--mode` совпадают с пятью проверками выше: `meaning`, `form`, `register`,
`spoken`, `written`.

## Mastery

- `new` — встречено;
- `recognition` — узнаётся;
- `recall` — воспроизводится;
- `active` — есть корректное spoken и written use в разные даты;
- `stable` — несколько успешных delayed reviews и повторный transfer.

Если recall < 70%, уменьшить новый объём. Если due items > 25, новый материал временно приостановить.
