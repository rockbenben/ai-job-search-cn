# -*- coding: utf-8 -*-
"""面板上的渠道开关必须有人读，否则它就是个装饰品。

这一块 2026-08-19 加：面板原来只说「搜到 2600 个岗」，不说这些岗来自哪几家。
用户看不见两件事——某个网站根本没在抓（浏览器渠道默认关着），
以及某个网站抓得到岗却打不出分（前程无忧读不到 JD 正文）。

**开关落在盘上而不是浏览器 localStorage，唯一的理由就是让抓取流程读得到。**
所以这条守的是那根链条的每一环都在：

    面板勾选 → POST /api/portals → portals.json → /job-scrape 读它

任何一环断了，勾选框都会变成「点了有反应、但什么也没发生」——
这个仓库里最贵的一类 bug（`test_dashboard_matching` 那一批盯的是同一件事）。
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


class TheSwitchIsWiredEndToEnd(unittest.TestCase):

    def test_exporter_computes_portal_rows(self):
        import export_web_data as ex
        self.assertTrue(hasattr(ex, "portal_rows"), "导出器没有 portal_rows")
        self.assertTrue(hasattr(ex, "set_portal"), "导出器没有 set_portal")
        # 四家都要有固有属性，缺一家面板上就少一行
        for name in ("猎聘", "BOSS", "智联", "前程无忧"):
            self.assertIn(name, ex.PORTAL_FACTS)
            self.assertIn("jd", ex.PORTAL_FACTS[name],
                          "「能不能拿到 JD 正文」必须带给面板——它解释"
                          "「抓了一堆却一个可投的都没有」")

    def test_missing_file_means_all_on(self):
        """**没设置过 ≠ 全关。** 缺文件时默认全开，否则第一次跑就什么都不抓。"""
        import export_web_data as ex
        got = ex.portals_enabled("__不存在的用户__")
        self.assertTrue(all(got.values()), f"缺文件时不该有关着的：{got}")

    def test_serve_has_the_endpoint(self):
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        self.assertIn('"/api/portals"', src, "serve.py 没有写回端点")
        # **那道 job_id 检查必须放行它**：检查要求每单都带职位 id，
        # 而开关不是针对某个职位的操作，不放行就永远 400。
        self.assertIn('"/api/portals", "/api/prefs"', src,
                      "job_id 检查没放行开关类端点——它们没有 id，会被挡成 400")
        # 而且它要和别的写入端点走同一条 dispatch 链（那条链在 `_WRITE_LOCK` 里）。
        # 另开一块的写法通不过 `test_serve_writes_are_serialized`：读-改-写整份文件，
        # 两个标签页同时勾会互相盖掉。
        self.assertIn('elif path == "/api/portals":', src,
                      "渠道开关没走 dispatch 链——那条链才在写锁里")

    def test_the_scrape_workflow_reads_it(self):
        """最容易断的一环：开关写盘了，但抓取流程从没读过。"""
        wf = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("portals.json", wf, "/job-scrape 没说要读这个开关")
        self.assertIn("关掉的整家跳过", wf)
        auto = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("portals.json", auto, "/job-auto 没说要读这个开关")

    def test_frontend_posts_to_the_disk_not_localstorage(self):
        exc = (ROOT / "web" / "src" / "data" / "excluded.ts").read_text(encoding="utf-8")
        self.assertIn("/api/portals", exc, "前端没有调用写回接口")
        comp = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("postPortal", comp)
        # 没有本地服务时不能给一个点了写不回去的开关
        self.assertIn("hasServer", comp,
                      "没有本地服务时开关要禁用——给一个点了没用的开关是骗人")


class ThePortalFactsMatchTheMeasuredDoc(unittest.TestCase):
    """面板上写的渠道属性，要与 `cdp-portals.md` 的实测表一致。

    两处各写各的必然飘：文档改了、面板还在说旧的，而用户信的是面板。
    """

    def test_the_jd_column_agrees_with_the_doc(self):
        import export_web_data as ex
        doc = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        self.assertIn("详情页（JD 正文与补充字段）", doc, "文档里那张实测表没了")
        # **三家都读得到。** 这条断言 2026-08-19 反过来过一次：原来断言前程无忧
        # 读不到，而那个结论是「没找到」被写成了「没有」。
        for name in ("BOSS", "智联", "前程无忧"):
            self.assertTrue(ex.PORTAL_FACTS[name]["jd"],
                            f"{name} 被标成拿不到 JD——先按文档的方法找过了吗")
        self.assertIn("钩住 `window.open`", doc, "前程无忧取详情 URL 的方法没写下来")

    def test_the_doc_keeps_the_two_extraction_traps(self):
        """两个坑要留在文档里，因为它们**只靠读 DOM 发现不了**。"""
        doc = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        self.assertIn("是图片不是文字", doc, "BOSS 猎头角标那个坑没写下来")
        self.assertIn("只有「前两个是年限与学历」这一条是稳的", doc,
                      "BOSS 标签区那条没写下来")
        self.assertIn("一个样本推不出一条规则", doc,
                      "「从一个样本推规律」这个教训没留下来——它当天犯了两次")


class LoginIsCheckedUpFrontNotOnCollision(unittest.TestCase):
    """没登录要**开跑前就问**，不是撞上了才说，更不是静默跳过。

    2026-08-19 实测里两件事让这条成了硬规矩：

    1. 智联撞到登录墙时已经跑了半程，用户是在报告里才知道「这家没抓」——
       而他登录只要几秒。少一整家的岗，代价远大于开跑前问一句。
    2. **前程无忧未登录时不会报错，只会悄悄变质**：裸入口照样返回 20 条，
       但那 20 条是本地泛招聘，与用户的求职期望毫无关系。没有任何报错、
       数量也正常，只有内容全不对——不查登录态就抓，这批脏数据会直接进库。

    第 2 条是这条规则真正的理由：**「拿不到」会报错，「拿到错的」不会。**
    """

    def _doc(self):
        return (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")

    def test_the_check_comes_first(self):
        doc = self._doc()
        self.assertIn("开跑前先查登录态", doc)
        # 必须排在「通用流程」之前——排在后面就成了流程里的一步，
        # 而流程是一家一家走的，那就又变成「抓一家停一次」。
        self.assertLess(doc.index("开跑前先查登录态"), doc.index("## 通用流程"),
                        "登录态检查排在通用流程之后——那就成了边抓边撞")

    def test_it_forbids_silently_skipping(self):
        doc = self._doc()
        self.assertIn("不要静默跳过", doc)
        self.assertIn("一次问清所有缺的", doc, "没写「一次问清」——会变成抓一家停一次")

    def test_it_records_why_silent_bad_data_is_the_real_danger(self):
        """理由要留下来：不是「拿不到」，是「拿到错的且不报错」。"""
        doc = self._doc()
        self.assertIn("没有任何报错", doc)

    def test_the_scrape_and_auto_workflows_both_carry_it(self):
        wf = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("先查登录态", wf, "/job-scrape 没写这一步")
        auto = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("登录招聘网站那一下", auto,
                      "/job-auto 的「永远归人」表里没有登录这一项")


class TheFourPortalsAreJudgedFromMeasurement(unittest.TestCase):
    """四家的能力判定必须来自实测表，不来自印象。

    2026-08-19 逐家跑了一遍，纠正的都是「凭印象写下的规则」：
    前程无忧被说成不个性化（其实看登录态）、拿不到 JD（其实能）、
    BOSS 被说成不是猎头（角标是图片）、猎聘被说成限流就没了（浏览器还在）。
    """

    def _doc(self):
        return (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")

    def test_the_measured_table_exists_and_covers_four(self):
        doc = self._doc()
        self.assertIn("四家逐个实测", doc)
        head = doc[doc.index("四家逐个实测"):doc.index("### 四条从这张表读出来的结论")]
        for name in ("猎聘", "BOSS", "智联", "前程无忧"):
            self.assertIn(name, head, f"实测表里没有 {name}")
        # 没打通的格子要如实写，不许留空或猜
        self.assertIn("没打通", head, "没打通的格子应当如实写出来")

    def test_throttling_stops_the_whole_site(self):
        """**这条 2026-08-19 当天翻过案，别再翻回去。**

        原来断言的是「停的是这条通道，不是这个网站」，并要求文档写清「换哪条路」。
        依据是当天上午的实测：猎聘 CLI 报 `RATE_LIMITED` 时浏览器搜索页照常能开、
        容量还大一倍。

        当天晚些照这条做的结果：CLI 撞限流后开浏览器，猎聘安全中心当场要短信验证，
        账号被标「行为异常」。**浏览器「当时能开」不等于换通道安全**——同一家、
        同一个 IP，换通道是把软限流升级成硬风控。容量大小在这里不是判据。

        > **2026-08-21（上午）：断言从「钉文案」改成「钉规则」。** 原来断言的是那句
        > 「停的是整个网站，不是那条通道」的**原文**。而当天给的理由
        > （「两条通道用的是同一个账号」）核实后是错的——CLI 全匿名、没有账号，
        > 共用的是 IP。理由改了，措辞跟着改，断言就红了——**可它要守的那件事
        > 一个字没变**：CLI 撞限流时不许改用浏览器。所以改成断言那件事本身。

        > **2026-08-21（用户裁定）：「硬停」改成「放慢」，规则本身动了。**
        > 原话「浏览器其实是刻意访问的，要不 cli 封的时候，浏览器加大访问间隙」——
        > 浏览器那条是他已登录的 Chrome、一次一个页面、人在场，与 CLI 的自动批量
        > 不是一回事，为后者的限流把它整整停一天，代价是整条渠道。
        >
        > **但 08-19 那次升级是真的**，所以放慢要慢到真的改变密度剖面：
        > 间隔 ×3（取值只有一处：`portal_budget.SLOW_GAP_FACTOR`）。
        > 这里原来写的是「每轮上限降到 3（约 1/7 速率）」—— 上限那个旋钮
        > 2026-08-26 已删，`1/7` 则是旧口径（两件事叠起来时）的残留换算。
        > 这条断言守的因此是
        > **「不许按原速换过去」**，不再是「不许换」—— 措辞变了，教训没变。
        > 要是哪天文档里又出现「CLI 撞了就换浏览器，容量还更大」那种写法，
        > 「放慢」这两个字会先消失，这条就红。
        """
        auto = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("放慢", auto,
                      "CLI 撞限流后按原速开浏览器，正是当天把账号标异常的那条路——"
                      "文档要写清它是自动放慢，不是随便换")
        self.assertIn("间隔 ×3", auto,
                      "只说「放慢」不给数，等于没有约束：慢多少全凭执行者心情")
        self.assertIn("portal_budget.py", auto,
                      "只说不许按原速换通道、不说用什么挡住，执行者下次还是会换")

    def test_the_reverse_direction_is_documented_too(self):
        """**浏览器被封不该拖累匿名 CLI**——这一半 2026-08-21 才补上。

        上一条守的是「不许升级」，这一条守的是「不许过度封」。两条都要有：
        只写前者，下一个人会照着「限的是账号」把整家一起停，
        而那正是刚刚推翻的东西。
        """
        scrape = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("CLI 照常抓", scrape, "没写浏览器被封时 CLI 还能用")
        self.assertIn("liepin-browser", scrape,
                      "没给渠道名，用户只会写平台名，那会连 CLI 一起封")
        self.assertIn("health liepin-search", scrape,
                      "没写 CLI 怎么手动探恢复，用户只能干等 24 小时")

    def test_capacity_differences_are_recorded(self):
        """容量差一个数量级，补货顺序要按它排；BOSS 抓完就是抓完了。"""
        doc = self._doc()
        self.assertIn("50 页", doc, "前程无忧的页数没记")
        self.assertIn("21 页", doc, "猎聘浏览器的页数没记")
        self.assertIn("BOSS 抓完就是抓完了", doc, "BOSS 封顶这条没记")

    def test_liepin_selectors_are_not_hardcoded(self):
        """猎聘浏览器端类名是哈希的，写死选择器下次构建就废。"""
        doc = self._doc()
        self.assertIn("哈希", doc)
        self.assertIn("不能写死", doc)


class TheJobTypeSwitchActuallyFilters(unittest.TestCase):
    """「这几类岗要不要看」也必须真的滤，不能只写盘 + 显示个数。

    2026-08-19 加这块时**当场犯了同一个错**：开关写进 `prefs.json` 了、面板显示
    「代招 1361 个」了，但没有任何地方按它过滤——点了没有任何反应。
    上面那条 `TheSwitchIsWiredEndToEnd` 守的就是这个失败模式，而它只盯渠道开关，
    新加的这一组从它下面绕了过去。

    **一个开关的完整链条有四环，缺一环它就是装饰品：**
    写盘 → 导出带上判据 → 页面按它过滤 → 命令行侧也读得到。
    """

    def test_the_predicate_has_exactly_one_home(self):
        """计数和过滤必须用同一份判据，否则两个数对不上。"""
        import export_web_data as ex
        self.assertTrue(hasattr(ex, "pref_tags"), "判据没抽成函数")
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        # 计数走 pref_tags，每个岗也带 pref_tags —— 两个消费方读同一个函数。
        # **盯的是「调了这个函数」，不是某一种参数写法。**
        # 原来钉的是字面量 `pref_tags(v)`；2026-08-21 给它加了第二个参数
        # （驻场要读 JD 正文，见 `_onsite_ids`），这条当场红 ——
        # 而它要守的那件事一个字没变。
        self.assertRegex(src, r"pref_tags\(v[,)]", "计数没走同一个判据")
        self.assertRegex(src, r'"prefTags": pref_tags\(e[,)]', "岗位上没带判据结果")
        # 加参数之后新出现的风险：两处各算一遍那个集合。
        self.assertEqual(src.count("_onsite_ids(user)"), 1,
                         "驻场集合被算了不止一次 —— 计数和逐岗标记会飘")

    def test_the_panel_filters_by_it(self):
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("passesPrefs", app, "页面没按开关过滤——那开关就是装饰品")
        self.assertIn("prefTags", app, "过滤没用导出器给的判据，八成是又写了一份")

    def test_a_search_miss_says_so(self):
        """搜索没搜到是第四种「空表」，不能复用「去找岗」那一支。"""
        sl = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        i = sl.index("emptyText:")
        head = sl[i:i + 400]
        self.assertIn("kw || channel", head,
                      "空表文案没有「搜索没搜到」那一支——用户会被指去 /job-scrape，"
                      "而库里两千多个岗好好躺着")


class TheFourthLinkIsNotJustAComment(unittest.TestCase):
    """第四环——**命令行侧真的读 `prefs.json`**。

    上面那条列出了四环（写盘 → 导出带判据 → 页面过滤 → 命令行侧也读得到），
    却只验了前三环。2026-08-20 查出第四环是**断的**：

    - `prefs.json` 只有 `export_web_data` 读，没有任何工作流读它；
    - 而 `export_web_data` 的注释两处写着「命令行侧的 `/job-rank`、`/job-apply`
      也读得到」——**注释不是机制**，这个仓库为这句话付过多次学费。

    实测后果：用户在面板上关掉「猎头代招」，那 84 个可投的代招岗从名单里消失，
    `/job-apply` 批量却照样给它们出材料——**看不见的岗在后台生成材料**。
    """

    def test_apply_reads_the_switch_before_choosing_jobs(self):
        t = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
        self.assertIn("prefs.json", t, "/job-apply 选岗前不读这个开关")
        self.assertIn("不进批量名单", t, "没写清关掉的那类岗要怎么处理")

    def test_rank_reads_it_too(self):
        t = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        self.assertIn("prefs.json", t, "/job-rank 排序前不读这个开关")

    def test_neither_lets_the_switch_rewrite_verdicts(self):
        """降权/跳过可以，改判词不行——判词是评估的产物，偏好不该反向改写它。"""
        for wf in ("job-apply.md", "job-rank.md"):
            t = (ROOT / "workflows" / wf).read_text(encoding="utf-8")
            seg = t[t.index("prefs.json") - 400: t.index("prefs.json") + 700]
            self.assertTrue(
                "判词与分数不动" in seg or "不结案" in seg or "不该反向改写" in seg,
                f"{wf} 没写明这个开关不许改判词")

    def test_the_comment_matches_reality(self):
        """导出器那句「命令行侧也读得到」必须真的成立。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        if "命令行侧的 `/job-rank`、`/job-apply` 也读得到" not in src:
            self.skipTest("注释已改写")
        for wf in ("job-rank.md", "job-apply.md"):
            self.assertIn("prefs.json",
                          (ROOT / "workflows" / wf).read_text(encoding="utf-8"),
                          f"注释承诺 {wf} 读它，实际没有——注释不是机制")


