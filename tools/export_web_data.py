#!/usr/bin/env python3
"""把活动用户的真实数据导出成 web/ 那个 antd 页能读的 JSON。

## 为什么需要它

`web/` 原来只有一份**虚构**演示数据（`src/data/sample.ts`）。虚构数据的问题不是
"不够真"，而是**它长得像真的**：职位链接点了打不开、「打开定制简历 PDF」指向一个
不存在的文件——按钮看着能用，其实是死的。这比没有按钮更糟。

所以这个脚本干两件事：
1. 把 `seen_jobs.json` + `documents/applications/*/` 里的真实内容导出成 `data.json`；
2. **把真实的 resume.pdf 复制进 web/public/pdf/**，让那个按钮真的能打开。

## 隐私

输出目录 `web/public/` 整体 gitignore。这里面是简历 PDF、话术、薪资期望、能力边界
——都属于 `users/<你>/`，绝不进版本库。脚本只写这一个目录，不改任何源文件。

零依赖，只用标准库。
"""

from __future__ import annotations

import collections
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

# 复用面板的解析器，**不写第二套**。投递目录的职位链接有优先级
# （outreach.md 的「职位链接：」优先，posting.md 的「原始链接：」兜底），
# 第一版这里只读了 posting.md，于是两个投递目录匹配不上、材料凭空消失。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402
from build_dashboard import (NO_REPLY_ALARM,  # noqa: E402
                             _days_since,
                             _INTERVIEW_STATUSES as INTERVIEW_STATUSES,
                             dedup_apps_by_url,
                             _OFFER_STATUSES as OFFER_STATUSES,
                             find_applications, is_parked, job_next_step, match_tracker,
                             is_optional, load_tracker, n_parked, n_processed,
                             n_waiting,
                             next_step, parse_commands, profile_ready, resolve_score)
# 别名不是随手起的：这个文件里 `tracker` 是个**局部变量**（台账文件路径），
# 直接 `import tracker` 会在函数里被它遮住，报的还是 AttributeError 那种绕远的错。
import tracker as tk  # noqa: E402
import query_yield as qy  # noqa: E402
# 同一家公司归组用它，**不另写一份**：脱敏串（「某知名公司」库里 158 次）
# 不是公司身份，归到一起就成了「你在这家投了 158 个岗」。
from followups import cluster_key  # noqa: E402


def bare_verdict(verdict: str) -> str:
    """判词去掉「粗筛：」前缀。**这一份是正本。**

    「粗筛」说的是**这个分怎么来的**（只看了列表卡片，没读 JD），不是判词本身。
    它是框架内部词（AGENTS.md「给用户看的措辞」），凡是给人看的地方都要剥。

    剥它的代码原来散在四处各写一遍：本文件两处、`Shortlist.tsx` 的
    `plainVerdict`、`writeback.py` 数「结论前缀残留」。第五个消费方
    （`applied_jds.render`）没跟上，于是 `upskill/applied-jds-<日期>.md` ——
    一份**用户直接打开的 markdown**，下游没有任何显示层——里印着
    「当时评分：70 分 粗筛：值得投」。实测 85 条投递里有 5 条带着它。
    """
    return _cli.strip_triage(verdict)
#: 回读那两个分、以及从屏幕上剥掉打分算式，**都只有 `gap_split` 那一份实现**。
#: 说明分别在 `gap_split.FORMULA` 和 `read_pair` 的注释里。
from gap_split import FORMULA as _FORMULA, read_pair as _read_pair  # noqa: E402


#: 脱敏公司名的判据。**正本在 `_cli`** —— `build_dashboard.match_tracker` 也要用它
#: （见那里的「脱敏串不构成公司身份」），而它不能反过来 import 本模块（循环）。
is_anonymous_employer = _cli.is_anonymous_employer


#: 判词判「出局」的那几档——页面把它们放进搁置区，不算在「可以投的岗位」里。
#: **唯一的一份判据**（TS 侧 `App.tsx` 的 `isOut` 是同一条，两边由
#: `tests/test_pipeline_counts.py` 钉住相等）。
#: 能进「可以投的岗位」的判词。**白名单，不是黑名单。**
#:
#: 原来这里是 `OUT_VERDICTS = ("不满足硬性条件", "跳过", "不建议")` ——列不许进的，
#: 其余放行。2026-08-13 两天内被漏进来两次：新造的「粗筛：待定」不在名单里；
#: 「不满足硬性条件 (学历)」带了门名后缀，精确匹配那条落空。
#:
#: 判词是自由度很高的字段（加档、加后缀、改措辞都是常事），而黑名单每次变动的
#: 默认后果都是「混进最显眼的表」。白名单的默认后果是「漏一个」——看得见、能查，
#: 比把硬门没过的岗摆到第一行便宜得多。
#:
#: 与前端 `App.tsx` 的 `SELLABLE` 同源，改一处要改两处
#: （`tests/test_pipeline_counts.py` 与 `tests/test_one_number_per_concept.py` 钉住相等）。
SELLABLE_VERDICTS = _cli.VERDICTS[:3]     # 词表正本在 _cli，切片即子集

#: 这三档里，**可以直接发出去**的只有前两档。
#:
#: `04-job-evaluation.md` 给的定义就不一样：「值得投」是「投，在沟通中主动补缺口」，
#: 「可以考虑」是「**先问清楚**关键信息再决定」。前者是一个动作，后者是一个待办。
#:
#: 2026-08-13 实测：面板与自检都说「还有 63 个岗材料就绪但没投」，催人去发——
#: 而那 63 个里 **59 个是「可以考虑」**，真正备好可以直接发的只有 4 个。
#: 一个把「已经决定要投」和「还没决定要不要投」加在一起的数，读起来像进度，
#: 其实是把 59 件需要动脑的事说成了 59 次复制粘贴。
STRONG_VERDICTS = _cli.VERDICTS[:2]       # 同上


def is_strong(verdict: str) -> bool:
    """判词是不是「可以直接发」那两档。**匹配语义必须与 `is_sellable` 一模一样。**

    第一版写成 `v.startswith(STRONG_VERDICTS)`（容后缀），而 `is_sellable` 是
    精确 `in`。差别在带后缀的判词上就炸：

        「值得投（附条件）」 → is_strong 真、is_sellable 假

    后果是一个岗**被算进「先发这 N 个」，却根本不在那张名单里**——用户按提示去发，
    数得到、找不着。真实数据里当时还没踩到（0 条），但判词加后缀是常事，
    这类不一致只会在有人写出第一个带后缀的判词那天才显形。

    白名单的精神是「不认识就不进」，`is_strong` 是它的子集，只能更严、不能更松。
    """
    return bare_verdict(verdict) in STRONG_VERDICTS


#: 投出去多少天还没任何动静，就当「大概率没戏」。
#:
#: **这个数不问用户。** 用户 2026-08-13 原话：「很多是没反馈也就不会填」——
#: 沉默是这条流水线上最常见的结果，而它恰恰**不产生任何事件**：没有邮件、
#: 没有电话、没有状态变化。要求用户手动记「这个没回我」，等于要他为
#: 「什么都没发生」这件事每周点几十次。所以：算出来，不要问。
#:
#: **取值来自 `followups.py.QUIET_DAYS`，不在这里另写一个。** 2026-08-13 实测
#: 同一件事有三个数：催办 10 天、这里写死 14、`job-gmail-sync.md` 写 30——
#: 于是面板催你「该催了」的同时，统计还把它算在「还在等」里。
#:
#: 它只影响**怎么归类**，不改任何状态：用户随时可以自己点「没下文」结案。
try:
    from followups import QUIET_DAYS as SILENT_DAYS
except Exception:      # pragma: no cover - 只在 followups.py 被删/改坏时
    SILENT_DAYS = 10


def applied_fit(jobs: list, seen: dict) -> dict | None:
    """**投出去的那批**按 `gap_split` 的四格分。分不出返回 None —— 不猜。

    「投了这么多没回音」有好几种解释，而这一条最容易被跳过：
    **不是简历不行，是投的地方不对**。它和渠道那条（猎头代招占一半）并列，
    但指向的动作完全不同 —— 那条要你换到达方式，这条要你换投递对象。

    实测活动用户 2026-08-22：投出去的 78 份可回读评估里，
    **49 个（63%）是「专业能力够、行业经验对不上」**，主场只有 17 个。
    这条此前只活在一个命令行工具里（`gap_split.py --applied`，由 `/job-upskill`
    调用），面板的零回音诊断从没说过。

    ## 为什么读原始条目，不读导出的 `dimensions`

    导出侧那条 note 已经被 `strip_weights` 剥成「专业能力 88 · 行业经验 65」
    （屏幕上不该出现打分算式，AGENTS.md 那条），而 `gap_split.FORMULA` 认的是
    带 `×0.6` 的原式 —— 拿剥过的去配必然全部落空。判据与分界一律走
    `gap_split`（`STACK_OK` / `DOMAIN_OK`），**这里连数字都不抄**：
    它们取自框架各维自身的分档，抄一遍就等着它们哪天不一样 —— 而那一天
    2026-08-23 到了：专业能力那条从 70 改成 60（70 根本不是框架里的档位下沿，
    判据见 `gap_split.STACK_OK` 上面那段），而这里的 70 一起变成了旧数。

    ## 只算投出去的那批

    全库那份会被宽泛抓取的噪音淹掉 —— 实测全量 593 份里「两样都差」占 372，
    而只算投过的 78 份，它掉到 7、「选岗问题」升到 49。
    **投过的那批天然干净，因为用户自己已经把不对路的筛掉了。**
    """
    applied_urls = {j.get("url") for j in jobs
                    if j.get("applied") and not j.get("dupOf") and j.get("url")}
    out = _fit_of(seen, applied_urls)
    if out is None:
        return None
    # **还没投的那批也分一遍。** 「往主场方向投」这句建议，只有在手上真的挑得出
    # 行业对口的岗时才可执行 —— 实测 2026-08-22：还没投的 227 个可投岗里主场只有 11 个，
    # 分数 54-59，一个都没进「值得投」。那句话真正的意思是
    # **「去改搜索词多抓这类」**，而不是「从现有名单里挑」。差别很大：
    # 一个是今晚能做的事，一个是明天才有的结果。
    open_urls = {j.get("url") for j in jobs
                 if j.get("url") and not j.get("dupOf") and not j.get("applied")
                 and not j.get("skipped") and not j.get("expired")
                 # 「能进可投名单的三档」= `_cli.VERDICTS[:3]`。**不在这里内联一份**
                 # ——那张词表的代码侧唯一定义在 `_cli`，切片即子集
                 # （`test_shared_vocab_single_source` 盯着，我刚被它拦下一次）。
                 and any(k in (j.get("verdict") or "") for k in _cli.VERDICTS[:3])}
    out["open"] = _fit_of(seen, open_urls)
    return out


def _fit_of(seen: dict, urls: set) -> dict | None:
    """给定一批链接，按 `gap_split` 的四格数。样本不足 10 返回 None —— 不猜。"""
    try:
        import gap_split as gs
    except Exception:
        return None
    if not urls:
        return None
    box = {k: 0 for k in (gs.HOME, gs.PICK, gs.LEARN, gs.OFF)}
    for e in seen.values():
        if not isinstance(e, dict) or e.get("url") not in urls:
            continue
        pair = gs.read_pair(e)
        if not pair:
            continue
        box[gs.quadrant(*pair)] += 1
    total = sum(box.values())
    if total < 10:          # 样本太小，说不出话来
        return None
    return {"total": total, "home": box[gs.HOME], "pick": box[gs.PICK],
            "learn": box[gs.LEARN], "off": box[gs.OFF]}


