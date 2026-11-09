"""生成物必须与派生器当前输出一致。

这条测试是「生成物入库」这个决定的**代价**：入库的产物会漂，所以 CI 跑
`gen_entries.py --check`，本地跑这条。两者判据同源（都调 `diff`）。
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _entries  # noqa: E402
import gen_entries  # noqa: E402


class GeneratedEntriesAreCurrent(unittest.TestCase):
    def test_every_generated_file_matches(self):
        drift = gen_entries.diff(ROOT)
        self.assertEqual(
            drift, [],
            "这些生成物与派生器当前输出不一致 —— 跑 `python tools/gen_entries.py` "
            "再提交：\n  " + "\n  ".join(drift))

    def test_the_check_flag_exits_nonzero_on_drift(self):
        """对照用例：`--check` 真的会红 —— 否则上面那条恒绿。

        临时目录要拷**整个 `tools/`**：`build_dashboard` 除了 `_cli`、`doctor`
        还 import `tracker` 与 `followups`（2026-09-28 实测），只拷三个文件会让
        子进程死在 ModuleNotFoundError 上——那时 `returncode != 0` 只是「撞死」，
        不是「发现漂移」，这条对照等于没对照。所以断言要看 `diff()` 自己的
        缺文件标记「（缺）」。
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            shutil.copytree(ROOT / "tools", tmp / "tools")
            (tmp / "workflows").mkdir(parents=True)
            shutil.copy(ROOT / "workflows" / "INDEX.md", tmp / "workflows" / "INDEX.md")
            r = subprocess.run([sys.executable, "tools/gen_entries.py", "--check"],
                               cwd=tmp, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(r.returncode, 0,
                                "空仓库上 --check 居然通过了 —— 它大概什么都没比")
            self.assertIn("（缺）", r.stdout + r.stderr,
                          f"非零但不是因为缺文件，大概是撞死了：\n{r.stdout}\n{r.stderr}")

    def test_both_families_carry_every_generated_shell(self):
        for fam in _entries.SHELL_FAMILIES:
            for name in _entries.generated_names():
                p = ROOT / fam / "skills" / name / "SKILL.md"
                self.assertTrue(p.is_file(), f"{p} 不存在 —— 生成物没入库？")

    def test_the_settings_files_are_owned_by_the_generator(self):
        """本仓库**生成**的权限文件只有一份，它必须在生成物的清单里。

        原来这条循环里还躺着 `.gemini/settings.json`，前面挂一个 `if 存在`。那份文件
        2026-09-29 取证后就撤回不再生成了，所以那半截**永远不进循环体** —— 一条只有
        在「我们已经决定不生成的文件又出现」时才可能失败的断言，绿着等于没写
        （本仓库点名的失败模式：「扫不到文件时，『没有问题』和『没有检查』长得一样」）。
        手放一份 `.gemini/settings.json` 该由谁拦，正本是 `tools/security_guards.py`
        （它按 key 面查那份文件，`required: False`），不是这条。
        """
        owned = {str(k.relative_to(ROOT)).replace("\\", "/")
                 for k in gen_entries.desired_files(ROOT)}
        rel = ".claude/settings.json"
        self.assertTrue((ROOT / rel).is_file(),
                        f"{rel} 不在盘上 —— 这条要核的东西没了，断言会空转")
        self.assertIn(rel, owned,
                      f"{rel} 存在但生成器不管它 —— 它会漂而没人发现")

    def test_generated_files_are_crlf(self):
        """生成物的行尾由生成器定，统一 CRLF——**担保人是 `.gitattributes` 那几行**。

        没有 `text eol=crlf`，blob 里存的是 LF，Linux 上 checkout 出来也是 LF，
        而生成器写 CRLF：于是 `--check` 与这条测试**只在 CI 上红**，本地 Windows 的
        autocrlf 把 LF 转回 CRLF、看起来全绿（2026-09-30 两族壳第一次入库时就这样，
        两条 CI 报错同一个根）。所以这条断言真正的对象不是「盘上碰巧是 CRLF」，
        是「任何平台上 checkout 出来的都等于生成器的输出」。

        「跟随原文件」的写法还有个洞：一个存成 LF 的文件会永远保持 LF，
        `--check` 也不会说它不对。
        """
        for path in gen_entries.desired_files(ROOT):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            self.assertIn(b"\r\n", raw, f"{path.name} 不是 CRLF")
            self.assertFalse(raw.replace(b"\r\n", b"").count(b"\n"),
                             f"{path.name} 里混进了裸 LF")

    @unittest.skipUnless(shutil.which("git"), "需要 Git 验证检出行尾")
    def test_checkout_keeps_crlf_without_autocrlf(self):
        """模拟 Linux 检出，避免 Windows 的 autocrlf 掩盖新族漏配行尾规则。

        除生成物外也覆盖手写路由壳：它同样必须与其它族逐字一致。
        不复制个人数据，不提交，只从临时索引检出。
        """
        paths = set(gen_entries.desired_files(ROOT))
        paths.update(ROOT / fam / "skills" / name / "SKILL.md"
                     for fam in _entries.SHELL_FAMILIES
                     for name in _entries.HANDWRITTEN_NAMES)
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            checkout = Path(td) / "checkout"
            repo.mkdir()

            def git(*args):
                return subprocess.run(
                    ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
                    check=True, capture_output=True)

            git("init", "--quiet")
            shutil.copyfile(ROOT / ".gitattributes", repo / ".gitattributes")
            for path in paths:
                target = repo / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
            git("add", "--all")
            git("checkout-index", "--all", f"--prefix={checkout.as_posix()}/")
            for path in sorted(paths):
                rel = path.relative_to(ROOT)
                with self.subTest(path=rel.as_posix()):
                    expected = (repo / rel).read_bytes().replace(b"\n", b"\r\n")
                    self.assertEqual((checkout / rel).read_bytes(), expected,
                                     f"{rel} 检出后不是 CRLF，检查 .gitattributes")


if __name__ == "__main__":
    unittest.main()
