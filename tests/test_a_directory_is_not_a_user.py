# -*- coding: utf-8 -*-
"""`users/` 下有个目录 ≠ 这里有个用户。四个地方各写各的，终端 10 个、面板 8 个。

实测活动用户 2026-08-24，同一份 clone：

    tools/doctor.py           目录就算             → 共 10 个
    tools/serve.py            目录就算             → 共 10 个
    tools/_cli.py             目录就算             → 共 10 个
    tools/export_web_data.py  要有 candidate.md    → 8 个（面板上就是 8 个）

差的两个是 `users/张三/`（只有一个 `portal_budget.json`）和 `users/谁/`
（连文件都没有，只剩一个空的 `job_scraper/`），时间戳都停在 2026-08-19 ——
**测试留下的空壳**。

## 数字对不上只是表症

真正的代价是自检那一行把「谁」当成可切换的用户报出来：照着切过去，落进一个
什么都没有的工作区，然后每条命令都说「资料还没填」——**是工具自己把人指进
死胡同的**。「下一步」那条更直接，它取 `users[0]`，而排序按名字来，
排在最前的完全可能就是个空壳。

## 两头都改

- **判据统一**（`_cli.all_users`）：目录全列，但标出哪些还没建档。
  **不过滤**——过滤掉的东西用户就再也找不到、也删不掉。
- **根上堵住**（`portal_budget.save`）：不存在的用户不给凭空造目录。
  2026-08-19 那次修的是 `fetch_details.run` 一个调用方，`save` 本身照旧能造，
  下一个忘了注入 `budget` 的调用方会再来一遍。

面板那份仍然只列建过档的，那是**另一件事**：弹层里每一行都配一条
`/job-user <名>` 让人点着切过去，切到空壳是死胡同。理由记在导出那里。
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import portal_budget as pb  # noqa: E402

DOCTOR = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
EXPORT = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
SERVE = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
CLI = (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8")
JOIN_HAVE = "'、'.join(" + "have)"


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*#:?\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def fake_repo(tmp: pathlib.Path, *users):
    """`users` 里每项是 `(名字, 建没建档)`。"""
    for name, filled in users:
        d = tmp / "users" / name
        (d / "job_scraper").mkdir(parents=True, exist_ok=True)
        if filled:
            (d / "profile").mkdir(parents=True, exist_ok=True)
            (d / "profile" / "candidate.md").write_text("x", encoding="utf-8")
    return tmp


class TheSharedCriterionMarksShells(unittest.TestCase):
    def test_it_lists_every_directory(self):
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True), ("乙", False))
            self.assertEqual(_cli.all_users(r), [("乙", False), ("甲", True)])

    def test_a_shell_is_not_filtered_away(self):
        """过滤掉的东西用户找不到、也删不掉 —— 这条守着「列出来」。"""
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("乙", False))
            self.assertIn("乙", [n for n, _ in _cli.all_users(r)])

    def test_no_users_dir_is_empty_not_a_crash(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(_cli.all_users(pathlib.Path(t)), [])

    def test_a_loose_file_under_users_is_not_a_user(self):
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True))
            (r / "users" / "readme.txt").write_text("x", encoding="utf-8")
            self.assertEqual([n for n, _ in _cli.all_users(r)], ["甲"])


class TheLineItPrintsSaysWhatToDo(unittest.TestCase):
    def test_it_names_the_shells_separately(self):
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True), ("乙", False))
            line = _cli.user_list_line(r)
            self.assertIn("共 2 个", line)
            self.assertIn("「乙」", line)
            self.assertNotIn("「甲」", line)

    def test_it_hands_over_the_command(self):
        """面板每处引导都要写出命令，终端同理 —— 不说敲什么，用户就删不掉。"""
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True), ("乙", False))
            self.assertIn("/job-user --remove 乙", _cli.user_list_line(r))

    def test_it_says_nothing_extra_when_all_are_filled(self):
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True), ("丙", True))
            line = _cli.user_list_line(r)
            self.assertNotIn("还没建档", line)
            self.assertNotIn("--remove", line)

    def test_the_active_one_is_marked(self):
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True), ("丙", True))
            self.assertIn("甲（当前）", _cli.user_list_line(r, active="甲"))

    def test_it_uses_plain_chinese_not_internal_words(self):
        with tempfile.TemporaryDirectory() as t:
            r = fake_repo(pathlib.Path(t), ("甲", True), ("乙", False))
            line = _cli.user_list_line(r)
            for w in ("空壳", "shell", "profile_ok", "candidate.md"):
                self.assertNotIn(w, line, f"内部词漏到台面上了：{w}")


class BothErrorPathsUseIt(unittest.TestCase):
    """打错名字时列出来的那份候选，不能把空壳当候选递过去。"""

    def test_cli_pick_user_lists_through_the_helper(self):
        seg = CLI[CLI.index("def pick_user("):CLI.index("def resolve_user(")]
        self.assertIn("user_list_line(base)", seg)
        self.assertNotIn(JOIN_HAVE, seg, "又自己拼了一份名单 —— 空壳会混进候选里")

    def test_serve_lists_through_the_helper(self):
        self.assertIn("_cli.user_list_line(ROOT)", SERVE)
        self.assertNotIn(JOIN_HAVE, SERVE)

    def test_it_still_says_what_to_do_with_zero_users(self):
        """一个用户都没有时不能只说「共 0 个」—— 那句话没有下一步。"""
        self.assertIn("一个用户都还没有——先跑 /job-setup", CLI)
        self.assertIn("先跑 /job-setup", SERVE)


class DoctorKeepsAnHonestCopy(unittest.TestCase):
    """doctor 不许 import 仓库模块，只能持副本 —— 那就要钉住两边同判据。"""

    def _seg(self) -> str:
        i = DOCTOR.index('st["users"] = users')
        return DOCTOR[i - 900:i + 200]

    def test_it_uses_the_same_criterion(self):
        self.assertIn('"profile" / "candidate.md"', self._seg(),
                      "doctor 又退回「目录就算」了 —— 它会比面板多报几个")

    def test_it_names_the_source_of_truth(self):
        self.assertIn("_cli.all_users", flat(self._seg()))

    def test_the_two_agree_on_this_repo(self):
        """真实仓库上直接对一遍 —— 注释说得再好，跑出来不一样也白搭。"""
        if not (ROOT / "users").is_dir():
            self.skipTest("这份 clone 下没有 users/")
        shells = [n for n, ok in _cli.all_users() if not ok]
        if not shells:
            self.skipTest("这份 clone 下没有没建档的目录")
        # 钉死标准形式（带斜杠）：doctor 在非 Claude Code 会话里会把命令去斜杠，
        # 下面断言的是文档正本的 `/job-user --remove`；去斜杠归
        # test_code_tool_detection 覆盖。
        env = dict(os.environ, JOBS_CODE_TOOL="claude")
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "doctor.py")],
                             cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             env=env).stdout
        for n in shells:
            self.assertIn("「" + n + "」", out, f"doctor 没说「{n}」还没建档")
        self.assertIn("/job-user --remove", out)

    def test_the_next_step_does_not_recommend_a_shell(self):
        i = DOCTOR.index('if st.get("user_missing"):')
        seg = DOCTOR[i:i + 1500]
        self.assertIn("real = [n for n in users", seg)
        self.assertNotIn("/job-user {users[0]}", seg,
                         "又拿名单第一个当推荐了 —— 那可能是个空目录")

    def test_it_still_prints_the_plain_count(self):
        """加了一行警告不等于可以把原来那句吃掉。"""
        self.assertIn("当前用户：{user}", DOCTOR)
        self.assertIn("（共 {len(users)} 个：", DOCTOR)


class ThePanelIsDeliberatelyNarrower(unittest.TestCase):
    def _why(self) -> str:
        i = EXPORT.index('"allUsers"')
        return flat(EXPORT[i - 1500:i].replace("#", " "))

    def test_the_filter_is_still_there(self):
        seg = EXPORT[EXPORT.index('"allUsers"'):]
        self.assertIn('"candidate.md"', seg[:400])

    def test_the_reason_is_written_down(self):
        seg = self._why()
        self.assertRegex(seg, r"\*\*这里比终端那份少。\*\*")
        self.assertRegex(seg, r"切到空壳是死胡同")
        self.assertRegex(seg, r"判据的正本是 `_cli.all_users`")

    def test_it_carries_the_measurement(self):
        self.assertRegex(self._why(), r"2026-08-24：终端 10 个、这里 8 个")

    def test_the_no_leak_rule_is_untouched(self):
        """只报名字这条底线不能因为加注释就松了。"""
        seg = EXPORT[EXPORT.index('"allUsers"'):]
        seg = seg[:seg.index("]")]
        for leak in ("seen_jobs", "tracker", "read_text"):
            self.assertNotIn(leak, seg)


class ABudgetFileCannotInventAUser(unittest.TestCase):
    """空壳从哪来的：写额度时一路 `mkdir(parents=True)` 把假名字变成真目录。"""

    def test_saving_for_an_unknown_user_raises(self):
        with tempfile.TemporaryDirectory() as t:
            old = pb.ROOT
            try:
                pb.ROOT = pathlib.Path(t)
                (pathlib.Path(t) / "users").mkdir()
                with self.assertRaises(FileNotFoundError):
                    pb.save("查无此人", {"猎聘": {}})
                self.assertFalse((pathlib.Path(t) / "users" / "查无此人").exists(),
                                 "报错了却还是把目录造出来了")
            finally:
                pb.ROOT = old

    def test_saving_for_a_real_user_still_works(self):
        with tempfile.TemporaryDirectory() as t:
            old = pb.ROOT
            try:
                pb.ROOT = fake_repo(pathlib.Path(t), ("甲", True))
                pb.save("甲", {"猎聘": {"actions": []}})
                self.assertEqual(pb.load("甲"), {"猎聘": {"actions": []}})
            finally:
                pb.ROOT = old

    def test_the_error_says_how_to_avoid_it_in_tests(self):
        with tempfile.TemporaryDirectory() as t:
            old = pb.ROOT
            try:
                pb.ROOT = pathlib.Path(t)
                (pathlib.Path(t) / "users").mkdir()
                with self.assertRaises(FileNotFoundError) as cm:
                    pb.save("查无此人", {})
            finally:
                pb.ROOT = old
        self.assertIn("budget=", str(cm.exception))

    def test_the_incident_is_recorded(self):
        src = (ROOT / "tools" / "portal_budget.py").read_text(encoding="utf-8")
        # 只锚函数名，不锚完整签名 —— 加一个参数（`expect`）不该让这条红。
        seg = flat(src[src.index("def save("):][:1800])
        self.assertRegex(seg, r"13 个 URL 一个都没发出去")
        self.assertRegex(seg, r"那修的是\*\*那一个调用方\*\*")

    def test_the_injection_escape_hatch_still_exists(self):
        """堵死写盘不能把 `fetch_details` 的注入口一起堵了。"""
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        self.assertIn("_persist = budget is None", src)


if __name__ == "__main__":
    unittest.main()
