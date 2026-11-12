# -*- coding: utf-8 -*-
"""同一份工作流让你「收到 14 天内」，又让你往深翻页 —— 而这两条会不会互相抵消，
**取决于深页的卡片带不带日期，那是个会变的事实**。

`job-scrape.md` Step 3 要求用渠道的「多久之内」参数把范围收到最近 14 天；
猎聘那条是 `--jobage`，而它是**客户端过滤**：`filterByAge` 把
`date === null` 的卡片直接 `return false` 丢掉。这一段没变，也不该变 ——
本文件第一组测试就盯着它。

## 结论翻过一次，这件事本身才是这条守卫的正文

**2026-08-23 的观察**：入库的猎聘岗按 `found_by` 里的页码分组，带日期的比例是
第 1 页 250/860（29%）、第 2 页往后 9/710（1%）。据此写进工作流的规则是
「`--jobage` 在第 2 页之后几乎会把结果清空，所以**第 1 页可以带，往后翻就不带**」。

**2026-08-27 一轮 `/job-auto` 把它推翻了**：从同一个 CLI、同样不传 `--jobage`
抓了 8 次（4 个词 × 前 2 页），入库 140 个 —— **第 1 页 97/97、第 2 页 43/43，
两边都是 100% 带日期**。同样的调用方式，深页的日期覆盖率从 1% 变成 100%。

所以那个 1% **不是页码的性质，是当时那批数据的性质**（接口行为变过，或者早期
入库那批的页码标注口径与现在不同）。全库现在是第 1 页 17%、深页 7%，
差距还在但只有 2 倍多，撑不起「几乎清空」那个结论。

## 于是这条守卫改成验两件事，而不是钉一个倍数

1. **前提还在**：`filterByAge` 仍然丢掉没日期的卡片（第一组测试，没动）。
   这一条一旦变了，整条规则连讨论的必要都没有。
2. **工作流写的是现在这一版**：不再说「翻页干脆别传」，而是说清那个结论被推翻过，
   并把判据交回给 `droppedNoDate` —— 它看的是**这一次请求的实际情况**，
   不是一个会过期的分布。

原来这里还有两条现算断言（`第 1 页 > 深页 × 5`、`深页带日期 < 10%`），
**已经删掉**：它们钉的正是被推翻的那个结论。留着只会逼下一个人去改断言，
而不是去改规则 —— 这个仓库另一处早就写过同一句话：
「哪天两边倒过来，那条规则就该重写，而不是把数改一改」。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
SKILL = (ROOT / ".agents" / "skills" / "liepin-search"
         / "SKILL.md").read_text(encoding="utf-8")
SEARCH_TS = (ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "src"
             / "commands" / "search.ts").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheFilterReallyDropsUndatedCards(unittest.TestCase):
    """整条规则建立在这个行为上 —— 它变了，规则就没有依据了。"""

    def test_a_null_date_is_dropped_not_kept(self):
        i = SEARCH_TS.index("export function filterByAge(")
        body = SEARCH_TS[i:SEARCH_TS.index("\n}", i)]
        m = re.search(r"if \(c\.date === null\) \{\s*noDate\+\+\s*return (\w+)",
                      body)
        self.assertIsNotNone(m, "认不出没日期那一支了")
        self.assertEqual(m.group(1), "false", "没日期的卡片不再被丢掉 —— "
                                              "那这条规则的前提变了，重新量一次")

    def test_the_two_reasons_are_still_counted_apart(self):
        i = SEARCH_TS.index("export function filterByAge(")
        body = SEARCH_TS[i:SEARCH_TS.index("\n}", i)]
        self.assertIn("tooOld++", body)
        self.assertIn("noDate++", body)

    def test_a_zero_or_absent_age_filters_nothing(self):
        """不传 `--jobage` 时一张卡都不该丢 —— 那正是这条规则要人走的路。"""
        i = SEARCH_TS.index("export function filterByAge(")
        body = SEARCH_TS[i:SEARCH_TS.index("\n}", i)]
        self.assertIn("if (!days || days <= 0 || days >= 9999)", body)
        self.assertIn("return { cards, tooOld: 0, noDate: 0 }", body)


class TheWorkflowSaysWhenNotToPassIt(unittest.TestCase):
    def _block(self) -> str:
        i = SCRAPE.index("「多久之内」是在结果上过滤的")
        return flat(SCRAPE[i:SCRAPE.index("\n4.", i)])

    def test_it_says_the_old_conclusion_was_overturned(self):
        """**推翻这件事本身要写在文里。** 只把数字换掉，下一个人会以为规则没变过。"""
        seg = self._block()
        self.assertRegex(seg, r"被实测推翻")
        self.assertIn("2026-08-27", seg)

    def test_it_carries_both_measurements(self):
        """说明旧结论为什么被推翻 —— 避免读者判断失准。"""
        seg = self._block()
        self.assertRegex(seg, r"深页是否有日期并非固定不变|日期覆盖率")

    def test_it_no_longer_tells_people_to_drop_the_flag_when_paging(self):
        seg = self._block()
        self.assertNotRegex(seg, r"\*\*翻页的时候干脆别传它。\*\*")
        self.assertRegex(seg, r"翻页时照常可以传 `--jobage`")

    def test_it_hands_the_judgement_back_to_the_live_number(self):
        """会过期的分布换成每一轮都看得到的读数。"""
        seg = self._block()
        self.assertRegex(seg, r"每一轮都看一眼 `droppedNoDate`")
        self.assertRegex(seg, r"不是一个会过期的分布")

    def test_the_original_after_the_fact_note_survives(self):
        """事后那条仍然有用（第 1 页也会丢七成）—— 不能被这次改动顶掉。"""
        seg = self._block()
        self.assertIn("droppedNoDate", seg)
        self.assertRegex(seg, r"别传 `--jobage` 再跑一次")

    def test_the_fourteen_day_instruction_still_stands(self):
        """这次不是废掉「收到 14 天内」，只是说清它在第几页有效。"""
        self.assertIn("把范围收到**最近 14 天**", SCRAPE)


class TheSkillSaysItToo(unittest.TestCase):
    """CLI 的使用者可能只读 SKILL.md，不读工作流。"""

    def _seg(self) -> str:
        i = SKILL.index("**`--jobage` 是客户端过滤。**")
        return flat(SKILL[i:SKILL.index("- **翻页上限 10 页。**", i)])

    def test_it_says_the_old_conclusion_was_overturned_too(self):
        """**两边一起改。** 这一段是工作流那条的抄件；只改一头，
        读 SKILL.md 的人还会照着已经作废的结论去关掉 `--jobage`。
        """
        seg = self._seg()
        self.assertRegex(seg, r"被实测推翻")
        self.assertIn("2026-08-27", seg)

    def test_it_carries_both_measurements_too(self):
        seg = self._seg()
        self.assertRegex(seg, r"第 1 页 250/860|日期覆盖率|深页")

    def test_it_no_longer_tells_people_to_drop_the_flag_when_paging(self):
        seg = self._seg()
        self.assertNotRegex(seg, r"\*\*翻页时干脆别传它。\*\*")
        self.assertRegex(seg, r"翻页照常可以传")

    def test_it_hands_the_judgement_back_to_the_live_number_too(self):
        seg = self._seg()
        self.assertRegex(seg, r"每一轮都看一眼 `droppedNoDate`")

    def test_the_existing_caveats_survive(self):
        seg = self._seg()
        self.assertRegex(seg, r"猎聘接口的 `pubTime` 参数是哑的")
        self.assertRegex(seg, r"没有更新时间的卡片也会被丢掉")

    def test_the_page_cap_note_survives(self):
        """这条紧挨着，最容易在插入时被顶掉。"""
        self.assertIn("- **翻页上限 10 页。**", SKILL)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：第 1 页与深页的日期覆盖真的差一个数量级。"""

    def _by_page(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        f = ROOT / "users" / u / "job_scraper" / "seen_jobs.json"
        if not f.is_file():
            self.skipTest("没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        first = [0, 0]
        deep = [0, 0]
        for e in seen.values():
            if not isinstance(e, dict) or e.get("portal") != "liepin-search":
                continue
            fb = e.get("found_by") or ""
            if not fb:
                continue
            m = re.search(r"\bp(\d+)\s*$", fb)
            box = deep if (m and int(m.group(1)) >= 2) else first
            box[1] += 1
            if e.get("date"):
                box[0] += 1
        if first[1] < 100 or deep[1] < 100:
            self.skipTest("某一档样本太少，说明不了")
        return first, deep

    def test_both_buckets_still_have_dates_at_all(self):
        """**不再断言「第 1 页远高于深页」** —— 那个结论 2026-08-27 被推翻了
        （理由见模块开头）。现在只验一件还成立的事：两档都还拿得到日期，
        也就是 `date` 这个字段没有整个消失。它真消失了，
        「收到 14 天内」那条指令才是需要重新论证的。
        """
        first, deep = self._by_page()
        self.assertGreater(first[0], 0, "第 1 页一个带日期的都没有了")
        self.assertGreater(deep[0], 0, "深页一个带日期的都没有了")


if __name__ == "__main__":
    unittest.main()
