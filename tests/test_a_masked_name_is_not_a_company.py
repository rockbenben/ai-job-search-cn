# -*- coding: utf-8 -*-
"""「某知名公司」不是公司名，是占位符——凡拿公司名当键的地方都得先过这道判据。

猎聘给猎头岗打脱敏串。全库实测 2026-08-25：2262 个岗里 **1231 个脱敏（54%）**，
其中 97.4% 是猎头岗（`/a/` 链接）；光「某知名公司」这一个串就出现 **138 次**——
（这几个数原来写的是 1355 / 51% / 98.5%，标着同一天却在当天就对不上 ——
`TheDocstringFiguresAreRecomputed` 现在现算着它们，所以每次归档、每批新抓
都会把它们顶红一次，那是它该有的样子。）
那是 138 家不同的用人方。判据本身早就有（`is_anonymous_employer`，含「某」
「保密」「未公开」），可它此前**只有一个消费方**在用（「找人内推」那一处）。

两处漏掉它，各是一种错法：

| 哪里 | 拿脱敏串当身份的后果 |
|---|---|
| `build_dashboard.match_tracker` 的模糊回退 | 一条手工记的、没有链接的投递记录，把库里 6 个岗一起认成已投（实测活动用户），它们随即从可投名单消失 |
| `followups.cluster_key`（本次新增的按公司聚拢） | 猎头那 38 条公司名全是脱敏串，不设防会误并 5 组 12 条，然后建议他「把这 4 个岗合成一条催」——而那是 4 家不同的公司 |

第一处是**一把钥匙开了六把锁**，和 `match_tracker` 文档里那段「同一个岗有多把
钥匙」正好互为反面：那边是漏认（多看见一个已投的岗，代价小），这边是错认
（六个没投的岗永远消失，代价大）。判据正本因此搬进 `_cli`——
`build_dashboard` 不能反过来 import `export_web_data`（循环）。
"""
import sys
import re
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import build_dashboard as B  # noqa: E402
import export_web_data as X  # noqa: E402
import followups as F  # noqa: E402


class TheJudgeHasOneHome(unittest.TestCase):
    def test_it_lives_in_cli(self):
        self.assertTrue(_cli.is_anonymous_employer("某知名公司"))
        self.assertFalse(_cli.is_anonymous_employer("鲸涛科技"))

    def test_the_export_forwards_to_it(self):
        """抄第二份就等着两处分叉。"""
        self.assertIs(X.is_anonymous_employer, _cli.is_anonymous_employer)

    def test_it_is_not_anchored_to_the_start(self):
        """平台常写「上海某大型物流公司」——绑 `^某` 会漏掉一半。"""
        self.assertTrue(_cli.is_anonymous_employer("上海某大型物流公司"))
        for w in ("保密", "未公开"):
            with self.subTest(w=w):
                self.assertTrue(_cli.is_anonymous_employer(f"{w}企业"))


class MatchTrackerDoesNotMatchOnAMask(unittest.TestCase):
    """一条没有链接的投递记录，不许靠脱敏公司名认领别的岗。"""

    ROW = {"source": "", "company": "某知名公司", "role": "AI产品经理"}

    def test_a_masked_row_claims_nothing(self):
        job = {"company": "某知名公司", "title": "AI产品经理（Agent方向）"}
        self.assertIsNone(
            B.match_tracker(job, "https://www.liepin.com/a/9.shtml", [self.ROW]),
            "脱敏串把一个没投过的岗认成已投")

    def test_a_real_name_still_matches(self):
        """**别把回退整条关掉**——手工记的行本来就常常没有链接，
        具名公司靠 company+role 认回来是这条回退存在的理由。"""
        row = {"source": "", "company": "鲸涛科技", "role": "AI产品经理"}
        self.assertIsNotNone(
            B.match_tracker({"company": "鲸涛科技", "title": "AI产品经理（Agent方向）"},
                            "https://x/job/9", [row]))

    def test_a_masked_row_with_a_link_still_matches(self):
        """链接是可靠的键，脱敏与否都不影响它——这条路不许被误伤。"""
        url = "https://www.liepin.com/a/9.shtml"
        row = {"source": url, "company": "某知名公司", "role": "AI产品经理"}
        self.assertIsNotNone(
            B.match_tracker({"company": "某知名公司", "title": "AI产品经理"}, url, [row]))

    def test_the_reason_is_written_next_to_the_code(self):
        """这一条读起来像「少了个判断」，注释必须说清为什么宁可漏认。"""
        src = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
        seg = src[src.index("def match_tracker("):][:3000]
        self.assertIn("is_anonymous_employer", seg)
        self.assertRegex(seg, r"宁可漏认|不可错认", "没写清这条取舍朝哪边偏")


