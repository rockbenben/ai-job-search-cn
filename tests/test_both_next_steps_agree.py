"""两个入口的「下一步」不许给相反的建议。

终端自检（`doctor.next_step`）和总览页（`build_dashboard.next_step`）是同一件事的
两个出口。用户看哪个都行，**但不能看到两条互相矛盾的**。

这个仓库已经在同一个地方栽过两次：

- 2026-08-13：手上 107 份材料没发，面板说「还有 107 个岗材料就绪但没投」，
  自检说「跑 /job-scrape 补充名单」。修法是给自检补 `ready` 分支。
- 2026-08-22：投了 85 个 0 回音，面板说「先停下来查，别接着投」，
  自检说「有 4 个『值得投』的材料备好了，先发这批」。**只改了面板那一份。**

两次都是「一条规则加在一个出口上，另一个出口照旧」。所以这里不测措辞——
两处措辞本来就该不同（一个进面板、一个进终端）——只测**结论指向哪儿**。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402
from datetime import date as _date  # noqa: E402
import export_web_data as ex  # noqa: E402
from _srcscan import code_of  # noqa: E402
import followups  # noqa: E402


def _doctor_says(**over):
    st = {"in_repo": True, "user": "u", "gaps": {},
          "scraped": 500, "ranked": 300, "materials": 60, "applied": 85,
          "ready": 62, "ready_strong": 4, "interviewing": 0, "offers": 0,
          "replied": 0, "decided": 54,
          "direct_decided": 22, "direct_replied": 0}
    st.update(over)
    return "\n".join(doctor.next_step({"node": True, "web_build": True}, st))


def _panel_says(**over):
    counts = {"applied": 85, "ready": 62, "ready_strong": 4, "interviewing": 0,
              "ranked": 300, "replied": 0, "decided": 54, "applied_months": [],
              "direct_decided": 22, "direct_replied": 0}
    counts.update(over)
    return bd.next_step(counts, True, top_ranked_url="u", n_sellable=9)[0]


class OneDateParserForEveryConsumer(unittest.TestCase):
    """人手填的台账里日期有四种写法，而三处各认各的。

    实测 2026-08-23，同一行 `2026.07.12`：

        /job-outcome followup（`followups.parse_date`）  四种全认 —— 判「该催了」
        会话自检（`doctor.parse_date`）                  只认两种 —— 这条不计入
        面板（`export_web_data.days_since`）             只认 ISO  —— 这条掉出统计

    两处的注释还都写着「同 `followups.parse_date`」。少认一种的后果是**静默的**：
    自检那边这条投递不进 `n_decided`（零回音警报的门槛、猎头/直招的分母都从它来），
    面板那边它掉出回音分桶、按分数段的回复率和直招分母 —— 三个数一起偏。

    正本是 `build_dashboard._days_since`（内部走 `followups.parse_date`，
    并为 `2026-08-21T10:00` 这种带时间的写法留了切前 10 位那一手）。
    面板改成 import 它；doctor 不许 import 仓库模块，只能持副本 —— 副本钉在这里。
    """

    #: 四种写法 + 一种带时间的。**都要认**。
    SAME_DAY = ("2026-08-01", "2026/08/01", "2026.08.01", "2026年8月1日")

    def test_the_canonical_parser_takes_all_four(self):
        for sfmt in self.SAME_DAY:
            with self.subTest(fmt=sfmt):
                self.assertEqual(followups.parse_date(sfmt),
                                 _date(2026, 8, 1), sfmt)

    def test_the_panel_side_takes_all_four(self):
        for sfmt in self.SAME_DAY:
            with self.subTest(fmt=sfmt):
                self.assertEqual(bd._days_since(sfmt, _date(2026, 8, 23)), 22,
                                 f"面板读不出 {sfmt}")

    def test_the_panel_side_still_takes_a_timestamp(self):
        """`2026-08-01T10:00` 这种写法不许被这次统一弄丢。"""
        self.assertEqual(bd._days_since("2026-08-01T10:00", _date(2026, 8, 23)), 22)

    def test_the_outcome_stats_use_that_parser(self):
        """`days_since` 曾经是同一个文件里的第二份实现 ——
        而同一份文件另一处早就写着「别另写一套」并 import 了正本。"""
        seg = code_of("tools/export_web_data.py", "def outcome_stats(")
        self.assertIn("_days_since(x, today)", seg, "又自己解析了一遍")
        self.assertNotIn("fromisoformat", seg, "还留着只认 ISO 的那一版")

    def test_doctors_copy_lists_the_same_formats(self):
        self.assertEqual(tuple(doctor.DATE_FORMATS),
                         tuple(followups._DATE_FORMATS),
                         "自检那份日期格式表和正本分叉了")

    def test_an_unreadable_date_is_never_guessed(self):
        """宽进到此为止：拿不准返回 None，不猜一个日期出来。"""
        for junk in ("", "下周", "2026-13-45", None):
            with self.subTest(v=junk):
                self.assertIsNone(followups.parse_date(junk))
                self.assertIsNone(bd._days_since(junk, _date(2026, 8, 23)))


class TheHeadhunterSplitIsJudgedTheSameWay(unittest.TestCase):
    """「其中 N 个投的是猎头代招 …… 但企业直招那 M 个也是一个回音都没有」——
    这句话是整段诊断的落点，而两处曾经算出不同的 N/M。

    实测活动用户 2026-08-23，同一份数据：

        自检   猎头 38 · 直招 38
        面板   猎头 43 · 直招 33

    总数都是 76，分法差 5 个。原因是 doctor 写的是
    `bool(e.get("isHeadhunter"))` —— **「字段不在」被算成「确认是直招」**，
    而且完全不看 `recruiter` 那条规则（招聘方叫「××猎头」时不管字段怎么写）。
    正本 `export_web_data.via_headhunter` 的 docstring 专门警告过这一件：
    「没判过 ≠ 判过是『不是』…返回 False 是给错误的信息」。

    往「企业直招」那个分母里掺没判过的岗，等于用没查过的数据加强一个结论。

    doctor 不许 import 仓库模块，所以判据是内联副本 —— 副本就得有人钉着。
    """

    CASES = [
        ({"recruiter": "某先生 · 猎头顾问"}, True, "招聘方名字里带「猎头」"),
        ({"recruiter": "某女士 · ××人力资源"}, True, "人力资源也是中介"),
        ({"recruiter": "某女士 · 招聘HR", "isHeadhunter": False}, False, "确认过的直招"),
        ({"isHeadhunter": True}, True, "字段说是"),
        ({"isHeadhunter": False}, False, "字段说不是"),
        ({}, None, "**没判过** —— 不许算成直招"),
        ({"recruiter": ""}, None, "空的招聘方名字也不构成判断"),
    ]

    def test_both_sides_answer_the_same(self):
        for entry, want, why in self.CASES:
            with self.subTest(why=why):
                self.assertIs(doctor._via_headhunter(entry), want, why)
                self.assertIs(ex.via_headhunter(entry), want,
                              f"正本和副本分叉了（{why}）")

    def test_the_word_lists_are_equal(self):
        self.assertEqual(tuple(doctor.AGENCY_WORDS), tuple(ex._AGENCY_WORDS),
                         "中介词表两边不一样了")

    def test_doctor_no_longer_coerces_missing_to_false(self):
        """**只扫代码**：那段 docstring 里逐字引着 `bool(e.get("isHeadhunter"))`。"""
        seg = code_of("tools/doctor.py", "def _via_headhunter(")
        self.assertNotIn('bool(entry.get("isHeadhunter"))', seg)
        self.assertIn("return None", seg, "没判过那一支不见了")

    def test_the_map_is_built_with_it(self):
        src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("hh = {e.get(\"url\"): _via_headhunter(e)", src,
                      "算了没用上 —— 那句话照旧按旧判据说")

    def test_unjudged_falls_out_of_both_buckets(self):
        """`None` 既不算猎头也不算直招。下游那句 `is_hh is False` 靠的就是这个。"""
        self.assertIsNot(doctor._via_headhunter({}), False)
        self.assertIsNot(doctor._via_headhunter({}), True)





class MoneyComesBeforeMorePractice(unittest.TestCase):
    """拿到 offer 那一刻，两个入口说的是相反的话。

    实测 2026-09-01，同一份状态（一个岗 offer 在手）：

        终端（`doctor.next_step`）   有 1 个 offer 在手 → /job-offer <公司>
        面板（`bd.next_step`）       有面试了，去备面   → /job-interview <公司>

    面板那条不认 offer：`_INTERVIEW_STATUSES` 把 `offer` 一起收了，
    流水线头顶那格于是把拿到 offer 的人算成「在面试」。

    **而同一个文件已经写过这条规则**，就在逐岗那条下一步里：

    > offer 要**先于** interview 判……拿到 offer 之后该做的是算可守区间、
    > 过背调红线、和别的 offer 比——那是 `/job-offer`，不是再练一轮面试题。
    > 这一步给错，用户就会在最该谈钱的时候去背题。

    一件事两个住址，规则只写进了其中一个 —— 而它错的那一格是全流程最该
    谈钱的那一步，也是面板上最显眼的那一行。
    """

    @staticmethod
    def _panel(**over):
        counts = {"applied": 85, "ready": 62, "ready_strong": 4,
                  "interviewing": 0, "offers": 0, "ranked": 300,
                  "replied": 0, "decided": 54, "applied_months": [],
                  "direct_decided": 22, "direct_replied": 0}
        counts.update(over)
        return bd.next_step(counts, True, top_ranked_url="u", n_sellable=9)

    def test_an_offer_sends_both_to_the_money_step(self):
        """offer 在手时，两边都得指向 /job-offer。"""
        panel_text, panel_cmd = self._panel(offers=1, interviewing=1)
        self.assertIn("/job-offer", panel_cmd)
        self.assertIn("/job-offer", _doctor_says(offers=1, interviewing=1))

    def test_neither_sends_him_to_practice_more_questions(self):
        """**这才是代价那一半。** 指错的那一步不是少说了什么，是多说了
        一句会把他带走的话 —— 最该谈钱的时候去背面试题。
        """
        _text, panel_cmd = self._panel(offers=1, interviewing=1)
        self.assertNotIn("/job-interview", panel_cmd)
        self.assertNotIn("/job-interview", _doctor_says(offers=1,
                                                        interviewing=1))

    def test_interviewing_without_an_offer_still_goes_to_practice(self):
        """反向支点：没 offer 时那条备面照旧 —— 别为了修这个把面试那支吃掉。"""
        _text, panel_cmd = self._panel(interviewing=1)
        self.assertIn("/job-interview", panel_cmd)
        self.assertIn("/job-interview", _doctor_says(interviewing=1))

    def test_an_old_counts_without_the_key_does_not_blow_up(self):
        """老调用方传的 counts 里没有这一格 —— 少一个键不该炸掉整块面板。"""
        counts = {"applied": 0, "ready": 0, "interviewing": 0, "ranked": 1,
                  "materials": 0, "scraped": 1}
        self.assertIsNotNone(bd.next_step(counts, True, top_ranked_url="u"))

    def test_the_web_export_feeds_that_branch_too(self):
        """**改在 `next_step` 里只落在单页版上。** 网页版自己建一份 counts
        （`export_web_data` 里那个），少了这一格，`counts.get("offers", 0)`
        恒为 0 —— 而用户看的正是网页版。

        同一个数两处各建一份，正是这次要修的形状本身；这一条钉的是
        「新加的那一格两边都建了」。
        """
        import export_web_data as ex
        self.assertIs(ex.OFFER_STATUSES, bd._OFFER_STATUSES,
                      "网页版又抄了一份 offer 状态，不是同一个集合")
        seg = code_of("tools/export_web_data.py", chr(34) + "applied" + chr(34)
                      + ": n_sent,")
        self.assertIn(chr(34) + "offers" + chr(34), seg.splitlines()[0],
                      "网页版那份 counts 里没有 offers 这一格")

    def test_the_offer_statuses_match(self):
        """**按值扫的守卫看不见这一对** —— `{"offer"}` 只有一个成员，
        `test_one_value_one_home` 的抽取器要 `len(v) >= 2`（单成员集合
        天然会撞，收进来全是噪音）。所以这一条只能手写，同
        `test_the_out_prefixes_match` 当初那一脚：名字不同，按名字扫的
        守卫看不见。
        """
        self.assertEqual(set(doctor.OFFER_STATUSES), set(bd._OFFER_STATUSES))

    def test_the_panel_counts_offers_from_the_record_not_from_practice(self):
        """练过面试题不等于拿到了 offer —— 那一格只认投递记录里的状态。"""
        line = code_of("tools/build_dashboard.py",
                       chr(34) + "offers" + chr(34) + ": sum(").splitlines()[0]
        self.assertIn('j["offer"]', line, "这一格不是从投递记录来的了")
        self.assertNotIn("interview_preps", line)


class TheBatchEntryIsHandedOver(unittest.TestCase):
    """「已排名、一个材料都还没出」时，两个出口都得给**一次敲完**的批量入口。

    这一支原来只给单岗链接 `/job-apply <url>`。理由是「排序结果写在机器读的
    文件里，人能看的只有总览页，所以他得先去挑一个」——**它对单岗成立，
    对这一支不成立**：这一支的条件是「有可投的已评岗没材料」，而用户不知道
    该做什么时问的是「我手上还有什么没做完的」，答案是一批。

    后果不是多敲一次：面板叫他一个一个敲，而他之所以在敲第 3 个，恰恰是因为
    他不知道有批量那条路。

    `test_both_next_steps_agree.py` 顶上把这个形状记成「已经栽过两次」。
    """

    @staticmethod
    def _panel(top=None, n_sellable=0, n_unranked=0):
        counts = {"applied": 0, "ready": 0, "ready_strong": 0, "interviewing": 0,
                  "offers": 0, "ranked": 120, "scraped": 543, "materials": 0,
                  "replied": 0, "decided": 0, "applied_months": [],
                  "direct_decided": 0, "direct_replied": 0}
        return bd.next_step(counts, True, top_ranked_url=top,
                            n_sellable=n_sellable, n_unranked=n_unranked)

    @staticmethod
    def _doctor(**over):
        st = {"in_repo": True, "user": "u", "gaps": {}, "scraped": 12,
              "ranked": 12, "materials": 0, "applied": 0, "ready": 0,
              "interviewing": 0, "offers": 0, "n_sellable": 0, "n_unranked": 0}
        st.update(over)
        return "\n".join(doctor.next_step({"node": True, "web_build": True}, st))

    def test_all_ranked_and_none_sellable_sends_both_to_restocking(self):
        """一个能投的都没有 → 两边都得指向 `/job-auto`，不是 `/job-apply` 也不是
        `/job-scrape`。

        `/job-scrape` 也不行：它抓完自动评分但**不出材料**，敲完还是一排没材料
        的岗——`test_the_next_step_is_the_spine.py` 顶上记的就是这件事，
        2026-10-14 面板那条「名单见底」的分支也一并改成了 `/job-auto`。
        """
        _text, panel_cmd = self._panel()
        self.assertEqual(panel_cmd, "/job-auto")
        said = self._doctor(scraped=12, ranked=12, materials=0, applied=0,
                            ready=0, n_sellable=0)
        self.assertIn("/job-auto", said, f"自检给的命令与面板不一致：{said}")
        self.assertNotIn("/job-apply", said, f"自检还在叫人去出材料：{said}")

    def test_some_sellable_left_sends_both_to_the_batch_entry(self):
        """反向支点：还有可投的 → 两边都指向一次敲完的批量入口。

        `AGENTS.md`「一条引导对应一条命令」：给 `--top` / `可以考虑` / `全部`
        三个里挑一个让用户选，那正是引导要替他省掉的一步。
        """
        _text, panel_cmd = self._panel(top="https://x/1", n_sellable=8)
        self.assertEqual(panel_cmd, "/job-apply 全部")
        said = self._doctor(scraped=12, ranked=12, materials=0, applied=0,
                            ready=0, n_sellable=8)
        self.assertIn("/job-apply 全部", said, f"自检还在一个一个教：{said}")

    def test_a_thin_shortlist_with_no_materials_still_restocks(self):
        """手上一个材料都没有、能投的只剩 2 个时，两个出口都该先补货。

        `doctor` 的补货分支原来只在 `ready > 0` 里面；`materials == 0` 那一支
        只看 `n_sellable == 0`，于是 1–4 个可投岗时会叫用户去 `/job-apply`，
        而面板同一时刻说的是 `/job-auto`。用户 2026-10-14 的裁定是
        **名单见底时补货优先于先发** —— 手上没有材料时同样成立。
        """
        _text, panel_cmd = self._panel(top="https://x/1", n_sellable=2)
        self.assertEqual(panel_cmd, "/job-auto")
        said = self._doctor(scraped=12, ranked=12, materials=0, applied=0,
                            ready=0, n_sellable=2)
        self.assertIn("/job-auto", said, f"自检没有先补货：{said}")
        self.assertNotIn("/job-apply", said,
                         f"自检在材料为零时叫用户去批量出材料：{said}")

    def test_an_unknown_count_does_not_trip_the_restock(self):
        """读不到那个数时**不许当成 0**——那是猜，而猜错的方向是「别发了，去抓」。

        判据只看**第一行**：用户只读第一行（`test_two_entry_points_agree.py`
        同一处写过这句）。「先把备好的用掉，名单见底了再去补货」那个收尾
        里本来就带着 `/job-auto`，所以不能拿它当「有没有触发补货」的证据。
        """
        said = self._doctor(scraped=12, ranked=12, materials=0, applied=0,
                            ready=0, n_sellable=None)
        first = said.splitlines()[0]
        self.assertNotIn("可以投的岗位只剩", first,
                         f"读不到那个数就被说成名单见底：{first}")


class RestockingOutranksSendingWhenTheListIsThin(unittest.TestCase):
    """**名单见底时，两个出口都要先说去补货，哪怕手上还有材料没投。**

    ## 这条是用户 2026-10-14 的裁定

    原话：「**还有材料没投的时候也会先说去补货。这是正确的**」。

    面板那一支 2026-08-13 就有（`build_dashboard.SHORTLIST_FLOOR` 那一支，
    立论是「补货的前置时间比名单见底的速度长」）。**终端没有**——于是
    「手上 14 份材料没投、能投的只剩 3 个」这个状态下，面板说去补货、
    自检说先把备好的发出去。

    ## 它不是推翻 2026-08-29 那条裁定

    「有材料没发 → 先发」前面多了一个前置判断：**名单还够不够**。
    够就照旧先发。正本在 `AGENTS.md`「跟进归用户，工具不催」那一节 ——
    **规则只活在一次会话里，换一轮就整条丢掉，这条规矩已经付过两次代价**。
    """

    @staticmethod
    def _panel(n_sellable):
        counts = {"applied": 9, "ready": 14, "ready_strong": 14, "ready_asked": 0,
                  "ready_old": 0, "expired_unsent": 0, "interviewing": 0,
                  "offers": 0, "ranked": 349, "scraped": 543, "materials": 23,
                  "replied": 2, "decided": 9, "applied_months": [],
                  "direct_decided": 4, "direct_replied": 1}
        return bd.next_step(counts, True, n_sellable=n_sellable, n_unranked=0)

    @staticmethod
    def _doctor(n_sellable, **over):
        st = {"in_repo": True, "user": "u", "gaps": {}, "scraped": 543,
              "ranked": 349, "materials": 23, "applied": 9, "ready": 14,
              "ready_strong": 14, "ready_asked": 0, "interviewing": 0,
              "offers": 0, "n_sellable": n_sellable, "n_unranked": 0}
        st.update(over)
        return "\n".join(doctor.next_step({"node": True, "web_build": True}, st))

    def test_both_restock_when_the_list_is_thin(self):
        """能投的少于门槛 → 两边都说补货，哪怕手上 14 份材料没投。"""
        p_text, p_cmd = self._panel(3)
        self.assertEqual(p_cmd, "/job-auto", f"面板这一支变了：{p_text}")
        self.assertIn("/job-auto", self._doctor(3), "自检还在叫人先发")

    def test_both_still_send_when_the_list_is_not_thin(self):
        """反向支点：名单还够 → 收窄别把「先发」一起吃掉。"""
        p_text, p_cmd = self._panel(bd.SHORTLIST_FLOOR)
        self.assertEqual(p_cmd, "/job-outcome <公司>", f"名单够却催补货：{p_text}")
        self.assertIn("/job-outcome", self._doctor(bd.SHORTLIST_FLOOR))

    def test_the_unranked_backlog_goes_to_rank_on_both_sides(self):
        """有待评积压时两边都先去评库存 —— `/job-scrape` 死循环就是从这儿漏的。"""
        counts = {"applied": 9, "ready": 14, "ready_strong": 14, "ready_asked": 0,
                  "ready_old": 0, "expired_unsent": 0, "interviewing": 0,
                  "offers": 0, "ranked": 349, "scraped": 543, "materials": 23,
                  "replied": 2, "decided": 9, "applied_months": [],
                  "direct_decided": 4, "direct_replied": 1}
        p_text, p_cmd = bd.next_step(counts, True, n_sellable=3, n_unranked=180)
        self.assertEqual(p_cmd, "/job-rank", f"面板这一支变了：{p_text}")
        self.assertIn("/job-rank", self._doctor(3, n_unranked=180))

    def test_doctors_floor_is_the_same_number(self):
        """`doctor` 不 import 仓库模块，所以门槛是一份**正当副本** ——
        相等由这一条钉住。同族：`QUIET_DAYS`、`AGENCY_WORDS`、`DATE_FORMATS`。

        两处各写一个数，就能一处触发一处不触发，而**这个差别正好落在
        「该不该先把备好的发出去」上**。
        """
        self.assertEqual(doctor.SHORTLIST_FLOOR, bd.SHORTLIST_FLOOR)

    def test_the_panel_survives_a_count_it_was_never_given(self):
        """`n_unranked` 的缺省值是 `None`，而 `next_step` 原来直接 `> 0`。

        **那是个 `TypeError`，不是一条难看的建议** —— 面板整页出不来。
        现有两个调用方都传了数，所以它一直藏着；2026-10-14 把
        「读不到就交回 None」的约定接到 `doctor` 那侧之后，
        `None` 变成了真实可达的值。

        判据是「不许炸」，不是「None 该走哪一支」——读不到就是读不到，
        不许拿它当 0 去催补货。
        """
        counts = {"scraped": 543, "ranked": 349, "materials": 23, "applied": 9,
                  "interviewing": 0, "offers": 0, "ready": 14, "ready_strong": 14,
                  "replied": 2, "decided": 9, "applied_months": [],
                  "direct_decided": 4, "direct_replied": 1}
        for n_sellable in (0, 3, None):
            with self.subTest(n_sellable=n_sellable):
                text, cmd = bd.next_step(dict(counts), True,
                                         n_sellable=n_sellable)
                self.assertTrue(text and cmd, f"这一格什么都没说：{text!r}")


class NobodyTellsYouToRecordAnApplicationYouDidNotSend(unittest.TestCase):
    """备好的**一个都发不出去**时，两个出口都不许把 `/job-outcome` 交出来。

    ## 这一条踩的是安全铁律，不是措辞

    `_ready_text` / `doctor` 那一支在 `ready_strong == 0` 时说的是
    「**别当群发名单**」——「可以考虑」按 `04` 的定义是「先问清楚关键信息再决定」。
    而两个出口原来都无条件把 `/job-outcome <公司>` 当成下一步：**前半句叫他别发，
    后半句叫他记一笔投递。**

    记一笔不是记个备忘：它写进 `job_search_tracker.csv`，往后回复率、漏斗、
    面试/offer 三条分支全从那一行长出来。`workflows/job-auto.md`
    「什么归机器，什么永远归人」那张表的判据是
    「**后果是不是只有用户承担**」——替用户认定「投出去了」正好是他承担。

    「有材料没发 → 先发」那条裁定（2026-08-29）的前提是备好的那些**发得出去**；
    一个都发不出去时，那个前提不成立。

    ## 该给的是什么

    那一档缺的是「投前必问」。`04` 规定**写不出来就说明它不属于这一档**
    （`job-apply.md` 补法表原话），所以 `/job-apply 可以考虑` 逼每个岗自己
    结一次案，而不是替他记一笔假的。都列了要问什么的话，那就没有命令可敲——
    人就在页面上，命令留空是诚实的。
    """

    @staticmethod
    def _panel(**over):
        counts = {"applied": 30, "ready": 30, "ready_strong": 0, "ready_asked": 3,
                  "ready_old": 0, "expired_unsent": 0, "interviewing": 0,
                  "offers": 0, "ranked": 120, "scraped": 300, "materials": 30,
                  "replied": 0, "decided": 5, "applied_months": [],
                  "direct_decided": 4, "direct_replied": 1}
        counts.update(over)
        return bd.next_step(counts, True, n_sellable=30, n_unranked=0)

    @staticmethod
    def _doctor(**over):
        st = {"in_repo": True, "user": "u", "gaps": {}, "scraped": 300,
              "ranked": 120, "materials": 30, "applied": 30, "ready": 30,
              "ready_strong": 0, "ready_asked": 3, "interviewing": 0,
              "offers": 0, "n_sellable": 30}
        st.update(over)
        return "\n".join(doctor.next_step({"node": True, "web_build": True}, st))

    def test_the_missing_questions_become_the_command(self):
        _text, panel_cmd = self._panel()
        self.assertEqual(panel_cmd, "/job-apply 可以考虑")
        self.assertIn("/job-apply 可以考虑", self._doctor())

    def test_neither_side_offers_to_record_an_unsent_application(self):
        """**这才是代价那一半。** 指错的那一步不是少说了什么。"""
        _text, panel_cmd = self._panel()
        self.assertNotIn("/job-outcome", panel_cmd or "",
                         "一边说「别当群发名单」一边叫他记一笔投递")
        self.assertNotIn("/job-outcome", self._doctor())
        self.assertNotIn("我投了", self._doctor(),
                         "这一档一个都还没发，那句「发完点一下我投了」是假的")

    def test_when_every_question_is_written_there_is_nothing_to_run(self):
        """都列了要问什么 → 没有命令可敲，命令留空是诚实的。"""
        _text, panel_cmd = self._panel(ready_asked=30)
        self.assertEqual(panel_cmd, "", "没有命令可敲时给了一条命令")
        self.assertNotIn("/job-outcome", self._doctor(ready_asked=30))

    def test_a_state_that_can_actually_be_sent_is_untouched(self):
        """反向支点：还有发得出去的 → 仍然「发出去 → 记一笔」。"""
        _text, panel_cmd = self._panel(ready_strong=17)
        self.assertEqual(panel_cmd, "/job-outcome <公司>")
        self.assertIn("/job-outcome", self._doctor(ready_strong=17))

    def test_an_old_snapshot_without_the_split_stays_on_the_old_answer(self):
        """`ready_strong` 拿不到时不能当成 0 —— 那是猜。

        `count_ready` 的约定一直是：读不到的数交回 `None`，调用方退回不分档的
        旧文案。把「不知道」读成「一个都发不出去」，方向正好是最坏的那个。
        """
        _text, panel_cmd = self._panel(ready_strong=None)
        self.assertEqual(panel_cmd, "/job-outcome <公司>")


class BothNextStepsAgree(unittest.TestCase):
    def test_the_alarm_threshold_has_one_value(self):
        """门槛是一个数。两处各写一个，就能一处触发一处不触发。"""
        self.assertEqual(doctor.NO_REPLY_ALARM, bd.NO_REPLY_ALARM)

    def test_the_silence_line_has_one_value(self):
        """静默线同理。`doctor` 不许 import 仓库内模块（它会被单独拷走跑），
        只能重抄一遍这个数——所以这里钉住它跟正本相等。"""
        self.assertEqual(doctor.QUIET_DAYS, followups.QUIET_DAYS,
                         "doctor 抄的静默线和 followups 正本不一致了")


    def test_a_single_reply_lets_both_move_on(self):
        """有一个回音就不是「全军覆没」了——两边都该放行，别一直卡在跟进上。

        没有这一条，上面那个测试用「永远说催跟进」也能过。
        """
        for who, said in (("自检", _doctor_says(replied=1)),
                          ("面板", _panel_says(replied=1))):
            with self.subTest(who=who):
                self.assertNotIn("一个回音都没有", said, f"{who}有回音了还在报警：{said}")



    def test_a_snapshot_without_the_split_does_not_guess(self):
        """老快照拆不出直招/猎头时 **不猜** —— 退回不分渠道的说法，别编一个数。"""
        for who, said in (("自检", _doctor_says(direct_decided=None)),
                          ("面板", _panel_says(direct_decided=None))):
            with self.subTest(who=who):
                self.assertNotIn("猎头", said, f"{who}在没数据时编了渠道结论：{said}")

    def test_waiting_applications_do_not_trip_the_alarm(self):
        """还在等的不算数。拿等待中的去算回复率，是把「还没到时候」说成「没人要你」。"""
        for who, said in (("自检", _doctor_says(decided=3)),
                          ("面板", _panel_says(decided=3))):
            with self.subTest(who=who):
                self.assertNotIn("一个回音都没有", said, f"{who}拿还在等的报了警：{said}")


if __name__ == "__main__":
    unittest.main()
