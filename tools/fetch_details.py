#!/usr/bin/env python3
"""按节流抓职位详情，**撞风控立刻停手**，抓到的当场存进详情库。

## 为什么要有这个文件

`cdp-portals.md` 的账号安全铁律写着：撞验证码 / 风控提示就**立即停止、不重试硬闯**。
但这段逻辑一直是每次临时写的，于是写错过一次——

    r = subprocess.run([...], capture_output=True)
    try:
        d = json.loads(r.stdout)          # ← 错误不在 stdout
    except json.JSONDecodeError:
        continue                          # ← 于是限流被当成「解析失败」跳过
    if d.get("code") == "RATE_LIMITED":   # ← 永远走不到这里
        break

`liepin-search` CLI 的错误走的是 **stderr + 退出码 1**，stdout 是空的。上面那段
只看 stdout，结果第一个就撞限流的一批 13 个 URL **全部发了出去**，一个都没停。

**安全机制不能靠每次现写。** 所以固化在这里，并由测试盯住「撞限流必须停」。

## 用法

    python tools/fetch_details.py --missing              # 试运行：列出缺 JD 的职位
    python tools/fetch_details.py --missing --apply      # 真抓，抓到就存
    python tools/fetch_details.py --urls a.txt --apply

只处理**猎聘**的链接：BOSS 的详情页返回加载页、前程无忧撞阿里云 WAF、智联需要
登录态，那三家走浏览器渠道（见 `workflows/reference/cdp-portals.md`），不在这里。

零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import collections as _collections
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

import datetime as _dt  # noqa: E402
import jd_store as st  # noqa: E402
import portal_budget as pb  # noqa: E402
#: 判词出局与否只有一个定义，在 `doctor` 里（那个文件是依赖链的底，
#: 只用标准库、不 import 仓库里的任何模块，所以反过来 import 它是安全的）。
from doctor import is_out_verdict  # noqa: E402

CLI = ".agents/skills/liepin-search/cli/src/cli.ts"

#: 不给 `--limit` 时这一轮抓几个。
#:
#: **原来没有默认值** —— `main()` 里是 `if args.limit: entries = entries[:limit]`，
#: 不给就是**一个不落全抓**。而这个工具只打猎聘 CLI 那条通道，
#: 它恰好是会限流、且封了要用户**换网络出口 IP** 才解得开的那条
#: （`portal_budget` 里那段实测：到点换的还是同一个 IP，探一次限一次）。
#:
#: 更糟的是被推荐的形态：`audit_pipeline` 与 `applied_jds` 两处印给用户的都是
#: `python tools/fetch_details.py --recheck --apply` —— **带 `--apply`、不带上限**。
#: 而同一个仓库的 `job-rank.md` 那张「通道决定批大小」表写着：
#: 猎聘 CLI 的 detail「每批 **12**，撞到就停」。
#: 印出来的命令和写下来的规矩对不上，而印出来的那条才是真会被敲的。
#:
#: 12 取自那张表，不是新拍的。要多抓自己加 `--limit`。
#: （撞风控立刻停手那一层照旧 —— 那是最后一道网，不是限量。）
DEFAULT_LIMIT = 12

#: 浏览器通道每轮取几个。取自 `job-rank.md`「通道决定批大小」那张表的实测值：
#: 猎聘详情页走浏览器**实测不限**（同一页 CLI 报限流、浏览器正常返回 2821 字正文），
#: 表里写「可放大到 20-30」，取中间的 25；其余三家「15 左右，低频」。
#:
#: **这几个数不是新拍的，是把已经写下来的规则接进代码。** 在此之前那张表只存在于
#: 文档里，代码里唯一的数是上面那个 12 —— 而它是为一条**会限流的 CLI 通道**定的。
BROWSER_BATCH = {"liepin-browser": 25}
BROWSER_BATCH_DEFAULT = 15

#: 这个工具够得着的那一个渠道标记。**只收猎聘** —— 其余三家的 JD 只能在
#: 抓取当次的浏览器访问里取（`cdp-portals.md` 第 6 条）。
#:
#: 起这个名字是因为它有第二个读者：`audit_pipeline` 的「判词自称读过 JD」
#: 那条要拿它把「够得着的」和「够不着的」分开报。字面量抄一份过去，
#: 就是又一处会各自漂的渠道表。
CLI_PORTAL = "liepin-search"

#: 请求间隔。CLI 内置的 1.5 秒节流是**进程内**的，跨进程调用时不生效，要自己保证。
#:
#: **从闸门取，别在这儿再写一个数。** 这里原来写死 2.0 秒，而
#: `portal_budget.GAP_S` 给 fetch 类动作定的是 4 秒 —— 同一件事两个说法，
#: 而 2026-08-26 删掉固定额度之后，**间隔是仅剩的那道密度闸门**
#: （本人裁定：「没有固定额度的……应该是控制单渠道每次访问的间隙时间」）。
#: 唯一的控制有两个数，等于没有控制。
INTERVAL_S = pb.gap_for("fetch")

#: 撞到这些错误码就**立刻停**，不继续、不重试。
STOP_CODES = {"RATE_LIMITED"}


def runtime_argv(exe: str) -> list[str]:
    """把可执行文件拼成调用前缀。**两个运行时的命令形状不同**：
    `bun run <file>` 有 `run` 子命令，`node <file>` 没有——拼错就是一个 127。"""
    return [exe, "run"] if "bun" in Path(exe).name.lower() else [exe]


def find_runtime() -> list[str]:
    """找一个能跑 CLI 的运行时，**node 优先**。

    全仓口径一致：node 是默认路径（AI 编码工具走 npm 安装，Node 必然已存在），
    bun 是可选。这里原来只找 bun、找不到就 `SystemExit`——于是一台只有 Node 的
    机器上，自检说「一切就绪、Bun 不需要」，抓详情这一步却直接死掉，报的还是
    「装了才能跑」，而用户刚被告知不用装。
    """
    for name in ("node", "node.exe"):
        exe = shutil.which(name)
        if exe:
            return runtime_argv(exe)
    for name in ("bun", "bun.exe", "bun.CMD"):
        exe = shutil.which(name)
        if exe:
            return runtime_argv(exe)
    p = Path.home() / ".bun" / "bin" / "bun.exe"
    if p.is_file():
        return runtime_argv(str(p))
    raise SystemExit("node 与 bun 都找不到 —— 装其中一个才能跑 liepin-search CLI。"
                     "推荐 Node（https://nodejs.org），装了 AI 编码工具通常就有；"
                     "跑一次 python tools/doctor.py 看当前环境。")


def parse_result(proc: subprocess.CompletedProcess) -> dict:
    """把 CLI 的输出解析成 dict。

    **两个流都要看。** 成功走 stdout，错误走 stderr + 退出码 1。只看 stdout 会把
    错误当成「解析失败」——限流就是这么被漏掉的。
    """
    for stream in (proc.stdout, proc.stderr):
        if not (stream or "").strip():
            continue
        try:
            d = json.loads(stream)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            return d
    return {"error": f"CLI 输出无法解析（退出码 {proc.returncode}）",
            "code": "UNPARSEABLE"}


def fetch_one(runtime, url: str, timeout: int = 90) -> dict:
    """`runtime` 是 `find_runtime()` 给的 argv 前缀，不是一个可执行名——
    node 与 bun 的命令形状不同，前缀里已经含好了各自该带的子命令。"""
    proc = subprocess.run(
        [*runtime, CLI, "detail", url, "--format", "json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(ROOT))
    return parse_result(proc)


def needs_recheck(e: dict) -> bool:
    """判过、但判据没经过 JD 正文复核的条目。

    框架规定（04「判据只认 JD 正文」）：预筛/字段判的硬门，抓到 JD 后**必须复核**。
    但第一版这个工具只抓 `status == "new"` 的——被判过的条目永远不会被抓 JD，
    复核规则永远不触发。上一轮 8 个错判的硬门 FAIL 正是从这种「写了规则、
    没接管道」的缝里漏出来的。
    """
    b = e.get("rank_breakdown") or {}
    # 「未抓 JD」按**包含**匹配，不按精确串——2026-08-20 实测库里有 32 条
    # 「粗筛（未抓 JD）」，精确匹配「预筛（未抓 JD）」把它们整批漏出复核队列。
    # 这正是 test_verdict_cap 批判过的形状：「读过」vs「读了」一字之差漏 613 条。
    # `来源` 是自由文本，判它只能按语义片段，不能按整串。
    # **「没读过正文」有好几种说法，这里要全收。** 只认「未抓 JD」时，
    # 实测活动用户 2026-08-24（猎聘·已评·库里无正文的那批）漏掉两类：
    #
    #     粗筛（标题即判据）              129 个  ← 它明说了只看标题
    #     粗筛（历史条目，来源未记录）        56 个  ← 不知道判据硬不硬
    #
    # 第一类最刺眼：这个函数的 docstring 说的就是「判据没经过 JD 正文复核」，
    # 而那句措辞是它最直白的自白。上面那条注释已经学过一次「按语义片段判、
    # 不能按整串」（「粗筛（未抓 JD）」vs「预筛（未抓 JD）」），
    # 却仍然只盯着同一个词根 —— 换个说法就又漏一批。
    #
    # 「来源未记录」也算：**不知道硬不硬，就当不够硬**。复核一次的代价是
    # 一次请求，漏一个错判的代价是一个岗白扔。
    src = str(b.get("来源", ""))
    return ("未经" in str(b.get("证据", ""))
            or "未抓 JD" in src
            or "标题即判据" in src
            or "来源未记录" in src)


def judged_without_stored_body(user: str, e: dict) -> bool:
    """判词自称「读过 JD 正文」，而详情库里查无此条。

    **这类最难发现**：`needs_recheck` 按 `来源` 的措辞判，而这些条目的措辞恰恰是
    「读过 JD 正文」——它自称已复核，于是从复核队列里整个漏出去。
    2026-08-20 实测 283 个，`needs_recheck` 一个都不认。

    真相是 JD 当时确实读过，但在会话里读完就扔了（早期的浏览器路径、以及不走
    `jd_store` 的直读）。后果不是「少存一份」：面试前回查、`/job-upskill` 算差距、
    深评复查原文全都拿不到，而且**没有任何人知道该去补**——判词看起来是可信的。

    与 `needs_recheck` 分开定义：那个问「判据够不够硬」，这个问「证据还在不在」。
    两个问题的答案可以相反，合并只会让其中一个被另一个吞掉。
    """
    # **深评回写那一类也算。** 实测活动用户 2026-08-24：32 个条目的来源写的是
    # 「深评（writeback.py 从 evaluation.md 回写）」—— 深评当然读过 JD 正文
    # （那是 `/job-apply` 的活），只是这条路把结论写回了库、没把正文留下。
    # 它既不说「未抓 JD」（上面那个函数不认），也不说「读过 JD」（这里不认），
    # **正好落在两个判据之间**。而这个函数问的是「证据还在不在」——
    # 按事实该收，按措辞才漏。
    #
    # 上面 docstring 里那句「「靠不住」有两种」写于 2026-08-20，
    # 那时只见过两种；写死「两种」正是这类枚举最容易过期的地方。
    src = str((e.get("rank_breakdown") or {}).get("来源") or "")
    if "读过 JD" not in src and "深评" not in src:
        return False
    return not st.has_body(st.load(user, e.get("url") or "", e.get("title") or ""))


def missing_by_portal(user: str) -> dict:
    """缺 JD、还活着的岗按渠道分布。**给报告用，让「补不了的那批」说得出来。**

    2026-08-20 实测：缺 JD 且还活着的 1116 个里，只有 724 个是猎聘、这个工具够得着；
    另外 392 个分散在 BOSS/智联/前程无忧的六种 portal 标记下，**没有任何工具会去补**
    ——它们只能在下次抓取的同一次浏览器访问里顺手取。
    不报出来的话，跑完这个工具会显得「缺 JD 的都补了」，而实际差着三分之一。
    """
    return {p: len(v) for p, v in _missing_alive(user).items()}


def _missing_alive(user: str) -> dict:
    """`{portal: [entry, ...]}` —— 缺 JD、**还活着**的岗。计数与列表共用这一份。

    **「还活着」是这里唯一的判据，而它必须读叠加层。** 用户在总览页点的
    「不投 / 已下线」只写进 `user_state.json`，库里那条仍是 `ranked`；
    只读裸 `status` 就会把他已经否掉的岗列进待办。
    实测活动用户 2026-08-25：这个报告说 1120 个岗还活着，带上叠加层是 1118。

    ## 「还活着」也包括「还没被判死」

    上面那段只挡住了 `status` 与叠加层这两条出局路径，**漏了第三条：预筛/粗筛
    已经结案的岗**。它们的 `status` 仍是 `ranked`、用户也没点过什么，但判词已经
    是「跳过 / 不建议 / 硬门没过」—— 再去抓一次 JD 不会改变任何决定。

    实测 2026-08-27 一次 `/job-auto`：`--browser-list` 给出 549 个待办，其中
    **362 个（三分之二）已经结案**（跳过 273、硬门 FAIL 39、不建议 23……），
    而队首连着三条都是同一轮 `prescreen --apply` 刚判为「这家的这个岗你已经投过」
    的岗 —— 照名单走，头三次浏览器访问全花在了已经结案的岗上。

    浏览器那条一次只能开一个页面、还有间隔闸门，**名单里每一条假货都是一次
    真实的额度**。这正是本函数存在的理由（见 `browser_todo` 的 docstring：
    手挑会漏掉叠加层）—— 只是当时只想到了叠加层这一条。

    ## 第三条出局路径现在由**调用方**挡

    本函数只滤 `expired` / `skipped` 与已有正文的；**判词那一条搬到了
    `browser_todo`**（它才是决定待办名单的那一层，`tests/
    test_a_settled_job_is_not_still_on_the_worklist.py` 钉住它不许沉回来）。
    判据不自己写：`doctor.is_out_verdict` 是判词出局与否的唯一定义，
    本文件顶部从 `doctor` 导入，`build_dashboard` 是同一份的正本。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        return {}
    seen = _cli.seen_of(json.loads(p.read_text(encoding="utf-8")))
    ustate = _cli.load_user_state(p)
    out = {}
    for k, e in seen.items():
        if _cli.decided_status(e, ustate.get(k)) in ("expired", "skipped"):
            continue
        if st.has_body(st.load(user, e.get("url") or "", e.get("title") or "")):
            continue
        out.setdefault(e.get("portal") or "?", []).append(e)
    return out


