"""额度闸门：**CLI 撞了限流要停整家**，而浏览器撞风控只停它自己。

这条规则的前半是 2026-08-19 用真实代价换来的，而且当天被写反过一次——文档先被
改成「CLI 撞限流就换浏览器，容量还更大」，照做之后猎聘账号被标「行为异常」、
要短信验证。所以它不能只活在文档里：文档能被下一次「实测」再改回去，测试不能。

**后半是 2026-08-21 补的，而且推翻了当时给的理由。** 原话是「限的是账号，
CLI 和浏览器用的是同一个账号」——核实 `liepin-search` 的请求头，
两处 fetch 都**没有 `Cookie`、没有 `Authorization`**，它是全匿名的、没有账号。
真正共用的是 IP。按错理由封出来的范围也就错了：用户在浏览器里被要求短信验证，
不该让一个匿名接口跟着停 24 小时。

所以形状是**不对称**的，两个方向各有各的判据：

| 谁撞上 | 另一条 | 为什么 |
|---|---|---|
| CLI 撞限流 | 浏览器**放慢**（间隔 ×3；「每轮上限」2026-08-26 已删） | 同一家同一个网络出口，按原速换通道会把软限流升级成账号风控 |
| 浏览器撞风控 | CLI **照常** | 匿名接口与那个账号无关 |

> **「放慢」是 2026-08-21 用户裁定的，原来是硬停。** 理由：
> 「浏览器其实是刻意访问的，要不 cli 封的时候，浏览器加大访问间隙」——
> 它用的是他自己已登录的 Chrome、一次一个页面、人在场，
> 与 CLI 的自动批量不是一回事。**但 08-19 那次升级是真的**，
> 所以放慢要慢到改变密度剖面（合起来约 1/7 速率），判据钉了下限。

盯四件事：
1. `block()` 了 CLI 之后，浏览器**能用但被实质放慢**、CLI 自己停；
2. `block()` 了浏览器之后，**CLI 仍然过得了**——这是新增的那一半；
3. `fetch_details.py` 撞 `RATE_LIMITED` 时确实调了 `block()`（不靠人记得）；
4. 文档里不许再出现「换同一家的另一条路」那个写法。

> **这个文件曾经整份在 CI 上没跑过。** 它原来写成 pytest 风格的模块级函数，
> 而 CI 跑的是 `python -m unittest discover`——后者只收 `TestCase` 的方法，
> 13 条判据一条都没被执行过（2026-08-20 用 pytest/unittest 收集数对比发现：
> pytest 收 1767，unittest 只跑 1754）。**判据存在、却从不执行**，
> 跟这个仓库反复在治的「空 glob 恒绿」是同一个形状，而且更难看见——
> 本机用 pytest 跑是绿的，CI 上它压根不存在。
> 现已转为 `TestCase`；`tests/test_ci_actually_runs_every_test.py` 盯着不许再犯。
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import portal_budget as pb  # noqa: E402

NOW = dt.datetime(2026, 8, 19, 15, 0, 0)


class BlockStopsTheWholeSite(unittest.TestCase):
    def test_a_cli_block_really_slows_the_browser_down(self):
        """**CLI** 撞限流之后，浏览器那条**放慢**（2026-08-21 前是硬停）。

        ## 这条改过一次，两个版本都要读

        **原样**：CLI 撞限流 → 浏览器一起停 24 小时。依据是 2026-08-19 实测
        （CLI 报 `RATE_LIMITED` 之后立刻开浏览器搜索页，安全中心当场要短信验证）。

        **现在**：用户 2026-08-21 裁定改成放慢 ——「浏览器其实是刻意访问的，
        要不 cli 封的时候，浏览器加大访问间隙」。两条通道的访问性质确实不同：
        浏览器是他自己已登录的 Chrome、一次一个页面、人在场；CLI 是自动批量。
        为后者的限流把前者整整停一天，代价是整条渠道。

        **但那次升级是真的**，所以这条判据盯的不是「能不能用」，
        是**密度有没有被实质压低**：象征性地加几秒等于没改。
        """
        data = {}
        pb.block(data, "liepin-search", "CLI 撞 RATE_LIMITED", NOW)

        # CLI 那条自己照旧停 —— **点名问它**才是这个意思。
        ok, why = pb.check(data, "liepin-search", NOW)
        self.assertFalse(ok, "liepin-search 居然还能抓")
        self.assertIn("停着", why)

        # **裸平台名问的是「这家还能不能动」，不是「主通道能不能动」。**
        # 它原来和 `liepin-search` 一起断言 False —— 那时候两条通道一起停，
        # 说得通。改成放慢之后这个断言就把设计本身否掉了：`job-scrape.md`
        # 让执行者见退出码 1 就跳整站，于是 CLI 一撞限流，**浏览器那条整整
        # 一天用不上**，而它明明只是要放慢。判据搬进了 `effective_lane()`。
        ok, why = pb.check(data, "猎聘", NOW)
        self.assertTrue(ok, f"CLI 冷却把整家都跳过了，而裁定是浏览器放慢不停：{why}")
        self.assertIn("放慢", why, "放行了却不说它在放慢，执行者会按原速抓")
        self.assertIn("liepin-search", why, "没说清是哪条封着、要走那条得先问谁")
        self.assertEqual(pb.effective_lane(data, "猎聘", NOW), "browser")

        # 两条都封时，裸平台名才是「这家不能动」。
        both = {}
        pb.block(both, "liepin-search", "CLI 撞 RATE_LIMITED", NOW)
        pb.block(both, "liepin-browser", "要短信验证", NOW)
        ok, why = pb.check(both, "猎聘", NOW)
        self.assertFalse(ok, "两条都封着还说能抓")
        self.assertIn("都不通", why, "没说另一条也封着——用户会照它去开浏览器")

        # 浏览器：能用，但额度是「放慢」那一套
        ok, why = pb.check(data, "liepin-browser", NOW)
        self.assertTrue(ok, f"浏览器被停掉了，而裁定是放慢：{why}")
        self.assertIn("放慢", why, "没告诉用户它正在放慢，看着就像一切正常")
        # **间隔真的变长了**：原速能过的时刻，放慢时必须过不去。
        # （原来这儿还钉一句「每轮上限降到 3」，2026-08-26 那个上限删了，
        #   放慢从此只剩间隔这一种表现 —— 下面这几行就是它的全部。）
        pb.note(data, "liepin-browser", 1, NOW, "navigate")
        base = pb.gap_for("navigate")
        ok_fast, _ = pb.check(data, "liepin-browser", NOW + dt.timedelta(seconds=base + 1))
        self.assertFalse(ok_fast, "按原速就放行了——那就不是放慢")
        ok_slow, _ = pb.check(
            data, "liepin-browser",
            NOW + dt.timedelta(seconds=base * pb.SLOW_GAP_FACTOR + 1))
        self.assertTrue(ok_slow, "等够放慢后的间隔也不放行")

        # 说清为什么慢 —— 不说的话下一个人会以为是工具卡了
        _, why2 = pb.check(data, "liepin-browser", NOW + dt.timedelta(seconds=base + 1))
        self.assertIn("放慢", why2)

    def test_the_slowdown_reaches_the_only_thing_that_enforces_it(self):
        """放慢必须在 **`--wait`** 里生效 —— 那才是真正执行间隔的那一处。

        `--wait` 自己的说明写着：「`--check` 只会告诉你「太密」，**不会拦住任何人**
        ……这条命令把『该等多久』变成『已经等过了』」。
        也就是说 `check()` 是**告示**，`--wait` 是**闸**。

        2026-08-21 加放慢时先只改了 `check()`，`--wait` 照旧按原速睡 ——
        放慢就成了只在嘴上说的。这条盯着两处用同一个倍数。

        **判据 2026-08-21 从「扫源码」换成「真跑一遍」。** 原来它 grep 源码里有没有
        `SLOW_GAP_FACTOR` 和 `lane_of(` 两个字符串 —— 两个都在，而放慢**根本没生效**：
        文档教的写法是 `--wait navigate --portal 猎聘`（裸平台名），
        `lane_of("猎聘")` 是 `cli`，于是那一支永远算不出 slow，照睡 8 秒。
        **字符串在、行为不在**，正是这个仓库反复在治的「空 glob 恒绿」同一个形状。
        """
        import contextlib
        import io
        import shutil
        import tempfile
        base = pb.gap_for("navigate")
        # **临时目录，绝不碰真实用户。** 同 `test_the_write_actually_lands.py`：
        # 真跑 `main()` 就得有个真的用户目录（`pick_user` 会校验它存在），
        # 而在真实 `users/` 下造一个，跑完忘了删就会绊倒
        # `test_no_maintainer_data_in_repo`（那条把 `users/` 下的目录名
        # 当成真人姓名扫全仓库）。2026-08-21 手工跑一次就踩到了。
        tmp = Path(tempfile.mkdtemp())
        user = "写盘判据"
        (tmp / "users" / user / "job_scraper").mkdir(parents=True)
        (tmp / ".active_user").write_text(user, encoding="utf-8")

        def said(portal: str) -> str:
            """跑真的 `--wait`，把它自己报的「要求间隔 N 秒」抓回来。

            不会真睡：`--wait` 只在「距上一个动作还不够久」时才 sleep，
            而这里一次动作都没记，`slept` 恒为 0，秒数照样打印出来。
            """
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                pb.main(["--wait", "navigate", "--portal", portal, "--user", user])
            return buf.getvalue()

        saved_root = pb.ROOT
        pb.ROOT = tmp
        try:
            data = {}
            # **用真实时钟，不是 `NOW`。** `main()` 内部取的是 `dt.datetime.now()`，
            # 而 `NOW` 是 2026-08-19 —— 按它记的冷却早就到期了，
            # 于是这条判据会「通过检查、什么也没测到」。
            pb.block(data, "liepin-search", "CLI 撞 RATE_LIMITED", dt.datetime.now())
            pb.save(user, data)
            for portal in ("猎聘", "liepin-browser"):
                with self.subTest(portal=portal):
                    out = said(portal)
                    self.assertIn(f"间隔 {base * pb.SLOW_GAP_FACTOR} 秒", out,
                                  f"--wait {portal} 睡的还是原速 —— "
                                  "放慢就成了只在嘴上说的")
                    self.assertIn("放慢", out, "没说为什么变慢，下一个人会以为工具卡了")
            # 对照：没撞限流的家照原速，别把所有人一起拖慢
            self.assertIn(f"间隔 {base} 秒", said("BOSS"), "没撞限流的家也被放慢了")
        finally:
            pb.ROOT = saved_root
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_slowdown_is_not_cosmetic(self):
        """放慢要**慢到改变密度剖面**，不是加几秒意思一下。

        08-19 那次升级是真的：象征性放慢等于把那条教训丢掉，
        而代价由用户的账号承担。

        ⚠️ **这条判据的底线在 2026-08-26 降了，要说清楚。** 原来放慢是两件事
        叠起来的：间隔 ×3 **加上**每轮上限 10→3，合计约 10 倍，所以钉的是
        「至少 5 倍」。那天删掉固定额度之后（本人裁定：额度该由平台判，
        我们只控间隔），放慢只剩间隔一项 —— **实际保护从约 10 倍降到 3 倍**。
        这不是判据放水，是被保护的量真的变小了；要补回来，
        唯一的旋钮是 `SLOW_GAP_FACTOR`。
        """
        self.assertGreaterEqual(
            pb.SLOW_GAP_FACTOR, 3,
            f"放慢只有 {pb.SLOW_GAP_FACTOR} 倍 —— 密度剖面没有实质变化，"
            "而 2026-08-19 的账号风控是拿真实代价换来的")

    def test_a_browser_block_does_not_stop_the_anonymous_cli(self):
        """反方向不成立：浏览器账号被标异常，**匿名的 CLI 照常能抓**。

        这一条 2026-08-21 之前是反的——`block()` 一律封整家，理由写着
        「CLI 和浏览器用的是同一个账号」。而 `liepin-search` 的两处 fetch
        都不发 `Cookie`/`Authorization`（见 `cli/src/helpers.ts`），它没有账号。
        代价是用户过一次短信验证，一个与那次验证毫无关系的匿名接口
        跟着停 24 小时。
        """
        data = {}
        pb.block(data, "liepin-browser", "账号异常，要短信验证", NOW)
        ok, why = pb.check(data, "liepin-search", NOW)
        self.assertTrue(ok, "浏览器的账号风控把匿名 CLI 一起拦下了：" + why)
        ok2, why2 = pb.check(data, "liepin-browser", NOW)
        self.assertFalse(ok2, "浏览器那条自己却没被拦住")
        self.assertIn("CLI", why2, "没告诉用户另一条还能用，他会以为整家停了")

    def test_the_anonymous_cli_really_sends_no_credentials(self):
        """上一条的**前提**：CLI 真的不带凭据。前提变了，那条规则就该跟着变。

        断言写在这里而不是只写在注释里，是因为它是可验证的事实：
        哪天 CLI 加上了登录态，这条会红，提醒下一个人重新想「分开封」还成不成立。
        """
        src = (ROOT / ".agents" / "skills" / "liepin-search" / "cli"
               / "src" / "helpers.ts")
        if not src.is_file():
            self.skipTest("liepin-search CLI 没装")
        t = src.read_text(encoding="utf-8")
        for cred in ("Cookie", "Authorization", "credentials:"):
            self.assertNotIn(
                cred, t,
                f"CLI 开始发 {cred} 了——它不再是匿名的，"
                "「浏览器被封不影响 CLI」这条规则要重新判")

    def test_reblocking_does_not_restart_the_clock(self):
        """已经停着的时候再撞一次，**起算时刻不变**，只更新原因。

        挡的是「手动重试」那个功能自带的陷阱：探失败时最顺手的动作是再
        `--block` 一次记一笔，而那会把起点推到现在 —— 屏幕上「已经封了
        16 小时」当场归零，读起来像刚发生的，用户以为自己刚把它撞封。

        2026-08-26 之前判的是「剩余时间不变」；封控不再自动到期之后，
        同一件事换个量表达：**已经封了多久要接着涨，不许归零**。
        """
        data = {}
        pb.block(data, "liepin-search", "第一次撞", NOW)
        later = NOW + dt.timedelta(hours=13)
        pb.block(data, "liepin-search", "探了一次，还在限流", later)
        st = pb.block_state(data, "猎聘", later)
        self.assertEqual(st["held_minutes"], 13 * 60,
                         "再 block 一次把起点推到了现在——「已经封了多久」被归零")
        self.assertEqual(st["why"], "探了一次，还在限流", "原因没跟着更新")

    def test_it_never_lets_go_on_its_own(self):
        """**过多久都不会自己解开。**（2026-08-26 本人裁定：
        「只有用户手动点继续 cli 后，才能继续 cli」。）

        这条取代的是原来那对：`test_cooldown_expires`（到点要自己解）和
        `test_a_fresh_block_after_the_cooldown_does_restart`（过完再撞算新事件）。
        两条都建立在「会过完」上，而那件事没有了。

        为什么归人：解封的前提是**外面那件事真的变了** —— 浏览器那条要他
        本人过完验证，CLI 那条要他换掉网络出口的 IP。工具看不见这两件事，
        按时间放行等于替他赌一把，而 08-24、08-25 连着赌输两次。
        """
        for h in (1, 25, 24 * 7):
            with self.subTest(hours=h):
                data = {}
                pb.block(data, "BOSS", "security_check", NOW)
                later = NOW + dt.timedelta(hours=h)
                self.assertFalse(pb.check(data, "BOSS", later)[0],
                                 f"{h} 小时后它自己解开了")
                self.assertEqual(pb.block_state(data, "BOSS", later)["held_minutes"],
                                 h * 60)
        # 只有人动手才解得开
        data = {}
        pb.block(data, "BOSS", "security_check", NOW)
        pb.clear(data, "BOSS", NOW + dt.timedelta(hours=1))
        self.assertTrue(pb.check(data, "BOSS", NOW + dt.timedelta(hours=1))[0],
                        "人点了「继续抓」还是解不开")

    def test_block_says_whether_it_actually_started_a_new_cooldown(self):
        """本来就停着时，**不许再说一句「刚停的」**。

        起算时刻并没有变（上一条守着），所以那句话是假的 —— 用户会以为
        是自己刚把它撞封的。这一条守的是**别说没做过的事**。

        原来第三段验的是「冷却过完之后再撞算新事件」。2026-08-26 起封控
        不会自己过完，那一段换成：**隔多久再撞都不是新事件**，
        因为中间没有任何东西解开过它。
        """
        data = {}
        _, _, fresh = pb.block(data, "liepin-search", "第一次撞", NOW)
        self.assertTrue(fresh, "第一次撞应当报「新封」")
        _, _, again = pb.block(data, "liepin-search", "又撞了", NOW + dt.timedelta(hours=1))
        self.assertFalse(again, "停着的时候再撞却报成了新封")
        after = NOW + dt.timedelta(days=30)
        _, _, third = pb.block(data, "liepin-search", "一个月后又撞", after)
        self.assertFalse(third, "中间没人解过，一个月后再撞也不是新事件")
        # 人解开之后再撞，才是新事件。
        pb.clear(data, "liepin-search", after)
        _, _, fourth = pb.block(data, "liepin-search", "解开之后又撞", after)
        self.assertTrue(fourth, "人解开之后再撞，那确实是新事件")

    def test_the_probe_gets_through_the_very_door_it_tests(self):
        """探恢复要穿过的，**正是它要测试的那道冷却门**。

        照常 `--check` 一律退出码 1，用户点名要的「CLI 手动重试」就永远够不着。
        所以 `probe=True` 免冷却 —— 但只免冷却。
        """
        data = {}
        pb.block(data, "liepin-search", "撞了限流", NOW)
        self.assertFalse(pb.check(data, "liepin-search", NOW)[0],
                         "普通检查居然放行了被封的通道")
        self.assertTrue(pb.check(data, "liepin-search", NOW, probe=True)[0],
                        "探测被它自己要测的那道门拦住了")

    def test_the_probe_is_not_a_skeleton_key(self):
        """三条焊死：**只免冷却、只对 CLI、不免密度。**

        开口一旦大过必要，下一个人就会拿它绕过整个闸门 ——
        而闸门守的是用户的账号。
        """
        # ① 不免密度：间隔照样拦
        #    （原来这一支拿日上限试，2026-08-26 那个上限删了；
        #     密度现在只剩间隔，所以试的是间隔 —— 守的还是同一件事。）
        data = {}
        pb.note(data, "liepin-search", 1, NOW, "navigate")
        ok, why = pb.check(data, "liepin-search",
                           NOW + dt.timedelta(seconds=1), probe=True)
        self.assertFalse(ok, "探测把动作间隔也绕过去了")
        self.assertIn("太密", why)

        # ② 只对 CLI：浏览器封的是账号，工具探不出来
        d2 = {}
        pb.block(d2, "liepin-browser", "要短信验证", NOW)
        self.assertFalse(pb.check(d2, "liepin-browser", NOW, probe=True)[0],
                         "给浏览器开了探测口——那条只有用户本人过得了验证")

        # ③ 只对有 CLI 的平台：BOSS 那三家没有第二条通道
        d3 = {}
        pb.block(d3, "BOSS", "security_check", NOW)
        self.assertFalse(pb.check(d3, "BOSS", NOW, probe=True)[0],
                         "BOSS 没有 CLI，却被探测口放行了")

    def test_it_does_not_claim_the_cli_is_fine_when_it_is_not(self):
        """浏览器被封时提一句「CLI 那条照常」很有用 —— **前提是它真的照常**。

        老格式迁移过来的记录两条通道都封（那时候的语义就是整家停），
        这句话会当场自相矛盾。实测在用户的真实数据上撞见过。
        """
        data = {}
        pb.block(data, "liepin-browser", "要短信验证", NOW)
        _, why = pb.check(data, "liepin-browser", NOW)
        self.assertIn("CLI", why, "CLI 明明能用，却没告诉用户")
        pb.block(data, "liepin-search", "也撞了限流", NOW)
        _, why2 = pb.check(data, "liepin-browser", NOW)
        self.assertNotIn("照常可以抓", why2,
                         "CLI 也封着，却还在说它照常——用户会去试一条走不通的路")

    def test_a_bare_platform_name_still_mentions_the_other_lane(self):
        """裸平台名落到主通道，**放行的只是那一条**。

        实测缺口：浏览器封着、CLI 正常时 `--check 猎聘` 回「可以」，
        照它去开浏览器就一头撞进验证页。放行照旧放行 ——
        但不许让它看起来像「整家都没事」。
        """
        data = {}
        pb.block(data, "liepin-browser", "要短信验证", NOW)
        ok, why = pb.check(data, "猎聘", NOW)
        self.assertTrue(ok, "CLI 是好的，不该拦住")
        self.assertIn("浏览器", why, "另一条封着却只字不提")
        # 点了名的渠道不必赘述——他已经说清要走哪条了。
        ok2, why2 = pb.check(data, "liepin-search", NOW)
        self.assertTrue(ok2)
        self.assertNotIn("注意", why2, "点名了还啰嗦一遍另一条")

    def test_docs_quote_the_real_numbers(self):
        """文档里写的额度**必须是代码里那个数**。

        2026-08-21 的更新日志里加过一条「账号安全有闸门」（那份文件后来删了，
        git 历史里还在），
        里面点名了四个数（每轮 10 次、每天 2 轮、冷却 24 小时、动作间隔 8/4/3 秒）。
        ⚠️ 前两个 **2026-08-26 已经删掉了**（本人裁定：额度该由平台判，我们只管
        间隔），现在的闸门只剩后两个 —— 上面那串是当时的现场，不是现行清单。
        这条守卫本身照常有效：它扫的是**文档里出现的数**与代码常量对不对得上，
        数少了一样得对得上。
        **那是要发出去的文件**，而它们和 `portal_budget.py` 的常量之间
        原来没有任何东西连着 —— 改一次常量，文档就开始静默说谎，
        而说的正是「会不会把你账号弄封」这件最要紧的事。

        **全量扫已跟踪的 md，不钉某一个文件**：今天写在这份文档里，
        明天可能被抄进另一份。固定名单的失效方式这个仓库见过太多次
        （`test_writes_are_atomic` 的注释里就记着一条）。
        """
        import subprocess
        r = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            self.skipTest("不是 git 仓库")
        docs = [ROOT / f for f in r.stdout.split("\n") if f.strip()]
        self.assertGreaterEqual(len(docs), 20, "扫不到 md —— 判据会恒绿")

        # (正文里的写法, 该是多少)。**只钉数字和它紧挨着的那几个字**，
        # 别把整句话写进来 —— 那是「断言绑死一种写法」。
        # 「每轮 ≤N 次动作」「每家每天 ≤N 轮」两条 2026-08-26 随固定额度删了。
        want = [(r"冷却\s*(\d+)\s*小时", pb.BLOCK_COOLDOWN_H),
                (r"导航\s*(\d+)\s*秒", pb.GAP_S["navigate"]),
                (r"取数\s*(\d+)\s*秒", pb.GAP_S["fetch"]),
                (r"点击\s*(\d+)\s*秒", pb.GAP_S["click"])]
        bad, seen = [], 0
        for p in docs:
            if not p.is_file():
                continue
            body = p.read_text(encoding="utf-8")
            for pat, real in want:
                for m in re.finditer(pat, body):
                    seen += 1
                    if int(m.group(1)) != real:
                        bad.append(f"{p.relative_to(ROOT).as_posix()}："
                                   f"写着 {m.group(1)}，代码里是 {real}")
        self.assertEqual(bad, [], "文档里的额度和代码对不上：\n  " + "\n  ".join(bad))
        self.assertGreater(seen, 0,
                           "一处都没扫到 —— 要么文档里不再写这些数（那这条判据该删），"
                           "要么写法变了、判据够不着了")

    def test_clearing_by_platform_name_really_unblocks_it(self):
        """点「我处理好了」之后**必须真的解开** —— 不管它内部分了几条通道。

        2026-08-21 通读 `check()` 时逮到的跨编辑缺陷（单看任何一次改动都看不出）：

        - `LANES` 是全局的，于是 BOSS / 智联 / 前程无忧凭空多出一条 `cli`；
        - 老格式迁移（`blocked_until` → 两条都封）把那条**不存在的通道**也标成封着；
        - `clear()` 给平台名时只解一条，而两条剩余时间相等时
          `block_state` 取的是 `LANES` 里排前面的 `cli`；
        - 于是解了那条不存在的，浏览器那条原样留着。

        **实测后果：用户在面板上点「我处理好了」，拿到成功回执，什么也没变。**
        面板刷新后告警条还在，而他已经真的去过完验证了。
        """
        for site in ("BOSS", "智联", "猎聘", "前程无忧"):
            with self.subTest(site=site):
                data = {site: {"actions": [], "rounds": [],
                               "blocked_until":
                                   (NOW + dt.timedelta(hours=10)).isoformat(),
                               "why": "要验证"}}
                self.assertFalse(pb.check(data, site, NOW)[0], "封了却没拦住")
                pb.clear(data, site, NOW)
                # **要查「一条都没剩」，不能只查 `check()`。**
                # 第一版就写成了 `check(site)`，而它给裸名时看的是**主通道** ——
                # 猎聘解了 CLI、浏览器还封着，它照样回 True。
                # 变异验证当场揭穿：把 `clear` 退回「只解一条」，套件全绿。
                st = pb.block_state(data, site, NOW)          # lane 留空 = 任意一条
                self.assertFalse(
                    st["blocked"],
                    f"点了「我处理好了」，{site} 的{st['lane']}那条还封着")
                self.assertTrue(pb.check(data, site, NOW)[0], f"{site} 还是抓不了")

    def test_clearing_does_not_wipe_a_verification_he_never_passed(self):
        """两条通道各因**不同的事**封着、而给的是平台名时：**一条都不解。**

        CLI 撞限流 + 浏览器要短信验证同时存在时，工具**不知道**用户刚才办的是
        哪一条。两个猜法都错过：

        - 「一起解」会把那个他根本没过的短信验证也解掉，等于替他假装做过；
        - 「解剩余时长最长的那条」= 解**最近封的那条**。这一版这条判据就是这么
          写的，而它和用户处理了哪条毫无关系 —— 顺序反过来就是解掉那个验证，
          把浏览器放回一条活的验证页。

        > **这条判据自己也曾经测不出对错**：它拿 `block_state(data, site)` 算出
        > `head`，再断言「留下的正好是除 head 之外的那条」—— 而 `clear()` 内部
        > 用的是同一个调用。两边同源，解掉哪一条它都绿。
        > 现在断言的是**结果**：两条都还在，且报出的是 `AMBIGUOUS`。

        > 这条和上一条（老格式要一起解）不矛盾，判据只有一个：
        > **它们是不是同一件事。** 老格式的两条是同一个事件迁移出来的
        > （`until` 与 `why` 相同）；两次独立事件不同。
        """
        data = {}
        pb.block(data, "liepin-search", "撞了限流", NOW)
        later = NOW + dt.timedelta(minutes=5)
        pb.block(data, "liepin-browser", "账号异常，要短信验证", later)
        now = later + dt.timedelta(minutes=1)

        site, lane, was = pb.clear(data, "猎聘", now)
        self.assertEqual(lane, pb.AMBIGUOUS, "给平台名时它还在猜解哪一条")
        self.assertFalse(was)
        still = [lg for lg in ("cli", "browser")
                 if pb.block_state(data, "猎聘", now, lg)["blocked"]]
        self.assertEqual(still, ["cli", "browser"],
                         "一条都不该解 —— 工具不知道他办的是哪一条")

        # 点名渠道名照样解得掉，而且只解那一条。
        for target, left in (("liepin-search", ["browser"]),
                             ("liepin-browser", [])):
            with self.subTest(target=target):
                _, lg, ok = pb.clear(data, target, now)
                self.assertTrue(ok, f"{target} 点名了还解不掉")
                self.assertEqual(
                    [x for x in ("cli", "browser")
                     if pb.block_state(data, "猎聘", now, x)["blocked"]], left)

    def test_clearing_an_unblocked_lane_does_not_claim_success(self):
        """解一条**本来就没封**的通道，不许报「已解除」。

        2026-08-21 通读时逮到：那个「原来真封着吗」的返回值查的是
        **这一家有没有被封**，而动作却是针对**某一条通道**的。
        两者不同的那一刻就说假话 —— 只有浏览器封着时 `--clear liepin-search`
        什么也没解，却打印「猎聘 的 CLI 冷却已解除」。

        用户照它去抓，撞的是那条根本没解开的路。
        """
        data = {}
        pb.block(data, "liepin-browser", "要短信验证", NOW)
        _, lane, was = pb.clear(data, "liepin-search", NOW)
        self.assertEqual(lane, "cli")
        self.assertFalse(was, "CLI 本来就没封，却报成「解除了」")
        self.assertTrue(pb.block_state(data, "猎聘", NOW)["blocked"],
                        "顺手把浏览器那条也解了")
        # 解对了那条才算数
        _, lane2, was2 = pb.clear(data, "liepin-browser", NOW)
        self.assertEqual(lane2, "browser")
        self.assertTrue(was2)
        self.assertFalse(pb.block_state(data, "猎聘", NOW)["blocked"])

    def test_a_site_without_a_cli_never_has_a_cli_lane(self):
        """没有 CLI 的平台不该凭空多出一条 CLI 通道 —— 上一条的根因。"""
        self.assertEqual(pb.lanes_of("猎聘"), pb.LANES)
        for site in ("BOSS", "智联", "前程无忧"):
            with self.subTest(site=site):
                self.assertEqual(pb.lanes_of(site), ("browser",),
                                 f"{site} 多出了一条它没有的通道")

    def test_clearing_by_channel_name_still_clears_only_that_one(self):
        """但**给渠道名时只解那一条**：两件事不能互相代表。

        「liepin-search 探通了」不等于「浏览器那个短信验证我过完了」——
        后者只有用户本人做得到，工具替他解等于假装他做过。
        """
        data = {}
        pb.block(data, "liepin-browser", "要短信验证", NOW)
        pb.block(data, "liepin-search", "撞了限流", NOW)
        pb.clear(data, "liepin-search", NOW)
        self.assertTrue(pb.check(data, "liepin-search", NOW)[0], "CLI 没解开")
        self.assertFalse(pb.check(data, "liepin-browser", NOW)[0],
                         "顺手把浏览器那条也解了——那个验证他还没过")

    def test_block_does_not_leak_to_other_sites(self):
        """猎聘被封不该连累 BOSS——它们是不同账号。"""
        data = {}
        pb.block(data, "猎聘", "账号异常", NOW)
        ok, _ = pb.check(data, "BOSS", NOW)
        assert ok, "封一家不该停全部，那会让整条流水线因为一家停摆"



class CeilingsAndGapsActuallyBite(unittest.TestCase):
    def test_there_is_no_invented_ceiling(self):
        """**没有次数上限**（2026-08-26 本人裁定）。

        原话：「你为什么直接限制了额度，没有固定额度的，你应该等撞到才算到了额度，
        我们当前应该是控制单渠道每次访问的间隙时间」。

        这条判据取代的是原来那两条（「动作到 10 就该停」「一天到 2 轮就该停」）。
        它盯的是**反方向**：别再有人把一个拍脑袋的数装回来。
        真正的额度由平台判 —— 撞到 `--block` 才算。
        """
        for name in ("ACTIONS_PER_ROUND", "SLOW_ACTIONS_PER_ROUND",
                     "ROUNDS_PER_DAY", "MIN_ROUND_GAP_S", "REQUESTS_PER_DAY"):
            self.assertFalse(hasattr(pb, name),
                             f"{name} 又回来了 —— 固定额度是被裁掉的那件事")

        # 隔够间隔就一直能跑：连发 200 次，只要每次都等够，一次都不该被拦。
        data, t = {}, NOW
        for i in range(200):
            ok, why = pb.check(data, "智联", t)
            self.assertTrue(ok, f"第 {i + 1} 次就被拦了，而它等够了间隔：{why}")
            pb.note(data, "智联", 1, t, "navigate")
            t += dt.timedelta(seconds=pb.gap_for("navigate"))

    def test_the_only_ceiling_is_the_platform_saying_stop(self):
        """撞到了才算到额度：`--block` 之后才停，之前一直放行。"""
        data = {}
        self.assertTrue(pb.check(data, "智联", NOW)[0])
        pb.block(data, "智联", "撞 security_check", NOW)
        ok, why = pb.check(data, "智联", NOW)
        self.assertFalse(ok, "平台已经说停了，闸门还放行")
        self.assertIn("停着", why)

    def test_an_old_action_does_not_hold_today_back(self):
        """很久以前的动作不该压住现在 —— 间隔看的是**上一次**，不是这辈子。"""
        data = {}
        pb.note(data, "前程无忧", 50, NOW - dt.timedelta(days=3))
        ok, _ = pb.check(data, "前程无忧", NOW)
        assert ok, "三天前的动作不该压住现在"

    def test_gaps_are_tiered_by_action_weight(self):
        """间隔按动作轻重分级——一个数套所有动作，两头都不对。

        2026-08-20 复盘当天实际用过的间隔：点卡片 1.8/2.2/2.0 秒（低于当时的 3 秒规则）、
        同源 fetch 3.2 秒（合规）、而 `browser_batch` 里两个 navigate **零间隔**
        ——正是 BOSS 返回 `_security_check` 的那一轮。
        一次整页加载和一次卡片点击差着一个数量级。
        """
        assert pb.gap_for("navigate") > pb.gap_for("fetch") > pb.gap_for("click")
        assert pb.gap_for("read") == 0, "纯读 DOM 不发请求，不该占间隔"
        # 认不出的按最重的算——猜错方向要往安全那边猜
        assert pb.gap_for("没见过的动作") == pb.MIN_ACTION_GAP_S == max(pb.GAP_S.values())

    def test_the_gate_uses_the_recorded_action_kind(self):
        """记了类型，下一次的间隔就按那个类型判——否则分级只是摆设。"""
        now = dt.datetime(2026, 8, 20, 12, 0, 0)
        data = {}
        pb.note(data, "BOSS", 1, now - dt.timedelta(seconds=5), kind="navigate")
        ok, why = pb.check(data, "BOSS", now)
        assert not ok and "navigate" in why, why      # 才过 5 秒，navigate 要 8 秒
        # 同样 5 秒，但上一个是 click（要 3 秒）就该放行
        data2 = {}
        pb.note(data2, "BOSS", 1, now - dt.timedelta(seconds=5), kind="click")
        assert pb.check(data2, "BOSS", now)[0]


# 原来这儿有个 `OpeningARoundDoesNotLockOutThatRound` 类，守的是
# 「`can_start_round` 与 `check` 必须分开」那次事故。2026-08-26 轮次这个概念
# 整个删了（没有固定额度就不需要「一轮」），两个函数一起没了，判据随之作废。
# 那次事故的教训本身没有丢：闸门不许把自己锁在外面 —— 同一形状的守卫现在是
# `test_recording_an_action_is_not_a_stop_sign.py`（记一笔账不许把自己劝退）。


class TheRuleIsWiredIntoTheTools(unittest.TestCase):
    def test_fetch_details_blocks_the_site_when_rate_limited(self):
        """CLI 撞限流必须落一笔冷却——只在进程里 break 挡不住下一条命令。"""
        src = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
        assert "portal_budget" in src, "fetch_details 没接额度闸门"
        head, _, tail = src.partition("if code in STOP_CODES:")
        assert tail, "撞限流的分支不见了"
        # 按行走到真正的 break 语句为止。不能 split("break")——注释里也会出现这个词
        # （现在那段注释就写着「光在这里 break 只挡住了本进程」），会提前截断。
        branch = []
        for line in tail.splitlines():
            if line.strip().startswith("break"):
                break
            branch.append(line)
        branch = chr(10).join(branch)
        assert ".block(" in branch, (
            "撞 RATE_LIMITED 只 break 不 block：本进程停了，"
            "下一条命令（或浏览器）照样走进去——那正是账号被标异常的路径")

    def test_the_numbers_live_in_exactly_one_place(self):
        """额度的数只许在 portal_budget.py 里定义，文档引用不重抄。"""
        src = (ROOT / "tools" / "portal_budget.py").read_text(encoding="utf-8")
        for name in ("MIN_ACTION_GAP_S", "GAP_LOOKBACK", "SLOW_GAP_FACTOR",
                     "BLOCK_COOLDOWN_H"):
            assert f"{name} = " in src, f"{name} 不在 portal_budget.py 里"
        scrape = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        assert "portal_budget.py" in scrape, "job-scrape 没写要过闸门，闸门就形同虚设"

    def test_wait_is_offered_because_check_does_not_block(self):
        """`--check` 只会说、不会拦，所以必须另有一条**真的睡够**的路。"""
        src = (ROOT / "tools" / "portal_budget.py").read_text(encoding="utf-8")
        assert "--wait" in src, "没有能真正过间隔的命令"
        assert "time.sleep" in src, "--wait 没有真的睡"


class TheDocsDoNotTeachTheWrongThing(unittest.TestCase):
    DOCS = ("workflows/job-auto.md", "workflows/reference/cdp-portals.md")

    def test_docs_no_longer_tell_you_to_switch_channels(self):
        """文档里不许再教「换同一家的另一条路」。

        引用它、讲它为什么错是允许的——那正是 job-auto.md 现在那段说明在做的事。
        所以只禁**祈使**写法：出现「先换同一家的另一条路」这个短语即失败。
        """
        for doc in self.DOCS:
            with self.subTest(doc=doc):
                # 引用块（以 > 开头的行）里允许出现——那是在讲这条规则为什么错。
                text = chr(10).join(
                    l for l in (ROOT / doc).read_text(encoding="utf-8").splitlines()
                    if not l.lstrip().startswith(">"))
                assert "先换同一家的另一条路" not in text, (
                    f"{doc} 又把 2026-08-19 上午那条写回去了——照它做会把软限流"
                    "升级成要用户过短信的账号风控")

    def test_batch_rule_is_documented(self):
        """`browser_batch` 零延迟这条此前完全没写过——它是最容易犯的。"""
        doc = (ROOT / "workflows" / "reference" / "cdp-portals.md").read_text(encoding="utf-8")
        assert "browser_batch" in doc, "没提 browser_batch 的零延迟问题"
        assert "不许放两个发请求的动作" in doc
        scrape = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        assert "--kind" in scrape, "抓取流程没让执行者记动作类型"
        assert "--wait" in scrape, "抓取流程没给出怎么真的过间隔"


if __name__ == "__main__":
    unittest.main()


class TheSlowdownNumberHasOneHome(unittest.TestCase):
    """降速档只有一个数，工作流里印的必须是它。

    2026-09-02 实测：`job-scrape.md` 里同一个档位写了**两个数** ——
    六处「间隔 ×3」（与 `SLOW_GAP_FACTOR = 3` 一致），另有两处原来写着「按 1/7 速率照跑」。
    `7` 在 `portal_budget.py` 里**查无出处**。

    代价落在最贵的那一格 —— 这是「刚被限流的那家还能跑多快」：
    读到 1/7 的人会把猎聘浏览器压到实际的 43%，而猎聘占这个库语料的 84%；
    反过来，若有人认定 1/7 才对，就会把另外六处写对的话当成错的去「订正」。

    同 `test_one_number_per_concept` 那一族：**一个概念一个数**。
    这里钉的是「工作流印的那个数 == 代码里的那个」。

    引用块不算 —— 记「原来错在哪」要引得出旧写法。
    """

    #: 「间隔 ×N」＝倍数；「1/N 速率」＝倒数。两种写法都要对上同一个 N。
    #:
    #: **倍数是个小整数。** `cdp-portals.md` 的 JS 片段里有
    #: `setTimeout(r, <该类型的间隔×1000>)` —— 那是秒转毫秒，不是降速档。
    #: 上界取 20：降速倍数不会是三位数，而秒转毫秒一定是。
    _GAP_MAX = 20
    _GAP = re.compile(r"间隔\s*×\s*(\d+)")
    _RATE = re.compile(r"1/(\d+)\s*速率")

    #: 说到「原来是这样、现在删了」的行不算违规 —— 记事要引得出旧写法。
    #: （`>` 引用块同理。）
    _HISTORY = re.compile(r"原来|曾经|删了|已删|不再|又回来|旧口径")

    def _lines(self):
        """**扫的不只是 workflows。**

        第一版只扫 `workflows/`，于是同一个过期的数在 `tools/` 与 `tests/` 里
        安然活着：2026-09-02 一并扫到四处现行断言 ——
        `fetch_details.py` 的注释、`test_an_ip_block_is_not_a_timer` 的模块说明、
        本文件顶上那张表、`test_portal_switch_is_read` 里那句
        原来那句「每轮上限降到 3（约 1/7 速率）」（**两个过期的数并排**）。

        更难堪的是最后两处：**守卫自己的说明在讲一件它另一条断言正禁止的事**
        —— `test_an_ip_block_is_not_a_timer` 里就有一条「每轮上限又回来了 ——
        固定额度是被裁掉的那件事」。
        """
        for base, pat in ((ROOT / "workflows", "**/*.md"),
                          (ROOT / "tools", "*.py"),
                          (ROOT / "tests", "test_*.py")):
            for p in sorted(base.glob(pat)):
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if line.lstrip().startswith(">") or self._HISTORY.search(line):
                        continue
                    yield p.name, i, line

    def test_the_scan_sees_the_number(self):
        """控制用例：工作流里确实印着这个数，否则下面两条对着空气跑。"""
        n = sum(1 for _, _, l in self._lines() if self._GAP.search(l))
        self.assertGreaterEqual(n, 3, f"只扫到 {n} 处「间隔 ×N」—— 判据八成失效了")

    def test_every_interval_factor_matches_the_code(self):
        bad = [f"{n}:{i} 写的是 ×{m.group(1)}"
               for n, i, l in self._lines()
               if (m := self._GAP.search(l))
               and int(m.group(1)) <= self._GAP_MAX
               and int(m.group(1)) != pb.SLOW_GAP_FACTOR]
        self.assertEqual(
            bad, [],
            f"这几处印的降速倍数与 `SLOW_GAP_FACTOR`（{pb.SLOW_GAP_FACTOR}）对不上：{bad}")

    def test_no_workflow_states_a_different_rate(self):
        bad = [f"{n}:{i} 写的是 1/{m.group(1)} 速率"
               for n, i, l in self._lines()
               if (m := self._RATE.search(l)) and int(m.group(1)) != pb.SLOW_GAP_FACTOR]
        self.assertEqual(
            bad, [],
            f"这几处拿「1/N 速率」说降速，而 N 与 `SLOW_GAP_FACTOR`"
            f"（{pb.SLOW_GAP_FACTOR}）对不上：{bad}")


class ABrokenBudgetFileFailsClosed(unittest.TestCase):
    """读不出来的额度文件不能变成「什么都没封」。"""

    def _with_user_file(self, raw: bytes):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        (root / "users" / "u" / "job_scraper").mkdir(parents=True)
        (root / "users" / "u" / "job_scraper" / "portal_budget.json").write_bytes(raw)
        old = pb.ROOT
        pb.ROOT = root
        self.addCleanup(setattr, pb, "ROOT", old)

    def test_a_bom_prefixed_budget_still_reads_its_cooldown(self):
        """记事本/PowerShell 存 UTF-8 会带 BOM；BOM 不该被当成坏文件。"""
        data = {"猎聘": {"blocks": {"cli": {
            "until": "2099-01-01T00:00:00", "since": "2026-10-24T12:00:00",
            "why": "测试封控"}}}}
        self._with_user_file(b"\xef\xbb\xbf" + json.dumps(
            data, ensure_ascii=False).encode("utf-8"))
        loaded = pb.load("u")
        self.assertTrue(
            pb.block_state(loaded, "liepin-search", NOW, lane="cli")["blocked"],
            "带 BOM 的额度文件被读成空的 —— 冷却被静默清掉了")

    def test_an_unreadable_file_blocks_every_site(self):
        """坏 JSON 不是「没封过」，而是「不知道封没封」——按封着算。"""
        self._with_user_file(b"{not json")
        loaded = pb.load("u")
        for site in pb.PORTALS:
            with self.subTest(site=site):
                self.assertTrue(
                    pb.block_state(loaded, site, NOW)["blocked"],
                    f"{site} 在坏额度文件上被判成了可以抓")

    def test_recording_a_hit_on_a_corrupt_lane_does_not_crash(self):
        """撞限流后要记账，而一条坏掉的 lane 记录不该把这条路炸掉。"""
        data = {"猎聘": {"blocks": {"cli": "oops"}}}
        pb.block(data, "liepin-search", "撞了限流", NOW)
        self.assertTrue(
            pb.block_state(data, "liepin-search", NOW, lane="cli")["blocked"],
            "坏记录被撞了一次之后没有变成有效的封控记录")
