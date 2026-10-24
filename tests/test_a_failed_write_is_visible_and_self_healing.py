# -*- coding: utf-8 -*-
"""写操作失败时，用户必须看得见；能自己修好的，不该让他动手。

## 这条修的是什么

2026-10-23 实测：用户点总览页的「我投了」，**没反应**——页面上什么提示都没有。

根因有三层，缺一不可：

1. **服务重启过。** `serve.py` 每次启动换一个写操作通行凭据（token），
   已经开着的那个标签页手里的旧 token 就废了 → 每个写操作都撞 403。
2. **错误文案被渲染在一块刚被卸载掉的区域里。** `JobReadout.tsx` 的
   `statusErr` 写在 `{marked && …}` 块**里面**，而失败那一支的
   `setMarked(null)`（回滚乐观更新）把整块卸载了——紧接着设置的
   `statusErr` 根本没有地方显示。**文案是有的，只是没人看得见。**
3. **前端只拿得到一句中文。** 服务端分不清「凭据过期（刷新就好）」
   和「这个岗真没了（要重取快照）」，页面只能把两种一起当「失败」。

## 判据

- 凭据过期：**自己换新凭据重试一次**（`excluded.ts` 的 `refreshToken`），
  用户什么都不用做。
- 真的没写进去：**那句话必须显示出来**，而且要显示在**不会被回滚卸载**
  的地方。
- 服务端给回来的错要带一个**机器能认的 `code`**，前端才不必去认中文。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web" / "src"
TOOLS = ROOT / "tools"

EXCLUDED = (SRC / "data" / "excluded.ts").read_text(encoding="utf-8")
READOUT = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
SERVE = (TOOLS / "serve.py").read_text(encoding="utf-8")


class TheTokenSurvivesARestart(unittest.TestCase):
    """服务重启不该让已经开着的页面失去写能力。"""

    def test_the_token_is_read_from_a_file_not_minted_per_process(self):
        self.assertIn("def _load_or_make_token(", SERVE,
                      "token 又是每次启动现生成的了 —— 重启一次就废掉一页")
        self.assertIn("token_path(", SERVE,
                      "token 没有落盘的地方")
        self.assertIn(".api_token", SERVE,
                      "token 的文件名写死错了地方")

    def test_the_page_injects_the_same_one_that_is_checked(self):
        """**注进页面的与校验的必须是同一个**。

        原来模块里躺着 `TOKEN`、服务却去别处现读——同一份代码里两个 token，
        谁对不上谁就说不清（2026-10-23 实测：测试拿 `srv.TOKEN` 去打服务，
        服务拿文件里那个来比，于是同源请求被判 403）。
        """
        self.assertIn("json.dumps(TOKEN)", SERVE,
                      "注进页面的不是模块里那一个")
        self.assertIn('body.get("token") or ""), TOKEN', SERVE,
                      "校验用的不是模块里那一个")

    def test_it_falls_back_when_there_is_no_active_user(self):
        """没有活动用户时不能在这里炸 —— 服务还要能起来报错。"""
        i = SERVE.index("def _load_or_make_token(")
        seg = SERVE[i:i + 1400]
        self.assertIn("except Exception", seg,
                      "读不到活动用户就整个导入失败 —— 服务起不来")


class TheTokenFollowsThePinnedUser(unittest.TestCase):
    """`--user bob` 必须用 bob 的 token，不能再沿用活动用户的。

    `TOKEN` 在模块导入时按 `.active_user` 读一次；而 `--user` 要到 `main()`
    里才生效。两者之间没有重新加载，于是「活动用户 alice、起 bob 的面板」
    会拿 alice 的 token——按用户分文件的隔离在这一步断了。
    """

    def test_main_reloads_the_token_after_pinning(self):
        src = (TOOLS / "serve.py").read_text(encoding="utf-8")
        pin = src.index("_PINNED_USER = u")
        after = src[pin:]
        self.assertIn("TOKEN = _load_or_make_token()", after,
                      "设置 _PINNED_USER 之后没有重新加载 token")


class TheServerSaysWhatWentWrongInAMachineReadableWay(unittest.TestCase):
    """前端要能分辨「刷新就好」和「这个岗没了」，不能去认中文。"""

    def test_the_token_failure_carries_a_code(self):
        self.assertIn('"code": "token_expired"', SERVE,
                      "凭据过期没有 code —— 前端没法自动恢复")

    def test_the_unknown_job_carries_a_code(self):
        self.assertIn('"code": "unknown_job"', SERVE,
                      "岗不在库里没有 code —— 前端只能跟用户说「失败了」")

    def test_the_code_reaches_the_thrown_error(self):
        i = EXCLUDED.index("async function post<")
        seg = EXCLUDED[i:i + 1600]
        self.assertIn("data.code", seg,
                      "服务端的 code 没被带出来 —— 前端拿不到就自动不了")


class AFailedWriteHealsItselfWhenItCan(unittest.TestCase):
    """能自己修的，别让用户动手。"""

    def test_there_is_a_token_refresh(self):
        self.assertIn("refreshToken", EXCLUDED,
                      "凭据过期没有自愈路径 —— 用户只能自己刷新")

    def test_it_retries_once_and_only_once(self):
        """重试必须有上限，否则两个过期来回打转。"""
        i = EXCLUDED.index("async function post<")
        seg = EXCLUDED[i:i + 1800]
        self.assertIn("retry", seg,
                      "重试没有开关 —— 会来回打转")
        self.assertRegex(seg, r"token_expired.*&& *retry",
                         "重试没有限定在「凭据过期」这一种失败上")

    def test_it_reads_the_new_token_from_the_same_origin(self):
        """同源取 `/`——那上面注着当前有效的 token。跨站读不到。"""
        i = EXCLUDED.index("async function refreshToken(")
        seg = EXCLUDED[i:i + 800]
        self.assertIn("__API_TOKEN__", seg,
                      "没有从同源页面取回新 token")


class TheReasonIsActuallyVisible(unittest.TestCase):
    """**判据钉的是「那句『没记上』渲染在不会被回滚卸载的地方」。**

    2026-10-23 之前它在 `{marked && …}` 块里面，而失败那一支正好
    `setMarked(null)` 把那块卸载了——于是文案有、界面没有。
    """

    def test_the_error_is_rendered_outside_the_marked_block(self):
        i = READOUT.index("statusErr && (")
        # 往上找它所在的块开头：必须在 `{marked &&` **之外**。
        before = READOUT[:i]
        marked_open = before.rfind("{marked && (")
        marked_close = before.rfind(")}")
        self.assertTrue(
            marked_close > marked_open,
            "『没记上』那句还在 `{marked && …}` 块里面 —— "
            "回滚乐观更新时它跟着一块被卸载，用户还是看不见")

    def test_it_has_a_visible_style(self):
        css = (SRC / "theme" / "cockpit.css").read_text(encoding="utf-8")
        # **只认独立的那条规则**（行首 `.status-err {`）——
        # 上面还有一条把 `.status-err` 跟别的选择器并在一起的，
        # 正则若不锚行首会先撞上那一条，量到的就不是这条规则的样式。
        m = re.search(r"(?m)^\.status-err\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m, "`.status-err` 的样式不见了")
        self.assertIn("--lock", m.group(1), "错误不用警示色 —— 跟正文一样，看不出来")
        self.assertIn("display: block", m.group(1),
                      "错误还挤在那一行里 —— 用户扫过去看不见")


if __name__ == "__main__":
    unittest.main()
