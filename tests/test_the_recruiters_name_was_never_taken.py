# -*- coding: utf-8 -*-
"""台账那一列 0/85 有值，而猎聘每次搜索都把那个名字递到手里、我们取错了字段。

`contact_person` 有四处在读，四处都在降级：跟进话术称呼「团队」而不是
「<姓>女士」——`job-outcome.md` 自己写着那正是「群发」和「专门找我」的分界。
补它的办法此前只有一条：**开口问用户**。

而猎聘搜索接口每张卡片都带一个 `recruiter` 对象，里面同时有：

    recruiterName    人          ← 从没取过
    recruiterTitle   角色标签     ← 一直取的是这个

实测样本 42 张卡片里 `recruiterTitle` 装的是**职务**：「猎头顾问」一个值就挂在
**16 个不同的 `recruiterId`** 上，还有「HRBP」「招聘专员」「研发总监」和 4 张空串。
同一个值挂在十几个人身上，它标的就不是人 —— 它既当不了跟进消息里的称呼，
也当不了外包硬门要的招聘主体名称。**推不出来的不是这个字段，是取错了字段。**

实测活动用户 2026-08-25：

    职位库 2637 个，来自猎聘搜索  2232（85%）
    已投 85 笔，来自猎聘搜索        66（78%）
    contact_person 填了             0 / 85

也就是说七成八本来就是白给的，却一直在问用户。

## 只吐姓，不吐全名

全名是第三方个人信息，而下游要它只为一句称呼。`job-outcome.md` 早就写死了
「只记姓 + 称呼就够，不要全名、不要电话、不要微信号」—— 所以截断放在
**最上游**（CLI 里），落了盘再脱敏等于赌后面每一层都记得脱一次。

非中文名一律返回 `null`：拉丁名分不出姓在前在后，猜错就是把全名原样吐出去。

## 顺带：写一句「谁在读它」会被数成一个读者

往 `job-scrape.md` 的字段价值表里加这一行的当天，那条审计报出来的读者数
从 4 变成 5 —— 多出来的正是那句话本身。第三次踩同一个坑（前两次是
`tracker.py` 和 `audit_pipeline.py` 自己）。
"""
import csv
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402
import _cli  # noqa: E402

CLI = ROOT / ".agents" / "skills" / "liepin-search"
HELPERS = (CLI / "cli" / "src" / "helpers.ts").read_text(encoding="utf-8")
SKILL = (CLI / "SKILL.md").read_text(encoding="utf-8")
URLREF = (CLI / "url-reference.md").read_text(encoding="utf-8")
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
OUT = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")
PORTALS = (ROOT / "workflows" / "reference"
           / "cdp-portals.md").read_text(encoding="utf-8")
AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?|//:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheParserTakesTheName(unittest.TestCase):
    def test_the_field_is_on_the_card(self):
        i = HELPERS.index("export interface LiepinJobCard {")
        self.assertIn("recruiterSurname: string | null",
                      HELPERS[i:HELPERS.index("\n}", i)])

    def test_the_search_path_fills_it_from_the_name(self):
        """**这是修掉的那一处。** 取的必须是 `recruiterName`，不是它旁边那个。"""
        self.assertIn("recruiterSurname: surnameOf(recruiter.recruiterName),",
                      HELPERS)

    def test_the_detail_path_says_why_it_is_null(self):
        """详情页不带这个对象 —— 和它旁边那几个 null 同因，别让人以为是漏了。"""
        i = HELPERS.index("    recruiterSurname: null,")
        self.assertRegex(flat(HELPERS[max(0, i - 300):i]), r"详情页不带招聘者对象")

    def test_the_old_field_is_still_taken(self):
        """`recruiterTitle` 是既有契约的一部分，这一条是加的，不是换的。"""
        self.assertIn("recruiterTitle: str(recruiter.recruiterTitle),", HELPERS)


