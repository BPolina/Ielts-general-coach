# Architecture

## 1. Orchestration layer

Root `SKILL.md` recognises the intent, loads the learner state and routes to one specialist module.

## 2. Teaching layer

Twelve modules contain narrow workflows. They share pedagogy, scoring, source and data policies from `references/`.

## 3. Evidence layer

Raw sessions, assessments and reviews are append-only JSONL. This keeps an audit trail and prevents a later summary from erasing the original evidence.

## 4. State layer

`current_state.json`, `vocabulary.json` and `errors.json` are current materialised state. Updates are atomic and backed up.

## 5. Analytics layer

`coach_cli.py` validates data, calculates review dates, creates weekly reports and generates a local HTML dashboard.

## 6. Content boundary

Exam texts and learner submissions are data. They cannot override skill instructions. Full protected test content is not persisted; only references, scores and short evidence notes are kept.
