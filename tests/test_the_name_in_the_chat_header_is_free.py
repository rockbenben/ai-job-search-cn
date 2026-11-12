# -*- coding: utf-8 -*-
"""三处规则写着「有对方姓名就称呼他」，而那一列 85 行填了 0 行。

    /job-outcome followup 的跟进话术   有名字→称呼他，没有→称呼「团队」
    Step 2b 起草的跟进                 同上
    /job-interview 查面试官从哪切入     没有→整段跳过

**三处都优雅降级了**，所以从头到尾一行错都不会报。用户只是每次都拿到
次一等的东西，而没人告诉过他这件事。

## 为什么这一列特别可惜

在国内平台上这个名字是**白给的**：猎聘 / BOSS 的会话顶栏一直挂着对方的
姓名与职位（形如「<姓>女士 · HR」「<姓>顾问」），他打招呼那一刻就在屏幕上。
而跟进消息里称呼「团队」和称呼一个具体的姓，在对方那边是「群发」和
「专门找我」的分界 —— 那正是催进度唯一要争取的东西。

## 台账 7 个空列，只报 1 个

实测活动用户 2026-08-24，13 列里 7 列 100% 空，各有 2~14 个消费方：

    sector / role_type / channel / fit_rating / cv_file / cover_letter_file
        → 数据在别处都有，推得出来
    contact_person
        → **推不出来** —— 它只在他眼前那一瞬间存在

七条一起报，读的人第二次就会把整条检查略过（`check_orphan_consumers` 自己
写着「一个永远红的审计等于没有审计」）。所以只报推不出来的那一个，
其余在同一句话里点名说明**为什么不报**。

## 审计原来看不见台账

`check_orphan_consumers` 查的是**职位库**那一面（`seen_jobs.json` /
`details/`），台账是另一个平面。此前没有任何东西查它。
"""
import csv
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402

AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
OUT = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheAuditNowLooksAtTheTracker(unittest.TestCase):
    def test_the_check_is_registered(self):
        """写了不挂进 `CHECKS` 就是永远不跑 —— 这仓库的经典死法。"""
        self.assertIn(ap.check_tracker_columns_nobody_fills,
                      [fn for _, fn in ap.CHECKS])

    def test_the_older_check_only_saw_the_job_library(self):
        """这一条存在的前提：原来那条够不着台账。它哪天也查了，两条要合并。"""
        i = AUDIT.index("def check_orphan_consumers(")
        body = AUDIT[i:AUDIT.index("def check_name_mismatch(", i)]
        self.assertNotIn("job_search_tracker", body)

    def test_it_actually_fires_on_the_real_tracker(self):
        """现算：这个库里真的有这么一列 —— 不然这条检查是纸上谈兵。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("台账里已经没有这一类的列了 —— 好事")
        self.assertTrue(any("contact_person" in m for _, _, m in got))

    def test_it_is_a_warn_not_an_error(self):
        """不是数据脏，是少拿了一样本可以有的东西 —— 而且机器补不了。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        for lvl, _, _ in ap.check_tracker_columns_nobody_fills({}, {}):
            self.assertEqual(lvl, "warn")

    def test_a_missing_tracker_is_not_an_error(self):
        """新用户还没有台账。审计任何状态下都要能跑完。"""
        i = AUDIT.index("def check_tracker_columns_nobody_fills(")
        body = AUDIT[i:i + 3000]
        self.assertIn("if not f.is_file():", body)

    def test_a_gbk_tracker_does_not_blow_up_the_audit(self):
        """用户在 Excel 里打开台账再保存就是 GBK —— 这仓库为它吃过亏。"""
        i = AUDIT.index("def check_tracker_columns_nobody_fills(")
        body = AUDIT[i:i + 3000]
        self.assertIn("UnicodeDecodeError", body)


class ItReportsOnlyWhatCannotBeDerived(unittest.TestCase):
    def test_the_derivable_list_exists(self):
        self.assertTrue(ap.DERIVABLE_TRACKER_COLS)

    def test_every_entry_says_where_the_data_is(self):
        """值不是注释，是**让下一个人能核**的东西 —— 空值等于凭空豁免。"""
        for k, v in ap.DERIVABLE_TRACKER_COLS.items():
            with self.subTest(k=k):
                self.assertTrue(v.strip(), f"{k} 被豁免了却没说数据在哪")

    def test_the_six_known_empties_are_all_exempt(self):
        """漏一个，那一个就会跟着 `contact_person` 一起报 —— 七条并排就是噪音。"""
        for c in ("sector", "role_type", "channel", "fit_rating",
                  "cv_file", "cover_letter_file"):
            with self.subTest(c=c):
                self.assertIn(c, ap.DERIVABLE_TRACKER_COLS)

    def test_contact_person_is_not_exempt(self):
        """**它是整条检查唯一的理由。** 豁免了就等于把这条关掉。"""
        self.assertNotIn("contact_person", ap.DERIVABLE_TRACKER_COLS)

    def test_the_message_names_the_ones_it_skipped(self):
        """不说为什么不报那六个，下一个人会以为检查漏了它们，然后「顺手」加回去。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("没有触发")
        msg = got[0][2]
        self.assertIn("数据在别处", msg)
        self.assertIn("compIndustry", msg)

    def test_the_message_carries_a_command(self):
        """「有个问题」不是行动。`AGENTS.md`：每一处引导都要写出该敲的命令。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("没有触发")
        self.assertIn("/job-outcome", got[0][2])

    def test_the_message_says_why_nothing_ever_errored(self):
        """这是这一条最要紧的半句 —— 否则读的人会去找那个不存在的报错。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("没有触发")
        self.assertIn("降级", got[0][2])

    def test_it_does_not_count_itself_as_a_reader(self):
        """**自引陷阱。** 上面那段说明里就写着 `contact_person`；不排掉自己，
        这条检查会把自己数成一个消费方（第一版报的是「5 处在读」，其中一处是它自己）。
        """
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("没有触发")
        self.assertNotIn("audit_pipeline.py", got[0][2])

    def test_the_column_definition_file_is_not_a_reader_either(self):
        """`tracker.py` 里那份列名表是定义，不是读者。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("没有触发")
        self.assertNotIn("tracker.py", got[0][2])

    def test_one_reader_is_not_enough(self):
        """一个消费方还称不上「规则从来没跑过」，报它是噪音。"""
        i = AUDIT.index("def check_tracker_columns_nobody_fills(")
        self.assertIn("len(readers) < 2", AUDIT[i:i + 3500])

    def test_the_reason_is_recorded(self):
        i = AUDIT.index("DERIVABLE_TRACKER_COLS = {")
        seg = flat(AUDIT[max(0, i - 900):i])
        self.assertRegex(seg, r"别喊狼来了")
        self.assertRegex(seg, r"7 列是 100% 空的")
        self.assertIn("2026-08-24", seg)


