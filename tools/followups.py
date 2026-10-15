#!/usr/bin/env python3
"""哪些投递该催了：安静天数、已跟进次数、终结状态，一次算清。

## 为什么要有这个文件

`outcome.md` 的 Step 2b 用一整段规定了催进度的判定：

> 状态不是终结态、距 `date`（或 `notes` 里最后一个 `followed up` 标记，若有）
> 已过阈值、且已记录的跟进**少于两次**。日期要防御性解析——解析不了的行**跳过
> 并说明**，不要猜。

三条规则、两个日期来源、一个上限，全靠每次现算。本仓库已经在同一件事上栽过：
`fetch_details.py` 的「撞限流就停」原来也是临时写的，写错一次就把 13 个 URL 全发了
出去。**判定逻辑不能靠每次现写。**

而且这里错了是静默的：少算几天就不催（机会窗口过去了），多算几天就催早了
（显得急躁），把已跟进 2 次的算成 1 次就会催第三遍——`outcome.md` 明确禁止的事。

## 用法

    python tools/followups.py                 # 列出该催的（默认 10 天）
    python tools/followups.py --days 14
    python tools/followups.py --all           # 连不该催的一起列，附不催的原因

只读，不写盘。要写 `followed up` 标记由 `/job-outcome` 的 Step 2b 自己做——
这里只回答「该催谁」。

零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

#: 终结态从状态机的家里取，不另抄——抄第二份的下场见 `tracker.FINAL_STATUSES`
#: 上面的注释（`build_dashboard` 那份就漏了 `no_response`）。
#: `interview`/`offer` 不在此列——流程还在走，该催照催。
from tracker import FINAL_STATUSES, channel_of  # noqa: E402

#: 最多两次。`job-outcome.md` 第 8 条的原话：「每次投递最多跟进两次。第二次跟进
#: 仍然没动静之后，**诚实的做法是把结果记下来，不是接着磨。**」
#:
#: ⚠️ **这里原来括的是一句转述，不是原话** —— 意思一样、字不一样，而它用了
#: 引号。2026-08-23 有人照着它去 `job-outcome.md` 里搜，**一个字都搜不到**，
#: 于是无从判断这个 2 到底还成不成立。引号里要么放原话，要么别用引号。
MAX_FOLLOWUPS = 2

#: 投出去多少天没动静就算「该催了 / 大概率没戏」。
#: **这是全仓库唯一的定义**——面板的「超过十天没动静可以催一次」、
#: 投后统计的「大概率没戏」都以它为准。
#:
#: > 2026-08-13 与 08-23 两次实测，同一件事上有过三个数：这里 10、
#: > 投后统计写死 14、`job-gmail-sync.md` 写 30。三处各说各的，用户看面板说
#: > 「该催了」、看统计说「还在等」。要改就改这里，别在别处另写一个。
#: >
#: > **而「唯一」这个词当时是个愿望，不是事实**：统计那处的 14 改了，
#: > `job-gmail-sync.md` 那个 30 又活了十天。2026-08-23 实测代价：
#: > 那一步按 30 天判「该跟进了」，而活动用户 85 笔投递里 **75 笔安静了
#: > 10-29 天、0 笔满 30 天** —— 同一时刻，面板说这 75 个该催，
#: > 那条命令一个都不提。
#: >
#: > 教训不是「再喊一次唯一」，是**让别处引不到数**：文档里要写就写
#: > 「按静默线（`followups.QUIET_DAYS`）」并注明「别在这里另定一个数」，
#: > 像 `job-html-report.md` 那条一样。`test_one_silence_line.py` 现在
#: > 扫所有工作流，出现第二个数就红。
QUIET_DAYS = 10

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日")


def parse_date(s: str):
    """宽进地解析日期；解析不了返回 None —— **不猜**。

    真实 tracker 是人手填的，`2026-07-15`、`2026/07/12` 都出现过。但「宽进」到
    此为止：拿不准的行要如实报出来让用户自己补，而不是估一个日期继续算——
    催早了催晚了都由这个估值造成，用户还看不出是估的。
    """
    s = (s or "").strip()
    if not s:
        return None
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def followup_dates(notes: str) -> list:
    """`notes` 里全部 `followed up YYYY-MM-DD` 标记，按时间排序。"""
    out = [parse_date(m) for m in
           re.findall(r"followed up\s+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", notes or "")]
    return sorted(d for d in out if d)


def assess(row: dict, today: date, threshold: int, agency: dict | None = None,
           scores: dict | None = None) -> dict:
    """一行投递记录 → 该不该催、安静几天、为什么不催。"""
    status = (row.get("status") or "").strip().lower()
    notes = row.get("notes") or ""
    fups = followup_dates(notes)
    applied = parse_date(row.get("date") or "")

    rec = {"company": (row.get("company") or "").strip(),
           "role": (row.get("role") or "").strip(),
           "status": status, "n_followups": len(fups),
           # 渠道**推得出来就推**。这一行本来就想显示它（下面拼 `· {channel}`），
           # 可 `channel` 那一列历来全空 —— 实测 85 条投递 85 行是空的，
           # 于是这个位置一次都没出现过内容。而它在这里不是装饰：
           # **能不能催，取决于在哪个网站投的** —— BOSS 是聊天窗口，随时能追一句；
           # 猎聘纯网申多半没有对话入口，只能等；智联走站内信。
           # 不知道渠道，这份「该催的 53 个」就没法照着做。
           "channel": channel_of(row),
           "contact": (row.get("contact_person") or "").strip(),
           # 猎头代招 / 企业直招 / 对不上（None，**不猜**）。判据见 `agency_map`。
           "agency": (agency or {}).get((row.get("source") or "").strip()),
           # 排序用。取不到给 None —— 排序时沉底，不当成 0 分
           # （0 分和「不知道」在屏幕上是两件事）。
           "score": (scores or {}).get((row.get("source") or "").strip()),
           "quiet_days": None, "due": False, "why_not": ""}

    if status in FINAL_STATUSES:
        rec["why_not"] = f"已终结（{status}）"
        return rec
    if applied is None:
        # 说出来而不是猜——这条规则 outcome.md 明确写了
        rec["why_not"] = "投递日期解析不了，无法计算安静天数（请补上日期）"
        return rec
    if len(fups) >= MAX_FOLLOWUPS:
        rec["quiet_days"] = (today - fups[-1]).days
        rec["why_not"] = (f"已跟进 {len(fups)} 次，到上限。"
                          "该记录结果了（/job-outcome <公司>），不是催第三遍")
        return rec

    # 安静天数从**最后一次动作**算起：跟进过就从跟进日，没跟进过才从投递日。
    # 从投递日算是常见的错——跟进过一次之后它会立刻又判「该催」。
    since = fups[-1] if fups else applied
    rec["quiet_days"] = (today - since).days
    if rec["quiet_days"] < threshold:
        rec["why_not"] = (f"距上次{'跟进' if fups else '投递'}才 {rec['quiet_days']} 天，"
                          f"不到 {threshold} 天")
        return rec
    rec["due"] = True
    return rec


def agency_map(user: str) -> dict:
    """`投递链接 → 猎头代招 / 企业直招 / 没判过`。取不到就返回空字典 —— **不猜**。

    ## 为什么这份清单必须按这个分组

    「该催的 53 个」平铺成一列，是一份**没法照着做的清单**：催猎头顾问和催企业 HR
    是两件事，对象不同、能不能催也不同。

    - **猎头代招**：顾问有推荐费驱动，会回你，而且答得上「岗位还在不在」
      「用人方那边什么反馈」—— 催他是这批里性价比最高的动作。
    - **企业直招**：BOSS 是聊天框，随时能追一句；猎聘/智联走站内信，
      多半没有对话入口。真正能改变结果的是**找人内推**，而那只对具名公司成立。

    台账的 `source` 列存的就是原始链接，和库里的 `url` 精确对得上
    （实测活动用户 85 行 85 中），不必模糊匹配。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    # **判据走 `_cli.via_headhunter`，不要在这里读字段。**
    # 这里原来写的是 `bool(e.get("isHeadhunter"))`，两处错：
    #   1. 不看 `recruiter` —— 招聘方名字里带「猎头 / 人力资源 / 人才 / 咨询」
    #      的岗，那边判 True，这边判 False；
    #   2. **把「没判过」塌成「直招」** —— 抓取器没给这个字段时（实测 2026-08-23
    #      全库 2630 个岗里 66 个，集中在浏览器抓的 BOSS / 智联 / 前程），
    #      正本返回 `None`，这里返回 `False`。
    # 后者正是 `via_headhunter` 自己的文档点名的害处：
    # 「把没判过的岗算进直招，等于让他去一个可能是猎头挂的岗上找人内推」——
    # 而这份清单的直招那一组说的恰恰就是「具名的公司还能同时找人内推」。
    # 实测 2026-08-23 他 85 条投递里 **5 条**受影响。
    return {e["url"]: _cli.via_headhunter(e)
            for e in _cli.seen_of(store).values()
            if isinstance(e, dict) and e.get("url")}


