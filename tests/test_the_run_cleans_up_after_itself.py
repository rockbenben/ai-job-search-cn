# -*- coding: utf-8 -*-
"""自己写坏的，自己在同一轮里补掉 —— 不要报给用户。

`/job-auto` 收尾那条 `audit_pipeline.py --actionable` 会把「深评缺小节」
「「可以考虑」没写投前必问」连着文件名一起报出来。而**其中一部分正是这一轮
几分钟前刚写下的** —— 把它印成一条「你去跑 `/job-apply <链接>`」，等于自己
写坏了再让用户来收拾，而这条命令的整个卖点是「中途不用你盯着」。

## 证据：整批整批地缺，而且几乎只缺同一节

实测活动用户 2026-08-30，按深评自己写的评估日期拆开：

    （按批次拆开的分布见下面 TheBatchRunsItInsteadOfLookingAtIt
    的 docstring —— 同一张表这个文件里原来存了两份。）
    2026-08-11   79 份   全写齐
    2026-08-25    6 份   全写齐

一次跑里要么每份都写、要么每份都不写。缺的不是规则（04 早就写着
「条件已在结论里的写「同上」」），是**收工前那一眼**。

## 两道网，位置不同

1. **写盘前**（`job-apply.md` 第 6 步）：写完那一份就对一眼小节。最早、最便宜。
2. **收尾**（`job-auto.md`）：兜底。本轮出的当场补，存量照报不改。

第二道网不能替代第一道：等到收尾时材料已经落盘，用户可能已经打开过了。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _srcscan import code_of  # noqa: E402
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
APPSRC = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
EVAL04 = (ROOT / "workflows" / "reference"
          / "04-job-evaluation.md").read_text(encoding="utf-8")


#: 造样例用的换行。写成常量而不是字面量，是因为这份文件被补丁脚本改过。
LF = chr(10)


def flat(x: str) -> str:
    return " ".join(x.split())


class TheFirstNetIsBeforeItHitsDisk(unittest.TestCase):
    def test_apply_checks_its_own_sections(self):
        self.assertIn("### 落盘前对一眼小节", APPLY)

    def test_it_does_not_copy_the_section_list(self):
        """清单在 04，这里指过去就行 —— 抄一份就等着分叉。"""
        i = APPLY.index("### 落盘前对一眼小节")
        seg = flat(APPLY[i:APPLY.index("### 落盘前成品扫描")])
        self.assertIn("04-job-evaluation.md", seg)
        self.assertIn("这里不抄一份", seg)
        # 六节的名字一个都不许在这一段里被列出来（列出来就是第二份清单）
        for name in ("职位真伪信号", "优势", "缺口", "评分明细"):
            with self.subTest(name=name):
                self.assertNotIn(f"「{name}」、", seg)

    def test_it_says_write_the_placeholder_not_delete_the_heading(self):
        i = APPLY.index("### 落盘前对一眼小节")
        seg = flat(APPLY[i:APPLY.index("### 落盘前成品扫描")])
        self.assertIn("写「同上」或「无」，不要整节删掉", seg)

    def test_it_says_why_the_heading_matters(self):
        """不写理由，下一个人还会因为「没东西可写」把它删掉。"""
        i = APPLY.index("### 落盘前对一眼小节")
        seg = flat(APPLY[i:APPLY.index("### 落盘前成品扫描")])
        self.assertIn("一节没写就当那一项为空", seg)

    def test_the_measurement_is_recorded(self):
        i = APPLY.index("### 落盘前对一眼小节")
        seg = APPLY[i:APPLY.index("### 落盘前成品扫描")]
        self.assertIn("落盘前", seg)

    def test_gate_fails_are_excused(self):
        """硬门 FAIL 的文件本来就该短 —— 不把合法的短文件也报成缺节。"""
        i = APPLY.index("### 落盘前对一眼小节")
        seg = flat(APPLY[i:APPLY.index("### 落盘前成品扫描")])
        self.assertIn("任一 FAIL 则到此为止", seg)


class TheSecondNetFixesItsOwnOutput(unittest.TestCase):
    def test_auto_fixes_this_rounds_own_files(self):
        self.assertIn("本轮自己出的材料当场补完再收工", AUTO)

    def test_the_backlog_is_still_only_reported(self):
        """291 份逐份补是另一笔账，得用户点头 —— 别顺手替他决定。"""
        i = AUTO.index("**本轮自己出的那几份，当场补，不要报给用户。**")
        seg = flat(AUTO[i:i + 1200])
        self.assertIn("存量", seg)
        self.assertIn("得用户点头", seg)

    def test_it_only_fills_the_missing_section(self):
        """借这个口子重写存量，正是 `materials` 那条要挡的。"""
        i = AUTO.index("**本轮自己出的那几份，当场补，不要报给用户。**")
        seg = flat(AUTO[i:i + 1200])
        self.assertIn("只补缺的那一节，不重跑深评、不重写已有的开场白", seg)

    def test_it_re_runs_the_check_after_fixing(self):
        """补完不验一遍，等于把「补了」当成「补对了」。"""
        i = AUTO.index("**本轮自己出的那几份，当场补，不要报给用户。**")
        seg = flat(AUTO[i:i + 1200])
        self.assertIn("补完重跑一次这条检查确认它不再报", seg)

    def test_it_says_the_first_net_comes_first(self):
        i = AUTO.index("**本轮自己出的那几份，当场补，不要报给用户。**")
        seg = flat(AUTO[i:i + 1600])
        self.assertIn("job-apply.md", seg)


class TheBlockedListPointsAtTheBlockedJob(unittest.TestCase):
    """批量不回头问，问题攒到面板上 —— 那一栏给的命令要指得到那几个岗。

    原来给的是 `/job-apply --top N`，而那条**按分数取前 N**。卡住的岗不一定
    在里面：它可能是「可以考虑」那一档，也可能排在第 45。那时
    「答完这几条，再跑一次下面的命令就会把它们补上」是句假话 ——
    他敲完发现没动，然后连带不信这一整块。

    批量命令在这里天然不对：这一栏的每一行都是一个**具体的、被具体东西卡住的**
    岗，而批量的选岗条件（分数、档位、有没有材料）与「谁被卡住了」毫无关系。
    """

    def test_it_names_the_job_not_a_batch(self):
        i = APPSRC.index("有 {blocked.length} 个岗卡住了")
        seg = APPSRC[i:i + 1800]
        self.assertIn("/job-apply ${blocked[0].url}", seg,
                      "阻塞那一栏又给了一条批量命令 —— 它未必包含被卡住的岗")
        self.assertNotIn("--top ${TOP_N}", seg)

    def test_the_sentence_matches_the_command(self):
        """文案说的和命令做的要是同一件事：逐个跑，不是跑一次批量。"""
        i = APPSRC.index("有 {blocked.length} 个岗卡住了")
        seg = APPSRC[i:i + 1800]
        self.assertIn("逐个跑", seg)

    def test_the_reason_is_recorded(self):
        i = APPSRC.index("有 {blocked.length} 个岗卡住了")
        seg = " ".join(APPSRC[i:i + 2200].split())
        self.assertIn("按分数取前 N", seg)


class TheRuleItLeansOnIsReallyIn04(unittest.TestCase):
    """指过去的那两条要真的在 —— 指一条不存在的规则比不指更坏。"""

    def test_the_signal_section_says_write_none(self):
        self.assertIn("没有就写「无」", EVAL04)

    def test_the_advice_section_says_write_same_as_above(self):
        self.assertIn("上面结论那一行里已经把条件说了的，这里写「同上」", EVAL04)

    def test_the_gate_fail_shortcut_is_real(self):
        self.assertIn("到此为止", EVAL04)


class TheBatchRunsItInsteadOfLookingAtIt(unittest.TestCase):
    """**「记得对一眼」在第 30 份上从来指望不上。**

    `job-apply.md` Step 6 写着写盘前逐节对一遍小节清单。规则没错，
    错在它是一句给写手看的散文提示，而这件事发生在一批 20、30 份的中间。
    实测按批次拆开（2026-08-30）：

        2026-08-17   40 份   40 份缺「建议」
        2026-08-26   10 份   10 份缺「建议」
        2026-08-27   30 份   30 份缺「建议」
        2026-08-11   79 份   全写齐
        2026-08-25    6 份   全写齐

    一次跑里要么每份都写、要么每份都不写 —— 那不是手滑，是那一眼没发生。

    ## 命令为什么在 `job-auto.md` 而不在 `job-apply.md`

    `/job-apply` 承诺不依赖 Python（README 与 SETUP 都这么写，
    `test_no_python_sneaks_in` 盯着）。第一版就把 `python tools/…` 写进了
    Step 6，当场被那条守卫拦下 —— **拦得对**。
    而实测出问题的是**批量**，批量走 `/job-auto`，它本来就依赖 Python；
    单岗跑只出一份文件，Step 6 那一眼够用。
    """

    def test_the_batch_step_runs_the_checker(self):
        i = AUTO.index("出材料（")
        j = AUTO.index("收尾（无条件）")
        make = AUTO[i:j]
        self.assertIn("--sections", make,
                      "每批写完盘没跑逐份小节检查")

    def test_it_runs_before_the_snapshot_refresh(self):
        """先查再刷快照 —— 反过来的话这一批已经被选走了。"""
        i = AUTO.index("出材料（")
        j = AUTO.index("收尾（无条件）")
        make = AUTO[i:j]
        self.assertLess(make.index("--sections"),
                        make.index("export_web_data.py"),
                        "查小节排在刷快照后面了")

    def test_the_gate_says_what_to_do_when_it_fires(self):
        """**一道只报数的闸门等于没有闸门。**

        `--sections` 报非零之后，工作流原来直接往下走去刷快照 —— 而刷完快照
        这一批就被选走，缺陷当场变成「存量」。同一份文件上面那段实测算的正是
        这笔账：「收尾当场补的话，它们在离开那一轮之前就齐了；报给用户，
        就变成 55 份存量。」

        差别不在工作量，在**手里还有没有那份 JD**：这一批刚写完，补一节是顺手；
        存量要重开一次页面。
        """
        i = AUTO.index("出材料（")
        j = AUTO.index("收尾（无条件）")
        make = AUTO[i:j]
        k = make.index("--sections")
        seg = make[k:make.index("export_web_data.py", k)]
        self.assertIn("当场补", seg, "闸门报了非零，却没说要补")
        self.assertTrue(re.search(r"别刷快照|重跑到零", seg),
                        "没说清补完之前不许往下走")

    def test_it_says_which_sections_can_be_filled_in(self):
        """补法不能凭记性 —— 三节三种规矩，写错一节就是撒谎。"""
        i = AUTO.index("每批那条 `--sections` 在补哪个洞")
        seg = AUTO[i:i + 2500]
        self.assertIn("同上", seg)
        self.assertIn("不能写「无」", seg)
        self.assertIn("整份重跑", seg)

    def test_the_gate_survives_midnight(self):
        """**一轮会跨过午夜，而闸门只认「今天」时会真空通过。**

        23:55 写完那一批、00:05 跑闸门 —— 集合是空的，它报「没什么可查的」、
        退出码 0，那一批的缺口直接变成存量。

        这个仓库为同一形状付过学费：`portal_budget` 的间隔判据原来
        「00:00:05 跑一次，23:59 那个动作落在窗口外，`acts` 为空，
        整个间隔判据被跳过」。

        只放宽凌晨那几个小时：拿「最近有产出的那一天」兜底会把三天前的存量
        整批报出来，而这道闸门的全部价值是「这一批」。
        """
        import datetime as _d
        import audit_pipeline as ap

        # **钉行为，不钉那三行写在谁的函数体里。**
        # 2026-08-31 那三行搬进了 `this_batch_days()`（收尾那一档也要同一个
        # 窗口，两处各写一份就是第二个住址）—— 这条当场红了，而页面行为
        # 一点没变。判据改成「这个窗口真的跨得过午夜」。
        days = ap.this_batch_days()
        self.assertIn(_d.date.today().isoformat(), days)
        want = 2 if _d.datetime.now().hour < ap._MIDNIGHT_GRACE_H else 1
        self.assertEqual(len(days), want, "宽限窗口跨不过午夜了")
        seg = code_of("tools/audit_pipeline.py", "def _sections_cli(")
        self.assertIn("this_batch_days()", seg, "闸门没走那一份")

    def test_the_grace_does_not_swallow_the_backlog(self):
        """宽限只回看一天 —— 再宽就成了存量报表。"""
        import audit_pipeline as ap
        self.assertLessEqual(ap._MIDNIGHT_GRACE_H, 12)
        seg = code_of("tools/audit_pipeline.py", "def _sections_cli(")
        self.assertNotIn("days=2", seg)

    def test_apply_still_has_no_python(self):
        """这条重复了 `test_no_python_sneaks_in`，但重复得有理由：

        它是**这一处改动**当场踩过的那一脚，钉在这里读的人才看得见因果。
        """
        self.assertNotRegex(APPLY, r"python\s+tools/")

    def test_apply_points_at_the_batch_net(self):
        """单岗那一眼要说清批量有兜底，否则读的人以为只有自己这一道。"""
        i = APPLY.index("### 落盘前对一眼小节")
        seg = flat(APPLY[i:APPLY.index("### 落盘前成品扫描")])
        self.assertIn("每批写完盘就跑一条逐份检查", seg)
        self.assertIn("不依赖 Python", seg)


class TheSectionRuleHasOneImplementation(unittest.TestCase):
    """全量审计和写盘后那条查的必须是同一件事。"""

    def test_the_full_check_calls_the_shared_judge(self):
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        i = src.index("def check_evaluation_sections")
        body = src[i:i + 6000]
        self.assertIn("missing_sections(t)", body,
                      "全量那条又自己判了一遍")

    def test_the_gate_fail_exemption_is_in_the_shared_judge(self):
        """硬门 FAIL 的文件本来就该短 —— 这条豁免也只能有一份。"""
        import audit_pipeline as ap
        self.assertIsNone(ap.missing_sections("| 学历 | **FAIL** | 差得远 |"))
        self.assertIsNone(ap.missing_sections("这个岗不满足硬性条件"))

    def test_it_reports_what_is_missing(self):
        import audit_pipeline as ap
        self.assertIn("建议", ap.missing_sections("## 结论") or [])
        full = LF.join("## " + k for k in ap.EVAL_SECTIONS)
        self.assertEqual(ap.missing_sections(full), [])

    def test_the_exit_code_is_non_zero_when_something_is_missing(self):
        """写完盘那一刻要的是**闸门**，不是一段读物。"""
        import audit_pipeline as ap
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "一个岗" / "evaluation.md"
            f.parent.mkdir()
            f.write_text("## 结论" + LF + "投", encoding="utf-8")
            self.assertEqual(ap._sections_cli([str(f.parent)]), 1)
            f.write_text(LF.join("## " + k for k in ap.EVAL_SECTIONS),
                         encoding="utf-8")
            self.assertEqual(ap._sections_cli([str(f.parent)]), 0)


if __name__ == "__main__":
    unittest.main()
