---
name: ielts-general-planner
version: 2.0.0
description: Создание адаптивного недельного плана по данным, ошибкам, задолженности и целям IELTS.
---

# Weekly Planner

1. Прочитай profile, current_state, последние 14 дней sessions/assessments, due vocabulary и active errors.
2. Определи текущую фазу по `references/26_week_roadmap.md` — она задаёт, что на этой
   неделе уместно, а что рано. Условия перехода между фазами — в
   `references/adaptation_rules.md`; они зависят от данных, а не от календаря.
3. Назови невыполненный carryover.
4. Выбери 2–4 измеримые цели и максимум 3 класса ошибок.
5. Назначь критерии успеха на Saturday control.
6. Распредели 5 учебных дней + Saturday control + Sunday review.
7. Сохрани решение в `data/logs/decisions.jsonl` с причиной.
8. Обнови `data/current_state.json`.

## Формат целей

Плохо: «улучшить словарь».

Хорошо:

- воспроизвести ≥ 75% из 30 due chunks без подсказки;
- написать formal complaint letter за 22 минуты с полным покрытием трёх bullet points;
- сократить `grammar.article` в контрольном тексте до ≤ 4 подтверждённых ошибок;
- получить ≥ 17/20 в Listening block без `lost_place` более одного раза.

Используй `templates/weekly_plan.md`.
