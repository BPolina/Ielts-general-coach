import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "coach_cli.py"


class CoachCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = os.environ.copy()
        self.env["IELTS_COACH_HOME"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, check=True):
        proc = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
        )
        if check and proc.returncode != 0:
            self.fail(f"CLI failed: {proc.stderr}\n{proc.stdout}")
        return proc

    def test_init_and_validate(self):
        self.run_cli("init")
        proc = self.run_cli("validate")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")

    def test_vocab_srs_and_mastery(self):
        self.run_cli("init")
        result = self.run_cli(
            "add-vocab", "--chunk", "meet a deadline", "--meaning", "уложиться в срок",
            "--topic", "work", "--date", "2026-07-20"
        )
        item = json.loads(result.stdout)["item"]
        self.assertEqual(item["id"], "V0001")
        self.run_cli("review-vocab", "--id", "V0001", "--quality", "4", "--mode", "meaning", "--date", "2026-07-20")
        self.run_cli("review-vocab", "--id", "V0001", "--quality", "4", "--mode", "form", "--date", "2026-07-21")
        self.run_cli("review-vocab", "--id", "V0001", "--quality", "4", "--mode", "spoken", "--date", "2026-07-27")
        result = self.run_cli("review-vocab", "--id", "V0001", "--quality", "4", "--mode", "written", "--date", "2026-08-10")
        item = json.loads(result.stdout)["item"]
        self.assertIn(item["mastery"], {"active", "stable"})

    def test_error_closes_after_three_dates_and_two_contexts(self):
        self.run_cli("init")
        result = self.run_cli(
            "add-error", "--skill", "writing", "--category", "lexis.collocation",
            "--original", "do a decision", "--correction", "make a decision", "--severity", "high",
            "--date", "2026-07-20"
        )
        error_id = json.loads(result.stdout)["item"]["id"]
        self.run_cli("practice-error", "--id", error_id, "--success", "--context", "Task 1", "--date", "2026-07-21")
        self.run_cli("practice-error", "--id", error_id, "--success", "--context", "Speaking", "--date", "2026-07-24")
        result = self.run_cli("practice-error", "--id", error_id, "--success", "--context", "Task 2", "--date", "2026-07-28")
        self.assertEqual(json.loads(result.stdout)["item"]["status"], "stable")

    def test_due_errors_orders_by_severity_then_overdue(self):
        self.run_cli("init")
        self.run_cli("add-error", "--skill", "reading", "--category", "reading.inference",
                     "--original", "a", "--correction", "b", "--severity", "medium",
                     "--date", "2026-07-01", "--next-review", "2026-07-02")
        self.run_cli("add-error", "--skill", "writing", "--category", "writing.task_fit",
                     "--original", "c", "--correction", "d", "--severity", "critical",
                     "--date", "2026-07-10", "--next-review", "2026-07-11")
        result = self.run_cli("due-errors", "--date", "2026-07-20")
        payload = json.loads(result.stdout)
        self.assertEqual((payload["total"], payload["returned"]), (2, 2))
        # critical идёт первым, несмотря на меньшую просрочку
        self.assertEqual(payload["items"][0]["severity"], "critical")
        self.assertEqual(payload["items"][0]["days_overdue"], 9)
        # урезанный вывод не тащит архивные поля
        self.assertNotIn("signature", payload["items"][0])
        self.assertNotIn("successful_evidence", payload["items"][0])
        # --limit урезает выдачу, но не должен занижать общее число просроченного
        limited = json.loads(self.run_cli("due-errors", "--date", "2026-07-20", "--limit", "1").stdout)
        self.assertEqual((limited["total"], limited["returned"]), (2, 1))

    def test_due_errors_skips_stable_and_future(self):
        self.run_cli("init")
        result = self.run_cli("add-error", "--skill", "writing", "--category", "lexis.collocation",
                              "--original", "do a decision", "--correction", "make a decision",
                              "--date", "2026-07-20")
        error_id = json.loads(result.stdout)["item"]["id"]
        # ещё не наступило
        self.assertEqual(json.loads(self.run_cli("due-errors", "--date", "2026-07-20").stdout)["total"], 0)
        for context, day in [("Task 1", "2026-07-21"), ("Speaking", "2026-07-24"), ("Task 2", "2026-07-28")]:
            self.run_cli("practice-error", "--id", error_id, "--success", "--context", context, "--date", day)
        # закрытая ошибка не всплывает даже сильно позже
        self.assertEqual(json.loads(self.run_cli("due-errors", "--date", "2027-01-01").stdout)["total"], 0)

    def test_show_error_reports_unknown_id(self):
        self.run_cli("init")
        proc = self.run_cli("show-error", "--id", "E9999", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["unknown"], ["E9999"])

    def test_recent_returns_tail_only(self):
        self.run_cli("init")
        for day in ["2026-07-20", "2026-07-21", "2026-07-22"]:
            self.run_cli("log-session", "--lesson-type", "listening", "--planned", "60",
                         "--completed", "60", "--status", "completed", "--date", day)
        payload = json.loads(self.run_cli("recent", "--log", "sessions", "--limit", "2").stdout)
        self.assertEqual((payload["total"], payload["returned"]), (3, 2))
        self.assertEqual(payload["items"][-1]["date"], "2026-07-22")

    def write_decision(self, **fields):
        path = Path(self.tmp.name) / "logs" / "decisions.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(fields, ensure_ascii=False) + "\n")

    def log_one_session(self, date, minutes=60):
        self.run_cli("log-session", "--lesson-type", "listening", "--planned", str(minutes),
                     "--completed", str(minutes), "--status", "completed", "--date", date)
        payload = json.loads(self.run_cli("recent", "--log", "sessions", "--limit", "1").stdout)
        return payload["items"][-1]["id"]

    def test_corrections_patch_field_without_rewriting_line(self):
        self.run_cli("init")
        session_id = self.log_one_session("2026-08-04")
        self.write_decision(id="D-1", timestamp="2026-08-06T10:00:00+03:00", type="data_correction",
                            supersedes=[session_id], corrections={"date": "2026-08-06"})
        fixed = json.loads(self.run_cli("recent", "--log", "sessions", "--limit", "1").stdout)
        self.assertEqual(fixed["items"][0]["date"], "2026-08-06")
        self.assertTrue(fixed["items"][0]["corrected"])
        self.assertEqual(fixed["corrections_applied"]["corrected"], 1)
        # строка на диске не переписана
        raw = json.loads(self.run_cli("recent", "--log", "sessions", "--limit", "1", "--raw").stdout)
        self.assertEqual(raw["items"][0]["date"], "2026-08-04")
        # отчёт считает урок по исправленной дате
        report = self.run_cli("weekly-report", "--start", "2026-08-05", "--end", "2026-08-09").stdout
        self.assertIn("Completed minutes: 60", report)
        self.assertIn("Field-corrected records: 1", report)

    def test_retract_removes_record_from_analytics(self):
        self.run_cli("init")
        session_id = self.log_one_session("2026-08-04")
        self.write_decision(id="D-1", timestamp="2026-08-06T10:00:00+03:00", type="data_correction",
                            supersedes=[session_id], retract=True)
        payload = json.loads(self.run_cli("recent", "--log", "sessions", "--limit", "5").stdout)
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["corrections_applied"]["retracted"], 1)

    def test_supersedes_without_instruction_is_reported(self):
        self.run_cli("init")
        session_id = self.log_one_session("2026-08-04")
        self.write_decision(id="D-1", timestamp="2026-08-06T10:00:00+03:00", supersedes=[session_id])
        proc = self.run_cli("validate", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(any("D-1" in e for e in json.loads(proc.stdout)["errors"]))
        # запись не тронута: молча выбрасывать доказательство нельзя
        self.assertEqual(json.loads(self.run_cli("recent", "--log", "sessions").stdout)["total"], 1)

    def test_decision_superseding_decision_is_narrative_only(self):
        self.run_cli("init")
        self.write_decision(id="D-1", timestamp="2026-08-06T10:00:00+03:00", decision="first")
        self.write_decision(id="D-2", timestamp="2026-08-06T11:00:00+03:00", supersedes=["D-1"])
        proc = self.run_cli("validate", check=False)
        self.assertEqual(json.loads(proc.stdout)["status"], "ok")
        items = json.loads(self.run_cli("recent", "--log", "decisions", "--limit", "5").stdout)["items"]
        self.assertEqual(items[0]["superseded_by"], "D-2")

    def test_error_thresholds_come_from_policies_file(self):
        """Порог из config/policies.json должен менять поведение, а не только печататься."""
        policy_path = ROOT / "config" / "policies.json"
        original = policy_path.read_text(encoding="utf-8")
        tightened = json.loads(original)
        tightened["errors"]["stable_unique_contexts"] = 3
        try:
            policy_path.write_text(json.dumps(tightened, ensure_ascii=False, indent=2), encoding="utf-8")
            self.run_cli("init")
            result = self.run_cli("add-error", "--skill", "writing", "--category", "lexis.collocation",
                                  "--original", "do a decision", "--correction", "make a decision",
                                  "--date", "2026-07-20")
            error_id = json.loads(result.stdout)["item"]["id"]
            self.run_cli("practice-error", "--id", error_id, "--success", "--context", "Task 1", "--date", "2026-07-21")
            result = self.run_cli("practice-error", "--id", error_id, "--success", "--context", "Speaking", "--date", "2026-07-24")
            # двух контекстов больше не хватает — при прежнем пороге здесь было бы stable
            self.assertEqual(json.loads(result.stdout)["item"]["status"], "improving")
            result = self.run_cli("practice-error", "--id", error_id, "--success", "--context", "Task 2", "--date", "2026-07-28")
            self.assertEqual(json.loads(result.stdout)["item"]["status"], "stable")
        finally:
            policy_path.write_text(original, encoding="utf-8")

    def test_validate_catches_prose_drift(self):
        policy_path = ROOT / "config" / "policies.json"
        original = policy_path.read_text(encoding="utf-8")
        drifted = json.loads(original)
        drifted["vocabulary"]["minimum_delayed_recall_rate"] = 0.8
        try:
            policy_path.write_text(json.dumps(drifted, ensure_ascii=False, indent=2), encoding="utf-8")
            self.run_cli("init")
            proc = self.run_cli("validate", check=False)
            self.assertEqual(proc.returncode, 1)
            reported = " ".join(json.loads(proc.stdout)["errors"])
            self.assertIn("minimum_delayed_recall_rate", reported)
            self.assertIn("80%", reported)
        finally:
            policy_path.write_text(original, encoding="utf-8")

    def test_validate_reports_effective_policies(self):
        self.run_cli("init")
        payload = json.loads(self.run_cli("validate").stdout)
        self.assertEqual(payload["effective_policies"]["errors"]["stable_unique_contexts"], 2)

    def test_multi_mode_review_advances_srs_once_by_worst_mode(self):
        self.run_cli("init")
        self.run_cli("add-vocab", "--chunk", "look forward to", "--meaning", "ждать", "--date", "2026-08-01")
        result = self.run_cli("review-vocab", "--id", "V0001", "--mode", "meaning", "written",
                              "--quality", "0", "5", "--date", "2026-08-03")
        item = json.loads(result.stdout)["item"]
        # провал на recall не затирается успехом в письме
        self.assertEqual(item["srs"]["repetitions"], 0)
        self.assertEqual(item["mastery"], "new")
        # но само письменное употребление как доказательство сохранено
        self.assertEqual(item["successful_uses"]["written"], ["2026-08-03"])
        self.assertEqual(item["successful_uses"]["meaning"], [])
        self.assertEqual(item["successful_review_dates"], [])
        review = json.loads(result.stdout)["review"]
        self.assertEqual((review["quality"], review["qualities"]), (0, [0, 5]))

    def test_one_quality_applies_to_every_mode(self):
        self.run_cli("init")
        self.run_cli("add-vocab", "--chunk", "meet a deadline", "--meaning", "успеть", "--date", "2026-08-01")
        result = self.run_cli("review-vocab", "--id", "V0001", "--mode", "spoken", "written",
                              "--quality", "4", "--date", "2026-08-03")
        item = json.loads(result.stdout)["item"]
        self.assertEqual(item["srs"]["repetitions"], 1)
        self.assertEqual(item["successful_uses"]["spoken"], ["2026-08-03"])
        self.assertEqual(item["successful_uses"]["written"], ["2026-08-03"])

    def test_quality_count_must_match_modes(self):
        self.run_cli("init")
        self.run_cli("add-vocab", "--chunk", "in due course", "--meaning", "в своё время", "--date", "2026-08-01")
        proc = self.run_cli("review-vocab", "--id", "V0001", "--mode", "meaning", "written", "spoken",
                            "--quality", "4", "5", "--date", "2026-08-03", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--quality", json.loads(proc.stdout)["message"])

    def test_transliteration_warning_is_advisory_and_dated(self):
        self.run_cli("init")
        # запись до вступления соглашения в силу — не проверяется
        self.run_cli("add-error", "--skill", "writing", "--category", "grammar.article",
                     "--original", "I go to the work", "--correction", "I go to work",
                     "--explanation", "Oshibka zafiksirovana dvazhdy, artikl ne nuzhen",
                     "--date", "2026-08-01")
        payload = json.loads(self.run_cli("validate").stdout)
        self.assertEqual(payload["warnings"], [])

        self.run_cli("add-error", "--skill", "writing", "--category", "grammar.preposition",
                     "--original", "answer on the letter", "--correction", "answer the letter",
                     "--explanation", "Predlog vybran po russkoi modeli, oshibka povtoryaetsya",
                     "--date", "2026-08-10")
        proc = self.run_cli("validate")
        payload = json.loads(proc.stdout)
        self.assertEqual(len(payload["warnings"]), 1)
        self.assertIn("E0002", payload["warnings"][0])
        # предупреждение не проваливает проверку
        self.assertEqual((proc.returncode, payload["status"]), (0, "ok"))

    def test_english_content_is_not_flagged_as_transliteration(self):
        self.run_cli("init")
        self.run_cli("add-error", "--skill", "writing", "--category", "lexis.collocation",
                     "--original", "If I will know about the deadline earlier, I would have finished",
                     "--correction", "If I had known about the deadline earlier, I would have finished",
                     "--explanation", "Второй тип условного предложения: if + Past Perfect.",
                     "--date", "2026-08-10")
        self.assertEqual(json.loads(self.run_cli("validate").stdout)["warnings"], [])

    def test_prune_backups_dry_run_keeps_every_file(self):
        self.run_cli("init")
        self.run_cli("add-vocab", "--chunk", "meet a deadline", "--meaning", "успеть", "--date", "2026-08-01")
        for quality in ("3", "4", "5"):
            self.run_cli("review-vocab", "--id", "V0001", "--mode", "meaning", "--quality", quality)
        backups = Path(self.tmp.name) / ".backups"
        before = len(list(backups.glob("*.bak")))
        self.assertGreater(before, 1)
        payload = json.loads(self.run_cli("prune-backups", "--keep", "1", "--dry-run").stdout)
        self.assertTrue(payload["dry_run"])
        self.assertGreater(payload["would_remove"], 0)
        self.assertEqual(len(list(backups.glob("*.bak"))), before)  # ничего не удалено

    def test_prune_backups_keeps_newest(self):
        self.run_cli("init")
        self.run_cli("add-vocab", "--chunk", "in due course", "--meaning", "в своё время", "--date", "2026-08-01")
        for quality in ("3", "4", "5"):
            self.run_cli("review-vocab", "--id", "V0001", "--mode", "meaning", "--quality", quality)
        backups = Path(self.tmp.name) / ".backups"
        payload = json.loads(self.run_cli("prune-backups", "--keep", "1").stdout)
        self.assertEqual(payload["kept"], 1)
        self.assertEqual(len(list(backups.glob("*.bak"))), 1)

    def test_register_is_a_review_mode(self):
        self.run_cli("init")
        self.run_cli("add-vocab", "--chunk", "I am writing to enquire", "--meaning", "пишу, чтобы узнать",
                     "--register", "formal", "--date", "2026-08-01")
        result = self.run_cli("review-vocab", "--id", "V0001", "--mode", "register", "--quality", "4")
        item = json.loads(result.stdout)["item"]
        self.assertEqual(item["successful_uses"]["register"], [date.today().isoformat()])

    def test_dashboard_created(self):
        self.run_cli("init")
        result = self.run_cli("dashboard")
        path = Path(json.loads(result.stdout)["dashboard"])
        self.assertTrue(path.exists())
        self.assertIn("IELTS General Coach", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
