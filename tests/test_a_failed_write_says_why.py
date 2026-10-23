# -*- coding: utf-8 -*-
"""七条写路径里有一条把服务端的真因吞掉了。

`excluded.ts` 的 `post()` 是所有写动作的共用入口，它自己的注释写着：

> 服务端把真因放在 error 里；**别把失败咽掉** —— 咽掉的结果是页面显示已排除、
> 盘上其实没改，下次刷新它又回来，而用户不知道为什么。

`Portals.tsx` 三条写路径都照做了（`setErr(e instanceof Error ? e.message : …)`）。
而 `hr-answer` 那条原来是 `catch { return false; }` —— 于是「profile 目录不存在」
「token 不对」「文件只读」一律显示成同一句「没存进去——本地服务还在跑的话再点
一次」，而**再点一次都没用**。

## 判据钉的是「真因到得了界面」，不是某种写法

`Portals` 用 `setErr(e.message)`，`HrAnswers` 现在也是。写法可以变，
不变的是：失败时界面上出现的**不能只有那句通用兜底**。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web" / "src"

EXCLUDED = (SRC / "data" / "excluded.ts").read_text(encoding="utf-8")
APP = (SRC / "App.tsx").read_text(encoding="utf-8")
HRQA = (SRC / "components" / "HrAnswers.tsx").read_text(encoding="utf-8")
PORTALS = (SRC / "components" / "Portals.tsx").read_text(encoding="utf-8")


class TheSharedPostStillRefusesToSwallow(unittest.TestCase):
    """这一整条建立在 `post()` 会抛、而且带着服务端的话上。"""

    def test_it_throws_with_the_server_message(self):
        i = EXCLUDED.index("async function post<")
        seg = EXCLUDED[i:i + 1200]
        # **判据钉的是「服务端那句话被原样带出来」，不是某个类名。**
        # 2026-10-23 起 `post()` 抛的是 `ApiError`（Error 的子类，多带一个
        # 机器能认的 `code`）—— 那句话一个字没少，只是多了一个字段。
        self.assertIn("data.error", seg,
                      "不再把服务端的 error 带出来了 —— 下面那些断言就全落空了")
        self.assertIn("throw new ", seg,
                      "post() 不再抛了 —— 失败就没人接得住")

    def test_the_reason_it_must_not_swallow_is_recorded(self):
        self.assertIn("别把失败咽掉", EXCLUDED)


class NoWritePathSwallowsTheReason(unittest.TestCase):
    def test_the_hr_answer_path_no_longer_returns_false(self):
        i = APP.index("postHrAnswer(q, a)")
        seg = APP[max(0, i - 400):i + 200]
        self.assertNotIn("return false", seg,
                         "又把失败吞成一个布尔了 —— 真因到不了界面")

    def test_the_component_shows_the_message(self):
        i = HRQA.index("await onSave(it.q, draft)")
        seg = HRQA[i:i + 400]
        self.assertIn("e instanceof Error ? e.message", seg,
                      "只显示了那句通用兜底")

    def test_the_generic_line_is_only_a_fallback(self):
        """那句「再点一次」要留着 —— 拿不到 message 时总得说点什么。"""
        self.assertIn("没存进去——本地服务还在跑的话再点一次", HRQA)

    def test_the_signature_says_to_throw(self):
        i = HRQA.index("onSave: (q: string, a: string)")
        self.assertIn("Promise<void>", HRQA[i:i + 80],
                      "签名还收 boolean —— 那就是在邀请调用方吞异常")

    def test_portals_is_still_the_pattern(self):
        """它是这条改动照抄的样板。样板变了，这里的说法就要跟着变。"""
        n = len(re.findall(r"setErr\(e instanceof Error \? e\.message", PORTALS))
        self.assertGreaterEqual(n, 3, f"Portals 那三条写路径的样板变了（现在 {n} 处）")


class EveryWriteIsGatedByTheServer(unittest.TestCase):
    """静态打开时按钮点下去存不回盘 —— 那比不给按钮更坏。"""

    def test_every_component_that_writes_asks_hasserver(self):
        for name in ("Portals.tsx", "JobPrefs.tsx", "HrAnswers.tsx", "JobReadout.tsx"):
            p = SRC / "components" / name
            text = p.read_text(encoding="utf-8")
            with self.subTest(component=name):
                self.assertTrue("hasServer" in text or "live" in text,
                                f"{name} 里有写动作却不看服务在不在")

    def test_the_offline_branch_names_the_command(self):
        """`AGENTS.md`「每一处引导都要写出该敲的命令」—— 不给按钮就得说怎么开。"""
        self.assertIn("python tools/serve.py", HRQA)


if __name__ == "__main__":
    unittest.main()
