"""给用户看的界面里不许出现内部词与未解释的英文码。

为什么要有这个测试：这些词第一版全都出现在界面上——「求职驾驶舱」（比喻，看不懂是
什么）、「台账」（政企公文词）、「硬门」（生造词）、「SCRAPE / RANK / DRAFT」
（英文码）。它们都是从 `workflows/` 的框架词汇顺手搬到屏幕上的，而框架词是给 AI
用的，不该让用户先学一套词才会用工具。规则写在 AGENTS.md「给用户看的措辞」。

扫的是**渲染后的输出**，不是源码：源码里的注释、变量名、以及 `derive_stage` 里
匹配 `/job-rank` 写入的「硬门 FAIL」都是内部实现，允许保留。
"""

import ast
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402
import export_web_data as ex  # noqa: E402
import tracker as tk  # noqa: E402

# 内部词 / 公文词：出现在给用户看的文本里就是 bug
BANNED_WORDS = [
    "驾驶舱", "台账", "入账", "硬门", "短名单", "读数",
    # AGENTS.md 措辞表第三行写着「四维 / 读数 → 评分明细 / 岗位详情」，可这张
    # 词表**只抄了「读数」**，漏了「四维」。于是评估报告模板的标题一直写着
    # 「四维打分」，全绿。抄一张表的时候漏一行，比没有这张表更难发现。
    "四维",
    # 「能力边界缺口」是框架里的全称，但**裸的「能力边界」同样是那个内部词**。
    # 只挡全称的话，短的那个照样上屏——实测 `BaseResume` 就写着「你自己划的能力边界」，
    # 而同一页的 `JobReadout` 对同一件事说的是「经历对不上的地方」。
    # 这段文案还正好落在 `jsx_text_nodes` 从前看不见的那三分之一里，两头都没拦住。
    "能力边界", "信息质量",
    # AGENTS.md 正文点名的四个框架词是「硬门、能力边界、四维、判词」，
    # 而下面那张对照表**没有判词这一行**——于是它既不在换词表
    # （`INTERNAL_TERMS`）也不在这里，`/job-rank` 产出模板的两个表头
    # 一直写着「判词」，直接打进聊天、不经任何转换层。2026-08-21 通读时抓到。
    # 替换词不用另造：评估文件里那一节本来就叫 `## 结论：`
    # （`build_dashboard.py` 就是拿它当锚点解析的）。
    "判词",
    # 实测把页面打开逐块读时补进来的两个：
    # 「降权泊车」是 prescreen 的规则分组术语。它出现在流水线那条说明里，而那句话
    #   要**用一整句去解释它**——需要当场解释的词，本身就说明它没在说人话。
    #   现在直接说事：「只看了标题、还没细看」。
    "降权泊车", "泊车",
    # 「投放」是广告业的词。岗位卡片上印「+2 投放」，求职者不会想到那是
    #   「这个岗在别处也挂着」。改成说它做的事。
    "投放",
]
# 未解释的英文码。作为独立词出现才算（"CDP skill" 算，"data-stage" 里的不算）
#: **`PASS` / `FAIL` / `FLAG` 故意不在这张表里。** 2026-08-21 实测加过一次：
#: 全部 10 处命中都落在 `04-job-evaluation.md` 的硬性条件表，而那里它们是
#: **写进 `evaluation.md` 的机器标记**，由 `gate_why()` 与 `INTERNAL_TERMS`
#: 在显示层换成「满足 / 不满足 / 要留意」。禁掉等于砸掉那套「文件存码、
#: 显示换词」的设计。
#:
#: 分界线是**这段字在到达用户之前过不过转换层**：写进文件再导出的可以用码，
#: 直接打进聊天的不行。同日在 `job-rank.md` Step 5（直接打给用户的那份产出）
#: 抓到一处「标了 FLAG」，改的是那一处，不是这张表。
BANNED_CODES = ["COCKPIT", "SCRAPE", "RANK", "DRAFT", "INTV", "CDP", "ATS"]

# （原来这里有 SEEN 样例数据和 _visible_text 剥标签器——单页渲染器 bd.render
# 删除时留下的残骸，定义后全文件零引用，已清。）


class StandaloneReportTemplatesUsePlainWords(unittest.TestCase):
    """用户**直接打开**的那两份报告，模板里不许有框架词。

    ## 范围为什么这么窄

    `evaluation.md` 正文里出现「硬门」「信息质量」是允许的——`AGENTS.md` 明说
    导出时会统一换成人话（`INTERNAL_TERMS`）。所以不能一刀切「所有模板都不许有框架词」，
    那会把合法用法也判红。

    真正没有这层翻译的是**独立报告**：`/job-resume` 写进 `reports/`、
    `/job-upskill` 写进 `upskill/` 的那两份 —— **用户拿编辑器直接打开，
    中间没有任何一层会替它换词**。

    ## 实测

    2026-08-21 读用户真实产出：`reports/resume-audit-2026-08-01.md` 里有「能力边界」，
    `upskill/report-2026-07-30.md` 里有「硬门」「能力边界」。

    顺着查模板：`job-upskill.md` 的模板是干净的（那份报告的词是模型飘的，
    而且它生成于翻译之前）；**`job-resume.md` 的模板自己就写着**

        ### 必须改（事实对不上 / 越过「明确的能力边界」）

    ——那是**报告里的小节标题**，会被逐字抄进用户打开的那份文件。
    与同一天在 `06-outreach-templates.md` 抬头块上撞见的是同一个形状：
    **模板里出现的字会被逐字抄走。**
    """

    #: 只查这两条 —— 它们的产出不经导出器翻译。
    OWNERS = ("job-resume.md", "job-upskill.md")

    WORDS = ("硬门", "四维", "判词", "能力边界", "短名单", "台账", "驾驶舱", "读数")

    def _fenced(self, name: str) -> str:
        """取这份工作流里所有围栏块的内容（外层围栏规则，与别处一致）。"""
        t = (ROOT / "workflows" / name).read_text(encoding="utf-8")
        out, depth = [], 0
        for line in t.splitlines():
            st = line.strip()
            if st.startswith("```"):
                if depth == 0:
                    depth = 1
                elif st == "```":
                    depth = 0
                continue
            if depth:
                out.append(line)
        return "\n".join(out)

    def test_the_owners_exist(self):
        for name in self.OWNERS:
            with self.subTest(name=name):
                self.assertTrue((ROOT / "workflows" / name).is_file(),
                                f"{name} 不在了 —— 这条判据该跟着改")

    def test_no_framework_word_in_those_templates(self):
        bad = []
        for name in self.OWNERS:
            body = self._fenced(name)
            for w in self.WORDS:
                if w in body:
                    bad.append(f"{name} 的输出模板里有「{w}」")
        self.assertEqual(
            bad, [],
            "这两份报告用户拿编辑器直接打开，中间没有任何一层会替它换词 —— "
            "模板里出现的字会被逐字抄走：\n  " + "\n  ".join(bad))

    def test_the_resume_template_says_it_is_user_facing(self):
        t = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")
        self.assertIn("这份报告是给用户看的", t,
                      "模板没说它是给用户看的 —— 执行者会照框架词写")

    def test_the_fence_reader_actually_reads_something(self):
        """对照用例：真的取到围栏内容 —— 否则上面那条恒绿。"""
        for name in self.OWNERS:
            with self.subTest(name=name):
                self.assertGreater(len(self._fenced(name)), 200,
                                   f"{name} 里几乎没取到围栏内容，取段逻辑像是失效了")


class TheTemplateDoesNotNameToolsForYou(unittest.TestCase):
    """示例里的**工具名**必须是占位符 —— 它会被逐字抄进要发出去的话。

    2026-08-21 实测：该用户资料里只有 Claude Code / Codex / Dify / Coze / n8n，
    **没有 Cursor、Copilot、Windsurf、CodeBuddy**。而 285 份产出里
    16 份的开场白点了这四个中的某一个，其中 4 份连 Claude Code 都没提 ——
    最硬的一条直接写着「有 Copilot 落地经验」。

    源头是这份规格的示例：**它把产品名做成了占位符 `<你的产品>`、
    却把工具名写死成一个具体名字**，16 份里 12 份是那句话的回声。

    这一节上面就写着「写手是照着示例抄的，示例错了，规则写多少条都没用」——
    那条警告针对的是另一条规则（2026-08-17 的开场铺垫问题），
    工具名从它眼皮底下过去了。**一条警告只挡它当时看见的那一种。**
    """

    SPEC = ROOT / "workflows" / "reference" / "06-outreach-templates.md"

    def test_no_concrete_tool_name_in_the_example(self):
        t = self.SPEC.read_text(encoding="utf-8")
        i = t.index("一个真实产出")
        block = t[i:i + 900]
        for tool in ("Cursor", "Copilot", "Windsurf", "CodeBuddy", "通义灵码"):
            with self.subTest(tool=tool):
                self.assertNotIn(
                    tool, block.split("> ⚠️")[0],
                    f"示例里写死了「{tool}」—— 用户资料里没有它时会被照抄进话术")

    def test_the_rule_is_written_down(self):
        t = self.SPEC.read_text(encoding="utf-8")
        self.assertIn("只点名 `candidate.md` 里有的工具", t,
                      "没写下这条规则，改了示例下次还会飘回来")


