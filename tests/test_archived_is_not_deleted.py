# -*- coding: utf-8 -*-
"""`writeback` 把「已归档」说成「记录被删过」。

## 事故

2026-10-12 一轮 `/job-auto` 的收尾，跑完这两条：

    python tools/archive.py --apply      # 已归档 817 个 · 热库剩 693 个
    python tools/writeback.py            # ⚠ 1 个目录的职位链接在库里找不到
                                       #   （可能岗位记录被删过）

**没删。** `archive.py` 自己写着「归档不是删除」，它搬的是出局两周以上的岗，
分数与判词原样留在存档里。而 `writeback` 查岗位只查热库 —— 于是每一个被归档的
岗，它的材料目录都被报成「记录被删过」。

那一轮刚好撞上：archive 刚归了 817 个，下一条工具就开始说「谁删了记录」。
用户照着这句话去查，查不到，因为**没有人删**。它把「搬走了」说成了「没了」，
而这两件事下一步该做的事完全相反（前者什么都不用做，后者要去翻删除记录）。

## 为什么归档不能算「找不到」

`archive.py --revive` 能把存档整个拉回热库，材料与分数都还在。
一个「记录被删过」的提示会让人去找一条根本不存在的事故。

## 判据

材料目录里的链接在**热库 ∪ 存档**里都找不到，才叫「被删过」；
只在存档里找到的，单独一档，说清它是什么、要不要管。
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import archive as A  # noqa: E402
import writeback as W  # noqa: E402


def _run(user: str) -> str:
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "writeback.py"),
                        "--user", user],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT))
    return r.stdout


class ArchivedIsNotDeleted(unittest.TestCase):
    """控制用例：这台机器上真的有一个「材料在、岗已归档」的目录。"""

    def setUp(self):
        if not (ROOT / ".active_user").is_file():
            self.skipTest("没有活动用户")
        self.user = _cli.read_active_user()[0]
        _sj, self.arc = A.paths(self.user)
        if not self.arc.is_file():
            self.skipTest("没有存档")
        self.archived = _cli.seen_of(
            __import__("json").loads(self.arc.read_text(encoding="utf-8")))
        # **要按 `writeback` 自己认链接的那一份来数**（`read_dir` 读 posting.md），
        # 不能用 `archive.collect_material_urls` —— 那是读 outreach.md 的，
        # 两者在这台机器上恰好指向两个不同的岗（第 5 条那个目录就是）。
        apps = ROOT / "users" / self.user / "documents" / "applications"
        self.covered = []
        if apps.is_dir():
            for d in sorted(x for x in apps.iterdir() if x.is_dir()):
                got, _why = W.read_dir(d)
                if got and _cli.norm_url(got[0]) in {
                        _cli.norm_url(e.get("url") or "")
                        for e in self.archived.values() if e.get("url")}:
                    self.covered.append(d.name)
        if not self.covered:
            self.skipTest("这台机器上没有「材料在、岗已归档」的目录")

    def test_it_is_not_reported_as_deleted(self):
        out = _run(self.user)
        self.assertNotIn("可能岗位记录被删过", out,
                         "已归档又被报成「记录被删过」")

    def test_it_is_reported_as_what_it_is(self):
        out = _run(self.user)
        self.assertIn("已经归档（不是删除，材料还在）", out)

    def test_it_tells_the_user_nothing_needs_doing(self):
        """归档不是故障 —— 说清「不用管」比只报个数有用。"""
        out = _run(self.user)
        self.assertIn("这些不用管", out)

    def test_the_revival_command_is_named(self):
        """`AGENTS.md`「每一处引导都要写出该敲的命令」。"""
        out = _run(self.user)
        self.assertIn("archive.py --revive", out)

    def test_nothing_to_do_stays_exit_zero(self):
        """归档不该让这条命令失败 —— 它不是错误。"""
        u = _cli.read_active_user()[0]
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "writeback.py"),
                            "--user", u],
                           capture_output=True, text=True, encoding="utf-8",
                           cwd=str(ROOT))
        self.assertEqual(r.returncode, 0)


class TheLookupActuallyCoversTheArchive(unittest.TestCase):
    """守卫不认文案的形状，认「它查了哪里」。"""

    def test_it_reads_the_archive_before_calling_it_deleted(self):
        src = (ROOT / "tools" / "writeback.py").read_text(encoding="utf-8")
        self.assertIn("archive.paths(user)", src,
                      "又只查热库了 —— 归档的岗会被说成「记录被删过」")
        self.assertIn("archived_urls", src)

    def test_it_borrows_the_archive_paths_instead_of_building_its_own(self):
        self.assertNotIn('"archive.json"', src_of_writeback(),
                         "存档路径自己拼了一份 —— 与 archive.py 分叉的入口")

    def test_the_two_messages_stay_different(self):
        """把两档合成一档，正是这次要防的事。"""
        src = src_of_writeback()
        self.assertIn("可能岗位记录被删过", src)
        self.assertIn("已经归档（不是删除，材料还在）", src)


def src_of_writeback() -> str:
    return (ROOT / "tools" / "writeback.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()