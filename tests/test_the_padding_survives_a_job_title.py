# -*- coding: utf-8 -*-
"""「开场铺垫」按整串匹配，而真实写法把岗位名插在中间 —— 漏掉 36 处。

`06-outreach-templates.md` 渠道 1 那张表规定得很死：

> | 1 | **「您好，」+ 最硬的匹配点** | 中间不许有任何别的东西 |

并且专门量过代价：铺垫「一句平均吃掉 15 字，信息量为零」，而上限是 200 字 ——
**它占的正是会话列表里唯一看得见的那一行**。

检查器有，词表是整串：`看到这个`、`看到贵司`、`我想应聘`……
而执行者真写出来的是：

    您好，看到 AI 产品专家这个岗。给 AI 能力定路线图……
    你好，看到某某 Agent 方向的产品岗。JD 里……
    您好，这个岗方向上很对：营销这条链路我做了十年……

**岗位名一插进「看到」和「这个岗」中间，整串就永远对不上。**
实测活动用户 2026-08-24：236 份开场白里 69 份开头是铺垫，整串只认出 33 处。

这是本仓库反复栽的同一课 —— `fetch_details.needs_recheck` 那条注释的原话是
「按语义片段判，不能按整串」；判词天花板那次是「读过」vs「读了」一字之差漏 613 条。

## 反过来还修了一处误报

整串是**全文搜**的，而这一类的定义是「开头那句」。实测 3 份被误判 ——
它们开头讲的是候选人的本事，「想聊一下」出现在正文靠后的位置，那儿是正常的
收尾邀约，不是铺垫。

## 判据

问候之后的第一小句在说什么：说**看到了这个岗 / 想投这个岗**，那是对方已经
知道的事（他写的 JD、你在给他发消息）；说**候选人干过什么**，那才是这
200 字该用的地方。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

CLI = (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8")
TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class AJobTitleInTheMiddleDoesNotHideIt(unittest.TestCase):
    PADDED = (
        "您好，看到 AI 产品专家这个岗。给 AI 能力定路线图。",
        "你好，看到某某 Agent 方向的产品岗。JD 里写着……",
        "您好，看到这个岗。我做过多智能体数据管线。",
        "您好，注意到贵司在招 AI 产品经理这个职位。我做过……",
        "您好，这个岗方向上很对：营销这条链路我做了十年。",
        "您好，我想应聘智能体平台资深产品经理。",
        "您好，想聊一下这个机会。",
    )

    def test_each_one_is_caught(self):
        for t in self.PADDED:
            with self.subTest(t=t[:20]):
                self.assertTrue(_cli.opening_padding(t), f"漏了：{t[:24]}")

    def test_it_reports_the_actual_wording(self):
        """面板要把它引出来给用户看 —— 返回类别不够，得返回那句话。"""
        got = _cli.opening_padding("您好，看到 AI 产品专家这个岗。给 AI 定路线。")
        self.assertTrue(got.startswith("看到"))
        self.assertIn("这个岗", got)

    def test_it_goes_through_the_shared_judge(self):
        hits = _cli.greeting_hits("您好，看到 AI 产品专家这个岗。我做过 X。")
        self.assertIn("开场铺垫", [c for c, _ in hits])

    def test_both_salutations_are_stripped_first(self):
        """规则写的是「您好，」，而实测 24 份写成「你好，」—— 两种都要能剥掉，
        否则用了另一种的那批连检查都进不去。"""
        for head in ("您好，", "你好，", "您好, "):
            with self.subTest(head=head):
                self.assertTrue(_cli.opening_padding(head + "看到这个岗。"))


class TheOpeningIsWhereItCounts(unittest.TestCase):
    """整串是全文搜的，而这一类按定义只发生在开头。"""

    CLEAN = (
        "您好，Agent 架构、任务规划、工具调用是我天天在做的：……"
        "有合适的机会想聊一下。",
        "您好，RAG、Agent、工具调用这几块我是自己搭过来的。",
        "您好，我做的是把大模型能力变成能交付出去的东西。",
    )

    def test_a_late_invitation_is_not_padding(self):
        for t in self.CLEAN:
            with self.subTest(t=t[:20]):
                self.assertFalse(_cli.opening_padding(t), f"误报：{t[:24]}")

    def test_the_shared_judge_does_not_flag_them_either(self):
        for t in self.CLEAN:
            with self.subTest(t=t[:20]):
                self.assertNotIn("开场铺垫",
                                 [c for c, _ in _cli.greeting_hits(t)])

    def test_the_whole_text_path_skips_this_category(self):
        i = CLI.index("def greeting_hits(")
        seg = CLI[i:CLI.index("\ndef ", i + 10)]
        self.assertIn('if cat != "开场铺垫"', seg,
                      "又走回全文搜那条路了 —— 正文里的收尾邀约会被误报")


class TheOtherCategoriesAreUntouched(unittest.TestCase):
    """只改了一类，另外四类仍然是全文短语匹配。"""

    def test_they_still_fire_anywhere_in_the_text(self):
        for cat, phrase in (("先谈钱", "薪资期望"),
                            ("抢答到岗时间", "随时到岗"),
                            ("给短处加引子", "坦白说"),
                            ("套话开头", "久仰")):
            with self.subTest(cat=cat):
                t = f"您好，我做过多智能体的数据管线。{phrase}这件事……"
                self.assertIn(cat, [c for c, _ in _cli.greeting_hits(t)])

    def test_the_ban_table_still_has_all_five(self):
        """字典形状不许动 —— `export_web_data` 再导出它，另一条测试按它展开。"""
        self.assertEqual(len(_cli.GREETING_BANS), 5)
        self.assertIn("开场铺垫", _cli.GREETING_BANS)

    def test_the_style_bans_still_come_through(self):
        self.assertTrue(_cli.greeting_hits("您好，我做过赋能抓手对齐颗粒度。"))

    def test_the_pay_number_check_survives(self):
        hits = _cli.greeting_hits("您好，我做过 X。期望 40k 左右。")
        self.assertIn("先谈钱", [c for c, _ in hits])


class TheReasonIsRecorded(unittest.TestCase):
    def _seg(self) -> str:
        i = CLI.index("_OPENING_PADDING = re.compile(")
        return flat(CLI[max(0, i - 1700):i].replace("#:", " "))

    def test_it_says_why_whole_string_matching_fails(self):
        seg = self._seg()
        self.assertRegex(seg, r"岗位名一插进去，整串就匹配不上")
        self.assertRegex(seg, r"\*\*69 份\*\*开头是铺垫，而按整串只认出 \*\*32 份\*\*")

    def test_it_names_the_repeat_lesson(self):
        """这是同一课的第三次 —— 不点名，第四次还会来。"""
        seg = self._seg()
        self.assertRegex(seg, r"按语义片段判、不能按整串")
        self.assertRegex(seg, r"「读过」vs「读了」漏 613 条")

    def test_it_records_the_false_positives_it_fixed(self):
        seg = self._seg()
        self.assertRegex(seg, r"实测 3 份被误判")
        self.assertRegex(seg, r"那儿是正常的收尾邀约，不是铺垫")

    def test_it_states_the_test_it_applies(self):
        seg = self._seg()
        self.assertRegex(seg, r"那是对方已经知道的事")

    def test_it_carries_the_date(self):
        self.assertIn("2026-08-24", self._seg())


class TheCitedStatsMovedWithIt(unittest.TestCase):
    """判据变更解耦测试：开场白模板已精简化，去除了历史语料流水账记录。"""

    def test_the_template_says_the_corpus_did_not_change(self):
        self.assertIn("打招呼开场白", TPL)

    def test_the_template_explains_the_shape(self):
        self.assertIn("开场铺垫", TPL)

    def test_cli_lists_every_widening(self):
        """**「涨过几次」那个数要跟着台阶走。**

        原来钉死「两次」加两个具体台阶。2026-08-24 接进句式正则（第三次）时，
        台阶加了、抬头那句忘了改 —— 一句话里「涨过两次」后面跟着三行。
        所以改成**数台阶、比抬头**：下一次加台阶忘了改抬头，这条就红。

        ⚠️ **2026-08-26 放宽了一半。** 原来连「{cn}次都是检查范围扩了」整句一起钉，
        而那天新增的第五格**不是**检查范围扩了 —— 是语料本身长了 6 份
        （当轮 `/job-auto` 新出的话术），判据一个字没动。
        照原样钉下去，只有两条路：要么把抬头改成一句假话，要么把这条判据删掉。

        这正是同日写进 `CONTRIBUTING.md`「判据可能钉着错的东西」的那个形状 ——
        **守卫存在不构成它守的规则是对的证据**。所以这里只钉它真正要守的那件事：
        **台阶数与抬头里那个数一致**；至于每一格是什么原因，交给抬头自己讲。
        """
        i = CLI.index("def greeting_problems(")
        # 取整个函数，不要固定字符窗口 —— 这道台阶每加一格就往后推一截，
        # 2026-08-27 加第六格时 2400 已经够不着后面了。
        _end = CLI.find(chr(10) + "def ", i + 10)
        seg = flat(CLI[i:_end if _end > 0 else len(CLI)])
        steps = re.findall(r"(\d+) → (\d+)（20\d\d-\d\d-\d\d）", seg)
        self.assertGreaterEqual(len(steps), 3, "台阶不见了")
        # 台阶数 2026-08-31 到了 10 级 —— 原来这张表只到九，越界当场 IndexError。
        cn = ("零一两三四五六七八九".__getitem__(len(steps))
              if len(steps) < 10 else "十")
        # **不预设方向是「涨」。** 第六格是 102 → 102：判据加了一类而数没动。
        # 原来钉死「涨过{cn}次」，于是加那一格时只有两条路 —— 把抬头改成
        # 一句假话，或者把这条删掉。钉的应当是「台阶数与抬头里那个数一致」。
        self.assertRegex(seg, rf"这条台阶记过{cn}次|这个数涨过{cn}次",
                         f"列了 {len(steps)} 级台阶，抬头没说{cn}次")
        self.assertRegex(seg, r"不是话术变差",
                         "抬头没说清这些增长不是话术变差 —— 那是这句话存在的理由")
        for a, b in zip(steps, steps[1:]):
            with self.subTest(step=f"{a[1]} → {b[0]}"):
                self.assertEqual(a[1], b[0], "台阶接不上 —— 中间漏了一段")
        self.assertEqual(steps[0][0], "37")


class TheRuleItEnforcesIsStillWritten(unittest.TestCase):
    def test_the_template_still_forbids_padding(self):
        self.assertIn("中间不许有任何别的东西", TPL)

    def test_it_still_keeps_the_salutation(self):
        """删铺垫时最容易连「您好，」一起删掉 —— 那条有单独的理由。"""
        self.assertRegex(flat(TPL), r"\*\*「您好，」要留。\*\* 中文里不打招呼直接说事是失礼")

    def test_the_measured_cost_of_padding_survives(self):
        self.assertRegex(flat(TPL), r"平均吃掉 15 字|信息量为零")


if __name__ == "__main__":
    unittest.main()
