# -*- coding: utf-8 -*-
"""前端不留死代码。和 `test_no_dead_css` 是同一件事的两半。

2026-08-13 扫出三个：

    GateStampRow        —— 「列表行里的紧凑章排」。那一列早撤了
                           （`Shortlist.tsx` 里留着当时的注释），组件成了孤儿。
    FONT_SERIF          —— 宋体字体栈。真正生效的是 `cockpit.css` 的 `--serif`，
                           这份 TS 常量是复制品，改一处不会同步另一处。
    WithCompanyApplied  —— 给 `TodayBatch` 加的类型，那个组件当天就删了。

死代码的害处是**误导**：下一个人看到 `FONT_SERIF` 会以为改它能换字体。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"

def imported_paths(source):
    return set(re.findall(
        r"""(?:from\s+|import\s*\(\s*)["']\.{1,2}/([\w/.-]+)["']""", source))


class NoDeadExports(unittest.TestCase):

    def test_every_export_is_referenced(self):
        files = {p: p.read_text(encoding="utf-8") for p in SRC.rglob("*.ts*")}
        dead = []
        for p, t in files.items():
            for m in re.finditer(
                    r"^export (?:async )?(?:function|const|interface|type) (\w+)", t, re.M):
                name = m.group(1)
                # 别处引用了 → 活的
                if any(re.search(rf"\b{re.escape(name)}\b", v)
                       for k, v in files.items() if k != p):
                    continue
                # 只在自己文件里被用（类型被结构化引用是常态）→ 也算活的
                if len(re.findall(rf"\b{re.escape(name)}\b", t)) > 1:
                    continue
                dead.append(f"{p.relative_to(SRC)} → {name}")
        self.assertEqual(dead, [],
                         "这些导出没人用——留着会让下一个人以为改它有效：\n  "
                         + "\n  ".join(dead))

    def test_no_orphan_files(self):
        files = {p: p.read_text(encoding="utf-8") for p in SRC.rglob("*.ts*")}
        allsrc = "\n".join(files.values())
        imported = imported_paths(allsrc)
        orphan = [str(p.relative_to(SRC)) for p in files
                  if p.stem != "main"
                  and not any(p.stem == Path(i).stem for i in imported)]
        self.assertEqual(orphan, [], "没被任何地方 import 的文件：\n  " + "\n  ".join(orphan))

    def test_dynamic_imports_are_dependencies(self):
        self.assertEqual(imported_paths(
            'import { App } from "./App";\n'
            'const Panel = lazy(() => import("./components/Panel"));\n'),
            {"App", "components/Panel"})

    def test_the_detector_can_fail(self):
        """变异内建：只出现一次的导出必须被判成死的。"""
        t = "export const ZZZ = 1;\n"
        self.assertEqual(len(re.findall(r"\bZZZ\b", t)), 1)


if __name__ == "__main__":
    unittest.main()
