# -*- coding: utf-8 -*-
"""auto 说「评到排空」，可没有任何一处在验它有没有排空。

`job-auto.md` 的循环第 1 步写着「队列里还有待评的 → 跑 `/job-rank`
（**它自己会评到排空**）」，而循环的四个分支里**没有一个出口是「队列非空」**。
停手条件表里唯一允许留下待评的，是「撞验证码 → 用户不响应 → 该渠道的岗
保持待评」。合起来就是一条可判的规则：

    队列非空 ⇒ 那些岗的渠道必须是停着的

而在这条检查之前，没有任何一处在验它。`doctor` 会说「还有 N 个没评」，
但它不区分「评不动」和「没去评」；auto 的总账那句「队列还剩多少」同样
只是照数报出来 —— 报出来反而让「还剩 66 个」看起来像一个正常结局。

## 实测代价（2026-09-01）

同一天里两次停在非空队列上（先 62 个、后 66 个），两次那些岗的渠道
**都已经解封**，两次都反过来叫用户自己敲 `/job-rank`。用户当场问：
「auto 不是该包含 rank 吗，为什么还提示 rank」。

第二条检查（同一份 JD 判定不一致）是同一次复查里发现的另一类：
`export_web_data` 的归并只看链接，同一份 JD 换个雇主脱敏名挂到另一个链接上
就绕过了它，于是两条记录可以拿到两个不同的判词，而面板只渲染其中一条 ——
渲染哪一条取决于归并顺序，不取决于哪条判得对。
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402
import portal_budget as pb  # noqa: E402

AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")


class TheRuleItLeansOnStillExists(unittest.TestCase):
    """这条检查的判据借自 job-auto.md。那句话没了，检查就成了无源之水。"""

    def test_the_loop_still_delegates_ranking_to_rank(self):
        self.assertRegex(AUTO, r"跑 /job-rank（它自己会评到排空",
                         "循环第 1 步不再说「rank 会评到排空」—— 这条检查的前提没了")

class TheQueueCheckFires(unittest.TestCase):

    @staticmethod
    def _seen(portal, n=3, status="new"):
        return {f"u{i}": {"url": f"https://x/{i}", "title": f"岗{i}",
                          "portal": portal, "status": status}
                for i in range(n)}

    def test_empty_queue_says_nothing(self):
        self.assertEqual(ap.check_queue_left_on_a_live_channel({}, {}), [])

    def test_a_live_channel_with_leftovers_is_reported(self):
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        out = ap.check_queue_left_on_a_live_channel(self._seen("boss-browser"), {})
        self.assertTrue(out, "渠道通着还剩 3 个待评，居然没报")
        self.assertEqual(out[0][0], "error")
        self.assertIn("3", out[0][2])
        self.assertIn("/job-rank", out[0][2], "没给出该敲的命令")

    def test_already_ranked_jobs_do_not_count(self):
        """只数 `status == "new"` 的 —— 评过的不该被当成积压。"""
        self.assertEqual(
            ap.check_queue_left_on_a_live_channel(
                self._seen("boss-browser", status="ranked"), {}), [])

    def test_pending_verification_pauses_only_its_channel_until_recovery(self):
        day = ap._dt.date.today().isoformat()
        log = [{"round_id": "round", "date": day, "expected": ["BOSS", "智联"]},
               {"round_id": "round", "portal": "boss-browser", "outcome": "captcha"}]
        seen = self._seen("boss-browser")
        seen["other"] = next(iter(self._seen("zhaopin-browser").values()))
        with (patch.object(ap, "_query_log", return_value=log),
              patch.object(ap, "_SELECTED_USER") as selected,
              patch.object(pb, "load", return_value={})):
            selected.get.return_value = "fixture"
            rows = ap.check_queue_left_on_a_live_channel(seen, {})
            self.assertNotIn("boss-browser", rows[0][2])
            self.assertIn("zhaopin-browser 1 个", rows[0][2])
            log.append({"round_id": "round", "portal": "boss-browser", "outcome": "ok"})
            self.assertIn("boss-browser 3 个", ap.check_queue_left_on_a_live_channel(seen, {})[0][2])


class TheDuplicateVerdictCheckFires(unittest.TestCase):
    """判据是 **JD 正文**，不是标题。第一版按标题分组，一轮误报 49 组 ——
    其中「AI 产品经理」一个标题下挂着 34 个互不相干的岗。"""

    BODY = "岗位职责：" + "定义 Agent 的能力边界、任务编排逻辑与工具调用策略。" * 6

    def _fixture(self, v1, v2, b1=None, b2=None):
        seen = {
            "a": {"url": "https://a/1", "title": "AI产品经理", "status": "ranked",
                  "rank_verdict": v1},
            "b": {"url": "https://b/2", "title": "AI产品经理", "status": "ranked",
                  "rank_verdict": v2},
        }
        det = {"https://a/1": {"url": "https://a/1", "description": b1 or self.BODY},
               "https://b/2": {"url": "https://b/2", "description": b2 or self.BODY}}
        return seen, det

    def test_same_jd_different_verdicts_is_reported(self):
        out = ap.check_same_posting_got_different_verdicts(*self._fixture("值得投", "可以考虑"))
        self.assertTrue(out, "同一份 JD 判成了两个结论，居然没报")
        self.assertEqual(out[0][0], "warn", "这一档要人工重判，不该占「要修」")
        self.assertIn("值得投", out[0][2])

    def test_same_jd_same_verdict_is_quiet(self):
        self.assertEqual(
            ap.check_same_posting_got_different_verdicts(*self._fixture("值得投", "值得投")), [])

    def test_same_title_different_jd_is_quiet(self):
        """**这才是第一版栽的地方。** 标题相同不等于同一个岗。"""
        other = "岗位职责：" + "负责智能硬件的供应链与量产上市，对经营结果负责。" * 6
        self.assertEqual(
            ap.check_same_posting_got_different_verdicts(
                *self._fixture("值得投", "硬门 FAIL (明确排除)", b2=other)), [])

    def test_a_job_without_a_stored_jd_does_not_participate(self):
        """没有正文就没有判据 —— 猜一个只会把误报换个来源。"""
        seen, det = self._fixture("值得投", "可以考虑")
        det.pop("https://b/2")
        self.assertEqual(ap.check_same_posting_got_different_verdicts(seen, det), [])


class BothAreRegistered(unittest.TestCase):
    def test_they_are_in_the_checks_table(self):
        names = [n for n, _ in ap.CHECKS]
        for want in ("去重：同一份 JD 挂多处，判定不一致", "抓取：还有待评的岗，而渠道没停"):
            with self.subTest(want=want):
                self.assertIn(want, names)


if __name__ == "__main__":
    unittest.main()
