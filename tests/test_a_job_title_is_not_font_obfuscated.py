# -*- coding: utf-8 -*-
"""职位标题不许带**字体混淆**的私用区字符。

## 它防的是什么

平台用自定义字体把数字映射到 Unicode 私用区（U+E000–U+F8FF）。截图上肉眼是
`30-50K`，抓取下来是 `U+E037 U+E031 - U+E039 U+E031 K`。**面板上它就是乱码**
——那是用户看见的东西，而库里没有任何东西会红。

实测活动用户 2026-10-14：热库 1628 条里 **75 条**中招，面板 1354 个岗里
**74 个**。根因与修法见 `workflows/reference/cdp-portals.md`（那一节对 BOSS
那一路记着同一现象，并写明**那个映射每轮都不一样、不可硬编码**）。

已经修过的那 75 条由 `tools/fix_pua_titles.py` 修：它用同一条记录**本来就对**
的结构化 `salary` 字段换掉标题尾部那一段——不写任何映射，因此免疫「每轮都变」。

## 为什么导出侧还要兜一层

`fix_pua_titles.py` 只修**存量**。下一次抓取带进来的新 PUA，它要到下次
跑那个工具才会被处理，而用户是先看见乱码的。所以 `export_web_data` 在
上屏前也过一遍 `_cli.plain_title`。

**兜底不是修复。** 切不动的那种（没有 `salary`、尾部不是薪资骨架）
`plain_title` 原样返回，于是本条会当场报出来——那条路径要有人来看。

## 它不查什么

- 不查私用区出现在别的字段（目前实测只在 `title`）。
- 不查 `id`：详情文件名由 `stable_id(url, 标题)` 决定，改标题就得改文件名，
  `fix_pua_titles.py` 一并做（实测 75 条里有 54 条有详情文件）。
"""

from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402


def _seen() -> dict:
    user = _cli.pick_user("", root=ROOT)
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        return {}
    return _cli.seen_of(json.loads(p.read_text(encoding="utf-8")))


class AJobTitleIsNotFontObfuscated(unittest.TestCase):
    """库里的标题就是上屏的标题——带私用区就等于面板上是一串乱码。"""

    def test_no_title_carries_private_use_characters(self):
        seen = _seen()
        if not seen:
            self.skipTest("没有活动用户或职位库 —— 无从比对")
        bad = [f"{k}  {str(v.get('title'))!r}"[:110]
               for k, v in seen.items()
               if isinstance(v, dict)
               and _cli.PUA_RE.search(str(v.get("title") or ""))]
        self.assertEqual(
            bad, [],
            "这些标题里带着字体混淆的薪资（私用区字符），面板上显示为乱码：\n  "
            + "\n  ".join(bad[:10])
            + f"\n  …共 {len(bad)} 条。\n"
            + "修法：`python tools/fix_pua_titles.py --apply`"
            + "（它用本记录自己的 `salary` 换掉那段，并同步改详情文件名）。")

    def test_the_exporter_would_clean_it_anyway(self):
        """导出侧兜底：即便库里又有新的，`plain_title` 也认得出来。

        钉住的是**这个能力本身**，不是「今天库里恰好干净」——后者在
        `test_no_title_carries_private_use_characters` 已经管了。
        """
        pua = "".join(chr(0xE031 + n) for n in (3, 0))       # -> "30"
        self.assertEqual(
            _cli.plain_title(f"产品经理 {pua}-{pua}K", "30-40K"),
            "产品经理 30-40K")

    def test_it_refuses_instead_of_guessing(self):
        """切不动就**原样留着**，让上面那条报出来。

        两种切不动：没有 `salary`、尾部剥掉私用区之后不是薪资骨架。
        削掉职位名比显示难看更坏。
        """
        pua = "".join(chr(0xE031 + n) for n in (3, 0))
        # 没有 salary -> 不动
        t = f"产品经理 {pua}-{pua}K·{chr(0xE031 + 4)}{chr(0xE031 + 3)}薪"
        self.assertEqual(_cli.plain_title(t, ""), t)
        # 尾部不是薪资骨架（这里混进了别的词）-> 不动
        t2 = f"产品经理 {pua}-{pua}K 负责内部平台建设"
        self.assertEqual(_cli.plain_title(t2, "30-40K"), t2)

    def test_a_clean_title_is_untouched(self):
        for t in ("示例产品经理（示例方向 × 示例策略）",
                  "【99校招】示例数据分析师/示例数据工程师",
                  "示例自动化项目 8000+ 3.5-4.5K"):
            self.assertEqual(_cli.plain_title(t, "30-40K"), t)


