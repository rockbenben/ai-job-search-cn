# -*- coding: utf-8 -*-
"""流程里写「见 Step X」，那个 Step 得真的存在。

2026-08-13 全面检查命令逻辑时扫出来：`job-rank.md` 与 `job-auto.md` 一共 5 处
引用 `Step 7a` / `Step 1.7` / `Step 1.7b`，而**这三个编号从来没在任何标题里出现过**。
内容一直都在（预筛淘汰在 Step 1 里跑、deep-eval set 也在那儿定），只是没编号。

## 它原来只扫 `workflows/`

而**引这些编号最多的地方是 `tests/` 和 `tools/`**：实测 2026-08-31，那两处
点名了某份工作流的步号引用有 **384 条**，守卫一条都没看过。当场捞出两条
断链，指向的还是同一处：`job-interview.md` 的 Step 3.1 / 3.5 —— 那份文件
**自己的正文也按 `（3.1）`「（3.5）」引**，而六个子步的标题写的是 `### 1.`～`### 6.`。
仓库别处一律是 `### 1.5a`、`### 2.6`、`### 5.0` 这种带父级的编号，只有这一处没跟。
同日把标题改成 `### 3.1`–`### 3.6`，引用与标题这才对得上。

隔壁那条同族守卫（`test_cross_references_resolve` 的 `SectionCitationsResolve`）
早就把扫描扩到了 `tests/`，还专门留了一条 `test_the_scan_covers_tests_too` ——
**同一课学过一次，另一条守卫没跟上。**

**引用一个不存在的编号，比不写更糟**——它让读的人以为自己漏看了一节，
翻遍全文找不到，最后只能猜那句话到底指什么。而这份文件是给 AI 执行的，
猜错的后果直接落在用户的投递上。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
WF = sorted((ROOT / "workflows").rglob("*.md"))


def headings(text: str) -> set:
    """标题里定义过的 Step 记号，含 `7a` 这种字母后缀。

    **子步的标题常常不带 `Step` 前缀**（`#### 1a. Check the CLI runtime`、
    `### 5d. 视觉检查`），而引用它们时带（「见 Step 1a」）。两种写法都收——
    第一版只认带前缀的，把 9 个真实存在的子步全报成了断链。
    """
    out = set()
    for m in re.finditer(r"^#+\s*(?:Step\s+|第\s*)?([\d]+(?:\.[\d]+)*[a-z]?)[.:：\s]", text, re.M):
        out.add(m.group(1))
    return out


def citable(text: str) -> set:
    """这份文件里**引得到**的步号：标题里的，加上顶层有序列表项。

    和 `headings()` 分开：那个喂的是「步号顺序对不对」，列表项进去会把它搅乱。
    而人引「第 3 步」时，指的常常正是伪代码里那个 `3.` ——`job-auto.md` 的
    主循环整个是一张有序列表，没有一个标题。
    """
    out = set(headings(text))
    # 列表项前面常有 `**`（`   **7a. 排序 + 取前 M**`）与引用符。
    item = re.compile(r"^[\s>*#-]{0,8}(\d+(?:\.\d+)*[a-z]?)[.)、]\s", re.M)
    out |= set(item.findall(text))
    # **复合编号**：`Step 1` 底下的第 3 点就叫 `Step 1.3`。
    # 这是这些文件自己的写法 —— `job-rank.md` 把第 7 点的标题直接写成
    # `### Step 1.7`，再往下分 `7a` / `7b`。不把它算进来，一半的引用指不到。
    parts = re.split(r"^(?=## )", text, flags=re.M)
    for seg in parts:
        m = re.match(r"##\s*(?:Step\s+|第\s*)?(\d+(?:\.\d+)*[a-z]?)", seg)
        if not m:
            continue
        for sub in item.findall(seg):
            out.add(f"{m.group(1)}.{sub}")
    return out


#: 代码里引工作流步号的写法：`Step 3.1` / `第 1.6c 步`。
_CITE = re.compile(r"Step\s+(\d+(?:\.\d+)*[a-z]?)|第\s*(\d+(?:\.\d+)*[a-z]?)\s*步")


class CodeCitationsResolve(unittest.TestCase):
    """`tests/` 与 `tools/` 里引的步号，也要指得到。

    只判**点了名**的那些 —— 窗口里没出现任何 `xxx.md` 或 `/job-xxx` 时，
    无从知道它说的是哪份文件，跳过（同上面那条的窗口判法）。
    """

    def setUp(self):
        self.heads = {f.name: citable(f.read_text(encoding="utf-8"))
                      for f in WF}
        self.src = [(f, f.read_text(encoding="utf-8", errors="replace"))
                    for d in ("tests", "tools")
                    for f in sorted((ROOT / d).rglob("*.py"))]

    def _cites(self, src=None):
        for f, t in (self.src if src is None else src):
            for m in _CITE.finditer(t):
                win = t[max(0, m.start() - 200):m.end() + 80]
                pool, named = set(), set()
                for g in re.findall(r"`?([\w-]+\.md)`?", win):
                    if g in self.heads:
                        named.add(g)
                        pool |= self.heads[g]
                for g in re.findall(r"/(job-[\w-]+)", win):
                    if g + ".md" in self.heads:
                        named.add(g + ".md")
                        pool |= self.heads[g + ".md"]
                if named:
                    yield (f, m.group(1) or m.group(2),
                           sorted(named), pool)

    def test_the_scan_finds_them(self):
        """**先证明它扫得到东西。** 一条都没收集到时，下面那条在空集上
        永远绿 —— 而「扫不到」正是这条守卫此前的样子（它只看 workflows/）。
        """
        n = sum(1 for _ in self._cites())
        self.assertGreater(n, 200, f"只扫到 {n} 条，扫描八成坏了")

    def test_the_detector_can_fail(self):
        """喂一个真不存在的编号进去，它得报出来。

        本文件的说明里逐字引着 `Step 7a` / `Step 1.7b` —— 那是它当年抓到的
        断链，写下来是留证据。原来为此把本文件整个排除在扫描之外，而变异实测
        证明那句排除**一条都挡不住**：复合编号一认，`job-rank.md` 的 `**7a.`
        `**7b.` 就都指得到了，两个例子如今都是真编号。排除删了，改成这一条。
        """
        # 编号**拼出来**，源码里一个字面的步号都不能留 —— 扫描现在也扫
        # 本文件，留个字面的就等于亲手往语料里塞一条断链（自己绊自己一跤）。
        n = "9" + "1.7"
        fake = [(Path("fake.py"), f"见 `job-rank.md` Step {n} 那一节")]
        got = [step for _f, step, _n, pool in self._cites(fake)
               if step not in pool]
        self.assertEqual(got, [n], "假的步号没被认出来")

    def test_every_cited_step_exists(self):
        bad = []
        for f, step, named, pool in self._cites():
            # `Step 1` 命中 `Step 1a` 也算 —— 那是同一节的细分。
            if step in pool or any(h.startswith(step + ".")
                                   or (h[:-1] == step and h[-1:].isalpha())
                                   for h in pool):
                continue
            bad.append(f"{f.name}: 引 {named} 的第 {step} 步，那几份里都没有")
        self.assertEqual(bad, [], NL.join(bad))


class StepReferencesResolve(unittest.TestCase):

    def setUp(self):
        self.text = {f.name: f.read_text(encoding="utf-8") for f in WF}
        self.heads = {n: headings(t) for n, t in self.text.items()}
        self.assertTrue(any(self.heads.values()), "一个 Step 标题都没解析到")

    def test_every_reference_points_at_a_real_step(self):
        bad = []
        for name, t in self.text.items():
            for m in re.finditer(r"Step\s+(\d+(?:\.\d+)*[a-z]?)", t):
                step = m.group(1)
                ln = t[:m.start()].count("\n") + 1
                line = t.splitlines()[ln - 1]
                # 点了别的流程文件就去那边找。**看窗口不看行**：
                # 「`/job-scrape` Step 5.5」常被折行拆成两行，只看当前行会漏掉
                # 文件名，把一个正当的跨文件引用报成断链（第一版就是这么误报的）。
                win = t[max(0, m.start() - 200):m.end() + 80]
                pool = set(self.heads.get(name, ()))
                for g in re.findall(r"`?([\w-]+\.md)`?", win):
                    pool |= self.heads.get(g, set())
                # `/job-xxx` 这种写法也算点名（很多地方写命令名不写文件名）
                for g in re.findall(r"/(job-[\w-]+)", win):
                    pool |= self.heads.get(g + ".md", set())
                if step in pool:
                    continue
                # `Step 1` 命中 `Step 1a` 也算——那是同一节的细分
                if any(h.startswith(step) for h in pool):
                    continue
                # 正文里就地定义的子步（「Step 1a：…」出现在列表项里）也认
                if re.search(rf"^\s*[-*\d.]*\s*\**Step\s+{re.escape(step)}\b", t, re.M):
                    continue
                bad.append(f"{name}:{ln} → Step {step}   「{line.strip()[:60]}」")
        self.assertEqual(bad, [],
                         f"这些 Step 引用落不了地（共 {len(bad)} 处）：\n  " + "\n  ".join(bad))

    def test_steps_appear_in_numeric_order(self):
        """Step 标题要按编号从小到大出现 —— 编号本来就是拿来说顺序的。

        ## 实测撞到的那一处

        `job-scrape.md` 里 **Step 4.6 排在 Step 4.5 前面**，而且不只是换了个位置：
        它整个插在 **Step 4 的正文中间**，把 Step 4 那个编号列表劈成两半 ——
        「1. 把这一轮全部岗位写进 seen_jobs.json」在 4.6 之前，
        「2. 只摆出不在已见列表里的岗」在 4.6 之后，中间还夹着 Step 4 的入库
        schema 说明。照着做的执行者走到一半会被支去写词表，回来接着入库。

        `HEAD` 里就是这样（2026-08-21 通读时发现，不是当天改坏的）。

        ## 判据

        比的是**同一份文件里 Step 标题的先后顺序与编号大小是否一致**，
        不看内容、不看措辞。带字母后缀的子步（`5a`/`1b.5`）不参与比较 ——
        它们的排序规则不是数值。
        """
        import re

        PAT = re.compile(r"^#{2,4}\s*(?:Step|第)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:步)?\s*[:：]")
        bad = []
        for f in WF:
            nums = [(float(m.group(1)), n)
                    for n, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
                    if (m := PAT.match(ln))]
            for i in range(1, len(nums)):
                if nums[i][0] < nums[i - 1][0]:
                    bad.append(
                        f"{f.name}: Step {nums[i][0]}(第{nums[i][1]}行) "
                        f"排在 Step {nums[i-1][0]}(第{nums[i-1][1]}行) 之后")
        self.assertEqual(
            bad, [],
            "这些 Step 没按编号顺序出现 —— 编号说的就是顺序，"
            "照着做的执行者会被支到别处再回来：" + " · ".join(bad))

    # **这里原来有一条拿 `git show HEAD:workflows/job-scrape.md` 回测的负对照，
    # 2026-10-14 删掉。** 它要的是「修复之前那份乱序原文」，而修复早已提交 ——
    # HEAD 上永远是修好的那份，于是它每次都走
    # 「HEAD 里那份已经是修好的了」这一支跳过，**而且永远不会再生效**：
    # 修复不可能被撤销。真实原文也取不回来了（那次修复早于本仓库压平历史的那一刀）。
    #
    # 下面 `test_the_detector_can_fail` 用钉死的字面量守同一件事，它会一直有效；
    # 真实文件那一侧由同文件的正向用例读真文件守着。两侧都在，丢的只是那个
    # 「更强但已失效」的第三份。

    def test_the_detector_can_fail(self):
        self.assertIn("1.7", headings("### Step 1.7：这一轮评哪几个"))
        self.assertIn("7a", headings("### Step 7a: Write Approved Updates"))
        self.assertNotIn("9", headings("### Step 1: Load State"))


if __name__ == "__main__":
    unittest.main()
