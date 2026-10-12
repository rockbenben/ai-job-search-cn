# -*- coding: utf-8 -*-
"""「公司性质」那张表按融资阶段一条轴切，而 `compStage` 里装着三条。

实测活动用户 2026-08-23 的库（2638 个岗，`compStage` 57% 有值），
这**一个字段**同时装着：

    融资阶段    天使轮 / A / B / C / D轮及以上 / 战略融资 / 融资未公开 / 不需要融资
    上市板块    已上市 / 沪深A股 / 港股 / 美股 / 科创板 / 创业板 / 新三板
    所有权性质  民营 / 国企 / 事业单位 / 合资 / 外资（欧美）/ 外资（非欧美）/ 外商独资

而 `04-job-evaluation.md` 那张表原来只有 5 行，代价量得出来：

- **「民营」116 个、「不需要融资」87 个表里没有对应行**，只能落进最后一行的
  「其他」被当成信息缺失 —— 而这两个值本身就是信息。「不需要融资」尤其冤：
  它排掉的正是下一行要扣分的那种风险（现金流断档）。
- **国企 18 / 合资 22 / 外资各写法 23，共 63 个**，表里写的判据是
  「公司名/行业可判」—— 而字段已经直接写出来了，等于让人去猜一个摆在眼前的答案。

两种读法在真实评估里都出现过：一份把「不需要融资」读成「稳定性好」，
另一份把同类情形判成「信息缺失非中性」。**规格不全，执行就会分叉。**

## 显示层那一半

`export_web_data` 的换词表把 `compStage` 译成「融资阶段」。今天没造成错显示
（那个词在导出里一次都没出现，换词从没触发），但它是**留在原地的错答案**：
字段一旦被引用，屏幕上就会出现「融资阶段：国企」。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import export_web_data as ex  # noqa: E402

EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    """拉平成一行。**先剥引用块的 `> `**：这一节新加的两段整块是引用，
    跨行的句子里会夹一个 `>`（`国企 18 / > 合资 22`），只抹空格抹不掉它。
    然后再去掉汉字之间那个折行留下的空格（英文词之间的要留着）。"""
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def nature_table() -> str:
    i = EVAL.index("**公司性质**（对国内求职者的实际含义差别极大）")
    return EVAL[i:EVAL.index("#### 雇主匿名", i)]


class TheFieldIsDescribedForWhatItIs(unittest.TestCase):
    def test_it_warns_that_the_name_lies(self):
        seg = flat(nature_table())
        self.assertRegex(seg, r"它不是「融资阶段」，它混了三条轴")

    def test_all_three_axes_are_named(self):
        seg = flat(nature_table())
        for axis in ("融资阶段", "上市板块", "所有权性质"):
            with self.subTest(axis=axis):
                self.assertIn(axis, seg)

    def test_it_says_to_read_the_value_literally(self):
        """「假设它是个轮次」正是这次要治的那个动作。"""
        self.assertRegex(flat(nature_table()),
                         r"\*\*照字面读那个值，别假设它是一个轮次。\*\*")

    def test_it_carries_the_measurement(self):
        seg = flat(nature_table())
        self.assertRegex(seg, r"2638 个岗，57% 有值")
        self.assertIn("2026-08-23", seg)


class EveryRealValueHasARow(unittest.TestCase):
    """枚举出来的取值，每一类都要在表里找得到落点。"""

    def _rows(self) -> str:
        return flat(nature_table())

    def test_ownership_values_are_named_as_field_values(self):
        """原来这两行写的是「公司名/行业可判」—— 而字段直接给了。"""
        seg = self._rows()
        for v in ("外资（欧美）", "外商独资", "国企", "事业单位", "合资"):
            with self.subTest(v=v):
                self.assertIn(v, seg, f"表里认不出 `compStage` 的取值「{v}」")

    def test_the_field_comes_first_and_the_name_is_the_fallback(self):
        """字段有值就用字段；空了才去看公司名 —— 顺序反了就是猜。"""
        seg = self._rows()
        self.assertRegex(seg, r"字段为空时看公司名/行业")
        self.assertRegex(seg, r"字段为空时看行业与公司名")

    def test_unlisted_private_has_its_own_row(self):
        seg = self._rows()
        self.assertIn("| 未上市民营 |", nature_table())
        self.assertIn("「民营」「股份制企业」", seg)

    def test_self_funded_has_its_own_row(self):
        seg = self._rows()
        self.assertIn("| 自负盈亏 |", nature_table())
        self.assertIn("「不需要融资」", seg)

    def test_neither_is_called_missing_information(self):
        """这是整条改动的要点：它们有信息，只是不在融资那条轴上。"""
        seg = self._rows()
        self.assertRegex(seg, r"\*\*不是信息缺失\*\* —— 它说的是所有权")
        self.assertRegex(seg, r"\*\*也不是信息缺失。\*\*")

    def test_self_funded_says_which_risk_it_removes(self):
        """只说「不是缺失」不够 —— 要说它到底排掉了什么。"""
        seg = self._rows()
        self.assertRegex(seg, r"它排掉的是\*\*现金流断档\*\*这一种风险")
        self.assertRegex(seg, r"别把它和「融资未公开」并成一档")

    def test_self_funded_does_not_become_a_free_bonus(self):
        """反过来也不许当成好消息 —— 不烧钱也可能是不长。"""
        self.assertRegex(self._rows(), r"\*\*不说明成长性\*\*")

    def test_the_listed_row_says_the_board_matters(self):
        seg = self._rows()
        self.assertRegex(seg, r"\*\*板块本身是信息\*\*")

    def test_the_genuinely_missing_row_narrowed(self):
        """兜底那一行还在，但只兜真的空的 —— 别把有值的又扫回去。"""
        seg = self._rows()
        self.assertRegex(seg, r"\| 融资未公开 / 其他 / 空 \|")
        self.assertRegex(seg, r"\*\*信息缺失，不要当成中性\*\*")

    def test_the_funding_row_survives(self):
        seg = self._rows()
        self.assertRegex(seg, r"轮次越早风险越高")

    def test_the_reason_is_recorded_with_counts(self):
        seg = self._rows()
        self.assertRegex(seg, r"原来只有 5 行，按融资阶段一条轴切")
        self.assertRegex(seg, r"「民营」116 个、「不需要融资」87 个")
        self.assertRegex(seg, r"国企 18 / 合资 22 / 外资各写法 23")

    def test_it_records_that_both_readings_really_happened(self):
        """「规格不全会分叉」是论断；这句是它的证据。"""
        seg = self._rows()
        self.assertRegex(seg, r"一份评估把「不需要融资」读成「稳定性好」")
        self.assertRegex(seg, r"另一份把同类情形判成「信息缺失非中性」")


class TheDisplayLayerDoesNotCallItAFundingRound(unittest.TestCase):
    def _entry(self, key: str) -> tuple:
        return next(t for t in ex.INTERNAL_TERMS if t[0] == key)

    def test_the_swap_no_longer_says_only_funding(self):
        self.assertEqual(self._entry("compStage")[1], "公司性质 / 融资阶段")

    def test_the_combined_one_matches(self):
        """`compScale/Stage` 和 `compStage` 说的是同一个字段，别只改一个。"""
        self.assertEqual(self._entry("compScale/Stage")[1], "公司规模与公司性质")

    def test_the_longer_key_still_comes_first(self):
        """`compScale/Stage` 必须排在 `compScale` 前面，否则被切成两半。"""
        keys = [t[0] for t in ex.INTERNAL_TERMS]
        self.assertLess(keys.index("compScale/Stage"), keys.index("compScale"))

    def test_the_neighbouring_swaps_survive(self):
        for k, v in (("compScale", "公司规模"), ("compIndustry", "所属行业"),
                     ("salaryMonths", "几薪")):
            with self.subTest(k=k):
                self.assertEqual(self._entry(k)[1], v)

    def test_the_reason_is_at_the_table(self):
        i = EX.index("INTERNAL_TERMS = [")
        seg = flat(EX[max(0, i - 800):i].replace("#:", " "))
        self.assertRegex(seg, r"\*\*`compStage` 不叫「融资阶段」。\*\*")
        self.assertRegex(seg, r"屏幕上就会出现 「融资阶段：国企」"
                              r"|屏幕上就会出现「融资阶段：国企」")

    def test_it_points_at_the_enumeration_instead_of_copying_it(self):
        """取值枚举只留一份，在 04 里。"""
        i = EX.index("INTERNAL_TERMS = [")
        seg = flat(EX[max(0, i - 800):i].replace("#:", " "))
        self.assertIn("04-job-evaluation.md", seg)

    def test_the_swap_still_works(self):
        out = ex.plain("公司规模与 compStage 都空")
        self.assertNotIn("compStage", out)
        self.assertIn("公司性质 / 融资阶段", out)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：那三条轴真的挤在一个字段里。"""

    def _values(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        f = ROOT / "users" / u / "job_scraper" / "seen_jobs.json"
        if not f.is_file():
            self.skipTest("没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        vals = [(e.get("compStage") or "").strip() for e in seen.values()
                if isinstance(e, dict)]
        vals = [v for v in vals if v]
        if len(vals) < 200:
            self.skipTest("有值的太少，说明不了")
        return vals

    def test_ownership_values_really_occur(self):
        vals = set(self._values())
        own = {v for v in vals
               if re.search(r"民营|国企|事业单位|合资|外资|外商|股份制", v)}
        self.assertTrue(own, "一个所有权取值都没有 —— 那几行没有依据了")

    def test_the_two_off_table_values_are_not_rare(self):
        """「民营」「不需要融资」表里没有对应行，只能落进「其他」那档——
        所以它们得真的常见，这条才撑得起给它们单开一行。

        2026-10-12：下限 50 → 30。热库有 `compStage` 的 555 条里这两个合计
        **47 条（8.5%）**。热库会随 `archive.py` 归档而缩水（已归档的岗
        搬出热库，带值的也一起搬走），绝对数跟着掉；判据问的是
        **「罕见不罕见」**，那是占比不是计数，所以跟着占比走。
        """
        vals = self._values()
        n = sum(1 for v in vals if v in ("民营", "不需要融资"))
        share = n / len(vals)
        self.assertGreater(n, 30,
                           f"「民营」+「不需要融资」只有 {n} 个（占 {share:.1%}）—— 重新量一次")
        self.assertGreater(share, 0.05,
                           f"占比掉到 {share:.1%} 了，那已经不是「不罕见」—— 重新量一次")

    def test_funding_rounds_also_occur(self):
        """三条轴要真的共存，才谈得上「混」。"""
        vals = set(self._values())
        self.assertTrue({v for v in vals if re.search(r"轮|融资", v)})
        self.assertTrue({v for v in vals if "上市" in v})


if __name__ == "__main__":
    unittest.main()
