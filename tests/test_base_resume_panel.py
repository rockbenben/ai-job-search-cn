"""基简历要在面板上看得见——它才是所有投递共用的那一份。

面板原来碰简历只有两处，**都不是「你的简历」本身**：

- 「市场怎么读你的简历」—— 从评估语料反推主场与该补的词，不含简历内容
- 各岗详情里的「打开定制简历 PDF」—— 某次投递的定制版，还得先展开那一行

而基简历改一次，影响之后**每一次**投递。它的内容、编译出的 PDF、审核报告，
一个入口都没有——用户的原话：「GUI 端我没有看到可以查看简历以及相关功能的地方」。
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools"))

from jsx import is_copyable  # noqa: E402
import export_web_data as ex  # noqa: E402


class ExporterEmitsTheBaseResume(unittest.TestCase):

    def test_field_exists_in_real_export(self):
        data = ROOT / "web" / "public" / "data.json"
        if not data.is_file():
            self.skipTest("还没导出")
        d = json.loads(data.read_text(encoding="utf-8"))
        u = (ROOT / ".active_user").read_text(encoding="utf-8").strip()
        if not (ROOT / "users" / u / "resume" / "main.typ").is_file():
            self.skipTest("这个用户还没有简历")
        self.assertIn("baseResume", d, "面板拿不到基简历，那一块只能是空的")
        b = d["baseResume"]
        self.assertTrue(b.get("sections"), "没导出章节顺序 —— 那是看结构有没有被动过的唯一线索")
        self.assertTrue(b.get("updated"), "没导出最后修改日期")

    def test_stale_pdf_is_flagged(self):
        """PDF 比源文件旧 = 改了 .typ 没重新编译，打开的是**上一版**。

        这种「文件在、但内容是旧的」最容易骗人：按钮能点、PDF 能开，只是内容
        不是你以为的那份。不标出来，用户会拿着旧版去投。
        """
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("pdfStale", src, "没有过期判断")
        self.assertRegex(src, r"pdf\.stat\(\)\.st_mtime\s*<\s*st\.st_mtime",
                         "过期判断不是比 mtime —— 那就只是个写死的值")

    def test_audit_summary_is_a_summary_not_the_whole_report(self):
        """整份报告塞进 data.json 会膨胀；更糟的是报告改了、导出没跑，
        面板显示的结论与文件里的对不上——那比不显示更糟。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("只摘不塞全文", src)

    def test_verdict_is_anchored_to_the_section_not_guessed(self):
        """第一版按关键词模糊匹配措辞，一句都没摘到——报告里那句结论用的词
        恰好都不在猜的那几个里。结构是 workflows/job-resume.md 规定的，锚它更可靠。"""
        self.assertEqual(
            ex._audit_verdict.__doc__ and "结论" in ex._audit_verdict.__doc__, True)
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn(r'^##\s*结论\s*$', src, "没有锚到「## 结论」小节")

    def _verdict_of(self, body: str) -> str:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.md"
            p.write_text(body, encoding="utf-8")
            return ex._audit_verdict(p)

    def test_verdict_extraction(self):
        self.assertEqual(
            self._verdict_of("# 报告\n\n## 结论\n\n**可以直接投。**\n\n下一次…\n"),
            "可以直接投。")

    def test_no_conclusion_section_returns_empty_not_a_guess(self):
        self.assertEqual(self._verdict_of("# 报告\n\n## 必须改\n\n- 某条\n"), "",
                         "没有结论段却编出了一句")


class TheJobDetailOffersTheBaseResume(unittest.TestCase):
    """大多数岗只有开场白，没有定制简历 —— 详情里也得能打开投递用的那份简历。

    原来只有 `m.score` 里的定制 PDF；主简历只藏在首屏「你的简历」弹窗里，
    用户展开岗位后要滚回去找，或者根本不知道要带哪一份。
    """

    def test_app_passes_the_base_pdf_to_the_shortlist(self):
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            app.count("baseResumePdf={snap.baseResume?.pdf}"), 2,
            "两处 Shortlist（主表/可以考虑）没有都传主简历 PDF")

    def test_the_shortlist_passes_it_to_the_detail(self):
        s = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(
            encoding="utf-8")
        self.assertIn("baseResumePdf?: string;", s)
        self.assertIn("baseResumePdf={baseResumePdf}", s)

    def test_custom_resume_still_wins_and_base_is_the_fallback(self):
        s = (ROOT / "web" / "src" / "components" / "JobReadout.tsx").read_text(
            encoding="utf-8")
        self.assertRegex(
            s, r"m\?\.resumePdf \?[\s\S]{0,500}打开定制简历 PDF[\s\S]{0,500}"
               r"baseResumePdf \?[\s\S]{0,300}打开主简历 PDF",
            "定制简历优先、主简历兜底的顺序不对")
        self.assertIn("没有定制简历时也要有简历可打开", s,
                      "没有留下这条兜底的理由")

    def test_stale_base_pdf_is_flagged_at_the_job_action_row(self):
        """主简历 PDF 过期时，岗位详情不能只给一个“打开”就完事。

        `pdfStale` 原来只在「你的简历」弹窗里说；用户在详情里直接下载
        就会拿到上一版。把标记透到动作行，在发出去之前提醒。
        """
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            app.count("baseResumePdfStale={snap.baseResume?.pdfStale}"), 2,
            "两处 Shortlist 没有都传 PDF 过期标记")
        jr = (ROOT / "web" / "src" / "components" / "JobReadout.tsx").read_text(
            encoding="utf-8")
        self.assertIn("baseResumePdfStale", jr)
        self.assertIn("主简历 PDF 是旧版", jr,
                      "详情里没有告诉用户打开的是旧版")


