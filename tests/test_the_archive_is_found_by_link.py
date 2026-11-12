# -*- coding: utf-8 -*-
"""归档目录**不能靠名字找**，链接才是钥匙。

归档叫 `documents/applications/<公司>_<岗位>/`，而三条命令
（`/job-interview`、`/job-cv`、`/job-outcome` 自己）都按这个模式去拼路径。
可那个名字**不是按规则生成的**：

    岗位名里的斜杠、括号、副标题落到文件名上就得改
        「上海-AI高级产品经理（AI提效/AI落地）」→「…（AI提效_AI落地）」
    公司名还常被手动加注（「<某公司>」→「<某公司>（两贴同岗）」、
    工商全称后面手动补上通用叫法）

实测活动用户 2026-08-22：

    85 条投递里，按名字找得到归档的      55
    按 `source` 链接找得到的           **85**（全部）

链接这条路是满的：284 份 `posting.md` 每一份都带着标签链接。所以这条规矩不是在
补窟窿，是**把一个已经成立的惯例写死**——它现在只活在执行者的习惯里。

> **这几个数第一版是错的（75 份缺链接 / 链接只找得到 62 条）。**
> 猎聘的岗位页有三种路径（`/a/` 猎头职位、`/job/` 企业直招、`/lptjob/`），
> 我量的时候只认了 `/a/`，静默漏掉四成。**判据里的正则少认一种形态，
> 得出的结论会反过来。**
`build_dashboard.find_applications` 的注释早就记着同一件事的代价：
「少写一行，整个投递目录就接不上职位：材料消失、硬性条件消失，**且无声**。」
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")
ITV = (ROOT / "workflows" / "job-interview.md").read_text(encoding="utf-8")
CV = (ROOT / "workflows" / "job-cv.md").read_text(encoding="utf-8")


class TheLinkIsWrittenIntoTheArchive(unittest.TestCase):
    def test_posting_must_carry_the_source_url(self):
        """没有这一行，往后新建的归档还是接不上。"""
        self.assertRegex(OUT, r"第一行必须是\s*`原始链接：",
                         "job-outcome 没要求把岗位链接写进 posting.md")

    def test_existing_archives_get_the_line_backfilled(self):
        """存量那 75 份缺链接的不补，这条规矩只对未来生效。"""
        self.assertRegex(OUT, r"缺这一行的.{0,12}补上",
                         "没说已有归档要补这一行")

    def test_the_label_matches_what_the_parser_reads(self):
        """写入端的标签必须在读取端认得的那几个里，否则写了也读不到。"""
        bd = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
        self.assertIn("原始链接", bd, "解析器不认「原始链接」这个标签了")


class TheUrlShapesAreAllKnown(unittest.TestCase):
    """猎聘的岗位页有三种路径，只认一种的判据会静默漏掉四成。

    实测 2026-08-22 全库 2232 个猎聘岗：`/a/` 1360、`/job/` 868、`/lptjob/` 4。
    `/a/` 是猎头职位、`/job/` 是企业直招（`liepin-search` CLI 的 `helpers.ts`
    写着这条对应）。**我上一轮量归档链接时只认了 `/a/`，于是得出「75 份没有链接」
    ——真值是 0。** 判据里的正则少认一种形态，结论会反过来。

    顺带验过一件事：这两种路径下的 id **没有一个重合**（2232 条、2231 个不同 id、
    0 个 id 出现在两种路径下）——它们是不同的岗，不是同一个岗的两个别名，
    所以不存在 `check_scheme_twins` 那种孪生问题。
    """

    def test_the_cli_documents_both_shapes(self):
        h = (ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "src"
             / "helpers.ts").read_text(encoding="utf-8")
        for shape in ("/job/", "/a/"):
            with self.subTest(shape=shape):
                self.assertIn(shape, h, f"CLI 里不再记着 {shape} 这种路径了")

    def test_the_workflow_warns_about_the_narrow_regex(self):
        """这个坑要留在原地 —— 下一个量归档链接的人还会踩。"""
        self.assertRegex(OUT, r"三种路径", "没写清猎聘有几种岗位页路径")
        self.assertRegex(OUT, r"只认其中一种的正则会静默漏掉",
                         "没说清少认一种的后果")


class LookupGoesByLinkFirst(unittest.TestCase):
    def test_the_interview_prep_does_not_guess_the_path(self):
        self.assertRegex(ITV, r"别拿「公司_岗位」去拼路径",
                         "备面那条还在按名字拼路径")
        self.assertIn("source", ITV, "没说用哪个字段去对")

    def test_it_says_what_to_do_when_neither_works(self):
        """3 条两条路都找不到 —— 那时不许拿名字相近的目录顶替。"""
        self.assertRegex(ITV, r"别拿一个名字相近的目录当成它",
                         "没挡住「找个像的凑合用」")

    def test_every_consumer_got_the_rule(self):
        """三条命令都按名字找归档 —— 只修其中两条，第三条照样认错目录。

        实测：第一版只改了 `/job-interview` 和 `/job-outcome`，`/job-cv` 漏了，
        而它改的是**要发出去的简历** —— 认错目录就是拿 A 公司的岗改了 B 公司的简历。
        """
        for name, text in (("job-interview.md", ITV), ("job-cv.md", CV)):
            with self.subTest(cmd=name):
                self.assertIn("source", text, f"{name} 没说用链接对")
                self.assertRegex(text, r"别拿一个名字相近的目录当成它",
                                 f"{name} 没挡住「找个像的凑合用」")

    def test_the_measurements_are_recorded(self):
        self.assertIn("目录名不是可靠的钥匙，链接才是", OUT)


if __name__ == "__main__":
    unittest.main()
