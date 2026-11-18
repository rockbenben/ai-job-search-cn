# -*- coding: utf-8 -*-
"""可投档却没材料 —— 这件事此前没有任何一处在看。

`/job-auto` 的出材料那一步是**无条件**跑的，选岗按 `job-apply.md` 第 0 步那七条。
照理跑完就不该有漏网的。但那七条读的是**跑那一刻的快照** —— 分数在这之后
再变一次，就没有人回头看了。

实测（2026-08-26）：一个岗当轮先评 58 分「可以考虑」，材料那一步照规矩跳过；
随后把强度/发展落到粗筛四档（框架规定这两维只许取 30/50/70/85），综合分重算成
**60**，跨进「值得投」—— 而出材料那一步早已跑完。本人问「为什么还有资料未准备的」
才发现，而自检的十几条检查里没有一条问「可投的都有材料吗」。

## 这条检查自己也踩过一次它要拦的坑

第一版是从 `seen_jobs.json` 自己筛的，当场误报一个 74 分的岗 —— 那是**重复挂牌**
（`dupOf`，材料在主贴那边），而 `dupOf` 是导出时才算的（公司 + JD 正文哈希 +
手写的「同岗重复挂牌.md」），职位库里根本没有这个字段。

`job-apply.md` 第 0 步早就写着「选岗优先读面板那份快照
`users/<活动用户>/job_scraper/dashboard/data.json`，不要照着 `seen_jobs.json`
自己再筛一遍」。所以这个文件同时钉两件事：
**它报得出漏网的**，以及**它是从快照按七条选的**。
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import PANEL_SNAPSHOT, keep_panel_snapshot  # noqa: E402
import audit_pipeline as ap  # noqa: E402

SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def _seg() -> str:
    i = SRC.index("def check_sellable_without_materials(")
    return SRC[i:SRC.index("\ndef ", i + 10)]


class ItReportsTheRealThing(unittest.TestCase):
    def _run(self, jobs):
        """拿一份构造快照跑这条检查。"""
        snap = PANEL_SNAPSHOT
        if not snap.is_file():
            self.skipTest("没有面板快照")
        real = json.loads(snap.read_text(encoding="utf-8"))
        payload = {"activeUser": real.get("activeUser"), "jobs": jobs}
        # 还原走共享的那一个 —— 自己写一遍就是第四份 dance
        # （判据：tests/test_a_probe_run_leaves_nothing_behind.py）。
        restore = keep_panel_snapshot()
        try:
            snap.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return ap.check_sellable_without_materials({}, None)
        finally:
            restore()

    def test_it_fires_on_a_sellable_job_with_no_materials(self):
        got = self._run([{"company": "蓝湾智投科技", "title": "AI产品经理",
                          "verdict": "粗筛：值得投", "score": 60}])
        self.assertTrue(got, "可投档、没材料，却一个字都没报")
        self.assertIn("可投档却没材料", got[0][1])
        self.assertIn("/job-apply", got[0][2], "没给该敲的那条命令")

    def test_a_duplicate_posting_is_not_reported(self):
        """**这就是第一版误报的那个形状。** 重复挂牌的材料在主贴那边。"""
        got = self._run([{"company": "蓝湾智投科技", "title": "AI产品经理",
                          "verdict": "粗筛：值得投", "score": 74,
                          "dupOf": "jd0000"}])
        self.assertEqual(got, [], "把重复挂牌当成了漏网的")

    def test_the_other_five_exclusions_hold(self):
        for k in ("evaluated", "materials", "applied", "skipped", "expired"):
            with self.subTest(excluded=k):
                got = self._run([{"company": "蓝湾智投科技", "title": "AI产品经理",
                                  "verdict": "粗筛：值得投", "score": 60, k: True}])
                self.assertEqual(got, [], f"「{k}」这一条没排掉")

    def test_the_weaker_bands_are_not_reported(self):
        """「可以考虑」按框架是「先问清楚再决定」，它没有材料是**正常**的 ——
        要连它一起备料是显式动作（`/job-apply 可以考虑`）。"""
        for v in ("粗筛：可以考虑", "不建议", "跳过", "不满足硬性条件（英语）"):
            with self.subTest(verdict=v):
                got = self._run([{"company": "蓝湾智投科技", "title": "AI产品经理",
                                  "verdict": v, "score": 55}])
                self.assertEqual(got, [], f"「{v}」这一档不该被催出材料")


class ItSelectsFromTheSnapshotNotTheStore(unittest.TestCase):
    def test_it_reads_the_snapshot(self):
        seg = _seg()
        self.assertIn("data.json", seg, "没读快照 —— 那就拿不到 dupOf")
        self.assertIn("dupOf", seg)

    def test_it_does_not_re_filter_the_store(self):
        """`seen` 那个入参在这条检查里应当**不被使用** —— 一用就是又筛一遍。"""
        seg = _seg()
        body = seg.split('"""', 2)[-1]
        self.assertNotIn("seen.values()", body,
                         "又从 seen_jobs.json 自己筛了一遍 —— job-apply 第 0 步明令禁止")

    def test_the_predicates_come_from_one_place(self):
        """判词那两个谓词走正本，不在这儿另写一份档位表。"""
        seg = _seg()
        self.assertIn("is_out_verdict", seg)
        self.assertIn("is_strong", seg)

    def test_the_incident_is_on_record(self):
        seg = _seg()
        self.assertIn("2026-08-26", seg)
        self.assertIn("58", seg, "没记下那个岗是从哪个分数跨过来的")
        self.assertIn("74", seg, "没记下第一版误报的那个")


