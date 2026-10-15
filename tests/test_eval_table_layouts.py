"""评估表格的列布局有多种，解析必须按**表头名**定位，不能写死下标。

## 这是同一类 bug 的第四次

前三次：
1. 话术标题的「渠道 N：」前缀 → `_section` 只认关键词紧跟 `##`
2. 邮件主题的加粗冒号位置 → `**主题**：` vs `**主题：**`
3. 综合得分的三种写法 → `综合得分：64/100` / `约 62/100` / 写成加权算式

这次是**列布局**。实测 4 份真实产出里有两种表：

    | 维度 | 分数 | 说明 |            ← 3 列，分数在第 2 列
    | 维度 | 权重 | 分 | 依据 |         ← 4 列，分数在第 3 列

导出器写死了 `row[2]` 是分数、并要求 `len(row) >= 4`，于是 **3 列的表整张被丢掉**
——4 份深评里 3 份的四维数据凭空消失，页面上技能列显示「—」。

共同形状始终一样：**AI 按 markdown 习惯写出多种合法变体，解析器只认一种，
静默丢数据**。所以规则是：**读 AI 写的表，一律按表头名定位列。**
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import export_web_data as ex  # noqa: E402
from _live import is_gate_fail  # noqa: E402

THREE_COL = """## 四维打分

| 维度 | 分数 | 说明 |
|---|---|---|
| 技能与经验 | 76 | AIGC 内容全链路 |
| 薪资与职级 | 46 | 年包低于期望 |
| 强度与公司性质 | 62 | 港股上市 |
| 通勤与地点 | PASS | 上海-黄浦 |
| 发展与风险 | 70 | 新兴上行方向 |
"""

FOUR_COL = """## 四维打分

| 维度 | 权重 | 分 | 依据 |
|---|---|---|---|
| 技能与经验 | 30% | **55** | 见下 |
| 薪资与职级 | 25% | **72** | 区间覆盖期望 |
| 强度与公司性质 | 20% | **62** | 创业板上市 |
| 发展与风险 | 25% | **58** | 见下 |
"""

# 列顺序换一换也要认
SHUFFLED = """## 四维打分

| 维度 | 依据 | 分 |
|---|---|---|
| 技能与经验 | 直接对口 | 88 |
| 薪资与职级 | 高于期望 | 85 |
"""


def dims(text):
    return {d["name"]: d for d in ex.parse_dimensions(text)}


class BothLayoutsParse(unittest.TestCase):
    def test_three_column_layout(self):
        d = dims(THREE_COL)
        self.assertIn("技能与经验", d, "3 列的表被整张丢掉了")
        self.assertEqual(d["技能与经验"]["score"], 76)
        self.assertEqual(d["薪资与职级"]["score"], 46)

    def test_four_column_layout(self):
        d = dims(FOUR_COL)
        self.assertEqual(d["技能与经验"]["score"], 55)
        self.assertEqual(d["技能与经验"]["weight"], 30)
        self.assertEqual(d["发展与风险"]["score"], 58)

    def test_column_order_does_not_matter(self):
        """按表头名定位，换列序照样认。"""
        d = dims(SHUFFLED)
        self.assertEqual(d["技能与经验"]["score"], 88)
        self.assertEqual(d["薪资与职级"]["score"], 85)

    def test_weight_absent_is_zero_not_crash(self):
        d = dims(THREE_COL)
        self.assertEqual(d["技能与经验"]["weight"], 0)

    def test_pass_fail_row_yields_no_score(self):
        """通勤是 Pass/Fail 的门，不该被当成分数。"""
        d = dims(THREE_COL)
        self.assertIsNone(d["通勤与地点"]["score"])

    def test_note_comes_from_the_reason_column(self):
        d = dims(THREE_COL)
        self.assertIn("AIGC", d["技能与经验"]["note"])
        d4 = dims(FOUR_COL)
        self.assertIn("区间覆盖期望", d4["薪资与职级"]["note"])


def _has_dim_section(t: str) -> bool:
    """这份评估里有没有评分明细那一节。

    别名从 `export_web_data` 取，不在这里抄字面量：模板的标题按措辞表从
    「四维打分」改成了「评分明细」，抄一份的话新产出的评估会全被跳过，
    用例静默变空转。
    """
    return any(a in t for a in ex.DIM_SECTION_ALIASES)


class TheGateFailExemptionDoesNotWiden(unittest.TestCase):
    """豁免硬门 FAIL 的是「语法」，**放宽它的代价是把真故障放过**。

    下面这几条钉的是**反方向**：放宽判据最容易出的事故不是漏认，而是
    认得太宽——把一份正常打了分、只是解析器读不出的评估也当成「框架规定
    不打分」，于是守卫再也不红。实测 464 份里这类有 **0** 份，那是因为
    标题锚在 `##` 上；哪天有人图省事改成全文搜「不满足硬性条件」，
    硬性条件那张表里逐条的「不满足」就会把打分的那份一起吞掉。

    这是 `04-job-evaluation.md` 的硬性条件表**逐行**都在写「不满足」的那种
    文件——它打了分，却处处命中这三个字面量。
    """

    SCORED_WITH_FAILING_ROWS = """# 深评：某公司 - 某产品经理