class TheOutreachHeaderIsUserFacingToo(unittest.TestCase):
    """`outreach.md` 的抬头块同样按「给用户看的措辞」写。

    ## 实测：124 份真实产出的抬头里写着「判词」

    2026-08-21 扫用户的 236 份 `outreach.md`：**124 份的抬头里有「判词：」**，
    少数写「能力边界」。而 `06-outreach-templates.md` 的产出格式里
    **从来没有这两行**——是执行者自己加的。

    加的时候它用了满篇指令里的那个词。这与
    `tests/test_workflow_prose_is_chinese.py` 记的机制**完全相同，只是换了词汇**：

    > 「周围一整片英文指令，模型写『照着念给用户』的那几行时就往英文飘。」

    那一轮治的是英文，这一轮是框架词。**同一个泄漏路径，第二种载荷。**

    ## 为什么只钉规格，不扫产出

    产出是用户的个人数据（`documents/applications/**` 已 gitignore），
    干净 clone 上一份都没有，扫它的判据在 CI 上只会 skip；
    而存量那 124 份是历史产物，下一次 `/job-apply` 会覆写。
    **能一劳永逸的是规格**——把「抬头也是给用户看的」写进去，
    并给出那一行的人话写法。
    """

    SPEC = ROOT / "workflows" / "reference" / "06-outreach-templates.md"

    def test_the_spec_says_the_header_is_user_facing(self):
        t = self.SPEC.read_text(encoding="utf-8")
        self.assertIn("抬头那几行也是给用户看的字", t,
                      "规格没说抬头是给用户看的 —— 执行者会照内部词写")
        self.assertIn("给用户看的措辞", t, "没指回 AGENTS.md 那节")

    def test_the_spec_gives_the_plain_wording_for_that_line(self):
        """光禁不给替代写法，执行者只会换一个内部词。"""
        t = self.SPEC.read_text(encoding="utf-8")
        self.assertIn("- 评分：", t,
                      "规格没给出那一行的人话写法（`- 评分：<分数> 分，属于「…」`）")

    def test_the_header_template_itself_is_free_of_framework_words(self):
        """规格里那段模板本身不许含内部词 —— 它会被逐字照抄。"""
        t = self.SPEC.read_text(encoding="utf-8")
        i = t.index("# <公司> - <岗位> 投递话术")
        head = t[i:t.index("## 打招呼开场白", i)]
        for w in ("判词", "四维", "硬门", "能力边界", "短名单", "台账"):
            with self.subTest(word=w):
                self.assertNotIn(w, head,
                                 f"模板抬头里有内部词「{w}」，会被逐字抄进用户的文件")

    def test_the_detector_would_catch_a_regression(self):
        """变异内建：把内部词放回模板抬头，上面那条必须认得出来。"""
        fake = "# <公司> - <岗位> 投递话术\n\n- 判词：<判词>\n\n## 打招呼开场白"
        i = fake.index("# <公司>")
        head = fake[i:fake.index("## 打招呼开场白", i)]
        self.assertIn("判词", head, "取段逻辑没框住抬头，那条断言等于空转")


class GateVerdictNeverReachesTheScreenRaw(unittest.TestCase):
    """evaluation.md 的判定不能原样倒进页面。

    表里写的是 `**FLAG，非 FAIL**` 这种（框架自己规定的写法）。原样渲染出来是
    竖线、星号、反引号一个不少，还夹着没解释的 PASS / FAIL / FLAG。

    > **这批用例是从单页版搬过来的。** 单页版删掉之前，它的 `format_gate_flag`
    > 测试是这条规则在整个仓库里**唯一**的覆盖——而网页版走的是
    > `export_web_data.gate_why`，那个函数**一条测试都没有**。搬的时候当场发现
    > 它不剥 markdown：`**FLAG，非 FAIL**` 会渲染成「（**，非 **）」。
    >
    > 删一套实现之前，先问「它的测试是不是某条规则的唯一守卫」。
    """

    CASES = [
        ("**FLAG，非 FAIL**", "要求 3 年以上，刚过线", "刚过线"),
        ("**PASS（基于假设值，请你确认）**", "`你的资料` 未确认", "假设值"),
        ("FAIL", "JD 要求硕士及以上", "JD 要求硕士及以上"),
    ]

    def test_markdown_markup_never_reaches_the_page(self):
        for verdict, reason, _ in self.CASES:
            out = ex.gate_why(verdict, reason)
            for ch in ("|", "**", "`"):
                with self.subTest(v=verdict[:16], ch=ch):
                    self.assertNotIn(ch, out, f"渲染后不该残留 markdown「{ch}」：{out}")

    def test_state_words_are_translated_away(self):
        """状态由那枚方章表达，依据里不必也不该再写一遍英文码。"""
        for verdict, reason, _ in self.CASES:
            out = ex.gate_why(verdict, reason)
            for code in ("PASS", "FAIL", "FLAG"):
                with self.subTest(v=verdict[:16], code=code):
                    self.assertNotIn(code, out, f"渲染后不该残留「{code}」：{out}")

    def test_flag_is_not_collapsed_into_fail(self):
        """FLAG 是「过线但要留意」。折叠成「不满足」会让人白白放弃这个岗。"""
        out = ex.gate_why("**FLAG，非 FAIL**", "刚过线")
        self.assertNotIn("不满足", out, f"FLAG 被说成了不满足：{out}")

    def test_the_reason_is_kept(self):
        """依据不能丢——它是用户判断要不要投的全部信息。"""
        out = ex.gate_why("FAIL", "JD 要求硕士及以上")
        self.assertIn("JD 要求硕士及以上", out)

    def test_an_unexpected_shape_still_gets_cleaned(self):
        out = ex.gate_why("学历 FAIL 没有竖线的一行", "")
        self.assertNotIn("FAIL", out, f"兜底路径也必须清理：{out}")

    def test_extra_parenthetical_information_survives(self):
        """判定词以外的括注可能有信息（「PASS（仅限上海）」），不能一并抹掉。"""
        self.assertIn("仅限上海", ex.gate_why("PASS（仅限上海）", "你就在上海"))

    #: 判定那一格真出现过的写法，加上守卫自己造的几种。
    #: **括号套括号的那一条是从导出的真实快照里逮出来的**（2026-08-31）。
    BRACKETS = [
        "要留意（**减 5 分**）",     # 里层自带括号 —— 就是它断的
        "PASS（仅限上海）",
        "不过（见上）",
        "需留意（见上）",
        "**FLAG，非 FAIL**",
        "PASS（基于假设值，请你确认）",
        "FAIL",
        "不适用",
        "学历 FAIL 没有竖线的一行",
    ]

    def test_no_bracket_is_left_open(self):
        """开了没关的括号 = 一句断在半截的话。

        `.strip("（）…")` 两头都剥，判定词自己带括号时它会把里层那个
        右括号一并带走：`要留意（减 5 分）` 剥成 `要留意（减 5 分`，
        拼出来是「（要留意（减 5 分）」。

        ⚠️ **这是同一个形状的第三次。** 前两次（「非」那半句、
        `不过（见上）` 那两个左括号）的修法都是往 `drop` 里再加一个词 ——
        只盖得住已经想到的那几个。所以这条钉的是**性质**：不管判定那一格
        写成什么，出来的字里成对标点必须配得上对。
        """
        for v in self.BRACKETS:
            out = ex.gate_why(v, "JD 要求硕士及以上")
            with self.subTest(v=v):
                for a, b in (("（", "）"), ("(", ")"), ("「", "」")):
                    self.assertEqual(out.count(a), out.count(b),
                                     f"「{a}{b}」配不上对：{out}")

    def test_the_information_inside_those_brackets_survives(self):
        """配平不许靠丢字 —— 那样也「平”了，但话没了。"""
        self.assertIn("减 5 分", ex.gate_why("要留意（**减 5 分**）", "JD 写了清单"))

    def test_the_brackets_are_not_doubled_either(self):
        """配平也不许靠再套一层 —— `（（仅限上海））` 数得平，读着不像话。

        变异照出来的：把剥外层那一步换成 `break`，上面两条都不红
        （既没开着口，字也没丢），而屏幕上是两层括号。

        ⚠️ **只查开头那两个左括号，不查结尾。** 第一版连 `））` 一起查，
        当场把 `（要留意（减 5 分））` 判成违规 —— 那不是套了两层，
        是判定那一格**自己带着括号**，内容如实带过来而已。
        「重复包一层」和「内容里本来就有括号」在结尾处长得一样，
        只有开头分得清。
        """
        for v in self.BRACKETS:
            out = ex.gate_why(v, "JD 要求硕士及以上")
            with self.subTest(v=v):
                self.assertNotIn("（（", out, f"外层括号包了两遍：{out}")


