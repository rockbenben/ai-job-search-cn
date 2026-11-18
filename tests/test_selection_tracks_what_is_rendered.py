"""选中与推荐都要盯**真正渲染出来的那份列表**，不是叠屏蔽之前的。

App 里过滤分两层：

    shortlist  jobs 里去掉 重复挂法/判词出局/不投/已下线/流水线筛选/刚记过的
    visible    再叠上「这几类岗要不要看」（prefs）与屏蔽词（hidden）

**行来自 `visible`**（`mainList ∪ restList` 恰好等于它，`cut` 两支都成立）。
而 `effectiveId` 与 `recommended` 原来都拿 `shortlist` 算——差的正是那两层屏蔽。

漏的是这条路径：展开一个岗 → 在「这几类岗要不要看」里关掉它所属的那一类
（或把它公司加进屏蔽词）→ 那一行从名单里消失，`selectedId` 还指着它，
展开态没人收。等他把那一类打开，那一行**已经是展开的**——他没点过。

关键词与网站筛选也在 App 里应用，之后才切分显示的名单。

推荐同理：被屏蔽的岗照样能当选，而它那一行不渲染，于是整页一个「先投这个」
的标记都没有——用户分不清是没推荐还是标记坏了。

顺带钉住 TDZ：两个 memo 都必须排在 `visible` **之后**，否则 tsc 直接报
「used before its declaration」。这一节改动里撞了三次，写下来省得下次再撞。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "web" / "src" / "App.tsx"


class BothTrackTheRenderedList(unittest.TestCase):

    def setUp(self):
        self.src = APP.read_text(encoding="utf-8")
        self.code = re.sub(r"//.*", "", re.sub(r"/\*.*?\*/", "", self.src, flags=re.S))

    def test_selection_is_validated_against_visible(self):
        self.assertIn("visible.some((j) => j.id === selectedId)", self.code,
                      "选中又拿 shortlist 校验了——那是叠屏蔽之前的，"
                      "被屏蔽的岗会留着展开态，用户没点过它却是开的")
        self.assertNotIn("shortlist.some((j) => j.id === selectedId)", self.code)

    def test_recommendation_comes_from_visible(self):
        i = self.code.index("const recommended")
        body = self.code[i:self.code.index("  );", i)]
        self.assertIn("visible.reduce", body,
                      "推荐又从 shortlist 里挑了——挑中被屏蔽的岗时，"
                      "整页一个「先投这个」的标记都不会出现")
        self.assertIn("[visible]", body, "依赖没跟着改，memo 不会重算")

    def test_both_sit_after_visible(self):
        """TDZ：`visible` 是 const，用在它前面 tsc 直接报错。"""
        i_vis = self.code.index("const visible = useMemo(")
        for name in ("const effectiveId", "const recommended"):
            with self.subTest(name):
                self.assertGreater(self.code.index(name), i_vis,
                                   f"{name} 排在 visible 前面——tsc 会报"
                                   "「used before its declaration」")


    def test_search_runs_before_the_tiers_are_split(self):
        start = self.code.index("const visible = useMemo(")
        end = self.code.index("const worth = visible", start)
        self.assertIn("available.filter((j) => matchesJobSearch(j, kw, channel))", self.code[start:end])


class TheFunnelCellsStillMatchTheirRows(unittest.TestCase):
    """控制测试：格子上的数必须等于点开看到的行数（真实数据实算）。"""

    def test_every_cell_equals_its_rows(self):
        import json
        f = ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            self.skipTest("还没导出过面板数据")
        jobs = json.loads(f.read_text(encoding="utf-8")).get("jobs", [])
        if not jobs:
            self.skipTest("还没有职位")
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        sell = _cli.VERDICTS[:3]        # 词表正本在 _cli，这里不另抄一份

        def plain(v):
            return re.sub(r"^粗筛[：:]\s*", "", str(v or "")).strip()

        for funnel in ("materials", "applied", "interview"):
            with self.subTest(funnel):
                cell = sum(1 for j in jobs if funnel in (j.get("funnels") or []))
                rows = sum(1 for j in jobs
                           if funnel in (j.get("funnels") or [])
                           and not j.get("dupOf") and not j.get("expired")
                           and plain(j.get("verdict")) in sell)
                self.assertEqual(cell, rows,
                                 f"「{funnel}」格子写 {cell}、点开 {rows} 行——"
                                 "funnels_of 的排除与行集的过滤又分叉了")


if __name__ == "__main__":
    unittest.main()
