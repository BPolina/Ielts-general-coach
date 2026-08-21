---
name: ielts-writing-task2
version: 2.0.0
description: Глубокая проверка IELTS Writing Task 2 с task-fit audit, критериями, самостоятельной коррекцией и реалистичной улучшенной версией.
---

# Writing Task 2

## Workflow

1. Отделить prompt, planning notes и scored essay.
2. Определить instruction words и обязательные части вопроса.
3. Проверить position и task fit до языковой правки.
4. Разделить текст на review units: sentence для локальной ошибки, paragraph для логики.
5. Оценить исходный essay по TR, CC, LR, GRA.
6. Для каждого критерия дать конкретные evidence points.
7. Выделить не более пяти blockers.
8. Попросить автора исправить ключевые фрагменты.
9. После попытки дать близкую к авторскому смыслу improved version.
10. Показать `Band 7 bridge`: три изменения, наиболее вероятно повышающие стабильность результата.
11. Назначить micro-rewrite и занести errors/chunks.

## Ограничения

- минимум 250 слов;
- ориентир 40 минут внутри полного Writing;
- score относится к original essay;
- model/improved essay не должен выглядеть как недостижимый Band 9;
- не придумывать факты и статистику ради «аргументации».

Форма разбора — `templates/writing_feedback.md`. Условия набора и редактирования под
таймером — `references/computer_test_protocol.md`.
