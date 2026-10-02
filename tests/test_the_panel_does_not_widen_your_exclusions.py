# -*- coding: utf-8 -*-
"""面板不许建议用户去违反工具自己立的规矩。

`job-rank.md` 刚立了一条：**「候选人明确排除」这一道只认资料里明写过的条款**，
资料里没有的不许拿来当门（判据是 9 个岗死在他从没设过的排除上）。

而「市场怎么读你的简历」那一栏原来写着：

> 英语要求 32 · 改不了的约束：**把外企/全球化协作岗写进搜索排除条件**

照做的后果有两层：把一整类还能投的岗永久关掉，以及往排除清单里加一条
**他资料里没有的条款**。更糟的是，这正是他资料里**已经记过一次**的那种错——
英语那一条件他原样记过：只排除「口语沟通不了」这一种，执行时被扩大成
「凡沾英语一律排除」，2026-08-12 本人确认收窄。面板等于在劝他把收窄前的版本永久化。

实测（2026-08-22）那 36 条判词逐条看下来，写的全是口语 / 听说 / 流利 / 英语面试
—— **判定是对的**，挡住他的是 JD 里那几个字，不是公司性质；国内很多外企岗
本来就是中文工作环境。
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

SRC = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")


def _english_note() -> str:
    m = re.search(r'"name": "英语要求".*?"note": (.*?)\}\)', SRC, re.S)
    assert m, "找不到英语那条阻碍的文案"
    return "".join(re.findall(r'"([^"]*)"', m.group(1)))


class TheAdviceStaysInsideHisBoundary(unittest.TestCase):
    NOTE = _english_note()

    def test_it_does_not_tell_him_to_exclude_a_whole_company_type(self):
        """「把外企整类写进排除」比他的边界宽得多，而且他没设过这一条。"""
        self.assertNotRegex(
            self.NOTE, r"把外企.{0,12}写进|外企.{0,8}排除条件",
            "又在劝他把外企整类划掉——那是他资料里没有的条款")

    def test_it_says_what_actually_blocks_him(self):
        """挡住他的是「要口语」，不是公司性质。说清楚才改得对地方。"""
        for w in ("口语", "读写"):
            with self.subTest(w=w):
                self.assertIn(w, self.NOTE, f"没说清是「{w}」这一层")

    def test_it_says_the_write_only_jobs_are_still_in_play(self):
        """只要求读写的岗不在这批里 —— 不说的话他会以为凡沾英语都没戏。"""
        self.assertRegex(self.NOTE, r"不在这里面|照常评",
                         "没说清只要求读写的岗还能投")

    def test_the_lever_it_offers_is_the_search_query_not_a_new_gate(self):
        """想少刷到这类，改的是搜索词；新增排除条款要走 `/job-setup`，不是面板暗示。"""
        self.assertIn("搜索词", self.NOTE, "没给出真正该动的那个旋钮")
        self.assertRegex(self.NOTE, r"不用新增排除条款|不用加排除",
                         "没写明不必新增排除条款")

    def test_the_note_carries_no_markdown(self):
        """这段字直接进纯文本节点，`**` 会连着星号一起显示。"""
        self.assertNotIn("**", self.NOTE)


class TheRuleItMustNotContradict(unittest.TestCase):
    def test_the_gate_rule_still_says_profile_only(self):
        """上面那条测试的前提：排除条款只认资料里明写过的。这条没了，那条就失去意义。"""
        rank = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        self.assertIn("资料里没有的条款，不许拿来当门", rank)

    def test_his_boundary_is_the_narrow_one(self):
        """判据取自模板而不是他的真实资料——资料是 gitignore 的个人数据。"""
        tpl = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")
        self.assertIn("明确排除", tpl, "模板里没有「明确排除」这一节了")


if __name__ == "__main__":
    unittest.main()
