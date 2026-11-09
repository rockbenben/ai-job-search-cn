"""各族壳逐字相同。

`AGENTS.md`「工具特化」原来把这条写成散文规则（「两份壳必须逐字一致，否则同一个技能
在 Claude Code 和别的工具里触发词、权限都能不一样」）。生成器落地后它成了可执行的断言。

⚠️ 原来这里把路径硬编码成 `.claude` / `.agents`，2026-11-09 接 WorkBuddy 加族时
新族没人盯。现在从 `_entries.SHELL_FAMILIES` 取，以第一族为基准逐族对拍——
以后加族/删族都不用再改这份测试。
"""
import filecmp
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _entries  # noqa: E402


class ShellFamiliesAreByteIdentical(unittest.TestCase):
    BASE = _entries.SHELL_FAMILIES[0]

    def test_every_generated_shell_matches_across_families(self):
        bad = []
        for name in _entries.generated_names():
            ref = ROOT / self.BASE / "skills" / name / "SKILL.md"
            for fam in _entries.SHELL_FAMILIES[1:]:
                other = ROOT / fam / "skills" / name / "SKILL.md"
                if not (ref.is_file() and other.is_file()):
                    bad.append(f"{name}: {fam} 缺文件"
                               f"（基准={ref.is_file()} {fam}={other.is_file()}）")
                elif not filecmp.cmp(ref, other, shallow=False):
                    bad.append(f"{name}: {fam} 与基准不一致")
        self.assertEqual(bad, [], "各族壳不一致：" + "、".join(bad))

    def test_the_handwritten_router_matches_too(self):
        """手写壳没有生成器兜着，这一组全靠人工同步 + 本条测试。"""
        for name in sorted(_entries.HANDWRITTEN_NAMES):
            ref = ROOT / self.BASE / "skills" / name / "SKILL.md"
            self.assertTrue(ref.is_file(), f"{name} 基准族得有")
            for fam in _entries.SHELL_FAMILIES[1:]:
                other = ROOT / fam / "skills" / name / "SKILL.md"
                self.assertTrue(other.is_file(), f"{name} 在 {fam} 也得有")
                self.assertTrue(filecmp.cmp(ref, other, shallow=False),
                                f"{name}: {fam} 与基准不一致 —— 改一边就要改每一族")

    def test_the_set_is_exactly_index_plus_router(self):
        """对照用例：壳的集合不许自己长大或缩小。

        多一个 = 有条命令没有工作流正文；少一个 = 用户敲得到面板上那条、
        但在别的工具里叫不动它。
        """
        for fam in _entries.SHELL_FAMILIES:
            on_disk = {p.parent.name for p in (ROOT / fam / "skills").glob("*/SKILL.md")}
            on_disk -= {"liepin-search"}          # 可插拔平台技能，不是命令壳
            self.assertEqual(on_disk, set(_entries.shell_names()),
                             f"{fam}/skills 的壳集合与索引对不上")


if __name__ == "__main__":
    unittest.main()
