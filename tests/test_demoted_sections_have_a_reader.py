# -*- coding: utf-8 -*-
"""搬走的每一节都要有落点，且落点**别人 clone 得到**。

`AGENTS.md` 因为 agy 的 24,000 B 闸门把叙述与实测记录搬到了别处（见
`tests/test_core_agents_md_fits_the_tightest_gate.py`）。搬家只成了两半：
搬走、以及在 `AGENTS.md` 原处留一句「见 X」。**只有前半的等于删掉** ——
规则还在，依据没了，下一个人照样会把同一件事再犯一遍。

第二条断言（落点不被 gitignore）是这条测试存在的全部理由：`docs/superpowers/` 被
`.gitignore` 排除（注释原话「contain maintainer notes, not product」），把依据层
搬进那儿，别人 clone 不到，本地看着齐、仓库里是空的。

第三条断言按**条数**比，不是问「提到过没有」：有的落点被指了两处，只删其中一处时
文本里仍然找得到那个路径 —— 子串判据对这种事是瞎的。见 `POINTER_FLOOR`。
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 搬走的节（键是 `AGENTS.md` 里指针句的说法）→ 落点文件。
#: 落点必须①存在且非空、②入库（`git check-ignore` 为空）、
#: ③被 `AGENTS.md` 指到**且一处不少**（条数见 `POINTER_FLOOR`）。
DEMOTED = {
    "21 条命令的索引表": "workflows/INDEX.md",
    "各工具的入口 / 缺哪项能力卡住哪几条": "docs/tool-entries.md",
    "取数渠道顺位的逐家实测": "workflows/reference/cdp-portals.md",
    "措辞那三类为什么单列 + plain() 前后条数": "docs/why/wording.md",
    "引导规则的实测记录（倒计时三天、规则真出处假）": "docs/why/guidance.md",
    "资料守卫的实测记录（一条规则只贴一个写手、六条各抄一份）": "docs/why/profile-guards.md",
    "三条脊梁的取舍记录（那三条为什么不进图、README 四步版）": "docs/why/spine.md",
    "跟进裁定说过两次的记录": "docs/why/followup.md",
    "浏览器判据表关掉三家那一轮的经过": "docs/why/browser-gate.md",
    "并行分派那四条各自真发生过的事": "docs/why/parallel-dispatch.md",
}

#: 每个落点在 `AGENTS.md` 里**实测到的指针条数**，判据是「不少于这条下限」。
#:
#: 为什么「提到过就行」不够：`workflows/INDEX.md`、`docs/why/guidance.md`、
#: `docs/why/profile-guards.md`、`docs/why/spine.md` 各被指了**两处**，而两处各管各的
#: （`docs/why` 那三处是指向两段不同的实测记录；`workflows/INDEX.md` 一处是搬家指针、
#: 一处是说「索引的正本在那儿」）。子串判据只答「文本里还剩没有这个路径」，
#: 删掉其中一处照样绿 —— 那半句话从此没人守，而测试说「还指着」。按条数比才会红。
#:
#: 下限而不是等值：**多**指一处不是缺陷（同一节里再补一句「经过见 X」是好事），
#: **少**一处一定是 —— 要拦的失败模式正是「搬走而没留指针」。
#:
#: 搬家搬出**新指针**时同步这张表；`test_the_pointer_floor_covers_every_demoted_spot`
#: 保证这张表与 `DEMOTED` 不会各自漂开（漏一条 = 那次搬家没人守条数）。
POINTER_FLOOR = {
    "workflows/INDEX.md": 2,
    "docs/tool-entries.md": 1,
    "workflows/reference/cdp-portals.md": 1,
    "docs/why/wording.md": 1,
    "docs/why/guidance.md": 2,
    "docs/why/profile-guards.md": 2,
    "docs/why/spine.md": 2,
    "docs/why/followup.md": 1,
    "docs/why/browser-gate.md": 1,
    "docs/why/parallel-dispatch.md": 1,
}


def _ignored(rel: str) -> bool:
    """git 会不会 ignore 这个路径。**不要求文件存在** —— 比的是规则。

    不在 git 仓库里（打包分发、tarball）时返回 False：那时无从判断，
    宁可报出来让人看一眼，也不要静默放行。
    """
    try:
        r = subprocess.run(["git", "check-ignore", "-q", rel],
                           cwd=ROOT, capture_output=True)
    except OSError:
        return False
    return r.returncode == 0


def _missing(dests: dict[str, str]) -> list[str]:
    """落点不存在或是空文件的条目。"""
    out = []
    for k, v in dests.items():
        p = ROOT / v
        if not p.is_file():
            out.append(f"{k} → {v}（没有这个文件）")
        elif p.stat().st_size == 0:
            out.append(f"{k} → {v}（文件是空的）")
    return out


def _gitignored(dests: dict[str, str]) -> list[str]:
    return sorted({v for v in dests.values() if _ignored(v)})


def _cited(dest: str, text: str) -> int:
    """`AGENTS.md` 正文里指向这个落点的**次数**。"""
    return text.count(dest)


def _drop_one_citation(text: str, dest: str) -> str:
    """抹掉指向 `dest` 的**一处**指针（其余句子原样留着），用来做变异对照。"""
    i = text.index(dest)
    return text[:i] + text[i + len(dest):]


def _pointer_gaps(dests: dict[str, str], text: str) -> list[str]:
    """指针条数低于 `POINTER_FLOOR` 的落点。

    三种情况都算缺口，且分开说：
      0 处 = 一句都没指，搬走就等于删掉；
      少于下限 = 指针被删了一处（子串判据对这种是瞎的）；
      落点不在下限表里 = 这张表自己漏登记，搬家没人守条数。
    """
    out = []
    for dest in sorted(set(dests.values())):
        floor = POINTER_FLOOR.get(dest)
        if floor is None:
            out.append(f"{dest}：没登记在 POINTER_FLOOR 里，指针条数无从判定")
            continue
        got = _cited(dest, text)
        if got == 0:
            out.append(f"{dest}：一处指针都没有（搬走就等于删掉）")
        elif got < floor:
            out.append(f"{dest}：应有 {floor} 处指针，实际只剩 {got} 处"
                       "（少的那一处指着的经过，从此没人指着）")
    return out


class DemotedSectionsHaveAReader(unittest.TestCase):
    def test_every_demoted_section_landed_somewhere(self):
        gone = _missing(DEMOTED)
        self.assertEqual(gone, [], f"这些搬走的节没有落点文件（或落点是空的）：{gone}")

    def test_no_landing_spot_is_gitignored(self):
        bad = _gitignored(DEMOTED)
        self.assertEqual(bad, [],
                         f"这些落点被 .gitignore 排除，别人 clone 不到：{bad}")

    def test_agents_md_points_at_each_landing_spot(self):
        """搬走而没留指针 = 删掉；**只留了一半指针**同样是删掉了一半。

        所以按条数比，不按「文本里出现过」比：`workflows/INDEX.md` 这类被指两处的落点，
        删掉一处时子串判据是绿的（`POINTER_FLOOR` 的注释里有实测经过）。
        """
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        gaps = _pointer_gaps(DEMOTED, text)
        self.assertEqual(gaps, [],
                         f"AGENTS.md 指向这些落点的指针少于预期，搬走的材料正在失联：{gaps}")

    def test_the_pointer_floor_covers_every_demoted_spot(self):
        """`POINTER_FLOOR` 与 `DEMOTED` 是两张表，漏登记的那一张会让条数断言空转。

        新落点只加进 `DEMOTED` 而忘了这里 → `_pointer_gaps` 会报「没登记」，
        而不是静默按 0 处理（0 下限等于没有断言）。
        """
        unregistered = sorted(set(DEMOTED.values()) - set(POINTER_FLOOR))
        self.assertEqual(unregistered, [],
                         f"这些落点没登记指针条数下限，删掉指针不会被发现：{unregistered}")
        stale = sorted(set(POINTER_FLOOR) - set(DEMOTED.values()))
        self.assertEqual(stale, [],
                         f"POINTER_FLOOR 里这些条目对应的落点已不在名单上：{stale}")
        # 下限必须 ≥1，否则「没登记」与「登记成 0」是同一个洞的两种写法。
        zeros = sorted(d for d, n in POINTER_FLOOR.items() if n < 1)
        self.assertEqual(zeros, [], f"这些落点的下限是 0，等于没断言：{zeros}")

    def test_the_demoted_list_covers_every_why_file(self):
        """`docs/why/` 下每一份都要在这份名单里 —— 名单漏一条，那次搬家就没人守。

        与 `test_multiuser_paths.py` 查枚举完整性同一个道理：新落点不会自己长进名单。
        """
        on_disk = sorted(p.relative_to(ROOT).as_posix()
                         for p in (ROOT / "docs" / "why").glob("*.md"))
        unpinned = sorted(set(on_disk) - set(DEMOTED.values()))
        self.assertEqual(unpinned, [],
                         f"这些 docs/why 落点没进 DEMOTED 名单：{unpinned}")

    # ---- 对照/变异用例：探测器点得着火 ------------------------------------

    def test_the_ignore_detector_can_fire(self):
        """`_ignored` 真的认得出被排除的路径。"""
        self.assertTrue(_ignored("docs/superpowers/specs/x.md"),
                        "docs/superpowers/ 没有被忽略？那这条测试的对照用例失效")
        self.assertFalse(_ignored("docs/tool-entries.md"))
        self.assertEqual(_gitignored({"x": "docs/superpowers/specs/x.md"}),
                         ["docs/superpowers/specs/x.md"])

    def test_the_landing_spot_detector_can_fire(self):
        self.assertEqual(_missing({"存在的": "docs/why/wording.md"}), [])
        self.assertEqual(len(_missing({"丢了": "docs/why/没有这个文件.md"})), 1)

    def test_the_pointer_detector_can_fire(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(_pointer_gaps(DEMOTED, text), [])
        # 一句都没指 —— 报红。
        self.assertEqual(_pointer_gaps({"索引表": "workflows/INDEX.md"}, "正文里没有路径"),
                         ["workflows/INDEX.md：一处指针都没有（搬走就等于删掉）"])
        # 落点改了名（指针还指着老路径）—— 报红。
        self.assertEqual(len(_pointer_gaps({"假新家": "docs/moved/index.md"}, text)), 1)
        # 下限表漏登记：报「没登记」，不静默按 0 放行。
        self.assertIn("没登记", _pointer_gaps({"漏登记": "docs/why/新搬的.md"}, "x")[0])

    def test_the_pointer_count_bites_when_a_citation_is_deleted(self):
        """这条是新口径存在的全部理由：**两处里删掉一处**，老口径还是绿的。

        `workflows/INDEX.md`、`docs/why/guidance.md`、`profile-guards.md`、`spine.md`
        各被指两处。子串判据只答「文本里还剩没有这个路径」，删掉一处它看不见；
        按条数比才当场红。这里在**盘上的真实文本**上做删除，不是合成串。
        """
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        multi = sorted(d for d, n in POINTER_FLOOR.items() if n > 1)
        self.assertGreaterEqual(len(multi), 4,
                                f"被指两处的落点少于预期（{multi}），这条控制用例就空了")
        for dest in multi:
            cut = _drop_one_citation(text, dest)
            self.assertEqual(_cited(dest, text), POINTER_FLOOR[dest])
            self.assertEqual(_cited(dest, cut), POINTER_FLOOR[dest] - 1)
            # 对照组：老口径（只问「还剩没剩」）在这份文本上看不见任何缺失 = 假绿。
            self.assertIn(dest, cut, "对照组不成立：删掉一处之后不该还剩着这个路径")
            gaps = _pointer_gaps(DEMOTED, cut)
            self.assertEqual(len(gaps), 1, f"{dest}：删掉一处指针而探测器没反应：{gaps}")
            self.assertIn(dest, gaps[0])


if __name__ == "__main__":
    unittest.main()
