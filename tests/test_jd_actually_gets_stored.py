"""JD 读过就得存下来，而且落库率要摆在面板上。

2026-08-19 实测的落库率：猎聘 66.3%、BOSS 0.8%、智联 1.4%、**前程无忧 0%**。
而同一批岗的判词里写着「粗筛（读过 JD 正文）」——**JD 读过，然后在会话里扔了。**
猎聘之所以高，是因为它走 CLI，`fetch_details.py` + `jd_store.py` 把落盘做进了流程；
浏览器三家没有对应物，谁也没回头补过。

这件事躺了一个月没人发现，因为**没有任何地方显示这个数**。所以这一组盯两件：

1. 规则写进了 `cdp-portals.md`（抓 JD 的同一轮就落库）；
2. 落库率真的一路走到面板上——写盘 → 导出 → 类型 → 组件，四环缺一环它就是装饰。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import export_web_data as ex  # noqa: E402


class TheRuleIsWrittenDown(unittest.TestCase):
    def test_browser_channels_are_told_to_persist_in_the_same_round(self):
        doc = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        self.assertIn("同一次访问", doc, "没写「抓到 JD 就存，别拖到下一次访问」这条规则")
        # **2026-08-27：这条路上的命令换成了 `--save`。**
        # 浏览器渠道是一个一个读的，手上只有一段正文；要用 `--import-from`
        # 得先把每段拼成 JSON 写到目录里 —— 那正是这条规则一直没人执行的原因
        # （实测 191 个岗读了没存）。这里钉的是「说了用什么存」，不是钉某个开关。
        self.assertRegex(doc, r"jd_store\.py --(save|import-from)",
                         "只说要存、不说用什么存，等于没说")

    def test_the_measured_gap_is_recorded(self):
        """把实测数字留在文档里——没有它，下一个人会以为这条规则是洁癖。"""
        doc = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        self.assertIn("66.3%", doc, "猎聘的落库率没记")
        self.assertIn("0%", doc, "浏览器渠道的落库率没记")


class TheNumberReachesTheScreen(unittest.TestCase):
    """写盘 → 导出 → 类型 → 组件。缺一环这个数就到不了用户眼前。"""

    def test_export_computes_it(self):
        rows = ex.portal_rows("__不存在的用户__", {}, [], [])
        self.assertTrue(rows, "portal_rows 一个渠道都没给")
        for r in rows:
            self.assertIn("withJd", r, f"{r['name']} 少了 withJd 字段")
            self.assertIsInstance(r["withJd"], int)

    def test_it_counts_only_real_bodies(self):
        """几十个字的占位不算「存过 JD」——与 `jd_store.has_body` 同一条线。"""
        import jd_store
        self.assertFalse(jd_store.has_body({"description": "岗位职责：详见附件"}))
        self.assertTrue(jd_store.has_body({"description": "职" * 80}))

    def test_the_type_declares_it(self):
        t = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
        self.assertIn("withJd", t, "Portal 类型里没有 withJd，前端拿不到")

    def test_the_component_shows_it(self):
        c = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("withJd", c, "组件没读这个字段——导出算了个没人看的数")
        self.assertIn("职位描述存了", c, "面板上没有给用户看的那句话")

    def test_low_coverage_is_visually_loud(self):
        """低了要变色。常态没有颜色，否则四家全是黄的，警示就不再是警示。"""
        c = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("is-thin", c, "低落库率没有任何视觉提示")
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
        self.assertIn(".portal-jd.is-thin", css, "警示色没有对应样式，class 加了也不变色")
        self.assertIn("--caution", css.split(".portal-jd.is-thin")[1][:80],
                      "is-thin 没用警示色")




class BlockedPortalsShoutOnTheDashboard(unittest.TestCase):
    """撞了风控要在面板上**显眼**地说，不能只躺在 portal_budget.json 里。

    被拦的那一刻起这家一个岗也抓不到，而多数情况**只有用户本人能解**（去手机上
    过一条短信）。他看到的现象只会是「怎么最近都没新岗了」——工具停手是对的，
    不告诉他是错的。2026-08-19 猎聘和 BOSS 同一天双双被拦，正是这个场景。
    """

    def test_export_carries_the_block_state(self):
        rows = ex.portal_rows("__不存在的用户__", {}, [], [])
        for r in rows:
            for f in ("blocked", "blockedWhy", "blockedHeldHours"):
                self.assertIn(f, r, f"{r['name']} 少了 {f}")
            self.assertFalse(r["blocked"], "没有额度文件时不该报被封——"
                                           "误报会让用户去过一次根本不需要的短信验证")

    def test_a_real_block_shows_up(self):
        import datetime as dt
        import portal_budget as pb
        data = {}
        pb.block(data, "猎聘", "账号行为异常，要短信验证", dt.datetime.now())
        st = ex._block_state(data, "猎聘")
        self.assertTrue(st["blocked"])
        self.assertIn("短信", st["blockedWhy"], "原因要原样传给用户，别吞成「出错了」")
        self.assertGreater(st["blockedHeldHours"], 0,
                           "不说已经停了多久，用户没法判断换 IP 值不值得现在做")

    def test_the_type_and_component_render_it(self):
        t = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
        for f in ("blocked", "blockedWhy", "blockedHeldHours"):
            self.assertIn(f, t, f"Portal 类型里没有 {f}")
        c = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("portal-alarm", c, "没有告警条——被封只在行内加小字等于没说")
        self.assertIn("只有你本人能过", c, "没告诉用户这件事要他自己动手")
        self.assertIn("--clear", c, "没告诉用户验完怎么恢复，他只能干等 24 小时")

    def test_the_alarm_is_styled_loud(self):
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
        self.assertIn(".portal-alarm", css, "告警条没有样式，会渲染成一段普通文字")
        self.assertIn("--lock", css.split(".portal-alarm")[1][:400],
                      "告警条没用红色——不显眼的告警不叫告警")


class EveryNumberOnScreenCarriesItsDenominator(unittest.TestCase):
    """屏幕上的裸数字会**继承读者刚看到的那个分母**。

    实测（2026-08-21）「什么在挡你」那一节：

        你的主场    评过的 687 个岗里，107 个…
        什么在挡你  英语要求 33          ← 出自另一个总体
                    学历/专业 221        ← 同上
                    行业经验太集中 319/687

    前两条数的是「硬性条件没过」的那批，第三条数的是「有四维拆解」的那批 ——
    **两批几乎不重叠**（过不了硬门的岗通常没有拆解）。而它们并排显示，
    紧挨着的句子刚说完 687。读者会把 33 读成 687 里的，而那 33 个
    一个都不在里面。

    这和同一天在 `/job-upskill --applied` 报表里犯的是同一个错：
    **把另一个语料的数搬进当前语境**。
    """

    def test_blockers_all_carry_one(self):
        import export_web_data as ex
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        seg = src[src.index("blockers = []"):src.index("# ---- 简历")
                  if "# ---- 简历" in src else src.index("blockers = []") + 2500]
        n_of = seg.count('"of"')
        n_append = seg.count("blockers.append")
        self.assertEqual(n_of, n_append,
                         f"{n_append} 条阻碍里只有 {n_of} 条带分母 —— "
                         "裸数字会被读成上一句里那个总数")

    def test_the_component_renders_it(self):
        c = (ROOT / "web" / "src" / "components" / "ResumeRead.tsx").read_text(
            encoding="utf-8")
        self.assertIn("b.of", c, "组件没渲染分母，给了也白给")


class ReadJdAtTheRightMoment(unittest.TestCase):
    """卡片 → 预筛 → 只给活下来的读 JD，全在同一次访问里。

    三条都是拿实测换来的，缺一条就退回原样：
    - 先筛后读：前程无忧 194 个里 121 个（62%）光凭薪资就判掉了，给它们读 JD 是白扔额度；
    - 同一次访问：回头补要重开页面（一次新的风控暴露），而且**列表会变**——
      当天 BOSS 过一次 `_security_check` 后搜索结果重排，4 个岗的卡片直接不在页上了。
    """

    def _doc(self):
        return (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")

    def test_prescreen_runs_before_reading_jd(self):
        d = self._doc()
        self.assertIn("卡片 → 预筛 → 只给活下来的读", d, "没写清三拍的顺序")
        self.assertIn("prescreen.py", d, "没说用什么筛")
        # 锚点同上：那条命令 2026-08-27 换成了 `--save`。比的是先后，不是开关名。
        i, j = d.index("prescreen.py"), d.index("jd_store.py --save")
        self.assertLess(i, j, "预筛写在读 JD 后面了——顺序反了，规则就没用")

    def test_why_not_later_is_recorded(self):
        """把「为什么不能回头补」的两个理由留下，否则下次又会被挪到 /job-rank。"""
        d = self._doc()
        self.assertIn("列表会变", d, "没记「回头时卡片可能已经不在页上」这条实测")
        self.assertIn("风控暴露", d, "没记「回头要重开页面」的代价")


class PortalsRunInParallel(unittest.TestCase):
    """四家是四个独立账号，跨平台并行安全；同一家内部并发危险。"""

    def _doc(self):
        return (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")

    def test_parallel_across_sites(self):
        d = self._doc()
        self.assertIn("并行", d, "还写着串行抓——四家没有互相等待的理由")
        self.assertIn("跨账号并行安全，同账号并发危险", d,
                      "没写下这条边界，下次会有人把一家的翻页也并发出去")

    def test_priority_is_for_budget_not_for_order(self):
        """顺位是「额度先花在谁身上」，不是「谁先开始」——两者混了就退回串行。"""
        d = self._doc()
        self.assertIn("顺位只用来分额度", d, "顺位的用途没说清")
        self.assertIn("BOSS", d)
        self.assertIn("命中率", d)


class TheBlockBannerLinksToTheFix(unittest.TestCase):
    """只说「要短信验证」不给入口，等于把最后一步又扔回给用户。"""

    # 这三条原来直接读写 `data["猎聘"]["where"]` / `blocked_until`，
    # 也就是**绑死了存储结构而不是规则**。2026-08-21 封控改成按通道分开存，
    # 三条一起坏——而它们要守的那件事（拦截页链接到得了用户手上、解封真的解得开）
    # 一个字都没变。改成走公开读口 `block_state()` / `clear()`。
    def test_budget_records_where(self):
        import datetime as dt
        import portal_budget as pb
        now = dt.datetime.now()
        data = {}
        pb.block(data, "猎聘", "要验证", now,
                 "https://safe.liepin.com/v/intercept/verifysms")
        self.assertEqual(pb.block_state(data, "猎聘", now)["where"],
                         "https://safe.liepin.com/v/intercept/verifysms")

    def test_it_falls_back_to_the_home_page(self):
        """没记到拦截页也要给个能点的——让用户自己去翻哪页要验证是最差的一种。"""
        import datetime as dt
        import portal_budget as pb
        now = dt.datetime.now()
        data = {}
        pb.block(data, "BOSS", "风控", now)
        self.assertTrue(pb.block_state(data, "BOSS", now)["where"]
                        .startswith("https://"))

    def test_clear_wipes_it(self):
        import datetime as dt
        import portal_budget as pb
        now = dt.datetime.now()
        data = {}
        pb.block(data, "智联", "风控", now, "https://x.example")
        self.assertFalse(pb.check(data, "智联", now)[0], "封了却没拦住")
        pb.clear(data, "智联", now)
        ok, _ = pb.check(data, "智联", now)
        self.assertTrue(ok, "解冷却之后还是被拦着")

    def test_a_rate_limited_cli_gets_no_fake_link(self):
        """**CLI 撞的是限流，没有页面可去。**

        `block()` 原来一律把 `where` 退到该平台首页。对浏览器那条是对的
        （用户真要去那儿过验证），对 CLI 那条是**编了一个入口**：
        点开只是猎聘首页，什么也不做，而用户会以为自己漏了一步。
        """
        import datetime as dt
        import portal_budget as pb
        now = dt.datetime.now()
        data = {}
        pb.block(data, "liepin-search", "撞了 RATE_LIMITED", now)
        self.assertEqual(pb.block_state(data, "猎聘", now)["where"], "",
                         "给一条没有页面可去的限流编了个「去处理」链接")
        # 浏览器那条照旧要有——那才是用户真正要去的地方。
        data2 = {}
        pb.block(data2, "liepin-browser", "要短信验证", now)
        self.assertTrue(pb.block_state(data2, "猎聘", now)["where"]
                        .startswith("https://"), "浏览器那条反而没给入口")

    def test_the_panel_says_different_things_for_the_two_lanes(self):
        """面板对两种封控要说不同的话，否则对 CLI 说的每一句都是错的。

        原来两者共用一段文案：「点『去处理』在 Chrome 里打开」（CLI 没有页面）、
        「处理完回来点『我处理好了』」（他什么也没处理）——而那个按钮点下去，
        会在接口**仍然限流**的情况下恢复抓取。
        """
        c = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(
            encoding="utf-8")
        self.assertIn("blockedLane", c, "组件没读通道，只能对两者说同一句")
        self.assertIn("不用你做什么", c, "没告诉用户 CLI 那条他插不上手")
        # 命令要在，但**渠道名是后端给的**（`b.channel`），不是写死的字面量 ——
        # 写死的话，哪天第二家有了 CLI 通道，告警条列着它却教用户去探猎聘那条。
        self.assertIn("/job-scrape health ${b.channel}", c,
                      "没写探恢复的命令，或渠道名写死了——用户不知道该敲什么")
        ts = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
        self.assertIn("blockedLane", ts, "类型里没有 blockedLane")
        ex = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("blockedLane", ex, "导出没带通道，字段到不了前端")

    def test_a_blocked_portal_is_visible_without_clicking_anything(self):
        """告警**默认就得看得见**，不能藏在折叠区里等人去点开。

        组件里那句注释写着「要顶到最上面，不能只在自己那一行里加个小字」，
        而整块告警都在「从哪些招聘网站找岗」这个默认折叠的 Collapse 底下。
        2026-08-21 在浏览器里真看了一眼才发现：猎聘 CLI 封着 9 小时，
        面板首屏一个字都没有 —— 用户看到的现象只会是「怎么最近都没新岗」。

        **读源码看不出这个**：JSX 全对、文案全对，缺的是 `defaultActiveKey`。
        """
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        # **2026-08-24：容器换了第三次，守的事没变。**
        # 折叠时代靠 `defaultActiveKey` 自动展开；抽屉时代靠一颗固定按钮；
        # 现在是那一排文字按钮里的「招聘网站」—— 它就在「下一步」下面，
        # 本来就在首屏，所以**不需要自动展开任何东西**，也不该弹窗打断人。
        # 判据从「会不会自动展开」换成「不点开看不看得见」。
        i = app.index('key: "portals"')
        seg = app[i:i + 4200]
        self.assertIn("被拦住了", seg, "按钮上没有任何被拦住的信号")
        self.assertIn("blockNeedsYou", seg, "那枚标记跟被拦住无关")
        self.assertIn('className="deskbar"', app,
                      "那一排按钮没了 —— 告警又要靠点开才看得见")
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(
            encoding="utf-8")
        self.assertIn(".deskbtn-alarm {", css, "那枚标记没有样式，会是一团裸字")

    def test_the_link_reaches_the_component(self):
        """「去处理」那个链接要真的走到组件里。

        **2026-08-21：告警条从「一家一行」改成「一条通道一行」**，链接跟着搬进
        `blockedLanes[].url`。平铺的 `blockedUrl` 还在（它是把一家塌成一条的结果，
        别处还在读），但**组件不再读它** —— 断言要跟着搬，否则守的是一个
        没人再走的字段。守的那件事一个字没变：地址要到用户手上、要能点、要新开页。
        """
        c = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("blockedLanes", c,
                      "组件没读按通道分行的那份数据，第二条被封的通道界面上不存在")
        self.assertIn("href={b.url}", c, "那一行没把「去处理」的地址接上")
        self.assertIn("去处理", c, "没有可点的入口")
        self.assertIn('target="_blank"', c, "链接不在新标签页开，会把面板顶掉")
        ts = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
        self.assertIn("blockedUrl", ts, "类型里没有 blockedUrl")
        self.assertIn("blockedLanes", ts, "类型里没有 blockedLanes")


class TheCliLaneIsPacedAndAccounted(unittest.TestCase):
    """CLI 那条要**记账、按间隔发、撞到就停**。

    2026-08-19 复盘：闸门第一版只数浏览器点击，而 `fetch_details.py` 的 CLI 调用
    一次都没被计数——08-17 那天一口气发了 926 次详情请求 + 106 次搜索，共 1032 次。
    当天没报错，**两天后以「您的 IP 被拦截」结账**。

    **这个类 2026-08-26 改过名。** 原来叫 `ADailyCapExists`，钉的是
    「每家每天的请求总数要有硬上限」。那个上限当天删了 —— 本人裁定：
    「没有固定额度的，你应该等撞到才算到了额度，我们当前应该是控制单渠道
    每次访问的间隙时间」。上面那段实测仍然成立，只是它证明的事情变了：
    它证明的是「这家平台不快速失败」，不是「所以要拍一个日上限」。
    上限改由平台判（`--block`），我们守的是间隔。
    """

    def test_the_cli_lane_is_accounted(self):
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        self.assertIn("pb.note", src, "CLI 发了请求不记账，间隔就无从算起")

    def test_the_cli_interval_comes_from_the_gate(self):
        """间隔是仅剩的那道闸门，**不许在两个地方各写一个数**。

        实测 2026-08-26：`fetch_details` 写死 `INTERVAL_S = 2.0`，而
        `portal_budget.GAP_S["fetch"]` 是 4 —— 唯一的控制有两个说法。
        """
        import fetch_details as fd
        import portal_budget as pb
        self.assertEqual(fd.INTERVAL_S, pb.gap_for("fetch"),
                         "CLI 那条的间隔和闸门对不上")
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        self.assertIn("pb.gap_for(", src, "间隔又被写死成一个字面量了")

    def test_it_records_before_the_request_not_after(self):
        """记在发之前。只记成功的等于把失败请求从账上抹掉，而平台按发出次数算。"""
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        body = src.split("for i, e in enumerate(entries):")[1]
        note_at = body.index("pb.note")
        fetch_at = body.index("d = fetch(")
        self.assertLess(note_at, fetch_at, "记账写在发请求后面了")

    def test_a_blocked_lane_really_stops_that_lane(self):
        """**问的那条通道**封着就停 —— 批量调用方据此收手。

        原来这条问的是 `remaining_today() == 0`。2026-08-26 那个函数随日上限
        一起删了，于是改问 `check()` —— 本来就该问它：两道公共闸门对同一个
        名字给相反答案，正是这条判据 2026-08-21 记下的那次事故。现在只剩一道。
        """
        import datetime as dt
        import portal_budget as pb
        now = dt.datetime.now()
        data = {}
        pb.block(data, "liepin-search", "IP 被拦截", now)
        self.assertFalse(pb.check(data, "liepin-search", now)[0],
                         "CLI 那条封着还放行——926 次就是这么发出去的")
        # **另一条不受连累**：浏览器只是放慢，不是停。
        self.assertTrue(pb.check(data, "liepin-browser", now)[0],
                        "CLI 的冷却把浏览器那条也停了")
        self.assertTrue(pb.check(data, "猎聘", now)[0],
                        "裸平台名把整家都判停了")
        # 两条都封了才是真的停。
        pb.block(data, "liepin-browser", "要短信验证", now)
        self.assertFalse(pb.check(data, "猎聘", now)[0])

    def test_hitting_the_limit_is_what_stops_it(self):
        """「撞到才算」要真的接上：收到 RATE_LIMITED 才 `pb.block`。"""
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        body = src.split("for i, e in enumerate(entries):")[1]
        self.assertIn("STOP_CODES", body, "撞限流那一支没了")
        self.assertIn("pb.block(", body, "撞了限流不封通道，下一条命令照样走进去")

    def test_the_measured_history_is_recorded(self):
        src = (ROOT / "tools" / "portal_budget.py").read_text(encoding="utf-8")
        self.assertIn("1032", src, "08-17 那天的请求量没记——那是「平台不快速失败」的唯一物证")
        self.assertIn("IP", src, "没记最终后果是 IP 被封")


class UnblockingIsAlwaysManual(unittest.TestCase):
    """封 > 勾：被封的家勾着也不抓；**只有人能放行，工具永远不自动解**。

    **这个类的名字来回翻过三次，三次都值得记。**

    1. 最早叫 `UnblockingIsAlwaysManual`，钉的是 `job-scrape.md` 里
       「工具永远不自动解」。
    2. 2026-08-25 发现代码相反（`_one_lane` 一直是 `if now >= t:
       return NOT_BLOCKED`，到点自动放行），于是改名成
       `UnblockingIsManualOrAfterTheCooldown`，**判据倒过去迁就代码**。
    3. 2026-08-26 本人裁定：「cli 被封后……只有用户手动点继续 cli 后，
       才能继续 cli」。自动到期那一行删了，名字翻回第 1 版。

    第 2 次是最贵的一次：那天核的是「文档和代码对不对得上」，
    **没核哪一边才是对的** —— 于是把一条正确的规则改成了错的，
    还顺手给错的那条配了判据。矛盾两边各有一条测试，所以它
    两边全绿地活了一周：不是没人查，是两个查的人各查各的一半。
    """

    def test_the_rule_is_written_down(self):
        d = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("勾着也不抓", d, "没写清「封了就是封了，勾选不算数」")
        self.assertIn("工具永远不自动解", d, "没写死放行归人")
        self.assertIn("不会到点自己解开", d, "没写清它不会自己解")

    def test_the_wrong_sentence_only_lives_as_a_quote(self):
        """**换成 08-25 那句错的了。** 「24 小时满了自动放行」只许以被更正的
        形式出现，不许再作为一句生效的说明 —— 否则下一轮又会照它改代码。"""
        d = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertEqual(d.count("24 小时满了自动放行"), 1, "它又活成一条规则了")
        i = d.index("24 小时满了自动放行")
        self.assertIn("第三次翻面", d[max(0, i - 600):i])

    def test_the_code_really_never_auto_clears(self):
        """文档说的那件事，拿代码现验一遍 —— 光改文字会再飘一次。

        **这条 2026-08-26 反过来了**：原来验的是「满了要自动放行」。
        它当时验得没错，错的是它验的那件事。"""
        import datetime as _dt
        import portal_budget as _pb
        data = {}
        now = _dt.datetime(2026, 1, 1, 12, 0)
        _pb.block(data, "BOSS", "撞了", now)
        self.assertTrue(_pb.block_state(data, "BOSS", now)["blocked"])
        for days in (1, 2, 30):
            with self.subTest(days=days):
                after = now + _dt.timedelta(days=days)
                self.assertTrue(_pb.block_state(data, "BOSS", after)["blocked"],
                                f"{days} 天后自己解开了 —— 那文档那句"
                                "「工具永远不自动解」又成了空话")
        _pb.clear(data, "BOSS", now + _dt.timedelta(days=1))
        self.assertFalse(_pb.block_state(data, "BOSS",
                                         now + _dt.timedelta(days=1))["blocked"],
                         "人动手也解不开")

    def test_the_server_exposes_an_unblock_endpoint(self):
        s = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        self.assertIn("/api/unblock", s, "面板上没法点解封")
        self.assertIn("def apply_unblock", s)
        self.assertIn('seen_path(user).with_name("portal_budget.json")', s,
                      "解封写的是这个文件，不盯它的 mtime 就不会重导出，"
                      "点完告警条还挂着")

    def test_the_button_and_the_halted_badge_exist(self):
        c = (ROOT / "web" / "src" / "components" / "Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("postUnblock", c, "按钮没接接口")
        self.assertIn("我处理好了", c, "没有解封按钮")
        self.assertIn("portal-halt", c,
                      "勾选框旁边没标「被平台拦住」——用户看到勾是开的会以为它在抓")
        # 钉的是**类名**不是那个词（措辞 2026-08-21 从「已停用」改成
        # 「被平台拦住」：勾选框自己已经在说「用不用」，两件事不能共用一个词）。
        self.assertIn("被平台拦住", c, "那个标记没有说清「拦住」和「你没勾」的区别")


if __name__ == "__main__":
    unittest.main()


class TheTwoTimingsCrossReference(unittest.TestCase):
    """浏览器当场抓、猎聘 CLI 下一条命令抓——两种时机都对，但必须互相指向对方。

    不交叉引用的下场是：读 `cdp-portals.md` 的人看到「同一次访问里读 JD」，
    读 `job-rank.md` 的人看到「Step 7 才抓」，两边都以为对方写错了，
    然后有人去「统一」它们——统一到哪一边都会退化。
    """

    def test_cdp_doc_explains_why_cli_differs(self):
        d = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        self.assertIn("和猎聘 CLI 那条路不一样，这不是矛盾", d)
        self.assertIn("预筛在前", d, "没点出两边共用的那条原则")

    def test_rank_doc_points_back(self):
        d = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        self.assertIn("浏览器渠道的岗不走这一步的抓取部分", d)
        self.assertIn("cdp-portals.md", d, "没指回浏览器那边的规则")

    def test_prescreen_really_comes_first_on_the_cli_path(self):
        """`/job-rank` 的顺序必须是先预筛后抓，否则 CLI 也在给死岗花额度。"""
        d = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        i = d.index("预筛：先淘汰，再排序")
        j = d.index("fetch_details", i)  # 抓详情的第一次出现必须在预筛之后
        self.assertLess(i, j, "job-rank 里抓详情排在预筛前面了")


class LiepinBrowserIsInScope(unittest.TestCase):
    """猎聘浏览器是浏览器渠道，浏览器那套规则对它一条不少地适用。

    2026-08-19 用户指出：JD 取数时机的表里没有猎聘浏览器。查下来不只是漏说——
    `cdp-portals.md` 的标题只列了 BOSS/智联/前程无忧，**猎聘字面上不在这份文档的
    范围里**，而「同一次访问取 JD」「每轮 ≤10 次动作」都写在这份文档里。
    于是 `liepin-browser` 这条真实存在的通道，规则上是悬空的。
    """

    def test_the_doc_scope_includes_liepin(self):
        d = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        head = d.split("\n", 1)[0]
        self.assertIn("猎聘", head, "文档标题没把猎聘后备路径算进范围")
        self.assertIn("一条不少地适用", d,
                      "没写清「用的是浏览器，就按浏览器那套来」——"
                      "否则会有人因为它是猎聘就去套 CLI 的分批逻辑")

    def test_cli_is_preferred_but_the_browser_lane_still_runs(self):
        """**CLI 优先 ≠ CLI 一停这家就整个没了。**

        原来这条测的是反面：钉着「猎聘只走 CLI」「CLI 长期不可用」，
        把浏览器那条锁死在「后备、不进常规轮次」。而同一个仓库里有三处说的是
        相反的话 —— `cdp-portals.md` 的结论 1（「猎聘 CLI 限流 ≠ 这一轮没有猎聘」）、
        `portal_budget` 的实现（CLI 冷却时浏览器放行、只降速）、
        `job-scrape.md` Step 0.46（「跳的是通道，不是整家」）。

        实测代价（2026-08-25 一次 `/job-auto`）：CLI 第一个请求就撞限流，
        执行者照那一行把**整个猎聘**跳过，报告写「明天再说」。补跑浏览器：
        一页搜索 40 张卡、新增 36 个 —— 而同一天另外三家合计 50 个。
        猎聘占这个库语料的 84%。
        """
        s = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("闸门放行的通道都要抓", s,
                      "Step 0.44 的标题不再说「按渠道枚举」了")
        self.assertIn("CLI 被闸门挡住时，浏览器那条照常进这一轮", s,
                      "CLI 冷却时改走浏览器这条规则丢了")
        for dead in ("猎聘只走 CLI", "不进常规轮次，只在 CLI 长期不可用"):
            self.assertNotIn(dead, s,
                             f"「{dead}」写回来了 —— 它会把猎聘整家跳过，"
                             "而那是这个库 84% 的语料")

    def test_cli_still_goes_first(self):
        """反向：也别滑到另一头去，变成「两条通道一起全速跑」。"""
        s = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("同一家网站不要同时用两条通道抓", s, "同时双通道的禁令丢了")
        self.assertIn("猎聘：CLI 优先", s, "CLI 优先的顺位丢了")


class SnapshotsAreSelfContained(unittest.TestCase):
    """`posting.md` 是**归档**，`job_scraper/details/` 是**工作缓存**。
    一份依赖缓存的归档不是归档。

    2026-08-20 对账：284 份快照里 163 份（57%）的 JD 已经取不回来——79 份写着
    「JD 正文见 details/」而缓存里没有那条（指针悬空），84 份两样都没有。
    而这批恰恰是**已经出过材料、有些已经投出去**的岗：面试通常在投递后二到三周，
    届时职位早下线，快照是唯一能回查原文的地方。

    悬空指针比坦白没有更糟——它看起来像存过。所以规则是二选一：
    要么自带正文，要么明写「本轮没取到 JD 正文」。
    """

    def test_the_rule_is_in_the_workflow(self):
        d = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
        self.assertIn("JD 正文必须", d, "没写死「快照要自带正文」")
        self.assertIn("一份依赖缓存的归档不是归档", d, "没写下判据，下次又会改回指针")
        self.assertIn("本轮没取到 JD 正文", d, "没给「取不到时怎么写」的出口")

    def test_the_audit_watches_it(self):
        import audit_pipeline as audit
        names = [n for n, _ in audit.CHECKS]
        self.assertTrue(any("快照" in n for n in names), "审计里没有这一项检查")

    def test_dangling_pointer_is_an_error_not_a_warning(self):
        """悬空指针必须是 error：它看起来像存过，比明说没有更容易误事。"""
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        seg = src.split("def check_posting_snapshots_are_self_contained")[1]
        seg = seg.split("\ndef ")[0]
        self.assertIn('"error", "JD 快照的指针悬空"', seg)
        self.assertIn('"warn", "JD 快照里没有正文"', seg)


class TheJdLifecycleIsFullyCovered(unittest.TestCase):
    """JD 三段（抓取→判断→存储）每一格都要有人管，且缺口要说得出来。

    2026-08-20 拉矩阵查出三个空格：

    1. **判词自称「读过 JD」却没存**（283 个）——`needs_recheck` 按 `来源` 措辞判，
       而这些的措辞恰恰是最可信的那一档，从复核队列整个漏出去；
    2. **补抓队列只覆盖猎聘**——缺 JD 的 1116 个里 392 个在浏览器渠道上，
       没有任何工具会去补，而报告只说「待抓 N 个」，读起来像已经全覆盖；
    3. **存了 JD 却还挂「未抓 JD」判词**（156 个）——正文已在库里，判词还是旧的。

    三个都不是「代码写错」，是**没人负责这一格**——所以钉的是覆盖，不是行为。
    """

    def test_claimed_read_without_body_is_a_distinct_predicate(self):
        """「判据够不够硬」和「证据还在不在」是两个问题，不能合并。"""
        import fetch_details as fd
        e = {"rank_breakdown": {"来源": "粗筛（读过 JD 正文）"}}
        self.assertFalse(fd.needs_recheck(e), "措辞可信，第一个谓词本来就不该认它")
        # 第二个谓词按「库里有没有」判——没有活动用户时用假用户，必然查不到
        self.assertTrue(fd.judged_without_stored_body("__不存在的用户__", e))

    def test_recheck_queue_covers_both_predicates(self):
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        seg = src.split("def missing_urls")[1].split("\ndef ")[0]
        self.assertIn("needs_recheck(e)", seg)
        self.assertIn("judged_without_stored_body(user, e)", seg,
                      "复核队列没收「自称读过却没存」那一类——283 个岗没人管")

    def test_out_of_reach_backlog_is_reported(self):
        """够不着的那批必须说出来，否则「待抓 N 个」读起来像全覆盖。"""
        import fetch_details as fd
        self.assertTrue(hasattr(fd, "missing_by_portal"))
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        self.assertIn("这个工具够不着", src, "报告没提够不着的那批")
        self.assertIn("下次 /job-scrape 时顺手落库", src, "没给出它们该怎么补")

    def test_the_audit_watches_the_evidence_gap(self):
        import audit_pipeline as audit
        names = [n for n, _ in audit.CHECKS]
        self.assertTrue(any("自称读过" in n for n in names),
                        "审计里没有「判词自称读过就必须存下」这一项")

    def test_liepin_only_scope_is_deliberate_and_stated(self):
        """只收猎聘不是漏，是设计——但必须写明理由，否则下次有人「补全」它。"""
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        seg = src.split("def missing_urls")[1].split("\ndef ")[0]
        self.assertIn("只收猎聘", seg)
        self.assertIn("列表会重排", seg, "没写清为什么其余渠道不能回头补")
