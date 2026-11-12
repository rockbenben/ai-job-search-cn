# -*- coding: utf-8 -*-
"""别说「粗筛分偏高」—— 实测正相反，它是保守的。

`job-apply.md` 的批量小结模板原来写死了一句：

> 这 20 个里 N 个只到「可以考虑」，**粗筛分偏高**，下一轮可以先修 `profile`
> 的判据或重跑 `/job-rank`

2026-08-22 拿真实数据对了一遍。库里 80 个岗先粗筛后深评、两个分都留着
（`prev_score` / `rank_score`）：

    深评之后涨了  63    降了  14    不变  3      中位 +5

**粗筛是保守的，不是虚高。** 而且偏差不均匀：

    粗筛 <50    n=45   中位 +6
    粗筛 50-54  n=22   中位 +5
    粗筛 55-59  n= 8   中位 +0
    粗筛 60+    n= 5   中位 +1

低分段偏低五六分，**55 分往上基本准**。所以「这一批多数只到可以考虑」推不出
「粗筛虚高、去修判据」—— 同一批岗深评之后分只会更高一点，档位边界是稳的。

> 这个测量顺带否掉了我自己的另一个念头：「粗筛 55-59 那 59 个岗深评后大概率
> 过 60」。**那一档的中位改动恰恰是 0**（4 涨 3 降）。把只在低分段成立的修正
> 推广到全段，会推出一个反向的建议。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")


class TheFalseClaimIsGone(unittest.TestCase):
    def test_the_summary_no_longer_asserts_inflation(self):
        """这句话会让人去修一个没坏的判据。"""
        m = re.search(r"粗筛分偏高", APPLY)
        if m:
            seg = APPLY[max(0, m.start() - 200):m.start()]
            self.assertIn("别照着说", seg,
                          "「粗筛分偏高」又被当成结论写进小结模板了")

    def test_the_measurement_replaces_it(self):
        self.assertRegex(APPLY, r"粗筛是\*\*保守\*\*的|粗筛是保守的",
                         "没说清偏的是哪一边")

    def test_the_band_table_is_there(self):
        """一个总体中位数会被误用成全段修正 —— 分段的数才拦得住。"""
        for band in ("<50", "50-54", "55-59", "60+"):
            with self.subTest(band=band):
                self.assertIn(band, APPLY, f"分段表里缺 {band}")

    def test_it_says_the_boundary_is_stable(self):
        """结论要落到「所以怎么办」：档位边界稳，别去改判据。"""
        self.assertRegex(APPLY, r"档位边界是稳的",
                         "没说清这个测量对用户意味着什么")

    def test_it_tells_you_how_to_recheck(self):
        """凭印象是这条错结论的来源 —— 要给出重算的办法。"""
        self.assertIn("prev_score", APPLY, "没说清拿哪两列现算")


class TheSummaryStillReportsComposition(unittest.TestCase):
    def test_the_batch_still_gets_a_summary(self):
        """删掉错的诊断，不等于删掉小结本身。"""
        self.assertRegex(APPLY, r"小结里如实说这一批的构成",
                         "把小结整段删了")

    def test_running_to_the_end_is_still_the_rule(self):
        """这一段原本管的是「别因为结论中途停手」，那条不能被顺手改掉。"""
        self.assertIn("不要拿结论当中途退出的理由", APPLY)


if __name__ == "__main__":
    unittest.main()
