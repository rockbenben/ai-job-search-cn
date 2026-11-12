# -*- coding: utf-8 -*-
"""平台白给的结构化字段必须参与硬门判定，不能只读 JD 散文。

用户 2026-08-13 点着一个岗问：「学历不是写着硕士吗，学历是没过的」。
查下来不是一个岗的事：库里 **89 个岗的 `eduLevel` 写着硕士/博士，
其中 36 个从没被学历门碰过**——最高判到「强匹配 83」，2 个已经投出去了。

根因很具体：评估只读 JD 的**散文部分**，而多数 JD 正文根本不写学历
（那是招聘方在发布表单里勾的筛选项，平台按它过滤，正文里一个字不提）。
猎聘 CLI 每条都免费带着这个字段，**从来没人看**。

判法分两种，混了同样是错：
  - JD 正文明写「硕士及以上」        → FAIL
  - 只有平台字段写着、正文没提        → FLAG，投前确认（不判死）
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / "workflows" / "job-rank.md"


def seen():
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        return {}
    u = ptr.read_text(encoding="utf-8").strip()
    f = ROOT / "users" / u / "job_scraper" / "seen_jobs.json"
    if not f.is_file():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("seen", {})


class TheRuleIsWrittenDown(unittest.TestCase):

    def test_workflow_says_to_read_both(self):
        t = WF.read_text(encoding="utf-8")
        self.assertIn("硬门要读**两处**", t)
        self.assertIn("eduLevel", t, "没点名那个字段，下一个人不知道要读哪个")

    def test_it_distinguishes_fail_from_flag(self):
        """混成一种判法同样是错：全判 FAIL 会误杀，全放行等于没查。"""
        t = WF.read_text(encoding="utf-8")
        self.assertIn("JD 正文明写", t)
        self.assertIn("FLAG，不是 FAIL", t)

    def test_it_names_the_field_to_write(self):
        """判完要落到**哪个字段**，规则里必须写出来。

        2026-08-13：规则把「怎么判」写了两张表，唯独没说产物放哪。执行者两个岗
        都判对了、话也写在 `rank_breakdown.依据` 那段散文里，字段却一个没设——
        下面 `test_every_masters_posting_was_looked_at` 当场报错。
        判断正确却仍然算漏，因为**没有任何东西会去读那段散文**。

        这条守的不是数据，是规则本身：一条只说「要做什么」、不说「产物放哪」的
        规则，下一个人一定会放错地方。
        """
        t = WF.read_text(encoding="utf-8")
        for field in ('rank_breakdown["学历待确认"]', 'rank_breakdown["专业待确认"]'):
            with self.subTest(field=field):
                self.assertIn(field, t,
                              f"规则里没写出 {field}——执行者只能靠猜，"
                              f"或者靠测试报错才知道")
        self.assertIn("不能只写在散文依据里", t,
                      "要明说散文不算数，否则「我在依据里写了」听起来像已经做了")


class NoJobEscapesTheEducationGate(unittest.TestCase):

    def test_every_masters_posting_was_looked_at(self):
        """`eduLevel` 是硕士/博士的岗，要么按硬门否掉，要么标了待确认。

        两者都没有 = 这个字段被无视了，正是 2026-08-13 那个 bug 的形状。
        """
        s = seen()
        if not s:
            self.skipTest("这个 clone 里没有真实职位库")
        hi = [v for v in s.values() if (v.get("eduLevel") or "") in ("硕士", "博士")]
        if not hi:
            self.skipTest("库里没有要求硕士/博士的岗")
        missed = []
        for v in hi:
            vd = str(v.get("rank_verdict") or "")
            if vd.startswith(("不满足", "硬门")):
                continue
            bd_ = v.get("rank_breakdown") or {}
            if bd_.get("学历待确认") or bd_.get("学历已核"):
                continue
            hard = bd_.get("硬性条件") or bd_.get("硬门") or {}
            if hard.get("学历院校") in ("FLAG", "FAIL") or hard.get("学历与院校") in ("FLAG", "FAIL"):
                continue
            if "不建议" in vd or "跳过" in vd:
                continue
            if v.get("status") == "new":
                continue          # 还没评的不算漏
            # **已下线的也不算漏。** 这条守卫自己写着守的是「评过分、**还可能去投**
            # 的岗」，而 `expired` 按定义投不出去 —— `job-apply.md` 选岗那七条里
            # `j["expired"] is falsy` 是单独一条，理由原话是「材料做完也投不出去」。
            # 实测 2026-08-27：一个 `eduLevel` 写硕士的岗在浏览器里打开跳到了职位
            # 聚合页，按规矩标了 `expired`。它**从来没被评过**（没有判词、没有
            # rank_breakdown），于是上面三条出路一条都不占，被记成了漏判 —— 而它
            # 是这条守卫刚刚**成功挡下**的那种岗的反面：不是没人看，是已经没得投。
            # 这一档此前不存在，浏览器标下线是 2026-08-25 才有的路径。
            if v.get("status") == "expired":
                continue
            # **没打过分的不算漏。** `prescreen.py` 会在打分之前先按薪资/学历下限
            # 结案一批（`rank_score` 为 None、判词「跳过」）——那类岗**根本没走到
            # 学历这一栏**，没有可记录的判断。这条守的是「评过分、还可能去投的岗
            # 别把硕博字段无视掉」；一个分数为空、判词是跳过的岗，面板上不会
            # 出现在任何可投清单里，误导不了人。实测 2026-08-17 撞出 9 个，
            # 全是被薪资先结案的（有几个的依据里还留着 prescreen 记的降权说明）。
            if v.get("rank_score") is None and "跳过" in vd:
                continue
            missed.append(f"{v.get('rank_score')} {(v.get('title') or '')[:26]}")
        self.assertEqual(missed, [],
                         f"这些岗平台字段写着硕士/博士，却既没否掉也没标待确认"
                         f"（共 {len(hi)} 个候选）：\n  " + "\n  ".join(missed))


class TheMajorCountsToo(unittest.TestCase):
    """学历门不止比层次。用户 2026-08-13：「计算机相关本科及以上学历……
    其实也不符合，不该标为学历过关」。

    实测 43 个岗的 JD 写着「计算机/理工科等相关专业」，学历门却一律 PASS——
    判的时候只比了「本科 vs 本科及以上」，专业那半句根本没进判据。
    """

    def test_the_workflow_covers_the_major(self):
        t = WF.read_text(encoding="utf-8")
        self.assertIn("学历门要看**两件事**", t)
        self.assertIn("专业不限", t, "没写清「优先」和「不限」不算门槛，会误杀")

    def test_it_is_a_flag_not_a_fail(self):
        """判死会误杀（实测这批里有 82 分的），判 PASS 又等于骗人。"""
        t = WF.read_text(encoding="utf-8")
        self.assertIn("为什么大多数是 FLAG 而不是 FAIL", t)

    def test_flagged_jobs_say_why(self):
        s = seen()
        if not s:
            self.skipTest("这个 clone 里没有真实职位库")
        flagged = [v for v in s.values()
                   if (v.get("rank_breakdown") or {}).get("专业待确认")]
        if not flagged:
            self.skipTest("库里没有标了专业待确认的岗")
        # **解释该在哪里：字段值本身。** 这条原来只去 `依据` 那段散文里找死字符串
        # 「专业不符」，而 job-rank.md 的 FLAG 表写的是「**值**写成一句人话，说清凭什么
        # 标的、投前要问什么」——解释的正房就是字段值，散文那句是「提一句没问题」。
        # 于是把话写在正房里、写得比「专业不符」四个字还清楚的条目被判成没说清。
        # 实测 2026-08-17 撞出 33 个，全都在字段值里写明了 JD 的专业清单与不符之处。
        # 现在两处都认，只要求**真说了点什么**（不是空串、不是一个「是」字）。
        bad = []
        for v in flagged:
            bd_ = v.get("rank_breakdown") or {}
            said = f"{bd_.get('专业待确认', '')}\n{bd_.get('依据', '')}"
            if len(str(bd_.get("专业待确认") or "").strip()) < 8 and "专业不符" not in said:
                bad.append((v.get("title") or "")[:24])
        self.assertEqual(bad, [], "标了待确认却没说清差在哪：\n  " + "\n  ".join(bad))


if __name__ == "__main__":
    unittest.main()


class TheFlagValueIsASentenceNotABoolean(unittest.TestCase):
    """FLAG 字段要写「投前问什么」，不是一个 `true`。

    `job-rank.md`「FLAG 判完，结论落到哪个字段」写着：

    > 值写成一句人话，说清**凭什么标的、投前要问什么**。

    2026-09-02 实测：`学历待确认` 31 个里 **13 个**、`专业待确认` 48 个里
    **13 个**，值是裸 `True` —— 用户拿到一个「有疑问」的标记，
    **既没有理由，也没有该问的那句话**，而这一档的全部用途就是那句话。

    **本文件上面几条只查「有没有这个键」**（`if bd_.get("学历待确认")`），
    布尔值一路绿灯。那正是那一节自己的论点再走一步：
    规则写清了「产物放哪」，**没人查产物长什么样**。

    存量归审计（`check_flag_fields_carry_a_sentence`，留意档，
    给的命令是 `/job-rank --all`）—— 让整套测试为存量数据长期红着，
    等于把它关掉。这里只钉两件**不会因存量而红**的事：
    规则原话还在、审计那条检查接着线。
    """

    def test_the_rule_still_demands_a_sentence(self):
        t = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        i = t.index("### FLAG 判完，结论落到哪个字段")
        seg = t[i:t.index("\n## ", i)]
        self.assertIn("值写成一句人话", seg,
                      "「值写成一句人话」这条要求没了 —— 审计那条检查就失去了依据")
        self.assertRegex(seg, r"投前要问什么|投前确认",
                         "没说清那句人话要回答什么")

    def test_the_audit_actually_checks_it(self):
        """写了规则没人查 = 没写。审计那条要真接在 CHECKS 上。"""
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import audit_pipeline as ap
        names = [n for n, _ in ap.CHECKS]
        self.assertTrue(
            any("FLAG" in n and "true" in n for n in names),
            f"审计里没有查 FLAG 值的那条：{[n for n in names if 'FLAG' in n]}")

    def test_the_check_can_actually_fire(self):
        """给它一条裸 True 的记录，它要报出来。"""
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import audit_pipeline as ap
        fake = {"x": {"title": "某岗", "url": "https://example.invalid/1",
                      "rank_breakdown": {"学历待确认": True}}}
        out = ap.check_flag_fields_carry_a_sentence(fake, {})
        self.assertTrue(out, "裸 True 没被报出来")
        self.assertEqual(out[0][0], "warn")

    def test_a_real_sentence_passes(self):
        """写了人话的不许误报 —— 否则这条会把守规矩的一起骂。"""
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import audit_pipeline as ap
        ok = {"x": {"title": "某岗", "url": "https://example.invalid/2",
                    "rank_breakdown": {
                        "学历待确认": "卡片写硕士、JD 正文没提，投前问一句是否卡学历"}}}
        self.assertEqual(ap.check_flag_fields_carry_a_sentence(ok, {}), [])
