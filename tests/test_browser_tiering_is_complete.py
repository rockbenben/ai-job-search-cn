"""讲「怎么用浏览器取数」的地方，三层顺位不能只讲两层。

## 漏的总是第 1 层

`AGENTS.md`「取数渠道的顺位（别搞反）」定的是四层，最上面那层根本不经过浏览器：

| 顺位 | 用什么 | 为什么在这个位置 |
|---|---|---|
| 1 | **你所在 AI 工具自带的浏览器能力** | 驱动的就是用户自己那个已登录的 Chrome，登录态天然带着，用户不必装任何第三方东西 |
| 2 | `web-access` skill 的 CDP 代理 | 只在没有第 1 层、或它够不着时才用。**第三方全局技能，本项目不附带** |
| 3 | `site:` 域名限定搜索 | 前两层都没有时的兜底，字段少得多 |

这套顺位在仓库里有五份副本。实测 `workflows/reference/search-queries.md` 写的是：

    有 `web-access` skill 时走 CDP 流程，否则退到下面的 `site:` 兜底。

**第 1 层整个不见了。** 执行者照它办，会跳过用户已经登录好的浏览器，
直接去要求他装一个本项目并不附带的第三方全局技能——而那一层恰恰是
`AGENTS.md` 反复强调「不要搞反」的那一层，也是唯一不需要用户额外做任何事的。

`AGENTS.md` 还专门写过一句：「**「浏览器能力」不是这个仓库要你装的东西**，
它由你所在的 AI 工具提供」。漏掉第 1 层，正好把这句话推翻了。

## 2026-09-29 搬家之后：清单与实测各在一个地方

顺位是四层（公开 API → 工具自带的浏览器扩展 → `web-access` 的 CDP 代理 → `site:`
兜底）。上面那三条判据数的是**浏览器那三层**，一个字没放宽。

`AGENTS.md` 那一节同时是常驻入口，agy / Codex 会静默截断它，所以逐家实测记录
（BOSS 的 `code:37`、前程的阿里云 WAF、智联的端点 404）搬到了
`workflows/reference/cdp-portals.md`「顺位的逐家实测」——那一份现在是权威，
不再回头把权威指出去。`TheLadderStaysWhereItIsExecutable` 钉的就是这条边界：
**四层清单按顺序 + 禁令 + 「浏览器能力不是要你装的」留在 `AGENTS.md`，
逐家实测只能在 `cdp-portals.md` 那一节里。**

## 判据

一份文件只要同时讲到第 2 层（`web-access`）和第 3 层（`site:` 兜底），
它就是在描述这套顺位——那它必须也讲第 1 层。判据不看措辞，看**这三层在不在**。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TIER1 = re.compile(r"工具自带的浏览器|自带的浏览器能力|浏览器扩展")
TIER2 = "web-access"
TIER3 = re.compile(r"`site:`|site: 兜底")


def docs():
    yield from sorted((ROOT / "workflows").rglob("*.md"))
    # **`profile.example/` 也要扫** —— 上一版只在这里加了一段说明、没加这一行，
    # 变异实测当场露馅：把旧文案放回去，整套测试照样全绿。
    yield from sorted((ROOT / "profile.example").glob("*.md"))
    # **`profile.example/` 也要扫。** `/job-setup` 从这里起手生成
    # `profile/search-queries.md`（`job-setup.md` 第 5 步），所以模板里那份阶梯
    # 会**原样进到每个新用户的资料里**。2026-10-14 那里还写着旧的两层
    # （「有 web-access skill 时走 CDP，否则退 site:」——把第 1 层整个漏了），
    # 而这份名单里没有它，所以没人拦。这已经是同一处漏网第二次了：
    # 第一版只扫 workflows + AGENTS/CLAUDE，`SETUP.md` 里那句「CDP 为主、
    # site: 兜底」也一直没人拦，直到把名单扩开。
    # SETUP.md / README.md 也讲这套顺位，而且是**用户先读到**的那两份——
    # 第一版只扫 workflows + AGENTS/CLAUDE，于是 SETUP.md 里那句
    # 「覆盖方式是 CDP 为主、site: 兜底」（跳过第 1 层）一直没人拦。
    for name in ("AGENTS.md", "CLAUDE.md", "SETUP.md", "README.md"):
        p = ROOT / name
        if p.is_file():
            yield p


def describes_tiering(text: str) -> bool:
    return TIER2 in text and bool(TIER3.search(text))


class EveryCopyStatesAllThreeTiers(unittest.TestCase):

    def test_the_scan_finds_copies(self):
        """控制用例：真扫到了讲这套顺位的文件。"""
        found = [p.name for p in docs()
                 if describes_tiering(p.read_text(encoding="utf-8"))]
        self.assertGreaterEqual(
            len(found), 3,
            f"只扫到 {found} 在讲浏览器顺位——判据大概失效了")

    def test_the_authority_still_defines_it(self):
        """控制用例：AGENTS.md 里那节还在，否则本测试没有依据。"""
        self.assertIn(
            "取数渠道的顺位", (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
            "AGENTS.md 里「取数渠道的顺位」一节不见了——本测试失去依据")

    def test_no_copy_drops_tier_one(self):
        bad = []
        for p in docs():
            text = p.read_text(encoding="utf-8")
            if not describes_tiering(text):
                continue
            if not TIER1.search(text):
                bad.append(p.relative_to(ROOT).as_posix())
        self.assertEqual(
            bad, [],
            "这些地方讲了第 2、3 层，却没讲第 1 层：\n  " + "\n  ".join(bad)
            + "\n执行者照它办，会跳过用户已经登录好的浏览器，"
            "\n直接要求他装一个本项目并不附带的第三方全局技能。"
            "\n（AGENTS.md：「「浏览器能力」不是这个仓库要你装的东西」）")


CDP = ROOT / "workflows" / "reference" / "cdp-portals.md"

#: 四层清单，按顺序。少一层、换一层、把第 1 层挪到浏览器之后，都在这里红。
LADDER = ("平台自己的公开 API", "Claude 浏览器扩展",
          "web-access skill（CDP 代理）", "`site:` 域名限定网络搜索")

#: 从 `AGENTS.md` 搬走的逐家实测记录。它们出现在 `AGENTS.md` 就是搬家搬漏了，
#: 出现在 `cdp-portals.md` 的「顺位的逐家实测」之外就是权威没落到位。
MEASUREMENTS = ("code:37", "阿里云 WAF", "端点已 404")


def flat(s: str) -> str:
    """压掉换行与 markdown 标记，只比句子本身（`AGENTS.md` 每行 ~40 字，
    句子都会被硬折行，按行比对等于没比对）。"""
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；:：、（）「」]) +(?=[一-鿿，。；:：、（）「」])", "", s)


def section(text: str, heading: str) -> str:
    """从某个标题到下一个任意级别的标题。找不到标题就直接红——不去测一个
    空字符串，那会把「节被删了」报成「句子不在里面」，读的人会去找错地方。"""
    i = text.index(heading)
    m = re.search(r"^#{1,4} ", text[i + len(heading):], flags=re.M)
    return text[i: i + len(heading) + (m.start() if m else len(text) - i)]


class TheLadderStaysWhereItIsExecutable(unittest.TestCase):
    """2026-09-29 权威移交的守门人：搬家只搬散文，不搬顺位，也不搬禁令。"""

    def test_agents_still_holds_the_four_tiers_in_order(self):
        raw = section(
            (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
            "### 取数渠道的顺位（别搞反）")
        seg = flat(raw)
        at = [seg.find(t) for t in LADDER]
        self.assertNotIn(-1, at, f"四层清单缺层：{list(zip(LADDER, at))}")
        self.assertEqual(at, sorted(at), "四层清单顺序被改了")
        # 光比名字的顺序还不够：把清单编号改成「3. 公开 API」也是一次换层，
        # 而读的人信的是编号。所以编号本身也要按 1-2-3-4 排。
        markers = re.findall(r"(?m)^(\d+)\. \*\*", raw)
        self.assertEqual(markers, ["1", "2", "3", "4"],
                         f"四层清单的编号不是 1-4 顺排：{markers}")

    def test_the_prohibition_stayed_behind(self):
        """禁令搬走 = 谁都能为了「凑第 1 层」去破反爬。这条不跟着搬家。"""
        seg = flat(section(
            (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
            "### 取数渠道的顺位（别搞反）"))
        for rule in ("不要为了凑第 1 层去破解反爬",
                     "这三家没有可用的免登录 API",
                     "绕过 WAF 或反爬挑战不做",
                     "平台给了什么",
                     "「浏览器能力」不是这个仓库要你装的东西"):
            self.assertIn(rule, seg, f"常驻的那条规则不见了：{rule}")

    def test_the_measurements_left_agents_and_landed_in_cdp_portals(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for tok in MEASUREMENTS:
            self.assertNotIn(
                tok, agents,
                f"`AGENTS.md` 里还留着逐家实测（{tok}）——常驻文件又被实测散文占满了")
        seg = section(CDP.read_text(encoding="utf-8"), "### 顺位的逐家实测")
        for tok in MEASUREMENTS:
            self.assertIn(
                tok, seg,
                f"「顺位的逐家实测」这一节里没有 {tok}：搬家搬漏了，"
                "而 `AGENTS.md` 那份已经删掉——这条实测记录现在哪都没有")

    def test_cdp_portals_states_it_is_the_authority(self):
        """两处反向引用（原第 57、152 行）改成「本文件是权威」，别再指着别人。"""
        text = CDP.read_text(encoding="utf-8")
        seg = section(text, "### 顺位的逐家实测")
        self.assertIn("这里就是正本", seg, "新落点没声明自己是权威")
        self.assertIn("顺位的逐家实测", text)
        for stale in ("顺位见 `AGENTS.md`", "（`AGENTS.md`「取数渠道的顺位」）"):
            self.assertNotIn(stale, text, f"还留着旧的反向引用：{stale}")



if __name__ == "__main__":
    unittest.main()
