"""投过的岗不该继续躺在「可以投的岗位」里。

## 这条是实测撞出来的

用户在面板上给一个岗点了「我投了」，又点了「没下文」。投递记录写对了
（`status: no response`，两条备注都在）、`applied` 也回接到了那个岗上、
`nextStep` 置成了 null、流水线「已投递」变成 1 —— **数据链路整条都是对的**。

可那一行照旧显示在「可以投的岗位」里。用户的原话：「怎么该项还在可以投」。

病在过滤条件：`shortlist` 只看重复挂法（`dupOf`）、判词（`isOut`）、手动排除
（`excluded`）和流水线筛选（`matchFunnel`）—— **一个字都没提投递状态**。

## 为什么「挂个已投小标」不算修好

这个岗位表里早就有一枚「已投」chip，注释写着它是为了解决「面板说已投递 1，
可哪一个投了完全看不出来」。那解决的是**辨识**问题，没解决**分类**问题：

- 标题写着「可以投的岗位」，里面装着一个已经投出去、而且已经没下文的岗——标题在说谎。
- 求职最容易犯的错就是重复投同一家。把已投的和没投的摆在同一份名单里、只靠一枚
  小标区分，正是在制造那个错。

## 三条边界

1. **排除只在没开筛选时生效。** 点了流水线的「已投递 / 材料就绪 / 面试中」就是专门
   来看它们的。而且 Python 侧的计数口径是「材料就绪**含**已投的」，格子里的数字
   必须等于点开看到的行数——`test_pipeline_counts.py` 守着这一条。
2. **不许静默消失。** 默认视图里少了一行而没有解释，在用户那里等同于「数据丢了」。
   所以要有一处说明还剩几个已投的、并且点得回去。
3. **「推荐先投」不能落在已投的岗上。** 它从 `shortlist` 里挑最高分——名单里没有
   已投的，这条就自动成立；这里钉住的是「推荐从 shortlist 派生」这个前提。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsx import POSITION_VIEW  # noqa: E402

APP = ROOT / "web" / "src" / "App.tsx"


def src() -> str:
    return APP.read_text(encoding="utf-8")


def shortlist_block(text: str) -> str:
    """`const shortlist = useMemo(...)` 那一段。

    锚在名字上、而不是行号上——行号会随着上面加注释而漂。找不到就直接失败，
    不要返回空串：空串会让下面每条 `assertIn` 都红，而报的原因是错的
    （「过滤条件里没有 applied」而不是「这段代码改名了」）。
    """
    i = text.find("const shortlist = useMemo(")
    assert i != -1, "App.tsx 里找不到 `const shortlist = useMemo(` —— 改名了？"
    j = text.find(");", i)
    assert j != -1, "shortlist 那段没有收尾的 `);`"
    return text[i:j]


class AppliedJobsDropOutOfTheShortlist(unittest.TestCase):

    def test_the_filter_actually_looks_at_applied(self):
        block = shortlist_block(src())
        self.assertIn("applied", block,
                      "「可以投的岗位」的过滤条件里没有投递状态 —— "
                      "投过的岗会继续躺在名单里，标题在说谎")

    def test_the_exclusion_is_scoped_to_the_unfiltered_view(self):
        """点了流水线格子时必须看得见已投的，否则那三格点开是空的。"""
        block = shortlist_block(src())
        self.assertRegex(
            block, r'funnel\s*===\s*""',
            "排除没有限定在「没开筛选」时 —— 点「已投递」那一格会看到空表")

    def test_recommendation_comes_from_the_shortlist(self):
        """「推荐先投」必须从已排除已投岗的那份名单里挑，不能另起一份。"""
        text = src()
        i = text.find("const recommended = useMemo(")
        self.assertNotEqual(i, -1, "找不到 recommended —— 改名了？")
        seg = text[i:i + 600]
        self.assertIn("visible.reduce", seg,
                      "推荐不是从 shortlist 派生的 —— 可能会推荐一个已经投过的岗")


class TheHiddenOnesAreAccountedFor(unittest.TestCase):
    """收起来了要说一声，并且点得回去。"""


    def test_the_count_is_computed(self):
        self.assertIn('{ id: "applied", label: "已投递", count: funnelCounts.applied }', src())


    def test_there_is_a_way_back_to_them(self):
        text = src()
        i = text.index('className="position-views"')
        self.assertIn(POSITION_VIEW, text[i:i + 550])


class TheDataSideAlreadyHoldsUpItsEnd(unittest.TestCase):
    """这条 bug 的数据侧是好的，钉住它，免得将来「修」错地方。

    实测那次：台账写对了、`applied` 回接了、`nextStep` 置空了、流水线也变了。
    唯独前端的一处过滤没跟上。所以这里钉的是**导出器不要反过来去藏数据**——
    已投的岗必须照常出现在 `jobs` 里并带上 `applied`，页面才有得筛。
    """

    def test_the_exporter_attaches_applied_instead_of_dropping_the_job(self):
        ex = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('j["applied"] = {', ex,
                      "导出器没把投递状态回接到岗位上")
        self.assertNotRegex(
            ex, r"jobs\s*=\s*\[[^\]]*not\s+\w+\.get\(.applied.\)",
            "导出器把已投的岗整个丢掉了 —— 那样流水线「已投递」点开会是空的，"
            "该藏的是默认视图，不是数据")


if __name__ == "__main__":
    unittest.main()
