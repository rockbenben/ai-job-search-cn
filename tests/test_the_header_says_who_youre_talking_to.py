# -*- coding: utf-8 -*-
"""抬头要答清「在跟谁说话、这一档是什么」——236 份真实产出，两样都缺。

`06-outreach-templates.md` 的产出格式规定了话术抬头，`/job-apply` 1.5a 也写着
「判定结果（**有无对话方** + 猎头/HR/用人方）写入产出物的头部」。实测活动用户
2026-08-24 扫 236 份：

    抬头有「投递路径：」            0/236   ← 上一条刚写完「必需的，不是可选的」
    渠道判定没写是猎头还是直招       110 份
    抬头说「直招」而库里是猎头       28 份
    抬头里连个分数都没有            177 份（`评分：` 字段 0/236，59 份写成 `判词：`）
    「判词」出现在抬头里            102 份   ← 同一段规范点名不要写的那个词
    猎头岗对着顾问说「贵司」         9 份

## 三件事各有各的代价

- **少了猎头/直招那半句**，第二轮就没法照着走：`06` 那张表里猎头问薪资与到岗
  时间要直接答（他要拿这两个数去匹配），HR 直招则不主动展开。
- **说反了更贵。** 那 28 份全是一个方向（文件说直招、库说猎头），而且
  **28/28 的雇主名是「某上海……公司」这类占位** —— 猎聘只对猎头/代招岗隐雇主名，
  HR 自己发的岗公司名就在那儿。文件错，字段对。照着「直招」写，就会对着顾问讲
  「贵司如何如何」—— 实测 9 份已经这么写了。
- **没有分数与档名**，打开文件看不出这份是「强匹配」还是「可以考虑」，
  而那正是决定发不发的那个数。

## 规格那一半也改了

236/236 不符合规格时先怀疑规格。执行者把「投递路径」和「渠道判定」并成一行
（`有对话方 · 猎聘聊天框（猎头）`）**比拆成两行好** —— 一行答完两件事。
所以 `06` 改成**只钉内容不钉行数**，检查也只查内容。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import audit_pipeline as ap  # noqa: E402

TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def head(**kw) -> str:
    """造一份最小的 outreach.md。"""
    lines = ["# 投递话术：某公司 - 某岗位", ""]
    for k, v in kw.items():
        lines.append(f"- {k}：{v}")
    lines += ["", "## 打招呼开场白（≤200 字）", "", kw.pop("_greeting", "您好，我做过 X。")]
    return "\n".join(lines)


class TheCheckIsWiredIn(unittest.TestCase):
    def test_it_is_registered(self):
        names = [n for n, _f in ap.CHECKS]
        self.assertIn("话术：抬头没说清在跟谁说话", names)

    def test_it_runs_before_the_company_claims_one(self):
        """同族三条挨在一起，报出来才读得成一段。"""
        names = [n for n, _f in ap.CHECKS]
        self.assertLess(names.index("话术：抬头没说清在跟谁说话"),
                        names.index("话术：说了公司的事就要有出处"))


class TheHeadIsCutAtTheFirstSection(unittest.TestCase):
    def test_it_stops_at_the_first_heading(self):
        t = "# 标题\n\n- 渠道判定：猎头\n\n## 打招呼开场白\n\n您好，贵司如何如何。"
        self.assertIn("渠道判定", ap._head_of(t))
        self.assertNotIn("贵司", ap._head_of(t),
                         "抬头切到正文里去了 —— 开场白里的字会被当成抬头查")

    def test_a_file_with_no_section_is_all_head(self):
        self.assertIn("渠道判定", ap._head_of("- 渠道判定：猎头"))


class ItReadsAgainstTheRealCorpus(unittest.TestCase):
    """有语料时直接跑一遍 —— 注释里的数说得再好，跑不出来也白搭。"""

    def _run(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        root = ROOT / "users" / u
        sj = root / "job_scraper" / "seen_jobs.json"
        if not sj.is_file() or not (root / "documents" / "applications").is_dir():
            self.skipTest("这份 clone 下没有语料")
        seen = _cli.seen_of(json.loads(sj.read_text(encoding="utf-8")))
        return ap.check_outreach_header_says_who_youre_talking_to(seen, {})

    def test_it_reports_something_on_this_corpus(self):
        out = self._run()
        if not out:
            self.skipTest("这份语料下抬头全都合规 —— 那这条检查的依据要重量")
        for level, _title, _body in out:
            self.assertEqual(level, "warn",
                             "这条没有机械修法，判 error 会让零 error 那条测试长红")

    def test_it_names_the_headhunter_split(self):
        titles = [t for _l, t, _b in self._run()]
        if not titles:
            self.skipTest("这份语料下抬头全都合规")
        self.assertIn("话术抬头没说清在跟谁说话", titles)

    def test_the_wrong_direction_claim_still_holds(self):
        """「28/28 都是匿名雇主」是这条检查最硬的论据 —— 它变了就要重写。"""
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        root = ROOT / "users" / p.read_text(encoding="utf-8").strip()
        sj = root / "job_scraper" / "seen_jobs.json"
        if not sj.is_file():
            self.skipTest("没有职位库")
        seen = _cli.seen_of(json.loads(sj.read_text(encoding="utf-8")))
        by = {_cli.norm_url(e.get("url") or ""): e for e in seen.values()}
        anon = both = 0
        for f in sorted((root / "documents" / "applications").glob("*/outreach.md")):
            t = f.read_text(encoding="utf-8", errors="replace")
            h = ap._head_of(t)
            # 重推规则的测试**测不出规则变了** —— 走正本
            # （`test_shared_vocab_single_source.py` 盯着这条）。
            if _cli.addressee_said(h) != "直招":
                continue
            m = re.search(r"职位链接[：:]\s*(\S+)", t)
            e = by.get(_cli.norm_url(m.group(1))) if m else None
            if not (e and e.get("isHeadhunter")):
                continue
            both += 1
            c = (e.get("company") or "").strip()
            if not c or re.match(r"^(某|一家)", c):
                anon += 1
        if not both:
            self.skipTest("这份语料里没有写反的")
        self.assertGreater(anon, 0,
                         f"写反的 {both} 份里只有 {anon} 份是匿名雇主")


class ItCatchesEachKindOnConstructedInput(unittest.TestCase):
    """真实语料只证明现在有问题；这几条证明检查认得出问题。"""

    def _run(self, files, seen):
        import tempfile
        old = ap.ROOT
        try:
            with tempfile.TemporaryDirectory() as t:
                r = pathlib.Path(t)
                d = r / "users" / "甲" / "documents" / "applications"
                for name, text in files.items():
                    (d / name).mkdir(parents=True, exist_ok=True)
                    (d / name / "outreach.md").write_text(text, encoding="utf-8")
                (r / "users" / "甲" / "profile").mkdir(parents=True, exist_ok=True)
                (r / "users" / "甲" / "profile" / "candidate.md").write_text(
                    "x", encoding="utf-8")
                (r / ".active_user").write_text("甲", encoding="utf-8")
                ap.ROOT = r
                return ap.check_outreach_header_says_who_youre_talking_to(seen, {})
        finally:
            ap.ROOT = old

    def _titles(self, files, seen=None):
        return [t for _l, t, _b in self._run(files, seen or {})]

    def test_a_clean_header_reports_nothing(self):
        ok = ("# 投递话术：甲公司 - 某岗\n\n"
              "- 渠道判定：**有对话方 · 猎聘聊天框（HR 直招）**\n"
              "- 生成日期：2026-08-24\n"
              "- 职位链接：https://example.com/1\n"
              "- 评分：72 分，属于「值得投」\n\n"
              "## 打招呼开场白\n\n您好，我做过 X。\n")
        self.assertEqual(self._titles({"甲公司_某岗": ok}), [])

    def test_it_catches_a_missing_kind(self):
        t = ("- 渠道判定：**有对话方 · 猎聘聊天框**\n- 评分：72 分\n\n"
             "## 打招呼开场白\n\n您好。\n")
        self.assertIn("话术抬头没说清在跟谁说话", self._titles({"甲_岗": t}))

    def test_it_catches_a_missing_score(self):
        t = ("- 渠道判定：**有对话方 · 聊天框（猎头）**\n\n"
             "## 打招呼开场白\n\n您好。\n")
        self.assertIn("话术抬头缺分数档 / 用了内部词", self._titles({"甲_岗": t}))

    def test_it_catches_the_banned_words(self):
        for w in ("判词", "四维", "硬门", "能力边界", "台账"):
            with self.subTest(w=w):
                t = (f"- 渠道判定：**有对话方 · 聊天框（猎头）**\n- {w}：值得投（72 分）\n\n"
                     "## 打招呼开场白\n\n您好。\n")
                self.assertIn("话术抬头缺分数档 / 用了内部词",
                              self._titles({"甲_岗": t}),
                              f"「{w}」没被认出来")

    def test_it_catches_the_wrong_kind(self):
        seen = {"a": {"url": "https://example.com/1", "isHeadhunter": True,
                      "company": "某上海互联网公司"}}
        t = ("- 渠道判定：**有对话方 · 聊天框（HR 直招，非猎头）**\n"
             "- 职位链接：https://example.com/1\n- 评分：72 分\n\n"
             "## 打招呼开场白\n\n您好。\n")
        body = [b for _l, ti, b in self._run({"甲_岗": t}, seen)
                if ti == "话术抬头没说清在跟谁说话"]
        self.assertTrue(body, "写反的没报出来")
        self.assertIn("1 份写反了", body[0])

    def test_it_catches_your_company_said_to_a_consultant(self):
        seen = {"a": {"url": "https://example.com/1", "isHeadhunter": True,
                      "company": "某上海互联网公司"}}
        t = ("- 渠道判定：**有对话方 · 聊天框（猎头）**\n"
             "- 职位链接：https://example.com/1\n- 评分：72 分\n\n"
             "## 打招呼开场白\n\n您好，看到贵司在招这个岗。\n")
        self.assertIn("猎头岗的开场白对着顾问说「贵司」",
                      [t2 for _l, t2, _b in self._run({"甲_岗": t}, seen)])

    def test_direct_employers_may_say_your_company(self):
        """直招岗写「贵司」是对的 —— 这条挡住把规则套到所有岗上。"""
        seen = {"a": {"url": "https://example.com/1", "isHeadhunter": False,
                      "company": "甲公司"}}
        t = ("- 渠道判定：**有对话方 · 聊天框（HR 直招）**\n"
             "- 职位链接：https://example.com/1\n- 评分：72 分\n\n"
             "## 打招呼开场白\n\n您好，看到贵司在招这个岗。\n")
        self.assertEqual(self._run({"甲_岗": t}, seen), [])

    def test_a_score_anywhere_in_the_head_counts(self):
        """不查有没有「评分：」那个字段，查有没有那个数 —— 06 只钉内容不钉行数。"""
        t = ("- 渠道判定：**有对话方 · 聊天框（猎头）**\n"
             "- 这个岗 72 分，属于「值得投」\n\n## 打招呼开场白\n\n您好。\n")
        self.assertEqual(self._titles({"甲_岗": t}), [])


class TheSpecMatchesWhatIsActuallyProduced(unittest.TestCase):
    def _seg(self) -> str:
        i = TPL.index("一条规格")
        return flat(TPL[i:i + 2600])

    def test_it_admits_the_old_shape_was_never_followed(self):
        self.assertRegex(self._seg(), r"只钉内容，不钉行数")

    def test_it_says_to_suspect_the_spec_first(self):
        """规格不被遵守时，先怀疑规格。"""
        self.assertRegex(self._seg(), r"一条规格.*不被遵守，先怀疑规格")

    def test_it_says_the_merged_line_is_better(self):
        seg = self._seg()
        self.assertRegex(seg, r"\*\*执行者做的那件事更好\*\*")
        self.assertRegex(seg, r"拆成两行只是把同一件事说两遍")

    def test_it_now_pins_content_not_line_count(self):
        seg = self._seg()
        self.assertRegex(seg, r"\*\*所以这里只钉内容，不钉行数\*\*")
        self.assertRegex(seg, r"从此是示例，不是唯一合法形状")

    def test_the_four_required_things_are_listed(self):
        seg = self._seg()
        self.assertRegex(seg, r"有没有对话方，以及是猎头还是 HR 直招")
        self.assertRegex(seg, r"这一档是什么")
        self.assertRegex(seg, r"链接与日期")
        self.assertRegex(seg, r"不许出现内部词")

    def test_it_names_the_check_that_watches_it(self):
        self.assertIn("话术：抬头没说清在跟谁说话", self._seg())

    def test_it_carries_the_anonymous_employer_argument(self):
        seg = self._seg()
        self.assertRegex(seg, r"针对隐去公司名的猎头代招岗")

    def test_the_skeleton_no_longer_lists_the_dead_field(self):
        i = TPL.index("# <公司> - <岗位> 投递话术")
        block = TPL[i:i + 500]
        self.assertNotIn("投递路径：平台直聊", block,
                         "骨架里又摆回那一行了 —— 实测 0/236 会照它写")
        self.assertIn("渠道判定", block)
        self.assertIn("评分", block)


class TheOlderOutreachRulesAreIntact(unittest.TestCase):
    def test_the_consultant_rule_is_still_written(self):
        self.assertIn("跟他讲「贵司如何如何」是讲错了人", TPL)

    def test_the_two_round_table_survives(self):
        self.assertIn("## 渠道判定：猎头 / HR / 用人方本人", TPL)

    def test_the_jargon_ban_still_names_its_source(self):
        self.assertRegex(flat(TPL), r"抬头那几行也是给用户看的字，"
                                    r"同样按 `AGENTS.md`「给用户看的措辞」写")

    def test_the_jargon_list_matches_the_wording_table(self):
        """检查里那份词表不能自己长出词来 —— 判据在 AGENTS.md 那张表。"""
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for w in ap._HEAD_JARGON:
            self.assertIn(w, agents, f"「{w}」不在 AGENTS.md 的措辞表里，凭什么禁")


if __name__ == "__main__":
    unittest.main()
