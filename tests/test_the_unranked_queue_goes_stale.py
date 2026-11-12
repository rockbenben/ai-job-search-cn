# -*- coding: utf-8 -*-
"""「还有 182 个没评」印了两处，两处都只有一个数 —— 而这批是会烂的。

抓的时候只收**最近 14 天**内的岗（`job-scrape.md` Step 1b 第 3 条），而**评一个岗
要花抓详情的额度** —— 这套系统里最稀缺的东西（撞过限流、封过 9 小时、一天发过
926 次请求）。一个已经在平台上关掉的岗，评它就是把那份额度烧掉，还得回头把它标成
`expired`。

实测活动用户 2026-08-24：182 个待评的**中位放了 7 天、最久 26 天**，
其中 11 个已经超过 14 天 —— 比抓它时的标准还旧。

`archive.py` 帮不上：它明写「不碰待评/可投/已投/有材料的」。**没评过的岗永远不会
自己老去**，只会在队列里堆着。所以只能在报数的地方把年龄一起说了。

## 只在真放旧了才说

正常情况下抓完就自动评了（`AGENTS.md`：「抓完直接排出可以投的，不停在待评」），
这一段本该是空的。没有超过 14 天的就一个字都不印 —— 一句永远都在的提醒等于没有。

## 年龄不并进那一行

第一版把它并进了「已抓 N · 已评 M（还有 K 个没评，跑 /job-rank）」，
结果「跑 /job-rank」被挤到一长串从句后面 —— 而那五个字才是那一行的用处。
拆成单独一行，`WARN` 级。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import doctor  # noqa: E402

DOC = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
TYPES = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
EXPORT = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*[>#]:?\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seen_of(*days):
    """`days` 是每个待评岗「抓回来放了几天」。"""
    import datetime as dt
    today = dt.date(2026, 8, 24)
    out = {}
    for i, d in enumerate(days):
        out[f"u{i}"] = {"status": "new", "rank_score": None,
                        "first_seen": (today - dt.timedelta(days=d)).isoformat()}
    return out


class TheAgeIsComputed(unittest.TestCase):
    def test_it_reports_median_oldest_and_stale(self):
        a = doctor.waiting_age(seen_of(1, 3, 20, 30), today=__import__(
            "datetime").date(2026, 8, 24))
        self.assertEqual(a["n"], 4)
        self.assertEqual(a["oldest"], 30)
        self.assertEqual(a["stale"], 2, "超过 14 天的没数对")

    def test_only_unranked_ones_count(self):
        """**两个条件都要**：`status == new` 且 `rank_score is None`。

        判据同 `n_waiting`。第二个条件挡的是「已经落了分、状态还没翻」那一刻的
        中间态 —— 变异实测：只留第一个条件时，拿 `status: ranked` 当反例是测不
        出来的（它被第一个条件挡掉了），要拿 `status: new` + 有分的那种。
        """
        import datetime as dt
        s = seen_of(20)
        s["scored"] = {"status": "new", "rank_score": 70,
                       "first_seen": "2026-07-01"}
        s["done"] = {"status": "ranked", "rank_score": 70,
                     "first_seen": "2026-07-01"}
        self.assertEqual(
            doctor.waiting_age(s, today=dt.date(2026, 8, 24))["n"], 1,
            "把已经落了分的也算进待评了")

    def test_a_missing_date_is_skipped_not_guessed(self):
        import datetime as dt
        s = {"a": {"status": "new", "rank_score": None, "first_seen": ""},
             "b": {"status": "new", "rank_score": None,
                   "first_seen": "2026-08-20"}}
        a = doctor.waiting_age(s, today=dt.date(2026, 8, 24))
        self.assertEqual(a["n"], 1, "没日期的被猜了一个年龄")

    def test_an_empty_queue_says_nothing(self):
        a = doctor.waiting_age({})
        self.assertEqual((a["n"], a["median"], a["stale"]), (0, None, 0))
        self.assertEqual(doctor.waiting_note({}), "")

    def test_the_freshness_line_matches_the_scraper(self):
        """14 这个数在两处出现 —— 别各定一个。"""
        self.assertEqual(doctor.WAITING_FRESH_DAYS, 14)
        self.assertIn("最近 14 天", (ROOT / "workflows"
                                  / "job-scrape.md").read_text(encoding="utf-8"))


class TheNoteOnlyAppearsWhenSomethingIsStale(unittest.TestCase):
    def test_a_fresh_queue_gets_no_warning_line(self):
        """一句永远都在的提醒等于没有。"""
        import datetime as dt
        s = seen_of(1, 2, 3)
        self.assertEqual(doctor.waiting_age(s, today=dt.date(2026, 8, 24))["stale"], 0)

    def test_doctor_gates_the_line_on_stale(self):
        i = DOC.index('st["waiting_stale"]')
        self.assertIn('if st.get("waiting_stale"):', DOC,
                      "那一行不管新旧都印 —— 正常状态下也会挂个警告")
        del i

    def test_the_exporter_gates_it_too(self):
        i = EXPORT.index("_wait_note = (")
        seg = EXPORT[i - 400:i + 400]
        self.assertIn('["stale"]', seg, "导出不看有没有旧的就给字段")

    def test_the_panel_renders_it_conditionally(self):
        self.assertIn("{st.waitingNote && (", APP)

    def test_the_type_says_it_is_optional(self):
        self.assertIn("waitingNote?: string;", TYPES)
        i = TYPES.index("waitingNote?: string;")
        self.assertIn("只有出现了超过 14 天的才给", flat(TYPES[i - 300:i]))


class TheNoteSaysWhyItMatters(unittest.TestCase):
    def test_it_names_the_scrape_window(self):
        import datetime as dt
        note = doctor.waiting_note(seen_of(1, 30), today=dt.date(2026, 8, 24))
        self.assertIn("14 天", note)
        self.assertIn("抓的时候只收", note)

    def test_it_says_some_are_already_closed(self):
        import datetime as dt
        note = doctor.waiting_note(seen_of(30), today=dt.date(2026, 8, 24))
        self.assertIn("在平台上已经关了", note)

    def test_it_carries_median_and_oldest(self):
        import datetime as dt
        note = doctor.waiting_note(seen_of(2, 30), today=dt.date(2026, 8, 24))
        self.assertRegex(note, r"中位 \d+ 天")
        self.assertRegex(note, r"最久 30 天")


class TheReasonIsRecorded(unittest.TestCase):
    def _seg(self) -> str:
        i = DOC.index("def waiting_age(")
        return flat(DOC[i:DOC.index("def waiting_note(", i)])

    def test_it_names_the_scarce_resource(self):
        seg = self._seg()
        self.assertRegex(seg, r"评它要花\*\*抓详情的额度\*\*")

    def test_it_says_archive_cannot_help(self):
        """不写这句，下一个人会去改 archive 而不是改报数。"""
        seg = self._seg()
        self.assertRegex(seg, r"`archive.py` 帮不上")
        self.assertRegex(seg, r"没评过的岗永远不会自己老去")

    def test_it_carries_the_measurement(self):
        seg = self._seg()
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"中位放了 7 天、最久 26 天")

    def test_the_layout_decision_is_recorded(self):
        """并进那一行会把「跑 /job-rank」挤到从句后面 —— 记下来别改回去。"""
        i = DOC.index('if st.get("waiting_stale"):')
        seg = flat(DOC[i - 900:i])
        self.assertRegex(seg, r"不并进上面那行")
        self.assertRegex(seg, r"而那五个字才是这一行的用处")


class TheRankingWorkflowKnowsToPreferFreshOnes(unittest.TestCase):
    def _seg(self) -> str:
        # 锚点往前挪两个字符 —— 起点正好切在 `**` 中间，断言里那对星号就永远
        # 匹配不上（第一版当场红了一次）。
        i = RANK.index("队列里的岗是会烂的") - 2
        return flat(RANK[i:i + 1200])

    def test_the_rule_is_there(self):
        self.assertRegex(self._seg(), r"\*\*队列里的岗是会烂的，先评新的。\*\*")

    def test_it_says_what_ranking_costs(self):
        self.assertRegex(self._seg(), r"评一个岗要花抓详情的额度")

    def test_it_says_last_not_discarded(self):
        """丢掉是错的 —— 它可能还活着，只是希望小。"""
        seg = self._seg()
        self.assertRegex(seg, r"\*\*排到最后\*\*（不是丢掉")

    def test_it_carries_the_measurement(self):
        seg = self._seg()
        self.assertRegex(seg, r"超过 14 天|没评过的岗")

    def test_the_batch_size_rule_survives(self):
        """批大小按通道取，不是一个写死的数 —— 这条原来钉的是「批大小仍是 12」，
        而同一份文件「通道决定批大小」那节 2026-09-02 起就按表取了：
        一条测试钉住了文件里那句过期的话，让它改不掉。2026-09-04 通读时一并改。"""
        self.assertIn("批大小按通道算", RANK)
        self.assertNotIn("批大小仍是 12", RANK, "那句写死 12 的话又回来了")

    def test_the_drain_to_empty_rule_survives(self):
        """「先评新的」不是「只评新的」—— 队列还是要排空。"""
        self.assertIn("分批循环，直到队列排空", RANK)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    def test_the_real_queue_still_has_old_ones(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        import _cli
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("没有职位库")
        seen = _cli.seen_of(json.loads(f.read_text(encoding="utf-8")))
        a = doctor.waiting_age(seen)
        if not a["n"]:
            self.skipTest("队列已经排空了 —— 那这条提醒这轮没话说，正常")
        self.assertIsNotNone(a["median"])
        self.assertGreaterEqual(a["oldest"], a["median"])


if __name__ == "__main__":
    unittest.main()
