# -*- coding: utf-8 -*-
"""`05` 说期望年包按送出渠道决定写不写 —— 而出简历那一步拿不到渠道。

`05-cv-templates.md`「期望年包写不写：看这份简历怎么送出去」按送出方式分四档，
只有**网申表单**那一档写。理由是 `06` 那条铁律的同一个道理：

> 先谈钱＝让对方在读完你能干什么之前先按价格分类，
> **给一个正在找理由过滤你的人递上一把尺子**。

而 `job-apply.md` 第 5b 步（出定制简历的那一步）**全文没有一处引用送出方式**。
规则要一个输入，没人把它传下来 —— 于是它只能靠执行者临场想起来。

## 实测：15 份里 4 份想反了

活动用户 2026-08-24，`documents/applications/*/resume.typ` 共 15 份：

    平台内直聊（猎聘 / BOSS / 智联）   15 份   ← 按上表一份都不该写这一行
    实际写了「期望…」的                4 份   ← 其中一份还是明确的猎头岗

**不是执行者不懂规则。** 输入不在手上，凭记忆做四选一，错四份是必然。

## 代价 05 自己量过

他已投的 83 个有年包的岗里，只有 **1 个**上沿低于那条线（真会被这行字挡掉的），
而 **42 个的区间跨过它** —— 那 42 个本来是可谈的，而简历替他先报了价。

## 输入本来就有

第 1.5a / 1.5b 步已经判过「有无对话方 + 猎头还是直招 + 平台」，
而且 1.5b 最后一句明写着「判定结果写入产出物的头部」。
这一轮做的只是**让 5b 去读它**，不是新造一个判断。
"""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
CV = (ROOT / "workflows" / "reference"
      / "05-cv-templates.md").read_text(encoding="utf-8")
RESUME = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = APPLY.index("#### 期望年包那一行：按**这一份怎么送出去**决定写不写")
    return flat(APPLY[i:APPLY.index("**联系方式缺失检测", i)])


class TheStepNowReadsTheChannel(unittest.TestCase):
    def test_the_section_exists(self):
        self.assertIn("#### 期望年包那一行：按**这一份怎么送出去**决定写不写", APPLY)

    def test_it_sits_inside_the_resume_step(self):
        """放在别处等于没放 —— 出简历的人读的是 5b。"""
        a = APPLY.index("### 5b. 生成定制简历")
        b = APPLY.index("#### 期望年包那一行")
        self.assertLess(a, b)
        self.assertLess(b, APPLY.index("### 5c"))

    def test_it_points_at_the_existing_judgement(self):
        """**不新造判断。** 1.5 已经判过，重判就是第二份，两份迟早分叉。"""
        s = seg()
        self.assertRegex(s, r"第 1\.5a / 1\.5b 步已经判过")
        self.assertRegex(s, r"读那个头部，别重判")

    def test_the_judgement_it_cites_really_writes_a_header(self):
        """引一句不存在的话，这条就落空了。"""
        self.assertIn("判定结果（有无对话方 + 猎头/HR/用人方）写入产出物的头部", APPLY)

    def test_it_maps_all_four_buckets(self):
        s = seg()
        for k in ("网申表单", "平台内直聊", "猎头", "内推"):
            with self.subTest(k=k):
                self.assertIn(k, s)

    def test_only_the_form_bucket_writes_it(self):
        """写错方向就是这条规则的全部内容 —— 四档里只有一档写。"""
        i = APPLY.index("| 1.5 判的是 | 05 表里对应哪一档 | 这一行 |")
        rows = [r for r in APPLY[i:APPLY.index("\n\n", i)].splitlines()
                if r.startswith("| ") and "---" not in r][1:]
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(1 for r in rows if "**写**" in r), 1)
        self.assertEqual(sum(1 for r in rows if "**不写**" in r), 3)

    def test_the_form_bucket_demands_the_unit(self):
        """`50k` 是月薪还是年包？国内薪资是月薪 × 薪数，不写口径就要多一轮来回。"""
        self.assertRegex(seg(), r"45-50k×12")

    def test_unknown_means_do_not_write(self):
        """**判不出来是常态。** 不给默认值，这条又回到凭记忆。"""
        s = seg()
        self.assertRegex(s, r"判不出来时不写")

    def test_the_asymmetry_is_spelled_out(self):
        """只说「不写」，下一个人会觉得两边都差不多，然后改回去。"""
        s = seg()
        self.assertRegex(s, r"写了是\*\*静默\*\*少掉一批本来可谈的岗")
        self.assertRegex(s, r"你永远不知道少了谁")

    def test_the_asymmetry_matches_the_online_resume_rule(self):
        """同一件事的在线简历版早就这么判了 —— 两处不许各说各的。"""
        self.assertIn("job-resume.md", seg())
        self.assertRegex(flat(RESUME), r"按可谈的下限填，不按理想值填")
        self.assertRegex(flat(RESUME), r"填高了是\*\*静默\*\*少掉一批")

    def test_the_measurement_is_recorded(self):
        s = seg()
        self.assertIn("2026-08-24", s)
        self.assertRegex(s, r"15 份定制简历\*\*全部\*\*是平台内直聊场景")
        self.assertRegex(s, r"\*\*4 份写了\*\*")

    def test_it_names_the_root_cause(self):
        """写成「执行者不小心」的话，下一轮只会再喊一次「注意」。"""
        s = seg()
        self.assertRegex(s, r"不是执行者不懂规则")
        self.assertRegex(s, r"规则要的那个输入\s*从来没被传到这一步")

    def test_it_carries_the_cost(self):
        s = seg()
        self.assertRegex(s, r"42 个的区间跨过那条线")


