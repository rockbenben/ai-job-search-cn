# -*- coding: utf-8 -*-
"""谈薪那三个数里「当前」填不出来 —— 而这个洞只给应届生补了。

`/job-offer` Step 1 那张表：底线 / 期望 / 当前。「当前」是涨幅的分母，也是背调
核薪的那个数。表里原来标着「**应届生这一格是空的**」，分流也按身份判：
「写着在读 / 应届 / 在校的，上面那张表用不了」。

**判据错了：填不出这一格的远不止应届生。** 实测活动用户 2026-08-24 ——
他的资料那一行写着「**不报**：自有公司经营所得，非固定月薪」，而求职状态是
「**离职，正在找工作**」。按身份判的那条分流一条都接不住他，Step 1 会拿「不报」
当分母去算涨幅百分比。

国内这几种都不少见：自有公司 / 个体经营 / 承包、自由职业或多来源、长期空窗、
有数但不愿报。

## 补的不是同一段内容

应届那一节讲的是**校招档位制**（签字费、职级、落户，base 谈不动）。社招但没有
当前数的人面对的是另外三件事：

1. **涨幅不算** —— 没有分母就不给百分比，编一个分母等于把后面每条建议都建在假数上。
2. **锚点换成市场价，而这个市场价他手上真有。** Step 1 末尾写着「行情数字你既拿不出
   来源，对方也不会认」—— 那对**网上听来的**成立，对**他自己抓的库**不成立：
   实测同一天，库里 2638 个岗有 2607 个明写薪资，可投三档的 428 个里 423 个有。
   （报区间时要说一句「其中只有 244 个带薪数字段，其余按 12 薪保守折」——
   不说的话那个区间被低估了自己都不知道。）
3. **背调那一关反而要多说一句** —— 国内第三方背调核的是个税与社保记录，
   工资薪金以外的收入结构在那套记录里是另一类；查不到不等于查出问题，
   而**编一个月薪**才是真的红线，因为它在个税记录里对不上。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OFF = (ROOT / "workflows" / "job-offer.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = OFF.index("### 「当前」这一格给不出数字时")
    return OFF[i:OFF.index("### 应届生：", i)]


class TheTriggerIsTheFieldNotTheIdentity(unittest.TestCase):
    def test_the_section_exists(self):
        self.assertIn("### 「当前」这一格给不出数字时", OFF)

    def test_it_says_the_criterion_out_loud(self):
        self.assertRegex(flat(seg()),
                         r"\*\*判据是那一格填不出一个数，不是身份。\*\*")

    def test_the_table_row_points_at_it(self):
        """表是读者第一眼看到的东西 —— 分流写得再好，表里不提也走不到。"""
        i = OFF.index("涨幅的分母")
        row = OFF[i:i + 260]
        self.assertIn("这一格常常给不出一个数", row)
        self.assertIn("判据是填不出数，不是身份", row)

    def test_it_enumerates_the_shapes(self):
        s = flat(seg())
        for shape in ("自有公司", "自由职业", "长期空窗", "不愿报"):
            with self.subTest(shape=shape):
                self.assertIn(shape, s, f"「{shape}」这一种没列出来")

    def test_it_records_the_case_that_exposed_it(self):
        """不写这个例子，下一个人会觉得按身份判也够用。"""
        s = flat(seg())
        self.assertRegex(s, r"给不出当前月薪数字的远不止应届生")
        self.assertRegex(s, r"拿非标准文本当分母去算涨幅")

    def test_fresh_grads_still_go_to_their_own_section(self):
        """校招那一节讲的是档位制，和这几种不是一回事，别合并。"""
        self.assertRegex(flat(seg()), r"除了第一种（走校招那一节）")
        self.assertIn("### 应届生：上面那三个数里有一个不存在", OFF)


class TheThreeThingsToDoInstead(unittest.TestCase):
    def test_no_growth_percentage_without_a_denominator(self):
        s = flat(seg())
        self.assertRegex(s, r"\*\*涨幅不算。\*\*")
        self.assertRegex(s, r"编一个分母出来，等于把后面每一条建议\s*都建在一个假数上"
                            r"|编一个分母出来，等于把后面每一条建议都建在一个假数上")

    def test_the_anchor_moves_to_his_own_library(self):
        """这条推翻了 Step 1 末尾那句「行情你拿不出来源」—— 要明写推翻的是哪半句。"""
        s = flat(seg())
        self.assertRegex(s, r"行情数字你既\s*拿不出来源|行情数字你既拿不出来源")
        self.assertRegex(s, r"对\*\*网上听来的\*\*行情成立，对\*\*你自己抓的库\*\*不成立")

    def test_the_library_numbers_are_there(self):
        s = flat(seg())
        self.assertRegex(s, r"流水线抓取的职位库绝大部分都明写了薪资区间|明写了薪资")

    def test_it_warns_that_the_range_is_conservative(self):
        """不说这句，报出来的区间被 12 薪折低了自己都不知道。"""
        s = flat(seg())
        self.assertRegex(s, r"按 12 薪保守折")
        self.assertRegex(s, r"报区间的时候要说这一句")

    def test_the_background_check_half_is_specific(self):
        s = flat(seg())
        self.assertRegex(s, r"核的是\*\*个税与社保记录\*\*")
        self.assertRegex(s, r"查不到「工资薪金」不等于查出问题")

    def test_making_up_a_number_is_named_as_the_real_risk(self):
        """「说结构不给数字」听起来只是含糊 —— 要说清另一条路更危险。"""
        s = flat(seg())
        self.assertRegex(s, r"\*\*说结构、不给数字\*\*")
        self.assertRegex(s, r"编的那个数在个税记录里对不上，那才是真的红线")

    def test_it_defers_to_what_he_already_wrote(self):
        self.assertRegex(flat(seg()), r"\*\*照他写的答\*\*，别另起一套")


class TheCampusSectionIsIntact(unittest.TestCase):
    def _grad(self) -> str:
        i = OFF.index("### 应届生：上面那三个数里有一个不存在")
        return OFF[i:OFF.index("\n### ", i + 4)]

    def test_it_still_reads_the_status_field(self):
        self.assertIn("求职状态", self._grad())

    def test_the_levers_survive(self):
        for lever in ("签字费", "职级", "落户"):
            with self.subTest(lever=lever):
                self.assertIn(lever, self._grad())

    def test_the_tripartite_penalty_survives(self):
        self.assertIn("三方协议的违约金", self._grad())


class TheRestOfStepOneIsIntact(unittest.TestCase):
    def test_the_three_prices_survive(self):
        for w in ("开口价", "可守价", "走人价"):
            with self.subTest(w=w):
                self.assertIn(w, OFF)

    def test_the_walk_away_line_is_still_the_users_own_number(self):
        self.assertRegex(flat(OFF), r"`profile` 里那个数是他清醒时定的")

    def test_the_annual_package_unit_rule_survives(self):
        self.assertRegex(flat(OFF), r"月薪 × 薪数，别拿月薪比年包")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：那个「手上真有的行情」确实还在。"""

    def test_the_library_still_carries_salaries(self):
        import json
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("没有职位库")
        seen = _cli.seen_of(json.loads(f.read_text(encoding="utf-8")))
        if len(seen) < 500:
            self.skipTest("语料太小")
        withsal = sum(1 for v in seen.values()
                      if (v.get("salary") or "").strip()
                      and "面议" not in (v.get("salary") or ""))
        self.assertGreater(
            withsal, len(seen) * 0.8,
            f"{withsal}/{len(seen)} 个岗写了薪资 —— 「行情你手上真有」这条要重量")


if __name__ == "__main__":
    unittest.main()
