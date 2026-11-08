# -*- coding: utf-8 -*-
"""「自己再扫一眼 JD 正文」—— 2581 份正文，扫哪几个没人说。

`dupOf` 的键是「公司字符串 + JD 正文前 300 字」。**带公司是对的**：同一份 JD
模板真的会被不同雇主原样复用，只按正文归并会把两个真岗合成一个、在页面上
整条抹掉一个（`export_web_data` 那段注释记了实测撞上的那次）。这条裁定不动。

代价是「同一个岗被两家猎头各自脱敏成不同公司名」认不出来，而 `job-apply.md`
对这批的交代是「选岗时**自己再扫一眼 JD 正文**……同一个岗别打两次招呼：
两边猎头撞车对候选人是减分的」。规则对，**可它没说扫哪几个**。

实测活动用户 2026-08-25：

    JD 正文前 300 字一字不差的组      66 组 / 156 个岗
    └ 公司名相同（已归并 dupOf）       22 组
    └ **公司名不同（故意没并）**       44 组 / 100 个岗
       └ 两条以上都还活着的            12 组 / 27 个岗
       └ **已经出过整套材料的**         11 个岗

而算这件事的数据导出器**刚算完就扔了**（正文前缀哈希就在同一个循环里）。

当天面板上「可以投」的前六里，「智能体软件需求专家」并排挂着两条
（某大型整车制造公司 96-144 万 / 某上海整车制造上市公司 63-91 万），
两条都是「值得投」，其中一条材料就绪等着发。

## 只标不并

判不了：可能是一个岗两家猎头在代招（只该投一个），也可能是两家公司套了
同一份模板（两个都该投）——两种的下一步正好相反。所以摆出来给人看，
不归并、不隐藏、不替他决定。判不出来时按「两个都跑」办：多花一次工时，
好过少投一个真岗。
"""
import hashlib
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import _cli  # noqa: E402
import _srcscan  # noqa: E402
from jsx import element_color  # noqa: E402

EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
TYPES = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
READOUT = (ROOT / "web" / "src" / "components"
           / "JobReadout.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?|//:?|\*)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def _block() -> str:
    i = EX.index("# ---- 同文不同名：**不归并，只标出来** ---")
    return EX[i:EX.index('if n_same:', i)]


class ItComputesTheGroup(unittest.TestCase):
    def test_it_reuses_the_hash_already_computed(self):
        """再读一遍 2581 份 JSON 是白花的 —— 上一个循环刚算过。"""
        i = EX.index("by_body.setdefault(prefix, []).append(job)")
        seg = EX[max(0, i - 300):i]
        self.assertIn('prefix = hashlib.sha1(norm[:300].encode("utf-8")).hexdigest()', seg)

    def test_the_company_key_still_carries_the_company(self):
        """**那条裁定不许动。** 去掉公司就会错并两家套同一模板的雇主。"""
        i = EX.index("key = hashlib.sha1(")
        self.assertIn("(job.get('company') or '').strip()", EX[i:i + 200])

    def test_it_requires_the_company_to_differ(self):
        """公司相同的那批走 `duplicates`（已归并）—— 不能在这儿再报一遍。"""
        b = _block()
        self.assertIn('(x.get("company") or "").strip()', b)
        self.assertIn('!= (j.get("company") or "").strip()', b)

    def test_it_skips_already_merged_entries(self):
        """`dupOf` 的在页面上任何地方都不渲染，摆出来点不开。"""
        b = _block()
        self.assertIn('live = [j for j in group if not j.get("dupOf")]', b)

    def test_it_never_merges_or_hides(self):
        """**这是它和 `dupOf` 的全部区别。** 一旦开始写 dupOf 就越界了。"""
        b = _block()
        self.assertNotIn('dupOf"] =', b)
        self.assertNotIn("skipped", b)

    def test_it_carries_what_the_user_needs_to_decide(self):
        b = _block()
        for k in ('"url"', '"company"', '"salary"', '"score"'):
            with self.subTest(k=k):
                self.assertIn(k, b)


class TheReasonIsRecorded(unittest.TestCase):
    def test_it_says_why_it_does_not_merge(self):
        b = flat(_block())
        self.assertRegex(b, r"那条裁定是对的，这里一个字都不改")
        self.assertRegex(b, r"错并的代价是一个岗在页面上整条消失")

    def test_it_says_why_a_rule_alone_was_not_enough(self):
        """规则一直都在 —— 缺的是「扫哪几个」。"""
        b = flat(_block())
        self.assertRegex(b, r"可它没说扫哪几个")
        self.assertRegex(b, r"2581 个岗靠肉眼扫，这条规则等于没有")

    def test_it_quotes_the_rule_it_is_backing(self):
        """引原话，不转述 —— 转述一遍就等着两处各长各的。"""
        b = flat(_block())
        self.assertRegex(b, r"`job-apply\.md` 对这批的交代是")
        self.assertRegex(b, r"两边猎头撞车对候选人是减分的")

    def test_that_rule_really_says_that(self):
        self.assertRegex(flat(APPLY), r"两边猎头撞车对候选人是减分的")

    def test_it_carries_the_measurement(self):
        b = _block()
        self.assertIn("2026-08-25", b)
        for n in ("66 组", "44 组", "12 组"):
            with self.subTest(n=n):
                self.assertIn(n, b)

    def test_it_says_why_it_cannot_decide(self):
        """两种读法的下一步正好相反 —— 这就是「不替他判」的理由。"""
        b = flat(_block())
        self.assertRegex(b, r"前者只投一个，后者两个都投")

    def test_the_ruling_it_leans_on_still_stands(self):
        """「宁可漏归组，不可错合并」没了，这一条就没有立足点。"""
        self.assertRegex(flat(EX), r"\*\*宁可漏归组，不可错合并\*\*")

    def test_it_prints_how_many(self):
        """默不作声地标上，等于没标 —— 跑导出的人要知道有这回事。"""
        i = EX.index("if n_same:")
        seg = flat(EX[i:i + 500])
        self.assertRegex(seg, r"JD 正文开头相同、公司名不同")
        self.assertRegex(seg, r"投之前自己看一眼")


class ThePanelShowsIt(unittest.TestCase):
    def test_the_type_exists(self):
        self.assertIn("sameJd?: {", TYPES)

    def test_the_type_says_it_is_not_duplicates(self):
        """两个字段挨着、长得也像 —— 不点破，下一个人会把它们并成一个。"""
        i = TYPES.index("sameJd?: {")
        seg = flat(TYPES[max(0, i - 900):i])
        self.assertRegex(seg, r"和 `duplicates` 是两回事")
        self.assertRegex(seg, r"这批\*\*判不了\*\*")

    def test_the_type_names_the_cost(self):
        i = TYPES.index("sameJd?: {")
        self.assertRegex(flat(TYPES[max(0, i - 900):i]),
                         r"同一个岗投给两家猎头会撞单")

    def test_the_readout_renders_it(self):
        """钉整个开花括号 —— 只判条件本身，前面加个 `false &&` 照样绿
        （变异实测过）。"""
        self.assertIn("{job.sameJd && job.sameJd.length > 0 && (", READOUT)

    def test_it_states_both_readings_and_the_action(self):
        i = READOUT.index("job.sameJd && job.sameJd.length > 0")
        seg = flat(READOUT[i:i + 1200])
        self.assertRegex(seg, r"公司写的却不是同一家")
        self.assertRegex(seg, r"真是同一个就只投一个，两边都投会撞单")

    def test_it_links_out_so_he_can_compare(self):
        """只说「另有 N 个」他没法核 —— 得点得开。"""
        i = READOUT.index("job.sameJd && job.sameJd.length > 0")
        seg = READOUT[i:i + 1200]
        self.assertIn("href={d.url}", seg)
        self.assertIn("d.company", seg)

    def test_it_is_marked_as_something_to_watch(self):
        """这句话拿到的是琥珀（「要留意」），不是安抚色也不是判定色。

        原来锚的是「条件表达式之后 400 个字符里有没有 `var(--caution)`」。
        2026-09-30 把这条静态颜色从 inline style 收进 `.act-note.is-warn`，
        窗口里再也没有那个字串——**而颜色一个字没变**，证人却红了。
        窗口和「颜色写在哪」都不能当锚，所以改问：包着这句话的元素最终是什么色。
        内联与 class 两条路都由 `jsx.element_color` 认（一份实现，两处共用）。
        """
        i = READOUT.index("job.sameJd && job.sameJd.length > 0")
        seg = _srcscan.strip_comments(READOUT[i:])   # 注释里也写着这句话，先剥
        color = element_color(seg, "公司写的却不是同一家", CSS)
        self.assertEqual(color, "var(--caution)",
                         "「另有 N 家同 JD」是要留意，不是安抚（灰）也不是不满足（红）")

    def test_the_merged_one_still_renders(self):
        """这一条是加的，`duplicates` 那条一个字不许动。"""
        self.assertIn("job.duplicates && job.duplicates.length > 0", READOUT)
        self.assertIn("这个岗在别处也挂着，价不一样：", READOUT)

    def test_no_markdown_leaks_into_the_node(self):
        """这句字进的是纯文本节点（AGENTS.md 末尾那条）。"""
        i = READOUT.index("这个岗的职位描述和另外")
        self.assertNotIn("**", READOUT[i:i + 400])


class TheWorkflowPointsAtTheList(unittest.TestCase):
    def _seg(self) -> str:
        i = APPLY.index("> **别再靠肉眼扫。**")
        return flat(APPLY[i:APPLY.index("**其余那几条按「镜像目录」落盘", i)])

    def test_it_no_longer_tells_him_to_scan_by_eye(self):
        """**这是修掉的那一处。** 2581 份正文，人不会去扫。"""
        self.assertNotIn("**所以选岗时自己再扫一眼 JD 正文**", APPLY)

    def test_it_names_the_field(self):
        s = self._seg()
        self.assertIn("`sameJd`", s)
        self.assertIn("web/public/data.json", s)

    def test_it_names_what_the_panel_says(self):
        """他手边多半开着面板，不会去读 JSON。"""
        self.assertRegex(self._seg(), r"这个岗的职位描述和另外 N 个一字不差")

    def test_the_panel_really_says_that(self):
        self.assertIn("这个岗的职位描述和另外 ", READOUT)

    def test_both_branches_are_spelled_out(self):
        s = self._seg()
        self.assertRegex(s, r"认出是同一个岗就只跑一个")
        self.assertRegex(s, r"\*\*认出是两家公司套了同一份模板就两个都跑\*\*")

    def test_it_says_what_to_do_when_unsure(self):
        """两支都写了却不说拿不准怎么办，等于把判断推回给他。"""
        self.assertRegex(self._seg(),
                         r"判不出来时按\*\*两个都跑\*\*办：多花一次工时，好过少投一个真岗")

    def test_it_keeps_the_dont_merge_ruling(self):
        s = self._seg()
        self.assertRegex(s, r"\*\*只标不并\*\*")

    def test_the_old_incident_survives(self):
        """2026-08-17 那次实测是这一整段的由来，别连着一起改掉。"""
        self.assertRegex(flat(APPLY), r"实测 2026-08-17 一轮 29 个岗里撞上 4 组")

    def test_the_mirror_directory_convention_survives(self):
        self.assertIn("同岗重复挂牌.md", APPLY)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：拿真库重做一遍这个分组，再和导出的那份对账。"""

    def _data(self):
        p = ROOT / "web" / "public" / "data.json"
        if not p.is_file():
            self.skipTest("还没导出过面板数据")
        return json.loads(p.read_text(encoding="utf-8"))

    def _regroup(self):
        """照导出器同一套口径重算：正文前 300 字、<80 字不参与。"""
        d = self._data()
        user = user_or_skip()
        det = ROOT / "users" / user / "job_scraper" / "details"
        if not det.is_dir():
            self.skipTest("还没抓过 JD 正文")
        by = {}
        for j in d["jobs"]:
            f = det / f"{j['id']}.json"
            if not f.is_file():
                continue
            try:
                desc = json.loads(f.read_text(encoding="utf-8")).get("description") or ""
            except json.JSONDecodeError:
                continue
            norm = re.sub(r"\s+", "", desc)[:300]
            if len(norm) < 80:
                continue
            by.setdefault(hashlib.sha1(norm.encode("utf-8")).hexdigest(), []).append(j)
        groups = {k: v for k, v in by.items() if len(v) > 1}
        if len(groups) < 5:
            self.skipTest("同文的组太少，说不出话来")
        return d, groups

    def test_the_deliberately_unmerged_set_is_not_empty(self):
        """**这是整条的支点。** 一个都没有时，这一节没有存在的理由。"""
        _d, groups = self._regroup()
        cross = [v for v in groups.values()
                 if len({(x.get("company") or "").strip() for x in v}) > 1]
        self.assertGreater(len(cross), 5,
                           f"只有 {len(cross)} 组同文不同名 —— 这一节的论点要重看")

    def test_dup_of_really_does_not_catch_them(self):
        """归并的和这一批是两批人 —— 交集大了说明其中一条口径写错了。"""
        _d, groups = self._regroup()
        cross = [v for v in groups.values()
                 if len({(x.get("company") or "").strip() for x in v}) > 1]
        merged = sum(1 for v in cross for x in v if x.get("dupOf"))
        total = sum(len(v) for v in cross)
        self.assertLess(merged, total * 0.5,
                        f"{merged}/{total} 已经被 dupOf 并掉了 —— 那两套口径开始重叠")

    def test_the_export_flagged_them(self):
        d, groups = self._regroup()
        flagged = {j["id"] for j in d["jobs"] if j.get("sameJd")}
        self.assertTrue(flagged, "导出的那份里一个都没标")
        want = {x["id"] for v in groups.values()
                for x in v if not x.get("dupOf")
                if len({(y.get("company") or "").strip()
                        for y in v if not y.get("dupOf")}) > 1}
        missing = want - flagged
        self.assertEqual(missing, set(), f"{len(missing)} 个该标没标")

    def test_nothing_got_hidden(self):
        """**只标不并。** 被标出来的岗一个都不许带上 `dupOf`。"""
        d = self._data()
        bad = [j["id"] for j in d["jobs"] if j.get("sameJd") and j.get("dupOf")]
        self.assertEqual(bad, [], f"{len(bad)} 个既被标又被并了")

    def test_it_never_points_at_the_same_company(self):
        d = self._data()
        bad = []
        for j in d["jobs"]:
            me = (j.get("company") or "").strip()
            for x in j.get("sameJd") or []:
                if (x.get("company") or "").strip() == me:
                    bad.append(j["id"])
        self.assertEqual(bad, [], f"{len(bad)} 个指向了同名公司 —— 那是 duplicates 的活")

    def test_the_redundant_self_check_is_marked_as_such(self):
        """`x is not j` 今天走不到 —— 公司比较已经把自己排掉了。

        **不为它写断言**（那会永远绿，变异实测证过），改为钉住那段说明：
        下一个人要么读到「它是防御性的」，要么就该连同判据一起重想。
        """
        b = flat(_block())
        self.assertRegex(b, r"`x is not j` 这半是\*\*防御性的、今天走不到\*\*")
        self.assertRegex(b, r"别为它写测试")

    def test_some_of_them_already_cost_real_work(self):
        """已经各自出过材料的那批，是这一条真正防的东西。归零了就 skip。"""
        d = self._data()
        n = sum(1 for j in d["jobs"] if j.get("sameJd") and j.get("materials"))
        if not n:
            self.skipTest("没有同文的岗出过材料 —— 好事")
        self.assertGreater(n, 0)


if __name__ == "__main__":
    unittest.main()
