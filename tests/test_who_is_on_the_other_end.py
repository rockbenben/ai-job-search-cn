# -*- coding: utf-8 -*-
"""渠道判定只有两档，而平台每张卡片都说得出第三档。

`06-outreach-templates.md` 的「渠道判定」原来分猎头和 HR 直招，判据是
`isHeadhunter` 一个字段。可猎聘搜索接口**每张卡片都带着招聘者职务**
（`recruiterTitle`）——实测样本 42 张卡片：

    猎头顾问          16
    HR 那一侧         16   （HR / HRBP / 人事经理 / 人力资源专员 …）
    **用人方本人**      4   （研发总监、运营经理、商务主管、法人）
    职务认不出          6   （空着 5 张，还有 1 张写着四个乱码字母）

直招里认得出职务的 20 张，**五分之一对面根本不是 HR**。

这在国内不是细微差别：HR 筛的是硬条件与稳定性，而用人方老大关心的是
「你能不能干活」，**他当场就能拍板**。对着他讲职业规划与稳定性，
是把唯一一次直达决策人的机会说成了 HR 面。

## 这个字段此前被整个否掉过

`cdp-portals.md` 那张表里写着它「既当不了外包硬门要的招聘主体名称，也当不了
跟进消息里的称呼」—— **两句都对**（它是角色标签不是人名，同一个「猎头顾问」
挂在十几个不同招聘者身上）。但「当不了人名」不等于没用：它回答的是另一个问题。
**一个字段按一种用途否掉之后就没人再看它**，是这个仓库反复踩的形状。

## 顺带修的：1.5b 一直在教一条作废了的写法

`job-apply.md` 1.5b 写着「`isHeadhunter: true` → 猎头版：开场白中主动交代
期望薪资区间与求职状态」——而 `06` 明写这条 **2026-08-17 已作废**
（「期望薪资与到岗时间一律不写」），`_cli.GREETING_BANS` 的「先谈钱」
「抢答到岗时间」两类查的就是这两句，审计实测各 4 份、5 份。

**同一件事两个文件两条相反的规矩，执行者读到哪份算哪份。**
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
PORTALS = (ROOT / "workflows" / "reference"
           / "cdp-portals.md").read_text(encoding="utf-8")
FIXTURE = (ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "tests"
           / "fixtures" / "search-response.json")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheJudgeHasThreeAnswersAndOneShrug(unittest.TestCase):

    def test_a_headhunter_wins_regardless_of_title(self):
        """猎头代招先判 —— 顾问的职务写什么都不改变这一点。"""
        for t in ("猎头顾问", "高级顾问", "", "研发总监"):
            with self.subTest(title=t):
                self.assertEqual(_cli.counterpart_of(t, True), "猎头")

    def test_hr_side_titles(self):
        for t in ("HR", "HRBP", "hrbp经理", "HR Assistant Manager", "人事",
                  "人事经理", "人力资源专员", "招聘专员", "招聘经理",
                  "绩效管理主管", "薪酬主管", "行政经理"):
            with self.subTest(title=t):
                self.assertEqual(_cli.counterpart_of(t, False), "HR")

    def test_hr_is_judged_before_the_boss_words(self):
        """**顺序不能换。** 「HR经理」两边都命中，而它当然是 HR。"""
        self.assertEqual(_cli.counterpart_of("HR经理", False), "HR")
        self.assertEqual(_cli.counterpart_of("招聘总监", False), "HR")
        i = _cli.__file__ and (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8")
        self.assertLess(i.index("COUNTERPART_HR = "), i.index("COUNTERPART_BOSS = "),
                        "HR 词表要排在用人方词表前面，注释里那句「判在前面」才成立")

    def test_the_hiring_side_titles(self):
        for t in ("研发总监", "运营经理", "商务主管", "法人", "技术负责人",
                  "CTO", "架构师", "创始人", "合伙人"):
            with self.subTest(title=t):
                self.assertEqual(_cli.counterpart_of(t, False), "用人方")

    def test_garbage_is_not_a_hiring_manager(self):
        """**两边都要命中才下结论。**

        只判「不含 HR 词就算用人方」的话，样本里那张写着四个乱码字母的卡片
        会被说成研发总监同一档，而下一步的话术全按这个走。
        """
        for t in ("sfsf", "。。", "12345", "?"):
            with self.subTest(title=t):
                self.assertEqual(_cli.counterpart_of(t, False), "")

    def test_no_title_is_a_shrug_not_a_guess(self):
        self.assertEqual(_cli.counterpart_of("", False), "")
        self.assertEqual(_cli.counterpart_of(None, False), "")

    def test_it_is_case_insensitive(self):
        self.assertEqual(_cli.counterpart_of("hr assistant", False), "HR")
        self.assertEqual(_cli.counterpart_of("cto", False), "用人方")


class TheThirdBucketIsReal(unittest.TestCase):
    """现算：拿 CLI 那份实测样本跑一遍判据，第三档真的存在。"""

    def _cards(self):
        if not FIXTURE.is_file():
            self.skipTest("没有 CLI 样本")
        out = []

        def find(o):
            if isinstance(o, dict):
                if isinstance(o.get("recruiter"), dict) and isinstance(o.get("job"), dict):
                    out.append(o)
                for v in o.values():
                    find(v)
            elif isinstance(o, list):
                for v in o:
                    find(v)
        find(json.loads(FIXTURE.read_text(encoding="utf-8")))
        if len(out) < 20:
            self.skipTest(f"样本只有 {len(out)} 张，判不出比例")
        return out

    def _split(self):
        got = {}
        for r in self._cards():
            lab = _cli.counterpart_of(
                r["recruiter"].get("recruiterTitle"),
                str(r["job"].get("jobKind")) == "1")
            got[lab] = got.get(lab, 0) + 1
        return got

    def test_the_hiring_side_bucket_is_not_empty(self):
        """**支点。** 一张都没有的话，这一整节没有存在的理由。"""
        got = self._split()
        self.assertGreaterEqual(
            got.get("用人方", 0), 3,
            f"样本里认不出用人方本人了：{got} —— 这一节引的实测数要重看")

    def test_it_is_a_fifth_of_the_direct_ones(self):
        got = self._split()
        direct = got.get("HR", 0) + got.get("用人方", 0)
        self.assertGreater(direct, 10, f"直招样本太小：{got}")
        share = got.get("用人方", 0) * 100 // direct
        self.assertGreaterEqual(
            share, 10,
            f"用人方只占直招的 {share}%，文档里写的「五分之一」过时了：{got}")

    def test_the_shrug_bucket_exists_too(self):
        """认不出的那一档也要真有 —— 没有的话「别猜」那句话没有依据。"""
        self.assertGreater(self._split().get("", 0), 0)

    def test_headhunters_all_land_in_their_own_bucket(self):
        got = self._split()
        self.assertGreater(got.get("猎头", 0), 5, f"猎头那一档空了：{got}")


class TheTableSaysWhatChanges(unittest.TestCase):

    def _seg(self) -> str:
        i = TPL.index("## 渠道判定：猎头 / HR / 用人方本人")
        return TPL[i:TPL.index("\n---", i)]

    def test_the_section_exists(self):
        self.assertIn("## 渠道判定：猎头 / HR / 用人方本人", TPL)

    def test_the_table_has_three_columns(self):
        seg = self._seg()
        header = next(l for l in seg.splitlines() if l.startswith("| | 猎头"))
        self.assertIn("用人方本人", header)

    def test_it_names_the_judge(self):
        self.assertIn("_cli.counterpart_of", self._seg())

    def test_that_judge_exists(self):
        self.assertTrue(callable(_cli.counterpart_of))

    def test_it_says_what_never_to_do_with_a_hiring_manager(self):
        """第三档的价值全在这一句：别把直达决策人的机会说成 HR 面。"""
        seg = flat(self._seg())
        self.assertIn("别讲职业规划与稳定性", seg)
        self.assertIn("他当场就能拍板", seg)

    def test_it_says_the_greeting_layer_is_unchanged(self):
        """开场白这一层三档没有区别 —— 不说清就会有人给第三档另写一版。"""
        self.assertIn("开场白这一层三者没有区别", self._seg())

    def test_the_retired_rule_stays_retired(self):
        seg = flat(self._seg())
        self.assertIn("期望薪资与到岗时间", seg)
        self.assertIn("一律不写", seg)

    def test_an_unreadable_title_falls_back_and_says_so(self):
        seg = flat(self._seg())
        self.assertIn("认不出就是认不出", seg)
        self.assertIn("别猜", seg)

    def test_it_carries_the_measurement(self):
        seg = flat(self._seg())
        self.assertIn("用人方本人", seg)
        self.assertIn("根本不是 HR", seg)

    def test_it_records_why_the_field_was_dismissed_before(self):
        """否掉的理由是对的，错的是「否掉之后再没人看它」—— 两句都要留。"""
        seg = flat(self._seg())
        self.assertIn("两句都对", seg)
        self.assertIn("一个字段按一种用途否掉之后就没人再看它", seg)

    def test_that_dismissal_is_still_in_the_portal_table(self):
        """引的是 `cdp-portals.md` 里的原话 —— 它没了这段就成了无源之谈。"""
        self.assertIn("既当不了外包硬门要的招聘主体名称", PORTALS)


class TheApplyStepUsesIt(unittest.TestCase):

    def _seg(self) -> str:
        i = APPLY.index("### 1.5b 对话方是谁")
        return APPLY[i:APPLY.index("### 1.5c", i)]

    def test_it_calls_the_shared_judge(self):
        self.assertIn("_cli.counterpart_of(recruiterTitle, isHeadhunter)", self._seg())

    def test_it_lists_three_buckets(self):
        seg = self._seg()
        for k in ("猎头", "HR", "用人方"):
            with self.subTest(k=k):
                self.assertIn(f"| **{k}**", seg)

    def test_it_points_at_the_full_table(self):
        self.assertIn("渠道判定：猎头 / HR / 用人方本人", self._seg())

    def test_the_header_line_offers_all_four_answers(self):
        """产出物头部那一行要摆得下「认不出」，否则执行者只能硬填一个。"""
        line = next(l for l in APPLY.splitlines() if l.startswith("- 渠道判定：<"))
        for k in ("猎头", "HR 直招", "用人方本人", "职务认不出"):
            with self.subTest(k=k):
                self.assertIn(k, line)

    def test_step_zero_now_fetches_the_field(self):
        self.assertIn("`isHeadhunter`、`recruiterTitle`、`description` 等字段", APPLY)


class TheRetractedRuleIsGoneFromTheStep(unittest.TestCase):
    """1.5b 教的写法必须和 `_cli.GREETING_BANS` 查的一致。"""

    def _seg(self) -> str:
        i = APPLY.index("### 1.5b 对话方是谁")
        return APPLY[i:APPLY.index("### 1.5c", i)]

    def test_it_no_longer_tells_the_writer_to_state_salary(self):
        seg = self._seg()
        i = seg.index("这段话原来写的是")     # 退休说明里引了原话，那一处是唯一允许的
        self.assertNotIn("主动交代期望薪资区间", seg[:i],
                         "1.5b 还在教「开场白里主动交代期望薪资」—— "
                         "那是 2026-08-17 作废的写法，写了会被审计当场抓")

    def test_the_retraction_is_recorded(self):
        seg = flat(self._seg())
        self.assertIn("2026-08-17", seg)
        self.assertIn("同一件事两个文件两条相反的规矩", seg)

    def test_it_names_the_checker_that_would_catch_it(self):
        self.assertIn("_cli.GREETING_BANS", self._seg())

    def test_those_two_bans_really_exist(self):
        for k in ("先谈钱", "抢答到岗时间"):
            with self.subTest(k=k):
                self.assertIn(k, _cli.GREETING_BANS)

    def test_the_banned_sentence_really_trips_them(self):
        """现算：照旧写法写一句，两条禁令都得命中。否则上面那句因果是空话。"""
        bad = "您好，我已离职、随时到岗，期望 45-60k。"
        cats = {c for c, _w in _cli.greeting_hits(bad)}
        self.assertIn("先谈钱", cats)
        self.assertIn("抢答到岗时间", cats)


class ThePanelSaysItWhereHeCopies(unittest.TestCase):
    """判据要有**生产**消费方，不能只有工作流在引它。

    实测 2026-08-25：这条判据写完只被 `job-apply.md` 引用，
    `test_long_writes_do_not_clobber.test_every_public_judge_in_cli_has_a_consumer`
    当场把它报成「没有消费者的正本」—— 那条守卫是上一轮为 `fold_user_state`
    立的，这一轮抓的是我自己新写的。接到面板上：和 `sendVia`、`greetingWarn`
    同一个位置，也就是他按「复制开场白」的那一下。
    """

    EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
    TYPES = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
    READOUT = (ROOT / "web" / "src" / "components"
               / "JobReadout.tsx").read_text(encoding="utf-8")

    def test_the_export_calls_the_judge(self):
        self.assertIn("_cli.counterpart_of(e.get(\"recruiterTitle\")", self.EX)

    def test_it_sits_next_to_send_via(self):
        i = self.EX.index('mats["sendVia"]')
        self.assertIn("counterpart", self.EX[i:i + 1400],
                      "要和「这段话怎么发出去」同一处 —— 那是他按复制的那一下")

    def test_an_unreadable_title_writes_no_key(self):
        """**不猜。** 空串时连键都不写，面板那边 `?? ` 兜不出一个假答案。"""
        i = self.EX.index("_cp = _cli.counterpart_of")
        seg = self.EX[i:i + 200]
        self.assertIn("if _cp:", seg)
        self.assertIn('mats["counterpart"] = _cp', seg)

    def test_the_type_exists(self):
        self.assertIn("counterpart?: string;", self.TYPES)

    def test_the_type_says_where_the_judge_lives(self):
        i = self.TYPES.index("counterpart?: string;")
        self.assertIn("_cli.counterpart_of", self.TYPES[max(0, i - 700):i])

    def test_the_panel_only_speaks_up_for_the_third_bucket(self):
        """猎头和 HR 那两档面板本来就说得清，只有第三档是新信息。"""
        self.assertIn('m.counterpart === "用人方"', self.READOUT)

    def test_it_tells_him_what_to_do_not_what_it_is(self):
        i = self.READOUT.index('m.counterpart === "用人方"')
        seg = self.READOUT[i:i + 500]
        self.assertIn("讲具体怎么落地", seg)
        self.assertIn("别讲职业规划和稳定性", seg)
        self.assertIn("上手第一件事", seg)

    def test_no_internal_words_reach_the_screen(self):
        """面板上的字要说人话（`AGENTS.md`「给用户看的措辞」）。"""
        i = self.READOUT.index('m.counterpart === "用人方"')
        seg = self.READOUT[i:i + 500]
        for w in ("渠道判定", "判据", "counterpart_of", "isHeadhunter"):
            with self.subTest(word=w):
                self.assertNotIn(w, seg.split("</p>")[0].split(">")[-1])


class TheScrapeStoresIt(unittest.TestCase):

    def test_the_schema_lists_the_field(self):
        i = SCRAPE.index('"recruiterSurname"')
        self.assertIn('"recruiterTitle"', SCRAPE[i:i + 200],
                      "抓到了不入库，判据就永远拿不到这个字段")

    def test_the_field_table_says_what_breaks_without_it(self):
        line = next(l for l in SCRAPE.splitlines()
                    if l.startswith("| `recruiterTitle`"))
        self.assertIn("counterpart_of", line)
        self.assertIn("退回两档", line)

    def test_the_cli_really_emits_it(self):
        """上游不给，这一整条就是空转。"""
        src = (ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "src"
               / "helpers.ts").read_text(encoding="utf-8")
        self.assertIn("recruiterTitle: str(recruiter.recruiterTitle)", src)


class TheTitleCanSayItItself(unittest.TestCase):
    """头衔那一栏常常是「公司名 · 角色名」，而公司名里的行业词会喧宾夺主。

    实测活动用户 2026-08-30：4 个岗的头衔明写「某某 · 猎头顾问」，
    而职位库里 `isHeadhunter` 记着 `False`。这 4 个里 **1 个被判成了 HR** ——
    头衔是「某某人力资源 · 猎头顾问」，公司名里的「人力」撞上了
    `COUNTERPART_HR`，而那张表是按**角色名**写的。

    代价落在 `/job-apply` 第 1.5 步：照 HR 直招版写话术就是不主动谈薪资与
    到岗时间，而对猎头那两样恰恰要直接答（`06` 渠道判定）。

    同一条硬规则在 `_cli.via_headhunter` 和 `doctor._via_headhunter` 里各有
    一份（后者是不 import 仓库模块的手抄件），三处一致由
    `test_one_judge_for_agency_or_direct` 钉住。
    """

    def test_the_title_beats_the_word_lists(self):
        self.assertEqual(
            _cli.counterpart_of("某某人力资源 · 猎头顾问", False), "猎头",
            "公司名里的「人力」不该盖过角色名里的「猎头」")

    def test_it_works_when_the_field_says_direct(self):
        for t in ("某某企业管理咨询 · 猎头顾问", "某某人才 · 猎头顾问",
                  "猎头顾问"):
            with self.subTest(t=t):
                self.assertEqual(_cli.counterpart_of(t, False), "猎头")

    def test_only_this_direction(self):
        """反过来不成立：头衔像用人方 ≠ 不是猎头。

        实测 19 个含中介词的头衔里 15 个是「人力资源总监」「HRBP」
        「人才招聘经理」—— **企业自己的 HR**。所以只认「猎头」二字，
        别把整张 `_AGENCY_WORDS` 套到这一栏上。
        """
        self.assertEqual(_cli.counterpart_of("人力资源总监", False), "HR")
        self.assertEqual(_cli.counterpart_of("人才招聘经理", False), "HR")
        self.assertEqual(_cli.counterpart_of("研发总监", True), "猎头",
                         "字段说是猎头时，它仍然说了算")


if __name__ == "__main__":
    unittest.main()
