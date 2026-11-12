# -*- coding: utf-8 -*-
"""「可以考虑必写投前必问」这条规则，写在离写手 670 行远的地方。

上一轮量出：最近 30 份这一档的深评里 **22 份跳过了这一节（73%）**。
这一轮查为什么。把那 22 份的小节名列出来：

    结论：可以考虑 17 · 优势 17 · 缺口 17 · 本轮产出 17 · 评分明细 16
    硬性条件 15 · 职位真伪信号 15 · 建议 15 · 待核实的信息 15

**相邻小节一个不少。** 真伪信号在它上面、建议在它下面，两个都写了 ——
写的人是照着输出格式一节一节往下写的，唯独漏掉中间这一个。

原因不是懒，是**规则不在它该在的地方**：

    04-job-evaluation.md 第 40 行附近（引用块）  「「可以考虑」这一档必写这一节」
    04-job-evaluation.md 第 713 行（输出格式）   「没有就写「无」」  ← 写的人在这儿

写手此刻读的是输出格式那一行，而那一行看起来是**可选的**。
这就是本仓库反复记的那条：**一条规则只贴在一个写手身上，另外两个照样会犯**
（`AGENTS.md` 讲 `candidate.md` 小节名时用的是同一个判据）。

两头都补，形态照搬开场白那次（那次把违规率压住的就是「自检行 + 事后审计」）：

- **写的时候**：规则挪到输出格式那一节旁边，并把「写不出来说明它不属于这一档」
  的出路一起写上（升档 / 归「缺口」）。
- **落盘那一刻**：`job-apply.md` 写回四个字段的清单里加一条 —— 那张清单已经有
  「写之前对一眼判词天花板」，同一个位置、同一种形态。
- **事后**：`audit_pipeline` 那条（上一轮刚修好分母）继续兜底。

顺带把两个同义小节的分工写清楚（`投前必问` 是评估者的判断，
`投前先问清楚（沟通必问）` 是本文四处指令的机械落点）——
下游宽进两个都认，但模板里摆着两个没解释过的同义标题，本身就是漏写的诱因。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")


def _section(text, head):
    """从某个小节标题起、到下一个同级标题止的那一段。"""
    i = text.index(head)
    m = re.search(r"^#{2,4}\s", text[i + len(head):], re.M)
    return text[i:i + len(head) + (m.start() if m else 2000)]


class TheRuleIsAtTheOutputFormat(unittest.TestCase):
    """写手此刻在输出格式那一节上 —— 规则得在那儿。"""

    def _seg(self):
        return _section(EVAL, "### 投前必问")

    def test_the_tier_is_named_right_there(self):
        self.assertIn("可以考虑", self._seg(), "输出格式那一节没说哪一档必写")

    def test_it_says_it_is_mandatory_for_that_tier(self):
        self.assertRegex(self._seg(), r"必写|不许写「无」",
                         "看起来仍然是可选的")

    def test_it_gives_the_way_out(self):
        """只说「必写」会逼人硬凑三条。要给出路：升档、或归缺口。"""
        seg = self._seg()
        self.assertRegex(seg, r"升档|升「值得投」")
        self.assertIn("缺口", seg)

    def test_the_bullet_itself_carries_it(self):
        """注释会被读者跳过。那一行占位符本身也要带上这个条件。"""
        line = next(ln for ln in self._seg().splitlines()
                    if ln.startswith("- ..."))
        self.assertIn("可以考虑", line, f"占位符那行没提这一档：{line}")

    def test_the_other_tiers_are_still_optional(self):
        """别把「必写」扩到全部档位 —— 其余两档是「投，在沟通中补」。"""
        self.assertRegex(self._seg(), r"其余档次|其余两档",
                         "没说清别的档位仍然可写可不写")


class TheWriteBackChecklistCarriesIt(unittest.TestCase):
    """落盘那一刻还有一次机会 —— 那张清单已经有一条同形的。"""

    def _seg(self):
        i = APPLY.index("**写之前对一眼判词天花板**")
        return APPLY[i:i + 1400]

    def test_the_check_exists(self):
        self.assertIn("投前必问", self._seg(), "写回清单里没有这一条")

    def test_it_is_scoped_to_the_tier(self):
        self.assertIn("可以考虑", self._seg())

    def test_it_carries_the_measured_cost(self):
        self.assertIn("投前必问", self._seg())

    def test_the_original_check_is_untouched(self):
        """判词天花板那条不许被挤掉 —— 它管的是另一件事。"""
        self.assertIn("判词档不得高于技能与经验", self._seg())


class TheTwoSynonymousSectionsAreDistinguished(unittest.TestCase):
    """模板里摆着两个没解释过的同义标题，本身就是漏写的诱因。"""

    def test_both_still_exist(self):
        """**不合并。** 本文四处「放进沟通必问清单」都指着下面那一节。"""
        self.assertIn("### 投前必问", EVAL)
        self.assertIn("### 投前先问清楚（沟通必问）", EVAL)

    def test_each_says_what_the_other_is_for(self):
        for head, other in (("### 投前必问", "沟通必问"),
                            ("### 投前先问清楚（沟通必问）", "投前必问")):
            with self.subTest(head=head):
                self.assertIn(other, _section(EVAL, head),
                              f"{head} 没说和另一节怎么分")

    def test_the_routing_instructions_still_land_somewhere(self):
        """那四处指令是有主人的 —— 合并或改名会让它们无处可去。"""
        n = EVAL.count("放进沟通必问")
        self.assertGreaterEqual(n, 3, f"「放进沟通必问清单」的指令只剩 {n} 处")
        self.assertIn("本文里所有「放进沟通必问清单」的指令都落在这一节",
                      _section(EVAL, "### 投前先问清楚（沟通必问）"))

    def test_the_downstream_accepts_either(self):
        """两个标题并存的前提是下游宽进。哪天收窄了，这两节就得合并。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        i = src.index("def parse_ask_before(")
        self.assertRegex(src[i:i + 1600], r"投前必问\|必问\|要问清",
                         "下游不再宽进，而模板还摆着两个标题")


if __name__ == "__main__":
    unittest.main()
