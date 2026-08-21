---
name: ielts-weekly-review
version: 2.0.0
description: Субботний контроль и недельный анализ по измеримым целям, типичным ошибкам и carryover.
---

# Weekly Control and Review

## Control 90–120 minutes

- vocabulary retrieval;
- repeated-error test в новых контекстах;
- timed receptive task;
- Writing или Speaking productive task;
- короткая reflection после сдачи.

Подсказки запрещены до фиксации ответа.

Протокол и бланк контроля — `templates/weekly_control.md`: там же фиксируются условия,
отключённые инструменты и запрет конвертировать частичный блок в точный band.

## Review

- выполнено ли каждое goal;
- плановые и фактические минуты;
- due/retained vocabulary;
- new, repeated, stable и relapsed errors;
- receptive raw scores и timing;
- Writing/Speaking criterion ranges;
- что стало лучше, не изменилось или ухудшилось;
- достаточно ли данных для вывода;
- carryover и приоритет следующей недели.

Используй `templates/weekly_review.md`. После разбора пересобери отчёт и дашборд —
сами они не обновляются:

```bash
python scripts/coach_cli.py weekly-report --start ГГГГ-ММ-ДД --end ГГГГ-ММ-ДД
python scripts/coach_cli.py dashboard
```
