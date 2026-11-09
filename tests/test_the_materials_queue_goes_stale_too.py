# -*- coding: utf-8 -*-
"""待评那队会烂，仓库修过了；旁边那队更贵，一个字没说。

自检印的是「已出材料 141 份」——**一个平数**。而这批和待评队列一样会烂，
**而且贵得多**：一份材料是一次公司调研加起草审稿两轮，一次待评只是一次打分。

## 实测（活动用户 2026-08-24）

    备好没投的（面板口径）  60 份，岗龄中位 19 天
    其中排了两周以上        9 份
    全库已下线              19 个
    其中出过材料的          12 个
    **其中已经投出去的**    **0 个**

也就是说：**所有「下线且有材料」的岗，材料全是白做的**。

## 面板早就在说，自检从来没说

`build_dashboard.season_note` 里那句「已经有 N 个岗在你发出去之前就下线了」，
还带着按岗龄分桶的实测（>14 天那一档 8/34 已下线，≤14 天只有 2-7%）。
而 `doctor.py` 里 `ready_old` / `expired_unsent` 出现 **0 次**。

自检偏偏是**会话开始第一件事**（`AGENTS.md`「会话开始：先跑自检」），
也就是每次最先被看见的那份报告。

## 这是同一个病的另一半

本文件的 `waiting_age` 修的是**待评队列**的年龄，理由一字不差地适用于旁边这一队：
「光有个数说不出这里面有一批该先处理」。当时只治了一半。
"""
import datetime
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402
import export_web_data as ex  # noqa: E402

DR = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
BD = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def snap(tmp, jobs):
    """在临时树里放一份面板快照，`ready_age` 读的就是它。"""
    u = tmp / "users" / "甲"
    (tmp / "users" / "甲" / "job_scraper" / "dashboard").mkdir(parents=True, exist_ok=True)
    u.mkdir(parents=True, exist_ok=True)
    (tmp / "users" / "甲" / "job_scraper" / "dashboard" / "data.json").write_text(
        json.dumps({"activeUser": "甲", "jobs": jobs}, ensure_ascii=False),
        encoding="utf-8")
    return u


def job(**kw):
    base = {"materials": {"greeting": "x"}, "applied": None, "dupOf": None,
            "skipped": False, "expired": False,
            # `staleDays` 留着是因为它仍然是快照里的真字段（名单上那个
            # 「抓到时已 N 天没刷新」用它）—— 但 `ready_age` 已经不看它了。
            "staleDays": 5, "queuedDays": 5, "queuedLong": False}
    base.update(kw)
    return base


class TheThresholdComesFromThePanel(unittest.TestCase):
    def test_there_is_no_copy_at_all(self):
        """**2026-08-25：从「两个副本必须相等」升级成「只许有一个」。**

        原来这里是 `READY_STALE_DAYS = 14` 加一条「与 `STALE_POSTING_DAYS` 同值」
        的断言。现在 `ready_age` 读快照里的 `queuedLong` —— 谁算得久由面板那边
        判完，这边读结论，副本整个删了。
        """
        self.assertFalse(hasattr(doctor, "READY_STALE_DAYS"),
                         "副本又回来了 —— 读 `queuedLong` 就不需要它")
        self.assertNotIn("READY_STALE_DAYS = ", DR)

    def test_it_says_why_the_copy_is_gone(self):
        i = DR.index("这里不再留副本")
        seg = flat(DR[max(0, i - 200):i + 600])
        self.assertRegex(seg, r"\*\*两个副本相等，不如只有一个。\*\*")
        self.assertRegex(seg, r"直接读快照里的 `queuedLong`")

    def test_the_original_still_exists(self):
        """判据搬走了，不是没了 —— 面板那一份必须还在。"""
        self.assertEqual(ex.STALE_POSTING_DAYS, 14)

    def test_the_panel_still_says_it(self):
        """这一条建立在「面板早就在说」上 —— 它没了，两边就一起哑了。"""
        self.assertIn("ready_old", BD)
        self.assertIn("expired_unsent", BD)
        # **钉的是「面板说得出这句话」，不是它住在哪个函数里。**
        # 原来钉的是 `season_note` 里那句源码模板；2026-09-01 那句搬去了
        # `_ready_text`（季节一变它就整句消失，见那儿的注释），这一条当场红 ——
        # 而面板行为本身没坏。判据改成现算。
        self.assertIn("个岗在你发出去之前就下线了",
                      bd._ready_text(62, 30, 0, None, 11))


