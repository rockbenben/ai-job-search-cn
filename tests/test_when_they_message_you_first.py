# -*- coding: utf-8 -*-
"""`job-resume.md` 2.6 那一整节是为了让人来找你 —— 而人来了之后没有下一步。

2.6 讲的是**被搜到**那条路：在线简历、刷新频率、公开范围、期望岗位、完整度。
它的开场白自己写着：

> 国内主流平台（猎聘 / BOSS / 智联 / 前程）上，HR 有很大一部分工作是**反过来的**：
> 在简历库里搜，主动联系人。

而全仓库**没有任何一处**接住那件事做成之后的场景。搜遍 `workflows/`：
「对方先」「主动来」「来找你」「收到打招呼」—— 零命中。整套流程只走一个方向：
你找岗 → 你评估 → 你发出去。

## 接不住的地方具体在哪

1. **`job-apply.md` 1.5a** 那张「有没有对话方」的表只有两行（平台内直聊 /
   网申表单），**没有一行问「谁先开的口」**。
2. **`06` 渠道 1** 的结构表第 1 项写死「「您好，」+ 最硬的匹配点」。对方先开口时
   照这个写，等于对一句已经问到脸上的话视而不见。
3. **入口没人说**。`/job-apply <整段职位描述>` 早就能吃一段粘贴进来的 JD ——
   那正是「猎头把岗丢进聊天框」的入口，而索引里从没点明过。

## 「看到这个岗」在这里是双重错误

它本来就在「不许出现」那张表里（开场铺垫；实测活动用户 2026-08-24，
236 份开场白里 69 份栽在这一类）。而对方先开口时它还多一层荒谬：**那是他发给你的**,
「看到」是理所当然 —— 会话列表里唯一看得见的那一行，被一句废话占掉。

## 改的是三处措辞，不是新增一条命令

评估这一半 `/job-apply` 本来就做得了。缺的只是：判定里加一问、渠道 1 加一个回信版、
索引里点明入口。**不新增命令** —— 一条只换第一句话的流程不值一个新入口。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")
RESUME = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")
# 索引表的正本：`workflows/INDEX.md`（2026-09-29 从 AGENTS.md 搬出，AGENTS.md 只留指针）。
INDEX = (ROOT / "workflows" / "INDEX.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class ThePathTableAsksWhoSpokeFirst(unittest.TestCase):
    def _table(self) -> str:
        i = APPLY.index("### 1.5a 有没有对话方")
        return APPLY[i:APPLY.index("**无对话方时**", i)]

    def test_there_is_a_row_for_it(self):
        self.assertIn("对方先来找你", self._table())

    def test_it_is_still_a_counterparty(self):
        """对方先开口仍然有人可写 —— 别把它错分进「无对话方」那一档，
        那一档是「渠道 1 不生成」。"""
        row = next(l for l in self._table().splitlines() if "对方先来找你" in l)
        self.assertIn("有对话方", row)
        self.assertNotIn("**无对话方**", row)

    def test_the_two_original_rows_survive(self):
        t = self._table()
        self.assertIn("平台内直聊", t)
        self.assertIn("网申表单", t)

    def test_the_criterion_is_one_question(self):
        """判定不能靠平台猜 —— 同一个平台两种都有。"""
        i = APPLY.index("对方先来找你")
        self.assertRegex(flat(APPLY[i:i + 1400]),
                         r"这段 JD 是他发给你的，还是你自己找到的？")

    def test_it_says_why_this_is_not_a_corner_case(self):
        i = APPLY.index("对方先来找你")
        seg = flat(APPLY[i:i + 1400])
        self.assertRegex(seg, r"`job-resume.md` 2.6 那一整节")
        self.assertRegex(seg, r"存在的目的就是把它做出来")

    def test_it_points_at_the_reply_variant(self):
        i = APPLY.index("对方先来找你")
        self.assertIn("对方先开口时怎么写", APPLY[i:i + 1500])


class TheReplyVariantExists(unittest.TestCase):
    def _seg(self) -> str:
        i = TPL.index("### 对方先开口时怎么写")
        return TPL[i:i + 2200]

    def test_only_the_first_line_changes(self):
        """2、3 和全部禁语照旧 —— 不说这句，读者会以为要另写一套。"""
        seg = flat(self._seg())
        self.assertRegex(seg, r"只有第 1 项换掉，2、3 和全部禁语照旧")

    def test_it_answers_them_before_pitching(self):
        seg = self._seg()
        self.assertIn("先回他问的那件事", seg)
        self.assertIn("再接最硬的匹配点", seg)

    def test_the_salutation_still_stays(self):
        self.assertIn("「您好，」", self._seg())

    def test_it_bans_the_double_mistake(self):
        seg = flat(self._seg())
        self.assertRegex(seg, r"「看到这个岗」这类话在这里是双重错误")
        self.assertRegex(seg, r"\*\*那是他发给你的\*\*")

    def test_it_bans_the_thank_you_opener(self):
        """「谢谢关注」占的是匹配点的位置 —— 这是回信版最容易长出来的东西。"""
        seg = flat(self._seg())
        self.assertRegex(seg, r"别把它写成感谢信")
        self.assertRegex(seg, r"「谢谢关注」")

    def test_the_pay_rule_still_holds_even_when_asked(self):
        """对面先问了薪资，也不在这 200 字里报 —— 那两个数留到第二轮。"""
        seg = flat(self._seg())
        self.assertRegex(seg, r"即便他先问了也一样")
        self.assertRegex(seg, r"留到第二轮")

    def test_it_carries_the_measurement_with_a_date(self):
        seg = flat(self._seg())
        self.assertIn("开场铺垫", seg)


class TheEntryPointIsNamed(unittest.TestCase):
    def test_the_index_says_where_to_paste_it(self):
        row = next(l for l in INDEX.splitlines()
                   if l.startswith("| 深评一个岗"))
        self.assertIn("整段职位描述", row)
        self.assertIn("猎头/HR 主动来找你时", row)

    def test_the_paste_form_still_exists_in_the_workflow(self):
        """索引说得再好，正文得真收得下一段粘贴进来的 JD。"""
        self.assertIn("抓不到时请用户改为粘贴全文", APPLY)


class TheHeaderRecordsWhichVariantItIs(unittest.TestCase):
    """抬头不记这一笔，打开文件的人分不清是照回信版写的、还是把规则写漏了。

    **默认不写。** 自己找到再发过去的是常态，全部要求标一遍等于凭空造出
    两百多条待办（实测活动用户 2026-08-24：236 份产出里 0 份是对方先来的）。
    标记的价值全在稀有。
    """

    def _seg(self) -> str:
        i = TPL.index("有没有对话方，以及是猎头还是 HR 直招")
        return flat(TPL[i:i + 900])

    def test_the_spec_asks_for_the_marker(self):
        self.assertRegex(
            self._seg(),
            r"\*\*对方先来找你的，在这一行末尾加一句「他先开口」\*\*")

    def test_it_says_the_marker_is_opt_in(self):
        seg = self._seg()
        self.assertRegex(seg, r"\*\*默认不写。\*\*")
        self.assertRegex(seg, r"标记的价值全在稀有")

    def test_it_says_why_the_header_must_carry_it(self):
        self.assertRegex(self._seg(), r"分不清这一份是照回信版写的，还是把规则写漏了")


class TheCheckOnlyFiresOnTheMarkedOnes(unittest.TestCase):
    """存量零噪音 —— 一条新检查上来就报两百条，整个审计会被略过。"""

    def _run(self, head, greeting):
        import sys as _s, tempfile
        _s.path.insert(0, str(ROOT / "tools"))
        import audit_pipeline as ap
        old = ap.ROOT
        try:
            with tempfile.TemporaryDirectory() as t:
                r = pathlib.Path(t)
                d = r / "users" / "甲" / "documents" / "applications" / "某公司_某岗"
                d.mkdir(parents=True)
                (d / "outreach.md").write_text(chr(10).join([
                    "# 投递话术：某公司 - 某岗", "",
                    head,
                    "- 评分：72 分",
                    "- 职位链接：https://example.com/1", "",
                    "## 打招呼开场白", "",
                    greeting, ""]), encoding="utf-8")
                (r / "users" / "甲" / "profile").mkdir(parents=True)
                (r / "users" / "甲" / "profile" / "candidate.md").write_text(
                    "x", encoding="utf-8")
                (r / ".active_user").write_text("甲", encoding="utf-8")
                ap.ROOT = r
                return [t2 for _l, t2, _b in
                        ap.check_outreach_header_says_who_youre_talking_to({}, {})]
        finally:
            ap.ROOT = old

    TITLE = "对方先来找你的那几份，开场白还是「看到这个岗」"
    IN = "- 渠道判定：**有对话方 · 聊天框（猎头 · 他先开口）**"
    OUT = "- 渠道判定：**有对话方 · 聊天框（猎头）**"

    def test_it_catches_the_echo(self):
        self.assertIn(self.TITLE, self._run(self.IN, "您好，看到这个岗。我做过 X。"))

    def test_it_catches_the_thank_you_opener(self):
        """「谢谢关注」不在那五类禁语里 —— 只有回信这个场景里它才是错的。"""
        self.assertIn(self.TITLE, self._run(self.IN, "您好，谢谢关注。我做过 X。"))

    def test_a_correct_reply_passes(self):
        self.assertNotIn(self.TITLE,
                         self._run(self.IN, "您好，在看的。Agent 平台我天天在做。"))

    def test_it_stays_silent_on_the_outbound_ones(self):
        """你先开口的那份写「看到这个岗」也是错的，但那归五类禁语管 ——
        两条检查报同一件事，用户会以为有两个问题。"""
        self.assertNotIn(self.TITLE,
                         self._run(self.OUT, "您好，看到这个岗。我做过 X。"))

    def test_the_real_corpus_is_silent(self):
        """存量 236 份一份都不该报 —— 报了就说明标记判据写宽了。"""
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        import sys as _s
        _s.path.insert(0, str(ROOT / "tools"))
        import audit_pipeline as ap
        apps = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
                / "documents" / "applications")
        if not apps.is_dir():
            self.skipTest("没有语料")
        marked = [f for f in apps.glob("*/outreach.md")
                  if "他先开口" in ap._head_of(
                      f.read_text(encoding="utf-8", errors="replace"))]
        self.assertEqual(marked, [], "存量里出现了带标记的产出 —— 那这条断言要重写")


class TheOtherHalfOfTheLoopIsStillThere(unittest.TestCase):
    """这次改动的前提是 2.6 那一节还在做「让人来找你」这件事。"""

    def test_the_online_resume_section_survives(self):
        self.assertIn("### 2.6 在线简历：HR 主动搜的是它，不是你投出去的 PDF", RESUME)

    def test_it_still_says_hr_searches_the_database(self):
        self.assertRegex(flat(RESUME), r"HR 有很大一部分工作是\*\*反过来的\*\*")

    def test_refresh_is_still_the_daily_one(self):
        self.assertIn("这是这张表里唯一一件**每天都要做**的事", RESUME)


class TheOutboundRulesAreUntouched(unittest.TestCase):
    def test_the_original_structure_table_survives(self):
        self.assertIn("| 1 | **「您好，」+ 最硬的匹配点** | 中间不许有任何别的东西 |", TPL)

    def test_the_two_hundred_cap_survives(self):
        self.assertIn("**硬约束：≤200 字。**", TPL)

    def test_the_five_bans_survive(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        self.assertEqual(len(_cli.GREETING_BANS), 5)
        self.assertIn("开场铺垫", _cli.GREETING_BANS)

    #: 这条守卫写下时的命令总数是 20。**这个数是个绊线，不是上限** ——
    #: 它拦的是「顺手加一个入口」，不是「永远不许有新命令」。
    #: 每加一条都要在这里改数并写清是谁定的：
    #:   21 ← 2026-09-01 加 `/job-refresh`（在线简历刷新）。本人明确要求
    #:        （原话「那你应该有个专门用于刷新建立的命令，每天刷新一次。
    #:        该命令是单独的，auto也会包括它」）。它有自己的动作、自己的账本
    #:        （`tools/resume_refresh.py`）和自己的一天一次节律，
    #:        不是「只换第一句话」那一类。
    COMMAND_COUNT = 21

    def test_no_new_command_was_invented(self):
        """一条只换第一句话的流程不值一个新入口 —— 命令数不许因此涨。

        **真正的判据是下面那三个名字**：`job-reply` / `job-inbound` /
        `job-respond` 一旦出现，就说明「猎头主动来找你」被做成了独立命令，
        而它本该只是 `/job-apply` 的一种输入。上面那个总数只是绊线。
        """
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import export_web_data as ex
        names = {it["name"] for g in ex.parse_commands() for it in g["items"]}
        self.assertEqual(len(names), self.COMMAND_COUNT,
                         f"命令变成 {len(names)} 条了 —— 新加的那条是谁定的？"
                         f"在 COMMAND_COUNT 上面记一行再改这个数")
        for bad in ("job-reply", "job-inbound", "job-respond"):
            self.assertNotIn(bad, names)


if __name__ == "__main__":
    unittest.main()
