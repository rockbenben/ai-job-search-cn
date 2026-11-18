# -*- coding: utf-8 -*-
"""「不想看什么」：视图过滤，不改任何岗的状态。

用户 2026-08-13：「某些公司投过的，让用户选择是否隐藏。比如隐藏某些公司、
某些职位、某些字段」。名单长到 90 行时，翻的成本主要来自**已经处理过的噪音**：
同一家公司挂七八个岗、标题里带「销售」的一眼不想看、某几列从来不看。

## 和「不投」必须分开

`excluded.ts` 管的是对这个岗的**判断**（要写回盘上，`/job-rank`、报表、催进度
都得认）。这里管的是**看的时候不想看见**——纯视图偏好。

混在一起会出事：「这家公司我投过了，别再显示」不等于「这家公司的岗我都不投」，
后者会让下个月这家开了个好岗时完全看不见。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
H = (ROOT / "web" / "src" / "data" / "hidden.ts").read_text(encoding="utf-8")
UI = (ROOT / "web" / "src" / "components" / "HidePrefs.tsx").read_text(encoding="utf-8")
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
SL = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(encoding="utf-8")


class ItIsAViewFilterNotAJudgement(unittest.TestCase):

    def test_it_only_touches_local_storage(self):
        """写盘就成了「判断」，那是 excluded 的活。"""
        self.assertIn("localStorage", H)
        self.assertNotIn("/api/", H, "屏蔽偏好不该调任何写盘接口")

    def test_the_distinction_is_written_down(self):
        self.assertIn("和「不投」是两件事", H)
        self.assertIn("不改任何岗的状态", UI)

    def test_the_ui_says_it_changes_nothing(self):
        """用户得知道清掉之后岗会回来，否则不敢用。"""
        self.assertIn("清掉就全回来了", UI)


class ItCannotSilentlyEatTheList(unittest.TestCase):

    def test_the_hidden_count_is_always_visible(self):
        """一个开着的筛选器最危险的失败模式是用户忘了它开着。"""
        self.assertIn("hiddenCount", UI)
        self.assertIn("藏了", UI)

    def test_there_is_a_clear_all(self):
        self.assertIn("全部清掉", UI)

    def test_hiding_happens_before_the_tier_split(self):
        """切档之后再滤，两档的数会对不上。"""
        # 锚在**变量名**上，不锚在当时的写法上：`hide(shortlist)` 2026-08-13
        # 改成了 useMemo（裸函数调用让 1200 个岗每次渲染都重过一遍全部关键词，
        # 关键词加到 50 多个时渲染进程直接无响应）。守的规矩——先滤再切档——没变。
        i_vis = APP.index("const available = ")
        i_cut = APP.index("const worth = visible")
        self.assertLess(i_vis, i_cut, "屏蔽发生在切档之后，两档的数会对不上")
        seg = APP[i_vis:i_cut]
        self.assertIn("isHidden", seg, "关键词筛选前的名单应先应用屏蔽规则")
        self.assertIn("useMemo", seg, "屏蔽没进 useMemo——每次渲染都会重算整表")


class TheDetailsThatBite(unittest.TestCase):

    def test_applied_job_itself_stays_visible(self):
        """藏「投过的公司」时，**已经投的那个岗自己要留着**——
        否则用户找不到自己投了什么。"""
        self.assertIn("!job.applied && co && appliedTo.has(co)", H)

    def test_prefs_survive_a_schema_change(self):
        """存量结构少一个键不该让整份偏好失效，更不该在渲染时炸。"""
        self.assertIn("Array.isArray", H)

    def test_only_real_columns_are_offered(self):
        """给一个关不掉的东西加开关，用户点了没反应只会以为坏了。
        第一版列了「硬性条件」——而那一列早就撤掉了。"""
        keys = re.findall(r'\{ key: "(\w+)", label:', H)
        self.assertTrue(keys, "没解析到可关的列")
        for k in keys:
            with self.subTest(col=k):
                self.assertIn(f'key: "{k}"', SL, f"「{k}」这一列在表里根本不存在")

    def test_the_load_bearing_columns_are_not_offered(self):
        keys = re.findall(r'\{ key: "(\w+)", label:', H)
        self.assertNotIn("score", keys, "分数列不能关——那是这张表存在的理由")
        self.assertNotIn("title", keys, "职位名关掉就不知道每行是什么了")


if __name__ == "__main__":
    unittest.main()


class TheEmptyStateSaysWhichEmptyItIs(unittest.TestCase):
    """空表有三种原因，说错一种就是把用户指向错的地方。

        真没有岗   → 去 /job-scrape 找
        筛选筛空了 → 点「×」取消筛选
        屏蔽藏没了 → 去「不想看什么」里清掉      ← 2026-08-13 加屏蔽时漏的

    实测：56 个关键词把表滤空，页面说「还没有职位可以看——下一步是去找岗」，
    而库里有 1204 个岗。**照它去 /job-scrape 只会抓回更多看不见的岗。**
    """

    SL = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(encoding="utf-8")

    def test_all_three_branches_exist(self):
        self.assertIn("hiddenCount ? (", self.SL, "没有「被屏蔽滤空」这一支")
        self.assertIn("filtered ? (", self.SL, "没有「筛选筛空」这一支")
        self.assertIn("还没有职位可以看", self.SL, "没有「真没有岗」这一支")

    def test_the_hidden_branch_comes_first(self):
        """屏蔽那支要排在最前：它同时也可能处于某个筛选下，
        而「你自己藏的」比「这个筛选没有」更接近用户能动手的地方。"""
        i_hidden = self.SL.index("hiddenCount ? (")
        i_filter = self.SL.index("filtered ? (")
        self.assertLess(i_hidden, i_filter)

    def test_it_points_at_the_way_out(self):
        seg = self.SL[self.SL.index("hiddenCount ? ("):][:400]
        self.assertIn("不想看什么", seg, "没告诉用户去哪清")
        self.assertIn("全部清掉", seg, "没指出那个按钮")

    def test_app_passes_the_count(self):
        """每个 `<Shortlist>` 都要拿到 hiddenCount，否则它的空状态会说错话。

        数出现次数不行：`<HidePrefs hiddenCount={hiddenCount}>` 也带这个 prop，
        算进去就永远对不上（第一版就是这么误报的）。**逐个标签看**。
        """
        import re as _re
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        tags = _re.findall(r"<Shortlist\s(.*?)/>", app, _re.S)
        self.assertTrue(tags, "找不到 <Shortlist>")
        missing = [i for i, t in enumerate(tags) if "hiddenCount" not in t]
        self.assertEqual(missing, [],
                         f"第 {missing} 个 <Shortlist> 没拿到 hiddenCount，空状态会说错话")
