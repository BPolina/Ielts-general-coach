# IELTS General Coach

[Русский](#русский) · [English](#english)

<a id="русский"></a>

## Русский

### О проекте

IELTS General Coach — локальный модульный AI-тренер для подготовки к компьютерному IELTS General Training. Проект объединяет учебные сценарии, интервальное повторение, журнал повторяющихся ошибок, оценивание Writing и Speaking и локальную аналитику прогресса.

Обычный чат легко теряет учебный контекст: одни и те же ошибки разбираются заново, новая лексика не возвращается в нужный момент, а единичная удачная работа принимается за устойчивый результат. IELTS General Coach хранит доказательства прогресса локально и строит следующие занятия на фактических ошибках и просроченных повторениях.

Это личный учебный проект и одновременно переносимый шаблон. Профиль ученика, расписание и целевые баллы настраиваются в `config/student_profile.json`.

### Возможности

- 12 специализированных учебных модулей;
- отдельные сценарии для Listening, General Reading, Writing Task 1, Writing Task 2 и Speaking;
- SM-2-подобное интервальное повторение словаря;
- журнал ошибок с проверкой устойчивого исправления в разные даты и контексты;
- append-only журналы занятий и оценок;
- разделение официальных результатов, внешней проверки и AI-предположений;
- адаптивные недельные планы;
- локальный HTML-дашборд;
- CLI только на стандартной библиотеке Python;
- резервные копии и валидация структуры данных.

### Архитектура

```text
SKILL.md                 главный оркестратор
skills/                  специализированные учебные модули
references/              педагогика, scoring и правила работы с данными
templates/               шаблоны уроков, отчётов и обратной связи
scripts/coach_cli.py      локальное состояние, SRS и аналитика
config/                   профиль ученика и пороги политик
data/                     приватные runtime-данные, не публикуются
tests/                    тесты CLI и правил данных
```

Корневой `SKILL.md` определяет задачу и загружает только необходимый модуль. Учебные тексты и ответы ученика считаются данными, а не инструкциями. Подробное описание: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Быстрый запуск

Требуется Python 3.10 или новее. Внешние Python-пакеты не нужны.

```bash
python scripts/coach_cli.py init
python scripts/coach_cli.py validate
```

Затем подключите папку к AI-окружению, поддерживающему инструкции в Markdown, и используйте одну из команд:

```text
Начать диагностическую неделю
Составить план недели
Начать урок
Повторить словарь
Проверить General Writing Task 1
Проверить Writing Task 2
Разобрать Listening
Разобрать General Reading
Провести Speaking mock
Провести недельный контроль
Показать прогресс
```

Подробный старт: [`docs/QUICK_START.md`](docs/QUICK_START.md).

### Дашборд

```bash
python scripts/coach_cli.py dashboard
```

Результат создаётся локально в `data/dashboard.html`.

### Проверка

```bash
python -m unittest discover -s tests -v
```

### Конфиденциальность

Папка `data/` содержит словарь, ошибки, оценки, учебные работы и журналы занятий. Она исключена из публичного репозитория. Не добавляйте реальные работы ученика, аудиозаписи, локальные настройки AI-инструментов или резервные копии в Git.

Публичная версия содержит только обезличенный пример профиля. Для реального использования рекомендуется отдельная приватная рабочая копия.

### Ограничения

- AI-оценки Writing и Speaking являются ориентировочными и не заменяют официального экзаменатора.
- Произношение нельзя надёжно оценить только по текстовой расшифровке.
- Для устойчивого прогноза нужны серии сопоставимых работ, а не один высокий результат.
- Проект не связан с IELTS, British Council, IDP или Cambridge University Press & Assessment.

### Происхождение идей

Проект написан под персональный учебный процесс. Использованные открытые источники и архитектурные ориентиры перечислены в [`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md).

### Лицензия

Лицензия пока не выбрана. До добавления файла `LICENSE` действуют стандартные авторские права автора.

---

<a id="english"></a>

## English

### About the project

IELTS General Coach is a modular, local-first AI coach for computer-delivered IELTS General Training. It combines structured lesson workflows, spaced repetition, recurring-error tracking, Writing and Speaking assessment, and local progress analytics.

A conventional chat can easily lose learning context: the same mistakes are explained repeatedly, new vocabulary is not reviewed at the right time, and a single strong performance may be mistaken for stable progress. IELTS General Coach keeps evidence locally and builds future lessons around actual errors and overdue reviews.

This is both a personal learning project and a reusable template. The learner profile, schedule, and target scores are configured in `config/student_profile.json`.

### Features

- 12 specialised learning modules;
- dedicated workflows for Listening, General Reading, Writing Task 1, Writing Task 2, and Speaking;
- SM-2-inspired spaced repetition for vocabulary;
- an error registry that requires successful correction across different dates and contexts;
- append-only session and assessment logs;
- explicit separation of official results, external reviews, and AI inferences;
- adaptive weekly planning;
- a local HTML dashboard;
- a Python standard-library-only CLI;
- backups and data-structure validation.

### Architecture

```text
SKILL.md                 root orchestrator
skills/                  specialised learning modules
references/              pedagogy, scoring, source, and data policies
templates/               lesson, report, and feedback templates
scripts/coach_cli.py      local state, SRS, and analytics
config/                   learner profile and policy thresholds
data/                     private runtime data, never published
tests/                    CLI and data-policy tests
```

The root `SKILL.md` identifies the task and loads only the required specialist module. Exam texts and learner submissions are treated as data, not instructions. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the detailed design.

### Quick start

Python 3.10 or newer is required. No third-party Python packages are needed.

```bash
python scripts/coach_cli.py init
python scripts/coach_cli.py validate
```

Connect the folder to an AI environment that supports Markdown-based instructions, then use one of the built-in Russian trigger phrases:

```text
Начать диагностическую неделю
Составить план недели
Начать урок
Повторить словарь
Проверить General Writing Task 1
Проверить Writing Task 2
Разобрать Listening
Разобрать General Reading
Провести Speaking mock
Провести недельный контроль
Показать прогресс
```

For setup details, see [`docs/QUICK_START.md`](docs/QUICK_START.md).

### Dashboard

```bash
python scripts/coach_cli.py dashboard
```

The generated dashboard is stored locally at `data/dashboard.html`.

### Verification

```bash
python -m unittest discover -s tests -v
```

### Privacy

The `data/` directory may contain vocabulary, recurring errors, assessments, learner submissions, and session logs. It is excluded from the public repository. Never commit real learner work, audio recordings, local AI-tool settings, or backups.

The public version contains only an anonymised sample profile. A separate private working copy is recommended for real use.

### Limitations

- AI estimates for Writing and Speaking are indicative and do not replace an official examiner.
- Pronunciation cannot be assessed reliably from a text transcript alone.
- Stable score estimates require a series of comparable performances, not one strong result.
- This project is not affiliated with IELTS, the British Council, IDP, or Cambridge University Press & Assessment.

### Sources and inspiration

The project was built for a personal learning workflow. Open-source references and architectural inspiration are documented in [`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md).

### License

No licence has been selected. Standard copyright law applies until a `LICENSE` file is added.