class ItRefusesToEmitAFullName(unittest.TestCase):
    """**全名一次都不许出现在输出里。** 这是这条改动的边界。"""

    def _doc(self) -> str:
        i = HELPERS.index("export function surnameOf(")
        return flat(HELPERS[max(0, i - 1600):i])

    def test_the_reason_is_recorded(self):
        d = self._doc()
        self.assertRegex(d, r"本 CLI 不输出全名")
        self.assertRegex(d, r"落了盘再脱敏，等于赌后面每一层都记得脱一次")

    def test_it_cites_the_rule_it_obeys(self):
        self.assertRegex(self._doc(), r"只记姓 \+ 称呼就够，不要全名")

    def test_that_rule_still_exists(self):
        self.assertRegex(
            flat(OUT),
            r"\*\*只记姓 \+ 称呼就够\*\*.{0,80}不要全名、不要电话")

    def test_a_latin_name_returns_null(self):
        """拉丁名分不出姓在前在后 —— 猜错就是把全名原样吐出去。"""
        i = HELPERS.index("export function surnameOf(")
        body = HELPERS[i:HELPERS.index("\n}", i)]
        self.assertIn("[一-鿿]", body)
        self.assertRegex(self._doc(), r"非中文名一律 `null`")

    def test_it_never_returns_more_than_two_characters(self):
        """现算：照着源码里那份复姓表，最长就是两个字。"""
        i = HELPERS.index("const COMPOUND_SURNAMES = new Set([")
        block = HELPERS[i:HELPERS.index("])", i)]
        names = re.findall(r'"([^"]+)"', block)
        self.assertTrue(names)
        self.assertEqual([n for n in names if len(n) != 2], [],
                         "复姓表里混进了不是两个字的条目")

    def test_the_compound_list_says_it_is_deliberately_partial(self):
        """不求全是个决定，不是疏漏 —— 不写下来，下一个人会去补那八十条。"""
        i = HELPERS.index("const COMPOUND_SURNAMES = new Set([")
        self.assertRegex(flat(HELPERS[max(0, i - 500):i]), r"不求全")


class TheContractSaysSo(unittest.TestCase):
    def test_the_skill_lists_the_field(self):
        """钉的是**那份字段清单**，不是「全文出现过」。

        只判后面那段解释也能绿 —— 而调用方读的是清单：清单里没有，
        它就不知道有这个键可取。变异实测过（把清单里那一项删掉，
        原来的写法一声不响）。
        """
        i = SKILL.index("搜索结果每条包含契约字段")
        listing = SKILL[i:SKILL.index("缺失值一律为 `null`", i)]
        self.assertIn("`recruiterSurname`", listing)

    def test_the_skill_says_it_is_not_the_title(self):
        """两个字段挨着，名字也像 —— 不点破，下一个人还会取错那个。"""
        i = SKILL.index("`recruiterSurname` 是跟你说话的那个人的")
        seg = flat(SKILL[i:i + 900])
        self.assertRegex(seg, r"它和 `recruiterTitle` \*\*不是一回事\*\*")
        self.assertRegex(seg, r"同一个值会挂在几十个不同的招聘者身上")
        self.assertRegex(seg, r"那是角色，不是人")

    def test_the_skill_says_detail_does_not_have_it(self):
        i = SKILL.index("详情页本身")
        self.assertIn("recruiterSurname", SKILL[max(0, i - 200):i])

    def test_the_url_reference_maps_it(self):
        row = next(l for l in URLREF.splitlines()
                   if l.startswith("| `recruiterSurname`"))
        self.assertIn("recruiter.recruiterName", row)
        self.assertIn("不输出全名", row)

    def test_the_old_row_survives(self):
        self.assertIn("| `recruiterTitle` | `recruiter.recruiterTitle` |", URLREF)


class TheScraperStoresIt(unittest.TestCase):
    """CLI 吐出来没人存，等于没取（这个仓库为此付过一次学费，就在同一节）。"""

    def test_the_schema_has_it(self):
        """锚在那一节的标题上 —— `"seen"` 在这份文件里出现三次。"""
        i = SCRAPE.index("### ⚠️ 打分要用的字段，抓到了就必须存下来")
        j = SCRAPE.index('"recruiterSurname"')
        self.assertLess(j, i, "字段没写在那一节上面的 schema 例子里")

    def test_the_value_table_names_who_waits_for_it(self):
        row = next(l for l in SCRAPE.splitlines()
                   if l.startswith("| `recruiterSurname` |"))
        self.assertIn("contact_person", row)
        self.assertIn("/job-outcome followup", row)
        self.assertIn("/job-interview", row)

    def test_that_row_says_what_it_costs(self):
        row = next(l for l in SCRAPE.splitlines()
                   if l.startswith("| `recruiterSurname` |"))
        self.assertRegex(flat(row), r"「群发」和「专门找我」的分界")
        self.assertIn("三处一起降级", row)

    def test_the_lesson_that_section_already_taught_survives(self):
        """「打分要用的字段，抓到了就必须存下来」—— 这一条建立在它上面。"""
        self.assertIn("### ⚠️ 打分要用的字段，抓到了就必须存下来", SCRAPE)


