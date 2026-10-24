# -*- coding: utf-8 -*-
"""没读 JD 正文，判词就不许往上抬到「可以考虑」及以上。

## 能判的那一半是合规的，别一刀切

未抓 JD 也判得了的：**跳过 / 不建议 / 硬门 FAIL** —— 薪资上沿低于底线、标题
明显是另一条职能线、地点跨城，这些光看卡片就成立，`prescreen` 存在的理由
就是它们。全库实测（2026-08-26）：477 个没读正文的判定里 **456 个是这一类**，
一个都不用动。

## 不能判的是往上抬

「可以考虑」的定义是「先问清楚关键信息再决定投不投」，而没读 JD 连**关键信息
是什么**都还不知道 —— 那个分只能来自标题和卡片字段，七道硬门一条没核过。
而它会把这个岗排进用户真的会去翻的那份名单里。

实测：**21 个**，全部产于 2026-08-13、全部来自 `liepin-search`、来源都写着
「粗筛（未抓 JD）」。用户 2026-08-26 问「为什么还有 20 个没读 jd，都是必须读的」——
他说得对，而框架里此前没有任何一处拦着这件事。

## 修法是退回待评，不是补一个分

没有依据的档位不该原地改成另一个档位（那只是换个数字继续猜）。
`--requeue-no-jd` 把它们放回队列，判词存进 `prev_verdict` 留痕。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as AP  # noqa: E402

RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
# 档序只有一份正本，切片即子集（`test_shared_vocab_single_source` 盯着）。
import _cli  # noqa: E402
BANDS = _cli.VERDICTS[:3]


def _seen():
    p = ROOT / ".active_user"
    if not p.is_file():
        return None
    f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
         / "job_scraper" / "seen_jobs.json")
    if not f.is_file():
        return None
    import _cli
    return _cli.seen_of(json.loads(f.read_text(encoding="utf-8")))


class TheRuleIsWrittenDown(unittest.TestCase):
    def test_the_workflow_says_which_way_is_forbidden(self):
        self.assertIn("判词就不许往上抬", RANK, "job-rank 里没有这条规则")

    def test_it_does_not_ban_the_legitimate_half(self):
        """**不是「没读 JD 就不许判」。** 一刀切会把 456 个合规判定一起废掉。"""
        i = RANK.index("判词就不许往上抬")
        seg = RANK[i:i + 1600]
        self.assertIn("判得了", seg, "没说清哪半是可以判的")
        self.assertRegex(seg, r"跳过 / 不建议 / 硬门 FAIL")

    def test_it_says_what_to_do_instead(self):
        i = RANK.index("判词就不许往上抬")
        seg = RANK[i:i + 1600]
        self.assertIn("保持 `status: new`", seg, "没说抓不到 JD 时该怎么办")
        self.assertIn("--requeue-no-jd", seg, "没给已经长出来那批的修法")


class TheAuditWatchesIt(unittest.TestCase):
    def test_the_check_is_registered(self):
        names = [n for n, _ in AP.CHECKS]
        self.assertIn("JD：没读就给了可投档位", names, "自检里没有这一项")

    def test_it_enters_the_actionable_tier(self):
        """这条报的是能退回待评的岗，不是只能围观的存量。

        `/job-auto` 收尾跑 `--actionable`；不调 `sendable_state` 的检查会被
        整条滤掉。实测 2026-10-24：41 个这类岗**全部**还能发，而收尾只报了
        1 条别的提醒。这里用一份最小临时库验「它真的问过还能不能发」。
        """
        import tempfile
        from pathlib import Path
        old = (AP.ROOT, AP._cli.ROOT)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "users" / "u").mkdir(parents=True)
            (root / ".active_user").write_text("u", encoding="utf-8")
            AP.ROOT = root
            AP._cli.ROOT = root
            e = {"url": "https://x/1", "title": "岗", "status": "ranked",
                 "rank_verdict": "可以考虑",
                 "rank_breakdown": {"来源": "粗筛（未抓 JD）"}}
            old_live = set(AP._cli.LIVE_SEEN)
            old_calls = AP._cli._SENDABLE_CALLS[0]
            AP._cli.LIVE_SEEN.clear()
            try:
                out = AP.check_no_jd_but_sellable({"k": e}, {})
                calls_after = AP._cli._SENDABLE_CALLS[0]
                live_seen = set(AP._cli.LIVE_SEEN)
            finally:
                AP.ROOT, AP._cli.ROOT = old
                AP._cli.LIVE_SEEN.clear()
                AP._cli.LIVE_SEEN.update(old_live)
            self.assertTrue(out, "构造的岗没有被报出来")
            self.assertGreater(calls_after, old_calls,
                               "检查没有问「还能不能发」——收尾会把它滤掉")
            self.assertIn(AP._cli.norm_url("https://x/1"), live_seen,
                          "还能发的岗没有记进收尾那两个集合")

    def test_an_unmatched_url_is_not_called_gone(self):
        """「对不上职位库」不是「已经出局」——没有链接的岗不许被说成已投/已下线。"""
        import tempfile
        from pathlib import Path
        old = (AP.ROOT, AP._cli.ROOT)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "users" / "u").mkdir(parents=True)
            (root / ".active_user").write_text("u", encoding="utf-8")
            AP.ROOT = root
            AP._cli.ROOT = root
            e = {"title": "没有链接的岗", "status": "ranked",
                 "rank_verdict": "可以考虑",
                 "rank_breakdown": {"来源": "粗筛（未抓 JD）"}}
            try:
                out = AP.check_no_jd_but_sellable({"k": e}, {})
            finally:
                AP.ROOT, AP._cli.ROOT = old
            msg = out[0][2] if out else ""
            self.assertIn("在职位库里对不上", msg,
                          "判不了还能不能发的岗被说成了别的状态")
            self.assertNotIn("都已经投出去", msg,
                             "把「判不了」说成了「已经出局」")

    def test_the_check_function_exists(self):
        self.assertTrue(hasattr(AP, "check_no_jd_but_sellable"))
        self.assertTrue(hasattr(AP, "requeue_no_jd_sellable"), "没有修法，只有报警")

    def test_the_requeue_keeps_a_receipt(self):
        """同 `requeue_unfounded_gate_fails`：判词留痕，不抹掉。"""
        import inspect
        src = inspect.getsource(AP.requeue_no_jd_sellable)
        self.assertIn("prev_verdict", src, "判词被直接抹掉了，事后查不出当初判了什么")
        self.assertIn("prev_score", src)
        self.assertIn("expect=stamp", src, "整份写回没带版本戳，会盖掉面板上刚点的那一下")

    def test_the_requeue_defaults_to_dry_run(self):
        import inspect
        src = inspect.getsource(AP.requeue_no_jd_sellable)
        self.assertIn("if not hit or not apply:", src, "不加 --apply 也会落盘")


class OnRealDataItIsClean(unittest.TestCase):
    """现算：库里不许再有「没读 JD 却给了可投档位」的岗。"""

    def test_no_such_job_remains(self):
        seen = _seen()
        if seen is None:
            self.skipTest("这台机器上没有职位库")
        bad = []
        for e in seen.values():
            if not isinstance(e, dict) or e.get("status") != "ranked":
                continue
            src = (e.get("rank_breakdown") or {}).get("来源") or ""
            if "读过 JD" in src or "读了 JD" in src or src.startswith("深评"):
                continue
            if any(b in (e.get("rank_verdict") or "") for b in BANDS):
                bad.append(f"{e.get('company','')[:16]} {e.get('title','')[:20]}")
        self.assertEqual(bad[:8], [],
                         f"{len(bad)} 个岗没读 JD 却给了可投档位 —— "
                         "跑 python tools/audit_pipeline.py --requeue-no-jd --apply")

    def test_the_legitimate_half_survived(self):
        """反向：别把「未抓 JD 判跳过」也一起清了 —— 那 456 个是对的。"""
        seen = _seen()
        if seen is None:
            self.skipTest("这台机器上没有职位库")
        ok = 0
        for e in seen.values():
            if not isinstance(e, dict) or e.get("status") != "ranked":
                continue
            src = (e.get("rank_breakdown") or {}).get("来源") or ""
            if "读过 JD" in src or "读了 JD" in src or src.startswith("深评"):
                continue
            if any(b in (e.get("rank_verdict") or "") for b in BANDS):
                continue
            ok += 1
        if ok < 50:
            self.skipTest("语料里这一类太少，说明不了")
        self.assertGreater(ok, 50, "未抓 JD 判出的跳过/不建议被一起清掉了")


if __name__ == "__main__":
    unittest.main()
