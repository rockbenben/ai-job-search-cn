# -*- coding: utf-8 -*-
"""日常路径必须只教「填资料 → 跑 auto → 你自己发 → 记一笔」，不能还教已自动化的中间步。

用户 2026-08-13：「你应该有几个简单的命令，让新用户一次跑到头」。
查下来这条脊梁**从来没被说出来过**，而入口文档教的还是旧的三步：
`/job-setup` → `/job-scrape` → `/job-rank`。

那条路现在有两处空转：`/job-scrape` 抓完自动接评分（job-scrape.md Step 5.5），
`/job-auto` 又把抓、评、出材料整个包了。多教一步的代价不是多敲一次，
是让人以为不敲就会漏东西——新用户没有判断力去分辨哪步是多余的。

## 后来它从两条变成了三条，而只有一半跟着改（2026-08-20 发现）

`/job-outcome` 进脊梁之后，`AGENTS.md` 改成了「只有三条命令」，本文件第一条断言
也跟着查三个命令——**但文件名、本段说明、README 全停在「两条」**。
于是同一个概念在同一个仓库里活着两个数：入口文档说三条，落地页说两条。

代价不是数字不好看：**README 的快速开始表当时只有两行，从没告诉新用户投完要记一笔**，
而催进度、备面、谈薪全都从那一笔长出来。少教一步和多教一步一样有害，
只是方向相反。

所以下面补了 `TheDocsAgreeOnTheNumber`：两份文档里那个数必须一致，
且必须等于 `SPINE` 的实际长度。**脊梁再变时，改一处而漏另一处会当场红。**
"""

import re
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jsx  # noqa: E402  两标记切片与 firstrun 都在这儿，别再写第二份

README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
COMMANDBOOK = (ROOT / "web" / "src" / "components"
               / "CommandBook.tsx").read_text(encoding="utf-8")
APP_TSX = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

#: 这条脊梁本身。改它就得改两份文档里的那个数——下面那条断言会盯着。
SPINE = ("/job-setup", "/job-auto", "/job-outcome")

#: 中文数词。脊梁不会长到需要第六个。
CN_NUM = {1: "一", 2: "两", 3: "三", 4: "四", 5: "五"}

#: 只认「日常只有/只用 N 条」这个说法。**不能宽到匹配任何「N 条命令」**——
#: `AGENTS.md` 里还有一句「三条命令都会写这一个文件」，说的是
#: `/job-setup`、`/job-expand`、`/job-rank` 都写 candidate.md，是**另一个三**。
#: 宽正则会把它一起框进来，脊梁一变它就误报。
_DAILY = re.compile(r"日常(?:只有|只用|只需)([一两三四五])条")
_HEADING = re.compile(r"一次跑到头：只有([一两三四五])条命令")


class TheSpineIsStated(unittest.TestCase):

    def test_agents_names_the_spine(self):
        self.assertIn("一次跑到头", AGENTS)
        for cmd in SPINE:
            with self.subTest(cmd=cmd):
                self.assertIn(cmd, AGENTS)

    def test_the_spine_says_the_human_step(self):
        """三条命令之间夹着「你自己去发」，不说清就会有人等工具替他投。"""
        block = AGENTS[AGENTS.index("## 一次跑到头"):AGENTS.index("## 工作流索引")]
        self.assertIn("你自己去招聘网站", block)
        self.assertIn("唯一要人的一步", block)

    def test_readme_no_longer_teaches_the_dead_step(self):
        """README 不能再把 /job-rank 当成新用户必敲的一步。"""
        for m in re.finditer(r"^.*`/job-scrape`\s*(?:→|->)\s*`/job-rank`.*$",
                             README, re.M):
            self.assertTrue(m.group(0).lstrip().startswith(">"),
                            f"旧三步路径还活着：{m.group(0).strip()[:70]}")

    def test_readme_leads_with_auto(self):
        self.assertIn("/job-auto", README)
        first = README.index("/job-auto")
        rank = README.find("/job-rank")
        self.assertTrue(rank == -1 or first < rank,
                        "README 里 /job-rank 出现得比 /job-auto 还早，新用户会先学到旧路")