def score_map(user: str) -> dict:
    """`投递链接 → 评分`。取不到就返回空字典 —— 不猜。

    ## 为什么这份清单要能排序

    「该催的 53 个」按天数平铺，等于**没有顺序** —— 一天做不完 53 条
    （每条 60-120 字、逐条写，不许套模板，见 `job-outcome.md`），
    而用户没有任何依据决定先做哪几条。

    分数是现成的（实测 85 条投递 85 条取得到，50-82 分）。
    **不给「一次做几个」定数** —— 那取决于他今天有多少时间，工具不知道；
    但从上往下做至少是对的顺序。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {e["url"]: e["rank_score"]
            for e in _cli.seen_of(store).values()
            if isinstance(e, dict) and e.get("url")
            and isinstance(e.get("rank_score"), int)}


def load_rows(user: str) -> list:
    """**读法走 `_cli.read_tracker_rows`，别在这儿再开一份。**

    原来这里自己 `DictReader`：BOM 接住了，`UnicodeDecodeError` 没接 ——
    台账被 Excel 存成 GBK 时（中文 Windows 上是默认行为），13 个工具里
    只有这一条甩栈回溯（2026-09-01 实测）。`export_web_data` 的调用点
    早就写着「不要在这里内联一份 DictReader」。
    """
    p = ROOT / "users" / user / "job_search_tracker.csv"
    return [r for r in _cli.read_tracker_rows(p)
            if (r.get("company") or "").strip()]


def cluster_key(company: str) -> str:
    """把同一家公司的多笔投递归到一起用的键。**脱敏串归不了，返回空串。**

    催进度是**按人**发的：同一家公司投了 5 个岗，发 5 条各问各的，
    对面看到的是同一个人在同一个 ATS 里刷屏。一条里把几个岗一次问全才是对的。
    实测活动用户 85 笔投递里 23 笔落在 9 家公司（最多的一家 5 笔），
    而这份清单按分数倒序平铺，那 5 笔散在五个地方。

    **但脱敏串不能当公司身份。** 猎聘给猎头岗打的「某知名公司」在库里出现
    158 次 —— 那是 158 家不同的用人方，归到一起就是把八竿子打不着的岗
    说成「同一家」，然后建议他合并成一条去催。同一族的前科：
    `build_dashboard.match_tracker` 曾经拿它做模糊匹配，一条手工记的投递
    吃掉库里 6 个岗（判据现在共用 `_cli.is_anonymous_employer`）。
    """
    c = (company or "").strip()
    return "" if not c or _cli.is_anonymous_employer(c) else c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="列出该催进度的投递。只读，不写盘。")
    ap.add_argument("--days", type=int, default=QUIET_DAYS,
                    help="安静多少天算该催（默认 10，与 outcome.md 的阈值一致）")
    ap.add_argument("--all", action="store_true", help="连不该催的一起列，附原因")
    ap.add_argument("--today", help="覆盖今天的日期（测试用，YYYY-MM-DD）")
    ap.add_argument("--user", help=_cli.HELP_USER)
    args = ap.parse_args(argv)

    # 不判存在就直接 read_text 会在**全新 clone 上**抛 FileNotFoundError 栈回溯
    # ——新用户敲错顺序是常态，第一次撞见的不该是 traceback。
    user = _cli.pick_user(args.user or "", root=ROOT)
    today = _cli.parse_today(args.today) or date.today()
    rows = load_rows(user)
    if not rows:
        print(f"{user} 还没有投递记录 —— 投出去之后跑 /job-outcome <公司> 记一笔")
        return 0

    ag, sc = agency_map(user), score_map(user)
    got = [assess(r, today, args.days, ag, sc) for r in rows]
    due = [g for g in got if g["due"]]
    print(f"投递记录 {len(rows)} 条（用户：{user}，阈值 {args.days} 天，"
          f"今天 {today.isoformat()}）\n")
    if due:
        # **按「催谁」分组，不平铺。** 判据见 `agency_map` 的文档：
        # 催猎头顾问和催企业 HR 是两件事，一列 53 行没法照着做。
        groups = [
            (True, "猎头代招 —— 催顾问",
             "顾问有推荐费驱动，多半会回，还能问出「岗位还在不在」"
             "「用人方那边什么反馈」。这批性价比最高，先做。"
             "组内按分数从高到低排 —— 一天做不完就从上往下做。"),
            (False, "企业直招 —— 催 HR",
             "BOSS 是聊天框，随时能追一句；猎聘/智联走站内信，"
             "多半没有对话入口。具名的公司还能同时找人内推。"),
            # **两种「不知道」合成一组：库里没有它，和库里有、但没判过。**
            # 理由不同，该做的事完全一样（按平台形态自己判断），
            # 而且都不能塞进直招 —— 那一组的建议是「找人内推」，
            # 对一个可能是猎头挂的岗做这件事是白费力气。
            (None, "拿不准是猎头还是直招 —— 按平台形态自己判断",
             "两种情况：这几条在职位库里找不到对应记录（手填的、或岗位已删）；"
             "或者库里有、但抓取器没给「是不是猎头」这个字段。"
             # 强调不能用 `**`：这一行是**印到终端上的**，
             # markdown 标记会连着星号一起显示（`test_display_wording` 盯这条）。
             "没判过不等于判过是「不是」，所以不并进直招那一组。"),
        ]
        print(f"该催的 {len(due)} 个：")
        for flag, title, why in groups:
            batch = [g for g in due if g["agency"] is flag]
            if not batch:
                continue
            # **组内按分数倒序** —— 一天做不完 53 条，从上往下做至少是对的顺序。
            # 取不到分数的沉底（`-1`），不装作它是 0 分。
            #
            # **同一家公司的几笔排在一起**，位置由这家最高的那一笔决定 ——
            # 分数优先级一点没变，只是把本来散在五处的同公司行收拢，让他一眼
            # 看出该合并成一条催（判据见 `cluster_key`，脱敏串不并）。
            # 归不了组的（脱敏、空公司名）各自成组，行为和原来完全一样。
            def _sc(g):
                return g["score"] if g["score"] is not None else -1

            def _k(g, i):
                # 键做成元组：归得了组的用 `(公司名, 平台, 0)`，归不了的用
                # `("", "", i)` 各自独一份。**不要用哨兵字符**（`\x00`、`#` 之类）
                # ——公司名是自由文本，任何一个可打印前缀都可能真的撞上。
                #
                # **平台必须进键。** 只按公司名归，下面那句「催一条把几个岗一次
                # 问全，别发 N 条」就会落在**两个不同的聊天框**上：猎聘和 BOSS
                # 是两个 app、两个对话、多半是两个人，一条消息物理上发不到两边。
                # 实测活动用户 2026-08-23：4 家有多笔投递的公司里 **3 家跨平台**
                # （一家 猎聘 4 笔+智联 1 笔，另两家各是 猎聘 1 笔+BOSS 1 笔），
                # 覆盖 11 笔里的 9 笔 —— 那条建议对它们做不到。
                # 猎头/直招那一维已经由分组本身隔开了（见下面那条注释）。
                c = cluster_key(g["company"])
                ch = (g["channel"] or "").strip()
                return (c, ch, 0) if c else ("", "", i + 1)

            keys = {id(g): _k(g, i) for i, g in enumerate(batch)}
            best, size = {}, {}
            for g in batch:
                k = keys[id(g)]
                best[k] = max(best.get(k, -1), _sc(g))
                size[k] = size.get(k, 0) + 1
            batch.sort(key=lambda g: (-best[keys[id(g)]], keys[id(g)], -_sc(g)))
            seen_key = set()
            print(f"\n  【{title}】{len(batch)} 个")
            print(f"  {why}")
            for g in batch:
                fu = f"，已跟进 {g['n_followups']} 次" if g["n_followups"] else ""
                # **渠道为空时不要留那个分隔符。** 面板按钮写的行不填 `channel`
                # （实测 83 行里全空），无条件拼 ` · {channel}` 的结果是每一行都以
                # 「安静 11 天 · 」收尾——一个吊在末尾、后面什么都没有的点。
                # 与 `doctor.py` 那个吊着的「或者」同一族：
                # **分隔符要跟着它分隔的东西走。**
                ch = f" · {g['channel']}" if (g["channel"] or "").strip() else ""
                # 分数取不到时留空，不印「? 分」——那一列宽度固定，空着就是空着。
                sd = f"{g['score']:>3} 分" if g["score"] is not None else "     "
                # **行首那个点号留着。** 取不到分数的行没有它就是一片空白，
                # 而且 `test_followups` 靠它定位行（查「渠道为空时有没有吊着的
                # 分隔符」）—— 换个标记等于把那道守卫悄悄拆了。
                print(f"    · {sd}  {g['company'][:18]:<20} {g['role'][:20]:<22} "
                      f"安静 {g['quiet_days']} 天{fu}{ch}")
                # 一家公司只说一次，说在它第一行下面。**这一组里几笔就说几笔** ——
                # 猎头挂的和企业直招是两个联系人，跨组合并会让他去跟猎头问
                # 一个他其实是直投的岗。
                k = keys[id(g)]
                if k not in seen_key:
                    if size[k] > 1:
                        where = f"在{k[1]}上" if k[1] else "在这一组里"
                        print(f"      └ 这家你{where}投了 {size[k]} 个岗——"
                              f"催一条把几个岗一次问全，别发 {size[k]} 条")
                    # **同一家公司走了两条渠道，要说一句。** 这不只是「别合并」：
                    # 国内投递里同一家既被猎头报备、自己又直投过，用人方那边会
                    # 撞成重复候选人，谁来推、推荐费算谁的都要掰扯，处理不好
                    # 两条都卡住。这里只报事实，不替他决定先撤哪一条。
                    other = sorted({ch for (co, ch, _z) in size
                                    if co and co == k[0] and ch != k[1]})
                    if other:
                        print(f"      └ 这家你还在{'、'.join(other)}上投过——"
                              f"两边是两个联系人，各催各的；"
                              f"同一家走两条渠道，用人方那边可能撞成重复候选人")
                seen_key.add(k)
    else:
        print("没有到催进度时机的投递。")

    # 日期解析不了的**永远要报**，不管加不加 --all：它是数据缺陷，不是「不该催」
    broken = [g for g in got if "解析不了" in g["why_not"]]
    if broken:
        print(f"\n⚠ {len(broken)} 条日期解析不了，未参与判定（不猜，请补上日期）：")
        for g in broken:
            print(f"  · {g['company'][:18]:<20} {g['role'][:20]}")

    if args.all:
        rest = [g for g in got if not g["due"] and g not in broken]
        if rest:
            print(f"\n不催的 {len(rest)} 个及原因：")
            for g in rest:
                print(f"  · {g['company'][:18]:<20} {g['role'][:18]:<20} {g['why_not']}")
    elif not due:
        print("（加 --all 看每一条为什么不催）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
