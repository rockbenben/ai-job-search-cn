# -*- coding: utf-8 -*-
"""流程每轮都要问「谁还没处理」，而两个问题都没有工具回答——于是手写脚本，一手就错。

2026-08-25 一次 `/job-auto` 里，同一个形状犯了两次：

## 一、拿浏览器补 JD 时手挑目标

`fetch_details.py` 只抓猎聘 CLI 那条，其余渠道只报**数量**（「另有 335 个够不着」）。
执行者手里没有名单，就自己去 `seen_jobs.json` 里挑 —— 漏掉了 `user_state.json`
那层叠加：**库里 `ranked`、用户在面板上已标不投的岗，看起来完全够格。**
抓完才发现那个岗早就深评过（值得投 62）且被标了不投。当时四家渠道每家只剩
个位数动作额度，那两次动作是这一轮唯一能用在别处的额度。

## 二、判断「还有没有可投但没材料的岗」时用了公司名

`job-apply.md` 第 0 步写着**从面板快照（`users/<活动用户>/job_scraper/
dashboard/data.json`）按七条挑，不要照着 `seen_jobs.json` 自己再筛一遍**。
执行者跳过那七条，自己写脚本拿**公司名前缀**
匹配材料目录名，两次报出「有 16 个 / 4 个没材料」，真值是 **0**。
错在键：这个库 54% 的岗雇主名是脱敏串（`某国内大型…公司`），
`_cli.is_anonymous_employer` 的说明原话是「凡是拿公司名当键去匹配、分组、去重的都错」。

两条的修法是同一条：**每轮都要问的问题，要有工具回答，工作流里点名那条命令。**
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import fetch_details as FD  # noqa: E402

RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")


class TheBrowserWorklistExists(unittest.TestCase):
    def test_the_tool_offers_it(self):
        self.assertTrue(hasattr(FD, "browser_todo"), "没有浏览器待办名单这个函数")
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        self.assertIn("--browser-list", src, "名单没有命令行入口，等于没有")

    def test_the_workflow_names_the_command(self):
        self.assertIn("--browser-list", RANK,
                      "工作流没点名这条命令 —— 下一个人还是会自己去库里挑")
        self.assertIn("不要自己去 `seen_jobs.json` 里挑", RANK,
                      "没写清禁的是什么，只给命令拦不住手挑")

    def test_the_list_is_the_only_source_of_urls(self):
        """**工具挡不住手敲一个它没列的地址，只有规矩能。**

        实测 2026-08-26（加了 `--browser-list` 的第二天）：执行者跑了名单、
        挑够前四个，第五个凭前一天抓取的记忆敲了 URL —— 那个岗早就评过
        （值得投 60）且用户已标不投，工具把它排除得好好的。
        所以工作流必须写死「不在名单里的一个都不开」，并点名
        「我记得昨天抓到过」这个非法来源。
        """
        self.assertIn("不在名单里的一个都不开", RANK)
        self.assertIn("不是合法来源", RANK,
                      "没点名「凭记忆敲 URL」这条路，下一个人还会走")

    def test_a_jd_read_in_the_browser_gets_stored(self):
        """浏览器读来的正文只活在那一次访问里 —— 不落库，下一步要重花一次额度。

        实测 2026-08-26：全库 80 个「可以投」的岗里 35 个查不到 JD 正文，而判词
        来源全写着「读过 JD 正文」——**读是读了，没存**。同一天评出来的 4 个可投岗，
        四份 JD 都在浏览器里读过、落库 0 份，到出材料那一步四个全得重读，
        而额度那时正好用完了。

        `job-scrape.md` Step 4.5 管的是抓取那一趟；评分时这一趟在它覆盖之外，
        所以规则要写在 `job-rank.md` 补 JD 那一节里。
        """
        self.assertIn("当场存进详情库", RANK, "没写「读到就存」")
        self.assertIn("jd_store.py --import-from", RANK, "没给落库的命令")
        self.assertIn("再花一次额度", RANK, "没说清不存的代价是什么")

    def test_the_filter_is_shared_not_copied(self):
        """名单与计数必须共用一份过滤，两份迟早分叉（本仓库反复付过的学费）。"""
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        self.assertIn("def _missing_alive(", src, "过滤没有正本")
        i = src.index("def browser_todo(")
        seg = src[i:src.index("\ndef ", i + 10)] if "\ndef " in src[i + 10:] else src[i:]
        self.assertIn("_missing_alive(", seg, "browser_todo 没走那份正本")
        self.assertNotIn("decided_status", seg, "browser_todo 自己又判了一遍「还活着」")


class TheWorklistRespectsWhatTheUserDecided(unittest.TestCase):
    """**这是整条测试的靶心。** 面板上点的「不投 / 已下线」只写进
    `user_state.json`，库里那条仍是 `ranked` —— 只读裸 `status` 就会把它列进待办。
    """

    def _run(self, seen, ustate):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "users" / "u" / "job_scraper"
            d.mkdir(parents=True)
            (d / "seen_jobs.json").write_text(
                json.dumps({"seen": seen}, ensure_ascii=False), encoding="utf-8")
            (d / "user_state.json").write_text(
                json.dumps(ustate, ensure_ascii=False), encoding="utf-8")
            old = FD.ROOT
            try:
                FD.ROOT = root
                return [e.get("url") for e in FD.browser_todo("u")]
            finally:
                FD.ROOT = old

    ALIVE = {"url": "https://www.zhipin.com/job_detail/a.html", "title": "活的",
             "portal": "boss-browser", "status": "new", "first_seen": "2026-08-25"}
    SKIPPED = {"url": "https://www.zhaopin.com/jobdetail/b.htm", "title": "他标了不投",
               "portal": "zhaopin-browser", "status": "ranked", "first_seen": "2026-08-24"}

    def test_a_job_marked_skipped_on_the_panel_is_out(self):
        urls = self._run({"a": self.ALIVE, "b": self.SKIPPED},
                         {"b": {"decision": "skipped", "date": "2026-08-25"}})
        self.assertIn(self.ALIVE["url"], urls)
        self.assertNotIn(self.SKIPPED["url"], urls,
                         "他在面板上标了不投，名单还把它列出来 —— "
                         "额度就是这么花在他已经否掉的岗上的")

    def test_an_expired_job_is_out(self):
        urls = self._run({"a": self.ALIVE, "b": self.SKIPPED},
                         {"b": {"decision": "expired", "date": "2026-08-25"}})
        self.assertNotIn(self.SKIPPED["url"], urls, "已下线的还在名单里")

    def test_the_cli_lane_is_not_in_the_browser_list(self):
        """猎聘 CLI 那条有自己的 `--missing`，混进来会让人用浏览器去开它。"""
        cli = dict(self.ALIVE, url="https://www.liepin.com/a/1.shtml",
                   portal=FD.CLI_PORTAL, title="猎聘CLI能抓的")
        urls = self._run({"a": self.ALIVE, "c": cli}, {})
        self.assertNotIn(cli["url"], urls)

    def test_newest_first(self):
        """抓的时候只收 14 天内的岗，队尾那批多半已经关了（同 job-rank 自动模式）。"""
        older = dict(self.ALIVE, url="https://www.zhipin.com/job_detail/old.html",
                     first_seen="2026-07-01")
        urls = self._run({"new": self.ALIVE, "old": older}, {})
        self.assertEqual(urls[0], self.ALIVE["url"], "旧的排在了前面")


class TheMaterialsQuestionIsAnsweredByTheSnapshot(unittest.TestCase):
    def test_apply_still_owns_the_seven_conditions(self):
        self.assertIn('j["materials"] is falsy', APPLY, "七条判据里那一条没了")
        self.assertIn("不要照着 `seen_jobs.json`", APPLY,
                      "「别自己再筛一遍」这条没了，auto 那边的指针就悬空了")

    def test_auto_forbids_hand_rolling_it(self):
        self.assertIn("别先自己判断", AUTO, "auto 没禁止自己算「还有没有活」")
        self.assertIn("空集就是没活", AUTO, "没写清空集是结论，不是要再验证的猜测")

    def test_auto_records_why_company_names_are_the_wrong_key(self):
        """不写清错在哪个键，下一个人还会拿公司名去匹配。"""
        self.assertIn("脱敏串", AUTO)
        self.assertIn("只认职位链接", AUTO)

    def test_the_masked_name_rule_is_still_where_auto_points(self):
        doc = _cli.is_anonymous_employer.__doc__ or ""
        self.assertIn("当键去匹配", doc, "auto 引的那句话在正本里查无此话")


if __name__ == "__main__":
    unittest.main()
