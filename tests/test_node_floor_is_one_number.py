# -*- coding: utf-8 -*-
"""「要多高版本的 Node」这个数，全仓只能有一个值。

**为什么是 22.18 而不是 22.6。** 22.6 加的是 `--experimental-strip-types` 这个
*开关*；默认剥离 TS 类型是 **22.18** 才有的。而本仓库文档里给的命令是不带任何
开关的裸 `node .agents/skills/liepin-search/cli/src/cli.ts …`——写 22.6 的后果是：
用户装了 22.10，自检说「就绪」，照抄命令却撞 `ERR_UNKNOWN_FILE_EXTENSION`，
而自检刚告诉他环境没问题。（`cli.ts` 的入口判据 `import.meta.main` 是 22.16+，
两者取大，仍是 22.18。）

这个数原来散在 doctor、README、SETUP、job-scrape.md、两份 CLI README 里各写一遍，
改一处漏一处必然发生——`CONTRIBUTING.md` 那张失效表的最后一条就是
「同一个数只定义一处」。现在权威在 `doctor.NODE_MIN`，这条钉住文档跟它一致。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import doctor  # noqa: E402

#: 会对用户说出版本号的地方。生成物（web/dist）不算。
DOCS = [ROOT / "README.md", ROOT / "SETUP.md",
        ROOT / "workflows" / "job-scrape.md",
        ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "README.md"]

_VER = re.compile(r"v?(\d+)\.(\d+)(?:\.\d+)?\s*(?:\+|以上|或更高)")


class TheFloorIsDefinedOnce(unittest.TestCase):

    def test_doctor_owns_the_number(self):
        self.assertEqual(doctor.NODE_MIN, (22, 18),
                         "改下限就改这里，然后让下面几条告诉你还有哪些地方要跟")

    def test_the_check_uses_the_constant(self):
        """别把常量摆在那儿、判断里仍写死一个字面量。"""
        src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        self.assertIn(">= NODE_MIN", src)
        self.assertNotIn("(22, 6)", src)

    def test_docs_quote_the_same_number(self):
        want = doctor.NODE_MIN
        bad = []
        for p in DOCS:
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if "Node" not in line and "node" not in line:
                    continue
                for maj, mino in _VER.findall(line):
                    got = (int(maj), int(mino))
                    # 只管 Node 那条线；Typst 0.13、Python 3.10 之类不在此列。
                    if got[0] != want[0]:
                        continue
                    if got != want:
                        bad.append(f"{p.relative_to(ROOT).as_posix()}:{i} 写着 "
                                   f"v{maj}.{mino}，而 doctor.NODE_MIN 是 "
                                   f"{want[0]}.{want[1]}  |  {line.strip()[:70]}")
        self.assertEqual(bad, [], "版本号对不上：\n  " + "\n  ".join(bad))

    def test_the_old_flagged_floor_is_gone(self):
        """22.6 只是「加开关能剥类型」，不是「能跑裸 node cli.ts」。"""
        for p in DOCS:
            with self.subTest(doc=p.name):
                text = p.read_text(encoding="utf-8")
                for m in re.finditer(r"22\.6\b", text):
                    line = text[:m.start()].count("\n") + 1
                    ctx = text.splitlines()[line - 1]
                    self.assertIn(
                        "开关", ctx,
                        f"{p.name}:{line} 还把 22.6 当下限说：{ctx.strip()[:70]}")

    def test_the_detector_can_fail(self):
        """变异验证判据本身分得开。"""
        self.assertEqual(_VER.findall("需要 v22.18 或更高"), [("22", "18")])
        self.assertEqual(_VER.findall("Node 22.6+"), [("22", "6")])
        self.assertEqual(_VER.findall("Typst 0.13+"), [("0", "13")])


if __name__ == "__main__":
    unittest.main()
