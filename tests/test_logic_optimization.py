import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import auto_progress
import jd_store
import score
import scoring
from validate_evaluations import exclusion_errors


class LogicOptimizationTests(unittest.TestCase):
    def test_unknown_pay_redistributes_weights_and_keeps_adjustment(self):
        dims = {"技能与经验": 60, "薪资与职级": None,
                "强度与公司性质": 50, "发展与风险": 70}
        self.assertEqual(scoring.composite(dims, {"专业减分": -5}), 56)

    def test_note_uses_months_from_salary_string(self):
        note = scoring.pay_note({"salary": "35-40k·15薪", "salaryMonths": 12}, 45, (72, 96))
        self.assertIn("15薪", note)
        self.assertNotIn("没写几薪", note)
        self.assertIn("52.5-60", note)

    def test_invalid_months_are_explained_as_assumed(self):
        note = scoring.pay_note({"salary": "35-40k·25薪", "salaryMonths": 25}, 45, (72, 96))
        self.assertIn("按 12 薪", note)
        self.assertNotIn("×25薪", note)

    def test_deep_document_can_clear_and_restore_pay(self):
        text = "| 薪资与职级 | 55 | 旧说明 |\n综合得分：59/100\n## 结论：可以考虑\n"
        cleared = score.patch_evaluation(text, (55, 59, "可以考虑"),
                                         (None, 61, "可以考虑", "薪资未知"))
        self.assertIn("信息缺失（不计入）", cleared)
        restored = score.patch_evaluation(cleared, (None, 61, "可以考虑"),
                                          (55, 59, "可以考虑", "已确认薪资"))
        self.assertIn("| 55 |", restored)

    def test_same_url_preserves_each_job_and_refuses_ambiguous_fallback(self):
        details = jd_store.DetailIndex()
        a = {"url": "https://example.com/a", "title": "产品经理", "description": "甲"}
        b = dict(a, title="工程师", description="乙")
        details.add(a)
        details.add(b)
        self.assertEqual(len(details), 2)
        self.assertIsNone(details.get(a["url"]))
        self.assertIs(jd_store.detail_for(details, a), a)
        self.assertIs(jd_store.detail_for(details, b), b)

    def test_legacy_unique_link_can_be_resolved(self):
        details = jd_store.DetailIndex()
        details.add({"url": "https://example.com/a", "description": "旧正文"})
        self.assertEqual(jd_store.detail_for(details, {"url": "https://example.com/a", "title": "产品经理"})["description"], "旧正文")

    def test_target_is_complete_only_after_materials_are_saved(self):
        job = {"id": "a", "verdict": "值得投", "evaluated": True,
               "materials": {"greeting": "您好"}}
        pending = dict(job, id="b", materials={})
        result = auto_progress.progress([job, pending, dict(job, id="c", dupOf="a")], 2)
        self.assertTrue(result["stop_search"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["remaining"], 1)
        self.assertEqual(result["pending"], ["b"])
        self.assertTrue(auto_progress.progress([job, dict(pending, materials={"greeting": "您好"})], 2)["complete"])

    def test_target_respects_applied_and_preferences(self):
        jobs = [{"id": "a", "verdict": "值得投", "applied": True},
                {"id": "b", "verdict": "值得投", "prefTags": ["agency"]}]
        self.assertEqual(auto_progress.progress(jobs, 2, {"agency": False})["eligible"], 0)

    def test_exclusion_requires_both_real_sources(self):
        entry = {"title": "产品经理", "rank_verdict": "硬门 FAIL (候选人明确排除)",
                 "rank_breakdown": {"排除依据": {"个人条件": "不接受外包", "职位原文": "劳务外包"}}}
        self.assertEqual(exclusion_errors(entry, "本人不接受外包", {"description": "这是劳务外包岗位"}), [])
        self.assertTrue(exclusion_errors(entry, "接受外包", {"description": "正式招聘"}))


if __name__ == "__main__":
    unittest.main()
