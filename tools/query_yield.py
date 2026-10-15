#!/usr/bin/env python3
"""把「哪个查询词带来了哪些岗」量出来，并写回 `profile/search-queries.md`。

## 要解决什么

`search-queries.md` 的词表原来**只在 `/job-setup` 那一次生成，之后再没人改过**。
实测代价：该文件的校准注释停在 2026-07-24，而 07-30 之后候选人资料新增了
「AI 提效 / 效能产品 / 流程自动化 → 真实强项」这条判据——**新认定的强项从来没被搜过**。
后来临时补了 6 个提效类关键词，一轮就多出 75 个新岗（默认 11 组只贡献 2 个）。
但那 6 个词**没有任何地方存着**，下一轮又退回旧词表。

这跟 `writeback.py` 治的是同一个病，那里的原话是「**写回靠工具，不靠纪律**」：
指望流程文档写一句「记得把好用的词存下来」，AI 漏一步就白干。所以：

- **发现交给数据**——每个岗记下 `found_by`（哪个词搜到的），不再靠回忆；
- **写回交给本工具**——机械聚合、幂等重写 `search-queries.md` 里一块带标记的区域。

## 为什么按「词 × 平台」而不是只按词

实测：6 个提效词在猎聘上第一轮出 75 个、**同一天第二轮出 0**（挖空了），
可它们在前程无忧上是全新的，一轮出 67 个。**「这个词没用了」和「这个词在这个平台
没用了」是两回事**，只按词聚合会把后者误报成前者，然后把还能用的词删掉。

表里的 `—` 表示该词在该平台还没跑过——那通常是下一轮最值钱的格子。

## 用法

    python tools/query_yield.py            # 只报告（与 prescreen/writeback 同惯例）
    python tools/query_yield.py --apply    # 写回 search-queries.md 的自动维护块

零第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

BEGIN = "<!-- QUERY-YIELD:BEGIN"
END = "<!-- QUERY-YIELD:END -->"

#: 历史上同一家平台写过好几个名字（`51job` / `51job-cdp`），聚合前先归一，
#: 否则同一个平台会被拆成两列，每列都显得产出很低。
#:
#: **后缀会随驱动方式增生，别名表要跟着长。** 2026-08-19 实测：用 AI 工具自带的
#: 浏览器扩展抓了 BOSS/智联/前程共 72 个岗，portal 写成 `*-browser`——不在表里，
#: 于是整批落进「其它」，而「下一轮最值钱的格子」照旧把这三家推荐了一遍。
#: 这正是本文件开头那段注释警告的失败模式：跑过的格子没留痕，工具会永远推荐它。
#: 同一家平台的所有驱动方式（CLI / cdp / 浏览器扩展）都归到同一列。
PORTAL_ALIAS = {
    "liepin-search": "猎聘", "liepin": "猎聘", "liepin-cdp": "猎聘",
    "liepin-browser": "猎聘",
    "51job": "前程无忧", "51job-cdp": "前程无忧", "51job-browser": "前程无忧",
    "BOSS直聘": "BOSS", "boss-cdp": "BOSS", "boss": "BOSS", "boss-browser": "BOSS",
    "智联招聘": "智联", "zhaopin-cdp": "智联", "zhaopin": "智联",
    "zhaopin-browser": "智联",
    # 这三条原来只长在 `export_web_data.PORTAL_NAMES` 那一份上。两张表的**键域
    # 本来就是同一个**（都在问「这个内部键是哪一家」），而分头维护已经漏过两次：
    # 一次是 `*-browser` 后缀那边先补、这边后补，一次是中文名这边先认、那边后认。
    # 2026-08-31 起 `PORTAL_NAMES` 从这张表现推，这三条一并收进来。
    "job51-cdp": "前程无忧", "前程无忧": "前程无忧", "猎聘": "猎聘",
}
PORTALS = ["猎聘", "前程无忧", "BOSS", "智联"]

#: 「值得留在词表里」的判据。两条都要满足——只看新增数会把大量低质命中的
#: 泛词（`产品经理`）排到前面，而那正是 profile 已经标为「实测低效」的东西。
MIN_NEW = 5
MIN_HIGH_RATE = 0.25

#: 「这个词该停一停了」的判据：抓够这么多、而高匹配**一个都没有**。
#:
#: **只报不删。** 15 个样本下 0 命中说明不了它一定差 —— 全库平均命中率才 4%，
#: 一个平均水平的词有一半机会在 15 个里颗粒无收。所以这里给的是**事实**
#: （抓了多少、出了几个），不是判决；停不停由用户定，他知道自己那一行的词。
#:
#: 那为什么还要报：**抓取时间是这套系统里最稀缺的东西**。次数上限已经没有了
#: （2026-08-26），但每次请求之间要隔 8 秒 —— 抓 303 个岗就是 40 分钟挂在
#: 那儿。实测 2026-08-26 这个用户 13 个词各抓了 ≥15 个、高匹配全 0，合计 303 个岗，
#: 全花在从没出过一个可投岗的词上。而报告此前只会说「下一轮跑哪个词」，
#: 从不说「哪个别跑了」。
DEAD_MIN_N = 15

#: 报告里换算「白抓这些花掉多少」时用的**每次请求间隔**。
#:
#: 原来的基准是日上限（「约等于一个平台 N 天的额度」）。2026-08-26 固定
#: 额度删了 —— 稀缺的不再是次数而是**时间**，因为拦在前面的只剩间隔。
#: 正本在 `portal_budget.GAP_S`；这里只为它缺席时也能打印一句话。
try:
    from portal_budget import gap_for as _gap_for
    GAP_HINT_S = _gap_for("navigate")
except Exception:                                   # pragma: no cover
    GAP_HINT_S = 8


def norm(p: str | None) -> str:
    return PORTAL_ALIAS.get((p or "").strip(), (p or "其它").strip())


def is_runnable(q: str) -> bool:
    """这条来源能不能当查询词直接跑。

    BOSS 与智联登录后，**裸搜索页本身就按账号里设的「求职期望」过滤**，那一批岗
    的来源不是某个关键词。它照样要进上面的产出表（那是真实来源，而且实测它的
    高匹配率低得值得看见），但**不能进可执行块**——`-q "账号求职期望(AI产品经理)"`
    粘到 CLI 里只会报错，而用户不一定会先读一遍就照抄。
    """
    return not q.startswith(("账号求职期望", "期望:", "期望："))


def collect(seen: dict) -> tuple[dict, int, int]:
    """(词 → {平台 → [条目]}, 有来源的条目数, 没来源的条目数)"""
    by: dict = defaultdict(lambda: defaultdict(list))
    have = miss = 0
    for v in seen.values():
        # 本文件另外两处循环都有这一行，唯独这里没有 —— 而它是最早跑到的
        # 那一个。实测 2026-09-01：库里一条 `null` 就在这儿 `AttributeError`。
        if not isinstance(v, dict):
            continue
        q = (v.get("found_by") or "").strip()
        if not q:
            miss += 1
            continue
        have += 1
        by[q][norm(v.get("portal"))].append(v)
    return by, have, miss


#: 一个日子要有这么多个岗，它的「100% 有来源」才算得数 —— 只抓到一两个的
#: 日子全中也说明不了机制在跑，拿它当界碑会把后面所有缺口都算成漏记。
FULL_DAY_MIN = 10


def late_misses(seen: dict) -> tuple[int, dict]:
    """没记来源的那批里，**有多少是在这个字段已经在用之后才抓到的**。

    ## 为什么要拆

    报告原来对整批只说一句「本字段是后加的，更早抓的补不上」。那句话是**断言，
    不是算出来的**，而实测活动用户 2026-08-23 它对不上：

        08-11  缺 119/507 = 23%
        08-12  缺   0/274 =  0%     ← 机制在跑
        08-13  缺   0/ 56 =  0%
        08-14  缺 186/186 = 100%    ← 之后整整一天全丢了
        08-17  缺   0/1008 = 0%

    08-14 那 186 个不是历史遗留，是一次回退。而那句安慰恰恰让人不会去看
    —— 正是本仓库反复点名的最贵错法：**把「上游丢了数据」说成「核对过没问题」**。

    代价不是抽象的：没来源的 702 个岗里有 **129 个是评过分能投的**，占全部
    可投岗的 30%。而这张表决定的是**抓取额度往哪儿花**（每次请求之间要隔 8/4/3 秒、撞了风控整站冷却 24 小时），
    却建立在一个自己漏了三成好结果、还宣称漏的部分无关紧要的语料上。

    ## 判据：第一个**满覆盖日**之后还缺的，才算漏记

    界线不能取「有来源的岗里最早那个」—— 一个早期孤例就会把线拖到前面。
    实测活动用户 2026-08-23：那样取会报 649 个，而 07-30、08-10 整天 0%
    的那批（共 321 个）分明是机制还没跑起来时抓的，**虚高 3.5 倍**。
    报大了和报小了一样坏：读的人核对一次发现多数是历史遗留，
    下次就不看这一行了。

    所以取**第一个覆盖率 100% 的日子**（且当天不少于 `FULL_DAY_MIN` 个岗，
    免得一个只抓到 1 个的日子当了界碑）。从那天之后还缺的，无从辩解 ——
    同一条流水线前一天做得到、后一天没做。他这份语料里那条线是 08-12
    （274 个岗全有来源），漏的是 08-14 那 **186 个**。

    按日期归档返回：一个日期比一个总数好查得多 —— 拿它去对当天跑的是哪条路径。
    """
    days: dict = defaultdict(lambda: [0, 0])          # 日期 → [有来源, 总数]
    for v in seen.values():
        if not isinstance(v, dict):
            continue
        d = str(v.get("first_seen") or "")[:10]
        if not d:
            continue
        days[d][1] += 1
        if (v.get("found_by") or "").strip():
            days[d][0] += 1
    full = [d for d in sorted(days)
            if days[d][1] >= FULL_DAY_MIN and days[d][0] == days[d][1]]
    if not full:
        return 0, {}
    late = {d: days[d][1] - days[d][0] for d in sorted(days)
            if d > full[0] and days[d][0] < days[d][1]}
    return sum(late.values()), late


def unlogged_rounds(doc: dict, seen: dict | None = None) -> dict:
    """抓到了岗、却一条 `query_log` 都没留的日子 → `{日期: 新岗数}`。

    `seen` 传**热库 + 冷库合并后**的那份（`main` 里已经合好）：归档的岗
    也算它那天抓到过。只看热库的话，一次归档就能让某一天的岗数掉到
    `FULL_DAY_MIN` 以下，那天的漏记随之消失 —— 同 `collect` 上面那条注释的
    道理（「出局岗一归档，挖空的词就丢了产出记录」）。不传时退回
    `_cli.seen_of(doc)`：**老格式的库把条目直接摊在顶层**，取不到那个键
    就默默拿到一个空字典，然后一路往下报「里面没有职位」。

    ## 和 `late_misses` 是两个独立的漏法

    两套记账是分开写的（每个岗一个 `found_by`、每组查询一条 `query_log`），
    所以会各自独立地漏。实测活动用户 2026-08-23：

        08-13   56 个岗 · found_by 全有 · query_log **0 条**
        08-14  186 个岗 · found_by **全无** · query_log **0 条**

    只查 `found_by` 会漏掉 08-13 那一天。

    ## 少了它，工具会永远推荐同一个空格子

    这不是记账洁癖。`query_log` 的作用写在 `ran()` 的注释里：区分表里的
    `0`（跑了、没产出）和 `—`（还没跑过）。零产出的查询**不会留下任何岗**，
    于是没有 `found_by`；只要那一格还显示 `—`，「下一轮最值钱的格子」
    就会把它再推荐一遍 —— **永远推荐下去**，而抓取额度是这套系统里最稀缺的。

    ## 判据

    以**第一个留了 `query_log` 的日子**为界（在那之前这个机制还不存在），
    之后每一个「有岗（≥ `FULL_DAY_MIN`）却零条记录」的日子都算。
    与 `late_misses` 同一套界线思路：只报无从辩解的那部分。
    """
    logs: dict = defaultdict(int)
    for e in (doc.get("query_log") or []):
        d = str(e.get("date") or "")[:10]
        if d:
            logs[d] += 1
    if not logs:
        return {}
    first = min(logs)
    jobs: dict = defaultdict(int)
    for v in (seen if seen is not None else _cli.seen_of(doc)).values():
        if not isinstance(v, dict):
            continue
        d = str(v.get("first_seen") or "")[:10]
        if d:
            jobs[d] += 1
    return {d: n for d, n in sorted(jobs.items())
            if d > first and n >= FULL_DAY_MIN and not logs.get(d)}


def ran(doc: dict) -> set:
    """跑过的 (词, 平台) —— 只靠 `found_by` 是**看不见零产出的**。

    实测：`AI应用落地` 在猎聘返回 0 条。0 条就没有条目、没有 `found_by`，
    表里那一格仍然显示 `—`（没跑过），于是工具下一轮又把它当成
    「最值钱的空格子」推荐一遍——**永远推荐下去**。同理，翻到第 2、3 页
    只拿回重复项时也是新增 0，同样看不见。

    所以 `/job-scrape` 每跑一组查询就往 `query_log` 记一笔，无论产出多少。
    有了它，表里 `0`（跑了没产出）与 `—`（没跑过）才分得开——这个区分本身
    就是这张表存在的理由，分不开的话它给的建议是错的。
    """
    return {(e.get("query", ""), norm(e.get("portal")))
            for e in (doc.get("query_log") or []) if e.get("query")}


def is_high(r: dict) -> bool:
    """这个岗算不算「高匹配」——**判过的以判词为准，没判过的才退回抓取时的猜测**。

    原来只看 `fit == "high"`（抓取时按标题给的粗略标记）。2026-08-20 与 2026-08-23 两次拿全库对账：fit 说 202 个高匹配、判词说 128 个可投，**单岗错位 204 个**；
    按词看更糟——「研发效能」fit 报 27、判词只有 4，「AI应用落地」19 对 2，
    虚高 3-8 倍。词表的「最值钱的格子」就靠这一列推荐，等于一直被一个乐观的
    旧信号驱动，翻页翻进噪音层（p5-p7 命中率 0-2%）它还觉得这词值钱。

    ## 「命中率」说的是**顶两档**，不是「可投」

    这句原来没写清是哪个率，代价当场就有：复核时按「可投三档」
    重算得到 p5 6% · p6 13% · p7 11%，与 0-2% 差 5-10 倍，**差一点把一个
    正确的数字改掉**。两个口径在同一份语料上是这样（已评过的岗为分母）：

        页码      已评    可投三档    顶两档
        p1-p4    1442      18%       5.3%
        p5-p10    333      11%       1.5%    ← 顶两档 3/198，就是那句 0-2%

    **两个都要看，各答一个问题。** 顶两档答「深页还出不出直接能发的岗」——
    答案是基本不出；可投三档答「深页还值不值得抓」——11% 对 18%，
    是浅页的六成，**不是零**。把它读成零，会得出「永远别翻页」这个
    过头的结论；而额度紧张时该做的是「先把每个词的第 1 页跑遍，
    再回头翻深页」，不是把深页整个划掉。

    判词是评过 JD 的结论，fit 是评之前的猜测——有前者时用后者没有道理。
    """
    v = _cli.strip_triage(r.get("rank_verdict"))
    if v in _cli.VERDICTS:                    # 判过（五档之一）：以判词为准
        return v in _cli.VERDICTS[:2]
    if v:                                     # 硬门 FAIL / 已下线等：明确不是高匹配
        return False
    return r.get("fit") == "high"             # 真没判过：退回抓取时的标记


def stats(rows: list) -> tuple[int, int]:
    return len(rows), sum(1 for r in rows if is_high(r))


def n_home(rows: list) -> int:
    """这批岗里有几个是「主场」—— 专业能力够 **且** 行业经验对得上。

    ## 为什么这一列和「高匹配」不是一回事

    「高匹配」问的是**分够不够高**（能不能进短名单），主场问的是
    **行业经验对不对得上**。实测活动用户 2026-08-22，两者按词排序**几乎相反**：

        企业AI应用   已评 12 · 高匹配 5（42%） · 主场 0
        AI提效       已评  8 · 高匹配 5（63%） · 主场 1
        开发者工具    已评 12 · 高匹配 1（ 8%） · 主场 3（25%）

    两个比率的相关系数只有 **0.33**。只看高匹配的话，「企业AI应用」会被推荐，
    而它抓回来的 12 个岗**行业经验一个都对不上**；「开发者工具」会被判成弱词，
    而它是这批里主场率最高的。

    **两列都给，不替用户选。** 哪一列要紧取决于他现在卡在哪：短名单不够长时
    看高匹配，投出去没回音、而回音里多数是「行业对不上」时看主场
    （判据见 `export_web_data.applied_fit`）。

    分格与分界一律走 `gap_split`，不在这里另抄一份。
    """
    try:
        import gap_split as gs
    except Exception:
        return 0
    n = 0
    for r in rows:
        pair = gs.read_pair(r)
        if pair and gs.quadrant(*pair) == gs.HOME:
            n += 1
    return n


def _home_caveat(keep: list) -> str:
    """达标的词里，哪几个**一个主场岗都没抓到过**。没有就返回空串。

    「达标」只看高匹配率 —— 那回答的是「分够不够高」。而抓取额度是这套系统里
    最稀缺的东西，把它花在**扩张一个零主场的词**上，抓回来的会是更多
    「专业能力够、行业经验对不上」的岗（实测活动用户投出去的 63% 就是这一类，
    判据见 `export_web_data.applied_fit`）。

    **不从推荐里删掉它们** —— 短名单不够长时，分高的词照样有用；
    这两件事哪个要紧取决于他现在卡在哪（判据见 `n_home`）。
    这里只把话说出来，让那次额度的分配是**知情的**。
    """
    zero = [q for q, tot, _hi, hm in keep if hm == 0]
    if not zero:
        return ""
    # 强调用「」引号 + 破折号，不用 `**` —— 这段字既进 markdown 也进终端，
    # 而 `test_display_wording` 抓到过星号原样上屏（同本文件 `apply_block` 那条注释）。
    return ("\n> 上面这几个词分够高，但一个「主场」岗都没抓到过——"
            + "、".join(zero[:6])
            + "——抓回来的多半还是「你能干、但行业经验对不上」那类。"
            "短名单不够长时它们照样有用；要是你正卡在「投出去没回音」上，"
            "这几个词就先别往新平台上扩了。\n")


#: `研发效能 p6` 里的 ` p6` 是**翻页**，不是另一个查询词。
_PAGE = re.compile(r"\s*p\d+$")


def base_query(q: str) -> str:
    """把翻页并回主词。`研发效能 p6` → `研发效能`。"""
    return _PAGE.sub("", q).strip()


def merge_pages(by: dict) -> dict:
    """`{词: {平台: [条目]}}` 按主词合并。

    **表格照旧一页一行**（翻到第几页、哪一页开始颗粒无收，那是真信息），
    **但所有结论都用这份合并视图**。此前只有「该停一停的词」并了，
    「达标」和「下一轮最值钱的格子」没并 —— 同一份报告里两个分母。

    代价实测（2026-08-23，活动用户）：不并时达标 3 个词，其中两个是**页**——

        AI原生 p2      16 抓 4 高匹配 = 25% ✓     而 AI原生 整词 50 抓 6 = 12%
        企业AI应用 p3  10 抓 4 高匹配 = 40% ✓     而整词 87 抓 11 = 13%

    于是报告推荐「AI原生 p2 × 前程无忧」——**这条指令跑不了**：
    `-q "AI原生 p2"` 搜的是「AI原生 p2」这个字符串。9 个推荐格子里
    6 个建立在一页的运气上。（`is_runnable` 本来就是为「粘到 CLI 里只会报错」
    的来源设的，但它只挡了「账号求职期望(...)」那一类。并页之后，
    带页码的串根本到不了那里。）

    扩到一个新平台时跑的是**词**、从第 1 页开始，所以能预测产出的是整词的
    命中率，不是某一页的。反过来同理：一个词被拆成七八行，每行都不够
    `MIN_NEW`，真正高产的词也永远达不了标 —— 那正是停用清单那段注释
    已经写下的理由，只是当时只修了它自己那一半。
    """
    out: dict = {}
    for q, per in by.items():
        acc = out.setdefault(base_query(q), {})
        for portal, rows in per.items():
            acc.setdefault(portal, []).extend(rows)
    return out


def next_cells(by: dict, keep: list, ran_pairs: set = frozenset()) -> list:
    """达标的词 × 还没跑过的平台 —— 下一轮的行动项。

    **判「跑过没有」要用合并视图。** 拿 `by` 直接查会说「`AI原生` 没在猎聘
    跑过」（跑过的是 `AI原生 p2`），于是推荐一个已经挖过的格子。
    `ran_pairs`（跑过但零产出）同理按主词折一遍。

    单独成函数是因为它**必须被测试打到**：这段逻辑原来内联在 `main` 里，
    测试只能照抄一份来验 —— 抄件不会跟着生产代码变，两处折页判据分叉时
    它照样绿（2026-08-23 变异实测，两条断言就是这么空转的）。
    """
    merged = merge_pages(by)
    ran_base = {(base_query(q), p) for q, p in ran_pairs}
    return [(q, p) for q, *_ in keep if is_runnable(q)
            for p in PORTALS
            if p not in merged.get(q, {}) and (q, p) not in ran_base]


def render(by: dict, ran_pairs: set = frozenset()) -> tuple[str, list]:
    lines = ["| 查询词 | " + " | ".join(PORTALS) + " | 累计 | 其中高匹配 | 其中主场 |",
             "|---|" + "---|" * (len(PORTALS) + 3)]
    keep = []
    order = sorted(set(by) | {q for q, _ in ran_pairs},
                   key=lambda q: -sum(len(v) for v in by.get(q, {}).values()))
    for q in order:
        cells, tot, hi, hm = [], 0, 0, 0
        for p in PORTALS:
            if p not in by.get(q, {}):
                # `0` = 跑过、没产出；`—` = 还没跑过。分不开的话建议就是错的。
                cells.append("0" if (q, p) in ran_pairs else "—")
                continue
            n, h = stats(by[q][p])
            cells.append(str(n))
            tot += n
            hi += h
            hm += n_home(by[q][p])
        lines.append(f"| {q} | " + " | ".join(cells) + f" | {tot} | {hi} | {hm} |")
    # **达标按主词算，不按行算**（判据与实测代价见 `merge_pages`）。
    # 表格一页一行是有意的；结论跟着行走，就会把「某一页的运气」当成词的产出，
    # 然后推荐一条粘进 CLI 会搜到空的指令。
    for q, per in merge_pages(by).items():
        tot = hi = hm = 0
        for rows in per.values():
            n, h = stats(rows)
            tot += n
            hi += h
            hm += n_home(rows)
        if tot >= MIN_NEW and hi / tot >= MIN_HIGH_RATE:
            keep.append((q, tot, hi, hm))
    keep.sort(key=lambda k: -k[1])
    return "\n".join(lines), keep


#: 用户自己写的查询行里的城市。`-l` 收中文城市名（见 profile.example 的说明）。
_CITY = re.compile(r'-l\s+"([^"]+)"')


def primary_city(target: Path) -> str:
    """从用户那份 `search-queries.md` 里取目标城市。

    **只看自动维护块之外**的行：块里的城市正是本工具上次写进去的，拿它当来源
    就是自我循环——错一次就永远错下去。块外那部分归用户，`/job-setup` 按他的
    目标城市生成。

    取不到就返回空串，由调用方决定怎么办——**不要在这里编一个**。写死一个城市
    的代价实测过：北京的用户跑一次 `--apply`，自动维护块里那几条命令全变成搜
    上海，他照着敲抓回来的岗一个都不对口。
    """
    if not target.is_file():
        return ""
    text = target.read_text(encoding="utf-8")
    if BEGIN in text:
        tail = text.split(END)[-1] if END in text else ""
        text = text.split(BEGIN)[0] + tail
    seen = [c.strip() for c in _CITY.findall(text)]
    # 占位符（`[YOUR_PRIMARY_CITY]`）是「还没填」，不是城市。
    seen = [c for c in seen if c and not c.startswith("[")]
    if not seen:
        return ""
    return max(seen, key=lambda c: (seen.count(c), -seen.index(c)))


def home_note(home: int, long: bool = False) -> str:
    """待停的词旁边那半句「其中 N 个是主场」。0 个就返回空串。

    **两个消费方共用这一个**：终端那份要短，写回 `search-queries.md` 的
    那份要把「主场」解释一次（下一轮读它的人手边没有这份文档）。
    措辞可以不同，但**「0 个不印」这条判据只能有一份** —— 各写一遍，
    迟早一边印出「其中 0 个是主场」这种纯噪音。

    （第一版就是各写一遍的，而给它写的测试**把格式逻辑在测试里又抄了一遍**，
    于是变异「0 个也印」照样绿 —— 那条测试在测它自己。）
    """
    if not home:
        return ""
    if long:
        return f"，但其中 {home} 个是主场（专业能力与行业经验都对上）"
    return f"  其中 {home} 个是主场"


def dead_ends(by: dict) -> list[tuple[str, int]]:
    """抓够 `DEAD_MIN_N` 个、而可投的一个都没出的词。

    按**词本身**合计（把「研发效能 p6」这类翻页并回主词），否则一个词被拆成
    七八行，每行都不够 `DEAD_MIN_N`，于是永远报不出来。

    **这个函数原来长在 `main()` 里。** 抽出来是因为它的结果此前只 print 到终端，
    而下一轮真正被读的是 `search-queries.md` —— 见 `build_block` 里那一段。
    """
    merged: dict = {}
    for base, per in merge_pages(by).items():
        acc = merged.setdefault(base, [0, 0, 0])
        for _p, rows in per.items():
            # `by[词][平台]` 存的是**条目列表**，不是算好的 (n, hi)。
            # 数由 `stats()` 出——它顺带用的是 `is_high()`（判过的以判词为准，
            # 没判过的才退回抓取时那个乐观的 fit 标记）。自己在这儿数一遍，
            # 早晚和它分叉。
            n, hi = stats(rows)
            acc[0] += n
            acc[1] += hi
            # **主场也一并数出来。** 停用判据不看它（只按「可投一个都没出」），
            # 但报告要把它摆出来 —— 这个工具的立场是「给的是事实，不是判决」，
            # 而 `n_home` 自己的文档写着：两个比率的相关系数只有 0.33，
            # 「投出去没回音、而回音里多数是行业对不上时看主场」。
            #
            # 实测活动用户 2026-08-27：13 个待停的词里 1 个出过主场岗
            # （`AI工具`，47 抓里 1 个）。只报「可投 0」的话，用户会把它和
            # 另外 12 个一起停掉 —— 而那一个是专业能力与行业经验都对上的。
            acc[2] += n_home(rows)
    return sorted(((q, n, home) for q, (n, hi, home) in merged.items()
                   if n >= DEAD_MIN_N and hi == 0), key=lambda x: -x[1])


def hit_rate(by: dict) -> float:
    """全库平均命中率 —— 「该停一停」那句话的参照系。"""
    merged: dict = {}
    for base, per in merge_pages(by).items():
        acc = merged.setdefault(base, [0, 0])
        for _p, rows in per.items():
            n, hi = stats(rows)
            acc[0] += n
            acc[1] += hi
    tot = sum(n for n, _ in merged.values())
    return sum(hi for _, hi in merged.values()) / max(1, tot)


def build_block(by: dict, today: str, miss: int, ran_pairs: set = frozenset(),
                city: str = "", late: dict | None = None,
                dead: list | None = None, gaps: list | None = None,
                rate: float = 0.0) -> str:
    table, keep = render(by, ran_pairs)
    # 城市由调用方从用户资料里取（见 `primary_city`），**不在这里写死**：
    # 本函数每次 --apply 都会重写每个用户的自动维护块，写死一个城市等于让
    # 别的城市的用户照着敲一串搜错地方的命令，而且重跑还会再写回去一次。
    # 取不到就**不给 `-l`**——端一条城市错的命令出去，比不端更坏。
    loc = f' -l "{city}"' if city else ""
    runnable = "\n".join(f'-q "{q}"{loc}' for q, *_ in keep if is_runnable(q))
    # 这几句最终落进 markdown 文件，不是终端。但 `test_display_wording` 扫的是
    # `tools/*.py` 里**所有**非 docstring 的中文字面量（它故意放宽过，因为有一类
    # 文案是「先 return 再由别处打印」的）。与其为本文件开个例外把那道闸放松——
    # 它真抓到过 `**` 原样上屏——不如按它建议的中文强调办法写：「」引号 + 破折号。
    note = ""
    if miss:
        note = (f"\n> 库里还有 {miss} 个岗没有 `found_by`。它们不进上表"
                f"——「上表只反映测得到的部分」，不是全部历史。\n")
        # **「本字段是后加的，更早抓的补不上」原来是无条件写死的一句安慰。**
        # 它把两件事混成一件：字段还不存在时抓的（确实补不上），和字段
        # 已经在用、却仍然漏记的（那是回退，要修）。前者无关紧要，后者
        # 正是本仓库反复点名的最贵错法 —— 把「上游丢了数据」说成
        # 「核对过没问题」。判据与实测见 `late_misses`。
        n = (late or {}).get("n", 0)
        days = (late or {}).get("days", {})
        if n:
            when = "、".join(f"{d} 漏 {c} 个" for d, c in list(days.items())[:4])
            more = "…" if len(days) > 4 else ""
            note += (f">\n> 其中 **{n} 个不是历史遗留**：它们抓到的时候这个"
                     f"字段已经在用了，是漏记（{when}{more}）。上表算不到"
                     f"它们，而这张表决定下一轮把抓取额度花在哪 —— 先看那"
                     f"几天跑的是哪条路径，判据见 `job-scrape.md` 的"
                     f"「`found_by`」那一节。\n")
    # ── 「别再跑什么」和「下一轮跑哪一格」也要落盘 ──
    #
    # **这两段原来只 print 到终端。** 而下一轮真正被读的是这个文件：
    # `job-scrape.md` Step 1b 写着「把 `profile/search-queries.md` 里的查询词，
    # 翻成这个渠道认的参数形式」—— 终端那份输出只活在跑它的那一次会话里。
    #
    # 代价是可量的：实测活动用户 2026-08-24，12 个词抓够 15 个而可投一个都没出，
    # 合计白抓 267 个岗 —— 按每次请求隔 8 秒算，约等于 36 分钟的抓取时间。
    # 更要命的是上面那句「`—` 通常是下一轮最值钱的格子」：它是对整张表说的，
    # 而那 12 个死词各自还空着两三格 —— 照着读，最没用的词反而成了最值钱的格子。
    # 真正过滤好的那份交叉清单（达标词 × 未跑平台）同样只在终端里。
    #
    # 这是本仓库反复出现的那一族：算了没显示、存了没人读。
    dead = dead or []
    gaps = gaps or []
    stop = ""
    if dead:
        waste = sum(n for _q, n, _h in dead)
        rows = "\n".join(
            f"- 「{q}」抓了 {n} 个，可投 0"
            + home_note(home, long=True)
            for q, n, home in dead[:10])
        stop = (
            f"\n该停一停的词（抓够 {DEAD_MIN_N} 个、可投的一个都没出）：共 "
            f"{len(dead)} 个，合计白抓 {waste} 个岗 —— 按每次请求隔 "
            f"{GAP_HINT_S} 秒算，约等于 "
            f"{max(1, round(waste * GAP_HINT_S / 3600))} 小时的抓取时间。\n\n"
            f"{rows}\n\n"
            f"> 上面那句「`—` 是下一轮最值钱的格子」对这几个词不成立 —— "
            f"它们空着的格子是「还没在那儿浪费过」，不是机会。\n"
            f">\n"
            f"> 这不是判决：全库平均命中率只有 {rate:.0%}，一个中等的词也常在"
            f"十几个里颗粒无收。数给你，停不停你定 —— 你比它更清楚自己这一行的词。\n")
    nxt = ""
    if gaps:
        cells = "\n".join(f"- {q} × {pf}" for q, pf in gaps[:12])
        more = f"\n\n（还有 {len(gaps) - 12} 个没列）" if len(gaps) > 12 else ""
        nxt = (f"\n下一轮最值钱的格子（只列达标的词 × 还没跑过的平台，共 "
               f"{len(gaps)} 个）：\n\n{cells}{more}\n")
    # **指路只在真有那一节时才写。** 一句「先看下面那一节」而下面没有那一节，
    # 比不写更坏 —— 读的人会以为自己漏看了，或者以为块被截断了。
    # 这条是这次改动自己的守卫测试当场抓到的：`dead` 为空时那半句照写。
    # 用「」和破折号强调，**不用 markdown 粗体** —— `test_display_wording`
    # 扫本文件所有非 docstring 的中文字面量，它真抓到过 `**` 原样上屏。
    # 这段最终落进 markdown 没错，但那道闸看不出去向，上面 `note` 那段
    # 的注释里已经把这一课写过一遍了 —— 我照写了一遍 `**`，当场被逮到。
    look = ("先看下面「该停一停」那一节 —— 已经证明挖不出东西的词，"
            "它空着的格子不算机会。" if dead else "")
    return (
        f"{BEGIN} 本块由 tools/query_yield.py 写入，手改会被覆盖。\n"
        f"     要长期固定某个词，写到上面的「优先级」分类里——那块归你。 -->\n"
        f"### 实测产出（自动维护 · 最近更新 {today}）\n\n"
        f"每个词在每个平台带来过多少个「新」岗、其中多少个匹配度高。\n"
        f"`—` 表示「这个词在这个平台还没跑过」——那通常是下一轮最值钱的格子，\n"
        f"别把它当成「跑了没产出」。{look}\n\n"
        f"{table}\n{note}\n"
        f"近期产出达标的（新增 ≥{MIN_NEW} 且高匹配占比 "
        f"≥{int(MIN_HIGH_RATE*100)}%），"
        f"下一轮优先跑：\n\n```\n{runnable}\n```\n{nxt}{stop}\n{END}"
    )


def write_back(p: Path, block: str) -> str:
    text = p.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        head = text[:text.index(BEGIN)]
        tail = text[text.index(END) + len(END):]
        return head + block + tail
    # 首次写入：插在「查询分类」这一节的开头，紧挨着人工维护的优先级列表
    m = re.search(r"^##\s*查询分类\s*$", text, re.M)
    if not m:
        return text.rstrip() + "\n\n" + block + "\n"
    i = text.index("\n", m.end()) + 1
    return text[:i] + "\n" + block + "\n" + text[i:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="量出每个搜索词的实际产出，并写回 search-queries.md。"
                    "不加 --apply 就是试运行。")
    ap.add_argument("--apply", action="store_true", help="真的写回 search-queries.md")
    ap.add_argument("--user", help=_cli.HELP_USER)
    ap.add_argument("--today", default="", help="写进标题的日期（默认从库里最新 first_seen 取）")
    args = ap.parse_args(argv)
    # **在任何一条早退之前就验。** 这几个工具都有「只报不写」的那条路，
    # 验证挪到写盘那一步的话，敲错日期的人会先拿到一份看着正常的输出
    # （实测 2026-09-01：`applied_jds --today 不是日期` 退出码 0）。
    _today = _cli.parse_today(args.today)

    user = _cli.pick_user(args.user or "", root=ROOT)
    store = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not store.is_file():
        raise SystemExit(_cli.no_store(store))
    doc = _cli.read_json(store)
    # **走 `_cli.seen_of`，别自己写 `doc.get("seen", doc)`。** 扁平格式的职位库顶层
    # 还住着 `query_log` 这个旁路数据（它必须留在那儿，见
    # `tests/test_the_ingest_is_the_only_way_in.py`），而下面 `collect(seen)` 按
    # 「顶层每个值都是岗位」遍历 —— 2026-10-13 实测：自己写这一行就是一次
    # `AttributeError: 'list' object has no attribute 'get'`。
    # `seen_of` 是收口处，它认得这两代格式，也会隐去非岗位的键。
    seen = _cli.seen_of(doc)
    # **归档的岗也要算进产出。** 词表量的是「这个词在这个平台带来过什么」——
    # 那是历史，不随岗位出局而消失。只读热库的话，出局岗一归档，
    # 挖空的词就丢了产出记录，下一轮又被推荐成「最值钱的格子」，
    # 正是 `query_log` 那节要防的「永远推荐下去」。
    # 读存档走 `_cli.archived`：读文件、解析、兜住坏文件那三步不在这里重写一遍
    # （它自己的 docstring 里记着「第三个该问的地方压根没问」那次事故）。
    seen = {**_cli.archived(user, root=ROOT), **seen}   # 同键以热库为准（它更新）

    by, have, miss = collect(seen)
    late_n, late_days = late_misses(seen)
    # **这句要在最前面、要走 stderr。** `/job-scrape` Step 4.6 每轮收尾都跑本工具
    # ——那正是发现漏记的时机：AI 此刻还记得哪个词搜到了什么，补得回来；
    # 等下一轮再看，那批岗已经没人认得出来源了（实测活动用户 2026-08-23：
    # 08-14 那 186 个就是这样，
    # 9 天没人发现）。埋在写回块的脚注里等于没报。
    #
    # **不改退出码。** `/job-auto` 把这一步串在链子里，退出码非 0 会让整条链
    # 停在一个「数据不全」而不是「跑不动」的问题上；这里给的是要人补的事实，
    # 不是闸门 —— 与本文件「只报不删」同一条分寸。
    gaps = unlogged_rounds(doc, seen)
    if late_n or gaps:
        print("⚠ 这份职位库有几笔抓取没留下记账，下面那张表算不到它们：",
              file=sys.stderr)
        if late_n:
            when = "、".join(f"{d} 漏 {c} 个" for d, c in late_days.items())
            print(f"  · {late_n} 个岗没记「是哪个词搜到的」（{when}）",
                  file=sys.stderr)
        if gaps:
            when = "、".join(f"{d} 抓了 {c} 个" for d, c in gaps.items())
            print(f"  · 有 {len(gaps)} 天抓了岗却没留查询记录（{when}）"
                  f"——那些词在表里会一直显示成「还没跑过」，"
                  f"下一轮还会再推荐一遍", file=sys.stderr)
        print("  判据与补法见 `workflows/job-scrape.md` 的"
              "「`found_by`」「`query_log`」两节。\n", file=sys.stderr)
    if not by:
        print("库里没有一个岗记着「是哪个词搜到的」（`found_by`）——")
        print("这一轮 /job-scrape 落库时把查询词一起写进去，下次就能量了。")
        return 0

    today = _today.isoformat() if _today else max(
        (v.get("first_seen") or "" for v in seen.values()), default="")
    ran_pairs = ran(doc)
    table, keep = render(by, ran_pairs)
    # 终端这一侧和写回块里那句是**同一件事**，两处都要说实话 ——
    # 只改一处的话，读报告的人和读文件的人各拿到一个版本。
    tail = ""
    if late_n:
        tail = (f"，其中 {late_n} 个是漏记的（抓它们的时候这个字段已经在用了，"
                f"最近一次 {max(late_days)}）")
    print(f"有来源的 {have} 个 · 没来源的 {miss} 个{tail}\n")
    print(table)
    print(f"\n达标（新增 ≥{MIN_NEW} 且高匹配 ≥{int(MIN_HIGH_RATE*100)}%）："
          f"{len(keep)} 个词")
    # **达标只看分够不够高，看不见「行业对不对」。** 那句提醒本来就写好了
    # （`_home_caveat`），却从来没有人调用它 —— 全仓库只有测试在调，
    # 而那组测试把它的行为验得很细，偏偏没有一条问「谁在用它」。
    # 同一个文件里 `n_home` 那组就有这一条（`render 没调它`），两组不对称。
    # 这一族在本仓库反复出现：算了没显示、存了没人读。
    #
    # 位置贴在「达标」下面：那一行说「这几个词值得往新平台上扩」，
    # 这一行说「其中这几个扩出来的多半还是行业对不上的」——挨着才有意义。
    print(_home_caveat(keep), end="")

    # ── 反过来那一半：哪几个词该停一停 ──
    # 上面那节回答「下一轮跑什么」，这节回答「别再跑什么」。缺了后者，
    # 低质词会一轮一轮地烧额度，而额度是这里最稀缺的资源。
    # 按**词本身**合计（把 `研发效能 p6` 这类翻页并回主词），否则一个词
    # 被拆成七八行，每行都不够 `DEAD_MIN_N`，于是永远报不出来。
    # 算法在 `dead_ends` / `hit_rate` 里 —— 抽出去是因为**写回那份也要用它**，
    # 而它原来只长在这里、只 print 到终端。
    dead = dead_ends(by)
    rate = hit_rate(by)
    if dead:
        waste = sum(n for _q, n, _h in dead)
        print(f"\n该停一停的词（抓够 {DEAD_MIN_N} 个、可投的一个都没出）："
              f"{len(dead)} 个，合计白抓 {waste} 个岗")
        for q, n, home in dead[:10]:
            print(f"  {q}  抓 {n}  可投 0{home_note(home)}")
        print(f"  —— 每次请求要隔 {GAP_HINT_S} 秒，这 {waste} 次"
              f"约等于 {max(1, round(waste * GAP_HINT_S / 3600))} 小时的抓取时间。")
        print(f"  这不是判决：全库平均命中率只有 {rate:.0%}，一个中等的词也常在"
              f"十几个里颗粒无收。数给你，停不停你定——你比它更清楚自己这一行的词。")

    # 「在某个平台还没跑过」的格子——下一轮的行动项，别让它只躺在表里
    gaps = next_cells(by, keep, ran_pairs)
    if gaps:
        print(f"\n下一轮最值钱的格子（达标的词 × 还没跑过的平台，共 {len(gaps)} 个）：")
        for q, p in gaps[:12]:
            print(f"  {q} × {p}")

    target = ROOT / "users" / user / "profile" / "search-queries.md"
    if not target.is_file():
        print(f"\n⚠ 没有 {target}，跳过写回")
        return 0
    if args.apply:
        # search-queries.md 里有用户**亲手校准**的优先级块——原子写，不许先截断
        # （`_cli.atomic_write` 的说明里有这一课的全文）。
        _cli.atomic_write(
            target,
            write_back(target, build_block(by, today, miss, ran_pairs,
                                           primary_city(target),
                                           late={"n": late_n,
                                                 "days": late_days},
                                           dead=dead, gaps=gaps, rate=rate)))
        print(f"\n已写回 {target.relative_to(ROOT).as_posix()} 的自动维护块")
    else:
        print(chr(10) + _cli.DRY_RUN_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
