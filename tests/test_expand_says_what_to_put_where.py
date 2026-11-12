# -*- coding: utf-8 -*-
"""`/job-expand` 会把四个空目录扫一遍，然后给你一份每行都写着「跳过」的报告。

实测活动用户 2026-08-23：

    documents/cv/            0 个文件
    documents/linkedin/      0 个文件
    documents/diplomas/      0 个文件
    documents/references/    0 个文件
    documents/applications/  838 个文件   ← **有意不扫**（工具自己写的，读回去是自己抄自己）
    candidate.md 里的 URL     0 个

Step 0 的守卫只查 `candidate.md` 在不在、填完没有 —— 这两条他都过。于是命令
一路往下：读两份资料、扫四个空目录、找不到链接可抓，最后在 Step 6 的报告里
留一句「哪些是缺失、空的」。**用户读完还得自己倒推该做什么。**

而「该做什么」是有明确答案的：`documents/README.md` 有一整张表写着放什么、
放哪个子目录。只是**没有任何地方把用户送到那儿** —— doctor 没有、面板没有、
这条命令自己也没有（它假定文件已经在了）。

所以在 Step 1 开头拦一道：全空就现在说，并说清放什么放哪儿。
**只拦「全空」** —— 部分为空是正常的（很多人没有领英导出），照常跑，
空的那几个在 Step 6 如实写一句。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPAND = (ROOT / "workflows" / "job-expand.md").read_text(encoding="utf-8")
DOCS = (ROOT / "documents" / "README.md").read_text(encoding="utf-8")


def _seg() -> str:
    i = EXPAND.index("**先看一眼有没有东西可扫，别扫完才说。**")
    j = EXPAND.index("把每一个能拿到的来源都扫一遍", i)
    return EXPAND[i:j]


class ItChecksBeforeItScans(unittest.TestCase):
    def test_the_check_exists(self):
        self.assertIn("**先看一眼有没有东西可扫，别扫完才说。**", EXPAND)

    def test_it_comes_before_the_sub_steps(self):
        """摆在 1a 后面就白拦了 —— 那时候已经开始扫了。"""
        self.assertLess(EXPAND.index("**先看一眼有没有东西可扫"),
                        EXPAND.index("### 1a. documents/cv/"))

    def test_it_gives_a_runnable_check(self):
        seg = _seg()
        self.assertIn("ls users/<活动用户>/documents/", seg)
        self.assertIn("grep -cE 'https?://'", seg, "没查资料里有没有链接")

    def test_it_names_all_four_directories(self):
        seg = _seg()
        for d in ("cv", "linkedin", "diplomas", "references"):
            with self.subTest(d=d):
                self.assertIn(d, seg)

    def test_it_says_what_a_pointless_run_looks_like(self):
        """不写清代价，下一版会把这一步当多余的仪式删掉。"""
        seg = " ".join(_seg().split())
        self.assertRegex(seg, r"每行都写着「跳过」的报告")
        self.assertRegex(seg, r"用户读完还得自己倒推该做什么")

    def test_it_carries_the_measured_state(self):
        seg = " ".join(_seg().split())
        self.assertRegex(seg, r"四个目录都空")
        self.assertIn("applications/", seg)


class ItTellsHimWhatToPutWhere(unittest.TestCase):
    def test_it_does_not_just_say_nothing_found(self):
        """「没挖到」和「你还没放东西」是两回事 —— 前者会让他以为自己没东西可挖。"""
        seg = " ".join(_seg().split())
        self.assertRegex(seg, r"把「你还没放东西」说成了「你没有东西可挖」")

    def test_it_lists_the_directories_with_what_goes_in_them(self):
        seg = _seg()
        for d, what in (("cv/", "简历"), ("diplomas/", "学位证")):
            with self.subTest(d=d):
                i = seg.index(f"`{d}` ——")
                self.assertIn(what, seg[i:i + 80], f"{d} 没说放什么")

    def test_it_mentions_the_online_resume_export(self):
        """平台那份在线简历通常比 PDF 细 —— 1a 已经写过这条，这里要接上。"""
        self.assertIn("在线简历导出也放这儿", _seg())

    def test_it_points_at_the_readme_instead_of_copying_the_table(self):
        """那张表的正本在 `documents/README.md`。抄过来两处就会各长各的。"""
        seg = _seg()
        self.assertIn("documents/README.md", seg, "没指向正本")
        rows = re.findall(r"^\s*\|", seg, re.M)
        self.assertEqual(rows, [], "把那张表抄过来了")

    def test_it_offers_the_url_route_too(self):
        """有作品/主页链接的话不用放文件 —— 那是另一条路，不该只给一条。"""
        self.assertRegex(" ".join(_seg().split()), r"那条路不用放文件")

    def test_it_says_partial_is_fine(self):
        """要求四个都放齐会把人拦在门外 —— 多数人没有领英导出。"""
        self.assertIn("哪个有放哪个，不用齐", _seg())


class ItDoesNotOverstep(unittest.TestCase):
    def test_it_does_not_create_the_directories(self):
        """建目录是替他做决定 —— 而且空目录会让下一次检查以为「有了」。"""
        seg = " ".join(_seg().split())
        self.assertRegex(seg, r"不要替他建目录")

    def test_it_only_stops_on_all_empty(self):
        seg = " ".join(_seg().split())
        self.assertRegex(seg, r"只有部分为空.*照常往下跑")
        self.assertRegex(seg, r"这一条只拦「全空」那一种")

    def test_partial_emptiness_still_gets_reported(self):
        """照常跑不等于闭嘴 —— 空的那几个仍要进「跳过的来源」。"""
        self.assertIn("「跳过的来源」如实写一句", _seg())


class ThePremisesStillHold(unittest.TestCase):
    """这一步引的两件事：`applications/` 有意不扫，`README` 有那张表。"""

    def test_applications_is_still_deliberately_excluded(self):
        self.assertIn("再读回去就是自己抄自己", EXPAND,
                      "`applications/` 的排除理由没了 —— 那 838 个就会被扫进去")

    def test_postings_is_still_excluded_too(self):
        self.assertRegex(EXPAND, r"postings/`.*第三方写的职位描述")

    def test_the_readme_still_has_the_table(self):
        self.assertIn("| 子目录 | 放什么 |", DOCS)
        for d in ("`cv/`", "`linkedin/`", "`diplomas/`"):
            with self.subTest(d=d):
                self.assertIn(d, DOCS)

    def test_the_readme_still_says_where_the_directory_lives(self):
        """它不在仓库根，在 `users/<你的名字>/` 下 —— 拦下来那句话要指对地方。"""
        self.assertIn("users/<你的名字>/documents/", DOCS)
        self.assertIn("users/<你的名字>/documents/", _seg())

    def test_step0_guard_is_untouched(self):
        """Step 0 查的是资料在不在，这一步查的是素材在不在 —— 两道门，别合并。"""
        self.assertIn("## Step 0：先读用户现有的资料", EXPAND)
        i = EXPAND.index("## Step 0：先读用户现有的资料")
        self.assertIn("profile/candidate.md", EXPAND[i:i + 1200])


class EverySubdirIsEitherScannedOrExplained(unittest.TestCase):
    """`documents/` 下的每一个目录，要么扫、要么**写明为什么不扫**。

    上面那条 `test_it_names_all_four_directories` 写死了四个名字 ——
    也就是说**加第七个目录时它不会红**：新目录既不在那四个里，也不在
    「有意不扫」那两条里，于是无声无息地被漏掉，而 Step 1 的 `ls` 也不会带上它。

    这个仓库为同一形状交过三次学费（`documents/` 那六个子目录）：
    `/job-setup` 建的时候只建了一个、`/job-reset` 删的时候只删五个、
    `/job-reset` 给用户看的预览又只报五个。**枚举写在几处，就会各漏各的。**

    所以判据从文档抽，不写死：正本是 `documents/README.md` 那张表
    （`job-reset.md` 也点名照它写全）。

    顺带记一处 2026-09-02 改掉的：`AGENTS.md` 索引里给这条命令的说明原来是
    「扫 `documents/` 下你放的**全部文件**」—— 而 `postings/` 恰恰是「你放的」，
    却有意不扫。索引第三、四列同时是**面板上那份帮助**，那句话对用户是个假承诺。
    """

    def _declared(self) -> list:
        """`documents/README.md` 那张表里列的目录名（正本）。"""
        t = (ROOT / "documents" / "README.md").read_text(encoding="utf-8")
        return [m for m in re.findall(r"^\|\s*`([a-z]+)/`\s*\|", t, re.M)]

    def test_the_source_of_truth_still_lists_them(self):
        """控制用例：抽得到那张表，否则下面那条对着空气跑。"""
        got = self._declared()
        self.assertGreaterEqual(
            len(got), 5, f"从 documents/README.md 只抽到 {got} —— 表的写法改了？")

    def _preamble(self) -> str:
        """Step 1 的前言：从标题到第一个子步骤 `### 1a`。

        **不能用 `_seg()`** —— 它从「先看一眼有没有东西可扫」起截，
        而「有意不扫的两个」那段引用块在它**前面**。第一版就这么写的，
        当场报 `postings` 缺失，而它明明在文里。
        """
        i = EXPAND.index("## Step 1：")
        return EXPAND[i:EXPAND.index("### 1a.", i)]

    def test_each_one_is_scanned_or_excluded(self):
        seg = self._preamble()
        missing = [d for d in self._declared() if d not in seg]
        self.assertEqual(
            missing, [],
            f"`documents/` 下这些目录 Step 1 既没说扫、也没说为什么不扫：{missing}"
            " —— 加一个新目录而这里不提，它就被无声地漏掉了")

    def test_the_index_does_not_overpromise(self):
        """索引不许说「全部文件」—— 有两个目录是**有意不扫**的。
        （索引表正本在 workflows/INDEX.md，2026-09-29 从 AGENTS.md 搬过去。）"""
        ag = (ROOT / "workflows" / "INDEX.md").read_text(encoding="utf-8")
        i = ag.index("`workflows/job-expand.md`")
        row = ag[i:ag.index("\n", i)]
        self.assertNotIn(
            "全部文件", row,
            "索引又承诺「扫 documents/ 下你放的全部文件」了 —— "
            "而 postings/ 正是他放的，却有意不扫")


if __name__ == "__main__":
    unittest.main()
