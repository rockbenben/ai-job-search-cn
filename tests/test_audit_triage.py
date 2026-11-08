"""Checks refined after reviewing the active user's audit findings."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_pipeline as audit
import export_web_data as export
import writeback


class AuditTriageTests(unittest.TestCase):
    def jobs(self, salary_b="40-60k", tail_b="A"):
        body = "负责企业AI产品需求调研与工作流设计。" * 50
        seen = {
            "a": {"url": "https://example.com/a", "title": "产品经理", "salary": "40-60k", "status": "ranked", "rank_verdict": "值得投"},
            "b": {"url": "https://example.com/b", "title": "产品经理", "salary": salary_b, "status": "ranked", "rank_verdict": "可以考虑"},
        }
        details = {"https://example.com/a": {"description": body + "A"}, "https://example.com/b": {"description": body + tail_b}}
        return seen, details

    def test_shared_prefix_is_not_equal_job_text(self):
        self.assertEqual(audit.check_same_posting_got_different_verdicts(*self.jobs(tail_b="B")), [])

    def test_different_salary_can_explain_different_verdict(self):
        self.assertEqual(audit.check_same_posting_got_different_verdicts(*self.jobs(salary_b="20-30k")), [])

    def test_identical_text_and_conditions_still_warn(self):
        self.assertTrue(audit.check_same_posting_got_different_verdicts(*self.jobs()))

    def test_origin_prefix_does_not_change_verdict(self):
        seen, details = self.jobs()
        seen["b"]["rank_verdict"] = "粗筛：值得投"
        self.assertEqual(audit.check_same_posting_got_different_verdicts(seen, details), [])

    def test_unknown_gate_keeps_its_inner_parentheses(self):
        text = export.gate_why("未知（JD未提相关用工形式）", "")
        self.assertEqual(text.count("（"), text.count("）"))
        self.assertIn("JD未提相关用工形式", text)

    def test_multiple_forbidden_claims_are_kept_together(self):
        rows = export.parse_gaps('## 缺口\n- 「桌面自动化」——没有做过（别写成：「熟悉桌面自动化」「做过企业推广」）\n')
        self.assertEqual(rows[0]["detail"], "没有做过")
        self.assertIn("熟悉桌面自动化", rows[0]["overclaim"])
        self.assertIn("做过企业推广", rows[0]["overclaim"])

    def test_inner_dash_is_not_a_field_separator(self):
        rows = export.parse_gaps('## 缺口\n- 尚无带队经验（例如「带团队——交付产品」）\n')
        self.assertEqual(rows[0]["detail"], "")
        self.assertTrue(rows[0]["claim"].endswith("）"))

    def test_empty_actionable_view_does_not_claim_everything_passed(self):
        out = io.StringIO()
        with patch.object(audit._cli, "pick_user", return_value="sample"), patch.object(audit, "run", return_value=[]), contextlib.redirect_stdout(out):
            self.assertEqual(audit.main(["--actionable"]), 0)
        self.assertIn("历史记录", out.getvalue())
        self.assertNotIn("检查全过", out.getvalue())

    def test_writeback_uses_the_same_normalized_title_as_the_panel(self):
        short = {"url": "https://example.com/a", "title": "AI Agent 产品经理 （零售行业 ）"}
        long = {"url": short["url"], "title": short["title"] + " 50-80K*16薪"}
        entry, reason = writeback.pick_entry([short, long], "某公司_AI Agent产品经理（零售行业）")
        self.assertIs(entry, short)
        self.assertEqual(reason, "")

    def test_writeback_does_not_choose_the_shorter_peer_title(self):
        short = {"url": "https://example.com/a", "title": "产品经理"}
        long = {"url": short["url"], "title": "高级产品经理"}
        entry, _ = writeback.pick_entry([short, long], "某公司_高级产品经理")
        self.assertIs(entry, long)

    def test_writeback_still_refuses_identical_normalized_peer_titles(self):
        first = {"url": "https://example.com/a", "title": "AI 产品经理"}
        second = {"url": first["url"], "title": "AI产品经理"}
        entry, reason = writeback.pick_entry([first, second], "某公司_AI产品经理")
        self.assertIsNone(entry)
        self.assertIn("2 个岗", reason)

    def test_nonstandard_pass_field_is_not_reported_as_rejection(self):
        seen = {"a": {"title": "产品经理", "rank_verdict": "可以考虑",
                      "rank_breakdown": {"硬性条件": {"地点（跨城搬迁）": "PASS"}}}}
        message = audit.check_gate_is_one_of_the_seven(seen, {})[0][2]
        self.assertIn("不能据此认定这些岗位都被排除", message)
        self.assertNotIn("个岗判了硬门", message)
