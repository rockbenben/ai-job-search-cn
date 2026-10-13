"""年包 = 月薪 × 薪数。**一个数三处各说各的，被校验的只有两处。**

`04-job-evaluation.md`「几薪」那一条写死了这条算式，但它只是文字：

- 分数走 `scoring.pay_dim`，从职位库的 `salary` + `salaryMonths` 算；
- 面板走 `export_web_data.annual_package` —— 又一份实现；
- 评估正文里那句年包是**手写的第三份**，谁也没校验它。

审计只比分数，于是第三份没人管。它错了不会报错，只是变成一句假话 ——
而那句话正是投前必问、面试谈薪时要照着说的东西。

**同一件事有三份说法时，出错的永远是没人校验的那份。** 所以这里扫算术本身：
凡是同一处出现「月薪区间 + 薪数」与「年包区间」，就把两边乘一遍对账。
对不上的不是「写得不好看」，是「这句话是假的」。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 「10-20k×12薪」「30-40k·**18薪**」「50-60k×**15 薪**」都认。
#: 例子一律用合成数字 —— 样例里摆真实挂牌的薪资区间，提交就替职位库泄了底。
#: 薪数是必需的那一半 —— 没写几薪时正文按 12 薪保守折算，那条另有判据管。
SALARY = re.compile(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*k\s*[·x×*]?\s*\**\s*(\d+(?:\.\d+)?)\s*薪")
PACKAGE = re.compile(r"年包\s*\**\s*(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*万")

#: 容差。年包写「97.5」而算出来是 97.5 是精确的；但有的正文为了好看
#: 取整到「98」，差 0.5 不算错。超过 1.5 万就是另一回事了。
TOL = 1.5


def evaluations(user: str) -> list[Path]:
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    return [d / "evaluation.md" for d in sorted(apps.iterdir())
            if (d / "evaluation.md").is_file()]


def active_user() -> str | None:
    ptr = ROOT / ".active_user"
    return ptr.read_text(encoding="utf-8").strip() if ptr.is_file() else None


class TheAnnualPackageIsSalaryTimesMonths(unittest.TestCase):
    """写下来的年包必须真的等于月薪 × 薪数。"""

    def _mismatches(self) -> list[str]:
        user = active_user()
        if not user:
            return []
        bad: list[str] = []
        for f in evaluations(user):
            lines = f.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                # 年包常写在表格行的下一格，所以往后借一行 —— 只借一行。
                window = line + ("\n" + lines[i + 1] if i + 1 < len(lines) else "")
                for m in SALARY.finditer(window):
                    lo, hi, months = (float(m.group(k)) for k in (1, 2, 3))
                    pkg = next((p for p in PACKAGE.finditer(window)
                                if p.start() >= m.end() - 1), None)
                    if pkg is None:
                        continue
                    want_lo, want_hi = lo * months / 10, hi * months / 10
                    got_lo, got_hi = float(pkg.group(1)), float(pkg.group(2))
                    if abs(want_lo - got_lo) > TOL or abs(want_hi - got_hi) > TOL:
                        bad.append(
                            f"{f.parent.name}:{i + 1}  {m.group(0)} 写着年包 "
                            f"{pkg.group(1)}-{pkg.group(2)} 万，"
                            f"乘出来是 {want_lo:g}-{want_hi:g} 万")
        return bad

    def test_every_annual_package_matches_the_multiplication(self):
        bad = self._mismatches()
        self.assertEqual(
            bad, [],
            "评估里写的年包不等于「月薪 × 薪数」——同一个数在正文里是假的：\n  "
            + "\n  ".join(bad[:10])
            + f"\n（共 {len(bad)} 处）"
            "\n判据见 `04-job-evaluation.md`「几薪」：年包 = 月薪 × 薪数，"
            "薪数已经算进去了，别再叠一次年终奖。")

    def test_the_matcher_really_matches(self):
        """控制用例：这一对写法必须被认出来，否则上面那条永远绿。"""
        self.assertTrue(SALARY.search("30-40k·**18薪**"))
        self.assertTrue(PACKAGE.search("年包 **54-72 万**"))
        line = "- 薪资：30-40k·18薪　→　**年包 54-72 万**"
        m = SALARY.search(line)
        pkg = PACKAGE.search(line)
        self.assertIsNotNone(m)
        self.assertIsNotNone(pkg)
        self.assertAlmostEqual(30 * 18 / 10, float(pkg.group(1)), delta=TOL)


if __name__ == "__main__":
    unittest.main()