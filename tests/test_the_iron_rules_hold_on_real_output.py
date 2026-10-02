# -*- coding: utf-8 -*-
"""`03` 的两条硬铁律，在真实产出上现算一遍 —— 只留棘轮，不加检查。

## 为什么是棘轮而不是一条自检

`03-writing-style.md` 六条铁律里，机械上够得着的只有两条：

    铁律 3  能力边界是禁区 ——「所列内容在任何文案中都不得出现或被暗示」
    铁律 4  不用没有证据支撑的评价词 ——「每一个『精通』『资深』『深入』
            都必须紧跟一个具体事实」

两条都查过了，**两条都在被遵守，而且加检查会是净噪音**：

- **铁律 3**：资料里 8 条边界，剥出话题词去扫 280 份开场白，命中 49 处
  （「代码」35、「英语」7、「口语」7）。逐条看过采样 —— **每一处都是在如实交代
  那条边界本身，没有一处改口去主张对方要的能力**（原句不在这里引，那是某个人的
  自我评价，公开仓库里只需要知道结论）。
  那正是这条铁律要的结果，而一条按「话题出现」判的检查会把它们全报成越界。
  真正该判的是「这句在主张还是在交代」，那不是正则做得了的事。

- **铁律 4**：280 份里评价词共 10 处（熟练 5、资深 2、深入 1、擅长 1、精通 1），
  同句内找不到数字或英文专名的只有 2 处 —— 而那 2 处**都是在引用职位描述**
  （「我想应聘智能体平台资深产品经理」是岗位名；「要求里写了精通一门后端语言」
  是引 JD 的要求）。

所以这里不加自检，只留一道**只降不升**的棘轮：数字变坏了会红，
而它不会天天对着正确的产出喊狼来了。判据与 `test_measured_numbers_carry_their_date`
的棘轮同源。
"""
import collections
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402
import _cli  # noqa: E402

#: 铁律 4 点名的那几个词。
BOAST = ("精通", "资深", "深入", "擅长", "熟练", "丰富的经验", "经验丰富")
#: 「具体事实」的近似判据：同一句里有数字，或有专有名词式的英文。
FACT = re.compile(r"\d|[A-Za-z]{3,}")
#: 实测 2026-08-30：280 份开场白里 2 处 —— 两处都是在引用职位描述。
#: **这个数只许降。** 升了说明产出里真开始出现没有证据的评价词。
BOAST_WITHOUT_EVIDENCE = 2


def _openings():
    user = user_or_skip()
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    out = []
    for f in sorted(apps.glob("*/outreach.md")):
        g = ap._greeting_of(f.read_text(encoding="utf-8", errors="replace")) or ""
        if g:
            out.append((f.parent.name, g))
    return out


class IronRuleFourHolds(unittest.TestCase):
    """评价词要么带证据，要么是在引用职位描述。"""

    def test_the_ratchet_only_goes_down(self):
        rows = _openings()
        if not rows:
            self.skipTest("没有开场白")
        bad = []
        for name, g in rows:
            for sent in re.split(r"[。！？\n]", g):
                if any(w in sent for w in BOAST) and not FACT.search(sent):
                    bad.append(f"{name.split('_')[0][:14]}：{sent.strip()[:40]}")
        self.assertLessEqual(
            len(bad), BOAST_WITHOUT_EVIDENCE,
            f"没有证据支撑的评价词从 {BOAST_WITHOUT_EVIDENCE} 涨到了 {len(bad)}"
            f"（`03` 铁律 4：每一个「精通」「资深」「深入」都必须紧跟一个具体"
            f"事实）：\n  " + "\n  ".join(bad))

    def test_the_detector_can_fire(self):
        """对照：带证据的不报，光秃秃的报。"""
        withev = "我精通 Typst，写过 3 份模板"
        bare = "我精通产品设计"
        self.assertTrue(FACT.search(withev))
        self.assertFalse(FACT.search(bare))


class WhyThereIsNoCheckForIronRuleThree(unittest.TestCase):
    """铁律 3 不做成自检的理由要写下来 —— 不然下一个人会加一条噪音检查。"""

    def test_the_reason_is_recorded(self):
        doc = __doc__ or ""
        #: 钉「如实交代」这四个字，不钉整句——那份采样结论后来去掉了原句引用
        #: （原句是某个人的自我评价，不进公开仓库），说法会重排，判据不该跟着漂。
        self.assertIn("如实交代", doc)
        self.assertIn("那不是正则做得了的事", doc)

    def test_the_boundary_section_is_still_there(self):
        """理由建立在「资料里那一节存在」之上 —— 它没了这段话就该重看。

        ⚠️ **断言里不许出现资料本身。** 第一版用 `assertRegex(t, ...)`，
        失败时 unittest 会把 `t` 整个印进报告 —— 那是用户的私人资料
        （姓名、薪资、边界），而测试报告会被贴进对话、CI 日志、issue。
        先算成布尔再断言。
        """
        user = user_or_skip()
        p = ROOT / "users" / user / "profile" / "candidate.md"
        if not p.is_file():
            self.skipTest("没有候选人资料")
        found = any(re.match(r"#{2,4}\s*明确的能力边界", ln)
                    for ln in p.read_text(encoding="utf-8").splitlines())
        self.assertTrue(found, "资料里没有「明确的能力边界」那一节了 ——"
                               "本文件顶上那段「为什么不加检查」要重看")


if __name__ == "__main__":
    unittest.main()