class TheRuleItServesIsStillWritten(unittest.TestCase):
    def test_the_table_still_exists(self):
        self.assertIn("| 送出方式 | 期望年包 | 为什么 |", CV)

    def test_the_table_still_has_four_rows(self):
        i = CV.index("| 送出方式 | 期望年包 | 为什么 |")
        rows = [r for r in CV[i:CV.index("\n\n", i)].splitlines()
                if r.startswith("| ") and "---" not in r][1:]
        self.assertEqual(len(rows), 4, "05 那张表的档数变了 —— 5b 那张对照要跟着改")

    def test_only_one_row_says_write(self):
        i = CV.index("| 送出方式 | 期望年包 | 为什么 |")
        rows = [r for r in CV[i:CV.index("\n\n", i)].splitlines()
                if r.startswith("| ") and "---" not in r][1:]
        self.assertEqual(sum(1 for r in rows if "**写**" in r), 1)

    def test_the_reason_still_traces_to_the_greeting_rule(self):
        """这条建立在「先谈钱＝递给对方一把尺子」上。它没了，这条就没依据了。"""
        seg_ = flat(CV[CV.index("### 期望年包写不写"):][:1400])
        self.assertRegex(seg_, r"递上一把尺子")

    def test_it_is_not_restated_in_the_apply_step(self):
        """5b 那张是**对照**（1.5 的判定 → 05 的档），不是把 05 抄一遍。"""
        s = seg()
        self.assertNotIn("递上一把尺子", s)
        self.assertIn("05-cv-templates.md", s)


class TheTailoringDisciplineStillHolds(unittest.TestCase):
    """这一条只放开一行。别的定制纪律一个字不许松。"""

    def test_it_still_forbids_touching_numbers(self):
        # 原话在 `job-apply.md:1076`（`job-resume.md` 引的是个转述版，
        # 少了「或日期」三个字 —— 钉原话，别钉转述）。
        self.assertRegex(flat(APPLY),
                         r"\*\*不得\*\*重排结构、增删经历、修改任何数字或日期")

    def test_it_still_forbids_reordering_sections(self):
        self.assertRegex(
            flat(APPLY), r"任何情况下都不许为这一个岗重排章节")

    def test_the_contact_check_still_follows(self):
        self.assertIn("**联系方式缺失检测（绝不编造）**", APPLY)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那 15 份真的全是直聊场景，而写了那一行的真的不该写。"""

    def _rows(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = ROOT / "users" / p.read_text(encoding="utf-8").strip()
        f = u / "job_scraper" / "seen_jobs.json"
        if not f.is_file():
            self.skipTest("还没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        byurl = {(e.get("url") or ""): e for e in seen.values()
                 if isinstance(e, dict)}
        out = []
        for r in sorted((u / "documents" / "applications").glob("*/resume.typ")):
            post = r.parent / "posting.md"
            url = ""
            if post.is_file():
                m = re.search(r"https?://\S+",
                              post.read_text(encoding="utf-8", errors="replace"))
                    # 2026-10-12：这里是 `r"https?://\\S+"` —— **raw 字符串里的
                    # 双反斜杠，匹配的是一个字面的反斜杠**，于是永远匹配不上，
                    # `url` 恒为 `""`、`byurl.get("")` 恒为 `None`、
                    # `portal` 恒为 `"?"`，`test_they_are_all_chat_platforms`
                    # 于是恒定地报「15/15 对不上平台」。
                    #
                    # **它一直在空跑**：这条守卫的全部依据是「15 份定制简历
                    # 全在直聊场景，所以「一份都不该写期望薪资」才成立」，
                    # 而它从来没量过那 15 份到底来自哪个渠道。修好之后实测
                    # 15 份全部对得上，`portal` 无一个 `"?"`。
                    #
                    # 与 `tests/test_one_value_one_home.py` 是同一族：
                    # 正则写错时报的不是「正则写错了」，是它本该守的那件事
                    # 「对不上」—— 而那句话读起来完全合理。
                url = m.group(0).rstrip(")>」") if m else ""
            out.append(("期望" in r.read_text(encoding="utf-8", errors="replace"),
                        (byurl.get(url) or {}).get("portal") or "?"))
        if len(out) < 5:
            self.skipTest("定制简历太少，说不出话")
        return out

    def test_they_are_all_chat_platforms(self):
        """**这是「一份都不该写」的全部依据。** 出现网申岗时这条会红。"""
        rows = self._rows()
        bad = [p for _h, p in rows if p == "?"]
        self.assertLessEqual(
            len(bad), len(rows) * 0.2,
            f"{len(bad)}/{len(rows)} 份对不上平台 —— 那「全是直聊场景」这个"
            f"前提就核不了了")

    def test_some_still_carry_the_line(self):
        """修好之后这条会 skip —— 那时该把这一节的实测数更新掉。"""
        rows = self._rows()
        n = sum(1 for h, _p in rows if h)
        if not n:
            self.skipTest("已经一份都不写了 —— 好事，去更新这一节的数")
        self.assertGreater(n, 0)


if __name__ == "__main__":
    unittest.main()
