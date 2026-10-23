# -*- coding: utf-8 -*-
"""读真实数据的判据，在**没有活动用户**的机器上必须 skip，不能红。

## 它防的是什么

干净 clone —— 别人 clone 下来的样子，也是 CI `python-tests` job 的样子 ——
里面**没有** `users/`、没有 `.active_user`。那不是坏了，那是**还没跑
`/job-setup` 的正常状态**。

而 `_cli.pick_user()` 在那种状态下 `SystemExit(1)`。**那是它对用户的正确行为**
（CLI 就该说清「先跑 `/job-setup`」再退出，不该抛个栈回溯），所以要改的不是它，
是不加判断就调它的那些判据。

`SystemExit` 继承 `BaseException` 而不是 `Exception`，`except Exception` 接不住。

## 实测代价

- 2026-09-02：发布前的干净 clone 实测 **30 个文件、85 条红**，其中 60 条是这一个
  `SystemExit`。本机全绿，只有**别人**会红 —— 而「别人」的第一个就是首次 CI。
- 2026-10-15：同一个坑又长回来一条 —— `test_a_job_title_is_not_font_obfuscated.py`
  直接调 `_cli.pick_user()`，CI 的 `Python tool tests` job 红在它上面
  （`FAILED (errors=1, skipped=442)`）。那台跑 CI 的机器上没有活动用户，
  于是它 ERROR 而不是 skip。

**同一类坑栽了两次，所以这里钉住它。**

## 判据

凡是调 `_cli.pick_user(` 的判据文件，**必须**有下面三者之一的守卫：

- `user_or_skip` —— `tests/_live.py` 的正本（把 SystemExit 换成 SkipTest）；
- `.active_user` —— 先看这个文件在不在，不在就 skip；
- `except SystemExit` —— 自己接住那个退出。

三种都认：**写法可以变，不变的是「没有活动用户时这条判据要跳过去」。**
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

#: 守卫的三种形状。**只有一份** —— 判据文件认哪几种，列在这里。
GUARDS = ("user_or_skip", ".active_user", "except SystemExit")

#: `test_cli_contract.py` 测的就是 CLI 那条「用户怎么定」的路子，
#: 它**必须**直接调 `pick_user`（被测对象就是它）。它自己也有守卫，不豁免。
EXEMPT: tuple[str, ...] = ()


def callers() -> list[Path]:
    out = []
    for p in sorted(TESTS.glob("test_*.py")):
        if p.name in EXEMPT:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "_cli.pick_user(" in t:
            out.append(p)
    return out


class NoTestCrashesOnAMachineWithoutAUser(unittest.TestCase):

    def test_the_guard_is_not_vacuous(self):
        """控制用例：真扫到了那些调 `pick_user` 的文件。

        没有它，这条判据在「大家都不调了」的情况下会恒绿 ——
        而恒绿正是它要防的那种静默。
        """
        found = callers()
        self.assertGreaterEqual(len(found), 3,
                                f"只扫到 {len(found)} 个调 pick_user 的判据文件，"
                                f"像是扫空了（{len(found)}）")

    def test_every_caller_has_a_guard(self):
        bad = []
        for p in callers():
            t = p.read_text(encoding="utf-8")
            if not any(g in t for g in GUARDS):
                bad.append(p.name)
        self.assertEqual(
            bad, [],
            "这些判据直接调 `_cli.pick_user()`，而没有活动用户时它 `SystemExit(1)` ——"
            "干净 clone / CI 上是 ERROR 而不是 skip。\n  "
            "加一个守卫（三选一）：`from _live import user_or_skip`、"
            "先看 `.active_user` 在不在、或者自己 `except SystemExit`。\n  "
            + "\n  ".join(bad))


if __name__ == "__main__":
    unittest.main()