- 评估日期：2026-10-13

## 硬性条件

| 门槛 | 判定 | 依据 |
|---|---|---|
| 工作年限 | **不满足** | JD 写 5 年，他 3 年 |
| 候选人明确排除 | 不满足 | 无 |
| 年龄 | 不适用 | JD 没写 |

## 四维打分

| 维度 | 权重 | 分 | 依据 |
|---|---|---|---|
| 技能与经验 | 30% | **55** | 见下 |
| 薪资与职级 | 25% | **62** | 区间覆盖期望 |
"""

    def test_a_scored_evaluation_is_not_exempted(self):
        self.assertFalse(
            is_gate_fail(self.SCORED_WITH_FAILING_ROWS),
            "一份打了分的评估被判成硬门 FAIL —— 守卫从此再也抓不到真故障")

    def test_each_known_phrasing_is_recognised(self):
        for phrase in ("不打分（硬性条件没过）", "结论：不满足硬性条件", "| FAIL |"):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_gate_fail(f"## 某节\n\n{phrase}\n"))

    def test_the_heading_form_is_recognised(self):
        """第四种写法：结论直接写进 `##` 标题。

        实测活动用户 2026-10-14：`某上海大型智能硬件公司_解决方案产品经理
        （AI启蒙教育）` 走的是 `## 不满足硬性条件，不打分` —— 两种旧写法
        都没命中，红了三条守卫，而**那份评估写得完全正确**
        （`04-job-evaluation.md`：「硬门不过的职位不打分」）。
        """
        self.assertTrue(is_gate_fail("## 不满足硬性条件，不打分\n\n后文。\n"))


class RealEvaluationsAllYieldDimensions(unittest.TestCase):
    """控制测试：仓库里每一份真实评估都必须解析出评分明细。"""

    def test_every_real_evaluation_has_dimensions(self):
        files = sorted(ROOT.glob("users/*/documents/applications/*/evaluation.md"))
        if not files:
            self.skipTest("这个 clone 里没有真实投递目录")
        bad = []
        for f in files:
            t = f.read_text(encoding="utf-8", errors="replace")
            if not _has_dim_section(t) or is_gate_fail(t):
                continue          # 没有这一节的、以及硬性条件没过（框架规定不打分）的不算
            got = [d for d in ex.parse_dimensions(t) if d["score"] is not None]
            if not got:
                bad.append(f.parent.name)
        self.assertFalse(bad, f"这些评估的四维表解析不出分数：{bad}")

    def test_skill_dimension_is_found_in_every_real_evaluation(self):
        """技能与经验是页面上要单独显示的那一维，一份都不能漏。

        与上面那条一样要豁免硬门 FAIL：框架规定它**不打分**，没有评分明细是对的。
        这条原来漏了这个豁免——而且是靠一个巧合才一直绿的：别名表里的「打分」
        会匹配到「**不**打分（硬性条件没过）」这句话，于是硬门评估被
        `_has_dim_section` 判成「有这一节」，只是此前库里没有这种评估罢了。
        """
        files = sorted(ROOT.glob("users/*/documents/applications/*/evaluation.md"))
        if not files:
            self.skipTest("这个 clone 里没有真实投递目录")
        bad = []
        for f in files:
            t = f.read_text(encoding="utf-8", errors="replace")
            if not _has_dim_section(t) or is_gate_fail(t):
                continue
            names = [d["name"] for d in ex.parse_dimensions(t)]
            if not any("技能" in n for n in names):
                bad.append(f"{f.parent.name}({names})")
        self.assertFalse(bad, f"这些评估里找不到技能与经验：{bad}")


if __name__ == "__main__":
    unittest.main()
