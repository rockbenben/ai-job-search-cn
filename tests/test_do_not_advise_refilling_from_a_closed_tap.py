# -*- coding: utf-8 -*-
"""面板一边劝「旺季用来补新的」，一边把 84% 的供给显示成关着的。

上一轮把两个口径分开印了（「累计 N 个能投」vs「现在还剩 M 个」），
数摆出来了 —— **但没有任何一处把它和「去补货」这条建议连起来。**

实测活动用户 2026-08-24：

    贡献最大的渠道         累计判过能投 104 / 全部 124 = 84%
    它的开关               **关着**
    上一轮各家新增          它一家 150 · 开着的三家合计 87

照建议去补货，拿到的会是应有的三分之一，而没有一处说得出为什么。

## 判据用累计，不用「现在还剩」

`sellable` 减掉了已投/已下线/已跳过 —— 越给力的渠道那个数被吃得越干净，
拿它判会把**最该开回来的那家判成最没用的**。

## 不替他决定开不开

他关掉那家可能有自己的理由（命中率确实低）。这一条只负责让「去补货」
和「供给关着」出现在同一屏上 —— 此前它们从不照面。

## 只在够格时说

关掉一家小渠道是正常取舍，报它是噪音。门槛是**关掉的那家占了可投供给的过半**
（`OFF_SUPPLY_SHARE`）—— 到那时「去补新的」这条建议才是明显兑现不了的。
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

BD = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def ps(**over):
    """四家渠道的构造样本：一家关着、贡献最大。"""
    rows = [{"name": "猎聘", "enabled": False, "everSellable": 104},
            {"name": "BOSS", "enabled": True, "everSellable": 16},
            {"name": "智联", "enabled": True, "everSellable": 4},
            {"name": "前程无忧", "enabled": True, "everSellable": 0}]
    for r in rows:
        if r["name"] in over:
            r.update(over[r["name"]])
    return rows


class ItFiresOnlyWhenItMatters(unittest.TestCase):
    def test_a_closed_majority_supplier_is_reported(self):
        got = ex.off_supply(ps())
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "猎聘")
        self.assertEqual(got[1], 104)

    def test_all_open_says_nothing(self):
        self.assertIsNone(ex.off_supply([dict(p, enabled=True) for p in ps()]))

    def test_a_small_closed_portal_says_nothing(self):
        """关掉一家小渠道是正常取舍 —— 报它就是噪音。"""
        rows = ps(猎聘={"enabled": True}, 智联={"enabled": False})
        self.assertIsNone(ex.off_supply(rows))

    def test_the_threshold_is_a_majority(self):
        n = int(124 * ex.OFF_SUPPLY_SHARE)
        self.assertIsNone(ex.off_supply(ps(猎聘={"everSellable": n,
                                               "enabled": False},
                                           BOSS={"everSellable": 124 - n})))

    def test_a_tiny_library_says_nothing(self):
        """总共没几个可投的岗时，「占大头」说明不了任何事。"""
        self.assertIsNone(ex.off_supply(
            [{"name": "甲", "enabled": False, "everSellable": 5},
             {"name": "乙", "enabled": True, "everSellable": 1}]))

    def test_it_judges_by_the_cumulative_count(self):
        """**拿「现在还剩」判会把最该开回来的那家判成最没用的。**"""
        i = EX.index("def off_supply(portals: list):")
        body = EX[i:EX.index("def portal_rows(", i)]
        self.assertIn("everSellable", body)
        self.assertNotIn('"sellable"', body)

    def test_the_reason_is_recorded(self):
        i = EX.index("def off_supply(portals: list):")
        seg = flat(EX[i:EX.index("def portal_rows(", i)])
        # 首行也要钉：它说清了返回值是什么、以及触发条件。只钉正文的话，
        # 把首行换成「关掉的渠道里贡献最大的那家。」照样绿（变异实测）。
        self.assertRegex(seg, r"如果它占了可投供给的大头 → \(名字, 个数, 占比\)")
        self.assertRegex(seg, r"贡献了 83% 可投岗的那家是关着的")
        self.assertRegex(seg, r"拿到的会是应有的三分之一")
        self.assertRegex(seg, r"不替他决定开不开")
        self.assertIn("2026-08-24", seg)

    def test_the_threshold_says_why_it_is_not_always_on(self):
        i = EX.index("OFF_SUPPLY_SHARE = ")
        seg = flat(EX[max(0, i - 500):i])
        self.assertRegex(seg, r"不是每次都说")
        self.assertRegex(seg, r"报它是噪音")


class TheSentenceIsUsable(unittest.TestCase):
    def _n(self):
        return bd.off_supply_note(("猎聘", 104, 84))

    def test_nothing_when_there_is_nothing(self):
        self.assertEqual(bd.off_supply_note(None), "")

    def test_it_names_the_portal_and_the_share(self):
        n = self._n()
        self.assertIn("猎聘", n)
        self.assertIn("84%", n)
        self.assertIn("104", n)

    def test_it_states_the_consequence(self):
        """「你关了一家」不是行动依据 —— 要说清照建议做会少拿多少。"""
        self.assertRegex(self._n(), r"不开回来，这一轮补到的会少一大半")

    def test_it_says_where_to_switch_it_back(self):
        """`AGENTS.md`：每一处引导都要写出该怎么动手。"""
        self.assertRegex(self._n(), r"在这一页的「招聘网站」那一段点一下")

    def test_a_chinese_name_gets_no_spaces(self):
        """一律加空格会印出「你把 猎聘 关掉了」。"""
        self.assertIn("你把猎聘关掉了", self._n())

    def test_a_latin_name_does_get_spaces(self):
        self.assertIn("你把 BOSS 关掉了", bd.off_supply_note(("BOSS", 40, 60)))

    def test_no_markdown_or_jargon(self):
        n = self._n()
        self.assertNotIn("**", n)
        for w in ("硬门", "四维", "判词", "台账", "短名单", "封顶"):
            with self.subTest(w=w):
                self.assertNotIn(w, n)

    def test_it_does_not_tell_him_to_switch_it_on(self):
        """他可能有自己的理由。这条只摆事实，不替他决定。"""
        n = self._n()
        self.assertNotRegex(n, r"应该开|必须开|把它开回来吧")

    def test_the_reason_is_recorded(self):
        i = BD.index("def off_supply_note(")
        seg = flat(BD[i:BD.index("def season_note(", i)])
        self.assertRegex(seg, r"这里不重判")
        self.assertRegex(seg, r"此前它们\s*从不照面")


class ItReachesBothPiecesOfAdvice(unittest.TestCase):
    """两处都在劝人补货 —— 只接一处，另一处照旧空口。"""

    SLACK = [7, 7, 8, 8, 8]

    def test_the_season_line_carries_it(self):
        import datetime as dt
        got = bd.season_note(self.SLACK, dt.date(2026, 8, 24), "在职",
                             ready=60, off_supply=("猎聘", 104, 84))
        self.assertIn("旺季用来补新的", got)
        self.assertIn("你把猎聘关掉了", got)

    def test_the_season_line_is_unchanged_without_it(self):
        import datetime as dt
        got = bd.season_note(self.SLACK, dt.date(2026, 8, 24), "在职",
                             ready=60)
        self.assertIn("旺季用来补新的", got)
        self.assertNotIn("关掉了", got)

    def test_the_restock_branch_carries_it(self):
        """锚点那句 2026-10-14 改过（「跑一轮补货」→「跑一轮 /job-auto 补货」）。

        **锚点跟着文案走，判据没变**：要验的还是「关掉了一家主力渠道时，
        补货那条建议会把这件事说出来」，而不是那句文案长什么样。
        原来那句「跑一轮补货，抓完会自动评分排序」是 2026-08-13 写的，
        而同一支的命令当天就已经该是 `/job-auto`（它抓完不出材料）——
        2026-10-14 一并改对。
        """
        i = BD.index("越少越不该停下找岗")
        self.assertIn("off_supply_note", BD[i:i + 400])

    def test_the_exporter_feeds_it(self):
        self.assertIn('counts["off_supply"] = off_supply(_portals)', EX)

    def test_the_portals_are_computed_before_the_advice(self):
        """算在建议之后的话，建议手上永远没有渠道信息 —— 那正是原来的样子。"""
        self.assertLess(EX.index("_portals = portal_rows("),
                        EX.index("ns_text, ns_cmd = next_step("))

    def test_the_payload_reuses_that_same_result(self):
        """算两遍会多读一次详情库，而且两份哪天不一致，两处就各说各的。"""
        self.assertIn('"portals": _portals,', EX)
        # 数**调用**次数（排掉 `def` 那一行）。别按整串比：那次调用是折行的，
        # 拿一行的字面去数会得到 0，然后这条永远绿。
        calls = EX.count("portal_rows(") - EX.count("def portal_rows(")
        self.assertEqual(calls, 1, f"portal_rows 被调了 {calls} 次")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：这句话对他现在真的会出现，而且数是真的。"""

    def _live(self):
        p = ROOT / "web" / "public" / "data.json"
        if not p.is_file():
            self.skipTest("还没导出过面板数据")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_it_currently_fires(self):
        """**他哪天把那家开回来，这条就 skip** —— 那才是它想要的结局。"""
        d = self._live()
        got = ex.off_supply(d.get("portals") or [])
        if not got:
            self.skipTest("没有关着的主要供给了 —— 好事")
        self.assertGreater(got[2], 50)

    def test_the_panel_text_actually_says_it(self):
        d = self._live()
        if not ex.off_supply(d.get("portals") or []):
            self.skipTest("这条现在不该出现")
        self.assertIn("关掉了", (d.get("nextStep") or {}).get("text") or "",
                      "算出来了却没印到那句话里 —— 中间断了一层")

    def test_the_closed_one_really_out_supplied_the_open_ones(self):
        """这一整条建立在「它一家顶过其余全部」上。"""
        d = self._live()
        rows = d.get("portals") or []
        if not rows:
            self.skipTest("没有渠道数据")
        off = [p for p in rows if not p.get("enabled")]
        if not off:
            self.skipTest("全开着")
        top = max(off, key=lambda p: p.get("everSellable") or 0)
        rest = sum(p.get("everSellable") or 0 for p in rows if p is not top)
        self.assertGreater(top.get("everSellable") or 0, rest)


if __name__ == "__main__":
    unittest.main()
