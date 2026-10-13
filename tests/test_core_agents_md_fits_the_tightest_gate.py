# -*- coding: utf-8 -*-
"""`AGENTS.md` 必须塞得进最紧的那道闸门。

会**静默截断**的有这么两家：agy 单文件 24,000 B（按 `@[label](path)` 展开之后算）、
Codex `project_doc_max_bytes` 32 KiB（跨 AGENTS.md 累计）。静默的意思是——超了不报错，
排在后面的规则直接消失，而 agent 与用户都不知道少了什么。

> **别把这条写成「N 家里 M 家」**：2026-10-13 加进第六家工具时那句就得跟着数，
> 而**新加那家有没有截断上限是量不出来的**（本文件管的是字节闸，管不了各家
> harness 的注入预算）。所以这里点**名字**——名字是可核的，数量是下一次加档就会
> 过期的。

阈值定 23,500 B 而不是 24,000：闸门按**展开之后**算，那 500 B 是留给展开的缓冲，
不是留给新规则的额度。本文件一句 `@[label](path)` 都没有时，这层缓冲不保护任何东西
—— 现算的条数写在失败信息里。真加规则时的落点与搬法，也写在那条失败信息里。

字节账一律按**盘上字节**（`read_bytes()`，含 CRLF），不按 `len(text)`：本仓库的 `.md`
是 CRLF，一个换行在两种口径下差一个字节，按字符数算会把余量算多。
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LIMIT = 23_500
AGY_GATE = 24_000
CODEX_GATE = 32 * 1024

#: 万一将来又长过闸门，排在后面的节先掉。这份元组把**必须是规则**的那几节钉在
#: 头部、并钉住它们的**阅读顺序**，所以「规则节漂到尾部」这件事会当场红。
#:
#: ⚠️ **这条不是「截断只丢链接」的保证**，别把它读成那样。原本的说法是「尾部只剩
#: 按需材料，所以节序本身就是保险」，而盘上的 `AGENTS.md` 不是这个样子：尾部那一节
#: （`TAIL_SECTION`）除了搬家指针**还住着两条常驻规则**（就写在那一节里，
#: 本测试不抄它的内容，抄了就成了下一个会漂的假事实）；而 `docs/why/*` 的指针是
#: **就地写在各自规则节里**的，根本不住在尾部。真按 agy 闸门截断，先掉的是那两条
#: 规则加上尾部里的指针，不是纯链接。
#:
#: 把它变成真保险只有两条路，都不属于本测试：把尾部那两条规则挪到 `## 能力对照表`
#: 之前（那是 Task 11-12 的成品，不该在这里翻动），或者接受这个残余风险并把话说清楚。
#: 这里选后者。所以两条断言各管各的：`_order_violations` 只管**位置**（规则不许漂到
#: 会被先砍的地方），`test_the_why_pointers_are_outside_the_sacrifice_zone` 才管
#: **截断**（依据层的指针不许掉进砍掉区）。字节现值不写死在注释里，要现值看失败信息。
#: 每一项都是 `AGENTS.md` 里那条 `## ` 标题的**前缀**（标题带冒号后缀，节名不带）。
#: ⚠️ 前缀口径有一处已知的瞎：把 `## 资料没填完是分档的` 后面的措辞改掉、前缀原样留着，
#: 三条断言都不会红（本轮变异验过）。要拦「改标题」就得钉完整字面量，代价是任何
#: 无害的标题改写都会红 —— 那是裁定，不是本任务能顺手改的口径。
MUST_SURVIVE = (
    "## 角色",
    "## 活动用户与多用户",
    "## 往 `candidate.md` 里写东西",
    "## 资料没填完是分档的",
    "## 全局安全铁律",
    "## 会话开始",
    "## 给用户看的措辞",
    "## 每一处引导都要写出该敲的命令",
    "## 一次跑到头",
    "## 工作流索引",
    "## 能力对照表",
)

#: 截断时**应当**先掉的那一节。正文大部分已搬到 `docs/tool-entries.md`，
#: 但这一节仍留有上面注释里写明的两条常驻规则 —— 所以它是「最靠后的一节」，
#: 不等于「只有按需材料」。
TAIL_SECTION = "## 工具特化"

#: 依据层指针的标记（`docs/why/` 下的落点）。这些引用必须住在尾部截断区**之前**，
#: 否则截断之后规则还在而依据没了。按字面标记扫，不重复列落点名单
#: （名单在 `tests/test_demoted_sections_have_a_reader.py` 的 `DEMOTED`）。
WHY_POINTER_MARK = "docs/why/"

#: 这些目录不参与 Codex 的入口链累计（第三方壳与个人数据不是仓库规则）。
SKIP_DIRS = {".git", "node_modules", ".claude", ".agents", ".qoder", "users"}


def _bytes(p: Path) -> int:
    """盘上字节（含 CRLF）。字节账一律按这个口径，不按 `len(text)`。"""
    return len(p.read_bytes())


def _h2_byte_offsets(raw: bytes) -> list[tuple[int, str]]:
    """每个 `## ` 节的**起始字节偏移**（盘上口径，含 CRLF）＋标题原文。

    按字节切而不是按 `read_text()` 的解码文本：后者把 CRLF 折成 LF，
    每行少算一个字节，偏移就会比盘上靠前，而截断是按盘上字节发生的。
    """
    out, acc = [], 0
    for line in raw.splitlines(keepends=True):
        if line.startswith(b"## "):
            out.append((acc, line.rstrip(b"\r\n").decode("utf-8")))
        acc += len(line)
    return out


def _needle_offsets(raw: bytes, needle: str) -> list[int]:
    """某个字面量在**盘上字节**里的全部出现位置（用来判断指针落在哪一段）。"""
    return [m.start() for m in re.finditer(re.escape(needle.encode("utf-8")), raw)]


def _sacrifice_zone_start(raw: bytes) -> int | None:
    """尾部那一节的起始偏移：偏移之后的字节是「真撞闸门时先掉的那一段」。"""
    for off, head in _h2_byte_offsets(raw):
        if head.startswith(TAIL_SECTION):
            return off
    return None


def _h2(text: str) -> list[str]:
    """按出现顺序返回所有 `## ` 标题。"""
    return [m.group(0) for m in re.finditer(r"^## .+$", text, re.M)]


def _find(heads: list[str], prefix: str) -> int | None:
    for i, h in enumerate(heads):
        if h.startswith(prefix):
            return i
    return None


def _missing_rules(heads: list[str]) -> list[str]:
    """MUST_SURVIVE 里哪些已经不是标题了。

    只认**标题**，不认正文里的字面出现——把「## 角色」写进一句散文里不算这条规则还在。
    """
    return [p for p in MUST_SURVIVE if _find(heads, p) is None]


def _order_violations(heads: list[str]) -> list[str]:
    """规则节必须按元组顺序排在头部，且排在最后的是 `TAIL_SECTION`。

    钉的是**位置**（规则节不许漂到尾部），不是「尾部只剩链接」——
    后者盘上不成立，见 `MUST_SURVIVE` 上面那段注释。
    """
    if not heads:
        return ["AGENTS.md 里一个 `## ` 小节都没有"]
    bad = []
    held = [(p, _find(heads, p)) for p in MUST_SURVIVE]
    held = [(p, i) for p, i in held if i is not None]
    for (a, ia), (b, ib) in zip(held, held[1:]):
        if ib <= ia:
            bad.append(f"「{b}」排在「{a}」之前，规则节的位置漂了")
    if not heads[-1].startswith(TAIL_SECTION):
        bad.append(f"排在最后的是「{heads[-1]}」而不是指针节「{TAIL_SECTION}」")
    return bad


def _unpinned(heads: list[str]) -> list[str]:
    """既没被 `MUST_SURVIVE` 钉住、又不是尾部牺牲区的小节。

    有了这条，`MUST_SURVIVE` 就不再靠人手抄全 —— 元组漏钉某一节（本仓库真漏过两节，
    见 `test_dropping_any_pinned_section_goes_red` 之前）这件事本身会红，而不是等到
    那一节被砍掉时才发现没人守它。
    """
    out = []
    for h in heads:
        if h.startswith(TAIL_SECTION):
            continue
        if not any(h.startswith(p) for p in MUST_SURVIVE):
            out.append(h)
    return out


def _doc_chain(root: Path) -> list[Path]:
    """Codex 会累计的所有 AGENTS.md（正本 + 任何嵌套的入口文件）。"""
    out = []
    for p in sorted(root.rglob("AGENTS.md")):
        rel = p.relative_to(root)
        if set(rel.parts[:-1]) & SKIP_DIRS:
            continue
        out.append(p)
    return out


def _total_bytes(paths: list[Path]) -> int:
    return sum(_bytes(p) for p in paths)


class CoreAgentsFitsTheTightestGate(unittest.TestCase):
    def test_agents_md_is_within_budget(self):
        raw = (ROOT / "AGENTS.md").read_bytes()
        n = len(raw)
        room = LIMIT - n
        includes = raw.count(b"@[")
        buffer_now = (
            f"本文件当前有 {includes} 处 `@[` 引用"
            + ("，一条展开都没有 —— 那 "
               f"{AGY_GATE - LIMIT} B 眼下不保护任何真实存在的东西，"
               "它只在真用 `@[label](path)` 引用别的文件时才起作用"
               if includes == 0 else
               f"，展开后的字节必须仍 ≤ {AGY_GATE} B")
        )
        self.assertLessEqual(
            n, LIMIT,
            f"AGENTS.md 盘上 {n} B，比预算 {LIMIT} B 多出 {-room} B —— 要回到预算内，"
            f"得先按下面的办法搬走**至少 {-room} B**。\n"
            f"agy 的闸门是 {AGY_GATE} B，而且是**静默截断**：超了不报错，"
            f"排在后面的规则直接消失，agent 与用户都不知道少了什么。\n"
            f"字节从哪来：`LIMIT` 到 `AGY_GATE` 之间那 {AGY_GATE - LIMIT} B 是留给 "
            f"`@[label](path)` **展开**的缓冲（闸门按展开之后算），不是给你加规则的额度；"
            f"{buffer_now}。\n"
            f"这条预算没打算留可白拿的余量：在这里「加一条规则」不是写一句就多一句，"
            f"而是**同一次提交里加一句、搬一段**的那笔交易。\n"
            f"「搬着加」的做法：\n"
            f"  1. 叙述、实测记录、带日期的经过 → `docs/why/<主题>.md`；"
            f"各工具入口说明 → `docs/tool-entries.md`；索引表 → `workflows/INDEX.md`；\n"
            f"  2. **规则句本身一律留在 `AGENTS.md`**，搬走的只是它背后的经过；\n"
            f"     ⚠️ **「留着」也包括不改写那一个字。** 有测试逐字钉着规则句里的\n"
            f"     具体字串，不只是钉着规则本身：实测 2026-10-13 一天栽了两次——\n"
            f"     「「浏览器能力」不是这个仓库要你装的东西」被顺手改成「不由本仓库提供」，\n"
            f"     能力表里 PDF 那行的「（cp936）」被删。前一句是搬到 `docs/why/` 时\n"
            f"     **特意留在原处**的常驻规则，后一句让「`-enc UTF-8` 不是可选的」\n"
            f"     从一条可核的指令退化成偏好。**压缩搬的是叙述，不是措辞。**\n"
            f"  3. 在原处留一句「见 X」的指针，并把 `tests/"
            f"test_demoted_sections_have_a_reader.py` 里 `POINTER_FLOOR` 的条数一并改掉"
            f"（那条按**条数**验指针，指针少一处就红）；\n"
            f"  4. 搬走的字节数 ≥ 加进来的字节数，否则这条照旧红。\n"
            f"四条都做完还是超 → 回来找用户裁定，别自己改 `LIMIT`/`AGY_GATE`。")

    def test_the_codex_cumulative_gate(self):
        """Codex 的 32 KiB 是**跨 AGENTS.md 累计**，所以嵌套一份就等于多吃一口。

        与上一条测的不是同一个量：那条管根文件自己够不够小，这条管入口链加起来。
        """
        chain = _doc_chain(ROOT)
        total = _total_bytes(chain)
        self.assertLessEqual(
            total, CODEX_GATE,
            f"Codex 入口链累计 {total} B（{[str(p.relative_to(ROOT)) for p in chain]}），"
            f"闸门 {CODEX_GATE} B，同样**静默截断**。")

    def test_every_must_survive_section_is_still_there(self):
        heads = _h2((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(_missing_rules(heads), [],
                         "这些节从 AGENTS.md 的标题里消失了 —— 瘦身只许搬家，不许删规则")

    def test_the_pinned_rule_sections_keep_their_reading_order(self):
        """规则节的位置：按元组顺序递增，且最后一名是 `TAIL_SECTION`。

        这条只管**位置**（规则不许漂到会被先砍的地方），不管「砍掉的是不是纯链接」
        —— 后者盘上不成立，见 `MUST_SURVIVE` 上面的注释与下面那条测试。
        """
        heads = _h2((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(_order_violations(heads), [],
                         f"节序不对了：有规则节漂到了会被先砍的位置。当前节序 {heads}")

    def test_the_why_pointers_are_outside_the_sacrifice_zone(self):
        """截断真发生时，**依据层不能变成孤儿**：`docs/why/` 的指针必须全在尾部之前。

        agy 保头砍尾，所以 `_sacrifice_zone_start()` 之后的字节是「先掉的那一段」。
        搬走的经过若只剩尾部指着它，截断之后就是「规则还在、依据没了」——
        与 `tests/test_demoted_sections_have_a_reader.py` 防的同一件事，只是从截断这一侧防。
        这条管**截断**，`_order_violations` 管**位置**；尾部那两条常驻规则真会被砍，
        这条不假装它们不会。
        """
        raw = (ROOT / "AGENTS.md").read_bytes()
        start = _sacrifice_zone_start(raw)
        self.assertIsNotNone(start, f"找不到尾部节「{TAIL_SECTION}」，偏移无从算起")
        hits = _needle_offsets(raw, WHY_POINTER_MARK)
        # 空扫描会让断言恒绿，所以先要求它真的扫到了东西。
        self.assertGreater(len(hits), 0,
                           f"`AGENTS.md` 里一处 `{WHY_POINTER_MARK}` 指针都没有 —— "
                           "要么搬家指针被删了，要么标记改了名，两种都得有人看见")
        stranded = [off for off in hits if off >= start]
        self.assertEqual(
            stranded, [],
            f"这些 `{WHY_POINTER_MARK}` 指针住在「{TAIL_SECTION}」之后"
            f"（盘上偏移 {stranded}，尾节从 {start} 起）：真撞 {AGY_GATE} B 闸门时"
            "截断会把指针砍掉，规则留下而依据没了。把它们挪回各自规则节里。")

    # ---- 对照/变异用例：上面几条恒绿不算证据 --------------------------------

    def test_every_section_is_pinned_or_is_the_sacrifice_zone(self):
        """`AGENTS.md` 里每一个 `## ` 节都必须被**归类**：钉住，或明说是尾部牺牲区。

        这条不是「再验一遍顺序」，它管的是**元组自己的完整性**：新加一节而忘了钉，
        那条节序断言照样绿（它只比已钉项的相对位置），于是这节从此没人守。
        """
        heads = _h2((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        loose = _unpinned(heads)
        self.assertEqual(
            loose, [],
            f"这些小节没被 `MUST_SURVIVE` 钉住，也不是尾部牺牲区「{TAIL_SECTION}」："
            f"{loose}。是**规则**就加进元组（截断时它必须活着）；"
            f"是**纯按需材料**才允许留在尾部之后，而尾部那一节现在还要在"
            "`_order_violations` 里保持最后一名。")

    def test_dropping_any_pinned_section_goes_red(self):
        """元组里**每一项**都得单独证明会咬 —— 元组变长不等于每条都被咬过。

        这一轮新增的 `往 candidate.md 里写东西` 与 `资料没填完是分档的` 两节，
        当初就是「恒绿的守卫漏钉」的形状：把它们的标题抹掉，上面那条测试报的就是它们。
        """
        heads = _h2((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        for prefix in MUST_SURVIVE:
            i = _find(heads, prefix)
            self.assertIsNotNone(i, f"元组里的「{prefix}」在本文件找不到对应标题")
            gutted = heads[:i] + heads[i + 1:]
            self.assertEqual(_missing_rules(gutted), [prefix],
                             f"把「{prefix}」的标题抹掉而探测器没报红 —— 这条钉不住")
            self.assertEqual(_unpinned(gutted), [],
                             f"「{prefix}」没了却没被 `MUST_SURVIVE` 认出来")

    def test_the_missing_detector_can_fire(self):
        """`_missing_rules` 真的会报缺 —— 否则「规则节都还在」那条是空断言。"""
        self.assertEqual(_missing_rules(["## 角色"]),
                         [p for p in MUST_SURVIVE if p != "## 角色"])
        self.assertEqual(_missing_rules(list(MUST_SURVIVE)), [])
        # 只在正文里出现过一次字面量，不算「这条规则还在」。
        self.assertEqual(_missing_rules(["## 别的", "## 又一句"]),
                         list(MUST_SURVIVE))

    def test_the_order_detector_can_fire(self):
        heads = _h2((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(_order_violations(heads), [])
        # 把尾部节挪到最前（= 规则漂到会被先砍的位置）必须报红。
        moved = [heads[-1]] + heads[:-1]
        self.assertTrue(_order_violations(moved), f"探测器没反应：{moved}")
        # 两条规则节互换位置也必须报红。
        swapped = list(heads)
        i = _find(swapped, "## 会话开始")
        j = _find(swapped, "## 角色")
        swapped[i], swapped[j] = swapped[j], swapped[i]
        self.assertTrue(_order_violations(swapped), f"探测器没反应：{swapped}")
        self.assertEqual(_order_violations([]), ["AGENTS.md 里一个 `## ` 小节都没有"])

    def test_the_sacrifice_zone_detector_can_fire(self):
        """`_sacrifice_zone_start` / `_needle_offsets` 真能认出「指针掉进截断区」。"""
        real = (ROOT / "AGENTS.md").read_bytes()
        start = _sacrifice_zone_start(real)
        self.assertIsInstance(start, int)
        self.assertLess(start, len(real), "尾部节起始偏移该在文件内部")
        hits = _needle_offsets(real, WHY_POINTER_MARK)
        self.assertGreater(len(hits), 0)
        self.assertEqual([o for o in hits if o >= start], [],
                         "真实文件在这里就该红了，别拿它当控制用例")
        # 合成一份「指针被搬进尾部之后」的文本：必须报出 stranded 偏移。
        probe = "## 工具特化\r\n尾巴\r\n## 规则\r\n见 docs/why/a.md\r\n".encode("utf-8")
        stranded = [o for o in _needle_offsets(probe, WHY_POINTER_MARK)
                    if o >= _sacrifice_zone_start(probe)]
        self.assertEqual(len(stranded), 1, f"探测器没反应：{stranded}")
        # 同一句写在尾部之前则必须不报 —— 否则这条是恒红的死断言。
        ok = "## 规则\r\n见 docs/why/a.md\r\n## 工具特化\r\n尾巴\r\n".encode("utf-8")
        self.assertEqual([o for o in _needle_offsets(ok, WHY_POINTER_MARK)
                          if o >= _sacrifice_zone_start(ok)], [])

    def test_the_byte_account_is_disk_bytes_not_characters(self):
        """CRLF 口径：按 `len(text)` 数会把余量算多，这条钉住用的哪个口径。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "crlf.md"
            p.write_bytes("行一\r\n行二\r\n".encode("utf-8"))
            raw = _bytes(p)
            decoded = len(p.read_text(encoding="utf-8"))
            self.assertGreater(
                raw, decoded,
                f"盘上 {raw} B 不该多于解码后 {decoded} 字符 —— read_bytes 口径失效")
            self.assertEqual(_total_bytes([p, p]), raw * 2)

    def test_the_chain_detector_counts_nested_docs(self):
        """探测器认得出「再嵌套一份 AGENTS.md 会一起吃掉 32 KiB」。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("根\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "AGENTS.md").write_text("嵌套\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "AGENTS.md").write_text("不该被数\n", encoding="utf-8")
            chain = _doc_chain(root)
            self.assertEqual(len(chain), 2, f"入口链应该是 2 份：{chain}")
            self.assertGreater(_total_bytes(chain), _bytes(root / "AGENTS.md"))


if __name__ == "__main__":
    unittest.main()
