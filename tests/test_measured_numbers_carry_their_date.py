# -*- coding: utf-8 -*-
"""不带日期的实测数，读起来是在说「现在」—— 而它多半已经不是了。

这个仓库几乎每条规则都挂着一个实测数，那是它最好的习惯。**但数会过期，
规则不会**：语料每涨一批，所有引它的地方同时作废，而没有任何东西会红。

2026-08-23 实测过一次代价（判据见 `test_the_greeting_stats_are_not_stale`）：

    开场白       文档写 234 份      现算 236
    踩线         文档写 24 份 10%   现算 37 份 16%
    超 200 字     文档写 1 份 0.4%   现算 0 份

那个 234 被抄进了 **7 处**，三个数全飘了，同一份文档里还同时写着 234 和 236。

同一天顺着往下扫，另外几处查完都是**对的**：`158 家`（三处一致）、
`960 / 1094 个硬门 FAIL`（一个是活数、一个是带日期的推导）、
`107 / 63 个岗材料就绪但没投`（同一天的两个时点，各自算术自洽）。
**分辨它们花掉了一整轮**，而分辨的依据只有一个：那个数带没带日期。

## 这条守卫是棘轮，不是清零

存量 68 处不带日期。要求一次改完既不现实，也不该 —— 多数数是**当时那一次
观测**的产物（「那 40 份整整齐齐全缺同一节」），今天重算得不到同一批文件。

所以卡的是**增量**：这个数只许降、不许升。新写的实测数必须带日期
（或者配一条现算的守卫），旧的清一个少一个。规矩写在
`CONTRIBUTING.md`「写下一个实测数时，把日期一起写上」。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 「实测…N 个/份/条/家/次」。只认 `实测` 开头那一句，别把所有数字都算进来。
_MEASURED = re.compile(r"实测[^。\n]{0,40}?(?<![\d.])(\d{2,5})\s*(个|份|条|家|次)")
_DATE = re.compile(r"20\d\d-\d\d-\d\d")

def _para(text, at):
    """这个位置所在的**段落**。日期要在同一段里才算数。

    原来用的是「前 160 字、后 80 字」的固定窗口 —— 变异实测当场露馅：
    在一处不带日期的实测句后面 80 字内恰好有个**不相干**的 `2026-08-13`
    （下一节开头的「用户 2026-08-13 又点了一个岗」），于是那句被判成「带日期」。
    固定窗口会吃邻段，段落边界不会。

    Python 源码里没有空行分段的注释块，所以顺带把连续注释块也当一段：
    往上/往下走到第一个不以 `#` 开头、也不在同一个 docstring 里的行为止 ——
    实现上用「空行」和「两个换行」都切一刀，够用。
    """
    lo = text.rfind("\n\n", 0, at)
    lo = 0 if lo < 0 else lo + 2
    hi = text.find("\n\n", at)
    hi = len(text) if hi < 0 else hi
    return text[lo:hi]

#: 2026-08-23 数出来的存量（按段落切日期之后）。**只许降。**
#: 升了说明有人又写了一个不带日期的实测数。
#: 固定字数窗口那一版数出来是 68 —— 多的那 5 个是被邻段日期蒙混过去的。
#:
#: 59 → 55（2026-08-26）：那天扫重复定义，收掉了几处内联复刻
#: （`is_parked` 的两份内联、doctor 里写了两遍的同一段过滤），
#: 连带把它们各自带的那几个裸数字也带走了。**棘轮只许降，所以要跟着收紧** ——
#: 不收的话，下一个人再写回 4 个不带日期的实测数，这条守卫一声不吭。
#:
#: 55 → 54（2026-10-09）：复查时现算已是 54，基线还留在 55。
#: **不是谁新清出来的** —— 把 HEAD 与工作区各扫一遍对比过，两边都是 54，
#: 也就是说这一格余量早就摆在那儿了，只是没人跟着收。
#: 留着它的代价很具体：下一个人写回**一个**不带日期的实测数，这条守卫照样绿。
BASELINE = 54

SCAN = ("workflows", "tools")


def _undated():
    out = []
    for base in SCAN:
        for p in sorted((ROOT / base).rglob("*")):
            if p.suffix not in (".md", ".py") or "__pycache__" in str(p):
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            for m in _MEASURED.finditer(t):
                if not _DATE.search(_para(t, m.start())):
                    line = t[:m.start()].count("\n") + 1
                    out.append((str(p.relative_to(ROOT)).replace("\\", "/"), line,
                                t[m.start():m.start() + 40].replace("\n", " ")))
    return out


class TheRatchetOnlyGoesDown(unittest.TestCase):
    def test_no_new_undated_measurement(self):
        got = _undated()
        self.assertLessEqual(
            len(got), BASELINE,
            f"不带日期的实测数从 {BASELINE} 涨到了 {len(got)} —— "
            f"新写的那个要么补上日期（「实测活动用户 YYYY-MM-DD：…」），"
            f"要么配一条现算的守卫（模板见 "
            f"`test_the_greeting_stats_are_not_stale`）。"
            f"规矩见 CONTRIBUTING「写下一个实测数时，把日期一起写上」。"
            f"\n新增的大致在：{[f'{f}:{n}' for f, n, _s in got[-4:]]}")

    #: 清掉几个才要求改常量。**2 不是 6** —— 第一版给了 6，
    #: 而 63 + 6 ≥ 68 让「基线没跟着收紧」这个变异照样绿（变异实测）。
    #: 松弛的意义只是「顺手清掉一两个别红整套」，不是给缺口留位置。
    SLACK = 2

    def test_the_baseline_is_tightened_when_it_drops(self):
        """清掉几个却不把基线调下来，棘轮就松了一格 —— 下次又能悄悄涨回去。"""
        got = _undated()
        self.assertGreaterEqual(
            len(got) + self.SLACK, BASELINE,
            f"现在只剩 {len(got)} 处，而基线还写着 {BASELINE} —— "
            f"把 BASELINE 调到 {len(got)}，棘轮才咬得住")

    def test_the_scan_actually_finds_things(self):
        """扫不到东西的守卫等于没有。"""
        self.assertGreater(len(_undated()), 10, "扫描器认不出实测句了 —— 写法变了？")

    def test_dated_ones_are_not_counted(self):
        """带日期的是记录，不该进这个数。"""
        self.assertNotIn("实测活动用户 2026-08-23",
                         " ".join(s for _f, _n, s in _undated()))


class TheJudgeItselfIsRight(unittest.TestCase):
    """扫描器的判断要经得起单测 —— 它自己错了，上面那条就是空转。"""

    def _count(self, text):
        return sum(1 for m in _MEASURED.finditer(text)
                   if not _DATE.search(_para(text, m.start())))

    def test_a_dated_prefix_counts_as_dated(self):
        self.assertEqual(self._count("实测活动用户 2026-08-23：236 份开场白里…"), 0)

    def test_a_dated_suffix_counts_as_dated(self):
        self.assertEqual(self._count("实测 63 个岗材料就绪但没投（2026-08-13 撞上）"), 0)

    def test_a_bare_one_is_caught(self):
        self.assertEqual(self._count("实测 151 个待评职位里 113 个已有 JD。"), 1)

    def test_a_number_without_a_unit_is_ignored(self):
        """「实测相关系数只有 0.33」不是计数，不该被要求带日期。"""
        self.assertEqual(self._count("实测相关系数只有 0.33。"), 0)

    def test_it_does_not_reach_across_sentences(self):
        """句号之后就是另一件事了 —— 跨句抓会把不相干的数算成实测。"""
        self.assertEqual(self._count("实测过一次。后来又抓了 200 个岗。"), 0)

    def test_a_date_in_another_paragraph_does_not_count(self):
        """**变异实测抓到的那一个。** 固定字数窗口会吃进邻段的日期 ——
        实际撞上的是一句不带日期的实测话，往后 80 字内正好是下一节开头的
        「用户 2026-08-13 又点了一个岗」。那个日期属于下一节，与这句无关。
        """
        two = "实测 63 个岗没投。\n\n下一节。用户 2026-08-13 又点了一个岗。"
        self.assertEqual(self._count(two), 1, "邻段的日期被当成这句的了")

    def test_a_date_in_the_same_paragraph_does_count(self):
        one = "实测 63 个岗没投（2026-08-13 撞上），两个入口给相反的建议。"
        self.assertEqual(self._count(one), 0)


class TheConventionIsWrittenDown(unittest.TestCase):
    CONTRIB = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    def test_the_section_exists(self):
        self.assertIn("## 写下一个实测数时，把日期一起写上", self.CONTRIB)

    def test_it_distinguishes_record_from_claim(self):
        """两类要分开说 —— 只说「都带日期」会让人去给活数也贴个日期。"""
        seg = " ".join(self.CONTRIB.split())
        self.assertIn("带日期的是记录", seg)
        self.assertIn("不带日期的是在说「现在」", seg)

    def test_it_forbids_updating_a_dated_record(self):
        """把历史观测改成今天的数，是拿今天抹掉一次真实的记录。"""
        self.assertRegex(" ".join(self.CONTRIB.split()),
                         r"别去「更新」它")

    def test_it_points_at_the_recompute_template(self):
        self.assertIn("test_the_greeting_stats_are_not_stale", self.CONTRIB)

    def test_it_carries_the_measured_cost(self):
        seg = " ".join(self.CONTRIB.split())
        self.assertIn("被抄进了 **7 处**", seg)
        self.assertRegex(seg, r"234 份\s+现算 236|文档写 234 份")

    def test_it_says_why_not_everything_can_be_recomputed(self):
        """不写这一句，下一个人会去给 68 处全配现算守卫，而多数根本算不回来。"""
        self.assertRegex(" ".join(self.CONTRIB.split()),
                         r"今天重算得不到同一批文件")

    def test_it_covers_a_dated_number_that_is_wrong_on_its_own_date(self):
        """**规矩自己的漏洞，是拿它去查东西时露出来的。** 只写「带日期的别更新」，
        遇到一个标着今天却量错了的数就无从下手（实测撞到：
        `is_anonymous_employer` 标着 2026-08-23、写 1355，同一天同一判据是 1369）。"""
        seg = " ".join(self.CONTRIB.split())
        self.assertIn("例外：它在自己那天就是错的", seg)
        self.assertRegex(seg, r"拿它自己写的判据在\*\*那天的数据\*\*上重跑一遍",
                         "没给分辨「记录」和「量错了」的办法")
        self.assertRegex(seg, r"1355（51%）|1355 个脱敏（51%）", "没留下那个实例")

    def test_it_warns_about_half_updated_sentences(self):
        """改一个数、漏掉同句另一个 —— 分母对得上，读的人不会再查后半句。"""
        seg = " ".join(self.CONTRIB.split())
        self.assertRegex(seg, r"一半新一半旧，比两个都旧更难发现")
        self.assertRegex(seg, r"234 更正到 236", "没留下那个实例")

    def test_it_names_the_ratchet(self):
        self.assertIn("test_measured_numbers_carry_their_date", self.CONTRIB)
        self.assertRegex(" ".join(self.CONTRIB.split()), r"只降不升")


if __name__ == "__main__":
    unittest.main()
