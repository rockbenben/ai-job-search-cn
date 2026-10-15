"""深评产出之后，库必须跟着改——evaluation.md 与 seen_jobs.json 不许各说各话。

## 为什么

`04-job-evaluation.md` 规定「深评一旦产出，必须覆盖粗筛分」，`resolve_score` 还额外
兜了一道（导出时有 evaluation.md 就以它为准）。**兜底反而把病藏住了**：面板显示的
是对的，库里躺着错的，而 `/job-rank` 的「已评过就跳过」、预筛、`/job-upskill` 读的全是库。

实测体检抓出 4 个 7 月底的老投递目录深评从没写回：

    某央企运营商研究院_智能体产品经理   库 44/不建议  ← 深评 62/值得投
    某科技上市公司_AI智能体解决方案负责人  库 76/强匹配  ← 深评 62/值得投

第二个正是「全库唯一 76 强匹配」——用户看着面板上的 62 做判断，AI 读库时却按
76 强匹配引用它。**两套真相，各自都显得对。**

## 三条不变量（全部跑在真实数据上，没有就跳过）

1. 有 evaluation.md 的岗：库里 `rank_score`/`rank_verdict`/`evaluated` 与文件一致；
2. `evaluated` 的条目判词不带「粗筛：」前缀（深评结论没有粗筛这回事）；
3. 已评分（`status != "new"`）的条目不许残留 `deprioritized` 降权标记——
   那是「待评时排队尾」用的，评完还挂着会误导下一轮抓取排序。
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import build_dashboard as bd  # noqa: E402


def _user_root():
    au = ROOT / ".active_user"
    if not au.is_file():
        return None
    u = ROOT / "users" / au.read_text(encoding="utf-8").strip()
    return u if (u / "job_scraper" / "seen_jobs.json").is_file() else None


class DeepEvalAndStoreAgree(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        u = _user_root()
        if u is None:
            raise unittest.SkipTest("没有活动用户或职位库")
        cls.seen = json.loads(
            (u / "job_scraper" / "seen_jobs.json").read_text(encoding="utf-8"))["seen"]
        cls.by_url = {}
        for v in cls.seen.values():
            cls.by_url.setdefault(v.get("url") or "", v)
        cls.apps = u / "documents" / "applications"

    def test_every_evaluation_md_is_written_back(self):
        if not self.apps.is_dir():
            self.skipTest("还没有投递目录")
        bad = []
        for d in sorted(self.apps.iterdir()):
            ev_f, po_f = d / "evaluation.md", d / "posting.md"
            if not (ev_f.is_file() and po_f.is_file()):
                continue
            m = re.search(r"链接[：:]\s*(\S+)", po_f.read_text(encoding="utf-8"))
            e = self.by_url.get(m.group(1) if m else "")
            if e is None:
                continue          # 链接接不上是另一个测试的事
            pe = bd.parse_evaluation(ev_f.read_text(encoding="utf-8"))
            try:
                score = int(str(pe.get("score")).strip())
            except (ValueError, TypeError):
                continue          # 文件里没有可解析的分（如已下线岗的残档）
            verdict = (pe.get("verdict") or "").strip()
            if not verdict:
                continue
            if e.get("rank_score") != score:
                bad.append(f"{d.name[:30]}: 文件 {score} ≠ 库 {e.get('rank_score')}")
            if (e.get("rank_verdict") or "").replace("粗筛：", "") != verdict:
                bad.append(f"{d.name[:30]}: 文件判词 {verdict!r} ≠ 库 {e.get('rank_verdict')!r}")
            if not e.get("evaluated"):
                bad.append(f"{d.name[:30]}: 深评过却没标 evaluated")
        self.assertEqual(bad, [],
                         "深评没写回库 —— 面板靠 resolve_score 兜底显示是对的，"
                         "但 /job-rank、预筛、/job-upskill 读的是库：\n  " + "\n  ".join(bad))

    def test_deep_evaluated_entries_carry_no_triage_prefix(self):
        bad = [v.get("title") for v in self.seen.values()
               if v.get("evaluated")
               and (v.get("rank_verdict") or "").startswith("粗筛：")]
        self.assertEqual(bad, [],
                         f"深评过的条目还挂着「粗筛：」前缀：{bad}")

    def test_ranked_entries_carry_no_parking_marker(self):
        bad = [v.get("title") for v in self.seen.values()
               if v.get("deprioritized") and v.get("status") != "new"]
        self.assertEqual(bad, [],
                         "已评分的条目还留着降权标记 —— 那是「待评时排队尾」用的，"
                         f"评完还挂着会误导下一轮抓取排序：{bad}")


class TheTwoRefusalsAreToldApart(unittest.TestCase):
    """拒收有**两种互不相干**的原因，各自有各自的改法，所以收尾必须分开说。

    ## 它坏在哪

    「同一个链接下挂了 2 个岗，从目录名认不出是哪一个」要改的是**目录名**；
    「文件把结论写到了技能档天花板以上」要改的是**评估文件**。两件事、两个动作。

    原来它们共用一个 `refused`，而收尾只印了后者的那句「评估文件自身把结论写高
    了」。实测 2026-10-15：活动用户 3 条拒收**全是前者**，于是每一条都被指去了
    「去改评估文件的结论」—— 而真要改的是目录名，改评估文件一点用没有。

    这正是这个仓库反复在治的形状：**一句话把人指去做了另一件事。** 而它比数字
    过期更难发现，因为每一句单看都通顺。

    ## 为什么钉源码而不跑工具

    这两种原因**哪一种会发生取决于语料**（今天只有前者）。跑工具验只能验今天碰巧
    出现的那一种，另一支照样能被人合回去还全绿。所以钉**形状**：两个列表、两句
    收尾，且「认不出」那一支的措辞里不许出现「写高」。
    """

    SRC = ROOT / "tools" / "writeback.py"

    def setUp(self):
        self.src = self.SRC.read_text(encoding="utf-8")

    def test_the_two_reasons_are_stored_apart(self):
        self.assertIn("refused_ambiguous", self.src)
        self.assertIn("refused_cap", self.src)
        self.assertNotRegex(
            self.src, r"refused\.append",
            "两个原因又被塞回同一个列表了")

    #: 扫「印给用户的那几行」时先把注释去掉 —— 这一支上面那段注释本来就写着
    #: 「它和『文件写高了』共用一个 refused」，那是记历史的。扫全文会让这条守卫
    #: 因为自己的说明而红，而它要挡的是**屏幕上的措辞**。
    @staticmethod
    def _code_only(text: str) -> str:
        return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())

    def test_the_ambiguous_branch_names_the_directory_fix(self):
        """「认不出是哪个岗」那一支必须说改目录名，且**不许**说「结论写高了」。"""
        i = self.src.find("if refused_ambiguous:")
        j = self.src.find("if refused_cap:", i)
        self.assertGreater(j, i, "两个分支的收尾顺序反了或有一个不见了")
        branch = self._code_only(self.src[i:j])
        self.assertIn("目录名", branch,
                      "认不出是哪个岗的那一支没说改目录名")
        self.assertNotIn("写高", branch,
                         "认不出是哪个岗的那一支说了「把结论写高」"
                         "——那是另一个原因，读者会被指去改错东西")

    def test_the_cap_branch_still_says_so(self):
        i = self.src.find("if refused_cap:")
        branch = self._code_only(self.src[i:i + 400])
        self.assertIn("写高", branch,
                      "天花板那一支自己的说明不见了 —— 它才是真需要改评估文件的")

    def test_the_years_branch_is_told_apart_too(self):
        """年限门那一支要有自己的收尾 —— 它与上面两种都不是一件事。

        它拦的是「判了不满足，可引的是 `N 年以上 <领域> 经验` 而 N ≤ 总年限」
        —— 按 `04`「年限门：那个数带不带领域限定」，缺的是那个领域不是年数。
        改法是**重判那一条**，与「改目录名」「改结论写高」都不同。
        """
        i = self.src.find("if refused_years:")
        self.assertGreater(i, 0, "年限门那一支的收尾不见了")
        branch = self._code_only(self.src[i:i + 600])
        self.assertIn("领域", branch, "年限门那一支没说清「领域」是什么")
        self.assertIn("业务领域分", branch,
                      "没说领域缺口该写去哪 —— 读者不知道改完该怎么判")


class TheYearsGateStopsAtWriteTime(unittest.TestCase):
    """把领域当年数的那道门，**在写盘那一刻**就拦住，别等审计偶然撞见。

    ## 为什么不能只靠审计

    `04-job-evaluation.md` 那条判据（「把年数拿掉，剩下的半句是不是一条领域
    要求？」）在文档里写着，2026-08-24 还记了实测「这道门一次都没有真正因为
    『年数不够』FAIL 过」——**而同一段时间里它正在 14 份深评上误判**（2026-10-14
    实测）。两句能并存，是因为**散文规则不报错**：判据是给执行者读的，读漏了
    没有任何东西变红。而发现它的是审计——审计**只扫库里的存量**，写盘那一刻
    没人拦。

    `writeback.py` 就是写盘那一刻的闸门（它已经在拒收「把结论写高」），所以这一格
    该加在那里。判据提为 `_cli.years_gate_is_domain_only`（正本，`audit_pipeline`
    也改引它），writeback 用它拒收。

    ## 只在判了 FAIL 时才拦

    第一版只取依据格、不看判定格，于是**判 PASS 的评估也被拒收**——实测多报 7 个。
    那等于把「引了带领域限定的原话」（正常，本来就是原文）与「判错了」混成一件事，
    **比原来那道门更坏**。所以判定与依据要一起拿。
    """

    CLI = ROOT / "tools" / "_cli.py"
    AUDIT = ROOT / "tools" / "audit_pipeline.py"

    def test_the_criterion_has_one_home(self):
        cli = self.CLI.read_text(encoding="utf-8")
        self.assertIn("def years_gate_is_domain_only", cli,
                      "判据的正本不在 `_cli`")
        for path in (self.AUDIT, ROOT / "tools" / "writeback.py"):
            src = path.read_text(encoding="utf-8")
            with self.subTest(f=path.name):
                self.assertNotIn("_YEARS_REQ", src,
                                 f"{path.name} 里还留着判据的第二份")
                self.assertNotIn("_YEARS_BARE", src,
                                 f"{path.name} 里还留着词表的第二份")

    def test_it_only_fires_on_fail(self):
        """判 PASS 的照常写回 —— 照抄含领域限定的原话是正常的。"""
        bad = "| 工作年限 | **不满足** | 「3 年以上互联网产品经理相关经验」…… |"
        self.assertIn("不满足", _cli.years_row(bad)[0])
        self.assertIn("互联网产品经理", _cli.years_row(bad)[1])
        good = "| 工作年限 | 满足 | 「3 年以上互联网产品经理相关经验」…… |"
        self.assertNotIn("不满足", _cli.years_row(good)[0],
                         "这一份判的是 PASS，不该被判成误判")

    def test_the_predicate_reads_both_shapes(self):
        self.assertTrue(
            _cli.years_gate_is_domain_only("3 年以上互联网产品经理相关经验", 13)[0],
            "带领域限定且数不大于总年限 → 是领域要求")
        self.assertFalse(
            _cli.years_gate_is_domain_only("3 年以上工作经验", 13)[0],
            "裸年限 → 不是领域要求，那道门按总年限判本来就该过")
        self.assertFalse(
            _cli.years_gate_is_domain_only("20 年以上互联网产品经验", 13)[0],
            "数超过总年限 → 领域限定也救不了，年数真的不够")


if __name__ == "__main__":
    unittest.main()
