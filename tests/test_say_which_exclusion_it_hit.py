# -*- coding: utf-8 -*-
"""「明确排除」那一节把「什么时候 FAIL」写到了极细，却从没要求写清**是哪一条**。

那一节该有的都有：证据标准、套话误伤、「对方不会明写」怎么办、静默 PASS 等于
替他撤销排除项。唯独没有一句要求记下命中的是哪条排除。

审计一直在报这件事，理由也给得很硬：

> 295/396 个只写了「明确排除」，没说是哪一条。
> **这一档是七道门里唯一他能改的**，不知道每条排除挡掉多少个，
> 就没法决定放宽哪一条。

**检查在，规则不在。** 这个仓库反过来的情形见过很多次（规则写了没人验），
这一次是倒过来的：验的人知道该验什么，写的人从没被告知。

## 为什么单这一道门要求写清楚

学历、年限、户口、应届身份都不是他今天能动的；排除项是他自己下的结论，
随时可以放宽一条。但要决定放宽哪一条，他得先知道每条各挡掉了多少个岗 ——
实测 396 个死在这道门上的岗里 295 个答不了这个问题。

**他手里最大的一个调节旋钮，是唯一看不见刻度的那个。**

## 顺带定了一条兜底

写不出是哪一条 → 那就不该判 FAIL。说不清命中了哪条排除，本身就说明证据不够 ——
这与同一节既有的「证据标准照旧：JD 正文能确认命中才 FAIL」是同一条道理。
"""
import re
import sys
import pathlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as A  # noqa: E402

EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def section() -> str:
    i = EVAL.index("### 「明确排除」：他自己说了不要的")
    return EVAL[i:EVAL.index("### 执业资格 / 证照 / 职称", i)]


#: 两侧都是汉字的那个空格。中文行内本来就不该有空格，它只可能来自折行。
_CJK_GAP = re.compile(r"(?<=[一-鿿，。；：、（）「」])"
                      r" +(?=[一-鿿，。；：、（）「」])")


def flat() -> str:
    """这一节拉平成一行，供 `assertIn` / `assertRegex` 用。

    两道都要做，缺一条都会落空（三条断言第一版各栽了一次）：

    1. **剥掉引用块的 `> `** —— 新加那一段整块是引用，跨行的句子里会夹一个
       `>`（`他手里最大的一个 > 调节旋钮`）。
    2. **把汉字之间那个空格也去掉** —— 剥完 `>` 之后，折行本身还会留下一个
       空格（`户口、 应届身份`）。中文行内不该有空格，它只可能来自折行。
       **英文词之间的空格要留着**（`不该判 FAIL`、`tools/audit_pipeline.py`），
       所以只删两侧都是汉字/中文标点的那种。
    """
    s = " ".join(re.sub(r"^\s*>\s?", "", section(), flags=re.M).split())
    return _CJK_GAP.sub("", s)