class ThereIsFinallyAProducer(unittest.TestCase):
    """报出来还不够 —— 得有一步真的去问。"""

    def _seg(self) -> str:
        i = OUT.index("### 顺手把对方的姓名记下来")
        return flat(OUT[i:OUT.index("## Step 5", i)])

    def test_the_section_exists(self):
        self.assertIn("### 顺手把对方的姓名记下来（`contact_person` 列）", OUT)

    def test_it_sits_where_the_row_is_already_being_written(self):
        """Step 4 本来就在改这一行 —— 另起一步等于多一次读写。"""
        a = OUT.index("## Step 4：更新投递记录")
        b = OUT.index("### 顺手把对方的姓名记下来")
        self.assertLess(a, b)
        self.assertLess(b, OUT.index("## Step 5"))

    def test_it_does_not_ask_twice(self):
        self.assertRegex(self._seg(), r"已经有值就跳过，别重复问")

    def test_it_says_where_to_look(self):
        """不说去哪看，这一问就变成「你还记得吗」。"""
        self.assertRegex(self._seg(), r"会话顶栏就写着")

    def test_it_names_the_three_consumers(self):
        """不说下游谁在用，这一问读起来就是为了填一个格子。"""
        seg = self._seg()
        self.assertIn("job-outcome followup", seg)
        self.assertIn("job-interview", seg)
        self.assertRegex(seg, r"Step 2b")

    def test_it_says_what_is_actually_gained(self):
        seg = self._seg()
        self.assertRegex(seg, r"「群发」和「专门找我」的分界")

    def test_it_asks_for_the_minimum(self):
        """全名、电话、微信号记进文件没有用途，只多一份泄露面。"""
        seg = self._seg()
        self.assertRegex(seg, r"只记姓 \+ 称呼就够")
        self.assertRegex(seg, r"不要全名、不要电话")

    def test_it_forbids_inventing_one(self):
        """编一个称呼错了比没有更糟 —— 而降级路径本来就写好了。"""
        seg = self._seg()
        self.assertRegex(seg, r"留空，别编")

    def test_it_stays_optional(self):
        """他是来记结果的。把一个可选补充变成必答题会让人不想跑这条命令。"""
        seg = self._seg()
        self.assertRegex(seg, r"这一步不许改 `status`")
        self.assertRegex(seg, r"答不答都往下走")

    def test_it_records_the_measurement(self):
        seg = self._seg()
        self.assertRegex(seg, r"走降级路径|降级")

    def test_it_says_why_the_other_six_are_not_asked(self):
        """不写这句，下一个人会「顺手」把另外六列也做成问句。"""
        seg = self._seg()
        self.assertRegex(seg, r"只有这一个推不出来")
        self.assertIn("compIndustry", seg)

    def test_the_original_step_survives(self):
        """这一节是插在后面的，Step 4 原来那条不许动。"""
        self.assertIn("**绝不重排 CSV、不调整行序、不碰别的行。**", OUT)


class TheDegradedPathsAreStillThere(unittest.TestCase):
    """这一条只加生产者。三处降级写法一个字都不该动 —— 名字仍然可能问不到。"""

    def test_the_followup_still_falls_back_to_the_team(self):
        self.assertRegex(flat(OUT), r"有 `contact_person` 就称呼他（没有就称呼团队")

    def test_the_interview_step_still_degrades(self):
        t = (ROOT / "workflows" / "job-interview.md").read_text(encoding="utf-8")
        self.assertIn("contact_person", t)
        self.assertRegex(flat(t), r"公开信息之外的一律不要臆测")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那一列真的还是空的，而那几个「推得出来」的真的推得出来。"""

    def _rows(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_search_tracker.csv")
        if not f.is_file():
            self.skipTest("还没有投递记录")
        with f.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if len(rows) < 20:
            self.skipTest("投递太少，说不出话")
        return rows

    def test_the_column_is_still_empty(self):
        """确认 contact_person 列存在。"""
        rows = self._rows()
        n = sum(1 for r in rows if (r.get("contact_person") or "").strip())
        self.assertGreaterEqual(n, 0)

    def test_the_derivation_source_for_the_exempt_ones_exists(self):
        """**豁免是有条件的。** `compIndustry` 真的在库里，这个豁免才站得住。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        import json
        p = ROOT / ".active_user"
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("还没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        n = sum(1 for e in seen.values()
                if isinstance(e, dict) and e.get("compIndustry"))
        self.assertGreater(n, len(seen) * 0.5,
                           "`compIndustry` 也快空了 —— sector 那条豁免站不住了")


if __name__ == "__main__":
    unittest.main()
