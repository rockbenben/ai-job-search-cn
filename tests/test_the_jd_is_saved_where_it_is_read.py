# -*- coding: utf-8 -*-
"""「读到 JD 就存」这条规则，得长在**正文在眼前的那一步**。

规则一直都在，只是写在 `job-scrape.md` 的 Step 4.5 —— 而 Step 4.5 是照 CLI
那条路写的（`--import-from <抓好的目录>`、「详情接口返回的是搜索结果的超集」）。
**浏览器这条根本没有「抓好的目录」**：正文是在 Step 2 打开详情页时看到的，
走到 4.5 页面早关了。

实测（2026-08-30，按渠道量 JD 覆盖率）：

    liepin-browser   48 个岗   47 有 JD   98%
    boss-browser     81 个岗   49 有 JD   60%
    51job-browser    53 个岗   16 有 JD   30%
    zhaopin-browser  65 个岗   14 有 JD   22%

`liepin-browser` 98% 说明浏览器完全存得下，不是能力问题。只算**评过分的**
（预筛按薪资结案的不需要 JD）覆盖率仍是 猎聘 93% / BOSS 71% / 智联 56% /
前程无忧 51%。

丢掉的后果不是「回头补一次」那么轻：`/job-upskill` 少一份语料、复查原文无从核对、
**岗位下线之后永远查不回来**；回头补要重开页面、再花一次额度
（`fetch_details --browser-list` 自己也写着「浏览器渠道的 JD 只能在抓取当次取」）。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")

STEP2 = SCRAPE[SCRAPE.index("### Step 2：取详情、解析"):
               SCRAPE.index("### Step 2.5")]
STEP45 = SCRAPE[SCRAPE.index("### Step 4.5"):SCRAPE.index("### Step 4.6")]


class TheRuleSitsWhereTheTextIs(unittest.TestCase):
    def test_step_two_tells_the_browser_path_to_save_it(self):
        """正文在眼前的那一步要给出该敲的那条命令。"""
        self.assertIn("jd_store.py --save <职位链接> --apply", STEP2)

    def test_step_two_names_the_browser_portals(self):
        """三家常态浏览器渠道要点名 —— 泛指「网页抓取能力」时它被读成了别的路。"""
        for portal in ("BOSS", "智联", "前程无忧"):
            with self.subTest(portal=portal):
                self.assertIn(portal, STEP2)

    def test_step_two_says_why_it_cannot_wait(self):
        """不说清「为什么不能留到 4.5」，下一个人会把它挪回去。"""
        self.assertRegex(re.sub(r"\s+", "", STEP2), r"走到4\.5页面早关了")

    def test_step_45_still_owns_the_bulk_path(self):
        """CLI 那条（一整个目录）仍归 4.5 —— 两条路各有各的入口，不是一处抄两遍。"""
        self.assertIn("--import-from", STEP45)

    def test_the_cost_is_measured_not_asserted(self):
        """说明当场落库的必要性与代价。"""
        seg = re.sub(r"\s+", "", STEP2)
        self.assertIn("浏览器通道完全能存下JD正文", seg)

    def test_it_says_what_is_lost_forever(self):
        """「回头补一次」听起来很轻 —— 要说清岗位下线之后就再也补不回来。"""
        self.assertRegex(re.sub(r"\s+", "", STEP2), r"下线之后就永远查不回来")


if __name__ == "__main__":
    unittest.main()