class TheDocsAgreeOnTheNumber(unittest.TestCase):
    """入口文档、落地页说的必须是同一个数，且等于脊梁的实际长度。

    这条是 2026-08-20 补的：此前**没有任何东西在盯 README 的那个数**，
    于是 `/job-outcome` 进脊梁之后，`AGENTS.md` 改了、README 没改，
    两个数并行活了一阵谁也没发现。
    """

    DOCS = (("AGENTS.md", AGENTS), ("README.md", README))

    def test_every_doc_states_the_count(self):
        for name, text in self.DOCS:
            with self.subTest(doc=name):
                self.assertTrue(
                    _DAILY.search(text),
                    f"{name} 没说「日常只有/只用 N 条」—— 新用户得先知道要记几条命令")

    def test_the_counts_agree_with_each_other_and_with_the_spine(self):
        want = CN_NUM[len(SPINE)]
        for name, text in self.DOCS:
            for m in _DAILY.finditer(text):
                with self.subTest(doc=name, said=m.group(1)):
                    self.assertEqual(
                        m.group(1), want,
                        f"{name} 说日常 {m.group(1)} 条，而脊梁实际是 {len(SPINE)} 条"
                        f"（{'、'.join(SPINE)}）——同一个概念两处各记一份就会这样分叉")

    def test_the_agents_heading_agrees_too(self):
        """标题里那个数也要跟着改——它是最先被读到的一处。"""
        m = _HEADING.search(AGENTS)
        self.assertIsNotNone(m, "AGENTS.md 的「一次跑到头」标题不见了或改了写法")
        self.assertEqual(m.group(1), CN_NUM[len(SPINE)],
                         "AGENTS.md 的标题和正文自己就对不上")

    def test_readme_actually_teaches_all_three(self):
        """光说「三条」不算数——README 的快速开始表里三条都得出现。

        实测就是这么漏的：README 说了两条、表里也只有两行，`/job-outcome`
        只在功能列表里露过面，新用户照着快速开始走完根本不会去记那一笔。
        """
        self.assertEqual(_readme_daily_commands(README), list(SPINE),
                         "快速开始要按顺序各介绍一次三条日常命令")
        quick = README.split("## 快速开始", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(quick, r"由你.*(?:发送|投递)", "快速开始要说明由用户发送材料")

    def test_table_headers_and_argument_examples_can_change(self):
        changed = README.replace("| 日常命令 |", "| 输入的命令 |")
        changed = changed.replace("/job-outcome <公司>", "/job-outcome [公司]")
        self.assertEqual(_readme_daily_commands(changed), list(SPINE))

    def test_mentions_in_descriptions_cannot_replace_command_rows(self):
        for command in SPINE:
            with self.subTest(command=command):
                lines = README.splitlines()
                changed = "\n".join(line for line in lines
                                    if not line.startswith(f"| `{command}"))
                changed = changed.replace("| 会得到什么 |", f"| 说明 `{command}` |")
                self.assertNotEqual(_readme_daily_commands(changed), list(SPINE))

    def test_duplicate_or_reordered_commands_are_rejected(self):
        row = next(line for line in README.splitlines()
                   if line.startswith("| `/job-setup`"))
        duplicate = README.replace(row, row + "\n" + row, 1)
        self.assertNotEqual(_readme_daily_commands(duplicate), list(SPINE))
        swapped = README.replace("`/job-setup`", "`/job-swap`")
        swapped = swapped.replace("`/job-auto`", "`/job-setup`")
        swapped = swapped.replace("`/job-swap`", "`/job-auto`")
        self.assertNotEqual(_readme_daily_commands(swapped), list(SPINE))


def _readme_daily_commands(text: str) -> list[str]:
    """只读快速开始表格中的完整命令单元格，说明里的提及不算一行。"""
    quick = text.split("## 快速开始", 1)[1].split("\n## ", 1)[0]
    candidates = []
    for table in re.findall(r"^\|[^\n]*(?:\n\|[^\n]*)*", quick, re.M):
        commands = []
        for line in table.splitlines():
            for cell in line.strip("|").split("|"):
                match = re.fullmatch(r"`(/job-[a-z-]+)(?:[ \t]+[^`]*)?`", cell.strip())
                if match:
                    commands.append(match.group(1))
        if set(commands).intersection(SPINE):
            candidates.append(commands)
    if len(candidates) != 1:
        return []
    return candidates[0]


def _teaches_the_spine(block: str) -> list[str]:
    """block 里缺了脊梁哪几条——README/CommandBook 共用同一条判据。"""
    return [cmd for cmd in SPINE if cmd not in block]


def _every_count_in(block: str, pattern: str) -> list[str]:
    """block 里**所有**「…N 条」的那个数，不是只取第一个。

    `re.search` 只返回首个匹配 —— 而这几处每处都不止一份写法
    （`CommandBook.tsx` 顶部 JSDoc 里有一份、渲染的 kicker 里有一份；
    `App.tsx` 的 aria-label 一份、可见的 `<p>` 一份）。只查首个，
    等于让「谁先出现」决定判据查的是注释还是用户真看到的字。
    """
    return re.findall(pattern, block)


class ThePanelSpineAgreesToo(unittest.TestCase):
    """面板的命令帮助（`CommandBook.tsx`）是 UI 侧的快速开始，也要教全脊梁那 N 条。

    实测漏过（2026-09-03 发现）：脊梁从两条变三条时，md 都改了、
    **面板这块 .tsx 悄悄停在「日常就这两条」、漏了 `/job-outcome`**——而
    `TheDocsAgreeOnTheNumber` 只盯 md，够不着 .tsx。同一个概念又在
    文档说三、落地页说两分叉了一次。这条把 .tsx 也钉到 `SPINE` 上。

    ⚠️ 数的正则不能对整份文件搜——`CommandBook.tsx` 顶部的 JSDoc 注释里
    也写着「日常就这三条」（那是给读代码的人看的说明，不是渲染出来的字）。
    `re.search` 只返回第一个匹配，注释排在真正的 kicker 前面，于是量的其实
    是注释、不是界面。**先切到 `cmdbook-spine` 那个 div 再搜**，注释天然
    被切在外面。
    """

    def test_the_panel_states_the_count(self):
        block = jsx.between(COMMANDBOOK, "cmdbook-spine", "{!spineOnly")
        said = _every_count_in(block, r"日常就这([一两三四五])条")
        self.assertTrue(
            said, "CommandBook.tsx 的脊梁块（渲染出来的那个 kicker，不是注释里的）"
                  "不见了「日常就这 N 条」")
        for n in said:
            with self.subTest(said=n):
                self.assertEqual(
                    n, CN_NUM[len(SPINE)],
                    f"面板说日常 {n} 条，而脊梁实际是 {len(SPINE)} 条"
                    f"（{'、'.join(SPINE)}）—— md 改了 .tsx 没跟上，又分叉了")

    def test_the_panel_teaches_all_of_the_spine(self):
        block = jsx.between(COMMANDBOOK, "cmdbook-spine", "{!spineOnly")
        missing = _teaches_the_spine(block)
        self.assertEqual(
            missing, [],
            f"面板脊梁块里缺了 {missing} —— 那它们在界面上就没被教到")

    def test_the_stylesheet_comment_agrees_too(self):
        """`cockpit.css` 里给脊梁块配样式那句注释也写着「日常那 N 条命令」。

        它是这个数的第 4 份手抄件，而**在这条加进来之前没有任何测试读过 css**
        —— 那份可以永远停在旧数上，没有任何东西会红。既然已经手抄了，
        至少让它跟着一起红。
        """
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
        said = _every_count_in(css, r"日常那([一两三四五])条命令")
        self.assertTrue(said, "cockpit.css 里给 .cmdbook-spine 的那句注释不见了")
        for n in said:
            with self.subTest(said=n):
                self.assertEqual(
                    n, CN_NUM[len(SPINE)],
                    f"cockpit.css 说日常 {n} 条，而脊梁实际是 {len(SPINE)} 条")

    def test_the_onboarding_view_agrees_on_the_count(self):
        """`App.tsx` 那句「先跑这 N 条」是给还没建档的人看的第一屏。

        **那一块里有两处**：`<section>` 的 `aria-label` 和可见的 `<p>`。
        两处都要查 —— 只查首个的话，改了可见那句、没改 aria-label，
        判据照样绿，而用户看到的正是没改到的那半边。

        它只报数、不重复列命令：命令本身由它渲染的
        `<CommandBook groups={...} spineOnly />` 教（上面两条测试管）。
        """
        self.assertIn(jsx.FIRSTRUN, APP_TSX, "App.tsx 的新手首屏那一块没了")
        block = jsx.firstrun(APP_TSX)
        said = _every_count_in(block, r"先跑这([一两三四五])条")
        self.assertTrue(said, "App.tsx 的新手首屏不见了「先跑这 N 条」")
        for n in said:
            with self.subTest(said=n):
                self.assertEqual(
                    n, CN_NUM[len(SPINE)],
                    f"App.tsx 说先跑这 {n} 条，而脊梁实际是 {len(SPINE)} 条"
                    f"——第三处又漂了")


class AutoRunsUntilItCannot(unittest.TestCase):
    """auto 不给 target 就该跑到挖不动，而不是攒够 5 个收工。"""

    def test_default_is_not_a_constant(self):
        t = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("不给就是不设目标", t)
        for line in t.splitlines():
            if "SHORTLIST_FLOOR" in line and "默认" in line:
                self.assertTrue(line.lstrip().startswith(">"),
                                f"默认又变回常数了：{line.strip()[:70]}")

    def test_the_loop_honours_it(self):
        """循环第 3 步得说清没给 target 时不生效，否则规则与实现两张皮。"""
        t = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("没给 --target 时这条不生效", t)


class NoWorkflowStillTeachesTheDeadStep(unittest.TestCase):
    """那个死步骤 README 改了，**工作流里没跟**（2026-09-01 实测）。

    `job-notion-sync.md` Step 2 同步集为空时印的是
    「先跑 `/job-scrape` 和 `/job-rank`」—— 一句话里两个错：

    1. **给了两条命令。** `AGENTS.md`「每一处引导都要写出该敲的命令」立着
       「一条引导对应**一条**命令 —— 给两条以上，用户就要先做一次选择，
       那正是引导要替他省掉的那一步」。
    2. **第二条是空转。** `/job-scrape` 抓完自动评分（它自己的 Step 5.5），
       正是本文件开头那段说的那个错。

    `test_readme_no_longer_teaches_the_dead_step` 只扫 README ——
    同一句话换个文件就活了下来。判据从「README 里没有」扩到
    「**任何印给用户的引导里都没有**」。

    引用块（`>` 开头）不算：那是记录「原来错在哪」的地方，
    不写下来下一轮就会再犯一次。
    """

    #: 一句引导里串起两条斜杠命令。分隔词只认这几个 —— 命令**清单**
    #: （「`/job-setup`、`/job-scrape`、`/job-rank`」）是列举不是引导，
    #: 顿号不进这张表，否则 README 那三处清单会被误伤。
    CHAINED = re.compile(
        r"跑\s*`?(/job-[a-z-]+)`?\s*(?:和|然后|，然后|再)\s*`?(/job-[a-z-]+)")

    def _prose_lines(self):
        """所有工作流 + 三份入口文档的**正文**行（剥掉 `>` 引用）。"""
        files = sorted((ROOT / "workflows").glob("*.md")) + [
            ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "SETUP.md"]
        for f in files:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith(">"):
                    continue
                yield f.name, i, line

    def test_the_scan_sees_something(self):
        """**先证明扫描不是空的。** 行数为零时下面那条永远绿。"""
        self.assertGreater(sum(1 for _ in self._prose_lines()), 3000,
                           "正文行扫不出来，抽取器八成坏了")

    def test_no_guidance_chains_two_commands(self):
        bad = [f"{n}:{i}  {l.strip()[:90]}"
               for n, i, l in self._prose_lines() if self.CHAINED.search(l)]
        self.assertEqual(
            bad, [],
            "这几处在一句引导里给了两条命令（`AGENTS.md`「一条引导对应一条命令」）："
            + repr(bad))

    def test_the_detector_can_fail(self):
        """变异：那句话回来时要抓得到，而命令清单不误伤。"""
        self.assertTrue(self.CHAINED.search("先跑 `/job-scrape` 和 `/job-rank`"))
        self.assertTrue(self.CHAINED.search("跑 /job-setup 然后 /job-auto"))
        self.assertIsNone(self.CHAINED.search(
            "主线那一行的命令：`/job-setup`、`/job-scrape`、`/job-rank`、`/job-apply`"))


if __name__ == "__main__":
    unittest.main()