def outcome_stats(jobs: list, trows: list, seen: dict | None = None) -> dict:
    """投递之后的统计：回音情况、按分数段的回复率、拒绝原因分布。

    只数**匹配上职位的投递行**（`funnels_of` 的口径），不数台账里孤立的行——
    孤立行没有分数也没有判词，混进来会让「按分数段的回复率」失真。
    """
    import datetime as _dt
    today = _dt.date.today()

    def days_since(x):
        # **走正本 `build_dashboard._days_since`。** 这里原来是
        # `date.fromisoformat`，只认 ISO —— 而台账是**人手填的**，
        # 正本为此认四种写法（`-` / `/` / `.` / `年月日`）。
        # 同一行 `2026/07/12`：`/job-outcome followup` 判「该催了」、
        # 自检也数得着，而这一处读不出日期，那条投递就静默掉出
        # 回音分桶、猎头/直招分母和回复率 —— 三个数一起偏。
        # 讽刺的是同一个文件第 3125 行早就写着「别另写一套」并 import 了它，
        # 而这一行就是那句话说的「另一套」。
        return _days_since(x, today)
    GHOST = {"no response", "no_response"}

    buckets = {"约面或更远": 0, "被拒": 0, "还在等": 0, "大概率没戏": 0, "我撤回了": 0}
    by_band = {}          # 分数段 → [投了几个, 有回音几个]
    by_channel = {}       # 渠道 → [投了几个, 有回音几个, 其中猎头代招几个]
    n_agency = [0]        # 投出去的里面有几个是猎头代招
    direct = [0, 0]       # 企业直招的：[决出结果的, 其中有回音的]
    # **简历到底有没有到对方手上。** 猎聘 / BOSS 这类平台是先在会话里打招呼、
    # 对方有兴趣才要简历（`job-apply.md` 那条「简历不是第一道门」写的就是它）。
    # 也就是说这批投递里被读的是**开场白第一行**，简历还排在它后面。
    # 零回音时不分这一层，就会把人指去审一份对方还没看过的简历。
    chat = [0]            # 决出结果的里面，有几个是靠开场白发出去的
    # **简历被打开了吗** —— 只在企业直招那一组算（`job-outcome.md` Step 2b：
    # 猎头那组的「已查看」是顾问看了，不是用人方看了）。
    # `[标了已查看, 标了未查看]`，没标的两边都不进。
    viewed = [0, 0]
    direct_cos = set()    # 投过的、具名的企业直招公司
    reasons = {}
    wait_days = []

    for j in jobs:
        app = j.get("applied")
        if not app or j.get("dupOf"):
            continue
        st = (app.get("status") or "").strip().lower()
        d = days_since(app.get("date"))
        if st in ("interview", "offer", "hired", "interview_only"):
            bucket, replied = "约面或更远", True
        elif st in ("rejected", "offer declined", "offer_declined"):
            bucket, replied = "被拒", True
        elif st == "withdrawn":
            bucket, replied = "我撤回了", None
        elif st in GHOST:
            bucket, replied = "大概率没戏", False
        elif d is not None and d >= SILENT_DAYS:
            bucket, replied = "大概率没戏", False
        else:
            bucket, replied = "还在等", False
        buckets[bucket] += 1
        # 「已决出结果」= 有回音，或者过了静默线还没动静。**「还在等」不算**——
        # 那是「还没到时候」，拿它去算回复率就是把等待说成拒绝
        # （同 `next_step` 零回音分支的口径）。
        decided = replied is True or bucket == "大概率没戏"
        if bucket == "还在等" and d is not None:
            wait_days.append(d)

        sc = j.get("score")
        if replied is not None and isinstance(sc, int):
            band = "60 分以上" if sc >= 60 else ("50-59 分" if sc >= 50 else "50 分以下")
            b = by_band.setdefault(band, [0, 0])
            b[0] += 1
            if replied:
                b[1] += 1

        # **按渠道也拆一份。** 分数段回答「我该投多高分的岗」，渠道回答
        # 「我该把力气花在哪个网站」—— 后者在国内求职里往往更要紧：
        # 同一份简历在不同平台的回复率能差几倍（这个仓库自己的实测记着
        # BOSS 命中率 13.5% / 猎聘 4.8%），而台账此前根本答不了这个问题。
        # 猎头代招的有多少 —— **不拆回复率，只报个数**。
        # 拆成两行表格时两边都是 0%，说不出任何东西；而「一半的简历根本没到
        # 用人方手里」这个事实本身就是答案，一句话比一张 0% 的表有用。
        if j.get("viaHeadhunter"):
            n_agency[0] += 1
        elif j.get("viaHeadhunter") is None:
            # 没判过 —— 猎头那边不算，直招这边也不算。判据见 `via_headhunter`。
            pass
        elif decided:
            # **直招那批要单独有个分母。** 「投了 N 个 0 回音」这句话的分量
            # 完全取决于 N 里有多少是猎头代招：简历投给猎头是先进他的库，
            # 推不推、什么时候推由他定，岗位可能早关了——那批的沉默
            # **说明不了简历的事**（判据见 `via_headhunter` 的文档）。
            # 拿混在一起的总数去说「回头审简历」，是把渠道问题误判成简历问题。
            direct[0] += 1
            if replied:
                direct[1] += 1
            hv = j.get("hrViewed")
            if hv is True:
                viewed[0] += 1
            elif hv is False:
                viewed[1] += 1
        # **具名的企业直招有几家。** 这是「内推够得着的范围」——
        # 猎头岗和匿名岗没有人可找，只有真名实姓的用人方才谈得上找人引荐。
        elif not j.get("anonymousEmployer") and (j.get("company") or "").strip():
            direct_cos.add((j.get("company") or "").strip())
        if decided and ((j.get("materials") or {}).get("greeting") or "").strip():
            chat[0] += 1
        ch = (app.get("channel") or "").strip()
        if replied is not None and ch:
            c = by_channel.setdefault(ch, [0, 0, 0])
            c[0] += 1
            # **猎头占比要逐渠道算，不能只算一个总数。** 上面那段已经立了判据：
            # 「投了 N 个 0 回音」这句话的分量完全取决于 N 里有多少是猎头代招。
            # 那条当时只用在全局的 `viaAgency` 上 —— 而各渠道的猎头占比差得极远，
            # 正是这一点让这张表不能直接横着比：实测活动用户 2026-08-23，
            # 猎聘 66 个里 43 个是猎头（65%），BOSS 直聘 16 个里只有 1 个（6%）。
            # 同一页的头条说着「猎头那批没动静说明不了你简历的事」，
            # 这张表却把两者当成同一种东西比 —— 两段隔着不到一屏。
            if j.get("viaHeadhunter"):
                c[2] += 1
            if replied:
                c[1] += 1

        r = (app.get("outcome_reason") or "").strip()
        if r:
            reasons[tk.REASON_LABEL.get(r, r)] = reasons.get(
                tk.REASON_LABEL.get(r, r), 0) + 1

    total = sum(buckets.values())
    replied_n = buckets["约面或更远"] + buckets["被拒"]
    # **一个回音都没有、而多数还在等待窗口内时，不给这个比率。**
    #
    # 本文件下面那张「按分数段的回复率」图已经为同一件事让过路：
    # 「0% 对 0% 不是打分失效的证据，是还没有人回……等于人人先被泼一盆假冷水」。
    # 那条规矩当时只用在图上，**没用在头条上** —— 而头条是页面最显眼的位置：
    # 一个大号「有回音 0%」。
    #
    # 实测（2026-08-21）：85 个投出去，66 个还在等（中位已等 9 天，
    # 静默线 10 天）。读者看到的是「市场把你全拒了」，而实际是近八成还没到
    # 该回的时候。给 None，界面显示「还没有」——**是事实，不是判决**。
    #
    # **判据是「还在等的占多数」，不是「有一个在等」。** 上面这段讲的一直是
    # 「多数」（66/85），而它原来写成 `> 0`：199 个已读不回 + 1 个昨天刚投，
    # 也会把两个率一起吞掉，页面印「还没有」—— 那时 0% 是**真的**，
    # 藏起来就成了另一个方向的谎。
    too_early = replied_n == 0 and buckets["还在等"] > total * TOO_EARLY_SHARE
    order = ["60 分以上", "50-59 分", "50 分以下"]
    return {
        "total": total,
        "buckets": [{"k": k, "n": v} for k, v in buckets.items() if v],
        "repliedRate": None if (not total or too_early)
                       else round(replied_n / total * 100),
        "interviewRate": None if (not total or too_early)
                         else round(buckets["约面或更远"] / total * 100),
        "byBand": [{"band": b, "sent": by_band[b][0], "replied": by_band[b][1]}
                   for b in order if b in by_band],
        # 投得多的排前面——先看力气花在哪儿，再看那儿回不回。
        "byChannel": [{"channel": c, "sent": n[0], "replied": n[1],
                       "agency": n[2]}
                      for c, n in sorted(by_channel.items(), key=lambda x: -x[1][0])],
        "reasons": [{"k": k, "n": n} for k, n in
                    sorted(reasons.items(), key=lambda x: -x[1])],
        "viaAgency": n_agency[0],
        # 投出去那批的四格分布 —— 判据与理由见 `applied_fit`。
        "appliedFit": applied_fit(jobs, seen or {}),
        # 直招那批单拆的分母与分子。`next_step` 的零回音警报只信这一对——
        # 混着猎头算出来的「0 回音」会把渠道问题说成简历问题。
        "directDecided": direct[0],
        "directReplied": direct[1],
        # 决出结果的里面有几个走的是聊天框（有开场白）。`next_step` 的零回音
        # 分支拿它决定该指向开场白还是简历 —— 判据见 `_why_silent`。
        "chatDecided": chat[0],
        # 企业直招那组里，简历被打开过 / 没被打开过各有几个（面板上标的）。
        # 没标的不计 —— 「没查」和「查过是没打开」是两件事。
        "viewedDirect": viewed[0],
        "unviewedDirect": viewed[1],
        # 门槛跟着数据一起下发，**不让 TS 侧再抄一个 20**——同 `silentDays`。
        # 抄一份的下场：哪天三倍法则那个数改了，「下一步」那行和这一栏
        # 会在不同的样本量上各自触发。
        "noReplyAlarm": NO_REPLY_ALARM,
        # 只给家数与几个例子，不给全名单：这一栏是让人**改变做法**的一句话，
        # 不是一份要读完的清单（31 家铺开占半屏，而结论只有一句）。
        "directCos": len(direct_cos),
        "directCosSample": sorted(direct_cos)[:3],
        "silentDays": SILENT_DAYS,
        "waitingMedian": (sorted(wait_days)[len(wait_days) // 2] if wait_days else None),
    }


#: 「还没到时候」的门槛：**还在等的要占多数**，才藏起那两个率。
#: 不是拍的——它就是上面那段说明里一直在说的那个词（「多数还在等待窗口内」）。
TOO_EARLY_SHARE = 0.5


# **`is_out_verdict` 的正本 2026-08-26 搬到了 `build_dashboard`**，和 `is_parked` 放在一起。
# 理由：催与不催的那一处（`job_next_step`）在那个文件里，够不着这个函数，
# 于是它只问了「状态说出局没有」、没问「判词说出局没有」——
# 页面一边把岗算作出局、一边催他去投。两半必须在同一屏上。
from build_dashboard import is_out_verdict  # noqa: E402,F401
# 「建议」那一节也从这份正本取（同 `verdict`/`score`）——不在这里另切一刀。
from build_dashboard import parse_evaluation  # noqa: E402


#: 判词以这些开头就是出局。用前缀不用精确等于——门名后缀是常态。
OUT_PREFIXES = _cli.GATE_FAIL_PREFIXES     # 硬门终态前缀，正本在 _cli


def is_sellable(verdict: str) -> bool:
    """这个岗能不能进「可以投的岗位」。**白名单：不认识就不进。**

    用户 2026-08-13：「这个的规则应该更改，应该控制，而不是有新规则都能进入」。
    原来靠 `not is_out_verdict(...)` 反推——那是黑名单，默认放行，两天里漏进来两次：

        「粗筛：待定」            新造的判词，不在黑名单里
        「不满足硬性条件 (学历)」  带门名后缀，精确匹配落空

    判词是自由度很高的字段（加档、加后缀、改措辞都是常事），而黑名单每次变动的
    默认后果都是「混进最显眼的那张表」。白名单反过来：漏一个看得见、能查，
    比把不该投的摆到第一行便宜得多。
    """
    return bare_verdict(verdict) in SELLABLE_VERDICTS


def _parked_sent(jobs: list) -> tuple:
    """`(投过、却落在搁置区的岗数, 那句说法)`；一个都没有就 `(0, "")`。

    ## 为什么要说出来

    「投了多少」这一页有**两个数**：流水线第 4 格走 `funnels_of`，
    「投出去的那些」那颗按钮走投递记录行数。实测 2026-08-31 一个 **85**、
    一个 **88**，上下摆在同一屏，差 3，而页面一个字都没解释。

    两个都没算错：`funnels_of` 排掉判词出局与三类搁置是有意的
    （它自己的说明写着「格子上的数必须等于点开看到的行数」），而投了就是投了。
    **错的是不说** —— 这一格本来就有说这种话的地方（「另有 N 个被你关掉了」），
    那句存在的理由写着「否则用户会以为岗位凭空少了」，这里一字不差是同一件事。

    ## 理由现数，不写死

    今天 4 个全是判词出局（其中 1 个他后来还标了不投）。明天可能全是「已下线」。
    写死一句，语料一变那句话就成了假话。
    """
    parked = [j for j in jobs if j.get("applied") and not (j.get("funnels") or [])]
    if not parked:
        return 0, ""
    why = []
    if any(is_out_verdict(j.get("verdict") or "") for j in parked):
        why.append("评下来不满足硬性条件")
    if any(j.get("skipped") for j in parked):
        why.append("你标了不投")
    if any(j.get("expired") for j in parked):
        why.append("岗位已下线")
    if not why:
        return len(parked), ""
    return len(parked), (f"另有 {len(parked)} 个你投过的岗不算在这一格："
                         + "、".join(why) + "，都收在下面的搁置区")


def funnels_of(job: dict) -> list:
    """这个岗属于流水线的哪几格。**计数和筛选共用这一个判断。**

    格子可点开筛选，所以「格子上的数」必须等于「点开看到的行数」。两处各写一份
    判断，飘起来是必然的——实测三格全飘了，而且都要等到真有投递之后才显形：

    - 材料就绪：数的时候算上了已投的，筛的时候又排除掉
    - 已投递：数的是台账**行数**，筛的是**匹配上的岗**
    - 面试中：数用 `{interview, offer, hired}`，筛只认 `[interview, offer]`

    这里是**累计口径**（漏斗）：一个岗可以同时在「已投递」和「面试中」里。
    要改成互斥（每个岗只落一格）就改这一个函数，两边自动跟着变。

    标了「不投」的岗虽然做过材料，但它不再是待办——`shortlist` 把它放进搁置区，
    筛选看不到它，所以计数也不能算它。
    """
    # 页面的行集先排掉三类岗：重复挂法（dupOf，不单独占行）、判词出局
    # （不满足硬性条件/跳过/不建议，在搁置区）、标了不投的（skipped）。
    # 格子要和行数相等，这里就得排同样的三类——原来只有材料格排 skipped，
    # 纯 UI 路径即可复现对不上：点「我投了」再点「不投这个岗」，
    # 「已投递」格子数 +1，点开却看不到那一行。
    # 三类搁置走 `is_parked`（正本在 build_dashboard）——「不数它」和
    # 「不催它」得是同一个判断，此前各写一份，`job_next_step` 那份漏了，
    # 90 个搁置的岗照样被催去投递。
    if is_parked(job) or is_out_verdict(job.get("verdict") or ""):
        return []
    out = []
    if job.get("materials"):
        out.append("materials")
        # **「备好没发」单独一个键。** 上面那个 `materials` 是**累计漏斗**口径
        # （投出去的岗也走过这一步，所以它含已投的）—— 那对漏斗是对的，
        # 对「我现在该做什么」是错的：实测 142 里 80 个已经投过了。
        #
        # 而发出去是整条流水线里**唯一要人做的那一步**
        # （`AGENTS.md`「只有一处要人：投出去那一下」）。面板上那句
        # 「你手上已经有 N 个岗材料是齐的」此前只是一句话，点不开 ——
        # 有了这个键，那个数就等于点开看到的行数（同一份 `funnels`，
        # 按构造相等，不是两处各算一遍）。
        if not job.get("applied"):
            out.append("ready")
    if job.get("applied"):
        out.append("applied")
        if (job["applied"].get("status") or "").strip().lower() in INTERVIEW_STATUSES:
            out.append("interview")
    return out

ROOT = Path(__file__).resolve().parent.parent


#: 各渠道的**固有属性**（跟用户无关，写死是对的）：怎么取数、要不要登录态、
#: 能不能拿到 JD 正文。三者都是 2026-08-19 实测结论，出处见
#: `workflows/reference/cdp-portals.md`「各家实际给哪些字段」。
#:
#: **`jd` 这一项 2026-08-19 当天改过一次。** 第一版把前程无忧标成「拿不到 JD」，
#: 依据是「列表卡上没有逐岗详情链接」——那是**没找到**，不是没有：URL 由 JS 现拼，
#: 钩住 `window.open` 就能批量取，详情页本身读得很干净。三家现在都是 True。
#: 这条留着是因为它值钱：面板上一句「读不到详情」会让用户**放弃整个渠道**，
#: 而那句话当时是错的。
#: 每家的实情 + 实测产出。`note` 是**给用户看的**，所以只写他能据以做决定的话。
#:
#: 「抓到多少」不是重点，**「抓到的里面有几个能投」才是**。2026-08-19 实测：
#: 猎聘 2232 个岗出 107 个可投（4.8%）、BOSS 126 出 17（13.5%）、
#: 智联 70 出 4（5.7%）、前程无忧 194 出 **0**。命中率最高的那家抓得最少。
PORTAL_FACTS = {
    "猎聘": {"how": "免登录接口", "needsLogin": False, "jd": True,
             "note": "有公开搜索接口，不碰你的账号，量最大（占了库里八成半）。"
                     "一百个岗里只有五个能投——命中率是四家里偏低的，"
                     "但能投的岗有八成来自它：别家一次就给那么多，命中率再高也乘不上去"},
    "BOSS": {"how": "浏览器读页面", "needsLogin": True, "jd": True,
             "note": "要你在 Chrome 里登录。能投的比例是四家里最高的（约七个岗出一个），"
                     "但一次只给 15 个、没有下一页——抓完就是抓完了，反复抓没用"},
    "智联": {"how": "浏览器读页面", "needsLogin": True, "jd": True,
             "note": "要你在 Chrome 里登录。卡片字段最全、详情页最好读，"
                     "但上海这边挂的薪资普遍偏低，够得着你底线的不多"},
    "前程无忧": {"how": "浏览器读页面", "needsLogin": True, "jd": True,
                 "note": "要你在 Chrome 里登录，否则返回的是本地泛招聘。能翻 50 页最深，"
                         "但它的列表页不给逐个职位的链接，读不到职位描述——"
                         "抓回来的岗大多只能凭标题和薪资判，至今 0 个能投"},
}


#: 「这几类岗要不要看」——用户自己勾，落在盘上（`job_scraper/prefs.json`）。
#:
#: **它们只管「看不看见」，不改判词。** 判词是评估的产物，用户的偏好不该反向改写它；
#: 关掉只是把这类岗从可投名单里滤掉，判词与分数原样留在库里，随时能开回来。
#: 这与「不想看什么」那一块（`hidden.ts`）是同一性质，区别只在：
#: 那份存浏览器、只影响页面；这份落盘，命令行侧的 `/job-rank`、`/job-apply` 也读得到。
#:
#: **三个默认全是「看」。** 尤其代招——2026-08-19 实测某用户 12 个可投岗里 11 个是
#: 猎头/人力资源机构代招，只有 1 个企业直招。默认关掉它等于把国内高端岗位的常态排除掉。
#: 「谁发的」和「什么用工形式」是两件事，后者由硬门按 `employmentType` 判，与这个开关无关。
PREF_FACTS = {
    "agency": {"label": "猎头 / 机构代招的岗",
               "note": "国内高端岗位大多是这么发的；它只影响信息可信度，不代表岗位不真实。"
                       "用工形式是另一回事，由硬性条件按「全职/派遣」单独判"},
    "onsite": {"label": "要驻场 / 长期在客户现场的岗",
               "note": "FDE、交付、解决方案这一类。甲方正式员工被派到客户现场不算外包"},
    "anonymous": {"label": "公司未公开的岗",
                  "note": "猎头代招常见。公司背景查不到，评分说明里会标出来"},
}


def prefs_file(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / "prefs.json"


def prefs_enabled(user: str) -> dict:
    """哪几类岗要看。**缺文件 = 全看**——没设置过不等于全不要。"""
    f = prefs_file(user)
    if not f.is_file():
        return {k: True for k in PREF_FACTS}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {k: True for k in PREF_FACTS}
    return {k: bool(d.get(k, True)) for k in PREF_FACTS}


def set_pref(user: str, name: str, enabled: bool) -> dict:
    if name not in PREF_FACTS:
        return {"ok": False, "error": f"不认识这个选项「{name}」——"
                f"能开关的只有 {'、'.join(PREF_FACTS)}。刷新一下页面再点"}
    cur = prefs_enabled(user)
    cur[name] = bool(enabled)
    f = prefs_file(user)
    f.parent.mkdir(parents=True, exist_ok=True)
    _cli.atomic_write(f, json.dumps(cur, ensure_ascii=False, indent=2))
    return {"ok": True, "name": name, "enabled": bool(enabled)}


#: 驻场的措辞。**标题里几乎不写**，写在 JD 正文里。
ONSITE_WORDS = ("驻场", "外派", "客户现场", "长期出差", "常驻客户")

#: 正文里**才**认的那几个。比 `ONSITE_WORDS` 短一个词，故意的。
#:
#: 「客户现场」在标题里是岗位性质，在正文里多半只是**一件事**：
#:     「根据项目需要前往客户现场，参与需求调研」
#:     「能够适应一定频率的出差及客户现场工作」
#:     「私有化适配：支持产品在客户现场的私有化部署」
#: 实测（2026-08-21，1486 份详情）：正文命中 42 份，其中 22 份**只**因为
#: 这个词——而 `PREF_FACTS["onsite"]` 自己的说明写着「甲方正式员工被派到
#: 客户现场**不算**外包」。把它们标成驻场的代价是实的：用户关掉这个开关，
#: `passesPrefs` 会把这 22 个正常的自研岗从名单里滤掉，而开关旁边那个
#: 「关掉会少 N 个」还理直气壮地把它们算了进去。
#:
#: 剩下四个词说的是**用工安排**（驻场 / 外派 / 长期出差 / 常驻客户），
#: 不是某次去客户那儿。宁可漏标，不可错滤——漏标只是少一个提示，
#: 错滤是让人再也看不到这个岗。
ONSITE_WORDS_IN_BODY = tuple(w for w in ONSITE_WORDS if w != "客户现场")


def _onsite_ids(user: str) -> set:
    """详情库里 JD 正文提到驻场的那些岗（按 `stable_id`）。

    **这是 `pref_tags` 的注释里写了、却一直没做的那一半。** 那段注释写着
    「驻场看标题也看 JD 正文里的措辞——只看标题会漏掉绝大多数（实测只看标题：
    2610 个岗里只认出 4 个）」，而下面那行代码只拼了 `title + employmentType`。
    2026-08-21 面板上的数**正好还是 4** —— 注释记下了问题和修法，修法没落地。

    **id 直接取文件名。** `jd_store.save` 就是按 `stable_id(url, title)` 命名的
    （`jd_store.key_for`），所以 `p.stem` **就是**那个 key。从正文里把它重算一遍
    是白算，而且会掉东西：正文里没有 `url` 的记录（老版本存的、半截的）被
    `if u:` 静默跳过，标题字段与存盘时漂了一个字就算出另一个 id ——
    两种情况都不报错，只是这个岗的驻场标记安静地不见了。

    代价：这是对 `details/` 的**第二遍**扫描，`_stored_details` 那遍不共用
    （实测 1486 份约 100ms，一次性导出里可以忽略，所以没为它做管道）。
    """
    d = ROOT / "users" / user / "job_scraper" / "details"
    if not d.is_dir():
        return set()
    hit = set()
    for p in d.glob("*.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if any(w in (j.get("description") or "") for w in ONSITE_WORDS_IN_BODY):
            hit.add(p.stem)
    return hit


#: **判据搬到 `_cli` 了。** `followups.agency_map` 也要判这件事，而它
#: import 不动这个模块（这里会连带拉起 `build_dashboard`）。原来它自己写了
#: `bool(e.get("isHeadhunter"))` —— 那正是下面那段文档警告的错法：
#: 不看 `recruiter`、且把「没判过」塌成「直招」。实测 2026-08-23：
#: 全库 2630 个岗里 **66 个**两处判定相反，其中 5 个是他真投过的。
#: 名字留在这里，因为本模块内十几处在用它。
_AGENCY_WORDS = _cli._AGENCY_WORDS
via_headhunter = _cli.via_headhunter


def pref_tags(entry: dict, onsite_ids: set | None = None) -> list:
    """这个岗属于哪几类（`PREF_FACTS` 的键）。

    **判据只有这一份。** 面板上的计数、页面上的过滤、命令行侧的跳过，全都读它
    ——两处各写一份判据，必然出现「说会滤掉 1361 个、实际滤掉 1290 个」这种
    对不上的数，而用户没法知道该信哪个。
    """
    tags = []
    if via_headhunter(entry):
        tags.append("agency")
    # 驻场看标题也看 JD 正文里的措辞——只看标题会漏掉绝大多数
    # （实测只看标题：2610 个岗里只认出 4 个；接上正文之后见 `_onsite_ids`）
    blob = (entry.get("title") or "") + " " + (entry.get("employmentType") or "")
    hit = any(w in blob for w in ONSITE_WORDS)
    if not hit and onsite_ids:
        hit = stable_id(entry.get("url") or "",
                        entry.get("title") or "") in onsite_ids
    if hit:
        tags.append("onsite")
    if is_anonymous_employer(entry.get("company") or ""):
        tags.append("anonymous")
    return tags


def pref_rows(user: str, seen: dict, onsite_ids: set) -> list:
    """给面板：每类岗现在有多少个，关掉会滤掉多少。

    **数字要现算。** 只说「要不要看代招」而不说「关掉会少 1361 个」，
    用户没法判断这个开关值不值得动。
    """
    on = prefs_enabled(user)
    # **集合由调用方传进来，这里不自己算。** 各算一遍就是两次扫盘，
    # 中间只要详情库变了，计数和逐岗标记就对不上 —— 而下面那段注释
    # 正是为这件事写的。
    counts = collections.Counter(
        t for v in seen.values() for t in pref_tags(v, onsite_ids))
    return [{"key": k, "enabled": on.get(k, True), "label": f["label"],
             "note": f["note"], "n": counts.get(k, 0)}
            for k, f in PREF_FACTS.items()]



#: 在线简历「多久没刷新」到这个天数就该说一句。出处是 `job-resume.md` 2.6 那张表
#: 自己写的那句：「**两周**没登录的简历，HR 翻不到第几页就停了」——
#: 门槛跟着那句话走，不另立一个数。
#:
#: ## 为什么这件事需要一个落点
#:
#: 同一张表把刷新标成「这张表里**唯一一件每天都要做**的事」，理由是国内平台的
#: 简历库基本按「最近活跃」排序，而 **HR 主动搜人是唯一一条不靠他投递的路**。
#:
#: 而在这之前**没有任何地方记他做过没有**：提醒只在 `/job-auto` 收尾出现、
#: 且只在那一轮真出了材料时才说。后果有三层：
#:
#:   校准不了 —— 昨天刷过和二十天没刷，那句提醒一个字不差；
#:   升级不了 —— 那张表自己写着「三周没刷是建议改」，而没人知道到了三周；
#:   可能压根不响 —— 2026-08-24 那趟 `/job-auto` 出了 0 份材料，
#:                  按规则那句提醒被正确地压掉了，于是他那天什么也没被提醒。
RESUME_STALE_DAYS = 14

#: 刷新记录落在**单独一个文件**里，不塞进 `portals.json`。
#: 那份是 `{渠道: 布尔}`，`portals_enabled` 按布尔读；塞个日期进去，
#: 「关掉的渠道」会因为字典恒真而变成「开着」。
RESUME_REFRESH_FILE = "resume_refresh.json"


def resume_refresh_file(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / RESUME_REFRESH_FILE


def resume_refreshed(user: str) -> dict:
    """`{渠道: "YYYY-MM-DD"}`。没记过就是空的 —— **不是「今天」**。"""
    p = resume_refresh_file(user)
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {k: v for k, v in d.items()
            if k in PORTAL_FACTS and isinstance(v, str)} if isinstance(d, dict) else {}


def set_resume_refreshed(user: str, name: str, day=None) -> dict:
    """记一笔「今天在这家刷了在线简历」。`day=""` 撤销。"""
    if name not in PORTAL_FACTS:
        return {"ok": False, "error": f"不认识这个渠道「{name}」——"
                f"能记的只有 {'、'.join(PORTAL_FACTS)}。刷新一下页面再点"}
    cur = resume_refreshed(user)
    if day == "":
        cur.pop(name, None)
    else:
        cur[name] = day or _dt.date.today().isoformat()
    p = resume_refresh_file(user)
    p.parent.mkdir(parents=True, exist_ok=True)
    _cli.atomic_write(p, json.dumps(cur, ensure_ascii=False, indent=2))
    return {"ok": True, "name": name, "day": cur.get(name)}


def resume_stale_days(user: str, today=None) -> dict:
    """`{渠道: 多久没刷新（天）}`。没记过的渠道**不在这个字典里** ——
    「没记过」和「刷过很久了」是两件事，前者不该被渲染成一个天数。
    """
    out = {}
    t = today or _dt.date.today()
    for name, day in resume_refreshed(user).items():
        try:
            out[name] = (t - _dt.date.fromisoformat(day)).days
        except ValueError:
            continue
    return out

def portals_file(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / "portals.json"


def portals_enabled(user: str) -> dict:
    """哪些渠道开着。**缺文件 = 全开**——没设置过不等于全关。"""
    p = portals_file(user)
    if not p.is_file():
        return {k: True for k in PORTAL_FACTS}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {k: True for k in PORTAL_FACTS}
    # **解得开、但不是字典**，和「没这个文件」是同一件事：没设置过。
    # 上面那句「缺文件 = 全开——没设置过不等于全关」管的就是这个，
    # 只是原来只盖住了「读不出来」，没盖住「读出来是个列表」。
    # 实测 2026-09-01：`portals.json` 写成 `[]`，导出器当场
    # `AttributeError: 'list' object has no attribute 'get'` —— 面板出不来。
    if not isinstance(d, dict):
        return {k: True for k in PORTAL_FACTS}
    return {k: bool(d.get(k, True)) for k in PORTAL_FACTS}


def set_portal(user: str, name: str, enabled: bool) -> dict:
    if name not in PORTAL_FACTS:
        return {"ok": False, "error": f"不认识这个渠道「{name}」——"
                f"能开关的只有 {'、'.join(PORTAL_FACTS)}。刷新一下页面再点；还是不行就重启 python tools/serve.py"}
    cur = portals_enabled(user)
    cur[name] = bool(enabled)
    p = portals_file(user)
    p.parent.mkdir(parents=True, exist_ok=True)
    _cli.atomic_write(p, json.dumps(cur, ensure_ascii=False, indent=2))
    return {"ok": True, "name": name, "enabled": bool(enabled)}


#: 「关掉的那家其实是主要供给」这件事，够不够格说出来。
#:
#: **不是每次都说。** 关掉一家小渠道是正常取舍，报它是噪音；只有当**关掉的那家
#: 累计贡献的可投岗过半**时，「去补新的」这条建议才会明显兑现不了 —— 那时才说。
OFF_SUPPLY_SHARE = 0.5


def _decision_date(overlay_row, decision: str, fallback):
    """这条**出局决定**是哪天下的。不是这个决定就返回 None。

    叠加层一行上只有**一个** `date`，而 `decision` 可能是 `skipped` 也可能是
    `expired`。不比对 decision 就两条线都去读它 —— 于是一个在面板上标了
    「已下线」的岗，会同时报出一个它从没有过的「不投日期」。

    实测 2026-08-25（这一行加进来的当天）：面板上标不投的 96 个，
    带 `skipDate` 的却有 **97** 个；多出来那两个正是标了已下线的。
    `expiredDate` 那一侧本来就有同样的毛病，溢出 8 个 —— 它没露馅，
    只是因为渲染那一支被 `gone` 挡着。**挡得住不等于算得对**：
    别的消费方（导出的 JSON 是给人和别的工具读的）看到的就是错的。

    库里那份 `skip_date` / `expired_date` 是各自独立的键，不会串，
    所以只有叠加层这一侧要比对。
    """
    if isinstance(overlay_row, dict) and overlay_row.get("decision") == decision:
        return overlay_row.get("date") or fallback or None
    return fallback or None


def off_supply(portals: list):
    """关掉的渠道里贡献最大的那家，如果它占了可投供给的大头 → (名字, 个数, 占比)。

    ## 为什么这件事非说不可

    面板会劝「旺季用来补新的」「跑一轮补货」。而实测活动用户 2026-08-24：
    **贡献了 83% 可投岗的那家是关着的**（累计 104 / 全部 124），
    上一轮它一家带来 150 个新岗，开着的三家合计 87 个。
    照建议去补货，拿到的会是应有的三分之一，而没有任何一处说得出为什么。

    ## 判据用累计，不用「现在还剩」

    `sellable` 减掉了已投/已下线/已跳过 —— 越给力的渠道那个数被吃得越干净，
    拿它判会把最该开回来的那家判成最没用的（判据见 `portal_rows` 里
    `ever_ids` 那段）。

    **不替他决定开不开。** 他可能有自己的理由（那家命中率确实低）。
    这里只负责让「补货」这条建议和「供给关着」这个事实在同一屏上出现。
    """
    if not portals:
        return None
    tot = sum(p.get("everSellable") or 0 for p in portals)
    if tot < 10:
        return None                     # 样本太小，说不出「大头」
    off = [p for p in portals if not p.get("enabled")]
    if not off:
        return None
    top = max(off, key=lambda p: p.get("everSellable") or 0)
    n = top.get("everSellable") or 0
    if n <= tot * OFF_SUPPLY_SHARE:
        return None
    # **第四样：它现在是不是还被风控封着。**
    #
    # 开关和封锁是两份状态、两个主人 —— `job-scrape.md` 明写着
    # 「`portals.json` 是**用户**说这一轮开不开，`portal_budget.json` 是
    # **平台**那边的冷却」。上面那三样只读了前一份，于是这句劝导会去劝他
    # 打开一个此刻打开也抓不到的渠道。
    #
    # 实测活动用户 2026-08-25 03:51：猎聘开关是关的，而它的 CLI 通道
    # **正封到当天 11:30**（`fetch_details --missing` 第一个请求就 RATE_LIMITED）。
    # 面板那句写的是「不开回来，这一轮补到的会少一大半。要开就点一下」——
    # 照它点下去，抓到的是 0。
    #
    # 这一行不重判封锁，`portal_rows` 已经把 `blocked` / `blockedHeldHours` 算好了
    # （正本在 `portal_budget.block_state`）—— 这里只把它捎上。
    #
    # ⚠️ **捎的是「已经封了多久」，不是 `blockedUntil`。** 这里原来带的是后者，
    # 而它有两个毛病，叠在一起正好互相遮掩：
    #
    #   1. 它是 `2026-08-27T15:56` 这种 **ISO 机器格式**，`off_supply_note`
    #      直接插进句子里 —— 屏幕上真的会出现「被平台拦着（2026-08-27T15:56 起）」。
    #      （`_say_until` 就是为这个存在的，可它只接在另一条已经没人读的路上。）
    #   2. 它是**解封时刻**，却被那句话用「起」渲染，读起来像「从那时才开始封」。
    #      而 2026-08-26 裁定封控不再自动到期之后，那个时刻根本不会到来 ——
    #      正是 `portal_budget`「报『已经封了多久』，不报『还剩多久』」要去掉的东西。
    #
    # 没被发现是因为**夹具比现实更人性**：测试传的是 `"今天 11:30"`，
    # 一个生产路径永远产不出的值，于是断言绿着，而真实那串 ISO 没人看见。
    held = int(top.get("blockedHeldHours") or 0) if top.get("blocked") else 0
    return (top.get("name") or "?", n, round(n * 100 / tot), held)


def portal_rows(user: str, seen: dict, jobs: list, qlog: list) -> list:
    """给面板的「招聘网站」那一块：每个渠道抓了多少、最近哪天抓的、开着还是关着。

    **数字全部从库里现算**，不另存一份计数——存了就会和库飘。
    """
    on = portals_enabled(user)
    budget = _portal_budget(user)
    by = collections.defaultdict(
        lambda: {"jobs": 0, "sellable": 0, "everSellable": 0, "withJd": 0})
    # **JD 落库率要单列。** 2026-08-19 实测：猎聘 66.3%，而 BOSS 0.8%、智联 1.4%、
    # 前程无忧 **0%**——那时浏览器三家的 JD 在会话里读完就扔了，几乎没进过详情库。
    #
    # **2026-08-27 回头核了一次，这个数动了，而且是这一格起了作用的证明**：
    # 猎聘 75.7%、BOSS **28.6%**、智联 **21.2%**、前程无忧 **24.2%**。
    # 下面那句「静默的 0% 谁也发现不了」说的正是它 —— 摆上面板之后，
    # `jd_store --save` 那条落库路才被真的走起来。
    #
    # 数字更新了，**这一格要不要留着的结论没变**：三家仍在 20-30%，
    # 离「读一次存一次」还差得远，而每一个没落库的 JD 都意味着下次要重开页面。
    # 后果不是「少存一份」：`/job-upskill` 算能力差距、深评复查原文、职位下线后
    # 回查 posting.md，全都拿不到；想补只能重开一次页面，又是一次风控暴露。
    # 这个数**必须摆在面板上**——静默的 0% 谁也发现不了，它就是这么躺了一个月的。
    stored = {d.get("url") for d in _stored_details(user) if d.get("url")}
    for v in seen.values():
        p = qy.norm(v.get("portal"))
        by[p]["jobs"] += 1
        if (v.get("url") or "") in stored:
            by[p]["withJd"] += 1
    sellable_ids = {j.get("url") for j in jobs
                    if is_strong(j.get("verdict") or "")
                    and not j.get("applied") and not j.get("expired")
                    and not j.get("skipped") and not j.get("dupOf")}
    # **`sellable` 是「现在还剩几个能投」，不是「这家给过我几个」。**
    #
    # 两个意思，而面板上只印一个数 ——「2232 个岗 · 5 个可以投」。用户读它时
    # 当成的是**产能**，而它其实是**存量残余**：投过的、下线的、他自己跳过的
    # 全被减掉了，也就是说**越是给力的渠道，这个数被吃得越干净**。
    #
    # 实测活动用户 2026-08-24 —— 两个口径给出完全相反的结论：
    #
    #     渠道      抓到    还剩能投   累计判过能投
    #     猎聘      2232      5          104
    #     BOSS       125      1           16
    #     智联         86      0            4
    #     前程无忧    194      0            0
    #
    # 按「还剩」读：猎聘 2232→5 是四家里最差的一个。
    # 按「累计」读：猎聘一家占了全部可投岗的 83%（104/124），
    # 是其余三家总和的 5.2 倍。
    # 而他把猎聘**关掉了**，同一块面板还在劝他「旺季用来补新的」。
    #
    # 所以两个数都要给，且各自说清是什么。命中率不能单独用来做取舍：
    # BOSS 命中率 30% 最高，但它**一次只给 15 个、没有下一页**（见 `PORTAL_FACTS`
    # 那条 note），率再高也乘不上去。
    ever_ids = {j.get("url") for j in jobs
                if is_strong(j.get("verdict") or "") and not j.get("dupOf")}
    for v in seen.values():
        u_ = v.get("url")
        p_ = qy.norm(v.get("portal"))
        if u_ in sellable_ids:
            by[p_]["sellable"] += 1
        if u_ in ever_ids:
            by[p_]["everSellable"] += 1
    last = collections.defaultdict(str)
    fresh = collections.defaultdict(int)
    for e in qlog or []:
        p = qy.norm(e.get("portal"))
        d = str(e.get("date") or "")
        if d > last[p]:
            last[p], fresh[p] = d, 0
        if d == last[p]:
            fresh[p] += int(e.get("new") or 0)
    import resume_refresh as rr
    _stale = resume_stale_days(user)
    out = []
    for name, f in PORTAL_FACTS.items():
        _rf = rr.WEB_REFRESH.get(name)
        out.append({
            "name": name, "enabled": on.get(name, True),
            "how": f["how"], "needsLogin": f["needsLogin"], "jd": f["jd"],
            "note": f["note"],
            "jobs": by[name]["jobs"], "sellable": by[name]["sellable"],
            # 累计判过「能投」的（不减已投/已下线/已跳过）—— 判据见上面
            # `ever_ids` 那段：这个才是「这家给过我几个」。
            "everSellable": by[name]["everSellable"],
            "withJd": by[name]["withJd"],
            "lastRun": last.get(name) or None, "newLastRun": fresh.get(name, 0),
            # 网页版能不能刷新、入口与判断依据（正本在 `resume_refresh.WEB_REFRESH`）
            "webRefresh": _rf[0] if _rf else False,
            "refreshHow": _rf[1] if _rf else "",
            "refreshSuccess": _rf[2] if _rf else "",
            # 在线简历上次刷新是几天前。**没记过就不给这个字段** ——
            # 给个 null 会被渲染成「0 天」或「很久」，两个都是编的。
            **({"resumeStale": _stale[name]} if name in _stale else {}),
            **_block_state(budget, name),
        })
    return out


def _portal_budget(user: str) -> dict:
    """读额度/冷却状态。读盘与容错都在 `portal_budget.load` 里，这里只是薄封装——
    2026-08-20 收拢，此前这里手写了一遍同样的读文件 + 容错。"""
    import portal_budget as pb
    return pb.load(user)


#: 开场白铁律的判据**正本在 `_cli`**：面板这一处（复制按钮旁的提示）和
#: `audit_pipeline` 的全库审计要用同一份词表。此前两处各写一份、词表不同，
#: 同一件事报出两个数（开场铺垫 32 vs 17）—— 词表就是判据，判据分叉就是两套标准。
GREETING_BANS = _cli.GREETING_BANS
GREETING_MAX = _cli.GREETING_MAX
greeting_problems = _cli.greeting_problems


#: 资料里「这一项我没填」的几种写法。**不是占位符**——占位符（`[YOUR_NAME]`）
#: 由 `doctor.template_tokens` 管，那道门看得见；这几个是用户或 `/job-setup`
#: 真写下去的值，长得像内容，于是完整度检查一路放行。
_NO_VALUE = ("未提供", "未填", "待补", "暂无", "不详", "未确认", "未记录")


def short_rule(t: str, cap: int = 26) -> str:
    """把资料里那一条排除缩成一个标签。

    资料原文是 markdown，而这个标签既上终端也上面板 —— 先过 `plain()`
    （剥标记 + 把内部词换成人话），再截。

    **截断不能按字数硬切**：实测 2026-08-24 切出过「行业背景硬要求那条**不在
    放宽范围**，仍在「明」
    —— 半个词加一个孤零零的引号。按标点找一个能收住的地方。
    （面板上那些字断在半截是这个仓库有名字的一类，判据见
    `audit_pipeline.check_panel_text_is_not_cut_off`。）
    """
    t = plain(t).strip()
    if len(t) <= cap:
        return t
    cut = max((t.rfind(c, 0, cap) for c in "，。；、（("), default=-1)
    return (t[:cut] if cut >= 8 else t[:cap]) + "…"


def top_exclusions(jobs: list, user: str) -> list:
    """他自己划的那几条排除，各挡掉了多少个岗。按个数倒序，最多三条。

    ## 面板上原来只有一个总数

    「卡在硬性条件上的 N 个」那一行已经把「你资料里写明不要的 308」单列出来，
    还给了改它的命令 —— 而 308 是**十一条排除加起来**的数。他打开那份清单，
    十一条一样长，看不出该动哪一条。实测 2026-08-31：最贵的一条一个人
    挡掉 **102 个**，是第二名的 2.7 倍。

    这道门是七道里**唯一他今天就能改的**（`04` 那一节的原话），所以这几个数
    是这一页上最能换来岗位的信息 —— 而它此前只有全量自检在算，
    而全量自检他基本不跑。

    ## 判据与自检同源

    分组走 `_cli.exclusion_tally`（按二字片段归到资料里那一行，
    宁可漏报不可误报），不在这儿另写一套。
    """
    ents = _cli.exclusion_entries(user, root=ROOT)
    if not ents:
        return []
    reasons = []
    for j in jobs:
        if is_parked(j):
            continue
        raw = (j.get("gateFailReason") or "").strip()
        if not raw:
            continue
        gate, _inner = _cli.gate_in_verdict(raw)
        if gate != "候选人明确排除":
            continue
        reasons.append(_cli.exclusion_reason(raw))
    if len(reasons) < 20:
        return []                       # 样本太小，排不出「哪条最贵」
    # **搁置的不算，和上面那一行同一个口径。** 于是这几个数会比自检报的
    # 略小（实测 98 / 102）—— 那不是分叉：自检数的是全库，这一页数的是
    # 屏幕上真在的那些。两边口径都写在各自旁边，别去「对平」它们。
    tally, _blank, _orphan = _cli.exclusion_tally(ents, reasons)
    return [{"rule": short_rule(k), "n": n} for k, n in tally.most_common(3)]


def base_resume_style(pdf: Path) -> list:
    """主简历渲染出来的字里，有哪几句踩了 `03` 的风格铁律。

    ## 为什么面板也要报

    自检从 2026-08-27 起在查这件事，扫的是**全部** 17 份 PDF，报出来的是
    「这一句在 12 份里」。而那 12 份定制版是从主简历复制出去的 ——
    实测 2026-08-31：主简历自己就带着那一句，改一次，12 份下次重出时一起干净。

    也就是说这是这一页上**一次编辑收益最大**的那类提示，而它此前只在
    全量自检里出现，而全量自检他基本不跑。

    ## 判据要拿渲染出来的文本当输入

    照 `.typ` 源文件扫，六成命中的是排版注释（自检那条已经交过这笔学费）。
    所以走 `pdftotext`；没装 poppler 就整条不出 —— 缺依赖不是拒绝理由，
    但也不该拿一个查不了的结论去吓人（自检那边会说明这一条没查）。

    只扫主简历这一份：定制版归 `/job-cv` 重出，而修法写在主简历上。
    实测一次 20ms。
    """
    if not pdf.is_file():
        return []
    try:
        import verify_pdf as _vp
        text = _vp.run_tool(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"])
    except Exception:
        return []                       # 没装 poppler / 读不了：这一栏不出
    return style_rows(text)


def style_rows(text: str) -> list:
    """一段正文里踩了 `03` 的那几句，去重后逐句成行。

    **单独成函数是为了测试能钉住它。** 和 `base_resume_style` 连在一起时，
    要验「同一句不报两遍」就得先造一份 PDF —— 于是那条断言只能去查源码里
    有没有 `seen_line` 这个名字，而变异把判断条件删掉、名字留着，它照样绿。

    去重按整句：同一句在简历里出现两次（正文一次、摘要一次是常态），
    报两遍等于让他改两处，而那本来就是一处。
    """
    out, seen_line = [], set()
    for line in re.split(r"[。！？\n]", text or ""):
        line = line.strip()
        if len(line) < 6 or line in seen_line:
            continue
        hits = _cli.style_hits(line)
        if hits:
            seen_line.add(line)
            cat, word = hits[0]
            out.append(_cli.style_row(cat, word, line))
    return out


def gate_fail_tally(jobs: list) -> list:
    """卡在硬性条件上的岗，按**是哪道门**归一计数。

    ## 这个数原来只能靠悬停一千多次才看得出来

    门名一直**是存着的**：`seen_jobs.json` 里 1136 条硬门 FAIL，1135 条带门名
    （`硬门 FAIL (工作年限)` 这种），99%。可它只出现在一个地方 ——
    「不投的岗位」那 2278 行里、一个小戳的悬浮提示。**全貌看不见。**

    而全貌恰恰是最有用的那一层。实测活动用户 2026-08-22：

        工作年限 446 · 学历与院校 208 · 候选人明确排除 295 · 其余 187

    三件事一眼可见，而它们各自指向完全不同的动作：

    - **工作年限 446（39%）** —— 判据是「要求下限高出他 1 年以上就 FAIL」。
      占到四成说明这不是个别岗挑剔，是**层级整体够不着**：该往下调岗位层级，
      或者去核对年限该按总年限还是方向年限算（两个数不一样，`04` 有规定）。
    - **学历与院校 208（18%）** —— 统招/211/985 这类，改不了。但知道市场
      有近两成对他关着，比不知道强。
    - **候选人明确排除 295（26%）** —— **这是他自己设的过滤器**。每一条排除
      都有价格，而他设的时候看不见价格。这一档必须单独说：它是唯一一个
      「想通了就能改」的。

    归一走 `_cli.gate_of()`，不另造对照表：门名是自由文本，实测 106 种写法
    （「明确排除」「候选人明确排除」「明确排除（行业背景硬要求）」是同一道门）。

    返回 `[{"gate": 正规门名, "n": 个数}, ...]`，按个数倒序；认不出门名的
    归到「没说是哪道」——**那一档要露出来，不许并进「其余」**：
    它量的是**数据缺陷**（执行时漏填了门名），和「这道门确实挡住了人」是两件事。
    """
    #: 门名到**台面上的说法**。`_cli.GATES` 的键是给流程用的内部名，
    #: 只有这一个非改不可：「候选人明确排除」里的「排除」，在这一页已经是
    #: **「不投」那个动作**的同义词（`test_web_copy` 的 `ACTIONS` 盯着这组词）。
    #: 而这一档恰好紧挨着「不投的岗位」摆着——用户会把它读成
    #: 「我在这一页点掉的 405 个」，而它其实是他**资料里写明不要**的那些。
    #: 其余六道本来就是内地求职者自己会说的话，原样用。
    SAY = {"候选人明确排除": "你资料里写明不要的"}
    tally = {}
    for j in jobs:
        # **重复挂法不计。** 它在页面上任何地方都不渲染（行集过滤 `!dupOf`），
        # 算进来就会让这一行的合计大于上一行的「硬性条件没过 N」——
        # 相邻两行、同一件事、两个数。实测差了 14 个。
        # **优先级要和上一行的成分统计一致。** 那一行按
        # 已下线 → 你自己点的 → 规则判的 → 硬性条件 → 分太低 归类，
        # 一个岗只进一档。这里若不跟着排除前两档，同一个「手点不投 + 硬门没过」
        # 的岗会在成分行算「你自己点的」、在这一行算「硬性条件」——
        # **相邻两行、同一件事、两个数**（实测差 4 个）。
        # 三类搁置走 `is_parked`（正本在 build_dashboard）——这里原来是
        # 内联的同一个布尔表达式，2026-08-26 扫重复定义时收掉。
        if is_parked(j):
            continue
        raw = (j.get("gateFailReason") or "").strip()
        if not raw:
            continue
        # 解析走 `_cli.gate_in_verdict()`：括号有全角半角两种写法，判词前缀也有
        # 三种（`GATE_FAIL_PREFIXES`）。「工作年限 + 行业背景硬要求」这种一条挂
        # 两道门的**按第一道算** —— 拆成两条会让总数大于岗数，那一行读起来就
        # 不再是「有几个岗被挡住」。
        gate, inner = _cli.gate_in_verdict(raw)
        # **「写了别的理由」和「什么都没写」不是一回事。**
        # 前者写了（实测 18 个：技术栈 7、地点 4、英语 4、语言 2、行业经验 1、
        # 专业 1），只是没归到七道正规门名上 —— 对用户来说那就是「别的原因」，
        # 是条真信息；后者是漏填，量的是数据缺陷。并成一档就等于说
        # 「这 31 个都是脏数据」，而其中 18 个是实打实的挡门理由。
        key = gate or ("其它原因" if inner else "没说是哪道")
        tally[key] = tally.get(key, 0) + 1
    return [{"gate": SAY.get(g, g), "n": n} for g, n in
            sorted(tally.items(), key=lambda kv: -kv[1])]


def unfilled_gate_inputs(candidate_md: str) -> list:
    """资料里没填、而**七道硬门要用**的取值。返回 `[(字段, 对应哪道门)…]`。

    ## 为什么单挑硬门要用的那几项

    资料里没填的字段多得很，多数只影响一句话写得好不好。**硬门不一样：
    它的取值缺一项，那道门在每一个岗上都判不了** —— 不是判「不适用」，
    是判不了，而这两件事在结果上完全不同。

    实测（活动用户，2026-08-22）：`户口所在地：未提供`，而 257 份有硬门表的评估里
    **72 份干脆没写户口那一行**。他的目标城市全是上海，落户在国内是实打实的
    决策项（有的岗把落户名额当福利写在 JD 里，有的要求本地户口）。
    两件事各自躺着，没有任何地方把它们连起来说一句。

    ## 判据借 `_cli.gate_of()`，不另造一张对照表

    那个函数就是「门名归到七道正规门」的正本（认「户口」「学历」「年限」这些词）。
    资料里的字段名（「户口所在地」）拿它一过就知道属于哪道门 ——
    另写一张「字段 → 门」的表，等着它和正本分叉。
    """
    out = []
    for line in (candidate_md or "").splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*(.+?)[:：]\*\*\s*(.*)$", line)
        if not m:
            continue
        field, val = m.group(1).strip(), m.group(2).strip()
        if not any(k in val for k in _NO_VALUE):
            continue
        gate = _cli.gate_of(field)
        if gate:
            out.append((field, gate))
    return out


#: 国内社招简历的基线章节（`05-cv-templates.md`「简历结构」那一节）。
#: `概念 → 认得出的几种写法`。
#:
#: **查的是「在不在」，不是「排第几」**：那份文档同时写着「章节顺序按行业定一次」
#: （执业资格是准入门槛的行业要把技能提前），顺序本来就允许因行业而异，
#: 而「有没有求职意向」不因行业而变。
#:
#: 「基本信息」不在表里：它在 Typst 模板的页眉参数里，不是一个 `#section`，
#: 照着查必然误报。
CV_BASELINE = {
    "求职意向": ("求职意向", "应聘岗位", "目标岗位", "求职目标", "意向岗位"),
    "个人优势": ("个人优势", "核心优势", "个人简介", "自我评价"),
    "工作经历": ("工作经历", "工作经验", "职业经历"),
    "项目经历": ("项目经历", "项目经验", "代表项目"),
    "教育背景": ("教育背景", "教育经历"),
    "技能": ("技能", "技能与证书", "专业技能", "技能证书"),
}


def sections_written_elsewhere(user: str, missing: list) -> dict:
    """主简历缺的那几节，**在定制简历里是不是已经写过了**。返回 `{节名: 原文那一行}`。

    ## 为什么值得查

    实测（活动用户，2026-08-22）：主简历没有「求职意向」，而 15 份定制简历里
    **有 4 份第二行就写着**

        AI 产品经理（AIGC 内容方向）　｜　上海　｜　期望 45-50k×12（年包约 54-60 万）

    面板此前只说「少一节」——而这句话他早就写过一遍。让他从零想一句，
    和告诉他「你自己写过，在这儿，抄过来」，是完全不同的两件事。

    这与 `channel`、`isHeadhunter`、`date` 是同一个形状：**东西在盘上躺着，
    只是没有人把两头接起来。** 这次躺的位置是他自己的定制简历。

    只取第一份命中的那一行，不做合并：几份定制版的写法可能不同，
    摆一堆让他挑不如给一个能直接抄的。
    """
    if not missing:
        return {}
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return {}
    out: dict = {}
    for f in sorted(apps.rglob("resume.typ")):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for name in missing:
            if name in out:
                continue
            aliases = CV_BASELINE.get(name, (name,))
            for i, ln in enumerate(lines):
                # 命中方式有两种：这一节被显式写成 `#section("求职意向")`，
                # 或者那一行本身就是意向行（岗位｜城市｜期望，没有小节标题）。
                if any(f'#section("{a}' in ln for a in aliases):
                    body = next((x.strip() for x in lines[i + 1:i + 4] if x.strip()), "")
                    if body:
                        out[name] = body[:120]
                    break
                if name == "求职意向" and "期望" in ln and "｜" in ln:
                    out[name] = ln.strip()[:120]
                    break
        if len(out) == len(missing):
            break
    return out


def missing_cv_sections(sections) -> list:
    """基线里有、这份简历里没有的章节。

    ## 为什么要机械地查

    `/job-resume` Step 2.3 早就写着「对照 `05-cv-templates.md` 查章节顺序」——
    可那是让**模型读一遍再写一句话**。实测代价（活动用户，2026-08-22 发现）：
    2026-08-01 那份审阅报告白纸黑字写着

        「结构：求职意向 → 个人优势 → 工作经历 → 项目经历 → 教育背景 → 技能与证书，
          与 05-cv-templates.md 的基线顺序完全一致。」

    而 `resume/main.typ` 里**根本没有「求职意向」那一节**（只有个人优势、
    工作经历、项目经历、教育经历、技能）。报告不但没发现缺章，还把缺的那节
    列进了「完全一致」的证据里。

    **一句散文断言，没有任何东西核对它。** 而 `sections` 一直在导出，
    对照一下就知道 —— 该机械查的事别交给散文。

    在国内社招里这一节尤其不能少：HR 扫简历先找「这人要什么」（岗位 / 城市 /
    期望），再看「这人是谁」。没有它，对方得从经历里自己猜你投的是不是这个级别、
    这个城市，很多人就直接翻过去了。
    """
    have = "".join(sections or [])
    return [name for name, aliases in CV_BASELINE.items()
            if not any(a in have for a in aliases)]


def _audit_day(f):
    """`reports/resume-audit-2026-08-01.md` → `date(2026, 8, 1)`；认不出返回 None。

    月日**不强制补零**：`/job-resume` 写文件名时用的是当时那个格式，
    存量里两种都有，认死一种会把一半的报告判成「没有日期」。
    """
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$",
                 f.stem.replace("resume-audit-", ""))
    if not m:
        return None
    try:
        return _dt.date(*(int(x) for x in m.groups()))
    except ValueError:            # 2026-13-45 这种手写出来的
        return None


def _dated_audits(files: list) -> list:
    """`[(日期, 文件)…]`，只收文件名里认得出日期的那些。"""
    return [(d, f) for f in files if (d := _audit_day(f))]


def _say_until(iso: str) -> str:
    """`2026-08-21T23:14` → 「今晚 23:14」/「明天 07:00」/「08-23 09:15」。

    机器格式不上屏（同 `AGENTS.md`「给用户看的措辞」）。
    读不出来就原样返回 —— 不猜、也不吞掉。
    """
    try:
        t = _dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    now = _dt.datetime.now()
    d = (t.date() - now.date()).days
    hm = t.strftime("%H:%M")
    if d == 0:
        return ("今晚 " if t.hour >= 18 else "今天 ") + hm
    if d == 1:
        return "明天 " + hm
    return t.strftime("%m-%d ") + hm


def _block_state(budget: dict, name: str) -> dict:
    """这家现在是不是被平台拦着，还剩多久，为什么，去哪儿处理。

    **必须显眼地摆在面板上。** 2026-08-19 猎聘把用户账号标成「行为异常」、要短信
    验证——那一刻起这家一个岗也抓不到了，而只有他本人能去过那条短信。这个状态
    如果只活在 `portal_budget.json` 里，用户看到的现象是「怎么最近都没新岗」。

    解析在 `portal_budget.block_state`，这里只做面板字段名的映射——
    此前两边各解析一遍 `blocked_until`（2026-08-20 收拢）。
    """
    import portal_budget as pb
    # **一次 `now()`，喂给下面每一次判定。** 三处各取一次时钟的后果是
    # 塌成一条的 `blocked` 和逐条的 `blockedLanes` 可能算在不同的瞬间：
    # 冷却正好在这几微秒里到点，就得到 `blocked: true` 配 `blockedLanes: []` ——
    # 面板于是说这家被拦住了，却一行告警、一个解封按钮都不给。
    now = _dt.datetime.now()
    st = pb.block_state(budget or {}, name, now)
    # **通道要带出去。** 两种封控在面板上该说完全不同的话：浏览器是「有个验证
    # 只有你能过」，CLI 是「接口在限流，等它自己好，或者探一次」。少了这个字段，
    # 面板只能对两者说同一句，而对 CLI 说的那句每一条都是错的
    # （去处理→没有页面、我处理好了→他什么也没处理）。
    # **「还剩 5 小时」答不了「这时间怎么算的」。** 用户 2026-08-21 直接问了这句。
    # 冷却是**我们自己定的固定值**（`BLOCK_COOLDOWN_H`），不是平台告诉我们的；
    # 从撞上那一刻起算，到点自动解，探测失败不延长。这三件事都要能说出来，
    # 所以把「到什么时候」和「一共多久」一起给前端 —— 前端不自己算。
    #
    # `blockedAlsoStops`：CLI 被封时浏览器**被放慢**（不是停）。
    # 用户 2026-08-21 裁定：浏览器是刻意的、人在场的访问，为 CLI 的限流
    # 把它整整停一天代价太大；改成加大间隔。面板要把这件事说准 ——
    # 说成「也一起停」用户会以为整条渠道没了。
    #
    # ⚠️ **但「放慢」的前提是那条本身还通着。** 两条各自封着时（CLI 撞限流 +
    # 浏览器要短信验证）这句话就成了假的：面板会在「浏览器那条在冷却里」
    # 这一行的正上方写「浏览器那条不停、只是放慢」，用户照它换过去，
    # 一头撞进验证页 —— 正是这整套改动要防的那条升级路径。
    # 正本 `portal_budget.other_lane_note()` 判的就是这一条（它自己的说明
    # 记着「修了一处、漏了对称的另一处」），这里当时抄漏了它。
    _browser_down = pb.block_state(budget or {}, name, now, "browser")["blocked"]
    also = "浏览器" if (st["blocked"] and st["lane"] == "cli"
                     and pb.PRIMARY_LANE.get(name) == "cli"
                     and not _browser_down) else ""
    # **两条通道各自封着时，面板上必须是两行。**
    # `block_state` 不带 lane 时会把一家塌成一条（取 `held_minutes` 最大，平手偏 CLI），
    # 于是另一条**在界面上根本不存在** —— 用户刚在手机上过完浏览器那条短信验证，
    # 点「我处理好了」，按钮送出去的是平台名，`clear()` 按同样的规则挑中 CLI 那条，
    # 于是**他解的不是他处理的那一条**：匿名接口提前恢复，短信验证原样封着。
    #
    # 所以把每条封着的通道单独带出去，并且各自带上**要解它得报哪个渠道名**
    # （`CHANNEL_NAME`）—— 按钮报渠道名，`clear()` 的「给渠道名就只解那一条」
    # 那条分支才用得上，歧义在数据层就消掉了，不靠前端猜。
    lanes = []
    for lg in pb.lanes_of(name):
        one = pb.block_state(budget or {}, name, now, lg)
        if not one["blocked"]:
            continue
        lanes.append({
            "lane": lg,
            "channel": pb.CHANNEL_NAME.get((name, lg), name),
            "why": one["why"],
            # **已经封了多久**，不是「还剩多久」。2026-08-26 封控不再自动到期
            # （`portal_budget._one_lane`），倒计时那个数从此没有意义 ——
            # 留着它只会让人接着等，而等不来。
            "heldHours": max(1, round(one["held_minutes"] / 60)),
            # **不是第一次撞的话，面板也要说。** 「已经停了 16 小时」和
            # 「三天撞了 3 次、每次放行后几分钟又中」会导出相反的决定，
            # 而这一条只在真有流水时才有字（判据在 `pb.streak_note`）。
            "streak": pb.streak_note(budget or {}, name, lg, now).lstrip("。"),
            "until": _say_until(one.get("until") or ""),
            "url": one["where"],
            # 同上：浏览器那条自己也封着时，不能说它「只是放慢」。
            "alsoSlows": "浏览器" if (lg == "cli"
                                    and pb.PRIMARY_LANE.get(name) == "cli"
                                    and not _browser_down) else "",
        })
    # **「有通道被封」和「这家抓不动了」是两回事，前端不该自己推。**
    # 告警条要用它决定说「这家现在抓不了」还是「有一条被拦住了，另一条还能抓」。
    #
    # ⚠️ **这里不能用 `check()`。** 第一版就是那么写的，而 `check()` 回答的是
    # 「此刻能不能发下一个请求」——它会为**纯密度**原因返回 False：
    # 本轮动作用满、两次动作间隔不够、当天请求到顶。实测一个开着轮、
    # 刚做满 10 次动作的 BOSS：`blocked=False` 而 `check()=False`，
    # 于是面板顶出一条 role="alert" 说「BOSS 这家现在抓不了」——
    # 而它只是在按节奏歇 8 秒。**告警说的是封控，不是限速。**
    #
    # 判据回到字面：这家**还剩不剩没被封的通道**。
    # `now` 用上面钉住的那个，别再取一次钟（同上一段的理由）。
    can_scrape = any(
        not pb.block_state(budget or {}, name, now, lg)["blocked"]
        for lg in pb.lanes_of(name))
    return {"blocked": st["blocked"], "canScrape": can_scrape,
            "blockedWhy": st["why"],
            "blockedHeldHours": (max(1, round(st["held_minutes"] / 60))
                                 if st["blocked"] else 0),
            "blockedUrl": st["where"], "blockedLane": st["lane"],
            "blockedLanes": lanes,
            # `blockedUntil` / `blockedTotalHours` 2026-08-26 撤掉了：
            # 它们答的是「到几点自动恢复」，而封控不再自动恢复 ——
            # 屏幕上摆一个会过期的时刻，就是在教用户等。
            "blockedAlsoStops": also}


def _stored_details(user: str) -> list:
    """详情库里有 JD 正文的那些。只读 url，别把几千份正文全载进内存。"""
    d = ROOT / "users" / user / "job_scraper" / "details"
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if len((j.get("description") or "").strip()) >= _cli.JD_MIN_BODY:   # 阈值正本在 _cli
            out.append({"url": j.get("url")})
    return out
OUT_DIR = ROOT / "web" / "public"
PDF_DIR = OUT_DIR / "pdf"

# 判定词 → 四态。顺序有讲究：「FLAG，非 FAIL」必须在 FAIL 之前判掉，
# 否则一条"需注意但通过"的条件会被误读成不满足，让人白白放弃这个岗。
GATE_RULES = [
    ("不适用", "na"),
    ("FLAG", "pass"),          # 「FLAG，非 FAIL」= 过线但要留意
    ("FAIL", "fail"),
    ("PASS", "pass"),
    ("未知", "unknown"),
    ("待确认", "unknown"),
    ("无法", "unknown"),
]


#: 法定月计薪天数（劳社部发〔2008〕3 号）。日薪折月薪用它，不是随手取的 30 或 22。
_PAY_DAYS_PER_MONTH = 21.75
#: 标准工时制每日 8 小时（劳动法第三十六条）。时薪折日薪用它。
_HOURS_PER_DAY = 8

#: 计时/计件类的单位标记。**不同职业的薪酬写法完全不同**——互联网写 `25-35k`，
#: 产线与建筑写 `300-400元/天`，家教与兼职写 `50元/小时`，计件工写 `计件`。
_DAILY = ("元/天", "元/日", "/天", "/日", "日薪", "天薪")
_HOURLY = ("元/小时", "元/时", "/小时", "/时", "时薪", "小时工资")
#: 月薪写成「万」时的上限。超过它就只可能是年包——见 `annual_package` 里的说明。
_WAN_MONTHLY_CEILING = 10

#: 浮动部分：能算出底薪，但**大头不在底薪里**。销售、律师、中介、保险尤其如此。
_VARIABLE = ("提成", "分成", "创收", "绩效", "奖金", "计件", "抽成", "佣金")


def observed_months(jobs: list) -> int | None:
    """库里**明写了薪数**的岗，薪数的中位数。不足 30 个返回 None —— 不猜。

    ## 这个数拿来干什么

    平台只在薪数 >12 时才标 `·N薪`（那是卖点）。没标的按 12 薪保守折 —— 那是对的，
    宁可低不可高。但「保守」到什么程度，此前没有任何地方说得出来。

    实测活动用户 2026-08-22：2554 个有薪资的岗里 **1162 个（45%）没写薪数**；
    而明写的 1346 个里 **12 薪出现 0 次**，分布从 13 起，平均 15.1、中位 15。
    也就是说那个地板价大概率低两三成 —— 而薪资维占 25% 权重，
    实测薪数未知那批的中位分比已知那批低 4 分（51 对 55）。

    **不拿它去改折算**（那会把保守估变成猜测，且这批样本本身有选择偏差：
    肯标薪数的多半就是高的那些）。只用来在悬浮说明里给一句参照，
    让「按 12 薪算」这句话有个量级。

    **从他自己的库里现算，不写死一个数** —— 各行各业的薪数惯例差得远
    （互联网 15、外企 13、部分制造 12），写死一个就变成了行业预设。
    """
    ms = []
    for j in jobs:
        m = re.search(r"[·・]\s*(\d{1,2})\s*薪", str(j.get("salary") or ""))
        if m:
            n = int(m.group(1))
            # 合理区间只有一个出处（`_cli.SALARY_MONTHS_SANE`），别在这儿另写。
            if _cli.SALARY_MONTHS_SANE[0] <= n <= _cli.SALARY_MONTHS_SANE[1]:
                ms.append(n)
    if len(ms) < 30:
        return None
    return sorted(ms)[len(ms) // 2]


def annual_package(salary: str, months) -> dict | None:
    """把各渠道的薪资串折算成**年包区间（万）**。

    页面上原来直接显示原始串：`25-35k·20薪`、`40-70k`、`3.5-5万`、`8千-1.5万`。
    这几种口径混在一起，跨岗**根本没法比**——`25-35k·20薪` 的年包（60-84 万）
    其实高于 `40-70k` 按 12 薪算的 48-84 万的下沿。心算这个不是用户该干的事。

    没写薪数时按 12 薪保守折算，并标 `assumed12`，页面要说出来
    （见 `04-job-evaluation.md`「有月薪、但没写几薪」）。

    ## 不是只有互联网那几种写法

    第一版只认「数字 = k 或万，按月」。喂进别的行业常见的写法就会产出**看着像数的
    错数**——而那正是本仓库最忌的形状（静默做错、看起来像成功）：

        300-400元/天    → 360-480 万      （当成 300-400k/月）
        计件 6000-9000  → 7200-10800 万   （当成 6000k/月）
        25-30元/小时    → 30-36 万        （当成 25-30k/月）

    现在按单位分开算：日薪按法定月计薪天数 21.75 折、时薪再按每日 8 小时折，
    两者都标 `estimated`，页面要说明那是估算。带提成/绩效/计件的只算得出底薪，
    标 `variable` 让页面说清「另有浮动部分未计入」——对销售、律师、中介、保险，
    浮动部分往往才是大头，不说明就是在误导。

    单位认不出来（「面议」「另议」）一律返回 `None`：页面显示「—」是诚实的，
    编一个数不是。

    ## `months` 这个参数可以是 `None`，而且**串写了就以串为准**

    优先级固定是：**薪资串里的「N 薪」 > `months` 参数 > 12 薪保守估**。
    串是原始事实，`salaryMonths` 只是它的一份缓存。

    这一条要写下来，是因为**缺那个字段看起来像 bug，其实无害**：
    实测活动用户 2026-08-30，1831 个有薪资串的岗里 **11 个**串里明写着
    `·15薪` / `·18薪` 而 `salaryMonths` 是空的。看上去像「解析漏了、
    这些岗被按 12 薪低估了 25-50%」—— 但三个消费者（薪资维 `scoring.pay_dim`、
    预筛 `prescreen`、面板薪资栏）**全都走这个函数**，而它自己读串。
    所以那 11 个的年包、分数、档位都是对的。

    ⚠️ **别去「修」成先看字段。** 那会让缓存盖过事实：字段是抓取那一刻记的，
    串是页面上写的，两者不一致时对的是后者。
    `test_the_salary_string_beats_the_cached_field` 钉着这个次序。
    """
    # 判据走 `_cli.salary_unstated`（三处共用一份，见它的文档）。
    t = (salary or "").strip()
    if _cli.salary_unstated(t):
        return None
    # ⚠️ 薪数**优先从字符串里取**。CDP 渠道（BOSS/智联/前程）不填 `salaryMonths`，
    # 「18薪」只存在于原始串里；只读字段会把它当成没写薪数按 12 薪估——
    # 实测把一个 126-180 万的岗算成 84-120 万，低估约 30-50%。
    m_month = re.search(r"(\d{1,2})\s*薪", t)
    n_months = int(m_month.group(1)) if m_month else (
        months if isinstance(months, int) and months > 0 else None)
    # **薪数超出 12–24 一律当没写。** 这条合理性校验原来只写在 `cdp-portals.md`
    # 解 BOSS 混淆字体那一节，用过一次就没人再执行——2026-08-19 审计在存量里翻出
    # 三个：`60-90k·25薪`（150-225 万）、`150-220k·25薪`（**375-550 万**）、
    # `60-90k·30薪`（180-270 万）。平台原样给的就是这个数，但年薪 30 薪不是
    # 一个真实的用工形态，多半是招聘方标错或营销话术。
    #
    # 照单全收的后果不是「数字大一点」：薪资维占 25% 权重，这种量级直接把它顶满，
    # 一个可能并不对口的岗就被推上去了。按本仓库一贯的口径——**解不通就标未知，
    # 不输出半信半疑的数字**——退回 12 薪保守估，并让 `assumed12` 把这件事说出来。
    lo_m, hi_m = _cli.SALARY_MONTHS_SANE
    if n_months is not None and not (lo_m <= n_months <= hi_m):
        n_months = None

    # 取薪数之外的数字当薪资区间，别把「18薪」的 18 也算进去
    body = re.sub(r"\d{1,2}\s*薪", "", t)
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", body)]
    if not nums:
        return None
    lo, hi = (nums[0], nums[1] if len(nums) > 1 else nums[0])
    variable = any(w in t for w in _VARIABLE)

    # ---- 日薪 / 时薪：先折成月薪（元），再走下面的通用路径 ----
    # 这两种在产线、建筑、家政、家教、兼职里是常态，互联网几乎不用。
    # 只按「k 或万」硬算会差两个数量级，而结果长得像一个正常的数。
    per_day = any(w in t for w in _DAILY)
    per_hour = any(w in t for w in _HOURLY)
    if per_day or per_hour:
        if per_hour:
            lo, hi = lo * _HOURS_PER_DAY, hi * _HOURS_PER_DAY
        lo, hi = lo * _PAY_DAYS_PER_MONTH, hi * _PAY_DAYS_PER_MONTH
        # 元/月 → 万/月，再按 12 个月折年
        lo, hi = lo / 10000 * 12, hi / 10000 * 12
        return {"low": round(lo, 1), "high": round(hi, 1),
                "assumed12": False, "estimated": True, "variable": variable}

    is_year = "/年" in t or "年薪" in t
    unit_wan = "万" in body
    # 「万」不写「/年」时默认按月薪——猎聘就是这么给的（`3.5-5万` = 3.5-5 万/月）。
    # 但**数字大到一定程度，它就只可能是年包**：`30-60万（含提成）` 按月算是
    # 360-720 万，这个数不存在。销售、地产、金融的岗位标题里直接写年包区间是常态。
    #
    # 分界取 10 万/月（= 年包 120 万）：到这个量级的岗，招聘页基本都直接写
    # 「年薪」或「100-130k·20薪」，不会用「12万」这种写法让人猜。
    # 实测本机 72 个当月薪解析的「万」值全部落在 1.2-6 区间，离分界还有很大余量。
    #
    # 判成年包的**标 `estimated`**：原文没说按月还是按年，这是推断不是读到的。
    # 串里写明了「N薪」就是月薪的铁证，直接否决年包推断——「10-15万·13薪」
    # 按年包读是 10-15 万，实际是月薪 ×13 ≈ 130-195 万，差一个数量级。
    # 只认**串里自己写的**（m_month）：salaryMonths 字段是详情页另给的，
    # 不能证明串里那个数是月薪口径。
    inferred_year = (unit_wan and not is_year and not m_month
                     and max(nums) >= _WAN_MONTHLY_CEILING)
    if inferred_year:
        is_year = True
    unit_k = bool(re.search(r"[kK千]", body))
    # 元/月 这种写全的（「6000元/月」「月薪 8000」）：数字就是元，不是 k。
    # 认不出单位又没有 k/千/万 时**不猜**——`底薪5000` 猜成 5000k 就是 60 万。
    per_month_yuan = (not unit_wan and not unit_k
                      and (("元" in t) or ("月薪" in t) or ("/月" in t)))
    if per_month_yuan:
        m = n_months or 12
        return {"low": round(lo / 10000 * m, 1), "high": round(hi / 10000 * m, 1),
                "assumed12": n_months is None, "estimated": False,
                "variable": variable}
    if not unit_wan and not unit_k:
        # 光秃秃一串数字，量级完全靠猜——不猜。页面显示「—」，原始串照旧可见。
        return None

    if "千" in body:
        # 「8千-1.5万」这种混用：千的那一段除以 10，万的那一段本来就是万
        lo = lo / 10 if not unit_wan or body.index("千") < body.index("万") else lo
        if not unit_wan:
            hi = hi / 10
    elif not unit_wan:
        lo, hi = lo / 10, hi / 10          # k → 万
    if is_year:
        return {"low": round(lo, 1), "high": round(hi, 1), "assumed12": False,
                "estimated": inferred_year, "variable": variable}
    m = n_months or 12
    return {"low": round(lo * m, 1), "high": round(hi * m, 1),
            "assumed12": n_months is None, "estimated": False,
            "variable": variable}


#: 业务域到这个分以上算「行业对口」——**不叫「主场」**：
#: 那个词在 `gap_split` 里指「专业能力和行业经验两样都对得上」，
#: 而这里只看了行业这一维。实测 2026-08-22：这样算出来的 107 个岗里
#: 66 个（61%）专业能力不够。同一个词两个定义，撞在一个仓库里。
#: `04-job-evaluation.md` 的 60-79 档是
#: 「相邻域，业务语言能迁移」，跨过它才谈得上「这个岗的活你熟」。
SWEET_SPOT_DOMAIN = 60

#: 岗位多久没刷新就算「凉了」。
#:
#: 国内平台自己就按周分桶（猎聘、BOSS 都把「本周活跃」当成好状态摆在筛选里），
#: 两周没刷新意味着招聘方连着跳过了两个周期 —— 多半是招到人了、编制冻了，
#: 或者这个岗根本没人在跟。**投它不是运气差，是投了个没人看的地方。**
#:
#: 只标超过这个天数的：三天前刷新的岗标一句「3 天前刷新」是噪音，
#: 「18 天没刷新」才是要人改主意的那种信息（同「标记要标少数派」）。
STALE_POSTING_DAYS = 14


#: 「同一家你已经投过」这句话里的**「短期内」是多短**（天）。
#:
#: 这个数存在的理由不是精确，是**别让措辞跑在数字前面**。原来这里根本没有数：
#: 计数器数的是「有史以来投过几个」，印出来的话却写着「同一家**短期内**连投几个，
#: 对面看到的是同一个人在刷屏」。实测 2026-08-24 那句话是**碰巧**对的 ——
#: 他 85 条投递全落在 3~14 天内，一条都没出窗口。三个月后同一份台账、同一段代码，
#: 会对着去年的投递印出同一句「在刷屏」。（同一类：`batch_note` 那条
#: 「全库累计数只会随产量涨」。）
#:
#: 取 90 是国内几家大厂 ATS 简历保护期 / 锁定期常见区间（3~6 个月）的**下限** ——
#: 宁可少喊一次，也别在窗口外喊（审计那条「它会一直喊狼来了，然后被人整条关掉」）。
#: 而真正让这个数不必被信任的是**把日期印出来**：他自己看得见「11 天前」还是
#: 「去年 3 月」，不用替我的 90 背书。
SAME_COMPANY_DAYS = 90


def same_company_note(n: int, days: int | None) -> str:
    """还没投的这个岗，它所属的公司你已经投过几个 —— 一句话说完，含日期。

    **句子在 Python 这边拼，TS 侧不另写一套分支**：窗口内外说的话不一样，
    而 `SAME_COMPANY_DAYS` 只许有一份（同文件那条「TS 侧不另写一套状态机 ——
    两份状态机迟早会分叉，而分叉的样子是：页面画出一个按钮，服务端拒绝它」）。

    两个代价不是一回事，所以分开说：

        连投多个岗   对面在一个后台看到同一个人在刷屏 —— **只在窗口内成立**
        撞单         同一家既走猎头报备、自己又直投，用人方那边撞成重复候选人，
                     谁来推、推荐费算谁的都要掰扯 —— 一个岗也会发生，所以不设门槛

    窗口外不是「没事」，是**另一件事**：隔得够久重投不算刷屏，但话术里提一句
    「上次投过贵司」是国内常见失误 —— 对面查得到，而你把「这次也没别的选择」
    写在了脸上。
    """
    if n <= 0:
        return ""
    when = f"，最近一次是 {days} 天前" if days is not None else ""
    recent = days is not None and days <= SAME_COMPANY_DAYS
    out = f"这家你已经投过 {n} 个岗{when}。"
    if n >= 2 and recent:
        out += "同一家短期内连投几个，对面在一个系统里看到的是同一个人在刷屏。"
    if recent or days is None:
        out += "这个岗要是走猎头，先确认他没把你报备到同一家——撞成重复候选人，两条都可能卡住。"
    else:
        out += "隔了这么久，重投不算刷屏；但话术里别提上次投过。"
    return out


def posting_age(entry: dict, today=None):
    """这个岗**多久没刷新**了（天）。没有日期就返回 None。

    ⚠️ **这个数说的是「抓到它那天，它上一次刷新在多久以前」，不是「现在」。**
    去重规则是「见过的岗整条跳过」（`job-scrape.md` Step 4），所以 `date` 在首次
    抓到时就定住了，之后再没更新过 —— 一个岗后来被重新刷新，我们看不到。
    措辞必须跟着这个限制走（面板上写的是「抓到时已 N 天没刷新」，不是
    「招聘方 N 天没刷新」），否则对一个还在被正常维护的岗就是误报。

    数据来自猎聘接口的 `refreshTime`（`liepin-search` CLI 存成 `date`）。
    **只有猎聘给这个字段**，而且它自己也不是每条都给 —— 实测 2638 个岗里
    76 个有（占 4%）。有就用，没有就不说，别拿「不知道」当「很新」。

    这条链子此前断在导出这一层：CLI 抓到了、`seen_jobs.json` 存下了、
    而导出从不带它出来，面板上 0/2632。**这已经是同一批数据里第三个
    「抓到了、存下了、在某一层断掉」的字段**（前两个是 `channel` 和
    `isHeadhunter`），所以这次连同判据一起写在这儿，别再散到调用点上。
    """
    raw = (entry.get("date") or "").strip()
    if not raw:
        return None
    try:
        d = _dt.date.fromisoformat(raw)
    except ValueError:
        return None
    return (( today or _dt.date.today()) - d).days

#: 从候选人资料里抽技能词时，这些**结构词**不算技能——它们出现在任何人的资料里。
#: 只放通用的中文连接/程度词，**不放任何行业词汇**：一放行业词，这份工具就只服务
#: 那一个行业了。
_STOP = {
    "等", "与", "及", "的", "和", "以及", "包括", "相关", "方面", "能力", "经验",
    "熟悉", "掌握", "了解", "精通", "使用", "重度", "主力", "次要", "行业", "领域",
    "约", "年", "多年", "以上", "这一层", "为路径", "以内", "不限", "其它", "其他",
}

#: 抽出来的技能词至少要这么长，才拿去和 JD 比对。太短的（1 个字、单个字母）
#: 会在任何 JD 里命中，产出噪音。
_MIN_TERM = 2
_MAX_TERM = 24


def profile_terms(user: str) -> list[str]:
    """从**候选人自己的资料**里抽技能词——不是从写死的词表里取。

    ## 为什么必须这么做

    第一版把 `Prompt / Agent / RAG / Dify / Cursor` 这类词硬编码在这里。对当时那位
    AI 产品候选人好用，但换成护士、律师、财务的资料，这块面板要么全空、要么答非所问
    ——**那是把一个人的样本当成了所有人的规则**。

    改成从 `profile/candidate.md` 的「技能」小节抽词：用户写什么，就拿什么去比对。
    护士的资料里抽出的是护理术语，财务的是财务术语，这份工具才对所有人成立。

    ## 它能回答什么、不能回答什么

    - **能**：你写在资料里的这些能力，行业对口的岗提了几个？简历里写没写？
      → 找出「**你会、市场要、但简历没写**」——这类不是学习任务，是改简历，一天的事。
    - **不能**：市场反复要、而你**不会也没写**的（真缺口）。那需要中文分词才能从 JD
      里反向抽词，而本仓库零依赖。真缺口交给 `/job-upskill`（它有模型可用）。

    这个分工是干净的：确定性的部分（你会但没写）放面板，需要判断的部分（真缺口）
    放有模型的命令。界面上要把这条边界说清楚。
    """
    p = ROOT / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return []
    t = p.read_text(encoding="utf-8", errors="replace")
    # 只取「技能」那一节，且**遇到任何下一级标题就停**（含 `####`）。
    # 第一版只挡了 `^###\s`，于是 `#### 明确的能力边界` 挡不住，一路吞掉了后面
    # 「能力边界」「补充确认」「开源作品分层」几节——抽出 140 个词，大半是整句散文。
    # 标题**层级不设限**：`profile.example` 模板写的是 `## 技能`（二级），而这里原来
    # 只认 `### 技能`（三级）——照模板建档的每一个新用户，这里都静默抽出 0 个词，
    # 「简历要补什么」整块空白。恰好有一份真实资料用了三级标题，才一直没暴露。
    # 与硬门表「只认字面标题」同病（见 parse_table），判据一律：解析器要照**模板**
    # 写，不照手上那份样本写。
    m = re.search(r"^#{1,6}\s*技能\s*$(.*?)(?=^#{1,6}\s|\Z)", t, re.S | re.M)
    if not m:
        return []
    body = re.sub(r"<!--.*?-->", " ", m.group(1), flags=re.S)
    # 只认**条目行**（`- ...`）。小节里的说明性散文不是技能，混进来会污染比对。
    lines = [ln for ln in body.splitlines() if ln.lstrip().startswith(("-", "*"))]
    body = "\n".join(re.sub(r"^\s*[-*]\s*", "", ln) for ln in lines)
    body = re.sub(r"\*\*[^*]{0,12}：\*\*", " ", body)        # 去掉「**主力：**」这类标签
    # 按中英文标点切开。括注里的并列项（技能名、平台名那一类）也要切进来，
    # 不然整条括注会当一个词留在外面。
    parts = re.split(r"[；;，,、。\n\(\)（）/｜|]+", body)
    terms, seen_t = [], set()
    for raw in parts:
        s = raw.strip().strip("-·*　 ")
        s = re.sub(r"^\**|\**$", "", s).strip()
        s = re.sub(r"(等|的|这一层|层面)$", "", s).strip()   # 「Coze 这一层」→「Coze」
        if not (_MIN_TERM <= len(s) <= _MAX_TERM):
            continue
        if s in _STOP or s.lower() in seen_t:
            continue
        # 纯数字/纯符号不算技能
        if not re.search(r"[一-鿿A-Za-z]", s):
            continue
        seen_t.add(s.lower())
        terms.append(s)
    return terms


#: 职位名里的英文词。**这一层不需要分词**，所以零依赖也做得了。
_TITLE_TERM = re.compile(r"[A-Za-z][A-Za-z0-9+#.]{1,15}")

#: 一个词要在多大比例的对口岗标题里出现，才算「市场在用的叫法」。
#:
#: **5% 是量出来的，不是拍的。** 实测活动用户 2026-08-24（107 个行业对口的岗，
#: 门槛因此是 5 个标题）：过门槛的正好三个 —— `ai` 68（64%）· `agent` 19（18%）
#: · `fde` 10（9%），也就是「他有的两个 + 他没有的那一个」。
#: 门槛之下紧挨着的是 `engineer` 3、`harness` 3；再往下（放到 428 个可投岗上量）
#: 会带出 manager / product / pm / base / leader / digital —— 那些是双语职位名
#: 里的通用填充词，不是叫法。**噪音一进来这一栏就会被整个忽略。**
_TITLE_SHARE = 0.05


def title_terms(sweet: list) -> list[tuple[str, int]]:
    """行业对口的岗**标题**里反复出现的英文词。

    ## 为什么要单独有这一层

    `profile_terms` 的说明里写着它做不到的那一半：

    > **不能**：市场反复要、而你**不会也没写**的（真缺口）。那需要中文分词才能
    > 从 JD 里反向抽词，而本仓库零依赖。

    那句话对**中文散文**成立，对**职位名里的英文词不成立** —— `FDE`、`AIGC`、
    `SaaS`、`ICU`、`IPO` 这类切出来不需要任何分词，正则就够。而它们恰恰是
    国内招聘里最要紧的一类词：**HR 在简历库里搜人，打的就是职位名。**

    ## 它补上的是一个够不到的分支

    `asks` 的循环源是 `profile_terms(user)`（他自己写过的词），而 `inProfile`
    查的是同一个文件的全文 —— 所以 `inProfile` **恒为真**。面板上那个
    「行业对口的岗在要、而你资料和简历里都没有」的分支
    （`notHad = asks.filter(inResume === false && inProfile === false)`）
    **在结构上永远不会渲染**：实测 2026-08-24 导出的 7 条 asks 里，
    `inProfile` 非 true 的有 0 条 —— 那段带着「别直接写进简历」告诫的
    UI，一次都没出现过。词源只有一个的时候，它不可能出现。

    ## 实测（活动用户 2026-08-24，107 个行业对口的岗）

        ai      68 个标题（64%）   简历里有
        agent   19 个标题（18%）   简历里有
        fde     10 个标题（ 9%）   **资料里有、简历里没有**

    第三个就是这一层要报的东西：市场第三常用的那个叫法，不在 HR 会读到的
    那份文件里。而他已经投过 4 个标题带 FDE 的岗 —— 也就是说他自己知道这个词，
    只是简历上没有。放大到全部 428 个可投岗，`fde` 出现在 25 个标题里。

    ## 限制要说清

    只切英文。纯中文的职位名（「主管护师」「结构工程师」）这一层报不出来 ——
    那仍然要分词，仍然归 `/job-upskill`。**报不出来好过报一堆噪音**：
    门槛之下全是双语职位名里的通用英文填充词。
    """
    if not sweet:
        return []
    seen_terms = collections.Counter()
    for e in sweet:
        for t in set(_TITLE_TERM.findall(str(e.get("title") or ""))):
            seen_terms[t.lower()] += 1
    floor = max(3, int(len(sweet) * _TITLE_SHARE))
    return [(t, n) for t, n in seen_terms.most_common() if n >= floor]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def candidate_stage(user: str) -> str | None:
    """资料里的「求职状态」（在职 / 离职 / 在读）。读不出返回 None —— 不猜。

    `season_note` 拿它挑日历。两套日历在**七八月正好相反**：社招那边是淡季
    （HR 休假、面试排不齐），校招那边是**秋招提前批** —— 一个在读的学生八月
    打开面板，照社招那张表会被告知「现在是淡季」，而那正是他该动起来的时候。

    **只认这一个字段，不去猜**（不看年龄、学历、工作年限）。猜错的代价是
    给一个正在秋招的人说「现在别投」。占位符没填时也返回 None。
    """
    # **读原文，不用 `profile_text`** —— 那个走 `_norm`，换行被折掉了，
    # `splitlines()` 会拿到一整行，于是捕获组把下一条 bullet 也吃进来
    # （实测第二版取出来是 `'离职，正在找工作-到岗时间：随时'`）。
    f = ROOT / "users" / user / "profile" / "candidate.md"
    if not f.is_file():
        return None
    t = f.read_text(encoding="utf-8", errors="replace")
    # 资料里那一行是 `- **求职状态：** 离职，正在找工作` —— **冒号在加粗里面**。
    # 先把 `*` 和行首的 `- ` 剥掉再匹配，否则捕获组会吃进 `** `
    # （实测第一版取出来是 `'**离职，正在找工作-*'`）。
    for ln in t.splitlines():
        if "求职状态" not in ln:
            continue
        bare = ln.replace("*", "").lstrip("- ").strip()
        m = re.search(r"求职状态\s*[：:]\s*([^（(]{1,16})", bare)
        if not m:
            continue
        v = m.group(1).strip()
        # 占位符没填时当作「没写」，不是一个叫 `[YOUR_...]` 的状态。
        return None if not v or v.startswith("[") else v
    return None


#: HR 常问那几句的落点。`profile/` 已经在 `AGENTS.md` 的个人数据枚举里，
#: 不必再往那张表加一行。
HR_ANSWERS = "hr-answers.md"


def mark_restale(user: str, jobs: list) -> int:
    """给该重跑一遍的岗打上 `restale`，返回打了几个。

    **这个字段是给 `/job-apply --stale` 选岗用的**，不只是给面板显示。
    `/job-apply` 承诺不依赖 Python（README 与 SETUP 都这么写），所以它只能
    读这份快照 —— 让它去跑 `python tools/stale_materials.py` 就等于毁掉那个承诺，
    也等于让选岗有第二个实现。同一条规矩这个文件里已经写过：
    `dupOf` / `materials` / `applied` 全是这么给的。

    判据整个在 `tools/stale_materials.py` 里，这里**只贴标不重算**。

    已投 / 不投 / 已下线那批从**手上这份 `jobs`** 里现算，不让它回头去读
    `web/public/data.json`：那份文件正是这个函数所在的导出器要写的，
    读它等于拿上一轮的结果算这一轮，而且成环。

    算不出来就一个都不打（面板据此不渲染那一句）——
    一个附加字段不值得让整份导出失败。
    """
    try:
        import stale_materials as sm
        out = {_cli.norm_url(j.get("url") or "") for j in jobs
               if j.get("applied") or j.get("skipped") or j.get("expired")}
        rows, _ = sm.plan(user, out_urls=out)
        why = {_cli.norm_url(r["url"]): r["why"] for r in rows if r["flip"] or r["blind"]}
    except Exception:
        return 0
    n = 0
    for j in jobs:
        tag = why.get(_cli.norm_url(j.get("url") or ""))
        if tag:
            j["restale"] = tag
            n += 1
    return n


def hr_answers(user: str) -> list[dict]:
    """`profile/hr-answers.md` 里那几组「问题 → 答案」。

    ## 为什么要有这份东西

    聊天框里 HR 和猎头反复问的就那么几句（看机会的原因、看哪里、期望多少、
    什么时候到岗……）。**临场编的代价不是慢，是口径不一致** —— 同一个问题在
    打招呼、HR 初面、背调三处说法对不上，正是面试官交叉验证时要抓的
    （`07-interview-prep.md` 那一条）。

    ## 和 `candidate.md` 不是重复

    `candidate.md` 的「离职原因」里有完整版，那是**面试与背调**要用的长度；
    这里是**聊天框**那一版，短、能直接粘。两个渠道两种长度 ——
    合并它们等于让其中一个渠道用错长度。

    ## 解析

    `## ` 开头是问题，到下一个 `## ` 之间是答案。HTML 注释剥掉：那是写给
    填表人和 AI 的（「这一条不该是一个数字」这种），不是要粘给 HR 的话。
    答案剥完是空的 → **仍然返回，标 `empty`** —— 面板要显示「这条还没写」，
    静默跳过等于把没准备的那几条藏起来。
    """
    p = ROOT / "users" / user / "profile" / HR_ANSWERS
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    out: list[dict] = []
    parts = re.split(r"^##[ 	]+(.+?)[ 	]*$", text, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        q = parts[i].strip()
        body = re.sub(r"<!--.*?-->", "", parts[i + 1], flags=re.S).strip()
        out.append({"q": q, "a": body,
                    # 占位符没换掉的也算没写 —— 它比空着更危险：
                    # 看着像准备过了。
                    "empty": (not body) or bool(re.search(r"\[YOUR_[A-Z_]+\]", body))})
    return out


def set_hr_answer(user: str, question: str, answer: str) -> dict:
    """把面板上改过的那一条答案写回 `profile/hr-answers.md`。

    **只换那一节的正文，别的原样留着** —— 文件顶上的说明、每节里给填表人看的
    HTML 注释（「这一条不该是一个数字」那种），都是他下次改的时候要看的。
    整份重写等于把它们冲掉。

    问题认不出来就报错，**不新建一节**：面板上的问题就是从这个文件读出来的，
    认不到只可能是文件被手改过、或者页面比服务旧 —— 那时候静默追加一节，
    用户会得到两个同名问题，而他以为自己改的是其中一个。
    """
    p = ROOT / "users" / user / "profile" / HR_ANSWERS
    if not p.is_file():
        return {"ok": False, "error": "还没有这份常用问答——先跑 /job-setup"}
    text = p.read_text(encoding="utf-8")
    pat = re.compile(r"(^##[ \t]+" + re.escape(question) + r"[ \t]*$\n)"
                     r"(.*?)(?=^##[ \t]|\Z)", re.M | re.S)
    m = pat.search(text)
    if not m:
        return {"ok": False, "error": "这一条在文件里找不到了——刷新一下页面再试"}
    # 注释留在原处：它们是写给下次改的人看的，不该被这次编辑冲掉。
    keep = "".join(x.group(0) for x in re.finditer(r"<!--.*?-->\n?", m.group(2),
                                                   re.S))
    body = (answer or "").strip()
    _cli.atomic_write(p, text[:m.start(2)] + keep + ("\n" if keep else "")
                      + body + "\n\n" + text[m.end(2):])
    return {"ok": True}


def profile_text(user: str) -> str | None:
    """把候选人资料读成一段可搜索的纯文本。读不到返回 None —— 不猜。

    ## 这个函数原来不存在，而有一句话一直假装它存在

    面板「市场怎么读你的简历」那一栏的引导句写着：

    > 你**资料里写过**、行业对口的岗也在要、而简历里没出现的——这些不是学习任务，
    > 是你会但没写上去，改简历就能补

    可 `inResume` 只查了 `resume/main.typ`，**从没查过 `candidate.md`**。
    「资料里写过」这个前提一次都没有被验证过。

    对一个资料里也没有的市场词，那句话就变成了「你会，去写上」——
    而他并不会。往简历里加一条兜不住的东西，正是 `03-writing-style.md`
    铁律 3（能力边界）要挡的事，也是背调和面试里最贵的一种翻车。

    （实测活动用户 2026-08-22 唯一那条缺词「prompt engineering」在资料里**确实有**
    ——这一条碰巧是真的。碰巧成立的前提仍然是没验证的前提。）
    """
    p = ROOT / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return None
    return _norm(p.read_text(encoding="utf-8", errors="replace"))


def resume_text(user: str) -> str | None:
    """把简历读成一段可搜索的纯文本。读不到就返回 None（不猜、不假装比对过）。"""
    p = ROOT / "users" / user / "resume" / "main.typ"
    if not p.is_file():
        return None
    t = p.read_text(encoding="utf-8", errors="replace")
    # 粗暴剥掉 typst 语法：`#let`/`#show` 这类定义行、以及 `#函数(` 的壳。
    # 目的是关键词检索，不是还原排版——剥不干净不影响结论。
    t = re.sub(r"^\s*#(let|show|import|set)\b.*$", " ", t, flags=re.M)
    t = re.sub(r"#\w+\(", " ", t)
    return _norm(t)


#: 环境探测缓存多久。装/卸一个工具之后最多等这么久才反映到面板上——
#: 而那是**几个月一次**的事，导出却是**每点一次按钮**一次。
_ENV_TTL = 300.0


def _env_cache_file():
    """缓存放系统临时目录，按仓库路径分桶。

    **不放仓库里**：它是派生数据，放进去要么污染工作区、要么被 `web/public/`
    连带端给浏览器（那目录是静态服务的根）。按 ROOT 哈希分桶，多个 clone 各用各的。
    """
    import hashlib
    import tempfile
    tag = hashlib.md5(str(ROOT).encode("utf-8")).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"ai-job-search-env-{tag}.json"


def _probe_env_safe(*, force: bool = False) -> list:
    """跑一次环境探测；探测本身失败不该让整个导出挂掉。

    `doctor.probe_env()` 要起几个子进程——实测 **0.47 秒，占整份导出的 21%**。
    装了什么、装没装，与职位数据无关；探测炸了就返回空表，界面那一块不显示，
    而不是连带整份 `data.json` 出不来。

    ## 为什么缓存要落在**磁盘**上，不是进程内

    2026-08-19 profile：一次导出 1.9 秒，其中 0.47 秒是 `node --version`、
    `typst --version` 这四个子进程。而面板**每写一次就重导一次**——点十下
    「我投了」，工具链探测就跑十遍。

    第一版做成了进程内缓存，**一点用都没有**：`serve.py` 的 `_export_now()`
    是**起子进程**跑导出的（那是被静默毁数据咬过两次之后定下的设计，见它的
    docstring），每次都是全新解释器，进程内缓存永远是冷的。

    差点因此把导出搬回同进程——那等于把「服务器用启动那一刻的旧代码、
    在自愈重导时把新格式覆盖回旧格式」这个 bug 请回来。**缓存要迁就架构，
    不是反过来。** 落到磁盘，子进程照起，两边都拿到。

    `force=True` 给「就是要看当前真实状态」的调用方留一条路。
    """
    import json as _json
    import time as _time
    f = _env_cache_file()
    if not force and f.is_file():
        try:
            c = _json.loads(f.read_text(encoding="utf-8"))
            if _time.time() - float(c.get("at", 0)) < _ENV_TTL:
                return c.get("items") or []
        except (ValueError, OSError, TypeError):
            pass                                  # 缓存坏了就当没有，重探一次
    try:
        import doctor
        got = doctor.probe_env()
    except Exception as exc:                      # noqa: BLE001
        print(f"  环境探测失败，面板上「要装的工具」那块将为空：{exc}", file=sys.stderr)
        got = []
    try:
        _cli.atomic_write(f, _json.dumps({"at": _time.time(), "items": got},
                                         ensure_ascii=False))
    except OSError:
        pass                                      # 缓存写不了不算错，下次重探
    return got


def _audit_verdict(path: Path) -> str:
    """从简历审核报告里摘一句结论，给面板做摘要。

    **只摘不塞全文。** 整份报告塞进 `data.json` 会让它膨胀；更要紧的是报告改了、
    导出没跑，面板显示的结论就与文件里的对不上——那比不显示更糟。面板给出文件
    路径，要读全文去开那个文件。
    """
    t = path.read_text(encoding="utf-8", errors="replace")
    # 锚到「## 结论」小节，不靠猜措辞。第一版按关键词（可以/必须改/问题）模糊匹配，
    # 结果一句都没摘到——报告里那句结论用的词恰好都不在猜的那几个里。
    # 结构是 workflows/job-resume.md 规定的，锚它比猜措辞可靠。
    m = re.search(r"^##\s*结论\s*$(.*?)(?=^##\s|\Z)", t, re.S | re.M)
    if not m:
        return ""
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if s and not s.startswith(("-", "#", ">")):
            return s.strip("*").strip()
    return ""


def resume_insight(user: str, seen: dict, details_dir: Path,
                   applied_urls: set | None = None) -> dict | None:
    """从**已有的评估结果**反推「市场怎么读这份简历」。

    这一块刻意不做「简历点评」（措辞、结构、要不要加量化）——那种建议任何工具都能
    给，与本仓库这批评估无关。这里只回答三个别处拿不到答案的问题：

    1. **哪些行业对得上** —— 业务域 ≥60 的岗有多少、集中在哪些行业、反复要什么。
    2. **什么在挡你** —— 硬门与低分的成因分布，以及每样能不能改。
    3. **简历要补什么** —— 行业对口的岗要的词，简历里有没有。

    读不出足够数据时返回 None，面板整块不显示——**没有数据就不说话**，
    比显示一个空面板诚实。
    """
    stacks, domains, sweet = [], [], []
    #: **「行业对口 107 个」是历史统计，不是库存。** 那个数把已投的、
    #: 点掉的、下线的、判词出局的全算在里面 —— 它回答的是「市场里有多大一块
    #: 对得上你」，放在「市场怎么读你的简历」这一节里是对的。
    #:
    #: 可紧挨着它的建议是「认准熟的行业投」「选对岗」，那是**库存**指令。
    #: 实测活动用户 2026-08-23：107 个里已投 22、点掉/下线/低判词 36，
    #: **现在还能投的只有 49 个**。用户读 107 会以为手上还有一百来个可挑，
    #: 而实际是它的一半 —— 同一族的前科：`topReady.ready` 那个局部 0
    #: 盖住了全局 62 个备好的。**两个数要在同一句里说完。**
    still_open = 0
    applied_urls = applied_urls or set()
    for e in seen.values():
        # **回读那两个分只有一份实现**：`gap_split.read_pair`。
        # 这里原来自己写了一遍同样的正则（连「技术栈是旧名」那段注释都是抄的），
        # 而 `applied_jds._pair` 是第三份、宽容度还不一样（它认空格和 `x`/`*`）。
        # 2026-08-21 实测 687 条三者结果一致 —— **但那是运气**：
        # 哪天评估写成 `专业能力 88 × 0.6`，清单读得出、面板读不出，
        # 同一个岗在两处显示不同的分。
        # 正本还多认一种老格式（两笔单列成字段），抄件都没有。
        # （import 在模块顶上——放这儿会**每个条目重跑一次**，`seen` 有几千条。）
        pair = _read_pair(e)
        if not pair:
            continue
        st_, dm_ = pair
        stacks.append(st_)
        domains.append(dm_)
        if dm_ >= SWEET_SPOT_DOMAIN:
            sweet.append(e)
            if (e.get("status") not in ("expired", "skipped")
                    # 判据走白名单正本 `is_sellable`（`bare_verdict` 已剥「粗筛：」前缀）——
                    # 不在这里另写一遍「哪些判词还能投」，那是本仓库栽过两次的地方。
                    and is_sellable(e.get("rank_verdict") or "")
                    and _cli.norm_url(e.get("url") or "") not in applied_urls):
                still_open += 1
    if len(stacks) < 10:
        return None

    def median(xs):
        s = sorted(xs)
        return s[len(s) // 2]

    # ---- 行业对口的岗反复要什么（在它们的 JD 正文里数）----
    bodies = []
    for e in sweet:
        p = details_dir / f"{stable_id(e.get('url') or '', e.get('title') or '')}.json"
        if not p.is_file():
            continue
        try:
            bodies.append(_norm(json.loads(p.read_text(encoding="utf-8"))
                                .get("description") or ""))
        except json.JSONDecodeError:
            continue
    rt = resume_text(user)
    pt = profile_text(user)
    asks = []
    for term in profile_terms(user):
        needle = _norm(term)
        if len(needle) < _MIN_TERM:
            continue
        n = sum(1 for b in bodies if needle in b)
        if not n:
            continue          # 行业对口的岗没提的，不列——这块说的是「市场要什么」
        asks.append({
            "term": term, "n": n, "of": len(bodies),
            # 简历读不到时给 None，界面显示「没比对」而不是「没写」
            "inResume": None if rt is None else needle in rt,
            # 「你资料里写过」这个前提要真的查一遍 —— 判据见 `profile_text`。
            # 读不到资料时给 None（「没比对」），不假装比对过。
            "inProfile": None if pt is None else needle in pt,
        })
    # **第二个词源：职位名里的英文词。** 只有一个词源时，`inProfile` 恒为真
    # （`asks` 的循环源和 `profile_text` 读的是同一个文件），面板上
    # 「资料和简历里都没有」那个分支永远渲染不出来。判据与实测见 `title_terms`。
    #
    # `where` 分开标：正文里提到一个词，说的是「这个岗要它」；**标题里出现，
    # 说的是「HR 会拿这个词搜人」** —— 后者对「简历里写没写」的分量重得多，
    # 界面上要分得开。
    for a in asks:
        a["where"] = "正文"
    _have = {a["term"].lower() for a in asks}
    for term, n in title_terms(sweet):
        if term in _have:
            continue
        needle = _norm(term)
        asks.append({
            "term": term, "n": n, "of": len(sweet), "where": "标题",
            "inResume": None if rt is None else needle in rt,
            "inProfile": None if pt is None else needle in pt,
        })
    asks.sort(key=lambda a: (-a["n"], a["term"]))

    ind = collections.Counter((e.get("compIndustry") or "未标")
                              for e in sweet).most_common(6)

    # ---- 什么在挡你 ----
    gate = collections.Counter(
        str(e.get("rank_verdict") or "") for e in seen.values()
        if str(e.get("rank_verdict") or "").startswith("硬门"))
    n_eng = sum(v for k, v in gate.items() if "英语" in k)
    n_edu = sum(v for k, v in gate.items() if "学历" in k)
    # **这一档要拆成两半，它们的动作是相反的。**
    #
    # 说明里同时给了两条建议：「模板句不当真、照投」和「真卡的是明确要硕士的那些」
    # —— 而屏幕上只有一个数，用户没法知道自己面对的是哪一种。
    # 实测活动用户 2026-08-23：223 个里 **144 个平台字段写着硕士/博士**（他是本科，
    # 问一句也没用），只有 79 个是本科/统招本科/不限（那才是「问一句可能有戏」）。
    # 拿一个 223 去说「投前问一句」，等于让他给 144 个不可能的岗各发一条消息。
    #
    # 判据用平台的 `eduLevel` 字段，不解析 JD 散文 —— 那一层的准确度
    # `check_edu_field_cannot_close` 量过（与正文实测 58% 对不上），
    # 所以它**只用来分档说明，不参与任何判定**。
    _hard_edu = sum(
        1 for e in seen.values()
        if isinstance(e, dict) and "学历" in str(e.get("rank_verdict") or "")
        and str(e.get("eduLevel") or "") in ("硕士", "博士"))
    n_narrow = sum(1 for d in domains if d < 40)
    # **每条阻碍都要带分母。** 这三条来自**两个互不相交的总体**：
    # 英语/学历数的是「硬性条件没过」的那批（`gate`），行业经验数的是
    # 「有四维拆解」的那批（`domains`）—— 过不了硬门的岗通常没有拆解，
    # 两批几乎不重叠。
    #
    # 而屏幕上它们是并排的，紧挨着的引导句刚说完「评过的 N 个岗里」。
    # 裸数字会**继承读者刚看到的那个分母**：实测（2026-08-21）
    # 「英语要求 33」显示在「评过的 687 个岗里」下面，而那 33 个
    # 一个都不在这 687 里面。
    n_gate = sum(gate.values())
    blockers = []
    if n_eng:
        blockers.append({
            "name": "英语要求", "n": n_eng, "of": n_gate, "tone": "fixed",
            # **原来这句建议是「把外企/全球化协作岗写进搜索排除条件」——那是错的，
            # 而且是这个用户资料里已经记过一次的那种错。**
            #
            # 他的边界写着「要求英语面试、口语沟通、日常英文会议的岗排除；
            # 只要求读写的**不排除**（2026-08-12 本人确认，原写「一律排除」范围过宽）」。
            # 实测（2026-08-22）这 36 个判词逐条看下来，写的全是
            # 口语 / 听说 / 流利 / 英语面试 —— **判定是对的**，挡住他的是那几个字，
            # 不是公司性质。而「外企」在国内很多岗是中文工作环境。
            #
            # 照原来那句做的后果有两层：一是把一整类还能投的岗永久关掉，
            # 二是往排除清单里加一条**他资料里没有的条款**，而
            # `job-rank.md` 刚立的规矩是「资料里没有的条款，不许拿来当门」。
            # 面板不该建议用户去违反工具自己的规矩。
            "note": "这些是硬性条件没过的那批岗里、因为英语被挡下的（不在上面那"
                    "「你的主场」的统计里）。逐条看下来要的都是口语、听说、"
                    "英语面试——只要求读写的岗不在这里面，那批照常评。"
                    "口语不是几个月能补的，这一条先认了。"
                    "但别因此把「外企」整类划掉：国内很多外企岗是中文工作环境，"
                    "挡住你的是 JD 里那几个字，不是公司性质。"
                    "想少刷到这类，改搜索词避开「英语面试」「双语」这些信号就行，"
                    "不用新增排除条款。"})
    if n_edu:
        blockers.append({
            "name": "学历/专业", "n": n_edu, "of": n_gate, "tone": "ask",
            # 原来写「按 FLAG 处理」——FLAG 是评估框架里的档位名，屏幕上没解释过。
            # 直接说它对用户意味着什么：这类不当真、照投。
            "note": ("同一批岗里因为学历或专业被挡下的。"
                     + (f"其中 {_hard_edu} 个平台字段写着硕士或博士——那一批"
                        f"问也没用，认了；剩下 {n_edu - _hard_edu} 个是"
                        f"「计算机相关专业优先」这类模板句，不当真、照投，"
                        f"投前问一句卡不卡。"
                        if _hard_edu else
                        "多数只是「计算机相关专业优先」这类模板句，不当真、照投；"
                        "真卡的是明确要硕士的那些。投前问一句卡不卡。"))})
    if n_narrow:
        blockers.append({
            "name": "行业经验太集中", "n": n_narrow, "of": len(domains),
            "tone": "choose",
            # 原来这句把三个内部词搬上了屏幕：「业务域」（四维的维名）、
            # 「技能封顶 65」（打分器内部规则）、「补一个域」。还带着一对**星号**
            # ——JSX 不渲染 markdown，那两个星号是**真的印在屏幕上**的。
            # 说结论，不说打分器怎么算的。
            "note": "这些岗要的行业经验你没做过，光靠通用能力顶不上去，"
                    "所以分上不来。而换一个行业要几个月，你熟的那批岗又够多："
                    "认准熟的行业投，比硬补一个新行业划算。"})

    # **倒序。** 面板拿 `blockers[0]` 印一句「挡你最多的是 X（N）」，
    # 而这个列表此前是按**追加顺序**排的（英语 → 学历 → 行业），从没排过序。
    # 实测活动用户 2026-08-23：屏幕上写着「挡你最多的是英语要求（32）」，
    # 而同一份数据里学历/专业挡了 215、行业经验挡了 319 —— **把最小的那个
    # 说成了最大的**，而且指错了方向：真正挡他最多的正是行业经验
    # （这也是这批评估反复指向的那一件事）。
    #
    # 三项的分母不一样（英语/学历是 960 个硬门 FAIL，行业经验是 687 个评过分的），
    # 但展开的列表逐行印着 `n/of`，看得见；标题只印 `n`，而 319 个岗确实比
    # 215 个多。按率算也是同一个次序（46% > 22% > 3%），不会打架。
    blockers.sort(key=lambda b: -b["n"])

    return {
        "sweetSpot": {
            "count": len(sweet),
            "total": len(domains),
            "withBody": len(bodies),
            "industries": [{"name": k, "n": v} for k, v in ind],
            #: 这 `count` 个里，**现在还能投出去的**有几个（未投、未点掉、
            #: 未下线、判词还在可投三档）。见上面 `still_open` 那段。
            "open": still_open,
            "asks": asks,
            "resumeChecked": rt is not None,
        },
        "medianStack": median(stacks),
        "medianDomain": median(domains),
        "blockers": blockers,
    }


#: 渠道内部键 → 界面上的名字。**键的正本是 `query_yield.PORTAL_ALIAS`**，
#: 显示名的正本是 `_cli.PORTAL_DISPLAY` —— 这里只做一次合成，不再抄一份键。
#:
#: 抄一份的代价这张表自己吃过两次，原来那段注释逐字记着：
#: 「后缀随驱动方式增生，这张表要跟着长 —— 与 `query_yield.PORTAL_ALIAS` 同一个坑」
#: （2026-08-19 用浏览器扩展抓的 115 个岗 portal 写成 `*-browser`，不在表里，
#: 面板上全显示成「某招聘网站」），以及「历史上还直接写过中文名，一并认
#: （`query_yield.PORTAL_ALIAS` 早就认了，这边漏了）」。**两次都是一边补、一边没补。**
#:
#: 键对不上的后果不变：`liepin-search` 这种内部键会直接印到界面上（实测 73 个岗中招）。
PORTAL_NAMES = {k: _cli.PORTAL_DISPLAY[v]
                for k, v in qy.PORTAL_ALIAS.items()}


def stable_id(url: str, title: str) -> str:
    """按 URL + 职位名派生的**稳定** id。

    原来用枚举序号（`f"j{i}"`）——`seen_jobs` 增删一条，后面所有 id 全部错位。
    浏览器里按 id 存的任何状态（「已发」勾选、「不投」标记）就会张冠李戴：
    你排除了 A 岗，下次重新生成后被隐藏的是 B 岗。

    带上职位名是因为 51job 实测同一 URL 下挂着两个不同职位
    （见 `workflows/reference/cdp-portals.md`），只用 URL 会让两个岗共用一个 id。
    """
    h = hashlib.sha1(f"{url}#{title}".encode("utf-8")).hexdigest()
    return "j" + h[:10]


def portal_name(portal) -> str:
    """内部渠道键 → 用户看得懂的名字。

    没登记的键**不要原样显示**——`liepin-search`、`51job-cdp` 这种是实现细节。
    退回一个中性说法，并保留原值在 tooltip 之外的地方也不显示。
    """
    p = (portal or "").strip()
    if not p:
        return ""
    if p in PORTAL_NAMES:
        return PORTAL_NAMES[p]
    # 兜底：按域名词根猜，仍猜不出就说「某招聘网站」而不是印内部键
    for k, v in PORTAL_NAMES.items():
        root = k.split("-")[0]
        if root and root in p:
            return v
    return "某招聘网站"


def salary_months_unknown(salary: str) -> bool:
    """月薪串里没写「几薪」→ 年包算不出来，页面要提示。

    这条提示原来只在虚构演示数据里出现过——导出器根本没设这个字段，于是
    「4-6万/月 × 几薪？」这个年包歧义在真实数据上一个字都不提。
    实测 posting.md 明明记着「4-6万（月薪，未标薪数）」，seen_jobs 只存了「4-6万」。

    判定：有数字、不是年薪（无 `/年`）、也没写薪数（无 `N薪`）→ 未知。
    """
    t = (salary or "").strip()
    if _cli.salary_unstated(t):
        return False               # 「薪资面议」「空」不是「没写薪数」的问题
    if "/年" in t or "年薪" in t:
        return False               # 本来就是年包
    return not re.search(r"\d+\s*薪", t)


#: 判定码不是地名。`/job-rank` 的回传格式里，地点那道门的判定的键名一度与
#: 职位记录的 `location`（城市）撞名，照着回填的写手就把 `PASS` 写进了城市栏，
#: 面板的地点列直接显示它（实测 8 个岗）。正本已改：判定只住在 `hard_gates` 里。
#: 这里兜住已经落盘的那几条，以及以后再撞一次的。
_VERDICT_ONLY = re.compile(
    r"^(?:PASS|FAIL|FLAG|通过|不通过|满足|不满足|要留意|未知|不适用|不计权重)"
    r"(?:\s*[（(][^（）()]*[）)])?$",
    re.I)


def short_location(loc: str) -> str:
    """地点只留到区级。

    猎聘 detail 返回的是整段街道地址（「上海-杨浦区中国大陆上海市杨浦区民府路678号
    上海新江湾广场T2号楼，邮编：200082」），原样塞进列表行会把一行撑成两行，
    而多出来的那些字对「投不投」没有任何帮助——通勤判断到区就够了。
    """
    t = (loc or "").strip()
    if not t or _VERDICT_ONLY.match(t):
        return ""
    parts = [p for p in re.split(r"[-·]", t) if p.strip()]
    if len(parts) >= 2:
        city, dist = parts[0].strip(), parts[1].strip()
        # 「杨浦区中国大陆上海市杨浦区民府路…」→ 只取到「区」为止
        m = re.match(r"(.{1,6}?[区市县镇])", dist)
        return f"{city}·{m.group(1) if m else dist[:6]}"
    return t[:12]


def clean(t: str) -> str:
    """去掉 markdown 标记，只留人读的字。"""
    return t.replace("**", "").replace("`", "").strip()


#: 「不判 FAIL」「非 FAIL」「不算 FAIL」——**被否定掉的判定词不算判定词**。
#: GATE_RULES 的排序只挡得住「FLAG，非 FAIL」那一种（FLAG 排在 FAIL 前面，先命中）。
#: 实测（2026-08-20）2 个岗栽在没有 FLAG 托底的那种：状态格写「待确认，不判 FAIL」，
#: 子串撞上 FAIL 判成不满足，而判词仍是「值得投」——页面同时印着
#: 「有一条不满足就别投」和「值得投」，自相矛盾。
#: 全库 57 处否定写法，其中 12 处没有 FLAG 兜底。
#: 靠排序绕开否定是碰运气，识别否定才是机制。
NEGATED = re.compile(r"[不非](?:判|算|是|等于|作)?\s*(FAIL|PASS|FLAG)")


#: **整格就是这几个词**时的判定。与 `GATE_RULES` 的子串匹配分开，
#: 因为它们当子串太危险：「不过」在中文里也是「然而」——
#: 「PASS，不过要留意」按子串会被翻成「不满足」。
#:
#: 这批词是 2026-08-21 从**用户的 285 份真实评估**里数出来的：判定格里有
#: 35 处显示层认不出，其中 16 处是真的显示错了（其余 19 处是「未知」「待确认」
#: 「已下线」，本来就该是「结论不明」）。
#:
#: 最要紧的一处：某个岗评估的标题写着「两种算法都不过你的底线」，
#: 而判定格写的是「不过（见上）」—— 面板把这个岗**最决定性的一条**
#: 显示成了「未知」。
#:
#: 规格规定的是 `PASS` / `FAIL` / `FLAG` 三个码（`04-job-evaluation.md`），
#: 这些是执行者自造的。**规格那头也补了**（见那份文件），但存量的两百多份
#: 不会为一条新规矩重跑 —— 所以最后一道仍是显示层。
GATE_EXACT = {
    "不过": "fail",        # 「不过（见上）」——薪资底线那类
    "不过关": "fail",
    "不减分": "pass",      # 专业清单从硬门放宽为减分之后出现的写法
    "需留意": "pass",      # FLAG 的中文说法
    "需处理": "pass",
}

#: 上面判 `pass` 的那三个词，规格里写的是**满足（带提醒）**，不是干净的满足
#: （`04-job-evaluation.md` 那张表）。「带提醒」那一半原来整个丢了：
#: `gate_state` 给 pass、而 `gate_why` 只认字面 `FLAG`，于是判定格写「需留意」的
#: 那条渲染成一个不带任何提醒的「满足」章 —— **正是那张表想防的静默降级**。
#:
#: 状态仍是 pass（和 `FLAG` 一样），提醒挂在依据里。三个词各说各的话：
#: 「不减分」是不扣分但仍有事，「需处理」是有一件事等你去办，两者都不是「刚过线」。
GATE_FLAGGED = {
    "不减分": "这条不扣分，但仍要留意",
    "需留意": "刚过线，留意",
    "需处理": "过了，但有一项要你去处理",
}


def _bare(verdict: str) -> str:
    """剥掉粗体标记、括注与空白，取判定格的**主词**。

    「**不过**（见上）」→「不过」。括注是解释，不是判定。
    """
    # `re` 顶上就 import 了；这里再 import 一次是每格判定多一次 sys.modules 查表。
    # `_bare` 在硬门那层的热路径上（本文件下面测过那一层 7873 次调用 / 0.50 秒）。
    v = re.sub(r"[*`\s]", "", verdict or "")
    v = re.sub(r"[（(][^）)]*[）)]", "", v)
    return v.strip("：: 　")


def gate_state(verdict: str) -> str:
    verdict = NEGATED.sub("", verdict)
    # 先看整格是不是那几个自造词 —— 子串匹配对它们不安全。
    bare = _bare(verdict)
    if bare in GATE_EXACT:
        return GATE_EXACT[bare]
    for token, state in GATE_RULES:
        if token in verdict:
            return state
    return "unknown"


#: 评估正文里可能出现的内部标识 → 用户看得懂的说法。
#: 这些是 CLI 的字段名与文件名，实测漏到过界面上：
#: 「强度与公司性质：公司规模（compScale/Stage 空）＝信息缺失中性」
#: 每项 = (内部词, 换成什么, 后面跟着这些字**就不换**)。第三项见 `plain()` 的说明。
#: ⚠️ **`compStage` 不叫「融资阶段」。** 它混了三条轴 —— 融资阶段（A/B/C轮…）、
#: 上市板块（科创板 / 港股…）、以及**所有权性质**（民营 / 国企 / 事业单位 / 合资 /
#: 外资）。实测活动用户 2026-08-23：2638 个岗里「民营」116 个、「不需要融资」87 个、
#: 国企/合资/外资各写法 63 个 —— 把这些译成「融资阶段」，屏幕上就会出现
#: 「融资阶段：国企」。取值枚举与各自怎么读，见
#: `04-job-evaluation.md`「工作强度与公司性质」那张表。
INTERNAL_TERMS = [
    ("compScale/Stage", "公司规模与公司性质", ""),
    ("compScale", "公司规模", ""),
    ("compStage", "公司性质 / 融资阶段", ""),
    ("compIndustry", "所属行业", ""),
    ("salaryMonths", "几薪", ""),
    ("workYears", "年限要求", ""),
    ("eduLevel", "学历要求", ""),
    ("isHeadhunter", "是否猎头", ""),
    ("candidate.md", "你的资料", ""),
    ("profile/", "你的资料", ""),
    ("seen_jobs.json", "抓取记录", ""),
    # ---- AGENTS.md「给用户看的措辞」对照表 ----
    # 上面那批是字段名，这批是**框架词**。它们同样漏到了界面上，而且量大得多：
    # `/job-rank` 写的「依据」原样进了短名单行的悬浮提示，实测约 70 个岗的提示里
    # 带着「硬门 FAIL」「框架硬门表」。之所以一直没被发现，是因为
    # `test_display_wording.py` 用的是合成 fixture，不含真实的「依据」文本。
    #
    # **长的必须排在短的前面**：先换「硬门 FAIL」，否则「硬门」先被换掉，
    # 剩下一个孤零零的英文 FAIL 留在屏幕上。
    # 「业务域」是四维里那个子项的名字，屏幕上从没解释过。实测它印在
    # 「对口的地方」的依据里：「专业能力 88×0.6 + 业务域 65×0.4 + 加分项 +2」。
    # 换成求职者自己会说的话。
    #
    # **算式那一半原来只写了「不是换词能解决的，见 apply.md 的规定」就放过去了。**
    # 于是它在屏幕上又活了很久：2026-08-18 实测导出的 `data.json` 里 176 条依据
    # 带着完整算式。上游怎么写确实归 `workflows/job-apply.md` 管，可**这里是
    # 最后一道显示层**——上游改了规矩，存量的两千多条评估也不会为它重跑一遍。
    # 现在算式走下面的 `strip_weights`：不是换词，是把权重整段拿掉。
    ("业务域", "行业经验", ""),
    # 「不判 FAIL」走不了下面那条通用规则：换出来是「不判不满足」——
    # 一个**双重否定**，读着像打错字。更糟的是 `plain()` 结尾那步收缝
    # 会把中间的空格吃掉，把它焊死成一个词。
    # 实测（2026-08-21，读 applied_jds 的产出时发现）面板上 24 处在这么显示。
    # 引号把被否定的那个词括起来，双重否定就散了：
    # 「未知硬性条件标注不按「不满足」算」。
    ("不判 FAIL", "不按「不满足」算", ""),
    ("不判FAIL", "不按「不满足」算", ""),
    ("硬门 FAIL", "不满足硬性条件", ""),
    ("硬门FAIL", "不满足硬性条件", ""),
    # ---- 裸的英文状态码。AGENTS.md 明令禁的那类「未解释的英文码」。 ----
    # 实测「技能」列的悬浮说明里 FLAG 出现 40 次、FAIL 26 次：
    # 「FLAG：JD 写『中英文沟通清晰』」「未知硬性条件标注不判 FAIL」。
    # `gate_why()` 早就在硬性条件那一侧剥掉了这三个词，而「依据」这一侧没剥——
    # 同一套码，两条路只治了一条。**长的排在前面**（上面两条带「硬门」的先换）。
    #
    # 第三项那个守卫是必须的：这三个都是**别的英文词的前缀**。裸替换会把
    # FAILURE 切成「不满足URE」、PASSION 切成「满足ION」、FLAGSHIP 切成
    # 「要留意SHIP」——JD 原文里这类大写词并不稀奇（口号、产品名）。
    # 后面跟字母就不换，等于给它补了个右边界。
    ("FLAG", "要留意", "A-Za-z"),
    ("FAIL", "不满足", "A-Za-z"),
    ("PASS", "满足", "A-Za-z"),
    # ---- 框架自己的文件名。和上面 candidate.md / seen_jobs.json 同一类。 ----
    ("job-rank.md", "打分规则", ""),
    ("job-apply.md", "出材料的流程", ""),
    ("evaluation.md", "评估记录", ""),
    # 「框架」= 这套评估规则，用户没见过这个词。只换成短语的那两种用法，
    # 不裸换——JD 里「LangChain 框架」「前端框架」都是正常中文。
    ("框架的硬性条件", "打分规则的硬性条件", ""),
    ("按框架", "按打分规则", ""),
    ("硬门", "硬性条件", "槛"),          # 「硬门槛」是地道中文，别动
    ("能力边界缺口", "经历对不上的地方", ""),
    # ---- 2026-08-21 补的三个。实测导出里 502 处内部词，这三个占 491 处。----
    #
    # **搭配要分开写，别只留一个裸词。** 实测分布：
    #   「…明确的能力边界。」约 70 处 · 「在你的能力边界外」约 74 处
    # 裸词换成「经历对不上的地方」会得到「明确的经历对不上的地方」——
    # 比不换更难读。所以按真实搭配各给一条，**长的排前面**（表的老规矩）。
    #
    # 「你的能力边界外」必须单列在「能力边界外」之前：只写后者会替换成
    # 「在你的**你说过不做的范围**外」，那个「你的」重了。
    ("你的能力边界外", "你说过不做的范围之外", ""),
    ("能力边界外", "你说过不做的范围之外", ""),
    ("明确的能力边界", "你说过自己不做的事", ""),
    # 判词 277 处，几乎全是「判词被技能 N 档压到…」——换「结论」正好，
    # 而且评估文件里那一节本来就叫 `## 结论：`（`build_dashboard` 拿它当锚点）。
    ("判词", "结论", ""),
    # 「四维」是**真词的前两个字**：四维图新（NavInfo，北京上市公司，会出现在
    # 抓来的公司名里）、四维彩超、四维空间、四维立体。裸换的后果实测过：
    # `plain("这家是四维图新")` → 「这家是**评分明细**图新」。
    # 而它换对的次数少得可怜——全量 2632 个岗导出后只命中 2 处，其中一处
    # （JD 里的「需要四维总结案」）还是换错的。守住这几个搭配的头一个字。
    ("四维", "评分明细", "图彩空立超"),
    #
    # ⚠️ **裸的「能力边界」有意不映射，别来补完它。**
    #
    # 补完之后剩下 61 处，逐条看过：**大多数根本不是框架词**，
    # 是招聘方在 JD 里说「模型的能力边界」——
    #     「对 AI 能力边界有体感」「在模型能力边界里做取舍」
    #     「Agent 能力边界，理解 RAG」
    # 映射裸词会把它们变成「对 AI **你说过自己不做的事**有体感」，
    # **比不换坏得多**。
    #
    # 这就是这张表为什么按**搭配**写、还带 `guard` 列：同一个串在一处是
    # 内部词、在另一处是正常的行业说法。`硬门` 的 `槛` 守卫（「硬门槛」）
    # 和 `信息质量` 的 `差好高低不` 守卫（「信息质量差」）是同一个道理。
    ("信息质量", "待核实的信息", "差好高低不"),  # 「信息质量差」同理
    ("短名单", "可以投的岗位", ""),
    ("台账", "投递记录", ""),
    ("驾驶舱", "总览", ""),
]

#: 上表编译好的样子。**`plain()` 每次调用重建一遍是白干的**：
#: 表是模块常量，`re.escape` 的结果和守卫后视断言一个字都不会变。
#: 实测一次导出 `plain()` 走 4257 次（`lru_cache` 基本全是 miss），
#: 每次重建 35 条 → 约 15 万次 `re.escape`、18 万次 `re.sub`。
#: 拿 `data.json` 里 4000 条真串量过：每次重建 0.107 秒，预编译 0.036 秒，
#: 输出逐字节相同。而这条路在 `serve.py` 的请求路径上——面板上点一下状态，
#: 下一次取数就重导一遍。
_TERM_PATS = [(re.compile(re.escape(a) + (f"(?![{g}])" if g else "")), b)
              for a, b, g in INTERNAL_TERMS]


#: 打分器的算式。**权重不上屏**——这条规矩 `web/README.md` 和 `JobReadout.tsx`
#: 顶上都写着（「占 30% 对用户没有行动意义，他要的是投不投、为什么、怎么投」），
#: 而「技能与经验」这一维的依据一直原样带着算式：实测导出的 `data.json` 里有
#: **176 条**长成「专业能力 88 × 0.6 + 业务领域 65 × 0.4 + 加分项（合计）+2」。
#: 两个乘数是打分器的内部参数，读的人既改不了也用不上；有信息量的是那两个分。
#:
#: 换词表治不了它（`INTERNAL_TERMS` 是逐词替换），所以单独一条正则。
#: 上游怎么写由 `workflows/job-apply.md` 管，这里只保证**屏幕上**不出现算式——
#: 存量的两千多条评估不会为这件事重跑一遍。
#:
#: **正则本身是 `gap_split.FORMULA`**（顶上一次性 import 进来的 `_FORMULA`）。
#: 同一条式子在这儿是「剥掉它」、在那儿是「读出那两个分」，用途不同、认的字
#: 必须一样：抄一份过来的下场当天就见过 —— 抄件收窄了一条（`×0.4` 变成必填），
#: 于是「剥得掉但读不出」的岗从所有按分统计的口径里静默消失。
#: 算式后面常跟一条加分项。0 分的直接删（一个不改变任何事的 0），非 0 的留成人话。
#: 「加分项」后面跟的修饰词有三种写法（合计 / （合计） / 修正），实测都出现过——
#: 只认前两种时「加分项修正 +0」有 72 条原样留在屏幕上。
_BONUS_TAG = r"加分项(?:（合计）|合计|修正)?"
#: 零加分整段删。**尾词也要带走**：「加分项 0/5 命中」原来只删到 `0/5`，
#: 屏幕上留下孤零零一个「命中」——2026-08-20 实测，读起来像命中了什么。
_BONUS_ZERO = re.compile(r"\s*[+＋]\s*" + _BONUS_TAG
                         + r"\s*[+＋]?\s*0(?:/\d+)?\s*[项分]?\s*(?:命中|符合)?")
#: 数量部分**原样带过去**：「加分项 2 项」是两条加分，「加分项修正 +4」是加 4 分，
#: 两种意思不同，统一改写成任何一种都会说错一半。
_BONUS = re.compile(r"\s*[+＋]\s*" + _BONUS_TAG + r"\s*([+＋]?\s*\d+(?:/\d+)?\s*[项分]?)")
#: 结尾的「= 61」也删：总分就印在这一行左边那个大字上。
_EQ_TOTAL = re.compile(r"\s*=\s*\d+\s*$")
#: 另一种写法：句子先用中文说了两个分，末尾再补一遍算式
#: 「…领域 40：…。61 = 75×0.6 + 40×0.4」。两个分已经在正文里了，算式整段删。
_TRAILING_EQ = re.compile(
    r"[。.]?\s*\d+\s*=\s*\d+\s*[×xX*]\s*0\.6\s*\+\s*\d+\s*[×xX*]\s*0\.4\s*[。.]?\s*$"
)


def strip_weights(text: str) -> str:
    """把打分算式换成两个读得懂的数。**只动屏幕上的那一份**，不改评估原文。

    「专业能力 88 × 0.6 + 业务领域 65 × 0.4 + 加分项（合计）+2」
      → 「专业能力 88 · 行业经验 65 · 另有加分 +2」
    「专业能力 88 × 0.6 + 业务领域 60 × 0.4 + 加分项 1 项（有 Agent 经验）」
      → 「专业能力 88 · 行业经验 60 · 另有加分 1 项（有 Agent 经验）」

    加分那一段的数量**原样带过去**（`+2` 还是 `1 项`）：两种写法意思不同，
    统一改写成任何一种都会说错一半。加分为 0 时整段删掉——那是一条不改变
    任何事的信息。
    """
    out = _TRAILING_EQ.sub("。", text or "")
    # **还有一种没有标签的写法**：`按 04 第 1.3 节算式应为 66（70×0.6+60×0.4=66.0）`。
    # `_FORMULA`（= `gap_split.FORMULA`）认不了它——那条正则**必须**带标签，
    # 它同时负责「读出哪个是专业能力、哪个是行业经验」，靠的正是那两个词。
    # 而剥的时候不需要认字段：`×0.6` 在前、`×0.4` 在后是算式自己的定义。
    # 实测（2026-08-21）导出的 `data.json` 里这种写法有 35 处原样上屏，
    # 而 AGENTS.md 的措辞表明写着算式不给用户看。等号后面那个总分也一起带走，
    # 它就在同一句话前半截（「算式应为 66」）。
    out = _BARE_FORMULA.sub(r"专业能力 \1 · 行业经验 \2", out)
    if not _FORMULA.search(out):
        return out.strip()
    out = _FORMULA.sub(r"专业能力 \1 · 行业经验 \2", out)
    out = _BONUS_ZERO.sub("", out)
    out = _BONUS.sub(r" · 另有加分 \1", out)
    out = _EQ_TOTAL.sub("", out)
    return out.strip(" ·+")


#: 不带标签的算式：`70×0.6+60×0.4=66.0`。**只用来剥，不用来读**——
#: 谁是专业能力、谁是行业经验只能靠位置推（`×0.6` 在前），而
#: `gap_split.FORMULA` 那条要认字段，所以它必须带标签，两条不能合并。
#: 后面跟着的 `=总分` 一起吃掉：那个数在同一句话的前半截已经说过一遍
#: （「算式应为 66（…=66.0）」）。
_BARE_FORMULA = re.compile(
    r"(\d+)\s*[×xX*]\s*0\.6\s*\+\s*(\d+)\s*[×xX*]\s*0\.4"
    r"(?:\s*[=＝]\s*\d+(?:\.\d+)?)?"
)

#: markdown 的强调标记。面板上这些字进的是纯文本，星号和反引号会原样上屏。
_MD_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_MD_TICK = re.compile(r"`([^`\n]+)`")
#: 中日韩字符之间的空格。替换之后才收——见 `plain()` 末尾的说明。
_CJK = r"\u4e00-\u9fff\u3400-\u4dbf\u3001-\u303f\uff01-\uff65"
_CJK_GAP = re.compile(rf"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")
#: HTML 标签。**只列认得的标签名**，不写 `</?[a-zA-Z][^>]*>` 通吃：面板上要显示的
#: 命令模板里满是 `<公司>` `<职位链接>` 这种尖括号占位符，那是用户要照敲的东西。
#: 通吃版虽然碰不到它们（里面是中文），但 JD 原文里一旦出现 `A < b > c` 这种形状
#: 就会无声吃掉用户的字。宁可列一张名单，漏了顶多标签还在屏幕上看得见。
_HTML_TAGS = re.compile(
    r"</?\s*(?:br|wbr|hr|p|div|span|a|b|i|u|s|em|strong|code|pre|tt|kbd|mark|"
    r"small|big|sub|sup|font|center|blockquote|ul|ol|li|dl|dt|dd|table|thead|"
    r"tbody|tr|td|th|h[1-6]|img)\b[^<>]*>", re.I)
#: `<br>` 在纯文本节点里不会断行，只会留下一个空洞，所以换成一个空格，
#: 交给下面 `_CJK_GAP` 在两侧都是中文时收掉。
_HTML_BR = re.compile(r"<\s*br\s*/?\s*>", re.I)
#: 打分器追加在依据末尾的那段自述：「⚠️ 某日 score.py 现算订正：
#: 薪资与职级 90→80；综合分 77 → 77，结论可以考虑 → 值得投。这三样…由工具现算，
#: 不手填。」那是写给**下一个改评估文件的人**的（`tools/score.py` 用它顶住手改），
#: 不是给他看的分析——上屏的 142 条里，它说的三件事面板本来就显示着。
#: **认「现算订正」这四个字，不认 ⚠️**：别的 ⚠️ 段是真提醒（「要留意」那一档
#: 就靠它），一个都不许跟着剥。
_SCORE_LOG = re.compile(r"[ \t]*⚠️[^\n]*现算订正[^\n]*")



# `plain()` 是导出的第二大热点：2026-08-19 profile 里 7873 次调用吃掉 0.50 秒
# （占 23%）——判词、门名、维度名这些串大量重复，纯函数配缓存正好。
# maxsize 卡住上限：正文类长串各不相同，无界缓存会把整份 data.json 复制进内存。
import functools


@functools.lru_cache(maxsize=4096)
def plain(text: str) -> str:
    """把评估正文里的内部标识换成人话。字段名和文件名不该出现在界面上。

    **子串替换要带守卫。** 有些内部词是另一个自然词的前缀：真实开场白里写过
    「智能座舱行业经验是硬门槛，还是 Agent 产品能力也在考虑范围？」——那是地道
    中文，不是框架词。裸 `replace("硬门", "硬性条件")` 会把它改成「硬性条件槛」。
    同理「信息质量差」会变成「待核实的信息差」。所以第三项写上「后面跟着这些字
    就不换」。

    算式另走 `strip_weights`：它不是「换个词」，是**把权重整段拿掉**。

    **markdown 标记先剥。** 评估正文是 markdown，而面板上这些字进的是
    `title=` 悬浮提示和纯文本节点——`**这批里最值得投的一个**` 会连着四个星号
    一起显示。实测导出的 `data.json` 里 1035 条「技能」列说明带着裸星号，
    还有 10 条带着反引号包起来的 `job-rank.md`。
    剥在**换词之前**：反引号剥掉，下面那张表才认得出 `job-rank.md` 这个文件名。

    **成对剥完还要收落单的那半个。** `_MD_BOLD` 只认 `**…**` 这样成对的；
    上游一旦在一对星号中间切了一刀，落到这里的就是一句被劈开的边界条款
    —— 后半截头上挂着一个孤零零的 `**`，成对规则认不出，于是原样上了终端（2026-09-01 实测：
    `audit_pipeline` 的「哪一条排除最贵」那句就是这么漏出去的，源头在
    `_cli.exclusion_tally` 切分规则文本时切进了加粗里）。**补在这里而不是补在
    那个调用方**：面板、终端、话术都从这一个函数出去，在调用方各补一次
    就等着它们各漏各的。
    """
    out = _MD_BOLD.sub(r"\1", text or "")
    out = out.replace("**", "")          # 上游切断加粗留下的半个标记
    out = _MD_TICK.sub(r"\1", out)
    # **HTML 标签也要剥。** 评估正文是 markdown 写的，作者偶尔直接写 `<br>` 断行；
    # 而面板上这些字进的是纯文本节点与 `title=`，浏览器不渲染标签——
    # 「两条逐条核：<br>① 英语——」就原样上屏了（2026-09-30 在渲染后的 DOM 里量到 3 处）。
    # 顺序：先 `<br>`→空格、再剥标签，最后由末尾的 `_CJK_GAP` 把中文之间的缝收掉。
    out = _HTML_BR.sub(" ", out)
    out = _HTML_TAGS.sub("", out)
    out = _SCORE_LOG.sub("", out)
    for pat, b in _TERM_PATS:            # 表在模块顶上编译好，见 `_TERM_PATS`
        out = pat.sub(b, out)
    out = strip_weights(out)
    # 换完词再收一次缝。原文里「不判 FAIL」「按 `job-rank.md` 的口径」
    # 两侧的空格是给拉丁词留的，换成中文之后就成了「不判 不满足」——
    # 正是本仓库一直在拦的那种「中文之间被塞进空格」，只是这次是替换
    # 自己造出来的。两边都是中日韩字符才收，中英之间的空格不动。
    return _CJK_GAP.sub("", out)


def gates_from_breakdown(entry: dict) -> list[dict]:
    """粗筛存下的那份门判定 → 面板形状。**没有 `evaluation.md` 时的唯一来源。**

    ## 为什么要有这条路

    `job-rank.md` Step 2 的子代理判完七道门，整块存进
    `rank_breakdown["硬性条件"]`（老写法叫 `硬门`）。而导出这边**只从
    `evaluation.md` 的门表解析** —— 那是深评才有的文件。于是粗筛的岗，
    门判定躺在盘上，一次都没上过屏。

    实测活动用户 2026-08-26：库里 125 个岗存了这份判定，面板上看得到的 **2 个**。
    余下 123 个里：42 个有 FAIL，判词写着「硬门 FAIL」，用户还看得出个大概；
    31 个全 PASS，没什么可显示；**50 个只有 FLAG —— 那是判词表达不了的**
    （FLAG 不淘汰，判词照常是「粗筛：可以考虑」），其中几个还在可投档。
    而 04 对 FLAG 的规定正是「留在排序里，但挂一个显眼的 ⚠ 让用户自己判断」。
    那个 ⚠ 对粗筛的岗从来没出现过。

    ## 状态词沿用同一份表，不在这里另立一套

    门名不在七道里的留着并标 `offSpec`（同 `parse_gates`），前端据此不把它
    算进「投前要问清楚」的计数。

    `gate_state` / `gate_why` 就是正本：`FLAG` 归 `pass` 并在依据里写
    「刚过线，留意」（04 那张表叫「满足（带提醒）」），`不适用` 归 `na`。
    这里只是换了个数据来源，判据一个字不改。

    ## 依据是空的，这是实话

    子代理回传的是 `{门名: 判定}`，没有那一句原文依据。空着比编一句强 ——
    面板本来就允许 `why` 为空（`GateStamp` 只在有话时才挂提示）。
    """
    b = entry.get("rank_breakdown") or {}
    raw = b.get("硬性条件") or b.get("硬门")
    if not isinstance(raw, dict):
        return []
    out = []
    for name, verdict in raw.items():
        if not isinstance(verdict, str):
            continue
        # 门名不在七道里的**留着、标 `offSpec`**，不丢 —— 与 `parse_gates`
        # 那一段同款。前端据此不把它算进「还没查到、投前要问」的计数里，
        # 但它仍然显示出来（自造门名多半也承载了一条真信息）。
        #
        # ⚠️ `_cli.gate_of` 认不出时返回的是**空串不是 `None`**。
        # 第一版写 `is None`，于是这一支永远不成立、`offSpec` 一次没标过 ——
        # 而测试当场逮到。
        # `gate_why` 对空依据会给「无说明」—— 那是 `evaluation.md` 那条路的
        # 兜底（那边**应该**有依据，没有就是漏写，说出来是对的）。这条路上
        # 本来就没有依据原文，把「无说明」挂到每一个 PASS 的方章上纯属噪音。
        # 只留真正有话说的那半：FLAG 的「刚过线，留意」这类。
        why = gate_why(verdict, "")
        out.append({"name": plain(name), "state": gate_state(verdict),
                    "why": "" if why == "无说明" else why,
                    **({"offSpec": True} if not _cli.gate_of(name) else {})})
    return out


def gate_why(verdict: str, reason: str) -> str:
    """判定依据里不留 PASS / FAIL / FLAG —— 状态由方章表达，不必也不该重复写。

    只有两种附加语义要保留成中文：FLAG（过线但要留意）、基于假设值（要你确认）。
    **依据里已经说过的话不再拼一遍**——实测出现过
    「…未经确认（依据是你资料里未确认的假设值）」这种同一句说两遍。

    ## markdown 标记要先剥掉

    评估表里的判定常写成 `**FLAG，非 FAIL**`（框架自己就是这么规定的）。删掉
    关键词之后剩下的是 `**，非 **`——那对星号会**原样印到屏幕上**，因为 JSX
    不渲染 markdown。

    单页版的 `format_gate_flag` 一直在剥，这边没有。两套面板并存时这类「同一条
    规则只写了一侧」反复发生，而这一条是**合并时才发现的**：单页版删掉之前，
    它的测试是这条规则在整个仓库里唯一的覆盖（`gate_why` 一条测试都没有）。
    """
    verdict = re.sub(r"[*`|]", "", verdict or "")
    reason = plain(re.sub(r"[*`]", "", reason or ""))
    extra = []
    bare = _bare(verdict)
    if "FLAG" in verdict and "过线" not in reason:
        extra.append("刚过线，留意")
    elif bare in GATE_FLAGGED and GATE_FLAGGED[bare] not in reason:
        # 「满足（带提醒）」的另外三种写法。**不认它们就等于把提醒吞掉**——
        # 状态是 pass、依据里一个字不提，用户看到的是一个干净的「满足」。
        extra.append(GATE_FLAGGED[bare])
    if "假设值" in verdict and "假设值" not in reason and "未经确认" not in reason:
        extra.append("依据是你资料里未确认的假设值")
    # 判定词以外的括注也可能有信息（例如「PASS（仅限上海）」），一并保留。
    # 但「FLAG，非 FAIL」删掉关键词后会剩一个孤零零的「非」——这类连接词残渣要丢掉，
    # 否则界面上出现「（刚过线，留意；非）」这种半句话。
    # 判定词要**连同刚翻成人话的那个**一起删掉，否则「需留意（见上）」会拼出
    # 「（刚过线，留意；需留意（见上）」—— 同一个词说两遍，还带半个括号。
    # **凡是已经翻成人话的判定词，都要连同它一起从 `rest` 里删掉** ——
    # 不只 `GATE_FLAGGED`，`GATE_EXACT` 那几个（不过 / 不过关 / …）同样。
    # 漏掉后者的实测后果：`gate_why("不过（见上）", "薪资低于底线")` 拼出
    # 「薪资低于底线（不过（见上）」—— 两个左括号一个右括号，
    # 而且把 `gate_state` 刚翻成「不满足」的原词又原样回显了一遍。
    translated = bare in GATE_FLAGGED or bare in GATE_EXACT
    drop = r"PASS|FAIL|FLAG|不适用" + (f"|{re.escape(bare)}" if translated else "")
    # **只剥成对的外层括号。** `.strip("（）…")` 两头都剥，而判定词自己带
    # 括号时它会把里层那个右括号一并带走：`要留意（减 5 分）` 被剥成
    # `要留意（减 5 分`，拼出来就是「（要留意（减 5 分）」——
    # 一个开了没关的括号，原样印在硬性条件那一行的依据里。
    #
    # ⚠️ **同一个形状上面这段注释已经记过两次**（「非」那半句、
    # `不过（见上）` 那两个左括号），两次的修法都是往 `drop` 里再加一个词 ——
    # 那只盖得住已经想到的那几个。第三次（2026-08-31 实测在导出的真实
    # 快照里逮到）改的是剥法本身：分隔符照剥，括号只剥**配得上对**的那一层。
    rest = re.sub(drop, "", verdict).strip(" ，,、；;·- ")
    while (len(rest) > 2 and rest[0] in "（(" and rest[-1] in "）)"
           and rest[1:-1].count("（") == rest[1:-1].count("）")
           and rest[1:-1].count("(") == rest[1:-1].count(")")):
        rest = rest[1:-1].strip(" ，,、；;·- ")
    if (
        len(rest) > 2
        and rest not in {"假设值", "请你确认"}
        and "假设值" not in rest
    ):
        extra.append(rest)
    tail = "（" + "；".join(extra) + "）" if extra else ""
    return (reason + tail) if reason else (tail.strip("（）") or "无说明")


def _rows_from(lines: list[str], idx: int) -> list[list[str]]:
    """从第 `idx` 行**起**（含该行）往下取第一张表的所有行，分隔行不算。

    调用方自己决定首行是不是表头：按标题定位时从标题的下一行起扫（首行即表头），
    按表头特征认表时直接从表头那行起扫。这个边界弄反过一次——兜底路径传了表头
    所在行，函数却从下一行开始，于是第一条数据被当成表头吃掉。
    """
    rows: list[list[str]] = []
    seen_table = False
    for ln in lines[idx:]:
        s = ln.strip()
        if s.startswith("##"):
            break
        if not s.startswith("|"):
            if seen_table and rows:
                break          # 表已结束
            continue
        seen_table = True
        if set(s) <= set("|-: "):
            continue           # 分隔行
        rows.append([clean(c) for c in s.strip("|").split("|")])
    return rows


def parse_table(text: str, *heading_kw: str, cols: tuple[tuple[str, ...], ...] = ()):
    """取某个 `## 标题` 之下的第一张表，返回 `(表头, 数据行)`。

    **返回表头是必须的**：AI 写的表列布局不止一种，调用方必须按表头名定位列，
    不能写死下标。实测两种四维表并存：

        | 维度 | 分数 | 说明 |          ← 3 列，分数在第 2 列
        | 维度 | 权重 | 分 | 依据 |      ← 4 列，分数在第 3 列

    早先写死 `row[2]` 是分数、且要求 `len(row) >= 4`，于是 3 列的表整张被丢掉。

    **标题也要宽进，而且这一层比列布局更要命。** 原来只按单个字面词匹配标题
    （硬门表认死「硬门」二字）。可 `apply.md` 从没规定过标题怎么写，AGENTS.md 还
    明令「硬门」是内部词、不许出现在给用户看的东西里——于是 AI 越守措辞规则，
    写出的「## 第一步：硬性门槛」越是解析不出来，整张表**静默**丢弃。后果不是
    少一块内容：硬门为空时页面会印「这些条件都核对过了，没有要问的」，把
    **没解析到**说成**全部通过**。

    所以两道：先按多个同义标题找；都没有就交给 `cols` —— 全文扫表，谁的表头同时
    含这些列名谁就是它。标题怎么写都行，只要表还是那张表。
    """
    lines = text.splitlines()
    for kw in heading_kw:
        start = next((i for i, ln in enumerate(lines)
                      if ln.startswith("##") and kw in ln), None)
        if start is not None:
            rows = _rows_from(lines, start + 1)     # 标题的下一行起，首行即表头
            if len(rows) > 1:
                return rows[0], rows[1:]
    if not cols:
        return [], []
    # 兜底：按表头特征认表，不看标题
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("|") or set(s) <= set("|-: "):
            continue
        cells = [clean(c) for c in s.strip("|").split("|")]
        # cols 的每一项是**一组同义列名**：任一命中即算该列存在，所有组都在才算这张表。
        # 用 OR 组是必须的——同一张硬门表，表头可能写「门槛」也可能写「硬门」。
        if all(any(alt in h for alt in group for h in cells) for group in cols):
            rows = _rows_from(lines, i)             # 表头那行起，首行即表头
            if len(rows) > 1:
                return rows[0], rows[1:]
    return [], []


def _col(header: list[str], *names: str, default: int = -1) -> int:
    """按表头名找列号；找不到返回 default。名字用**包含**匹配，容忍「分」/「分数」。"""
    for i, h in enumerate(header):
        for n in names:
            if n in h:
                return i
    return default


#: 评分明细那一节的历史与现行标题写法。给用户看的模板现在写「评分明细」
#: （「四维」是内部词，见 AGENTS.md 的措辞表），但库里 40 多份旧评估还写着
#: 「四维打分」——两种都要能解析。**这是唯一一份别名表**：测试也从这里取，
#: 别在别处再抄一遍字面量（抄了就会在改标题时静默失配、把用例跳过去）。
#: ⚠️ 不要再往里加「打分」这种两字别名：它会匹配到硬门评估里的
#: 「综合得分：**不**打分（硬性条件没过）」，把一份按规定就没有评分表的评估
#: 判成「有这一节」。别名要么带小节标题的完整词（「评分明细」），
#: 要么带足够上下文（「维打分」）。
DIM_SECTION_ALIASES = ("维打分", "四维", "评分明细")


def parse_dimensions(text: str) -> list[dict]:
    """评分明细表 → [{name, score, weight, note}]，按表头名定位列。

    通勤那一行是 Pass/Fail 的门，不计权重也没有分数 → score 为 None。
    """
    header, rows = parse_table(text, *DIM_SECTION_ALIASES,
                               cols=(("维度",), ("分", "得分")))
    if not rows:
        return []
    i_name = _col(header, "维度", "项", default=0)
    i_score = _col(header, "分数", "分", "得分")
    i_weight = _col(header, "权重", "占比")
    i_note = _col(header, "依据", "说明", "备注")
    # 「分」也会匹配到「分数」：`| 维度 | 权重分 | 依据 |` 这种表头两个 `_col`
    # 会落到同一列。撞车时**丢权重、留分数**——分数是面板要显示的东西，权重按
    # 设计根本不上屏（「占 30%」是打分器的内部参数）。这里原来反过来置 i_score=-1，
    # 于是整张表的分数全成 None：四个维度一律掉进「要掂量的地方」，技能列显示「—」。
    # 而注释写的是「取靠后的那个当分数」，跟代码说的正相反。
    if i_score == i_weight and i_weight >= 0:
        i_weight = -1
    out = []
    for r in rows:
        if not r or i_name >= len(r):
            continue
        name = r[i_name].strip()
        if not name:
            continue
        raw = r[i_score] if 0 <= i_score < len(r) else ""
        # **只认斜杠左边那个数，不许退而取分母。** 这一列的写法实测只有 9 种
        # （2026-08-23，1062 行）：`88`（520）、`88/100`（424）、
        # `PASS（不计权重）`（106）、`—`、`PASS`、`88 ⚠`、`信息缺失`、`提示`。
        # **没有一种是「数字不在开头」**，所以按开头取是安全的。
        #
        # 换掉 `re.search` 的理由是那份产出模板自己：它写的是 `XX/100`。
        # 从任意位置捞第一个数，`XX/100` 会读成 **100** —— 一份跑断、
        # 占位符没被替掉的评估，会把那一维导出成**满分**，把这个岗顶到最前。
        # 错在最坏的方向上，而且没有任何地方会报错。真实语料里今天是 0 例
        # （`tests/test_an_unfilled_cell_is_not_a_perfect_score.py` 盯着），
        # 但 268 份评估全是大模型现写的，跑断不是假设。
        m = re.match(r"\s*(\d+)", raw)
        w = re.search(r"\d+", r[i_weight]) if 0 <= i_weight < len(r) else None
        note = r[i_note].strip() if 0 <= i_note < len(r) else ""
        out.append({
            "name": name,
            # **这一行算不算计权的四维。** 判据在 `_cli.is_weighted_dim`——
            # 不在四维里的（眼下只有「地点」）是被写进这张表的 Pass/Fail 门，
            # 不该进面板「对口 / 要掂量」那两栏。见那份常量的注释。
            "weighted": _cli.is_weighted_dim(name),
            "score": int(m.group()) if m else None,
            "weight": int(w.group()) if w else 0,
            "note": plain(dimension_note(text, name, note)),
        })
    return out


def dimension_note(text: str, name: str, fallback: str) -> str:
    """四维表里写「见下」时，去 `### <维度>` 小节取第一句正文当依据。

    表格里的「见下」对用户毫无意义——「为什么是这个分」正是他要看的那一列，
    所以必须把它补上，而不是原样显示。
    """
    if fallback and fallback not in {"见下", "见上", "同上", "-", "—"}:
        return fallback
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("###") and name in ln), None)
    if start is None:
        return fallback
    for ln in lines[start + 1:]:
        s = clean(ln)
        if not s or s.startswith("|") or set(s) <= set("-—"):
            continue
        if s.startswith("#"):
            break
        s = re.sub(r"^[-*]\s*", "", s)
        return s[:120]
    return fallback


def parse_gates(text: str) -> list[dict]:
    """evaluation.md 的硬性条件表 → `[{name, state, why, assumed?}]`。

    **这是唯一的入口，测试也走它。** 原来这段逻辑内联在导出主流程里，于是控制测试
    只能自己再调一遍 `parse_table` ——参数由测试自己写，改坏导出器那边的调用它照样
    绿。实测就这么漏过：把标题匹配退回只认字面词「硬门」，测试全绿。

    标题写法不设限：「硬门检查」「第一步：硬性门槛」「硬性条件」都认；都对不上就按
    表头特征认表（有「判定/结果/结论」列的那张）。为什么要这么宽，见 `parse_table`。
    """
    header, rows = parse_table(
        text, "硬门", "硬性门槛", "硬性条件", "门槛", "准入",
        cols=(("门槛", "硬门", "条件"), ("判定", "结果", "结论")))
    i_gate = _col(header, "硬门", "门槛", "条件", default=0)
    i_verdict = _col(header, "判定", "结果", "结论", default=1)
    i_basis = _col(header, "依据", "说明", "原文", default=2)
    out: list[dict] = []
    for row in rows:
        if len(row) <= max(i_gate, i_verdict, i_basis):
            continue
        row = [row[i_gate], row[i_verdict], row[i_basis]]
        # 竞业限制**不是硬门**（见 04-job-evaluation.md）。历史评估里它还在表内，
        # 且多半判的是资料里的假设值「无」——于是每个岗都挂一条「投前请自己确认」，
        # 对 99% 的岗没有判别力。只有用户真写了限制范围才留。
        # **薪资不是硬门**，同「竞业限制」那条 —— `04-job-evaluation.md`
        # 的七道门里没有它；薪资是第二步的**打分维度**（「薪资与职级 0-100」），
        # 低于底线给低分，不一票否决。
        #
        # 历史评估把「薪资底线」写进了这张表，判定格写「不过」。2026-08-21
        # 把「不过」接上显示层之后，流水线审计当场报出一条自相矛盾：
        # 「判词『值得投』却有硬门不满足」。**而评估本身没错** ——
        # 按框架自己的算式 73×0.3+25×0.25+85×0.2+75×0.25=63.9，
        # 确实落在「值得投」档。矛盾只来自那一行被放错了表。
        #
        # 不丢信息：这条警告在评估正文里有自己的 ⚠️ 段落，
        # 打分明细里也有「薪资与职级 25」。这里只是不让它读成一票否决。
        # **例外：候选人自己声明的排除是正规硬门，不能跟着一起丢。**
        # `04-job-evaluation.md` 的七道门里第七道就是「候选人明确排除」，
        # 而薪资底线正是它最典型的写法（「低于 <他自己填的那个数> 我不去」）。
        # 上面那段讲的是**历史评估把打分维度错放进这张表**，不是「凡带薪资二字
        # 的行都不算门」——按子串一刀切会把用户自己划的红线整行删掉，
        # 面板上再也看不到它，比原来显示成「结论不明」更糟。
        # 判据交给 `_cli.gate_of()`（认「排除」二字），它就是归门那一份正本。
        #
        # **能被救回来的是「名字里点了「排除」的那种」**，实测：
        #   候选人明确排除（薪资低于底线）  → 留
        #   薪资（候选人明确排除）          → 留
        #   薪资底线 / 薪资与职级           → 丢
        # 后两个正是**错放进这张表的打分维度**（框架的七道门里没有「薪资底线」），
        # 丢掉是对的：留着就会出现「判词『值得投』却有硬门不满足」那种自相矛盾。
        # 它们不是没了 —— 评估正文里有自己的 ⚠️ 段落，打分明细里有「薪资与职级 N」。
        if (("薪资" in row[0] or "薪水" in row[0] or "年包" in row[0])
                and _cli.gate_of(row[0]) != "候选人明确排除"):
            continue
        if "竞业" in row[0]:
            basis = row[2]
            # 「无」要**整格精确比**，不能用子串。一条真实的依据只要写成
            # 「限制同业，目标公司是否在内**无**法确认」就会被这个子串判断静默丢掉
            # ——而那正是最该显示给用户看的一条。
            stripped = basis.strip().strip("。.")
            if ("假设值" in row[1] or "假设值" in basis
                    or stripped in ("无", "未涉及", "无。", "不适用")):
                continue
        out.append({
            # 条件名要过 plain()：AI 写评估时会照框架措辞写出
            # 「英语（你的自带硬门）」这种名字，解析成功后就直接上屏。
            # **同一道门只用一个名字。** 这一格来自评估表的第一列，是自由文本，
            # 于是同一道门在屏幕上有好几种写法 —— 实测 2026-08-29：
            # 「执业资格/证照/职称」282 个 vs「执业资格·证照·职称」180 个、
            # 「外包/驻场/派遣」289 vs「外包/驻场」154 vs「外包·驻场·派遣」57、
            # 「候选人明确排除」440 vs「你自己划的排除项」59。
            # 用户挨个岗看下来，同一道门三种叫法。`_cli.gate_of` 本来就认得别名。
            # **认不出来的原样留着** —— 那批（地点、语言、行业背景…）正是
            # `check_gate_is_one_of_the_seven` 要报的，归一化会把它藏起来。
            "name": _cli.gate_of(plain(row[0])) or plain(row[0]),
            "state": gate_state(row[1]),
            # 依据里**不带**判定词：PASS / FAIL / FLAG 是框架内部词，而且状态已经由
            # 方章的形制表达了，再写一遍既是重复也是把英文码泄漏到界面上。只有
            # 「非 FAIL」这种附加语义（过线但要留意）值得留一句中文说明。
            "why": gate_why(row[1], row[2]),
            **({"assumed": True} if "假设值" in row[1] else {}),
            # **门名不在七道里的，不是一道硬性条件。**
            #
            # `04-job-evaluation.md` 第一步写着：「门名也只许用下表这七个 ——
            # 自造的门名和没判一样，查不出来」，并给了归位规则（地点、英语、
            # 年龄这类归「候选人明确排除」；技术栈、专业、行业经验本来就是
            # 要打分的维度，不该当门用）。
            #
            # 规则一直在，**面板却把这几行当成没查的硬性条件在催用户去问**。
            # 实测活动用户 2026-08-25：1699 行里 122 行门名不在七道里
            # （`地点` 47、`专业` 46、`专业相符` 8、`英语` 7、`对外持股` 3、
            # `工作地点` 3、`编码能力` 2、`年龄` 2，其余各 1），其中 6 行
            # 判定是 `unknown` —— 于是 6 个岗印着「投之前先问清 1 条」，
            # 而那 1 条**根本不是硬性条件**：数从 1 变 0，整句话都不该出现。
            # 其中两个是他分数最高的岗（77 分强匹配、71 分值得投），
            # 而那一行的依据里评估早就写了结论。
            #
            # **只打标，不删行**：那一行是审计要人去改的证据
            # （「硬门：门名没按七道正规名写」），删掉等于把问题藏起来。
            # 判据留在 Python 这一份（`_cli.gate_of`），TS 那边只读这个标志 ——
            # 同 `Dimension.weighted` 的做法，两处各写一份词表迟早分叉。
            **({"offSpec": True} if not _cli.gate_of(row[0]) else {}),
        })
    return out


def parse_quality(text: str) -> list[dict]:
    """信息质量提示：这一节里的项目符号，**带不带粗体标题都算一条**。

    标题同样宽进。「信息质量」和「硬门」一样是 AGENTS.md 禁止上屏的内部词——
    AI 守规则写成「待核实的信息」，只认字面词的解析器就一条都读不到。

    ## 为什么不能只认 `- **标题**：正文`

    那是**规格里不存在的形状**。`04-job-evaluation.md` 对这一节给的模板就一行：

        - ...（这个岗是真是假，你看出了什么；正面信号也写；没有就写「无」）

    ——一个纯文本项目符号，没有粗体标题。而旧解析器要求粗体加全角冒号，
    于是照规格写的那些一条都读不到。

    实测活动用户 2026-08-23，223 份带这一节的深评：

        写了「无」            27   ← 本来就没内容，不该出现在面板上
        解析得到              42
        **有内容却读不到     151**  ← 其中 138 份就是「没有粗体标题的纯文本」
        整节空                 3

    **68% 的内容卡在解析这一层。** 而这一节正是「这个岗是真是假」的落点——
    蓄水池、匿名雇主、字段自相矛盾都写在这里，用户在面板上一条都看不见。

    现在两种都收：有 `**标题**：` 的照旧拆成标题+正文；没有的整行当正文、
    标题留空（显示层不渲染那个冒号）。「无」「—」这类空占位跳过。
    """
    lines = text.splitlines()
    #: 这一节的标题写法。**「没核实」是 2026-09-02 补的第六个**：
    #: 04 的输出格式里有一节叫「有哪些信息没核实上（不计分）」，而上面五个词
    #: 一个都不含它（「没核实」不是「待核实」）。实测活动用户 2026-09-02：
    #: **195 份深评有这一节、195 份都写了真内容**，而这里一条都取不到 ——
    #: 「页面已下线，无法核实」「实名雇主，但本次未做公司调研，所在部门、
    #: 团队规模、业务阶段未核实」这类话，用户在面板上一个字看不见。
    #: 这正是本函数 docstring 记的那一课（「AI 守规则写成『待核实的信息』，
    #: 只认字面词的解析器就一条都读不到」）少收的第六个变体。
    #:
    #: ⚠️ **只救得了其中 39 份**：下面那个 `next(...)` 只取**第一个**匹配的小节，
    #: 而 156 份同时还有「职位真伪信号」，它排在前面、挡着。要救那 156 份得让
    #: 这里收齐所有匹配小节 —— 那是另一件事（两节语义不同，合并要先想清会不会
    #: 重复报），没在这一次做。
    KW = ("信息质量", "待核实", "真伪信号", "存疑", "要核实", "没核实")
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("##") and any(k in ln for k in KW)), None)
    if start is None:
        return []
    out, cur = [], None
    for ln in lines[start + 1:]:
        if ln.startswith("##"):
            break
        m = re.match(r"\s*-\s+\*\*(.+?)\*\*[：:]\s*(.*)", ln)
        if m:
            cur = {"title": plain(m.group(1).strip()), "detail": plain(clean(m.group(2)))}
            out.append(cur)
            continue
        b = re.match(r"\s*-\s+(.*)", ln)
        if b:
            # **没有粗体标题的项目符号也是一条。** 规格给的模板就是这个形状。
            # 注意 `- **加粗**，逗号接下去` 也走这一支：那里的粗体是句中强调，
            # 不是标题，硬拆成 `标题：正文` 会把一句话腰斩。
            body = b.group(1).strip()
            if not body or re.fullmatch(r"(无|无。|—|-|不适用|不适用。)", body):
                cur = None            # 空占位不进面板
                continue
            cur = {"title": "", "detail": plain(clean(body))}
            out.append(cur)
        elif cur is not None and ln.strip() and not ln.startswith("-"):
            # 折行接回去时**再过一次 `plain()`**：这里用一个空格拼接（英文折行
            # 需要它），而中文折行不需要——拼完屏幕上就是「没有公司名， 本轮无法
            # 独立核实」，标点后凭空多一个空格。实测 21 条这样的。
            # `plain()` 末尾那道「中日韩之间的空格收掉」正好治它，中英之间的
            # 空格照留，所以拼完再过一次，而不是在拼之前对每一段各过一次。
            cur["detail"] = plain((cur["detail"] + " " + clean(ln)).strip())
        elif not ln.strip():
            cur = None
    return out


def is_rule_skipped(entry: dict) -> bool:
    """这个岗是被**规则**淘汰的（预筛/粗筛判「跳过」），不是用户手点的不投。

    **唯一的一份判据。** 导出侧用它决定页面显不显示「放回可以投」按钮，
    `serve.py` 用它决定「放回」时撤不撤判词——两边语义必须一致，原来是
    两份字面副本，改一边另一边就出现「按钮显示了、放回却按手点处理」。
    """
    return ("跳过" in (entry.get("rank_verdict") or "")
            or "预筛" in ((entry.get("rank_breakdown") or {}).get("来源") or ""))


#: 「这一节没什么要问的」写成一条目时的样子。**它不是内容，是占位。**
#:
#: 实测活动用户 2026-08-24：363 条「投前必问」里 **74 条是字面的「无」**，
#: 而且这 74 条**各自占满了它所在岗位的整节** —— 也就是 176 个带这一节的岗里，
#: 有 74 个（42%）展开后看到的是一条写着「无」的待问事项。
#: 其中 **39 个判词是「可以考虑」**，而 `04` 给那一档的定义就是
#: 「先问清楚关键信息再决定投不投」，还明写「写不出三条就说明它不属于这一档」。
#:
#: **写「无」比空着更糟**：空着这一节整个不渲染，用户知道没有；
#: 写「无」在界面上长得和一条真问题一模一样，他得读完才发现什么也没说。
_ASK_EMPTY = re.compile(r"^(无|没有|暂无|不适用|待定|N/?A|[—\-])[。．.]?$", re.I)


#: markdown 列表项的折行接回去用。
#:
#: **这是一个真 bug，不是洁癖。** 写手把一条写长了就会换行：
#:
#:     1. **专业这条卡得严吗？**（JD 写「计算机科学、人工智能…等相关专业背景」，
#:        而你是历史学本科——这是本岗唯一的真门槛风险）
#:
#: 逐行匹配 `- ` / `1. ` 的解析器只拿得到第一行，第二行既不是新项也不是标题，
#: 被 `continue` 丢掉。面板上于是出现**断在逗号上、引号配不上对**的句子 ——
#: 自检「面板上有句子断在半截」报的 21 处里，`askBefore` 11 处、`gaps` 9 处
#: 全是这么来的（实测 2026-08-30）。
#:
#: 判据：**缩进的、不是新项、不是标题、不是表格行、不是空行** —— 那就是上一条的续行。
#: 中文列表常写成 `1、甲`，**分隔符后面没有空格** —— 要求空格的话这一族全漏。
#: 但也不能全放开：`1.5-2万` 顶格出现时会被当成列表项，所以数字那一支要求
#: 其后不是数字（`(?=\D)`）。`-` / `*` 那一支仍然要求空格，
#: 否则 `---` 分隔线和 `-30%` 这种也会被当成列表项。
_BULLET = re.compile(r"^\s*(?:[-*]\s+|\d+[.、)]\s*(?=\D))")


def _list_items(lines):
    """逐条产出列表项的**完整**文本（折行已接回）。非列表行不产出。"""
    cur = []
    for ln in lines:
        if not ln.strip():
            # 空行断开一条 —— markdown 里空行之后就是新段落了
            if cur:
                yield " ".join(cur)
                cur = []
            continue
        if ln.lstrip().startswith("#") or ln.lstrip().startswith("|"):
            if cur:
                yield " ".join(cur)
                cur = []
            continue
        if _BULLET.match(ln):
            if cur:
                yield " ".join(cur)
            cur = [_BULLET.sub("", ln, count=1).strip()]
        elif cur and ln.startswith((" ", "\t")):
            cur.append(ln.strip())
        else:
            if cur:
                yield " ".join(cur)
                cur = []
    if cur:
        yield " ".join(cur)


def parse_ask_before(text: str) -> list[str]:
    """深评里的「投前必问」——**这个岗还没弄明白、投之前要问清的那几条**。

    ## 为什么单独抽它

    「可以考虑」那一档的定义就是「先问清楚关键信息再决定投不投」
    （`04-job-evaluation.md`）。面板上那枚章现在写着「话术备好 · 先问清」——
    可它**没说要问什么**，用户还得自己打开评估文件翻。

    ## 这一节此前没人定义过

    两处消费方都让执行者「记进 `evaluation.md` 的「投前必问」」
    （`job-apply.md`、`06-outreach-templates.md`），而 04 的输出格式里
    **从来没有这一节**。后果是实测出来的（268 份深评）：

        有「投前必问」小节的            40 份
        判词含「可以考虑」的            144 份
        └ 其中有那一节的                 7 份   ← 该有的那一档，反而几乎都没有

    而那些「要问什么」的内容并没有消失，只是散在五个不同标题下
    （建议 27、投前必问 25、投前必问（…沟通…）25、职位真伪信号 8、缺口 2）。
    **标题没定义，写的人各起各的名，读的人一个都取不到。**

    所以这里**宽进**：认「投前必问」，也认「必问」「要问清」这些变体；
    04 那边同时把这一节写进输出格式并规定「可以考虑」必写。
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("#") and re.search(r"投前必问|必问|要问清", ln)), None)
    if start is None:
        return []
    out = []
    body = []
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        body.append(ln)
    for item in _list_items(body):
        q = plain(clean(item)).strip()
        # 占位不算一条 —— 判据与理由见 `_ASK_EMPTY`。
        if q and not _ASK_EMPTY.match(q):
            out.append(q)
    return out[:6]


#: 缺口那一行尾巴上的「（别写成：「xxx」）」。
#:
#: 收几种写法：`别写成` / `不能写成` / `不要写成`，中文括号或英文括号，
#: 引号可有可无。**写手的手会抖，判据不该跟着抖** —— 这一段是给人写的散文，
#: 不是机器填的表单（同 `parse_gaps` 那句「跑偏的是写手，不是解析器」）。
_OVERCLAIM = re.compile(
    r"[（(]\s*(?:别|不能|不要)写成\s*[：:]?\s*[「\"']?(.+?)[」\"']?\s*[)）]\s*$")


def _overclaim_of(detail: str):
    """`detail` → (剥掉尾巴的 detail, 不能写成的那句)；没有尾巴返回 None。

    ## 为什么要剥

    不剥的话那句话会连着括号一起进 `detail`，面板上就成了
    「……（别写成：「熟练 Python」）」—— 一句**说明**，混在他正要往材料里
    抄的那段实情后面。剥出来交给 `overclaim`，面板把它划红单独排
    （`JobReadout.tsx` 那个 `<s>` 分支），他一眼看得出哪句是能写的、
    哪句是不能写的。

    ## 这个字段等了很久

    `types.ts` 的 `overclaim`、面板的划红分支、示例数据里的两条，
    2026-08-25 之前全都在，**而真实数据里一条都没有** —— 因为
    `04-job-evaluation.md` 的缺口那一节从没要过它（同一天补上了）。
    整条链路只在示例数据里活着。
    """
    m = _OVERCLAIM.search(detail or "")
    if not m:
        return None
    # 冒号可有可无，于是 `（别写成：）` 会把冒号本身当成内容捞出来。
    # 剥干净再判空 —— 一个只剩标点的「不能写成」印到屏幕上比不印更糟。
    over = m.group(1).strip().strip("：:「」\"' ")
    if not over:
        return None
    head = detail[:m.start()].strip().rstrip("，,、")
    # **引号里那句才是「不能写成」的原话。**
    #
    # 捕获是懒惰的，可收尾要求一个右括号 —— 于是引号后面还跟着解释时
    # （`（别写成：「有合规相关项目经验」；你做过的是产品与交付…）`），
    # 那个 `」` 连同整段解释一起被卷进来。屏幕上就出现一句
    # `有合规相关项目经验」；你做过的是…` —— 一个开不了口的引号，
    # 而且把解释划红成了「不能写成」的一部分（它其实是**能**写的实情）。
    #
    # 两样都不丢：引号里的归 `overclaim`，引号后的解释还给 `detail`。
    i = over.find("」")
    if i >= 0:
        tail = over[i + 1:].strip().lstrip("；;，,、 ")
        over = over[:i].strip()
        if not over:
            return None
        if tail:
            head = (head + " —— " + tail) if head else tail
    return (head, over)


def parse_gaps(text: str) -> list[dict]:
    """「缺口」小节 → [{kind, claim, detail}]，给面板的「经历对不上的地方」。

    这个字段原来**根本没有解析器**：job 初始化成 `"gaps": []` 之后全文件再无
    第二处写入，于是深评明明写了缺口和不能吹的说法，页面却对每个岗都渲染
    「这个岗没有（对不上的地方）」——把「上游丢了数据」说成「核对过没问题」，
    正是 GateStamp 注释里点名的最危险错误类。

    真实数据里有**两种**形状，都要收：

    1. 平铺 bullet：`- 「要求原文」——你的实情`（规格给的就是这个，
       `04-job-evaluation.md`：`- ...（如实写，不美化）`）。
    2. **三列表格**：`| 缺口 | 严重程度 | 怎么讲 |`。这个形状规格里没有，
       是某几批跑法自己长出来的。

    ⚠️ **这次跑偏的是写手，不是解析器** —— 和 `parse_quality` 那次方向相反
    （那次规格给的是纯文本项目符号、而解析器要粗体标题）。照样收下，两条理由：
    那 137 条**已经写在盘上了**，拒收只是继续丢；而且表格
    **比 bullet 多一列信息**（严重程度），扔掉不划算。

    ## 只认第一种的代价

    实测活动用户 2026-08-23：264 份有缺口内容的深评里，**52 份写成了表格**，
    共 **137 条缺口**一条都没进面板。而这一节为空时面板渲染的是
    「这个岗没有对不上的地方」——**把「上游丢了数据」说成「核对过没问题」**，
    正是本函数上面那段注释点名的最危险错误类。它就在这个函数自己身上发生了。

    ## `kind` 那一格放什么

    bullet 那一支它填的是写手自带的前缀（`核心职责：` 这类）；表格那一支填的是
    「严重程度」列。**实测面板上 719 条缺口的 `kind` 全是空的** —— 那个 chip
    一次都没渲染过，位置是空的。所以两种来源共用它不会撞车。
    判据统一成：**写手在那个位置放的短标签，原样显示，不编造分类。**
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("##") and ("缺口" in ln or "对不上" in ln)), None)
    if start is None:
        return []
    out = []
    # **先试表格那一支。** 三列 `| 缺口 | 严重程度 | 怎么讲 |`，
    # 表头认法与 `parse_gates` 共用 `parse_table`，不另写一套匹配。
    header, rows = parse_table(
        text, "缺口", "对不上",
        cols=(("缺口", "差距", "对不上"), ("严重程度", "程度", "怎么讲", "说明")))
    if rows:
        i_claim = _col(header, "缺口", "差距", "对不上", default=0)
        i_sev = _col(header, "严重程度", "程度", default=1)
        i_how = _col(header, "怎么讲", "说明", "how", default=2)
        for row in rows:
            if len(row) <= max(i_claim, i_sev, i_how):
                continue
            claim = plain(clean(row[i_claim])).strip()
            if not claim:
                continue
            sev = plain(clean(row[i_sev])).strip()
            _row = {"kind": "" if sev in ("——", "—", "-") else sev,
                    "claim": claim,
                    "detail": plain(clean(row[i_how])).strip()}
            # **表格那一支也要剥。** 两种形状同一个判据 —— 只给 bullet 剥的话，
            # 52 份写成表格的深评（实测 2026-08-23）就永远拿不到这一格。
            _over = _overclaim_of(_row["detail"])
            if _over:
                _row["detail"], _row["overclaim"] = _over
            out.append(_row)
        # **不提前返回。** 表格和项目符号在同一节里共存时（实测活动用户
        # 2026-08-23 是 0 份，但没理由拒绝），两种都是缺口内容，两种都收；
        # 一个 `|` 行不可能同时被下面那个 `- ` 正则认走，不会重复计数。
    body = []
    for ln in lines[start + 1:]:
        if ln.startswith("##"):
            break
        body.append(ln)
    for item in _list_items(body):
        s = plain(clean(item)).strip()
        if not s:
            continue
        kind = ""
        km = re.match(r"(核心职责|任职要求|领域空白|加分项)\s*[：:]\s*(.+)", s)
        if km:
            kind, s = km.group(1), km.group(2)
        claim, _, detail = s.partition("——")
        row = {"kind": kind, "claim": claim.strip(), "detail": detail.strip()}
        over = _overclaim_of(row["detail"])
        if over:
            row["detail"], row["overclaim"] = over
        out.append(row)
    return out


def main(argv=None, *, show_next_step=True) -> int:
    """`argv` 必须能显式传入：`serve.py` 是**在自己的进程里**直接调这个函数的
    （见 `serve._export_now`）。默认去读 `sys.argv` 的话，服务器自己的
    `--port 29030` 会被导出器当成自己的参数，当场 `SystemExit(2)`——
    症状是面板打不开而且报的是一个跟端口毫无关系的错。"""
    # `--user` 必须真的管用：仓库里六个工具都认它，肌肉记忆是现成的。
    # 从前这里根本不解析参数——`--user bob` 会被吞掉、导出活动用户的数据、
    # 然后报成功。多人共用一份 clone 时那是把别人的资料摆到你面板上。
    user, _ = _cli.resolve_user(
        argv, root=ROOT, description="把这个用户的求职数据导成面板要读的 data.json")
    ud = ROOT / "users" / user

    sj_file = ud / "job_scraper" / "seen_jobs.json"
    if not sj_file.is_file():
        print(_cli.no_store(sj_file), file=sys.stderr)
        return 1
    raw = _cli.read_json(sj_file)
    # 真实结构是 {"seen": {url: {...}}}；容忍直接是 {url: {...}} 的老格式。
    # **正本是 `_cli.seen_of`**（2026-08-21 把 doctor / build_dashboard /
    # gap_split 三处手写的都收到了它上面）。这里当时漏了——而这是全仓
    # 影响面最大的一处：它写的是面板读的那份 `data.json`。留着抄件的下场是
    # 下次改宽容度时三个工具跟上、导出器不跟，面板又和自检各说一个数。
    seen = _cli.seen_of(raw)
    _cli.stop_on_unreadable_rows(seen, sj_file)
    # 用户自己下的决定（不投 / 已下线）在**另一个文件**里，见 `_cli.set_user_decision`。
    # 它是叠加层：有决定的以它为准，没有的看职位库自己的 status。
    ustate = _cli.load_user_state(sj_file)

    # 投递目录：用面板那套 find_applications 扫，url 与话术的解析规则完全一致。
    # 同一 URL 对应多个目录时**保留信息更全的**（有话术 > 有简历 > 面试准备多），
    # 不是「后者胜出」——直接字典推导会把前一个目录里已生成的 resume.pdf 与
    # 面试准备静默藏掉。这段逻辑 build_dashboard.build_model 早就写对了，
    # 但那个函数只有测试在调；真正生成 data.json 的是这里，此前跑的正是
    # 它注释里点名的坏写法。只扫一遍：原来 find_applications 被调了两次，
    # 目录解码失败的警告也会打两遍。
    app_root = ud / "documents" / "applications"
    all_apps = find_applications(app_root)
    apps = dedup_apps_by_url(all_apps)
    orphans = [a["dir"] for a in all_apps if not a["url"]]

    # 材料里常记不带 `#岗名` 后缀的干净链接，而库 key 可能带 fragment（51job 公司页
    # 甚至靠 fragment 区分同页多岗）。精确匹配不上时按基础 URL 兜底，但**两边都唯一
    # 才对上**：材料侧该基础 URL 只有一个目录、库侧也只有一个岗——任一不唯一都不猜，
    # 宁可显示「没材料」也不把别岗的话术端错人。实测 2026-08-12：63 个目录因此接不上。
    def _base(u: str) -> str:
        return (u or "").split("#", 1)[0]

    _app_base_ct = collections.Counter(_base(u) for u in apps)
    # 驻场标记要读 JD 正文（见 `_onsite_ids`）。**在这里算一次**，
    # 逐岗的 `prefTags` 与 `pref_rows` 的计数共用它 —— 两处各算一遍，
    # 计数和实际滤掉的数就会对不上。
    _onsite = _onsite_ids(user)
    apps_base = {_base(u): a for u, a in apps.items() if _app_base_ct[_base(u)] == 1}
    _seen_base_ct = collections.Counter(_base(k) for k in seen)

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for old in PDF_DIR.glob("*.pdf"):
        old.unlink()

    jobs, n_pdf, n_drift = [], 0, 0
    # **这里绑的是 `seen` 的键，不是链接。** 键的形态是 `<url>#<职位名>`
    #（51job 实测同一 URL 下挂着两个不同职位，只用 URL 会静默吃掉一条，
    # 见 `workflows/reference/cdp-portals.md`）。这一行原来把它命名为 `url` ——
    # 全仓十来处同样的循环都叫 `k`，只有这一处不是，而它恰好在产出面板那份
    # `data.json` 的文件里。名字骗人的代价是现成的：同一个作用域里还有
    # `e["url"]`（真链接），`ustate.get(...)` 要的却是键 ——两者今天恰好都对，
    # 是因为 1839 条**每一条都有** `url` 字段，那个 `or` 兜底从没触发过。
    for k, e in seen.items():
        # 分数与判词走面板同一个 resolve_score：**有 evaluation.md 就以深评为准**。
        # 两处各写一套必然飘，而这正是「面板 76、深评 62」那个 bug 的形状。
        app = apps.get(e.get("url") or k)
        if app is None and _seen_base_ct[_base(e.get("url") or k)] == 1:
            app = apps_base.get(_base(e.get("url") or k))
        score, verdict, evaluated = resolve_score(e, app)
        verdict = str(verdict or "")
        # **兜底要自嚷，不许静默圆场。** resolve_score 以 evaluation.md 为准，
        # 于是深评没写回库时面板照样显示对的——分叉被藏住了。实测 4 个目录
        # 分叉了四个月（库里 76/强匹配 vs 深评 62），期间 /job-rank 选岗、预筛、
        # /job-upskill 读的全是库里的旧值。这里逐岗比对，末尾一次性提醒补账命令。
        # 已下线的岗不计分叉：它不上面板，催着补一笔谁也看不见的账是纯噪音
        # （原来这行在 expired 的 continue 之前，旧账也被算进催办数）。
        if e.get("status") != "expired" and ((app or {}).get("evaluation") or {}) and (
                e.get("rank_score") != score
                or _cli.strip_triage(e.get("rank_verdict")) != verdict
                or not e.get("evaluated")):
            n_drift += 1
        gate_fail = verdict.startswith("硬门 FAIL")
        # 不满足硬性条件的岗**没有分数，但必须导出**——它们进「不建议投的岗位」，
        # 用户最需要看的就是「为什么不投」。第一版这里一律 `score is None → continue`，
        # 于是那一区永远是空的，19 vs 23 的差额也正是这批。
        # 真正该跳过的只有「还没评分」的：没分、也没有判词。
        #
        # 上一版把这句意图写在注释里，条件却只豁免了 `gate_fail`。当时看不出差别，
        # 因为预筛结案会编一个分数（20/25）出来，`score is None` 根本轮不到它。
        # 等到预筛改成诚实地不给分，37 个「跳过」的岗当场从面板上消失——
        # **注释描述的是意图，代码执行的是另一件事**，中间靠一个恰好掩盖它的
        # 副作用连着。所以这里按注释原本说的写：有判词就是已结案，必须导出。
        # 已下线的一律导出，**哪怕它从没评过分**：导出的目的是让它能在搁置区
        # 被放回来，而「没分」不代表「不需要回头路」——抓到之后还没评就先下线的
        # 岗同样可能是误判（点开恰好是聚合页）。少这一条，那类岗依旧人间蒸发。
        _st = _cli.decided_status(e, ustate.get(k))
        expired = _st == "expired"
        # 算一次就够：下面那个条件展开原来把同一串参数算了两遍。
        annual = annual_package(e.get("salary") or "", e.get("salaryMonths"))
        if score is None and not verdict.strip() and not expired:
            continue
        # **已经没人了的岗不进面板。** `expired` 是「职位下线/报名截止」，不是
        # 「不合适」——它不该出现在任何一栏里让人再看一遍，更不该被算进「打过分」
        # 那格的计数。
        #
        # 这条原来漏了：过滤只看「有没有分或判词」，而一个岗从 `ranked` 变成
        # `expired` 时分数照旧留着（那是评估结果，不因下线而失效），于是它继续
        # 被导出。实测把 BOSS 上一个已关闭的岗标掉之后，流水线「打过分」比
        # `seen_jobs.json` 里真正在场的多一个，`test_pipeline_counts` 当场红。
        # 已下线的岗**导出、但只进搁置区**（`expired` 标记，`funnels_of` 返回空、
        # 不进任何计数、不进可投名单；判定在上面）。
        #
        # 原来这里是 `continue`：整条不导出。那时它只由 `/job-apply` 批量写入，
        # 不导出等于「AI 判过就没了」。现在页面上也有「职位已下线」按钮，
        # 不导出就意味着**用户点完这个岗当场蒸发、没有任何回头路**——而
        # 「点开是聚合页」这种判断完全可能错。这正是本仓库删掉单文件面板时
        # 记下的那条教训的反面：一个只能记坏消息、还撤不回来的按钮比没有更坏。
        job = {
            "id": stable_id(e.get("url") or k, e.get("title") or ""),
            "url": e.get("url") or k,
            "title": e.get("title") or "",
            "company": e.get("company") or "",
            # 脱敏雇主要标出来。这个字段类型里声明了、界面上也用着
            # （Shortlist 会渲染「（公司未公开）」），但**导出器从没设过它**——
            # 只有虚构演示数据 `sample.ts` 里是 true。于是这个功能在 demo 上看着
            # 能用，真实数据里永远不亮。正是本文件开头警告过的那种坑：
            # 「虚构数据的问题不是不够真，而是它长得像真的」。
            #
            "anonymousEmployer": is_anonymous_employer(e.get("company") or ""),
            # 职位已下线（关了 / 报名截止 / 点开是聚合页）。只进搁置区，
            # 不进任何名单与计数；页面上给「放回可以投」。
            "expired": expired,
            **({"expiredDate": _decision_date(ustate.get(k), "expired",
                                             e.get("expired_date"))}
               if _decision_date(ustate.get(k), "expired",
                                 e.get("expired_date")) else {}),
            # **为什么下线。** 和 `skipReason` 那一行同一个形状的镜像那一半：
            # 执行者标下线时写了原因（`job-apply.md` 那张表分「页面写着已关闭」
            # 与「点开是聚合页」两类），而屏幕上一个字都没有 —— 实测活动用户
            # 2026-08-31：28 个已下线的岗里 **15 个带原因**，日期跨 08-10 到
            # 08-27（是现行做法，不是历史残留）。
            #
            # 搁置区那句「已下线没什么可回看的」对**页面确认**的那 6 条成立，
            # 对**推断**的那 5 条不成立（「跳到职位聚合页」「点开是公司聚合页」）
            # —— 而「放回」按钮的提示语正好在问「职位其实还在？」，
            # 用户此前没有任何依据回答它。原因只进悬浮提示，可见标签不变。
            #
            # 面板标下线只写日期不写原因（`serve.py` 那一行），所以来源只有库里
            # 这一个字段，不必像 `skipReason` 那样排优先级。
            **({"expiredReason": plain(str(e.get("expired_reason")))}
               if e.get("expired_reason") else {}),
            # **什么时候标的不投。** 和上面 `expiredDate` 一模一样的取法：
            # 面板点的写进叠加层（`date`），命令行 `/job-rank --skip` 写进库
            # （`skip_date`，判据见 `job-rank.md` 那段 schema）。
            #
            # 这一行 2026-08-25 之前不存在，而 `expiredDate` 一直有 ——
            # **出局两条路，只有一条把日期带到了屏幕上**。搁置区里
            # 「已下线」印着「（2026-08-14 标的）」，「你排除的」只有一句理由。
            # 实测活动用户：库里 88 条带 `skip_date`，面板上 96 个不投的岗
            # 一个日期都没有。
            #
            # 为什么这个日期要紧：**求职拖久了，标准自己会动。** 第一周否掉的
            # 和上周否掉的不是一回事，而搁置区里它们长得一模一样。
            # （同一条对称规则的另一半 2026-08-25 刚补进 `job-rank.md`：
            # 「出局两条路都得记日期」—— 那次补的是写入端，这次是显示端。）
            **({"skipDate": _decision_date(ustate.get(k), "skipped",
                                          e.get("skip_date"))}
               if _decision_date(ustate.get(k), "skipped",
                                 e.get("skip_date")) else {}),
            # 你自己标了不投的。**不能因此不导出**——不导出就没法在页面上放回来，
            # 只能回命令行改 JSON，那正是这一版要消灭的往返。它要出现在
            # 「不投的岗位」里，带一个「放回可以投」。
            # HR 有没有点开过这份简历（面板上点的，`_cli.set_hr_viewed`）。
            # 三态：True / False / 不在 = 还没看过平台的投递记录页。
            # **`None` 和 `False` 不是一回事** —— 一个是没查，一个是查过、没打开。
            **({"hrViewed": ustate[k]["hr_viewed"]}
               if isinstance(ustate.get(k), dict) and "hr_viewed" in ustate[k]
               else {}),
            "skipped": _st == "skipped",
            # **第三个来源是 `rank_breakdown.依据`。**
            # 规则/粗筛判「跳过」时，理由**一直是写着的**（实测 720 个岗 720 个都有，
            # 例：「年包上沿约 32 万，低于底线 42 万（原文：20-25k·13薪）」），
            # 而它只活在那份拆解里 —— 页面上这 720 行悬停显示的是**两个字「跳过」**。
            # 和硬门那次是同一类：数据在盘上、断在最后一层。
            # 顺序：用户自己写的原因 > 抓取侧的 > 规则给的依据。
            "skipReason": (ustate.get(k, {}).get("reason")
                           or e.get("skip_reason")
                           or (plain(str((e.get("rank_breakdown") or {}).get("依据") or ""))
                               if is_rule_skipped(e) else "")),
            # 规则淘汰的（预筛判「跳过」）同样要能放回。原来只有用户手点的那种
            # 带 `skipped`，界面据此决定显不显示「放回可以投」——于是 103 个
            # （占全部 38%）被规则杀掉的岗**在界面上没有任何回头路**，只能改 JSON。
            # 而规则恰恰最容易错：实测 4 个年包 72-160 万的「智能体开发产品经理」
            # 死于标题含「开发」。谁下的结论谁最可能错，就更要留撤销口。
            "ruleSkipped": is_rule_skipped(e),
            # 岗位多久没刷新（判据见 `posting_age`）。**只在超过阈值时才给**：
            # 前端拿到就显示，拿不到就当不知道 —— 「很新」和「不知道」
            # 不是一回事，不能让后者长得像前者。
            "staleDays": (lambda a: a if a is not None and a > STALE_POSTING_DAYS
                          else None)(posting_age(e)),
            # **它在你手上排了多久。** 和上面那个 `staleDays` 不是一回事：
            # 那个说的是「抓到它那天，招聘方上一次刷新在多久以前」（只有猎聘给，
            # 实测覆盖约 10%）；这个说的是「它进我们的库到今天多少天」
            # （`first_seen`，100% 有）。
            #
            # 这个数早就在算了 —— `counts["ready_old"]` 用的就是它，面板那句
            # 「其中 15 个排了两周以上，从它们开始」印的也是它。而它**只作为一个
            # 计数出去**，逐岗的值被挡在了 `_first_seen` 那个局部字典里，
            # 理由写着「面板不显示它」—— 那句话已经变成循环：面板不显示是因为
            # 没导出，没导出是因为面板不显示。
            #
            # 后果实测 2026-08-25：材料就绪没投的 60 个里 **15 个排了 15-32 天**，
            # 面板一边说「从它们开始」，一边把名单按分数排给他看，
            # **没有任何一处标出是哪 15 个**。要照那句话做，他得逐个点开 60 次
            # —— 而点开也看不到，这个数根本没上过屏。
            #
            # **只标超过阈值的**，判据同上面那条 `staleDays`（「标记要标少数派」：
            # 「排了 3 天」是噪音，「排了 26 天」才是要人改主意的信息）。
            # 也只给「材料备好、还没投」的岗：别的岗排多久都不构成一个动作。
            # 值在下面那个 `funnels` 循环里填 —— 判据要看 `funnels`，
            # 而它是这个字典建好之后才算的。这里先占个位，别让它成为
            # 「有的岗有这个键、有的岗没有」的可选字段。
            "queuedDays": None, "queuedLong": False,
            # 缺失的字段留空字符串，**不编占位符**。seen_jobs 里本来就不是每条都有
            # 薪资/地点/年限（列表页给什么就有什么），前端遇到空串直接不渲染那一段。
            # 印「未标年限」会把「我们没抓到」说成一条信息，满屏都是噪音。
            "salary": e.get("salary") or "",
            # 薪资串里没写「N薪」、但详情页字段给了 salaryMonths 时不算未知——
            # 两行下面的 annual 正是用那个字段算的（assumed12=False），这里再标
            # 「没写几薪」就是同一屏自相矛盾。
            "salaryMonthsUnknown": (salary_months_unknown(e.get("salary") or "")
                                    and not e.get("salaryMonths")),
            **({"annual": annual} if annual else {}),
            "evaluated": bool(evaluated),
            # **「没做深评」不等于「没读 JD」，这两件事此前被同一枚章代表。**
            #
            # 短名单那枚章的判据是 `!evaluated`，而它的字面与悬浮提示写的是
            # 「完整 JD 没读、硬性条件没核对、公司没查」。实测活动用户
            # 2026-08-26：会挂那枚章的 1416 个岗里，**940 个的判词来源明写
            # 「粗筛（读过 JD 正文）」** —— 对这 940 个，那句话三条里有两条是假的，
            # 真正没做的只有公司调研与双角色审稿。
            #
            # 屏幕上说的必须是真的，所以把「读没读 JD」单独带出来，让前端分两枚章。
            # 判据取判词自己记的来源：写着读过就是读过；写「未抓 JD」「标题即判据」
            # 或没记来源的，一律算没读（拿不准的不许说成读过）。
            "jdRead": bool(
                (lambda _s: "读过 JD" in _s or "读了 JD" in _s or _s.startswith("深评"))(
                    (e.get("rank_breakdown") or {}).get("来源") or "")),
            # 技能与经验单独带出来。这是这一页最该显示的第二个数：
            # 20 个岗挤在 58-78 分，总分已经分不出高下，而「技能 82」与「技能 45」
            # 是两回事——一个真对口，一个是被年包托上去的。
            **({"skill": (e.get("rank_breakdown") or {}).get("技能与经验")}
               if isinstance((e.get("rank_breakdown") or {}).get("技能与经验"), int)
               else {}),
            # `依据` 是 /job-rank 用框架词写的内部记录，但它原样进了短名单行的悬浮提示。
            # 过一道 plain()：内容照留，词换成人话。
            **({"skillWhy": plain((e.get("rank_breakdown") or {}).get("依据"))}
               if (e.get("rank_breakdown") or {}).get("依据") else {}),
            "location": short_location(e.get("location") or ""),
            # 抓取器存的是 `workYears`（schema 里就叫这个）——**下面那条警告说的
            # 就是这一行**，它当时只改了 `viaHeadhunter`，紧挨着的这个没动。
            # 实测 2026-08-23：2638 个岗里 2361 个（89%）平台给了年限，
            # 面板上这一栏 **2456 个全是空的**，从有这一栏起就是。
            # 年限是硬门（`04-job-evaluation.md`「明确要求的年限下限高于候选人
            # 实际年限」），而活动用户的资料写着要按岗位措辞在两个数里选
            # （总年限 13 年 11 个月 / AI 产品 3 年 4 个月）——按后者算，
            # 这批里 1161 个岗的下限高于它。那正是他最该在屏幕上看见的一栏。
            "experience": e.get("workYears") or "",
            "channel": portal_name(e.get("portal")),
            # 这个岗属于「这几类岗要不要看」里的哪几类。**过滤在前端做，判据在这里给**
            # ——两边各写一份判据，计数和实际滤掉的数就会对不上。
            # **和 `pref_rows` 用同一个集合**（上面 `_onsite` 只算一次）——
            # 两处各算一遍，计数和实际滤掉的数就会对不上，
            # 那正是上面那段注释警告的事。
            "prefTags": pref_tags(e, _onsite),
            # 判据在 `via_headhunter()`——**别在这里读字段名**，
            # 上一版就是在这儿写 `e.get("via_headhunter")`，而抓取器存的是
            # `isHeadhunter`，1358 个猎头岗全被印成了「企业 HR 直招」。
            "viaHeadhunter": via_headhunter(e),
            "score": None if gate_fail else score,
            "verdict": "不满足硬性条件" if gate_fail else (verdict or "已评分"),
            "gates": [], "gatesNotJudged": [], "dimensions": [], "gaps": [], "quality": [],
        }
        if gate_fail:
            job["gateFailReason"] = verdict.replace("硬门 FAIL", "不满足硬性条件")
        elif "不满足硬性条件" in (verdict or ""):
            # **深评直接写「不满足硬性条件（学历）」的那批也算。**
            #
            # `gate_fail` 只认 `硬门 FAIL` 这个前缀（粗筛写的形态），而深评是把
            # 结论直接写成中文的 —— 实测 40 个岗这么写，于是它们进不了
            # `gate_fail_tally`。后果是面板上相邻两行打架：搁置区成分说
            # 「硬性条件没过 983」，下一行的分档合计只有 960。
            # **同一件事两个数，隔一行。**
            job["gateFailReason"] = verdict

        # `/job-apply --top N` 批量跑到一半缺东西时写下的阻塞（JD 抓不到、联系方式是
        # 占位符、typst 没装……）。批量**不许回头在对话里问**——一次长跑被十几个
        # 问题切碎，用户要做的事就从「批准一次」变成「按二十次继续」。
        # 所以问题攒到这里、由面板列出来，用户有空时一次答完。
        # `status` 不受影响：这个岗没有出局，只是缺一样东西。
        if e.get("blocked"):
            job["blocked"] = e["blocked"]

        # **深评没有的岗，门判定退到库里那份。** 判据与来源见
        # `gates_from_breakdown` —— 实测活动用户 2026-08-26：125 个存了判定的岗只有 2 个上过屏，
        # 其中 50 个带着判词表达不了的 FLAG。
        # 放在 `if app` 之前：深评那条路会**覆盖**它（`evaluation.md` 里那张表
        # 有依据原文，更全），覆盖不到的才留着这一份。
        if not job["gates"]:
            job["gates"] = gates_from_breakdown(e)
            if job["gates"]:
                judged = {_cli.gate_of(g.get("name") or "") for g in job["gates"]}
                job["gatesNotJudged"] = [g for g in _cli.GATES if g not in judged]

        if app:
            d = app_root / app["dir"]
            ev = d / "evaluation.md"
            if ev.is_file():
                t = ev.read_text(encoding="utf-8", errors="replace")
                job["gates"] = parse_gates(t)
                # **哪几道门根本没那一行**——判据在 Python 这一份（`_cli.GATES`），
                # 不在 TS 里再写一遍。页面拿它把「都核对过了」和「有几道没查」分开：
                # 2026-08-20 实测 236 个岗印着「这些条件都核对过了，没有要问的」，
                # 其中 **60 个实际有 2-3 道门没判**——和「整张表为空」是同一种谎，
                # 只是局部，而局部的谎更难发现（表在、行也在，只是少几行）。
                judged = {_cli.gate_of(g.get("name") or "") for g in job["gates"]}
                job["gatesNotJudged"] = [g for g in _cli.GATES if g not in judged]
                # 通勤那行是 Pass/Fail 的门，不进四维
                job["dimensions"] = [d for d in parse_dimensions(t)
                                     if "通勤" not in d["name"]]
                job["quality"] = parse_quality(t)
                job["gaps"] = parse_gaps(t)
                job["askBefore"] = parse_ask_before(t)
                # **「建议」那一节**。04 要求每份深评都写它，而在此之前
                # **没有任何消费方读它** —— `data.json` 里从来没有这个字段，
                # 于是屏幕上只剩判词那一半。实测 2026-09-02：50 份深评的
                # 「建议」以「不投」开头，其中 13 个的「下一步」还印着
                # 「材料就绪，还没投——复制开场白、开职位链接自己投出去」。
                # 解析走 `build_dashboard.parse_evaluation`（判词与分数的正本，
                # 不在这里另切一刀），`plain()` 剥掉 markdown 标记 ——
                # 这一段会进纯文本节点，`**` 会连着星号一起显示。
                job["advice"] = plain(
                    (parse_evaluation(t) or {}).get("advice") or "")
                # 深评的技能分来自四维表的第一行，与粗筛的 skill 同义。
                # 循环变量**不能**叫 d —— 外层的 d 是投递目录 Path，覆盖了会炸。
                for dim in job["dimensions"]:
                    if "技能" in dim["name"] and isinstance(dim.get("score"), int):
                        job["skill"] = dim["score"]
                        break
            if app.get("interview_log"):
                job["interviewLog"] = app["interview_log"]
            mats = {}
            # 三渠道话术全部带过去。开场白用 find_applications 已解析好的
            # （它顺手剥掉了「（实际字数：N）」标注）。
            #
            # **不截断。** 开场白有 600 字的上限是因为它本身就 ≤200 字，砍不到；
            # 而邮件正文与网申自评是要**整段复制去投**的东西，截一刀就等于交一份
            # 断掉的材料——而且断在哪里用户看不出来。宁可 data.json 大一点。
            o = app.get("outreach") or {}
            # **四段都过 `plain()`。** `AGENTS.md`「给用户看的措辞」那条：
            # 凡是从文件正文流向界面的字段，显示层都要先剥掉 `**` 和反引号。
            #
            # 这四段比面板上别处更要紧 —— 它们**不只是显示**：复制按钮原样复制、
            # `mailto:` 把正文原样塞进链接。也就是说 `**` 会跟着邮件发到用人方
            # 那里。06 渠道 2 自己写着那一节的用途是「整段选中、粘进邮件发给
            # 用人方」，同一段还留着一句「比多几个星号糟得多」—— 星号是已知的、
            # 一直没人处理的那一半。
            #
            # 实测 2026-08-27：导出的 data.json 里带 markdown 标记的字符串
            # 只剩 **1 条**，而它正是一段 `emailBody`（正文里编了号的三条
            # 加粗小标题）。别处早就剥干净了，只有这条路没接上。
            for key, src in (("greeting", o.get("greeting")),
                             ("emailSubject", o.get("email_subject")),
                             ("emailBody", o.get("email_body")),
                             ("wangshen", o.get("wangshen"))):
                if (src or "").strip():
                    mats[key] = plain(src.strip())
            # 开场白的铁律检查（判据见 `greeting_problems`）。只查这一段——
            # 邮件与网申自评不受**那五条**限制。
            #
            # ⚠️ **但它们受 `03` 的风格铁律管**，那一半走下面的
            # `style_problems`。这句注释原来只写了前半句，于是那几段
            # 在屏幕上一个字的提示都没有 —— 实测 2026-08-31：10 段网申
            # 自评里 5 段踩了 03（黑话「闭环」1、翻译腔 4），而它们
            # 旁边就摆着复制按钮。审计从 2026-08-27 起在报这件事，
            # 但那是事后的一份清单，这里才是他要用这段话的时刻。
            for _k in ("emailBody", "wangshen"):
                if mats.get(_k):
                    _sp = _cli.style_problems(mats[_k])
                    if _sp:
                        mats[_k + "Warn"] = _sp
            if mats.get("greeting"):
                probs = greeting_problems(mats["greeting"])
                if probs:
                    mats["greetingWarn"] = probs
                # **这段话该怎么发出去。** 面板原来对每个岗都印同一句
                # 「粘到{平台}的聊天框直接发」，而 `followups.py` 催进度时
                # 早就分了流（「BOSS 是聊天框；猎聘/智联走站内信，多半没有
                # 对话入口」）—— 催的时候知道形态，发的时候不知道。
                # 实测 305 份里 86 份被指去找一个多半不存在的聊天框。
                # 判据在 `_cli.send_hint`，猎头/直招三态与平台一起看。
                # **在跟谁说话**——抬头那半句写反了，第二轮就走反了。
                # 判据与审计同源（`_cli.addressee_problem`）：那边事后报一份清单，
                # 这边报在他按「复制开场白」那一下，和 `greetingWarn` 同一个位置。
                _who = _cli.addressee_problem(
                    o.get("head") or "", mats["greeting"], via_headhunter(e))
                if _who:
                    mats["addresseeWarn"] = _who
                # **这句公司的事，他从哪看来的。** 判据同样与审计同源
                # （`_cli.claim_without_source`）：开场白真对公司下了断言、
                # 而「本次使用的公司事实」那一节是空的。
                #
                # 没有出处的主张**没有任何办法验证**（`03` 铁律 1「绝不编造」），
                # 而这段字是他按「复制开场白」直接发给用人方的 —— 编错一句，
                # 对面第一轮就问得出来。审计从一开始就在报这件事，报的是
                # 事后的一份清单；这儿是他要用这段话的那一下。
                _src = _cli.claim_without_source(
                    mats["greeting"], o.get("facts") or [])
                if _src:
                    mats["factWarn"] = _src
                mats["sendVia"] = _cli.send_hint(
                    portal_name(e.get("portal")), via_headhunter(e))
                # **对面是猎头、HR，还是用人方本人。** 和上面两条同一个位置：
                # 他要按「复制开场白」的那一下。
                #
                # 开场白这一层三档没有区别（期望薪资与到岗时间一律不写，
                # 2026-08-17 裁定），**分档是给第二轮用的** —— 对着用人方老大
                # 讲职业规划与稳定性，是把唯一一次直达决策人的机会说成 HR 面。
                # 判据与 `/job-apply` 1.5b 同源（`_cli.counterpart_of`）。
                #
                # 职务认不出（字段空着、或写着看不懂的字符）时返回空串，
                # **这里就不写这个键** —— 面板宁可不说，也不猜一个给他。
                _cp = _cli.counterpart_of(e.get("recruiterTitle"),
                                          via_headhunter(e) is True)
                if _cp:
                    mats["counterpart"] = _cp
            pdf = d / "resume.pdf"
            if pdf.is_file():
                # **这份定制简历比主简历旧吗。**
                #
                # 主简历有 `pdfStale`（PDF 比 .typ 旧）盯着，而**投出去的那几份
                # 定制简历没有任何人比过**。实测（2026-08-22）：15 份定制简历
                # **15 份全部**早于主简历最后一次修改（08-12），正文里的数字
                # 也确实对不上（45 / 50k / 54 / 60 万 / 2012 那几个）——
                # 不是定制时编的，是主简历后来改了、它们没跟上。
                #
                # 为什么这件事要紧：`job-interview.md` Step 1 自己写着
                # 「`resume.pdf` 是**真正交出去的那份**，面试官读的就是它们，
                # 这里准备的每一个论点都必须和它们的说法一致」。旧版意味着
                # 他按现行资料准备的说法，和对方手上那张纸对不上——
                # 而「说法前后一致」正是背调和交叉面在查的东西。
                #
                # 留 1 秒容差，理由同 `pdfStale`：改完立刻编译是常态，
                # 而有些文件系统的 mtime 精度就是秒。
                try:
                    _base_m = (ud / "resume" / "main.typ").stat().st_mtime
                    if pdf.stat().st_mtime < _base_m - 1:
                        mats["resumeStale"] = _dt.date.fromtimestamp(_base_m).isoformat()
                except OSError:
                    pass
                name = f"{job['id']}.pdf"
                shutil.copy(pdf, PDF_DIR / name)
                mats["resumePdf"] = f"pdf/{name}"
                n_pdf += 1
            # **文件名以 `job-apply.md` 为准：`cover-letter.md`（连字符）。**
            #
            # 这里原来找的是 `cover_letter.pdf` / `cover_letter.typ`（下划线，
            # 而且是另外两个后缀）—— 流程正文里 6 处写的全是 `cover-letter.md`
            # 与 `cover-letter.<源扩展名>`。三处对不上（连字符/下划线、.md/.typ），
            # 于是这一格**永远是假的**，面板那句「求职信已生成，在同一目录」
            # 一次都没渲染过。
            #
            # 同族的前科这个仓库记了好几笔：`validThrough` vs `deadline`、
            # 同名材料目录、http vs https —— `build_dashboard` 那处注释
            # 管它叫「这是第五处」。名字对不上永远不报错，只是静默地什么都没有。
            #
            # 收 `.md` 和编译产物两种：`.md` 是流程规定的定稿落点，
            # PDF 是网申表单真正要上传的那份。
            if any((d / f"cover-letter{ext}").is_file()
                   for ext in (".md", ".pdf", ".typ")):
                mats["coverLetter"] = True
            if mats:
                job["materials"] = mats
        jobs.append(job)

    jobs.sort(key=lambda j: (j["score"] is None, -(j["score"] or 0)))

    # ---- 同岗多投放归组 ------------------------------------------------
    # 同一个岗常被多个猎头重复投放（实测：同一份供应链 JD 五个投放、启蒙教育四个），
    # 不归组的话「值得投 31 个」是虚的——用户会把同一个岗研究两遍。
    # 键用 **JD 正文前缀的哈希**（归一化后前 300 字）：不同猎头会做不同程度的脱敏
    # （删公司名等），全文哈希会漏；前缀保守——**宁可漏归组，不可错合并**。
    # 没有正文的（浏览器渠道、未抓到 JD）不参与归组。
    details_dir = ROOT / "users" / user / "job_scraper" / "details"
    by_prefix: dict = {}
    by_body: dict = {}
    for job in jobs:
        p = details_dir / f"{job['id']}.json"
        if not p.is_file():
            continue
        try:
            desc = json.loads(p.read_text(encoding="utf-8")).get("description") or ""
        except json.JSONDecodeError:
            continue
        norm = re.sub(r"\s+", "", desc)[:300]
        if len(norm) < 80:
            continue          # 太短的正文撞车概率高，不归组
        # **公司必须一起进键。** 只按正文哈希归组，前提是「正文相同 ⇒ 同一个岗被
        # 多个猎头重复投放」。那个前提有个洞：**同一份 JD 模板会被不同雇主原样复用**。
        #
        # 实测撞上：「AI业务落地专家」这套 JD（八项能力那份）在三家不同公司下一字
        # 不差，于是「某上海石化公司」那条被并进了「某上海贸易进出口公司」，
        # 在面板上**整条消失**——两个不同雇主、两份不同的年包，用户少看到一个岗。
        #
        # 加上公司之后，代价是脱敏程度不同的重复投放（同一个岗被写成「某上海大型
        # 日化公司」和真名）不再归组。那正是本段注释自己定的方向：
        # **宁可漏归组，不可错合并**——漏了只是多研究一遍，错了是一个岗看不见。
        body = hashlib.sha1(norm.encode("utf-8")).hexdigest()
        by_body.setdefault(body, []).append(job)
        key = hashlib.sha1(
            f"{(job.get('company') or '').strip()}\x00{body}".encode("utf-8")
        ).hexdigest()
        by_prefix.setdefault(key, []).append(job)
    n_dup = 0
    for group in by_prefix.values():
        if len(group) < 2:
            continue
        # **按年包挑主投放，不按分数。**
        #
        # 原来靠「jobs 已按分数排过序，组内第一个就是分最高的」。那有个反馈环：
        # `/job-apply` 深评会把分数**写回** `seen_jobs.json`，而分数又决定谁是主投放——
        # 写一次分，主条目就可能漂到另一个价位上去。实测同一个岗的两个挂法
        # （80-100k·16薪 = 128-160 万 / 50-80k·17薪 = 85-136 万），深评写回之后
        # 面板显示的年包从 128-160 万变成了 85-136 万，**少了 43 万**。
        #
        # 年包是 JD 自己的属性，不受任何写回影响；而同一个岗挂多个价时，
        # 用户要投的本来就是价高的那条。分数相同的组按年包排也不会更差。
        def _ann_low(x):
            a = x.get("annual") or {}
            return a.get("low") if a.get("low") is not None else -1
        group = sorted(group, key=lambda x: (-_ann_low(x), -(x.get("score") or -1)))
        primary, rest = group[0], group[1:]
        primary["duplicates"] = [
            {"url": j["url"], "salary": j.get("salary") or "",
             "via": j.get("channel") or "", "score": j.get("score")}
            for j in rest
        ]
        for j in rest:
            j["dupOf"] = primary["id"]
        n_dup += len(rest)
    if n_dup:
        # 不说「投放」——那是广告业的词，求职者读到不会想到「同一个岗挂在多处」
        print(f"  同一个岗挂在多处：{n_dup} 条归并到 "
              f"{sum(1 for g in by_prefix.values() if len(g) > 1)} 个岗下")

    # ---- 同文不同名：**不归并，只标出来** --------------------------------
    #
    # 上面那个键带着公司，所以「同一份 JD、公司名不一样」的一律不归组 ——
    # **那条裁定是对的，这里一个字都不改**（同一份 JD 模板真的会被不同雇主
    # 原样复用，错并的代价是一个岗在页面上整条消失）。
    #
    # 但「不归并」被当成了「不用说」。实测活动用户 2026-08-25：
    #
    #     JD 正文前 300 字一字不差的组      66 组 / 156 个岗
    #     └ 公司名相同（已归并）             22 组
    #     └ **公司名不同（故意没并）**       44 组 / 100 个岗
    #        └ 两条以上都还活着的            12 组 / 27 个岗
    #        └ **已经各自出过整套材料的**     1 组
    #
    # 而 `job-apply.md` 对这批的交代是「选岗时**自己再扫一眼 JD 正文**，
    # 认出是同一个岗就只跑一个……同一个岗别打两次招呼：两边猎头撞车对候选人
    # 是减分的」。规则是对的，**可它没说扫哪几个** —— 2581 个岗靠肉眼扫，
    # 这条规则等于没有。而算它的那份数据，上面这个循环刚刚算完就扔了。
    #
    # 所以这里只做一件事：把同组的**摆出来**。不合并、不隐藏、不判定谁是主条目
    # —— 判不了：可能是一个岗两家猎头在代招，也可能是两家公司套了同一份模板，
    # 而这两种的下一步正好相反（前者只投一个，后者两个都投）。
    n_same = 0
    for group in by_body.values():
        # 已经被归并的不参与：它在页面上任何地方都不渲染，摆出来点不开。
        live = [j for j in group if not j.get("dupOf")]
        if len(live) < 2:
            continue
        for j in live:
            # `x is not j` 这半是**防御性的、今天走不到**：下面那个公司比较已经
            # 把自己排掉了（自己和自己公司名必然相等）。变异实测把它去掉，
            # 没有任何可观察差别。留着是因为这里是边界 —— 哪天判据从「公司不同」
            # 换成别的，它挡住的就是把自己列进自己那一行。
            # **别为它写测试**：那会是一条永远绿的断言（同 `requeue` 里
            # `rank_verdict` 那半留下的记录）。
            other = [x for x in live if x is not j
                     and (x.get("company") or "").strip()
                     != (j.get("company") or "").strip()]
            if not other:
                continue
            j["sameJd"] = [{"url": x["url"], "company": x.get("company") or "",
                            "salary": x.get("salary") or "", "score": x.get("score")}
                           for x in other]
            n_same += 1
    if n_same:
        print(f"  JD 正文一字不差、公司名不同：{n_same} 个岗标了出来"
              f"（不归并 —— 可能是同一个岗两家猎头在代招，也可能是两家公司"
              f"套了同一份模板，投之前自己看一眼）")

    # ---- 人已经判过的那批：读 `同岗重复挂牌.md`，按它归并 ----------------
    #
    # 上面那段说得很清楚：同文不同名**机器判不了** —— 「一个岗两家猎头代招」
    # 和「两家公司套同一份模板」的下一步正好相反。所以它只标不并。
    #
    # 而这个仓库早就有人这一环的答案：认出是重复挂牌时，那个目录里只留
    # `posting.md` + 一份 `同岗重复挂牌.md`（指向主贴），不出评估也不出话术
    # —— `job-apply.md` 对重复挂法给的就是这个形状，语料里已经有 16 份。
    #
    # **写下来了，却没人读。** 于是那些目录在面板上仍各占一行，还挂着「没材料」
    # —— 实测活动用户 2026-08-26：「可以投的岗位」5 行里有 2 行是这种，
    # 用户直接问「为什么还是出现没资料的情况」。材料在主贴那边，一份都没少。
    #
    # 判据收得很紧，只认那一个形状：**这个目录既没有 `evaluation.md` 也没有
    # `outreach.md`**（就是「只留快照 + 指路」），**且**指路文件里那个
    # `` `<目录名>/evaluation.md` `` 解析得到、指到另一个真实存在的岗。
    # 任一条不满足就不动它 —— 自己有评估的那几份是有人**特意**分开评的，
    # 归并等于把他做过的判断抹掉。
    n_manual = 0
    url2job = {_cli.norm_url(j["url"]): j for j in jobs if j.get("url")}
    dir2url = {a["dir"]: a["url"] for a in all_apps if a.get("url")}
    for a in all_apps:
        d = app_root / a["dir"]
        note = d / "同岗重复挂牌.md"
        if not note.is_file():
            continue
        if (d / "evaluation.md").is_file() or (d / "outreach.md").is_file():
            continue
        me = url2job.get(_cli.norm_url(a.get("url") or ""))
        if me is None or me.get("dupOf"):
            continue
        text = note.read_text(encoding="utf-8", errors="replace")
        primary = None
        for ref in re.findall(r"`([^`/\n]+)/(?:evaluation|posting)\.md`", text):
            cand = url2job.get(_cli.norm_url(dir2url.get(ref, "")))
            # 不许自指，也不许接到一个自己就是重复挂牌的岗上（那会成环）。
            if cand is not None and cand is not me and not cand.get("dupOf"):
                primary = cand
                break
        if primary is None:
            continue
        me["dupOf"] = primary["id"]
        primary.setdefault("duplicates", []).append(
            {"url": me["url"], "salary": me.get("salary") or "",
             "via": me.get("channel") or "", "score": me.get("score")})
        # **归并之后把 `sameJd` 清干净。** 两件事：
        #
        # 1. 挂在**这一条**上的标记成了死数据 —— 它不再渲染，标了给谁看；
        #    而 `test_same_jd_different_company_is_flagged.test_nothing_got_hidden`
        #    钉着「被标出来的岗一个都不许带 dupOf」，那条守的是**自动规则只标不并**，
        #    人的判断不该把它的不变量弄脏。
        # 2. 挂在**别人**身上、指向这一条的那一项要摘掉 —— 否则主贴上会留一句
        #    「这份 JD 在别处也有」，点过去是一行**根本不渲染**的岗。
        me.pop("sameJd", None)
        for other in jobs:
            lst = other.get("sameJd")
            if not lst:
                continue
            kept = [x for x in lst
                    if _cli.norm_url(x.get("url") or "") != _cli.norm_url(me["url"])]
            if len(kept) != len(lst):
                if kept:
                    other["sameJd"] = kept
                else:
                    other.pop("sameJd", None)
        n_manual += 1
    if n_manual:
        print(f"  你自己标过的重复挂牌：{n_manual} 条按「同岗重复挂牌.md」归并了"
              f"（材料在主贴那边，这几条不再单独占一行）")
    if n_drift:
        print(f"  ⚠ {n_drift} 个岗的深评结论还没写回职位库——总览页显示的是深评值，"
              "但排序与选岗读的是库。补账：python tools/writeback.py --apply")

    n_ranked = n_processed(seen)
    _n_wait = n_waiting(seen)
    # `doctor` 在本文件里是**按需 import** 的（见 `probe_env` 那处），
    # 顶上没有它 —— 这里照同样的写法，别为一句话把它提到模块级
    # （那会让每次 import 本模块都跟着起 doctor 的探测栈）。
    try:
        import doctor as _doc
        _wait_note = (_doc.waiting_note(seen)
                      if _doc.waiting_age(seen)["stale"] else "")
    except Exception:                             # noqa: BLE001
        _wait_note = ""                           # 取不到就不说，别猜
    # 投递记录**要回接到岗位上**，不能只数个数。
    #
    # 原来这里只算 `n_sent = 行数-1`，于是流水线显示「已投递 1」，但**哪一个投了
    # 看不出来**——那个岗照旧躺在「可以投的岗位」里，和没投过的长得一模一样。
    # 求职最容易犯的错就是重复投同一家；一个只报总数、不报是哪个的计数器，
    # 正好帮不上这个忙。
    #
    # 匹配**复用 `build_dashboard.match_tracker`**，不要在这里另写一套。第一版就在这
    # 另写了个「公司名+岗位名归一后比」的版本，比它差两处：它先按 source URL 精确匹配，
    # 而且知道 51job 同一详情 URL 下会挂两个不同职位——只比 URL 会让「投了甲」把同 URL
    # 的乙也标成已投，乙随之从待投区消失。同一件事只留一个实现。
    tracker = ud / "job_search_tracker.csv"
    trows: list[dict] = []
    # 走 `build_dashboard.load_tracker`，**不要在这里内联一份 DictReader**：
    # 那份没有 UnicodeDecodeError 兜底。用户在 Excel 里打开台账再保存就是 GBK，
    # 于是整个导出裸抛、data.json 一个都不生成，面板直接空掉——而 load_tracker
    # 早就把这一课写在注释里，`serve.py` 读同一个文件走的就是它。
    trows = [r for r in load_tracker(tracker) if (r.get("company") or "").strip()]

    for j in jobs:
        # match_tracker 只读 title / company，导出的 job 字典本来就有这两项，
        # 不必回头去 seen 里取。
        r = match_tracker(j, j.get("url") or "", trows)
        # 「这个状态接下来能点什么」由 Python 算好带过去，**TS 侧不另写一套状态机**。
        # 两份状态机迟早会分叉，而分叉的样子是：页面画出一个按钮，服务端拒绝它。
        # 台账里没有这一行 = 还没投，它也有下一步（「我投了」），所以这句要在
        # `continue` **之前**——放后面的话，没投过的岗一个按钮都没有，
        # 而那恰恰是最需要能点一下的那批。
        j["nextStatuses"] = tk.next_steps((r.get("status") or "") if r else "")
        if not r:
            continue
        status = (r.get("status") or "applied").strip()
        j["applied"] = {"date": (r.get("date") or "").strip(),
                        "status": status,
                        # 状态码是给统计用的英文值，页面上要说人话——由状态机的
                        # `say()` 译，不让 TS 侧另抄一份词表。
                        "statusLabel": tk.say(status),
                        # 渠道**推得出来就推**（`channel` 列历来全空，而
                        # `source` 里就存着原始链接）——判据在 `tracker.channel_of`。
                        "channel": tk.channel_of(r)}
    # 台账行钉在**重复挂法**上时，把投递状态移交给主条目——dup 条目在页面上
    # 任何地方都不渲染（行集过滤 `!dupOf`，funnels_of 也不计它），投递记录落在
    # 它身上等于整个消失：主投放看起来没投过、照旧躺在「可以投的岗位」里，
    # 恰是「防重复投同一家」要防的事故。
    by_id = {j["id"]: j for j in jobs}
    for j in jobs:
        if j.get("dupOf") and j.get("applied"):
            primary = by_id.get(j["dupOf"])
            if primary is not None and not primary.get("applied"):
                primary["applied"] = j["applied"]
                primary["nextStatuses"] = j["nextStatuses"]
    # **这家你已经投过几个了。** 同在 applied 回接之后算，理由和下一步一样。
    #
    # 国内投递里同一家公司连投多个岗是有代价的：大厂的 ATS 把同一人的记录
    # 合在一起给 HR 看，短期内连投几个读起来就是广撒网；更贵的是**撞单**——
    # 一个岗走猎头报备、另一个自己直投，用人方那边撞成重复候选人，
    # 谁来推、推荐费算谁的都要掰扯，处理不好两条都卡住。
    #
    # 这套道理 `followups.py` 早就写全了 —— 但它长在 `/job-outcome followup`
    # 里，那是**投完之后**才跑的。避撞单的意义恰恰在于别让它发生：
    # 实测活动用户 2026-08-23，备好没投的 75 个里有 **7 个**落在已投过的公司，
    # 最重的那家发完会是 **6 个**、第二重的 **4 个** —— 而同一块面板正劝他
    # 「手上那 62 份备好的别等」。
    #
    # **公司身份走 `cluster_key`，不用公司名裸比**：脱敏串「某知名公司」
    # 库里 158 次，裸比会印出「这家你已经投过 4 个岗」而那是四家不同的公司。
    # **收日期，不只是计数。** 这个 dict 的值是这家公司每一笔投递的日期串；
    # 「多久以前」交给正本 `build_dashboard._days_since` 解析（台账是人手填的，
    # 它认四种写法）。只数个数的那一版说不出「短期内」是真是假 —— 判据见
    # `SAME_COMPANY_DAYS`。
    _sent_at: dict[str, list[str]] = collections.defaultdict(list)
    for j in jobs:
        _a = j.get("applied")
        _k = cluster_key(j.get("company") or "")
        if _a and _k:
            _sent_at[_k].append((_a.get("date") or "").strip())
    _now = _dt.date.today()
    # `url → first_seen`。原来它只在下面算 `counts["ready_old"]` 时才建，
    # 注释写着「面板不显示它，不必为一个计数多带一列出去」——
    # 而那句话已经变成循环（见 `queuedDays` 那段）。现在逐岗也要用它。
    _first_seen_all = {e.get("url"): e.get("first_seen")
                       for e in seen.values()
                       if isinstance(e, dict) and e.get("url")}

    # 逐岗的下一步**必须在 applied 回接之后算**——它要看投递状态。
    # 放在前面算的话，已投/已面的岗会被判成「材料就绪，去投递」。
    for j in jobs:
        step = job_next_step(j)
        if step:
            j["nextStep"] = step
        j["funnels"] = funnels_of(j)
        # **它在你手上排了多久**（见这个键上面那段说明）。判据要看 `funnels`，
        # 所以填在这儿，不在上面那个字典字面量里。
        if "materials" in j["funnels"] and "applied" not in j["funnels"]:
            _q = _days_since(_first_seen_all.get(j.get("url")) or "", _now)
            if _q is not None:
                # **原始天数全给，「够不够久」单独标一个。**
                #
                # 原来这里只在超阈值时才填 —— 判据没错（名单上只标少数派），
                # 错在**把判据烧进了数据**：拿不到原始天数的人就只能另找一个字段
                # 去算。而真有这么一个人：`doctor.ready_age` 要报「这 60 份材料
                # 放了中位 N 天」，它拿不到这个数，就退去读了 `staleDays` ——
                # 那是「抓到它那天招聘方多久没刷新」，只有猎聘给、覆盖约 10%。
                #
                # 实测 2026-08-25 的代价：备好没发的 60 个里只有 10 个有
                # `staleDays`，于是自检那句「中位 20 天、其中 10 份排了两周以上」
                # 是在 10 个数上取的中位，而那 10 个又恰好全都超阈值
                # （`staleDays` 本身就只在超阈值时才有值）—— **那个「10」实际等于
                # 「有这个字段的有几个」**。同一时刻面板说 15。
                #
                # 判据仍然只有一份，只是搬了个位置：谁该被标由 `queuedLong` 说了算
                # （Python 这边判），前端只读标志 —— 同 `Gate.offSpec`、
                # `Dimension.weighted` 的做法。
                j["queuedDays"] = _q
                j["queuedLong"] = _q > STALE_POSTING_DAYS
        # 只给**还没投**的岗带这个数 —— 已投的那些，这条提醒来晚了，
        # 而且它们自己就是分子，印出来只会让人以为要重复处理。
        if not j.get("applied"):
            _days = _sent_at.get(cluster_key(j.get("company") or ""), [])
            _ago = [d for d in (_days_since(x, _now) for x in _days)
                    if d is not None]
            _note = same_company_note(len(_days), min(_ago) if _ago else None)
            if _note:
                j["sameCompanyWarn"] = _note

    # 流水线那三格**都由 `funnels` 数出来**，页面也按同一个字段筛。
    #
    # 那一段注释一直写着「数字必须等于点开能看到的那些——数字 5、点开 4，
    # 用户会以为漏了一个」，可三格里有三格对不上，因为计数和筛选各写各的：
    #
    #   材料就绪  数=有材料（含已投的）      点开=有材料**且没投**   → 说 4 给 3
    #   已投递    数=台账**行数**            点开=匹配上的岗         → 有对不上的行就虚高
    #   面试中    数={interview,offer,hired} 点开=[interview,offer]  → 录用的岗看不到
    #
    # 三处都是**投递发生之后**才显形的，而在页面能记状态之前，这些数永远是 0。
    # 所以口径只留一份：一个岗属于哪几格，`funnels_of` 说了算。
    n_mat = sum(1 for j in jobs if "materials" in j["funnels"])
    n_sent = sum(1 for j in jobs if "applied" in j["funnels"])
    n_intv = sum(1 for j in jobs if "interview" in j["funnels"])
    # **谈钱那一格单独数，不走 funnels。** 漏斗那一格是**累计**口径
    # （拿到 offer 的岗当然走过面试），对漏斗是对的；而 `next_step` 问的是
    # 「他现在最该做哪一件」——那一问上，offer 必须先于面试，判据见
    # `build_dashboard._OFFER_STATUSES` 上面那段。
    #
    # 少了这一行，那边 `counts.get("offers", 0)` 恒为 0：修法只落在单页版上，
    # 而用户看的是这一份。同一个数两处各建一份，正是这次要修的形状本身。
    n_offer = sum(1 for j in jobs
                  if j.get("applied")
                  and (j["applied"].get("status") or "").strip().lower()
                  in OFFER_STATUSES)

    # **投过、却落在搁置区的岗。**
    #
    # `funnels_of` 排掉判词出局与三类搁置 —— 那是对的：格子上的数必须等于
    # 点开看到的行数。可「投了多少」这个数**在同一屏上出现两次**：
    # 流水线第 4 格走 funnels，「投出去的那些」那颗按钮走投递记录行数。
    # 实测 2026-08-31：一个 **85**、一个 **88**，上下摆着，差 3，
    # 而页面一个字都没解释 —— 用户只能自己猜哪个是真的。
    #
    # 4 个岗是「投过、评下来却不满足硬性条件」（其中 1 个他后来标了不投）。
    # **数不算它们是对的，不说才是错的**（同这一格已有的「另有 N 个被你关掉了」）。
    n_sent_parked, _sent_note = _parked_sent(jobs)

    # 「匹配不到」要按**真匹配数**判，不能拿格子数 n_sent 判——n_sent 走 funnels，
    # 会排掉「投了之后又标不投」「深评判出局」的岗：那些台账行明明匹配上了，
    # 只是页面上不占行。拿 n_sent 判会把它们说成「公司名/岗位名写法不一致」，
    # 诊断指错方向（纯 UI 操作就能触发：点「我投了」再点「不投这个岗」）。
    n_matched = sum(1 for j in jobs if j.get("applied"))
    if len(trows) > n_matched:
        # 说出来，别静默。对不上多半是公司名/岗位名写法不一致，用户能自己改 CSV。
        # **不把这几条算进格子里**：格子点开只能显示匹配上的岗，算进去就又回到
        # 「数字比点开看到的多」——那正是这次要修的东西。
        print(f"  投递记录 {len(trows)} 条，其中 {len(trows) - n_matched} 条在职位列表里"
              f"匹配不到对应岗位（公司名或岗位名写法不一致）；"
              f"流水线只数匹配上的，点开才看得到")

    # 下一步用面板那套 next_step 算 —— 两个页面不能各给各的建议
    # `url → first_seen` 上面已经建过一份（`_first_seen_all`）——
    # 逐岗的 `queuedDays` 和这里的 `ready_old` 用的是**同一个**，
    # 两份各建一遍就是等它们哪天不一致。
    counts = {
        "scraped": len(seen), "ranked": n_ranked, "materials": n_mat,
        "applied": n_sent, "interviewing": n_intv, "offers": n_offer,
        # 「材料备好、还没投」直接数，不拿 materials − applied 去减：
        # 手动投的岗有 `applied` 却没材料目录，减法会把它多减一次
        # （2026-08-12 实测面板报 104、实际 105）。口径必须与 `funnels_of`
        # 一致——它已经排掉了重复挂法、已下线、标不投的和判词出局的，
        # 所以这里直接借它，不另写一份筛选。
        # 读 `j["funnels"]`——上面那个循环刚存好，别再按岗重算。
        # （口径仍是 `funnels_of`，存进去的就是它的返回值。）
        "ready": sum(1 for j in jobs
                     if "materials" in j["funnels"] and "applied" not in j["funnels"]),
        # **这批里在队列上躺过 14 天的有几个。**
        #
        # 注意和 `staleDays` 不是一回事：那个说的是「抓到它那天，它上一次刷新在
        # 多久以前」（靠猎聘的 `date`，实测只有 10% 的岗有），这个说的是
        # **它在我手上排了多久**（`first_seen` → 今天，100% 有）。
        #
        # 为什么要数它：岗位会在他发出去之前先下线。实测 2026-08-23，
        # 有材料没投的岗按队列岗龄分桶，已下线的比例是
        # **≤7 天 2/27、8-14 天 2/95、>14 天 8/34（23%）** ——
        # 超过两周那一档，将近四分之一已经没了。
        # 阈值直接用 `STALE_POSTING_DAYS`（14），不另立一个数。
        "ready_old": sum(
            1 for j in jobs
            if "materials" in j["funnels"] and "applied" not in j["funnels"]
            and (lambda a: a is not None and a > STALE_POSTING_DAYS)(
                _days_since(_first_seen_all.get(j.get("url")) or ""))),
        # 这批里**可以直接发**的那两档（见 `STRONG_VERDICTS`）。
        # 分开数是因为「可以考虑」那一档的定义是「先问清楚再决定」，
        # 把它和「值得投」加成一个数去催人发，等于替用户做了他还没做的决定。
        "ready_strong": sum(1 for j in jobs
                            if "materials" in j["funnels"]
                            and "applied" not in j["funnels"]
                            and is_strong(j.get("verdict") or "")),
        # 「可以考虑」那一档里，**评估真列了要问什么**的有几个。
        #
        # 那一档的定义就是「先问清楚再决定」，所以每一处劝人「投之前先问清楚」
        # 的话，都默认那份清单存在。实测活动用户 2026-08-30：有材料、在跑的
        # 「可以考虑」56 个，**其中只有 9 个列了**。
        # 对另外 47 个，那句建议指向一份不存在的东西 —— 面板上早就分两枚章
        # 说清了（`Shortlist.tsx` 的 `askBefore` 分支），而终端那句没有。
        #
        # 判据走 `parse_ask_before`（它会把「无 / 暂无 / 不适用」这类占位滤掉）
        # —— 有标题不等于有内容，那一课 `check_maybe_tier_has_questions` 记过。
        "ready_asked": sum(1 for j in jobs
                           if "materials" in j["funnels"]
                           and "applied" not in j["funnels"]
                           and not is_strong(j.get("verdict") or "")
                           and j.get("askBefore")),
        # **材料做出来了、岗却先关了。** 这个数是「别把备好的压着」那句建议
        # 的证据（`build_dashboard.season_note`）—— 没有它那句话只是个说法。
        # 注意不能用 `funnels`：`is_parked` 已经把已下线的排掉了，
        # 这里数的恰恰是被排掉的那一批。
        "expired_unsent": sum(1 for j in jobs
                              if j.get("materials") and j.get("expired")
                              and not j.get("applied") and not j.get("dupOf")),
    }
    top = next((j["url"] for j in jobs
                if j["score"] is not None and not j.get("materials")
                and not j.get("expired") and not j.get("skipped")), None)
    # 「现在还能投几个」——`next_step` 靠它判断名单是不是快见底了。
    # 口径必须与页面那份行集一致（`App.tsx` 的 `sellable`）：排掉重复挂法、
    # 判词出局的、标了不投的、以及已经投出去的。**不另写一份判据**——
    # 页面说「可以投的岗位 11」而下一步按另一个数提醒补货，是这一页最容易
    # 出现的自相矛盾。
    # 三类搁置同样走 `is_parked`（正本在 build_dashboard）：这里原来把
    # `dupOf / skipped / expired` 又内联展开了一遍，与那个函数逐字同义。
    # 2026-08-26 扫重复定义时收掉 —— 同一族的判断散在四处，正是
    # 「不另写一份判据」这句话自己防不住的东西。
    n_sellable = sum(
        1 for j in jobs
        if not is_parked(j) and not j.get("applied")
        and is_sellable(j.get("verdict") or ""))
    # profile_ok 曾经写死成 True —— 于是 next_step 的第一条分支
    # （「先建资料：跑 /job-setup」）**永远触发不到**。资料还是占位符时，面板会跳过
    # 这一条、直接建议去抓职位/去投递，而那时候投出去的材料里全是 [YOUR_NAME]。
    # 这是整条流水线最靠前的一道守卫，不能靠一个常量绕过去。
    cand = ud / "profile" / "candidate.md"
    # 判据只有一份，在 `build_dashboard.profile_ready`。这里原来自己写了条
    # `\[YOUR_[A-Z_]+\]` —— 只认模板 74 种占位符里的 38 种，学历 `[DEGREE]`、
    # 能力边界禁区 `[FORBIDDEN_CLAIM_1]` 全在它视野之外（实测：一份还剩 36 个
    # 占位符的资料被判为已就绪）。同一条规则的第二份副本，改一处不改另一处，
    # 面板和自检就会各说各的。
    profile_ok = profile_ready(cand)
    # 「抓到但没评」的数量也要传——见底分支靠它区分「先评库存」与「真要去抓」。
    # 两个调用方原来传的参数不相交（build_model 传 n_unranked 不传 n_sellable，
    # 这里反过来），于是「抓了 543 个、0 个已评」的新用户状态在面板上落进
    # 见底分支、被指回 /job-scrape 死循环，而 doctor 说的是 /job-rank。
    n_unranked = sum(1 for e in seen.values()
                     if (e.get("status") or "new") == "new")
    # **投后统计要先算**：`next_step` 要用它判断「投了这么多，回音率是多少」。
    # 那一条比「还有几个材料没投」更靠前，判据见 `next_step` 里那段说明。
    ostats = outcome_stats(jobs, trows, seen)
    _bk = {b["k"]: b["n"] for b in ostats["buckets"]}
    # 有回音 = 约到面试或被明确拒绝；已决出 = 再加上「大概率没戏」（过了静默线）。
    # 「还在等」不算——它还没到该有结论的时候。
    counts["replied"] = _bk.get("约面或更远", 0) + _bk.get("被拒", 0)
    counts["decided"] = counts["replied"] + _bk.get("大概率没戏", 0)
    # 直招那批单拆一份，判据见 `next_step` 的零回音分支。
    counts["direct_decided"] = ostats.get("directDecided", 0)
    counts["direct_replied"] = ostats.get("directReplied", 0)
    counts["chat_decided"] = ostats.get("chatDecided", 0)
    counts["viewed_direct"] = ostats.get("viewedDirect", 0)
    counts["unviewed_direct"] = ostats.get("unviewedDirect", 0)
    # 那批投递落在哪几个月 —— `season_note` 拿它判断「这批是不是赶上了淡季」。
    # 日期格式手填的台账里有四五种，`followups.parse_date` 已经全认，别另写一套。
    from followups import parse_date as _pd
    # 求职状态（在职 / 离职 / 在读）—— `season_note` 拿它挑校招还是社招日历。
    # 两套日历在七八月正好相反：社招淡季 vs 秋招提前批。读不出就不传，
    # 那时面板一句季节的话都不说（说错季节比不说更坏）。
    counts["stage"] = candidate_stage(user)
    counts["applied_months"] = [
        d.month for d in (_pd(r.get("date") or "") for r in trows) if d]
    # **渠道那一段要在 `next_step` 之前算。** 它原来排在 payload 里（更靠后），
    # 于是「去补新的」这类建议手上没有渠道信息 —— 而实测 2026-08-24 那正是
    # 现在最要紧的一条：贡献了 83% 可投岗的那家**关着**，同一块面板还在劝
    # 「旺季用来补新的」。`portal_rows` 只读 `(user, seen, jobs, qlog)`，
    # 这几样这时候都齐了，挪上来没有代价。
    _portals = portal_rows(
        user, seen, jobs,
        (raw.get("query_log") or []) if isinstance(raw, dict) else [])
    counts["off_supply"] = off_supply(_portals)
    ns_text, ns_cmd = next_step(counts, profile_ok, top,
                                n_unranked=n_unranked, n_sellable=n_sellable)

    # 「该重跑一遍」的标要在 payload 之前打 —— 它往 `jobs` 里塞字段，
    # 而下面那个字典就地引用了同一个列表。
    _n_restale = mark_restale(user, jobs)

    payload = {
        "isRealData": True,
        "outcomeStats": ostats,
        # 卡在硬性条件上的那批，按是哪道门归一计数。判据与理由见 `gate_fail_tally`。
        # 门名一直存着（99%），此前只在一个小戳的悬浮提示里出现过 —— 全貌看不见，
        # 而全貌才指得出动作（层级够不着 / 学历门关着 / 你自己的排除列表在收钱）。
        "gateFailTally": gate_fail_tally(jobs),
        # 那一行只给得出一个总数（十一条加起来）。他打开清单时十一条
        # 一样长，看不出该动哪一条 —— 最贵的那条一个人挡掉 102 个。
        "topExclusions": top_exclusions(jobs, user),
        # 库里明写薪数的岗，薪数中位数。给「按 12 薪保守算」那句话一个参照量级。
        # 判据与「为什么不拿它去改折算」见 `observed_months`。
        "observedMonths": observed_months(jobs),
        # **门槛是一个数，前端别再写死一份。** 面板那格「几天前刷的」原来
        # 在 `Portals.tsx` 里硬编码 `>= 14`，同一行的提示语还写着「两周」
        # —— 加上 `doctor.py` 那份有据的复刻，这个 14 一共有四份，
        # 而守卫只盖住了 Python 那两份。改这里的值，面板会继续按 14 上色。
        # 判据与「为什么是 14」见 `RESUME_STALE_DAYS`。
        "resumeStaleDays": RESUME_STALE_DAYS,
        "outcomeReasons": [{"value": v, "label": t} for v, t in tk.REASONS],
        # `ready` / `readyStrong` 要导出来：`doctor.count_ready` 第一件事就是读
        # `nextStep.ready`，而 payload 原来只有 text + command——那行代码从来没取到过值，
        # 每次都静默落到兜底分支（自己数 jobs）。结果碰巧一样，但那是条死路。
        "nextStep": {"text": ns_text, "command": ns_cmd or "",
                     "ready": counts["ready"],
                     "readyStrong": counts["ready_strong"],
                     # 「可以考虑」那批里真列了问题的有几个 —— 终端那句
                     # 「投之前先问清楚」靠它才说得准。口径归这里，
                     # `doctor` 只取数不重算（那边不 import 本仓库任何模块）。
                     "readyAsked": counts["ready_asked"]},
        "activeUser": user,
        # 环境探测。**原来根本没导出**，界面 `d.envItems ?? demoEnv` 兜底到了
        # 虚构演示数据——于是面板上那句「要装的工具 都装好了 4/4」是假的：
        # 写死的 Node v22.9.0 / Typst 0.13.0，与这台机器上的实际情况无关。
        # 这正是本文件开头警告的那种坑：虚构数据的问题不是不够真，而是它长得像真的。
        #
        # 漏掉的直接原因是**字段名对不上**：`doctor.probe_env()` 给的是 `label`，
        # 界面要的是 `name`。名字不同、类型宽松（可选字段），两边就这么各活各的。
        "envItems": [
            {"name": e.get("label") or e.get("name") or "",
             "ok": e.get("ok"), "detail": e.get("detail") or "",
             "unlocks": e.get("unlocks") or "",
             # **可选与否必须带过去。** 原来这一行没有，于是网页版只能按
             # `ok === false` 数「缺几项」——一台没装 Bun 的机器上它会说
             # 「还差 Bun（可选）」并每次默认展开，催人装一个不需要的东西。
             # 判断走 `build_dashboard.is_optional`，与单页版**同一个函数**。
             "optional": is_optional(e),
             # **会静默失败的那一项要单独标出来。** 中文字体是唯一「缺了不报错、
             # PDF 照样出、ATS 校验也过、但渲染是豆腐块」的依赖——只和别的项并排
             # 列在表里，用户不会意识到严重性。`doctor.py` 早就标了 `silent_fail`，
             # 这里原来没带过去（和 `optional` 同一个位置、同一个病）。
             "silentFail": bool(e.get("silent_fail")),
             # 怎么装。缺项时给出去，省得用户自己去搜。
             "fix": e.get("fix") or ""}
            for e in _probe_env_safe()
        ],
        # 全部命令。面板只露过 18 个工作流里的 7 个——`/job-outcome`（投完记录结果）、
        # `/job-offer`、`/job-upskill` 连提都没提过。而这个仓库的判断力全在命令行侧，
        # 面板不说出命令，用户就只能靠翻文档才知道自己还能做什么。
        # 从 workflows/INDEX.md 的索引解析，不在前端写死（写死必然跟索引飘）。
        "commands": parse_commands(),
        "detectedTool": _cli.detect_code_tool(),
        # 这个 clone 下有哪些用户。面板原来只知道「当前是谁」，于是那个
        # 「换个用户」按钮既列不出可选项、也说不出怎么新建——它就是个死按钮。
        # 多人共用一份 clone 是 AGENTS.md 明确支持的用法，界面得让人看得见。
        # 只报名字，不读任何人的数据：切换与新建都由 /job-user 在命令行做。
        #
        # **这里比终端那份少。** 判据的正本是 `_cli.all_users`，它把
        # `users/` 下每个目录都返回、并标出哪些还没建档；doctor 与命令行
        # 报错都照那份列，空壳也列出来（用户得找得到才删得掉）。
        # 这个弹层不一样：它每一行都配一条 `/job-user <名>` 让人点着切过去，
        # **而切到空壳是死胡同**——落进一个什么都没有的工作区，然后每条命令
        # 都说「资料还没填」。所以这里按 candidate.md 过滤，是有意的。
        # 实测活动用户 2026-08-24：终端 10 个、这里 8 个，差的两个是
        # 测试留下的空目录。要清它们，终端那条 /job-user --remove 会说。
        # HR 聊天框里反复问的那几句，连同已经写好的答案。判据见 `hr_answers`。
        "hrAnswers": hr_answers(user),
        "allUsers": sorted(
            d.name for d in (ROOT / "users").iterdir()
            if d.is_dir() and (d / "profile" / "candidate.md").is_file()
        ) if (ROOT / "users").is_dir() else [],
        # 「搜到 268 → 打过分 229」中间那个缺口，用户会读成「还有 39 个要做」。
        # 但其中一部分只是**降权泊车**：标题显示方向不对、留着没结案，抓 JD 的额度
        # 轮不到它们。把这个数单独给出来，缺口才解释得通——不然用户要么以为积压很多，
        # 要么以为工具漏了活。这就是当初「队列排不空」的正解：用记账解决记账问题。
        "parked": n_parked(seen),
        # 存档计数。archive.py 归档时顺手记在热库顶层，这里免费读到——
        # **不去啃冷库**：它只增不减，一年后几十 MB，为个计数每次点击都读一遍
        # 就把归档省下的时间又还回去了。
        "archivedCount": int((raw.get("archived") or {}).get("count") or 0)
                         if isinstance(raw, dict) else 0,
        # 「该重跑一遍的岗」有几个。按钮做不成（`serve.py` 那条路只改一个字段、
        # 不接大模型），但**命令必须印在他看得见的地方** —— 这条队列此前只在
        # `/job-auto` 收尾的终端输出里一闪而过，而终端日志没人看。
        "restaleCount": _n_restale,
        # 「招聘网站」那一块：各渠道开着没、抓了多少、最近哪天抓的。
        # **开关要落在盘上**（`job_scraper/portals.json`），因为读它的是命令行侧的
        # `/job-scrape` —— 存进浏览器 localStorage 的话，抓取时根本看不见。
        # 上面 `next_step` 之前就算过了，复用那一份 —— 算两遍会多读一次详情库，
        # 而且两份哪天不一致，面板和「下一步」就会各说各的。
        "portals": _portals,
        # 「这几类岗要不要看」。只管显示，不改判词——见 PREF_FACTS 的说明。
        "prefs": pref_rows(user, seen, _onsite),
        # 每格带上「这一步在做什么 + 该敲什么」。
        #
        # 原来五格只有数字和名字。而「各部分分别该做什么」这件事，页面上唯一说过的
        # 地方是最底下那个折叠的命令表——它按任务类型分组（找岗挑岗 / 投一个岗 /
        # 投出去之后），**与顶上这五格对不上号**，还得先展开才看得见。
        # 于是用户问出了「可以投的不多了，怎么让你继续抓取」：流程就在他眼前，
        # 但每一格该敲什么从来没写在格子上。
        #
        # 挂在格子上而不是另起一个说明版块：眼睛本来就落在这儿，格子还本来就可点。
        # `do` 一律是**可照抄的命令**，不写「去平台上投递」这种敲不了的话
        # （投递这一步没有命令，就明说它在招聘网站上做，再给投完那一步的命令）。
        #
        # **给的是不带参数的形式。** 三条原来写成 `/job-apply <职位链接>`、
        # `/job-outcome <公司>`、`/job-interview <公司>`，两个代价：
        #
        # 1. **那串放不进格子。** 五格并排时每格约 195px，扣掉内边距只剩 165px，
        #    而带参数那串要 ~160px 加复制图标 —— 1000-1180px 宽的屏幕上它折行，
        #    屏幕上是「/job-apply <职位链接」换行「> ⧉」。命令是这一页唯一
        #    要原样带走的东西，断开就等于让人怀疑自己看漏了。
        # 2. **它不能直接粘。** 用户站在总览页上，手里没有职位链接；
        #    复制走还得先把尖括号改掉。而这三条**不给参数都是有意义的**
        #    （见 workflows/INDEX.md 工作流索引第四列：apply 给「可以投」那档全部出材料、
        #    outcome 列出还在跑的投递、interview 列出约了面试的）——
        #    也正是站在这一页的人最可能想要的那个动作。
        #
        # 带参数的写法留在「能敲哪些命令」那张表的「怎么敲（举例）」列里，
        # 以及「下一步」那一条（它会把真实的公司名/链接填进去）。
        "pipeline": [
            {"step": 1, "label": "搜到职位", "count": len(seen),
             "does": "按你资料里的目标岗位和城市，去各平台搜一轮新岗",
             "cmd": "/job-scrape"},
            # `waiting`：**还在排队等着评的**。「搜到 2638 → 打过分 2450」
            # 并排画着，中间那 188 从来没被点名，而它也不全是待办（6 个是
            # 已下线的死岗，判据见 `doctor.n_waiting`）。同一时刻面板正说
            # 库存见底 —— 没评的那批里可能就有能投的。
            # **有才给**：正常抓完就自动评了，这个键平时不该出现。
            {"step": 2, "label": "打过分", "count": n_ranked,
             **({"waiting": _n_wait} if _n_wait else {}),
             # 光有个数说不出「这批是会烂的」——判据与实测见
             # `doctor.waiting_age`。**有旧的才给这个字段**，
             # 面板照它决定要不要多印一句。
             **({"waitingNote": _wait_note} if _wait_note else {}),
             "does": "给搜到的岗批量打分排序，能投的会进上面的名单",
             "cmd": "/job-rank"},
            {"step": 3, "label": "材料就绪", "count": n_mat,
             "does": "给想投的岗出评估和打招呼话术",
             "cmd": "/job-apply"},
            # `parked` / `parkedNote`：**有才给**（同上面 `waiting` 那两个键）。
            # 一个都不在搁置区时这两行不该占地方。
            {"step": 4, "label": "已投递", "count": n_sent,
             **({"parked": n_sent_parked, "parkedNote": _sent_note}
                if n_sent_parked and _sent_note else {}),
             "does": "投递在招聘网站上做；投完回来记一笔，后面的跟进和备面都从它长出来",
             "cmd": "/job-outcome"},
            # 曾经写死 0。于是流水线最后一格永远是零，而 next_step 的第一条分支
            # （`interviewing > 0` → 「有面试了，去备面」）在网页版**永远触发不到**
            # ——一段谁也走不到的死代码。单页面板那边一直是真算的，两边又不一致。
            {"step": 5, "label": "面试中", "count": n_intv,
             "does": "约到面试就备面，它会按这家公司出题并陪你练",
             "cmd": "/job-interview"},
        ],
        "jobs": jobs,
    }
    # ── 基简历本身 ──
    # 面板原来只碰简历两次：「市场怎么读你的简历」（从评估语料反推，不含简历内容）
    # 和各岗的「打开定制简历 PDF」（那是某次投递的定制版，还藏在展开的详情里）。
    # **基简历本身、它的审核报告、它编译出来的 PDF，一个入口都没有**——而它才是
    # 所有投递共用的那一份，改一次影响之后每一次投递。
    src = ud / "resume" / "main.typ"
    if src.is_file():
        st = src.stat()
        base: dict = {
            "updated": _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
            # 章节顺序是 05-cv-templates.md 管的东西，列出来才看得出有没有被动过
            "sections": (secs := re.findall(
                r'#section\("([^"]+)"\)',
                src.read_text(encoding="utf-8", errors="replace"))),
            # 基线里有、这份简历里没有的（判据见 `missing_cv_sections`）。
            "missingSections": (miss := missing_cv_sections(secs)),
            # 缺的那几节，他在定制简历里是不是已经写过（判据见上）。
            "missingWrittenElsewhere": sections_written_elsewhere(user, miss),
        }
        pdf = ud / "resume" / "main.pdf"
        if pdf.is_file():
            # 复制到 web/public 下才打得开：file:// 与 http:// 两种模式都要能取到
            shutil.copy(pdf, PDF_DIR / "_base_resume.pdf")
            base["pdf"] = "pdf/_base_resume.pdf"
            base["pdfLocal"] = "../resume/main.pdf"
            # 留 1 秒容差：`typst compile` 常在改完 .typ 的同一秒内跑完，
            # 而有些文件系统的 mtime 精度就是秒——严格比较会把「刚编译好」
            # 判成「旧的」，弹一条让人白跑一趟的提示。反过来漏报 1 秒内的
            # 真陈旧几乎不可能（人改完文件不会在同一秒里既不编译又去看面板）。
            base["pdfStale"] = pdf.stat().st_mtime < st.st_mtime - 1
        audits = sorted((ud / "reports").glob("resume-audit-*.md")) \
            if (ud / "reports").is_dir() else []
        if audits:
            # **按文件名里的日期挑最新的，不按字典序挑。** `audits[-1]` 有两个真坑：
            #   · `resume-audit-final.md` 排在所有日期后面 → 面板那一格印出「final」，
            #     而下面 `stale` 拿它跟今天做**字符串**比较（`"2026-08-22" > "final"`
            #     是 False），于是那句「这条结论说的是上一版」的提醒**恒不触发** ——
            #     正是它被加进来要防的那件事；
            #   · 月份没补零时 `2026-9-1` 排在 `2026-10-01` 之后，九月压过十月。
            # 解析得出日期的才参与挑选；一个都解析不出时退回原来的行为，
            # 至少还印得出点什么。
            last = max(_dated_audits(audits))[1] if _dated_audits(audits) else audits[-1]
            _aday = _audit_day(last)
            # 上屏用补零之后的规范写法：`2026-9-1` 和 `2026-09-01` 是同一天，
            # 印成两个样子会让人以为是两份报告。
            _adate = _aday.isoformat() if _aday else last.stem.replace("resume-audit-", "")
            # **审阅结论也会过期，而且比 PDF 过期更要紧。**
            # 上面已经算了 `pdfStale`（PDF 比 .typ 旧），却没算这一个 ——
            # 而审阅给的是一句**决定性的结论**（「可以直接投，没有必须处理的问题」）。
            # 实测（2026-08-21）：审于 08-01，而简历 08-12 改过 ——
            # 面板照样把那句话当现在时印出来，说的却是上一版。
            #
            # 只比到「天」：审阅报告的日期来自文件名，本来就只有天。
            # 同一天改的不算陈旧 —— 那多半正是照着报告在改。
            try:
                _amtime = _dt.date.fromtimestamp(st.st_mtime).isoformat()
            except (OSError, ValueError):
                _amtime = ""
            base["audit"] = {
                "date": _adate,
                "count": len(audits),
                # 只取结论段，不把整份报告塞进 data.json——那会让它膨胀且两处飘
                "verdict": _audit_verdict(last),
                "stale": bool(_amtime and _adate and _amtime > _adate),
                "resumeChangedOn": _amtime,
            }
        # 资料里没填、而七道硬门要用的取值。**放在这一块**是因为它和简历
        # 是同一类东西：都是「你手上的材料够不够」，而不是某一个岗的事。
        # 主简历正文里踩了 `03` 的那几句。**和「少一节」并排**：
        # 都是「你手上这一份还差什么」，而且都是改一次、之后每一次
        # 投递都受益（定制版下次重出时跟着干净）。判据见
        # `base_resume_style`。
        _sw = base_resume_style(ud / "resume" / "main.pdf")
        if _sw:
            base["styleWarn"] = _sw
        cand = ud / "profile" / "candidate.md"
        if cand.is_file():
            base["gateInputsMissing"] = [
                {"field": f, "gate": g} for f, g in unfilled_gate_inputs(
                    cand.read_text(encoding="utf-8", errors="replace"))]
        payload["baseResume"] = base

    insight = resume_insight(user, seen, details_dir,
                             applied_urls={_cli.norm_url(r.get('source') or '')
                                           for r in trows if r.get('source')})
    if insight:
        payload["resumeInsight"] = insight
        ss = insight["sweetSpot"]
        print(f"  简历市场反馈：行业对口 {ss['count']}/{ss['total']} 个岗"
              f" · 专业能力中位 {insight['medianStack']} / 行业经验中位 {insight['medianDomain']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "data.json"
    # 原子写：先写临时文件再 os.replace。serve.py 的 GET 在锁外读这个文件，
    # 直接 write_text（截断后重写）会让并发的读拿到半截 JSON。
    # 走 `_cli.atomic_write`，别自己拼一个：它的临时名带 pid/tid（两个导出并发
    # 时不会撞同一个 .tmp），replace 还带退避重试（Windows 上并发的 GET 持着读
    # 句柄会让 os.replace 抛 PermissionError）。这里原来是固定名 + 裸 replace，
    # 正好把 atomic_write 存在的两个理由各踩一遍。
    _cli.atomic_write(out, json.dumps(payload, ensure_ascii=False, indent=1))

    # 印**实际写到哪**，不要印写死的字面路径。测试会把 OUT_DIR 重定向到临时目录，
    # 而写死的那行照样印 `web/public/data.json`——看起来像是把真实数据覆盖成了
    # 两条样本，虚惊一场。同一类毛病：**把假信息当事实显示**。
    try:
        shown = out.relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(out)          # 重定向到仓库外时给绝对路径
    print(f"已导出 {shown}（用户：{user}）")
    if orphans:
        # 静默丢弃会让人以为「材料没生成」，实际是链接对不上——必须说出来
        print(f"  注意：{len(orphans)} 个投递目录没有职位链接，材料接不上："
              f"{'、'.join(orphans)}")
    print(f"  职位 {len(jobs)} 个（打过分的）· 带材料 {n_mat} 个 · 复制简历 PDF {n_pdf} 份")
    print("  这个目录已 gitignore —— 里面是你的真实资料，不会进版本库")
    # 指向 serve.py 而不是 vite preview：只有前者能让页面上的「不投」真正落盘。
    #
    # **被别的工具调用时不印这句。** `serve.py` 自动重导时会调这里，而那时服务
    # 已经在跑了——再叫人去起一遍是岔路。
    if show_next_step:
        print("  下一步：cd web && npm install && npm run build "
              "&& cd .. && python tools/serve.py")
    return 0


if __name__ == "__main__":
    # 显式传 sys.argv：`main(argv=None)` 的语义是「没有参数」，不是「去偷 sys.argv」。
    # 这样 serve.py 在同进程里调 main([...]) 时不会撞上服务器自己的参数。
    sys.exit(main(sys.argv[1:]))