class PanelSurfacesItWithGuidance(unittest.TestCase):

    SRC = ROOT / "web" / "src" / "components" / "BaseResume.tsx"

    def test_component_exists_and_is_wired(self):
        self.assertTrue(self.SRC.is_file())
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("<BaseResume data=", app, "组件没被渲染")

    def test_it_tells_you_the_command(self):
        """面板不改简历（那需要模型读懂内容）；它的职责是让人知道该敲什么。

        锚到**可复制的命令块**，不是全文搜 `/job-resume`——那个串在路径
        `resume/main.typ` 里也出现，把命令块整个换掉，全文搜照样命中。

        > 原来这里锚的是 `copyable=\\{\\{…\\}\\}>` 那段标记，把这份配置收进
        > `<Cmd>` 组件之后当场红了——而要验的事一个字没变。锚点挂在拼法上，
        > 正当的重构就会被当成回归。改问意图：走 `jsx.is_copyable`。
        """
        s = self.SRC.read_text(encoding="utf-8")
        self.assertTrue(
            is_copyable(s, "/job-resume"),
            "没有可复制的 /job-resume 命令块（路径 resume/main.typ 里那个不算）")

    def test_stale_pdf_warning_is_visible_and_actionable(self):
        s = self.SRC.read_text(encoding="utf-8")
        self.assertIn("pdfStale", s, "过期标记没被用上")
        self.assertIn("typst compile", s, "只说旧了、不说怎么重新编译，等于半句话")

    def test_the_recompile_command_is_copy_and_run(self):
        """**复制下来要能直接敲。**

        `<Cmd>` 是点一下就复制的。这条重编命令原来写死
        `typst compile users/<你>/resume/main.typ …` —— 复制到的那串粘进终端
        会失败，用户得先知道自己那个目录名叫什么。而面板手里就有
        `activeUser`（快照里那一项，`App.tsx` 一直在读）。

        `AGENTS.md`「每一处引导都要写出该敲的命令」的判据原话是
        「读完这句他能不能直接动手」—— 一条要用户先做一次替换的命令，
        差的正是这一步。

        面板上另外四处占位符（`/job-apply <职位链接>`、`/job-outcome <公司>`）
        **不在此列**：那些填的是用户自己要挑的东西，面板无从知道；
        `GateStamp` 有真链接时也确实用的是真链接。判据是
        **面板知不知道**，不是「有没有尖括号」。
        """
        s = self.SRC.read_text(encoding="utf-8")
        self.assertIn("user", s.split("export function BaseResume")[1][:200],
                      "组件没接活动用户这个入参")
        i = s.index("typst compile")
        cmd = s[i:s.index("\n", i)]
        self.assertNotIn("你", cmd,
                         "重编命令里还留着 `<你>` —— 复制下来敲不动")
        self.assertIn("${", cmd, "命令没有把活动用户插进去")
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertRegex(app, r"<BaseResume[^>]*user=\{activeUser\}",
                         "App 没把活动用户传下去，组件只能退回占位符")

    def test_never_audited_state_is_explicit(self):
        """从没审过是常态（新用户），不能显示成空白让人以为坏了。"""
        s = self.SRC.read_text(encoding="utf-8")
        self.assertIn("还没审过", s)

    def test_it_does_not_claim_to_edit(self):
        """改简历在命令行——面板要说清自己只负责看得见。"""
        s = self.SRC.read_text(encoding="utf-8")
        self.assertIn("只负责让你看得见", s)


if __name__ == "__main__":
    unittest.main()