class TheRuleExists(unittest.TestCase):
    def test_it_requires_naming_the_exclusion(self):
        self.assertIn("命中时必须写清是哪一条排除，不能只写「明确排除」四个字",
                      section(), "这一节仍然没要求写清是哪一条")

    def test_it_says_where_to_write_it(self):
        """「写清楚」落在哪一格 —— 不说的话各写各的地方，照样数不出来。"""
        seg = " ".join(section().split())
        self.assertRegex(seg, r"依据格里要出现他资料里那条排除的原话")
        self.assertRegex(seg, r"`候选人明确排除（跨城搬迁）`")

    def test_it_says_why_only_this_gate(self):
        """七道门里为什么单挑这一道 —— 不说就成了「所有门都写详细点」的空话。"""
        seg = flat()
        self.assertRegex(seg, r"它是七道里唯一他能改的")
        self.assertRegex(seg, r"学历、年限、户口、应届身份都不是他今天能动的")

    def test_it_says_what_the_information_is_for(self):
        seg = " ".join(section().split())
        self.assertRegex(seg, r"每条各挡掉了多少个岗")
        self.assertRegex(seg, r"要决定放宽哪一条")

    def test_it_carries_the_measurement(self):
        seg = " ".join(section().split())
        self.assertIn("只写了「明确排除」", seg)
        self.assertIn("不能只写「明确排除」四个字", seg)

    def test_the_image_that_makes_it_stick(self):
        """一句话说清代价，比一段论证更不容易被删。"""
        self.assertRegex(flat(), r"最大的一个调节旋钮，是唯一看不见刻度的那个")

    def test_it_has_a_fallback(self):
        """写不出来就不该判 FAIL —— 否则这条规则只会催生编出来的理由。"""
        seg = flat()
        self.assertRegex(seg, r"写不出是哪一条 → \*\*那就不该判 FAIL\*\*")
        self.assertRegex(seg, r"说不清命中了哪条排除，本身就说明证据不够")

    def test_it_points_at_the_checker(self):
        """规格要指得到**真正盯它的那一条**。

        2026-08-25 改名：原来指的是 `check_exclusions_trace_to_the_profile`
        里的一个副报告，那一版没有命令、还卡着「过半才报」的阈值。
        规则连同处置办法搬去了 `check_an_exclusion_fail_must_name_the_rule`。
        """
        self.assertIn("「判了排除却没说是哪一条」", section())
        self.assertNotIn("多半没说是哪一条", section(),
                         "还指着那个已经拆掉的副报告")


class TheCheckerItPairsWithIsIntact(unittest.TestCase):
    """规则是补给检查的 —— 检查没了，规则就没有兑现的地方。"""

    def test_the_check_exists(self):
        self.assertIn('("warn", "判了排除却没说是哪一条"', AUDIT)

    def test_the_check_says_the_same_why(self):
        i = AUDIT.index('"判了排除却没说是哪一条"')
        seg = " ".join(AUDIT[i:i + 700].split())
        self.assertRegex(seg, r"唯一你今天就能改的")
        self.assertRegex(seg, r"该放宽哪一条")

    def test_only_one_place_reports_that_number(self):
        """**同一个数字只许有一处讲规则。**

        2026-08-25 之前它挂在三处：`check_exclusions_trace_to_the_profile`
        的副报告、「哪一条排除最贵」的口径声明、以及这条。三处的说法已经分叉
        （一处说「没法决定放宽哪一条」，规格说「那就不该判 FAIL」）。
        现在只有这一条讲规则与处置；「最贵」那条保留一句纯口径声明。
        """
        self.assertNotIn("「他自己划的排除」多半没说是哪一条", AUDIT,
                         "那个副报告又回来了")
        # **数的是真跑出来的消息，不是源码里的字串。**
        # 数源码会把说明、引用、以及记录这次合并的注释一起算进去 ——
        # 而那几处本来就该写。要防的是**给用户看的消息里讲了两遍**。
        import _cli as _c
        seen, det = A.load(user_or_skip())
        said = [t for _lvl, t, m in
                [x for name, fn in A.CHECKS for x in (fn(seen, det) or [])]
                if "不该判 FAIL" in m]
        self.assertLessEqual(len(said), 1,
                             f"不止一条消息在讲这条规则：{said}")

    def test_the_stricter_sibling_check_survives(self):
        """更狠的那条：按一条他根本没设过的排除杀了岗。它是 error 不是 warn。"""
        self.assertIn('("error", "按一条他没设过的排除杀了岗"', AUDIT)

    def test_the_unreadable_profile_case_still_says_so(self):
        """读不出资料时要说「没查」，不是「查过没问题」。"""
        self.assertIn("所以「判词写的理由在资料里有没有出处」这一档没查——不是没有",
                      AUDIT)

    def test_the_reason_extractor_exists(self):
        self.assertTrue(hasattr(A, "_exclusion_reason"))