class TheOutcomeStepFetchesBeforeAsking(unittest.TestCase):
    def _seg(self) -> str:
        i = OUT.index("### 顺手把对方的姓名记下来（`contact_person` 列）")
        return flat(OUT[i:OUT.index("**为什么值得多问这一句：**", i)])

    def test_it_reads_the_library_first(self):
        s = self._seg()
        self.assertRegex(s, r"\*\*先去库里取，取不到才问。\*\*")
        self.assertIn("recruiterSurname", s)

    def test_it_says_not_to_ask_when_it_has_the_value(self):
        self.assertRegex(self._seg(), r"直接填 `<姓>`，不要问")

    def test_it_says_why_asking_would_be_wrong(self):
        self.assertRegex(self._seg(), r"让他抄一个我们手里已经有的字")

    def test_the_fallback_question_survives(self):
        """别的渠道没有这个字段 —— 问那一句还得留着。"""
        self.assertRegex(self._seg(), r"取不到（别的渠道、或那张卡片没给）才问")
        self.assertIn("这个岗在聊天框里跟你说话的是谁？", OUT)

    def test_it_still_refuses_to_change_the_status(self):
        """这一步是可选补充，不是必答题 —— 那条边界一个字不许动。"""
        self.assertRegex(flat(OUT), r"\*\*这一步不许改 `status`\*\*")


class TheFalseClaimIsRetracted(unittest.TestCase):
    """「只有这一个推不出来」——那句话是错的，而它正是「所以只能问」的全部依据。"""

    def test_the_claim_no_longer_stands(self):
        """**自引陷阱。** 撤回的那段自己引了那句话 —— 直接 `assertNotIn` 会红。

        所以判的是**它只许以被引用的形式活着**：全文恰好出现一次，
        且那一次落在撤回块里（形状同 `test_the_old_punt_is_gone`）。
        """
        self.assertEqual(OUT.count("只有这一个推不出来"), 1,
                         "它又作为一句生效的说明出现了")
        i = OUT.index("只有这一个推不出来")
        self.assertIn("这一节原来接着写", OUT[max(0, i - 40):i])

    def test_the_retraction_is_written_down(self):
        i = OUT.index("这一节原来接着写「只有这一个推不出来")
        seg = flat(OUT[i:i + 1400])
        self.assertRegex(seg, r"那句话是错的，2026-08-25 删掉了")
        self.assertRegex(seg, r"推不出来的不是这个字段，是取错了字段")

    def test_the_retraction_carries_the_numbers(self):
        i = OUT.index("这一节原来接着写「只有这一个推不出来")
        seg = flat(OUT[i:i + 1400])
        self.assertIn("recruiterSurname", seg)

    def test_the_other_six_columns_are_still_excused(self):
        """那一段里「另外 6 个空列不在这里问」是对的，别连着一起删。"""
        self.assertRegex(flat(OUT), r"台账另外 6 个空列不在这里问")
        self.assertIn("compIndustry", OUT)


class ThePortalTableNamesTheRightField(unittest.TestCase):
    def _row(self) -> str:
        return next(l for l in PORTALS.splitlines()
                    if l.startswith("> | `recruiter` |"))

    def test_it_admits_it_named_the_wrong_field(self):
        r = flat(self._row())
        self.assertRegex(r, r"\*\*那是指错了字段\*\*")
        self.assertIn("2026-08-25", r)

    def test_it_says_why_the_title_could_never_work(self):
        r = flat(self._row())
        self.assertRegex(r, r"既当不了外包硬门要的招聘主体名称，也当不了跟进消息里的称呼")

    def test_it_names_the_field_that_does(self):
        self.assertIn("recruiterName", self._row())
        self.assertIn("recruiterSurname", self._row())

    def test_the_warning_above_the_table_survives(self):
        """「页面上有」不等于「库里有」—— 这张表整个建立在那句话上。"""
        self.assertIn("**「页面上有」不等于「库里有」。这张表说的是前者。**", PORTALS)


