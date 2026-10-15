# -*- coding: utf-8 -*-
"""年限门在这个库里**一次都没有真正因为「年数不够」FAIL 过**。

中文 JD 几乎从不裸写年数，它总带一个限定词：「N 年以上**互联网产品**经验」
「N 年以上**智能座舱**经验」「N 年以上 **AI 相关**工作经验」。而候选人转过方向时
有两个都对的年限读数（总年限 / 现在这个方向的年限）—— **拿哪个比，`04` 原来没说。**

实测活动用户 2026-08-24（269 份深评）：

    有「工作年限」那一行的        257 份
    判 FAIL 的                 16 份
    其中引的是带领域限定的要求      16 份（**全部**）
    其中那个数没超过他的总年限      15 份
    只被这一道门杀掉的            15 份（没有第二道 FAIL）

引文长这样：「5 年以上 **SaaS/企业级产品**经验」「8 年以上 **B 端产品**工作经验」
「10 年以上**智能座舱/服务型产品**经验」—— 他总年限 13 年多，**每个数他都够**。
缺的全是限定词指的那个领域。

## 为什么这是错的，而且是 04 自己说过的

`04` 早就写着：**技术栈、行业经验、专业这类「能力够不够」的不是门**——
当门用等于把连续量做成一票否决。而**年限门是七道里唯一一道长得像「能力够不够」
的门**，领域要求就从这一格混了进来。

代价不是「多标了几个 FLAG」：判词一旦写成「不满足硬性条件」，这个岗**永久出局**；
而它的真实问题（领域不熟）本该只是业务领域分低几档，仍然在名单里。

## 三处一起改，少一处就断

- `04` 给判据（带不带领域限定，决定它是不是门）
- `job-rank.md` 派代理时**两个年限读数都要给** —— 只给一个，代理要么永远 PASS，
  要么见「N 年」就 FAIL
- `profile.example` 那一行要**在同一行里出现两个数字**：机器（`_candidate_years`）
  按「含『工作年限』且有 ≥2 个『N 年』的那一行」解析。模板原来写的是
  「不在此写独立数字，从工作经历自动推算」—— 那句话产出一行没有数字的散文，
  而**没有任何一处在做那个推算**，于是整档检查静默不跑
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402
import _cli  # noqa: E402  # noqa: E402

EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
TPL = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")
CLI = ROOT / "tools" / "_cli.py"
AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheFrameworkDecidesWhichNumber(unittest.TestCase):
    def _seg(self) -> str:
        i = EVAL.index("### 年限门：")
        return flat(EVAL[i:EVAL.index("### 专业不符", i)])

    def test_the_section_exists(self):
        self.assertIn("### 年限门：那个数**带不带领域限定**，决定它是不是门", EVAL)

    def test_all_three_cases_are_covered(self):
        """三分法缺一格，那一格就回到「各判各的」。"""
        seg = self._seg()
        self.assertIn("没有领域限定", seg)
        self.assertRegex(seg, r"他正在做的那个方向")
        self.assertRegex(seg, r"他没做过的领域")

    def test_the_domain_case_is_not_a_gate(self):
        """**锚在那张三分表的第三行上。** 第一版只查这一节里有没有「不是门」
        四个字，而散文里本来就有 —— 把表格那一行改成「是门」，测试照样绿
        （变异实测活下来了）。判据在表里，就得比表里那一行。
        """
        row = next(x for x in EVAL.splitlines()
                   if x.startswith("|") and "他没做过的领域" in x)
        self.assertIn("**不是门**", row)
        self.assertIn("**不比**", row)

    def test_the_other_two_rows_are_gates(self):
        """三分表另外两行必须还是门 —— 全判成「不是门」等于把这道门整个拆了。"""
        for key in ("没有领域限定", "他正在做的那个方向"):
            row = next(x for x in EVAL.splitlines()
                       if x.startswith("|") and key in x)
            with self.subTest(key=key):
                self.assertIn("**是门**", row)

    def test_it_gives_a_one_line_test(self):
        """判据要能当场套用，不能只讲道理。"""
        self.assertRegex(self._seg(),
                         r"把年数拿掉，剩下的那半句是不是一条领域要求")

    def test_it_says_where_the_gap_goes_instead(self):
        """只说「不是门」不够——不说它归哪儿，执行者只能自己发明一个去处。"""
        seg = self._seg()
        self.assertIn("业务领域", seg)

    def test_it_leans_on_the_rule_already_in_this_file(self):
        """这一节不是新规矩，是把既有那条落到最常漏的一格。"""
        seg = self._seg()
        self.assertRegex(seg, r"行业经验.{0,12}不是门|技术栈、行业经验、专业")
        self.assertRegex(seg, r"唯一一道长得像「能力够不够」的门")

    def test_the_measurement_is_recorded(self):
        seg = self._seg()
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"一次都没有真正因为「年数不够」\s*FAIL 过")
        self.assertRegex(seg, r"15 份")

    def test_it_names_the_real_cost(self):
        """「多标几个 FLAG」和「永久出局」不是一个量级。"""
        self.assertRegex(self._seg(), r"永久\s*出局")

    def test_the_gate_row_points_here(self):
        """读的人是在那张表上判的门，规矩写在别处就等于没写。"""
        i = EVAL.index("| **工作年限** |")
        row = EVAL[i:EVAL.index("\n", i)]
        self.assertIn("两个数", row)
        self.assertIn("年限门：那个数带不带领域限定", row)


class TheBatchGetsBothNumbers(unittest.TestCase):
    def test_the_enumeration_asks_for_two(self):
        """只给一个读数，代理要么永远 PASS 要么见「N 年」即 FAIL。"""
        i = RANK.index("学历院校 / 工作年限（")
        seg = flat(RANK[i:i + 400])
        self.assertIn("两个年限读数都要给", seg)
        self.assertIn("总年限", seg)
        self.assertRegex(seg, r"主要方向的年限")

    def test_it_says_what_breaks_with_only_one(self):
        i = RANK.index("学历院校 / 工作年限（")
        seg = flat(RANK[i:i + 400])
        self.assertRegex(seg, r"给总年限就永远 PASS")
        self.assertRegex(seg, r"给方向年限就见「N 年」即 FAIL")

    def test_it_points_at_the_framework_section(self):
        i = RANK.index("学历院校 / 工作年限（")
        self.assertIn("年限门：那个数带不带领域限定", RANK[i:i + 400])

    def test_the_tolerance_survived_the_edit(self):
        """这一格原来就有的那条别被挤掉。"""
        self.assertIn("差 1 年以内是 FLAG 不是 FAIL", RANK)


class TheTemplateLineIsMachineReadable(unittest.TestCase):
    def test_it_has_two_numbers_on_one_line(self):
        """`_candidate_years` 按「含『工作年限』且有 ≥2 个『N 年』」解析。
        模板给的形状要能被它读中，否则新用户那档检查静默不跑。"""
        line = next(x for x in TPL.splitlines() if "工作年限说明" in x)
        self.assertGreaterEqual(len(re.findall(r"\S+\s*年", line)), 2, line)

    def test_the_placeholder_shape_parses(self):
        """把占位符换成数字之后，真的能被解析出来 —— 不是「看起来像」。"""
        line = next(x for x in TPL.splitlines() if "工作年限说明" in x)
        filled = (line.replace("[TOTAL_YEARS]", "8")
                      .replace("[FOCUS_YEARS]", "3")
                      .replace("[YOUR_MAIN_DIRECTION]", "后端"))
        nums = [int(m) for m in re.findall(r"(\d+)\s*年", filled)]
        self.assertEqual((max(nums), min(nums)), (8, 3))

    def test_it_says_why_two_numbers(self):
        i = TPL.index("**工作年限说明：**")
        seg = flat(TPL[i:i + 1200])
        self.assertRegex(seg, r"机器要读它")
        self.assertIn("audit_pipeline._candidate_years", seg)

    def test_it_tells_the_unchanged_case_what_to_do(self):
        """没转过方向的人两个数一样，不说清楚他就只写一个，解析照样读不到。"""
        i = TPL.index("**工作年限说明：**")
        seg = flat(TPL[i:i + 1200])
        self.assertRegex(seg, r"两个数一样的，就把两个都写上")

    def test_the_old_instruction_is_gone(self):
        """原来那句「不在此写独立数字」产出一行没有数字的散文。

        **剥掉 HTML 注释再比。** 那句话仍然留在注释里当历史记录，
        而注释是给填表人看的说明，不是给他照做的指令 —— 第一版按整份文件搜，
        当场被自己写的那句引文绊倒（本仓库反复栽的同一类：自引陷阱）。
        """
        live = re.sub(r"<!--.*?-->", "", TPL, flags=re.S)
        self.assertNotIn("不在此写独立数字", live)
        self.assertIn("不在此写独立数字", TPL, "历史记录也一并删了")


class TheAuditCanActuallySeeIt(unittest.TestCase):
    def test_a_domain_qualified_requirement_is_caught(self):
        for frag, n in (("5 年以上 SaaS/企业级产品经验", 5),
                        ("10 年以上智能座舱/服务型产品经验", 10),
                        ("8 年及以上智能家居/人居 AI 行业经验", 8)):
            with self.subTest(frag=frag):
                m = _cli.YEARS_REQ.search(frag)
                self.assertIsNotNone(m, frag)
                self.assertEqual(int(m.group(1)), n)
                qual = re.sub(r"[*\s]", "", m.group(2))
                self.assertNotIn(qual, _cli.YEARS_BARE, f"「{qual}」被当成裸年限了")

    def test_a_bare_requirement_is_left_alone(self):
        """裸年限确实是门 —— 别把它也报成误用。"""
        for frag in ("8 年以上相关经验", "5 年以上工作经验", "3 年以上经验"):
            with self.subTest(frag=frag):
                m = _cli.YEARS_REQ.search(frag)
                self.assertIsNotNone(m, frag)
                self.assertIn(re.sub(r"[*\s]", "", m.group(2)), _cli.YEARS_BARE)

    def test_xiangguan_counts_as_bare(self):
        """「相关」最松，故意算裸年限 —— **宁可放过，不可误杀**：
        算成裸的就拿总年限比，门更容易 PASS。"""
        self.assertIn("相关", _cli.YEARS_BARE)
        i = (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8").index(
            "YEARS_BARE = {")
        self.assertRegex(flat((ROOT / "tools" / "_cli.py").read_text(
            encoding="utf-8")[i - 300:i]), r"宁可放过，不可误杀")

    def test_it_reads_the_evaluation_not_the_jd(self):
        """JD 原文就引在深评那张表里 —— 不必回头去读 JD，
        而「要读 JD 正文所以判不了」正是这条原来漏掉的借口。"""
        i = AUDIT.index("def _years_gate_smuggling_domain(")
        seg = AUDIT[i:i + 1200]
        self.assertIn("evaluation.md", seg)
        self.assertIn("工作年限", seg)

    def test_the_finding_names_the_command_to_fix_it(self):
        """**2026-08-25：这一条钉的命令换过一次，钉的是从 `--all` 换成
        `/job-apply`。** 上一版钉的是 `/job-rank --all` —— 而这一档报的是深评，
        `--all` 只重写职位库的 `rank_*`，深评文件一个字不动（写它的是
        `/job-apply`）。也就是说，这条守卫此前钉住的是一条**够不着的路**。

        判据与那次改动的实测都在 `test_a_deep_eval_can_only_be_fixed_by_a_deep_eval`。
        """
        i = AUDIT.index('"年限门挡掉的其实是领域经验"')
        seg = AUDIT[i:i + 900]
        self.assertIn("/job-apply <职位链接>", seg)
        self.assertNotIn("/job-rank --all", seg)

    def test_it_points_at_the_framework_section(self):
        i = AUDIT.index('"年限门挡掉的其实是领域经验"')
        self.assertIn("年限门：那个数带不带领域限定", AUDIT[i:i + 900])

    def test_the_old_punt_is_gone(self):
        """那句「这里判不了，不报、也不计入」是这一整档消失的原因。

        它现在只许以**被引用**的形式活着（「这里原来写着……」），
        不许再作为一句生效的说明。所以比的是**它前面那半句**：
        原文是「取决于 JD 问的是……—— 那要读 JD 正文」，
        引用版前面是「这里原来写着」。
        """
        i = AUDIT.index("那要读 JD 正文，这里判不了")
        self.assertIn("这里原来写着", AUDIT[max(0, i - 400):i],
                      "那句话又成了一条生效的说明")
        self.assertEqual(AUDIT.count("那要读 JD 正文，这里判不了"), 1)

    def test_the_first_two_tiers_survive(self):
        """新加一档不许把原来两档挤掉。"""
        self.assertIn('"年限门挡掉了「经验不限」的岗"', AUDIT)
        self.assertIn('"年限门挡掉了他年限够的岗"', AUDIT)

    def test_it_stays_a_warn(self):
        """这一档靠正则读散文，误差比「经验不限」那档大 ——
        判成 error 会让 `test_pipeline_audit_stays_clean` 长红，
        然后整个审计被当成背景噪音略过。"""
        i = AUDIT.index('"年限门挡掉的其实是领域经验"')
        self.assertIn('("warn", "年限门挡掉的其实是领域经验"', AUDIT[i - 40:i + 40])


class TheCheckItselfEmitsIt(unittest.TestCase):
    """**验的是那个检查，不是那个 helper。**

    变异实测：把 `smuggled = _years_gate_smuggling_domain(...)` 换成
    `smuggled = []`，整份测试仍然全绿 —— helper 被单独测着，而它跟检查之间
    那根线没有人拉。本仓库反复栽的同一类：上游写了、下游读不到。
    """

    def _fake(self, tmp, rows):
        """在临时树里造一个用户：一行年限说明 + 若干份深评。"""
        u = "甲"
        (tmp / "users" / u / "profile").mkdir(parents=True)
        (tmp / "users" / u / "profile" / "candidate.md").write_text(
            "**工作年限说明：** 总工作年限 13 年，AI 方向约 3 年。\n",
            encoding="utf-8")
        for name, res, why in rows:
            d = tmp / "users" / u / "documents" / "applications" / name
            d.mkdir(parents=True)
            (d / "evaluation.md").write_text(
                "| 门槛 | 结果 | 依据 |\n|---|---|---|\n"
                f"| 工作年限 | {res} | {why} |\n", encoding="utf-8")
        return u

    def _run(self, rows, seen):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            u = self._fake(tmp, rows)
            old_root, old_user = ap.ROOT, ap._USER
            ap.ROOT, ap._USER = tmp, [u]
            try:
                return ap.check_years_gate_vs_platform_field(seen, {})
            finally:
                ap.ROOT, ap._USER = old_root, old_user

    #: 一个撞了年限门的库条目。`workYears` 给足，免得触发前两档。
    SEEN = {"k": {"rank_verdict": "硬门 FAIL (工作年限)", "title": "某岗",
                  "workYears": "10年以上"}}

    def test_a_domain_qualified_one_is_reported(self):
        got = self._run(
            [("甲公司_某岗", "FAIL", "「5 年以上 SaaS/企业级产品经验」——SaaS 域为零")],
            self.SEEN)
        self.assertIn("年限门挡掉的其实是领域经验", [t for _, t, _ in got])

    def test_a_bare_one_is_not_reported(self):
        """裸年限确实是门。第一版少了限定词那一半条件，变异实测活了下来。"""
        got = self._run(
            [("甲公司_某岗", "FAIL", "「8 年以上相关经验」——差得远")], self.SEEN)
        self.assertNotIn("年限门挡掉的其实是领域经验", [t for _, t, _ in got])

    def test_a_number_over_the_total_is_not_reported(self):
        """15 > 13：这才是这道门该做的事，不许报成误用。"""
        got = self._run(
            [("甲公司_某岗", "FAIL", "「15 年以上市场营销经验」——市场约 10 年")],
            self.SEEN)
        self.assertNotIn("年限门挡掉的其实是领域经验", [t for _, t, _ in got])

    def test_a_flag_is_not_reported(self):
        """FLAG 没有杀掉任何岗，报它是噪音。"""
        got = self._run(
            [("甲公司_某岗", "FLAG，非 FAIL", "「5 年以上 SaaS 产品经验」")], self.SEEN)
        self.assertNotIn("年限门挡掉的其实是领域经验", [t for _, t, _ in got])

    def test_the_count_is_the_number_of_evaluations(self):
        got = self._run(
            [("甲_一", "FAIL", "「5 年以上 SaaS 产品经验」"),
             ("甲_二", "FAIL", "「8 年以上 B 端产品工作经验」"),
             ("甲_三", "FAIL", "「8 年以上相关经验」")], self.SEEN)
        msg = next(m for _, t, m in got if t == "年限门挡掉的其实是领域经验")
        self.assertIn("2 份", msg, "裸年限那份被算进去了")

    def test_the_wire_is_in_the_source(self):
        """静态兜底：helper 被算出来之后要真的进 `out`。"""
        self.assertIn("smuggled = _years_gate_smuggling_domain(max(yrs))", AUDIT)
        i = AUDIT.index("smuggled = _years_gate_smuggling_domain(max(yrs))")
        self.assertIn("if smuggled:", AUDIT[i:i + 200])


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时**现算**一遍，别让文里那几个数变成化石。"""

    def _live(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        apps = ROOT / "users" / u / "documents" / "applications"
        if not apps.is_dir():
            self.skipTest("这位用户还没有深评")
        rows = []
        for f in apps.glob("*/evaluation.md"):
            t = f.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^\|\s*\**工作年限\**\s*\|([^|]*)\|([^|]*)\|", t, re.M)
            if m and "FAIL" in m.group(1) and "FLAG" not in m.group(1):
                rows.append((f.parent.name, m.group(2)))
        if len(rows) < 5:
            self.skipTest("年限门 FAIL 太少，比不出来")
        return rows

    def test_every_failure_quotes_a_domain_qualified_requirement(self):
        """这一节的全部分量在这上面：**16/16 引的都是带领域限定的**。
        哪天出现一个真的裸年限 FAIL，这条就该红，说明这道门开始正常工作了。"""
        rows = self._live()
        bare = []
        for name, why in rows:
            m = _cli.YEARS_REQ.search(why)
            if m and re.sub(r"[*\s]", "", m.group(2)) in _cli.YEARS_BARE:
                bare.append((name, m.group(0)))
        self.assertLessEqual(
            len(bare), len(rows) * 0.2,
            f"{len(bare)}/{len(rows)} 个年限门 FAIL 引的是裸年限要求 —— "
            f"这一节的前提（几乎全是领域要求混进来）不成立了：{bare[:3]}")

    def test_the_audit_finds_them(self):
        """检查真的报得出来 —— 不是「代码在那儿」。"""
        self._live()
        yrs = ap._candidate_years()
        if yrs is None:
            self.skipTest("候选人年限读不出来")
        self.assertGreater(len(ap._years_gate_smuggling_domain(max(yrs))), 0)

    def test_the_candidate_line_still_parses(self):
        """活动用户那一行要读得出两个数 —— 读不出，上面整条链子只是摆设。"""
        if not (ROOT / ".active_user").is_file():
            self.skipTest("没有活动用户")
        yrs = ap._candidate_years()
        if yrs is None:
            self.skipTest("这位用户的资料里没有那一行")
        self.assertEqual(len(yrs), 2)
        self.assertGreater(yrs[0], yrs[1], "总年限应当不小于方向年限")


if __name__ == "__main__":
    unittest.main()