class TheOtherPathFromEvaluationToTheScreen(unittest.TestCase):
    """`gate_why` 守住了硬性条件那一侧，`plain()` 这一侧一直没人守。

    两个函数把 `evaluation.md` 的同一份正文送上同一块屏幕：`gate_why` 送硬性条件
    的依据，`plain()` 送「技能」列的悬浮说明和四维的打分依据。上面那个类逐条验了
    markdown 与 PASS / FAIL / FLAG，而 `plain()` **只换词、不剥标记**。

    代价（2026-08-18 实测导出的真实 `data.json`）：

      1035 条  `**这批里最值得投的一个**`      ← 裸星号原样上屏
        40 条  `FLAG：JD 写「中英文沟通清晰」`  ← 没解释的英文码
        26 条  `未知硬性条件标注不判 FAIL`      ← 同上
        10 条  `按 job-rank.md 的口径`          ← 框架自己的文件名
       176 条  `专业能力 88 × 0.6 + 业务领域 65 × 0.4`
                                               ← 打分器的权重，规则说了不上屏

    最后那条尤其值得记：「权重百分比不显示」写在 `web/README.md` 和
    `JobReadout.tsx` 顶上，两处都写着理由，**没有一处是可执行的**。
    """

    def test_no_markdown_markers_survive(self):
        for raw in ("**这批里最值得投的一个**",
                    "按 `job-rank.md` 的口径判的",
                    "职责第 1 条「通过 **Vibe Coding** 快速搭原型」"):
            with self.subTest(raw=raw[:20]):
                out = ex.plain(raw)
                for ch in ("**", "`"):
                    self.assertNotIn(ch, out, f"markdown 记号上屏了：{out}")

    def test_no_bare_status_codes_survive(self):
        for raw in ("FLAG：JD 写「中英文沟通清晰」",
                    "未知硬性条件标注不判 FAIL。",
                    "学历 PASS，专业待确认"):
            with self.subTest(raw=raw[:20]):
                out = ex.plain(raw)
                for code in ("PASS", "FAIL", "FLAG"):
                    self.assertNotIn(code, out, f"英文码上屏了：{out}")

    def test_the_status_codes_do_not_eat_longer_words(self):
        """这三个码都是**别的英文词的前缀**，裸替换会把词切开。

        FAILURE → 「不满足URE」、PASSION → 「满足ION」、FLAGSHIP → 「要留意SHIP」。
        JD 原文里这类大写词并不稀奇（口号、产品名），而换词表是逐字符串替换的，
        不带边界。守卫写在 `INTERNAL_TERMS` 第三项（后面跟字母就不换）。
        """
        raw = "JD 里写着 FAILURE IS NOT AN OPTION 和 PASSION，还有 FLAGSHIP 产品"
        out = ex.plain(raw)
        for w in ("FAILURE", "PASSION", "FLAGSHIP"):
            self.assertIn(w, out, f"「{w}」被从中间切开了：{out}")

    def test_no_framework_file_names_survive(self):
        out = ex.plain("按 `job-rank.md` 的口径，深评正本在 某公司_某岗/evaluation.md")
        self.assertNotIn(".md", out, f"框架的文件名上屏了：{out}")

    def test_the_scoring_formula_is_gone_but_the_two_numbers_stay(self):
        """权重不上屏，**两个分要留下**——它们是这句话里唯一有行动意义的东西。"""
        out = ex.plain("专业能力 88 × 0.6 + 业务领域 65 × 0.4 + 加分项（合计）+2")
        self.assertNotIn("0.6", out, f"权重上屏了：{out}")
        self.assertNotIn("0.4", out, f"权重上屏了：{out}")
        self.assertIn("88", out, f"专业能力那个分丢了：{out}")
        self.assertIn("65", out, f"行业经验那个分丢了：{out}")

    def test_a_zero_bonus_is_dropped_rather_than_printed(self):
        """「加分项 +0」是一条不改变任何事的信息，占一行不如不占。"""
        out = ex.plain("专业能力 80 × 0.6 + 业务领域 40 × 0.4 + 加分项修正 +0")
        self.assertNotIn("加分", out, f"零加分还印着：{out}")

    def test_replacing_a_latin_token_does_not_leave_a_gap(self):
        """换词会**自己造出**中文之间的空格：`不判 FAIL` → `不判 不满足`。

        这正是本仓库一路在拦的那种「中文之间被塞进空格」，只是这一次塞进去的
        不是人，是替换本身。中英之间的空格是对的，不能一起收掉。
        """
        self.assertNotIn(" ", ex.plain("未知硬性条件标注不判 FAIL"))
        kept = ex.plain("用 Claude Code 开发了多组 Agent Skills")
        self.assertIn("用 Claude", kept, f"中英之间的空格被误收了：{kept}")

    #: 否定词 + 被换出来的「不满足」＝双重否定。用**规则**写，不钉某一种拼法。
    DOUBLE_NEG = re.compile("[不非](?:判|算|是|作|等于)?不满足")

    def test_a_negated_code_does_not_become_a_double_negative(self):
        """`不判 FAIL` 换成「不判不满足」，读着像打错字。

        **上面两条断言当时都是绿的**：一条查「没有英文码残留」，一条查
        「没有中文之间的空格」——两条都过，而屏幕上那句话根本读不通。
        少一个「读得通吗」的问句，就能让 24 处摆在面板上没人发现
        （2026-08-21 实测，是读 `applied_jds.py` 的产出时看见的）。

        修法是给这个搭配单列一条换词（长的排前面），用引号把被否定的那个词
        括起来：「未知硬性条件标注不按「不满足」算」。
        """
        for raw in ("按 `job-rank.md` 的口径，未知硬门标注不判 FAIL。",
                    "英语程度待确认（分不清口说/书面，不判 FAIL）",
                    "任职要求未展示，按拿不准不判 FAIL"):
            with self.subTest(raw=raw[:16]):
                out = ex.plain(raw)
                self.assertIsNone(
                    self.DOUBLE_NEG.search(out),
                    "双重否定上屏了：" + out)
                self.assertNotIn("FAIL", out, "英文码上屏了：" + out)

    def test_longer_phrases_come_before_the_short_ones(self):
        """换词表**按顺序逐条替换**，所以短词排在长词前面会把长词吃掉。

        这条规则写在表里那段注释上（「**长的必须排在短的前面**：先换
        『硬门 FAIL』，否则『硬门』先被换掉，剩一个孤零零的英文 FAIL 留在屏幕上」），
        **却没有任何东西守着它** —— 全靠下一个加条目的人记得。
        今天一口气加了 7 条（能力边界那三个搭配、判词、四维、不判 FAIL 两条），
        每一条都得手动想一遍自己该插在哪儿。

        判据是机械的：**A 是 B 的子串、A 又排在 B 前面 → B 永远轮不到。**
        """
        T = ex.INTERNAL_TERMS
        bad = []
        for i, (a, _, _) in enumerate(T):
            for j, (b, _, _) in enumerate(T):
                if i < j and a != b and a in b:
                    bad.append(f"「{a}」(第 {i + 1} 条) 是「{b}」(第 {j + 1} 条) 的子串，"
                               f"却排在它前面 —— 后者永远轮不到")
        self.assertEqual(bad, [], "换词表的顺序会让长词失效：\n  " + "\n  ".join(bad))
        self.assertGreater(len(T), 20, "表像是没读出来 —— 空表恒绿")

    def test_no_reply_yet_is_not_printed_as_zero_percent(self):
        """一个回音都没有、而多数还在等待窗口内时，**不许印「0%」**。

        `OutcomeStats.tsx` 的注释早就为同一件事让过路：0 回音时不画各档回复率图，
        因为「0% 对 0% 不是打分失效的证据，是还没有人回……**等于人人先被泼一盆
        假冷水**」。**那条规矩只用在图上，没用在头条上** —— 而头条是整页最显眼的
        位置：一个大号「有回音 0%」。

        实测（2026-08-21）：85 个投出去，66 个还在等（中位已等 9 天，静默线 10 天）。
        读者看到的是「市场把你全拒了」，而实际是近八成还没到该回的时候。
        """
        import export_web_data as ex
        src = ex.__file__ and (ROOT / "tools" / "export_web_data.py").read_text(
            encoding="utf-8")
        self.assertIn("too_early", src, "后端没有「还没到时候」这个判据")
        # **两处都要改。** 这句话在组件和 App 里各渲染了一遍。
        for rel in ("web/src/components/OutcomeStats.tsx", "web/src/App.tsx"):
            with self.subTest(file=rel):
                c = (ROOT / rel).read_text(encoding="utf-8")
                if "repliedRate" not in c:
                    continue
                self.assertNotIn(
                    "repliedRate ?? 0", c,
                    f"{rel} 用 `?? 0` 把「还没到时候」印成了「0%」")
                self.assertIn("还没有", c, f"{rel} 没给 null 一个说法")

    def test_a_stale_resume_audit_says_so(self):
        """审阅结论比简历旧时，**先说这件事，再给结论**。

        实测（2026-08-21）：审于 08-01，简历 08-12 改过，而面板照样把
        「这份简历现在可以直接投，没有必须处理的问题」当现在时印出来 ——
        说的却是上一版。

        同一个文件里 `pdfStale`（PDF 比 .typ 旧）早就算了，
        **审阅结论没有** —— 而它给的是一句决定性的话，读的人会照着它去投。
        """
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('"stale"', src, "导出没算审阅结论是不是过期了")
        c = (ROOT / "web" / "src" / "components" / "BaseResume.tsx").read_text(
            encoding="utf-8")
        self.assertIn("audit.stale", c, "组件没读这个字段，算了也没人看")
        # **顺序**：提醒必须排在结论之前，否则等于让人先信一遍再收回。
        self.assertLess(c.index("audit.stale"), c.index("audit.verdict &&"),
                        "提醒排在结论后面了")
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(
            encoding="utf-8")
        self.assertIn(".bresume-stale", css, "提醒没有样式，会是一团裸字")

    def test_onsite_reads_the_jd_not_just_the_title(self):
        """驻场标记要读 JD 正文 —— **注释里写了，代码一直没做。**

        那段注释原话：「驻场看标题也看 JD 正文里的措辞——只看标题会漏掉绝大多数
        （实测只看标题：2610 个岗里只认出 4 个）」，而它下面那行只拼了
        `title + employmentType`。2026-08-21 面板上的数**正好还是 4** ——
        注释记下了问题和修法，修法从来没落地。接上正文之后是 45。

        这一类岗对用户不是小事：同一天的 `--applied` 分析里，
        FDE / 驻场那一族的赔率是 **7 : 1**（7 个「选岗问题」对 1 个「主场」）。
        一个只认出 4 个的过滤器等于没有。
        """
        # ① 标题里有的照旧认
        self.assertIn("onsite", ex.pref_tags({"title": "解决方案顾问（驻场）"}))
        # ② 标题里没有、但 JD 正文里有 —— 靠传进来的集合
        e = {"title": "AI 业务落地专家", "url": "https://x.example/1"}
        self.assertNotIn("onsite", ex.pref_tags(e))
        ids = {ex.stable_id(e["url"], e["title"])}
        self.assertIn("onsite", ex.pref_tags(e, ids),
                      "给了正文命中的集合却没认")

    def test_both_call_sites_share_one_set(self):
        """计数与逐岗标记**必须用同一个集合**。

        那段注释自己写着：「过滤在前端做，判据在这里给 —— 两边各写一份判据，
        计数和实际滤掉的数就会对不上」。加了 JD 正文这一路之后，
        「各算一遍」变成了很容易犯的错：两次 `_onsite_ids(user)` 各扫一次盘，
        中间要是有别的东西改了详情库，两个数就不一样了。
        """
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("_onsite_ids(user)"), 1,
                         "`_onsite_ids` 被算了不止一次 —— 两处的数会飘")
        self.assertIn("pref_tags(e, _onsite)", src, "逐岗那处没用上共享的集合")
        self.assertIn("pref_tags(v, onsite_ids)", src, "计数那处没用上共享的集合")

    def test_two_different_counts_do_not_share_a_word(self):
        """同一页上两个不同的总体，**不许用同义的词**。

        实测（2026-08-21）：漏斗第 2 步写「打过分：2626 个」，
        而简历那块写「评过的 687 个岗里」—— 同一个词、同一页、差四倍。
        两边数的其实是不同的东西：漏斗那个含**被粗筛和硬性条件挡掉**的
        （1930 个：粗筛跳过 708 + 硬性条件没过 979），它们没走到打分那一步。

        这是当天第三次撞上「分母/语境不对」：前两次是
        「什么在挡你」的裸数字、和 `--applied` 报表里搬错语料的英语数。
        """
        c = (ROOT / "web" / "src" / "components" / "ResumeRead.tsx").read_text(
            encoding="utf-8")
        i = c.index("ss.total")
        lead = c[max(0, i - 200):i]
        self.assertNotIn("评过的 <b>", lead,
                         "又用回了和漏斗同义的词 —— 两个不同的数会被读成一个")
        self.assertIn("完整", lead, "没说清这个数比漏斗那个窄在哪")

    def test_runnable_commands_are_copyable(self):
        """面板上**能敲的命令一律用 `Cmd`**（可复制、带读屏名），不用行内 `<code>`。

        用户 2026-08-21 的原话：「这个说明还是不明显，比如命令阶段。」
        当时那条探恢复的命令是段落里一个行内 `<code>` —— 而同一页上
        「第 1 步 `/job-scrape`」那些全都是可复制的块，两种待遇。

        顺着查出四处同类，最该修的一处里**嵌着一整条职位链接**
        （`/job-apply <URL>`）—— 不能复制就得手工选中一长串网址。

        `<code>` 留给**不是命令的东西**：路径（`reports/`）、占位符
        （`<职位链接>`）、标识符。判据只认「命令样子的」。
        """
        import re as _re
        bad = []
        for p in sorted((ROOT / "web" / "src").rglob("*.tsx")):
            body = p.read_text(encoding="utf-8")
            for m in _re.finditer(r"<code>(.{0,80}?)</code>", body, _re.S):
                inner = m.group(1)
                looks_runnable = (inner.strip().startswith("/job-")
                                  or "python tools/" in inner)
                # **分界是「让你去敲」还是「提到它」。** 「上面那条 /job-apply
                # 跑完才会有这些」是回指 —— 那条命令就印在上面几行，
                # 再给一个复制按钮是噪音。判据看紧邻前文有没有祈使的动词。
                # **窗口要按「去掉空白之后」算。** 第一版取前 24 个字符，
                # 而 JSX 里 `<code>` 前面常是 20 个缩进空格加 `{" "}` ——
                # 那个「跑」字落在窗口外，变异验证当场骗过了自己（它没红）。
                before = _re.sub(r'\s+|\{"\s*"\}', "", body[max(0, m.start() - 90):m.start()])[-24:]
                told_to_run = any(w in before for w in ("跑", "敲", "运行", "执行"))
                # 占位符（`&lt;…&gt;`）不算：它们是语法说明，不是让你敲的
                if looks_runnable and told_to_run and "&lt;" not in inner:
                    line = body[:m.start()].count(chr(10)) + 1
                    bad.append(f"{p.name}:{line}  <code>{inner.strip()[:40]}</code>")
        self.assertEqual(
            bad, [],
            "这些是能敲的命令，却写成了不可复制的行内 code：\n  "
            + "\n  ".join(bad))

    def test_the_gate_column_vocabulary_round_trips(self):
        """**规格里列的每一种判定写法，显示层都要认得出。**

        2026-08-21 实测用户 285 份真实评估：判定格里 35 处显示层认不出。
        最要紧的一处 —— 评估标题写着「两种算法都不过你的底线」，
        判定格写「不过（见上）」，而面板把这个岗**最决定性的一条**
        显示成「未知」。用户看到的是一个没有明显硬伤的岗。

        规格与显示层是**两头**，中间那根线断了没人会发现：
        规格只说「用 PASS/FAIL/FLAG」，而真实产出里有七种写法。
        这条把两头钉在一起 —— 规格新增一行，显示层就得跟上。
        """
        want = {"PASS": "pass", "FAIL": "fail", "FLAG，非 FAIL": "pass",
                "不适用": "na", "未知": "unknown", "待确认": "unknown",
                "不减分": "pass", "需留意": "pass", "需处理": "pass",
                "不过": "fail", "不过关": "fail"}
        for v, st in want.items():
            with self.subTest(v=v):
                self.assertEqual(ex.gate_state(v), st,
                                 f"判定「{v}」显示层认不出，会印成「结论不明」")
        # 括注是解释，不是判定
        self.assertEqual(ex.gate_state("**不过**（见上）"), "fail")
        # **危险用例**：「不过」在中文里也是「然而」——不许因此翻成不满足
        self.assertEqual(ex.gate_state("PASS，不过要留意年限"), "pass",
                         "把句中的「然而」当成了判定")
        # 规格那头也要写着，否则下一个人还会自造
        spec = (ROOT / "workflows" / "reference"
                / "04-job-evaluation.md").read_text(encoding="utf-8")
        self.assertIn("判定格只许用这几种写法", spec, "规格没写下这条")

    def test_salary_is_not_a_hard_gate(self):
        """薪资低于底线**不是一票否决** —— 它是打分维度。

        `04-job-evaluation.md` 的七道门里没有薪资；它在第二步是
        「薪资与职级（0-100）」。历史评估把「薪资底线」写进了硬门表、
        判定格写「不过」，于是 2026-08-21 把「不过」接上显示层之后，
        流水线审计当场报「判词『值得投』却有硬门不满足」。

        **而评估本身没错**：按框架自己的算式
        73×0.3 + 25×0.25 + 85×0.2 + 75×0.25 = 63.9，确实落在「值得投」档。
        矛盾只来自那一行被放错了表 —— 与「竞业限制」那条是同一个形状。
        """
        # 数字是编的 —— 夹具里写真实薪资就是把用户的数字带进版本库
        # （`test_no_maintainer_data_in_repo` 第一版当场逮到）。
        md = "\n".join([
            "## 硬性条件检查",
            "",
            "| 门槛 | 结果 | 依据 |",
            "|---|---|---|",
            "| 学历与院校 | PASS | 不限 |",
            "| 薪资底线 | 不过 | 挂牌低于底线 |",
            "",
        ])
        names = [g["name"] for g in ex.parse_gates(md)]
        self.assertIn("学历与院校", names, "正常的门被丢了")
        self.assertNotIn("薪资底线", names,
                         "薪资被当成一票否决 —— 框架里它是打分维度")

    def test_ordinary_text_is_untouched(self):
        """控制检查：没有标记的正文一个字都不该动。"""
        # 数字是编的——撞上真实资料里的期望区间就成了泄漏（见
        # `test_no_maintainer_data_in_repo.NoPersonalFiguresInTrackedFiles`）。
        raw = "年包下沿 51 万，落进期望区间 48-63 万"
        self.assertEqual(ex.plain(raw), raw)


