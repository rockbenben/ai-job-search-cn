# -*- coding: utf-8 -*-
"""13 个岗死在一条资料里没有的规则上，而那条规则是执行者自己写的。

依据逐字写着：

    「你的资料写明**外企一律排除**」
    「你的资料写明「**外企、海外团队、全球化协作岗一律排除**」」

而 `candidate.md` 全文搜（实测活动用户 2026-08-24）：

    外企        0 次
    外资        0 次
    跨国        0 次
    海外团队    0 次
    全球化协作  0 次

资料里真正写的是**相反的一半**：

    **排除**：要求英语面试、英语口语沟通、日常英文会议、或明确写
             「流利商务英文 / 纯英文办公」的岗位——按硬门处理。
    **不排除**：JD 用英文写、要读英文资料、要写英文文档或邮件、
               与海外同事**书面**协作。

## 这已经是第二次

那一节旁边就记着上一次：「这条原来只写『无法口语沟通』，执行时却被当成
『凡沾英语一律排除』——**边界写清楚才拦得住误杀**。」

边界写清楚了，还是又犯了一次。**所以这次把它升成一条明写的禁令**，
而不是又一句告诫。

## 代价不是「少几个岗」

硬门 FAIL 是**永久出局**，不是分数低。那 13 个里最刺眼的两个，依据自己都写了
「可惜」：一个 IT 副总监岗，JD 特意说明「该职位并非深度技术工程岗位，而是聚焦于
AI 产品负责人职责」；一个 AI Manager 岗，内容是「智能体搭建 + AI 营销方案设计」。
**执行者看出了它对口，然后用一条不存在的规则把它关掉了。**

## 为什么这一轮没有配一个自动检查

试过四版检测器（二字片段对锚点、豁免子句、只取「## 明确排除」那一节、
字面主语比对），**每一版的控制组都是 0** —— 也就是说没有一版能证明它不误报。
按这个仓库自己的规矩（审计那条「它会一直喊狼来了，然后被人整条关掉」），
零误报证不出来的检查不该上。所以这一轮只落规则与实测，检测器等更硬的判据。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheBanIsWritten(unittest.TestCase):
    def _seg(self) -> str:
        i = EVAL.index("#### 引资料里没有的规则")
        return flat(EVAL[i:EVAL.index("### 执业资格", i)])

    def test_the_section_exists(self):
        self.assertIn("#### 引资料里没有的规则 = 编造，和编造经历一样严重", EVAL)

    def test_it_states_the_requirement(self):
        self.assertRegex(self._seg(),
                         r"必须在 `candidate\.md` 里.{0,3}真的找得到")

    def test_it_says_what_the_failure_costs(self):
        """「少几个岗」和「永久出局」不是一个量级。"""
        self.assertRegex(self._seg(), r"硬门 FAIL 不是分数低，是不再出现在任何名单里")

    def test_it_gives_the_fallback(self):
        """只说「不许」，执行者拿不准时还是得选一个 —— 要给他那条路。"""
        seg = self._seg()
        self.assertRegex(seg, r"拿不准就不判 FAIL")
        self.assertRegex(seg, r"照常打分并 FLAG")

    def test_it_forbids_widening_by_paraphrase(self):
        """「英语口语沟通」转述成「外企」，宽度差一个量级 —— 这才是机制。"""
        seg = self._seg()
        self.assertRegex(seg, r"引原话，不要转述成一条更宽的规则")
        self.assertRegex(seg, r"宽度差了一整个量级")


class TheMeasurementIsRecorded(unittest.TestCase):
    def _seg(self) -> str:
        i = EVAL.index("#### 引资料里没有的规则")
        return flat(EVAL[i:EVAL.index("### 执业资格", i)])

    def test_it_carries_the_count_and_date(self):
        seg = self._seg()
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"13 个岗死在一条资料里没有的规则上")

    def test_it_shows_the_zero_counts(self):
        """这一条全部的分量在这几个 0 上 —— 不是「用词不当」，是查无此条。"""
        seg = self._seg()
        for w in ("外企", "外资", "跨国"):
            with self.subTest(w=w):
                self.assertRegex(seg, w + r"`?.{0,2}\*\*0 次\*\*")

    def test_it_quotes_what_the_profile_actually_says(self):
        """不并排放着，读的人不会自己去翻 —— 而这两句正好相反。"""
        seg = self._seg()
        self.assertRegex(seg, r"不排除\*\*：JD 用英文写")

    def test_it_records_that_this_is_the_second_time(self):
        """第一次的教训就写在那一节旁边，照样又犯 —— 这是升成禁令的理由。"""
        seg = self._seg()
        self.assertRegex(seg, r"凡沾英语一律排除")
        self.assertRegex(seg, r"边界写清楚了，还是又犯了一次")

    def test_it_names_the_two_that_hurt(self):
        seg = self._seg()
        self.assertRegex(seg, r"并非深度技术工程岗位")
        self.assertRegex(seg, r"执行者看出了它对口，然后用一条\s*不存在的规则把它关掉了")


class TheBatchScorerIsToldToQuoteVerbatim(unittest.TestCase):
    """代理手上没有资料文件 —— 转述宽一格就成了它自己新立的红线。"""

    def test_the_enumeration_says_copy_not_paraphrase(self):
        i = RANK.index("**候选人自己划的「明确排除」**")
        seg = flat(RANK[i:i + 400])
        self.assertRegex(seg, r"把那几条原样抄进提示里，别转述")

    def test_it_carries_the_incident(self):
        i = RANK.index("**候选人自己划的「明确排除」**")
        seg = flat(RANK[i:i + 400])
        self.assertRegex(seg, r"避免凭空捏造排除规则|原样抄进提示里")

    def test_it_points_at_the_framework_section(self):
        i = RANK.index("**候选人自己划的「明确排除」**")
        self.assertIn("引资料里没有的规则 = 编造", RANK[i:i + 400])

    def test_the_no_reread_rule_survives(self):
        """这一句是插在它前面的，别把它挤掉。"""
        self.assertIn("**不要**让代理再去读一遍资料文件。", RANK)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那几个词在他资料里真的一次都没出现。"""

    def _profile(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "profile" / "candidate.md")
        if not f.is_file():
            self.skipTest("这位用户还没有资料")
        return f.read_text(encoding="utf-8")

    def test_the_invented_terms_are_absent(self):
        t = self._profile()
        for w in ("外企", "外资", "跨国"):
            with self.subTest(w=w):
                self.assertNotIn(w, t, f"资料里现在有「{w}」了 —— "
                                       f"那这一节引的实测数就过时了，去更新")

    def test_the_real_rule_is_present(self):
        """真规则要在 —— 它不在的话，这一节对比的另一半就没了。"""
        t = self._profile()
        self.assertIn("口语", t)
        self.assertRegex(t, r"不排除\*\*：JD 用英文写|只要求读写的\*\*不排除")

    def test_the_library_still_carries_the_mis_kills(self):
        """名单还在库里就该看得见 —— 修掉之后这条会 skip，那时才算清了。"""
        import json
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("还没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        bad = [e for e in seen.values()
               if isinstance(e, dict) and "FAIL" in str(e.get("rank_verdict") or "")
               and re.search(r"资料写明.{0,12}外企|外企.{0,8}一律排除",
                             str((e.get("rank_breakdown") or {}).get("依据") or ""))]
        if not bad:
            self.skipTest("那批已经清掉了 —— 好事；这一节的实测数该跟着更新")
        self.assertGreater(len(bad), 0)


if __name__ == "__main__":
    unittest.main()