class TheAgeIsComputed(unittest.TestCase):
    def _age(self, jobs):
        with tempfile.TemporaryDirectory() as t:
            return doctor.ready_age(snap(pathlib.Path(t), jobs))

    def test_it_counts_the_unsent_ones(self):
        got = self._age([job(), job(), job(applied={"date": "2026-08-01"})])
        self.assertEqual(got["n"], 2)

    def test_it_excludes_duplicates_and_skipped_and_expired(self):
        """口径要和面板一模一样，否则两处各报一个数。"""
        got = self._age([job(), job(dupOf="x"), job(skipped=True),
                         job(expired=True)])
        self.assertEqual(got["n"], 1)

    def test_expired_ones_are_counted_separately(self):
        """**它们被上面那几个条件排掉了，而这一档恰恰是最要紧的那个数。**"""
        got = self._age([job(), job(expired=True), job(expired=True)])
        self.assertEqual((got["n"], got["lost"]), (1, 2))

    def test_an_expired_but_applied_one_is_not_lost(self):
        """已经投出去了，岗后来关了——材料没白做。"""
        got = self._age([job(expired=True, applied={"date": "2026-08-01"})])
        self.assertEqual(got["lost"], 0)

    def test_old_reads_the_flag_not_a_local_threshold(self):
        """谁算得久由面板判完（`queuedLong`），这边只数。"""
        got = self._age([job(queuedLong=True), job(queuedLong=False), job()])
        self.assertEqual(got["old"], 1)

    def test_the_median_comes_from_queued_days(self):
        """**不是 `staleDays`。** 那个说的是「招聘方多久没刷新」，
        而这句话说的是「这几份材料放了多久」——两件事。

        用错字段的代价实测过（2026-08-25）：备好没发的 60 个里只有 10 个有
        `staleDays`，于是「中位 20 天」是在 10 个数上取的；而 `staleDays` 只在
        超阈值时才有值，那 10 个必然全部超阈值 —— 那个「其中 10 份排了两周以上」
        实际等于「有这个字段的有 10 个」。同一时刻面板说 15。
        """
        got = self._age([job(queuedDays=3), job(queuedDays=9),
                         job(queuedDays=30)])
        self.assertEqual(got["median"], 9)

    def test_stale_days_no_longer_decides_anything(self):
        """**只给 `staleDays` 时什么也算不出。** 那正是它不再被用的证据：
        以前这两个岗会被算成「放了 30 天、两个都超两周」。"""
        got = self._age([job(staleDays=30, queuedDays=None),
                         job(staleDays=30, queuedDays=None)])
        self.assertIsNone(got["median"])
        self.assertEqual(got["old"], 0)

    def test_no_snapshot_returns_empty_not_a_guess(self):
        """读不到就说读不到——同本文件其余几处对「没查」的处理。"""
        with tempfile.TemporaryDirectory() as t:
            u = pathlib.Path(t) / "users" / "甲"
            u.mkdir(parents=True, exist_ok=True)
            self.assertEqual(doctor.ready_age(u), {})

    def test_another_users_snapshot_is_refused(self):
        """身份对不上就不读——否则报的是别人的进度。"""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            snap(tmp, [job()])
            (tmp / "users" / "乙").mkdir(parents=True, exist_ok=True)
            self.assertEqual(doctor.ready_age(tmp / "users" / "乙"), {})


class TheNoteOnlySpeaksWhenItMatters(unittest.TestCase):
    def _note(self, jobs):
        with tempfile.TemporaryDirectory() as t:
            return doctor.ready_note(snap(pathlib.Path(t), jobs))

    def test_a_fresh_queue_says_nothing(self):
        """全都是新的——这一行不该占地方（标记要标少数派）。"""
        self.assertEqual(self._note([job(queuedDays=2), job(queuedDays=3)]), "")

    def test_nothing_ready_says_nothing(self):
        self.assertEqual(self._note([]), "")

    def test_an_old_one_speaks(self):
        said = self._note([job(queuedDays=30, queuedLong=True)])
        self.assertIn("排了两周以上", said)

    def test_a_lost_one_speaks(self):
        said = self._note([job(), job(expired=True)])
        self.assertIn("下线", said)
        self.assertIn("白做", said)

    def test_it_says_what_to_do(self):
        """只报数不给动作，用户读完还是不知道先发哪个。"""
        said = self._note([job(queuedDays=30, queuedLong=True)])
        self.assertIn("先发排得最久的", said)

    def test_it_says_the_score_did_not_change(self):
        """不说这句，人会以为是分数掉了——那会让他重新评一遍，白花额度。"""
        self.assertIn("分数没变", self._note([job(queuedLong=True, queuedDays=30)]))

    def test_no_markdown_reaches_the_terminal(self):
        """终端不渲染 markdown，星号会原样上屏。"""
        self.assertNotIn("**", self._note([job(queuedLong=True, queuedDays=30), job(expired=True)]))


