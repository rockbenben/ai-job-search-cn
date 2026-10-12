# -*- coding: utf-8 -*-
"""「会把**够得着的**补回来」—— 够不着的有几个，那句话一个字没说。

`fetch_details` 自己写得很清楚：**只收猎聘**。其余三家的 JD 只能在抓取当次的
浏览器访问里取（`cdp-portals.md` 第 6 条）。它甚至专门有个 `missing_by_portal()`
把「补不了的那批」报出来，理由写在它的 docstring 里：

> 不报出来的话，跑完这个工具会显得「缺 JD 的都补了」，而实际差着三分之一。

**而审计那条没这么做。** 它说的是「`fetch_details --recheck --apply` 会把
**够得着的**补回来」—— 一个不带数的限定词。读的人只会把它读成「都能补」，
然后等一批永远补不完的账。

实测活动用户 2026-08-25，那 256 个自称读过 JD 却查无正文的岗：

    猎聘（够得着）                   193
    BOSS / 智联 / 前程（够不着）       63

那 63 个不是没救，是**另一条路**：下次 `/job-scrape` 抓到它们时顺手落库。

## 判据借那边的，不另写一套渠道表

`fetch_details` 里那句 `!= "liepin-search"` 原来是个写死的字面量。抄一份到
审计里，就是又一处会各自漂的渠道表 —— 所以给它起了名
（`fetch_details.CLI_PORTAL`），两处引同一个。

## 这是同一类第三次

    /job-rank --requeue-unfounded   报「放回 6 个」，另外 15 个判据同样不成立、
                                    工具按设计不碰，一个字没说（2026-08-25 修）
    年限门那条                       报的是深评，给的修法却是粗筛命令（同日修）
    这一条                           报 256，能补的只有 193

形状一样：**一句话把「我做了什么」说全了，把「剩下那些怎么办」留空。**
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import audit_pipeline as ap  # noqa: E402
import fetch_details as fd  # noqa: E402

AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
FD = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def body() -> str:
    i = AUDIT.index("def check_claimed_reads_are_stored")
    nxt = AUDIT.find("\n\n\ndef ", i)
    return AUDIT[i:nxt if nxt > 0 else i + 6000]


class TheReachableCountIsNamed(unittest.TestCase):
    def test_it_counts_the_reachable_ones(self):
        b = body()
        self.assertIn("reach = sum(", b)
        self.assertIn("out_of_reach = len(bad) - reach", b)

    def test_the_message_says_both_numbers(self):
        b = body()
        self.assertIn("其中 {reach} 个 ", b)
        self.assertIn("另有 {out_of_reach} 个这个工具够不着", b)

    def test_the_hedge_only_lives_as_a_quote(self):
        """**这是修掉的那一处**，而说明里引了它 —— 直接 `assertNotIn` 会红。

        所以判的是「它只许以被引用的形式活着」：全文恰好一次，
        且那一次落在说明块里（形状同这个仓库别处那几条自引守卫）。
        """
        b = body()
        self.assertEqual(b.count("会把够得着的补回来"), 1,
                         "它又作为一句生效的措辞回来了")
        i = b.index("会把够得着的补回来")
        self.assertIn("原来这句话写的是", b[max(0, i - 120):i])

    def test_it_names_which_portals(self):
        """只说「63 个够不着」他不知道是哪几家、也就不知道该等哪条路。"""
        b = body()
        self.assertIn("by.most_common(3)", b)

    def test_it_says_what_happens_to_them(self):
        """够不着不等于没救 —— 不说另一条路，那 63 个就成了死账。"""
        b = flat(body())
        self.assertRegex(b, r"浏览器渠道的 JD 只能在抓取当次取")
        self.assertRegex(b, r"下次跑 /job-scrape 抓到它们时顺手落库")

    def test_the_tail_disappears_when_all_reachable(self):
        """全在猎聘时不该多出一句「另有 0 个」。"""
        b = body()
        self.assertIn('tail = ""', b)
        self.assertIn("if out_of_reach:", b)


class TheJudgeIsBorrowed(unittest.TestCase):
    def test_the_constant_exists(self):
        self.assertEqual(fd.CLI_PORTAL, "liepin-search")

    def test_the_audit_uses_it(self):
        self.assertIn("fd.CLI_PORTAL", body())

    def test_no_second_portal_table(self):
        """字面量抄一份过去，就是又一处会各自漂的渠道表。"""
        b = body()
        self.assertNotIn('"liepin-search"', b)
        self.assertNotIn("BOSS直聘", b.split('return [("warn"')[0])

    def test_fetch_details_uses_it_too(self):
        """起名的意义在于**两处都引它** —— 那边还留着字面量就白起了。"""
        i = FD.index("def missing_urls(")
        self.assertIn("!= CLI_PORTAL", FD[i:i + 3000])

    def test_the_constant_says_why_it_has_a_name(self):
        i = FD.index('CLI_PORTAL = "liepin-search"')
        seg = flat(FD[max(0, i - 700):i])
        self.assertRegex(seg, r"\*\*只收猎聘\*\*")
        self.assertRegex(seg, r"它有第二个读者")

    def test_that_scope_is_still_the_rule(self):
        """哪天它能抓浏览器渠道了，这一整条要重看。"""
        i = FD.index("def missing_urls(")
        self.assertRegex(flat(FD[i:i + 2000]), r"⚠️ \*\*只收猎聘。\*\*")


class TheReasonIsRecorded(unittest.TestCase):
    def test_it_says_why_a_bare_hedge_is_not_enough(self):
        b = flat(body())
        # 小标题也要钉：变异实测把它换成「顺带分一下」时，下面两条照样绿 ——
        # 一整段说明只剩两句被看着，标题一换，读的人先入为主就走偏了。
        self.assertRegex(b, r"\*\*「够得着的」是几个，得说出来。\*\*")
        self.assertRegex(b, r"一个不带数的限定词")
        self.assertRegex(b, r"读的人只会把它读成「都能补」")

    def test_it_carries_the_measurement(self):
        b = body()
        self.assertIn("2026-08-25", b)
        self.assertIn("193", b)
        self.assertIn("63", b)

    def test_it_cites_the_sibling_that_already_did_this(self):
        b = flat(body())
        self.assertRegex(b, r"`fetch_details\.missing_by_portal\(\)` 存在的理由就是这句话")

    def test_that_sibling_really_says_it(self):
        self.assertRegex(flat(fd.missing_by_portal.__doc__ or ""),
                         r"跑完这个工具会显得「缺 JD 的都补了」，而实际差着三分之一")


class TheMessageIsFitForTheTerminal(unittest.TestCase):
    def test_no_markdown(self):
        i = body().index('return [("warn" if wired')
        self.assertNotIn("**", body()[i:])

    def test_the_escalation_is_untouched(self):
        """复核队列认不出它们时仍然升 error —— 那条既有判据不许被带掉。"""
        b = body()
        self.assertIn('("warn" if wired else "error"', b)
        self.assertIn("而且复核队列也认不出它们——没有任何人知道该去补。", b)

    def test_the_bill_warning_survives(self):
        """「先跑一次不加 --apply 的试运行看账单」是这条最贵的一句。"""
        self.assertIn("先跑一次不加 `--apply` 的试运行看账单", body())


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那 256 个真的跨渠道，而且够不着的那批真的不小。"""

    def _got(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = _cli.pick_user("", root=ROOT)
        seen, details = ap.load(user)
        ap._USER[:] = [user]
        return seen, ap.check_claimed_reads_are_stored(seen, details)

    def test_it_fires_today(self):
        _seen, got = self._got()
        if not got:
            self.skipTest("都补齐了 —— 好事")
        self.assertIn("结论自称读过 JD", got[0][1])

    def test_the_out_of_reach_group_is_not_empty(self):
        """**支点。** 全在猎聘时这一条没有由头（那时 tail 也该是空的）。

        ## 2026-10-12：下限从「> 5」降到「> 0」

        原来那 5 不是一条质量线，是**「这个检查不是空转」**的下限。
        而这条尾巴是被真活干掉的：2026-10-12 这一轮补抓把 313 个岗的正文
        补到了 309 个，`fetch_details` 能够着的都补上了，够不着的从
        「一批」缩到 **1 个（51job-browser 1）—— 浏览器渠道的 JD 只能在
        抓取当次落库，下次跑 `/job-scrape` 顺手就有了**。

        语料变了就该重新量，而不是把语料变回那个数。这里守的还是原来那件事
        （这一栏不能是空的、这一句不能是空转），只是把「不小」换成「不空」——
        要是哪天它真的归零，`test_it_fires_today` 会先跳过，那时这条也该跟着退。
        """
        _seen, got = self._got()
        if not got:
            self.skipTest("都补齐了")
        if "另有" not in got[0][2]:
            self.skipTest("这一批全在猎聘 —— 那一句本来就该不出现")
        m = re.search(r"另有 (\d+) 个这个工具够不着", got[0][2])
        self.assertTrue(m)
        self.assertGreater(int(m.group(1)), 0)

    def test_the_two_numbers_add_up(self):
        """现算对账：够得着 + 够不着 = 总数。对不上就是判据分了叉。"""
        _seen, got = self._got()
        if not got:
            self.skipTest("都补齐了")
        msg = got[0][2]
        tot = int(re.search(r"^(\d+) 个岗的判词", msg).group(1))
        reach = int(re.search(r"其中 (\d+) 个 `fetch_details", msg).group(1))
        m = re.search(r"另有 (\d+) 个这个工具够不着", msg)
        rest = int(m.group(1)) if m else 0
        self.assertEqual(reach + rest, tot, f"{reach} + {rest} ≠ {tot}")

    def test_a_hand_count_agrees(self):
        """独立数一遍 —— 判据断掉时它会静默地把所有岗算成够得着。"""
        seen, got = self._got()
        if not got:
            self.skipTest("都补齐了")
        msg = got[0][2]
        reach = int(re.search(r"其中 (\d+) 个 `fetch_details", msg).group(1))
        tot = int(re.search(r"^(\d+) 个岗的判词", msg).group(1))
        self.assertLess(reach, tot,
                        "全算成够得着了 —— 那个渠道判据多半没生效")


if __name__ == "__main__":
    unittest.main()
