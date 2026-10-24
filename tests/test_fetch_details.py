"""抓详情：撞风控必须**立刻停手**，而且错误要两个流都看。

## 这条测试是被打过脸才写的

`cdp-portals.md` 的账号安全铁律写着：撞验证码 / 风控提示就立即停止、不重试硬闯。
但这段逻辑一直是每次临时写的，于是写错过一次：

    try:
        d = json.loads(r.stdout)          # ← 错误不在 stdout
    except json.JSONDecodeError:
        continue                          # ← 限流被当成「解析失败」跳过
    if d.get("code") == "RATE_LIMITED":   # ← 永远走不到
        break

`liepin-search` CLI 的错误走 **stderr + 退出码 1**，stdout 是空的。结果一批 13 个
URL——**第一个就撞限流**——全部发了出去，一个都没停。13 次本不该发出的请求。

**安全机制不能靠每次现写。** 所以逻辑固化进 `tools/fetch_details.py`，这里盯住它。
"""

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
import fetch_details as fd  # noqa: E402
import portal_budget as pb  # noqa: E402


def proc(stdout="", stderr="", code=0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code,
                                       stdout=stdout, stderr=stderr)


RATE = json.dumps({"error": "详情页被重定向到限流验证页", "code": "RATE_LIMITED"},
                  ensure_ascii=False)
GOOD = json.dumps({"url": "https://x/1", "title": "某岗",
                   "description": "正文" * 60}, ensure_ascii=False)


class ErrorsAreReadFromBothStreams(unittest.TestCase):
    def test_error_on_stderr_is_parsed(self):
        """这正是漏掉的那一步：错误在 stderr，stdout 是空的。"""
        d = fd.parse_result(proc(stdout="", stderr=RATE, code=1))
        self.assertEqual(d.get("code"), "RATE_LIMITED",
                         "只看 stdout 会把限流当成「解析失败」")

    def test_success_on_stdout_is_parsed(self):
        d = fd.parse_result(proc(stdout=GOOD))
        self.assertEqual(d.get("title"), "某岗")

    def test_garbage_on_both_streams_is_reported_not_swallowed(self):
        d = fd.parse_result(proc(stdout="<html>", stderr="boom", code=1))
        self.assertEqual(d.get("code"), "UNPARSEABLE")
        self.assertIn("退出码", d.get("error", ""))


class StopsImmediatelyOnRateLimit(unittest.TestCase):
    """撞风控就停 —— 不是「记一笔失败然后继续」。"""

    def setUp(self):
        self.calls = []

    def _fetch(self, responses):
        def f(bun, url):
            self.calls.append(url)
            return responses.get(url, {"error": "?", "code": "UNKNOWN"})
        return f

    def test_first_url_rate_limited_stops_the_whole_run(self):
        urls = [{"url": f"https://x/{i}", "title": f"岗{i}"} for i in range(13)]
        r = fd.run("张三", urls, apply=True,
                   fetch=self._fetch({"https://x/0": json.loads(RATE)}),
                   sleep=lambda s: None, budget={})
        self.assertEqual(len(self.calls), 1,
                         f"第一个就撞限流，却发了 {len(self.calls)} 次请求")
        self.assertEqual(r["stopped"], "RATE_LIMITED")

    def test_rate_limit_midway_stops_and_keeps_what_was_fetched(self):
        urls = [{"url": f"https://x/{i}", "title": f"岗{i}"} for i in range(6)]
        good = {"url": "https://x/0", "title": "岗0", "description": "正文" * 60}
        saved = []
        orig = fd.st.save
        fd.st.save = lambda user, d: saved.append(d)
        self.addCleanup(lambda: setattr(fd.st, "save", orig))
        r = fd.run("张三", urls, apply=True,
                   fetch=self._fetch({"https://x/0": good,
                                      "https://x/1": json.loads(RATE)}),
                   sleep=lambda s: None, budget={})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(r["ok"], 1, "停手前抓到的必须留下")
        self.assertEqual(len(saved), 1, "抓到就该当场存，别攒到最后")

    def test_ordinary_failures_do_not_stop_the_run(self):
        """NOT_FOUND 这类不是风控，继续跑就行 —— 别把停手条件放宽。"""
        urls = [{"url": f"https://x/{i}", "title": f"岗{i}"} for i in range(3)]
        r = fd.run("张三", urls, apply=True,
                   fetch=self._fetch({
                       "https://x/0": {"error": "没了", "code": "NOT_FOUND"},
                       "https://x/1": {"error": "解析不出", "code": "PARSE_FAILED"},
                       "https://x/2": {"error": "网络", "code": "REQUEST_FAILED"}}),
                   sleep=lambda s: None, budget={})
        self.assertEqual(len(self.calls), 3)
        self.assertIsNone(r["stopped"])
        self.assertEqual(len(r["failed"]), 3)

    def test_dry_run_sends_nothing(self):
        urls = [{"url": "https://x/1", "title": "岗"}]
        r = fd.run("张三", urls, apply=False,
                   fetch=self._fetch({}), sleep=lambda s: None, budget={})
        self.assertEqual(len(self.calls), 0, "试运行不该发任何请求")
        self.assertEqual(r["attempted"], 0)