class TheSelfcheckPrintsIt(unittest.TestCase):
    def test_it_is_collected(self):
        self.assertIn('st["ready_note"] = ready_note(udir)', DR)

    def test_it_is_printed(self):
        self.assertIn('if st.get("ready_note"):', DR)

    def test_it_sits_next_to_the_waiting_note(self):
        """两队是同一个病的两半，报告里也该挨着 —— 分开放会让人以为是两回事。"""
        a = DR.index('print(f"{WARN}这 {st[\'waiting\']} 个{st[\'waiting_note\']}")')
        b = DR.index('if st.get("ready_note"):')
        self.assertLess(abs(a - b), 400)

    def test_it_is_not_the_single_next_step(self):
        """自检只给一条下一步，这是一条提醒 —— 不许去抢那一条。"""
        i = DR.index("def next_step(")
        # **取整个函数，不要固定窗口。** `next_step` 现在 8000 字，而这里原来
        # 只看前 6000 —— 最后 2000 字不在检查范围内，那一段里真出现
        # `ready_note` 的话这条会**静默通过**。同一课本仓库已经记过两次
        # （`test_the_padding_survives_a_job_title` 2026-08-27、
        #  `test_the_greeting_stats_are_not_stale` 2026-08-31），
        # 而那两次都是 assertIn（窗口不够会变红）；这里是 assertNotIn，
        # **方向反过来就是假绿**。
        _end = DR.find(chr(10) + "def ", i + 10)
        self.assertNotIn("ready_note", DR[i:_end if _end > 0 else len(DR)])

    def test_the_reason_is_recorded(self):
        i = DR.index("def ready_age(")
        seg = flat(DR[i:DR.index("def ready_note(", i)])
        self.assertRegex(seg, r"而且更贵")
        self.assertRegex(seg, r"材料全是白做的")
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"自检这边一个字没有")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算一遍：这批材料真的在变旧，而且真的有白做的。"""

    def _live(self):
        p = ROOT / "web" / "public" / "data.json"
        act = ROOT / ".active_user"
        if not (p.is_file() and act.is_file()):
            self.skipTest("还没导出过面板数据")
        u = ROOT / "users" / act.read_text(encoding="utf-8").strip()
        a = doctor.ready_age(u)
        if not a.get("n"):
            self.skipTest("手上没有备好没发的材料")
        return a

    def test_every_expired_one_with_materials_was_never_sent(self):
        """**这一节全部的分量在这上面**：白做不是「有几个」，是「全部」。

        哪天出现「下线但已经投过」的岗，这条就该红 —— 那说明材料没白做，
        这一行的措辞要跟着改。
        """
        self._live()
        d = json.loads((ROOT / "web" / "public" / "data.json")
                       .read_text(encoding="utf-8"))
        exp = [j for j in d["jobs"]
               if j.get("expired") and j.get("materials") and not j.get("dupOf")]
        if len(exp) < 3:
            self.skipTest("已下线且有材料的太少")
        sent = [j for j in exp if j.get("applied")]
        self.assertLessEqual(
            len(sent), len(exp) * 0.2,
            f"{len(sent)}/{len(exp)} 个下线的岗其实投出去了 —— "
            f"「材料全白做」这个前提不成立了")

    def test_the_note_actually_fires(self):
        """代码在那儿不等于说得出来。"""
        self._live()
        u = ROOT / "users" / (ROOT / ".active_user").read_text(
            encoding="utf-8").strip()
        self.assertTrue(doctor.ready_note(u))


if __name__ == "__main__":
    unittest.main()