class TheSurroundingRulesAreIntact(unittest.TestCase):
    """新规则插在这一节开头 —— 底下那几条判据一条都不能被挤掉。"""

    def test_the_precedent_survives(self):
        self.assertIn("这一节原来**没有任何消费者**", section())

    def test_the_evidence_standard_survives(self):
        seg = section()
        self.assertIn("JD 正文能确认命中才 FAIL", seg)
        self.assertIn("一票否决仍然只许建立在确凿证据上", seg)

    def test_the_boilerplate_carve_out_survives(self):
        """纯中文岗末尾挂一句「英语六级」是最常见的误伤形状。"""
        seg = " ".join(section().split())
        self.assertRegex(seg, r"「拿不准」那档赢")
        self.assertRegex(seg, r"纯中文岗末尾挂一句「英语六级以上」")

    def test_the_silent_pass_rule_survives(self):
        self.assertRegex(" ".join(section().split()),
                         r"静默 PASS 等于替他把这条排除项撤了")

    def test_the_framework_does_not_second_guess_him(self):
        """排除项是他自己下的结论，框架执行、不复核。"""
        self.assertIn("框架的职责是执行，不是复核", section())

    def test_the_gate_is_still_one_of_the_seven(self):
        i = EVAL.index("| 门槛 | FAIL 的判据 | 注意 |")
        self.assertIn("候选人自己划的排除项", EVAL[i:i + 1200])


class TheCumulativeNumberNeedsABatchNumber(unittest.TestCase):
    """全库累计数只会随产量涨 —— 要判断规则灵不灵，得看最近一批。

    这是本仓库自己的判据（`batch_note` 上面那段）：

    > 审计每一条报的都是全库累计数，而那个数只会随产量涨：改好了也降不下来，
    > 因为分母里绝大多数是规则收紧之前产的。**改完一条规则之后，唯一能回答
    > 「它生效了没有」的是「最近一批还犯不犯」。**

    而这条检查只报累计数。实测 2026-08-30 接上之后：全库 89 个只写「明确排除」，
    **而最近那个像样的批次（08-27，36 个）里就有 13 个（36%）** ——
    不是存量遗留，是现在还在犯。两句话给读的人的动作完全不同。

    分组用职位库自己的 `rank_date`（344 个判死的全都有），不是文件时间 ——
    同一课 `test_a_trend_needs_something_to_trend_over` 记过：mtime 会被重新
    归档、批量改权限、同步工具推到今天。
    """

    SRC = (pathlib.Path(__file__).resolve().parents[1]
           / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")

    def _seg(self) -> str:
        i = self.SRC.index("def check_an_exclusion_fail_must_name_the_rule")
        return self.SRC[i:self.SRC.index(chr(10) + "def ", i + 10)]

    def test_it_reports_the_latest_batch(self):
        """**要算，还要真印出去。**

        第一版只断言 `batch_note(` 出现过 —— 变异实测当场证明它空转：
        把拼报文那半句 `+ (f"{_bn}。" if _bn else "")` 删掉，赋值那行还在，
        断言照样绿，而用户再也看不到那个数。
        「算了却没有消费者」是本仓库反复记的形状。
        """
        seg = self._seg()
        self.assertIn("batch_note(", seg,
                      "只报累计数 —— 改好了也降不下来，看不出规则灵没灵")
        # ⚠️ 取**最后**那个 return：函数开头还有一句 `if not bare: return []`，
        # 用 `index` 会从那儿起切，把上面的赋值行也圈进来 —— 变异实测时
        # 这条断言因此空转了一轮（删掉拼报文那半句，它照样绿）。
        ret = seg[seg.rindex('return [("warn"'):]
        self.assertIn("_bn", ret, "算了批次数却没拼进报文，用户看不到")

    def test_it_groups_by_the_stored_date(self):
        seg = self._seg()
        self.assertIn("rank_date", seg)
        self.assertNotIn("st_mtime", seg, "又按文件时间分组了")

    def test_the_note_is_shared_not_hand_written(self):
        """`batch_note` 是共用的那一份 —— 手写第三遍就会有第四遍写不出来。"""
        self.assertNotIn("最近一批（", self._seg(),
                         "把那句话手写进这条检查了，判据该走 batch_note")


if __name__ == "__main__":
    unittest.main()
