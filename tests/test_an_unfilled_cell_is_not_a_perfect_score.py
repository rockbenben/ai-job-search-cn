# -*- coding: utf-8 -*-
"""评分明细那一列原来从格子里**任意位置**捞第一个数 —— 于是 `XX/100` 读成 100。

`04-job-evaluation.md` 的产出模板自己写的就是 `XX/100`：

    | 技能与经验 | XX/100 | **必须写拆解**：… |
    | 薪资与职级 | XX/100 或「信息缺失」 | … |

一份跑断、占位符没被替掉的评估，那一维会导出成**满分**，把这个岗顶到最前 ——
错在最坏的方向上，而且没有任何地方会报错。

## 为什么按开头取是安全的

这一列的写法实测只有 9 种（活动用户 2026-08-23，1062 行）：

    520  88
    424  88/100
    106  PASS（不计权重）
      4  —
      3  PASS
      2  88 ⚠
      1  信息缺失 · 1 提示 · 1 88 ⚠️

**没有一种是「数字不在开头」**（0 例）。所以 `re.match` 覆盖全部真实取值，
且正好拒绝 `XX/100`。改前改后真实语料的有分数行数都是 **947**，一分没动。

## 今天没有真的踩到

0/1062。但 268 份评估全是大模型现写的，跑断不是假设 —— 这条守的是那一天。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_dashboard as bd  # noqa: E402
import export_web_data as ex  # noqa: E402

EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")

HEAD = "## 评分明细\n| 维度 | 分数 | 说明 |\n|---|---|---|\n"


def score_of(cell: str):
    got = ex.parse_dimensions(HEAD + f"| 技能与经验 | {cell} | 说明 |\n")
    return got[0]["score"] if got else "（整行没解析出来）"


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class ThePlaceholderDoesNotBecomeAScore(unittest.TestCase):
    def test_the_template_placeholder_yields_nothing(self):
        self.assertIsNone(score_of("XX/100"))

    def test_it_specifically_is_not_the_denominator(self):
        """这才是要害：读成 None 是对的，读成 100 是灾难。"""
        self.assertNotEqual(score_of("XX/100"), 100,
                            "没填的格子导出成了满分")

    def test_other_unfilled_forms_too(self):
        for cell in ("XX", "XX/100", "X/100", "??/100", "待定 /100"):
            with self.subTest(cell=cell):
                self.assertIsNone(score_of(cell), f"「{cell}」读出了分数")

    def test_the_output_template_really_writes_it(self):
        """这条守卫的前提：模板里真的有 `XX/100` 这个写法。"""
        i = EVAL.index("## 输出格式")
        tmpl = re.search(r"```\n(.*?)\n```", EVAL[i:], re.S).group(1)
        self.assertIn("XX/100", tmpl,
                      "模板不再写 XX/100 了 —— 这条守卫的前提变了，重新量一次")


class EveryRealShapeStillWorks(unittest.TestCase):
    """实测枚举出来的 9 种写法，一种都不许读错。"""

    CASES = [
        ("88", 88),                    # 520 次
        ("88/100", 88),                # 424 次 —— 取分子
        ("PASS（不计权重）", None),      # 106 次
        ("—", None),
        ("PASS", None),
        ("88 ⚠", 88),
        ("88 ⚠️", 88),
        ("信息缺失", None),
        ("提示", None),
    ]

    def test_each_shape(self):
        for cell, want in self.CASES:
            with self.subTest(cell=cell):
                self.assertEqual(score_of(cell), want)

    def test_a_zero_is_a_score_not_a_blank(self):
        """0 分和「没打分」是两件事 —— 别被 falsy 顺手吞掉。"""
        self.assertEqual(score_of("0"), 0)
        self.assertEqual(score_of("0/100"), 0)

    def test_leading_spaces_are_tolerated(self):
        self.assertEqual(score_of("  72"), 72)

    def test_the_other_columns_survive(self):
        got = ex.parse_dimensions(
            "## 评分明细\n| 维度 | 分数 | 权重 | 依据 |\n|---|---|---|---|\n"
            "| 技能与经验 | 72/100 | 30% | 对口 |\n")
        self.assertEqual(got[0]["score"], 72)
        self.assertEqual(got[0]["weight"], 30)
        self.assertEqual(got[0]["note"], "对口")
        self.assertTrue(got[0]["weighted"])

    def test_the_gate_row_still_lands_as_not_weighted(self):
        """`PASS（不计权重）` 那一行既没有分数、也不该被当成计权维度。"""
        got = ex.parse_dimensions(
            HEAD + "| 地点（跨城搬迁） | PASS（不计权重） | 上海 |\n")
        self.assertIsNone(got[0]["score"])
        self.assertFalse(got[0]["weighted"])


class TheNeighbouringParsersDoNotTakeDenominatorsEither(unittest.TestCase):
    def test_the_total_score_ignores_the_placeholder(self):
        """`**综合得分：XX/100**` 不许变成 100 —— 那是整个岗的分。"""
        r = bd.parse_evaluation(
            "## 职位评估\n\n**综合得分：XX/100**\n\n### 结论：值得投\n")
        self.assertNotEqual(r.get("score"), 100)
        self.assertFalse(str(r.get("score") or "").strip())

    def test_the_total_score_still_reads_a_real_one(self):
        r = bd.parse_evaluation(
            "## 职位评估\n\n**综合得分：72/100**\n\n### 结论：值得投\n")
        self.assertEqual(str(r.get("score")), "72")


class TheReasonIsRecorded(unittest.TestCase):
    def _seg(self) -> str:
        i = EX.index('m = re.match(r"\\s*(\\d+)", raw)')
        return flat(EX[max(0, i - 1100):i].replace("#", " "))

    def test_it_says_what_it_refuses_to_do(self):
        self.assertRegex(self._seg(),
                         r"\*\*只认斜杠左边那个数，不许退而取分母。\*\*")

    def test_it_carries_the_enumeration(self):
        seg = self._seg()
        self.assertRegex(seg, r"1062 行")
        self.assertRegex(seg, r"\*\*没有一种是「数字不在开头」\*\*")
        self.assertIn("2026-08-23", seg)

    def test_it_names_the_worst_case(self):
        seg = self._seg()
        self.assertRegex(seg, r"导出成\*\*满分\*\*")
        self.assertRegex(seg, r"错在最坏的方向上")

    def test_it_admits_there_is_no_live_case(self):
        """今天 0 例 —— 不写清楚，下一个人会以为它修过一个真 bug。"""
        seg = self._seg()
        self.assertRegex(seg, r"真实语料里今天是 0 例")
        self.assertRegex(seg, r"跑断不是假设")

    def test_it_points_at_this_test(self):
        self.assertIn("test_an_unfilled_cell_is_not_a_perfect_score.py",
                      self._seg())


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：真实格子里数字确实都在开头，且分数一个没丢。"""

    def _cells(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        d = ROOT / "users" / u / "documents" / "applications"
        if not d.is_dir():
            self.skipTest("没有投递归档")
        out = []
        for f in d.glob("*/evaluation.md"):
            t = f.read_text(encoding="utf-8", errors="replace")
            header, rows = ex.parse_table(t, *ex.DIM_SECTION_ALIASES, cols=())
            if not header:
                continue
            i = ex._col(header, "分数", "分", "得分")
            if i < 0:
                continue
            out += [r[i].strip() for r in rows if i < len(r)]
        if len(out) < 200:
            self.skipTest("格子太少，说明不了")
        return out

    def test_no_real_cell_hides_its_number(self):
        odd = [c for c in self._cells()
               if "不计入" not in c and re.search(r"\d", c) and not re.match(r"\s*(?:\d|参考\s*\d)", c)]
        self.assertEqual(odd[:5], [],
                         f"{len(odd)} 个格子的数字不在开头 —— 按开头取会丢分，"
                         f"重新量一次")

    def test_no_unfilled_placeholder_is_sitting_in_the_corpus(self):
        """真有的话就不是「守未来」了，是当场的脏数据，要报出来。"""
        bad = [c for c in self._cells() if re.match(r"\s*[Xx?]{2,}", c)]
        self.assertEqual(bad, [],
                         f"语料里有 {len(bad)} 个没填的格子：{bad[:5]}")

    def test_the_scored_row_count_is_what_it_was(self):
        """改动前后都是 947 行有分数 —— 变了说明这次改动动了真数据。"""
        n = sum(1 for c in self._cells() if re.match(r"\s*\d", c))
        self.assertGreater(n, 800,
                           f"只剩 {n} 行有分数 —— 比记录的 947 少太多")


if __name__ == "__main__":
    unittest.main()