class TheTogglesActuallyRoundTrip(unittest.TestCase):
    """**真写一次再读回来** —— 上面那些只验链条的形状，不验它通不通。

    上面几条查的是「有没有 `set_portal`」「有没有那个端点」「工作流读不读」
    「前端 POST 到盘还是 localStorage」——全是**形状**。
    2026-08-21 量 `tools/` 的行覆盖率才发现：**中间那一环（真把开关写进盘、
    再读回来）一行都没跑过**。`set_pref` 与 `prefs_enabled`（「这几类岗要不要看」）
    更彻底：整套测试里没有任何一条提到过它们。

    而本文件开头自己写着：「任何一环断了，勾选框都会变成『点了有反应、
    但什么也没发生』——这个仓库里最贵的一类 bug」。**没测到的正是那一环。**

    这条只做最朴素的事：写 → 读回来 → 值对得上；名字不认识时要**拒绝并说清
    能开关的有哪些**，而不是静默写进一个没人读的键。
    """

    def _sandbox(self):
        """把导出器的 ROOT 指到临时目录；本文件的惯例是**方法内** import。"""
        import tempfile

        import export_web_data as ex

        tmp = Path(tempfile.mkdtemp())
        saved = ex.ROOT
        ex.ROOT = tmp
        return ex, tmp, saved

    def test_portal_toggle_round_trips(self):
        ex, tmp, saved = self._sandbox()
        try:
            name = next(iter(ex.PORTAL_FACTS))
            self.assertTrue(ex.portals_enabled("试用")[name],
                            "没设置过应当默认全开")

            r = ex.set_portal("试用", name, False)
            self.assertTrue(r.get("ok"), f"关不掉：{r}")
            self.assertFalse(
                ex.portals_enabled("试用")[name],
                "写进去了却读不回来 —— 勾选框会变成「点了有反应、什么也没发生」")
            self.assertTrue(ex.portals_file("试用").is_file(),
                            "没落到盘上，抓取流程就读不到它")

            self.assertTrue(ex.set_portal("试用", name, True).get("ok"))
            self.assertTrue(ex.portals_enabled("试用")[name], "开不回来")
        finally:
            ex.ROOT = saved

    def test_pref_toggle_round_trips(self):
        ex, tmp, saved = self._sandbox()
        try:
            name = next(iter(ex.PREF_FACTS))
            self.assertTrue(ex.prefs_enabled("试用")[name],
                            "没设置过应当默认全看")

            r = ex.set_pref("试用", name, False)
            self.assertTrue(r.get("ok"), f"关不掉：{r}")
            self.assertFalse(ex.prefs_enabled("试用")[name], "写进去了却读不回来")

            self.assertTrue(ex.set_pref("试用", name, True).get("ok"))
            self.assertTrue(ex.prefs_enabled("试用")[name], "开不回来")
        finally:
            ex.ROOT = saved

    def test_an_unknown_name_is_refused_with_the_valid_list(self):
        """名字不认识时要**拒绝**并列出能开关的，不能静默写进一个没人读的键。"""
        ex, tmp, saved = self._sandbox()
        try:
            for fn, facts, what in ((ex.set_portal, ex.PORTAL_FACTS, "渠道"),
                                    (ex.set_pref, ex.PREF_FACTS, "选项")):
                with self.subTest(what=what):
                    r = fn("试用", "查无此名", False)
                    self.assertFalse(r.get("ok"), f"不认识的名字却说成功了：{r}")
                    msg = r.get("error") or ""
                    self.assertTrue(
                        any(k in msg for k in facts),
                        f"拒绝了但没说能开关的有哪些，用户无从改对：{msg!r}")
        finally:
            ex.ROOT = saved

