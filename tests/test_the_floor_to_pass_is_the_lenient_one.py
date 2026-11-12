# -*- coding: utf-8 -*-
"""`--annual-floor` 该传哪个数 —— 规则与例子曾经各说各的。

资料里的薪资常常不止一个数：一个常规底线，加一句「方向极对的岗可以降到 X 谈」。
预筛只有标题和薪资串，**判不了方向对不对**（那是评估那一步才知道的事），
而 `--annual-floor` 又是四条规则里**唯一能结案**的（不可逆）。所以它只能传
**低的那个**：用常规底线，误杀的恰好就是弹性条款专门要保护的那一批。

## 事故形状：规则在一处，可复制的例子在另一处，两处不是一个数

实测（2026-08-26 量这份语料）：232 条按 42 万结案、64 条按 45 万 ——
**同一个参数两个数在轮流用**，同一个岗这轮死下轮活，不可复现。
根因是 `job-auto.md` 的取值行写「可接受底线」（45），而 `job-rank.md` 与
`prescreen.py --help` 里可复制的例子写的是 42 —— **执行者复制的是例子。**

那 64 条里有 4 个年包上沿落在 42–45 万之间，方向极对的 0 个 —— 没造成实际损失，
但那是运气（那 4 个本来就在别的职能线上），不是设计。

## 这里钉两半

**取值规则**同向（下面第一组），以及支撑它的那条性质：**底线传得越低，
结案的岗只会更少，绝不会更多**（第二组）。第二组才是「取最宽」安全的前提 ——
比较符一旦写反，第一组那套说辞就全部失效。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import prescreen  # noqa: E402

AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
SRC = (ROOT / "tools" / "prescreen.py").read_text(encoding="utf-8")


class TheSourcingRuleSaysTakeTheLenientOne(unittest.TestCase):
    def _row(self) -> str:
        rows = [ln for ln in AUTO.splitlines() if ln.startswith("| `--annual-floor`")]
        self.assertEqual(len(rows), 1, f"取值表里的那一行不是一行：{rows}")
        return rows[0]

    def test_the_table_row_names_the_widest_floor(self):
        row = self._row()
        self.assertIn("最宽", row, "取值规则没说「取最宽的那个下限」")

    def test_the_table_row_no_longer_names_the_regular_floor(self):
        """「可接受底线」是资料里**常规**的那个数 —— 正是不该传的那个。"""
        self.assertNotIn("可接受底线", self._row())

    def test_the_help_text_says_the_same_thing(self):
        """`--help` 是执行者在复制例子之前会看的那一处，两处必须同向。"""
        i = SRC.index('"--annual-floor"')
        seg = SRC[i:SRC.index('"--off-track"', i)]
        self.assertIn("传低的那个", seg)
        self.assertIn("判不了方向", seg, "没说清为什么不能用常规底线")
        self.assertIn("唯一能结案", seg, "没说清它不可逆 —— 那才是要保守的理由")

    def test_the_incident_is_on_record(self):
        self.assertIn("同一个参数两个数在轮流用", AUTO)


class ALowerFloorNeverClosesMoreJobs(unittest.TestCase):
    """单调性：底线只要不升，结案集合只会缩不会涨。

    「取最宽的那个数是安全的」这句话，全部的份量都压在这条性质上。
    """

    JOBS = [
        {"title": "AI产品经理", "salary": "25-28k", "salaryMonths": 16},   # 44.8 万
        {"title": "AI产品经理", "salary": "15-30k", "salaryMonths": 14},   # 42.0 万
        {"title": "AI产品经理", "salary": "40-70k", "salaryMonths": 16},   # 上沿远超
        {"title": "AI产品经理", "salary": "10-12k", "salaryMonths": 12},   # 远低
        {"title": "AI产品经理", "salary": ""},                             # 判不了
        {"title": "AI产品经理", "salary": "30-35k"},                       # 未标薪数
    ]

    def _closed(self, floor: float) -> set:
        return {i for i, e in enumerate(self.JOBS)
                if prescreen.rule_annual(e, floor) is not None}

    def test_lowering_the_floor_only_shrinks_the_closed_set(self):
        floors = [60.0, 50.0, 45.0, 42.0, 30.0]
        sets = [self._closed(f) for f in floors]
        for (hf, hi), (lf, lo) in zip(zip(floors, sets), zip(floors[1:], sets[1:])):
            self.assertTrue(lo <= hi,
                            f"底线从 {hf} 降到 {lf}，结案的岗反而多了："
                            f"{sorted(lo - hi)} —— 比较符写反了")

    def test_the_two_floors_in_play_differ_by_exactly_the_jobs_in_between(self):
        """42 与 45 之间那一档，正是弹性条款要保护的那批。"""
        extra = self._closed(45.0) - self._closed(42.0)
        self.assertEqual(sorted(extra), [0, 1],
                         "44.8 万和 42.0 万这两个岗，应当只在用常规底线时才被结案")

    def test_an_unreadable_salary_is_never_closed(self):
        """读不出年包 → 不结案。淘汰要保守，这条与「取最宽」是同一个方向。"""
        for floor in (30.0, 45.0, 60.0, 200.0):
            with self.subTest(floor=floor):
                self.assertIsNone(prescreen.rule_annual({"title": "X", "salary": ""}, floor))


if __name__ == "__main__":
    unittest.main()