class FollowUpsClusterByCompanyButNotByMask(unittest.TestCase):
    def test_a_real_name_clusters(self):
        self.assertEqual(F.cluster_key("鲸涛科技"), "鲸涛科技")

    def test_a_mask_never_clusters(self):
        for c in ("某知名公司", "某上海互联网公司", "保密", ""):
            with self.subTest(c=c):
                self.assertEqual(F.cluster_key(c), "",
                                 f"「{c}」被当成了一家具体的公司")


class TheClusterNoteSaysWhatToDo(unittest.TestCase):
    """渲染层：同公司的几笔要挨着，而且只提示一次。"""

    SRC = (ROOT / "tools" / "followups.py").read_text(encoding="utf-8")

    def test_rows_of_one_company_sit_together(self):
        seg = self.SRC[self.SRC.index("组内按分数倒序"):][:2000]
        self.assertIn("cluster_key", seg, "排序没用聚拢键")
        self.assertIn("best[", seg, "位置不是由这家最高的那一笔决定")

    def test_the_score_order_still_wins(self):
        """聚拢**不许**改变优先级：分高的公司仍排在前面。"""
        seg = self.SRC[self.SRC.index("组内按分数倒序"):][:2000]
        self.assertRegex(seg, r"-best\[", "聚拢键成了第一排序位，分数被挤掉了")

    def test_the_note_appears_once_per_company(self):
        seg = self.SRC[self.SRC.index("组内按分数倒序"):][:2600]
        self.assertIn("seen_key", seg, "同一家会重复提示 N 次")

    def test_the_note_is_scoped_to_the_group(self):
        """猎头挂的和企业直招是两个联系人。跨组合并会让他去跟猎头
        问一个他其实是直投的岗。"""
        seg = self.SRC[self.SRC.index("组内按分数倒序"):][:2600]
        self.assertIn("这一组里", seg, "提示没说清数的是这一组内的")

    def test_it_says_the_action_not_just_the_count(self):
        """只报「你投了 5 个」是个观察。要说出该怎么做。"""
        seg = self.SRC[self.SRC.index("组内按分数倒序"):][:2600]
        self.assertRegex(seg, r"催一条", "没说该合并成一条")

    def test_no_sentinel_character_in_the_key(self):
        """公司名是自由文本，任何可打印前缀都可能真撞上；
        不可打印的（`\\x00`）则会把源文件写成无法解析的东西——实测栽过。"""
        seg = self.SRC[self.SRC.index("def _k("):][:1400]
        self.assertNotIn(chr(0), self.SRC, "源码里混进了空字节")
        # 键 2026-08-23 从 `(c, 0)` 变成 `(c, 平台, 0)` —— 猎聘和 BOSS 上的两个岗
        # 不是一个对话框，判据见 `test_one_message_cannot_reach_two_apps`。
        # **这一条验的是「元组，不是拼串」**，元数不该写死。
        self.assertRegex(seg, r"return \(c, [^)]*0\) if c else",
                         "键不是元组，又回到哨兵字符拼串了")
        self.assertNotRegex(seg, r'c \+ ["\']|f"\{c\}', "公司名被拼进了字符串键")


class TheHistoricalSampleIsConsistent(unittest.TestCase):
    """这组日期和计数描述历史样本，测试不读取活动用户的职位库。"""

    def test_the_documented_percentage_matches_its_sample(self):
        doc = _cli.is_anonymous_employer.__doc__ or ""
        sample = re.search(r"(\d+) 个岗里 (\d+) 个\s*脱敏（(\d+)%）", doc)
        self.assertIsNotNone(sample)
        total, masked, share = map(int, sample.groups())
        self.assertEqual(round(masked / total * 100), share)

    def test_adding_a_named_company_keeps_the_mask_count(self):
        names = ["某知名公司", "保密", "未公开", "测试公司"]
        self.assertEqual(sum(_cli.is_anonymous_employer(name) for name in names), 3)
        names.append("另一家测试公司")
        self.assertEqual(sum(_cli.is_anonymous_employer(name) for name in names), 3)

    def test_the_early_sample_is_marked_as_one(self):
        self.assertIn("最早那次抽样", _cli.is_anonymous_employer.__doc__ or "")

if __name__ == "__main__":
    unittest.main()
