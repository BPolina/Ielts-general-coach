# Data Schema

## vocabulary.json

Each item contains:

- `id`, `chunk`, `meaning_ru`, `topic`, `register`;
- `pattern`, `stress`, `example`;
- `source`, `source_ref`;
- `mastery`;
- `successful_uses.meaning/form/spoken/written` as unique dates;
- `srs.repetitions`, `interval_days`, `ease_factor`, `last_review`, `next_review`, `last_quality`.

## errors.json

Each item contains:

- stable `signature` for deduplication;
- skill, category, severity;
- original, correction, explanation;
- recurrence count and status;
- successful evidence with date and context;
- next review and source.

## vocabulary_reviews.jsonl

Одна запись — один подход к одной единице, сколько бы режимов ни проверяли:

- `modes` и `qualities` — проверенные режимы и оценка каждого, в одном порядке;
- `quality` — действующая оценка, по которой посчитан интервал: минимум из `qualities`;
- `next_review`, `mastery` — состояние после подхода.

Записи до 2026-08-06 содержат `mode` и `quality` в единственном числе — по одному
режиму на запись. Это тот же формат с одним элементом, читать их можно по `quality`.

## JSONL logs

Every line is one immutable event object. Required common fields:

- `id`;
- `timestamp`;
- `date` where relevant;
- event-specific evidence;
- `source` for numerical or evaluative conclusions.

## Пороги

Числовые пороги заданы в `config/policies.json` и оттуда читаются кодом:

- `errors.*` — сколько успешных применений, в скольких датах и контекстах закрывают
  ошибку. Исполняется `practice-error`.
- `vocabulary.*`, `estimation.*` — канонические значения для тренера. В прозе они
  записаны словами там, где применяются; `validate` сверяет прозу с конфигом и
  сообщает, если они разошлись.

Меняя порог в конфиге, поправь и прозу — `validate` покажет, где именно.

## Corrections

Строки логов не переписываются. Исправление — новая запись в `data/logs/decisions.jsonl`, которая
называет отменяемые id и говорит, что с ними делать:

| Поле | Смысл |
|---|---|
| `supersedes` | список id исправляемых записей |
| `corrections` | `{поле: значение}` — правка полей; запись остаётся в аналитике |
| `retract` | `true` — запись выпадает из аналитики целиком |
| `restates` | id прозаического исправления, которое эта запись переизлагает машиночитаемо |

`supersedes` без `corrections` и без `retract` на данные **не влияет** и попадает в
ошибки `validate`. Умолчание безопасное: молча выбросить доказательство хуже, чем
не применить исправление.

Отмена решения решением — частный случай: она меняет актуальность вывода, а не данные,
и помечает старое решение полем `superseded_by`.

Правки применяются в порядке `timestamp` и собираются со всех записей, включая те, что
сами кем-то отменены: правка — это факт о данных, а не суждение.

`recent --raw` показывает журнал без применения исправлений — как он лежит на диске.

## Migration rule

Never silently change schema semantics. Increase `schema_version`, preserve the old file in `.backups`, and write a decision record.
