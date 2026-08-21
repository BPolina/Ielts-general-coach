# CLI Commands

## Выборка под урок

Реестры растут всю подготовку, поэтому на уроке они читаются выборкой, а не файлом.
`due-*` по умолчанию отдают урезанные карточки; `--full` возвращает полные.

```bash
python scripts/coach_cli.py due-errors --limit 10
python scripts/coach_cli.py due-errors --severity critical high
python scripts/coach_cli.py show-error --id E0011 E0018
python scripts/coach_cli.py due-vocab --limit 15
python scripts/coach_cli.py recent --log sessions --limit 5
python scripts/coach_cli.py recent --log assessments --limit 5
```

## Остальное

```bash
python scripts/coach_cli.py init
python scripts/coach_cli.py validate
python scripts/coach_cli.py add-vocab --chunk "meet a deadline" --meaning "уложиться в срок" --topic work --register neutral --source model_inference
python scripts/coach_cli.py review-vocab --id V0001 --mode spoken --quality 4 --evidence "Used in Speaking Part 1"
python scripts/coach_cli.py review-vocab --id V0001 --mode meaning written --quality 0 5
python scripts/coach_cli.py review-vocab --id V0001 --mode spoken written --quality 4
python scripts/coach_cli.py add-error --skill writing --category lexis.collocation --original "do a decision" --correction "make a decision" --severity high
python scripts/coach_cli.py practice-error --id E0001 --success --context "Task 2 paragraph"
python scripts/coach_cli.py log-session --lesson-type writing_task2 --planned 120 --completed 115 --status completed
python scripts/coach_cli.py log-assessment --skill listening --task "Official sample" --score 34 --max-score 40 --minutes 30 --source source_of_truth
python scripts/coach_cli.py weekly-report --start 2026-07-20 --end 2026-07-26
python scripts/coach_cli.py dashboard
```
