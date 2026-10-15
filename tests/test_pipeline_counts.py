"""三个入口报的数必须是同一个口径。

## 为什么有这个测试

同一份真实数据，三处报出两套答案：

    doctor.py            已评 23 个 · 已出材料 5 份
    build_dashboard.py   打过分 23  · 材料就绪 3
    export_web_data.py   职位 19 个 · 带材料 3 个

查下来是两个独立的 bug：

**A. `doctor` 把「applications/ 下有几个目录」当成「出了几份材料」。** 一个跑到一半
的 `/job-apply` 会留下只含 `posting.md` 的空目录——它被算成了一份材料。数字虚高还会
影响下一步建议（`materials == 0` 那条分支永远进不去）。

**B. 导出器把「不满足硬性条件」的岗整个丢掉**（`rank_score is None` 就 `continue`）。
于是 antd 页的「不建议投的岗位」永远是空的——而这些岗恰恰是用户最需要看到
「为什么不投」的那批。Python 面板有搁置区，两边对不上。
"""

import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools"))

from jsx import attr_expr, jsx_open_tags  # noqa: E402

import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402
import export_web_data as ex  # noqa: E402


def _mk_user(tmp: Path, *, dirs: dict, seen: dict) -> Path:
    """造一个最小用户目录。dirs: {目录名: [文件名…]}"""
    u = tmp / "users" / "张三"
    (u / "job_scraper").mkdir(parents=True)
    (u / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps({"seen": seen}, ensure_ascii=False), encoding="utf-8")
    (u / "profile").mkdir()
    (u / "profile" / "candidate.md").write_text("# 候选人\n真实内容\n", encoding="utf-8")
    apps = u / "documents" / "applications"
    apps.mkdir(parents=True)
    for name, files in dirs.items():
        d = apps / name
        d.mkdir()
        for f in files:
            (d / f).write_text("x\n", encoding="utf-8")
    (tmp / ".active_user").write_text("张三", encoding="utf-8")
    return u


