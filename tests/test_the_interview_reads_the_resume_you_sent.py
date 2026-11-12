# -*- coding: utf-8 -*-
"""备面整条口径一致的规矩，建立在一份 89% 的投递里根本不存在的文件上。

`job-interview.md` 开头就把这条立成命令的存在理由：

> `/job-apply` 优化的是对方「读到」的东西，`/job-interview` 优化的是对方「听到」的
> 东西。把两者连起来的是**口径一致**：面试官读过你交出去的简历和求职信，
> 所以这里准备的每一句话，都必须和那两份文件的说法对得上。

而 Step 1 把那份简历指向 `documents/applications/<公司>_<岗位>/resume.pdf`，
兜底那条还写死：「**简历与求职信没有归档之外的第二个存放处**——归档里没有就
**直说，不要猜**」。

## 那句话是错的，而且错得很贵

**定制简历是例外不是默认** —— `job-apply.md` 开头的原话是「简历一律发主简历
`resume/main.pdf`；定制简历只在特殊情况由 `/job-cv` 做」。
实测活动用户 2026-08-24：

    85 条投递 · 认得回归档的 64 条 · 归档里带 resume.pdf 的 7 条（11%）
    268 个材料目录 · 有 resume.pdf 的 15 个

也就是说**近九成的面试**，照这条走会得到「查无此简历」，然后整条口径一致的规矩
没有输入——而它是这条命令的立命之本。**那份简历一直都在**：`resume/main.pdf`，
就是他当时发出去的那一份。

## 还有一个更隐蔽的坑：主简历会被改

实测同一天：`resume/main.typ` 最后改动 2026-08-12，而 **19 条投递发生在那之前**。
那 19 次面试的口径基准**盘上已经不存在了** —— 读现在这版当成「面试官读的那版」，
会教出一套对方没看过的说法。这与面板上「上次审于 X，之后改过没再审」是同一个坑，
那边已经处理过，这边没有。

## 求职信那一半是对的，别一起改掉

求职信确实只在归档里，而且它是场景触发的产出——实测全库产出 0 份。
原来那句话的毛病是**把两者写成一样的**。
"""
import csv
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import _cli  # noqa: E402

DOC = (ROOT / "workflows" / "job-interview.md").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class ItLooksWhereTheResumeActuallyIs(unittest.TestCase):
    def _seg(self) -> str:
        i = DOC.index("**他交出去的那份简历**")
        return flat(DOC[i:i + 1800])

    def test_both_places_are_named(self):
        seg = self._seg()
        self.assertIn("`resume.pdf`", seg)
        self.assertIn("`resume/main.pdf`", seg)

    def test_the_archive_copy_is_the_exception(self):
        """反过来说就成了「归档没有 = 没投过简历」，那是 89% 的情况。"""
        seg = self._seg()
        self.assertRegex(seg, r"\*\*没有 → 交出去的是主简历 `resume/main.pdf`\*\*")
        self.assertRegex(seg, r"定制简历是例外\s*不是默认|定制简历是例外不是默认")

    def test_it_carries_the_measurement(self):
        seg = self._seg()
        self.assertIn("resume/main.pdf", seg)
        self.assertIn("定制版", seg)

    def test_it_records_why_the_first_number_was_wrong(self):
        """匹配需拿 source 链接去对，而不是仅按名字猜。"""
        seg = self._seg()
        self.assertIn("source", seg)
        self.assertIn("posting.md", seg)

    def test_it_says_what_breaks_without_it(self):
        """只说「还有一个地方」不够 —— 要说清缺了它这条命令还剩什么。"""
        self.assertRegex(self._seg(),
                         r"\*\*近九成\*\*的面试拿不到「面试官读的是什么」这个输入")


