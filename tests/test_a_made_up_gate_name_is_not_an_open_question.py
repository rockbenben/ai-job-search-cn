# -*- coding: utf-8 -*-
"""04 说「自造的门名和没判一样」，而面板拿它去催用户问一件不是门的事。

`04-job-evaluation.md` 第一步写得很死：

> ⚠️ **门名也只许用下表这七个——自造的门名和没判一样，查不出来。**

并给了归位规则：地点、英语、年龄这类「候选人自己不接受 / 达不到」的归
**「候选人明确排除」**；技术栈、专业、行业经验这类「能力够不够」的**本来就是
第 1 维要打的分，不是门**。

规则一直在。审计也一直在报（行标题「硬性条件：门名没按七道正规名写」）。
**可面板把这几行当成「没查的硬性条件」在催用户去问。**

实测活动用户 2026-08-25：

    硬性条件表 1699 行，门名不在七道里的      122 行
      地点 47 · 专业 46 · 专业相符 8 · 英语 7 · 对外持股 3 ·
      工作地点 3 · 编码能力 2 · 年龄 2 · 其余各 1
    其中判定是 `unknown` 的                    6 行
    因此印着「投之前先问清 N 条」而那 N 条根本不是门的岗   **6 个**

那 6 个的数一律是 1 → 去掉之后是 0，**整句话都不该出现**。其中两个是他分数
最高的（77 分强匹配、71 分值得投）。而那句话的下半句写着「JD 和公司资料里都
没写」—— 实测那几行的依据里引着 JD 原话，**那半句是假的**。

最扎眼的一条：年龄那一行的依据里，评估自己写着「不当硬性条件判」——
明说了它不是一道门，面板照样让他去问。

## 只打标，不删行

那一行是审计要人去改的证据，删掉等于把问题藏起来。所以行照渲染，只是
**不算一道没查的硬性条件**，并在名字后面标一句「不算硬性条件」。

判据留在 Python 那一份（`_cli.gate_of`），TS 只读标志 —— 形状同
`Dimension.weighted`（那也是「在表里但不是那四维」）。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import _cli  # noqa: E402
import export_web_data as ex  # noqa: E402

WEB = ROOT / "web" / "src"
EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
TYPES = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
READOUT = (ROOT / "web" / "src" / "components"
           / "JobReadout.tsx").read_text(encoding="utf-8")
STAMP = (ROOT / "web" / "src" / "components"
         / "GateStamp.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
FRAME = (ROOT / "workflows" / "reference"
         / "04-job-evaluation.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?|//:?|\*)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


SEC = "## 硬性条件\n"


class TheParserMarksThem(unittest.TestCase):
    def test_an_off_spec_name_is_marked(self):
        got = ex.parse_gates(SEC + "| 门槛 | 判定 | 依据 |\n|---|---|---|\n"
                             "| 专业 | 未知 | JD 列了清单 |\n")
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].get("offSpec"))

    def test_a_real_gate_is_not_marked(self):
        got = ex.parse_gates(SEC + "| 门槛 | 判定 | 依据 |\n|---|---|---|\n"
                             "| 学历与院校 | PASS | 本科及以上 |\n")
        self.assertEqual(len(got), 1)
        self.assertNotIn("offSpec", got[0])

    def test_all_seven_canonical_names_pass_through_clean(self):
        for g in _cli.GATES:
            with self.subTest(g=g):
                got = ex.parse_gates(SEC + "| 门槛 | 判定 | 依据 |\n|---|---|---|\n"
                                     f"| {g} | PASS | x |\n")
                self.assertNotIn("offSpec", got[0], f"「{g}」被当成自造名了")

    def test_the_row_is_never_dropped(self):
        """**只打标，不删行。** 删掉等于把审计要人改的证据藏起来。"""
        got = ex.parse_gates(SEC + "| 门槛 | 判定 | 依据 |\n|---|---|---|\n"
                             "| 年龄 | 未知 | JD 写 35 岁以下 |\n"
                             "| 学历与院校 | PASS | 本科 |\n")
        self.assertEqual([g["name"] for g in got], ["年龄", "学历与院校"])

    def test_every_off_spec_mark_borrows_the_one_judge(self):
        """哪一处另写一份七道门的词表，两处迟早分叉。

        **2026-08-27 从「第一处」改成「每一处」。** 那天 `"offSpec": True`
        由一处变成两处：粗筛那条路（`gates_from_breakdown`，读的是
        `rank_breakdown` 里存的门判定）也要标。而这条原来用 `EX.index()`
        只看第一处 —— 新函数恰好排在 `parse_gates` 前面，于是它去检查了
        新代码、还找不到旧写法（`row[0]` vs `name`），当场红。

        「只看第一处」本身就是 `test_test_anchors_are_unambiguous` 盯的形状：
        断言可能落在别人的文字上，而且平时不会红。逐处验才是这条的本意。
        """
        marks = [m.start() for m in re.finditer(r'"offSpec": True', EX)]
        self.assertGreaterEqual(len(marks), 2,
                                "只找到一处 —— 粗筛那条路的标记没了？")
        for i in marks:
            with self.subTest(at=EX[:i].count(chr(10)) + 1):
                self.assertIn("_cli.gate_of(", EX[i:i + 120],
                              "这一处自己判了门名，没走那份唯一的词表")

    def test_the_reason_is_recorded(self):
        i = EX.index("# **门名不在七道里的，不是一道硬性条件。**")
        seg = flat(EX[i:EX.index('"offSpec": True', i)])
        self.assertRegex(seg, r"自造的门名和没判一样")
        self.assertRegex(seg, r"\*\*面板却把这几行当成没查的硬性条件在催用户去问\*\*")
        self.assertIn("2026-08-25", seg)

    def test_it_carries_the_measurement(self):
        i = EX.index("# **门名不在七道里的，不是一道硬性条件。**")
        seg = EX[i:EX.index('"offSpec": True', i)]
        for n in ("1699", "122", "`地点` 47", "`专业` 46"):
            with self.subTest(n=n):
                self.assertIn(n, seg)

    def test_it_says_why_the_row_stays(self):
        i = EX.index("# **门名不在七道里的，不是一道硬性条件。**")
        seg = flat(EX[i:EX.index('"offSpec": True', i)])
        self.assertRegex(seg, r"\*\*只打标，不删行\*\*")
        self.assertRegex(seg, r"删掉等于把问题藏起来")

    def test_the_rule_it_leans_on_still_stands(self):
        self.assertIn("**门名也只许用下表这七个——自造的门名和没判一样，查不出来。**",
                      FRAME)

    def test_the_relocation_rule_still_stands(self):
        """地点/英语/年龄 归哪儿、专业/技术栈为什么不是门 —— 引的就是这两条。"""
        s = flat(FRAME)
        self.assertRegex(s, r"\*\*地点、英语、年龄这类「候选人自己不接受 / 达不到」的\*\* → 归")
        self.assertRegex(s, r"它们\*\*本来就是第 1 维要打的分\*\*，\s*不是门")


class NoneOfTheThreeCountersUsesIt(unittest.TestCase):
    """三处各数一遍 —— 漏掉任何一处，那句话就还在。

    2026-08-31 起三处走同一个 `countsAsUnknown`（`GateStamp` 是它的家）。
    **判据跟着从「每处都写着 `!g.offSpec`」改成「每处都过那个函数」**：
    钉字面表达式等于钉实现位置 —— 收掉重复时它会把收拢本身判成违规，
    而「三处不许各判各的」这件事一个字没变。

    多加一条：那个表达式在整棵 `web/src` 只许有一处（就是函数体里那处）。
    原来三处各写一遍，加一个条件就要改三处 —— 而 `assumed` 当初就只补进了
    其中两处（它是**另一类**、另一句话，不能相加，所以那不是 bug；
    但「加一处漏一处」的形状是真的）。
    """

    #: 那个复合判据的字面写法。只许出现在 `countsAsUnknown` 的函数体里。
    RAW = 'g.state === "unknown" && !g.offSpec'

    def test_the_readout_headline_skips_them(self):
        i = READOUT.index("const unknowns = job.gates.filter(")
        self.assertIn("countsAsUnknown", READOUT[i:i + 200])

    def test_the_section_note_skips_them(self):
        """「有一条不满足就别投 ·『还没查到』不算满足」那句。"""
        i = READOUT.index('g.state === "fail" ||')
        self.assertIn("countsAsUnknown(g)", READOUT[i:i + 200])

    def test_the_grid_footer_skips_them(self):
        i = STAMP.index("const unknownCount = gates.filter(")
        self.assertIn("countsAsUnknown", STAMP[i:i + 160])

    def test_the_readout_imports_it_rather_than_rewriting(self):
        """引进来，不是自己再写一份 —— 后者正是这条要防的。

        锚点用 `from "./GateStamp"`（全文唯一）。第一版拿 `/**` 当「import 区
        到此为止」的界标，而它在那个文件里出现 **10 次** ——
        `test_test_anchors_are_unambiguous` 当场抓红：`index()` 取第一处，
        断言可能落在别人的文字上**而且不会红**。
        """
        i = READOUT.index('from "./GateStamp"')
        self.assertIn("countsAsUnknown", READOUT[READOUT.rindex("import", 0, i):i],
                      "没从 GateStamp 引进来 —— 八成又自己写了一份")

    def test_the_predicate_has_exactly_one_home(self):
        homes = {f.relative_to(WEB).as_posix(): t.count(self.RAW)
                 for f in WEB.rglob("*.ts*")
                 for t in [f.read_text(encoding="utf-8")]
                 if self.RAW in t}
        self.assertEqual(sum(homes.values()), 1,
                         "「算不算还没查到」又被抄了一份。住址：" + repr(homes))
        self.assertEqual(list(homes), ["components/GateStamp.tsx"],
                         "唯一那份不在 countsAsUnknown 那里：" + repr(homes))

    def test_the_grid_footer_says_why(self):
        """下半句「JD 和公司资料里都没写」是假的 —— 那才是这一处的要害。"""
        i = STAMP.index("// **自造门名不进这个数**")
        seg = flat(STAMP[i:STAMP.index("const unknownCount", i)])
        self.assertRegex(seg, r"问的是一件根本不存在的门")
        self.assertRegex(seg, r"那半句是\*\*假的\*\*")

    def test_that_half_sentence_really_is_there(self):
        self.assertIn("JD 和公司资料里都没写", STAMP)

    def test_the_assumed_counter_is_untouched(self):
        """「按假设值判的」是另一回事，一个字不许动。"""
        self.assertIn('const assumedCount = gates.filter((g) => g.assumed).length;',
                      STAMP)


class TheRowStillShowsAndSaysWhatItIs(unittest.TestCase):
    def test_the_marker_renders(self):
        self.assertIn('{g.offSpec && <span className="gate-offspec">不算硬性条件</span>}',
                      STAMP)

    def test_it_sits_next_to_the_name(self):
        """挨着门名，不是挨着依据 —— 依据那行是灰的小字，标在那儿看不见。"""
        i = STAMP.index('className="gate-offspec"')
        j = STAMP.rindex("{g.name}", 0, i)
        k = STAMP.index('className="gate-why"')
        self.assertLess(j, i)
        self.assertLess(i, k, "标跑到依据后面去了")

    def test_it_says_why_the_marker_is_needed(self):
        i = STAMP.index("{/* 行留着（审计要人去改它）")
        seg = flat(STAMP[i:STAMP.index('className="gate-offspec"', i)])
        self.assertRegex(seg, r"一个「还没查到」的章会读成「这条没过关」")

    def test_the_style_exists(self):
        self.assertIn(".gate-offspec {", CSS)

    def test_the_style_does_not_stretch_chinese(self):
        """等宽加字距只适用于拉丁文（AGENTS.md 末尾那条）。"""
        i = CSS.index(".gate-offspec {")
        self.assertNotIn("letter-spacing", CSS[i:CSS.index("}", i)])

    def test_the_type_exists(self):
        self.assertIn("offSpec?: boolean;", TYPES)

    def test_the_type_says_where_the_judge_lives(self):
        i = TYPES.index("offSpec?: boolean;")
        seg = flat(TYPES[max(0, i - 900):i])
        self.assertRegex(seg, r"判据在 `_cli\.gate_of`，别在 TS 里\s*再写一份词表")
        self.assertRegex(seg, r"行照样渲染")

    def test_it_follows_the_sibling_pattern(self):
        """`Dimension.weighted` 是同一个形状：在表里，但不是那四维。"""
        self.assertIn("weighted?: boolean;", TYPES)
        i = TYPES.index("weighted?: boolean;")
        self.assertRegex(flat(TYPES[max(0, i - 400):i]),
                         r"判据在 `_cli\.is_weighted_dim`")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那批自造名真的在库里，而且真的在冒充待办。"""

    def _data(self):
        p = ROOT / "web" / "public" / "data.json"
        if not p.is_file():
            self.skipTest("还没导出过面板数据")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_off_spec_rows_really_exist(self):
        """**支点。** 一行都没有时这一节没有存在的理由。"""
        d = self._data()
        n = sum(1 for j in d["jobs"] for g in (j.get("gates") or [])
                if g.get("offSpec"))
        if not n:
            self.skipTest("门名已经全归位了 —— 好事")
        self.assertGreater(n, 20, f"只剩 {n} 行，这一节的实测数要重看")

    def test_the_mark_matches_the_judge(self):
        """现算：面板上每一行的标志都跟 `_cli.gate_of` 对得上。"""
        d = self._data()
        bad = []
        for j in d["jobs"]:
            for g in j.get("gates") or []:
                want = not _cli.gate_of(g.get("name") or "")
                if bool(g.get("offSpec")) != want:
                    bad.append((j["id"], g["name"]))
        self.assertEqual(bad[:5], [], f"{len(bad)} 行标错了")

    def test_it_really_silenced_some_false_asks(self):
        """改前印着「先问清」的岗里，有几个那 N 条全是自造名。"""
        d = self._data()
        before = [j for j in d["jobs"]
                  if any(g["state"] == "unknown" for g in (j.get("gates") or []))]
        after = [j for j in before
                 if any(g["state"] == "unknown" and not g.get("offSpec")
                        for g in j["gates"])]
        if len(before) == len(after):
            self.skipTest("没有一个岗因此变干净 —— 那批已经归位了")
        self.assertLess(len(after), len(before))

    def test_the_ones_it_silenced_had_nothing_to_ask(self):
        """**不是少问几条，是那句话整个不该出现。** 剩下 0 条才算修对。"""
        d = self._data()
        for j in d["jobs"]:
            gates = j.get("gates") or []
            unk = [g for g in gates if g["state"] == "unknown"]
            if not unk or any(not g.get("offSpec") for g in unk):
                continue
            # 这个岗改前会印「先问清 N 条」，改后一条都不剩 —— 正是要的
            self.assertTrue(all(g.get("offSpec") for g in unk))

    def test_the_real_unknowns_still_ask(self):
        """别把真门也一起消音了。"""
        d = self._data()
        n = sum(1 for j in d["jobs"]
                if any(g["state"] == "unknown" and not g.get("offSpec")
                       for g in (j.get("gates") or [])))
        if not n:
            self.skipTest("库里没有真正判不了的门了")
        self.assertGreater(n, 0)

    def test_the_audit_still_reports_them(self):
        """打标不等于修好 —— 审计那条得继续喊，不然没人去改门名。

        **两边判的必须是同一批。** 面板上一行都没有时审计也该闭嘴；还有行时
        它不许因为「都标过了」就不喊 —— 标志是给读的人看的，审计是催人去改的。

        原来这里拿「审计报没报」当跳过条件、再断言它报了，两条路都不会红。（判据见 `test_no_assertion_is_dead_on_arrival.py` 第 6 种）
        """
        import audit_pipeline as ap
        seen, details = ap.load(user_or_skip())
        ap._USER[:] = [user_or_skip()]
        kinds = [k for _n, fn in ap.CHECKS for _l, k, _m in fn(seen, details)]
        panel = sum(1 for j in self._data()["jobs"]
                    for g in (j.get("gates") or []) if g.get("offSpec"))
        # **两条都算。** 门名有两个住址：库里的判词 / 明细，和深评文件里那张表 ——
        # 审计按数据来源拆成了两条检查（2026-08-30），而面板那一列两边都可能来
        # （`parse_gates` 读文件，读不到才退回 `gates_from_breakdown` 读库）。
        # 只认其中一条的话，把库那边清干净就会红 —— 而面板上一行没少。
        # 行标题 2026-09-01 从「硬门：…」改成「硬性条件：…」
        # （`test_display_wording`：印给用户的标题不许带内部词）。
        # 这里认的是**那两条检查**，不是某一种写法 —— 只查「门名」这个词。
        shouting = any("门名" in k for k in kinds)
        self.assertEqual(
            shouting, panel > 0,
            f"面板上有 {panel} 行自造名，审计却"
            f"{'不喊' if panel else '还在喊'} —— 两边判的该是同一批")


if __name__ == "__main__":
    unittest.main()
