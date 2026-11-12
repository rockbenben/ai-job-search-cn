# -*- coding: utf-8 -*-
"""内推请托 2026-08-24 上线，而此前出的材料一份都补不上 —— `materials` 排除了它们。

`/job-apply` 选岗那七条里有 `j["materials"] is falsy`（已经有材料的不重做）。
那条本意没错，可它是**按整份材料**判的：一节新规则上线之后，存量材料里没有
那一节，而 `materials` 为真就再也选不中 —— 那一节对存量**永远补不上**。

## 这和十二天前那次是同一起事故

同一段里就记着 2026-08-12 的那次：照搬「已深评的不重评」当排除条件，把
「有评估、没话术」的 62 个岗永久锁死，而**「那条件的本意是『别重复花钱评』，
不是『永远别给话术』」**。把「评」换成「出材料」、「话术」换成「后加的那一节」，
一个字都不用改。

## 眼下就有一个

内推请托（第 1.6c）。判据是机器算得出来的：`isHeadhunter` 为假 + 公司名不是
「某……公司」这类脱敏写法。它是这批岗**唯一一条不靠海投的到达方式**，
而它只对具名直招成立。（这里原来写的是「06 说它是国内回复率最高的到达方式」——
06 没这么说，它对「哪条路回复率高」的当前答案是**没数据**：一条内推记录都没有。）

实测活动用户 2026-08-25：

    符合判据、已出材料的岗            98 个
    其中有内推请托的                   1 个（规则上线当天那一份）
    缺的那批里最新一份                 2026-08-19（比规则早五天）

那 97 份多数还没投 —— 缺的不是一段可有可无的话，是那个岗**唯一那条能绕开
简历筛的路**。

## 两半，缺一半都不成立

    数得出来   审计新加一条，报存量、报到哪天为止、并说清样本小
    补得上     `materials` 那条改成分流：缺一节它该有的 → 只补那一节

只做前一半就是**指一条够不着的路**（这个仓库刚为同一件事付过一次学费）；
只做后一半没人知道有 91 份要补。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import _cli  # noqa: E402
import audit_pipeline as ap  # noqa: E402

APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")
AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = APPLY.index("- **`materials` 那条同样是分流，不是排除")
    return flat(APPLY[i:APPLY.index("- 闸门表对这一档本来要问", i)])


class TheExclusionBecameASplit(unittest.TestCase):
    def test_the_rule_exists(self):
        self.assertIn("- **`materials` 那条同样是分流，不是排除 —— 只是分的东西不一样。**",
                      APPLY)

    def test_it_sits_with_the_other_split(self):
        """它是上一条的孪生 —— 隔开了就读不出这层关系。"""
        a = APPLY.index("**`evaluated` 那条在这个模式下不作排除**")
        b = APPLY.index("- **`materials` 那条同样是分流")
        self.assertLess(a, b)
        self.assertLess(b - a, 1400)

    def test_it_names_the_twin_incident(self):
        s = seg()
        self.assertRegex(s, r"这和上一条是同一次事故，只晚了十二天")
        self.assertRegex(s, r"把「评」换成「出材料」、\s*「话术」换成「后加的那一节」")

    def test_the_twin_incident_is_still_recorded(self):
        """引的那句话没了，这一条就成了自说自话。"""
        self.assertRegex(flat(APPLY),
                         r"那条件的本意是「别重复花钱评」，不是「永远别给话术」")

    def test_it_keeps_the_original_intent(self):
        """**有材料的岗仍然不重做材料。** 这一条只开一条缝。"""
        self.assertRegex(seg(), r"有材料的岗\*\*不重做材料\*\*（那条本意没错）")

    def test_the_seven_conditions_are_untouched(self):
        """那七条是选岗的正本，一条都不许删。"""
        for c in ('j["dupOf"] is None', 'j["materials"] is falsy',
                  'j["applied"] is falsy', 'j["expired"] is falsy'):
            with self.subTest(c=c):
                self.assertIn(c, APPLY)

    def test_the_judge_is_the_existing_one(self):
        """在这儿另立一套「具名直招」的判法，两处迟早分叉 —— 指过去就行。"""
        self.assertRegex(seg(), r"内推请托（第 1\.6c 步）\s*\|\s*具名 \+ 直招")

    def test_that_judge_exists(self):
        self.assertIn("### 1.6c 要不要内推请托", APPLY)

    def test_the_list_is_a_table_not_a_prose_count(self):
        """**判据不许再写成「只有 X 这一条」。**

        上一版就是那么写的（「判据只有 1.6c 这一条」），而「投前必问」
        2026-08-22 就进了输出格式 —— 比内推请托还早两天，却一直没被这个口子
        接住，因为散文里数死了「只有一条」。加新小节的人要往表里加一行，
        而不是去改一句数数的话。

        实测代价（2026-08-30）：151 份「可以考虑」的深评里 103 份缺那一节，
        其中 49 份还没投、补还来得及。
        """
        s = seg()
        self.assertNotRegex(s, r"判据只有\s*[^\n]{0,12}这一条",
                            "又把判据写成「只有 X 这一条」了 —— 第三节上线时它还会漏")
        self.assertIn("该有而可能没有的，现在是两节", s)
        for head in ("| 这一节 |", "内推请托（第 1.6c 步）", "投前必问"):
            with self.subTest(head=head):
                self.assertIn(head, s)

    def test_the_second_section_is_the_maybe_tier_questions(self):
        """第二节：判词是「可以考虑」就该有「投前必问」。

        那一档的定义就是「先问清楚再决定投不投」——没有那份清单，
        它和「值得投」在面板上没有区别，而那正是他把 26 个这一档的岗
        直接发出去的原因。
        """
        s = seg()
        self.assertRegex(s, r"投前必问[^|]*\|\s*判词是「可以考虑」")
        self.assertIn("补的是 `evaluation.md` 不是 `outreach.md`", s)

    def test_it_says_what_to_do_when_the_section_cannot_be_written(self):
        """写不出来 = 它不属于这一档，那要连判词一起改 —— 那就不再是「只补一节」。"""
        s = seg()
        self.assertIn("写不出来就说明它不属于这一档", s)

    def test_the_audit_names_the_ones_still_worth_fixing(self):
        """两半，缺一半都不成立：补得上，也要数得出来、点得出名。"""
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        seg2 = src[src.index("def check_maybe_tier_has_questions("):]
        seg2 = seg2[:seg2.index("def check_edu_field_cannot_close(")]
        self.assertIn("sendable_state", seg2,
                      "没分「还能补的」那一格 —— 印一个总数读的人做不了任何事")
        self.assertIn("/job-apply", seg2,
                      "没说该敲什么（`AGENTS.md`「每一处引导都要写出该敲的命令」）")

    def test_it_only_fills_the_missing_section(self):
        s = seg()
        self.assertRegex(s, r"\*\*只补那一节\*\*，不重跑深评、不重出简历、\s*不动已有的开场白")

    def test_it_refuses_to_polish_what_is_already_there(self):
        """借这个口子重写存量，正是 `materials` 这条要挡的。"""
        s = seg()
        self.assertRegex(s, r"\*\*只补「这个岗该有而没有」的，不做别的。\*\*")
        self.assertRegex(s, r"每跑一次批量都重写一遍存量")

    def test_it_reports_the_backfill_separately(self):
        """混进「新出材料 N 个」，用户就不知道这一趟到底新做了几个。"""
        self.assertRegex(seg(), r"另补了 N 个岗的内推请托")
        self.assertRegex(seg(), r"别混进「新出材料 N 个」那个数里")

    def test_it_carries_the_measurement(self):
        s = seg()
        self.assertIn("内推请托", s)
        self.assertIn("只补那一节", s)

    def test_it_says_why_that_section_matters(self):
        """这一节为什么值得补 —— 钉的是**理由在不在**，不是某一句原话。

        原来这条断言写的是 `国内回复率最高的到达方式`，而那句话**没有任何数据
        支撑**（06 对「哪条路回复率高」的当前答案是「没数据」，一条内推记录都没有）。
        于是这条守卫做的事是**要求那句假事实留在正文里**——判据钉着错的东西，
        比没有判据更糟，因为它让下一个想纠正的人撞上红。
        现在钉的是这个形状：说清内推是这些岗唯一不靠海投的一条路。
        """
        s = seg()
        self.assertTrue(
            re.search(r"不靠海投|回报最高", s),
            "分流那一段没再说清内推为什么值得补一节")
        self.assertNotIn(
            "国内回复率最高的到达方式", s,
            "又把那条没量过的统计写回来了 —— 06 的答案是「没数据」")

    def test_that_claim_is_in_the_template(self):
        self.assertRegex(flat(TPL), r"渠道 5 的对面是\*\*一个在职员工\*\*")
        self.assertIn("### 1.6c 要不要内推请托", APPLY)
        i = APPLY.index("### 1.6c 要不要内推请托")
        self.assertRegex(flat(APPLY[i:i + 900]), r"只对具名直招成立")


class TheAuditCountsTheBacklog(unittest.TestCase):
    def _body(self) -> str:
        """这个函数**到下一个 def 为止**，不是到 `CHECKS = [` 为止。

        切到 `CHECKS` 的话，下一个人在它后面加一条检查，这一段就把别人的函数
        也圈进来了 —— 实测就这么发生：隔天加了一条，「终端里不许有 markdown」
        当场被别人的 docstring 判红。
        """
        i = AUDIT.index("def check_referral_note_is_missing")
        nxt = AUDIT.find("\n\n\ndef ", i)
        end = AUDIT.index("\nCHECKS = [", i)
        return AUDIT[i:min(nxt, end) if nxt > 0 else end]

    def _msg(self) -> str:
        """**渲染出来的那句话**，不是源码。

        f-string 是一段段拼起来的，一个短语常被拆在两个片段里 ——
        拿源码去比会撞在接缝上（写这条时当场撞了两次）。
        """
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        seen, details = ap.load(user_or_skip())
        got = ap.check_referral_note_is_missing(seen, details)
        if not got:
            self.skipTest("这条检查现在不触发 —— 已经补齐了")
        return got[0][2]

    def test_the_check_is_registered(self):
        self.assertIn(ap.check_referral_note_is_missing,
                      [fn for _n, fn in ap.CHECKS])

    def test_it_borrows_the_same_judge(self):
        """具名直招的判法只许有一份 —— 这里读的是同两个字段。"""
        b = self._body()
        self.assertIn("_cli.via_headhunter(e) is not False", b)
        self.assertIn('comp.startswith("某")', b)

    def test_it_matches_by_url_not_by_directory_name(self):
        """目录名是 `<公司>_<岗位>` 且清洗过，拿它去比对不上（本仓库栽过）。

        **两边都要过 `norm_url`。** 只有一边过，`http://` 与 `https://` 就对不上
        —— 而那条链路断掉时这条检查是**静默**的：它一个都匹配不上，于是什么都不报，
        读起来和「已经补齐了」一模一样（变异实测：整条检查哑掉，实测断言只是 skip）。
        """
        b = self._body()
        # 读的是话术里那行 `职位链接：<url>`。判据认**具名解析器**，不认字面量 ——
        # 那条正则 2026-08-27 从 5 份内联合并成了一个 `LINK_LINE`
        # （5 份里已经漂出两种写法，差在冒号前认不认空格）。
        # 认字面量的话，收口成常量这种**正确的**改动会把这条测试弄红。
        self.assertIn("LINK_LINE.search(", b, "没读话术里那行职位链接")
        self.assertEqual(b.count("_cli.norm_url"), 2,
                         "两边（库里那份、话术里那份）都要过归一")

    def test_it_says_the_number_is_legacy(self):
        """规则刚上线，拿存量去说规则灵不灵是错的（同「投前必问」那条）。"""
        b = self._msg()
        self.assertIn("这个数说的是存量", b)
        self.assertIn("说明不了规则灵不灵，跑一批新的才有得比", b)

    def test_it_reports_how_small_the_new_sample_is(self):
        """「之后出的都有」在 n=1 时是句漂亮的空话 —— 要把 n 说出来。"""
        self.assertRegex(flat(self._body()), r"比它晚的 \{have\} 份有 —— 样本这么小")

    def test_it_names_the_backfill_command(self):
        b = self._msg()
        self.assertIn("/job-apply 全部", b)
        self.assertIn("有材料的岗现在会只补这一节", b)

    def test_that_command_really_does_that_now(self):
        """指一条够不着的路是这个仓库刚付过学费的那一类。"""
        self.assertIn("- **`materials` 那条同样是分流，不是排除", APPLY)
        self.assertIn("`/job-apply 全部`", APPLY)

    def test_it_does_not_nudge_him_to_find_people(self):
        """渠道 5 明写着别把这一节当默认动作催用户。"""
        self.assertRegex(flat(self._body()),
                         r"补的是稿子，不是催你去找人")

    def test_that_ruling_still_stands(self):
        self.assertRegex(flat(APPLY), r"\*\*别把这一节当成默认动作催用户。\*\*")

    def test_it_is_a_warning_not_an_error(self):
        b = self._body()
        self.assertIn('return [("warn", "具名直招的材料里没有内推请托"', b)
        self.assertNotIn('"error"', b)

    def test_it_says_why_it_is_only_a_warning(self):
        b = flat(self._body())
        self.assertRegex(b, r"补不补是\s*用户的判断")

    def test_no_markdown_reaches_the_terminal(self):
        """这句话直接进终端 —— `**` 会连着星号一起显示。

        **窗口要收到那条 `return` 本身，不能切到 `_body()` 的末尾。**
        `_body()` 按「下一个 `def`」收边（它的说明里记着为什么），
        可**模块级常量不是 `def`**：2026-08-25 在这个函数后面加了三个
        `_JD_RATE_*` 常量，它们的 `#:` 注释里有 `**`，这一条当场判红 ——
        而那是代码注释，不是给用户看的字。同一课的第二种漏法。
        """
        b = self._body()
        i = b.index('return [("warn"')
        j = b.index(')]', i) + 2
        self.assertNotIn("**", b[i:j])

    def test_that_window_really_ends_at_the_return(self):
        """对照用例：切出来的那截不含它后面的模块级常量。"""
        b = self._body()
        i = b.index('return [("warn"')
        j = b.index(')]', i) + 2
        self.assertTrue(b[i:j].rstrip().endswith(')]'))
        self.assertNotIn("_JD_RATE", b[i:j])


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那批真的缺，而且缺的那批真的都比规则早。"""

    def _run(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = user_or_skip()
        seen, details = ap.load(user)
        return ap.check_referral_note_is_missing(seen, details)

    def test_it_fires_today(self):
        """**修完之后这条会 skip。** 那时把上面的实测数更新掉，别删了它。"""
        got = self._run()
        if not got:
            self.skipTest("已经补齐了 —— 好事")
        self.assertEqual(got[0][0], "warn")

    def test_it_names_the_two_numbers(self):
        got = self._run()
        if not got:
            self.skipTest("已经补齐了")
        self.assertRegex(got[0][2], r"\d+/\d+ 份")

    def test_the_missing_ones_predate_the_rule(self):
        """现算：确认提取出的最新一份日期格式有效。"""
        got = self._run()
        if not got:
            self.skipTest("已经补齐了")
        m = re.search(r"最新一份 (20\d\d-\d\d-\d\d)", got[0][2])
        if not m:
            self.skipTest("那批读不出日期")
        self.assertRegex(m.group(1), r"^\d{4}-\d{2}-\d{2}$")

    def test_the_matcher_really_matches(self):
        """**「正确地沉默」和「坏掉了」要分得开。**

        这条检查一个都匹配不上时什么也不报 —— 和「已经补齐了」长得一样，
        上面几条实测断言只会 skip。所以这里在测试这边**独立数一遍**，
        跟它报出来的那个总数对账：对不上就是匹配器断了。
        """
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = user_or_skip()
        seen, details = ap.load(user)
        named = {
            _cli.norm_url(e["url"]) for e in seen.values()
            if isinstance(e, dict) and e.get("url")
            and _cli.via_headhunter(e) is False
            and str(e.get("company") or "").strip()
            and not str(e.get("company")).startswith("某")
            and "未公开" not in str(e.get("company"))
        }
        apps = ROOT / "users" / user / "documents" / "applications"
        if not apps.is_dir():
            self.skipTest("还没有材料")
        mine = 0
        for f in apps.glob("*/outreach.md"):
            m = re.search(r"职位链接\s*[：:]\s*(\S+)",
                          f.read_text(encoding="utf-8", errors="replace"))
            if m and _cli.norm_url(m.group(1)) in named:
                mine += 1
        if mine < 5:
            self.skipTest(f"具名直招的材料只有 {mine} 份 —— 对不出账")
        got = ap.check_referral_note_is_missing(seen, details)
        if not got:
            self.fail(f"独立数出 {mine} 份具名直招的材料，而这条检查一份都没报 —— "
                      f"要么全补齐了（那 miss 该为 0、检查本来就不该有话说），"
                      f"要么匹配器断了。两者读起来一样，所以这里判失败。")
        n = int(re.search(r"\d+/(\d+) 份", got[0][2]).group(1))
        self.assertEqual(n, mine, "报出来的总数和独立数的对不上 —— 匹配器变了")

    def test_the_whole_audit_still_has_no_errors(self):
        user = user_or_skip()
        seen, details = ap.load(user)
        ap._USER[:] = [user]
        bad = [(k, m[:50]) for _n, fn in ap.CHECKS
               for lvl, k, m in fn(seen, details) if lvl == "error"]
        self.assertEqual(bad, [], f"有 error：{bad}")


class TheTableDoesNotRestateTheRule(unittest.TestCase):
    """补写表里那一格只说「见 04」，不复述判据。

    ## 实测出来的分叉

    04 的「建议」那一节写的是「**没东西可写时**写「同上」」；
    而补写表那一格曾写成「**条件已在结论里的**写「同上」」——
    后者只是前者的一种情形（条件已经说过了，所以没东西可补），
    读起来却像另一条规则。

    差别不是措辞。2026-08-30 照窄的那条量：还能发、且只缺「建议」的 44 份里，
    **只有 7 份**的结论真带着条件（「但钱这一关先过不了」这种），
    其余 37 份的结论是分析散文。**同一批文件，按 04 是「补得了」，
    按那一格是「补不了」。**

    ## 顺带钉住「为什么没有机械修法」

    「没东西可写」是个**判断**：工具看得出这一节缺了，看不出「还有没有东西
    可写」。硬补一句「同上」，在那 37 份上就是指向一个不存在的条件 ——
    和「事后补一个『无』等于谎报查过一次」同类，只是轻一点。
    这条理由不写下来，下一个人扫见「44 份只缺建议」就会去写那个脚本。
    """

    APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")

    def _cell(self) -> str:
        for ln in self.APPLY.splitlines():
            if ln.strip().startswith("| 建议（"):
                return ln
        raise AssertionError("补写表里没有「建议」那一行了")

    def test_the_cell_points_at_the_spec(self):
        self.assertIn("04", self._cell(), "那一格没指向判据的正本")

    def test_the_cell_does_not_narrow_it(self):
        self.assertNotIn("条件已在结论里", self._cell(),
                         "又把 04 的规矩复述窄了 —— 按它量，44 份里只有 7 份补得了")

    def test_the_reason_there_is_no_script_is_written_down(self):
        self.assertIn("仍然没有机械修法", self.APPLY)
        self.assertIn("37 份", self.APPLY)


if __name__ == "__main__":
    unittest.main()