class ItUsesTheSameSevenAsTheWorkflow(unittest.TestCase):
    """选岗条件在两处：`job-apply.md` 第 0 步那七条，和这条检查的代码。

    **两处必须是同一批**，否则这条检查报的就不是「那一轮漏了的活」：
    工作流多一条排除、检查不跟，它会把按规矩跳过的岗报成漏网；
    工作流少一条、检查不跟，真漏的那批它看不见。

    这条检查自己的说明里就在按那七条推理（「上面的选岗条件已经排掉了
    applied / skipped / expired」）—— 推理成立的前提正是两边同步，
    而那件事此前没有任何东西验。

    判据是**字段名**这一层：七条里六条是布尔字段，第七条是判词，
    由 `is_out_verdict` / `is_strong` 两个正本谓词表达（上面那条钉着）。
    """

    #: 那七条里，判词那一条不是布尔字段，另行由谓词表达。
    VERDICT_ROW = 'j["verdict"]'

    def _seven(self) -> list:
        apply_md = (ROOT / "workflows" / "job-apply.md").read_text(
            encoding="utf-8")
        i = apply_md.index("条件就这几个字段（七条")
        block = apply_md[i:apply_md.index("```", apply_md.index("```", i) + 3)]
        return re.findall(r'j\["(\w+)"\]', block)

    def test_the_workflow_still_lists_seven(self):
        """尺子先证明自己会亮：抽不出来时下面那条在空表上永远绿。"""
        got = self._seven()
        self.assertEqual(len(got), 7, f"从 job-apply.md 抽出来的是 {got}")

    def test_every_boolean_field_is_tested_here(self):
        seg = _seg()
        missing = [f for f in self._seven()
                   if f != "verdict" and f'"{f}"' not in seg]
        self.assertEqual(
            missing, [],
            f"`job-apply.md` 第 0 步按这几个字段挑岗，而这条检查不看它们："
            f"{missing} —— 按规矩跳过的岗会被报成漏网")

    def test_the_verdict_row_is_expressed_by_the_predicates(self):
        """判词那一条不是字段比对，由两个正本谓词表达 —— 别在这儿另写档位表。"""
        self.assertIn("verdict", self._seven())
        seg = _seg()
        self.assertIn("is_out_verdict", seg)
        self.assertIn("is_strong", seg)

    def test_nothing_extra_is_filtered_here(self):
        """反过来也要真：检查里多一条工作流没有的排除，同样是两处对不上。

        **按语法取那条推导式，不要按第一个 `]` 截。** 里面有
        `(d.get("jobs") or [])` —— 按 `]` 截会停在它上面，条件一条都取不到，
        断言在空集上永远绿（变异当场照出来）。
        """
        import ast
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "check_sellable_without_materials")
        seg = ""
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "bad"
                    for t in node.targets):
                seg = ast.get_source_segment(src, node) or ""
        self.assertTrue(seg, "取不到那条选岗推导式")
        used = set(re.findall(r'j\.get\("(\w+)"\)', seg))
        self.assertGreaterEqual(len(used), 5, f"只取到 {used} —— 抽取失配了")
        extra = sorted(used - set(self._seven()))
        self.assertEqual(extra, [],
                         f"这条检查比工作流多排了几样：{extra}")


class ItIsRegistered(unittest.TestCase):
    def test_the_check_is_in_the_list(self):
        """挂进清单才会跑。清单是 `(标题, 函数)` 的元组表，
        所以判据是「函数名出现在 def 之外的地方」，不是找某个变量名。"""
        uses = [ln for ln in SRC.splitlines()
                if "check_sellable_without_materials" in ln
                and not ln.lstrip().startswith("def ")]
        self.assertTrue(uses, "写了检查却没挂进自检清单 —— 那它永远不会跑")
        self.assertTrue(any("(" in ln and "," in ln for ln in uses),
                        f"没看到它被登记成一行清单项：{uses}")


if __name__ == "__main__":
    unittest.main()