class TheCutIsJudgedInOnePlace(unittest.TestCase):
    """「哪里该切」只有一份判据，**两个出口都走它**。

    ## 这条是同一个教训的第二轮

    `fix_pua_titles.py` 的注释写着：它把 `PUA_RE` / `SALARY_SKELETON` 搬进 `_cli`
    正是因为「同一个值住在两个模块里，没人钉住它们相等」。**可当时只搬了常量，
    用它们的那套切法留在了原地** —— 于是 `_cli.plain_title`（导出侧兜底）和
    `fix_pua_titles.salary_tail`（写回侧修复）各判一次「哪里该切」。

    实测 2026-10-15：两条路在下面 8 个边界例上全对，所以那段时间它**没有显形**
    —— 而这正是危险的地方。**常量漂了会当场报，这个算法漂了两边都不报错**，
    只是导出侧显示的标题与工具写回库的标题悄悄分叉。

    ## 所以钉的是「它不许自己判」

    行为相等不够：明天有人给其中一个加一条特判，两边就分叉了，而上面那些
    `plain_title` 用例照样全绿。要挡的是**那个动作本身** —— 所以
    `salary_tail` 现在只是 `_cli.salary_split` 的一层壳，这里按实现钉住。
    """

    @staticmethod
    def _pua(*ns) -> str:
        return "".join(chr(0xE031 + n) for n in ns)

    def cases(self):
        """切点判据的每一条分支：无 PUA / PUA 前无空格 / 有空格 / 小数 /
        日薪 / 骨架不认 / 职位名自带数字 / 没有 salary。"""
        p3, p0, p4, p5 = self._pua(3, 0), self._pua(0), self._pua(4), self._pua(5)
        return (
            (f"产品经理 {p3}-{p0}K·{p4}{p5}薪", "30-50K*15薪"),
            (f"工程师 {p3}.{p5}-{p0}.{p5}K", "3.5-4.5K"),
            (f"岗{p3}{p0}K", "30-50K"),
            (f"岗 {p3}", ""),
            (f"【99校招】工程师 {p3}K", "20-30K·13薪"),
            (f"销售 {chr(0xE03A)}元/天", "300元/天"),
            (f"运维 {p3} 元", "面议"),
            ("没有 PUA 的普通岗位", "30-50K"),
        )

    def test_the_tool_does_not_judge_the_cut_itself(self):
        """它不许持有判据 —— 只许转发。"""
        import fix_pua_titles as fpt
        src = inspect.getsource(fpt.salary_tail)
        self.assertIn("_cli.salary_split", src,
                      "salary_tail 没有转发给正本")
        self.assertNotIn("rfind", src,
                         "salary_tail 又开始自己算切点了（rfind 是切点判据）")

    def test_both_ends_agree_case_by_case(self):
        import fix_pua_titles as fpt
        for title, sal in self.cases():
            with self.subTest(title=title):
                self.assertEqual(fpt.salary_tail(title),
                                 _cli.salary_split(title),
                                 "工具那侧和 `_cli` 正本对同一条标题给出了不同切法")

    def test_both_ends_agree_on_what_they_would_write(self):
        """切法相同还不够 —— 最终写进库的标题也必须相同。"""
        import fix_pua_titles as fpt
        for title, sal in self.cases():
            with self.subTest(title=title):
                parts = fpt.salary_tail(title)
                by_tool = (parts[0] + sal) if (parts and sal) else title
                self.assertEqual(_cli.plain_title(title, sal), by_tool,
                                 "导出侧显示的标题与工具写回库的标题分叉了")


if __name__ == "__main__":
    unittest.main()
