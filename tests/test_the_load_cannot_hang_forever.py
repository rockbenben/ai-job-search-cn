# -*- coding: utf-8 -*-
"""总览页读数据那一格不能「悬着」，也不该用假数据顶替真数据。

## 两条病，同一个格子

**一、永远转下去。** `fetch` 只有拿到**响应头**才 resolve；正文那一段断了
（连接被重置、服务进程被杀、`Content-Length` 说好了多少却没送够），它
**既不 resolve 也不 reject**，只是不 settle。实测 2026-10-12：

    页面停在「正在读取本机数据…」两分钟不动；
    浏览器控制台 **一条错都没有**；
    `python tools/serve.py` 的日志是一串 ConnectionAbortedError。

**`try/catch` 抓不到这种「悬着」** —— 它不是异常，是没结束。刷��和干等是
用户仅有的两个选择，而两个都不知道自己该等什么。

**二、拿别人的进度顶替。** 失败一律退回演示数据：110/23/3 与 5 个虚构
职位，每一处都长得像真的。页头那行「演示数据（虚构）」是诚实的，
可它要用户**注意到** —— 而他刚打开页面，正等着看自己的进度。

## 分寸：只拦「服务端接上了却没交出数据」那一种

服务压根没起（`file://` 直开、忘了起 serve）时，演示数据是一份**正当的
首次体验**，不该报错 —— 那条路由 `isRealData` 的横幅管着。把两者混成
一个错误提示，等于让真正出事的人对着一句「服务没开」。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOAD = ROOT / "web" / "src" / "data" / "load.ts"
APP = ROOT / "web" / "src" / "App.tsx"


def _src(p):
    return p.read_text(encoding="utf-8")


def _fn(text, name):
    """取某个顶层函数的正文（从 def 到下一个顶层 def/EOF）。"""
    i = text.index(name)
    seg = text[i:]
    m = re.search(r"\n(?=(export |const |function |class |def ))", seg[1:])
    return seg[:m.start() + 1] if m else seg


class TheLoadCannotHangForever(unittest.TestCase):
    def test_the_fetch_has_a_deadline(self):
        """没有超时，悬着的那一种就永远等下去。"""
        t = _src(LOAD)
        self.assertRegex(t, r"LOAD_TIMEOUT_MS\s*=\s*\d",
                         "读数据没有上限 —— 悬着的时候这一格不会结束")
        self.assertIn("AbortController", t, "超时得有一个真的会响的东西去 abort")
        self.assertIn("signal: ctl.signal", t,
                      "signal 没传给 fetch —— 超时那道闸门等于没装")

    def test_the_timer_is_always_cleared(self):
        """忘了 clearTimeout：每次读数据都留一个定时器。"""
        body = _fn(_src(LOAD), "export async function loadSnapshot")
        self.assertIn("finally", body, "没有 finally：异常路径上定时器留着")
        self.assertIn("clearTimeout", body)

    def test_a_hang_is_not_mistaken_for_a_missing_server(self):
        """两者对用户是两件事：一个是坏了，一个是没开。"""
        body = _fn(_src(LOAD), "export async function loadSnapshot")
        self.assertRegex(body, r"reached\s*=\s*true",
                         "没区分「服务端接上了」与「压根没接上」")


class AFailedLoadSaysSoInsteadOfBorrowingSomebodyElsesProgress(unittest.TestCase):
    def test_it_records_a_reason(self):
        self.assertIn("loadError", _src(LOAD))

    def test_the_ui_shows_it(self):
        app = _src(APP)
        self.assertIn("snap.loadError", app, "失败原因没人显示 —— 白记")
        self.assertIn("读不到本机数据", app,
                      "没有一句说清发生了什么的话")

    def test_the_ui_names_the_command_that_fixes_it(self):
        """`AGENTS.md`「每一处引导都要写出该敲的命令」。"""
        app = _src(APP)
        i = app.index("snap.loadError")
        seg = app[i:i + 700]
        self.assertIn("python tools/serve.py", seg,
                      "这一格没给出该敲的命令 —— 用户只能猜")

    def test_the_command_is_copyable(self):
        """让人对着屏幕手打命令是在制造错字。"""
        app = _src(APP)
        i = app.index("snap.loadError")
        seg = app[i:i + 700]
        self.assertRegex(seg, r"<Cmd>\s*python tools/serve\.py\s*</Cmd>",
                         "命令不在可复制块里")

    def test_the_first_screen_still_says_what_it_is_waiting_for(self):
        """加载中那一句要说明在等什么，否则分不清加载还是卡死。

        ⚠️ **断言不能锚在体量单位上**：第一版写的是「约 2.4 MB」，而字母单位
        夹在中文句子里会被 `test_web_copy` 判成散落英文 —— 于是那句提示本身
        把一条守卫弄红了。这里断言「说了多久/多大」这件事，不锚具体写法。
        """
        app = _src(APP)
        i = app.index("正在读取本机数据")
        seg = app[i:i + 200]
        self.assertNotEqual(seg.strip(), "正在读取本机数据…",
                            "加载提示只有一句干话：用户不知道该等多久")
        # 句尾要带一个括注（等多久/多大），而不是补一个「请稍候」就完事
        self.assertIn("（", seg, "加载提示没有说明体量或时长")


class AServerThatIsNotRunningIsNotAnError(unittest.TestCase):
    """分寸：演示数据在「服务没起」时是**正当的首次体验**。"""

    @staticmethod
    def _catch_code():
        body = _fn(_src(LOAD), "export async function loadSnapshot")
        seg = body[body.index("} catch"):]
        # 剥掉行尾注释再比 —— 那句「不是错误」正是它要保的规矩本身
        return "\n".join(re.sub(r"//.*$", "", ln) for ln in seg.splitlines())

    def test_the_demo_path_survives_a_refused_connection(self):
        """连接被拒、且这一页**从没读到过真数据**时，退回演示数据且不带 loadError。

        「从来没读过」是新增的前提：已经显示过真实数据的页面断连，不能再换成
        另一份看起来像真的演示数据（否则用户会以为自己的记录没了）。
        """
        catch = self._catch_code()
        self.assertIn("everLoadedReal", catch,
                      "没记住这页读到过真数据，断连仍会换回演示数据")
        self.assertRegex(catch, r"(?m):\s*demo\s*;?\s*$",
                         "从没读过真数据时不能带 loadError —— 那不是错误")

    def test_and_that_path_carries_no_error(self):
        self.assertNotRegex(self._catch_code(), r":\s*demo\s*,\s*loadError",
                            "服务没起时也报错了 —— 演示数据是正当的首次体验")


class TheNewFieldTravelsTheWholeWay(unittest.TestCase):
    """`normalize` 是手写白名单：漏一个字段，那块界面就永远不出现。"""

    def _interface_body(self):
        t = _src(LOAD)
        i = t.index("export interface Snapshot")
        # 注释里的 `}` 会让「找到第一个右花括号」找错地方，按行剥掉注释再取
        seg = t[i:t.index("\n}", i)]
        return "\n".join(ln for ln in seg.splitlines()
                         if not ln.strip().startswith(("*", "/*", "*/")))

    def test_it_is_declared_on_the_type(self):
        self.assertIn("loadError", self._interface_body())

    def test_it_is_carried_by_normalize(self):
        """与 `test_no_silent_demo_fallback` 那条同源，这里只盯这一个字段。"""
        body = _fn(_src(LOAD), "function normalize")
        self.assertIn("loadError", body, "`loadError` 没被 normalize 带过去")


class TheHonestExitStillWorks(unittest.TestCase):
    def test_real_data_still_wins_over_the_length_check(self):
        """这一条是 `test_no_silent_demo_fallback` 的正身，这里只防改坏。

        只问**顺序**，不钉那行长什么样：原来跟着钉了一句
        `if (d.isRealData) return`，写成 `if (d.isRealData) { return }` 语义没变
        而守卫会红——那正是 `test_a_guard_pins_behaviour_not_a_line.py` 数的那种。
        下面这条同时要求这个判断**存在**（`index` 找不到直接报错）且排在长度判断之前。
        """
        body = _fn(_src(LOAD), "export async function loadSnapshot")
        self.assertLess(body.index("d.isRealData"), body.index("d.jobs.length === 0"),
                        "isRealData 的判断排在长度判断之后，等于没判")


if __name__ == "__main__":
    unittest.main()