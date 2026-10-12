"""让路不是崩溃：`StaleWrite` 到用户面前必须是一句人话，不是栈回溯。

带戳写盘的三个工具（`prescreen` / `writeback` / `archive`）都会撞上它，
而且**撞上是正常的**：`/job-auto` 一跑几分钟，这期间用户在总览页点一下
「不投」「我投了」完全正常。`StaleWrite` 说的是「你手里那份过期了，这次没写」
——一次干净的让路。

而它原来是未捕获异常：三个入口都是 `sys.exit(main())`，落到用户眼前就是
几十行 Traceback 加一个英文类名 `StaleWrite`。两条规矩同时被破：

- `pick_user` 的 docstring：「新用户第一次撞见的不该是栈回溯」
- AGENTS.md：未解释的英文码不许摆到台面上

**指令要按受众分。** 异常消息只陈述事实（哪个文件、多半是谁在写），
指令由调用方补：命令行前面的人要的是「把这条命令再跑一遍」，库的调用方要的是
「重新读一次再应用」——后者写在类的 docstring 里。原来把库那句塞进了消息，
包上 `run_cli` 之后两句并排打架。

重跑是对的：工具每次都从盘上重新读，没有需要用户手工合并的东西。
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402

STAMPED = ("prescreen", "writeback", "archive", "audit_pipeline", "rekey")


class TheUserSeesASentence(unittest.TestCase):

    def _capture(self, main):
        err = io.StringIO()
        old, sys.stderr = sys.stderr, err
        try:
            code = _cli.run_cli(main)
        finally:
            sys.stderr = old
        return code, err.getvalue()

    def test_a_real_collision_ends_cleanly(self):
        """真跑一次撞车：读完、别人改了、再写。"""
        p = Path(tempfile.mkdtemp()) / "seen_jobs.json"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")
        _, stamp = _cli.load_json_stamped(p)
        time.sleep(0.02)
        p.write_text(json.dumps({"a": 2}), encoding="utf-8")

        def main(argv=None):
            _cli.atomic_write(p, json.dumps({"a": 3}), expect=stamp)
            return 0

        code, out = self._capture(main)
        self.assertEqual(code, 2, "撞车该是非零退出码")
        self.assertNotIn("Traceback", out, "用户又看到栈回溯了")
        self.assertNotIn("StaleWrite", out,
                         "英文类名漏到台面上了——AGENTS.md 禁止未解释的英文码")
        self.assertIn("再跑一遍", out, "没告诉用户该怎么办")
        self.assertIn("你的数据一个字没动", out,
                      "没说清这是让路不是丢数据——用户会以为写坏了")
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"a": 2},
                         "让路的前提是真没写")

    def test_the_two_instructions_do_not_collide(self):
        """异常消息里不许再带「重新读一次」——那是给库调用方的，会和 CLI 那句打架。"""
        p = Path(tempfile.mkdtemp()) / "x.json"
        p.write_text("{}", encoding="utf-8")
        _, stamp = _cli.load_json_stamped(p)
        time.sleep(0.02)
        p.write_text("{ }", encoding="utf-8")
        with self.assertRaises(_cli.StaleWrite) as cm:
            _cli.atomic_write(p, "{}", expect=stamp)
        msg = str(cm.exception)
        self.assertNotIn("重新读一次", msg,
                         "库那句指令又回到消息里了——CLI 包起来之后两句并排打架")
        self.assertIn("被改过了", msg, "事实那半句得留着")
        self.assertIn("重新读", _cli.StaleWrite.__doc__ or "",
                      "给库调用方的说明该在 docstring 里，别丢了")

    def test_success_passes_through(self):
        """收口不能吞掉正常返回值。"""
        self.assertEqual(_cli.run_cli(lambda argv=None: 0), 0)
        self.assertEqual(_cli.run_cli(lambda argv=None: 7), 7)

    def test_other_errors_still_surface(self):
        """只接 StaleWrite。别的异常照旧抛出去——静默吞掉比栈回溯糟得多。"""
        def boom(argv=None):
            raise ValueError("真的坏了")
        with self.assertRaises(ValueError):
            _cli.run_cli(boom)


class EveryStampedToolGoesThroughIt(unittest.TestCase):

    def test_every_entry_point_is_wrapped(self):
        for name in STAMPED:
            with self.subTest(name):
                src = (ROOT / "tools" / f"{name}.py").read_text(encoding="utf-8")
                self.assertIn("_cli.run_cli(main)", src,
                              f"{name}.py 的入口没走收口——撞车还是栈回溯")

    def test_the_list_matches_who_actually_stamps(self):
        """名单从**谁真的带戳写**现推，不手抄。

        以后哪个工具开始用 `expect=`，它就得跟着进收口——手抄的名单不会提醒任何人。
        """
        import re
        stamps = set()
        for f in (ROOT / "tools").glob("*.py"):
            if f.name in ("_cli.py",):
                continue
            if re.search(r"expect=", f.read_text(encoding="utf-8")):
                stamps.add(f.stem)
        self.assertEqual(stamps, set(STAMPED),
                         f"带戳写盘的工具变了（现在是 {sorted(stamps)}）——"
                         "新加的那个也要走 _cli.run_cli，否则它撞车时是栈回溯")


if __name__ == "__main__":
    unittest.main()