class WritingWhoReadsItDoesNotMakeYouAReader(unittest.TestCase):
    """第三次踩同一个坑：一句「谁在读它」被数成了一个读者。"""

    def test_the_producer_doc_is_excluded(self):
        i = AUDIT.index('if x.name not in ("tracker.py", "audit_pipeline.py"')
        self.assertIn('"job-scrape.md"', AUDIT[i:i + 160])

    def test_the_three_reasons_are_each_written(self):
        i = AUDIT.index("# **排除三个「写它的人」")
        seg = AUDIT[i:AUDIT.index("srcs = [x for x in", i)]
        for w in ("tracker.py", "audit_pipeline.py", "job-scrape.md"):
            with self.subTest(w=w):
                self.assertIn(w, seg)
        self.assertRegex(flat(seg), r"报出来的读者立刻从 4 变成 5")

    def test_the_reported_readers_are_all_real(self):
        """现算：报出来的每个文件都不许是「只写了列名的说明」。"""
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_tracker_columns_nobody_fills({}, {})
        if not got:
            self.skipTest("没有触发")
        msg = got[0][2]
        for bad in ("job-scrape.md", "audit_pipeline.py", "tracker.py"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, msg)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那一列真的还空着，而猎聘真的占了他大半个库。"""

    def _user(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        return user_or_skip()

    def test_the_column_is_still_empty(self):
        """**填上之后这条会 skip。** 那时把上面的实测数更新掉，别删了它。"""
        f = ROOT / "users" / self._user() / "job_search_tracker.csv"
        if not f.is_file():
            self.skipTest("还没有投递记录")
        rows = list(csv.DictReader(f.open(encoding="utf-8-sig")))
        n = sum(1 for r in rows if (r.get("contact_person") or "").strip())
        if n:
            self.skipTest(f"已经填了 {n}/{len(rows)} —— 那条链路开始生效了")
        self.assertEqual(n, 0)

    def test_liepin_search_supplies_most_of_the_library(self):
        """**这是整条的支点。** 猎聘占比很小时，改它的 CLI 换不来什么。"""
        user = self._user()
        f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
        if not f.is_file():
            self.skipTest("还没抓过职位")
        seen = _cli.seen_of(_cli.load_json_stamped(f)[0])
        if len(seen) < 200:
            self.skipTest("库太小")
        n = sum(1 for e in seen.values()
                if isinstance(e, dict) and e.get("portal") == "liepin-search")
        self.assertGreater(n, len(seen) * 0.5,
                           f"猎聘搜索只占 {n}/{len(seen)} —— 这一节的论点要重看")

    def test_the_title_field_would_not_have_helped(self):
        """**它标的是角色，不是人** —— 判据是同一个值挂在好几个人身上。

        「取值看着像职务」是肉眼判断，机器判不了；而「一个 `recruiterTitle`
        对应 N 个不同的 `recruiterId`」是能算的，而且正是「它不是人名」
        这句话的定义。
        """
        fx = (CLI / "cli" / "tests" / "fixtures" / "search-response.json")
        if not fx.is_file():
            self.skipTest("没有抓取样本")
        raw = json.loads(fx.read_text(encoding="utf-8"))
        cards = raw["data"]["data"]["jobCardList"]
        by = {}
        for c in cards:
            r = c.get("recruiter") or {}
            t, rid = r.get("recruiterTitle"), r.get("recruiterId")
            if t and rid:
                by.setdefault(t, set()).add(rid)
        self.assertTrue(by, "样本里一个 recruiterTitle 都没有")
        most = max(len(v) for v in by.values())
        self.assertGreaterEqual(
            most, 5,
            f"最多只有 {most} 个人共用同一个 recruiterTitle —— "
            f"它开始像人名了，这一节的论点要重看")

    def test_the_name_field_is_there_to_take(self):
        fx = (CLI / "cli" / "tests" / "fixtures" / "search-response.json")
        if not fx.is_file():
            self.skipTest("没有抓取样本")
        raw = json.loads(fx.read_text(encoding="utf-8"))
        cards = raw["data"]["data"]["jobCardList"]
        has = [c for c in cards if (c.get("recruiter") or {}).get("recruiterName")]
        self.assertEqual(len(has), len(cards), "有卡片没带 recruiterName")


if __name__ == "__main__":
    unittest.main()
