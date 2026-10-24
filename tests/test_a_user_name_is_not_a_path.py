# -*- coding: utf-8 -*-
"""用户名只能是 `users/` 下的一个目录名，不能是一条路径。

`AGENTS.md` 的枚举和 `job-user.md` 的清洗规则都写着这一点，但代码此前只做
`(root / "users" / name).is_dir()`：`..` 会解析成仓库根、绝对路径会整个跳出
`users/`，两者都能通过。随后 `store_dir("..")`、额度文件、绑定 token 都跟着
落到 `users/` 之外——多用户隔离和「个人数据只在 users/ 下」的前提一起失效。

这里钉的是**解析层的判据**，不是某个调用方的措辞。
"""

import contextlib
import io
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import doctor  # noqa: E402


class AUserNameCannotEscapeUsers(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "users" / "alice").mkdir(parents=True)
        (self.root / ".active_user").write_text("alice", encoding="utf-8")

    def test_dot_dot_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            _cli.pick_user("..", root=self.root)
        self.assertEqual(cm.exception.code, 2)

    def test_an_absolute_path_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            _cli.pick_user(str(self.root), root=self.root)
        self.assertEqual(cm.exception.code, 2)

    def test_an_embedded_parent_is_refused(self):
        with self.assertRaises(SystemExit):
            _cli.pick_user("alice/..", root=self.root)

    def test_trailing_dot_is_refused(self):
        """Windows 把 `alice.` 归一成 `alice`；同一个目录两个名字，隔离就说不清。"""
        with self.assertRaises(SystemExit) as cm:
            _cli.pick_user("alice.", root=self.root)
        self.assertEqual(cm.exception.code, 2)

    def test_dots_only_is_refused(self):
        """`users/...` 在 Windows 上解析成 `users/` 本身（实测）。"""
        for name in ("...", "...."):
            with self.subTest(name):
                with self.assertRaises(SystemExit) as cm:
                    _cli.pick_user(name, root=self.root)
                self.assertEqual(cm.exception.code, 2)

    def test_windows_reserved_names_are_refused(self):
        for name in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT9", "con.txt"):
            with self.subTest(name):
                with self.assertRaises(SystemExit):
                    _cli.pick_user(name, root=self.root)

    def test_a_normal_child_still_works(self):
        self.assertEqual(_cli.pick_user("alice", root=self.root), "alice")

    def test_the_active_pointer_cannot_escape_either(self):
        (self.root / ".active_user").write_text("..", encoding="utf-8")
        user, msg = _cli.read_active_user(self.root)
        self.assertEqual(user, "..")
        self.assertTrue(msg, "指向 `..` 的 .active_user 被当成了合法用户")
        self.assertIn("/job-user", msg)

    def test_the_active_pointer_cannot_use_a_windows_alias(self):
        """`...` 不是 `..`，但 Windows 上一样解析到 `users/` 本身。"""
        (self.root / ".active_user").write_text("...", encoding="utf-8")
        user, msg = _cli.read_active_user(self.root)
        self.assertEqual(user, "...")
        self.assertTrue(msg, "指向 `...` 的 .active_user 被当成了合法用户")
        self.assertIn("不是一个可用的用户名", msg)

    def test_doctor_does_not_open_the_repo_root_as_a_user(self):
        """自检不 import `_cli`，所以它必须自己持一份同样的判据。"""
        (self.root / "AGENTS.md").write_text("x", encoding="utf-8")
        (self.root / "workflows").mkdir()
        (self.root / "users" / "alice" / "profile").mkdir(parents=True)
        (self.root / "users" / "alice" / "profile" / "candidate.md").write_text(
            "x", encoding="utf-8")
        old = doctor.ROOT
        doctor.ROOT = self.root
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                st = doctor.check_repo("..")
        finally:
            doctor.ROOT = old
        self.assertTrue(st.get("user_missing"),
                        "doctor --user .. 把仓库根当成了用户目录")
        self.assertTrue(st.get("user_invalid"),
                        "doctor 没把「名字非法」和「用户不存在」分开")


if __name__ == "__main__":
    unittest.main()