class AnExistingCooldownStopsTheRun(unittest.TestCase):
    """已经封着的通道，不该由这个工具再发出一次请求。

    `fetch_details` 自己会记账、撞到限流还会 `block()`，但它此前只做了
    「撞了之后停」，没做「来之前先看闸门」——上一轮留下的 24 小时冷却是
    可以绕过的。这个工具是主动发请求的那一方，闸门必须在这里生效。
    """

    def test_a_blocked_channel_sends_nothing(self):
        budget = {}
        pb.block(budget, "liepin-search", "上一轮撞了限流",
                 dt.datetime(2026, 10, 24, 12, 0, 0))
        calls = []
        with mock.patch.object(fd, "find_runtime", return_value=[]):
            r = fd.run("张三", [{"url": "https://x/1", "title": "岗"}],
                       apply=True,
                       fetch=lambda runtime, url: calls.append(url) or {},
                       sleep=lambda s: None, budget=budget)
        self.assertEqual(calls, [], "通道封着，fetch_details 仍然发了请求")
        self.assertEqual(r["stopped"], "BLOCKED")
        self.assertIn("停着", r.get("gate", ""))


class AnotherWriterDoesNotGetClobbered(unittest.TestCase):
    """补一轮 JD 要几分钟到几十分钟，额度文件却可能被总览页改。

    这一趟只在开跑时读一次。中间用户点了「继续抓」（`serve.apply_unblock`
    读→改→写一次落盘），拿开跑那份快照写回去就把他刚解开的冷却
    **盖回封着**——两边都不报错，而告警条会重新挂上。
    """

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "users" / "u" / "job_scraper").mkdir(parents=True)
        old = pb.ROOT, fd.ROOT
        pb.ROOT, fd.ROOT = tmp, tmp
        self.addCleanup(lambda: (setattr(pb, "ROOT", old[0]),
                                 setattr(fd, "ROOT", old[1])))
        orig_save = fd.st.save
        fd.st.save = lambda user, d: None
        self.addCleanup(lambda: setattr(fd.st, "save", orig_save))
        patcher = mock.patch.object(fd, "find_runtime", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_one(self, fetch):
        return fd.run("u", [{"url": "https://x/1", "title": "岗"}],
                      apply=True, fetch=fetch, sleep=lambda s: None)

    def test_a_concurrent_action_is_merged_not_overwritten(self):
        pb.save("u", {"猎聘": {"actions": []}})
        orig_note, fired = pb.note, {"yes": False}

        def note_then_other_writer(data, portal, n, now, kind=""):
            orig_note(data, portal, n, now, kind)
            if not fired["yes"]:
                fired["yes"] = True
                other, _ = pb.load_stamped("u")
                pb.note(other, "BOSS", 1, now, kind="navigate")
                pb.save("u", other)

        with mock.patch.object(pb, "note", note_then_other_writer):
            r = self._run_one(lambda bun, url: {
                "url": url, "title": "岗", "description": "正文" * 60})
        self.assertEqual(r["ok"], 1)
        self.assertIsNone(r["stopped"])
        saved = pb.load("u")
        self.assertTrue(saved.get("BOSS", {}).get("actions"),
                        "另一边记的动作被这一趟的旧快照写没了")
        self.assertTrue(saved.get("猎聘", {}).get("actions"),
                        "这一趟自己的动作没记上")

    def test_three_collisions_in_a_row_stop_the_run(self):
        """连着撞三次说明另一个人在连续写 —— 这一趟该停，不是无限重试。"""
        pb.save("u", {"猎聘": {"actions": []}})
        calls = []

        def always_stale(user, data, *, expect=None):
            raise _cli.StaleWrite("别人一直在写")

        with mock.patch.object(pb, "save", always_stale):
            r = self._run_one(lambda bun, url: calls.append(url) or {})
        self.assertEqual(calls, [], "额度写不进去，请求还是发出去了")
        self.assertEqual(r["stopped"], "BUDGET_STALE")

    def test_a_block_that_appears_mid_write_stops_the_request(self):
        """读的时候还没有文件，不等于写的时候也没有。

        `None` 在 `atomic_write` 里是「不比对」——第一次记账正好撞上别人
        刚建了一份带冷却的文件时，整份被他那份盖掉的是**我们**这份空快照，
        冷却看着还在；反过来我们这份若带着旧记录，盖掉的就是他的。这里用
        `NO_FILE` 让那次写撞出来，再合并回去看冷却。
        """
        orig_note, fired = pb.note, {"yes": False}

        def note_then_block(data, portal, n, now, kind=""):
            orig_note(data, portal, n, now, kind)
            if not fired["yes"]:
                fired["yes"] = True
                fresh = {}
                pb.block(fresh, "liepin-search", "另一边撞了限流", now)
                pb.save("u", fresh)

        calls = []
        with mock.patch.object(pb, "note", note_then_block):
            r = self._run_one(lambda bun, url: calls.append(url) or {})
        self.assertEqual(calls, [], "合并后已经看见冷却，还是把请求发了出去")
        self.assertEqual(r["stopped"], "BLOCKED")
        self.assertIn("另一边撞了限流",
                      pb.load("u")["猎聘"]["blocks"]["cli"]["why"])


class ThrottleIsHonoured(unittest.TestCase):
    def test_sleeps_between_requests_but_not_before_the_first(self):
        slept = []
        urls = [{"url": f"https://x/{i}", "title": ""} for i in range(3)]
        good = {"url": "https://x/0", "title": "", "description": "正文" * 60}
        orig = fd.st.save
        fd.st.save = lambda user, d: None
        self.addCleanup(lambda: setattr(fd.st, "save", orig))
        # **必须传 budget={}**：不传就去读真实额度文件，而猎聘正在风控冷却里
        # （`remaining_today` 返回 0）→ 一条都不发 → 这条测试红，
        # 而它验的是节流、跟额度无关。2026-08-20 撞到过：闸门在正确工作，
        # 是测试没隔离环境。同文件其它用例早就传了，只有这条漏了。
        fd.run("张三", urls, apply=True,
               fetch=lambda b, u: dict(good, url=u), sleep=slept.append, budget={})
        self.assertEqual(len(slept), 2, "3 个请求之间该睡 2 次")
        self.assertTrue(all(s >= 1.5 for s in slept), f"间隔太短：{slept}")

    def test_interval_is_at_least_the_cli_builtin(self):
        """跨进程调用时 CLI 内置的 1.5 秒节流不生效，这里必须自己不低于它。"""
        self.assertGreaterEqual(fd.INTERVAL_S, 1.5)


class OnlyLiepinUrlsAreInScope(unittest.TestCase):
    def _repo(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "users" / "张三" / "job_scraper").mkdir(parents=True)
        (tmp / "users" / "张三" / "job_scraper" / "seen_jobs.json").write_text(
            json.dumps({"seen": {
                "a": {"url": "https://www.liepin.com/job/1.shtml", "title": "甲",
                      "status": "new", "portal": "liepin-search"},
                "b": {"url": "https://www.zhipin.com/job_detail/x.html", "title": "乙",
                      "status": "new", "portal": "boss-cdp"},
                "c": {"url": "https://www.liepin.com/job/2.shtml", "title": "丙",
                      "status": "ranked", "portal": "liepin-search"},
                # 判过、但判据没经过 JD 正文复核的两类：字段判的硬门 / 预筛淘汰
                "d": {"url": "https://www.liepin.com/job/3.shtml", "title": "丁",
                      "status": "ranked", "portal": "liepin-search",
                      "rank_verdict": "硬门 FAIL (学历院校)",
                      "rank_breakdown": {"证据": "⚠ 依据来自列表页字段，未经 JD 正文复核"}},
                "e": {"url": "https://www.liepin.com/job/4.shtml", "title": "戊",
                      "status": "ranked", "portal": "liepin-search",
                      "rank_verdict": "粗筛：跳过",
                      "rank_breakdown": {"来源": "预筛（未抓 JD）"}},
            }}, ensure_ascii=False), encoding="utf-8")
        saved_fd, saved_st = fd.ROOT, fd.st.ROOT
        fd.ROOT, fd.st.ROOT = tmp, tmp
        self.addCleanup(lambda: (setattr(fd, "ROOT", saved_fd),
                                 setattr(fd.st, "ROOT", saved_st)))

    def test_other_portals_are_not_collected(self):
        """BOSS/智联/前程的详情页抓不到，交给浏览器渠道，不该混进来白撞风控。"""
        self._repo()
        got = fd.missing_urls("张三")
        self.assertEqual([e["title"] for e in got], ["甲"],
                         "默认只该收待评的猎聘职位")

    def test_recheck_includes_unreviewed_verdicts(self):
        """复核回路：框架规定「抓到 JD 后必须复核」，但只抓 status=new 的话，
        判过的条目永远不会被抓 JD——规则写了、管道没接上。上一轮 8 个错判的
        硬门 FAIL 正是从这条缝里漏出来的。"""
        self._repo()
        got = {e["title"] for e in fd.missing_urls("张三", recheck=True)}
        self.assertEqual(got, {"甲", "丁", "戊"},
                         "recheck 要把字段判的硬门与预筛淘汰一并收进来")
        # 已按正文复核过的（证据不含「未经」）不收——别重复抓
        self.assertNotIn("丙", got)

    def test_a_job_marked_skipped_on_the_panel_is_not_fetched(self):
        """他在总览页点了「不投」，补 JD 就不该再花额度抓它。

        决定只写进 `user_state.json`，库里那条仍然是 `ranked` —— 这里原来读的
        是裸 `status`，于是 `--recheck` 照抓不误。猎聘每次请求之间要隔几秒、撞限流
        整站冷却，额度花在他否掉的岗上就是没花在还等着补 JD 的岗上。
        """
        self._repo()
        import _cli
        sj = fd.ROOT / "users" / "张三" / "job_scraper" / "seen_jobs.json"
        self.assertIn("丁", {e["title"] for e in fd.missing_urls("张三", recheck=True)},
                      "先确认没标之前它是会被抓的 —— 否则下面那条断言恒真")
        _cli.set_user_decision(sj, "d", "skipped", reason="不想投", date="2026-08-25")
        got = {e["title"] for e in fd.missing_urls("张三", recheck=True)}
        self.assertNotIn("丁", got, "标了不投还在抓 —— 额度白烧")
        self.assertIn("甲", got, "别把没标的一起排除了")

    def test_the_backlog_count_drops_the_ones_he_dropped(self):
        """「还缺 JD 的活岗」这个数也要减掉他标过的。"""
        self._repo()
        import _cli
        sj = fd.ROOT / "users" / "张三" / "job_scraper" / "seen_jobs.json"
        before = sum(fd.missing_by_portal("张三").values())
        _cli.set_user_decision(sj, "d", "skipped", reason="不想投", date="2026-08-25")
        after = sum(fd.missing_by_portal("张三").values())
        self.assertEqual(after, before - 1,
                         f"标了不投，缺 JD 的活岗数没跟着减（{before}→{after}）")

    def test_deprioritized_jobs_queue_last(self):
        """降权的岗必须排在队尾——限流额度先花给没被降权的。

        这条规则原来只有一个自证式守卫（test_prescreen_guards 里自建 list、
        自己 sort、断言自己），对产品的唯一接触是 hasattr。实测把
        fetch_details 的排序键改反（降权反而排队首、优先烧限流额度），
        全套测试照绿。这里对 `missing_urls` 的返回**顺序**做真断言。
        """
        self._repo()
        import json as _json
        p = fd.ROOT / "users" / "张三" / "job_scraper" / "seen_jobs.json"
        store = _json.loads(p.read_text(encoding="utf-8"))
        # 再加两个待评的猎聘岗：排在前面的那个带降权标记
        store["seen"]["f"] = {"url": "https://www.liepin.com/job/9.shtml",
                              "title": "降权岗", "status": "new",
                              "portal": "liepin-search",
                              "deprioritized": {"依据": "标题方向不对"}}
        store["seen"]["g"] = {"url": "https://www.liepin.com/job/8.shtml",
                              "title": "正常岗", "status": "new",
                              "portal": "liepin-search"}
        p.write_text(_json.dumps(store, ensure_ascii=False), encoding="utf-8")
        titles = [e["title"] for e in fd.missing_urls("张三")]
        self.assertIn("降权岗", titles)
        self.assertEqual(titles[-1], "降权岗",
                         f"降权的岗没有排到队尾：{titles} —— "
                         "抓 JD 的限流额度会先烧在它身上")
        self.assertLess(titles.index("正常岗"), titles.index("降权岗"))


class RecheckSeesEveryUnverifiedFamily(unittest.TestCase):
    """「未抓 JD」按包含匹配——精确匹配漏过 32 条「粗筛（未抓 JD）」。

    `来源` 是自由文本（库里实测过 15 种写法），判它只能按语义片段。
    精确匹配整串的失败形状这个仓库已经付过两次学费：「读过」vs「读了」
    一字之差漏 613 条；这次是「预筛」vs「粗筛」漏 32 条。
    """

    def test_both_families_are_seen(self):
        for src in ("预筛（未抓 JD）", "粗筛（未抓 JD）", "预筛（未抓 JD，按薪资）"):
            with self.subTest(src=src):
                self.assertTrue(fd.needs_recheck({"rank_breakdown": {"来源": src}}))

    def test_evidence_sentinel_is_seen(self):
        self.assertTrue(fd.needs_recheck(
            {"rank_breakdown": {"证据": "未经 JD 正文复核——标题两可"}}))

    def test_verified_entries_are_not_dragged_back(self):
        for src in ("粗筛（读过 JD 正文）", "深评（读过 JD 正文）"):
            with self.subTest(src=src):
                self.assertFalse(fd.needs_recheck({"rank_breakdown": {"来源": src}}))


if __name__ == "__main__":
    unittest.main()


class TheBatchSizeComesFromTheDocumentedTable(unittest.TestCase):
    """不给 `--limit` 时抓几个，要等于文档里为这条通道定的批大小。

    2026-09-02 实测：`--limit` **没有默认值** —— `main()` 里是
    `if args.limit: entries = entries[:limit]`，不给就是**一个不落全抓**。

    而这个工具只打猎聘 CLI 那一条通道，它恰好是会限流、且封了要用户
    **换网络出口 IP** 才解得开的那条（`portal_budget` 里那段实测：
    到点换的还是同一个 IP，探一次限一次）。

    被推荐的形态更要命：`audit_pipeline` 与 `applied_jds` 两处印给用户的都是
    `python tools/fetch_details.py --recheck --apply` —— **带 `--apply`、不带上限**。
    而同一个仓库的 `job-rank.md` 那张「通道决定批大小」表明写着：
    猎聘 CLI 的 detail「每批 **12**，撞到就停」。
    **印出来的命令和写下来的规矩对不上，而印出来的那条才是真会被敲的。**

    所以判据不是「等于 12」，是「等于那张表里写的那个数」—— 表改了，
    默认值要跟着改，而不是各走各的。
    """

    def _documented(self) -> int:
        t = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        i = t.index("### 通道决定批大小")
        seg = t[i:t.index("\n---", i)]
        m = re.search(r"猎聘 CLI[^|]*\|[^|]*\|\s*(\d+)", seg)
        self.assertIsNotNone(m, "job-rank.md 那张表里找不到猎聘 CLI 那一行的批大小")
        return int(m.group(1))

    def test_the_table_still_states_it(self):
        """控制用例：那张表还在，否则下面那条对着空气跑。"""
        self.assertGreater(self._documented(), 0)

    def test_the_default_matches_the_table(self):
        self.assertEqual(
            fd.DEFAULT_LIMIT, self._documented(),
            "`--limit` 的默认值和 `job-rank.md`「通道决定批大小」那张表对不上")

    def test_there_is_a_default_at_all(self):
        """**不给 `--limit` 不能等于「全抓」。**

        两处工具印的推荐命令都不带 `--limit`，所以这个默认值就是它们的实际上限。
        """
        p = fd.build_parser() if hasattr(fd, "build_parser") else None
        if p is None:
            src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
            self.assertIn("default=DEFAULT_LIMIT", src,
                          "`--limit` 又变成没有默认值了 —— 不给就会一个不落全抓")
            return
        ns = p.parse_args([])
        self.assertEqual(ns.limit, fd.DEFAULT_LIMIT)
