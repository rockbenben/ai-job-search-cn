# -*- coding: utf-8 -*-
"""猎聘 CLI 给了五个原生筛选参数，而工作流从来没说过传不传 —— 传了会静默丢掉 8%。

`liepin-search/SKILL.md` 列着 `--edu` / `--years` / `--salary` / `--industry` /
`--comp-scale`，`job-scrape.md` 却只讲过 `--jobage`。这五个看起来是白捡的效率：
少抓一批不合适的，省额度、省评分。**而额度正是这套系统里最稀缺的东西**
（撞过限流、封过 9 小时、一天发过 926 次请求），所以下一个执行者迟早会去捡。

实测活动用户 2026-08-24，库里 2638 个岗，把「传了会排掉什么」逐个算出来：

    --edu（按本科）      排掉 283 个要求硕士/博士的  其中 24 个（8%）本来评到可投三档
    --industry（锁行业） 排掉 225 个行业字段为空的   其中 57 个能投；可投三档横跨 68 个行业
    --comp-scale        排掉 319 个规模字段为空的   其中 68 个能投
    --salary            排掉 31 个面议/空的         其中 5 个能投

第三列全是**静默损失**：不是「少看几个烂岗」，是「有几个能投的你永远不会知道」。
空值那几行尤其要命 —— 字段没填不等于不合适，服务端一律当不合适。

## 为什么这不是「多一层过滤更省事」

`prescreen.py` 早就量过同一个字段：`eduLevel` 与 JD 正文 **58% 对不上**，
所以它只肯**降权泊车**、不肯据此判死。同一个字段拿到服务端去用，等于把一个
58% 不准的判据升级成一票否决，而且**看不见** —— 客户端泊车还能回头翻，
服务端排掉的从来没进过库。

还有第三条，纯机械的：这几个参数收的是猎聘的筛选码，值不合法时接口返回
`flag !== 1`，**和限流长得一模一样**。而本仓库撞见限流就记额度封控 ——
一个拼错的筛选码能把整家停 24 小时。

## 例外只有两个，判据是「客观事实 vs 判断」

`--location`（CLI 里必填）和 `--jobage`。它们过滤的是城市和发布时间 ——
客观事实，不是「这个岗要不要得起你」那种判断。判断留在客户端：
那里有泊车、有回收、有 JD 正文。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
SKILL = (ROOT / ".agents" / "skills" / "liepin-search"
         / "SKILL.md").read_text(encoding="utf-8")
CLI_TS = (ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "src"
          / "cli.ts").read_text(encoding="utf-8")
PRESCREEN = (ROOT / "tools" / "prescreen.py").read_text(encoding="utf-8")

#: 服务端筛选码 —— 这五个不许传进求职流程。
FILTERS = ("--edu", "--years", "--salary", "--industry", "--comp-scale")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheRuleLandsWhereTheDecisionIsMade(unittest.TestCase):
    """规则要写在执行者读的那一步，不是只写在 CLI 的参数表里。"""

    def _seg(self) -> str:
        i = SCRAPE.index("其余原生筛选参数一律不传")
        return flat(SCRAPE[i - 200:i + 2600])

    def test_the_scrape_workflow_says_it(self):
        self.assertRegex(
            self._seg(),
            r"\*\*除了「城市」和「多久之内」，其余原生筛选参数一律不传。\*\*")

    def test_it_names_all_five(self):
        seg = self._seg()
        for f in FILTERS:
            with self.subTest(f=f):
                self.assertIn(f, seg, f"{f} 没被点名，下一个人照样会传")

    def test_it_says_why_they_look_tempting(self):
        """不写「它看起来对」，规则读起来就像洁癖。"""
        seg = self._seg()
        self.assertRegex(seg, r"看起来是白捡的效率")
        self.assertRegex(seg, r"省额度、省评分")

    def test_the_two_exceptions_have_a_criterion(self):
        """列白名单不够 —— 下一个新参数进来时要判得出该不该放。"""
        seg = self._seg()
        self.assertRegex(seg, r"`--location` 是例外")
        self.assertRegex(seg, r"它们过滤的是\*\*客观事实\*\*")
        self.assertRegex(seg, r"判断留在客户端")


class TheNumbersAreThere(unittest.TestCase):
    def _seg(self) -> str:
        i = SCRAPE.index("其余原生筛选参数一律不传")
        return SCRAPE[i:i + 2600]

    def test_the_table_carries_all_four_rows(self):
        seg = flat(self._seg())
        for f in ("--edu", "--industry", "--comp-scale", "--salary"):
            with self.subTest(f=f):
                self.assertIn(f, seg, f"{f} 没有包含在分析中")

    def test_it_reports_the_loss_not_just_the_saving(self):
        """只报「排掉多少个」是在夸这个参数好用。要报它连带杀掉几个。"""
        seg = flat(self._seg())
        self.assertRegex(seg, r"其中本来评到「可以投」三档的|静默损失")

    def test_it_names_the_industry_spread(self):
        """「锁行业」最像常识，所以要给出客观说明。"""
        self.assertRegex(flat(self._seg()), r"可投.*行业|跨.*行业")

    def test_it_calls_the_loss_silent(self):
        seg = flat(self._seg())
        self.assertRegex(seg, r"\*\*静默损失\*\*")
        self.assertRegex(seg, r"有几个能投的\s*你永远不会知道"
                              r"|有几个能投的你永远不会知道")

    def test_it_carries_the_date_and_the_corpus_size(self):
        seg = flat(self._seg())
        self.assertIn("服务端过滤", seg)


class TheThreeReasonsAreDistinct(unittest.TestCase):
    def _seg(self) -> str:
        i = SCRAPE.index("其余原生筛选参数一律不传")
        return flat(SCRAPE[i:i + 2600])

    def test_no_parking_no_recovery(self):
        seg = self._seg()
        self.assertRegex(seg, r"服务端过滤没有泊车、也没有回收")
        self.assertRegex(seg, r"\*\*从来没进过库\*\*")

    def test_the_field_is_a_display_value(self):
        seg = self._seg()
        self.assertRegex(seg, r"列表页那几个字段是展示值，不是 JD 的真实要求")
        self.assertRegex(seg, r"58% 对不上")

    def test_a_bad_code_looks_like_a_rate_limit(self):
        """这条最机械，也最容易被当成小事 —— 它能把整家停 24 小时。"""
        seg = self._seg()
        self.assertRegex(seg, r"传错值会伪装成限流")
        self.assertRegex(seg, r"停 24 小时")

    def test_the_58_percent_claim_traces_to_prescreen(self):
        """引了别处的数就要引得到 —— 出处没了这条就成了传说。"""
        self.assertIn("58%", PRESCREEN,
                      "prescreen 里那个 58% 不见了，job-scrape 引的是空气")


class TheSkillDocPointsBack(unittest.TestCase):
    """执行者也可能只读 SKILL 的参数表就动手。"""

    def _row(self) -> str:
        i = SKILL.index("猎聘原生筛选码")
        return flat(SKILL[i - 120:i + 700])

    def test_the_row_warns(self):
        self.assertRegex(self._row(), r"求职流程里不要传这五个")

    def test_it_names_where_the_full_account_is(self):
        self.assertIn("job-scrape.md", self._row())

    def test_it_does_not_call_the_cli_broken(self):
        """参数本身没毛病，是这条流程不该用 —— 别把它写成 bug，
        否则下一个人会去「修」CLI。"""
        self.assertRegex(self._row(), r"接口本身没问题")


class TheFiltersReallyExist(unittest.TestCase):
    """规则禁的是真存在的东西 —— 参数改名了这条要跟着改。"""

    def test_the_cli_still_takes_them(self):
        for f in FILTERS:
            with self.subTest(f=f):
                self.assertIn(f, CLI_TS, f"CLI 里没有 {f} 了，规则该跟着改")

    def test_location_and_jobage_still_exist(self):
        for f in ("--location", "--jobage"):
            with self.subTest(f=f):
                self.assertIn(f, CLI_TS)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时把那张表重算一遍。数变了要重量，不是改注释。"""

    #: 可投的那三档。**切片 `_cli.VERDICTS`，不要在这儿再抄一份** ——
    #: 抄一份就多一个会跟正本分叉的地方，`test_shared_vocab_single_source` 拦这个。
    SELL = _cli.VERDICTS[:3]

    def _seen(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        f = ROOT / "users" / u / "job_scraper" / "seen_jobs.json"
        if not f.is_file():
            self.skipTest("没有职位库")
        seen = _cli.seen_of(json.loads(f.read_text(encoding="utf-8")))
        if len(seen) < 500:
            self.skipTest("语料太小，比例说明不了问题")
        return seen

    def _sellable(self, v) -> bool:
        return any(s in (v.get("rank_verdict") or "") for s in self.SELL)

    def test_a_degree_filter_would_still_kill_real_candidates(self):
        seen = self._seen()
        hi = [v for v in seen.values() if (v.get("eduLevel") or "") in ("硕士", "博士")]
        if not hi:
            self.skipTest("这份库里没有要求硕士/博士的岗")
        good = sum(1 for v in hi if self._sellable(v))
        self.assertGreater(
            good, 0,
            f"要求硕士/博士的 {len(hi)} 个岗里一个能投的都没有了 —— "
            f"「传 --edu 会杀掉 8%」不再成立，重新量一次再决定要不要放开")

    def test_an_empty_field_is_not_an_unsuitable_job(self):
        """服务端过滤会把「字段没填」一并排掉 —— 这条守着那批的价值。"""
        seen = self._seen()
        for field in ("compIndustry", "compScale"):
            with self.subTest(field=field):
                blank = [v for v in seen.values() if not (v.get(field) or "").strip()]
                if not blank:
                    self.skipTest(f"{field} 没有空值")
                good = sum(1 for v in blank if self._sellable(v))
                self.assertGreater(
                    good, 0,
                    f"{field} 为空的 {len(blank)} 个岗里没有一个能投 —— "
                    f"那「空值不等于不合适」这句要重说")

    def test_the_sellable_ones_span_many_industries(self):
        """锁行业最像常识 —— 这条把「常识」按住。"""
        seen = self._seen()
        inds = {(v.get("compIndustry") or "").strip()
                for v in seen.values() if self._sellable(v)}
        inds.discard("")
        if not inds:
            self.skipTest("还没有可投的岗")
        self.assertGreater(
            len(inds), 10,
            f"可投的岗只落在 {len(inds)} 个行业里 —— 锁行业的代价没那么大了，"
            f"那条规则要重新论证")


class TheOlderScrapeRulesSurvive(unittest.TestCase):
    def test_the_jobage_page_depth_rule_is_intact(self):
        """**这条 2026-08-27 被实测推翻了，这里跟着改成验新写法。**

        原来验的是「第 1 页可以带 `--jobage`，往后翻就不带」。那条规则建立在
        「深页的卡片几乎都没日期」（2026-08-23 实测 1%）上，而同日一轮
        `/job-auto` 从同一个 CLI 抓的前 2 页 **140/140 全部带日期**——
        前提没了，结论也就没了。详见
        `test_the_age_filter_empties_deep_pages.py` 的模块说明。

        **这是第三处抄件。** 同一条规则写在 `job-scrape.md`、
        `liepin-search/SKILL.md` 和这里，改的时候三处都要跟上。
        """
        seg = flat(SCRAPE)
        self.assertRegex(seg, r"翻页时照常可以传 `--jobage`")
        self.assertRegex(seg, r"被实测推翻")

    def test_the_dropped_no_date_rule_is_intact(self):
        self.assertIn("droppedNoDate", SCRAPE)

    def test_the_twenty_per_call_rule_is_intact(self):
        self.assertIn("每次调用**收到 20 条左右**", SCRAPE)

    def test_the_format_json_rule_is_intact(self):
        self.assertIn("`--format json`", SCRAPE)

    def test_prescreen_still_only_parks_on_education(self):
        """客户端那条判据不能因为这次改动被顺手收紧成判死。"""
        self.assertIn("只能**降权泊车**", PRESCREEN)


if __name__ == "__main__":
    unittest.main()