class TheTwoResumeCaseIsHandled(unittest.TestCase):
    """国内常见两份并行：网申用精简版，**猎头要、面试带的是详版**。

    而「面试带的那一份」恰恰是这条命令要对口径的那一份 —— 上一版这里写死
    `resume/main.pdf`，等于在最要紧的场合默认读错。`job-resume.md` Step 1
    早就记着这件事（并实测活动用户目录里就有两份），只是没传到这边。
    """

    def _seg(self) -> str:
        i = DOC.index("`resume/` 里可能不止一份主简历")
        return flat(DOC[i:i + 800])

    def test_it_looks_before_assuming_one(self):
        self.assertRegex(self._seg(), r"先 `ls resume/\*.pdf`")

    def test_it_names_the_two_resume_habit(self):
        seg = self._seg()
        self.assertRegex(seg, r"两份并行")
        self.assertRegex(seg, r"\*\*猎头要、面试带的详版\*\*")

    def test_it_says_why_this_command_is_the_worst_place_to_guess(self):
        self.assertRegex(self._seg(), r"恰好在最要紧的场合可能读错")

    def test_it_asks_instead_of_picking(self):
        seg = self._seg()
        self.assertRegex(seg, r"\*\*多于一份就问他一句")
        self.assertRegex(seg, r"别替他挑")

    def test_it_still_has_a_fallback(self):
        """问不出来不能卡住 —— 走默认，但把口径说清。"""
        seg = self._seg()
        self.assertRegex(seg, r"问不出来就按 `main.pdf` 走")
        self.assertRegex(seg, r"你带详版去的话再核一遍")

    def test_the_source_of_the_habit_is_still_written_down(self):
        """引的是 job-resume Step 1 —— 那一节没了这条就成了孤证。"""
        r = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")
        self.assertRegex(flat(r), r"国内求职常见\*\*两份并行\*\*")
        self.assertIn("ls resume/*.typ", r)


class TheStaleResumeTrapIsNamed(unittest.TestCase):
    def _seg(self) -> str:
        i = DOC.index("**主简历会在投出去之后被改。**")
        return flat(DOC[i:i + 900])

    def test_it_tells_you_to_compare_the_dates(self):
        self.assertRegex(self._seg(), r"比一眼它的修改时间和这次投递的日期")

    def test_it_says_which_version_the_interviewer_holds(self):
        self.assertRegex(self._seg(),
                         r"\*\*改过的话，面试官手上是旧版，你现在读到的是新版。\*\*")

    def test_it_carries_the_measurement(self):
        seg = self._seg()
        self.assertIn("resume/main.typ", seg)
        self.assertIn("修改时间", seg)

    def test_it_does_not_stop_the_command(self):
        """备面不能因为这个停下 —— 照实说一句，接着做。"""
        seg = self._seg()
        self.assertRegex(seg, r"照实说")
        self.assertRegex(seg, r"然后照常往下做")


class TheCoverLetterHalfIsUntouched(unittest.TestCase):
    """求职信确实只在归档里 —— 别把它跟简历一起改掉。"""

    def _seg(self) -> str:
        i = DOC.index("**求职信**没有归档之外的第二个存放处")
        return flat(DOC[i:i + 700])

    def test_the_cover_letter_still_has_one_home(self):
        self.assertRegex(self._seg(), r"\*\*求职信\*\*没有归档之外的第二个存放处")
        self.assertRegex(self._seg(), r"归档里没有就\*\*直说，不要猜\*\*")

    def test_the_two_are_now_separated(self):
        seg = self._seg()
        self.assertRegex(seg, r"\*\*简历不一样\*\*")
        self.assertRegex(seg, r"这句话原来把两者写成一样的")

    def test_it_says_the_cover_letter_is_usually_absent_by_design(self):
        self.assertRegex(self._seg(), r"它本来就是场景触发的产出")


class TheIronRuleAgreesWithStepOne(unittest.TestCase):
    """铁律那一条是这条命令被引用最多的一句 —— 它不能还指着归档。"""

    def _rule(self) -> str:
        i = DOC.index("## 铁律")
        return flat(DOC[i:i + 700])

    def test_it_no_longer_says_only_the_archive(self):
        self.assertNotIn("面试官读的是归档里那份简历和求职信", DOC,
                         "铁律又回到只认归档了 —— 和 Step 1 打架")

    def test_it_names_both_places(self):
        rule = self._rule()
        self.assertRegex(rule, r"归档里有定制版就是它，没有就是主简历")

    def test_it_points_at_the_full_criterion(self):
        self.assertIn("见 Step 1 第 1 条", self._rule())

    def test_the_rule_itself_survives(self):
        self.assertRegex(self._rule(),
                         r"\*\*准备包既不许和它们矛盾，也不许教出超出它们的说法。\*\*")


