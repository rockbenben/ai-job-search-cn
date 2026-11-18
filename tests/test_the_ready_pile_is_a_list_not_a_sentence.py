# -*- coding: utf-8 -*-
"""「你手上已经有 62 个岗材料是齐的」——说完了，然后呢？

发出去是整条流水线里**唯一要人做的那一步**
（`AGENTS.md`「只有一处要人：投出去那一下」）。
而这 62 个的清单此前**只是一句话**：读完还得自己去
222 行的「可以考虑」里翻。

流水线第 3 格「材料就绪 142」是可点的，但它是**累计漏斗**口径 ——
142 里 80 个已经投过了（漏斗该这么算，但「我现在该做什么」不是漏斗）。
点开给一份 56% 已完成的清单，等于没给。

所以给 `funnels` 加一个 `ready` 键（有材料 且 未投），那句话里的数字变成入口：
点「材料已备」那一档只看这批，再点一次取消。

**数和行由同一份 `funnels` 出，按构造相等** —— 这一页反复栽过的
「格子上的数 ≠ 点开看到的行数」在这里不可能发生（那三次的教训写在
`FUNNEL_OF` 上面那段注释里）。
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import export_web_data as X  # noqa: E402
from jsx import POSITION_VIEW  # noqa: E402

APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")


class TheKeyMeansReadyToSend(unittest.TestCase):
    #: `applied` 存的是**台账那一行**（dict），不是布尔 —— 下游还要读它的
    #: `status` 判「面试中」。夹具写成 `True` 会在那一行炸掉，而那正好证明
    #: 这个字段是有结构的。
    APPLIED = {"status": "applied", "date": "2026-08-10"}

    def _f(self, **job):
        return X.funnels_of({"materials": None, "applied": None, **job})

    def test_materials_and_not_applied(self):
        self.assertIn("ready", self._f(materials={"greeting": "您好"}))

    def test_already_sent_is_not_ready(self):
        f = self._f(materials={"greeting": "您好"}, applied=self.APPLIED)
        self.assertNotIn("ready", f)
        self.assertIn("materials", f, "累计漏斗那一格不该被这次改动动到")

    def test_no_materials_is_not_ready(self):
        self.assertNotIn("ready", self._f())

    def test_parked_jobs_get_nothing_at_all(self):
        """搁置的（不投 / 已下线 / 重复挂法）本来就不进任何一格。"""
        for k in ("skipped", "expired", "dupOf"):
            with self.subTest(k=k):
                f = X.funnels_of({"materials": {"greeting": "x"}, k: True})
                self.assertEqual(f, [])

    def test_the_funnel_stays_cumulative(self):
        """**别把 `materials` 改成互斥的。** 那一格是漏斗，投出去的岗
        确实走过这一步；改了，2638→2450→142→85 那条线就断了。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        i = src.index("def funnels_of(")
        self.assertIn("这里是**累计口径**（漏斗）", src[i:i + 1400])


class TheNumberIsTheEntryPoint(unittest.TestCase):
    def _seg(self):
        i = APP.index("mat-gap-have")
        return APP[i:i + 1400]

    def test_it_is_a_button(self):
        self.assertIn("have-jump", self._seg(), "那个数还是一句话，点不开")

    def test_it_toggles_that_filter(self):
        seg = self._seg()
        self.assertRegex(seg, r'changeFunnel\(funnel === "ready" \? "" : "ready", true\)',
                         "点第二下不取消，用户会以为卡住了")

    def test_it_reports_its_own_state(self):
        """筛选是有状态的东西，读屏和肉眼都要看得出它开着。"""
        self.assertIn('aria-pressed={funnel === "ready"}', self._seg())
        self.assertIn('.have-jump[aria-pressed="true"]', CSS, "按下没有视觉反馈")


    def test_the_ready_view_has_a_named_control(self):
        self.assertIn('{ id: "ready", label: "材料已备", count: funnelCounts.ready }', APP)
        self.assertIn(POSITION_VIEW, APP)

    def test_the_filter_counter_knows_it(self):
        """`funnelCounts` 少一个键，格子上的数会在这个筛选下算错。"""
        i = APP.index("const funnelCounts")
        self.assertIn("ready: 0", APP[i:i + 300])

    def test_the_state_type_allows_it(self):
        self.assertRegex(APP, r'useState<"" \| "materials" \| "ready" \|')


class TheCountEqualsTheRows(unittest.TestCase):
    """这一页栽过三次「格子上的数 ≠ 点开看到的行数」。这次按构造相等。"""

    def test_both_come_from_the_same_field(self):
        seg = APP[APP.index("const readyToSend"):][:400]
        self.assertIn("j.materials", seg)
        self.assertIn("!applied(j)", seg)
        self.assertIn("(j.funnels ?? []).includes(funnel)", APP,
                      "筛选不再走 funnels 了 —— 两边又会各算一遍")

    def test_on_real_data_they_agree(self):
        data = ROOT / "web" / "public" / "data.json"
        if not data.is_file():
            self.skipTest("还没导出面板数据")
        snap = json.loads(data.read_text(encoding="utf-8"))
        rows = sum(1 for j in snap["jobs"] if "ready" in (j.get("funnels") or []))
        self.assertEqual(rows, snap["nextStep"]["ready"],
                         f"点开 {rows} 行，而那句话说 {snap['nextStep']['ready']} 个")

    # 「这一块的变量都定义了没」归 `test_css_and_cjk_text.EveryCssVarIsDefined`
    # 全库扫（2026-08-31 把五份按块扫的抄件一起删了）—— 抄件用的是正本
    # 已经修掉的写法：`(?m)^\s*--x\s*:` 一行里只认得第一个变量。


if __name__ == "__main__":
    unittest.main()