def browser_todo(user: str) -> list:
    """浏览器渠道那批该补 JD 的岗，**已经按「还活着」过滤好**，新的排前面。

    ## 为什么要有它

    这个工具只抓猎聘 CLI 那条；其余渠道的 JD 得人拿浏览器一个个开。而
    `missing_by_portal()` 原来只报**数量**（「另有 335 个够不着」），
    执行者手里没有名单，只能自己去 `seen_jobs.json` 里挑 —— 一手挑就会
    漏掉 `user_state.json` 那层叠加：**库里写着 `ranked`、用户在面板上已经
    标了不投的岗，看起来完全够格。**

    实测代价（2026-08-25 一次 `/job-auto`）：执行者手挑了一个岗去开浏览器，
    抓完才发现它早就深评过（值得投 62）、而且用户标了不投。当时四家渠道
    每家只剩个位数动作额度，那两次动作是这一轮**唯一**能用在别处的额度。

    ## CLI 停着的时候，它那批也归浏览器

    平时排掉 `CLI_PORTAL` 是对的 —— 猎聘那批由本工具自己抓，不该占人的手。
    **但撞限流之后不成立**：那一刻这批岗恰好变成了只有浏览器够得着的活。

    而本工具撞停时印的那句话，指的正是这份名单（「这段时间猎聘的浏览器那条
    一直是通的……名单跑 `--browser-list`」）—— 一条**按设计排掉了刚被封的
    那一家**的名单。实测 2026-08-27 一次 `/job-auto`：CLI 抓到 24 份撞限流停手，
    此时缺 JD 的 **407 个**猎聘岗一个都不在名单里，照提示走等于对着空名单干活。

    判据不自己写，问 `portal_budget`：**只有 CLI 那条通道真封着**才放进来
    （`lane="cli"` —— 不点名通道的话，浏览器自己被封时会把 CLI 那批也拉进来，
    那就正好反了）。

    ## 判过死刑的不进这份名单

    `_missing_alive` 只挡 `status` 与叠加层两条出局路径（它必须如此，理由见那边：
    `--recheck` 要抓的正是判词已经出局的那批）。而**这份名单是给人拿浏览器一个个
    开的** —— 判词已经是「跳过 / 不建议 / 硬门没过」的岗再开一次不改变任何决定，
    纯浪费额度。所以这一道滤加在这里，名单是那个计数的**子集**。

    实测 2026-08-27 一次 `/job-auto`：这份名单给出 549 个待办，其中 **362 个
    （三分之二）已经结案**（跳过 273、硬门 FAIL 39、不建议 23……）；更直接的代价是
    队首连着三条都是同一轮 `prescreen --apply` 刚判为「这家的这个岗你已经投过」的岗
    —— 照名单走，头三次浏览器访问全花在了已经结案的岗上。滤掉之后 549 → 187。

    判据不自己写：`doctor.is_out_verdict` 是判词出局与否的唯一定义。
    """
    out = [e for p, v in _missing_alive(user).items() if p != CLI_PORTAL for e in v]
    out = [e for e in out if not is_out_verdict(e.get("rank_verdict"))]
    if pb.block_state(pb.load(user), CLI_PORTAL, _dt.datetime.now(),
                      lane="cli")["blocked"]:
        out += [e for e in _missing_alive(user).get(CLI_PORTAL, [])
                if not is_out_verdict(e.get("rank_verdict"))]
    # 新的排前面：抓的时候只收 14 天内的岗，队尾那批多半已经在平台上关了
    #（同 `job-rank.md` 自动模式「队列里的岗是会烂的，先评新的」）。
    out.sort(key=lambda e: str(e.get("first_seen") or ""), reverse=True)
    return out


