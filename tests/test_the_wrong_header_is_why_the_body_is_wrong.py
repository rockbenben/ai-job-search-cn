# -*- coding: utf-8 -*-
"""两条检查各报一半，而它们是同一件事的因和果。

审计眼下报着两条不相干的警告：

    话术抬头没说清在跟谁说话        110 份没写、28 份写反
    猎头岗的开场白对着顾问说「贵司」   9 份

**它们是一件事。** 抬头写着「直招」，起草的人就照着「对面是用人方」写，
于是正文对着一个猎头顾问讲「贵司如何如何」。这条因果本来就写在那个函数的
说明里（「照着『直招』写，就会对着顾问讲『贵司如何如何』」）——
**而报出去的两条消息里一个字都没有**。

读的人看到的是两条并列的毛病，于是去把那一句「贵司」改掉，抬头留在原地 ——
下次重跑照样写错。

## 拿对照组说话，不拿单边的数

实测活动用户 2026-08-25（库里是猎头的 130 份话术）：

    抬头写反（说直招） 28 份 → 正文对错了人 6 份（21%）
    抬头写对（说猎头） 42 份 → 正文对错了人 1 份（2%）
    抬头没写           60 份

单说「28 份里 6 份」看不出是不是这一档本来就容易错。**拿写对的那批一比，
差出一个量级**，才说得上是因果而不是巧合。

## 两头都要说

    抬头那条   写反的代价看得见：这批里 N 份正文跟着对错了人（对照组只有 M）
    贵司那条   其中 K 份的抬头本身就写反了 —— 只改这一句，下次重跑还会错

只在一头说，另一头的读者仍然看不见。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import audit_pipeline as ap  # noqa: E402

AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def fallout_src() -> str:
    i = AUDIT.index("def _addressee_fallout")
    return AUDIT[i:AUDIT.index("\n\ndef ", i)]


class TheOverlapIsTracked(unittest.TestCase):
    def test_the_three_sets_exist(self):
        for name in ("_dir_wrong_kind", "_dir_wrong_who", "_dir_right_kind"):
            with self.subTest(name=name):
                self.assertIn(name, AUDIT)

    def test_they_are_keyed_by_directory(self):
        """显示串带着括注（「写『直招』，库里是『猎头』」），拿它做交集会全落空。"""
        self.assertIn("_dir_wrong_kind.add(f.parent.name)", AUDIT)
        self.assertIn("_dir_wrong_who.add(f.parent.name)", AUDIT)

    def test_the_control_group_is_only_headhunter_jobs(self):
        """对照组要是同一类岗 —— 把直招岗算进来，那批本来就不会说错人。"""
        i = AUDIT.index("_dir_right_kind.add(f.parent.name)")
        self.assertIn('elif real == "猎头":', AUDIT[max(0, i - 200):i])

    def test_the_reason_is_recorded(self):
        i = AUDIT.index("_dir_wrong_kind, _dir_wrong_who, _dir_right_kind")
        seg = flat(AUDIT[max(0, i - 900):i])
        self.assertRegex(seg, r"是同一件事的因和果")
        self.assertRegex(seg, r"\*\*而报出去的两条消息里一个字都没有\*\*")
        self.assertRegex(seg, r"下次重跑照样写错")


class TheComparisonIsAgainstAControlGroup(unittest.TestCase):
    def test_it_reports_both_rates(self):
        b = fallout_src()
        self.assertIn("ra, rb =", b)
        self.assertIn("而抬头写对的", b)

    def test_it_says_why_a_single_rate_is_not_enough(self):
        b = flat(fallout_src())
        self.assertRegex(b, r"只报\*\*比例差\*\*，不报单边的数")
        self.assertRegex(b, r"差出一个量级才说得上是因果")

    def test_it_stays_quiet_on_tiny_samples(self):
        """样本小的时候比例是噪音。"""
        b = fallout_src()
        self.assertIn("if len(wrong) < 10 or len(right) < 10:", b)

    def test_it_stays_quiet_when_the_rates_are_close(self):
        """**没拉开差距就别把巧合说成因果。**"""
        b = fallout_src()
        self.assertIn("if ra <= rb * 2:", b)
        self.assertRegex(flat(b), r"别把巧合说成因果")

    def test_a_clear_signal_speaks(self):
        wrong = {f"w{i}" for i in range(20)}
        right = {f"r{i}" for i in range(20)}
        gui = {f"w{i}" for i in range(8)} | {"r0"}
        said = ap._addressee_fallout(wrong, right, gui)
        self.assertIn("40%", said)
        self.assertIn("5%", said)
        self.assertIn("先改抬头", said)

    def test_a_flat_signal_says_nothing(self):
        wrong = {f"w{i}" for i in range(20)}
        right = {f"r{i}" for i in range(20)}
        gui = {f"w{i}" for i in range(5)} | {f"r{i}" for i in range(5)}
        self.assertEqual(ap._addressee_fallout(wrong, right, gui), "")

    def test_a_tiny_sample_says_nothing(self):
        self.assertEqual(
            ap._addressee_fallout({"a"}, {"b"}, {"a"}), "")

    def test_no_overlap_says_nothing(self):
        wrong = {f"w{i}" for i in range(20)}
        right = {f"r{i}" for i in range(20)}
        self.assertEqual(ap._addressee_fallout(wrong, right, {"r0"}), "")

    def test_it_points_at_the_other_finding(self):
        said = ap._addressee_fallout({f"w{i}" for i in range(20)},
                                     {f"r{i}" for i in range(20)},
                                     {f"w{i}" for i in range(8)})
        self.assertIn("猎头岗的开场白对着顾问说「贵司」", said)

    def test_it_carries_the_measurement(self):
        b = fallout_src()
        self.assertIn("2026-08-25", b)
        # 两行都要钉：只钉一行时，删掉另一行照样绿（变异实测）
        self.assertIn("抬头写反（说直招） 28 份 → 正文对错了人 6 份（21%）", b)
        self.assertIn("抬头写对（说猎头） 42 份 → 正文对错了人 1 份（2%）", b)

    def test_the_measurement_names_the_judge_it_used(self):
        """手搜「贵司」会少算 —— 那条正本还收「你们」「咱们」这类。
        不写清用的是哪一把尺，下一个人复算会得到别的数（我就得到过 8）。"""
        b = flat(fallout_src())
        self.assertRegex(b, r"按 `_WRONG_ADDRESSEE` 这条正本判")
        self.assertRegex(b, r"手工只搜「贵司」会少算")


class BothSidesCarryTheLink(unittest.TestCase):
    def _msgs(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = _cli.pick_user("", root=ROOT)
        seen, details = ap.load(user)
        ap._USER[:] = [user]
        got = ap.check_outreach_header_says_who_youre_talking_to(seen, details)
        return {k: m for _l, k, m in got}

    def test_the_addressee_side_names_the_header(self):
        """**同上：「该不该说」独立算。** 拿「说了没有」当跳过条件，
        把整句删掉就变成 skip（变异实测，这一轮两头各栽了一次）。"""
        m = self._msgs().get("猎头岗的开场白对着顾问说「贵司」")
        if not m:
            self.skipTest("这一条现在不触发 —— 好事")
        wrong, right, gui = self._groups()
        n = len(wrong & gui)
        if not n:
            self.assertNotIn("的抬头本身就写反了", m, "不该说的时候说了")
            self.skipTest("这一批的抬头都写对了 —— 本来就不该说")
        self.assertIn(f"其中 {n} 份的抬头本身就写反了", m, "该说的时候没说")
        self.assertIn("只改这一句、不改抬头，下次重跑还会照着错的对象写", m)

    def test_the_header_side_names_the_fallout(self):
        """**「该不该出现」要独立算出来，不能拿「出现了没有」当跳过条件。**

        原来这条写的是「文本里没有那句就 skip」—— 于是把整段因果从消息里
        拆掉，它变成 skip 而不是红（变异实测）。用「它在不在」决定「要不要验
        它在不在」，是一条永远绿的断言。
        """
        m = self._msgs().get("话术抬头没说清在跟谁说话")
        if not m:
            self.skipTest("这一条现在不触发 —— 好事")
        want = bool(self._fallout_expected())
        if not want:
            self.assertNotIn("写反的代价看得见", m, "不该说的时候说了")
            self.skipTest("这一轮样本太小或没拉开差距 —— 本来就不该说")
        self.assertIn("写反的代价看得见", m, "该说的时候没说")
        self.assertRegex(m, r"这 \d+ 份里 \d+ 份（\d+%）正文对着顾问说了「贵司」")
        self.assertRegex(m, r"而抬头写对的 \d+ 份里只有 \d+ 份（\d+%）")
        self.assertIn("先改抬头，正文那条自然少", m)

    def _fallout_expected(self) -> str:
        """拿那个纯函数在真数据上现算一遍 —— 消息里该不该有那段，它说了算。"""
        return ap._addressee_fallout(*self._groups())

    def _groups(self):
        """在测试这边独立分一遍组：写反的 / 写对的 / 对错了人的。"""
        import re as _re
        user = _cli.pick_user("", root=ROOT)
        seen = _cli.seen_of(_cli.load_json_stamped(
            ROOT / "users" / user / "job_scraper" / "seen_jobs.json")[0])
        by = {_cli.norm_url(e.get("url") or ""): e for e in seen.values()
              if isinstance(e, dict) and e.get("url")}
        apps = ROOT / "users" / user / "documents" / "applications"
        if not apps.is_dir():
            return set(), set(), set()
        wrong, right, gui = set(), set(), set()
        for f in sorted(apps.glob("*/outreach.md")):
            t = f.read_text(encoding="utf-8", errors="replace")
            mm = _re.search(r"职位链接\s*[：:]\s*(\S+)", t)
            e = by.get(_cli.norm_url(mm.group(1))) if mm else None
            if not e or not e.get("isHeadhunter"):
                continue
            head = ap._head_of(t)
            # 重推规则的测试**测不出规则变了** —— 走正本
            # （`test_shared_vocab_single_source.py` 盯着这条）。
            said = _cli.addressee_said(head)
            if said == "直招":
                wrong.add(f.parent.name)
            elif said == "猎头":
                right.add(f.parent.name)
            g = ap._greeting_of(t)
            if g and ap._WRONG_ADDRESSEE.search(g):
                gui.add(f.parent.name)
        return wrong, right, gui

    def test_neither_side_lost_what_it_already_said(self):
        """每一句解释都要跟着它解释的那一半走 —— 但只在那一半真的报了的时候。

        「那是文件错、字段对」讲的是**写反**那一类（猎聘只对猎头岗隐雇主名，
        所以雇主名是「某…公司」而抬头写着直招时，错的是文件不是字段）。
        2026-08-30 那 28 份写反的被 `tools/outreach_header.py` 一次改完之后，
        这条自检只剩「4 份没写是哪一种」，那句解释自然不再印 ——
        **无条件断言它就成了「清干净反而红」**。
        """
        msgs = self._msgs()
        a = msgs.get("话术抬头没说清在跟谁说话")
        if a:
            self.assertIn("见 06「渠道判定」那张表", a)
            if "写反" in a:
                self.assertIn("那是文件错、字段对", a)
        b = msgs.get("猎头岗的开场白对着顾问说「贵司」")
        if b:
            self.assertIn("对面是顾问不是用人方", b)

    def test_no_markdown_reaches_the_terminal(self):
        for m in self._msgs().values():
            with self.subTest(m=m[:20]):
                self.assertNotIn("**", m)


class TheCausalClaimIsAlreadyInTheSpec(unittest.TestCase):
    """这一条不是新立规矩，是把一条早写下的因果接到报告上。"""

    def test_the_docstring_already_said_it(self):
        """**锚在那句话本身，不是函数前的一个窗口。**

        它前面刚插进一个新函数，3000 字的窗口当场切歪 —— 这一轮第三次栽在
        「按窗口切」上。
        """
        self.assertIn("照着「直招」写，就会对着顾问讲「贵司如何如何」", AUDIT)
        import ast
        function = next(node for node in ast.walk(ast.parse(AUDIT))
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "check_outreach_header_says_who_youre_talking_to")
        self.assertIn("照着「直招」写，就会对着顾问讲「贵司如何如何」",
                      ast.get_docstring(function))


    def test_the_rule_it_leans_on_still_exists(self):
        tpl = (ROOT / "workflows" / "reference"
               / "06-outreach-templates.md").read_text(encoding="utf-8")
        self.assertRegex(flat(tpl), r"对面是顾问不是用人方")

    def test_the_field_is_the_source_of_truth(self):
        """文件错、字段对 —— 反过来就不该改抬头了。"""
        i = AUDIT.index('real = "猎头" if e.get("isHeadhunter") else "直招"')
        self.assertIn("said != real", AUDIT[i:i + 200])


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：写反那批的出错率真的高出一截。"""

    def _rates(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = _cli.pick_user("", root=ROOT)
        seen = _cli.seen_of(_cli.load_json_stamped(
            ROOT / "users" / user / "job_scraper" / "seen_jobs.json")[0])
        by = {_cli.norm_url(e.get("url") or ""): e for e in seen.values()
              if isinstance(e, dict) and e.get("url")}
        apps = ROOT / "users" / user / "documents" / "applications"
        if not apps.is_dir():
            self.skipTest("还没有材料")
        wrong = right = wg = rg = 0
        for f in sorted(apps.glob("*/outreach.md")):
            t = f.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"职位链接\s*[：:]\s*(\S+)", t)
            e = by.get(_cli.norm_url(m.group(1))) if m else None
            if not e or not e.get("isHeadhunter"):
                continue
            head = t[:400]
            gui = "贵司" in t
            if "直招" in head and "猎头" not in head:
                wrong += 1
                wg += gui
            elif "猎头" in head:
                right += 1
                rg += gui
        if wrong < 10 or right < 10:
            self.skipTest(f"样本太小（写反 {wrong} / 写对 {right}）")
        return wrong, wg, right, rg

    def test_the_wrong_header_group_errs_far_more(self):
        """**支点。** 两边差不多时，这一整条就不该说话（代码也确实不说）。"""
        wrong, wg, right, rg = self._rates()
        ra, rb = wg * 100 / wrong, rg * 100 / right
        self.assertGreater(ra, rb * 2,
                           f"写反 {wg}/{wrong}（{ra:.0f}%）vs "
                           f"写对 {rg}/{right}（{rb:.0f}%）—— 没拉开，论点要重看")

    def test_the_field_disagrees_with_the_file_not_the_other_way(self):
        """写反的那批全是一个方向（文件说直招、库说猎头）—— 既有判据。"""
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = _cli.pick_user("", root=ROOT)
        seen, details = ap.load(user)
        ap._USER[:] = [user]
        got = {k: m for _l, k, m in
               ap.check_outreach_header_says_who_youre_talking_to(seen, details)}
        m = got.get("话术抬头没说清在跟谁说话")
        if not m or "写反的例" not in m:
            self.skipTest("这一轮没有写反的")
        self.assertNotIn("写「猎头」，库里是「直招」", m)


if __name__ == "__main__":
    unittest.main()