class SelfCheckAndPanelReportTheSameNumbers(unittest.TestCase):
    """自检那行数与面板那五个格子，同一份数据必须报同一个数。

    实测两处对不上，而且**每一侧自己就前后不一致，两侧还刚好反着**：

    |        | 已评 / 打过分 | 已出材料 / 材料就绪 |
    |--------|---------------|---------------------|
    | doctor | 193（排除已标不投） | 5（含已标不投） |
    | 面板   | 195（含）          | 4（排除）        |

    「已标不投」这一个概念，两处各答各的。谁也不比谁更对，但它们**必须说同一个数**
    ——用户看到 193 与 195、5 与 4，没有任何线索知道差在哪，只会以为工具算错了。

    本文件开头那几条比的是「导出 vs seen」，**从没比过自检 vs 面板**——这条轴一直是空的。

    造的用例正是出事的那种：一个岗**已标不投、而且出过材料**。
    """

    SEEN = {
        "https://x/1": {"url": "https://x/1", "title": "岗A", "company": "甲",
                        "status": "ranked", "rank_score": 80, "rank_verdict": "强匹配"},
        "https://x/2": {"url": "https://x/2", "title": "岗B", "company": "乙",
                        # 评过分、然后被手动标了不投；材料也已经出了
                        "status": "skipped", "rank_score": 70, "rank_verdict": "值得投"},
        "https://x/3": {"url": "https://x/3", "title": "岗C", "company": "丙",
                        "status": "new"},
    }

    def _both(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            u = _mk_user(tmp, seen=self.SEEN, dirs={})
            apps = u / "documents" / "applications"
            for name, url in (("甲_岗A", "https://x/1"), ("乙_岗B", "https://x/2")):
                d = apps / name
                d.mkdir(parents=True, exist_ok=True)
                (d / "outreach.md").write_text(
                    f"## 打招呼开场白\n\n- 职位链接：{url}\n\n你好。\n",
                    encoding="utf-8")
            out = tmp / "web" / "public"
            old = (ex.ROOT, ex.OUT_DIR, ex.PDF_DIR)
            ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = tmp, out, out / "pdf"
            try:
                self.assertEqual(ex.main(show_next_step=False), 0)
                panel = {p["label"]: p["count"] for p in json.loads(
                    (out / "data.json").read_text(encoding="utf-8"))["pipeline"]}
            finally:
                ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = old
            # **跑 doctor 真正打印那一行的那条路**，不去调它内部的计数函数。
            # 第一版调的是 `doctor._n_processed(seen)`——把 `check_repo` 里的
            # 计数改回旧口径，那条断言照样绿：验了零件，没验那条路。
            # `check_repo` 先认「这是不是仓库根」（缺 AGENTS.md 或 workflows/ 就
            # 直接返回、一个字不打）。临时目录里得把这两样摆上，否则测的是那条
            # 早退分支——第一次就栽在这儿：断言报「没打印那行进度」，而真因是
            # 它压根没走到打印。
            (tmp / "AGENTS.md").write_text("# 占位\n", encoding="utf-8")
            (tmp / "workflows").mkdir(exist_ok=True)
            old_root = doctor.ROOT
            doctor.ROOT = tmp
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    doctor.check_repo()
            finally:
                doctor.ROOT = old_root
            line = next((ln for ln in buf.getvalue().splitlines()
                         if "已抓" in ln and "已评" in ln), "")
            self.assertTrue(line, "doctor 没打印那行进度：" + buf.getvalue())
            nums = re.findall(r"(\d+)", line)
            self.assertGreaterEqual(len(nums), 4, f"那行读不出四个数：{line}")
            self_check = {"打过分": int(nums[1]), "材料就绪": int(nums[2]), "行": line}
            return self_check, panel

    def test_ranked_count_agrees(self):
        me, panel = self._both()
        self.assertEqual(
            me["打过分"], panel["打过分"],
            f"自检说已评 {me['打过分']}，面板说打过分 {panel['打过分']} —— "
            "同一份数据两个数，用户只会以为工具算错了")

    def test_materials_count_agrees(self):
        me, panel = self._both()
        self.assertEqual(
            me["材料就绪"], panel["材料就绪"],
            f"自检说已出材料 {me['材料就绪']} 份，面板说材料就绪 {panel['材料就绪']} "
            "—— 出事的正是这种「已标不投、但出过材料」的岗")

    def test_the_skipped_job_is_what_makes_them_differ(self):
        """判据自检：这个用例真的含一个「已标不投 + 有材料」的岗，不是空跑。

        少了它，上面两条会在一份没有分歧的数据上双双通过——测法看着对，
        实际什么都没验。
        """
        skipped = [k for k, v in self.SEEN.items() if v.get("status") == "skipped"]
        self.assertTrue(skipped, "用例里没有被标不投的岗")
        me, panel = self._both()
        self.assertEqual(panel["材料就绪"], 1,
                         "两份材料里应当只有一份还算「就绪」（另一份的岗已标不投）")


class MaterialsCountMeansMaterials(unittest.TestCase):
    """「已出材料 N 份」要数**真出了材料的**，不是数目录个数。"""

    def test_posting_only_dir_is_not_a_material(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _mk_user(tmp, seen={}, dirs={
                "甲公司_岗A": ["posting.md", "outreach.md", "resume.pdf"],
                "乙公司_岗B": ["posting.md"],          # /job-apply 跑一半，没出材料
                "丙公司_岗C": ["posting.md", "outreach.md"],
            })
            n = doctor.count_materials(tmp / "users" / "张三")
            self.assertEqual(
                n, 2,
                "只有 posting.md 的目录不算「出了材料」——它是跑一半的 /job-apply 留下的")

    def test_empty_dir_is_not_a_material(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _mk_user(tmp, seen={}, dirs={"甲公司_岗A": []})
            self.assertEqual(doctor.count_materials(tmp / "users" / "张三"), 0)

    def test_no_applications_dir_is_zero_not_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            u = Path(t) / "users" / "张三"
            u.mkdir(parents=True)
            self.assertEqual(doctor.count_materials(u), 0)


class OrphanMaterialsUseUrlFieldNotKey(unittest.TestCase):
    """判「材料接不回职位列表」要比 `url` 字段，不能比 seen 的键。

    `seen_jobs.json` 的键是 `<url>#<职位名>` 形式的**去重键**——51job 实测同一 URL 下
    挂着两个不同职位，只用 URL 当键会静默吃掉一条（见 cdp-portals.md）。
    拿键去比对投递目录里的职位链接，接得上的也会被判成接不上，于是终端凭空报出
    「N 份材料上不了总览页」。
    """

    def _run(self, seen):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            u = _mk_user(tmp, seen=seen, dirs={})
            apps = u / "documents" / "applications"
            d = apps / "甲公司_岗A"
            d.mkdir(parents=True, exist_ok=True)
            (d / "outreach.md").write_text(
                "## 打招呼开场白\n\n- 职位链接：https://x/1\n\n你好。\n",
                encoding="utf-8")
            return doctor.orphan_materials(u, seen)

    def test_key_with_title_suffix_still_counts_as_linked(self):
        seen = {"https://x/1#岗A": {"url": "https://x/1", "title": "岗A"}}
        self.assertEqual(
            self._run(seen), [],
            "键带 #职位名 后缀，但 url 字段对得上 —— 不该判成接不回")

    def test_genuinely_unscraped_job_is_reported(self):
        seen = {"https://other/9": {"url": "https://other/9", "title": "别的岗"}}
        self.assertEqual(self._run(seen), ["甲公司_岗A"],
                         "职位确实没被抓到过，应该报出来")

    def test_empty_seen_reports_the_orphan(self):
        self.assertEqual(self._run({}), ["甲公司_岗A"])


class TheReasonForBeingOrphanedIsToldApart(unittest.TestCase):
    """「接不回去」有两种原因，给用户的说法完全不同——不能混着报一句。

    - 职位库里根本没有这个岗（对着粘来的 JD 跑 `/job-apply`）→ 正常，没得修。
    - 库里有，只是 `outreach.md` 漏了 `- 职位链接：<url>` → 一行就修好。

    自检原来只写了第一种：「对没被 /job-scrape 抓到过的职位跑 /job-apply 就会这样；
    不影响材料本身」。实测一次批量投递之后 **14 个目录全是第二种**——用户照着
    这句话会认为「正常」，于是这 14 个岗永远不上总览页。
    **诊断给错原因比不给更坏**：它让人停止排查。
    """

    def _mk(self, tmp, seen, outreach, evaluation):
        u = _mk_user(tmp, seen=seen, dirs={})
        d = u / "documents" / "applications" / "甲公司_岗A"
        d.mkdir(parents=True, exist_ok=True)
        (d / "outreach.md").write_text(outreach, encoding="utf-8")
        if evaluation:
            (d / "evaluation.md").write_text(evaluation, encoding="utf-8")
        return u

    def test_a_missing_link_line_is_recognised_as_fixable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            u = self._mk(Path(t), {"https://x/1#岗A": {"url": "https://x/1"}},
                         "# 话术\n\n你好。\n", "职位链接见 https://x/1 这里\n")
            self.assertEqual(doctor.orphan_materials(
                u, {"https://x/1#岗A": {"url": "https://x/1"}}), ["甲公司_岗A"])
            self.assertEqual(
                doctor.recoverable_link(u, "甲公司_岗A",
                                        {"https://x/1#岗A": {"url": "https://x/1"}}),
                "https://x/1", "库里有这个岗、链接就在同目录里 —— 应判为可修复")

    def test_a_genuinely_unscraped_job_is_not_called_fixable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            seen = {"https://other/9": {"url": "https://other/9"}}
            u = self._mk(Path(t), seen, "# 话术\n\n你好。\n", "见 https://x/1\n")
            self.assertEqual(doctor.recoverable_link(u, "甲公司_岗A", seen), "",
                             "库里确实没有这个岗 —— 不该说成「补一行就好」")

    def test_two_candidate_links_are_not_guessed_between(self):
        """同目录里两个链接都能对上库时不猜——猜错就把材料挂到别的岗上了。"""
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            seen = {"a": {"url": "https://x/1"}, "b": {"url": "https://x/2"}}
            u = self._mk(Path(t), seen, "# 话术\n\n你好。\n",
                         "https://x/1 和 https://x/2\n")
            self.assertEqual(doctor.recoverable_link(u, "甲公司_岗A", seen), "")


class GateFailJobsSurviveExport(unittest.TestCase):
    """不满足硬性条件的岗必须导出，只是不进「可以投」那张名单。"""

    SEEN = {
        "https://x/1": {"url": "https://x/1", "title": "岗A", "company": "甲",
                        "status": "ranked", "rank_score": 80, "rank_verdict": "强匹配"},
        "https://x/2": {"url": "https://x/2", "title": "岗B", "company": "乙",
                        "status": "ranked", "rank_score": None,
                        "rank_verdict": "硬门 FAIL (学历院校)"},
        "https://x/3": {"url": "https://x/3", "title": "岗C", "company": "丙",
                        "status": "new"},          # 还没评分，不该进这一页
    }

    def _export(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _mk_user(tmp, seen=self.SEEN, dirs={})
            out = tmp / "web" / "public"
            old_root, old_out, old_pdf = ex.ROOT, ex.OUT_DIR, ex.PDF_DIR
            ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = tmp, out, out / "pdf"
            try:
                self.assertEqual(ex.main(), 0)
                return json.loads((out / "data.json").read_text(encoding="utf-8"))
            finally:
                ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = old_root, old_out, old_pdf

    def test_gate_fail_job_is_exported(self):
        d = self._export()
        titles = [j["title"] for j in d["jobs"]]
        self.assertIn("岗B", titles,
                      "不满足硬性条件的岗被整个丢掉 → 页面上的「不建议投」永远是空的")

    def test_gate_fail_job_has_no_score_and_a_reason(self):
        d = self._export()
        j = next(x for x in d["jobs"] if x["title"] == "岗B")
        self.assertIsNone(j["score"], "不满足硬性条件就不该有分数")
        self.assertEqual(j["verdict"], "不满足硬性条件")
        self.assertIn("学历院校", j.get("gateFailReason", ""),
                      "要说清是哪一条不满足")
        self.assertNotIn("硬门", j.get("gateFailReason", ""),
                         "显示层不该出现内部词「硬门」")

    def test_unranked_job_is_not_exported(self):
        """还没评分的岗不进这一页——那是面板搁置区的事。"""
        d = self._export()
        self.assertNotIn("岗C", [j["title"] for j in d["jobs"]])

    def test_ranked_job_still_exported(self):
        d = self._export()
        j = next(x for x in d["jobs"] if x["title"] == "岗A")
        self.assertEqual(j["score"], 80)


class CountsAgreeAcrossEntryPoints(unittest.TestCase):
    """控制测试：有真实数据时，各入口的口径必须对得上。

    导出器收的是**已处理过的**条目：
    - `ranked` —— 打过分的（有分给分，不满足硬性条件的记原因）
    - `skipped` —— 你自己标了不投的。**也要导出**，否则页面上没法放回来，
      只能回命令行改 JSON。

    - `expired` —— 已下线的。**也要导出**（只进搁置区、不进任何计数），
      否则用户在面板上点完「职位已下线」这个岗就人间蒸发、没有回头路。

    只有 `new`（还没评）不导出。

    > 这条测试红过一次，而且红得有价值：`serve.py` 上线后用户在总览页点了一个
    > 「不投」，条目从 `ranked` 变成 `skipped`，于是「导出数 == ranked 数」当场
    > 不成立。**代码是对的，是这条断言没跟上「被排除的岗也要导出」那次改动。**
    """

    @staticmethod
    def _decided(seen: dict) -> dict:
        """把叠加层折算进来，得到每个岗**真正生效**的状态。

        面板点的「不投 / 已下线」写 `job_scraper/user_state.json`，不写职位库
        （2026-08-19 拆开的：读一次库、评十几分钟、整份写回，会把中间
        用户点的那一下静默抹掉）。`_cli.decided_status` 明写「有决定的以它为准」，
        导出器照做 —— 判据也必须照做，否则它数的是**用户看不到的那份状态**。

        实测代价（2026-08-21，真实数据）：库里 89 个不投、叠加层 4 个，导出 93。
        这条判据拿 93 比 89，把**正确的导出**报成缺陷。
        它此前一直绿，只因为 `web/public/data.json` 还是叠加层出现之前导的；
        重启 serve.py 触发重导，当场现形 —— **任何用过面板那个按钮的用户都会撞上。**
        """
        import _cli
        user = (ROOT / ".active_user").read_text(encoding="utf-8").strip()
        # **传的是 seen_jobs.json 的路径，不是用户名。** 传错不报错，
        # 只是静默返回 {} —— 判据会安静地退化成「没有叠加层」。
        sj = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
        ustate = _cli.load_user_state(sj)
        return {k: _cli.decided_status(e, ustate.get(k))
                for k, e in seen.items()}

    def _real(self):
        au = ROOT / ".active_user"
        if not au.is_file():
            self.skipTest("这个 clone 里没有活动用户")
        name = au.read_text(encoding="utf-8").strip()
        u = ROOT / "users" / name
        sj = u / "job_scraper" / "seen_jobs.json"
        data = ROOT / "web" / "public" / "data.json"
        if not sj.is_file() or not data.is_file():
            self.skipTest("还没有职位数据或还没导出")
        payload = json.loads(data.read_text(encoding="utf-8"))
        # `web/public/data.json` 是**全用户共用的一个文件**，而 `seen_jobs.json`
        # 每人一份。多人共用一份 clone 时（AGENTS.md 明确支持），切了用户但没重导，
        # 这两份就属于不同的人——拿 A 的盘上数据去比 B 的导出，下面每条断言都会
        # 报出无意义的失败，还会被误读成计数口径有问题（实测跨 5 个模拟用户走查时
        # 就这么绊了一次）。
        #
        # 所以先核对身份：不一致就是**快照过期**，跳过而不是失败。真正的一致性
        # 由 serve.py 的自愈保证（`.active_user` 也计入 mtime，切用户会触发重导）。
        if (payload.get("activeUser") or "") != name:
            self.skipTest(
                f"data.json 属于「{payload.get('activeUser')}」、当前用户是「{name}」"
                " —— 快照过期，跑一次 export_web_data.py 再测")
        return (json.loads(sj.read_text(encoding="utf-8")).get("seen", {}),
                payload["jobs"])

    def test_exported_count_matches_processed_entries(self):
        seen, jobs = self._real()
        st = self._decided(seen)
        n_ranked = sum(1 for v in st.values() if v == "ranked")
        n_skipped = sum(1 for v in st.values() if v == "skipped")
        # 已下线的也导出（只进搁置区，见下面那条）——不导出就没法在页面上放回来，
        # 而面板现在有「职位已下线」按钮，点完不能让这个岗人间蒸发。
        n_expired = sum(1 for v in st.values() if v == "expired")
        self.assertEqual(
            n_ranked + n_skipped + n_expired, len(jobs),
            f"已处理 {n_ranked} 打过分 + {n_skipped} 不投 + {n_expired} 已下线 = "
            f"{n_ranked + n_skipped + n_expired}，导出的却是 {len(jobs)} 个 —— 口径不一致")

    def test_skipped_entries_are_exported_and_marked(self):
        """被排除的岗要能在页面上认出来，才放得回去。"""
        seen, jobs = self._real()
        st = self._decided(seen)
        n_skipped = sum(1 for v in st.values() if v == "skipped")
        if not n_skipped:
            self.skipTest("这份数据里没有被排除的岗")
        marked = sum(1 for j in jobs if j.get("skipped"))
        self.assertEqual(marked, n_skipped,
                         "盘上标了不投的，导出时必须带 skipped 标记")

    def test_unranked_entries_are_not_exported(self):
        """还没评的不导出。**已下线的要导出**——但只进搁置区。

        这条原来把 `expired` 和 `new` 并列成「都不该出现在页面上」。
        那时 `expired` 只由 `/job-apply` 批量写得出来，不导出还说得过去；
        现在面板上有「职位已下线」按钮，不导出就意味着用户点完这个岗当场蒸发、
        没有任何回头路——而「点开是聚合页」这种判断完全可能错。
        所以改成：导出、带 `expired` 标记、不进任何名单与计数、给「放回可以投」。
        """
        seen, jobs = self._real()
        st = self._decided(seen)
        n_new = sum(1 for e in seen.values() if (e.get("status") or "new") == "new")
        self.assertEqual(len(seen) - n_new, len(jobs),
                         "还没评的不该出现在页面上")

    def test_expired_entries_are_exported_but_flagged(self):
        """已下线的导出了、标了、且不进任何流水线格子。"""
        seen, jobs = self._real()
        st = self._decided(seen)
        n_expired = sum(1 for v in st.values() if v == "expired")
        if not n_expired:
            self.skipTest("这份数据里没有已下线的岗")
        gone = [j for j in jobs if j.get("expired")]
        self.assertEqual(len(gone), n_expired,
                         "盘上标了已下线的，导出时必须带 expired 标记，"
                         "否则页面上放不回来")
        for j in gone:
            with self.subTest(job=j["title"][:16]):
                self.assertEqual(j.get("funnels"), [],
                                 "已下线的岗被算进了流水线格子")


if __name__ == "__main__":
    unittest.main()


class FunnelCellsAreClickableSoCountsMustMatch(unittest.TestCase):
    """流水线后三格现在可以点开筛选——数字就必须等于点开能看到的那些。

    原来它们是**假按钮**：渲染成 `<button>`、屏读器播报成按钮、键盘能聚焦，
    按下去什么也不发生。而它们本该是这一页最自然的导航：「下一步」说
    「材料就绪，去投递」，那几个岗却埋在 54 行里要一行行找。

    接成真筛选之后就多了一条契约：**格子上的数 = 点开后的行数**。实测第一版
    就违约了——格子写 5、点开只有 4，差的那个是用户手动标了「不投」的岗
    （它在搁置区，可投名单里本来就没有）。数字 5、点开 4，用户会以为漏了一个。
    """

    def test_materials_count_excludes_manually_skipped(self):
        """走真实的 funnels_of 判——第一版是纯恒真式：本地造 jobs、用**测试自己的
        表达式**算出 1、断言等于 1，对产品只 `hasattr(ex, "main")`。把导出器里的
        排除逻辑删光它也绿，名字承诺了它没做的检查。"""
        import export_web_data as ex
        jobs = [
            {"materials": {"greeting": "x"}},                    # 待投
            {"materials": {"greeting": "x"}, "skipped": True},   # 手动不投，不在名单里
            {},                                                   # 没材料
        ]
        n = sum(1 for j in jobs if "materials" in ex.funnels_of(j))
        self.assertEqual(n, 1, "标了「不投」的岗仍被算进「材料就绪」")

    def test_both_dashboards_leave_out_the_ones_you_said_no_to(self):
        """两个面板的同一个格子不能给出不同的数。

        标了「不投」的岗虽然做过材料，但它已经进了搁置区、筛选也看不到它，
        所以两边都不能把它算进「材料就绪」。

        > 这条原来断言的是**字面串** `j.get("materials") and not j.get("skipped")`。
        > 把同一个判断抽进 `funnels_of`（参数名从 `j` 变成 `job`）它就红了——
        > 意思一个字没变，锚点却挂在拼法上。改成验行为。
        """
        # 网页版：直接喂真值给那个唯一的判断
        self.assertEqual(
            ex.funnels_of({"materials": {"greeting": "x"}, "skipped": True}), [],
            "网页版把标了「不投」的岗算进了「材料就绪」")
        self.assertEqual(
            ex.funnels_of({"materials": {"greeting": "x"}, "skipped": False}),
            ["materials", "ready"])

    def test_cells_exclude_exactly_what_the_rows_exclude(self):
        """格子可点开，数必须等于点开的行数——行集排掉的，格子也要排掉。

        页面行集过滤 `!dupOf && !isOut(verdict) && !excluded`。原来 funnels_of
        只在材料格排 skipped，纯 UI 路径即可复现对不上：点「我投了」再点
        「不投这个岗」→「已投递」格 +1，点开却没有那一行。
        """
        applied = {"applied": {"status": "applied"}}
        self.assertEqual(ex.funnels_of({**applied, "skipped": True}), [],
                         "标了不投的岗还在「已投递」格里")
        self.assertEqual(ex.funnels_of({**applied, "dupOf": "abc123"}), [],
                         "重复挂法（页面上不占行）被算进了格子")
        for v in ("跳过", "不建议", "不满足硬性条件"):
            with self.subTest(verdict=v):
                self.assertEqual(ex.funnels_of({**applied, "verdict": v}), [],
                                 f"判词「{v}」的岗页面上在搁置区，格子却算了它")
        self.assertEqual(ex.funnels_of({**applied, "verdict": "值得投"}),
                         ["applied"], "正常岗反而不算了——排除面拉太宽")

    def test_the_collapsed_band_opens_under_a_filter(self):
        """点开格子要能**一次**看齐所有行，包括「可以考虑」那一档。

        契约是「格子上的数 = 点开看到的行数」。名单按判词切成主表 +
        「可以考虑」折叠区，默认收起是对的（给长名单一个停止点），但筛选开着时
        收起就意味着要再点一次才数得齐——实测点「材料就绪 19」，标题只写 16。

        **`key` 是这条的要害。** `defaultActiveKey` 只在挂载时读一次，而切筛选时
        这个组件早就挂着了：只改 `defaultActiveKey` 能过类型检查、能构建、
        在页面上一点效果都没有（实测如此，靠真点一遍才发现）。所以这里两样都验。
        """
        src = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        i = src.find('key: "maybe"')
        self.assertNotEqual(i, -1, "找不到「可以考虑」那个折叠区了")
        block = src[max(0, i - 1400):i]
        self.assertRegex(
            block, r"defaultActiveKey=\{funnel\s*\?",
            "「可以考虑」折叠区没有跟着筛选展开 —— 点开格子数不齐")
        self.assertRegex(
            block, r"key=\{funnel",
            "只写了 defaultActiveKey 没写 key —— 组件不会重挂载，"
            "这个默认值在切筛选时根本不生效（改了等于没改）")

    def test_applied_pinned_on_a_duplicate_moves_to_the_primary(self):
        """台账行钉在重复挂法上时，投递状态必须移交主条目。

        dup 条目在页面上任何地方都不渲染——投递记录落在它身上等于整个消失：
        主投放看起来没投过、照旧躺在「可以投的岗位」里，恰是「防重复投同一家」
        要防的事故。机制在 main() 的移交循环里，这里验行为等价的最小复现。
        """
        jobs = [{"id": "p1", "applied": None},
                {"id": "d1", "dupOf": "p1",
                 "applied": {"status": "applied", "date": "2026-08-01"}}]
        jobs[0].pop("applied")
        by_id = {j["id"]: j for j in jobs}
        for j in jobs:                        # 与 main() 里的移交循环同构
            if j.get("dupOf") and j.get("applied"):
                primary = by_id.get(j["dupOf"])
                if primary is not None and not primary.get("applied"):
                    primary["applied"] = j["applied"]
        self.assertTrue(jobs[0].get("applied"), "投递状态没移交到主条目")
        # 真正的守卫：main() 里必须存在这段移交（复现循环防的是语义漂移，
        # 这句防的是「整段被删」）
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("dupOf\") and j.get(\"applied", src,
                      "main() 里的「投递状态移交主条目」那段没了")
        # 单页版：它自己那份计数也要排除
        one = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
        i = one.index('"materials": sum(')
        self.assertIn("skipped", one[i:i + 200],
                      "单页版没排除手动不投的 —— 两个面板会各说各的")

    def test_single_page_jobs_carry_the_skipped_flag(self):
        """单页版原来完全不读这个状态，`derive_stage` 里也没有 skipped 这一档。

        少了它，上一条那个判断会永远为真（等于没写）——这种「改了但不生效」
        最难发现，因为测试和肉眼都看不出区别。
        """
        one = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
        self.assertIn('"skipped": entry.get("status") == "skipped"', one,
                      "单页版的 job 字典没带 skipped，上面那条判断是空转")

    def test_ui_only_filters_cells_it_can_honour(self):
        """前两格不接筛选：「搜到职位」含没上表的（待评/降权/已过期），
        点了给不出对应的行；硬接会让点击结果与数字对不上，比不能点更糟。

        验的是**「能不能点」这件事最终取决于有没有筛选键**，不是某一种拼法。
        原来这里断言的是字面串 `disabled={!key`，把条件收敛成一个具名变量
        （`actionable`）之后就红了——意思没变，锚点却挂在拼法上。
        """
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("3: \"materials\", 4: \"applied\", 5: \"interview\"", app,
                      "可筛选的格子映射变了")
        # 走 `tests/jsx.py` 那个按大括号深度扫的共用件，不另抄一份正则：
        # `data-state={s.count > 0 ? …}` 里那个 `>` 会让 `<button[^>]*>` 提前收尾，
        # 截出来的片段里正好没有 `disabled=`——这条就变成了空转。
        # 命中区域是格子里那个 `.rail-hit` 按钮，不是格子本身——格子后来改成
        # `div`，因为里面要放「该敲什么」那条命令，而命令自带复制按钮，
        # 套在 `<button>` 里既是嵌套可交互元素、点复制还会顺手触发筛选。
        # 这条验的仍是同一件事（能不能点取决于有没有筛选键），只是锚点跟着挪了。
        cell = next((t for t in jsx_open_tags(app, "button")
                     if 'className="rail-hit"' in t), None)
        self.assertIsNotNone(cell, "流水线格子里找不到 <button class=rail-hit> 了")
        expr = attr_expr(cell, "disabled")
        self.assertIsNotNone(expr, "不可筛选的格子没有禁用，留着假的可点性")
        # 条件可以是行内表达式，也可以是就近定义的具名变量——两种都追一层
        if re.fullmatch(r"!?\s*[A-Za-z_$][\w$]*", expr):
            name = expr.lstrip("! ")
            bind = re.search(rf"const {re.escape(name)}\s*=\s*(.+?);", app, re.S)
            self.assertIsNotNone(bind, f"{name} 是从哪来的读不出来")
            expr = bind.group(1)
        self.assertIn("key", expr,
                      f"禁用与「有没有筛选键」脱钩了：{expr!r} —— "
                      "前两格会变成按下去什么都不发生的假按钮")

    def test_a_drained_shortlist_sends_you_back_to_restocking(self):
        """名单见底时必须叫人去补新岗——这条分支原来整个不存在。

        只要投过一次，`applied > 0` 那支就永远接管，在「还有 N 个材料没投」与
        「都投出去了，等回复」之间来回，**没有任何一条路通向补货**。而同一
        时刻终端自检说的是「跑 /job-scrape 补充名单」。两份实现给出**不同的行动
        建议**，用户看哪个算哪个——实测用户就是因此问出「怎么让你继续抓取」。

        流程是个环（投完要回去找），而面板把它画成了一条走到头的线。

        **2026-10-14：命令从 `/job-scrape` 改成 `/job-auto`，分支本身没动。**
        这一支的理由是 `SHORTLIST_FLOOR` 常量 docstring 里那句「**补货的前置
        时间比名单见底的速度长**，所以要在见底之前就提醒」——`/job-auto` 同样
        先抓，那条理由一点没丢。而 `/job-scrape` 抓完自动评分却**不出材料**，
        敲完他手上是一排没材料的岗，还得再敲一条才走得到能发的那一步
        （`test_the_next_step_is_the_spine.py` 顶上记的就是同一件事，
        2026-08-30 把终端那一支改成了 `/job-auto`）。
        """
        counts = {"scraped": 543, "ranked": 349, "materials": 23,
                  "applied": 9, "interviewing": 0}
        for n in (0, 1, bd.SHORTLIST_FLOOR - 1):
            with self.subTest(sellable=n):
                _, cmd = bd.next_step(counts, True, "https://x/1", n_sellable=n)
                self.assertEqual(cmd, "/job-auto",
                                 f"可以投只剩 {n} 个，却没叫人去补货")
                self.assertNotIn("/job-scrape", cmd,
                                 "补货那条停在半路：抓完没有材料，还得再敲一条")
        # 名单还够时不要瞎催——补货提示天天弹就等于没有提示
        _, cmd = bd.next_step(counts, True, "https://x/1",
                              n_sellable=bd.SHORTLIST_FLOOR)
        self.assertNotEqual(cmd, "/job-auto", "名单还够就别催补货")

    def test_interviews_outrank_restocking(self):
        """有面试在跑时，备面比补货要紧——补货不能抢它的位置。"""
        counts = {"scraped": 543, "ranked": 349, "materials": 23,
                  "applied": 9, "interviewing": 2}
        _, cmd = bd.next_step(counts, True, "https://x/1", n_sellable=0)
        self.assertEqual(cmd, "/job-interview <公司>")

    def test_the_sellable_count_uses_the_pages_own_row_set(self):
        """「还能投几个」必须与页面那份行集同口径，不另写一份判据。

        页面说「可以投的岗位 11」而下一步按另一个数催补货，是这一页最容易出现的
        自相矛盾。判词出局那几档由 `is_out_verdict` 一处说了算，TS 侧的 `isOut`
        与它对齐。
        """
        # 两个函数管两件事，别混：
        #   is_sellable   —— 能不能进「可以投的岗位」。**白名单**，不认识就不进。
        #   is_out_verdict —— 进不进流水线格子。**黑名单**，已投的岗不管判词都要数，
        #                     否则格子上的数和点开看到的行数对不上。
        for v in ("值得投", "强匹配", "可以考虑",
                  "粗筛：值得投", "粗筛：强匹配", "粗筛：可以考虑"):
            with self.subTest(sellable=v):
                self.assertTrue(ex.is_sellable(v), f"「{v}」该能进可投名单")
        for v in ("不满足硬性条件", "不满足硬性条件 (学历)", "硬门 FAIL (工作年限)",
                  "跳过", "粗筛：跳过", "不建议", "粗筛：不建议",
                  "粗筛：待定", "已评分", "", "随便编一个"):
            with self.subTest(sellable=v):
                self.assertFalse(ex.is_sellable(v),
                                 f"「{v}」不该进可投名单——白名单之外一律不进")
        # 出局判定要**容后缀**：2026-08-13 就是 `== "不满足硬性条件"` 落空，
        # 让「不满足硬性条件 (学历)」混进了名单。
        for v in ("不满足硬性条件", "不满足硬性条件 (学历)", "硬门 FAIL (工作年限)",
                  "跳过", "粗筛：跳过", "不建议", "粗筛：不建议"):
            with self.subTest(out=v):
                self.assertTrue(ex.is_out_verdict(v), f"「{v}」该算出局")
        for v in ("值得投", "强匹配", "可以考虑", "已评分", ""):
            with self.subTest(out=v):
                self.assertFalse(ex.is_out_verdict(v),
                                 f"「{v}」不该算出局——它会把已投的岗从格子里抹掉")
        # TS 侧那份判据要与这里同源
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        m = re.search(r"const SELLABLE = \[(.+?)\];", app, re.S)
        self.assertIsNotNone(m, "前端的 SELLABLE 找不到了")
        for w in ex.SELLABLE_VERDICTS:
            self.assertIn(w, m.group(1),
                          f"前端的白名单少了「{w}」——两边行集会不一样")

    def test_each_stage_says_what_to_do_and_what_to_type(self):
        """五格每格都要写出「在做什么 + 该敲什么」。

        用户问「可以投的不多了，怎么让你继续抓取」时，流程就在他眼前——五格
        标着搜到职位/打过分/材料就绪/已投递/面试中——但**每一格该敲什么从来
        没写在格子上**。页面上唯一说过这件事的地方是最底下那个折叠的命令表，
        它按任务类型分组，与顶上五格对不上号。
        """
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        for cmd in ("/job-scrape", "/job-rank", "/job-apply", "/job-outcome", "/job-interview"):
            self.assertIn(f'"cmd": "{cmd}', src,
                          f"流水线某一格没给出 {cmd} —— 那一步用户不知道敲什么")
        self.assertEqual(src.count('"does":'), 5,
                         "五格不是每格都写了「在做什么」")
        # 前端要真渲染它们，不然导出了也白导
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("rail-guide", app, "格子上没有渲染「该敲什么」那一块")
        self.assertIn("s.does", app)
        self.assertIn("s.cmd", app)

    def test_the_highlighted_cell_is_the_one_next_step_names(self):
        """高亮哪一格由「下一步」说了算，不另立判据。

        两处各判一次的话，会出现「下一步叫你去搜岗、亮起来的却是投递格」。
        """
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        m = re.search(r"const nudged =\s*(.+?);", app, re.S)
        self.assertIsNotNone(m, "找不到高亮判据 nudged")
        expr = m.group(1)
        # **验等式两边，不验「这个词出现过」。** 第一版只断言 expr 里含
        # `nextStep.command`，而把比较改成 `s.step === 1` 之后那个词仍留在前面的
        # 空值判断里——控制检查当场是绿的。字符串出现过 ≠ 拿它做了比较。
        # 操作数要在 `&&` / `||` 处断开。第一版写的是 `[^=;]+?`，于是左操作数把
        # 前面整个 `Boolean(s.cmd) && Boolean(nextStep.command) &&` 一起吞了进来，
        # 两个词都还在里面——把比较改成 `s.step === 1` 照样绿。
        cmp_ = re.search(r"([^=;&|]+?)===([^=;&|]+)", expr)
        self.assertIsNotNone(cmp_, f"高亮判据里没有比较：{expr!r}")
        sides = (cmp_.group(1), cmp_.group(2))
        self.assertTrue(any("s.cmd" in s for s in sides),
                        f"比较的一边不是这一格的命令：{expr!r}")
        self.assertTrue(any("nextStep.command" in s for s in sides),
                        f"比较的另一边不是 nextStep 的命令：{expr!r} —— "
                        "高亮另立了一条判据，迟早与「下一步」指向两件事")

    def test_every_cell_count_equals_what_clicking_it_shows(self):
        """格子上的数 = 按它筛出来的行数。**这一条覆盖所有格子，不是逐个点名。**

        三格曾经全飘了，而且都要等真有投递之后才显形——在页面能记状态之前，
        这些数永远是 0，谁也发现不了：

            材料就绪  数=有材料（含已投的）      筛=有材料**且没投**
            已投递    数=台账**行数**            筛=匹配上的岗
            面试中    数={interview,offer,hired} 筛=[interview,offer]

        修法是口径只留一份：`funnels_of` 说一个岗属于哪几格，计数按它数、
        页面按它筛。所以这条直接验那个函数——**加一个新格子也自动被它覆盖**。
        """
        base = {"materials": {"greeting": "x"}, "skipped": False}
        # `ready`（有材料且没投）**不是流水线的第五格**，是「备好还没发」那份
        # 清单的筛选键（面板那句「你手上已经有 N 个」点开就用它）。
        # 它走同一个 `funnels_of`，所以数和行照样按构造相等 ——
        # 这也正是上面那句「加一个新格子也自动被它覆盖」说的事。
        cases = [
            ("刚出材料", {**base}, ["materials", "ready"]),
            ("出了材料又投了", {**base, "applied": {"status": "applied"}},
             ["materials", "applied"]),
            ("面试中", {**base, "applied": {"status": "interview"}},
             ["materials", "applied", "interview"]),
            ("拿到 offer", {**base, "applied": {"status": "offer"}},
             ["materials", "applied", "interview"]),
            ("已录用", {**base, "applied": {"status": "hired"}},
             ["materials", "applied", "interview"]),
            ("被拒", {**base, "applied": {"status": "rejected"}},
             ["materials", "applied"]),
            ("标了不投", {**base, "skipped": True}, []),
            ("没材料没投", {}, []),
        ]
        for name, job, want in cases:
            with self.subTest(name):
                self.assertEqual(ex.funnels_of(job), want)

    def test_the_counts_are_derived_from_that_one_function(self):
        """计数不许另写一遍判断——写第二遍就是让它有机会飘。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        code = re.sub(r"#.*$", "", src, flags=re.M)
        for var in ("n_mat", "n_sent", "n_intv"):
            m = re.search(rf"^ *{var} = (.+)$", code, re.M)
            self.assertIsNotNone(m, f"{var} 不见了")
            self.assertIn('"funnels"', m.group(1),
                          f"{var} 没从 funnels 数出来：{m.group(1).strip()!r} —— "
                          "计数和筛选又变成两套判断了")

    def test_the_page_filters_on_that_same_field(self):
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        code = re.sub(r"//.*$", "", app, flags=re.M)
        i = code.index("const matchFunnel")
        body = code[i:code.index(";", i)]
        self.assertIn("funnels", body, "页面又自己判了一遍归属")
        for leaked in ("j.materials", "j.applied", "interview\"", "offer\""):
            with self.subTest(leaked):
                self.assertNotIn(leaked, body,
                                 f"筛选里出现了 {leaked} —— 判断该只在 funnels_of 一处")

    def test_active_filter_is_announced(self):
        """数字从 54 变成 4 而没有解释，用户第一反应是「我的岗怎么少了」。"""
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("funnel-chip", app, "筛选生效时没有可见的状态标")
        self.assertIn("aria-pressed", app, "屏读器听不出筛选是开还是关")


class FunnelBoxesFollowTheLiveFilters(unittest.TestCase):
    """格子上的数 = 点开看到的行数——**prefs 这一层也算**。

    `funnels_of` 的注释写着「计数和筛选共用这一个判断」，而 2026-08-19 加的
    「这几类岗要不要看」（prefs）是**后来叠上去的一层**：它只作用在列表，
    没作用到格子。实测（2026-08-20）关掉「猎头代招」后，「材料就绪」格子
    仍显示 146，点开只有 77 行——**差 69 行**，正是那条注释警告过的形状。

    这类错要等用户真去关一个开关才显形，所以钉在这里。
    """

    def test_boxes_are_computed_through_the_filter_chain(self):
        src = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("funnelCounts", src, "格子还在直接用导出的 s.count")
        seg = src.split("const funnelCounts")[1].split("}, [")[0]
        for f in ("passesPrefs", "isHidden", "excluded"):
            self.assertIn(f, seg, f"格子计数没过 {f} 这一层，会和列表飘")

    def test_no_raw_count_reaches_the_screen(self):
        """渲染与读屏都要用现算的数——两者不一致比都错更糟。"""
        src = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        seg = src.split('className="rail-hit"')[1].split("</button>")[0]
        self.assertNotIn("s.count", seg,
                         "按钮里还在渲染导出时的原数，和点开的行数对不上")
        self.assertIn("shown", seg)

    def test_the_gap_is_explained_not_hidden(self):
        """被筛掉多少要说出来，否则岗位看起来是凭空少的。"""
        src = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("rail-filtered", src, "没有「另有 N 个被关掉了」的说明")
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
        self.assertIn(".rail-filtered", css, "说明行没有样式，会渲染成一段裸文字")


class ReportSummaryCoversEveryBucket(unittest.TestCase):
    """`/job-html-report` 收尾那句小结，要把状态桶**全部**报出来。

    2026-08-21 通读时抓到：桶映射表有五个
    （已投递 / 面试中 / **拿到 offer** / 入职了 / 挂了·没下文），
    而给用户的那行小结只列了四个 —— **`拿到 offer` 整个不见了**。
    手上正好有 offer 的用户，在那行里哪儿都找不到自己。

    判据**从那张表里抽显示名**，再逐个到小结里找 —— 不写死名单，
    表里加一个桶、小结没跟上，这里就会红。
    """

    REPORT = ROOT / "workflows" / "job-html-report.md"

    def test_every_bucket_name_appears_in_the_summary(self):
        import re

        t = self.REPORT.read_text(encoding="utf-8")
        i = t.index("| 内部键 |")
        rows = [l for l in t[i:t.index(chr(10) * 2, i)].splitlines()
                if l.startswith("| `")]
        names = [re.sub(r"\*", "", l.strip("|").split("|")[-1]).strip()
                 for l in rows]
        self.assertGreaterEqual(len(names), 4, f"桶表没抽到：{names}")

        j = t.index("**这一轮的情况：**")
        summary = t[j:j + 400]
        missing = [n for n in names if n not in summary]
        self.assertEqual(
            missing, [],
            f"收尾小结没报这几个状态桶：{missing} —— "
            "正好处在那一档的用户，在小结里哪儿都找不到自己")

