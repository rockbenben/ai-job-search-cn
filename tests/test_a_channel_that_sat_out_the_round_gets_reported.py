# -*- coding: utf-8 -*-
"""漏跑一条渠道在任何地方都不留痕迹 —— 于是同一个错犯了两次。

`job-scrape.md` 那张渠道表写着「**一轮正常要动 4 条**」「**少一行就是漏了一条
渠道**」，第 2 行还专门写着「CLI 被闸门挡住时，浏览器那条**照常进这一轮**」。
`portal_budget.py` 的实现也是这么做的（CLI 冷却时 `--check liepin-browser` 放行）。
2026-08-28 用户又裁定一次：「浏览器渠道是等同的，应该一起去跑。」

**四处写对了，执行两次都没照做：**

- 2026-08-25：CLI 撞 `RATE_LIMITED`，执行者把整个猎聘跳过。用户当场纠正
  「CLI 停了不要紧，你可以用浏览器的啊」，规则为此推翻重写。
- 2026-08-27：CLI 又撞 `RATE_LIMITED`，又没换道；同一轮前程无忧闸门放行、
  0 次查询。那天 `query_log`：猎聘 CLI 8 次、BOSS 4 次、智联 1 次、
  猎聘浏览器 0 次、前程无忧 0 次。

规则改对了、执行照旧，因为**没有任何东西在验它**。这两条检查补的就是这一环。

**判据用 `query_log` 不用新岗数**：新岗数分不清「跑了没收获」和「根本没打开过」，
而这两件事的下一步正好相反 —— 前者说明这条渠道这轮挖空了，后者说明它漏了。
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import datetime as _dt  # noqa: E402
import _cli  # noqa: E402
import audit_pipeline as ap  # noqa: E402
import ingest  # noqa: E402
import query_yield  # noqa: E402


class Fake:
    """在临时目录里搭一个只有 `query_log` 和额度账本的用户。"""

    def __init__(self, log, block_log=None):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        d = root / "users" / "u" / "job_scraper"
        d.mkdir(parents=True)
        (d / "seen_jobs.json").write_text(
            json.dumps({"seen": {}, "query_log": log}, ensure_ascii=False),
            encoding="utf-8")
        led = {"猎聘": {"block_log": {"cli": block_log}}} if block_log else {}
        (d / "portal_budget.json").write_text(
            json.dumps(led, ensure_ascii=False), encoding="utf-8")
        self.root, self.old_root, self.old_user = root, ap.ROOT, list(ap._USER)

    def __enter__(self):
        ap.ROOT = self.root
        ap._USER[:] = ["u"]
        return self

    def __exit__(self, *a):
        ap.ROOT = self.old_root
        ap._USER[:] = self.old_user
        self.tmp.cleanup()


def q(day, lane, n=1):
    return [{"date": day, "portal": lane, "query": "AI产品经理", "page": 1}
            for _ in range(n)]


FULL = q("2026-08-27", "liepin-search", 8) + q("2026-08-27", "boss-browser", 3) \
    + q("2026-08-27", "zhaopin-browser", 3) + q("2026-08-27", "51job-browser", 3)


class AMissedPlatformReachesTheClosing(unittest.TestCase):
    """漏的是**这一批**那一轮时，这条也要进收尾那一档。

    与 `TheMissedLaneReachesTheClosing` 同一个道理、同一个机制 ——那一条修的是
    「猎聘 CLI 停了浏览器没接上」，这一条修的是「整家一次都没打开过」。
    两条都是「这一轮丢了东西」，而收尾那一档原来一条都看不见。
    """

    def _row(self, day):
        # 只跑猎聘：BOSS / 智联 / 前程三家整轮 0 次。
        with Fake(q(day, "liepin-search", 6)):
            before = _cli._ROUND_SCOPED_CALLS[0]
            rows = ap.check_a_whole_channel_sat_out_the_round({}, {})
            return rows, _cli._ROUND_SCOPED_CALLS[0] - before

    def test_this_batch_is_reported_and_shouted(self):
        rows, shouted = self._row(_dt.date.today().isoformat())
        self.assertEqual(len(rows), 1, "漏了三家却没报")
        self.assertEqual(shouted, 1, "没喊 —— 收尾看不见它")

    def test_this_batch_gets_a_fix_he_can_do_now(self):
        rows, _ = self._row(_dt.date.today().isoformat())
        msg = rows[0][2]
        self.assertIn("/job-scrape", msg, "没给能当场做的那条")
        self.assertNotIn("补它：跑 /job-auto", msg,
                         "收尾里叫人再跑一次 /job-auto —— 原地转圈")

    def test_an_older_round_is_reported_but_not_shouted(self):
        rows, shouted = self._row("2026-08-20")
        self.assertEqual(len(rows), 1, "往日那轮不报了？")
        self.assertEqual(shouted, 0, "往日那轮也喊 —— 收尾会被存量淹掉")
        self.assertIn("跑 /job-auto", rows[0][2])

    def test_a_full_round_says_nothing_and_shouts_nothing(self):
        """控制用例：四条都跑了就一个字都不说，也不喊。"""
        day = _dt.date.today().isoformat()
        log = (q(day, "liepin-search", 4) + q(day, "boss-browser", 4)
               + q(day, "zhaopin-browser", 4)
               + q(day, "51job-browser", 4))
        with Fake(log):
            before = _cli._ROUND_SCOPED_CALLS[0]
            self.assertEqual(
                ap.check_a_whole_channel_sat_out_the_round({}, {}), [])
            self.assertEqual(_cli._ROUND_SCOPED_CALLS[0], before,
                             "什么都没报却喊了一声")


class TheMissedLaneReachesTheClosing(unittest.TestCase):
    """漏的是**今天**那一轮时，这条要进收尾那一档。

    此前它进不去：`--actionable` 唯一的信号是「调没调 `sendable_state`」，
    而这条报的不是「哪些材料还发得出去」，是「这一轮丢了一整条渠道」。
    于是同一个错犯了两次，两次都靠人当场发现（说明里记着那两次）。
    2026-08-31 加了第二个信号 `_cli.note_round_scoped()`。

    ## 补法要分两种

    收尾本身就在 `/job-auto` 里。在那儿印一句「补它：跑 /job-auto」就是让人
    原地转圈 —— 这个仓库管这叫「收尾那句话许了一个它兑现不了的诺」。
    所以今天那一支给的是能当场做的：补跑一次浏览器那条。
    """

    def _row(self, day):
        log = q(day, "liepin-search", 4)
        with Fake(log, [{"at": day + "T14:12:00", "act": "hit"}]):
            before = _cli._ROUND_SCOPED_CALLS[0]
            rows = ap.check_the_blocked_lane_handed_over({}, {})
            return rows, _cli._ROUND_SCOPED_CALLS[0] - before

    def test_today_is_reported_and_shouted(self):
        rows, shouted = self._row(_dt.date.today().isoformat())
        self.assertEqual(len(rows), 1, "今天漏了却没报")
        self.assertEqual(shouted, 1, "没喊 —— 收尾那一档看不见它")

    def test_todays_fix_is_something_he_can_do_right_now(self):
        rows, _ = self._row(_dt.date.today().isoformat())
        msg = rows[0][2]
        self.assertIn("/job-scrape", msg, "没给能当场做的那条")
        self.assertNotIn("补它：跑 /job-auto", msg,
                         "收尾里叫人再跑一次 /job-auto —— 那是原地转圈")

    def test_an_older_day_is_reported_but_not_shouted(self):
        """往日那一轮补不回来，收尾不该被它占一行。"""
        rows, shouted = self._row("2026-08-20")
        self.assertEqual(len(rows), 1, "往日那次不报了？")
        self.assertEqual(shouted, 0, "往日那次也喊了 —— 收尾会被存量淹掉")
        self.assertIn("跑 /job-auto", rows[0][2])

    def test_a_lane_that_did_hand_over_is_quiet(self):
        """控制用例：浏览器那条真接上了，就一个字都不该说。"""
        day = _dt.date.today().isoformat()
        log = q(day, "liepin-search", 4) + q(day, "liepin-browser", 2)
        with Fake(log, [{"at": day + "T14:12:00", "act": "hit"}]):
            before = _cli._ROUND_SCOPED_CALLS[0]
            self.assertEqual(ap.check_the_blocked_lane_handed_over(
                {}, {}), [])
            self.assertEqual(_cli._ROUND_SCOPED_CALLS[0], before,
                             "什么都没报却喊了一声")


class ADryChannelIsReported(unittest.TestCase):
    def _run(self, log, block_log=None):
        with Fake(log, block_log):
            return (ap.check_a_whole_channel_sat_out_the_round({}, {}),
                    ap.check_the_blocked_lane_handed_over({}, {}))

    def test_a_full_round_is_quiet(self):
        dry, hand = self._run(FULL)
        self.assertEqual(dry, [], "四条都跑了还在报")
        self.assertEqual(hand, [])

    def test_the_missing_platform_is_named(self):
        """**这才是当初露出来的那一头。** 前程无忧 0 次查询，此前没有一处会说。"""
        log = [x for x in FULL if x["portal"] != "51job-browser"]
        dry, _ = self._run(log)
        self.assertEqual(len(dry), 1)
        self.assertIn("1 家缺记录：前程无忧", dry[0][2])
        self.assertIn("无法确认是否打开过", dry[0][2])

    def test_either_liepin_lane_covers_that_platform(self):
        """猎聘两条通道是二选一 —— 走了浏览器那条就不算漏。"""
        log = [x for x in FULL if x["portal"] != "liepin-search"] \
            + q("2026-08-27", "liepin-browser", 4)
        dry, _ = self._run(log)
        self.assertEqual(dry, [])

    def test_zero_queries_is_not_the_same_as_zero_jobs(self):
        """跑了没收获（有查询记录）不报，根本没打开过（无记录）才报。"""
        dry, _ = self._run(FULL)                      # 每条都有查询记录
        self.assertEqual(dry, [])

    def test_it_reads_the_latest_round_not_the_whole_history(self):
        """存量补不了，报的是最近一轮 —— 一条永远红着的自检会被当噪音略过。"""
        log = q("2026-08-01", "liepin-search", 1) + FULL   # 老日子缺三家
        dry, _ = self._run(log)
        self.assertEqual(dry, [], "翻到旧日子上去了")

    def test_lopsided_browser_lanes_are_called_out(self):
        """用户 2026-08-28 裁定「浏览器渠道是等同的」——差一个数量级也要说。"""
        log = q("2026-08-27", "liepin-search", 8) + q("2026-08-27", "boss-browser", 9) \
            + q("2026-08-27", "zhaopin-browser", 1) + q("2026-08-27", "51job-browser", 3)
        dry, _ = self._run(log)
        self.assertEqual(len(dry), 1)
        self.assertIn("等同", dry[0][2])

    def test_same_day_rounds_and_recovery(self):
        day = "2026-08-27"
        with Fake(FULL) as fake, patch.object(ingest, "ROOT", fake.root):
            user_args = ["--user", "u", "--today", day, "--apply"]
            self.assertEqual(ingest.main(user_args + ["--start-round", "--expected", "猎聘", "BOSS"]), 0)
            path = fake.root / "users/u/job_scraper/seen_jobs.json"
            first = json.loads(path.read_text(encoding="utf-8"))["query_log"][-1]["round_id"]
            self.assertEqual(ingest.main(user_args + ["--start-round", "--expected", "猎聘", "BOSS"]), 0)
            second = json.loads(path.read_text(encoding="utf-8"))["query_log"][-1]["round_id"]
            self.assertNotEqual(first, second)
            attempt = user_args + ["--round-id", second, "--portal", "liepin-browser", "--query", "智能体"]
            for outcome, label in (("login_required", "需要登录"), ("captcha", "需要人工验证"),
                                   ("load_failed", "页面未加载")):
                self.assertEqual(ingest.main(attempt + ["--outcome", outcome]), 0)
                rows = ap.check_a_whole_channel_sat_out_the_round({}, {})
                self.assertIn(label, rows[0][2])
                self.assertIn("漏了 1 家：BOSS", rows[1][2])
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(("智能体", "猎聘"), query_yield.ran(doc))
            empty = fake.root / "empty.json"
            empty.write_text("[]", encoding="utf-8")
            self.assertEqual(ingest.main(attempt + ["--input", str(empty)]), 0)
            self.assertEqual(ingest.main(user_args + ["--round-id", second, "--portal", "boss-browser",
                                                      "--input", str(empty)]), 0)
            self.assertEqual(ap.check_a_whole_channel_sat_out_the_round({}, {}), [])
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(("智能体", "猎聘"), query_yield.ran(doc))


class TheBlockedLaneMustHandOver(unittest.TestCase):
    BLOCK = [{"at": "2026-08-27T14:12:52", "act": "hit", "why": "RATE_LIMITED"}]

    def _run(self, log, block_log):
        with Fake(log, block_log):
            return ap.check_the_blocked_lane_handed_over({}, {})

    def test_cli_blocked_and_browser_idle_is_reported(self):
        """2026-08-27 的形状：CLI 撞限流，同一天浏览器那条 0 次查询。"""
        out = self._run(FULL, self.BLOCK)
        self.assertEqual(len(out), 1)
        self.assertIn("没接上", out[0][1])
        self.assertIn("2026-08-27", out[0][2])

    def test_handing_over_is_quiet(self):
        out = self._run(FULL + q("2026-08-27", "liepin-browser", 5), self.BLOCK)
        self.assertEqual(out, [])

    def test_no_block_no_complaint(self):
        """CLI 没被挡过就没有换道这回事。"""
        self.assertEqual(self._run(FULL, None), [])

    def test_a_block_on_another_day_does_not_fire(self):
        """挡的是别天，而那天浏览器跑过 —— 不报。"""
        block = [{"at": "2026-08-25T10:00:00", "act": "hit", "why": "x"}]
        log = FULL + q("2026-08-25", "liepin-browser", 2)
        self.assertEqual(self._run(log, block), [])


class TheyAreWiredIntoTheAudit(unittest.TestCase):
    def test_both_are_registered(self):
        fns = [fn for _, fn in ap.CHECKS]
        self.assertIn(ap.check_a_whole_channel_sat_out_the_round, fns)
        self.assertIn(ap.check_the_blocked_lane_handed_over, fns)

    def test_the_platforms_match_the_workflow_table(self):
        """平台名要和 `job-scrape.md` 那张渠道表对得上，否则数的是别的东西。

        ⚠️ **表里第三列是 `--check` 用的名字（额度账本的键），不是 `query_log`
        里的 `portal` 值** —— 两套命名本来就不同（`前程无忧` vs `51job-browser`）。
        第一版拿 `portal` 值去表里找，当场报「查无此名」。能对的是**平台**。
        """
        doc = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        for platform in set(ap._LANES.values()):
            with self.subTest(platform=platform):
                self.assertIn(platform, doc, f"{platform} 在渠道表里查无此名")

    def test_the_table_still_has_five_lanes(self):
        """五条渠道是这两条检查的全部依据 —— 表里加减一行，这里要跟着改。

        钉的是**去重后的 (平台, 通道) 对**，不是 `_LANES` 的长度：那个字典是
        渠道别名 → 平台，同一条通道有好几个历史别名（`51job` / `51job-cdp` /
        `51job-browser`），长度是 15 不是 5。
        """
        import portal_budget as pb
        doc = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("渠道一共 **5 条**", doc)
        lanes = {(site, pb.lane_of(ch)) for ch, site in ap._LANES.items()}
        self.assertEqual(len(lanes), 5, f"通道数变了：{sorted(lanes)}")
        self.assertEqual(len({s for s, _ in lanes}), 4)

    def test_the_lane_map_is_not_a_second_copy(self):
        """**这才是当初露出来的那一头。** 第一版在这里抄了一份五条渠道 + 一份
        历史别名，当场少认了一半老名字。现在从正本 `PORTAL_ALIAS` 现推。"""
        from query_yield import PORTAL_ALIAS, PORTALS
        self.assertEqual(ap._LANES,
                         {c: s for c, s in PORTAL_ALIAS.items() if s in PORTALS})
        for old_name in ("boss-cdp", "51job", "智联招聘", "BOSS直聘"):
            with self.subTest(alias=old_name):
                self.assertIn(old_name, ap._LANES, "老别名认不出来")


if __name__ == "__main__":
    unittest.main()


class TheYieldTableMustKeepUp(unittest.TestCase):
    """抓完没跑 `query_yield --apply`，下一轮还拿挖空的词再抓一遍。

    `job-auto.md` 写着「补货完**必须跑**」，而验它的只有一条查
    **工作流文件里有没有这句话**的守卫 —— 不是查这一步跑没跑。
    实测 2026-08-28：当轮抓了 40 个新岗，词表那个块的日期还停在 08-27。
    """

    def _run(self, log, stamp):
        with Fake(log) as f:
            p = f.root / "users" / "u" / "profile"
            p.mkdir(parents=True, exist_ok=True)
            (p / "search-queries.md").write_text(
                f"### 实测产出（自动维护 · 最近更新 {stamp}）\n", encoding="utf-8")
            return ap.check_the_yield_table_kept_up({}, {})

    def test_stale_table_after_a_scrape_is_reported(self):
        """**这才是当初露出来的那一头。**"""
        out = self._run(FULL, "2026-08-26")
        self.assertEqual(len(out), 1)
        self.assertIn("2026-08-27", out[0][2])   # 最后一次抓取
        self.assertIn("2026-08-26", out[0][2])   # 词表停在哪天
        self.assertIn("query_yield.py --apply", out[0][2])

    def test_same_day_refresh_is_quiet(self):
        self.assertEqual(self._run(FULL, "2026-08-27"), [])

    def test_a_later_refresh_is_quiet(self):
        self.assertEqual(self._run(FULL, "2026-08-28"), [])

    def test_it_reaches_the_closing(self):
        """**无条件**进收尾那一档 —— 这一条和旁边那两条不一样。

        漏一条通道、漏一整家：往日那一轮补不回来，所以只为「这一批」喊。
        而 `query_yield.py --apply` 是拿 `query_log` 现算整张表，哪天跑都补
        得上 —— 没有「太晚了」这一说。不补的代价还落在**下一轮**：同一批挖空
        的词再抓一遍，每次请求隔 8 秒。
        """
        before = _cli._ROUND_SCOPED_CALLS[0]
        out = self._run(FULL, "2026-08-26")
        self.assertEqual(len(out), 1)
        self.assertEqual(_cli._ROUND_SCOPED_CALLS[0] - before, 1,
                         "没喊 —— 收尾那一档看不见它")

    def test_a_fresh_table_shouts_nothing(self):
        """控制用例：没东西可报时不许喊（`run()` 按调用次数判，不看返回值）。"""
        before = _cli._ROUND_SCOPED_CALLS[0]
        self.assertEqual(self._run(FULL, "2026-08-28"), [])
        self.assertEqual(_cli._ROUND_SCOPED_CALLS[0], before,
                         "什么都没报却喊了一声")

    def test_an_unreadable_stamp_says_nothing(self):
        """读不出块头就不报 —— 「没查」和「查过没有」是两件事。"""
        with Fake(FULL) as f:
            p = f.root / "users" / "u" / "profile"
            p.mkdir(parents=True, exist_ok=True)
            (p / "search-queries.md").write_text("没有那个块头\n", encoding="utf-8")
            self.assertEqual(ap.check_the_yield_table_kept_up({}, {}), [])

    def test_it_is_registered(self):
        self.assertIn(ap.check_the_yield_table_kept_up,
                      [fn for _, fn in ap.CHECKS])


class TheStoreSideGateTableIsRead(unittest.TestCase):
    """硬门 FAIL 有两个住址（`evaluation.md`、职位库），守卫原来只查一个。

    实测 2026-08-28：执行者在库里单边改判成硬门 FAIL，`writeback --apply`
    从 `evaluation.md` 把分数和判词顶了回来（那是对的，存档是事实源），
    但它不碰 `硬性条件` 与 `依据` —— 留下「硬门 FAIL 配判词值得投」，
    而这条检查读的是文件，一声没吭。
    """

    def test_a_store_side_fail_with_a_sellable_verdict_is_caught(self):
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        seen = {"x": {"title": "造的", "rank_verdict": "值得投",
                      "rank_breakdown": {"硬性条件": {"工作年限": "FAIL"}}}}
        out = ap.check_gate_fail_blocks_the_verdict(seen, {})
        self.assertEqual(len(out), 1)
        self.assertIn("工作年限", out[0][2])
        self.assertIn("职位库", out[0][2])

    def test_a_store_side_fail_with_a_blocking_verdict_is_fine(self):
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        seen = {"x": {"title": "造的", "rank_verdict": "硬门 FAIL (工作年限)",
                      "rank_breakdown": {"硬性条件": {"工作年限": "FAIL"}}}}
        self.assertEqual(ap.check_gate_fail_blocks_the_verdict(seen, {}), [])

    def test_all_pass_is_fine(self):
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        seen = {"x": {"title": "造的", "rank_verdict": "值得投",
                      "rank_breakdown": {"硬性条件": {"工作年限": "PASS"}}}}
        self.assertEqual(ap.check_gate_fail_blocks_the_verdict(seen, {}), [])


class TheArchiveIsPartOfTheDedupKey(unittest.TestCase):
    """归档的岗被当新岗抓回来 —— 查重只试了热库这一把钥匙。

    `job-scrape.md` Step 4 写着「查重还必须连存档一起查」，而验它的一处也没有。
    实测 2026-08-28：当轮入库只对了热库，28 个已经归档的岗被插了回来，
    两份随后各自演化（一个热库记 55「可以考虑」、存档记「硬门 FAIL」）。

    同一个形状这是第四次 —— 前三次记在 `norm_url` 的 docstring 和 Step 4 里：
    协议不一致、51job 路径前缀、裸 URL vs `url#职位名`。
    """

    def _run(self, hot, cold):
        with Fake([]) as f:
            (f.root / "users" / "u" / "job_scraper" / "archive.json").write_text(
                json.dumps({"seen": cold}, ensure_ascii=False), encoding="utf-8")
            return ap.check_the_archive_was_consulted(hot, {})

    HOT = {"a": {"title": "某岗", "url": "https://x.com/1", "rank_verdict": "值得投"}}

    def test_a_job_in_both_stores_is_reported(self):
        """**这才是当初露出来的那一头。**"""
        out = self._run(self.HOT, {"a": {"title": "某岗", "url": "https://x.com/1",
                                         "rank_verdict": "硬门 FAIL (明确排除)"}})
        self.assertEqual(len(out), 1)
        self.assertIn("热库和存档", out[0][1])
        self.assertIn("结论已经不一样", out[0][2])

    def test_protocol_differences_do_not_hide_it(self):
        """两边协议不同也要认出来 —— 那正是 `norm_url` 记的第一课。"""
        out = self._run(self.HOT, {"a": {"title": "某岗", "url": "http://x.com/1"}})
        self.assertEqual(len(out), 1)

    def test_the_51job_prefix_does_not_hide_it_either(self):
        hot = {"a": {"title": "某岗",
                     "url": "https://jobs.51job.com/all/171700088.html"}}
        cold = {"a": {"title": "某岗",
                      "url": "https://jobs.51job.com/shanghai-mhq/171700088.html"}}
        self.assertEqual(len(self._run(hot, cold)), 1)

    def test_tracking_params_do_not_hide_it_either(self):
        """智联搜索页 2026-09-01 给的锚点尾巴上挂着埋点参数，每搜一次换一串。

        不剥它，同一个岗每轮都会当成新岗再入库一遍 —— 实测那一轮 120 个
        「新岗」里有 43 组是库里已经有的。
        """
        hot = {"a": {"title": "某岗", "url": "https://www.zhaopin.com/jobdetail/CC1.htm"}}
        cold = {"a": {"title": "某岗", "url":
                      "http://www.zhaopin.com/jobdetail/CC1.htm"
                      "?refcode=4019&srccode=401901&data_identity=c8f0"}}
        self.assertEqual(len(self._run(hot, cold)), 1)

    def test_the_job_title_survives_the_query_strip(self):
        """剥查询串不能顺手把 `#职位名` 也剥掉 —— 同一 URL 下的两个岗要分得开。"""
        self.assertNotEqual(_cli.norm_url("//a/1.htm?q=2#甲"),
                            _cli.norm_url("//a/1.htm?q=3#乙"))

    def test_disjoint_stores_are_quiet(self):
        self.assertEqual(self._run(self.HOT, {"b": {"title": "别的",
                                                    "url": "https://x.com/2"}}), [])

    def test_it_never_deletes_a_side(self):
        """只报不改 —— 哪份新要看评分日期和材料，机械并会挑错（实测挑错过一次）。"""
        src = ap.check_the_archive_was_consulted.__code__.co_names
        for verb in ("pop", "remove", "atomic_write"):
            self.assertNotIn(verb, src, f"这条检查动了盘：{verb}")

    def test_it_is_registered(self):
        self.assertIn(ap.check_the_archive_was_consulted,
                      [fn for _, fn in ap.CHECKS])


class ATruncatedJobIdIsSpotted(unittest.TestCase):
    """截断的职位号 —— 不报错、不空白、URL 还打得开，只是指向另一个岗。

    扩展的安全层会把长串数字当 token 挡掉，所以抓取时要把 id 分段再还原；
    **分段容易，还原容易少一位**。实测 2026-08-29：一轮猎聘浏览器入库的 5 条，
    10 位职位号全写成了 9 位，而库里同族另外 586 条都是 10 位。
    9 位那个 URL 点开是「三亚 总经理」，而记录写着「<公司> AI 产品经理」。

    发现它靠的是人点开看了一眼。位数这件事机器一眼就能看出来。
    """

    def _rows(self, good_n, bad_n, n_good=40, n_bad=2):
        seen = {}
        for i in range(n_good):
            jid = str(10 ** (good_n - 1) + i)
            seen[f"g{i}"] = {"title": f"岗{i}",
                             "url": f"https://www.liepin.com/job/{jid}.shtml"}
        for i in range(n_bad):
            jid = str(10 ** (bad_n - 1) + i)
            seen[f"b{i}"] = {"title": f"截断{i}",
                             "url": f"https://www.liepin.com/job/{jid}.shtml"}
        return seen

    def test_the_odd_one_out_is_reported(self):
        """**这才是当初露出来的那一头。**"""
        out = ap.check_job_ids_are_not_truncated(self._rows(10, 9), {})
        self.assertEqual(len(out), 1)
        self.assertIn("截断0", out[0][2])
        self.assertIn("10 位", out[0][2])

    def test_a_uniform_family_is_quiet(self):
        self.assertEqual(ap.check_job_ids_are_not_truncated(self._rows(10, 10), {}), [])

    def test_a_small_family_is_left_alone(self):
        """样本太少时位数分布说明不了什么 —— 不猜。"""
        self.assertEqual(
            ap.check_job_ids_are_not_truncated(self._rows(10, 9, n_good=8), {}), [])

    def test_a_large_minority_is_not_truncation(self):
        """占比高就不是「个别写错」，可能是平台真的换过号段 —— 不报。"""
        self.assertEqual(
            ap.check_job_ids_are_not_truncated(self._rows(10, 9, n_bad=12), {}), [])

    def test_families_do_not_bleed_into_each_other(self):
        """`liepin.com/job/`（10 位）和 `liepin.com/a/`（8 位）是两族，别混着比。"""
        seen = self._rows(10, 10)
        for i in range(30):
            seen[f"a{i}"] = {"title": f"猎头岗{i}",
                             "url": f"https://www.liepin.com/a/{7000_0000 + i}.shtml"}
        self.assertEqual(ap.check_job_ids_are_not_truncated(seen, {}), [])

    def test_it_is_registered(self):
        self.assertIn(ap.check_job_ids_are_not_truncated,
                      [fn for _, fn in ap.CHECKS])