class TerminalOutputIsNotMarkdown(unittest.TestCase):
    """终端不渲染 markdown —— 写进 `print()` 的 `**粗体**` 用户看到的就是星号。

    面板那侧早就守住了这条（`gate_why` 不许把 `**FLAG，非 FAIL**` 原样渲染出去），
    **终端这侧一直没人管**。实测四处：

        [!]  中文字体：一个都没命中 —— 这是唯一会**静默出错**的依赖：
        ⚠ 撞到 风控，已**立刻停手**，没有重试。
        ⚠ 3 处两边不一致，**未改写**已有值：
          只看了标题、先放一边（**没有结案**，只是排到队尾…

    成因很好理解：这些说明是照着仓库里 markdown 文档的语气写的，`**` 顺手就带上了。
    中文自己有强调的办法（「」引号、破折号提行、换个说法），不必借 markdown。

    只扫**真正会打印出去的**字符串，不扫 docstring 与注释——那些是给读代码的人看的，
    markdown 在那里是合适的。

    ## 只查粗体，不查反引号 —— 这是量过之后的决定

    这段说明原来写着「终端不渲染 markdown」，而判据只有 `**粗体**` 一条。
    **规则比判据宽**，下一个人照说明一扫就会去「补齐」。

    实测 2026-08-30：会上屏、且带反引号的中文串 **46 条**
    （`audit_pipeline` 34、`query_yield` 6，其余五个文件各 1-2 条），
    逐条看过 —— 几乎全是**字段名**：

        行业看职位库的 `compIndustry`
        匹配度看职位库的 `rank_score`
        个直接取（`recruiterSurname`），其余的在页面上看一眼或问一句

    反引号在这里标的是**代码标识符**，那是终端里读得通的惯例；
    而 `**粗体**` 在终端上就是四个星号，纯粹是噪音。两者不是一回事。

    ⚠️ 与 `AGENTS.md` 那条「显示层要剥掉 `**` 和反引号」不冲突：
    那一条管的是**面板**（`export_web_data.plain()`）—— 从文件正文流向
    界面的字段，反引号会连着显示在纯文本节点和悬浮提示里。终端这一侧的
    读者还包括执行者，字段名标出来是有用的。
    """

    #: 星号成对出现才算强调标记。单个 `*` 可能是乘号或列表符号，不算。
    #: **反引号不在此列**，理由与实测见上面那段。
    #:
    #: 这条豁免是**量过之后**定的，不是没想到 —— 下面
    #: `test_the_backtick_exemption_is_deliberate` 钉住那段理由，
    #: 免得有人照旧说明「补齐」判据，一次改 46 处。
    BOLD = re.compile(r"\*\*[^*\n]+\*\*")

    @staticmethod
    def _docstring_ids(tree):
        return {id(x.body[0].value) for x in ast.walk(tree)
                if isinstance(x, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef))
                and x.body and isinstance(x.body[0], ast.Expr)
                and isinstance(x.body[0].value, ast.Constant)
                and isinstance(x.body[0].value.value, str)}

    def test_the_backtick_exemption_is_deliberate(self):
        """判据窄于说明时，要写清窄在哪、为什么 —— 否则下一个人会去「补齐」。

        实测 46 条带反引号的上屏文案里几乎全是字段名（`compIndustry`
        这种），那是终端读得通的惯例；`**粗体**` 在终端上就是四个星号。
        """
        doc = TerminalOutputIsNotMarkdown.__doc__ or ""
        self.assertIn("只查粗体，不查反引号", doc)
        self.assertIn("46 条", doc, "没留实测数，这条豁免就成了口味")
        self.assertIn("export_web_data.plain()", doc,
                      "没说清面板那一侧仍然要剥 —— 两条规则会被混成一条")

    #: 产出 **markdown 文件**的函数：它们的字面量落进 `.md`，不上终端。
    #:
    #: 上面那段说明断言过「内部常量与正则里几乎不会同时出现中文和
    #: markdown 标记」—— 那时仓库里还没有**生成 markdown 文档**的工具。
    #: 2026-08-21 加了 `applied_jds.py`（把投过的岗聚成一份可翻的清单），
    #: 它的 `render()` 里 `**粗体**` 与 `> 引用` 都是对的，却被这条判据当成
    #: 「星号会原样上屏」报了出来。
    #:
    #: **按函数放行，不按文件**：同一个工具的 `main()` 里那些 print 照查。
    MARKDOWN_WRITERS = {("applied_jds.py", "render")}

    @classmethod
    def _markdown_writer_ids(cls, fname: str, tree) -> set:
        """放行名单里那些函数体内所有字符串字面量的 id。"""
        out = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (fname, node.name) not in cls.MARKDOWN_WRITERS:
                continue
            for c in ast.walk(node):
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    out.add(id(c))
        return out

    def _printed_strings(self):
        """所有**会上屏**的中文串。

        第一版只扫 `print(...)` / `write(...)` 里的字面量。可这个仓库里有一类文案
        是**先 return 再由别处打印**的（`gap_split` 的结论句、`doctor.next_step`
        返回的整段引导），它们一条都没被扫到——实测漏了
        `**先别急着开学习清单**` 这句，`**` 原样上屏。

        所以改成扫**所有非 docstring 的中文字面量**。实测放宽之后只多出那一处，
        没有误伤：内部常量与正则里几乎不会同时出现中文和 markdown 标记。
        """
        for p in sorted((ROOT / "tools").glob("*.py")):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:            # 语法坏了自有别的测试报
                continue
            docs = self._docstring_ids(tree)
            docs |= self._markdown_writer_ids(p.name, tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if id(node) in docs or not re.search(r"[一-鿿]", node.value):
                    continue
                yield p.name, node.lineno, node.value

    def test_the_scan_sees_something(self):
        """控制用例：真扫到了字符串，下面那条才不是空跑。"""
        self.assertTrue(list(self._printed_strings()),
                        "一条打印字符串都没扫到？那下面那条永远绿")

    def test_no_bold_markers_reach_the_terminal(self):
        bad = [f"{f}:{ln}  {s.strip()[:60]}"
               for f, ln, s in self._printed_strings() if self.BOLD.search(s)]
        self.assertEqual(
            bad, [],
            "终端输出里有 markdown 粗体，用户看到的是字面的星号：\n  "
            + "\n  ".join(bad)
            + "\n用中文自己的强调办法：「」引号、破折号提行、或换个说法")

    def test_no_banned_chinese_words_in_next_step_and_stage_strings(self):
        """经 data.json 上屏的中文串也要过词表——这条路原来没人扫。

        `BANNED_WORDS` 扫了 JSX 字面量、README/SETUP、workflows 围栏块，
        `print()` 那侧扫了粗体和英文码；**返回值经 data.json 上屏的中文**
        （next_step 的下一步文案、job_next_step 的逐岗建议、pipeline 每格的
        「在做什么」）一个都不在任何扫描面里——塞一个「台账」进 next_step，
        全套测试照绿。行为级扫：把这些函数在一批真实状态上跑一遍，扫返回值。
        """
        import build_dashboard as bd2
        texts = []
        base = {"scraped": 9, "ranked": 5, "materials": 3,
                "applied": 2, "interviewing": 1}
        for c, kw in [
            (base, {}),
            ({**base, "interviewing": 0}, {}),
            ({**base, "interviewing": 0, "applied": 0}, {}),
            ({**base, "interviewing": 0}, {"n_sellable": 0}),
            ({**base, "interviewing": 0}, {"n_sellable": 0, "n_unranked": 7}),
            ({**base, "interviewing": 0, "applied": 0, "materials": 0}, {}),
            ({"scraped": 0, "ranked": 0, "materials": 0,
              "applied": 0, "interviewing": 0}, {}),
        ]:
            t, cmd = bd2.next_step(c, True, "https://x/1", **kw)
            texts.append(t + " " + (cmd or ""))
        for status in ("", "applied", "interview", "offer", "no response"):
            step = bd2.job_next_step({"applied": {"status": status} if status else None,
                                      "company": "甲", "materials": {"greeting": "x"}})
            if step:
                texts.append(step.get("text") or "")
        # pipeline 每格的 does/cmd 是字面量，直接从源码抠
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        texts += re.findall(r'"does": "([^"]+)"', src)
        self.assertGreaterEqual(len(texts), 12, "扫描集像是空的")
        bad = [f"「{w}」in {t[:40]}" for t in texts
               for w in BANNED_WORDS if w in t]
        self.assertEqual(bad, [],
                         "经 data.json 上屏的文案里有内部词：\n  " + "\n  ".join(bad))

    def test_no_unexplained_english_codes_reach_the_terminal(self):
        """终端这一侧从前**只查粗体**，词表与英文码一次都没扫过。

        面板（`test_web_copy`）、用户文档（`test_docs_track_the_framework`）、
        工作流模板（`test_workflow_output_templates`）三处都拿 `BANNED_CODES`
        扫过，唯独 `print()` 出去的字没有。实测漏的就是 `doctor.py` 里那句
        「PDF 照样生成、ATS 校验也会过」——环境自检是**新用户看到的第一屏**。

        只查英文码，不查 `BANNED_WORDS`：中文内部词在 `tools/` 的字符串里还有
        一批是写给库的键名与状态值（`INTERNAL_TERMS` 的表头别名之类），
        那一侧另有 `OneThingKeepsOneNameOnScreen` 管，这里不重复也不误伤。
        """
        bad = [f"{f}:{ln} 英文码「{c}」  {s.strip()[:60]}"
               for f, ln, s in self._printed_strings()
               for c in BANNED_CODES if re.search(rf"\b{c}\b", s)]
        self.assertEqual(
            bad, [],
            "终端输出里有没解释过的英文码：\n  " + "\n  ".join(bad)
            + "\n要提某个能力就说它做的事，对照表见 AGENTS.md「给用户看的措辞」")


class OneThingKeepsOneNameOnScreen(unittest.TestCase):
    """同一样东西，屏幕上只能有一个名字。

    四维里那个子项，`export_web_data` 自己有一张翻译表把它译成**行业经验**，
    并在旁边写明「『业务域』是四维里那个子项的名字，屏幕上从没解释过」。可实测三个面
    各说各的：

    | 在哪 | 印的是什么 |
    |---|---|
    | 维度显示（走翻译表） | 行业经验 |
    | 面板的简历那块 | 业务领域 |
    | `gap_split` 与导出摘要 | **业务域**（那个明确被判为内部词的） |

    用户要自己把三个词对上号，而它们指的是同一个数。`test_web_copy` 有一条同名规则，
    但只管 React 那侧的「不投」；终端这侧一直没人管。

    这条不评判哪个名字更好——**正名取自那张翻译表**（代码里已经做过的决定），
    这里只保证别处不许再造第二个。
    """

    #: 翻译表所在的变量。按名字取，**不拿正则去全文捞三元组**——第一版那么干，
    #: 把解析表格用的列名别名 `("判定", "结果", "结论")` 也当成了翻译条目，
    #: 于是「未参与判定」这种正常说法被判成违规。
    TABLE = "INTERNAL_TERMS"

    @classmethod
    def _canonical(cls) -> dict:
        """从 `export_web_data.INTERNAL_TERMS` 读「内部词 → 屏幕上的说法」。"""
        tree = ast.parse((ROOT / "tools" / "export_web_data.py")
                         .read_text(encoding="utf-8"))
        node = next((n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", "") == cls.TABLE for t in n.targets)), None)
        if not isinstance(node, (ast.List, ast.Tuple)):
            return {}
        out = {}
        for item in node.elts:
            if not isinstance(item, (ast.Tuple, ast.List)) or len(item.elts) < 2:
                continue
            a, b = item.elts[0], item.elts[1]
            if (isinstance(a, ast.Constant) and isinstance(a.value, str)
                    and isinstance(b, ast.Constant) and isinstance(b.value, str)
                    and re.search(r"[一-鿿]", a.value)):
                out[a.value] = b.value
        return out

    def test_the_translation_table_is_still_there(self):
        """控制用例：正名取自那张表，表没了这条就无从判断。"""
        self.assertTrue(self._canonical(),
                        "export_web_data 里那张「内部词 → 屏幕说法」的表找不到了")

    #: 只扫 `print()` / `write()` 的**实参**，不扫所有中文字面量。
    #:
    #: 放宽到全部字面量试过一次，抓出一堆误报，而且是两类**本来就该保留内部词**的：
    #:
    #: - **正则模式**：`(?:专业能力|技术栈)(\d+)×0\.6\+业务域(\d+)` 要去回读
    #:   `/job-rank` 存下来的算式，改了就读不出来
    #: - **数据格式**：`硬门 FAIL` 是 `/job-rank` 写进 `seen_jobs.json` 的判词，
    #:   别的工具按它匹配。它该在**渲染时**被 `plain()` 换掉，而不是在源头改名
    #:
    #: markdown 那条检查可以放宽（实测只多一处、零误伤），这条不行——同一个扫描
    #: 范围不是对所有规则都合适。
    def _terminal_args(self):
        for p in sorted((ROOT / "tools").glob("*.py")):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if fn not in ("print", "write"):
                    continue
                for a in ast.walk(node):
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                       and re.search(r"[一-鿿]", a.value):
                        yield p.name, node.lineno, a.value

    def _audit_titles(self):
        """审计每一行的**标题** —— 它印在 `[留意] …` 后面。

        上面那个 `_terminal_args` 只看得见直接传给 `print` / `write`的字面量，
        而审计的行是 `(级别, 标题, 正文)` 三元组，`main` 统一印。够不着。
        实测 2026-09-01：4 个标题带着内部词上了屏 ——
        「深评漏判硬门」「硬门：深评表里的门名…」
        「判词自称读过 JD…」「总分和它自己的四维对不上」。

        ⚠️ **只查标题，不查正文。** 正文里合法地引着这些词（那条「深评正文里有
        框架词」的检查本身就要写「判词→结论、四维→评分明细」这张对照）。标题是
        标签，永远不需要解释内部词。

        ⚠️ **也不查 `CHECKS` 里的检查名。** 那是 `--only` 的选择器，是标识符，
        不是文案 —— 同 `_terminal_args` 上面那段对反引号的裁定：终端这一侧的
        读者还包括执行者。
        """
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            # `return [("warn", "标题", …)]` / `out.append((…))`
            if not isinstance(node, ast.Tuple) or len(node.elts) < 2:
                continue
            title = node.elts[1]
            lvl = node.elts[0]
            if not (isinstance(title, ast.Constant)
                    and isinstance(title.value, str)):
                continue
            # 第一格必须是级别，否则这个三元组不是审计的行
            ok = (isinstance(lvl, ast.Constant)
                  and lvl.value in ("warn", "error")) or isinstance(
                      lvl, ast.IfExp)
            if ok:
                yield node.lineno, title.value

    def test_the_title_scan_sees_them(self):
        """**先证明扫到了标题。** 抽取器坏掉时下面那条永远绿。"""
        got = list(self._audit_titles())
        self.assertGreater(len(got), 20,
                           f"只扫到 {len(got)} 个标题，抽取器八成坏了")

    def test_no_internal_name_reaches_an_audit_title(self):
        table = self._canonical()
        bad = []
        for ln, title in self._audit_titles():
            for inner, shown in table.items():
                if inner in title:
                    bad.append(f"audit_pipeline.py:{ln} 「{inner}」应写作「{shown}」：{title}")
        self.assertEqual(
            bad, [],
            "审计的行标题印在屏幕上，不许带内部词：\n  " + "\n  ".join(bad))

    def test_no_internal_name_reaches_the_terminal(self):
        """表里判为内部词的，不许出现在打印给用户的话里。"""
        table = self._canonical()
        bad = []
        for f, ln, s in self._terminal_args():
            for inner, shown in table.items():
                if inner in s:
                    bad.append(f"{f}:{ln} 「{inner}」应写作「{shown}」  "
                               f"{' '.join(s.split())[:48]}")
        self.assertEqual(sorted(set(bad)), [],
                         "终端文案里出现了翻译表判为内部词的说法：\n  "
                         + "\n  ".join(sorted(set(bad))))


class StatusCodesStayInTheStatusColumn(unittest.TestCase):
    """`applied` / `interview` 这些码只该待在 `status` 一列里。

    那一列是给统计用的（`/job-outcome`、`/job-html-report` 都按它算），保持英文没问题。
    但**备注是给人读的**——用户打开 `job_search_tracker.csv` 就看见它。

    实测在总览页点一遍：备注里写的是「改为 interview」，撤销一次再添一句
    「撤销，退回 applied」。服务端拒绝非法跳转时回给页面的也是
    「从「还没投」走不到「applied」」。三处都是把内部码直接搬到台面上。

    更值得记的是：`test_status_from_the_page` 里原本有一条
    `assertIn("interview", notes)`——**断言把这个 bug 钉成了正确行为**，
    所以全绿了这么久。
    """

    #: 从状态机自己派生，别另抄一份——加了新状态这里要自动跟上
    CODES = sorted({v for opts in tk.NEXT.values() for v, _ in opts})

    def _say_it_in_chinese(self, text: str, code: str, where: str):
        label = tk.LABEL[code]
        self.assertIn(label, text, f"{where}没说人话（应有「{label}」）：{text}")
        # `offer` 这类词求职者自己就这么说，它出现在「拿到 offer」里不算漏码；
        # 只有当码本身不是标签的一部分时，露出来才是问题。
        if code not in label:
            self.assertNotIn(code, text, f"{where}漏出了内部码「{code}」：{text}")

    def test_the_note_written_for_each_state_is_readable(self):
        for code in self.CODES:
            for created in (True, False):
                with self.subTest(code=code, created=created):
                    self._say_it_in_chinese(
                        tk.note("2026-08-02", code), code, "备注")

    def test_a_real_round_trip_leaves_no_codes_behind(self):
        """走**真实路径**：建行 → 推进 → 撤销，然后读盘上那一列。

        只测 `note()` 会漏掉 `undo()` 自己拼的那句——它是另写的一处。
        """
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "job_search_tracker.csv"
            job = {"company": "甲公司", "title": "岗A", "url": "https://x/1"}

            def row():
                return tk.load(p)[1][0]

            tk.set_status(p, None, job, "applied", "2026-08-02")
            r = tk.set_status(p, row(), job, "interview", "2026-08-05")
            tk.undo(p, row(), r["prev"], "2026-08-06")
            notes = row()["notes"]

            self.assertIn("撤销", notes, f"撤销没留痕：{notes}")
            for code in self.CODES:
                if code in tk.LABEL[code]:
                    continue
                with self.subTest(code=code):
                    self.assertNotIn(code, notes,
                                     f"备注串里漏出内部码「{code}」：{notes}")

    def test_an_unknown_state_is_shown_rather_than_swallowed(self):
        """认不出的状态原样露出来，好过把用户的状态说成别的。

        例子原来用的是 `withdrawn`——**选错了**：那不是「认不出的状态」，而是
        `/job-outcome` 文档里正式的终结态（`outcome.md` 的状态列表里就有它），
        只因为它不做成按钮、LABEL 从按钮表派生，就一直裸印英文码。
        拿一个真实存在的状态当「未知」的例子，等于把词汇表的洞钉成了正确行为。
        """
        self.assertEqual(tk.say("zzz_not_a_status"), "zzz_not_a_status")

    def test_every_outcome_documented_final_state_has_a_label(self):
        """`/job-outcome` 让用户记的每个终态，面板都得会说人话。

        清单以 `workflows/job-outcome.md` 的状态枚举为准（hired / offer declined /
        rejected / no response / withdrawn）。`withdrawn` 实测漏过：不是按钮 →
        派生不出 → 上屏是英文码。
        """
        doc = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")
        for code in ("hired", "offer declined", "rejected", "no response",
                     "withdrawn"):
            with self.subTest(code=code):
                self.assertIn(f"`{code}`", doc,
                              f"outcome.md 不再记 {code} 了？清单该跟着改")
                said = tk.say(code)
                self.assertNotEqual(said, code,
                                    f"终态「{code}」没有中文说法，会裸印英文码")

    def test_no_row_yet_is_not_shown_as_an_empty_string(self):
        """空串在这套状态机里是「台账里还没有这一行」，不是「状态为空」。"""
        self.assertTrue(tk.say("").strip(), "还没投的状态显示成了空白")


if __name__ == "__main__":
    unittest.main()


class WeightJargonStaysOffTheScreen(unittest.TestCase):
    """权重是打分器的内部参数，不上台面——**算式和散文都算**。

    `strip_weights` 只剥算式（`专业能力 88 × 0.6 + …`），剥不掉句子。
    2026-08-20 扫真实导出，1 条漏网：「按打分规则记信息缺失，**25% 权重重分配
    到其余三维**」——深评原文就是这么写的，剥离器一个字都动不了。

    给用户的写法是说**它对他的意思**：「薪资没标，这一项不计入，分数按其余三项算」。
    """

    def test_no_weight_wording_in_exported_notes(self):
        import json
        import re as _re
        f = ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            self.skipTest("还没导出过")
        pat = _re.compile(r"权重|占\s*\d+\s*%")
        bad = [f"{j.get('title','')[:20]}·{dim.get('name')}：{(dim.get('note') or '')[:44]}"
               for j in json.loads(f.read_text(encoding="utf-8"))["jobs"]
               for dim in (j.get("dimensions") or [])
               if pat.search(dim.get("note") or "")]
        self.assertEqual(bad, [],
                         "面板文案里出现了权重这个内部参数——说它对用户的意思，"
                         f"别说机制：\n  " + "\n  ".join(bad[:6]))

    def test_no_weight_wording_in_the_frontend_text(self):
        """同一把尺子还得量**前端自己写死**的那批句子。

        上一条扫的是 `data.json` 里 `dimensions[].note`——那是从评估文件导出来的字。
        组件里还有一类话不经过导出，直接写在 JSX 里，上一条永远看不见。
        2026-09-30 在渲染后的 DOM 里量到两句，都在 `OutcomeStats` 的投后统计空状态：
        「那就该回去调评估权重」「就该回去调权重」。
        取文本节点用 `test_web_copy.jsx_text_nodes`（屏幕上真会出现的字那份正本），
        不在这儿另写一套剥法。
        """
        sys.path.insert(0, str(ROOT / "tests"))
        from test_web_copy import jsx_text_nodes
        pat = re.compile(r"权重|占\s*\d+\s*%")
        bad, seen = [], 0
        for f in sorted((ROOT / "web" / "src").rglob("*.tsx")):
            for ln, txt in jsx_text_nodes(f.read_text(encoding="utf-8")):
                seen += 1
                if pat.search(txt):
                    bad.append(f"{f.name}:{ln} {txt[:44]}")
        self.assertGreater(seen, 120,
                           f"从 JSX 里只抽出 {seen} 个文本节点——扫描源怕是空了，"
                           "这条等于没跑")
        self.assertEqual(bad, [],
                         "前端写死的文案里出现了权重——说它对用户的意思，别说机制：\n  "
                         + "\n  ".join(bad[:6]))

    def test_the_rule_is_in_the_wording_table(self):
        t = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("散文里提权重", t, "措辞表只禁了算式，没禁散文里提权重")
        self.assertIn("这一项不计入", t, "没给出该怎么写")

    def test_zero_bonus_leaves_no_dangling_word(self):
        """「加分项 0/5 命中」整段删——只删到 0/5 会留下孤零零一个「命中」。"""
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import export_web_data as ex
        got = ex.strip_weights("技能与经验 63 = 专业能力 88 × 0.6 + 业务领域 25 × 0.4 + 加分项 0/5 命中")
        self.assertNotIn("命中", got, f"零加分删剩了尾巴：{got}")
        # 非零的两种写法要原样保留数量
        self.assertIn("1 项", ex.strip_weights("专业能力 88 × 0.6 + 业务域 60 × 0.4 + 加分项 1 项"))
        self.assertIn("+2", ex.strip_weights("专业能力 88 × 0.6 + 业务域 65 × 0.4 + 加分项（合计）+2"))


class TheRealSnapshotIsScannedToo(unittest.TestCase):
    """构造的输入走不到的分支，真实快照里走到了。

    上面 `test_no_banned_chinese_words_in_next_step_and_stage_strings` 的
    docstring 写着「塞一个『台账』进 next_step，全套测试照绿」—— 它正是为这件事
    写的，而 2026-08-29 面板上那句最显眼的话里就写着「台账上一个回音都没有」。

    没抓到不是判据错，是**喂的输入走不到那个分支**：那句话要求「有投出去、且已经
    沉底」的状态，而构造用例里没有。行为级扫描永远受限于构造的那几种状态。

    所以再加一条从**真实 `data.json`** 扫的：它覆盖的是这台机器上真正跑到过的
    每一个分支。没有快照就跳过 —— 不拿构造数据假装验过。

    ⚠️ **「能力边界」在这条里不算。** 词表挡它是对的（那是框架词），但面板上
    55 处里多数说的是**模型的**能力边界（「对 AI 能力边界有体感」「理解其能力边界
    和失败模式」）—— 那是 JD 自己的话，也是这一行的技术术语，不是在拿框架词跟
    用户说话。真要清的是「候选人的能力边界」那个用法，而这条扫描分不出来，
    分不出就不报（同「判不准的扫描器比没有更坏」）。
    """

    #: 面板上要挡的那几个：**只取没有普通中文读法的框架词**。
    #:
    #: `BANNED_WORDS` 是按具体界面校准的（JSX 字面量、报告模板、围栏块），
    #: 拿它扫**全量**面板数据会过火 —— 那里面还有用户自己的简历答案和 JD 原话。
    #: 实测 2026-08-29：直接套那张表报出 86 处，全部是「投放」
    #: （「零投放」「广告投放」是这一行的正常说法）、以及「能力边界」
    #: （多数说的是模型的能力边界，JD 自己的词）。
    #: **判不准的扫描器比没有更坏** —— 这个仓库为此删过一个。
    #: 「核销」也拿掉了：它作为政企公文词该挡（我们自己写「把这条核销」时），
    #: 但「团购核销」是本地生活这一行的业务术语，从 JD 里引过来的。同「投放」。
    LIVE = ["台账", "判词", "四维", "短名单", "驾驶舱", "读数", "入账",
            "信息质量", "硬门"]

    def _strings(self):
        f = ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            self.skipTest("还没导出过面板数据")
        out = []

        def walk(o, path):
            if isinstance(o, str):
                if len(o) > 3:
                    out.append((path, o))
            elif isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")

        walk(json.loads(f.read_text(encoding="utf-8")), "data")
        if len(out) < 50:
            self.skipTest("快照太小，说明不了什么")
        return out

    def test_no_internal_word_reaches_the_real_panel(self):
        rows = self._strings()
        bad = []
        for path, s in rows:
            for w in self.LIVE:
                if w == "硬门" and re.search(r"硬门(?!槛)", s) is None:
                    continue
                if w != "硬门" and w not in s:
                    continue
                bad.append(f"「{w}」 {path[:44]}  …{s[:44]}…")
        # 判词串里的门名（`不满足硬性条件 (语言（候选人自带硬门）)`）是**存量数据**，
        # 不是代码里的字面量 —— 它由 `/job-rank --all` 重评才改得掉。
        # 这条守的是「代码别再往面板上写框架词」，所以把那一族排掉，
        # 剩下的必须是零。存量那边由 audit 的「门名没按七道正规名写」盯着。
        bad = [b for b in bad if ".gateFailReason" not in b and ".gates[" not in b]
        self.assertEqual(bad, [],
                         "真实面板数据里有内部词（词表挡了，但没人扫这条路）：\n  "
                         + "\n  ".join(bad[:8]))

    def test_no_markdown_marker_reaches_the_real_panel(self):
        """**同一棵树，另一条规矩：`**` 和反引号也不许上屏。**

        `AGENTS.md`「给用户看的措辞」末尾那几段写着：面板上那些字进的是纯文本
        节点和悬浮提示，`**这批里最值得投的一个**` 会连着四个星号一起显示；
        凡是从文件正文流向界面的字段，显示层都要先过 `export_web_data.plain()`。

        **这条规则此前只有逐字段的断言**（全仓十几处 `assertNotIn("**", …)`，
        各自盯一个消息或一个字段），**没有任何一条扫整棵树** —— 也就是说
        新加一个字段就自动躲过。仓库自己的历史正好证明这个洞：
        2026-08-18 量出 1035 条，接上 `plain()` 后逐步清空，08-27 复算
        **只剩 1 条**，而那一条是 `emailBody` —— 用户整段粘进邮件发给用人方的字，
        `mailto:` 会把它原样塞进链接。它是**量出来**的，不是守出来的。

        判据用同一个 `_strings()`，不另写一套遍历。
        """
        bad = [f"{path[:46]}  …{s[:46]}…"
               for path, s in self._strings() if "**" in s or "`" in s]
        self.assertEqual(
            bad, [],
            "面板数据里有 markdown 标记（会连着星号/反引号一起显示，"
            "对外文案还会跟着邮件发出去）：\n  " + "\n  ".join(bad[:8]))

    #: 标题就写明「这一段是要说给用户听的」的小节。**只认这几种写法** ——
    #: 「这一行是不是对用户说的」在一般散文里判不准，而
    #: 「判不准的扫描器比没有更坏」是这个仓库删过一个扫描器换来的话。
    _FOR_USER = re.compile(r"^#{2,4}\s*.*(报给用户|后续步骤|汇报|给用户的|呈现)")

    def test_no_internal_word_in_a_section_written_for_the_user(self):
        """**工作流里那些「印给用户」的小节，也归这条规矩管。**

        `AGENTS.md`「给用户看的措辞」说的是「凡是给用户看的东西」，
        而本文件此前只扫**工具渲染出的输出**（`data.json`、终端）——
        工作流里的输出模板它够不着。

        实测 2026-09-01：`job-apply.md`「### 后续步骤」印给用户的是
        「用 `/job-outcome <company>` **记入台账**」——「台账」正是词表里
        点名要换掉的政企公文词（→ 投递记录），占位符还是英文的 `<company>`，
        而那恰好是要用户照着敲的那部分。全仓 21 处「台账」里，
        **只有这一处是对用户说话的**，其余都是流程内部描述（规则允许）。

        围栏里的字（```…```）另有两处内部词，都不是给用户的
        （一处是执行者的伪代码、一处是 JSON 字段名），所以判据取的是
        **小节标题**这个精确面，不是「围栏内」那个粗面。
        """
        words = self.LIVE
        bad = []
        for wf in sorted((ROOT / "workflows").glob("*.md")):
            lines = wf.read_text(encoding="utf-8").splitlines()
            idx = [i for i, l in enumerate(lines) if re.match(r"^#{2,4}\s", l)]
            for k, i in enumerate(idx):
                if not self._FOR_USER.match(lines[i]):
                    continue
                end = idx[k + 1] if k + 1 < len(idx) else len(lines)
                for j in range(i, end):
                    l = lines[j]
                    if l.lstrip().startswith(">"):
                        continue        # 引用块记的是「原来错在哪」
                    for w in words:
                        if w == "硬门" and not re.search(r"硬门(?!槛)", l):
                            continue
                        if w != "硬门" and w not in l:
                            continue
                        bad.append(f"{wf.name}:{j+1} 「{w}」 {l.strip()[:60]}")
        self.assertEqual(
            bad, [],
            "工作流里这些「印给用户」的小节带着内部词：\n  " + "\n  ".join(bad[:8]))

    def test_the_user_facing_sections_are_found(self):
        """**先证明它真扫到了小节。** 一个都认不出时上面那条永远绿。"""
        n = sum(1 for wf in (ROOT / "workflows").glob("*.md")
                for l in wf.read_text(encoding="utf-8").splitlines()
                if self._FOR_USER.match(l))
        self.assertGreater(n, 3, f"只认出 {n} 个给用户看的小节，判据八成失效了")

    def test_the_marker_detector_can_fail(self):
        """**先证明它抓得到。** 上面那条现在是 0 条，而「永远是 0」和
        「扫描器坏了」在断言层面长得一模一样 —— 这个仓库给这个形状起过名字：
        「写了、跑着、绿着，但看不见」。

        两头都验：扫描真的取到了成千上万条字符串，且带标记的那两种当场认得出。
        """
        rows = self._strings()
        self.assertGreater(len(rows), 500,
                           f"只扫到 {len(rows)} 条字符串，遍历八成坏了")
        leaked = [("data.jobs[0].emailBody", "您好，我做的是 **AI 产品**"),
                  ("data.jobs[0].nextStep.text", "跑 `/job-apply`")]
        self.assertEqual(
            [p for p, s in rows + leaked if "**" in s or "`" in s],
            [p for p, _ in leaked],
            "注进去的两条认不出来，或者真快照里混进了别的")
