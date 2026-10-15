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

## 这里为什么没有「总数」断言

原来这条是**棘轮**：数一串不带日期的实测句，总数只许降。2026-10-14 撤掉了那条
断言 —— 一个总数只有「永远不清理任何东西」才能维持，规则读起来像守卫，做起来
是记账。

**同一天规矩本身也翻了。** 原来写的是「带日期的是记录，过期不算错，别去更新
它」；现在写的是**带日期的不是豁免，是欠条** —— 日期记的是**这个数最后一次核对
是哪天**，语料一涨就得连数带日期一起改。规矩见 `CONTRIBUTING.md`
「写下一个实测数时，把日期一起写上」。

所以这里只留扫描器和它的判据：**扫得到、判得对**。哪天想知道现在还剩几处不带
日期，跑一次 `_undated()` 数一数；数字不进断言。

> **代价是这个数从此只靠人读，没有东西再盯它。** 记在这里是为了下次对得上：
> **2026-10-14 普查 = 55**（范围含 `workflows/`、`tools/`、`docs/` 与六个根文档）。
> 其中一条是检测器的粒度问题 —— `CONTRIBUTING.md` 里 2026-08-23 事故记录的
> 三个数，日期句在上一段，按空行切段就看不见了。基线 `6b1a7a9` 在原范围下是 56，
> 也就是说今天净减一条，而另外三条只是**扩了扫描范围才被看见**。
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

#: 2026-10-14 撤掉了 `BASELINE`。它记的是 2026-08-23 的存量 54（更早是 68，
#: 59 → 55 → 54 一路收下来的），而**「总数只许降」这件事本身没有终点**：唯一
#: 能维持它绿的办法是什么都不改。留着它的代价很具体 —— 下一个人写回一个不带
#: 日期的实测数，它照样绿；清掉一个却不收紧，它也照样绿。
#:
#: **计数还在**（`_undated()`），只是不再拿它当断言。想知道现状就跑一次数一数。

SCAN = ("workflows", "tools", "docs")

#: 治理层的正本也要扫。**它们不是例外，是同一批会飘的数所在的地方** ——
#: 2026-10-14 那轮审计里，「8 家吃斜杠」这个错数就同时存在于
#: `docs/tool-entries.md`、`README.md` 和 `SETUP.md`，而这条守卫只盯着
#: `workflows/` 与 `tools/`，三处全绿。
#:
#: `rglob` 只认目录，根上那几个文件要单列。
GOV_FILES = ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "README.md",
            "SECURITY.md", "SETUP.md")


def _undated():
    out = []
    paths = [q for base in SCAN for q in (ROOT / base).rglob("*")]
    paths += [ROOT / name for name in GOV_FILES if (ROOT / name).is_file()]
    for p in sorted(set(paths)):
        if p.suffix not in (".md", ".py") or "__pycache__" in str(p):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in _MEASURED.finditer(t):
            if not _DATE.search(_para(t, m.start())):
                line = t[:m.start()].count("\n") + 1
                out.append((str(p.relative_to(ROOT)).replace("\\", "/"), line,
                            t[m.start():m.start() + 40].replace("\n", " ")))
    return out


class TheScannerStillFindsThem(unittest.TestCase):
    """只管「扫得到、判得对」。**总数不再发断言** —— 理由见上面那段。"""

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

    def test_it_says_a_date_is_a_debt_not_a_freeze(self):
        """带日期不等于可以不管它了 —— 日期记的是最后一次核对，不是豁免。"""
        seg = " ".join(self.CONTRIB.split())
        self.assertIn("带日期的不是豁免，是欠条", seg)
        self.assertIn("最后一次被核对是哪天", seg)

    def test_it_requires_refreshing_a_dated_number(self):
        """**这条规矩翻过面了。** 原来写的是「带日期的是记录，别去更新它」。

        留着旧数比没有这个数更坏：没有数的人会去查，照着旧数做决策的人不会。
        """
        seg = " ".join(self.CONTRIB.split())
        self.assertNotIn("别去「更新」它", seg,
                         "规矩又翻回去了 —— 那条正是让全仓的数集体飘掉的原因")
        self.assertIn("数和日期一起改", seg)
        self.assertIn("留着一个已经不成立的数，比没有这个数更坏", seg)

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

    def test_it_covers_a_number_that_was_wrong_on_its_own_day(self):
        """**规矩自己的漏洞，是拿它去查东西时露出来的。**

        「它在自己那天就量错了」这一类，判据是拿它自己写的判据重跑一遍 ——
        实测撞到：`is_anonymous_employer` 标着 2026-08-23、写 1355，
        同一天同一判据跑出来是 1369。
        """
        seg = " ".join(self.CONTRIB.split())
        self.assertIn("自己那天就量错了的，照实改", seg)
        self.assertIn("拿它自己写的判据重跑一遍", seg,
                      "没给分辨「数飘了」和「当时就量错了」的办法")
        self.assertRegex(seg, r"1355（51%）|1355 个脱敏（51%）", "没留下那个实例")

    def test_it_warns_about_half_updated_sentences(self):
        """改一个数、漏掉同句另一个 —— 分母对得上，读的人不会再查后半句。"""
        seg = " ".join(self.CONTRIB.split())
        self.assertRegex(seg, r"一半新一半旧，比两个都旧更难发现")
        self.assertRegex(seg, r"234 更正到 236", "没留下那个实例")

    def test_it_says_what_to_do_with_a_number_it_cannot_recompute(self):
        """算不回来的可以留，但不许有规矩靠它做当前决策。"""
        seg = " ".join(self.CONTRIB.split())
        self.assertIn("实在算不回来的", seg)
        self.assertIn("别让规矩靠它做当前决策", seg,
                      "没说清「算不回来」的那批该怎么处理 —— 下一个人只能自己编")


if __name__ == "__main__":
    unittest.main()
