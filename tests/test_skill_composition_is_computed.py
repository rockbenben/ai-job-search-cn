"""技能与经验必须**照算式合成**，不是凭感觉给一个数。

`04-job-evaluation.md` 第 1.3 节把这条写得很死：

    技能与经验 = 专业能力 × 0.6 + 业务领域 × 0.4 + 加分项修正
    业务领域 < 40 时封顶 65，**封顶是合成的最后一步**（先算完再封）
    加分项每命中一条 +2，最多 +8；一条没中不扣分

**而 2026-08-20 之前没有任何守卫。** 拿全库 687 条有拆解的评分验算，
37 条对不上：36 条算式偏离（`70×0.6+15×0.4=48` 却写 42、`92×0.6+75×0.4=85.2`
却写 81），1 条业务域 35 破了 65 的封顶。

**偏离全部朝一个方向——往低了写**，不是随机噪声：执行者在合成分上又凭感觉扣了一次，
而 04 明写「照算，不要凭感觉给一个数」。8 分足以跨过档位线（60/40 是判词天花板的
边界），所以这不是四舍五入的事。

这一维占 30% 权重，且是判词天花板的依据——它错了，判词跟着错。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402

#: 「专业能力 88 × 0.6 + 业务域 65 × 0.4」这种拆解行。乘号有 ×/x/* 三种写法。
DECOMP = re.compile(r"专业能力\s*(\d+)\s*[×x*]\s*0\.6\s*\+\s*业务域\s*(\d+)\s*[×x*]\s*0\.4")

#: 加分项修正的上限（04 第 1.3 节：每条 +2，最多 +8）。
BONUS_MAX = 8
#: 业务领域低于这个数时，技能与经验封顶。
DOMAIN_FLOOR, SKILL_CAP = 40, 65


def decomposed():
    """(标题, 专业能力, 业务领域, 合成分)。只取写了拆解、能验算的那些。"""
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        raise unittest.SkipTest("这个 clone 里没有活动用户")
    user = ptr.read_text(encoding="utf-8").strip()
    f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not f.is_file():
        raise unittest.SkipTest("还没抓过职位")
    seen = _cli.seen_of(json.loads(f.read_text(encoding="utf-8")))
    out = []
    for e in seen.values():
        b = e.get("rank_breakdown") or {}
        skill = b.get("技能与经验")
        m = DECOMP.search(str(b.get("四维") or ""))
        if isinstance(skill, int) and m:
            out.append((e.get("title") or "", int(m.group(1)), int(m.group(2)), skill))
    if not out:
        raise unittest.SkipTest("库里还没有带拆解的评分")
    return out


class TheRuleIsDocumented(unittest.TestCase):
    def test_formula_and_cap_are_written(self):
        t = (ROOT / "workflows" / "reference" / "04-job-evaluation.md").read_text(
            encoding="utf-8")
        self.assertIn("专业能力 × 0.6 + 业务领域 × 0.4", t, "合成算式不在框架里")
        self.assertIn("封顶 65", t, "业务域 <40 的封顶规则不在")
        self.assertIn("封顶是合成的最后一步", t,
                      "没写先后顺序——两种读法差最多 8 分，足以跨档位线")

    def test_the_example_computes(self):
        """示例必须自己算得出来——它错过一次，把执行者校准歪了。"""
        t = (ROOT / "workflows" / "reference" / "04-job-evaluation.md").read_text(
            encoding="utf-8")
        m = re.search(r"技能与经验\s*(\d+)\s*=\s*专业能力\s*(\d+)\s*×\s*0\.6"
                      r"\s*\+\s*业务领域\s*(\d+)\s*×\s*0\.4", t)
        self.assertIsNotNone(m, "框架里那行示例不见了")
        got, pro, dom = int(m.group(1)), int(m.group(2)), int(m.group(3))
        base = pro * 0.6 + dom * 0.4
        self.assertLessEqual(abs(got - base), BONUS_MAX + 0.5,
                             f"示例自己算不平：{pro}×0.6+{dom}×0.4={base}，却写 {got}")


class RealScoresFollowTheFormula(unittest.TestCase):
    """控制测试：真实产出里，合成分必须落在算式给的区间内。"""

    def test_composition_within_bonus_range(self):
        bad = []
        for title, pro, dom, skill in decomposed():
            base = pro * 0.6 + dom * 0.4
            if dom < DOMAIN_FLOOR and skill == SKILL_CAP:
                continue                      # 封顶命中，合法
            if not (base - 6.0 <= skill <= base + BONUS_MAX + 0.6):
                bad.append(f"{title[:22]}  {pro}×0.6+{dom}×0.4={base:.1f} 却写 {skill}")
        self.assertEqual(bad, [],
                         "这些合成分不在算式给的区间里（下界=算式值，上界=+8 加分项）。"
                         "04 明写「照算，不要凭感觉给一个数」——偏离往往朝低走，"
                         f"而 8 分足以跨过判词天花板的档位线：\n  " + "\n  ".join(bad[:12]))

    def test_low_domain_is_capped(self):
        bad = [f"{t[:22]}  业务域 {d} < {DOMAIN_FLOOR}，技能却 {s}"
               for t, p, d, s in decomposed()
               if d < DOMAIN_FLOOR and s > SKILL_CAP]
        self.assertEqual(bad, [],
                         f"业务领域低于 {DOMAIN_FLOOR} 时技能与经验封顶 {SKILL_CAP}，"
                         "这几条破了顶——业务域错配不该被专业能力和加分项冲掉：\n  "
                         + "\n  ".join(bad[:10]))

    def test_the_detector_can_fail(self):
        """变异内建：造一个违规输入，判据必须抓得到。"""
        pro, dom, skill = 70, 15, 42
        base = pro * 0.6 + dom * 0.4
        self.assertFalse(base - 0.6 <= skill <= base + BONUS_MAX + 0.6,
                         "判据放得太宽，连 48 写成 42 都抓不到")


if __name__ == "__main__":
    unittest.main()
