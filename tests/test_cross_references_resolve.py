# -*- coding: utf-8 -*-
"""文档里指出去的东西，得真的指得到。

`test_step_references_resolve.py` 管的是「见 Step X」那一类。这里管另外三类，
它们此前**一条守卫都没有**：

1. **仓库文件路径** —— 反引号里的 `xxx/yyy.md`；
2. **命令名** —— `/job-xxx`（要认两族的技能壳 `.claude/skills/` 与 `.agents/skills/`）；
3. **工具开关** —— 流程里写的 `python tools/xxx.py --flag`，那个 flag 得在 `--help` 里。

第 3 类最要命：AI 会**照着敲**。开关不存在不是「文档不准」，是命令当场退出。

2026-08-13 第 8 轮检查实测：三类各扫一遍，只有第 1 类有问题——`job-add-portal.md`
三处写 `liepin-search/cli/src/helpers.ts`，真实路径是
`.agents/skills/liepin-search/...`。`.agents` 是隐藏目录，照着这个相对路径找，
在仓库根一无所获。文件存在、路径写不全，和不存在一样难找。
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "tools"))
import _entries  # noqa: E402  两族目录名的正本在派生器里，这里不另抄一份

#: 这些前缀是**按活动用户解析**的个人数据路径（`AGENTS.md`「活动用户与多用户」），
#: 仓库根下本来就不该有，不算断链。
PERSONAL = ("profile/", "job_scraper/", "documents/", "reports/", "gmail_sync/",
            "upskill/", "resume/main.typ", "cover_letter/main.typ",
            "job_search_tracker.csv", "templates/active-", "users/")


def _git_ignores(path: str) -> bool:
    """git 会不会 ignore 这个路径。**不要求文件存在** —— 比的是规则。

    不在 git 仓库里（打包分发、tarball）时一律返回 False：那时无从判断，
    宁可报出来让人看一眼，也不要静默放行。
    """
    try:
        r = subprocess.run(["git", "check-ignore", "-q", path],
                           cwd=ROOT, capture_output=True)
    except OSError:
        return False
    return r.returncode == 0


def _docs() -> dict:
    out = {str(f.relative_to(ROOT)): f.read_text(encoding="utf-8")
           for f in (ROOT / "workflows").rglob("*.md")}
    for n in ("AGENTS.md", "CLAUDE.md", "README.md", "SETUP.md", "CONTRIBUTING.md"):
        if (ROOT / n).is_file():
            out[n] = (ROOT / n).read_text(encoding="utf-8")
    # 搬家搬出去的节也要有人扫，否则「某文件的『某节』」这类指针在新家失联没人知道。
    # `docs/tool-entries.md` 是 Task 10 从 `AGENTS.md`「工具特化」搬出去的落点，
    # 姊妹判据 `tests/test_cross_file_section_refs.py` 的名单 2026-09-29 已经扩到它，
    # 这份当时漏了 —— 两份名单各自长，漏的那份就是静默放行。
    # Task 11 的落点 `workflows/reference/cdp-portals.md` 在上面 `workflows/**` 那条里，
    # 不重复列；`docs/superpowers/` 是 gitignore 的会话产物，**永远不进这份名单**
    # （权威不许落在那儿，见 `tools/security_guards.py` 顶部那条教训）。
    # Task 12 的落点 `docs/why/*.md` 同理：搬出去的记录要是没人扫，指向它们的
    # 「某文件的『某节』」就在新家失联也没人知道。
    # 2026-10-14 的落点是 `docs/finding-gaps.md`（从 `CONTRIBUTING.md` 里"怎么先找到
    # 还没被守住的地方"那一节整节搬出去的）—— 这份当时漏了，两条报同一件事。
    for n in ((ROOT / "docs" / "tool-entries.md",)
              + (ROOT / "docs" / "finding-gaps.md",)
              + tuple(sorted((ROOT / "docs" / "why").glob("*.md")))):
        if n.is_file():
            out[str(n.relative_to(ROOT))] = n.read_text(encoding="utf-8")
    return out


class FilePathsResolve(unittest.TestCase):
    """反引号里带目录的仓库路径必须存在。

    只查**带斜杠**的：裸文件名（`candidate.md`）多半是泛指某类文件，不是路径。
    """

    PAT = re.compile(r"`([A-Za-z0-9_.][A-Za-z0-9_./-]*/[A-Za-z0-9_.-]+"
                     r"\.(?:md|py|ts|tsx|typ|json|csv))`")

    def test_every_repo_path_exists(self):
        """路径要么在盘上，要么是 git 明说不入库的生成物 —— 两者都不算写错。

        2026-08-20 拿「干净 clone」实测（只放 `git ls-files` 加未跟踪未 ignore
        的那批文件，不放 `users/`、不放 `.active_user`）跑一遍，这条第一个红：

            SETUP.md            → `.claude/settings.local.json`
            job-apply/auto/user → `web/public/data.json`

        四处引用**全是对的**——文档正该告诉用户这两个文件是什么。它们只是
        「跑起来才会有」：一个是本机设置，一个是导出器的产物，两个都在
        `.gitignore` 里。而这条判据写的是「文件在不在盘上」，在维护者机器上
        它们早就生成好了，于是**只有别人会红**——首次 CI、每一个 contributor。

        判据改成：**git 说它该被 ignore，缺席就是预期**。`git check-ignore`
        对不存在的路径同样有效（它比的是规则不是文件），所以干净 clone 上也判得了。
        `PERSONAL` 留着不动——`documents/` 是共享框架目录，根本不在 ignore 里，
        换过去会把它一起放行。
        """
        missing = []
        for f, t in _docs().items():
            for m in self.PAT.finditer(t):
                p = m.group(1)
                if p.startswith(PERSONAL) or p.startswith(("http", "/")):
                    continue
                if not (ROOT / p).exists():
                    missing.append((f, p))
        bad = [f"{f} → `{p}`" for f, p in missing if not _git_ignores(p)]
        self.assertEqual(sorted(set(bad)), [],
                         "这些路径在仓库里找不到（写不全和不存在一样难找）：\n  "
                         + "\n  ".join(sorted(set(bad))))

    def test_the_detector_can_fail(self):
        """变异内建：正则要认得出真路径、也不能把泛指的裸文件名当成路径。

        样例用 ASCII 路径——仓库里的源文件名都是 ASCII，正则也只认这一类；
        拿中文文件名当样例只会测出「正则不支持中文」，与它要守的事无关。
        """
        m = self.PAT.search("参考 `tools/no_such_tool.py` 里的写法")
        self.assertIsNotNone(m, "带目录的真实路径应该被认出来")
        self.assertFalse((ROOT / m.group(1)).exists())
        # 真实存在的要能通过
        m2 = self.PAT.search("见 `tools/doctor.py`")
        self.assertIsNotNone(m2)
        self.assertTrue((ROOT / m2.group(1)).exists())
        # 裸文件名是泛指，不该被当成路径
        self.assertIsNone(self.PAT.search("往 `candidate.md` 里写"),
                          "裸文件名多半是泛指某类文件，当成路径会一堆误报")


class EveryReferencedSourceShips(unittest.TestCase):
    """**已跟踪的文件指向谁，谁就必须一起发出去。**

    上一条查的是「文件在不在盘上」——那只证明**维护者这台机器**上有。
    这一条查的是「它进没进版本库」，两件事在一台开发机上永远看不出区别。

    2026-08-21 实测抓到：`tools/applied_jds.py` 被 3 个已跟踪文件引用
    （`workflows/job-upskill.md`、技能壳、测试），自己却从来没 `git add` 过。
    它没被 ignore，只是忘了。**后果是静默的**：

    - 维护者本机全绿（文件就在盘上）；
    - `git commit -am` 只暂存已跟踪文件，**这个新工具不会进那次提交**；
    - 发出去的仓库里 `/job-upskill --applied` 对每个用户都是坏的；
    - **CI 也是绿的** —— 唯一能逮到它的那个测试文件同样没跟踪，一起漏掉。

    ## 范围：只查「被已跟踪文件指名道姓的」

    不是「`tools/` 下所有未跟踪的 .py」——那会让每写一个新文件套件就红一次，
    逼人先 `git add` 再跑测试，纯噪音。判据是**引用关系**：
    有东西指着它，它就得在。没人引用的新文件不关这条的事。
    """

    def _tracked(self):
        r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            self.skipTest("不是 git 仓库 —— 这条判据无从查起")
        return set(r.stdout.split("\n"))

    #: **可运行的命令是比反引号路径更强的引用。** 上一条那个正则要求反引号
    #: 且带目录，而实测漏掉的正是最要紧的一处：`tools/applied_jds.py` 三处引用
    #: 分别在 ```bash 围栏里、技能壳的 frontmatter 里（`Bash(python tools/…:*)`）、
    #: 和一处不带目录的反引号里 —— 三种写法一个都没命中。
    #: 所以这里另外扫一遍**裸的 tools/xxx.py**，不管它外面包着什么。
    RUNNABLE = re.compile(r"\b(tools/[A-Za-z0-9_][A-Za-z0-9_.-]*\.py)\b")

    def test_referenced_files_are_in_the_repo(self):
        tracked = self._tracked()
        bad = []
        for rel in sorted(tracked):
            if not rel.endswith(".md") or rel.startswith(("profile.example/",)):
                continue
            p = ROOT / rel
            if not p.is_file():
                continue
            body = p.read_text(encoding="utf-8")
            for m in list(FilePathsResolve.PAT.finditer(body)) + \
                    list(self.RUNNABLE.finditer(body)):
                target = m.group(1)
                if target in tracked or not (ROOT / target).is_file():
                    continue          # 已入库，或本来就不在盘上（上一条管那种）
                # 盘上有、却没入库 —— 除非 git 明说它是生成物
                ig = subprocess.run(["git", "check-ignore", "-q", target],
                                    cwd=ROOT, capture_output=True)
                if ig.returncode != 0:
                    bad.append(f"{rel} → {target}")
        self.assertEqual(
            sorted(set(bad)), [],
            "这些文件被已跟踪的文档指名引用，自己却没进版本库 —— "
            "`git commit -am` 不会带上它们，发出去就是断的：\n  "
            + "\n  ".join(sorted(set(bad))))


#: 「`某文件.md` 的『某节』」这种引用。反引号可有可无，中间那个「里/的/中」
#: 和「那一节」也可有可无 —— 实测这四种写法都在用。
_SECTION_CITE = re.compile(
    r"`?([A-Za-z0-9_.\-]+\.md)`?\s*(?:里|的|中)?\s*(?:那一?节|)?\s*「([^」]{2,30})」")


def _plain(text: str) -> str:
    """比对前先把标记剥掉。

    引的人和被引的人对**强调标记**的处理常常不一样：正本的标题写着
    `### 章节顺序按行业定**一次**，之后不再动`，引的人写「章节顺序按行业定一次」
    —— 那不是断链，是同一句话。反引号与「」同理。
    不剥的话这条守卫会报出一串假阳性，然后被整条关掉。
    """
    for ch in ("**", "`", "「", "」"):
        text = text.replace(ch, "")
    return text


class SectionCitationsResolve(unittest.TestCase):
    """引了别的文件的某一节，那一节得真的在那个文件里。

    `FilePathsResolve` 管的是**文件**指不指得到，这里管**文件里那一节**。
    此前没有任何东西验后者 —— 而「自称出处、出处里查无此话」是本仓库反复
    栽的一类：一条规则被执行着、被测试引用着，却从没写进它自称的那份正本。

    实测 2026-08-24 全仓库 194 处这类引用，剥掉标记后指不到的 3 处：

        tests/test_gap_split.py       → AGENTS.md ·「面板每处引导都要写出命令」
        tests/test_apply_step5_...py  → 05-cv-templates.md ·「按不超过上限判、不是恰好」
        tests/test_docs_accuracy.py   → SETUP.md ·「Python 是给 /job-dashboard 用的」

    （上面三行故意用 `·` 隔开而不是「的」—— 照真实写法写，这段文字自己就会被
    这条守卫扫出来。同一个自陷本仓库栽过五次，第一次跑这条测试时又栽了一次。）

    第一条是**真的**：那条规则一直在被执行（导出给面板的数据里 486 次斜杠命令、
    组件里 46 处命令块、`tools/` 下 355 处），而 `AGENTS.md` 里一个字都没有 ——
    **规则真、出处假**。代价不在这一处：换个 AI 工具读的就是 `AGENTS.md`，
    这条规则整条丢掉。已补进 `AGENTS.md`。
    后两条是**转述写成了引用**：意思对、原话对不上，照抄不到就查不到。改了措辞。

    ## 为什么连测试文件也扫

    那三处全在 `tests/` 里 —— 测试的失败信息是给下一个人看的第一手说明，
    它指错地方的代价和正文一样。**只扫正文就一条都抓不到。**
    """

    def _cites(self):
        out = []
        files = subprocess.run(["git", "ls-files", "*.md", "*.py"],
                               cwd=ROOT, capture_output=True, text=True).stdout.split()
        docs = {}
        for f in files:
            p = ROOT / f
            if p.is_file():
                docs[f] = p.read_text(encoding="utf-8", errors="replace")
        by = {}
        for k, v in docs.items():
            by.setdefault(Path(k).name, []).append(_plain(v))
        for src, text in docs.items():
            for m in _SECTION_CITE.finditer(text):
                tgts = by.get(m.group(1))
                if tgts:
                    out.append((src, m.group(1), m.group(2), tgts))
        return out

    def test_the_scan_finds_them(self):
        """扫不到就等于没测 —— 写法一变这条先红。"""
        self.assertGreaterEqual(len(self._cites()), 100,
                                "找不到「某文件的『某节』」这类引用了，正则该跟着改")

    def test_every_cited_section_exists(self):
        bad = [f"{src} → {fn} 的「{sec}」"
               for src, fn, sec, tgts in self._cites()
               if not any(_plain(sec) in t for t in tgts)]
        self.assertEqual(
            bad, [],
            "这些引用在目标文件里查无此话（转述就别写成引号里的引用；"
            "规则真的该在那儿就去补上）：\n  " + "\n  ".join(bad))

    def test_the_scan_covers_tests_too(self):
        """**这条不是凑数的。** 上面那三处发现全在 `tests/` 里 —— 把扫描范围
        收回「只扫正文」，这条守卫会照常全绿，而它此前抓到的东西一个都抓不着。
        实测：范围一收窄，其余四条变异测试全部照过（2026-08-24 变异实测）。
        """
        froms = {src for src, *_ in self._cites()}
        n = sum(1 for f in froms if f.startswith("tests/"))
        self.assertGreaterEqual(
            n, 5,
            f"只有 {n} 个测试文件在引用别处的小节 —— 扫描范围大概是被收窄了。"
            "测试的失败信息是给下一个人看的第一手说明，它指错地方的代价和正文一样")

    def test_emphasis_markers_do_not_cause_false_alarms(self):
        """控制用例：正本加粗、引的人没加粗，不算断链。"""
        self.assertIn(_plain("章节顺序按行业定一次"),
                      _plain("### 章节顺序按行业定**一次**，之后不再动"))

    def test_a_real_dangling_citation_would_be_caught(self):
        """变异内建：伪造一句查无此话的引用，必须报出来。"""
        self.assertNotIn(_plain("这句话哪儿都没有"),
                         _plain("### 章节顺序按行业定**一次**，之后不再动"))


class CommandNamesResolve(unittest.TestCase):
    """`/job-xxx` 要在**两族技能壳**里各有一份。

    原来这里认两个落点：`.claude/commands/` 的 stub 与 `.claude/skills/` 的壳，
    而且「任一处有」即算通过 —— 因为 `/job-scrape`、`/job-upskill` 当时只有壳。
    stub 删掉之后入口只剩壳一种形态，而壳一次落两族：`.claude/skills/` 给
    Claude Code，`.agents/skills/` 给其余各家。判据因此**变严**而不是变松：
    一族有一族没有 = 那一家的工具敲不到这条命令，不能算装上。
    """

    def _installed(self, fam: str) -> set:
        sk = ROOT / fam / "skills"
        return {p.name for p in sk.iterdir() if p.is_dir()} if sk.is_dir() else set()

    def test_every_command_mentioned_is_installed(self):
        fams = _entries.SHELL_FAMILIES
        have = set.intersection(*(self._installed(f) for f in fams))
        self.assertGreaterEqual(len(have), 15, "技能壳目录像是没扫到")
        bad = set()
        for f, t in _docs().items():
            for m in re.finditer(r"(/job-[a-z-]+)", t):
                if m.group(1).lstrip("/") not in have:
                    bad.add(f"{f} → {m.group(1)}")
        self.assertEqual(sorted(bad), [],
                         "这些命令文档里提了、至少一族没有壳（那一家的工具敲不到）：\n  "
                         + "\n  ".join(sorted(bad)))

    def test_every_workflow_has_an_entry_point(self):
        """反过来：每个 `workflows/job-*.md` 都要在两族**各**有一份壳，否则没人敲得到它。

        逐族分别核，不取并集：并集会让「只生成了一半」那种状态放行。
        """
        wf = {p.stem for p in (ROOT / "workflows").glob("job-*.md")}
        self.assertGreaterEqual(len(wf), 15, "workflows/ 像是没扫到")
        for fam in _entries.SHELL_FAMILIES:
            orphan = sorted(wf - self._installed(fam))
            self.assertEqual(orphan, [],
                             f"{fam}/skills 里缺这些工作流的壳，用户敲不到：{orphan}")


class MarkdownLinksResolve(unittest.TestCase):
    """第五类：`[文字](相对路径)` 里那个路径得真的存在。

    ## 为什么单独一类

    `FilePathsResolve` 查的是**反引号里**的 `xxx/yyy.md`。而 README 底部那排
    文档索引、SETUP 里的交叉指路、workflows 之间的互链，用的全是
    **markdown 链接**形态 —— 判据一条都够不着。

    对一个**即将公开**的仓库，这是读者最先撞上的一类失败：
    点一下，404。而它在本地永远不报错。

    2026-08-21 全量扫了 69 份 shipped markdown：**零断链**
    （README 底部 `SETUP/AGENTS/CONTRIBUTING/SECURITY/LICENSE` 五个全在）。
    判据留在这里，是为了让「零」保持是零。

    ## 占位符不算断链

    输出模板里 `[职位](<URL>)`、`[标题](url)`、`[...](…)` 是给执行者填的坑，
    不是链接。第一版没排除，6 条命中全是它们 —— **先怀疑仪器**。
    """

    #: 占位符特征：带尖括号、纯 `url`、或省略号。
    PLACEHOLDER = ("<", ">", "…", "...")

    def _scan(self):
        import re
        import subprocess

        out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8")
        files = out.stdout.split() if out.returncode == 0 else []
        link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
        bad = []
        for f in files:
            src = ROOT / f
            for n, ln in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
                for m in link.finditer(ln):
                    t = m.group(1)
                    if t.startswith(("http://", "https://", "#", "mailto:")):
                        continue
                    if t == "url" or any(c in t for c in self.PLACEHOLDER):
                        continue
                    path = t.partition("#")[0]
                    if not path:
                        continue
                    if not (src.parent / path).exists():
                        bad.append(f"{f}:{n} → {t}")
        return files, bad

    def test_every_relative_link_resolves(self):
        files, bad = self._scan()
        if not files:
            self.skipTest("跑不了 git ls-files")
        self.assertGreater(len(files), 40,
                           f"只扫到 {len(files)} 份 markdown，判据没在工作")
        self.assertEqual(
            bad, [],
            "这些 markdown 链接指向不存在的文件 —— 公开之后读者点一下就是 404："
            + " · ".join(bad))

    def test_the_readme_doc_index_is_all_there(self):
        """控制用例：README 底部那排文档索引确实被上面那条覆盖到。"""
        t = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in ("SETUP.md", "AGENTS.md", "CONTRIBUTING.md",
                     "SECURITY.md"):
            with self.subTest(doc=name):
                self.assertIn(f"]({name})", t, f"README 不再链接 {name} 了？")
                self.assertTrue((ROOT / name).is_file(), f"{name} 不在")


class PythonNamesResolve(unittest.TestCase):
    """第四类：文档里写 `模块.函数`，那个名字得真的在那个模块里。

    ## 为什么补这一类

    本文件开头列了三类（文件路径 / 命令名 / 工具开关），**唯独没有函数名**。
    2026-08-21 通读 `/job-user` 时撞见：规则 1 拿
    `build_dashboard.read_active_user` 当「实测」依据，而**全仓查无此函数**——
    正本是 `_cli.pick_user`。

    （2026-08-31 起 `_cli.read_active_user` 是个**真函数**了，是 `pick_user`
    底下那一层。上面这句仍然成立：判据按**模块**限定，`build_dashboard` 里
    从来没有这个名字。重名不影响判据，只会让读的人绊一下，所以在这里说一声。）

    坏处和「引用一个不存在的 Step 编号」一样：读的人以为自己漏看了，
    去翻 `build_dashboard.py` 找不到，最后只能猜那句话到底在说什么。
    更糟的是它挂着「实测」二字，看起来最不该被怀疑。

    （顺带发现那段的**后果描述也过期了**：它说「报错要等到某条命令去拼路径时
    才浮出来」，而 `_cli.pick_user` 现在当场就说人话并退出码 1，实测复现过。
    名字错了容易看出来，**行为描述过期不会有任何提示**。）

    ## 判据

    扫反引号里的 `xxx.yyy`，`xxx` 是 `tools/` 下某个模块时，
    `yyy` 必须是那个模块的顶层名字（函数 / 类 / 常量）。

    - **文件扩展名不算**：`` `serve.py` `` 会被拆成 `serve` + `py`。
      第一版没排除，30 条命中里 29 条是这个（先怀疑仪器，又一次）。
    - **讲这条规则本身的行放过**：判据得能解释自己，所以含「却把函数名写成了」
      「查无此」这类**复述坏例子**的行跳过（见上面 `_scan` 里的豁免）。
      `workflows/job-user.md` 里那三行复述当时已经删了 —— 正文留着的是实测事实，
      复述的价值归判据，不归正文；判据留着，它防的是下一次。
    """

    EXT = {"py", "json", "md", "csv", "typ", "tex", "pdf", "html",
           "ts", "tsx", "jpg", "png", "webp", "svg", "txt", "yml", "yaml"}

    @staticmethod
    def _toplevel_names() -> dict:
        import ast

        out = {}
        for f in (ROOT / "tools").glob("*.py"):
            names = set()
            for node in ast.parse(f.read_text(encoding="utf-8")).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    names.add(node.name)
                elif isinstance(node, ast.Assign):
                    names |= {t.id for t in node.targets
                              if isinstance(t, ast.Name)}
                elif isinstance(node, ast.AnnAssign) and isinstance(
                        node.target, ast.Name):
                    names.add(node.target.id)
            out[f.stem] = names
        return out

    def _scan(self):
        import re

        pat = re.compile(r"`([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)(?:\(\))?`")
        defined = self._toplevel_names()
        bad = []
        for f in sorted(list((ROOT / "workflows").rglob("*.md"))
                        + [ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]):
            if not f.is_file():
                continue
            for n, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if "却把函数名写成了" in ln or "查无此" in ln:
                    continue          # 讲这条规则本身的说明
                for m in pat.finditer(ln):
                    mod, fn = m.group(1), m.group(2)
                    if fn in self.EXT or mod not in defined:
                        continue
                    if fn not in defined[mod]:
                        bad.append(f"{f.name}:{n}  `{mod}.{fn}`")
        return bad, defined

    def test_every_python_name_mentioned_exists(self):
        bad, defined = self._scan()
        self.assertGreater(len(defined), 10,
                           f"只扫到 {len(defined)} 个 tools 模块，判据没在工作")
        self.assertEqual(
            bad, [],
            "文档里这些 `模块.函数` 在对应模块里找不到 —— "
            "读的人会去翻源码，翻不到只能猜：" + " · ".join(bad))

    def test_the_detector_can_fail(self):
        """变异内建：真实存在的名字放过，编一个必须抓住。"""
        _bad, defined = self._scan()
        self.assertIn("pick_user", defined.get("_cli", set()),
                      "`_cli.pick_user` 不在了？那上面那条判据失去了对照")
        self.assertNotIn("read_active_user", defined.get("build_dashboard", set()),
                         "`build_dashboard.read_active_user` 又出现了？"
                         "那 job-user.md 的旧写法该改回去")


class ToolFlagsResolve(unittest.TestCase):
    """流程里写的 `python tools/xxx.py --flag`，那个开关得真的存在。

    这一类最要命：**AI 会照着敲**。开关不存在不是「文档不准」，是命令当场退出，
    而自动模式下人不在场看。
    """

    CALL = re.compile(r"python3?\s+(tools/[\w_]+\.py)"
                      r"((?:\s+--?[\w-]+(?:[= ][^\s`|]+)?)*)")

    def test_every_flag_is_in_the_help(self):
        used, where = {}, {}
        for f, t in _docs().items():
            for m in self.CALL.finditer(t):
                script, tail = m.group(1), m.group(2) or ""
                used.setdefault(script, set())
                for fl in re.findall(r"(--[\w-]+)", tail):
                    used[script].add(fl)
                    where.setdefault((script, fl), set()).add(f)
        self.assertTrue(used, "一个工具调用都没扫到？正则多半坏了")
        bad = []
        for script, flags in sorted(used.items()):
            p = ROOT / script
            if not p.is_file():
                bad.append(f"{script} —— 脚本本身不存在")
                continue
            if not flags:
                continue
            r = subprocess.run([sys.executable, str(p), "--help"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=90)
            real = set(re.findall(r"(--[\w-]+)", (r.stdout or "") + (r.stderr or "")))
            for fl in sorted(flags):
                if fl not in real:
                    bad.append(f"{script} {fl} ← "
                               f"{'、'.join(sorted(where[(script, fl)]))}")
        self.assertEqual(bad, [],
                         "流程里写了这些开关，而工具的 --help 里没有——照着敲会直接退出：\n  "
                         + "\n  ".join(bad))


class SlashCommandFlagsResolve(unittest.TestCase):
    """`/job-xxx --flag` 里那个开关，得在它自己那份工作流里写着。

    `ToolFlagsResolve` 管的是 `python tools/xxx.py --flag`（拿 `--help` 对），
    `CommandNamesResolve` 管的是 `/job-xxx` 这个命令在不在。**中间这一格空着**：
    命令是真的、开关是编的，两条都放行。

    2026-08-30 补这条时全仓扫出 1 个：`tools/stale_materials.py` 的收尾印着
    「全部重出跑 `/job-apply --stale`」，而 `job-apply.md` 里从来没有这个开关。
    它比文档里写错更糟 —— **那句是印给用户看的**，用户照着敲，命令不认。

    与 `ToolFlagsResolve` 的区别在判据来源：斜杠命令没有 `--help`，
    它的「说明书」就是 `workflows/<命令名>.md`。开关在那份文件里出现过，
    执行者才知道它是什么意思。

    **扫的范围比 `_docs()` 宽**：那个坑就在 `tools/*.py` 里，只扫 md 看不见。
    面板组件（`web/src`）同样要扫 —— 面板上的命令块是用户点着复制的。
    """

    PAT = re.compile(r"/(job-[a-z][a-z-]*)\s+(--[a-z][a-z-]*)")

    def _sources(self) -> dict:
        out = dict(_docs())
        for sub, pats in (("tools", ("*.py",)), ("web/src", ("*.tsx", "*.ts")),
                          (".claude", ("*.md",))):
            d = ROOT / sub
            if not d.is_dir():
                continue
            for pat in pats:
                for f in d.rglob(pat):
                    if "__pycache__" in f.parts or "node_modules" in f.parts:
                        continue
                    out[str(f.relative_to(ROOT)).replace(chr(92), "/")] = \
                        f.read_text(encoding="utf-8")
        return out
        # tests/ 不扫：守卫本身要能拿假开关当反例（下面 test_the_detector_can_fail
        # 就写着一个）。真出现漂移时，扫描范围里的那 4 类已经够。

    def test_every_flag_is_documented(self):
        bad, seen = [], 0
        for f, t in self._sources().items():
            for cmd, flag in self.PAT.findall(t):
                wf = ROOT / "workflows" / f"{cmd}.md"
                if not wf.is_file():
                    continue          # 命令在不在归 CommandNamesResolve 管
                seen += 1
                if flag not in wf.read_text(encoding="utf-8"):
                    bad.append(f"/{cmd} {flag} ← {f}（workflows/{cmd}.md 里没有）")
        self.assertTrue(seen, "一个 命令+开关 都没扫到？正则多半坏了")
        self.assertEqual(sorted(set(bad)), [],
                         "这些开关印给用户看了，而它自己那份工作流里查无此项——"
                         "照着敲，命令不认：\n  " + "\n  ".join(sorted(set(bad))))

    def test_the_detector_can_fail(self):
        """假开关要真被认出来 —— 否则这条守卫是块安慰牌。"""
        hits = self.PAT.findall("跑 /job-apply --zzz-not-a-real-flag 试试")
        self.assertEqual(hits, [("job-apply", "--zzz-not-a-real-flag")])
        body = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
        self.assertNotIn("--zzz-not-a-real-flag", body)



class TestNamesResolve(unittest.TestCase):
    """第五类：反引号里写一个 `test_` 开头的名字，那个测试得真的在。

    （这句话里的 `test_` 后面故意没跟东西 —— 写成占位符「…xxx」它自己就会被这条
    守卫扫成断链。**断言撞上解释自己的文字**是本仓库的常客，第一次跑就又栽一次。）

    ## 为什么补这一类

    本文件已有四类（文件路径 / 命令名 / 工具开关 / `tools` 模块里的函数名），
    **唯独没有 `tests/` 里的名字**。而「某某守卫盯着」是最不该被轻信、却最容易
    被轻信的一句话 —— 读的人以为验过了，就不再去看。

    2026-08-31 一轮之内咬了三次：

    - `build_dashboard.read_active_user` —— 全仓查无此函数（第四类后来盖住了它）
    - 「新规则由 …MaterialsFollowScoresWithoutAGate 钉住」—— 那个类不存在，
      而它防的正是「把撤掉的点头闸门加回来」
    - `test_the_copies_in_doctor_still_match` —— 两处注释引它钉住 doctor 的副本
      相等，而 doctor 那份 `is_out_verdict` 当时**确实已经和正本判得不一样**了
      （漏了 2026-08-23 补进正本的「已下线」那一档，真语料上 4 个岗分叉）

    三次都是同一个形状：**声称有守卫，守卫不存在。** 比没有守卫更糟。

    ## 历史引用放过

    「原来这条叫 X」「这条取代的是原来那对 X、Y」是有价值的记录，不能因为 X 不在
    了就逼人删掉 —— 那会把「为什么改成现在这样」一起删掉。判据：引用**前** 170 字
    里出现下面任一个词，就算历史引用。

    实测这条判据把当时 8 处未解析引用分成 6 历史 + 2 真缺陷，两边都没有错分。
    """

    #: 出现在引用前面就算「在讲旧事」。
    PAST = ("原来", "曾经", "取代", "上一版", "此前", "已删", "删了", "改名",
            "旧守卫")

    #: 往前看多远。170 字够跨一句话，又不至于把上一段的「原来」也算进来。
    WINDOW = 170

    @staticmethod
    def _known() -> set:
        import ast as _ast

        out = set()
        for f in (ROOT / "tests").glob("test_*.py"):
            out.add(f.stem)
            try:
                tree = _ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:            # pragma: no cover - 语法错另有守卫
                continue
            for n in _ast.walk(tree):
                if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                                  _ast.ClassDef)):
                    out.add(n.name)
        return out

    #: 扫这五片。**每一片都要真的扫到文件**，见 `test_the_instrument_lights_up`。
    AREAS = ("tools/*.py", "workflows/**/*.md", "*.md", "web/src/**/*.ts*",
             "tests/*.py")

    def _scan(self):
        """返回 (总引用数, 活的但指不到的)。"""
        import re as _re

        known, pat = self._known(), _re.compile(r"`(test_[A-Za-z0-9_]+)`")
        total, bad = 0, []
        files = [f for g in self.AREAS for f in ROOT.glob(g)]
        for f in files:
            try:
                t = f.read_text(encoding="utf-8")
            except OSError:                # pragma: no cover
                continue
            for m in pat.finditer(t):
                total += 1
                if m.group(1) in known:
                    continue
                win = t[max(0, m.start() - self.WINDOW):m.start()]
                if any(k in win for k in self.PAST):
                    continue
                bad.append(f.relative_to(ROOT).as_posix() + " → " + m.group(1))
        return total, bad

    def test_the_instrument_lights_up(self):
        """用仪器之前先证明它会亮 —— 而且**逐片验，不看总数**。

        第一版只断言「总数 > 100」。实测把其中三片的路径改坏，它照样绿：
        `tests/*.py` 一片自己就有几百处引用，总数根本掉不下来。
        **一条永远绿的自检等于没有自检**，而它守的正是「扫描范围断了会静默
        变绿」这件事 —— 自检自己先犯了它要防的病。
        """
        for g in self.AREAS:
            with self.subTest(g):
                self.assertTrue(list(ROOT.glob(g)),
                                "这一片一个文件都没扫到，范围写坏了：" + g)
        total, _ = self._scan()
        self.assertGreater(total, 100,
                           "只扫到 %d 处 `test_*` 引用，扫描范围八成断了" % total)

    def test_every_cited_test_exists(self):
        _total, bad = self._scan()
        self.assertEqual(
            bad, [],
            "这些地方声称某条测试盯着，而那个名字在 tests/ 里查无此物"
            "（讲旧事就把「原来 / 取代 / 上一版」写在前面，守卫会放过）：\n  "
            + "\n  ".join(bad))


if __name__ == "__main__":
    unittest.main()
