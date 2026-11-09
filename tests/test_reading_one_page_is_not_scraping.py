# -*- coding: utf-8 -*-
"""同一个文件里，一条说「勾着就抓」，一条说「每次都要问」。

`job-auto.md` 开头（2026-08-19 第二次裁定）：

> 现在**勾选框是唯一开关**；要临时不碰账号用 `--no-browser`。

而同一个文件「永远归人」那张表里留着一行：

> | **用登录态浏览器抓取** | 同「撞风控」——用的是他的账号 |

裁定改了开关的归属，这一行没跟着改。**一个流程里两条相反的规则，执行者只能挑一条。**

## 挑错那一次的代价

实测 2026-08-24：`/job-apply --top 20` 选出一个 BOSS 的岗、JD 取不到。
执行者照「永远归人」那一行停下来问用户要不要开浏览器 —— 而 `job-apply.md`
在同一件事上写得毫不含糊：

> **「JD 抓不到」不是需要用户输入的地方——是你还没用浏览器。**
> 跳过这一层直接记阻塞，等于把工作流已经给你的能力原样退还给用户。

用户当场纠正：**「除了猎聘 cli，其他都应该通过浏览器的，你不该问」**。

## 现在的边界

    归机器   用浏览器读一页（取 JD、确认岗位还在不在）—— 单页访问，密度远低于抓取
    归机器   勾着的那几家的抓取 —— 勾选框就是那个点头，密度由额度闸门管
    归人     取消勾选 / 把某一家勾回来 —— 那是「要不要用我的账号」这个决定本身

判据是**「点过的头不要再问第二遍」**，不是「碰不碰账号」。后者会把每一次页面
访问都变成一道闸门，而取数顺位里浏览器本来就是第 2 层 —— 除了猎聘有免登录接口，
其余三家只有这一条路。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def machine_table() -> str:
    i = AUTO.index("### 归机器（自动跑完，不要停下来问）")
    return AUTO[i:AUTO.index("### 永远归人", i)]


def human_table() -> str:
    i = AUTO.index("### 永远归人（碰到就停下来问，不许替他决定）")
    return AUTO[i:AUTO.index("## 停手条件", i)]


class TheTwoTablesDoNotContradict(unittest.TestCase):
    def test_browser_scraping_is_no_longer_always_the_humans(self):
        """**这一行就是那次问错的依据。** 它和开头那句「勾选框是唯一开关」打架。"""
        self.assertNotIn("| **用登录态浏览器抓取** |", human_table())

    def test_reading_one_page_is_on_the_machine_side(self):
        seg = machine_table()
        self.assertIn("**用浏览器读一页**", seg)
        self.assertRegex(flat(seg), r"取某个岗的 JD、确认它还在不在")

    def test_scraping_the_ticked_ones_is_on_the_machine_side(self):
        """勾选框就是那个点头 —— 已经点过的头不要再问第二遍。"""
        seg = flat(machine_table())
        self.assertRegex(seg, r"勾着的那几家的抓取")
        self.assertRegex(seg, r"已经点过的头不要再问第二遍")

    def test_the_humans_half_is_the_checkbox_decision(self):
        """归人的不是「用不用浏览器」，是「要不要用我的账号」这个决定本身。"""
        seg = flat(human_table())
        self.assertRegex(seg, r"取消勾选 / 把某一家勾回来")
        self.assertRegex(seg, r"做完这个决定之后\*\*怎么执行不再归他\*\*")

    def test_the_single_switch_sentence_survives(self):
        """归机器那两行建立在它上面 —— 它没了，这两行就没有出处。

        2026-08-25 抓取规则收口到 `job-scrape.md`（Step 0.4 是唯一正本）之后，
        整句留在那边；`job-auto.md` 只保留「勾选框是唯一开关」这半句和指针 ——
        两个文件各留一份整句，正是收口要消掉的形状。"""
        self.assertIn("勾选框是唯一开关", AUTO)
        self.assertIn("勾着的就抓，取消勾选的整家跳过", SCRAPE)

    def test_no_row_says_browser_use_needs_asking(self):
        """兜底：归人那张表里不许再出现「用浏览器」这类执行动作。

        判据是**动作 vs 决定**：表里该放的是「决定」（勾不勾、等多久、投不投），
        放进「怎么执行」就会把每一次页面访问都变成一道闸门。
        """
        for row in human_table().splitlines():
            if not row.startswith("| **"):
                continue
            with self.subTest(row=row[:40]):
                self.assertNotRegex(
                    row, r"\*\*[^*]*用[^*]*浏览器[^*]*抓取\*\*",
                    "归人表里又出现了一个执行动作")


class TheApplySideAlreadySaidIt(unittest.TestCase):
    """`job-apply.md` 在同一件事上一直是对的 —— 冲突的是 `job-auto.md` 那一行。"""

    def test_apply_says_it_is_not_a_question_for_the_user(self):
        self.assertRegex(
            flat(APPLY), r"「JD 抓不到」不是需要用户输入的地方——是你还没用浏览器")

    def test_apply_names_the_cost_of_skipping_the_browser(self):
        self.assertRegex(flat(APPLY),
                         r"等于把工作流已经给你的能力原样退还给用户")

    def test_apply_still_allows_a_real_block(self):
        """真够不着的还是要记阻塞 —— 这条改的是「不问」，不是「什么都自己上」。"""
        seg = flat(APPLY)
        self.assertRegex(seg, r"只有\*\*真的够不着\*\*才记阻塞")
        self.assertRegex(seg, r"需要登录而浏览器未登录|撞上反爬或验证码")


class TheReasonIsRecorded(unittest.TestCase):
    def _seg(self) -> str:
        i = AUTO.index("这张表原来有一行「用登录态浏览器抓取")
        return flat(AUTO[i:i + 1400])

    def test_it_names_the_two_rules_that_collided(self):
        seg = self._seg()
        self.assertIn("勾选框是唯一开关", seg)
        self.assertRegex(seg, r"一条说「勾着就抓」、一条说「每次都要问」")

    def test_it_carries_the_measured_incident(self):
        seg = self._seg()
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"/job-apply --top 20")

    def test_it_quotes_the_correction(self):
        """用户的原话留着 —— 转述会把「不该问」软化成「可以不问」。"""
        self.assertRegex(self._seg(),
                         r"除了猎聘 cli，其他都应该通过浏览器的，你不该问")

    def test_it_names_what_it_cost(self):
        self.assertRegex(self._seg(), r"用户被问了一个他早就答过的问题")


class TheOrderOfChannelsBacksItUp(unittest.TestCase):
    """「除了猎聘，其余只有浏览器这条路」不是我们的说法，是取数顺位写着的。"""

    def test_agents_puts_the_browser_second(self):
        i = AGENTS.index("### 取数渠道的顺位")
        seg = flat(AGENTS[i:i + 1800])
        self.assertRegex(seg, r"平台自己的公开 API")
        self.assertRegex(seg, r"你所在工具自带的浏览器能力")

    def test_agents_says_the_other_three_have_no_free_api(self):
        i = AGENTS.index("### 取数渠道的顺位")
        seg = flat(AGENTS[i:i + 1800])
        self.assertRegex(seg, r"这三家没有可用的免登录 API")

    def test_the_machine_row_cites_that_order(self):
        self.assertRegex(flat(machine_table()),
                         r"除了猎聘有免登录接口，其余三家本来就只有这条路")


if __name__ == "__main__":
    unittest.main()