def missing_urls(user: str, recheck: bool = False) -> list[dict]:
    """缺 JD 正文、且是猎聘链接的。

    默认只收待评的（status=new）；`recheck=True` 时**把判过但正文靠不住的一并收进来**
    ——抓到正文后由评估方重审那些判定。「靠不住」有两种，缺一种就漏一批：

    1. `needs_recheck`：判据本身没读过正文（预筛/粗筛未抓 JD、标题即判据）；
    2. `judged_without_stored_body`：判词**自称**读过，而库里查无此条（实测 283 个）
       ——第二种此前完全没人管，因为它的措辞看起来是最可信的那一档。

    ⚠️ **只收猎聘。** 其余渠道的 JD 只能在抓取当次的浏览器访问里取
    （`cdp-portals.md` 第 6 条：卡片 → 预筛 → 只给活下来的读），
    回头补要重开页面、而且列表会重排。所以这里不是「漏了那几家」，
    是它们**根本不该走这条补抓路**——`missing_by_portal()` 负责把这件事说出来，
    别让人以为跑一次这个工具就补全了。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        # 与 prescreen/writeback/jd_store 同一条约定：还没跑过 /job-scrape 不是异常，
        # 是流水线的正常起点——报下一步，不甩栈回溯。
        print(_cli.no_store(p.relative_to(ROOT)))
        raise SystemExit(1)
    seen = _cli.seen_of(json.loads(p.read_text(encoding="utf-8")))
    # **抓谁要看叠加层。** 这里原来读的是裸 `status`，而用户在总览页点的
    # 「不投 / 已下线」只写进 `user_state.json` —— 那些岗在库里仍然是
    # `ranked`，`--recheck` 会照抓不误。代价不是多几行日志：猎聘每次请求
    # 之间要隔几秒、撞限流会整站冷却 24 小时（`portal_budget`），额度花在他已经否掉的岗上，
    # 就是没花在还等着补 JD 的岗上。
    #
    # 这正是 `prescreen` 那句话点名的形状 ——「页面上标了不投、命令行照样
    # 评它、评完又冒回名单里」，只是换了个文件。
    ustate = _cli.load_user_state(p)
    out = []
    for k, e in seen.items():
        _st = _cli.decided_status(e, ustate.get(k))
        wanted = (_st == "new"
                  or (recheck and _st == "ranked"
                      and (needs_recheck(e) or judged_without_stored_body(user, e))))
        if not wanted:
            continue
        if (e.get("portal") or "") != CLI_PORTAL:
            continue
        if st.has_body(st.load(user, e.get("url") or "", e.get("title") or "")):
            continue
        if e.get("url"):
            out.append(e)
    # 降权泊车的排到队尾，**不排除**。它们只有标题这一层依据显示方向不对，判不了
    # 死刑（见 prescreen 的规则分组说明）——但抓取额度有限、还会撞限流，先花在
    # 没被降权的上面。额度富余时它们照样轮得到，这才是「降权」而不是「淘汰」。
    out.sort(key=lambda e: bool(e.get("deprioritized")))
    return out


def _wait_for_gate(budget, sleep) -> str:
    """等到 `portal_budget.check()` 放行为止；返回空串表示可以发请求。

    跨进程的上一次动作也要算进来：`INTERVAL_S` 只管这一趟内部的节奏，
    而上一轮/另一条命令留下的间隔由闸门判断。返回非空串表示**停**，
    调用方要把原因带给用户。
    """
    why = ""
    for _ in range(pb.MIN_ACTION_GAP_S + 1):
        ok, why = pb.check(budget, CLI_PORTAL, _dt.datetime.now())
        if ok:
            return ""
        if "动作太密" not in why:
            return why
        sleep(1)
    return why


def _commit_budget(user: str, budget: dict, stamp, apply_note) -> tuple:
    """把这一笔额度写回去，返回 `(文件里的最新数据, 新戳)`。

    **这一趟是长跑，额度文件却可能被别人动。** 实测路径：补几十份 JD 要几分钟
    到几十分钟，中间用户完全可能在总览页点「继续抓」——那边读、改、写一次
    就落盘了。拿开跑时那份快照直接写回去，会把用户刚解开的冷却**盖回封着**，
    而两边都不报错。

    所以撞上 `StaleWrite` 时不覆盖：把**他那一份**读回来，再把这一笔
    （一次动作或一次封控）补上去重写。连撞三次就抛出去 —— 那已经不是偶发
    的一次点击，而是另一个人在连续写，这一趟该停。
    """
    for _ in range(3):
        try:
            return budget, pb.save(user, budget, expect=stamp)
        except _cli.StaleWrite:
            budget, stamp = pb.load_stamped(user)
            apply_note(budget)
    raise _cli.StaleWrite(
        f"{pb.path_for(user).name} 在几秒内被连着改了三次，这一趟先停")


def run(user: str, entries: list[dict], apply: bool, fetch=fetch_one,
        sleep=time.sleep, budget=None) -> dict:
    """逐个抓，**撞停手码立刻返回**。

    每抓到一份就当场存——中途停手时，已经抓到的不会跟着丢。

    `budget` 传了就用传进来的这份、**不读盘也不写盘**。这不是为了好测——
    是因为不传就会按 `user` 去写 `users/<user>/job_scraper/portal_budget.json`，
    而测试用的是「张三」这种假名字：2026-08-19 实测，跑一次测试就在真实仓库里
    造出一个 `users/张三/`，里面躺着一条 `blocked_until`；**下一次跑测试时
    冷却还在，13 个 URL 一个都没发出去**，四个测试集体变红而代码没动过。
    （同一个坑 `user_state` 踩过一次，那次的解法是把路径从库文件推出来。）
    """
    ok, failed, stopped = 0, [], None
    _persist = budget is None
    if _persist:
        _budget, _stamp = pb.load_stamped(user)
    else:
        _budget, _stamp = budget, None
    # **来之前先看闸门。** `fetch_details` 自己会记账、撞到限流也会 `block()`，
    # 但上一轮留下的冷却在它这里是可以直接绕过的——它是主动发请求的那一方，
    # 闸门必须在这里生效。冷却不等于「动作太密」：前者要停手，后者可以等。
    # 这一趟内部的间隔由 `INTERVAL_S` 负责；这里只处理**开跑前**已有的状态。
    if apply and entries:
        why = _wait_for_gate(_budget, sleep)
        if why:
            return {"ok": 0, "failed": [], "stopped": "BLOCKED",
                    "attempted": 0, "gate": why}
    runtime = find_runtime() if apply else []
    # **没有次数上限了**（2026-08-26）。这里原来先问 `remaining_today`、
    # 把这一批砍到今天剩下的额度；那个额度是我们自己拍的，删了。
    # 现在跑到撞上为止 —— 下面循环里 `STOP_CODES` 那一支就是「撞到才算」：
    # 真收到 RATE_LIMITED 才 `pb.block`，那条通道才进冷却。
    # 拦在前面的只剩间隔（`INTERVAL_S`，取自闸门）。
    for i, e in enumerate(entries):
        if not apply:
            continue
        if i:
            sleep(INTERVAL_S)
        bstate = pb.block_state(_budget, CLI_PORTAL, _dt.datetime.now(), lane="cli")
        if bstate["blocked"]:
            _ok, why = pb.check(_budget, CLI_PORTAL, _dt.datetime.now())
            return {"ok": ok, "failed": failed, "stopped": "BLOCKED",
                    "attempted": i, "gate": why or bstate["why"]}
        # 每发一次记一笔。**记在发之前**——请求已经出去了，哪怕它失败也算数；
        # 只记成功的等于把失败的请求从账上抹掉，而平台是按发出的次数算的。
        _now = _dt.datetime.now()
        pb.note(_budget, "猎聘", 1, _now, kind="fetch")
        if _persist:
            try:
                _budget, _stamp = _commit_budget(
                    user, _budget, _stamp,
                    lambda d: pb.note(d, "猎聘", 1, _now, kind="fetch"))
            except _cli.StaleWrite as exc:
                # 这一笔没落盘，就别再发下一个请求 —— 账上不记的动作，
                # 下一次的间隔判断看不见它。
                return {"ok": ok, "failed": failed, "stopped": "BUDGET_STALE",
                        "attempted": i, "gate": str(exc)}
            # 合并回来的那份可能带着一条刚出现的冷却（另一条命令在同一时刻
            # 撞了风控）。上面那次检查用的是开跑时/上一轮的状态，不算数了。
            _st = pb.block_state(_budget, CLI_PORTAL, _dt.datetime.now(), lane="cli")
            if _st["blocked"]:
                return {"ok": ok, "failed": failed, "stopped": "BLOCKED",
                        "attempted": i,
                        "gate": "另一边刚把这条通道封了 —— " + _st["why"]}
        d = fetch(runtime, e["url"])
        code = d.get("code")
        if code in STOP_CODES:
            stopped = code
            # 2026-08-19 实测：CLI 撞了 RATE_LIMITED 之后改用浏览器开猎聘
            # 搜索页，账号当场被标「行为异常」、要短信验证。同一家、同一个 IP，
            # **按原速**换通道就是把软限流升级成硬风控——所以封 CLI 那条时，
            # 闸门把浏览器那条放慢（间隔 ×`SLOW_GAP_FACTOR`），不是拦住
            # （原来这儿还写着「每轮上限 3」，那个旋钮已删；`portal_budget.check`
            # 里那条不对称规则也是从「硬停」改成「放慢」的）。
            # 光在这里 break 只挡住了本进程，下一条命令照样走进去。
            #
            # **渠道名要写全，别写平台名。** 写 `猎聘` 也能对，但那是靠
            # `PRIMARY_LANE` 恰好把它落到 CLI —— 那张表是给「用户没说清」准备的
            # 兜底，不是给知道自己在封哪条的调用方用的。
            # **把这一趟真拿到了什么写进封控记录。**（2026-08-26 本人：
            # 「cli 被封后，你应该显示实际获取的信息」。）
            #
            # 这个 `why` 是**唯一**会同时出现在终端拒绝语和面板告警条上的
            # 字段。不写进去的话，那两处就只剩「CLI 撞 RATE_LIMITED」——
            # 读起来像这一趟白跑了，而实际上前面那些 JD 已经落库了。
            # 用户下一步该做什么（补剩下的，还是先去换 IP）取决于这个数。
            _why = f"CLI 撞 {code}；撞停前已抓到 {ok} 份 JD，都存好了"
            _now = _dt.datetime.now()
            pb.block(_budget, "liepin-search", _why, _now)
            if _persist:
                try:
                    _budget, _stamp = _commit_budget(
                        user, _budget, _stamp,
                        lambda d: pb.block(d, "liepin-search", _why, _now))
                except _cli.StaleWrite as exc:
                    # **这条比动作账更要紧**：不记下来的话，下一条命令会照常
                    # 走进这条刚撞过风控的通道。所以停，并把该敲的那条命令给出来。
                    return {"ok": ok, "failed": failed,
                            "stopped": "BUDGET_STALE", "attempted": i + 1,
                            "gate": f"{exc}。撞上的 {code} 也没能写进额度文件 —— "
                                    f"先跑 python tools/portal_budget.py "
                                    f"--block liepin-search --why \"CLI 撞 {code}\" "
                                    f"再继续"}
            break                       # 不重试、不继续 —— 账号安全铁律
        if d.get("error"):
            failed.append((e.get("title") or "", code))
            continue
        if not st.has_body(d):
            failed.append((e.get("title") or "", "NO_BODY"))
            continue
        # **标题一律用职位库那条的，不用详情接口返回的。**
        #
        # 库里的键是 `stable_id(url, title)`，而**读取方一侧只有职位库的标题**
        # （`jd_store.load(user, e["url"], e["title"])`，`prescreen`、`/job-rank`、
        # `/job-apply`、`export_web_data` 全走它）。详情接口返回的标题与列表页
        # 存下来的常常不是一个字：平台后来改了标题、列表页截断过、或者干脆换了
        # 一个名字。用返回的那个存，文件写下了、请求花掉了，而**谁都读不回来**
        # —— 每一轮都会把同一个岗再抓一遍。
        #
        # 实测 2026-08-27：盘上 6 份详情就是这么废掉的，例：
        #     职位库「AI研发效能岗」        ← 详情页「证券公司AI治理岗」
        #     职位库「AI产品经理--上海/广州/北京」← 详情页「…/北京/成都」
        # 当轮 CLI 报「抓到 2 份」，而 `jd_store.status` 的 `new_have` 纹丝不动。
        #
        # `save_from_text`（`--save` 那条路）早就是这么做的，docstring 写着
        # 「标题不让调用方给……只收链接，标题连同已有的结构化字段一起从
        # `seen_jobs.json` 那条取」，并点明失败是静默的：「存进去的这份就再也
        # 读不回来 —— 而它**看起来是成功的**」。这条路当时绕开了那道保护。
        #
        # 详情页的标题不丢：它更全（带地点、带真实岗位名），留在 `detail_title`
        # 里，评估时能看见两边不一致。
        if (d.get("title") or "") != (e.get("title") or ""):
            d["detail_title"] = d.get("title")
        d["title"] = e.get("title") or d.get("title")
        st.save(user, d)
        ok += 1
    return {"ok": ok, "failed": failed, "stopped": stopped,
            "attempted": len(entries) if apply else 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="抓职位详情，撞风控立刻停手")
    ap.add_argument("--missing", action="store_true",
                    help="抓「待评且缺 JD」的猎聘职位")
    ap.add_argument("--recheck", action="store_true",
                    help="连「判过但未经 JD 正文复核」的一起抓（预筛淘汰/字段判的硬门）"
                         "——抓到后要人工重审那些判定")
    ap.add_argument("--urls", metavar="文件", help="每行一个 URL")
    ap.add_argument("--browser-list", action="store_true",
                    help="只列出浏览器渠道那批该补 JD 的岗（已按「还活着」过滤），"
                         "不发任何请求——拿浏览器补 JD 时照这份名单走，别自己挑")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"本轮最多抓几个（默认 {DEFAULT_LIMIT}，取自 job-rank.md「通道决定批大小」那张表）")
    ap.add_argument("--apply", action="store_true", help="真的发请求。不加就是试运行")
    ap.add_argument("--user", help=_cli.HELP_USER)
    args = ap.parse_args(argv)

    # 不判存在就直接 read_text 会在**全新 clone 上**抛 FileNotFoundError 栈回溯
    # ——新用户敲错顺序是常态，第一次撞见的不该是 traceback。
    user = _cli.pick_user(args.user or "", root=ROOT)
    if args.browser_list:
        rows = browser_todo(user)
        if not rows:
            print("浏览器渠道没有要补 JD 的岗。")
            return 0
        print(f"浏览器渠道待补 JD {len(rows)} 个（已排除已下线/标了不投的；新的在前）：")
        # **这一段不许用 `DEFAULT_LIMIT` 截。** 那个 12 是为**猎聘 CLI 的详情限流**
        # 定的（见它上面那段说明），而这条命令按自己的说明「**不发任何请求**」——
        # 拿一条会限流的通道的批大小去截一份只读清单，正是 `job-rank.md`
        # 「通道决定批大小」那一节明令禁止的事：「走浏览器时**不必沿用为 CLI 定的
        # 保守值**」。
        #
        # 实测代价（2026-09-02）：待补 100 个，这条命令只印 12 条、剩 88 个跟着
        # 一句「用 --limit 调」被折起来。照这份被截过的名单走，一轮只补得动 12 个，
        # **而截它的那个数来自一条当天根本没在跑的通道**（CLI 撞限流封着 35 小时）。
        shown = args.limit if args.limit != DEFAULT_LIMIT else len(rows)
        for e in rows[:shown]:
            print(f"  [{e.get('portal') or '?'}] {str(e.get('first_seen') or '')[:10]} "
                  f"{str(e.get('salary') or '—'):12} {(e.get('title') or '')[:30]}")
            print(f"      {e.get('url')}")
        if len(rows) > shown:
            print(f"  …… 另有 {len(rows) - shown} 个（用 --limit 调）")
        print("\n这些只能在浏览器里一个个开，额度走 tools/portal_budget.py。")
        # **按通道算出这一轮该取几个。** 规则原来只写在 `job-rank.md` 那张表里，
        # 没有任何一处把它算出来 —— 执行者要么照写死的 12，要么自己拍一个数。
        per = _collections.Counter(e.get("portal") or "?" for e in rows)
        print("\n这一轮按通道该取几个（`job-rank.md`「通道决定批大小」）：")
        total = 0
        for portal, n in per.most_common():
            cap = BROWSER_BATCH.get(portal, BROWSER_BATCH_DEFAULT)
            total += min(n, cap)
            print(f"  {portal:<18} 待补 {n:>3} · 通道上限 {cap} → 本轮取 {min(n, cap)}")
        print(f"  合计 {total} 个 —— 写死的默认是 {DEFAULT_LIMIT}，"
              f"那是猎聘 CLI 的数，不是浏览器的")
        return 0
    if args.urls:
        entries = [{"url": u.strip(), "title": ""}
                   for u in Path(args.urls).read_text(encoding="utf-8").splitlines()
                   if u.strip()]
    elif args.missing or args.recheck:
        entries = missing_urls(user, recheck=args.recheck)
        n_re = sum(1 for e in entries if e.get("status") == "ranked")
        if args.recheck and n_re:
            print(f"其中 {n_re} 个是待复核的既有判定——抓到正文后要重审，不是抓完就完")
    else:
        ap.error("要么 --missing / --recheck，要么 --urls")
    if args.limit:
        entries = entries[: args.limit]

    # **试运行报的就是真账单。** 这个数是用户唯一用来决定「跑不跑」的东西。
    #
    # 原来这里要额外说一句「但今天只抓得了 N 个，实际要跨 M 天」——
    # 因为 `--apply` 会被日上限砍。2026-08-26 那个上限删了
    # （见 `portal_budget` 开头），于是「条数 × 间隔」重新变成诚实的估计：
    # 拦在前面的只剩间隔，而间隔就是这里印的这个数。
    print(f"待抓 {len(entries)} 个（间隔 {INTERVAL_S} 秒，约 "
          f"{len(entries) * INTERVAL_S / 60:.1f} 分钟）")
    print("  跑到撞上限流为止 —— 真收到 RATE_LIMITED 才停，不预支额度")
    # **把这个工具够不着的那批说出来。** 只报「待抓 N 个」会被读成「缺 JD 的就这些」，
    # 而实测缺 JD 的三分之一在浏览器渠道上——它们只能在下次抓取的同一次访问里顺手取。
    by_portal = missing_by_portal(user)
    other = {k: v for k, v in by_portal.items() if k != "liepin-search"}
    if other:
        tail = "、".join(f"{k} {v}" for k, v in sorted(other.items(), key=lambda x: -x[1])[:4])
        print(f"另有 {sum(other.values())} 个缺 JD 的岗这个工具够不着（{tail}）——"
              f"浏览器渠道的 JD 只能在抓取当次取，回头补要重开页面且列表会重排，"
              f"下次 /job-scrape 时顺手落库")
        print(f"  真要现在拿浏览器补，名单跑："
              f"python tools/fetch_details.py --browser-list"
              f"（已排除已下线/标了不投的，别自己去 seen_jobs.json 里挑）")
    if not args.apply:
        for e in entries[:10]:
            print(f"  {(e.get('title') or e['url'])[:50]}")
        if len(entries) > 10:
            print(f"  …… 另有 {len(entries) - 10} 个")
        print("\n试运行，没有发请求。确认后加 --apply")
        return 0

    r = run(user, entries, apply=True)
    print(f"\n抓到 {r['ok']} 份")
    if r["failed"]:
        # 失败码翻成人话再上屏（AGENTS.md：未解释的英文码不上台面）。
        # 认不出的码原样保留——宁可露一个码，不把原因说成别的。
        SAY = {"NO_BODY": "页面没有职位正文", "UNPARSEABLE": "页面结构认不出"}
        print(f"失败 {len(r['failed'])} 个：")
        for t, c in r["failed"][:8]:
            print(f"  {SAY.get(c, c)}：{t[:34]}")
    if r["stopped"] == "BLOCKED":
        print("\n⚠ 这条渠道现在停着，这次没有继续发请求。")
        if r.get("gate"):
            print("  " + r["gate"])
        print("  这是账号安全闸门，不是失败；处理完再跑，别加重试。")
        return 0
    if r["stopped"] == "BUDGET_STALE":
        # 这不是撞风控，别说成「账号安全铁律」—— 用户会以为要去换 IP。
        print("\n⚠ 额度文件在跑的过程中被另一边改过了（多半是总览页上点了按钮）。")
        print("  这一趟先停：再写下去会把对方刚做的改动盖掉。")
        if r.get("gate"):
            print("  " + r["gate"])
        print(f"  已经抓到的 {r['ok']} 份 JD 都存好了；重跑这条命令就接着抓。")
        return 0
    if r["stopped"]:
        print(f"\n⚠ 撞到 {r['stopped']}，已立刻停手，没有重试。")
        print(f"  这一趟实际拿到 {r['ok']} 份 JD，都存进详情库了 —— 没有白跑。")
        print("  这是账号安全铁律：撞风控就停，硬闯会把账号搭进去。")
        # **不许说「等一段时间再跑一次」。** 那是这条路上最贵的一句话：
        # 限的是这个网络出口的 IP，等到点换的还是同一个 IP，探一次限一次
        # （08-24、08-25 各撞一次，第二次就是冷却刚过撞的）。而且 2026-08-26
        # 起封控**不会自动解**了，等再久也不会自己恢复。
        print("  CLI 这条现在停着，不会自动解：换掉这个网络出口的 IP 之后，")
        print("  跑 python tools/portal_budget.py --clear liepin-search 才继续；")
        print("  也可以在总览页那条告警上点「继续抓」。")
        print("  这段时间猎聘的浏览器那条一直是通的（自动放慢，不是停）：")
        print("  名单跑 python tools/fetch_details.py --browser-list")
    return 0


if __name__ == "__main__":
    # `_commit_budget` 已经把「连撞三次」收成 `StaleWrite` 并当场交代清楚了；
    # 这里再兜一次，防的是别处漏出来的那一笔 —— 撞车时不该是栈回溯。
    sys.exit(_cli.run_cli(main))
