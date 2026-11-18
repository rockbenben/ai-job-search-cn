# -*- coding: utf-8 -*-
"""「职位已下线」这个按钮：能标、能放回、不进任何名单与计数。

## 为什么要有它

`expired`（职位关了 / 报名截止 / 点开是聚合页）此前**只有 `/job-apply` 批量写得出来**，
面板上没有入口——用户看到一个明显已经下线的岗，只能回命令行或者干脆放着。

## 为什么必须能放回

加按钮的同时导出侧也得改。原来 `expired` 的岗**整条不导出**，那时它只由 AI 写入，
不导出还说得过去；一旦页面上有了按钮，不导出就意味着**用户点完这个岗当场蒸发、
没有任何回头路**——而「点开是聚合页」这种判断完全可能错（聚合页也可能是平台改版）。

这正是删掉单文件面板时记下的那条教训的反面：一个只能记坏消息、还撤不回来的按钮
比没有更坏。所以：导出、但只进搁置区，给「放回可以投」。

## 与「不投」的分工

- `skipped` = **你的判断**（不合适、不想投）→ 回看时要能看到当初写的原因
- `expired` = **外面的事实**（没了）→ 没什么可回看的，只标日期

分数与判词两种都不动：万一判错，放回来时那些还得在。
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import export_web_data as ex  # noqa: E402
import serve  # noqa: E402

WEB = ROOT / "web" / "src"


class ExpiredJobsStayOutOfEveryList(unittest.TestCase):
    """已下线的岗不进任何名单与计数——它不是「不合适」，是没了。"""

    def test_funnels_exclude_expired(self):
        for extra in ({"materials": {"greeting": "x"}},
                      {"applied": {"status": "applied"}}):
            with self.subTest(shape=list(extra)[0]):
                self.assertEqual(ex.funnels_of({**extra, "expired": True}), [],
                                 "已下线的岗被算进了流水线格子")
        # 反向：没下线的照常进（`ready` = 有材料且没投，同一个函数出的另一个键，
        # 是「备好还没发」那份清单的筛选键，不是流水线的第五格）
        self.assertEqual(
            ex.funnels_of({"materials": {"greeting": "x"}}),
            ["materials", "ready"])

    def test_the_sellable_count_excludes_expired(self):
        """「还能投几个」不能把下线的算进去——它决定要不要提示补货。

        **跟一层间接**，同下面那条的理由：写成 `not j.get("expired")`、
        还是走一个把它包含在内的具名谓词（`is_parked`），是等价的写法。
        2026-08-26 扫重复定义时把那三个内联条件收成 `is_parked(j)`，这条当场红了
        —— 又一次「断言绑死一种写法而非规则」（`CONTRIBUTING.md` 那张失效表）。

        所以改成两条一起验：**表达式里排掉了它**（字面或经由谓词），
        以及**那个谓词真的把已下线算作出局**（行为，不是措辞）。
        """
        import export_web_data as ex
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        i = src.index("n_sellable = sum(")
        seg = src[i:i + 400]
        self.assertTrue('not j.get("expired")' in seg or "is_parked(j)" in seg,
                        "n_sellable 没排除已下线的岗")
        if "is_parked(j)" in seg:
            self.assertTrue(ex.is_parked({"expired": True}),
                            "走了 is_parked，而它并不认已下线 —— 那这层间接是漏的")
            self.assertFalse(ex.is_parked({}), "is_parked 把干净的岗也算出局了")

    def test_the_frontend_lists_exclude_expired(self):
        """TS 侧三份行集（可投 / 名单 / 被收起的已投）都要排掉。

        **跟一层间接。** 判据写在行集里、还是提到一个具名谓词里，是等价的写法；
        这条原来只看锚点后 320 个字符，于是 2026-08-18 把 `hiddenApplied` 的条件
        提成 `isAppliedRow`（为的是让它和点开后的过滤逐字一致）时它就红了——
        又一次「断言绑死一种写法而非规则」（`CONTRIBUTING.md` 那张失效表）。
        """
        app = (WEB / "App.tsx").read_text(encoding="utf-8")

        def window(anchor: str, span: int = 320) -> str:
            """锚点那一段，加上它点名的每个具名谓词的定义段。

            **跟的是名字，不是写法。** 这里原来只认
            `const <名> = (j: Job) =>` 一种拼法，于是 2026-08-21 把那四条共同底
            提成 `const inPlay = useCallback((j: Job) => …)` 之后它当场跟丢 ——
            **同一个「断言绑死一种写法而非规则」，这是第三次**
            （前两次见本方法的说明）。现在 `const <名> =` 后面接什么都跟。
            """
            i = app.index(anchor)
            seg = app[i:i + span]
            for name in set(re.findall(r"\b([a-z][A-Za-z0-9]*)\b", seg)):
                d = f"const {name} ="
                if d in app and d not in anchor:
                    k = app.index(d)
                    seg += app[k:k + span]
            return seg

        for anchor in ("const sellable = useMemo", "const shortlist = useMemo",
                       "const funnelCounts = useMemo"):
            with self.subTest(list=anchor):
                self.assertIn("!j.expired", window(anchor),
                              f"{anchor} 没排除已下线的岗")

    def test_that_detector_still_fails_when_the_check_is_gone(self):
        """变异验证：跟一层间接之后，判据没了仍然要红。"""
        fake = ("const hiddenApplied = useMemo(\n"
                "  () => jobs.filter(isAppliedRow).length);\n"
                "const isAppliedRow = (j: Job) =>\n"
                "  !j.dupOf && canSell(j.verdict);\n")
        self.assertNotIn("!j.expired", fake)

    def test_the_shelf_takes_them_in(self):
        """排掉了就得有地方收——否则用户点完它就人间蒸发。"""
        app = (WEB / "App.tsx").read_text(encoding="utf-8")
        i = app.index("const shelved = useMemo")
        self.assertIn("j.expired", app[i:i + 260],
                      "搁置区没收已下线的岗 —— 点完就没了，且没有回头路")


class TheRoundTripWorksOnDisk(unittest.TestCase):
    """标 → 放回，盘上要能完整走一圈，且分数与判词全程不动。"""

    def _repo(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / ".active_user").write_text("张三", encoding="utf-8")
        u = tmp / "users" / "张三" / "job_scraper"
        u.mkdir(parents=True)
        (u / "seen_jobs.json").write_text(json.dumps({"seen": {
            "https://x/1#岗A": {
                "url": "https://x/1", "title": "岗A", "company": "甲公司",
                "status": "ranked", "rank_score": 72, "rank_verdict": "可以考虑",
            }}}, ensure_ascii=False), encoding="utf-8")
        old = serve.ROOT
        serve.ROOT = tmp
        self.addCleanup(lambda: setattr(serve, "ROOT", old))
        return tmp, u / "seen_jobs.json"

    def _entry(self, p):
        return json.loads(p.read_text(encoding="utf-8"))["seen"]["https://x/1#岗A"]

    def _state(self, p):
        """实际状态。2026-08-19 之后「已下线」在叠加层里，不在职位库里。"""
        import _cli
        e = self._entry(p)
        st = _cli.load_user_state(p)
        return _cli.decided_status(e, st.get("https://x/1#岗A"))

    def _decision(self, p):
        import _cli
        return _cli.load_user_state(p).get("https://x/1#岗A", {})

    def test_expire_then_restore(self):
        _, p = self._repo()
        jid = ex.stable_id("https://x/1", "岗A")

        r = serve.apply_expire(jid)
        self.assertTrue(r["ok"], r)
        e = self._entry(p)
        self.assertEqual(self._state(p), "expired")
        self.assertTrue(self._decision(p).get("date"), "没记下线日期")
        # **职位库一个字都不该动**——这正是把用户决定拆出去的理由：
        # `/job-rank` 整份重写职位库时，才不会把这一下抹掉。
        self.assertEqual(e.get("status"), "ranked", "标下线动了职位库")
        self.assertEqual(e["rank_score"], 72, "分数被下线动掉了 —— 放回来就没了")
        self.assertEqual(e["rank_verdict"], "可以考虑", "判词被下线动掉了")

        r2 = serve.apply_restore(jid)
        self.assertTrue(r2["ok"], r2)
        e2 = self._entry(p)
        self.assertEqual(self._state(p), "ranked",
                         "放回没退回原状态（打过分的该回 ranked）")
        self.assertEqual(self._decision(p), {}, "放回没清掉叠加层里那条决定")
        self.assertEqual(e2["rank_score"], 72)

    def test_the_endpoint_is_routed_and_serialized(self):
        """新写端点必须走 do_POST 的路由，并落在写锁之下。

        端点清单是从 do_POST 源码派生的（见 test_serve_writes_are_serialized），
        所以这里只验它真的写进了路由——写锁那条会自动把它扫进去。
        """
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index("def do_POST")
        j = src.index("def ", i + 10)
        self.assertIn('path == "/api/expire"', src[i:j],
                      "/api/expire 没接进 do_POST 的路由")
        self.assertIn('"/api/expire"', src[:i],
                      "终端日志的动词表里没有 /api/expire —— 会印成路径原文")


class TheTwoActionsAreToldApart(unittest.TestCase):
    """「不投」与「已下线」是两件事，界面上要分得开。

    用户原话：「我投了、不投这个岗的按钮…现在有点混在一起」。推进流程的动作与
    把这一行从名单里拿掉的动作，原来同字重、同一行、中间隔着一整句长说明。
    """

    def test_the_buttons_are_in_two_groups(self):
        src = (WEB / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        self.assertIn("act-advance", src, "推进那组没有自己的容器")
        self.assertIn("act-remove", src, "移出那组没有自己的容器")
        i = src.index("act-remove")
        self.assertIn("act-drop", src[i:i + 900], "「不投」不在移出那组里")
        self.assertIn("act-expire", src[i:i + 900], "「已下线」不在移出那组里")

    def test_the_groups_are_visually_separated(self):
        css = (WEB / "theme" / "cockpit.css").read_text(encoding="utf-8")
        self.assertIn(".act-remove", css, "移出那组没有样式，两组还是混在一起")
        self.assertIn(".act-sep", css, "两组之间没有分隔")
        # 靠右分开摆：原来是 .act-drop 自己 margin-left:auto，现在整组一起走。
        # 锚在**规则声明**上（`.act-remove {`），不是文件里第一次出现这个词——
        # 那次出现在注释里，测试第一版就抓错了地方。
        i = css.index(".act-remove {")
        self.assertIn("margin-left: auto", css[i:i + 200],
                      "移出那组没有与推进那组拉开")

    def test_expire_needs_a_server(self):
        """它写的是盘上的状态，没有服务写不了——不给按钮，别给个点了没反应的。"""
        src = (WEB / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        i = src.index("act-expire")
        self.assertIn("hasServer()", src[max(0, i - 400):i],
                      "「已下线」按钮没判断有没有服务")
        app = (WEB / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("onExpire={live ? expire : undefined}", app,
                      "静态模式下没把这个按钮撤掉")

    def test_removing_a_row_opens_the_next_one(self):
        """把一行移出名单后，展开要落到下一条——不能让页面塌下去。

        被移除的那行连同它的展开区（材料齐全的岗轻松两千像素）一起消失，
        页面高度骤减，浏览器不会替你调整滚动位置：视线当场落到不相干的地方，
        想接着处理下一个还得自己找回来。连着清理已下线的岗时尤其明显。

        `Shortlist` 已经有一个挂在 `selectedId` 上的效果（展开后把那一行滚回
        视口顶部），所以只要把选中挪到下一条，滚动自动跟着走——不必另写一套。
        """
        app = (WEB / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("function nextInList", app,
                      "没有「下一条是谁」的判断 —— 移除后页面会塌")
        i = app.index("function nextInList")
        body = app[i:i + 600]
        self.assertIn("mainList", body)
        self.assertIn("restList", body,
                      "只在主表里找 —— 在「可以考虑」折叠区里清理时会跳出去")
        self.assertIn("[i - 1]", body,
                      "移除最后一行时没有退回上一行，会直接收起")
        # 两个「移出名单」的动作都要接上。
        # **按函数体切，不用固定窗口**：`nextInList` 的定义就紧跟在 `expire`
        # 后面，900 字符的窗口会够到定义本身——把 expire 里的调用删掉照样绿
        # （控制检查实测）。锚点必须落在被验的那段代码里。
        for fn in ("expire", "exclude"):
            with self.subTest(handler=fn):
                m = re.search(rf"const {fn} = \([^)]*\) => \{{(.*?)\n  \}};",
                              app, re.S)
                self.assertIsNotNone(m, f"找不到 {fn} 的函数体")
                self.assertIn("nextInList(", m.group(1),
                              f"{fn} 没有把展开挪到下一条")

    def test_the_swap_happens_in_one_commit(self):
        """换行要在**同一次提交**里完成，否则先塌一下再跳。

        分两步（先 setSnap、再 setSelectedId）会让用户先看到页面塌陷、
        再看到跳转，比不做还难受。
        """
        app = (WEB / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("const refreshAnd", app, "没有「重取快照顺便换选中」那个函数")
        i = app.index("const refreshAnd")
        body = app[i:i + 420]
        self.assertIn("setSnap(s)", body)
        self.assertIn("setSelectedId(next)", body,
                      "快照与选中不在同一个回调里 —— 会先塌再跳")

    def test_restore_does_not_move_the_selection(self):
        """「放回」时不挪：那时没有行消失，挪反而把视线从刚放回的那个岗上带走。

        **查的是规则，不是写法。** 这条原来精确匹配
        `on ? nextInList(id) : undefined` 一种拼法；2026-08-21 把「挪选中」提前到
        乐观移除那一次提交里（`if (on) setSelectedId(nextInList(id))`）之后它当场红了
        —— 意图一字未变，只是换了个形状。**又一次「断言绑死一种写法而非规则」。**

        现在的判据：`exclude` 体内每一次 `setSelectedId`，前面都得有 `on` 这个条件。
        """
        app = (WEB / "App.tsx").read_text(encoding="utf-8")
        i = app.index("const exclude")
        body = app[i:i + 1200]
        hits = [m.start() for m in re.finditer(r"setSelectedId\(", body)]
        self.assertTrue(hits, "exclude 里一次都不挪选中了？标「不投」之后该接上下一条")
        for k in hits:
            near = body[max(0, k - 60):k]
            with self.subTest(at=body[k:k + 34]):
                self.assertRegex(
                    near, r"on \?|if \(on\)",
                    "挪选中没有以 `on` 为条件 —— 「放回」时也会跳，那是多余的跳转")

    def test_the_shelf_labels_them_differently(self):
        """搁置区里两者要分得开：一个能回看原因，一个只标日期。"""
        src = (WEB / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        self.assertIn("已下线", src, "搁置区没把已下线单列一档")
        self.assertIn("job.expiredDate", src, "没显示什么时候标的")
        i = src.index("const canRestore")
        self.assertIn("gone", src[i:i + 120], "已下线的岗给不了「放回可以投」")


if __name__ == "__main__":
    unittest.main()