class TheDefaultItLeansOnIsReal(unittest.TestCase):
    """「发主简历」这条默认要真的还在 —— 它变了，这一整条就要重写。"""

    def test_apply_still_says_send_the_main_resume(self):
        """引的是 `job-apply.md` 的原话，不是转述 —— 第一版写成了
        「平时直接发主简历就行」（那句在产出的抬头里，不在正文里），
        当场被这条逮到。"""
        self.assertRegex(flat(APPLY), r"简历一律发主简历 `resume/main.pdf`")
        self.assertIn("简历一律发主简历 `resume/main.pdf`", DOC,
                      "job-interview 引的那句和 job-apply 的原话对不上")

    def test_the_archive_copy_is_still_produced_by_job_cv(self):
        cv = (ROOT / "workflows" / "job-cv.md").read_text(encoding="utf-8")
        self.assertIn("resume.pdf", cv + APPLY)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时重算一遍：归档里带简历的到底占几成。"""

    def _rows(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        root = ROOT / "users" / p.read_text(encoding="utf-8").strip()
        tk = root / "job_search_tracker.csv"
        apps = root / "documents" / "applications"
        if not (tk.is_file() and apps.is_dir()):
            self.skipTest("没有语料")
        # **按工作流规定的那条连法认**：拿 `source` 去 `posting.md` /
        # `outreach.md` 里对（Step 1 第 1 条）。第一版只在 `evaluation.md` 里
        # 找「职位链接：」这个标签 —— 那是工作流明说不要用的路，量出来
        # 85 条只认回 64 条，比实际低了两成半。判据要和被测的规则同源。
        idx = {}
        for d in apps.iterdir():
            if not d.is_dir():
                continue
            for name in ("posting.md", "outreach.md"):
                f = d / name
                if not f.is_file():
                    continue
                for m in re.finditer(r"https?://[^\s)）\]\"'，。]+",
                                     f.read_text(encoding="utf-8",
                                                 errors="replace")):
                    idx.setdefault(_cli.norm_url(m.group(0)), d)
        out = []
        with tk.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                d = idx.get(_cli.norm_url(r.get("source") or ""))
                if d:
                    out.append((r, d))
        if len(out) < 10:
            self.skipTest("认得回归档的投递太少")
        return out

    def test_the_documented_ratio_still_holds(self):
        """文档里写着「85/85 认得回、11 条带简历」—— 现算一遍对不上就该重量。

        **不比死数**（语料每天在长），比的是**文档里那个比例还站不站得住**：
        带定制简历的仍是少数，且认回率仍然接近全中。
        """
        rows = self._rows()
        tk = (ROOT / "users"
              / (ROOT / ".active_user").read_text(encoding="utf-8").strip()
              / "job_search_tracker.csv")
        with tk.open(encoding="utf-8-sig") as f:
            total = sum(1 for _ in csv.DictReader(f))
        self.assertGreaterEqual(
            len(rows), total * 0.9,
            f"按规定的连法只认回 {len(rows)}/{total} —— "
            f"「按链接全部认得回归档」那句不成立了")
        have = sum(1 for _r, d in rows if (d / "resume.pdf").is_file())
        self.assertLess(have, len(rows) * 0.3,
                        f"{have}/{len(rows)} 带定制简历 —— 「近九成没有」要重写")

    def test_most_applications_have_no_archived_resume(self):
        rows = self._rows()
        have = sum(1 for _r, d in rows if (d / "resume.pdf").is_file())
        self.assertLess(
            have, len(rows) * 0.5,
            f"{have}/{len(rows)} 条投递的归档里都有定制简历了 —— "
            f"「定制是例外」不再成立，Step 1 那段要重写")

    def test_the_main_resume_exists_to_fall_back_to(self):
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        p = ROOT / ".active_user"
        root = ROOT / "users" / p.read_text(encoding="utf-8").strip()
        self.assertTrue((root / "resume" / "main.typ").is_file(),
                        "主简历不在 —— 那 Step 1 的回退落空了")

    def test_some_applications_predate_the_current_main_resume(self):
        """这条是「主简历会被改」那个坑的现场证据。全没有了就该重量。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        import datetime as dt
        p = ROOT / ".active_user"
        root = ROOT / "users" / p.read_text(encoding="utf-8").strip()
        cv = root / "resume" / "main.typ"
        if not cv.is_file():
            self.skipTest("没有主简历")
        changed = dt.date.fromtimestamp(cv.stat().st_mtime).isoformat()
        rows = self._rows()
        older = sum(1 for r, _d in rows if (r.get("date") or "")[:10] < changed)
        if not older:
            self.skipTest("这批投递全在主简历最后改动之后 —— 这轮没有旧版问题")
        self.assertGreater(older, 0)


if __name__ == "__main__":
    unittest.main()
