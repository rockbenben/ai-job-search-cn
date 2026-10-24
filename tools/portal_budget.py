#!/usr/bin/env python3
"""每家招聘网站的动作额度与风控冷却。**账号是用户的，封号后果他担，所以限制要有数。**

## 为什么要它

`cdp-portals.md` 的账号安全铁律原来只有三个形容词——「低频」「不批量」「撞验证码即停手」。
形容词拦不住任何人：2026-08-19 当天，执行者在**一次** `/job-auto` 里做完
1 次搜索 + 15 张卡提取 + 3 次详情页 fetch + 11 次卡片点击（约 10 分钟），
BOSS 就返回了 `_security_check` 重定向；同一天猎聘直接把账号标成
「行为异常」，要短信验证才能继续。**两家都不是被单次动作打掉的，是被密度打掉的。**

而密度这件事执行者自己数不清——他没有跨轮次、跨命令的记忆。所以固化在这里，
和 `fetch_details.py` 的「撞限流就停」同一个道理：**安全机制不能靠每次现写。**

## 当天实测出来的两条，都推翻了原来的写法

**① 撞限流之后换同一家的另一条通道，是把软限流升级成账号级风控。**
`job-auto.md` 原来写「猎聘 CLI 撞限流时，浏览器搜索页照常可用且容量更大」——
2026-08-19 照做的结果：CLI 报 `RATE_LIMITED` 之后开浏览器搜索页，当场跳
安全中心要短信验证。**撞了限流就别再碰这家**，换通道只会把软限流升级成硬风控。

> **但当时给的理由是错的，2026-08-21 核实后改了。** 原话是「CLI 和浏览器用的是
> 同一个账号」——`liepin-search` 的请求头里**没有 `Cookie`、没有 `Authorization`**
> （`cli/src/helpers.ts` 两处 fetch 都可查），它是全匿名的，压根没有账号。
> 真正共用的是 **IP**，那是弱得多的一层耦合。
>
> 按错理由封出来的范围也就错了：**用户在浏览器里被要求短信验证，不该让一个
> 匿名接口跟着停 24 小时。** 现在按通道分开判，形状是**不对称**的 ——

| 谁撞上 | 另一条 | 为什么 |
|---|---|---|
| **CLI 撞限流** | 浏览器**放慢，不停** | 同一家、同一个网络出口；按原速换通道就是上面那次教训。2026-08-21 用户裁定：浏览器是刻意的、人在场的访问，为 CLI 的限流停它一天代价太大，改成加大间隔 |
| **浏览器撞风控** | CLI **照常** | 匿名接口与那个账号无关；封的是账号，不是 IP |

解封也分开：浏览器那条只有用户本人过得了验证（`--clear liepin-browser`）；
CLI 那条是**探一次就知道**的，走 `/job-scrape health liepin-search`，
通了就 `--clear liepin-search`。**密度不分通道**——共用 IP 是真的，间隔按整家算（见下一节）。

## 密度只由一件事管：**两次动作之间的间隔**（2026-08-26 本人裁定）

原话：「你为什么直接限制了额度，没有固定额度的，你应该等撞到才算到了额度，
我们当前应该是控制单渠道每次访问的间隙时间」。

删掉的是四个**我们自己拍出来的**数：每轮 10 次动作、每天 2 轮、轮间隔 10 分、
每天 60 次请求。没有一个来自平台，全是拿某次实测值打三折得来的；而它们既没
拦住 2026-08-24、08-25 那两次 IP 封禁，又在天天把还通着的渠道劝停。

留下的是三件真东西：

- **动作间隔**（`GAP_S`，按动作轻重分级）—— 现在是唯一的密度闸门；
- **撞上了才算**：真撞了风控才 `--block`，那条通道进冷却
  （`BLOCK_COOLDOWN_H`）。额度是被平台判出来的，不是我们预支的；
- **一条封着、同一家另一条放慢**（`SLOW_GAP_FACTOR`）—— 现在只剩间隔 ×3
  这一种表现，因为没有别的数可降了。

> **一条反证要留着，别当它不存在。** 2026-08-17 那天发了 1032 次请求
> （搜索 106 + 详情 926），当场没有任何报错，**两天后**才以「您的 IP 被拦截」
> 的形式结账。也就是说这家平台并不快速失败 —— 「等撞到才算」在它身上会
> 晚两天撞到。日请求数因此仍然记着、也照常打印（`今天已发 N 次`），
> 但它是**给人看的读数，不是闸门**：真要收紧，收紧的应该是间隔。

### ⚠️ CLI 那条的限流是 **IP 级**的，等不掉（2026-08-26 本人指出）

原话：「猎聘 cli 封 ip 了，需要手动更换 ip 而不是等冷却。在停止时间使用
猎聘浏览器获取」。

冷却计时照常走 —— 它挡的是「别再往同一个出口上撞」，这一点没变。变的是
**剩余时间不是解法**：到点换的还是同一个 IP，探一次限一次，然后再封一天，
如此循环。实测活动用户 2026-08-24 起的两天，各撞一次、各封一天，第二次是
冷却刚过就撞的；封着那半天猎聘浏览器搜一页 **40 张卡、新增 36 个**，
另外三家合计才 50 个。

所以这条路上只有两个动作，与钟表无关：

1. **换 IP**（换网络出口 / 重拨 / 换热点），然后 `--clear liepin-search`
   或跑一次 `/job-scrape health liepin-search` 探通了再解；
2. **这段时间走浏览器那条** —— 它是**该走的那条**，不是备胎。放慢照旧
   （间隔 ×3，取值只有一处：`SLOW_GAP_FACTOR`），但放慢不等于不走。

**② BOSS 详情页不能用同源 `fetch()` 批量取。**
`cdp-portals.md` 原来推荐这么做。当天实测：`fetch('/job_detail/<id>.html')` 返回的是
「请稍候 - BOSS直聘」拦截页（41KB，`job-sec` 一个字都没有），紧接着整页就被
`_security_check` 重定向。改用搜索页点卡片、读右栏——那是人本来就会做的动作，
不额外发详情页请求。

## 数是怎么来的

**间隔不是拍的，是拿当天的触发值倒推的。** BOSS 约 30 次页面动作触发
`_security_check` —— 当时据此配过一条「每轮上限 10」，2026-08-26 随固定额度
一起删了（本人裁定：额度该由平台判，我们只控间隔）。**现在只剩间隔**：
`GAP_S` 按动作类型给，CLI 停着时浏览器那条乘 `SLOW_GAP_FACTOR`。
这是**安全边距不是实测阈值**——真实阈值只有平台知道，而且会变；
宁可慢，不要再让用户去过一次短信验证。

> ⚠️ **这一段原来还在解释「所以每轮上限取 10」，而那个旋钮已经不存在了**
> （删除记在 `SLOW_GAP_FACTOR` 上面那条注释里）。一段**讲理由的文字**
> 活得比它解释的那个东西久，比一个过期的数更难发现：读的人会照着它
> 去找那个上限，找不到就以为是自己漏看了。

## 用法

    python tools/portal_budget.py                    # 看各家还剩多少额度
    python tools/portal_budget.py --check BOSS       # 现在能不能动这家（退出码 0/1）
    python tools/portal_budget.py --wait navigate --portal BOSS  # 睡够间隔再动手
    python tools/portal_budget.py --note BOSS -n 5   # 记 5 次页面动作
    python tools/portal_budget.py --block 猎聘 --why "账号异常，要短信验证"
    python tools/portal_budget.py --clear 猎聘        # 用户说他处理完了，解冷却

**封控按通道，额度按整家。** 给渠道名就只动那条通道，给平台名落到它的主通道：

    python tools/portal_budget.py --block liepin-browser --why "要短信验证"
    python tools/portal_budget.py --clear liepin-search   # 探通了再解这条

`--block` 默认落到该平台的**主通道**（猎聘是 CLI，其余三家只有浏览器一条）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
from query_yield import PORTAL_ALIAS, PORTALS  # noqa: E402

#: 两次动作之间至少隔多少秒——**按动作的轻重分级**。
#:
#: 原来只有一个 3 秒，套在所有动作上。2026-08-20 复盘发现两头都不对：
#: 一次 `navigate` 是**整页加载**（带登录态 Cookie、拉几十个子资源），
#: 和「在已加载的页面上点一张卡」根本不是一个量级；而实际跑的时候，
#: 点卡片用了 1.8-2.2 秒（低于 3 秒）、`browser_batch` 里连着两个 navigate
#: **零间隔**——正是当天 BOSS 返回 `_security_check` 的那一轮。
#:
#: 分级之后：重动作给足，轻动作不必陪绑。
GAP_S = {
    "navigate": 8,    # 整页加载：新 URL、翻页、跳详情页
    "fetch": 4,       # 同源 fetch 详情：一个请求，但确实发出去了
    "click": 3,       # 在已加载页面上点卡片、展开：只触发局部 XHR
    "read": 0,        # 纯读 DOM / 截图：**不发请求**，不占间隔也不占额度
}
#: 认不出的动作名按最重的算——猜错方向要往安全那边猜。
MIN_ACTION_GAP_S = max(GAP_S.values())
#: 算间隔时往回看多久。**比「今天零点起」可靠**：零点那版在 00:00:05
#: 会看不见 23:59 的动作，于是仅剩的这道门在半夜自动失效。
#: 1 小时对 8-24 秒的间隔绰绰有余，`check()` 和 `--wait` 共用这一个。
GAP_LOOKBACK = dt.timedelta(hours=1)


def gap_for(kind: str) -> int:
    """这种动作之后至少要等几秒。认不出的按最重的算。"""
    return GAP_S.get((kind or "").strip().lower(), MIN_ACTION_GAP_S)
#: 撞了风控之后冷却多久。跨一整天，让平台的滑动窗口走完。
BLOCK_COOLDOWN_H = 24
#: 曾经有过一个「每家每天 60 次请求」的硬上限，2026-08-26 删掉了
#: （见模块开头「密度只由一件事管」）。**那次实测数据留在这儿当证据**，
#: 因为它说的事情没被推翻 —— 只是不再当闸门用：
#:
#:     08-11   181 次（搜索 19 + 详情 162）   没事
#:     08-12    14 次                        没事
#:     08-13     8 次                        没事
#:     08-17  1032 次（搜索 106 + 详情 926） ← 雷
#:     08-19   164 次 + 浏览器动作            限流 → 账号异常 → **IP 被封**
#:
#: 08-17 那 1032 次当场没报错，**两天后**才以「您的 IP 被拦截」结账。
#: 所以「等撞到才算」在这家平台上会晚两天撞到 —— 真要收紧，
#: 收紧的是 `GAP_S` 的间隔，不是再拍一个日上限出来。


def site_of(portal: str) -> str:
    """任何渠道名归到它所属的**平台**。**密度额度**按平台算——共用的是 IP。"""
    p = (portal or "").strip()
    return PORTAL_ALIAS.get(p, p)


#: 免登录、不带任何凭据的渠道名。**判据是请求里有没有账号**，不是名字里有没有
#: 「CLI」：`liepin-search` 的两处 fetch 都不发 `Cookie`/`Authorization`
#: （`.agents/skills/liepin-search/cli/src/helpers.ts`）。
#:
#: **名字必须是 `PORTAL_ALIAS` 认得的那些。** 这里原来还列了 `猎聘CLI`
#: 与 `猎聘 CLI`——而 `PORTAL_ALIAS` 里没有这两个键，于是 `site_of` 把它们
#: 原样返回，`--block 猎聘CLI` 在额度文件里开出一行叫「猎聘CLI」的**幽灵**：
#: `status_lines` 按 `PORTALS` 遍历、面板按平台遍历，谁也看不见它，
#: 而真正的猎聘一点没被封。命令行还会照常打印「已进冷却 24 小时」。
#: 列一个到不了的名字，比不列更坏——它看起来像是支持的。
CLI_CHANNELS = {"liepin-search", "liepin"}

#: 每家的**主通道**——没点名渠道时落到这条。猎聘默认走 CLI
#: （`job-scrape.md` Step 0.44），其余三家只有浏览器一条路。
PRIMARY_LANE = {"猎聘": "cli"}

LANES = ("cli", "browser")

#: CLI 在冷却里时，**浏览器那条放慢，不停**。
#:
#: 原来是硬停：CLI 撞限流 → 浏览器一起停 24 小时。依据是 2026-08-19 那次实测
#: （CLI 报 `RATE_LIMITED` 之后立刻开浏览器搜索页，安全中心当场要短信验证）。
#:
#: 用户 2026-08-21 裁定改成放慢，理由是**两条通道的访问性质不同**：
#: 「浏览器其实是刻意访问的，要不 cli 封的时候，浏览器加大访问间隙」——
#: 它用的是他自己已登录的 Chrome，一次开一个页面、人在场；
#: 而 CLI 是自动批量请求。为后者的限流把前者整整停一天，代价是整条渠道。
#:
#: **但那次升级是真的**，所以「放慢」要慢到真的改变密度剖面，不是象征性加几秒：
#: 间隔 ×3（导航 8→24 秒）。
#:
#: 原来还配了一条「每轮上限 10→3」，2026-08-26 随固定额度一起删了。
#: 放慢现在只剩间隔这一种表现 —— 那也正是本人当时要的那件事：
#: 「cli 封的时候，浏览器加大访问间隙」。
SLOW_GAP_FACTOR = 3


def lanes_of(site: str) -> tuple:
    """**这家真有的通道。** BOSS / 智联 / 前程无忧只有浏览器一条。

    全局那个 `LANES` 会让它们凭空多出一条 `cli` —— 老格式迁移
    （`blocked_until` → 两条通道都封）当场把这条不存在的通道也标成封着，
    于是 `--clear BOSS` 去解那条不存在的，浏览器那条原样留着。
    实测后果：用户在面板上点「我处理好了」，拿到成功回执，**什么也没变**。
    """
    return LANES if PRIMARY_LANE.get(site) == "cli" else ("browser",)

#: (平台, 通道) → **该敲的那个渠道名**。提示里要给真名，「具体渠道名」等于没说
#: （「面板每处引导都要写出命令」，终端里同理）。只有猎聘有两条通道，
#: 其余三家用平台名就够——所以这张表只有两行，不是漏了。
CHANNEL_NAME = {("猎聘", "cli"): "liepin-search",
                ("猎聘", "browser"): "liepin-browser"}


def known_channel(name: str) -> bool:
    """这个名字真有这么一条渠道 / 一家平台吗。

    合法的只有两类：`PORTALS` 里的裸平台名，和 `PORTAL_ALIAS` 收的渠道名
    （`liepin-search` / `liepin-browser` / `boss-browser` / …）。
    """
    n = (name or "").strip()
    return bool(n) and (n in PORTALS or n in PORTAL_ALIAS)


def unknown_channel_note(flag: str, name: str) -> str:
    """名字不认识时说什么。**别猜，把认得的都列出来。**"""
    names = sorted(set(PORTALS) | set(PORTAL_ALIAS))
    return (f"没有叫「{name}」的渠道，{flag} 这一下什么也没做。"
            f"{chr(10)}认得的名字：{'、'.join(names)}"
            f"{chr(10)}拿不准这一轮该跑哪几条就先跑："
            f"{chr(10)}    python tools/portal_budget.py --round")


def lane_of(portal: str) -> str:
    """这个渠道名属于哪条通道。**封控按通道分，因为凭据不是同一个。**

    没点名渠道（只给了平台名）时落到该平台的主通道 —— 用户没说走哪条，
    就按他平常会走的那条算。
    """
    p = (portal or "").strip()
    if p in CLI_CHANNELS:
        return "cli"
    if p in PORTALS:                    # **裸平台名**才落到主通道
        return PRIMARY_LANE.get(p, "browser")
    return "browser"                    # 点了名的渠道（liepin-browser 等）


def path_for(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / "portal_budget.json"


#: 整份额度文件读不出来时给用户的话。和单条 `blocks` 坏掉时的 `UNREADABLE_WHY`
#: 同一个方向：**读不出来 ≠ 没封过**。
UNREADABLE_BUDGET_WHY = (
    "额度文件读不出来（被改坏，或不是这个版本写的）。保守起见按四家都封着算；"
    "确认平台没问题就在总览页点「继续抓」，或跑 "
    "python tools/portal_budget.py --clear <渠道名>"
    "（<渠道名> 换成告警条上那一条），也可以先备份再修文件")


def _unreadable_budget() -> dict:
    """整份额度文件坏了时的替身：**每家、每条通道都按封着算**。

    原来 `load()` 遇到坏 JSON 返回 `{}`，而 `{}` 在这个数据模型里的意思是
    「一条冷却都没有」——一个手改坏的文件把风控静默清零。这个替身让所有
    读侧（`check` / 面板 / 合规检查）都走「保守拒绝」，用户能看见、
    也能用 `--clear` 自己解。
    """
    now = dt.datetime.now().isoformat(timespec="seconds")
    until = "9999-12-31T23:59:59"
    return {
        site: {"blocks": {
            lane: {"until": until, "since": now, "why": UNREADABLE_BUDGET_WHY,
                   "where": ""}
            for lane in lanes_of(site)}}
        for site in PORTALS
    }


#: 额度文件不存在时的版本戳。**不能用 `None`** —— `atomic_write` 把 `None`
#: 读作「不比对」，于是「读的时候还没有文件、写的时候别人刚建了一份」
#: 会变成静默覆盖。真实文件的 mtime_ns 不会是 0，这个值撞不上任何存量版本。
NO_FILE = (0, 0)


def load_stamped(user: str) -> tuple[dict, tuple]:
    """读额度，连同版本戳 —— 与 `save(..., expect=...)` 配对。

    **额度也是会被两个进程同时读改的。** 实测的路径：
    `fetch_details` 一次补几十份 JD，开跑读一次、每抓一份记一次；
    而总览页上的「继续抓」（`serve.apply_unblock`）随时可能在中间落一次盘。
    没有这道保险时，长跑那一侧手里的旧快照会把用户刚解开的冷却
    **原样盖回封着**，两边都不报错。

    读不出来时仍按「四家都封着」返回（见 `_unreadable_budget`），
    但带着**真实的戳**：调用方据此仍然可以解封/修复这份文件，
    同时不会把别人刚修好的版本盖掉。

    先取戳再读内容，顺序与 `_cli.load_json_stamped` 一致 —— 反过来会拿到
    「旧内容配新戳」，写回时比对通过，正好静默盖掉别人那一笔。
    """
    p = path_for(user)
    if not p.is_file():
        return {}, NO_FILE
    stamp = NO_FILE
    try:
        stamp = _cli._stamp_of(p)
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        # 取戳与读取之间被删了：按「读不出来」处理，别把 FileNotFoundError
        # 漏给调用方。戳用 NO_FILE，写回时若文件又出现会撞 StaleWrite。
        return _unreadable_budget(), stamp
    if not isinstance(data, dict):
        return _unreadable_budget(), stamp
    return data, stamp


def load(user: str) -> dict:
    return load_stamped(user)[0]


def save(user: str, data: dict, *, expect: tuple | None = None) -> tuple:
    """**不给不存在的用户凭空造目录。**

    `users/<名>/` 只能由 `/job-setup` 建。走到这里时它必然已经存在——额度是
    抓取途中记的账，而抓取的第一步就是 `_cli.pick_user`，用户不在它就退出了。
    所以「目录不存在」只有一个解释：名字是假的（打错，或者测试里的假名）。

    原来这里 `mkdir(parents=True)` 一路补齐，于是假名字当场变成一个真目录。
    实测代价（2026-08-19）：一次测试跑出一个 `users/张三/`，里面躺着一条
    `blocked_until`；**下一次跑测试时冷却还在，13 个 URL 一个都没发出去**，
    四个测试集体变红而代码没动过。当时的修法是给 `fetch_details.run` 加个
    `budget` 注入口——那修的是**那一个调用方**，`save` 本身照旧能造目录，
    下一个忘了注入的调用方会再来一遍。这里补的是根：造不出来就报错。

    留下的痕迹到 2026-08-24 还在：`users/张三/`（只有这一个额度文件）和
    `users/谁/`（连文件都没有）。终端把它们当成可切换的用户报了五天。

    `expect` 传 `load_stamped` 给的戳时，别人先写过就抛 `_cli.StaleWrite`，
    **不写**。返回写完之后的新戳：连记几笔的调用方（`fetch_details` 每发一个
    请求记一笔）拿它接着用，不必重读一遍。
    """
    p = path_for(user)
    if not p.parent.parent.is_dir():
        raise FileNotFoundError(
            f"没有 users/{user}/ 这个用户 —— 额度不该给一个不存在的人记账。"
            f"（测试里想跳过写盘就传 budget= 进去，别用假名字）")
    p.parent.mkdir(parents=True, exist_ok=True)
    # 用 `atomic_write` 返回的戳（替换前在临时文件上取的），不要替换后再 stat：
    # 那样会把「替换之后又被别人写了一次」的版本当成自己的基线。
    return _cli.atomic_write(p, json.dumps(data, ensure_ascii=False, indent=1),
                             expect=expect)


def _row(data: dict, site: str) -> dict:
    return data.setdefault(
        site, {"actions": [], "blocked_until": "", "why": ""})


def _blocks(row: dict, site: str = "") -> dict:
    """这一家各通道的封控记录。**老格式当成「两条都封」读**。

    `blocked_until` 在 2026-08-21 之前是整家一个字段。存量文件里还留着它，
    而那时候的语义确实是两条通道一起停 —— 照原样迁移，不要因为换了结构
    就把一条真实的冷却记录读丢。
    """
    if not isinstance(row, dict):
        # 整行不是字典（`{"猎聘": "oops"}`）。下面每个 `row.get` 都会抛
        # AttributeError，而这个函数在每次 `--check` 和每次面板导出的路径上。
        # 读不出来 ≠ 没封过 —— 交给 `_one_lane` 按「封着」算。
        return {lane: row for lane in (lanes_of(site) if site else LANES)}
    b = row.get("blocks")
    if isinstance(b, dict):
        return b
    if b is not None:
        # **`blocks` 在、却不是字典。** 这不是「没封过」，是「封控记录读不出来」。
        # 原来这里直接落到下面的老格式分支，`legacy` 为空就返回 `{}` ——
        # 于是 `'oops'` / `['a']` / `5` 一律变成「这家没被封」，
        # 一个手改坏的额度文件把**所有**风控冷却静默清零，
        # 下一次 `/job-auto` 直接走回那个刚要过短信验证的站。
        # 原样传给 `_one_lane`，由它统一按「读不出来 = 封着」处理。
        return {lane: b for lane in (lanes_of(site) if site else LANES)}
    legacy = row.get("blocked_until") or ""
    one = {"until": legacy, "why": row.get("why") or "",
           "where": row.get("where") or ""}
    # 迁移时也只给这家真有的通道 —— 见 `lanes_of` 的说明。
    lanes = lanes_of(site) if site else LANES
    # **`where` 只跟着浏览器那条走**，和 `block()` 同一条规矩：CLI 撞的是限流，
    # 没有页面可去、也没有验证可过。老记录里的那个地址迁过来时若也贴到 CLI 上，
    # 面板就会给限流那一行配一个「去处理」——用户点开一个什么也做不了的页面，
    # 然后以为自己漏了一步。（`test_a_rate_limited_cli_gets_no_fake_link` 守的是
    # 新写入的那条路，迁移这条当时没跟上。）
    return {lane: dict(one, **({} if lane == "browser" else {"where": ""}))
            for lane in lanes} if legacy else {}


def _since(stamps, floor: dt.datetime) -> list:
    out = []
    for s in stamps or []:
        try:
            t = dt.datetime.fromisoformat(s)
        except (TypeError, ValueError):
            continue
        if t >= floor:
            out.append(t)
    return out


#: `held_minutes` 是**已经封了多久**，不是「还剩多久」。
#: 2026-08-26 本人裁定封控不再自动到期（见 `_one_lane`），倒计时那个数
#: 从此没有意义 —— 留着它只会让人接着等。
NOT_BLOCKED = {"blocked": False, "why": "", "held_minutes": 0,
               "where": "", "lane": "", "until": ""}


#: 记录在、却读不出来时说的话。**结尾要给出路** —— 否则用户被一个
#: 他看不懂也解不掉的状态锁住，只能去手改 JSON。
UNREADABLE_WHY = ("这一条的冷却记录读不出来（额度文件被改坏或是别的版本写的）。"
                  "保守起见按封着算；确认没问题就跑 --clear <渠道名> 解掉")


def _one_lane(rec, lane: str, now: dt.datetime) -> dict:
    """单条通道的冷却状态。

    ## 没有记录 = 没封过；有记录但读不出来 = **按封着算**

    这两件事原来混在一起，都返回「没被封」，理由写的是「误报会让用户去过一次
    根本不需要的验证」。**那个理由只对前一半成立。** 一条记录存在，就说明
    某一刻真的有人写下过一次封控；把它读成「没封」是在丢一条安全记录，
    而这个模块存在的全部理由就是不丢它。

    两边的代价不对称：
    - 误判「封着」→ 用户多等，或者跑一次 `--clear`。有出路。
    - 误判「没封」→ 下一次 `/job-auto` 走回那个刚要短信验证的站，账号升级。**没有出路。**

    实测（2026-08-21）`blocks` 被写成 `'oops'` / `['a']` / `None` / `5` 四种形状时，
    `check()` 一律返回「可以抓」—— 一个手改坏的文件把所有冷却静默清零。

    **带时区的时间戳能读就读**，不要因为它带了 `+08:00` 就整条丢掉：
    `fromisoformat` 解得开，接着和 naive 的 `now` 比较才抛
    `can't compare offset-naive and offset-aware`，而那一抛就是每个 `--check`
    和整个面板导出一起崩。转成本地时间再比。
    """
    if not rec:
        return dict(NOT_BLOCKED)          # 没有记录：这条通道没被封过
    if not isinstance(rec, dict):
        return {"blocked": True, "why": UNREADABLE_WHY, "held_minutes": 0,
                "where": "", "lane": lane, "until": ""}
    try:
        t = dt.datetime.fromisoformat(rec.get("until") or "")
    except (TypeError, ValueError):
        return {"blocked": True, "why": rec.get("why") or UNREADABLE_WHY,
                "held_minutes": 0, "where": rec.get("where") or "",
                "lane": lane, "until": ""}
    if t.tzinfo is not None:              # 带时区：折算成本地时间，别丢掉这条记录
        t = t.astimezone().replace(tzinfo=None)
    # **不会自己解开。** 这里原来是 `if now >= t: return NOT_BLOCKED` ——
    # 到点自动放行。2026-08-26 本人裁定删掉：「cli 被封后……只有用户手动点
    # 继续 cli 后，才能继续 cli」。
    #
    # 这条本来就该是这样，模块里一直有人这么写、只是没人接上：
    # `serve.apply_unblock` 的说明第一行是「**只由人点，工具永远不自动解**」，
    # 引的是 2026-08-19 的裁定「显示封了的时候就应该停止 24 小时，
    # 除非手动点击解封」。**说明和代码反了整整一周**，而两边各有一条测试，
    # 所以它两边全绿地活了下来（`test_the_footnote_says_the_block_cleared`
    # 那个类名当时是往错的那边改的）。
    #
    # 为什么归人：解封的前提是**外面那件事真的变了** —— 浏览器那条要他本人
    # 过完短信/滑块，CLI 那条要他换掉这个网络出口的 IP（08-26 实测：等到点
    # 换的还是同一个 IP，探一次限一次）。这两件事工具都看不见。
    #
    # `t` 仍然记着（它是「撞上那一刻 + 标称时长」），但只用来算**已经封了多久**。
    # **存量记录按写它时的规矩算。** 2026-08-26 之前写下的记录没有 `since`，
    # 而它们是在「满 24 小时自动放行」的语义下写的 —— 到点那一刻它们**已经** 
    # 放行过了。改成永不到期之后若一视同仁，等于把历史改写：
    # 实测当天，一条 161 小时前的 BOSS 记录当场把 BOSS 整家判停，
    # 而同一天我刚用浏览器读完它 6 个职位页 —— 那条早就不成立了。
    #
    # 判据是 `since` 在不在：没有 = 老记录，照老规矩到点即释放；
    # 有 = 新记录，只有人能放行。
    if not rec.get("since") and now >= t:
        return dict(NOT_BLOCKED)

    # 撞上的时刻优先读 `since`。**别拿 `until - BLOCK_COOLDOWN_H` 倒推** ——
    # 那把「封了多久」和一个可调常量绑死了：改一次冷却时长，所有历史记录的
    # 起点跟着漂。存量记录没有 `since`，才退回倒推（那时它确实是这么算出来的）。
    try:
        since = dt.datetime.fromisoformat(rec.get("since") or "")
        if since.tzinfo is not None:
            since = since.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        since = t - dt.timedelta(hours=BLOCK_COOLDOWN_H)
    held = int((now - since).total_seconds() // 60)
    return {"blocked": True, "why": rec.get("why") or "撞过风控",
            "held_minutes": max(0, held),
            "where": rec.get("where") or "", "lane": lane,
            "until": t.isoformat(timespec="minutes")}


def _log(row: dict, lane: str, act: str, now: dt.datetime, why: str = "") -> None:
    """记一笔封控事件。**挂在行上，不挂在 `blocks[lane]` 里** ——
    后者一解封就整条弹掉，而这份流水存在的理由正是「解过之后又撞上」。
    """
    log = row.setdefault("block_log", {}).setdefault(lane, [])
    log.append({"at": now.isoformat(timespec="seconds"), "act": act,
                **({"why": why} if why else {})})
    row["block_log"][lane] = log[-40:]


def block_log(data: dict, portal: str, lane: str = "") -> list:
    """这条通道撞过/被放行过几次，按时间正序。读不出来就当没有。"""
    row = data.get(site_of(portal))
    if not isinstance(row, dict):
        return []
    log = row.get("block_log")
    if not isinstance(log, dict):
        return []
    out = log.get(lane or lane_of(portal))
    return [e for e in out if isinstance(e, dict)] if isinstance(out, list) else []


def streak_note(data: dict, portal: str, lane: str, now: dt.datetime) -> str:
    """「这条其实已经烂了好几天」那句话。**没有流水就一个字不说。**

    ## 为什么要它

    2026-08-26 本人问：「cli 实际已经封了几天，你每次都是一尝试就又封了吧」。
    ——是。而**工具答不出这句话**：封控记录只有 `{until, why, where}` 三个字段，
    每撞一次就把上一次原样覆盖掉，别处也不留痕。于是屏幕上永远只有
    「已经封了 16 小时」，读起来像个刚发生的小毛病；而真相是这个出口从
    08-24 起就没通过，中间每探一次就重封一次。

    **这两个读数会导出相反的决定**：16 小时 → 再等等；三天三次全灭 →
    这个 IP 不会好了，换出口或者干脆走浏览器那条。
    """
    hits = [e for e in block_log(data, portal, lane) if e.get("act") == "hit"]
    clears = [e for e in block_log(data, portal, lane) if e.get("act") == "clear"]
    if len(hits) < 2:
        return ""
    try:
        first = dt.datetime.fromisoformat(hits[0]["at"])
    except (TypeError, ValueError, KeyError):
        return ""
    days = max(1, round((now - first).total_seconds() / 86400))
    tail = ""
    if clears:
        # **放行之后多快又撞上** —— 这一个数最能说明「等」和「探」都没用。
        gaps = []
        for c in clears:
            try:
                t = dt.datetime.fromisoformat(c["at"])
            except (TypeError, ValueError, KeyError):
                continue
            after = [dt.datetime.fromisoformat(h["at"]) for h in hits
                     if h.get("at", "") > c.get("at", "")]
            if after:
                gaps.append((min(after) - t).total_seconds() / 60)
        if gaps:
            tail = (f"；中间放行过 {len(clears)} 次，最快一次放行后 "
                    f"{int(min(gaps))} 分钟就又撞上了")
        else:
            tail = f"；中间放行过 {len(clears)} 次"
    return (f"。⚠️ 这条已经不是第一次了：{first:%m-%d} 起一共撞了 "
            f"{len(hits)} 次、跨 {days} 天{tail} —— 同一个出口再试也是一样的结果")


def block_state(data: dict, portal: str, now: dt.datetime,
                lane: str = "") -> dict:
    """这家的风控冷却状态，一次解析、多处消费。

    `check()`（命令行侧拦抓取）和 `export_web_data`（面板告警条）原来各自解析
    `blocked_until`——同一段 isoformat + 剩余时长换算写了两遍（2026-08-20 收拢）。
    返回 `{"blocked", "why", "held_minutes", "where", "lane"}`。

    **`lane` 留空时看的是「有没有任何一条通道被封」**，取剩余最久的那条。
    面板要的就是这个：浏览器要短信验证时，哪怕 CLI 还在正常抓，用户也必须
    看见那条告警——只有他本人过得了那个验证。
    **`check()` 不能用这个口径**，它必须点名通道，否则浏览器的封控会把
    匿名的 CLI 一起拦下，那正是这次要修的东西。
    """
    site = site_of(portal)
    row = data.get(site) or {}
    blocks = _blocks(row, site)
    want = [lane] if lane else list(lanes_of(site))
    hits = [st for lg in want
            if (st := _one_lane(blocks.get(lg) or {}, lg, now))["blocked"]]
    return max(hits, key=lambda x: x["held_minutes"]) if hits else dict(NOT_BLOCKED)


def other_lane_note(data: dict, site: str, lane: str,
                    now: dt.datetime) -> str:
    """被封时那句「**另一条怎么办**」。只有这一份。

    它原来在 `check()` 和 `main()` 各写了一遍。2026-08-21 给 `check()` 那份
    补了「先看看 CLI 是不是也封着」，`main()` 那份没跟上 —— 于是
    CLI 已经在冷却里、浏览器又撞风控时，命令行照样打印
    「CLI 那条不受影响，照常可以抓」。**用户照它去抓，撞的是一条封着的路。**

    「同一个概念两处各写一份」这个病，这个仓库治过很多次；这次是同一天里
    修了一处、漏了另一处，间隔两小时。
    """
    if PRIMARY_LANE.get(site) != "cli":
        return ""                       # 这家只有一条通道，没有「另一条」可谈
    if lane == "cli":
        # **说「浏览器那条还能走」之前，先看看它自己封着没有。**
        # 上面那段说明记的正是反方向的同一次漏检（说「CLI 照常」而 CLI 也封着），
        # 而这一半当时没跟着改 —— 修了一处、漏了对称的另一处，同一天第二次。
        if block_state(data, site, now, "browser")["blocked"]:
            return "，浏览器那条也停着 —— 这家两条路眼下都不通"
        # CLI 封着的这段时间，**浏览器那条就是该走的那条**，不是备胎。
        # 2026-08-26 本人：「在停止时间使用猎聘浏览器获取」。
        return (f"，这段时间走浏览器那条（放慢：间隔 ×{SLOW_GAP_FACTOR}）"
                "—— 放慢是因为同一家同一个网络出口，按原速换通道会把限流"
                "升级成账号风控；但放慢不等于不走")
    # 说「CLI 那条照常」之前**先看看它是不是也封着**。
    return ("，CLI 那条不受影响，照常可以抓"
            if not block_state(data, site, now, "cli")["blocked"] else "")


def effective_lane(data: dict, portal: str, now: dt.datetime) -> str:
    """裸平台名要落到**此刻真走得通的那条**通道，不是永远落到主通道。

    `lane_of()` 回答的是「用户说的是哪条」，没说就落主通道 —— 那对 `--block` /
    `--clear` 是对的：他撞在哪就封哪，没说清按他平常走的那条算。
    但对 `--check` / `--wait` 是错的，这两条问的是**「现在能不能动
    这家、按什么密度动」**，而主通道封着 ≠ 这家不能动 —— 2026-08-21 起
    CLI 封着时浏览器只放慢、不停。

    照 `lane_of` 走的实测后果（都在同一个根上）：

    1. `--check 猎聘` 退出码 1，而 `job-scrape.md` 让执行者见 1 就**跳整站** ——
       不对称那套设计当场作废，浏览器那条整整一天用不上；
    2. `--wait navigate --portal 猎聘` 睡 8 秒而不是 24 秒 —— 而 `--wait` 是
       **唯一真正执行间隔的地方**（`--check` 只会告诉你太密，拦不住任何人），
       放慢于是成了只在嘴上说的。

    （原来第 2 条讲的是 `--round`，2026-08-26 那条命令随固定额度一起删了。）

    给了渠道名就照渠道名，一个字不猜。
    """
    if (portal or "").strip() not in PORTALS:
        return lane_of(portal)
    site = site_of(portal)
    lanes = lanes_of(site)
    # 主通道优先：没封就还是走他平常那条，行为不变。
    for lg in (lane_of(portal),) + tuple(lanes):
        if lg in lanes and not block_state(data, site, now, lg)["blocked"]:
            return lg
    return lane_of(portal)      # 全封着：落回主通道，让调用方去报它的冷却


def check(data: dict, portal: str, now: dt.datetime,
          probe: bool = False, after_acting: bool = False) -> tuple[bool, str]:
    """现在能不能动这家。返回 `(能不能, 为什么)`，`为什么` 直接说给用户听。

    ## 只有两道门

    1. **这条通道在不在冷却里** —— 只有真撞过风控才有（`--block` 记的）；
    2. **距上一个动作够不够间隔** —— `gap_for(kind)` 秒，同一家的 CLI
       封着时 ×`SLOW_GAP_FACTOR`。

    没有第三道。轮次上限、每日请求上限那些**固定额度 2026-08-26 删了**，
    理由见模块开头「密度只由一件事管」。日请求数还打印，但只是读数。

    ## `after_acting=True`：刚动完一下，问的是「**下一个**还能不能做」

    `--note` 用它。间隔那一条对这个问题的诚实答案是**「等 N 秒」，不是「停」**——
    而 `--note` 是在**记完之后**问的，于是它拿刚写下的那条动作跟自己比，
    gap 恒等于 0.x 秒，**每一次记账都回「动作太密」**。

    2026-08-26 实测（内存模拟，不写盘）：BOSS / 智联 / 前程无忧 / 猎聘
    四家全中，记之前一律 `ok=True`，记之后一律
    「动作太密：上一个是「navigate」，要隔 8 秒，现在才 0.4 秒」。
    而 `--note` 把 `ok=False` 印成**「记下了，但到线了」并返回退出码 1**，
    照 `job-scrape.md` 那套，执行器见 1 就收尾——**每记一次账就被劝退一次**。
    今天已经栽过两次的正是这个形状：工具说停，整条渠道于是一天没人动。

    所以这一支跳过间隔判据，只答**真会让人停手**的那一件：冷却。
    间隔照旧由 `--wait` 那一处真睡——**唯一真正执行间隔的地方**，
    这里不重算一遍它的秒数，只把那条命令写给执行器。

    ## `probe=True`：一次探恢复的哨兵请求

    用户 2026-08-21 点名要的「CLI 手动重试来检测是否恢复正常」有个死结：
    **探测要穿过的，正是它要测试的那道冷却门。** 照常 `--check` 一律退出码 1，
    这个功能就永远够不着。

    所以开一个口，而且把它焊死成三条：

    1. **只免冷却，不免密度。** 日上限、轮上限、动作间隔一条不放宽 ——
       冷却是「这条路现在通不通」，密度是「你按得多勤」，探测只质疑前者。
    2. **只对 CLI。** 浏览器那条封的是账号，要用户本人过验证 ——
       工具探不出来，探了也不能作数。给它开口只会让人误以为点一下就能解。
    3. **只由人开口时用。** 这是文档侧的约束（`job-scrape.md` 体检那节），
       但把它做成一个名字里带 probe 的显式参数，比只写一句「记得别滥用」难走偏 ——
       正常抓取路径上没人会顺手写 `probe=True`。
    """
    site = site_of(portal)
    row = data.get(site)
    if not row:
        # 「额度是满的」这个说法 2026-08-26 改了 —— 没有上限就没有「满」。
        # 但「额度」这个词要留着：面板那一栏靠它，而它现在指的是
        # 「平台还没喊停」。
        return True, f"{site} 今天已发 0 次，还没动过；没有次数上限，额度撞到才算"

    # **封控按通道判，而且是不对称的。** CLI 撞了限流，浏览器**放慢**（不是停）——
    # 2026-08-19 实测按原速换通道会把软限流升级成账号级风控，但用户 2026-08-21 裁定
    # 浏览器是他本人在场、一次一页，降密度就够。反过来不成立：浏览器的账号被标异常，
    # 不该让一个**不带任何凭据**的匿名接口跟着停 24 小时——那条照常跑。
    # **`probe` 是例外**：它问的就是「CLI 那条恢复没有」，要的正是被封的那条，
    # 不能改派到浏览器上去 —— 改派了就永远探不到它想探的东西。
    lane = lane_of(portal) if probe else effective_lane(data, portal, now)
    st = block_state(data, site, now, lane)
    if probe and lane == "cli":
        st = dict(NOT_BLOCKED)           # 只免冷却；下面的密度判据照常走
    # CLI 在冷却里时，浏览器那条**放慢**（见 `SLOW_GAP_FACTOR` 的说明）。
    # **只问这家真有的通道。** BOSS / 智联 / 前程无忧根本没有 CLI 那条，
    # 无条件去问它，一条手改进来的 `blocks["cli"]` 就能把这三家的每轮上限
    # 从 10 压到 3、间隔 ×3 —— 而 `block_state` / `clear` 都按 `lanes_of` 走，
    # 看不见也解不掉它。同 `lanes_of` 的说明：全局那个 `LANES` 会让它们凭空
    # 多出一条通道。
    slow = False
    if not st["blocked"] and lane == "browser" and "cli" in lanes_of(site):
        slow = block_state(data, site, now, "cli")["blocked"]
    if st["blocked"]:
        mins = st["held_minutes"]
        which = " CLI " if st["lane"] == "cli" else "浏览器"
        other = other_lane_note(data, site, st["lane"], now)
        chan = CHANNEL_NAME.get((site, st["lane"]), site)
        # **报「已经封了多久」，不报「还剩多久」。**（2026-08-26 本人裁定：
        # 「只有用户手动点继续 cli 后，才能继续 cli」。）
        #
        # 倒计时那个数以前读起来就是解法 ——「等到点就好了」。而它从来不是：
        # CLI 那条限的是这个网络出口的 IP，到点换的还是同一个 IP，探一次限
        # 一次；浏览器那条要他本人过完验证。**两件事都得人动手，钟表帮不上。**
        wait = f"，已经封了 {mins // 60} 小时 {mins % 60} 分"
        wait += "。不会自动解 —— 要你确认外面那件事已经变了才继续："
        wait += ("换掉这个网络出口的 IP" if st["lane"] == "cli"
                 else "本人过完那个验证")
        wait += f"，然后跑 --clear {chan}（或在总览页点那条上的「继续抓」）"
        # **不是第一次撞的话，把这件事说在最前面。** 见 `streak_note`：
        # 「已经封了 16 小时」和「三天撞了 3 次、每次放行后几分钟又中」
        # 会导出相反的决定，而屏幕上原来只有前者。
        streak = streak_note(data, site, st["lane"], now)
        return False, (
            f"{site} 的{which}停着（{st['why']}）{wait}{other}{streak}")

    # 日请求数**只是读数**，不是闸门（模块开头「密度只由一件事管」）。
    # 留着它是因为 08-17 那 1032 次的教训没被推翻 —— 只是它当不了闸门：
    # 那次当场没报错，两天后才结账，等它报警时已经晚了两天。
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_reqs = len(_since(row.get("actions"), day))

    # **唯一的密度闸门：距上一个动作够不够间隔。**
    #
    # 回看窗口用 `GAP_LOOKBACK`，不用「今天零点起」。用零点起有个只在半夜
    # 现形的洞：00:00:05 跑一次，23:59 那个动作落在窗口外，`acts` 为空，
    # **整个间隔判据被跳过**。而这一条现在是仅剩的那道门，漏不起。
    # 同一个窗口也是 `--wait` 用的那个（那里才是真睡的地方），一处定义。
    acts = [] if after_acting else _since(row.get("actions"), now - GAP_LOOKBACK)
    if acts:
        gap = (now - max(acts)).total_seconds()
        need = gap_for(row.get("last_kind") or "") * (SLOW_GAP_FACTOR if slow else 1)
        if gap < need:
            return False, (f"{site} 动作太密：上一个是「{row.get('last_kind') or '未知'}」，"
                           f"要隔 {need} 秒，现在才 {gap:.1f} 秒"
                           + ("（CLI 那条停着，间隔按 ×%d 放慢）" % SLOW_GAP_FACTOR
                              if slow else ""))
    ok = f"{site} 可以动（今天已发 {today_reqs} 次；没有次数上限，额度撞到才算）"
    if slow:
        ok += (f"。放慢中：CLI 那条停着，所以浏览器这条把间隔 ×{SLOW_GAP_FACTOR}"
               " —— 不是停，是拉长间隔")
    # **裸平台名是有歧义的**，它落到主通道。放行的是那一条，而调用方接下来
    # 未必走那一条 —— 实测缺口：浏览器封着、CLI 正常时，`--check 猎聘` 回「可以」，
    # 照它去开浏览器就一头撞进验证页。
    #
    # 文档规矩（「要检查你接下来真正要走的那条」）挡不住这个，因为写文档的人
    # 和读文档的人不是同一次。所以在这里把另一条的状态说出来：**放行照旧放行，
    # 但别让它看起来像「整家都没事」。**
    # 同上：只遍历这家真有的通道，别给单通道的三家凭空造一条 CLI。
    if (portal or "").strip() in PORTALS:
        for lg in lanes_of(site):
            if lg == lane:
                continue
            other_st = block_state(data, site, now, lg)
            if other_st["blocked"]:
                name = " CLI " if lg == "cli" else "浏览器"
                cmd = CHANNEL_NAME.get((site, lg), site)
                ok += (f"。注意：{site} 的{name}停着，"
                       f"要走那条先跑 --check {cmd}")
    return True, ok


def note(data: dict, portal: str, n: int, now: dt.datetime, kind: str = "") -> None:
    """记 n 次动作。`kind` 是动作类型（navigate/fetch/click/read），决定下一次要等多久。"""
    row = _row(data, site_of(portal))
    if kind:
        row["last_kind"] = kind
    for i in range(max(1, n)):
        row["actions"].append(
            (now + dt.timedelta(seconds=i)).isoformat(timespec="seconds"))
    row["actions"] = row["actions"][-200:]


#: 撞了风控时该去哪儿处理。**没记到具体拦截页时用这个兜底**——
#: 让用户从首页进去，平台会自己把他导到验证流程。
HOME = {"猎聘": "https://www.liepin.com", "BOSS": "https://www.zhipin.com",
        "智联": "https://www.zhaopin.com", "前程无忧": "https://www.51job.com"}


def round_plan(data: dict, user: str, now) -> list:
    """这一轮该跑哪几条**通道**。返回 `[(能不能跑, 渠道名, 一句话)]`。

    ## 为什么要有它

    闸门按**通道**判，而人（和执行者）习惯按**家**想。这两个粒度对不上时，
    「猎聘 CLI 停着」就被读成「这一轮没有猎聘」——而 `liepin-browser` 明明
    放行（降速 ×3）。规则写在三个地方（`AGENTS.md`、`job-scrape.md` Step 0.4、
    本模块 `SLOW_GAP_FACTOR` 上面那段），`--check liepin-search` 的回话里也
    明写着「这段时间走浏览器那条……放慢不等于不走」。

    **写了四处，还是连错两次**（2026-08-25 用户当场纠正过一次，2026-08-30
    又来一次：那天 CLI 撞限流、`liepin-browser` 0 次查询，而猎聘占这个职位库
    语料的大头）。差的不是规则，是**「这一轮到底跑哪几条」这件事得有人枚举**，
    而枚举是机械活。

    所以这里把它做成一张现成的单子：勾着的家 × 它真有的通道，逐条给出闸门结论。
    执行者照单子跑，不必再自己把「家」拆成「通道」。

    关掉的家不进单子（那是用户的开关，见 `switched_off`）；被闸门挡住的照样列，
    但标成不能跑并写清怎么解 —— **不列出来就等于把它藏了**，而藏起来的正是
    「这一轮为什么没有这家」的答案。
    """
    out = []
    off = switched_off(user)
    today = now.date().isoformat()
    ran = _lane_runs(user, today)
    for site in HOME:
        if site in off:
            continue
        for lane in lanes_of(site):
            name = channel_of(site, lane)
            ok, why = check(data, name, now)
            # **只给还能跑的通道补那半句。** 被封的那条上它既是噪音又是错的：
            # 全家今天那一次动作恰恰就是它自己（撞限流的那次请求 —— 没返回
            # 结果，所以 `query_log` 里没有它），而那半句会说成「落在另一条上」。
            # 实测 2026-08-30 第一版就是这么印的。
            out.append((ok, name,
                        why + (_own_count(name, site, ran, data, today)
                               if ok else "")))
    return out


def _lane_runs(user: str, day: str) -> dict:
    """今天**每条通道**各跑了几次查询。读 `query_log`，读不出返回空。

    `actions` 那份是按**家**记的（限流按 IP / 站点来，那个粒度是对的），
    而这里要答的是「这条通道今天动没动」—— 两个粒度不能互相顶替。
    """
    f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    try:
        log = json.loads(f.read_text(encoding="utf-8")).get("query_log")
    except (ValueError, OSError, AttributeError):
        return {}
    if not isinstance(log, list):
        return {}
    out: dict = {}
    for q in log:
        if not isinstance(q, dict):
            continue
        if str(q.get("date") or q.get("at") or "")[:10] != day:
            continue
        k = str(q.get("portal") or q.get("channel") or "")
        if k:
            out[k] = out.get(k, 0) + 1
    return out


def _own_count(name: str, site: str, ran: dict, data: dict, day: str) -> str:
    """给通道那一行补上**它自己**今天的次数。

    ## 为什么这半句要有

    `check()` 回的那句主语是**家**（「猎聘 今天已发 N 次」），而它印在一行
    `liepin-browser` 后面。句子没错，位置让人误读 —— 而误读的方向正是
    `round_plan` 上面那段记着的那个错：**以为这一家今天已经跑过了**。

    实测 2026-08-30：`猎聘.actions` 今天只有一条 `00:37:07`，那是
    **CLI 撞限流的那次请求**；而单子上 `liepin-browser` 那行照样印着
    「今天已发 1 次」。同一份输出下面两行才写「一家的主通道被挡住 ≠
    这一轮没有这家」—— 工具自己先请出了它要警告的那个误读。

    只在**会误读的那一种情形**下加话：这条通道今天 0 次、而全家非 0。
    两个数都是 0 时 `check()` 已经说了「还没动过」，再补一句是噪音。
    """
    n = ran.get(name, 0)
    if n:
        return f"。这条通道今天跑过 {n} 次查询"
    row = data.get(site) or {}
    fam = sum(1 for a in (row.get("actions") or []) if str(a)[:10] == day)
    if not fam:
        return ""
    return (f"。这条通道今天一次查询都没跑 —— 上面那个数是{site}全家的，"
            f"落在另一条上")


def block(data: dict, portal: str, why: str, now: dt.datetime,
          where: str = "") -> tuple[str, str, bool]:
    """记一次风控事件，**那条通道**进冷却。返回 `(平台名, 通道, 是不是新封的)`。

    第三个值必须有：本来就在冷却里时这次**不重算时间**（见下），
    调用方若照旧说一句「已进冷却 24 小时」就是在说一件没发生的事 ——
    用户会以为要从现在再等一天。

    给渠道名就封那一条，给平台名落到主通道（`lane_of`）。CLI 那条被封时
    `check()` 会把浏览器那条**放慢**（间隔 ×`SLOW_GAP_FACTOR`），不是拦住——
    （这里原来还写着「每轮上限降到 3」，那个旋钮 2026-08-26 已删）
    不对称是有意的，理由见 `check()` 里那段注释。

    `where` 是**撞上时那个页面的地址**（例如猎聘把你甩到的
    `https://safe.liepin.com/v/intercept/verifysms?...`）。记下来是为了让面板上的
    告警条能给一个**点进去就能办**的链接——多数风控只有用户本人能解，让他自己
    去翻哪个页面要验证，等于把最后一步又扔回给他。拿不到就退到 `HOME`。
    """
    site, lane = site_of(portal), lane_of(portal)
    row = _row(data, site)
    blocks = dict(_blocks(row, site))    # 老格式先迁移，别把存量记录读丢
    # **已经在冷却里的通道，时间不重算。** 冷却是「从第一次撞上起 24 小时」，
    # 期间再撞是意料之中的事（那正是「被封着」的意思），不该累加。
    #
    # 这条不是洁癖，它挡的是一个具体陷阱：用户 2026-08-21 要的「CLI 手动重试」，
    # 探失败时最顺手的动作就是再 `--block` 一次记一笔——而那会把 24 小时从头
    # 再算。**越想确认它恢复没有，就越晚能用**，功能变成惩罚。
    # 靠「记得别这么做」防不住，所以在这里按构造消掉。
    prev = blocks.get(lane)
    old = _one_lane(prev or {}, lane, now)
    old_ok = isinstance(prev, dict)
    # 原来的 `blocks[lane]["until"]` 假设 prev 一定是字典；而 `_one_lane` 刚刚
    # 明确把「非字典」也判成 blocked（safety 方向正确）。两边一撞，撞限流后
    # 想记账的那一下反而 TypeError —— 这里只在 prev 真是字典时保留旧时刻。
    blocks[lane] = {
        "until": (((prev.get("until") if old_ok else None)
                   if old["blocked"] else None)
                  or (now + dt.timedelta(hours=BLOCK_COOLDOWN_H)
                      ).isoformat(timespec="seconds")),
        # 撞上的时刻。**同 `until`，本来就在停着时不重写** —— 否则每撞一次
        # 「已经封了多久」就归零，读起来像刚发生的。
        "since": (((prev.get("since") if old_ok else None)
                   if old["blocked"] else None)
                  or now.isoformat(timespec="seconds")),
        "why": why or "撞过风控",
        # **只有浏览器那条配得上一个「去处理」的链接。** CLI 撞的是限流，
        # 没有页面可去、也没有验证可过——给它退到首页，等于让用户点开一个
        # 什么都不做的链接，然后以为自己漏了一步。
        #
        # **已经记下的那个地址不许被兜底盖掉。** 上面刚为「再撞一次不重算时间」
        # 写了一整段，而这一行原来是无条件重建的：第一次撞上记下的
        # `https://safe.liepin.com/v/intercept/verifysms?...` 会在第二次
        # 不带 `--where` 的 `--block` 里退回首页 —— 而重复撞上正是常态
        # （后面几次多半只拿得到一个错误码）。面板那个「去处理」于是从
        # 「点进去就能办」变回「你自己去翻哪个页面要验证」，正是 `where`
        # 这个字段存在的理由本身。
        "where": (where or (old["where"] if old["blocked"] else "")
                  or (HOME.get(site, "") if lane == "browser" else "")),
    }
    row["blocks"] = blocks
    row["blocked_until"] = ""            # 老字段作废，留空防止两处各说一套
    # **每一次都记，包括「本来就封着又撞一次」。** 后者正是「探一次限一次」
    # 的那条证据 —— 只记新封的话，屏幕上永远看不出探过几回。
    _log(row, lane, "hit", now, why)
    return site, lane, not old["blocked"]


#: `clear()` 的第二个返回值取这个时，表示**没解、也不该猜**：给的是平台名，
#: 而两条通道各自因为不同的事封着。调用方要把两个渠道名报给用户去点名。
AMBIGUOUS = "ambiguous"


def _event_of(rec) -> tuple:
    """一条封控记录的**身份**：`(until, why)`。

    `where` 不算 —— 它是给人看的「去处理」入口（限流那条压根没有），
    迁移时还会被故意抹空。拿整条记录比相等，同一个事件迁出来的两条
    会因为这个展示字段而互不相等。
    """
    if not isinstance(rec, dict):
        return (repr(rec),)
    return (rec.get("until") or "", rec.get("why") or "")


def clear(data: dict, portal: str, now: dt.datetime) -> tuple[str, str, bool]:
    """解掉一条通道的冷却。返回 `(平台, 通道, 原来是不是真被封着)`。

    **只由人触发，工具永远不自动解**（`serve.py.apply_unblock` 记着这条裁定的
    来龙去脉）。这里只负责「解哪一条」这个判断，三个调用方共用：
    命令行的 `--clear`、面板上的解封按钮、测试。原来三处各写一遍
    `row["blocked_until"], row["why"], row["where"] = "", "", ""`，
    换存储结构时就是三处各坏一次。

    **给渠道名就只解那一条** —— 「liepin-search 探通了」不等于
    「浏览器那个短信验证我过完了」，后者只有他本人做得到。

    **给平台名而两条通道各自因为不同的事封着 → 不解，返回 `AMBIGUOUS`。**
    这是 2026-08-21 第三次改这一段，前两版都在猜：

    - 「无差别解全部」会把他**根本没过的短信验证**一起解掉；
    - 「解剩余时长最长的那条」= 解**最近封的那条**，和他处理了哪条毫无关系。
      实测：10:00 封浏览器（要短信验证）、10:30 封 CLI（限流），
      10:31 `--clear 猎聘` 解掉 CLI、短信那条留着；顺序反过来就是解掉那个
      他从没过的验证，把浏览器放回一条活的验证页 —— 正是这整套闸门要防的事。

    工具**不知道**他刚才办的是哪一条，那就别猜：报出两个渠道名让他点名。
    多说一句话，换掉一次可能把账号送进风控的猜测。

    同一个事件迁移出来的两条（老格式 `blocked_until`）不算歧义 —— 一起解。
    判据是 `(until, why)`，**不是整条记录逐字相等**：迁移时会故意把 CLI 那条的
    `where` 抹空（限流没有页面可去），于是两条永远不相等，
    `--clear 猎聘` 只解一半、还打印成功（2026-08-21 实测）。
    `where` 是给人看的入口，不是事件的身份。

    第三个返回值是**目标通道原来真封着吗**，不是「这一家有没有被封」：
    两者不同的那一刻会说假话 —— 只有浏览器封着时 `--clear liepin-search`
    什么也没解，却打印「CLI 冷却已解除」（2026-08-21 通读时逮到）。
    """
    site = site_of(portal)
    row = data.get(site)
    bare = (portal or "").strip() in PORTALS
    # 先算**要动哪几条**，再看它们真封着没有 —— 顺序反过来就是上面那句假话。
    want = [lane_of(portal)]
    if bare:
        blocks = _blocks(row or {}, site)
        down = [lg for lg in lanes_of(site)
                if block_state(data, site, now, lg)["blocked"]]
        if len({_event_of(blocks.get(lg)) for lg in down}) > 1:
            return site, AMBIGUOUS, False
        want = down or [lane_of(portal)]
    lanes = [lg for lg in want
             if block_state(data, site, now, lg)["blocked"]]
    if not row or not lanes:
        return site, (want[0] if want else lane_of(portal)), False
    blocks = dict(_blocks(row, site))
    for lg in lanes:
        blocks.pop(lg, None)
    row["blocks"], row["blocked_until"] = blocks, ""
    for lg in lanes:
        _log(row, lg, "clear", now)
    return site, lanes[0], True


def switched_off(user: str) -> set:
    """用户在总览页**自己关掉**的渠道。读不出就当全开 —— 缺文件 ≠ 全关。

    ## 这不是把两道闸门合并

    `job-scrape.md` 明写着两件事的主人不同：`portals.json` 是**用户**说这一轮
    想不想抓这家，额度是**平台**说现在还让不让抓；合并之后「用户明明开着、
    工具却不抓」就没人解释得清是哪一层挡的。这里**不合并** —— 「可以抓 / 停」
    那个判词仍然只答平台那一问，关掉的渠道只在行尾多一句注脚。

    合并不行，但**互不提及也不行**。实测活动用户 2026-08-23：这份额度报告
    逐行写着「猎聘 可以抓」，而同一时刻面板写着「猎聘 你关着（占库里 85%）」。
    两句都对、两句都不提对方 —— 那正是上面那句警告的反面：
    **读的人一样不知道到底能不能抓。**

    判据与 `export_web_data.portals_enabled` 同源，这里内联一份：那边 import
    本模块（`import portal_budget as pb`），反向 import 就成环了。
    「缺文件 = 全开」是**要紧的默认**（`test_portal_switch_is_read` 钉着），
    抄漏它的话第一次跑就会说四家全关。
    """
    p = ROOT / "users" / user / "job_scraper" / "portals.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    # **判「关」用 `not bool(v)`，不是 `v is False`。** 正本
    # `portals_enabled` 写的是 `bool(d.get(k, True))` —— 手改过的文件里出现
    # `null` / `0` / `""` 时那边算关、这边算开，两处当场说反。
    # （第一版就写成 `v is False`，是变异测试把它逼出来的。）
    return {k for k, v in d.items() if not v} if isinstance(d, dict) else set()


#: 通道的中文名。印给用户看的字里不出现 `cli` / `browser` 这种码
#: （`AGENTS.md`「内部词不要搬到台面上」）。
LANE_NAMES = {"cli": "CLI（免登录接口）", "browser": "浏览器"}


def channel_of(site: str, lane: str) -> str:
    """`(平台, 通道)` → 一个能传给 `--check` / `--block` 的渠道名。

    **从 `PORTAL_ALIAS` 现推，不另立一张表** —— 这个仓库为「同一份映射两处实现」
    付过好几次学费。同一条通道有好几个历史别名（`51job` / `51job-cdp` /
    `51job-browser`），取带后缀的那个：它是现在写进 `query_log` 的那一个。
    """
    cands = [ch for ch, s in PORTAL_ALIAS.items()
             if s == site and ch not in PORTALS and lane_of(ch) == lane]
    if not cands:
        return site
    return sorted(cands, key=lambda c: (not c.endswith(("-browser", "-search")),
                                        len(c)))[0]


def status_lines(data: dict, now: dt.datetime, off: set | None = None) -> list[str]:
    out = []
    for site in PORTALS:
        ok, why = check(data, site, now)
        # **封着的通道全列出来，别只挑一条。** `block_state` 不带 lane 时按
        # 「剩得最久」挑一条，而同一行右边那句 `why` 来自 `check()`，它挑的是
        # `effective_lane`（主通道优先）—— 两条各自封着、到点时间不同时，
        # 同一行会点两个不同通道的名，读的人不知道该去解哪一条。
        down = [lg for lg in lanes_of(site)
                if block_state(data, site, now, lg)["blocked"]]
        st = block_state(data, site, now)
        tag = ""
        if st["blocked"]:
            # 哪条通道被封要写在脸上——浏览器那条只有用户本人过得了验证，
            # 而 CLI 那条探一次就知道恢复没有。两种处理方式完全不同。
            #
            # **放行那一支要把动词写进括号。** 括号里点的名是**被封的**那条，
            # 而 `ok=True` 时它粘在「可以抓」后面就成了「可以抓（浏览器）」——
            # 读起来正好是「浏览器可以抓」，说反了唯一一条不能抓的路。
            name = "、".join("CLI" if lg == "cli" else "浏览器" for lg in down)
            tag = f"（{name}）" if not ok else f"（{name}停）"
        # **注脚，不是判词。** 「可以抓」答的是平台那一问（额度/风控），不动；
        # 勾没勾上在行尾补一句。两道门分开报，读的人才说得清是哪一层挡的
        # （判据见 `test_the_two_gates_mention_each_other`）。
        #
        # 2026-08-23 试过把第一列改成「关着（额度没问题）」——理由是那一列上
        # 写的是动词，而读的人在那个位置问的是「这一轮会不会抓它」。
        # **撤回了**：那等于把两道门合并，而分开报是上一版有意的裁定，
        # 光凭措辞偏好不足以推翻。要的那个用户收益不碰这一列也拿得到 ——
        # 见下面那句注脚和 `job-scrape.md`「开抓前先看一眼有没有把大头关掉」（2026-08-25 从 job-auto.md 归位过去）。
        #
        # **但注脚要多说一句：当初拦它的还在不在。** 多数人关掉一家是因为
        # 当时撞了风控，拦解了平台不会通知，勾就一直关着。实测活动用户
        # 2026-08-23：猎聘勾是关的、`blocked` 已经 false，而它占语料 85%
        # （2232/2638），四家里唯一还在产可投岗的也是它（可投 8，其余合计 1）。
        # 这一句不进判词列，只在注脚里 —— 它答的是「开关」那一道门。
        note_off = ""
        if site in (off or ()):
            note_off = "　← 你在总览页关掉了这家"
            if ok and not st["blocked"]:
                note_off += "；当初拦它的已经解了"
        state = ("可以抓" if ok else "停") + tag
        out.append(f"  {site:<6} {state:<10} {why}{note_off}")
        # **一条通道一行。** `job-scrape.md` 那张渠道表是 **5 条**，而这里原来
        # 按平台印 **4 行** —— 猎聘的第二条通道被压进行尾一句注脚里。
        #
        # 实测代价，同一条通道漏了两次（2026-08-25、2026-08-27）：CLI 撞限流后
        # 浏览器那条该照常进这一轮，两次都没走，报告都写成「猎聘在冷却」。
        # 而这份输出正是 Step 0.44 让执行者「一眼看状态」用的那一份 ——
        # **规则说 5 条，仪表只显示 4 行，被漏掉的就是第 5 条。**
        #
        # 同一课这个文件里已经记过一次：「那个标记在行尾，别裸眼扫」
        # （关掉了这家的注脚，2026-08-24 整趟跑完没人提）。行尾放不住东西。
        lanes = lanes_of(site)
        if len(lanes) > 1:
            for lg in lanes:
                ch = channel_of(site, lg)
                ok2, why2 = check(data, ch, now)
                out.append(f"    └ {LANE_NAMES[lg]:<14}"
                           f"{'可以抓' if ok2 else '停':<8}{ch:<16}{why2}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="招聘网站的动作额度与风控冷却")
    ap.add_argument("--check", metavar="平台或渠道",
                    help="能不能动这家（不能则退出码 1）")
    ap.add_argument("--round", action="store_true",
                    help="列出这一轮该跑的每一条通道（勾着的家 × 它真有的通道）。"
                         "闸门按通道判而人按家想，两次整轮漏掉一条通道都是这么来的")
    ap.add_argument("--probe", action="store_true",
                    help="配 --check：这是一次探恢复的哨兵请求，"
                         "只免风控冷却（仅 CLI 渠道），密度上限照常")
    ap.add_argument("--note", metavar="平台", help="记页面动作")
    ap.add_argument("-n", type=int, default=1, help="记几次，默认 1")
    ap.add_argument("--kind", default="",
                    help="动作类型 navigate/fetch/click/read，决定下一次要隔多久")
    ap.add_argument("--wait", metavar="动作类型",
                    help="按该类型的间隔真的睡够再返回（配 --portal 指定哪一家）")
    ap.add_argument("--portal", default="", help="配合 --wait 用")
    ap.add_argument("--block", metavar="平台或渠道",
                    help="记一次风控事件，那条通道进冷却（给平台名落到主通道）")
    ap.add_argument("--why", default="", help="风控原因，会显示给用户")
    ap.add_argument("--where", default="",
                    help="撞上时那个页面的地址（验证页/拦截页），面板会做成可点的链接")
    ap.add_argument("--clear", metavar="平台或渠道",
                    help="解那条通道的冷却（用户说他已经处理完了）")
    ap.add_argument("--user", help=_cli.HELP_USER)
    a = ap.parse_args(argv)

    user = _cli.pick_user(a.user or "", root=ROOT)
    data = load(user)
    now = dt.datetime.now()

    # **名字不认识就停下，别当成一条崭新的渠道放行。**
    #
    # `lane_of` 对认不出的名字一律退回 `"browser"`，于是 `check()` 拿它当
    # 一条从没动过的通道：没冷却、没间隔 —— 打印「可以」，退出码 0。
    #
    # 实测 2026-09-01：`--check lieping-search`（比真名多一个字母，而真名那条
    # 正封着 112 小时）回的是「可以：lieping-search 今天已发 0 次，还没动过」。
    # **一个错字把硬停变成放行**，而这道闸门护的是用户自己的账号。
    # `--check LIEPIN-SEARCH`（大小写不同）同样放行。
    #
    # 名字给错在这条命令上有先例：`job-scrape.md` 记着执行者敲过
    # `--round liepin`。那次是往「当成整家没戏」的方向错，这次是往
    # **放行**的方向错 —— 后者更贵。
    #
    # 退出码用 2，不用 1：1 是「这条通道停着，别动」，执行者照它跳过这一条；
    # 名字打错要的是**停下改命令**，两件事不能共用一个码。
    for _flag, _val in (("--check", a.check), ("--block", a.block),
                        ("--clear", a.clear), ("--note", a.note),
                        ("--portal", a.portal)):
        if _val and not known_channel(_val):
            print(unknown_channel_note(_flag, _val), file=sys.stderr)
            return 2

    if getattr(a, "round", False):
        rows = round_plan(data, user, now)
        if not rows:
            print("这一轮一条通道都没有：四家你都在总览页上关掉了。"
                  "想开哪家就在那一页点开，或者跑 /job-scrape health 看一眼各家状态。")
            return 0
        go = [r for r in rows if r[0]]
        print(f"这一轮该跑的通道（用户：{user}）：{len(go)}/{len(rows)} 条能跑")
        for ok, name, why in rows:
            print(f"  {'✓' if ok else '✗'} {name:<16}{why}")
        # **这句话是这条命令存在的理由。** 闸门按通道判、人按家想，
        # 两次整轮漏掉一条通道都是这么来的（2026-08-25、2026-08-30）。
        blocked_sites = {name.split("-")[0] for ok, name, _w in rows if not ok}
        still = [name for ok, name, _w in rows
                 if ok and name.split("-")[0] in blocked_sites]
        if still:
            print(f"\n  ⚠ 一家的主通道被挡住 ≠ 这一轮没有这家："
                  f"{'、'.join(still)} 照跑（降速，不是停）。")
        return 0

    if a.check:
        ok, why = check(data, a.check, now, probe=a.probe)
        print(("可以：" if ok else "停手：") + why)
        return 0 if ok else 1

    if a.block:
        site, lane, fresh = block(data, a.block, a.why, now, a.where)
        save(user, data)
        which = " CLI " if lane == "cli" else "浏览器"
        st = block_state(data, site, now, lane)
        mins = st["held_minutes"]
        # 说清**这次停的是哪条、另一条怎么办**。只说「进冷却了」的话，用户既
        # 不知道要不要去过验证，也不知道还能不能抓——两条通道的解法不一样。
        # 本来就在冷却里时说「已进冷却 24 小时」是假的，时间并没有重算。
        # 原因并进这一句里，别另起一组括号——两组括号挨着读不下去。
        head = (f"{site} 的{which}停了（{a.why or '撞过风控'}）"
                f"——不会自动解，处理完跑 --clear "
                f"{CHANNEL_NAME.get((site, lane), site)} 才继续"
                if fresh else
                f"{site} 的{which}本来就停着，只更新了原因"
                f"（{a.why or '撞过风控'}）"
                f"；已经封了 {mins // 60} 小时 {mins % 60} 分")
        rest = other_lane_note(data, site, lane, now)     # 正本在上面，别再写一遍
        # **渠道名从 `CHANNEL_NAME` 取，别写死 `liepin-search`。** 现在只有猎聘
        # 有 CLI 那条，写死看着也对；哪天 `PRIMARY_LANE` 多一家，这句就会教用户
        # 去探另一个平台的渠道。（`lane == "cli"` 已经蕴含「这家有 CLI 那条」——
        # `lane_of` 只对 `CLI_CHANNELS` 或主通道是 cli 的平台名返回 "cli"，
        # 原来那个 `two = PRIMARY_LANE.get(site) == "cli"` 恒真，是条假的第二判据。）
        cli_name = CHANNEL_NAME.get((site, "cli"), site)
        how = (f"。探一次看恢复没有：/job-scrape health {cli_name}，"
               f"通了再跑 portal_budget.py --clear {cli_name}"
               if lane == "cli" else
               "。这条只有你本人过得了验证，办完用 --clear 解开")
        print(f"{head}{rest}{how}")
        return 0

    if a.clear:
        # 解哪一条的判断全在 `clear()` 里，这里只报结果。
        before = [lg for lg in lanes_of(site_of(a.clear))
                  if block_state(data, site_of(a.clear), now, lg)["blocked"]]
        site, lane, was = clear(data, a.clear, now)
        if lane == AMBIGUOUS:
            # 两条各自因为不同的事封着，而他给的是平台名 —— **不猜**。
            # 猜错的两个方向都很贵：要么解掉他没过的短信验证、把浏览器放回
            # 一条活的验证页；要么解了 CLI 而他办的是浏览器那条。
            print(f"{site} 两条通道各自封着，而且不是同一件事 —— 说清是哪一条：")
            for lg in before:
                st = block_state(data, site, now, lg)
                print(f"  --clear {CHANNEL_NAME.get((site, lg), site)}"
                      f"   （{'CLI' if lg == 'cli' else '浏览器'}：{st['why']}）")
            return 1
        after = [lg for lg in lanes_of(site)
                 if block_state(data, site, now, lg)["blocked"]]
        done = [lg for lg in before if lg not in after]
        which = ("两条通道" if len(done) > 1 else
                 (" CLI " if lane == "cli" else "浏览器"))
        if not was:
            # **话要说在通道上，不是说在整家上。** `clear()` 的第三个返回值
            # 问的是「你点名那条原来封着吗」，而这句原来答的是「这家没被封」——
            # 只有浏览器封着时 `--clear liepin-search` 会打印「猎聘 现在没有被封」，
            # 而 `--check 猎聘` 同时还在为浏览器那条报警。
            other = [lg for lg in lanes_of(site) if lg != lane
                     and block_state(data, site, now, lg)["blocked"]]
            name = " CLI " if lane == "cli" else "浏览器"
            tail = ("；不过{} 那条还封着（{}）".format(
                " CLI " if other[0] == "cli" else "浏览器",
                block_state(data, site, now, other[0])["why"])
                if other else "")
            print(f"{site} 的{name}现在没有被封，不用解{tail}")
            return 0
        save(user, data)
        left = block_state(data, site, now)
        tail = ("（另一条还停着：" + (" CLI " if left["lane"] == "cli" else "浏览器")
                + "）") if left["blocked"] else ""
        print(f"{site} 的{which}已放行，可以接着抓了{tail}")
        return 0

    if a.wait:
        # **真的睡够再返回。** `--check` 只会告诉你「太密」，不会拦住任何人——
        # 昨天点卡片用 1.8 秒、browser_batch 里两个 navigate 零间隔，都是这么过去的。
        # 这条命令把「该等多久」变成「已经等过了」：跑完它，下一个动作就是合规的。
        # **放慢也要在这儿生效。** 上面那段说明写着「`--check` 不会拦住任何人，
        # 这条命令把『该等多久』变成『已经等过了』」—— 所以 `--wait` 才是真正
        # 执行间隔的那一处。2026-08-21 加「CLI 冷却时浏览器放慢」时先只改了
        # `check()`，这里照旧睡原速 —— 放慢就成了只在嘴上说的。
        # **不给 `--portal` 就不许放行。** 原来这里是 `a.portal or a.wait`——
        # 拿**动作类型**当平台名用：`--wait navigate` 于是查一个叫 `navigate`
        # 的「平台」，那家当然没有任何动作记录，于是 `slept=0.0`，
        # 却照样印「可以下一步了」。而这条命令是**唯一真正执行间隔的地方**
        # （`--check` 只会告诉你太密，拦不住任何人）——一个不检查就说「等够了」
        # 的闸门，比没有闸门更坏。零间隔连发正是 2026-08-19 撞上
        # `_security_check` 的那条路。
        _who = (a.portal or "").strip()
        _site = site_of(_who)
        if _site not in PORTALS:
            print(f"停手：--wait 要配 --portal <平台>（{'、'.join(PORTALS)}）——"
                  f"不知道是哪一家就算不出该等多久，"
                  f"而这条命令是唯一真的会等的那一处", file=sys.stderr)
            return 1
        # 文档教的写法是 `--portal <平台>`（裸平台名），照 `lane_of` 落到 CLI，
        # ×3 就永远不生效 —— 而这里是唯一真睡的地方。
        _slow = (effective_lane(data, _who, now) == "browser"
                 and block_state(data, _site, now, "cli")["blocked"])
        need = gap_for(a.wait) * (SLOW_GAP_FACTOR if _slow else 1)
        row = data.get(_site) or {}
        acts = _since(row.get("actions"), now - GAP_LOOKBACK)   # 与 check() 同一个窗口
        slept = 0.0
        if acts:
            gap = (now - max(acts)).total_seconds()
            slept = max(0.0, need - gap)
        if slept:
            time.sleep(slept)
        print(f"等了 {slept:.1f} 秒（「{a.wait}」类动作要求间隔 {need} 秒"
              + (f"，已按 ×{SLOW_GAP_FACTOR} 放慢：CLI 那条停着" if _slow else "")
              + "），可以下一步了")
        return 0

    if a.note:
        note(data, a.note, a.n, now, a.kind)
        save(user, data)
        # `after_acting=True`：刚记完的这一条不许拿来跟自己比间隔，
        # 否则每次记账都回「太密」并退出码 1，把执行器劝退（见 `check` 的说明）。
        ok, why = check(data, a.note, now, after_acting=True)
        if ok:
            # 间隔仍然要守，只是它是**等**不是**停**——把该敲的命令写出来，
            # 秒数不在这儿重算（`--wait` 是唯一真睡的那处）。
            kind = a.kind or (data.get(site_of(a.note)) or {}).get("last_kind") or "navigate"
            print("记下了。" + why)
            print(f"下一个动作前先跑：python tools/portal_budget.py "
                  f"--wait {kind} --portal {site_of(a.note)}")
            return 0
        print("记下了，但到线了：" + why)
        return 1

    print(f"招聘网站额度（用户：{user}）")
    for line in status_lines(data, now, switched_off(user)):
        print(line)
    print("")
    gaps = "/".join(f"{k} {v}秒" for k, v in GAP_S.items())
    print(f"动作间隔按类型（{gaps}）· 撞了风控那条通道就停下"
          f"（同一家另一条不停，间隔 ×{SLOW_GAP_FACTOR}）")
    print("没有次数上限：能跑多少由间隔和平台说了算，撞到风控才算到额度")
    print("停下的通道不会自己恢复 —— 处理完跑 --clear <渠道名>，或在总览页点那个按钮")
    return 0


if __name__ == "__main__":
    # 走收口：`--block` / `--clear` 这些写盘路径也会撞上 `StaleWrite`
    # （比如 `fetch_details` 正在连着记动作），撞上时该是一句「再跑一遍」。
    raise SystemExit(_cli.run_cli(main))
