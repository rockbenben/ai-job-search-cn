#!/usr/bin/env python3
"""拿**真实职位库**当测试语料，审这条流水线自己的毛病。

## 为什么要它

单元测试验的是「代码按写的那样跑」，而这里要抓的是另一类问题——**代码跑得好好的，
但规则本身漏了**：

- 一个字段有两个消费者、零个生产者（那条规则等于从没跑过）；
- 生产方写 `validThrough`、消费方读 `deadline`（**名字不一样，永远接不上**）；
- 文档的字段表打着 ✅，实测覆盖率 0%；
- 文档写了合理性校验（「薪数落在 12–24」），但没有任何地方执行它。

这些用构造数据测不出来——**只有真实语料会暴露它们**。2026-08-19 第一次跑就在
2638 个岗上抓出 5 类，其中 `deadline` 那条让 `/job-rank` 的「7 天内标 🔥、过期转
expired」从上线起就没生效过。

## 用法

    python tools/audit_pipeline.py            # 全部检查
    python tools/audit_pipeline.py --json     # 机器可读，给测试用

退出码：有 error 级发现返回 1，只有 warn 返回 0。
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
#: 剥话术尾部自检元数据的正本在面板那一侧。同一份文本两个读法就是两套标准 ——
#: 这里此前自己切一遍、漏了剥，把 3 份合规的开场白误报成「超 200 字」。
from build_dashboard import (_strip_wordcount,  # noqa: E402
                             parse_evaluation)
from query_yield import PORTAL_ALIAS, PORTALS  # noqa: E402
import scoring as _sc  # noqa: E402  评分里确定性那几样的正本

#: 三样词表的正本都在 `_cli`（2026-08-20 收拢——来源族此前和 test_verdict_cap
#: 各写一份，**已经分叉过**：这边认「批量」、那边不认，同一条数据两个守卫结论相反）。
#: 从 `outreach.md` 里认出「这份材料是哪个岗的」。**归档接回职位列表就靠这一行**
#: （`job-apply.md`：「`- 职位链接：<url>` 一行都不能省」）。
#:
#: 本文件里这条原来抄了 5 遍，而且**已经漂了一格**：4 处写 `职位链接[：:]`、
#: 1 处写 `职位链接\s*[：:]`（多认冒号前的空格）。实测 2026-08-27 的 253 份
#: `outreach.md` 里没有一份踩到那格差别 —— 也就是说它不会自己显形，
#: 只会在某天某份归档多打一个空格时，让「同一个仓库里的两处检查」给出两个答案。
#: 取宽的那个当正本：归档是人和 AI 写的，解析器宁可多认。
#:
#: 收尾一次最多印几条「要改」的命令。再多就是一屏命令，读的人不会
#: 一条条敲；剩下的用一条命令拿到，不做沉默截断。
_REWRITE_SHOWN = 12

#: `posting.md` 那边用的是另一个字样（`原始链接：`，见 `job-outcome.md` Step 3），
#: 别拿这条去读它。
#: 正本在 `_cli.LINK_LINE`，这里只留别名（本模块十几处在用）。
LINK_LINE = _cli.LINK_LINE

VERDICTS = set(_cli.VERDICTS)
MONTHS_LO, MONTHS_HI = _cli.SALARY_MONTHS_SANE
SOURCE_FAMILIES = _cli.SOURCE_FAMILIES


def load(user: str):
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        raise SystemExit(_cli.no_store(p))
    data, _ = _cli.load_json_stamped(p)
    seen = _cli.seen_of(data)
    _cli.stop_on_unreadable_rows(seen, p)
    details = {}
    for f in glob.glob(str(ROOT / "users" / user / "job_scraper" / "details" / "*.json")):
        try:
            j = json.loads(Path(f).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if j.get("url"):
            details[j["url"]] = j
    return seen, details


def _site(e: dict) -> str:
    return PORTAL_ALIAS.get(e.get("portal") or "", "?")


def check_orphan_consumers(seen, details) -> list:
    """**有人读、没人写的字段。** 那条规则等于从没跑过。

    只查那些在 `workflows/` 里被当成数据字段引用的名字，逐个对着真实库数它出现几次。
    """
    import jd_store as st
    out = []
    wf = " ".join((ROOT / "workflows" / f).read_text(encoding="utf-8")
                  for f in ("job-rank.md", "job-apply.md", "job-scrape.md"))
    watched = ["deadline", "employmentType", "recruiter", "benefits",
               "validThrough", "headcount", "datePosted"]
    for name in watched:
        if name not in wf:
            continue
        n = sum(1 for e in seen.values() if e.get(name))
        nd = sum(1 for j in details.values() if j.get(name))
        if n == 0 and nd == 0:
            # **区分两种「没有」**：链路断了（我们的 bug，要修）vs 源头不给
            # （平台没这个数据，不是 bug，但要记着，别让读它的规则假装在跑）。
            # 一个永远红的审计等于没有审计——它会被当成背景噪音略过。
            # 改名表的**键和值都算接通**：键是详情里的名字、值是职位库里的名字，
            # 工作流引用的可能是任一侧（`job-scrape.md` 写 `datePosted`，
            # 而库里叫 `date`）。只查一侧会把已经接好的链路报成断的。
            wired = (name in st.MERGE_FIELDS
                     or name in st.MERGE_RENAME
                     or name in st.MERGE_RENAME.values())
            out.append(("warn" if wired else "error",
                        "字段有消费者没生产者（链路已通，等源头）" if wired
                        else "字段有消费者没生产者（链路是断的）",
                        f"`{name}` 在工作流里被引用，但职位库 {len(seen)} 个岗、"
                        f"详情库 {len(details)} 份里一个有值的都没有。"
                        + ("回填链路已经接通，抓取器一补上就能用；在那之前，"
                           "读它的规则实际是空转，别当它在生效。" if wired else
                           "而且 `jd_store` 也不回填它——就算抓到了也流不进职位库。")))
        elif n == 0 and nd:
            out.append(("error", "详情库有、职位库没有",
                        f"`{name}` 详情库里 {nd} 份有值，职位库 0 个——"
                        f"`jd_store.MERGE_FIELDS` 没带它，回填这一跳断了"))
    out.extend(_broken_hops(seen, details))
    return out


#: 抓取/存储自己的元数据，不是岗位字段 —— 搬进职位库没有意义。
_HOP_META = {"id", "url", "title", "company", "description", "portal",
             "fetched_by", "fetched_date", "capture", "captured", "note",
             "detail_title", "source", "detailFrom", "来源"}
#: 职位库自己的字段（评分、状态、发现记录）。详情里出现是导入残留，不是断链。
_HOP_OWN = {"first_seen", "fit", "status", "found_by", "rank_date",
            "rank_verdict", "rank_breakdown", "rank_score"}


def _broken_hops(seen, details) -> list:
    """**名单算出来，不手写。**

    上面那个 `watched` 是一张手写名单，而这个坑犯过两次，**两次的字段都不在
    那张名单上**：

        recruiterTitle    详情库 31 份有值、职位库 0 条   （2026-08-27 撞见）
        recruiterSurname  详情库  6 份有值、职位库 0 条   （2026-08-30 撞见）

    两次都是靠人顺手比对才发现的 —— 一次是查「对面是 HR 还是用人方」，
    一次是查「自检让用户去取的字段为什么是空的」。
    **手写名单只盖得住已经想到的字段**，而断链恰恰发生在没想到的那些上。

    判据改成算：详情库里有真值、职位库里 0 条、回填表没带、而且**有人读**
    （字段名出现在 `workflows/` `tools/` `web/src` 任一处）。最后一条是这张表
    自己的准入规矩 —— 没有消费者的字段搬过去只是多一列噪音
    （`fetched_by` / `fetched_date` 详情库各 151 份有值，零消费者，不报）。

    实测 2026-08-30：这样算出来**今天 0 条**（没有误报），
    而把那两个字段从回填表里拿掉，两个都抓得到。
    """
    import jd_store as st          # 同外层那条检查：本模块不在顶上 import 它
    consumers = []
    for d, pats in (("workflows", ("*.md",)), ("tools", ("*.py",)),
                    ("web/src", ("*.ts", "*.tsx"))):
        base = ROOT / d
        if base.is_dir():
            for pat in pats:
                consumers += [f for f in base.rglob(pat)
                              if "__pycache__" not in f.parts]
    text = "\n".join(f.read_text(encoding="utf-8", errors="replace")
                     for f in consumers)
    carried = (set(st.MERGE_FIELDS) | set(st.MERGE_RENAME)
               | set(st.MERGE_RENAME.values()))

    def _real(v) -> bool:
        return v not in (None, "", [], {}) and str(v).strip() != "None"

    det = collections.Counter()
    for j in details.values():
        if isinstance(j, dict):
            for k, v in j.items():
                if _real(v):
                    det[k] += 1
    in_seen = {k for e in seen.values() if isinstance(e, dict)
               for k, v in e.items() if _real(v)}

    out = []
    for k, nd in det.most_common():
        if (k in _HOP_META or k in _HOP_OWN or k in carried
                or k in in_seen or k not in text):
            continue
        out.append(("error", "详情库有、职位库没有",
                    f"`{k}` 详情库里 {nd} 份有值，职位库 0 条 —— "
                    f"`jd_store.MERGE_FIELDS` 没带它，回填这一跳断了。"
                    f"补它：把 `{k}` 加进 `jd_store.MERGE_FIELDS`，"
                    f"再跑 python tools/jd_store.py --merge --apply"))
    return out


def check_name_mismatch(seen, details) -> list:
    """**生产方与消费方用了不同的名字。** 抓得到也接不上。"""
    out = []
    pairs = [("validThrough", "deadline")]
    scrape = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
    rank = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
    import jd_store as st
    for produced, consumed in pairs:
        if produced in scrape and consumed in rank:
            resolved = (st.MERGE_RENAME.get(produced) == consumed
                        or produced in st.MERGE_FIELDS or consumed in st.MERGE_FIELDS)
            if not resolved:
                out.append(("error", "生产方与消费方名字不一致",
                            f"抓取侧写 `{produced}`（job-scrape.md），"
                            f"评分侧读 `{consumed}`（job-rank.md），"
                            f"而 `jd_store.MERGE_FIELDS` 两个都没有——"
                            f"中间没有任何一处把它们对上"))
    return out


def check_doc_claims_vs_reality(seen) -> list:
    """字段表标着能取，库里覆盖率却是 0 —— **盯的是这个差距，不是指控文档**。

    ## 措辞 2026-08-27 改过：它原来在冤枉一份诚实的文档

    这一条原来叫「文档说有、实测没有」，读起来像是文档写错了。而
    `cdp-portals.md` **自己就有一个 ⚠️ 框**在讲这件事，标题逐字是
    「『页面上有』不等于『库里有』。这张表说的是前者」，下面还列着一张
    0% 覆盖率的表（`recruiter` / `benefits` / `employmentType` /
    `deadline`），每一行都写了为什么。

    也就是说：**文档答的是「平台给不给」，这条检查答的是「我们取没取」**
    —— 两个问题，都答对了。指控它写错，比不报更坏：下一个人会去改一份
    本来正确的文档。

    ## 那它留着干什么

    盯**差距会不会合上**。抓取器哪天开始取这些字段，这一条就自己消失；
    在那之前它每轮提醒一次：`04` 的外包硬门还在靠标题关键词猜
    （`employmentType` 0.2%），薪资维还没把非现金部分算进去（`benefits`）。
    """
    out = []
    doc = ROOT / "workflows" / "reference" / "cdp-portals.md"
    if not doc.is_file():
        return out
    text = doc.read_text(encoding="utf-8")
    tot = collections.Counter(_site(e) for e in seen.values())
    for name in ("recruiter", "benefits"):
        if f"`{name}`" not in text:
            continue
        got = collections.Counter(_site(e) for e in seen.values() if e.get(name))
        dead = [s for s in PORTALS if tot[s] >= 20 and got[s] == 0]
        if len(dead) >= 2:
            out.append(("warn", "字段：能取到，但一直没取",
                        f"`{name}` 在 cdp-portals 的字段表里标着能取，"
                        f"而 {'、'.join(dead)} 实测落库覆盖率 0% —— "
                        f"这不是文档写错了：那份文档自己有一个 ⚠️ 框讲"
                        f"「页面上有不等于库里有」，还列着这几个字段的 0% 表。"
                        f"这一条盯的是差距会不会合上：抓取器开始取它，这条就自己消失"))
    return out


def check_salary_months_sane(seen) -> list:
    """**薪数超出 12–24。** 规则文档里有，没有任何地方执行。"""
    bad = []
    for e in seen.values():
        m = e.get("salaryMonths")
        if isinstance(m, int) and not (MONTHS_LO <= m <= MONTHS_HI):
            bad.append(f"{m}薪 · {e.get('salary')} · {(e.get('title') or '')[:26]}")
    if not bad:
        return []
    # 折算侧有没有把它挡住？挡住了就只是平台噪音（warn），没挡住才是真漏洞（error）。
    import export_web_data as ex
    guarded = (ex.annual_package("60-90k·30薪", 30) or {}).get("assumed12") is True
    tail = ("折算侧已按「解不通就当没写」退回 12 薪保守估，不会顶满薪资维。" if guarded
            else "折算侧没有挡 —— 年包会被算到离谱的量级并顶满薪资维（25% 权重）。")
    return [("warn" if guarded else "error", "薪数超出合理区间",
             f"{len(bad)} 个岗的 `salaryMonths` 不在 {MONTHS_LO}–{MONTHS_HI}"
             f"（平台原样给的）：\n      " + "\n      ".join(bad[:5])
             + "\n      " + tail)]


def check_verdict_vocabulary(seen) -> list:
    """判词必须落在五档（或硬门 FAIL / 不满足硬性条件族）。造新词下游就查不到表。"""
    bad = collections.Counter()
    for e in seen.values():
        v = _cli.strip_triage(e.get("rank_verdict"))
        if not v or v in VERDICTS:
            continue
        if v.startswith((*_cli.GATE_FAIL_PREFIXES, "已下线")):
            continue
        bad[v] += 1
    if not bad:
        return []
    return [("error", "结论不在词表里",
             f"{sum(bad.values())} 个岗的判词不是五档中文、也不是硬门族："
             f"{dict(bad.most_common(5))}")]


def check_source_families(seen) -> list:
    """判词依据的 `来源` 冒出新族 = 执行者临时造词，按来源分流的守卫会漏看。"""
    bad = collections.Counter()
    for e in seen.values():
        s = str((e.get("rank_breakdown") or {}).get("来源") or "")
        if s and not s.startswith(SOURCE_FAMILIES):
            bad[s[:28]] += 1
    if not bad:
        return []
    return [("warn", "结论来源冒出新族",
             f"这些 `来源` 不属于已知的 {SOURCE_FAMILIES}：{dict(bad.most_common(4))}")]


def check_scheme_twins(seen) -> list:
    """同一个岗以 http 和 https 各存一份 —— 查重漏了协议归一化。"""
    by = {}
    for e in seen.values():
        u = _cli.norm_url(e.get("url"))
        if u:
            by.setdefault((u, e.get("title") or ""), set()).add(e.get("url"))
    twins = [k for k, v in by.items() if len(v) > 1]
    if not twins:
        return []
    return [("error", "http/https 孪生条目",
             f"{len(twins)} 个岗被存了两份，只差协议：{[t[1][:22] for t in twins[:4]]}")]


def _also_missing_the_section(urls: set) -> int:
    """这批岗里，有几个的深评连「评分明细」那一节都没有。

    判据借 `missing_sections`（正本），不在这儿另写。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return 0
    dirs = dir_urls(user)
    n = 0
    for f in sorted(apps.glob("*/evaluation.md")):
        if _cli.norm_url(dirs.get(f.parent.name, "")) not in urls:
            continue
        gone = missing_sections(f.read_text(encoding="utf-8", errors="replace"))
        if gone and "评分明细" in gone:
            n += 1
    return n


def check_evaluations_are_dated(seen, details) -> list:
    """深评抬头那一行「- 评估日期：YYYY-MM-DD」写了没有。

    ## 规则在，没人验

    `04` 的输出格式里有这一行，旁边还有一整段说它为什么要紧：

    > 「评估日期」那一行不是装饰，是所有按批次看趋势的分析唯一的依据……
    > 审计每一条报的都是全库累计数，而那个数只会随产量涨。改完一条规则之后，
    > 能回答「它生效了没有」的只有「最近一批还犯不犯」—— 而那要按日期分组
    > 才看得出来。日期丢了，新加的规则就再也验不了。

    那段话还记着一次事故：3 份写了日期却没带 `- `，**当天新出的深评对每一个
    按日期分析的检查全部隐形**。

    **而验它的一处也没有**（2026-08-30 通读时发现）。

    ## 它还会漏掉写盘那道闸门

    `--sections` 按日期挑「这一批」，没日期的挑不出来 —— 除非把它们一律纳入
    （那一步同日改了）。实测全库 **1 份**没有这一行，而那 1 份正好缺小节：
    也就是说它此前**永远**补不上。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    urls = dir_urls(user)
    bad = []
    for f in sorted(apps.glob("*/evaluation.md")):
        # 硬门 FAIL 的那种文件按 04 本来就该短，但抬头那一行照样要写。
        if _eval_date(f.read_text(encoding="utf-8", errors="replace")):
            continue
        bad.append((urls.get(f.parent.name, ""), f.parent.name[:26]))
    if not bad:
        return []
    _live, tail = _cli.live_tail(user, seen, bad, verb="补")
    return [("warn", "深评没写评估日期",
             f"{len(bad)} 份深评的抬头缺「评估日期」那一行。"
             f"按批次看趋势的分析全靠它 —— 缺了这一行，那几份对每一条"
             f"「最近一批还犯不犯」的检查都是隐形的，写盘时那道逐份闸门"
             f"也挑不出它们。判据见 04 输出格式里那一段。{tail}")]


def check_basis_still_explains_the_number(seen) -> list:
    """`rank_breakdown["依据"]` 那段话，说的还是现在这个分吗。

    ## 为什么这条要在审计里

    判据本身长在 `writeback._basis_is_stale`（它是回写那一侧的写手，
    每轮收尾都跑），**这里不重写一份，直接借它**。

    要在这儿再报一次，是因为**收尾那个总数由这份审计出**：
    「下面这几条去重后是 N 个岗……一次补完」。而 2026-08-30 实测：
    `writeback` 报的「还能改的 10 个」里 **5 个不在那 105 里** ——
    也就是说那句「一次补完」当时是**不全的**。用户照它做完，
    还剩 5 个岗的依据在总览页上解释着别的数字。

    同一份收尾里两本账，是这个仓库反复栽的形状；这次的特别之处是
    **两本账各自都对**，错的是其中一本自称是总数。

    ## 它和 `writeback` 那句话不重复

    `writeback` 那句报的是**它这一轮刚写回的账**（顺带扫出库内残留）；
    这条报的是**现在还补得上的那几个**，并把它们计进收尾那个去重总数
    （准入判据是有没有调 `sendable_state`，见 `run()`）。
    """
    import writeback as _wb
    bad = []
    for v in seen.values():
        if not isinstance(v, dict):
            continue
        b = v.get("rank_breakdown") or {}
        if _wb._basis_is_stale(str(b.get("依据") or ""), b):
            bad.append((v.get("url") or "", (v.get("title") or "?")[:22]))
    if not bad:
        return []
    user = _cli.pick_user("", root=ROOT)
    _live, tail = _cli.live_tail(user, seen, bad, verb="改")
    return [("warn", "依据那段话说的不是现在这个分",
             f"{len(bad)} 个岗的「依据」还写着旧口径或旧数字 —— "
             f"那段字会显示在总览页上，用户读到的是在解释别的数字。"
             f"{tail}")]


def check_scored_without_dims(seen) -> list:
    """有分数却没有四维拆解 —— 分是哪来的无从复核。

    ## 它和「深评缺小节」不是两个问题

    实测活动用户 2026-08-30：这条报 11 个，而「深评缺小节」里
    「评分明细 11 份」—— **两边的交集是 11，两个方向的差集都是 0**。
    同一个缺陷的两个症状：那一次深评没出评分明细表，于是文件里没有那一节、
    回写进职位库的 `rank_breakdown` 里也没有那四维。

    所以这条**不给命令**，只报数并指过去。给了就是同一件事在收尾里出现两条
    可执行项，而读的人会以为要做两遍
    （`--actionable` 的判据是「有没有调 `sendable_state`」，不调就不进那一档
    —— 见 `run()`）。

    **两条检查都留着**：它们查的是两个存储（职位库 vs 深评文件），
    今天完全重合是**实测结果，不是保证**。哪天只有一边缺，
    下面那句自己就会说出来。
    """
    bad = [e for e in seen.values()
           if isinstance(e.get("rank_score"), int)
           and not str(e.get("rank_verdict") or "").startswith("硬门")
           and "技能与经验" not in (e.get("rank_breakdown") or {})]
    if not bad:
        return []
    urls = {_cli.norm_url(e.get("url") or "") for e in bad}
    urls.discard("")
    same = _also_missing_the_section(urls)
    if same == len(bad):
        tail = ("。这批和「深评缺小节」报的「评分明细」是同一批岗 —— "
                "同一次深评没出那张表，文件里少一节、库里少四维，"
                "补一次两边都好。命令在那一条下面，别做两遍")
    elif same:
        tail = (f"。其中 {same} 个的深评连「评分明细」那一节都没有"
                f"（和那条报的是同一批），另外 {len(bad) - same} 个"
                f"文件里有表、只是没回写进库")
    else:
        tail = "。这批的深评里有评分明细表，是回写那一跳没把四维带进库"
    return [("warn", "有分数没有拆解",
             f"{len(bad)} 个岗有 rank_score 但 rank_breakdown 里没有「技能与经验」，"
             f"复核时看不出这个分怎么来的{tail}")]


def check_every_gate_is_judged(seen, details) -> list:
    """深评的硬门表里，七道门**每一道都要有行**——没判和没有那行长得一模一样。

    04 第一步写着「每一道能一票否决的硬性条件都要检查」。而 2026-08-20 实测
    257 份带硬门表的深评：执业资格 75 份、户口与落户 72 份、应届生与三方 72 份
    **整个没判**（各约 28%）。

    **判不了不等于不判**：JD 没给依据时该写 `未知`（04 明写「未知的门永远不 FAIL，
    只是记给用户看」），那是一行；整行不写则查无对证——用户看到的是「六道全过」，
    而实际只判了六道里的四道。

    前端只按 `state` 过滤、不按门名，所以这个漏判**不会在面板上显形**，
    只能靠这里查。
    """
    import export_web_data as ex
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    missing = collections.Counter()
    n = 0
    #: 整张硬门表都没有的那几份（`parse_gates` 解析出 0 行）。
    #: **它们必须进分母。** 原来这里是 `if not gates: continue` —— 于是
    #: 「一道门都没判」这个最坏的形状既不进分子也不进分母，在唯一为它写的
    #: 检查里彻底隐形，读的人还把缩水后的分母当成全部。
    #: 2026-08-25 实测活动用户：276 份里 11 份是这样，且**全部带着可投的档位**。
    nogate = 0
    #: 每份记一笔 `(日期, 这份有没有漏)`，供 `batch_note` 算「最近一批还犯不犯」。
    rows = []
    for f in sorted(apps.glob("*/evaluation.md")):
        text = f.read_text(encoding="utf-8")
        gates = ex.parse_gates(text)
        n += 1
        if not gates:
            nogate += 1
        judged = {_cli.gate_of(g.get("name") or "") for g in gates}
        gaps = [c for c in _cli.GATES if c not in judged]
        for canon in gaps:
            missing[canon] += 1
        rows.append((_eval_date(text), bool(gaps)))
    if not missing or not n:
        return []
    # **全部列出来，不截断。** 原来这里是 `most_common(3)`——一共只有七道门，
    # 截到三道省不下几个字，代价却是**报告本身在少报**：2026-08-21 实测漏掉了
    # 第四道「候选人明确排除」（12 份），而 `04-job-evaluation.md` 专门为它写过一节，
    # 那一节的原话是「**用户最明确表达过的那条意愿，是唯一没人读的那条**」——
    # 它于是又成了唯一没被报出来的那道。
    #
    # 这是这个仓库反复在治的形状：**少报比没有判据更坏**，它让人以为已经清干净了。
    ranked = missing.most_common()
    rate = ranked[0][1] / n
    detail = "、".join(f"{k} {v} 份" for k, v in ranked)
    return [("warn" if rate < 0.5 else "error", "深评漏判硬性条件",
             f"{n} 份深评里，这几道门经常整个没有那一行：{detail}。"
             f"04 要求每一道都判；判不了要写「未知」，不是不写——"
             f"不写的话用户看到的是「其余全过」，而那几道根本没查。"
             + (f"其中 {nogate} 份连硬门表都没有，七道全算没判。" if nogate else "")
             + (f"{batch_note(rows)}。" if batch_note(rows) else ""))]


#: 深评输出格式里的必备小节（`04-job-evaluation.md`「输出格式」那一节）。
#: `节名 → 认得出的几种写法`（模型不会每次都用同一个词）。
#:
#: 「硬性条件」不在表里：它由 `check_every_gate_is_judged` 单独盯着，
#: 那一条查得比「有没有这一节」细得多。
EVAL_SECTIONS = {
    "评分明细": ("评分明细", "四维", "维打分", "打分明细"),
    "结论": ("结论",),
    "优势": ("优势", "对口"),
    "缺口": ("缺口", "差距", "对不上"),
    # **「待核实的信息」算数。** 04 为这两节写的内容清单原本几乎是同一张
    # （雇主匿名、平台字段自相矛盾、核实不一致同时列在两边），实测 08-17 那批
    # 40 份把真伪信号整个并了进去，内容一条没少。判「整个没有」就是把
    # **搬了家**说成**没查过** —— 而这条检查的整句结论正是「前者是没查」。
    # 两个标题都没有才算真的缺。分工已在 04 那一节写清（看出了什么 / 还不知道什么）。
    "职位真伪信号": ("真伪信号", "职位真伪", "待核实的信息", "信息质量"),
    "建议": ("建议",),
}


#: 硬门 FAIL 的深评本来就该短 —— 04 明写「任一 FAIL 则到此为止，不打分」。
_GATE_FAIL = re.compile(r"\|\s*\**FAIL\**\s*\|")


def missing_sections(text: str):
    """这一份深评缺哪几节。硬门 FAIL 的返回 `None`（本来就该短，不算漏）。

    ## 为什么要单独是个函数

    判据原来只长在 `check_evaluation_sections` 的循环里 —— 也就是说，
    **只有全量审计跑得动它**。而这件事真正该发生的时刻是**写盘之前**：
    `job-apply.md` Step 6 那一节写着「拿 04 的输出格式逐节对一遍」，
    是一句给写手看的散文提示。

    实测 2026-08-30 按批次拆开，那句提示的效果是这样的：

        2026-08-17   40 份   40 份缺「建议」
        2026-08-26   10 份   10 份缺「建议」
        2026-08-27   30 份   30 份缺「建议」
        2026-08-11   79 份   全写齐
        2026-08-25    6 份   全写齐

    **一次跑里要么每份都写、要么每份都不写。** 一批 30 份时，
    「记得对一眼」正是最靠不住的东西 —— 而这个仓库自己的教训早写过一遍：
    「用工具分，别手数」。所以判据搬出来，配一个 `--sections` 的入口，
    写完盘当场跑，非零就是没写全。
    """
    if _GATE_FAIL.search(text) or "不满足硬性条件" in text:
        return None
    heads = "\n".join(re.findall(r"^#{2,4}\s*(.+?)\s*$", text, re.M))
    return [name for name, alts in EVAL_SECTIONS.items()
            if not any(a in heads for a in alts)]


def ask_before_missing(text: str):
    """这一份该不该有「投前必问」，以及有没有。

    返回 `None` = 不是「可以考虑」那一档，本来就不要求；
    `True` = 该有而没有；`False` = 有。

    ## 为什么要单独是个函数

    和 `missing_sections` 同一个理由：判据原来只长在
    `check_maybe_tier_has_questions` 的循环里，**只有全量审计跑得动它**。
    而它该发生的时刻是写盘那一刻 —— 04 给这一档的定义就是
    「先问清楚关键信息再决定投不投」，**问什么就是这一档存在的理由**。

    实测（2026-08-30）：103/151 份缺这一节，而规则生效之后的 10 份里
    **仍缺 3 份（30%）** —— 这一条不是存量遗留，是新出的还在漏。

    两个判据都借正本，这里一个都不另写：
    判词走 `build_dashboard.parse_evaluation`（它的 docstring 记着为
    「只认一种写法」踩过三次坑），「什么算空」走
    `export_web_data.parse_ask_before`（它会滤掉「无 / 暂无 / 不适用 / N/A」
    这类占位 —— 有标题写一条「无」比空着更糟：空着不渲染，写「无」长得
    和真问题一样）。
    """
    import export_web_data as _ex
    if parse_evaluation(text).get("verdict") != "可以考虑":
        return None
    heads = "\n".join(re.findall(r"^#{2,4}\s*(.+?)\s*$", text, re.M))
    ok = any(a in heads for a in _ASK_HEADS) and bool(_ex.parse_ask_before(text))
    return not ok


#: 六节里，`/job-apply 全部` **补得了**的那几节。
#:
#: 正本是 `job-apply.md` 第 0 步那张补漏表 —— 它列出来的三样里，只有
#: 「建议」住在 `evaluation.md`（「内推请托」在话术里，「投前必问」有它
#: 自己那条检查）。两处相等由 `test_it_matches_the_backfill_table` 钉。
#:
#: **其余几节缺了只能整份重跑**，那张表的 ⚠️ 写得很直白：
#: 「「职位真伪信号」缺了只能整份重跑（事后补一个「无」等于谎报查过一次）」。
#: 实测 2026-08-31：还能动的 55 份里 44 份只缺「建议」（补得了），
#: 另外 11 份缺的是补不了的那几节 —— 而收尾原来把它们一起算进
#: 「一次补完：`/job-apply 全部`」，那条命令对这 11 份一份都动不了。
BACKFILLABLE_SECTIONS = ("建议",)


def check_evaluation_sections(seen, details) -> list:
    """深评文件的**必备小节**有没有写全。

    04 的「输出格式」把七节逐个列了出来，「职位真伪信号」那一节还专门写着
    **「没有就写「无」」**——也就是说漏写和写「无」是两件事，前者是没查。

    实测（2026-08-23，活动用户 268 份深评，排掉 20 份硬门 FAIL 的合法短文件）：

        建议          缺 86 份（35%）
        职位真伪信号  缺 44 份（18%）
        结论          缺 15 份（6%）
        优势          缺 14 份（6%）
        评分明细      缺 11 份（4%）

    ## 「一起缺 = 生成到一半停了」是错的，查过了

    这段原来写着「真伪信号与建议 86 份里 84 份同时缺，是输出格式的最后两节，
    说明生成到一半停了」。2026-08-23 把那几批打开看，**三条全错**：

    - 那批文件**更长**（中位 2350 字 vs 合规批的 1898），不是被截断；
    - 它们写了**更靠后**的小节（「投前必问」40/40 都有），不是停在某一点；
    - 真伪信号的内容一条没少，被**并进了「待核实的信息」**，而且更细
      （「平台字段行业写『互联网/电商』、融资写『融资未公开』——BAT 三家都已上市，
      字段本身就不可靠」）。

    真正的原因是**04 把同一件事要了两遍**：这两节的内容清单几乎重合，
    不同批次各挑了一个名字写。修在 04（那一节现在写清了分工：
    「看出了什么」进真伪，「还不知道什么」进待核实），这里同步认两个标题
    —— 判「整个没有」等于把**搬了家**说成**没查过**，而这条检查的结论
    偏偏就是「前者是没查」。认了之后 86 → 44，剩下的 44 才是真缺。

    「建议」那 86 份是另一回事：它们的结论行里已经带着条件
    （「值得投（64），但钱这一关先过不了」），而写了这一节的 179 份里
    **89 份（50%）**以「投 / 不投」开头 —— 复述判词。04 那一节现在写清了
    这里要的是**条件**不是判词，条件已在结论里的写「同上」。

    **硬门 FAIL 的不算漏**：04 明写「任一 FAIL 则到此为止，不打分」，
    那种文件本来就该短。不排掉它们，这条会常年报一个虚高的数，
    然后没人再当真 —— 少报和多报一样会让判据失效。

    面板不显形：它读的是解析出来的字段，一节没写就当那一项为空，
    和「有这一节但内容为空」长得一样。只能在这里查。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    missing, n, gatefail = collections.Counter(), 0, 0
    recent = []          # (文件时间, 这份缺了几节) —— 算「最近 N 份」的执行率
    # **点名还补得上的那几个。** 只报总数的话，读的人做不了任何事 ——
    # 291 份里绝大多数已经投出去或标了不投。完整的账在
    # `check_greeting_keeps_the_five_rules` 的 docstring 里。
    # 调这一下同时把这条检查带进 `--actionable`（`/job-auto` 收尾跑的那一档）：
    # 判据是行为不是名单，见 `run()`。
    # **分两拨。** 只缺「建议」的补一节就行；缺别的那几节的只能整份重跑
    # —— 两种给的命令不是一条，混成一个数就等于对后者许一个做不到的诺。
    live = []          # 补得了的：(链接, 目录名)
    rerun = []         # 只能整份重跑的
    urls = dir_urls(user)
    for f in sorted(apps.glob("*/evaluation.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        # 判据走 `missing_sections`（正本）—— 写盘前那条 `--sections` 用的是
        # 同一个函数，两处不许各判各的。
        gone = missing_sections(t)
        if gone is None:
            gatefail += 1
            continue
        n += 1
        for name in gone:
            missing[name] += 1
        gaps = len(gone)
        recent.append((_eval_date(t), f.parent.name, gaps))
        if gaps:
            # 链接走 `dir_urls`（正本）—— 在这儿自己搜 `evaluation.md` 会漏掉
            # 24 个「链接只写在 `outreach.md` 里」的目录，而漏掉的后果不是报错，
            # 是那几个岗**判不了还能不能补**。判据见 `dir_urls` 的说明。
            row = (urls.get(f.parent.name, ""), f.parent.name)
            if set(gone) <= set(BACKFILLABLE_SECTIONS):
                live.append(row)
            else:
                rerun.append(row)
    if not n or not missing:
        return []
    ranked = missing.most_common()
    detail = "、".join(f"{k} {v} 份" for k, v in ranked)
    rate = ranked[0][1] / n
    tail = f"（另有 {gatefail} 份硬门 FAIL 的没算——那种按 04 本来就该到此为止）"
    # **这里不报「趋势」，报批次。** 前两版都想从「最近 N 份」里读出一个方向，
    # 两版都读错了：按文件 mtime 排报「新出的已经好多了（13%）」，改按深评自己
    # 写的评估日期排，立刻翻成「新出的更差（90%）」。哪个都不是真的 ——
    # 实测 2026-08-23 按日期摊开，缺口根本不随时间走：
    #
    #     08-10  26 份全缺      08-11  79 份全写了
    #     08-13  16 份全缺      08-12  77 份只缺 1
    #     08-17  40 份全缺      08-19   3 份全写了
    #
    # **是整批漏，不是慢慢漂。** 缺的 86 份就是这几批加起来（26+16+2+40+2 无日期）。
    # 一个 30 份的窗口跨在批次边界上，落哪边就报哪边的数，方向纯属抽签 ——
    # 而两版报告都拿那个数下了因果断语。
    #
    # 这个形状也决定了该做什么：不是逐份补小节，是去看**那几次运行当时怎么跑的**
    # ——同一天出的 40 份整整齐齐全缺同一节，那是跑法的问题，不是写手手滑。
    #
    # **这里不按规则生效日切，`check_maybe_tier_has_questions` 那边要切。**
    # 那几节在 04 里由来已久，问的是写法漂没漂；那条查的是 08-22 才落地的新规矩，
    # 拿生效前的产出算它的执行率会得出一句假话（见 `_ASK_RULE_SINCE`）。
    #
    # 日期取深评抬头写的「评估日期」，不用 mtime：重新归档、批量改权限、同步工具
    # 都会把 mtime 推到今天，那时候按它排就是随机排 —— 上面那个 13% 就是这么来的。
    by_day: dict = {}
    for d, _k, g in recent:
        if not d:
            continue
        row = by_day.setdefault(d, [0, 0])
        row[0] += 1
        row[1] += 1 if g else 0
    #: 一批少于 5 份说明不了「整批」，不进这两个名单（08-14 的 2 份就是噪音）。
    allbad = [(d, v[0]) for d, v in sorted(by_day.items())
              if v[0] >= 5 and v[1] == v[0]]
    allok = [(d, v[0]) for d, v in sorted(by_day.items())
             if v[0] >= 5 and v[1] == 0]
    # **这段原来把每一批的日期和份数都列了出来，一行 472 字。**
    # 那串枚举是为了立住「整批漏，不是慢慢漂」这个判断，而**那个问题
    # 2026-08-30 已经答完了**：整批漏，且几乎只缺「建议」那一节，
    # 实测表与判据都进了 04 的「建议」那一节。结论立住之后，原始数据留在
    # 收尾里就成了噪音 —— 它排在真正要动手的那句前面，而这一档的全部价值
    # 就是「他现在动得了什么」。
    #
    # 留下的是**形状**（几批全缺、几批全写齐）加**最近一批还犯不犯**
    # （`batch_note`，本文件所有检查共用的那一个）。
    trend = ""
    if allbad and allok:
        trend = (f"是整批漏，不是慢慢漂：{len(allbad)} 批"
                 f"（共 {sum(n for _d, n in allbad)} 份）每份都缺了至少一节，"
                 f"另有 {len(allok)} 批（共 {sum(n for _d, n in allok)} 份）全写齐，"
                 f"而且几乎只缺「建议」那一节。")
    elif len(recent) >= 10:
        bad = sum(1 for _d, _k, g in recent if g)
        trend = (f"没有整批全缺、也没有整批全写的分界，"
                 f"{len(recent)} 份里 {bad} 份缺（{bad / len(recent):.0%}）。")
    # **`batch_note` 要接在那条链后面，不能插在中间。** 第一版把这两行放在
    # `if allbad and allok:` 和 `elif len(recent) >= 10:` 之间 —— `elif` 于是
    # 挂到了 `if _bn:` 上，「没有整批全缺」那一支再也够不着。
    # 一个纯排版的挪动改掉了控制流，而两条断言当场就红了。
    _bn = batch_note([(d, g) for d, _k, g in recent])
    if _bn:
        trend += _bn + "。"
    # 「该查的是那几次跑法」是对的，但它不是**他**现在能动的事。
    # 现在还没投的那几份补得上，而补一份就是重跑那个岗 —— 那条命令是
    # `/job-apply <链接>`（`AGENTS.md`「每一处引导都要写出该敲的命令」）。
    _live, todo = _cli.live_tail(user, seen, live)
    # 第二拨走 `verb="改"` —— 那个词把它们记进 `_cli.LIVE_REWRITE`，
    # 于是收尾会把这几条命令逐个印出来（「一次补完」那句改不了它们）。
    _r_live, _r_todo = _cli.live_tail(user, seen, rerun, verb="改")
    if rerun:
        todo += (f"另有 {len(rerun)} 份缺的不是「建议」那一节 —— 事后补一个「无」"
                 f"等于谎报查过一次，只能整份重跑（补漏表的 ⚠️）。"
                 + _r_todo)
    return [("warn" if rate < 0.5 else "error", "深评缺小节",
             f"该写全的 {n} 份深评里，这几节常常整个没有：{detail}{tail}。{trend}"
             # **理由不在这里展开。** 这两句（「漏写和写「无」是两件事」
             # 「一节没写就当那一项为空，看不出区别」）2026-08-30 已经进了
             # 04 的「建议」那一节和 `job-apply.md` 第 6 步 —— 写它的人在
             # 动笔前就会读到。收尾这一行要留的是**他现在动得了什么**，
             # 而这段解释排在那句前面，把它推到了 400 字开外。
             f"判据与实测表见 04 的「建议」那一节。"
             f"{todo}")]


#: 学历字段判死一个岗会误杀多少——超过这个比例就不配有结案权。
#: 12 个样本时是 58%，1485 份 JD 复核后是 60%；两次都远超阈值。
EDU_KILL_CEILING = 0.20
_EDU_ORD = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}
_EDU_REQ = re.compile(r"(大专|本科|硕士|博士)\s*(?:及|或)?以上")
_EDU_RELAX = re.compile(r"放宽|同等(?:经验|学力|能力)|优秀者?不限|学历不限|不限学历")


#: 「投前必问」那一节的几种写法。`export_web_data.parse_ask_before` 宽进认这几个，
#: 这里用同一份 —— 两处各写一份，迟早一处认得、另一处认不得。
_ASK_HEADS = ("投前必问", "必问", "要问清")

#: 「最近多少份」算当下的执行率。30 是在样本够稳（不被一两份带偏）与够近
#: （还能反映当前写法）之间取的；实测 20 / 30 / 50 三档结论一致
#: （70% / 73% / 56%，都远高于全量的 46%），对这个数不敏感。
RECENT_EVALS = 30

#: 「投前必问」写进 `04-job-evaluation.md` 输出格式的日期。出处是那份文档自己
#: 第 37 行的原话：「这一节是 2026-08-22 补进输出格式的」。
#:
#: **为什么这个常量非有不可。** 缺它的时候这条检查报的是
#: 「最近 30 份里缺 22 份（73%）——不是存量遗留，新出的更差」，
#: 而实测 2026-08-23：268 份深评最新的一份是 **08-19**，
#: 全部产在规则之前。那句「新出的更差」把**存量**说成了**规则不灵**，
#: 读的人会去重写规则，而正确的动作只是「跑一批新的再看」。
#: 一个趋势如果算的是规则生效前的材料，它就不是关于那条规则的趋势。
_ASK_RULE_SINCE = "2026-08-22"

#: 深评自己写在抬头的日期（`- 评估日期：2026-08-17（…）`）。
#: **不用文件 mtime**：重新归档、批量改权限、同步工具都会把它推到今天，
#: 而这里要问的是「这份深评是什么时候写的」。
#:
#: ⚠️ **列表符是可选的。** 原来写死 `^-\s*`，而 `04` 的输出格式里**根本没有
#: 这一行** —— 266/270 对得上只是因为早期批次碰巧都带了 `- `。
#: 实测 2026-08-24：3 份写了日期却没带列表符，其中**两份是当天照 04 的格式写的**，
#: 于是当天新出的深评对所有按日期分析的检查**全部隐形**
#: （批次趋势、`_ASK_RULE_SINCE` 那道时间线都读不到它们）。
#: 两头都修了：这里放宽，`04` 的输出格式也补上了那一行。
_EVAL_DATE = re.compile(r"^[-*\s]*评估日期[：:]\s*(\d{4}-\d{2}-\d{2})", re.M)


#: 重跑完留下的那一行。判据与 `stale_materials._REREAD` 同形 ——
#: 那边据它出队，这边据它认「这一批」。
_RERUN_DATE = re.compile(r"^[-*#\s]*重跑日期[：:]\s*(\d{4}-\d{2}-\d{2})", re.M)


def _rerun_date(text: str) -> str:
    m = _RERUN_DATE.search(text or "")
    return m.group(1) if m else ""


def _dated_text(f) -> str:
    """拿来读日期的那份文本。

    **话术文件自己没有「评估日期」那一行**（那是深评抬头的东西），
    所以同目录的 `evaluation.md` 顶上 —— 同一次跑产的两个文件，日期本来就是同一个。
    读不到就返回原文（`_eval_date` 会给空串，`batch_note` 自己会跳过）。
    """
    if f.name == "evaluation.md":
        return f.read_text(encoding="utf-8", errors="replace")
    sib = f.parent / "evaluation.md"
    if sib.is_file():
        return sib.read_text(encoding="utf-8", errors="replace")
    return ""


def batch_note(rows, min_size: int = 8) -> str:
    """「最近一批还犯不犯」——按日期分组，只报最后那一批。没得比就返回空串。

    `rows` 是 `[(日期字符串, 这份有没有问题)]`。

    ## 为什么每条检查都需要它

    审计每一条报的都是**全库累计数**（「191/269 份命中框架词」），而那个数
    只会随产量涨：改好了也降不下来，因为分母里绝大多数是规则收紧之前产的。

    **改完一条规则之后，唯一能回答「它生效了没有」的是「最近一批还犯不犯」。**
    这不是新想法 —— 本文件已经有两条检查在散文里手写过同一件事：

        深评缺小节：「是整批漏，不是慢慢漂：2026-08-10 那批 26 份每份都缺了
                    至少一节……而 2026-08-11 的 79 份全写齐了。
                    **该查的是那几次跑法，不是逐份补。**」
        可以考虑：  「这个数说的是存量，说明不了规则灵不灵，**跑一批新的才有得比**」

    手写两遍就会有第三遍写不出来。这里做成一个函数。

    **太小的批次不报**（`min_size`）：实测这个库里 2026-08-14 只有 2 份、
    08-19 只有 3 份 —— 「最近一批 2/2 都犯」在统计上说不出任何东西，
    而它读起来像个结论。宁可不说。
    """
    from collections import defaultdict
    by = defaultdict(list)
    for day, bad in rows:
        if day:
            by[day].append(bool(bad))
    if not by:
        return ""
    for day in sorted(by, reverse=True):
        got = by[day]
        if len(got) >= min_size:
            return (f"最近一批（{day}，{len(got)} 份）里 {sum(got)} 份 —— "
                    f"这个数才说得了规则灵不灵，全库那个数只会随产量涨")
    return ""


def watermark_note(days) -> str:
    """「最近一批是 X（N 个）—— 存量不必逐个补，盯的是这个数会不会再涨。」

    `days` 是每个命中项的日期，空的跳过；一个日期都没有就返回空串。

    ## 和 `batch_note` 的分工

    `batch_note` 要**分母**（那天判过这道门的全部），报的是「最近一批里犯了几成」
    —— 它能回答「规则灵不灵」。而有些检查拿不到分母（只看得见犯了的那几个），
    那时只能报**水位线**：最近一次是哪天、那天几个。两句话说的不是一回事，
    别混用；能拿到分母的一律用 `batch_note`。

    ## 为什么这里没有 `min_size`

    `batch_note` 拒绝报太小的批次（「最近一批 2/2 都犯」在统计上说不出任何
    东西，读起来却像个结论）。水位线不是比例：「最近一次是 08-26，那天 1 个」
    本身就是有意义的 —— 它说的是「规则大体上守住了」。

    ## 它 2026-08-31 之前在两处逐字重复

    薪资维那条、总分那条，连同前面那两行 `latest` / `recent` 的记账，一字不差。
    而 `batch_note` 自己的说明开头就写着：「手写两遍就会有第三遍写不出来。
    这里做成一个函数。」—— 那句话写下之后，同一个形状又长了两份。
    """
    got = [d for d in days if d]
    if not got:
        return ""
    latest = max(got)
    n = sum(1 for d in got if d == latest)
    return (f"最近一批是 {latest}（{n} 个）—— 存量不必逐个补，"
            f"盯的是这个数会不会再涨。")


def _eval_date(text: str) -> str:
    m = _EVAL_DATE.search(text)
    return m.group(1) if m else ""


def _named_section(text: str, keyword: str) -> str:
    """`outreach.md` 里标题含 `keyword` 的那一节正文，尾部自检元数据已剥。

    `_greeting_of` 原来把这段逻辑内联着，只服务开场白一个调用方。
    2026-08-27 加「另外几个渠道的文风」那条检查时要切邮件 / 网申自评 /
    求职信 / 内推请托 —— 再抄一份切片器，就正是 `_greeting_of` 自己的 docstring
    警告过的那件事：「**同一份文本两个读法，就是两套标准。**」
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("#") and keyword in ln), None)
    if start is None:
        return ""
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        out.append(ln)
    return _strip_wordcount("\n".join(out).strip())


def _greeting_of(text: str) -> str:
    """`outreach.md` 里要发出去的那段开场白。**尾部的自检元数据要剥掉。**

    切完小节还没完：真实产出的尾巴上挂着写给他自己看的东西 ——
    `（字数：199）`、`> 字数校验：**183 字**（去空白字符计），≤200 ✓`。
    不剥的后果分两层：

    - **对这几条检查**：字数上限那一条把自检行也算进去，实测 3 份被误报成
      「超 200 字」（207 / 208 / 232），而它们自己写着 199 / 200 / 183。
      这类检查误报一次就会被整条忽略。
    - **对用户**（更要紧，但这一层面板已经挡住了）：那段话是直接粘进聊天框的，
      混进一行说明就会连着发给 HR。`06-outreach-templates.md` 专门记过这一条。

    剥的动作复用 `build_dashboard._strip_wordcount` —— 面板那一侧从一开始就走它，
    这里此前自己切了一遍、漏了剥。**同一份文本两个读法，就是两套标准。**
    """
    return _named_section(text, "打招呼")


#: 抬头里不许出现的内部词。判据在 `AGENTS.md`「给用户看的措辞」那张表 ——
#: 这几个是给 AI 用的框架词，用户不该为了看懂一份话术先学一套生造词。
#:
#: **这张表可以比 `_DOC_JARGON` 严，因为抬头是结构化字段、不是散文。**
#: 「能力边界」在正文里读得通（「这是你写明的能力边界」），所以那边不收；
#: 而抬头是 `06` 规定的几行元信息，那里出现「能力边界」只可能是框架词。
#: 同理反过来：正文那张表里的词，抬头这张一个都不该少。
#:
#: 实测 2026-08-30 补了两个：`驾驶舱`（抬头里真出现过 1 次）、`短名单`
#: （0 次，但它和「驾驶舱」是同一类 —— 中文里没有别的读法，漏着只是等它出现）。
#: **正本在 `_cli.HEAD_JARGON`**，这里只取词那一列。
#: 原来是手写的八个词，而话术抬头的修理工手写着另外五个 —— 同一层的检查器
#: 与修理工分叉，报得出来改不了（实测 2026-08-30：报「1 份用了内部词」，
#: 修理工说「要改 0 份」，只好推给人）。
_HEAD_JARGON = tuple(w for w, _rx, _fix in _cli.HEAD_JARGON)

#: 猎头岗里不许对着顾问说的话。`06` 渠道 1 那张表原话：
#: 「对面是顾问不是用人方。跟他讲『贵司如何如何』是讲错了人」。
#: **正本在 `_cli`**（面板那一侧也要用同一份判据 —— 审计事后报、面板在他按
#: 「复制开场白」那一下报，两处说的必须是同一件事）。这里只留别名，别再抄一份。
_WRONG_ADDRESSEE = _cli.WRONG_ADDRESSEE
_head_of = _cli.head_of


#: 落盘产出里不许出现的框架词 → 该写成什么。判据在 `AGENTS.md`「给用户看的措辞」。
#:
#: **只收判据明确、且中文里不会误伤的那几个。** `能力边界` 不在这里：表里那一行
#: 写的是「能力边界**缺口**」，而「这是你写明的能力边界」在中文里读得通；
#: `信息质量` 同理（「信息质量好」是日常说法）。误报一次这条就会被整条忽略 ——
#: 本仓库为这句话付过好几次学费。
#:
#: ⚠️ **`业务域` 同样不收，而它看起来最像漏的那个。** 显示层的
#: `export_web_data.INTERNAL_TERMS` 里有它（→「行业经验」），这张表里没有，
#: 于是「三份词表两两不同」一扫就把它挑出来 —— 实测 2026-08-30 全库 **146 次**，
#: 加进来是这条检查一夜之间多报 145 个文件。
#:
#: 逐条看过那 146 处：**145 处是地道中文**，只有 1 处在打分算式里。
#: 原样抄三句：「充换电运营、能源电力这个业务域」「售后与车主服务这个业务域他没做过」
#: 「扣在知识产权这个业务域你完全不熟」—— 说的是「业务领域」，不是四维里那个子项名。
#: 显示层可以无脑换（那边换错了顶多把「业务领域」说成「行业经验」，意思还在），
#: 这里换错了是**报一个不存在的问题**。
#:
#: **三份词表不一样是有意的，不是漏。** 判据是各自的误伤代价：
#: 显示层最宽（换错了不伤），抬头次之（结构化字段，没有别的读法），
#: 正文最窄（散文，误报一次整条被忽略）。
#: `硬门` 要排掉 `硬门槛`：后者是中文里本来就有的词（实测 7 处），
#: 被换掉的只是框架自己造的那个简称。
#: 正文这张**从抬头那张减出来**，减掉的每一个都要在这里写明理由。
#: 原来两张各写各的七、八条，七条一模一样 —— 差的那一条要靠对着读才看得出来，
#: 而「三份不一样是有意的」这句话也就无从验证。现在差集是代码里的一个常量。
_DOC_EXCLUDE = {
    # 表里那一行写的是「能力边界**缺口**」，而「这是你写明的能力边界」
    # 在中文里读得通。抬头是结构化字段、没有别的读法，所以那边收、这边不收。
    "能力边界",
}
_DOC_JARGON = tuple(t for t in _cli.HEAD_JARGON if t[0] not in _DOC_EXCLUDE)


def check_documents_speak_chinese_to_the_user(seen, details) -> list:
    """深评与话术是给用户看的文件 —— 正文里不该有框架词。

    `AGENTS.md`「给用户看的措辞」管的是「凡是给用户看的东西」，逐条列了替换。
    面板那一侧有兜底（`export_web_data` 的替换表，「最后一道显示层」），
    **而用户直接打开这两个文件时没有任何一层挡在中间**。

    实测活动用户 2026-08-24（剥掉 HTML 注释，那些是写给 AI 的）：

        evaluation.md   268 份里 191 份命中（71%）  判词 282 · 四维 65 · 硬门 45
        outreach.md     236 份里 104 份命中（44%）  判词 102 · 驾驶舱 1 · 台账 1

    最扎眼的是前两个：**它们的正解就是输出格式里那两节的名字**
    （「结论」「评分明细」），写的人抬头就看得见，却在正文里改口叫回框架词；
    有几份干脆把小节标题写成了 `## 四维`。

    ## 为什么判「留意」而不是「要修」

    没有机械修法 —— 换词要读上下文（`判词是「不满足硬性条件」` 换成
    `结论是「不满足硬性条件」` 是对的，`判词上限` 换成什么要看那句在说什么）。
    存量 191 份也不该逐份补：该盯的是**新跑的批次别再犯**，判据现在贴在
    04 输出格式的开头，写的人第一眼就看得到。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    out = []
    for kind, label in (("evaluation.md", "深评"), ("outreach.md", "话术")):
        files = sorted(apps.glob("*/" + kind))
        if not files:
            continue
        hit, per_word, sample = [], collections.Counter(), []
        rows = []
        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace")
            # **话术把抬头切掉**：抬头那半归
            # `check_outreach_header_says_who_youre_talking_to` 管，两条都报
            # 等于同一批文件在审计里出现两次，用户会以为有两个问题
            # （2026-08-24 第一版就是这样：那边 103 份、这边 104 份）。
            if kind == "outreach.md":
                text = text[len(_head_of(text)):]
            # HTML 注释是写给 AI 的，不算「给用户看的东西」。
            text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
            words = [w for w, pat, _fix in _DOC_JARGON if re.search(pat, text)]
            # **每份都记一笔（不管有没有命中）**，`batch_note` 要靠它算
            # 「最近一批里 N 份」——只记命中的，分母就丢了。
            # 日期取自深评抬头那一行；话术没有那一行时同目录的深评顶上。
            rows.append((_eval_date(_dated_text(f)), bool(words)))
            if not words:
                continue
            hit.append(f)
            for w, pat, _fix in _DOC_JARGON:
                per_word[w] += len(re.findall(pat, text))
            if len(sample) < 3:
                sample.append(f"{f.parent.name.split('_')[0][:14]}（{words[0]}）")
        if not hit:
            continue
        fixes = "、".join(f"{w}→{fix}" for w, _p, fix in _DOC_JARGON
                          if per_word.get(w))
        out.append(("warn", f"{label}正文里有框架词",
                    f"{len(hit)}/{len(files)} 份命中（"
                    + "、".join(f"{w} {n} 次" for w, n in per_word.most_common()
                                if n)
                    + f"）。这个文件用户会直接打开，而面板那层措辞替换救不了它。"
                    f"换成：{fixes}（判据见 AGENTS.md「给用户看的措辞」，"
                    f"以及 04 输出格式开头那张表）。存量不必逐份补，"
                    f"盯新跑的批次{'：' + batch_note(rows) if batch_note(rows) else ''}。"
                    f"例：{'、'.join(sample)}"))
    return out


def _addressee_fallout(wrong: set, right: set, said_gui: set) -> str:
    """抬头写反的那批，正文跟着对错人的比例 —— 和写对的那批比一比。

    只报**比例差**，不报单边的数：单说「28 份里 8 份说了贵司」看不出是不是
    这一档本来就容易出错。拿写对的那批当对照，差出一个量级才说得上是因果。

    实测活动用户 2026-08-25（库里是猎头的 130 份话术，按 `_WRONG_ADDRESSEE`
    这条正本判「对错了人」—— 手工只搜「贵司」会少算，它还收「你们」「咱们」
    「公司刚发布了」这类）：

        抬头写反（说直招） 28 份 → 正文对错了人 6 份（21%）
        抬头写对（说猎头） 42 份 → 正文对错了人 1 份（2%）

    十倍。两边样本都太小时（任一侧 < 10）不说 —— 那时比例是噪音。
    """
    if len(wrong) < 10 or len(right) < 10:
        return ""
    a, b = len(wrong & said_gui), len(right & said_gui)
    if not a:
        return ""
    ra, rb = a * 100 // len(wrong), b * 100 // len(right)
    if ra <= rb * 2:
        return ""                     # 没拉开差距，别把巧合说成因果
    return (f"写反的代价看得见：这 {len(wrong)} 份里 {a} 份（{ra}%）正文"
            f"对着顾问说了「贵司」，而抬头写对的 {len(right)} 份里只有 "
            f"{b} 份（{rb}%）。先改抬头，正文那条自然少 —— "
            f"那一条见「猎头岗的开场白对着顾问说「贵司」」。")


def check_recruiter_title_contradicts_the_channel(seen, details) -> list:
    """招聘者头衔明写「猎头」，而 `isHeadhunter` 记成直招。

    ## 为什么这一条要有

    `isHeadhunter` 决定话术抬头写「猎头代招」还是「企业直招」，而那半句决定
    **第二轮怎么说话**（`06` 渠道判定：猎头问薪资与到岗时间要直接答，
    HR 直招不主动展开）。记反了，开场白就对着用人方说话 ——
    正是「猎头岗的开场白对着顾问说「贵司」」那条报的错，只是根因在字段上。

    实测活动用户 2026-08-30：两个字段都在的 152 条里 **4 条**这样
    （头衔写「XX人力资源 · 猎头顾问」，而 `isHeadhunter=False`）。
    四个都还没出材料，三个还能发 —— 现在改，比出完材料再改便宜。

    ## 只报一个方向

    「头衔里有『猎头』」⇒ 一定是代招，这条硬。
    反过来不成立：实测 6 条 `isHeadhunter=True` 的头衔是「顾问 · 某人力资源
    公司」「Consultant · 某某人力资源」，甚至「人力资源/HR · 某管理咨询公司」——
    **那些人确实在猎头公司里**，字段是对的，头衔里只是没有「猎头」二字。
    按「头衔像用人方」去反推会把这 6 条全报成错。

    第一版的检测就是双向的，当场把那 6 条一起报了出来 ——
    **判据不对称的时候，检查也得不对称。**

    ## 2026-08-30：这条从「报 4 个岗」改成「盯推导」

    原来它报的是**职位库里那个字段写错了**，收尾给的动作是「一次一个跑
    `/job-apply <链接>`」—— 4 次手工重跑。可这件事根本不必手工：
    「头衔含『猎头』⇒ 代招」是一条硬规则，判据搬进 `_cli.via_headhunter`
    之后，面板、`doctor`、`followups`、话术抬头四处一起跟着对，
    存在盘上的那个字段错不错已经没有消费者。

    同一天顺着这条线拆出来的**三份实现**（这才是那 4 个岗的真正代价）：

    | 谁 | 看的字段 | 那 4 个岗被判成 |
    |---|---|---|
    | `_cli.via_headhunter` | `recruiter` | 企业直招 ✗ |
    | `outreach_header.side_of` | 裸 `isHeadhunter` | 企业直招 ✗ |
    | `_cli.counterpart_of` | 两张角色词表 | 3 个空 + **1 个 HR** ✗ |

    最后那个最贵：头衔是「某某人力资源 · 猎头顾问」，公司名里的「人力」
    撞上了 `COUNTERPART_HR`，于是 `/job-apply` 第 1.5 步会给一个猎头顾问
    写 HR 直招版的话术 —— 而对猎头，薪资与到岗时间恰恰要直接答。

    所以现在这条查的是**推导有没有覆盖住**，不是**盘上那个字段对不对**。
    它在真语料上恒为 0；哪天有人把某一处的规则改回去，它就红。
    """
    bad = []
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        title = str(e.get("recruiterTitle") or "").strip()
        if "猎头" not in title:
            continue
        # 三处推导都要认出来。哪一处漏了都会让第二轮说错话。
        miss = []
        if _cli.via_headhunter(e) is not True:
            miss.append("via_headhunter")
        if _cli.counterpart_of(title, e.get("isHeadhunter")) != "猎头":
            miss.append("counterpart_of")
        if miss:
            bad.append(((e.get("title") or "?")[:22], title, "/".join(miss)))
    if not bad:
        return []
    rows = "、".join(f"{t}（{r[:16]} → {m}）" for t, r, m in bad[:3])
    return [("warn", "头衔明写「猎头」，而判据没认出来",
             f"{len(bad)} 个岗的招聘者头衔里写着「猎头」，"
             f"而下面这几处判据仍把它当直招：{rows}。"
             f"这半句决定第二轮怎么说话（06 渠道判定，猎头问薪资与到岗时间要"
             f"直接答）。这是代码回退，不是数据脏 —— 硬规则「头衔含『猎头』」"
             f"⇒ 代招 的正本在 _cli.via_headhunter，"
             f"counterpart_of 与 doctor._via_headhunter 各有一份手抄件。")]


def check_outreach_header_says_who_youre_talking_to(seen, details) -> list:
    """抬头要答清「在跟谁说话、这一档是什么」—— 实测两样都缺。

    `06-outreach-templates.md` 的产出格式规定了抬头块，`/job-apply` 1.5a 也写着
    「判定结果（**有无对话方** + 猎头/直招）写入产出物的头部」。而实测活动用户
    2026-08-24 扫 236 份真实产出：

        没写是猎头还是 HR 直招     110 份（只写到「有对话方 · 猎聘聊天框」就停了）
        抬头说「直招」而库里是猎头   28 份
        抬头里连个分数都没有        177 份（`评分：` 这个字段 0/236，
                                  59 份改写成 `判词：`，「判词」共出现在 102 份里）
        猎头岗对着顾问说「贵司」      9 份

    三件事各有各的代价：

    - **少了猎头/直招那半句**，第二轮就没法照着走。`06` 那张表里两边的答法
      是分开的：猎头问薪资与到岗时间要直接答（他要拿这两个数去匹配），
      HR 直招则不主动展开。抬头不说，发的时候只能重猜一遍。
    - **说反了更贵。** 那 28 份全是一个方向（文件说直招、库说猎头），
      而且 **28/28 的雇主名是「某上海……公司」这类占位**——猎聘只对猎头/代招岗
      隐雇主名，HR 自己发的岗公司名就在那儿。文件错，字段对。
      照着「直招」写，就会对着顾问讲「贵司如何如何」——实测 3 份已经这么写了。
    - **没有分数与档名**，打开文件看不出这份是「强匹配」还是「可以考虑」，
      而那正是决定发不发的那个数。59 份用的还是「判词」——`AGENTS.md`
      那张措辞表里点名要换掉的内部词，`06` 上一条也刚点过名。

    ## 为什么规格那一半也跟着改了

    236/236 不符合规格时，先怀疑规格。执行者把「投递路径」和「渠道判定」并成
    一行（`有对话方 · 猎聘聊天框（猎头）`）**比拆成两行好**——一行答完两件事。
    所以 `06` 改成只钉内容不钉行数，这条检查也只查内容：**不查有没有那几行，
    查那几件事说清没有**。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    by_url = {_cli.norm_url(e.get("url") or ""): e for e in seen.values()}
    no_kind, wrong_kind, no_band, jargon, wrong_who = [], [], [], [], []
    _who_live, _kind_live = [], []
    #: 上面两张单子的**交集**，按目录名存。
    #:
    #: 「抬头写反」和「对着顾问说贵司」是同一件事的因和果 —— 这一点本来就写在
    #: 上面那段说明里（「照着『直招』写，就会对着顾问讲『贵司如何如何』」），
    #: **而报出去的两条消息里一个字都没有**。读的人看到的是两条不相干的警告，
    #: 于是去把那一句「贵司」改掉，抬头留在原地 —— 下次重跑照样写错。
    _dir_wrong_kind, _dir_wrong_who, _dir_right_kind = set(), set(), set()
    #: 抬头标了「他先开口」，而开场白还照着「你先开口」那套写。
    inbound_bad = []
    for f in sorted(apps.glob("*/outreach.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        head = _head_of(text)
        who = f.parent.name.split("_")[0][:16]
        # 1) 有没有说是猎头还是直招
        #
        # **判据只有一份，在 `_cli`。** 这里原来把那三行原样又写了一遍。
        # 两份此刻同字同序，所以谁也不红 —— 而这正是 `_cli` 那段
        # 「每样只许在这里定义一次」点名的形状：分叉的样子永远是
        # 「改了一份、忘了另一份，且两份各自都有测试护着」。
        #
        # 这一份尤其不能分叉：面板那侧走的是 `_cli.addressee_problem`
        # （同一个 `addressee_said`），两边判的是**同一批** outreach 文件。
        # 规则一变，用户会在面板上看到一条警告，而审计说这份没问题。
        said = _cli.addressee_said(head)
        m = LINK_LINE.search(text)
        e = by_url.get(_cli.norm_url(m.group(1))) if m else None
        if not said:
            no_kind.append(who)
            # 还发得出去的那几份要点名并给命令 —— 这一行原来只报一个数字。
            _kind_live.append((m.group(1) if m else "", f.parent.name))
        # 2) 说了的，跟库里那个字段对一遍
        if e and said:
            real = "猎头" if e.get("isHeadhunter") else "直招"
            if said != real:
                wrong_kind.append(f"{who}（写「{said}」，库里是「{real}」）")
                _dir_wrong_kind.add(f.parent.name)
            elif real == "猎头":
                _dir_right_kind.add(f.parent.name)
        # 3) 猎头岗别对着顾问说「贵司」
        if e and e.get("isHeadhunter"):
            g = _greeting_of(text)
            hit = _WRONG_ADDRESSEE.search(g) if g else None
            if hit:
                wrong_who.append(f"{who}（「{hit.group(0)}」）")
                # 还发得出去的那几份要单独点出来（判定与命令走 `_cli.live_tail`）
                _who_live.append((e.get("url") or "", f.parent.name))
                _dir_wrong_who.add(f.parent.name)
        # 3.5) 对方先来找你的那一份，开场白第一句不该还是「看到这个岗」
        #
        # **只在抬头标了「他先开口」时才查**（`06` 的抬头规定：默认不写，
        # 只在反常态那一份上标）。所以这条对存量零噪音 —— 实测活动用户
        # 2026-08-24，236 份产出里 0 份带这个标记。它是给以后用的：
        # `job-resume.md` 2.6 那一整节的目的就是把「对方先来找你」做出来。
        #
        # 两种写法都要挡，而现有的五类禁语只挡得住第一种：
        # 「看到这个岗」——是他发给你的，你「看到」是理所当然（走 `opening_padding`）；
        # 「谢谢关注」——礼貌话占掉了第一行，而那一行要答的是「这人能不能干」，
        # 它不在那五类里（`_cli.GREETING_BANS` 查过，没有这一类）。
        if "他先开口" in head:
            g = _greeting_of(text)
            pad = _cli.opening_padding(g or "")
            body = re.sub(r"^[您你]好[，,]\s*", "", (g or "").lstrip())
            if pad:
                inbound_bad.append(f"{who}（「{pad}」）")
            elif re.match(r"(谢谢|感谢|多谢)", body):
                inbound_bad.append(f"{who}（「{body[:8]}…」）")
        # 4) 分数与档名
        if not re.search(r"\d{1,3}\s*分", head):
            no_band.append(who)
        # 5) 内部词。**按匹配式判，别用字面 `in`** —— 主表里 `硬门` 写的是
        # `硬门(?!槛)`，字面判会把中文本来就有的「硬门槛」报成框架词，
        # 而修理工按匹配式跑、根本不会去改它：报得出来改不了，又是一处。
        bad = [w for w, rx, _fix in _cli.HEAD_JARGON if re.search(rx, head)]
        if bad:
            jargon.append(f"{who}（{bad[0]}）")

    out = []
    if no_kind or wrong_kind:
        parts = []
        if no_kind:
            parts.append(f"{len(no_kind)} 份没写是猎头还是 HR 直招")
        if wrong_kind:
            parts.append(f"{len(wrong_kind)} 份写反了")
        # **点名 + 给命令。** 这一行原来只有一个数字，收尾里读到的人做不了
        # 任何事 —— `AGENTS.md`「每一处引导都要写出该敲的命令」管的正是它。
        #
        # 那几份为什么不是机械活：实测 2026-08-30，判不出渠道的 11 份里
        # **11 份连详情库记录都没有**（`isHeadhunter` / `recruiter` /
        # `recruiterTitle` 职位库和详情库两边全空，而 `jd_store.MERGE_FIELDS`
        # 三个都带着 —— 无米可炊，不是回填断了）。抓取当次没取到招聘者，
        # 事后只能开页面看，那正是 `/job-apply` 第 1.5 步在做的事。
        _lk, _kind_tail = _cli.live_tail(user, seen, _kind_live, verb="补")
        out.append(("warn", "话术抬头没说清在跟谁说话",
                    "、".join(parts)
                    + "。第二轮怎么说话完全取决于这半句（猎头问薪资与到岗时间"
                      "要直接答，HR 直招不主动展开，见 06「渠道判定」那张表）。"
                    + ("这几份的招聘者当初就没抓到（职位库和详情库两边都空），"
                       "机械补不出来 —— 只能开页面看一眼。" + _kind_tail
                       if no_kind else "")
                    + (f"写反的例：{'、'.join(wrong_kind[:3])}。"
                       "猎聘只对猎头/代招岗隐雇主名——雇主名是「某……公司」"
                       "而抬头写着直招，那是文件错、字段对。" if wrong_kind else "")
                    # **写反的代价不是一句抬头，是正文跟着对错了人。**
                    # 这条因果本来就写在上面那段说明里，而报出去的消息里没有 ——
                    # 于是它和「对着顾问说贵司」看起来是两件不相干的事，
                    # 修的人只会去改那一句。两边的出错率一比就看得出不是巧合。
                    + _addressee_fallout(_dir_wrong_kind, _dir_right_kind,
                                         _dir_wrong_who)))
    if wrong_who:
        _from_head = len(_dir_wrong_who & _dir_wrong_kind)
        out.append(("warn", "猎头岗的开场白对着顾问说「贵司」",
                    f"{len(wrong_who)} 份。06 渠道 1 那张表原话：「对面是顾问"
                    f"不是用人方。跟他讲『贵司如何如何』是讲错了人」——他要判断的"
                    f"是「这人能不能推」。"
                    + (f"其中 {_from_head} 份的抬头本身就写反了"
                       f"（写「直招」而库里是猎头）—— 只改这一句、不改抬头，"
                       f"下次重跑还会照着错的对象写。那一条见上面"
                       f"「话术抬头没说清在跟谁说话」。"
                       if _from_head else "")
                    + f"例：{'、'.join(wrong_who[:3])}。"
                    + _cli.live_tail(user, seen, _who_live, verb="改")[1]))
    if inbound_bad:
        out.append(("warn", "对方先来找你的那几份，开场白还是「看到这个岗」",
                    f"{len(inbound_bad)} 份。抬头标了「他先开口」，说明这个岗是"
                    f"猎头/HR 主动发过来的 —— 第一句该先回他问的那件事，"
                    f"不是复述他刚发给你的东西，也不是「谢谢关注」"
                    f"（判据见 06 渠道 1「对方先开口时怎么写」）。"
                    f"例：{'、'.join(inbound_bad[:3])}"))
    if no_band or jargon:
        parts = []
        if no_band:
            parts.append(f"{len(no_band)} 份抬头里没有分数与档名")
        if jargon:
            parts.append(f"{len(jargon)} 份用了内部词（例：{'、'.join(jargon[:3])}）")
        out.append(("warn", "话术抬头缺分数档 / 用了内部词",
                    "、".join(parts)
                    + "。打开文件看不出这份是「强匹配」还是「可以考虑」，"
                      "而那正是决定发不发的那个数。写成「49 分，属于『可以考虑』」，"
                      "「判词」「四维」这类框架词换成中文说人话（判据见 AGENTS.md"
                      "「给用户看的措辞」与 06 的抬头规定）。"))
    return out


def check_company_claims_have_a_source(seen, details) -> list:
    """开场白里**对公司下了断言**，就必须记下它的出处。

    `03-writing-style.md` 铁律 1 是「绝不编造」，而一条没有出处的公司主张
    **没有任何办法验证**——审稿者验不了，用户两周后自己也想不起来是从哪看的。
    产出格式里「本次使用的公司事实」那一节就是它的落点。

    ## 判据不在这儿

    正本是 `_cli.claim_without_source`（面板那一侧同一个函数），
    连「范围为什么这么窄」也记在那里 —— 别在这儿再写一份。

    顺手也证伪了「开场白是不是都长一个样」这个更要紧的怀疑：
    两两 4-gram Jaccard 相似度中位 **0.06**、最高 0.49、**超过 0.5 的配对为零**。
    它们确实是逐岗写的。共享的片段全是他自己的战绩（「10万+注册用户」），
    不是模板套话。**所以不许对用户说「你的开场白发给谁都成立」——那不是真的。**

    留下的这一条很窄，但它守的是这个仓库最硬的那条规矩：
    **有主张就要有出处。**
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    bad, live = [], []
    for f in sorted(apps.glob("*/outreach.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        g = _greeting_of(t)
        # 判据正本在 `_cli.claim_without_source` —— 面板那一侧（`materials.factWarn`）
        # 走的是同一个函数，两处不许各判各的。
        if _cli.claim_without_source(g, _cli.fact_items(t)):
            bad.append(f.parent.name.split("_")[0][:16])
            m = LINK_LINE.search(t)
            live.append((m.group(1) if m else "", f.parent.name))
    if not bad:
        return []
    return [("warn", "开场白说了公司的事，却没记从哪看来的",
             f"{len(bad)} 份的开场白里有对公司的主张，而「本次使用的公司事实」"
             f"那一节是空的——没有出处就没法验证它是不是编的（`03` 铁律 1）。"
             f"例：{'、'.join(bad[:4])}。"
             # 这一条报的是**要发出去的字**，而它此前一条命令都没给。
             # 只点还发得出去的那几份：已经投出去的改也来不及。
             + _cli.live_tail(user, seen, live, verb="改")[1])]


#: 「这一份还发得出去吗」**正本在 `_cli`** —— 第三个调用方（`writeback`）
#: 来了之后它就不该再住在这个文件里：那边只想报「还能改的有几个」，
#: 却要为此 import 整个自检（50 多条检查、几千行）。
#:
#: `run()` 的 `--actionable` 判据仍然是「这条检查问没问过」，
#: 计数器跟着搬到了 `_cli._SENDABLE_CALLS`。
_SENDABLE_CALLS = _cli._SENDABLE_CALLS
sendable_state = _cli.sendable_state


def dir_urls(user: str) -> dict:
    """`目录名 → 职位链接`。**正本是 `build_dashboard.find_applications`。**

    ## 为什么不在检查里自己搜

    这个仓库里「这个投递目录对应哪个岗」有过两份实现，而**两份各自不全**：

    - `find_applications` 从 `outreach.md` 找，找不到退到 `posting.md`
      （标签宽进：原始链接 / 职位链接 / 链接 / URL，全半角冒号都认，
      再退到文件头 12 行里的第一个链接）—— **它从不看 `evaluation.md`**；
    - 各条检查自己在 `evaluation.md` 上跑一次 `LINK_LINE` —— 它只看那一个文件。

    实测活动用户 2026-08-30，316 份深评：

        链接在两处都有                249 份
        只在 `evaluation.md`（没话术） 37 份   ← `find_applications` 靠 posting 兜住
        **只在 `outreach.md`**        24 份   ← 检查那份看不见
        两处都没有（有话术文件）        5 份
        彻底没有                       1 份

    那 24 + 5 个的后果不是「报错」，是**判不了**：`sendable_state` 对空链接
    返回「对不上职位库」，于是它们既不算「还能发」也说不清是什么 ——
    上一版更把这一档静默并进了「已经出局」。

    `find_applications` 那份 332 个目录**全部**解析得出，所以这里只取它的结果。
    """
    import build_dashboard as _bd
    apps = ROOT / "users" / user / "documents" / "applications"
    return {a["dir"]: (a.get("url") or "") for a in _bd.find_applications(apps)}


#: 问句归一化：去掉数字和标点，只留骨架。两个岗上问同一件事，
#: 中间夹的公司名会不一样，但骨架一样。
_Q_SKELETON = (re.compile(r"[0-9０-９]+"), re.compile(r"[，。、；：？?！\s]+"))


def check_greeting_questions_are_about_this_job(seen, details) -> list:
    """开场白结尾那个问题，**在几个不同的岗上问的是同一句**。

    `06-outreach-templates.md`「结尾怎么收」那一节 2026-09-02 把渠道 1 的第三件事
    从「一个真问题」改成了「引导看简历」，问题降为例外，三条判据里第一条是
    「这句话里有一个词是从这个岗的 JD 里来的」。

    **那一条机械判不了**（要 JD 正文、要分词、要词频过滤，还会漏两字专名），
    但它有一个不需要判断力的推论：**同一句问话出现在两个以上不同的岗上，
    那它按定义就不是关于某一个岗的。** 这条只查这个推论。

    实测活动用户 2026-09-02（改之前）：321 个问句里 **39 句落在 17 个模子里**，
    最多的一句出现在 4 个不同的公司上。清完之后是 0。

    ## 为什么判「留意」不判「要修」

    存量话术里的问题多数已经发出去了，改不回来；而这个数的用处是**盯它别再涨** ——
    新出的一批里冒出重复问句，说明写手又开始套模板了。同族判据见
    `check_greeting_keeps_the_five_rules` 的「这个数说的是存量」。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    num, punct = _Q_SKELETON
    where = collections.defaultdict(list)
    for f in sorted(apps.glob("*/outreach.md")):
        g = _greeting_of(f.read_text(encoding="utf-8", errors="replace"))
        if not g:
            continue
        for s in re.split(r"(?<=[。！？?])", g):
            s = s.strip()
            if s.endswith(("？", "?")):
                where[punct.sub("", num.sub("N", s))].append(
                    (f.parent.name.split("_")[0][:16], s))
    dups = {k: v for k, v in where.items() if len(v) > 1}
    if not dups:
        return []
    n_q = sum(len(v) for v in dups.values())
    worst = max(dups.values(), key=len)
    eg = "、".join(sorted({w for w, _s in worst})[:3])
    return [("warn", "话术：开场白的问题在好几个岗上是同一句",
             f"{n_q} 个问句落在 {len(dups)} 个模子里，最多的一句出现在 "
             f"{len(worst)} 个岗上（{eg}）。同一句问话问好几家，"
             f"那它就不是关于某一个岗的 —— 对方看得出来。"
             f"原话：「{worst[0][1][:34]}」。"
             f"默认结尾不该是问题（见 06「结尾怎么收」）："
             f"删掉它、换成引导看简历，问题移进评估的「投前先问清楚」，"
             f"等对方回话再问。要重出这几份：/job-apply <职位链接>")]


def check_greeting_keeps_the_five_rules(seen, details) -> list:
    """开场白那五条铁律，此前**没有任何东西在验它**。

    `06-outreach-templates.md` 渠道 1 用一整张表列了「这 200 字里不许出现的五类」，
    每一类都配了实际写过的反例。规则写得很细 —— 而它是写给执行者看的散文，
    执行者每次凭记忆遵守，写完也没有人回头查。

    ## 名字里那个「五」是出处的数，不是它现在查几类

    判据走 `_cli.greeting_hits`，它现在盖三份规则：

        06 渠道 1 那张表        五类禁区（开场铺垫 / 钱 / 到岗时间 /
                                看不见的短处 / 给短处加引子 + 套话开头）
        03 的风格铁律          AI 味清单 + 句式（`_cli.style_hits`，
                                四个渠道通用，2026-08-27 拆出去共用）
        06「缺口」那一节        缺口不许排在匹配点前面
                                （`gap_before_evidence`，2026-08-27 补）

    函数名没跟着改：改名要动登记表、测试和好几处引用，而「五」指的是**出处**
    那张表，本身没有过期。这一段是为了让读到名字的人不必去数。

    实测活动用户 2026-10-09，**330 份开场白里 0 份踩线、共 0 处**
    （2026-09-01 那次量到的是 59 份、共 64 处，随后逐份重写清零）

    ## 99 是个印出来没人能动的数 —— 所以要分开报

    这条消息原来收尾是「这些是已经写好、**等着发出去**的文件，不是待办」。
    实测活动用户 2026-08-25 把那句话推翻了：

        踩线           102 份
        ├ 已经投出去了   72 份   ← 改也来不及
        ├ 你标了不投     13 份
        ├ 岗位已下线      3 份
        └ **还发得出去**  11 份   ← 只有这一档能动

    「等着发出去」对四分之三的文件是错的。而错法很贵：**一个基本动不了的数
    被印成待办**，读的人要么去改 102 份、要么整条忽略 —— 多半是后者，
    然后那 11 份也跟着被忽略。

    所以现在总数之外必须给出「还发得出去」那一格，并**点名**是哪几个。
    同族的前科：`check_referral_note_is_missing` 的「这个数说的是存量」、
    `_REQUEUE_SKIPPED` 的「会放回 N 个」与「另有 M 个故意没动」——
    这个仓库反复栽在同一件事上：**总数印出来了，能动的那批认不出来。**

    ⚠️ **对不上职位库的不算「还能发」。** 不知道就说不知道，别乐观地算进去 ——
    那一格单列，读的人才知道这几份是查不到状态，不是查到了还活着。


    （判据后来扩过两次。**这里不抄那个数** —— 现算值与它的来历都记在
    `_cli.greeting_problems` 的台阶里，那串台阶最后一格 2026-09-02 已经归 0。
    下面这张构成是 2026-08-24 那次的快照，留着是为了说明这几类各占多少）：

        开场铺垫 17 · 到岗时间 5 · 先谈钱 4 · 给短处加的引子 2

    逐条核过都是真的（**注意上面那张分档表**：这些多数已经发出去了，不是「等着发出去」）：

    - 「您好，我想应聘智能体平台资深产品经理。」—— 岗位名是对方写的，
      发消息当然是想聊。第一行是会话列表里唯一看得见的那行，被这句吃掉了。
    - 「想先问下薪资口径：30-50k 是按几薪算？」—— 那张表里逐字列着的反例。
    - 「已离职、随时到岗，期望 45-60k。」—— 期望薪资与到岗时间**两样都不写**
      是用户 2026-08-17 亲自裁定的，这一份两样都写了。

    ## 为什么判「留意」而不是「要修」

    改法是把那句话重写，没有 `--apply`。本仓库的「要修」都配一个机械修法，
    而 `test_pipeline_audit_stays_clean` 钉死零 error —— 判错级别的代价是
    那条测试长红，然后整个审计被当成背景噪音略过。同族的
    `check_company_claims_have_a_source`、`check_maybe_tier_has_questions`
    也都是这一级。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    hit, by = [], collections.Counter()
    #: 这一条**只看开场白那一段**。同一个文件里还有邮件 / 网申自评 / 求职信 /
    #: 内推请托几节，它们同样受 `03` 约束（`_cli.STYLE_BANS` 的注释写着
    #: 「眼下只有开场白这一处在机械查……这是覆盖不全，不是豁免。说出来，
    #: 别让『查过了』被误读成『四条渠道都查过了』」）—— 这里数一下它们有多少段，
    #: 好把这句话说得出口。
    #:
    #: **不给它们加检查器**：实测活动用户 2026-08-24，邮件 7 段、网申自评 7 段、
    #: 求职信 3 段，`03` 词表 **0 命中**。样本这么小，加一条检查等于空跑，
    #: 而空跑的检查会让人以为覆盖到了 —— 那正是这段注释要防的事。
    other = 0
    # 「这一份还发得出去吗」走 `sendable_state` —— 判定只有一个住址。
    _where = sendable_state(user, seen)
    _state = collections.Counter()
    _live_urls = []
    _live = []
    for f in sorted(apps.glob("*/outreach.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        other += len(re.findall(r"^#{1,3}\s*(?:邮件|网申自评|求职信|内推请托)",
                                text, re.M))
        g = _greeting_of(text)
        if not g:
            continue
        # **一份只记一次**：一句话同时踩两类（「已离职、随时到岗，期望 45-60k」
        # 就是到岗时间 + 钱）不该让「27 份」变成「32 份」——那一行数的是文件数。
        # 分档里两类都记，因为它答的是「主要犯哪一类」。
        # 判据走 `_cli.greeting_hits()` —— **和面板复制按钮旁那条提示同一份词表**。
        # 上一版这里自己写了一套正则，而 `export_web_data` 早就有一份词表：
        # 两份不一样，同一类（开场铺垫）一边数出 32 份、一边 17 份。
        # 顺带白捡了字数那一条：`greeting_problems` 一起查 200 字上限，
        # 我那份正则表里根本没有它。
        bad = sorted({cat for cat, _w in _cli.greeting_hits(g)})
        if len(re.sub(r"\s", "", g)) > _cli.GREETING_MAX:
            bad.append("超 200 字")
        if bad:
            hit.append(f.parent.name.split("_")[0][:16])
            by.update(bad)
            # **这一份还发得出去吗。** 见下面那段说明：不分开报的话，
            # 这个数会被当成待办，而四分之三根本动不了。
            _m = LINK_LINE.search(text)
            _w = _where(_m.group(1) if _m else "")
            _state[_w] += 1
            if _w == "还能发":
                _live.append(f.parent.name.split("_")[0][:16])
                if _m:
                    _live_urls.append(_m.group(1))
    if not hit:
        return []
    # **两份词表，两个出处，报的时候要分得开。**
    # `_cli.GREETING_BANS` 来自 `06` 渠道 1 那张「不许出现的五类」；
    # `_cli.STYLE_BANS` 来自 `03` 的「AI 味清单」，管的是所有对外文案。
    # 原来这句写死「那五类……判据见 06 那张表」—— 加进 `03` 那三类之后
    # 它当场就成了错话：报出 7 个类别，却把用户指去一张查不到「互联网黑话」的表。
    #
    # ⚠️ **「所有对外文案」是那张表的适用范围，不是这里的检查范围。**
    # 这个检查只扫开场白。简历、求职信同样是对外文案，而且更对外 ——
    # 它们没有被扫，**这是有意的**，不是漏了：
    #
    # 实测活动用户 2026-08-24，拿这张表去扫 17 份简历源文件（主简历 2 份 +
    # 定制版 15 份），命中 41 处，其中：
    #
    #     25 处落在 Typst 注释里 —— 全是「对齐」，说的是「两处列表没对齐」
    #                              「共用同一条对齐轴」，**永远不进 PDF**
    #     15 处是同一句话          —— 那句话被复制进了 15 份定制版，
    #                              按份计数会把一句话报成 15 个问题
    #      1 处是真的
    #
    # 也就是说**照着源文件扫，六成是排版注释**。真要接进来，输入得是
    # **渲染出来的文本**（`verify_pdf` 已经在取，记得带 `-enc UTF-8`），
    # 而且要按「不同的句子」去重、不按文件数。在那之前，别顺手加一条
    # 扫 `.typ` 的检查 —— 它会一直喊狼来了，然后被人整条关掉。
    #
    # 第三份判据是**正则**（`_cli.STYLE_PATTERNS`），出处是 `03` 里**另一节**
    # 「句式：中文不这么说」。和「AI 味清单」不是同一节，所以不能合着报：
    # 那一节列的是**词**，而句式换词换不掉 —— 把人指到词表那一节，
    # 他会在里面找一个查不到的东西，然后以为是误报。
    # **记一笔，别绕过收尾那两个集合。** 这条检查自己拼尾巴（要报完整的
    # 状态分布，`live_tail` 把那半压掉了），于是它的岗此前既不进
    # 「去重后 N 个岗」那个总数，也不进「要改已有内容」那一批 ——
    # 而重写一份开场白正是 `/job-apply 全部` **不做**的事。
    _cli.note_live(_live_urls, rewrite=True)

    _style = set(_cli.STYLE_BANS)
    hit_style = [k for k in by if k in _style]
    hit_pat = [k for k in by if k in _cli.STYLE_PATTERNS]
    where = "，以及 ".join(
        ["06-outreach-templates.md 渠道 1 那张表"]
        + (["03-writing-style.md 的「AI 味清单」"] if hit_style else [])
        + (["03-writing-style.md 的「句式：中文不这么说」"] if hit_pat else []))
    return [("warn", "开场白有不该出现的写法",
             f"{len(hit)} 份开场白踩了线"
             f"（{'、'.join(f'{k} {n}' for k, n in by.most_common())}）。"
             f"其中还发得出去的只有 {_state['还能发']} 份"
             f"（其余：{'、'.join(f'{k} {n}' for k, n in _state.most_common() if k != '还能发')}）"
             f"{'，就是这几个：' + '、'.join(_live[:4]) + '。' if _live else '。'}"
             f"第一行是会话列表里唯一看得见的那行，被铺垫吃掉就没了；"
             f"期望薪资与到岗时间是 2026-08-17 裁定两边都不写。"
             # 「判据见某某文件」不是下一步 —— 用户不知道该敲什么
             # （`AGENTS.md`「每一处引导都要写出该敲的命令」：指一个文件名不够）。
             # 重写一份开场白就是重跑那个岗，而那条命令是 `/job-apply <链接>`。
             #
             # **一份还能发的都没有时，别给命令**：那时这一整条报的是存量，
             # 给一条敲了也白敲的命令比不给更坏。那时退回原来那句「修：重写
             # 那一句」——它说的是改法，不假装有下一步。
             + (f"补它：一次一个跑\n    /job-apply {_live_urls[0]}\n  "
                if _live_urls else "修：重写那一句，")
             + f"判据见 {where}。"
             # 这句话直接上终端 —— 不带 markdown（`AGENTS.md`「给用户看的措辞」
             # 那条：从文件正文流向界面的字段要先剥 `**`）。实测加它的那一版
             # 是整份审计输出里唯一带星号的一行。
             + (f"（这一条只查开场白那一段。同一批文件里另有 {other} 段"
                f"邮件 / 网申自评 / 求职信 / 内推请托 —— 它们不受这五类禁区"
                f"约束（06 那段 ⚠️ 明说的），但同样受 03-writing-style.md 的"
                f"风格铁律约束，那一半由「对外文案：另外几个渠道的文风」"
                f"单独报。）" if other else ""))]


def check_other_channels_keep_the_style_rules(seen, details) -> list:
    """开场白之外那几段对外文案的文风 —— 此前一个检查器都没有。

    ## 五类禁区不管它们，风格铁律管

    `06-outreach-templates.md` 渠道 1 那张表末尾那句 ⚠️ 写得很清楚：
    「五条只管渠道 1。渠道 2（邮件）、3（网申自评）、4（求职信）不受此限 ——
    那些场合对方已经在读你的完整材料，谈条件、讲缺口都是正常的。」

    **但 `03-writing-style.md` 没有这个豁免。** AI 味、互联网黑话、翻译腔，
    在哪个渠道都不该有 —— 而这些段落此前**没有任何一处在查**
    （上一条自检的免责里自己写着这句）。

    ## 实测（2026-08-27）

    开场白之外还有 30 段：邮件正文 9、网申自评 9、内推请托 9、求职信 3。
    一查，**网申自评 9 段里 5 段踩线**（翻译腔 4、互联网黑话 1「闭环」），
    其余三个渠道 0 段。

    网申自评集中踩线不是巧合：那一段是**写给系统看的自述**，最容易滑进
    「正是我这两年在做的」这类自我认证句式 —— 而 `STYLE_PATTERNS` 那三条
    正则本来就是冲着它去的（判据：1486 份真人 JD vs 236 份我们写的）。

    ## 判据借的是同一份

    走 `_cli.style_hits`，与开场白那一条共用 —— 两处各写一份词表，
    同一个「闭环」迟早在一边算违规、另一边不算。
    """
    if not _USER:
        return []
    apps = ROOT / "users" / _USER[0] / "documents" / "applications"
    if not apps.is_dir():
        return []
    by = collections.Counter()
    per_channel = collections.Counter()
    seg_total = collections.Counter()
    samples = []
    for d in sorted(apps.iterdir()):
        f = d / "outreach.md"
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        segs = [(label, _named_section(text, label)) for label in
                ("邮件", "网申自评", "求职信", "内推请托")]
        for label, seg in segs:
            seg = seg.strip()
            # 太短的多半是「无」「见上」这类占位，不是一段文案
            if len(seg) < 20:
                continue
            seg_total[label] += 1
            hits = _cli.style_hits(seg)
            if not hits:
                continue
            per_channel[label] += 1
            for cat, _w in hits:
                by[cat] += 1
            if len(samples) < 4:
                samples.append(f"{d.name[:16]}的{label}（{hits[0][1]}）")
    if not by:
        return []
    n_bad = sum(per_channel.values())
    n_all = sum(seg_total.values())
    chans = "、".join(f"{k} {v}/{seg_total[k]} 段" for k, v in per_channel.most_common())
    cats = "、".join(f"{k} {v}" for k, v in by.most_common())
    return [("warn", "对外文案：另外几个渠道的文风",
             f"开场白之外的 {n_all} 段对外文案里，{n_bad} 段踩了 03 的风格铁律"
             f"（{cats}）。按渠道：{chans}。例：{'、'.join(samples)}。"
             f"这几段不受渠道 1 那五类禁区约束（06 那段明说的），"
             f"但 AI 味、互联网黑话、翻译腔在哪个渠道都不该有。"
             f"改它：对这几个岗重跑 /job-apply <职位链接>，"
             f"判据见 03-writing-style.md 的「AI 味清单」与「句式：中文不这么说」")]


def check_resume_body_keeps_the_style_rules(seen, details) -> list:
    """简历正文的文风 —— 四条对外渠道里最后一条没查的。

    ## 为什么拖到现在才接

    不是忘了，是**输入不对**。照 `.typ` 源文件扫（2026-08-24 实测 17 份、
    41 处命中）：

        25 处落在 Typst 注释里 —— 全是「对齐」，说的是「两处列表没对齐」
                                 「共用同一条对齐轴」，**永远不进 PDF**
        15 处是同一句话         —— 那句被复制进了 15 份定制版，
                                 按份计数会把一句话报成 15 个问题
         1 处是真的

    也就是说**六成是排版注释**。那时写下的方子是：要接就得拿**渲染出来的
    文本**当输入，并且**按不同的句子去重、不按文件数**。这一条就是照方子做的。

    ## 照方子做完的实测（2026-08-27）

    17 份 PDF（主简历 2 + 定制版 15）全部抽得出文本，**不同的句子里踩线的
    只有 5 句**：「AI 深度参与」那一句（空心动词）被复制进 12 份、另外三句
    各 1 份、外加一处「闭环」（互联网黑话）。

    41 → 5，而且每一句都指得出该改哪儿。

    ## 抽不出文本时说出来，别当成干净

    `pdftotext` 没装就报「这一条没查」——**不是「没问题」**。同族的
    「读不出薪资底线，这条没查」是一个写法。抽取走 `verify_pdf.run_tool`，
    那边已经把中文 Windows 上 `-enc UTF-8` 那个坑处理过了（不给它，
    抽出来的中文简历会变成一份「没有汉字」的文本，据此下的结论是灾难性的假警报）。
    """
    if not _USER:
        return []
    ud = ROOT / "users" / _USER[0]
    pdfs = sorted(ud.glob("resume/*.pdf")) + sorted(
        ud.glob("documents/applications/*/resume.pdf"))
    if not pdfs:
        return []
    import verify_pdf as _vp
    where = collections.defaultdict(set)      # 句子 -> 出现在哪几份
    what = {}                                  # 句子 -> (类别, 认出来的写法)
    escapes = []                               # (文件名, 上下文)
    n_read = 0
    for f in pdfs:
        try:
            text = _vp.run_tool(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(f), "-"])
        except _vp.VerificationError as exc:
            if getattr(exc, "missing_tool", None):
                return [("warn", "简历正文的文风这一条没查",
                         f"{exc} —— 判据要拿渲染出来的文本当输入，"
                         f"照 .typ 源文件扫六成是排版注释。"
                         f"装上 poppler 之后这一条会自己跑起来")]
            continue                            # 单份读不了就跳过，别拖垮整条
        n_read += 1
        for line in re.split(r"[。！？\n]", text):
            line = line.strip()
            if len(line) < 6:
                continue
            hits = _cli.style_hits(line)
            if hits:
                where[line].add(f.parent.name if f.name == "resume.pdf" else f.name)
                what[line] = hits[0]
            if "\\" in line:
                _i = line.index("\\")
                escapes.append((f.parent.name if f.name == "resume.pdf" else f.name,
                                line[max(0, _i - 10):_i + 12]))
    out = []
    if escapes:
        # **反斜杠印到纸上了。** Typst 正文里的 `\+` 会渲染成一个可见的
        # 反斜杠 —— 而同一个符号在高亮正则串里（`\\+`）是对的，抄来抄去
        # 就混进了正文。这类错**编译不报**、预览不细看也不显眼，
        # 而读到它的是招聘方。
        #
        # 实测活动用户 2026-08-27：17 份 PDF 里 1 份中招（长版印着
        # 「1 万\+ GitHub stars」），当天改掉了。这条留着防下一次。
        e_rows = "；".join(f"{f}：…{ctx}…" for f, ctx in escapes[:3])
        e_more = f"，另有 {len(escapes) - 3} 处" if len(escapes) > 3 else ""
        out.append(("warn", "简历正文：反斜杠印到纸上了",
                    f"{len(escapes)} 处渲染出来的文字里带着反斜杠：{e_rows}{e_more}。"
                    f"Typst 正文里的转义符会原样印出来（高亮正则串里的写法是对的，"
                    f"两者别抄混）。改它：把源文件里那处的反斜杠去掉，重新 typst compile"))
    if not where:
        return out
    rows = []
    for sent, files in sorted(where.items(), key=lambda kv: -len(kv[1]))[:3]:
        cat, w = what[sent]
        many = f"（这一句在 {len(files)} 份里）" if len(files) > 1 else ""
        # 行文走 `_cli.style_row`（面板那条同一个函数）；「这一句在 N 份里」
        # 是自检独有的一层（它扫全部定制版），接在后面。
        rows.append(_cli.style_row(cat, w, sent) + many)
    more = f"，另有 {len(where) - 3} 句" if len(where) > 3 else ""
    return [("warn", "简历正文：有 03 说要改写的写法",
             f"{n_read} 份简历 PDF 里，{len(where)} 句踩了 03 的风格铁律"
             f"（按句子数，不按文件数 —— 同一句被复制进十几份定制版是常态，"
             f"按份数会把一句话报成十几个问题）：{'；'.join(rows)}{more}。"
             f"改它：先改主简历 resume/main.typ，再跑 /job-resume 复核；"
             f"定制版那几份下次 /job-cv 时会跟着重出。"
             f"判据见 03-writing-style.md 的「AI 味清单」与「句式：中文不这么说」")] + out


def check_maybe_tier_has_questions(seen, details) -> list:
    """「可以考虑」的深评里必须有「投前必问」——**那一节就是这一档的定义**。

    `04-job-evaluation.md` 给这一档的定义是「先问清楚关键信息再决定投不投」。
    也就是说：**问什么，就是这一档存在的理由**。没有那份清单，它和「值得投」
    在面板上就没有区别 —— 而实测他已经这样把 26 个这一档的岗直接发了出去，
    占全部投递的三成。

    实测活动用户 2026-08-22：99 个有材料的「可以考虑」里，只有 52 份深评真有
    那一节。面板那枚章的悬浮说明写着「评估里列了这个岗还没弄明白的地方」——
    **对另外 47 个，这句话是假的**。（章已经拆成两种说法，见 `Shortlist.tsx`；
    这里管的是源头。）

    ## 「有标题、写着一条『无』」和「没有这一节」是同一件事

    2026-08-24 之前这条只看标题在不在，于是那 74 个整节只有一条「无」的岗
    （其中 39 个正是这一档）被算成「有」。用户展开它看到的是一条写着「无」
    的待问事项 —— 比空着更糟：空着这一节不渲染，写「无」长得和真问题一样。
    判据借导出那一侧的 `parse_ask_before`，不在这儿另定「什么算空」。

    这一节是后来才写进 04 的输出格式的（`_ASK_RULE_SINCE`），所以存量里缺很正常。
    **这条检查看的是往后**：新出的深评还漏，说明规则又只写在了一个地方。
    只查「可以考虑」——别的档位没有这个要求，一并查会造出一堆假阳性。

    ## 趋势那半句必须按规则生效日切

    第一版报的是「最近 30 份里缺 22 份（73%）——不是存量遗留，新出的更差」。
    实测 2026-08-23 一查：268 份深评最新的一份写于 **08-19**，而这一节
    **08-22** 才进输出格式 —— **一份规则之后的产出都没有**。
    那句话把存量说成了规则不灵，读的人会去重写一条还没被执行过的规则。

    所以分母按 `_ASK_RULE_SINCE` 切：生效后一份都没有就直说
    「这个数说的是存量」；有了 ≥10 份才谈执行率，且**只用那一批当分母**。
    """
    import export_web_data as _ex
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    n = miss = 0
    recent = []          # (文件时间, 有没有那一节) —— 算「最近 N 份」的执行率
    # **点名还能动的那几个。** 只印总数的话，读的人做不了任何事 ——
    # 这一课的完整账在 `check_greeting_keeps_the_five_rules` 的 docstring 里
    #（实测四分之三的文件已经投出去或标了不投，改也来不及）。
    # 判定走 `sendable_state`，和那条检查同一个住址。
    live = []          # (链接, 目录名)；还能不能动交给 `_cli.live_tail` 判
    urls = dir_urls(user)
    for f in sorted(apps.glob("*/evaluation.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        # **判词看结论那一节，不看正文里出现过这四个字。**
        # 原来写的是 `if "可以考虑" not in t`，而评估正文里提一句
        # 「上一轮给了 63『可以考虑』」「比另一个岗更可以考虑」都会命中。
        # 实测活动用户 2026-08-23：命中 144 份，其中结论真是这一档的只有 108 份
        # —— 另外 6 份是「值得投」、3 份「不建议」，那两档本来就不要求写
        # 「投前必问」，进分母就是假阳性。
        #
        # **这条一律判「留意」，不按缺失率升 error。**
        #
        # 原来写着「≥50% 升级成 error」，而同一份文件里
        # `check_greeting_keeps_the_five_rules` 的「为什么判留意而不是要修」
        # 逐字点了这条的名：「本仓库的『要修』都配一个机械修法……同族的
        # `check_company_claims_have_a_source`、`check_maybe_tier_has_questions`
        # 也都是这一级」。两处一直对立，只是缺失率 46% 卡在门槛下面，
        # 没人撞见。
        #
        # 2026-08-24 撞见了：这条开始把「整节只写一条『无』」也算缺（此前
        # 只看标题在不在），缺失率 61/130 → **100/130（77%）**，当场升成 error。
        # 而它**依然没有机械修法** —— 改法是重写那份评估，没有 `--apply`。
        # `test_the_backlog_does_not_hide_the_trend` 早就把判据写下了：
        # 「一个永远红的审计会被当噪音略过。报出来让人看见，不劫持构建。」
        #
        # 所以解的是那个矛盾，不是把数字调回门槛以下。
        # 解析走 `build_dashboard.parse_evaluation`（判词解析的正本，
        # 它自己的 docstring 记着为「只认一种写法」踩过三次坑）。
        # 判据走 `ask_before_missing`（正本）—— 写盘时那道闸门用的是同一个
        # 函数，两处不许各判各的。上面那几段实测记录跟着判据搬进了它。
        gone = ask_before_missing(t)
        if gone is None:
            continue
        n += 1
        ok = not gone
        if not ok:
            miss += 1
            # 同上：链接走 `dir_urls`，不在这儿自己搜。
            live.append((urls.get(f.parent.name, ""), f.parent.name))
        recent.append((_eval_date(t), f.parent.name, ok))
    if not n or not miss:
        return []
    rate = miss / n
    # 「最近 N 份」按**深评自己写的评估日期**排（同日的按目录名，稳定即可）。
    # 不用日期窗口切：抓取节奏时密时疏，停跑几天就会拿到一个空样本，
    # 然后这半句静默消失。
    # 同上：只按 (日期, 目录名) 排，别让 `ok` 当次级键（那会让「最近 N 份」
    # 全落在同日里没写的那一侧）。
    recent.sort(key=lambda r: r[:2])
    after = [ok for d, _k, ok in recent if d and d >= _ASK_RULE_SINCE]
    tail = [ok for _d, _k, ok in recent[-RECENT_EVALS:]]
    newest = max((d for d, _k, _ok in recent if d), default="")
    if not after:
        # **规则之后一份都还没产出。** 这时候任何「最近 N 份」都只是在拿存量
        # 自比，说不出规则灵不灵 —— 把这件事直说，别让人去重写一条还没被
        # 执行过的规则。
        trend = (f"这 {n} 份——全部产于规则之前"
                 f"（最新一份 {newest or '日期缺失'}，而这一节 {_ASK_RULE_SINCE} "
                 f"才进 04 的输出格式）——这个数说的是存量，"
                 f"说明不了规则灵不灵，跑一批新的才有得比。")
    elif len(after) >= 10 and after.count(False):
        # 有了规则之后的样本才谈执行率，**分母只取那一批**。
        trend = (f"规则生效后的 {len(after)} 份里仍缺 {after.count(False)} 份"
                 f"（{after.count(False) / len(after):.0%}）——"
                 f"这一条是新出的，不是存量。")
    elif len(after) >= 10 and not after.count(False):
        # **下限和上面那支同一个 10。** 只有这一支没有地板时，一份合规的深评
        # 就够打出「缺的都是存量」这句定论；而同样一份不合规什么也说不出来
        # （悲观那支要 10 份）—— 这句话于是**结构上只可能往好的方向出现**。
        trend = f"规则生效后的 {len(after)} 份都写了，缺的都是存量。"
    elif len(tail) >= 10 and tail.count(False):
        # 生效后样本不足 10 份，只能报个规模，**不下「新出的更差」这种断语**。
        trend = (f"其中最近 {len(tail)} 份里缺 {tail.count(False)} 份"
                 f"（{tail.count(False) / len(tail):.0%}）；"
                 f"规则生效后只有 {len(after)} 份，还不够看趋势。")
    else:
        trend = ""
    # 印一个总数、不说该敲什么，等于把活原样退回去（`AGENTS.md`
    # 「每一处引导都要写出该敲的命令」）。补一节要重跑那份深评，
    # 而 `/job-apply <职位链接>` 就是重跑一个岗的那条。
    _live, todo = _cli.live_tail(user, seen, live)
    if _live:
        todo += "想一次补完这一档：/job-apply 可以考虑（已有材料的只补缺的那一节）。"
    return [("warn", "「可以考虑」的深评没写要问什么",
             f"{miss}/{n} 份（{rate:.0%}）缺「投前必问」那一节。{trend}这一档的定义就是"
             f"「先问清楚再决定投不投」——没有那份清单，它和「值得投」"
             f"在面板上就没有区别，而那正是他把 26 个这一档的岗直接发出去的原因。"
             f"{todo}")]


def check_edu_field_cannot_close(seen, details) -> list:
    """学历字段仍然不配有结案权——拿全部 JD 正文重算误杀率。

    `prescreen` 把 `--edu-floor` 定成「只降权、不结案」，依据是 12 个岗的实测
    误杀 58%。**一个 12 样本的数撑着一条规则**，语料涨到 1485 份之后该复核。

    这里就是那次复核的机制版：口径与原注一致——分母是**规则会命中的全部**，
    凡不能从正文确认硬性要硕博的都算误杀（包括「正文压根没写学历要求」，
    那是判不了，不是判过了）。

    ⚠️ 不要改成量「字段与正文是否一致」：那个口径给出 93% 一致，看着像可以结案了，
    而它把最大的一类（正文没写要求）整个排除在分母外。要量的不是字段准不准，
    是**照它结案会杀掉多少能投的岗**。
    """
    floor = "本科"
    fires = kill = 0
    for e in seen.values():
        lv = next((L for L in _EDU_ORD if L in str(e.get("eduLevel") or "")), None)
        if not lv or _EDU_ORD[lv] <= _EDU_ORD[floor]:
            continue
        body = (details.get(e.get("url")) or {}).get("description") or ""
        if len(body) < _cli.JD_MIN_BODY:
            continue
        fires += 1
        m = _EDU_REQ.search(body)
        hard = bool(m and _EDU_ORD[m.group(1)] > _EDU_ORD[floor]
                    and not _EDU_RELAX.search(body))
        if not hard:
            kill += 1
    if fires < 30:
        return []                       # 样本太小，说不出话来
    rate = kill / fires
    if rate <= EDU_KILL_CEILING:
        return [("warn", "学历字段的误杀率降下来了",
                 f"{fires} 个命中里只误杀 {kill}（{rate:.0%}），低于 "
                 f"{EDU_KILL_CEILING:.0%}。当初定「只降权」的依据是 58%——"
                 f"依据变了就该重新裁定，别让规则和它的理由脱节")]
    return []


def check_gate_fail_blocks_the_verdict(seen, details) -> list:
    """有一道硬门判 FAIL，判词就不能还是可投档——页面会自相矛盾。

    面板在硬门区上方印着「有一条不满足就别投」，紧挨着判词徽章。两者打架时
    用户信哪个都不对。

    2026-08-20 实测抓到 2 个：状态格写的是「待确认，**不判 FAIL**」，而
    `gate_state` 按子串撞见 FAIL 就判不满足——**被否定掉的判定词被当成了判定词**。
    `GATE_RULES` 的排序只挡得住「FLAG，非 FAIL」那一种（FLAG 排在前面先命中），
    没有 FLAG 托底的写法就漏了；全库 57 处否定写法里 12 处没有 FLAG。
    根因修在 `gate_state`（先剥否定再匹配），这里是不变量兜底：
    **不管解析器将来怎么改，fail 与可投档不能同时成立。**
    """
    import export_web_data as ex
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    # 判词走导出侧那个**白名单**判据，别在这儿再造一个集合——
    # `is_sellable` 的注释里写着它为什么是白名单（黑名单两天漏进来两次）。
    by_url = {_cli.norm_url(e.get("url") or ""): e for e in seen.values()}
    bad = []
    for f in sorted(apps.glob("*/evaluation.md")):
        text = f.read_text(encoding="utf-8")
        fails = [g for g in ex.parse_gates(text) if g.get("state") == "fail"]
        if not fails:
            continue
        m = LINK_LINE.search(text)
        e = by_url.get(_cli.norm_url(m.group(1))) if m else None
        verdict = (e or {}).get("rank_verdict") or ""
        if ex.is_sellable(verdict):
            bad.append(f"{f.parent.name[:30]}  判词「{verdict}」"
                       f"却有硬门 FAIL：{'、'.join(g['name'] for g in fails)}")
    # **硬门 FAIL 有两个住址，两个都要查。** 上面读的是 `evaluation.md` 里那张表；
    # 职位库的 `rank_breakdown["硬性条件"]` 是另一份，此前没有一处读它。
    #
    # 实测代价（2026-08-28，就是这条流程自己）：执行者在库里把一个岗单边改判成
    # 硬门 FAIL，`writeback --apply` 从 `evaluation.md` 把**分数和判词**顶了回来
    # —— 那是对的（存档是事实源），但它不碰 `硬性条件` 与 `依据`，于是留下
    # 「硬门 FAIL 配判词值得投」的混合状态，而这条检查一声没吭：它读的是文件，
    # 而那个 FAIL 只写在库里。
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        g = (e.get("rank_breakdown") or {}).get("硬性条件") or {}
        fails = [k for k, v in g.items() if str(v).upper() == "FAIL"]
        verdict = str(e.get("rank_verdict") or "")
        if fails and ex.is_sellable(verdict):
            bad.append(f"{(e.get('title') or '?')[:26]}  判词「{verdict}」"
                       f"却有硬门 FAIL：{'、'.join(fails)}（这份写在职位库里，"
                       f"不在 evaluation.md）")
    if not bad:
        return []
    return [("error", "硬性条件不满足却仍判可投",
             f"{len(bad)} 个岗自相矛盾——面板会同时印「有一条不满足就别投」和可投判词："
             + "；".join(bad[:4]))]


def check_claimed_reads_are_stored(seen, details) -> list:
    """判词自称「读过 JD 正文」，库里却查无此条。

    **最难自己冒头的一类**：`needs_recheck` 按 `来源` 措辞判，而这些条目的措辞
    恰恰是最可信的那一档，于是从复核队列里整个漏出去（2026-08-20 实测 283 个，
    旧口径一个都不认）。判词看起来有据，证据其实没了。
    """
    import jd_store as st
    have = {_cli.norm_url(j.get("url")) for j in details.values() if st.has_body(j)}
    bad = [e for e in seen.values()
           if "读过 JD" in str((e.get("rank_breakdown") or {}).get("来源") or "")
           and _cli.norm_url(e.get("url")) not in have]
    if not bad:
        return []
    # 复核队列认不认得它们？认得就只是待办（warn），认不得才是漏洞（error）。
    import fetch_details as fd
    user = _cli.pick_user("", root=ROOT)
    seen_by_recheck = sum(1 for e in bad if fd.judged_without_stored_body(user, e))
    wired = seen_by_recheck >= len(bad) * 0.9
    # **「够得着的」是几个，得说出来。**
    #
    # `fetch_details` 只收猎聘（它自己的 docstring：「⚠️ **只收猎聘。** 其余渠道的
    # JD 只能在抓取当次的浏览器访问里取」），而这批岗是跨渠道的。原来这句话写的是
    # 「会把够得着的补回来」——一个不带数的限定词，读的人只会把它读成「都能补」，
    # 然后等一批永远补不完的账。
    #
    # 实测活动用户 2026-08-25：256 个里 **193 个是猎聘**（够得着），
    # **63 个在 BOSS / 智联 / 前程**（这个工具一个都碰不到）。
    #
    # 那 63 个不是没救，是**另一条路**：下次 `/job-scrape` 抓到它们时顺手落库。
    # 不说清楚的话，跑完 `--recheck --apply` 会显得「补完了」，而实际差着四分之一
    # ——`fetch_details.missing_by_portal()` 存在的理由就是这句话，
    # 这里只是把同一件事也说给审计的读者听。
    #
    # 判据借那边的：portal 是不是 `liepin-search`。**不在这儿另写一套渠道表**。
    # **这一批刚判的那几个，收尾要当场看见。**
    #
    # `run()` 的说明把这条检查点名成「最典型的」那一例：「浏览器读来的正文
    # 只活在读它的那一刻，当批发现只要跑一次 `jd_store.py --save`，
    # 全量跑完再发现就得重开页面」。**而它进不了那一档** ——判据是「调没调过
    # `sendable_state`」，这条不调。理由写在那儿、例子也写在那儿，就是没接上。
    #
    # 2026-08-31 用第二个信号接上（`_cli.note_round_scoped()`）。
    # **只为这一批喊**：存量补不回来，收尾印它只会把还来得及的淹掉。
    # 「这一批」按 `rank_date` 算，跨午夜那一轮的尾巴由 `_MIDNIGHT_GRACE_H` 兜住 ——
    # 与 `--sections` 那道闸门同一个窗口，不另立一套。
    fresh = [e for e in bad if _in_this_batch(e.get("rank_date") or "")]
    if fresh:
        _cli.note_round_scoped()
    reach = sum(1 for e in bad if (e.get("portal") or "") == fd.CLI_PORTAL)
    out_of_reach = len(bad) - reach
    tail = ""
    if out_of_reach:
        by = collections.Counter((e.get("portal") or "?") for e in bad
                                 if (e.get("portal") or "") != fd.CLI_PORTAL)
        tail = (f"另有 {out_of_reach} 个这个工具够不着"
                f"（{'、'.join(f'{k} {v}' for k, v in by.most_common(3))}）"
                f"——浏览器渠道的 JD 只能在抓取当次取，"
                f"下次跑 /job-scrape 抓到它们时顺手落库。")
    return [("warn" if wired else "error", "结论自称读过 JD，库里却没有",
             f"{len(bad)} 个岗的判词写着「读过 JD 正文」，而详情库查无此条——"
             f"读完在会话里扔了。"
             + (f"其中 {len(fresh)} 个是这一批刚判的 —— 正文现在多半还在"
                f"手上，当场跑 `python tools/jd_store.py --save <职位链接> --apply`，"
                f"就存下了；等这一轮过去就得重开页面。" if fresh else "")
             + (f"复核队列认得其中 {seen_by_recheck} 个，其中 {reach} 个 "
                f"`fetch_details --recheck --apply` 补得回来 —— "
                f"但先跑一次不加 `--apply` 的试运行看账单 —— "
                f"这一批按每次隔几秒发，几十分钟量级，而且抓回正文之后"
                f"那些判定还要人工重审（判据见 `job-rank.md`"
                f"「回头补 JD」那一节）。" + tail
                if wired else
                "而且复核队列也认不出它们——没有任何人知道该去补。"))]


def check_posting_snapshots_are_self_contained(seen, details) -> list:
    """材料目录的 JD 快照必须自带正文——**归档不能依赖工作缓存**。

    `posting.md` 存在的理由写在 `job-apply.md`：「职位下线后 URL 即失效，而面试
    通常在投递后二至三周发生，没有快照届时无法回查」。而实测（2026-08-20）
    284 份里 163 份取不回 JD：79 份写着「JD 正文见 job_scraper/details/」却
    指向空处，84 份两样都没有。

    悬空指针比坦白没有更糟——它看起来像存过。所以两种分开报。
    """
    import re
    import jd_store as st
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    have = {_cli.norm_url(j.get("url")) for j in details.values() if st.has_body(j)}
    dangling, missing, total = [], [], 0
    for p in apps.glob("*/posting.md"):
        total += 1
        text = p.read_text(encoding="utf-8")
        body = text.split("JD 原文")[-1] if "JD 原文" in text else ""
        if len(body.strip()) >= 200:
            continue                                  # 自带正文，稳
        if "本轮没取到 JD" in text or "没取到 JD 正文" in text:
            continue                                  # 坦白没有，可接受
        m = re.search(r"(?:链接|原始链接)[：:]\s*(\S+)", text)
        url = _cli.norm_url(m.group(1)) if m else ""
        (dangling if (url and "details" in text) else missing).append(p.parent.name)
    out = []
    if dangling:
        out.append(("error", "JD 快照的指针悬空",
                    f"{len(dangling)}/{total} 份 posting.md 写着「JD 正文见 details/」，"
                    f"而详情库里没有那条——职位一下线，原文永远找不回来。"
                    f"例：{dangling[:3]}"))
    if missing:
        out.append(("warn", "JD 快照里没有正文",
                    f"{len(missing)}/{total} 份 posting.md 既不带 JD 正文、也没说明"
                    f"「本轮没取到」。能补的用详情库补，补不了的把话写明。"
                    f"例：{missing[:3]}"))
    return out


def _min_years(field: str):
    """平台标的年限要求 → **下限**。读不出返回 None —— 不猜。

    猎聘的取值是一小撮固定串：`经验不限` / `1-3年` / `3-5年` / `5-10年` /
    `10年以上` / `N年以上`。取下限而不是上限：硬门问的是「够不够」。
    """
    s = (field or "").strip()
    if not s:
        return None
    if "不限" in s:
        return 0
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _candidate_years():
    """`candidate.md` 的「工作年限说明」→ (总年限, 方向年限)。读不出返回 None。

    自由文本，只认「N 年」这种最稳的写法，月份忽略——硬门这一侧宁可少报不可多报。
    """
    if not _USER:
        return None
    p = ROOT / "users" / _USER[0] / "profile" / "candidate.md"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "工作年限" not in line:
            continue
        nums = [int(m) for m in re.findall(r"(\d+)\s*年", line)]
        if len(nums) >= 2:
            return (max(nums), min(nums))
    return None



#: 「有月薪、没标几薪」的岗，`04` 给薪资维的那两个取值。
#: 12 薪折算够不着底线、按 16 薪能够着 → **55**（并挂「⚠ 先问几薪」）；
#: 16 薪都够不着才给 **25**。
_MONTHS_MID, _MONTHS_LOW = 55, 25

#: 薪数未知时按哪个薪数估「最乐观能不能过底线」。正本在 `_cli`。
#: 这里原来重抄了一份 16，理由写的是「不 import prescreen（它跑起来会解析
#: 命令行参数）」—— 那个理由对的是**别 import prescreen**，不是**得再写一个数**：
#: `_cli` 本来就已经被 import 了。2026-08-30 收成一处。
_OPTIMISTIC_MONTHS = _cli.OPTIMISTIC_MONTHS


def _annual_floor():
    """`candidate.md` 薪资小节里的「可接受底线」年包（万）。读不出返回 None。

    自由文本，只认最稳的写法（「可接受底线」那一行里的「年包 N 万」），
    读不出就如实说没查 —— 同 `_candidate_years`。

    ## 这个数和预筛传给 `prescreen.py --annual-floor` 的**有意不同**，别去统一

    资料里常有两个数：常规的「可接受底线」，加一句「方向极对的岗可以降到 X 谈」。

    - **这里读常规那个（高的）。** 用途是**打分**：`04-job-evaluation.md` 的
      「有月薪、但没写几薪」拿它当基准分档。弹性是谈判姿态，不是打分输入。
    - **预筛传最宽那个（低的）。** 用途是**淘汰**，而且是四条规则里唯一能结案
      的（不可逆）；预筛只有标题和薪资串，判不了方向极不极对，用常规底线误杀的
      恰好是弹性条款要保护的那批（判据在 `job-auto.md` 的参数出处表）。

    两个用途的错误代价方向相反：打分错了还能重评，结案错了那个岗就没了。
    所以**看到两处数字不一样不是 bug**，把它们改成同一个才是。
    """
    if not _USER:
        return None
    p = ROOT / "users" / _USER[0] / "profile" / "candidate.md"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "可接受底线" not in line:
            continue
        m = re.search(r"年包\s*[*]*\s*([\d.]+)\s*万", line)
        if m:
            return float(m.group(1))
    return None


def _annual_expect():
    """`candidate.md` 薪资小节里的「期望区间」年包（万），返回 `(下沿, 上沿)`。

    读不出返回 None —— 同 `_annual_floor` / `_candidate_years`：**「没查」和
    「查过没有」是两件事**，读不出就如实说没查，不拿一个默认值顶上。

    只认最稳的写法（「期望区间」那一行里的「年包…N-M 万」）。这个数是
    `04-job-evaluation.md`「打分口径：比的是够不够」那张表的两个上档边界，
    和 `_annual_floor()` 的底线一起，把薪资维的取值锁死成四个数。
    """
    if not _USER:
        return None
    p = ROOT / "users" / _USER[0] / "profile" / "candidate.md"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "期望区间" not in line:
            continue
        m = re.search(r"年包[^\d]{0,4}([\d.]+)\s*-\s*([\d.]+)\s*万", line)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            return (min(lo, hi), max(lo, hi))
    return None


def _pay_row(text: str):
    """深评里「薪资与职级」那一行的分数。取不到返回 None。"""
    m = re.search(r"^\|\s*[*]*薪资与职级[*]*\s*\|\s*[*]*([^|*]+?)[*]*\s*\|",
                  text, re.M)
    if not m:
        return None
    n = re.match(r"(\d+)", m.group(1).strip())
    return int(n.group(1)) if n else None


def _annual_high_12(entry: dict):
    """按 12 薪折的年包上沿（万）——**只在「平台没给可信薪数」时返回数**。

    折算走 `ex.annual_package`，与面板显示的是同一个实现（这个仓库为
    「同一个数两份实现」付过好几次学费）。
    """
    import export_web_data as ex          # 函数内 import，同本文件其余几处
    pkg = ex.annual_package(entry.get("salary") or "", entry.get("salaryMonths"))
    if not pkg or not pkg.get("assumed12") or pkg.get("high") is None:
        return None
    return pkg["high"]


def check_unknown_months_is_not_a_death_sentence(seen, details) -> list:
    """月薪够、只是没写几薪的岗，被薪资维 25 分埋掉了。

    国内一半的岗只写月薪、不写几薪（实测活动用户 2026-08-24：2637 个岗里
    **1308 个没有 `salaryMonths`**）。这种情况的判据在
    `04-job-evaluation.md` 的「有月薪、但没写「几薪」」，写得极死：

    （⚠️ 上面那句引用**必须留在同一行里**：`test_cross_references_resolve` 按
    「某文件的『某节』」这个形状去核，节名被换行截断就查无此节 —— 实测当场报断链。）

    > **但打分不许用假设值把岗埋掉**：12 薪折算值已 ≥ 底线 → 正常取档；
    > 12 薪折算值低于底线、而按 16 薪估**能**过底线 → 这一维给 **55** 并打强制
    > 「⚠ 先问几薪」标志，**不给 25**；16 薪都过不了底线的才给 25。

    它甚至配了一整节讲为什么（「披露越多，分不能越低」）。**而没有任何东西在验它。**

    实测活动用户 2026-08-24：落在这一档的 **12 个岗，12 个全给了 25**，
    「⚠ 先问几薪」标志**一个都没有**。薪资维 25 → 55 是 30 分 × 25% 权重
    = 综合分 7.5 分，实测其中 2 个直接从「可以考虑」翻到「值得投」、
    另有 2 个正好压在 60 分线上。

    ## 根因不在执行者，在派活的那份枚举

    `job-rank.md` Step 2 派批量评分代理时，精简口径里原来只有
    「期望薪资区间与底线」—— 一条裸底线。代理拿着它按 12 薪折出 36 万、
    对着 45 万的底线给 25 分，**它是对的，因为它没被告知还有另一档**。
    2026-08-24 把那条规则一起写进了那份枚举。

    ## 为什么是 warn 而不是 error

    **这一条 2026-08-30 换了修法。** 原来写的是「深评只能逐个 `/job-apply
    <链接>` 重跑，没有机械修法」—— 对**判断**那部分至今成立，但这一条盯的
    薪资维不是判断，是 04 那张四行的查表：`python tools/score.py --deep --apply`
    连 `evaluation.md` 一起改，一次跑完。分界是**这一维要不要读 JD 才知道**，
    不是「粗筛还是深评」。
    判断那一级（「深评缺小节」「年限门挡掉的其实是领域经验」「话术抬头」）
    仍然只能 `/job-apply`。
    """
    floor = _annual_floor()
    if floor is None:
        return [("warn", "读不出薪资底线，这条没查",
                 "`candidate.md` 的「可接受底线」那一行里解析不出年包数，"
                 "所以「没标薪数的岗有没有被 25 分埋掉」这一档没查 —— 不是没有。"
                 "补一句「可接受底线：… （年包 N 万）」就能查")]
    if not _USER:
        return []
    apps = ROOT / "users" / _USER[0] / "documents" / "applications"
    if not apps.is_dir():
        return []
    by_url = {_cli.norm_url(e.get("url")): e for e in seen.values()
              if isinstance(e, dict) and e.get("url")}
    bad = []
    for f in sorted(apps.glob("*/evaluation.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = LINK_LINE.search(text)
        e = by_url.get(_cli.norm_url(m.group(1))) if m else None
        if e is None:
            continue
        hi12 = _annual_high_12(e)
        if hi12 is None:
            continue
        if not (hi12 < floor <= hi12 / 12 * _OPTIMISTIC_MONTHS):
            continue
        if _pay_row(text) == _MONTHS_LOW or "先问几薪" not in text:
            bad.append((f.parent.name, e.get("salary") or "?"))
    if not bad:
        return []
    return [("warn", "没标薪数的岗被薪资分埋掉了",
             f"{len(bad)} 份深评里，月薪没写几薪、按 12 薪折算够不着 {floor:g} 万"
             f"底线、而按 {_OPTIMISTIC_MONTHS} 薪能够着 —— 04 规定这一维给 "
             f"{_MONTHS_MID} 并挂「先问几薪」，不给 {_MONTHS_LOW}。"
             f"两者差 30 分 × 25% 权重 = 综合分 7.5 分，足以翻一整档。"
             f"例：{'、'.join(f'{n[:14]}（{t}）' for n, t in bad[:3])}。"
             f"修：跑 python tools/score.py --deep --apply"
             f"（它连 evaluation.md 一起改；剩下的会如实报「存档和库对不上」，"
             f"那几个才要人看）")]

def check_negotiable_salary_is_not_scored(seen, details) -> list:
    """薪资写着「面议」，薪资那一维却给了个分。

    `04-job-evaluation.md` 对这件事有一条明确规定：

    > **薪资面议**：`salary` 为「薪资面议」时，这一维**不打分**，标记为「信息缺失」
    > ——面议本身是个信号，意味着薪资弹性大或不愿公开。

    **规则写了，没有东西验它。** 实测活动用户 2026-08-23：21 个面议岗里 19 个
    照做了，2 个打了分 —— 其中一个给了 **0**。

    ## 为什么 0 比「随便给个数」更坏

    0 的意思是「薪资很差」，而真相是「不知道」。同一份文档算过这笔账：
    面议不计入、权重重分配 → 总分 76；照打 → 63。实测那个 0 把总分压到 45、
    判词落到「不建议」—— 一个可能不错的岗，因为对方没公开薪资而出局。

    另一个更隐蔽：薪资维写了 58，而它自己的依据里写着
    「薪资面议（这一项不计入，分数按其余三项算）」——**数和它的解释自相矛盾**，
    读的人不知道该信哪个。

    判据：**串非空、且一个数字都没有** —— 平台明写了「面议 / 另议 / 详谈」这类。
    不枚举写法（枚举必漏），但也**不把空串算进来**。

    ⚠️ **空 ≠ 面议。** 空只说明列表页没抓到这个字段，而深评是读过 JD 正文的 ——
    实测有一个岗列表薪资为空、评估里明写着「25-35k·15薪」，薪资维 46 完全正确。
    第一版直接用 `_cli.salary_unstated`（它把 `None` 也算「给不出数」）判，
    把这种合法情形报成了违规。**判不准的扫描器比没有更坏**，这个仓库为此删过一个。
    """
    hit = []
    for _k, e in seen.items():
        if not isinstance(e, dict):
            continue
        # **非空、且不含数字** —— 即平台明写了「面议 / 另议 / 详谈」这类。
        #
        # ⚠️ **`salary` 为空不算。** 空只说明列表没抓到，而深评是读过 JD 的：
        # 实测有一个岗列表薪资为空、评估里写着「25-35k·15薪」，薪资维 46 完全正确。
        # 第一版用 `salary_unstated` 直接判（它把 None 也算进去），
        # 把这种合法情形报成了违规 —— 判不准的扫描器比没有更坏。
        _s = str(e.get("salary") or "").strip()
        if not _s or not _cli.salary_unstated(_s):
            continue
        pay = (e.get("rank_breakdown") or {}).get("薪资与职级")
        if isinstance(pay, int):
            hit.append((pay, (e.get("title") or "?")[:18], e.get("rank_score")))
    if not hit:
        return []
    zeros = [h for h in hit if h[0] == 0]
    tail = ""
    if zeros:
        tail = (# 这一行印到终端，不许带 markdown（ 盯着）。
                f"其中 {len(zeros)} 个给的是 0 —— 0 的意思是「薪资很差」，"
                f"而真相是「不知道」，它会实打实把总分压下去。")
    return [("warn", "薪资面议却打了薪资分",
             f"{len(hit)} 个岗的薪资串平台明写着不是数字（面议 / 另议 / 详谈），"
             f"而薪资那一维仍然写了分数。{tail}"
             f"04-job-evaluation.md 规定这一维不打分、标「信息缺失」，"
             f"权重按其余三项重分配 —— 同一份文档算过：面议不计入 76 分，照打 63。"
             f"例：{'、'.join(f'{n}（薪资维 {s}，总分 {t}）' for s, n, t in hit[:3])}。"
             f"修：重评这几个（/job-rank --all），或按面议规则把薪资维抹成 null。")]


#: 四个取值的正本在 `tools/scoring.py` —— 那边是**算**的一侧，这边是查的一侧，
#: 两边共用一份实现。同一份逻辑两处实现是这个仓库最贵的那类错误。
_PAY_TOP, _PAY_IN, _PAY_OK = _sc.PAY_TOP, _sc.PAY_IN, _sc.PAY_OK


#: 抓取的五条渠道（`job-scrape.md`「抓取按渠道枚举，不按平台枚举」那张表）：
#: 猎聘的 CLI 与浏览器，加另外三家各一条浏览器。
#:
#: **映射从 `PORTAL_ALIAS` 现推，不另立一张表。** 第一版在这里抄了一份
#: 五条渠道 + 一份历史别名，当场就少认了 `boss-cdp` 那几个老名字里的一半 ——
#: 而正本 `query_yield.PORTAL_ALIAS` 十一个别名一个不少。同一份映射两处实现
#: 必然飘，这个仓库为它付过好几次学费（`gap_split` 的算式、`dupOf` 的键……）。
_LANES = {ch: site for ch, site in PORTAL_ALIAS.items() if site in PORTALS}


def _rounds_by_day(user: str):
    """`query_log` 按天归成 {日期: {渠道: 查询数}}。读不出返回 None。

    **这是唯一分得清「跑了没收获」和「根本没打开过」的记录。** 拿新岗数去数
    会把前者算成后者 —— 而两者的下一步正好相反（一个是这条渠道挖空了，
    一个是这条渠道漏了）。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        return None
    try:
        log = json.loads(p.read_text(encoding="utf-8")).get("query_log")
    except (ValueError, OSError):
        return None
    if not isinstance(log, list) or not log:
        return None
    out = {}
    for q in log:
        if not isinstance(q, dict):
            continue
        day = str(q.get("date") or "")[:10]
        lane = str(q.get("portal") or "")
        if len(day) == 10 and lane in _LANES:
            out.setdefault(day, {}).setdefault(lane, 0)
            out[day][lane] += 1
    return out or None


def check_a_whole_channel_sat_out_the_round(seen, details) -> list:
    """上一轮抓取有整条渠道一次都没打开过。

    ## 规则早就写对了，只是没有东西验它

    `job-scrape.md`「抓取按渠道枚举，不按平台枚举」那张表写着「**一轮正常要动
    4 条**（猎聘 CLI 或猎聘浏览器二选一，加 BOSS、智联、前程无忧）」，还有一句
    「**少一行就是漏了一条渠道**」。2026-08-28 用户又裁定一次：
    「浏览器渠道是等同的，应该一起去跑。」

    **而这三句话都是散文。** 实测代价，同一个错犯了两次：

    - 2026-08-25：猎聘 CLI 撞 `RATE_LIMITED`，执行者把**整个猎聘**跳过。
      用户当场纠正「CLI 停了不要紧，你可以用浏览器的啊」，规则为此推翻重写。
    - 2026-08-27：CLI 又撞 `RATE_LIMITED`，**又**没换道；同一轮里前程无忧
      闸门放行、0 次查询。那天的 `query_log`：猎聘 CLI 8 次、BOSS 4 次、
      智联 1 次、猎聘浏览器 0 次、前程无忧 0 次。

    规则改对了、执行照旧 —— 因为漏一条渠道**在任何地方都不会留下痕迹**。
    现在会了。

    ## 为什么读 `query_log` 而不是数新岗

    新岗数分不清「跑了没收获」和「根本没打开过」，而这两件事的下一步正好相反：
    前者说明这条渠道这轮挖空了（正常），后者说明它漏了（要补跑）。
    `query_log` 逐条记 `{date, portal, query, page}`，0 条就是没打开过。

    ## 只看最近一轮

    存量补不了（那天已经过去了），报的是「最近一轮漏没漏」—— 一条永远红着的
    自检会被当噪音略过（同 `test_the_backlog_does_not_hide_the_trend`）。
    """
    if not _USER:
        return []
    days = _rounds_by_day(_USER[0])
    if not days:
        return []
    day = max(days)
    ran = days[day]
    hit = {p for lane, p in _LANES.items() if ran.get(lane)}
    missing = [p for p in ("猎聘", "BOSS", "智联", "前程无忧") if p not in hit]
    # 跑了的那几条之间差得离谱也要说 —— 用户的裁定是「浏览器渠道是等同的」，
    # 一条只给了别人零头，和整条没跑是同一个毛病的轻症。
    import portal_budget as pb          # 函数内 import，同本文件其余几处
    browser = {lane: n for lane, n in ran.items()
               if n and pb.lane_of(lane) == "browser"}
    thin = ""
    if len(browser) > 1 and max(browser.values()) >= 3 * min(browser.values()):
        lo = min(browser, key=browser.get)
        hi = max(browser, key=browser.get)
        thin = (f"另外，跑了的浏览器通道之间差着 {browser[hi] // browser[lo]} 倍"
                f"（{hi} {browser[hi]} 次 vs {lo} {browser[lo]} 次）——"
                f"用户 2026-08-28 裁定「浏览器渠道是等同的，应该一起去跑」，"
                f"顺位表里那些命中率只在额度不够时用来分配，不是排队号。")
    # **漏的是这一批时，收尾要当场看见。**（同 `check_the_blocked_lane_handed_over`：
    # 判据是 `_cli.note_round_scoped()`，不是名单。）往日那一轮补不回来，
    # 收尾不该被它占一行 —— 补法也跟着分两种，否则就是在 `/job-auto` 里
    # 印一句「跑 /job-auto」，让人原地转圈。
    fresh = _in_this_batch(day)
    if not missing:
        if thin and fresh:
            _cli.note_round_scoped()
        return [("warn", "上一轮渠道之间跑得不均", thin)] if thin else []
    if fresh:
        _cli.note_round_scoped()
        fix = "这一轮就漏在这儿 —— 现在把漏掉的那几家补跑一遍：/job-scrape"
    else:
        fix = "补它：跑 /job-auto"
    detail = "、".join(f"{lane} {n} 次" for lane, n in sorted(ran.items(),
                                                           key=lambda x: -x[1]))
    return [("warn", "上一轮有渠道整条没跑",
             f"最近一轮抓取（{day}）漏了 {len(missing)} 家：{'、'.join(missing)}"
             f" —— `query_log` 里 0 次查询，也就是根本没打开过，不是跑了没收获。"
             f"那天实际跑的：{detail}。"
             f"job-scrape.md 那张渠道表写着一轮正常要动 4 条、少一行就是漏了一条；"
             f"BOSS / 智联 / 前程无忧只有浏览器这一条路，漏掉就是这家整轮没了。"
             f"猎聘漏掉时注意：CLI 被闸门挡住不等于这家没了，浏览器那条照常进轮次"
             f"（降速 ×3）。{thin}"
             f"{fix}")]


#: 成对的标点。一句话里数量对不上，多半是被截断了。
_PAIRS = (("「", "」"), ("（", "）"), ("(", ")"), ("《", "》"), ("【", "】"))


def check_panel_text_is_not_cut_off(seen, details) -> list:
    """面板上有句子断在半截 —— 引号开了没关，括号开了没合。

    ## 为什么用「括号配不上对」当判据

    中文列表里省略句末问号是正常写法（「研发节奏是怎样的，有没有大小周」），
    按标点结尾判会把它们全报出来 —— 实测活动用户 2026-08-29：那样报 196 条、
    占 44%，全是噪音。
    而**引号开了没关**几乎只有一种成因：这句话被截断了。

    实测活动用户 2026-08-29（读的是导出的真实快照）：

        投之前先问清   11 处   例：「…职责 1 是「定义 AI 参与开发的
        缺口           9 处
        材料正文        2 处
        硬性条件依据     1 处

    「投之前先问清」那一栏尤其伤：用户照着它去问，而问题本身停在半句。

    ## 职位名那几处不算

    平台自己的标题就带着不配对的括号（`AI产品与应用高级经理(技术背景出身must）`
    —— 半角开、全角关）。那是抓回来的原文，改它等于篡改数据源。
    """
    f = ROOT / "web" / "public" / "data.json"
    if not f.is_file():
        return []
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hit = collections.Counter()
    sample: dict = {}

    def bad(s: str) -> bool:
        return any(s.count(a) != s.count(b) for a, b in _PAIRS)

    def walk(o, field):
        if isinstance(o, str):
            # 职位名是抓回来的原文，平台自己就不配对；材料正文里的整段文书
            # 也常跨段落引用，误报率高 —— 两者都不进。
            if field in ("title", "company") or len(o) < 12 or len(o) > 400:
                return
            if bad(o):
                hit[field] += 1
                sample.setdefault(field, o)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, field or k)
        elif isinstance(o, list):
            for v in o:
                walk(v, field)

    for j in d.get("jobs") or []:
        for k, v in j.items():
            walk(v, k)
    if not hit:
        return []
    n = sum(hit.values())
    rows = "、".join(f"{k} {c} 处" for k, c in hit.most_common(4))
    eg = sample.get("askBefore") or next(iter(sample.values()))
    return [("warn", "面板上有句子断在半截",
             f"{n} 处文本的引号或括号配不上对 —— 多半是被截断了（{rows}）。"
             f"例：…{eg[-46:]}。「投之前先问清」那一栏尤其伤：用户照着它去问，"
             f"而问题本身停在半句。"
             f"判据不看句末标点（中文列表省略问号是正常写法，那样报会有 44% 的噪音），"
             f"只看成对标点。修：对这几个岗重跑 /job-apply <职位链接>")]


def _same_job(a: dict, b: dict) -> bool:
    """两条记录说的是不是**同一个岗**。

    ## 为什么光比链接不够

    职位库的键是 `链接#职位名`，而 `norm_url` 把 `#职位名` 剥掉了 ——
    于是**一个链接挂着多个岗**的平台上，不同的岗会被判成同一个岗的两份。

    实测 2026-08-30，`check_the_archive_was_consulted` 报的 6 个
    「热库和存档各有一份」，**6 个全是同一链接、不同职位名**：

        AI应用工程师(J11182)          vs  数字电路设计工程师(J11077)
        后端开发（路网数据方向）实习生    vs  Android研发工程师-豆包输入法
        AI Agent 评测工程师           vs  AI Agent 工程师

    前程无忧的 `jobs.51job.com/all/<码>.html` 是**公司页不是职位页**
    （`job-apply.md` 那张分流表里的「职位聚合页」说的就是它）。
    一个都不是重复，而报文写着「其中 5 个两边的结论已经不一样了」，
    还给了「逐个看 `/job-apply <链接>`」。

    ## 判据

    **职位库的键怎么算，这里就怎么算**：链接一样、职位名也一样，才是同一个岗。
    任一边没有职位名就只按链接判 —— 分不出来时宁可报（那是原来的行为）。

    这不影响这条检查本来要抓的那件事：2026-08 那次 28 个已归档的岗被当新岗
    插回，是**同一个岗**被抓了两遍，职位名当然一样，照样报得出来。
    """
    ta = str(a.get("title") or "").strip()
    tb = str(b.get("title") or "").strip()
    if not ta or not tb:
        return True
    return ta == tb


def check_the_archive_was_consulted(seen, details) -> list:
    """同一个岗热库和存档里各有一份 —— 查重没连存档一起查。

    ## 归一化之后还是两条，就是重复

    `job-scrape.md` Step 4 写得很死：「**查重还必须连存档一起查**
    （`job_scraper/archive.json`，出局超过两周的岗会被 `archive.py` 挪进去，
    同 schema）。只查热库的话，归档的岗下一轮会被当新岗抓回来、
    **重新评一遍死数据** —— 归档就白做了。」

    而验它的一处也没有。实测活动用户 2026-08-28：当轮入库只对了热库，
    **28 个已经归档的岗被当新岗插了回来**。两份还会各自演化 —— 那天其中一个
    热库记 55「可以考虑」（当轮深评）、存档记「硬门 FAIL (明确排除)」（旧判），
    同一个岗两个结论。

    ## 同一个形状，这是第四次

    `norm_url` 的 docstring 记着前两次（协议不一致 20 个里 4 个重复、
    51job 路径前缀 9 组），Step 4 自己记着第三次（裸 URL vs `url#职位名`，
    30 条）。**共同点是「同一个岗有多把钥匙，而查重只试了其中一把」** ——
    这一次漏试的那把是存档。

    判据：两边的 `norm_url(url)` 撞上、**且职位名一样**才报（见 `_same_job`）。
    **只报不改** —— 哪一份新要看评分日期和材料，机械并会挑错
    （那天我就挑错了一次，把较新的那份删了，靠 `evaluation.md` 才复原）。

    ## 职位名那一半是 2026-08-30 补的，而它本身就是同一个形状的第五次

    只比链接时这条报了 6 个，**6 个全是同一 URL、不同职位名** ——
    也就是 6 次手工，去看 6 个不存在的问题。上面那段刚说完
    「同一个岗有多把钥匙」，而这条检查自己**把两把钥匙当成了一把**：
    职位库的键是 `链接#职位名`，`norm_url` 把后半截剥掉了。
    """
    if not _USER:
        return []
    # **ROOT 显式传**：这个模块的 `ROOT` 会被测试替换成临时目录，
    # 而 `_cli` 有它自己的一份 —— 不传就会去读真实仓库下的存档。
    arch = _cli.archived(_USER[0], root=ROOT)
    if not arch:
        return []
    cold = {}
    for v in arch.values():
        if isinstance(v, dict) and v.get("url"):
            cold.setdefault(_cli.norm_url(v["url"]), []).append(v)
    dup = []
    for v in seen.values():
        if not isinstance(v, dict) or not v.get("url"):
            continue
        # 一个链接下可能挂着好几个岗（见 `_same_job`），逐个比职位名。
        for c in cold.get(_cli.norm_url(v["url"]), []):
            if _same_job(v, c):
                dup.append((v, c))
                break
    if not dup:
        return []
    rows = "、".join(
        f"{(v.get('title') or '?')[:18]}（热库 {v.get('rank_verdict') or '未评'}"
        f" / 存档 {c.get('rank_verdict') or '未评'}）" for v, c in dup[:3])
    split = sum(1 for v, c in dup
                if (v.get("rank_verdict") or "") != (c.get("rank_verdict") or ""))
    return [("warn", "同一个岗热库和存档各有一份",
             f"{len(dup)} 个岗在两边都有（`norm_url` 归一化之后键相同），"
             f"其中 {split} 个两边的结论已经不一样了。"
             f"job-scrape.md Step 4 写着「查重还必须连存档一起查」——"
             f"只查热库的话，归档的岗下一轮会被当新岗抓回来、重新评一遍死数据。"
             f"例：{rows}。"
             f"⚠️ 别机械删一边：哪份新要看评分日期和有没有材料。"
             f"逐个看：/job-apply <职位链接>")]


#: 从职位链接里抠出「站点 + 路径形状 + 数字 id」。同一族里 id 位数应当一致。
_JOB_ID = re.compile(r"//(?:www\.)?([a-z0-9.]+)/([a-z]+)/(\d+)\.(?:shtml|html|htm)")


def check_job_ids_are_not_truncated(seen, details) -> list:
    """同一个平台的职位号位数出现离群值 —— 多半是入库时被截断了。

    ## 为什么会截断

    浏览器扩展的安全层会把长串数字/字母当成 token 挡掉（`[BLOCKED: ...]`），
    所以抓取时要把 id 分段输出再还原。**分段容易，还原容易少一位。**

    实测活动用户 2026-08-29：一轮猎聘浏览器入库的 5 条，10 位职位号全被写成
    9 位 —— 而库里另外 586 条同族全是 10 位。9 位那个 URL **打得开**，
    指向的是另一个岗（点开是「三亚 总经理」，而记录写着「<公司> AI 产品经理」）。
    **不报错、不空白、打得开** —— 这是最难发现的一类错。

    发现它靠的是人点开看了一眼；而位数这件事机器一眼就能看出来。

    ## 判据：同族里的少数派

    按「站点 + 路径段」分族（`liepin.com/job/`、`liepin.com/a/`…），
    族里样本 ≥ 20 条时，位数占比不到 5% 的那些报出来。
    **不猜哪个是对的** —— 只说「这几条和同族的其余 N 条不一样」，
    改法是人去点开核对。
    """
    fam: dict = {}
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        m = _JOB_ID.search(_cli.norm_url(e.get("url") or ""))
        if m:
            fam.setdefault((m.group(1), m.group(2)), []).append((len(m.group(3)), e))
    out = []
    for (site, seg), rows in sorted(fam.items()):
        if len(rows) < 20:
            continue
        counts = collections.Counter(n for n, _e in rows)
        main, _n = counts.most_common(1)[0]
        odd = [e for n, e in rows if n != main and counts[n] / len(rows) < 0.05]
        if odd:
            out.append((site, seg, main, len(rows), odd))
    if not out:
        return []
    lines = []
    for site, seg, main, tot, odd in out:
        eg = "、".join(f"{(e.get('title') or '?')[:14]}" for e in odd[:3])
        lines.append(f"{site}/{seg}/ 同族 {tot} 条里 {len(odd)} 条位数和其余的不一样"
                     f"（其余是 {main} 位）：{eg}")
    n = sum(len(o[4]) for o in out)
    return [("warn", "职位号位数不像同一族",
             f"{n} 个岗的职位号位数是同族里的少数派 —— 多半是入库时截断了。"
             f"{'；'.join(lines)}。"
             f"截断的 URL 常常打得开、只是指向另一个岗 —— 不报错也不空白，"
             f"实测 2026-08-29 撞上过一次（9 位那个点开是别的城市别的岗位）。"
             f"核它：把链接点开，对一眼标题和公司；不对就重抓。")]


def check_the_yield_table_kept_up(seen, details) -> list:
    """抓完没跑 `query_yield.py --apply`，下一轮还会用同一批挖空的词去抓。

    ## 又是「规则写了，没有东西验它」

    `job-auto.md` 写着：「补货完**必须跑** `python tools/query_yield.py --apply`
    （`job-scrape.md` Step 4.6），否则下一轮又用同一批已经挖空的词去抓 ——
    自动循环会把这个浪费放大成十几轮。」

    验它的只有 `test_auto_mode_does_not_stop_early`，而那条查的是
    **工作流文件里有没有这句话**，不是这一步有没有真跑过。

    实测活动用户 2026-08-28：当轮四条渠道抓了 40 个新岗，而
    `search-queries.md` 那个自动维护块的日期还停在 08-27 —— 漏跑了，
    整趟跑完没有任何一处会说。

    ## 判据：两个日期比一下

    `query_log` 给最后一次抓取是哪天，`search-queries.md` 的块头
    「实测产出（自动维护 · 最近更新 YYYY-MM-DD）」给词表最后一次刷新是哪天。
    **抓过之后没刷过**就是漏了。两个日期都是现成的，此前没有一处把它们对起来。

    读不出块头就不报 —— 「没查」和「查过没有」是两件事（同 `_annual_floor`）。
    """
    if not _USER:
        return []
    days = _rounds_by_day(_USER[0])
    if not days:
        return []
    p = ROOT / "users" / _USER[0] / "profile" / "search-queries.md"
    if not p.is_file():
        return []
    m = re.search(r"实测产出（自动维护 · 最近更新 (\d{4}-\d{2}-\d{2})）",
                  p.read_text(encoding="utf-8"))
    if not m:
        return []
    scraped, refreshed = max(days), m.group(1)
    if refreshed >= scraped:
        return []
    # **无条件进收尾那一档**（`--actionable`）。
    #
    # 旁边那两条（漏一条通道、漏一整家）只为「这一批」喊 ——往日那一轮的
    # 抓取补不回来，印出来只会把还来得及的淹掉。**这一条不一样：**
    # `query_yield.py --apply` 是拿 `query_log` 现算整张表，哪天跑都补得上，
    # 没有「太晚了」这一说。而不补的代价落在**下一轮**：同一批已经挖空的词
    # 再抓一遍，每次请求隔 8 秒，自动循环会把它放大成十几轮。
    _cli.note_round_scoped()
    return [("warn", "抓完没刷词表产出",
             f"最后一次抓取是 {scraped}，而词表那个自动维护块还停在 {refreshed} —— "
             f"中间漏跑了 query_yield.py --apply。下一轮会拿同一批已经挖空的词"
             f"再抓一遍，而每次请求要隔 8 秒，自动循环会把这个浪费放大成十几轮。"
             f"补它：python tools/query_yield.py --apply")]


def check_the_blocked_lane_handed_over(seen, details) -> list:
    """猎聘 CLI 被闸门挡住那天，浏览器那条没有接上去 —— 这家整轮就没了半截。

    ## 同一个错犯过两次，两次都靠人当场发现

    `job-scrape.md` 那张渠道表第 2 行写得很死：「**只在 1 被闸门挡住时**走
    （自动降速：间隔 ×3）」，配套一整段还写着「CLI 被闸门挡住时，浏览器那条
    **照常进这一轮**……那不是『启用后备』，那就是正常执行」。
    `portal_budget.py` 的实现也是这么做的：CLI 冷却时 `--check liepin-browser`
    放行、只降速。

    **三处写对了，执行两次都没照做：**

    - 2026-08-25：CLI 第一个请求就 `RATE_LIMITED`，执行者把整个猎聘跳过，
      报告写成「CLI 在冷却，明天再说」。用户纠正后补跑：**浏览器搜一页 40 张卡、
      新增 36 个**，而同一天另外三家合计才 50 个。
    - 2026-08-27：CLI 14:12 撞 `RATE_LIMITED`（`block_log` 记着），
      当天 `liepin-browser` **0 次查询**。猎聘占这个库语料的 84%。

    判据两个数据源各出一半：`portal_budget.json` 的 `block_log` 给「哪天被挡的」，
    `query_log` 给「那天浏览器那条动没动」。两边都是现成的，此前没有一处把它们
    对起来看。

    ## 只报最近一次

    存量补不了。报最近那次，盯它会不会再犯。
    """
    if not _USER:
        return []
    days = _rounds_by_day(_USER[0])
    p = ROOT / "users" / _USER[0] / "job_scraper" / "portal_budget.json"
    if not days or not p.is_file():
        return []
    try:
        led = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    hits = [str(h.get("at") or "")[:10]
            for h in ((led.get("猎聘") or {}).get("block_log") or {}).get("cli", [])
            if isinstance(h, dict) and h.get("act") == "hit"]
    hits = [d for d in hits if len(d) == 10]
    if not hits:
        return []
    day = max(hits)
    import portal_budget as pb          # 函数内 import，同本文件其余几处
    if any(n for lane, n in days.get(day, {}).items()
           if _LANES.get(lane) == "猎聘" and pb.lane_of(lane) == "browser"):
        return []
    ran = days.get(day, {})
    detail = ("、".join(f"{k} {v} 次" for k, v in sorted(ran.items(),
                                                       key=lambda x: -x[1]))
              or "一条都没有")
    # **漏的是今天这一轮时，喊一声让收尾看见。**
    #
    # 这一条此前进不了 `--actionable`（收尾跑的那一档）—— 它不调
    # `sendable_state`，而那是当时唯一的信号。于是同一个错犯了两次，
    # 两次都靠人当场发现。判据仍然是行为：`_cli.note_round_scoped()`。
    #
    # ⚠️ **只在「今天」那一支喊，补法也跟着分两种。** 漏的是往日那一轮时，
    # 补法是「跑 /job-auto」；而收尾本身就在 `/job-auto` 里，在那儿印一句
    # 「跑 /job-auto」就是让人原地转圈 —— 这个仓库管这叫「收尾那句话
    # 许了一个它兑现不了的诺」。今天这一轮漏了的话，能当场做的是补跑浏览器
    # 那条：`/job-scrape`（Step 0.44 会把闸门放行的通道都带上）。
    today = _dt.date.today().isoformat()
    if day == today:
        _cli.note_round_scoped()
        fix = ("这一轮就漏在这儿 —— 现在补跑一次浏览器那条：/job-scrape"
               "（Step 0.44：闸门放行的通道都要抓）")
    else:
        fix = "补它：跑 /job-auto"
    return [("warn", "猎聘 CLI 停了，浏览器那条没接上",
             f"{day} 那天 CLI 撞了限流（`block_log` 记着），而同一天 "
             f"`liepin-browser` 0 次查询 —— 这家的后半轮就空了，"
             f"而它占这个职位库语料的大头。那天实际跑的：{detail}。"
             f"job-scrape.md 那张渠道表第 2 行写着「CLI 被闸门挡住时，"
             f"浏览器那条照常进这一轮（降速 ×3）」，"
             f"portal_budget 的实现也是这么做的（冷却时 --check liepin-browser 放行）。"
             f"同一个错 2026-08-25 犯过一次，用户当场纠正过。"
             f"{fix}")]


def _pay_dim_should_be(entry: dict, floor: float, expect):
    """按 04 那张表算这个岗的薪资维该给几分。**正本在 `tools/scoring.py`。**

    这里只留一个薄包装：查的一侧和算的一侧共用同一份实现，
    才不会出现「自检说对、写回时又算成另一个数」。
    """
    return _sc.pay_dim(entry, floor, expect)


_DEDUCT_CLAIM = re.compile(
    r"(?<!不)减分[^。；\n]{0,14}?[−–-]?\s*5(?![0-9])"
    r"|[−–-]\s*5\s*分?[^。；\n]{0,14}?(?<!不)减分"
    r"|已扣\s*5\s*分"
    r"|综合分\s*已?\s*[−–-]\s*5(?![0-9])")


def check_the_deduction_was_actually_deducted(seen, details) -> list:
    """评分明细的散文里说扣了分，就得有一个字段真的扣了。

    ## 这条自检补的是什么

    「专业清单不含历史学 → 综合分 −5」是资料里的裁定（2026-08-14）。执行者
    老老实实把它写进了评分明细，连算式都写全了：「作 −5 减分（**已扣**，
    60→55）」。**但存的分是 60，不是 55。** 写了、说了、一次没执行 ——
    2026-08-29 实测 **33 个岗**都是这样，其中 5 个的结论因此虚高一整档
    （含一个从「值得投」虚高上来的，差点按可投出了整套材料）。

    ## 为什么原来那条查不出来

    `check_composite_matches_its_dims` 比的是「综合分 vs 四维加权和」。而这里
    减分**压根没扣**，两边自然相等 —— 它看到的是一个完美自洽的错误。
    能查出来的只有第三个住址：散文里那句自称。**同一件事有三个住址
    （散文、字段、分数），而检查只去了其中两个。**

    这也是 `scoring.adjust_of` 存在的理由：写入端用 `专业减分`，
    而计算端一直只读 `调整` —— 两个名字，同一天一起修的。

    ## 判据为什么要卡这么紧

    第一版只查「同一格里既出现 `减分` 又出现 `5`」，当场吃到一个假阳性：
    一条依据写的是「专业写的是『优先』**不减分**」，而 60 个字以外的
    「3-5 年」里那个 `-5` 把它匹配上了。现在要求两者**挨着**（14 字内），
    并排掉「不减分」。散文判据只要放宽一格，报出来的就不是事实而是噪音。
    """
    bad = []
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        b = e.get("rank_breakdown")
        if not isinstance(b, dict) or _sc.adjust_of(b):
            continue
        for k, v in b.items():
            if isinstance(v, str) and _DEDUCT_CLAIM.search(v):
                bad.append((str(e.get("title") or e.get("company") or "")[:22],
                            e.get("rank_score"), k))
                break
    if not bad:
        return []
    rows = "、".join(f"{t}（存的是 {sc} 分，而「{k}」里说已经扣过）"
                    for t, sc, k in bad[:3])
    return [("warn", "说扣了分，却没有一个字段真的扣",
             f"{len(bad)} 个岗的评分明细里写着作了减分，却找不到对应的字段："
             f"{rows}。减分只写在散文里等于没减 —— 重算时没任何工具看得见它，"
             f"而「总分和四维对不上」那条也查不出来（没扣的话两边正好相等）。"
             f"写法：在 `rank_breakdown` 里加一个顶层字段（例：`\"专业减分\": -5`），"
             f"`scoring.adjust_of` 会把它算进综合分；"
             f"改完跑 `python tools/score.py --apply`。")]


def check_pay_dim_matches_its_own_number(seen, details) -> list:
    """薪资那一维的分，和这个岗自己的薪资串算出来的对不上。

    ## 这一维是四选一，不是打分

    `04-job-evaluation.md`「打分口径：比的是够不够」给的是一张查表：年包**下沿**
    到顶 90 / 落在期望区间 85 / 低于期望但过底线 55 / 低于底线 25。输入只有
    `salary` + `salaryMonths` + 资料里的两个数，**没有判断余地** ——
    它是这四维里唯一能被机器完整验算的一维。

    而此前没有任何一处在验。旁边那两条各守一个特例（面议不该打分、没标薪数
    不该被埋），**主表本身没人守**。

    ## 实测（2026-08-27）

    全库 763 个填了薪资维的岗，**247 个（32%）对不上**。分两类：

    - **取了表上没有的数**：70、72、75、80…… 一整条连续刻度。2026-08-24 那批
      93 个里 92 个如此 —— 那天的执行者是在「凭感觉给分」，而不是查表。
    - **查了表但比错了边**：拿上沿比、或把「先问定级」当成第三条路给 55。
      本会话自己就犯了后一种：`20-40K·15薪` 的下沿是 30 万、低于 45 万底线，
      写的却是 55 并附一句「门槛低说明定级弹性大」—— 04 早写过这句话的名字，
      叫「折算一个中性值」，那一节的标题就是**别走第三条路**。

    薪资维占 25% 权重，一档之差（25→55 或 55→85）是综合分 7.5 分，
    足以翻一整档判词。实测活动用户 2026-08-27：那 247 个里 24 个是当天那一批，
    当场按表订正掉（总分与结论跟着重算），**剩下 223 个是存量**——
    要重评才动得了，这条检查就长期报着它。

    ## 为什么不自动改

    这一维**能**机械重算 —— 但综合分不能：资料里的裁定可以在四维之外直接减分
    （`check_score_reconciles` 记着那条），机械重算会把它一起抹掉。
    所以只报，改法是重评。
    """
    floor, expect = _annual_floor(), _annual_expect()
    if floor is None or expect is None:
        return [("warn", "读不出薪资底线或期望区间，这条没查",
                 "`candidate.md` 的「可接受底线」「期望区间」两行里解析不出年包数，"
                 "所以「薪资维和它自己的薪资串对不对得上」这一档没查 —— 不是没有。"
                 "两行各补一个「（年包 N 万）」「（年包约 N-M 万）」就能查")]
    bad, latest = [], ""
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        got = (e.get("rank_breakdown") or {}).get("薪资与职级")
        if not isinstance(got, (int, float)):
            continue
        exp = _pay_dim_should_be(e, floor, expect)
        if exp is None or exp == got:
            continue
        day = str(e.get("rank_date") or "")
        latest = max(latest, day)
        bad.append(((e.get("title") or e.get("company") or "?")[:16],
                    e.get("salary") or "?", got, exp, day))
    if not bad:
        return []
    off_table = [b for b in bad if b[2] not in
                 (_PAY_TOP, _PAY_IN, _PAY_OK, _MONTHS_LOW)]
    rows = "、".join(f"{n}（{s}，写 {g}，查表 {x}）" for n, s, g, x, _ in bad[:3])
    tail = watermark_note([b[4] for b in bad])
    return [("warn", "薪资维和它自己的薪资串对不上",
             f"{len(bad)} 个岗的薪资维不等于按 04 那张表查出来的数"
             f"（其中 {len(off_table)} 个取的是表上根本没有的值——"
             f"那张表只有 {_PAY_TOP}/{_PAY_IN}/{_PAY_OK}/{_MONTHS_LOW} 四个数）。"
             f"比的是年包下沿（不是上沿）：到顶 {_PAY_TOP}、落在期望区间 {_PAY_IN}、"
             f"过底线 {floor:g} 万 {_PAY_OK}、低于底线 {_MONTHS_LOW}。"
             f"例：{rows}。这一维占 25% 权重，一档之差 7.5 分，足以翻一整档判词。"
             f"{tail}"
             f"修：跑 python tools/score.py --apply（粗筛那层）和 "
             f"python tools/score.py --deep --apply（深评那层，连 "
             f"evaluation.md 一起改）")]


def check_years_gate_vs_platform_field(seen, details) -> list:
    """判了「工作年限」FAIL，而平台自己标的年限要求他明明够。

    `job-rank.md` 写着猎聘 CLI 免费带的 `eduLevel` / `workYears` / `compScale`
    **必须参与硬门判定** —— 规则写了，**没有东西验它**。

    实测活动用户 2026-08-22：491 个岗死在「工作年限」这道门上（占全部硬门 FAIL
    的 43%，是最大的一道），而平台字段里：

        经验不限             42   ← 平台明写没有年限要求
        1年以上/2年以上/1-3年  14   ← 他两个年限读数都够
        3年以上               19
        3-5年                 69

    「经验不限」那 42 个没有任何解释空间：**一道平台说不存在的门，挡掉了 42 个岗。**

    ## 为什么分两档报

    第一档（`经验不限`）不需要知道候选人有几年 —— 下限是 0，谁都够。
    第二档要拿他的年限比，而年限写在 `candidate.md` 的自由文本里
    （「总工作年限 13 年 11 个月，但 AI 产品方向约 3 年 4 个月」）。
    读得出就比，**读不出就只报第一档并说明** —— 这条仓库规矩是
    「『没查』和『查过没有』是两件事」。

    比的时候用**两个读数里小的那个**再加 1 年容差（`04` 的「差 1 年以内 FLAG」）：
    小的那个都够，就没有任何一种读法能判 FAIL。

    ## 第三档：领域要求混进了年限门（2026-08-24 补）

    这里原来写着「要求更高的那些（5 年、10 年以上）按总年限还是方向年限算……
    那要读 JD 正文，这里判不了，不报、也不计入」。**那句话把最大的一类漏掉了**，
    而它不需要读 JD —— **深评自己就把 JD 那句原样引在依据里**。

    `04` 2026-08-24 补了判据（「年限门：那个数带不带领域限定」）：

    - 「N 年以上工作经验 / 相关经验」（**没有领域限定**）→ 拿总年限比，**是门**
    - 「N 年以上 <某领域> 经验」，而他在那个领域上是零 → **这条不是门**，
      是第 1 维的业务领域分。年限门按总年限判

    判据一落地，这一档就查得了：**引文带领域限定、而那个数没超过总年限**，
    就是把领域要求当成年限门用了。

    实测活动用户 2026-08-24（269 份深评）：判 FAIL 的 16 份里，
    **16 份引的全是带领域限定的要求**，15 份那个数没超总年限 14 年，
    **15 份是只被这一道门杀掉的**（没有第二道 FAIL）。唯一维持的是
    「15 年以上市场营销经验」—— 15 > 14，那才是这道门该做的事。

    代价不是「多标了几个 FLAG」：判词写成「不满足硬性条件」就是**永久出局**，
    而它们的真实问题（领域不熟）本该只是业务领域分低几档。
    """
    fails = [e for e in seen.values()
             if isinstance(e, dict) and "工作年限" in str(e.get("rank_verdict") or "")]
    if not fails:
        return []
    out = []

    zero = [e for e in fails if _min_years(e.get("workYears")) == 0]
    if zero:
        # `error` 而不是按比例定档：这一档是**逻辑矛盾**，不是「错得多不多」。
        # 平台写着没有年限要求，却按年限判了不满足——出现一个就是错一个。
        out.append(("error", "年限门挡掉了「经验不限」的岗",
                    f"{len(zero)}/{len(fails)} 个判了「工作年限」不满足，"
                    f"而平台字段写的是「经验不限」——一道平台说不存在的门。"
                    f"例：{'、'.join((e.get('title') or '?')[:16] for e in zero[:3])}。"
                    f"重评跑 /job-rank --all"))

    yrs = _candidate_years()
    if yrs is None:
        out.append(("warn", "候选人年限读不出来，第二档没查",
                    "`candidate.md` 里的「工作年限」那行解析不了，所以"
                    "「平台下限他够、却判了不满足」这一档没查——不是没有。"
                    "补一行「总工作年限 N 年，某方向 M 年」就能查"))
        return out

    floor = min(yrs) + 1
    low = [e for e in fails
           if (_min_years(e.get("workYears")) or 99) != 0
           and (_min_years(e.get("workYears")) or 99) <= floor]
    if low:
        # 这一档按比例定档，和 `check_evaluation_sections` 等兄弟检查一致：
        # 它依赖对 `candidate.md` 自由文本的解析，误差比上一档大。
        # **这一档要分两条路说，因为它本来就是两批。**
        #
        # 报一个数就收尾，用户不知道该敲什么
        # （`AGENTS.md`「每一处引导都要写出该敲的命令」）。
        # 而这一档给不了单一命令：粗筛判的那批一条
        # `--requeue-unfounded --apply` 就放回队列了，深评判的那批只能逐个
        # 重跑 `/job-apply` —— 实测活动用户 2026-08-25 是 6 + 5。
        # 混成一条写，就有一半人按那条改不动自己那几个岗。
        ev = [e for e in low if e.get("evaluated")]
        how = "修：python tools/audit_pipeline.py --requeue-unfounded --apply"
        if ev:
            how += (f"（那条只放回粗筛判的；另外 {len(ev)} 个已经深评过，"
                    f"它一律不碰，要逐个重跑 /job-apply <职位链接>）")
        # **报全库那个数，读起来就像存量。** 这个仓库对这件事有现成的说法
        # （`batch_note`，五条检查在用）：全库那个数只会随产量涨，说不了
        # 规则灵不灵；最近一批那个才行。这条此前没接上，而实测2026-08-31：
        #
        #     2026-08-19   33 个中  1 个是误判
        #     2026-08-24    7 个中  7 个是误判
        #     2026-08-27   21 个中 10 个是误判   ← 最近一批
        #
        # 21 这个全库数读起来像「历史遗留」，而近一半的**新**判定还在犯。
        _wrong = {id(e) for e in low}
        _bn = batch_note([(str(e.get("rank_date") or "")[:10],
                           id(e) in _wrong) for e in fails])
        out.append(("warn" if len(low) * 2 < len(fails) else "error",
                    "年限门挡掉了他年限够的岗",
                    f"{len(low)} 个判了「工作年限」不满足，而平台标的下限 ≤ "
                    f"{floor} 年——他两个年限读数里小的那个是 {min(yrs)} 年，"
                    f"加 1 年容差就够了。"
                    + (f"{_bn}。" if _bn else "") + how))

    # **这一档的修法不是 `/job-rank --all`。**
    #
    # 上面两档读的是职位库的卡片字段，重评一遍就改过来了。这一档读的是
    # `documents/applications/*/evaluation.md` —— 那个 FAIL 写在深评文件里，
    # 而 `/job-rank --all` 只重写库里的 `rank_*`，**深评文件一个字不动**
    # （写它的是 `/job-apply`，见 `job-rank.md`「不要动 job_search_tracker.csv」
    # 那一段划的边界：`/job-rank` 从不写投递目录）。
    #
    # 实测活动用户 2026-08-25，这 14 份：
    #
    #     evaluated=True            14/14   ← requeue 按设计一律不碰
    #     status=skipped             1/14   ← `--all` 明写不覆盖 skipped
    #     面板硬性条件表仍写 fail    14/14   ← 那张表就是从 evaluation.md 出的
    #
    # 所以指 `--all` 是**指了一条够不着的路**：跑完它，用户点开岗位看到的
    # 「工作年限 · 不满足」原封不动。同一份文件里 `requeue_unfounded_gate_fails`
    # 早就为同一个理由拒绝碰 `evaluated` 的岗。
    smuggled = _years_gate_smuggling_domain(max(yrs))
    if smuggled:
        out.append(("warn", "年限门挡掉的其实是领域经验",
                    f"{len(smuggled)} 份深评判了「工作年限」不满足，而引的那句"
                    f"带着领域限定、数又没超过他的总年限 {max(yrs)} 年——"
                    f"缺的是那个领域，不是年数。领域按 04 不是门，"
                    f"判成「不满足硬性条件」等于让这些岗永久出局，"
                    f"而它们本该只是业务领域分低几档。"
                    f"例：{'、'.join(x[0][:16] for x in smuggled[:3])}。"
                    f"判据见 04 的「年限门：那个数带不带领域限定」；"
                    f"逐个重跑 /job-apply <职位链接> 改这几份深评"))
    return out


#: 「N 年以上 <限定> 经验」里，哪些限定词算「没有领域限定」。
#: 「相关」是最松的一个，故意算进来——**宁可放过，不可误杀**：算成裸年限
#: 就是拿总年限比，门更容易 PASS，正是这道门该有的方向。
_YEARS_BARE = {"", "工作", "相关", "相关工作", "以上", "以上工作"}

#: 深评依据里引的那句年限要求。`(数字, 限定词)`。
_YEARS_REQ = re.compile(
    r"(\d+)\s*年(?:以上|及以上|\+|以内|-\d+\s*年)?\s*([^，。；、」\n]{0,20}?)(?:经验|经历)")


def _years_gate_smuggling_domain(total: int) -> list:
    """判了年限门 FAIL，而引文是「N 年以上 <某领域> 经验」且 N ≤ 总年限。

    返回 `[(目录名, 引文)]`。读的是深评里那张硬性条件表的「工作年限」行——
    **JD 原文就引在那儿**，不必回头去读 JD。
    """
    if not _USER:
        return []
    apps = ROOT / "users" / _USER[0] / "documents" / "applications"
    if not apps.is_dir():
        return []
    out = []
    for f in sorted(apps.glob("*/evaluation.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        # `[*]*` 而不是 `\\**`：终端措辞守卫扫的是非 docstring 的字面量，
        # 而 `\\**` 里那两个星号在它眼里就是 markdown 粗体（实测当场被逮）。
        row = re.search(r"^\|\s*[*]*工作年限[*]*\s*\|([^|]*)\|([^|]*)\|", t, re.M)
        if not row or "FLAG" in row.group(1) or "FAIL" not in row.group(1):
            continue
        q = _YEARS_REQ.search(row.group(2))
        if not q:
            continue
        n, qual = int(q.group(1)), re.sub(r"[*\s]", "", q.group(2))
        if n <= total and qual not in _YEARS_BARE:
            out.append((f.parent.name, q.group(0).strip()))
    return out

#: 哪几道门有**卡片字段**可以当依据。没有对应字段的门（明确排除、外包驻场）
#: 靠岗位名就判得了，不在这条检查的范围里——规则原话是
#: 「只在**卡片或 JD 的字段**够判时才判」，岗位名就是卡片字段。
_GATE_CARD_FIELD = {"工作年限": "workYears", "学历与院校": "eduLevel"}


def _gate_of_verdict(v: str) -> str:
    """判词 → 正规门名。**解析正本在 `_cli.gate_in_verdict()`**，这里只取第一格。

    原来这里自己写了一遍：只认半角括号、只认 `硬门 FAIL` 前缀。于是深评写的
    `不满足硬性条件（学历）` 那一批（实测 40 个）**对下面每一条审计检查都是隐形的**
    —— 不是判它们没问题，是从来没查过。同一段解析在 export 那边也各写一份，
    两份各修一半，这是本仓库记了多次的「N 个消费方里漏了一个」。
    """
    return _cli.gate_in_verdict(v)[0]


def _unfounded_gate_fails(seen, details) -> list:
    """判了硬门 FAIL，而正文和卡片字段两处都拿不出依据的岗。"""
    out = []
    for k, e in seen.items():
        if not isinstance(e, dict):
            continue
        field = _GATE_CARD_FIELD.get(_gate_of_verdict(e.get("rank_verdict")))
        if not field:
            continue
        body = (details.get(e.get("url")) or {}).get("description") or ""
        if len(body) >= _cli.JD_MIN_BODY:
            continue                      # 有正文，判得了，这条检查管不着
        if str(e.get(field) or "").strip():
            continue                      # 卡片字段就是依据
        out.append((k, e))
    return out


def check_gate_fail_without_evidence(seen, details) -> list:
    """判不了就别判死 —— 正文没抓到、卡片字段也空，还是把岗杀了。

    `job-rank.md` 那张表最后一行写着「**没抓到正文** → **FLAG**，判不了就别判死；
    标出来让人投前问一句」，Step 2 又写着「只在**卡片或 JD 的字段**够判时才判」。
    两句话合起来就是：**两处都没有依据时，不许 FAIL。**

    规则写了，此前没有东西验它。实测活动用户 2026-08-22：1094 个硬门 FAIL 里
    308 个（28%）没有 JD 正文 —— 但那不全是错的，`workYears` / `eduLevel` 是
    卡片字段，够判。收窄到**两处都空**的，还剩 18 个：年限 14、学历 4。

    十八个不多，可它们是**判不了却判死了**的十八个 —— 对用户来说和「真的不满足」
    长得一模一样，永远不会再出现在名单里。而这条检查真正的价值在往后：
    库涨一倍它就跟着涨，而没有它的话，谁也不会再手工量一遍。

    只覆盖有卡片字段兜底的那两道门。明确排除、外包驻场这些靠岗位名就判得了，
    岗位名也是卡片字段 —— 把它们算进来会造出一堆假阳性。
    """
    hit = _unfounded_gate_fails(seen, details)
    if not hit:
        return []
    by = collections.Counter(_gate_of_verdict(e.get("rank_verdict")) for _k, e in hit)
    return [("error", "判不了却判死了",
             f"{len(hit)} 个岗判了硬门不满足，而 JD 正文没抓到、对应的卡片字段也是空的"
             f"（{'、'.join(f'{g} {n}' for g, n in by.most_common())}）。"
             f"规则是判不了就标出来让人投前问一句，不是判死。"
             f"例：{'、'.join((e.get('title') or '?')[:16] for _k, e in hit[:3])}。"
             f"修：python tools/audit_pipeline.py --requeue-unfounded --apply")]


def check_an_exclusion_fail_must_name_the_rule(seen, details) -> list:
    """判「你自己划的排除」时**没说是哪一条** —— 规格说这就不该判 FAIL。

    `04-job-evaluation.md`「明确排除」那一节写得没有余地：

    > 写不出是哪一条 → **那就不该判 FAIL**。说不清命中了哪条排除，本身就说明
    > 判据不牢。

    同一节还写着括号是必须的，理由也写清了：**这一档是七道门里唯一他今天能改的**。
    学历、年限、户口、应届身份都不是他能动的；排除项是他自己下的结论，随时可以
    放宽一条。可要决定放宽哪一条，他得先知道每条各挡掉了多少个岗。

    ## 为什么单独成一条，而不是继续挂在「哪一条排除最贵」后面

    这个数一直有人算 —— `check_which_exclusion_costs_the_most` 末尾那个括号里
    的 `blank`。但它在那儿的身份是**统计口径的免责声明**（「上面那几个数是下限，
    不是全貌」）。读的人接收到的是「这张表数不准」，而不是「这几百个岗判错了」。

    **同一个数字，换个位置就换了意思。** 这个仓库栽过同族的两次：
    `check_referral_note_is_missing` 的「这个数说的是存量」、
    `check_greeting_keeps_the_five_rules` 的「102 份踩线里只有 11 份还发得出去」
    —— 两次的教训都是「总数印出来了，能动的那批认不出来」。这一条是第三次：
    数一直在，位置不对，于是没人拿它当待办。

    ## 判不了 vs 判得了却没说

    `check_gate_fail_without_evidence` 管的是另一半（正文没抓到、卡片字段也空），
    而它**明写着不含这一道门**：「明确排除、外包驻场这些靠岗位名就判得了」。
    那个理由对**判**成立，对**说清是哪一条**不成立 —— 靠岗位名判得出来的，
    照样说得出是哪一条。两条合起来才把这道门盖住。

    ## 报数要把能动的那批分出来

    有 JD 正文的，重判时点名或翻案都做得到；只有标题和卡片字段的那批，
    要么点得出名，要么按规格根本不该判死 —— 两种处置的紧迫程度不一样，
    所以分开报。
    """
    # `"FAIL" in ...` 这一条**当下是冗余的**：`_gate_of_verdict` 只认 FAIL 判词，
    # `硬门 FLAG (候选人明确排除)` 在它那儿就返回空串。留着是因为
    # **FLAG 是这道门的真实状态**（`04` 里就有“判 FLAG，不判 FAIL”的写法），
    # 那个解析器一旦跟着放宽，这条检查就会把 FLAG 一起报了 ——
    # 而 FLAG 本来就是“标出来让人投前问一句”，它不在这条的射程内。
    # （变异检验里它是一个**等价变异**，杀不掉；下面那条测试钉的是它依赖的前提。）
    fails = [e for e in seen.values()
             if isinstance(e, dict)
             and "FAIL" in str(e.get("rank_verdict") or "")
             and _gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"]
    bare = [e for e in fails if not _exclusion_reason(e)]
    if not bare:
        return []
    # `details` 的键是**原样 URL**（`_load` 里 `details[j["url"]] = j`），
    # 不是规范化过的。用 `norm_url` 去取一个都取不到 —— 而取不到不会报错，
    # 只会印出一个「0 个有 JD 正文」，看起来像一条结论。
    with_jd = [e for e in bare
               if (details.get(e.get("url")) or {}).get("description")]
    eg = "、".join((e.get("title") or "?")[:14] for e in bare[:3])
    # **最近一批还犯不犯。** 这条原来只有全库累计数 —— 而那个数只会随产量涨，
    # 改好了也降不下来（判据见 `batch_note` 上面那段，本文件已有三条在用它）。
    # 实测 2026-08-30 接上之后：最近那个像样的批次（08-27，36 个）里
    # **13 个没写是哪一条**，也就是说这不是存量遗留，是现在还在犯。
    # 分组用 `rank_date`（344 个判死的全都有），不是文件时间。
    _bn = batch_note([(str(e.get("rank_date") or "")[:10], not _exclusion_reason(e))
                      for e in fails if e.get("rank_date")])
    return [("warn", "判了排除却没说是哪一条",
             f"{len(bare)} 个岗的判词只写了「明确排除」四个字"
             f"（这道门一共判死 {len(fails)} 个）。"
             f"04-job-evaluation.md 那一节明写着：写不出是哪一条，那就不该判 FAIL。"
             f"这一档是七道门里唯一你今天就能改的 —— 而这批连「该放宽哪一条」都指不出来，"
             f"它们在名单上和真的不满足长得一模一样，不会再出现。"
             f"其中 {len(with_jd)} 个有 JD 正文，重判就点得出名或者当场翻案；"
             f"另 {len(bare) - len(with_jd)} 个只有标题和卡片字段。"
             + (f"{_bn}。" if _bn else "")
             + 
             f"例：{eg}。"
             f"重判它们：跑 /job-rank --all")]


def check_gate_is_one_of_the_seven(seen, details) -> list:
    """硬门要按**七道正规门名**写。写成别的，全流程都认不出来。

    `04` 第一步把硬门定成七道，写进 `_cli.GATES`。可门名那一格是自由文本，
    实测 2026-08-23 有 19 个岗写在七道之外：

        技术栈 7 · 地点 4 · 英语 4 · 语言 2 · 行业经验 1 · 专业 1

    **代价不是措辞不齐，是这批岗对整条流水线隐形。** 归类走 `gate_of()`，
    认不出就没有门名——面板那张分档表把它们扫进「没说是哪道」（看起来像漏填），
    下面每一条按门名分流的检查（`check_every_gate_is_judged`、
    `check_gate_fail_without_evidence`）则根本不看它们。

    **多数其实是真门，只是名字写错了。** 他资料里白纸黑字写着
    「跨城市搬迁才是硬门」、「要求英语口语沟通的按硬门处理」——
    那两类（地点 4 + 英语/语言 6）是**候选人明确排除**，照其余 393 个的写法
    应当写成 `候选人明确排除（跨城搬迁）`。写对了名字，它们才进得了那一档，
    也才会被「排除理由要能在资料里找到出处」那条查到。

    剩下的（技术栈 7、行业经验 1、专业 1）是另一回事：**那两样本来就是要打分的
    维度**（专业能力、业务领域）。提成门等于用「有一项对不上」替掉整套加权，
    而一票否决意味着四维一分不打、用户再也看不见这个岗。

    **判「留意」不判「要修」**：这两类的处置不一样（一类改名、一类重评），
    还有第三种可能是该往七道里加一道门（改 `04` 和 `_cli.GATES` 两处）——
    那是人的决定。本仓库的「要修」都配一个机械修法（`--apply`），这条没有，
    而一个永远红的审计会被当成背景噪音略过。
    """
    # **判词里点到的每一道门都要查，不能只查第一道。**
    # `_cli.gate_in_verdict`（单数）只取第一道是对的 —— 它服务于「有几个岗被
    # 这道门挡住」，拆开会让计数大于岗数。但这条查的是**门名写得规不规范**，
    # 漏看第二道就等于放过它：实测 2026-08-29，`硬门 FAIL (工作年限 +
    # 行业背景硬要求)` 这种第一道合法、第二道不合法的写法有 22 个，
    # 按单数那个查一个都报不出来（7 → 29）。
    hit = []
    for _k, e in seen.items():
        if not isinstance(e, dict):
            continue
        _known, off = _cli.gates_in_verdict(e.get("rank_verdict"))
        if off:
            hit.append(("+".join(off), e))
        b = e.get("rank_breakdown")
        hc = b.get("硬性条件") if isinstance(b, dict) else None
        if isinstance(hc, dict):
            bad = [k for k in hc if not _cli.gate_of(k)]
            if bad:
                hit.append(("+".join(bad), e))
    if not hit:
        return []
    # 括号里的备注不进分档：`地点（跨城搬迁）` 和 `地点（需迁往郑州）` 是同一类。
    # 分开算的话这一行全是 1，读不出哪一类被当成门用得最多。
    by = collections.Counter(i.split("(")[0].split("+")[0].strip() for i, _e in hit)
    return [("warn", "硬性条件：门名没按七道正规名写",
             f"{len(hit)} 个岗判了硬门，门名却不是七道里的任何一道"
             f"（{'、'.join(f'{i} {n}' for i, n in by.most_common(6))}）。"
             f"这批岗对按门名分流的检查是隐形的。"
             # **判据的正本在 04**（第一步「门名也只许用下表这七个」），
             # 这里只复述结论并指过去。原来反过来：整条规则**只**写在这句
             # 报错文案里，而写评估的人读的是 04 —— 他看不到它，
             # 于是照着自己的理解起名，审计再逐条抓。规则要长在写的人读的地方。
             f"地点、英语这类若资料里写了，应写成「候选人明确排除（跨城搬迁）」；"
             f"技术栈、行业经验本来就是要打分的维度，不该当门用"
             f"（判据见 04-job-evaluation.md 第一步「门名也只许用下表这七个」）。"
             f"例：{'、'.join((e.get('title') or '?')[:16] for _i, e in hit[:3])}。"
             f"修：改名或重评跑 /job-rank --all；"
             f"确实该新增一道门的，改 04 与 _cli.GATES（两处都要）。")]



def check_gate_table_names_are_one_of_the_seven(seen, details) -> list:
    """深评那张「硬性条件」表的第一列，门名也只许用七道。

    ## 为什么单独一条，不并进上面那个

    **门名有两个住址**：判词里那串，和这张表的第一列 —— 而**面板渲染的是后者**。
    2026-08-30 实测：把判词里那 29 条改成正规名之后，上面那条报 0，而面板上仍有
    72 行自造名（专业 62、地点 54、英语 8…）—— 检查说全清了，用户看到的还是
    老样子。`test_a_made_up_gate_name_is_not_an_open_question` 当场抓到这个背离，
    它比的正是「审计报的」和「面板显示的」是不是同一批。
    **同一件事有多个住址，而检查只去了一个** —— 这天第四次。

    并进上面那条试过，当场坏了另一件事：那条是拿 `seen` 驱动的、构造得出来，
    而这张表在文件系统里。合成一条之后，喂它一份干净的构造数据，它照样去读
    真库、照样报 —— **一个不由入参决定的检查，测试就再也钉不住它**
    （`test_the_gate_name_is_one_of_the_seven` 立刻红了）。
    所以按数据来源拆开：库里的归库里那条，文件里的归这条。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    import export_web_data as ex
    hit, by = [], collections.Counter()
    for f in sorted(apps.glob("*/evaluation.md")):
        try:
            rows = ex.parse_gates(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        bad = [(g.get("name") or "").strip() for g in rows
               if not _cli.gate_of(g.get("name") or "")]
        if bad:
            hit.append((f.parent.name, bad))
            by.update(bad)
    if not hit:
        return []
    return [("warn", "硬性条件：深评表里的门名没按七道正规名写",
             f"{len(hit)} 份深评的硬性条件表里有七道之外的门名，共 "
             f"{sum(by.values())} 行（{'、'.join(f'{i} {n}' for i, n in by.most_common(6))}）。"
             f"面板渲染的正是这张表 —— 用户看到的就是这些名字；"
             f"而按门名分流的检查一律看不见它们。"
             f"归位规则见 04-job-evaluation.md 第一步那两条"
             f"（「他自己不接受/达不到」的归候选人明确排除并写清哪一条；"
             f"「能力够不够」的本来就是要打分的维度，不该当门用）。"
             f"例：{'、'.join(n[:18] for n, _b in hit[:3])}。"
             f"修：逐个 /job-apply <职位链接> 重出深评，或直接改那张表的第一列。")]


#: 正本在 `_cli.EXCLUSION_SECTIONS`（2026-08-31 搬过去 —— 面板那一侧
#: 也要按同一套口径数「哪一条最贵」，而本模块反过来 import
#: `export_web_data`，共用只能放 `_cli`）。
_EXCLUSION_SECTIONS = _cli.EXCLUSION_SECTIONS


def _exclusion_anchors(user: str) -> set:
    """他资料里那几节排除条款的**二字片段**集合。读不出返回空集。

    用二字片段而不是整句比对：理由那一格是自由文本，写「英语口语」「英语流利」
    「口语沟通」的都有，指的是同一条。只要它和某条排除条款共享一个二字词，
    就认为找得到出处 —— **宁可漏报，不可误报**：这条检查一旦假阳性，
    用户就会开始忽略它。
    """
    p = ROOT / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return set()
    lines = p.read_text(encoding="utf-8").splitlines()
    keep, on = [], False
    for ln in lines:
        if ln.lstrip().startswith("#"):
            on = any(s in ln for s in _EXCLUSION_SECTIONS)
            continue
        # 那三节之外也认：**任何自称硬门 / 一律排除的行**。
        # 2026-08-29 实测栽在这儿 —— 「跨城市搬迁才是硬门」这条真硬门写在
        #  的通勤那一行，不在三节里，于是一个按它判出局的岗被报成
        # 「按一条他没设过的排除杀了岗」。**规则住在一处，检查去了另一处** ——
        # 同一个形状这天撞了三次。放宽只会让这条检查更少开口（宁可漏报），
        # 不会制造假阳性。
        if on or "硬门" in ln or "一律排除" in ln:
            keep.append(ln)
    text = "".join(re.findall(r"[一-鿿A-Za-z]+", "".join(keep)))
    return {text[i:i + 2] for i in range(len(text) - 1)}

def _exclusion_reason(e: dict) -> str:
    """判据正本在 `_cli.exclusion_reason`（面板那一侧同一个函数）。"""
    return _cli.exclusion_reason(e.get("rank_verdict"))


def _orphan_exclusions(fails, anchors) -> dict:
    """理由那一格写的词，在他资料的排除/边界两节里找不到出处的。

    `{那个词: [岗位名, ...]}`。按 `+`、顿号切开逐段查——
    「算法工程 + 英语」两段各有各的出处，整串比对会把它整条误报。
    """
    out = {}
    for e in fails:
        r = _exclusion_reason(e)
        if not r:
            continue
        for part in re.split(r"[+＋、,，]", r):
            part = "".join(re.findall(r"[一-鿿A-Za-z]+", part))
            if len(part) < 2:
                continue
            if any(part[i:i + 2] in anchors for i in range(len(part) - 1)):
                continue
            out.setdefault(part, []).append((e.get("title") or "?")[:16])
    return out


def check_exclusions_trace_to_the_profile(seen, details) -> list:
    """「明确排除」判的 FAIL，得说清是他哪一条排除，而且那一条得真的存在。

    这一档是七道硬门里**唯一一个他自己设的** —— 别的都是市场那边的门，
    改不了；这一条想通了就能改。可要决定放宽哪一条，他得先知道每条的价格。

    实测活动用户 2026-08-22，415 个「明确排除」FAIL：

        296 (71%)  没说是哪一条 ← 一条都定不了价（**这一档 2026-08-25 搬去
                   `check_an_exclusion_fail_must_name_the_rule`，理由见下面判定体
                   里那段注释**；留在这张表里是因为它是当时那次实测的一部分）
         18        行业背景硬要求
         14        英语口语
          8        营销职能
          8        生物医药 / 后端研发岗 / 企业信息化 ← 资料里一次都没出现过

    最后那一类是**评估自己造的门**（或者至少是随手写的标签，回头谁也对不上）。
    而这份资料里已经记了两次同类事故，两次都是用户自己发现的：

    - 英语那一条件他原样记过：原来只排除「口语沟通不了」这一种，执行时被扩大成
      「凡沾英语一律排除」；
    - 专业清单那一条也记过：某日早上按硬门写进去，同一天本人放宽成减分。

    **一个只有用户自己能发现的错误，就是一个迟早不会被发现的错误。**

    比对用二字片段，宁可漏报不可误报——这条检查一旦开始假阳性，
    用户就会连真的一起忽略。
    """
    fails = [e for e in seen.values()
             if isinstance(e, dict)
             and _gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"]
    if not fails:
        return []
    out = []

    # **「没说是哪一条」那半不在这儿报了。** 它归
    # `check_an_exclusion_fail_must_name_the_rule`（2026-08-25 拆出去）。
    # 拆的理由有三条，每条都单独够：
    #
    # 1. **同一个数字当时挂在三处**：这儿一处、「哪一条排除最贵」的口径声明
    #    一处、新那条一处。这个仓库治过很多次「一个概念两处各写一份」，
    #    而这次是三处 —— 三处的说法已经不一样了（这儿说「没法决定放宽哪一条」，
    #    规格里说「那就不该判 FAIL」，那才是真正的处置）。
    # 2. **这儿那一版没有命令。** `AGENTS.md` 写死了「凡是告诉用户接下来该做
    #    什么的地方，都要把命令原样写出来」—— 读完这句他不知道该敲什么。
    # 3. **这儿那一版卡着「过半才报」的阈值**（`len(blank) * 2 > len(fails)`）。
    #    掉到 40% 它就整条沉默，而 40% 的岗被一句说不清的理由判死并不比 51% 好。
    #
    # 这个函数按它自己的名字只管一件事：**判词写的理由，在他资料里找不找得到出处。**
    anchors = _exclusion_anchors(_USER[0] if _USER else "")
    if not anchors:
        out.append(("warn", "排除条款读不出来，出处没查",
                    "`candidate.md` 里的「明确排除」「明确的能力边界」两节解析不了，"
                    "所以「判词写的理由在资料里有没有出处」这一档没查——不是没有"))
        return out

    orphan = _orphan_exclusions(fails, anchors)
    if orphan:
        n = sum(len(v) for v in orphan.values())
        out.append(("error", "按一条他没设过的排除杀了岗",
                    f"{n} 个岗判了「明确排除」，而理由那一格写的词在他资料的"
                    f"「明确排除」「能力边界」两节里一次都没出现："
                    f"{'、'.join(sorted(orphan)[:5])}。"
                    f"资料里已经记了两次同类事故（英语那条被执行成「凡沾英语一律排除」、"
                    f"专业清单被写成硬门后当天放宽），两次都是他自己发现的。"
                    f"修：python tools/audit_pipeline.py --requeue-unfounded --apply"))
    return out


#: `requeue_unfounded_gate_fails` 跳过了几个（判据不成立、但已经深评过的）。
#: 放这儿而不是当返回值，是因为那个函数的返回值有三个读者，改签名要动三处。
_REQUEUE_SKIPPED: list = []


def requeue_unfounded_gate_fails(user: str, apply: bool = False) -> list:
    """把**判据不成立**的硬门 FAIL 放回待评队列。

    三类，判据分别见对应的检查：年限那道门判错的两档
    （`check_years_gate_vs_platform_field`：平台写「经验不限」的，
    以及平台下限低到他两个年限读数里小的那个都够的）、JD 正文没抓到而对应卡片字段也空
    却照样判死的（`check_gate_fail_without_evidence`）、按一条他资料里根本没有的
    排除杀掉的（`check_exclusions_trace_to_the_profile`）。

    留着它们的后果不是「多了几条告警」，是**几十个能投的岗永远不出现在名单里**——
    对用户来说，「判不了」和「真的不满足」在界面上长得一模一样。

    只动这两类：`status` 回 `new`、抹掉 `rank_verdict` / `rank_score` /
    `rank_date` / `rank_breakdown`。**不写新判词** —— 重评是 `/job-rank` 的活，
    这里只负责把它们放回队列。

    ## 抹掉之前先存进 `prev_verdict`

    「不写新判词」和「抹掉旧判词不留痕」是两件事，第一版把它们做成了一件。

    `serve.py` 的撤销路径做的是**同一个操作**（status 回 `new` + 弹掉那四个
    `rank_*`），而它明写着：**「撤掉的判词存进 `prev_verdict` 留痕，不是删掉
    —— 事后要能查这个岗当初为什么被杀。」** 同一个动作两个写手，一个留痕、
    一个抹掉。

    实测代价（2026-08-23，活动用户）：上一次 `--apply` 退回 107 个，
    其中 **99 个的上一轮判词彻底没了**（剩下 8 个带 `prev_verdict`，
    还是更早从面板上撤销时留的）。后果三条：

    - 自检和面板都说「还有 182 个没评」，而 107 个是**判据不成立退回来的**、
      75 个才是真没评过 —— 两种东西一个数，用户读不出区别；
    - `/job-rank` 重评时拿不到「上一轮判的是 `硬门 FAIL (工作年限)`」，
      规则若没真修好，同一批会以同样的理由再死一次，而**没人看得出这是第二次**；
    - 一个岗来回弹也查不出来。

    形状与 `serve.py` 那份保持一致（`判词` / `分` / `依据` / 日期），
    只有日期那个键不同：那边是用户点的「撤销于」，这边是审计判的「退回于」。

    默认 dry-run，`--apply` 才落盘（同 `fetch_details --recheck --apply` 的惯例），
    落盘前先存一份 `.bak-before-requeue`。
    """
    # **`_USER` 要在这里也设一次。** 它原本只在 `run()` 里设，而这条修复走的是
    # 另一条入口（`--requeue-unfounded` 不经过 `run`）—— 于是 `_candidate_years()`
    # 读不到用户、返回 None、年限第二档整个跳过，而且**一声不响**：
    # 命令打印「没有这一类的岗，不用动」，看着像已经修干净了。
    _USER[:] = [user]
    path = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    # **戳要接住。** 这中间要读 candidate.md、glob 全部 details/*.json、
    # 再逐份读 evaluation.md —— 2262 条的库上是几十秒到几分钟的窗口，
    # 正是 `load_json_stamped` 那份 docstring 里写的「长窗口」。
    # 期间用户在总览页点一下「不投」，写回时就该抛 StaleWrite 让路，
    # 而不是把十分钟前的快照盖回去。
    data, stamp = _cli.load_json_stamped(path)
    seen = _cli.seen_of(data)
    details = {}
    for f in glob.glob(str(ROOT / "users" / user / "job_scraper" / "details" / "*.json")):
        try:
            j = json.loads(Path(f).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if j.get("url"):
            details[j["url"]] = j
    # 两类都放回：平台明写「经验不限」的，和正文/卡片两处都没依据的。
    # 合成一条命令而不是两条 —— 它们是同一件事的两种形状（**判据不成立**），
    # 修法完全一样，分成两个开关只会让人只跑其中一个。
    # **年限那两档一起放回，不只是「经验不限」那一档。**
    #
    # `check_years_gate_vs_platform_field` 报两档：平台写「经验不限」的（42 个），
    # 和平台下限 ≤「他两个年限读数里小的那个 + 1 年容差」的（111 个）。
    # 第一版只修了前者 —— 而后者的判据一样硬，那条检查自己写着：
    # **「小的那个都够，就没有任何一种读法能判 FAIL」**。
    # 留着不修的后果不是「多一条告警」，是 111 个可证明错判的岗一直躺在不投里。
    #
    # 分档只是**报告时的信心分级**（前者不需要读 `candidate.md`，后者需要），
    # 不是「该不该修」的分级。读不出他的年限时 `floor` 是 None，那一档整个跳过。
    yrs = _candidate_years()
    floor = min(yrs) + 1 if yrs else None
    hit = {}
    for k, e in seen.items():
        if not isinstance(e, dict):
            continue
        if "工作年限" not in str(e.get("rank_verdict") or ""):
            continue
        if e.get("evaluated"):
            # **读过 JD 的深评结论不放回。** 这条修复治的是**粗筛**按卡片字段
            # 判错的那批；深评是读了职位正文之后的判断，比它强 ——
            # 抹掉等于丢掉真做过的工作。
            #
            # 而且盘上还留着一份 `evaluation.md`，导出侧照它出判词、
            # 与 `status` 无关：放回队列的结果是 `status` 是 `new`、
            # 页面上却照样有这个岗，流水线计数对不上
            # （`test_pipeline_counts` 抓到 3 个）。
            continue
        lo = _min_years(e.get("workYears"))
        if lo == 0 or (floor is not None and lo is not None and lo <= floor):
            hit[k] = e
    hit.update({k: e for k, e in _unfounded_gate_fails(seen, details)
                if not e.get("evaluated")})
    # 第三类：按一条他资料里根本没有的排除杀掉的。判据见
    # `check_exclusions_trace_to_the_profile` —— 同样是「判据不成立」。
    anchors = _exclusion_anchors(user)
    if anchors:
        excl = [e for e in seen.values()
                if isinstance(e, dict)
                and _gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"]
        bad = {t for names in _orphan_exclusions(excl, anchors).values() for t in names}
        hit.update({k: e for k, e in seen.items()
                    if isinstance(e, dict) and (e.get("title") or "?")[:16] in bad
                    and _gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"})
    # **数一下故意没动的那些，别让它们静默消失。**
    #
    # 上面两处 `evaluated` 跳过是对的（读过 JD 的判断比粗筛强，抹掉等于丢掉
    # 真做过的工作）。但**跳过不等于没问题**：那些岗的判据同样不成立，
    # 而这个工具只报「会放回 N 个」——用户读到的是「问题就这 N 个」。
    #
    # 实测活动用户 2026-08-25：审计那两条年限检查合起来报 **25 个**误判
    # （平台下限他够的 11 + 深评引了领域年限的 14），而这里只放回 **6 个**。
    # 同一屏上两个数对不上，一个字都没解释 —— 正是这个仓库点名过的
    # 「数字 5、点开 4，用户会以为漏了一个」。
    #
    # **它们的出路不是 `/job-rank --all`**（那要重评全库，还会覆盖别的深评
    # 结论），是**逐个重跑 `/job-apply <职位链接>`** —— 深评过的岗只能用深评修。
    skipped = set()
    for k, e in seen.items():
        if not isinstance(e, dict) or not e.get("evaluated"):
            continue
        if "工作年限" not in str(e.get("rank_verdict") or ""):
            continue
        lo = _min_years(e.get("workYears"))
        if lo == 0 or (floor is not None and lo is not None and lo <= floor):
            skipped.add(k)
    # **两档要取并集，不能相加。** 上面那档从职位库来（判词 + 卡片下限），
    # 领域经验那档从深评文件来 —— 实测 2026-08-25 是 5 和 14，而**交集有 4 个**：
    # 相加会报 19，真数是 15。同一个岗被两条判据同时认出来是常事，不是巧合。
    byurl = {e.get("url"): k for k, e in seen.items()
             if isinstance(e, dict) and e.get("url")}
    for d, _q in _years_gate_smuggling_domain(max(yrs) if yrs else 0):
        f = ROOT / "users" / user / "documents" / "applications" / d / "evaluation.md"
        try:
            m = re.search(r"https?://\S+", f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        k = byurl.get(m.group(0).rstrip("）)」，。")) if m else None
        if k:
            skipped.add(k)
    _REQUEUE_SKIPPED[:] = [len(skipped)]
    hit = list(hit.items())
    if not hit or not apply:
        return [k for k, _ in hit]
    # 备份也走 `atomic_write`：半截的备份比没有备份更坏——出事时你以为手里有一份。
    _cli.atomic_write(path.with_suffix(".json.bak-before-requeue"),
                      path.read_text(encoding="utf-8"))
    today = _dt.date.today().isoformat()
    for _k, e in hit:
        # **先留痕再抹。** 形状同 `serve.py` 的撤销路径（那边的 docstring 写着
        # 「事后要能查这个岗当初为什么被杀」）——同一个操作，两个写手要说同一句话。
        # 已经有 `prev_verdict` 的不覆盖：那是更早一次撤销留下的，更靠前的才是
        # 「当初为什么被杀」。
        # `rank_verdict` 那半是**防御性的、今天走不到**（三个选择器都以「有判词」
        # 为前提，变异实测删掉它没有任何可观察差别）。留着是因为这里是边界：
        # 将来加一个不要求判词的选择器时，它挡住的是一张 `{"判词": None}` 的空单据。
        # **别为它写测试** —— 那会是一条永远绿的断言（同 `_srcscan` 那个坑）。
        if e.get("rank_verdict") and not e.get("prev_verdict"):
            e["prev_verdict"] = {
                "判词": e.get("rank_verdict"), "分": e.get("rank_score"),
                "依据": (e.get("rank_breakdown") or {}).get("依据"),
                "退回于": today,
            }
        # `prev_score` 单独存一份：`/job-apply` 拿它和 `rank_score` 现算粗筛
        # 与深评的落差（`test_the_coarse_score_is_not_inflated`），
        # 那条路读的是这个平铺字段，不是上面那个字典。
        if e.get("rank_score") is not None and e.get("prev_score") is None:
            e["prev_score"] = e.get("rank_score")
        e["status"] = "new"
        # **`rank_breakdown` 也要抹。** 只抹前三个字段时，导出侧照着留下的
        # 四维拆解重建出了判词 —— 于是 `status` 是 `new`、页面上却照样有这个岗，
        # 流水线计数对不上（`test_pipeline_counts` 抓到 3 个）。
        # 一个岗要放回队列，它的深评拆解同样是陈的。
        for f in ("rank_verdict", "rank_score", "rank_date", "rank_breakdown"):
            e.pop(f, None)
    _cli.atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2),
                      expect=stamp)
    return [k for k, _ in hit]


def check_extra_resumes_are_never_audited(seen, details) -> list:
    """`resume/` 底下不止一份 `.typ`，而整条流程只认 `main.typ`。

    国内求职常见**两份并行**：网申/打招呼用的精简版，和猎头要、面试带的详版。
    目录本来就放得下，用户也确实这么用了 —— 实测活动用户 2026-08-23：

        main.typ        12 KB   ← /job-resume、/job-apply、/job-cv 全都写死这一个
        main-长版.typ    15 KB   ← 从来没有任何一步打开过

    危险的不是「少审一份」，是**审完之后那句话**：报告抬头叫「简历审核」、
    结论写「必须改：无」，用户读到的是「我的简历没问题」。同这个仓库那条
    「「没查」和「查过没有」是两件事」—— 而这里连「没查」都没说。

    两份并行还会**漂**：改了 `main.typ` 忘了改另一份，数字对不上，
    面试或背调时是要解释的。

    ## 为什么判「留意」

    多出来的那份也许是废稿、也许是他有意留的详版 —— **工具判不了，也不该替他判**
    （`job-resume.md` 那一步写的是「顺带问一句它是干什么用的，别替他决定」）。
    这里只负责让它别再隐形。同族的 `check_greeting_keeps_the_five_rules`
    也是这一级：没有机械修法的都不判 error。
    """
    user = _cli.pick_user("", root=ROOT)
    d = ROOT / "users" / user / "resume"
    # 目录不存在不必先判：`glob` 在缺目录上返回空，不抛。
    # （换成 `iterdir()` 就会抛 —— `test_it_survives_a_missing_directory` 盯着这一点。）
    extra = sorted(f.name for f in d.glob("*.typ")
                   if f.name not in ("main.typ", "template.typ"))
    if not extra:
        return []
    reports = ROOT / "users" / user / "reports"
    audits = sorted(reports.glob("resume-audit-*.md")) if reports.is_dir() else []
    tail = (f"最近一份审核 {audits[-1].name} 只覆盖了 main.typ。"
            if audits else "还没跑过 /job-resume。")
    msg = (f"{len(extra)} 份：{chr(12289).join(extra)}。"
           f"/job-resume 审 main.typ、/job-apply 与 /job-cv 发 main.pdf —— "
           f"整条流程写死这一个名字。{tail}"
           f"报告说「必须改：无」时，用户读到的是「我的简历没问题」，"
           f"而不是「我那几份里的一份没问题」。"
           f"两份并行还会漂：改了一份忘了另一份，数字对不上，面试或背调要解释。"
           f"修：跑 /job-resume 时按 Step 1 那一节点名，并问清那份是干什么用的")
    return [("warn", "resume/ 底下还有别的简历，没有任何一步读过它", msg)]


#: 台账那 13 列里，**空着也没关系的那些** —— 数据在别处都有，推得出来。
#:
#: 这张表存在的唯一理由是**别喊狼来了**。实测活动用户 2026-08-24：13 列里
#: 7 列是 100% 空的，而它们各有 2~14 个消费方。七条一起报，读的人第二次就
#: 会把整条检查略过（同这个仓库那句「一个永远红的审计等于没有审计」）。
#:
#: 值是「它的数据在哪儿」—— 写出来是为了让下一个人能核，而不是信这张表。
DERIVABLE_TRACKER_COLS = {
    "sector": "行业看职位库的 `compIndustry`",
    "role_type": "岗位类型从 `role` 与 JD 现读",
    "channel": "`tracker.channel_of` 从 `source` 链接现推",
    "fit_rating": "匹配度看职位库的 `rank_score`",
    "cv_file": "材料路径就是 `documents/applications/<公司>_<岗位>/`",
    "cover_letter_file": "同上",
}


def _surname_note(seen: dict, rows=None) -> str:
    """姓名从哪来。**取不到就直说取不到**，别让人去翻一个空字段。

    猎聘 CLI 2026-08-25 起会把招聘者截成姓输出（`recruiterSurname`），
    所以「库里就有」这句话在原理上成立；实测它到 2026-08-30 只覆盖到极少数岗。
    原来那句无条件写「猎聘的岗库里就有，直接取」—— 对 99% 的岗是句假话，
    而假话的代价不是这一次白翻，是他下次连这条建议一起不信。

    ## 数的是**台账里补得上的那几行**，不是库里有几个姓

    上一版数的是职位库（2026-09-01 实测 6 个），而这句话是接在
    「台账里 88 行一个都没填」后面的 —— 读的人自然理解成「这 88 行里有 6 行
    能直接补」。**实测对得上的只有 1 行**：另外 5 个姓挂在他从没投过的岗上，
    台账里根本没有对应的行，补无可补。

    差 6 倍的数就摆在「补它：」那句话里，而这正是上一版立这个函数时写下的
    那条理由 —— **能取到几个就说几个**。当时把「库里有没有」当成了
    「补得上几个」，只学到一半。

    `rows` 传不进来（老调用点）时退回只说库里那个数，并**明说它是库里的**，
    不装成台账的。
    """
    have = sum(1 for v in seen.values()
               if isinstance(v, dict) and str(v.get("recruiterSurname") or "").strip())
    if not have:
        return ("库里现在一个姓都没有（猎聘 CLI 会输出 `recruiterSurname`，"
                "但这批岗上是空的），所以都得在页面上看一眼或问一句")
    if rows is None:
        return (f"职位库里有 {have} 个姓（`recruiterSurname`），"
                f"能对上台账哪几行没算，其余的在页面上看一眼或问一句")
    by_url = {}
    for v in seen.values():
        if isinstance(v, dict) and v.get("url"):
            by_url[_cli.norm_url(v["url"])] = v
    fillable = sum(
        1 for r in rows
        if str((by_url.get(_cli.norm_url(str(r.get("source") or "")))
                or {}).get("recruiterSurname") or "").strip())
    if not fillable:
        return (f"职位库里那 {have} 个姓一个都对不上台账里的行"
                f"（挂在没投过的岗上），所以都得在页面上看一眼或问一句")
    return (f"其中 {fillable} 行能从职位库直接取（`recruiterSurname`；"
            f"库里共 {have} 个姓，其余挂在没投过的岗上），"
            f"剩下的在页面上看一眼或问一句")


def check_tracker_columns_nobody_fills(seen, details) -> list:
    """**台账里有人读、没人写的列。** 那几条规则从来没跑过，而且不会报错。

    `check_orphan_consumers` 查的是**职位库**那一面（`seen_jobs.json` /
    `details/`）。台账是另一个平面，此前没有任何东西查它 —— 而那儿真的有一个：

        contact_person   85 行填了 0 行，却有三处在读（实测 2026-08-24）

            /job-outcome followup 的跟进话术   有名字→称呼他，没有→称呼「团队」
            Step 2b 起草的跟进                 同上
            /job-interview 查面试官从哪切入     没有→整段跳过

    三处都**优雅降级**了，所以从头到尾没有一行报错 —— 用户只是每次都拿到
    次一等的东西，而没人告诉过他。国内平台上这个名字是白给的：猎聘 / BOSS
    的会话顶栏一直挂着对方姓名与职位，他打招呼那一刻就在屏幕上。

    **而猎聘连问都不用问**：搜索接口每张卡片都带 `recruiter.recruiterName`，
    CLI 2026-08-25 起把它截成姓输出（`recruiterSurname`）。实测那天库里
    2232/2637 个岗来自猎聘搜索、已投的 85 笔里 66 笔是它 —— 七成八本来就
    白给。所以下面那条修法是「先取后问」，不是「问一句」。

    ## 只报推不出来的

    另外 6 个空列的数据在别处都有（见 `DERIVABLE_TRACKER_COLS`），报它们
    是噪音。判「留意」不判「要修」：这不是数据脏，是**少拿了一样本可以有的
    东西**，而补它要人开口，机器补不了。
    """
    import csv as _csv
    user = _cli.pick_user("", root=ROOT)
    f = ROOT / "users" / user / "job_search_tracker.csv"
    if not f.is_file():
        return []
    try:
        with f.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(_csv.DictReader(fh))
    except (OSError, ValueError, UnicodeDecodeError):
        # 台账被 Excel 存成 GBK 是真事（`load_tracker` 为此写过注释）。
        # 读不了就不说 —— 审计不该因为一个可选检查整个炸掉。
        return []
    if not rows:
        return []
    cols = [c for c in (rows[0].keys() or ()) if c]
    # 消费方：`workflows/` 与 `tools/` 里按整词引用这个列名的文件。
    #
    # **排除三个「写它的人」——他们提到列名，但一个字都没读。**
    #
    #   tracker.py        列定义本身
    #   audit_pipeline.py **这段说明**（上面 docstring 里就写着 `contact_person`）
    #   job-scrape.md     抓取侧的字段价值表，写的是这一列的**上游从哪来**
    #
    # 前两个是第一版就踩过的（当时报「5 处在读」，其中一处是它自己）；
    # 第三个是 2026-08-25 当场又踩了一遍：那天往那张表里加了
    # 「`recruiterSurname` → 台账的 `contact_person` 列」一行，
    # 报出来的读者立刻从 4 变成 5。**每次有人写一句「谁在读它」，
    # 这条检查就会把那句话本身数成一个读者。**
    srcs = [x for x in
            list((ROOT / "workflows").rglob("*.md")) + list((ROOT / "tools").glob("*.py"))
            if x.name not in ("tracker.py", "audit_pipeline.py", "job-scrape.md")]
    texts = {x.name: x.read_text(encoding="utf-8", errors="replace") for x in srcs}
    out = []
    for c in cols:
        if c in DERIVABLE_TRACKER_COLS:
            continue
        if any((r.get(c) or "").strip() for r in rows):
            continue
        readers = sorted(n for n, t in texts.items()
                         if re.search(r"\b" + re.escape(c) + r"\b", t))
        if len(readers) < 2:            # 一个消费方以下：还称不上「规则没跑过」
            continue
        skipped = "、".join(f"{k}（{v}）" for k, v in DERIVABLE_TRACKER_COLS.items()
                            if k in cols and not any((r.get(k) or "").strip()
                                                     for r in rows))
        out.append((
            "warn", "投递记录里有人读、没人写的列",
            f"`{c}` 在 {len(rows)} 行里填了 0 行，而 {len(readers)} 处在读它："
            f"{'、'.join(readers)}。这几处都写了降级路径，所以一行错都不会报 —— "
            f"用户只是每次都拿到次一等的东西。"
            + (f"（另外几列空着不算问题，数据在别处：{skipped}）" if skipped else "")
            # **「岗库里就有，直接取」这句话原来是假的。**
            # 实测 2026-08-30：岗库 1839 条里 `recruiterSurname` 有值的 **0 条**
            #（详情库里真有值的 6 份，而 `jd_store` 的回填表里没有它，
            # 搬不过去 —— 同日已补进 `MERGE_FIELDS`）。
            #
            # 让人去「直接取」一个空字段，他取不到、以为自己弄错了，
            # 下次连这条建议一起不信。**能取到几个就说几个。**
            + f"补它：下次跑 /job-outcome 时按 Step 4「顺手把对方的姓名记下来」"
            f"那一节 —— {_surname_note(seen, rows)}"))

    return out


def check_pool_signal_is_computable(seen, details) -> list:
    """**04 的「蓄水池嫌疑」自己给自己下过一道封条，而没人回来揭。**

    那一行原来写着：「这条要等 `date` 真的会更新之后才算得出来 —— 在那之前抓的岗
    `date` 从首次抓到起就冻着（实测 578 个有日期的岗，`date` 一律早于
    `first_seen`）。**算不出来就写「无」**」。

    封条是对的 —— 当时确实算不出来。问题是**没有任何东西会告诉你它什么时候
    解冻**：`job-scrape.md` Step 4 那条「查重命中时更新 `date`」后来生效了，
    实测 2026-08-24 已经有 2 个岗 `date` 晚于 `first_seen`（都晚 2 天），
    而 04 还在让执行者一律写「无」。一整行真伪信号就这么永久躺平。

    所以这里两头都报，报法不同：

        一个都算不出来   → 说清楚封条还成立，别让人以为规则在跑
        算得出来了       → 说清楚它解冻了，并给出现在的分布

    ⚠️ **判「留意」不判「要修」。** 数据没脏，脏的是文档里那个数会过期；
    而它过期与否只有拿真库现算才知道 —— 这正是审计存在的理由。
    """
    import datetime as _dt

    def _d(x):
        try:
            return _dt.date.fromisoformat(str(x)[:10])
        except (TypeError, ValueError):
            return None

    pairs = []
    for e in seen.values():
        a, b = _d(e.get("date")), _d(e.get("first_seen"))
        if a and b:
            pairs.append((a - b).days)
    if len(pairs) < 30:
        return []                       # 样本太小，说不出话来
    later = [n for n in pairs if n > 0]
    same = sum(1 for n in pairs if n == 0)
    share = len(pairs) * 100 // max(1, len(seen))
    head = (f"{len(seen)} 个岗里 {len(pairs)} 个同时有 `date` 与 `first_seen`"
            f"（{share}%，`date` 只有猎聘给）")
    if not later:
        return [("warn", "「蓄水池嫌疑」还是算不出来",
                 f"{head}，没有一个 `date` 晚于 `first_seen` —— "
                 f"招聘方把岗顶上去这件事我们一次都没观测到。"
                 f"04 那一行现在的说法是「两个日期齐了才判」，"
                 f"照它执行的结果就是这一行永远写「无」。"
                 f"这不是数据脏，是那条信号眼下没有依据；"
                 f"别让它看起来像在生效。"
                 f"要确认抓取那侧还在更新 `date`：看 "
                 f"job-scrape.md Step 4「查重命中时，只更新一个字段」那一节")]
    return [("warn", "「蓄水池嫌疑」算得出来了",
             f"{head}，其中 {len(later)} 个 `date` 晚于 `first_seen`"
             f"（最多晚 {max(later)} 天）、{same} 个同一天。"
             f"这条信号已经解冻 —— 04 里那句实测数要跟着更新，"
             f"否则下一个执行者照旧一律写「无」。"
             f"对上这几个岗时把天数写进「职位真伪信号」那一节")]


#: 三样都在 `_cli`（`exclusion_entries` / `bigrams` /
#: `exclusion_tally`）。这边只留别名，别再各写一份 ——
#: 「每条各挡掉多少」现在面板也在数，两套算法就是两个数。
_exclusion_entries = _cli.exclusion_entries
_bigrams = _cli.bigrams


def check_which_exclusion_costs_the_most(seen, details) -> list:
    """**04 说该数的那张表，此前没有任何一处在数。**

    那一节要求「命中时必须写清是哪一条排除」，理由写得很清楚：

    > 为什么单这一道门要求写清楚：它是七道里唯一他能改的。学历、年限、户口、
    > 应届身份都不是他今天能动的；而排除项是他自己下的结论，随时可以放宽一条。
    > 但要决定放宽哪一条，他得先知道**每条各挡掉了多少个岗**。

    规则立了，实测 2026-08-24 也真的有 101 个岗写清了是哪一条 ——
    **而那个「每条各挡掉多少」从来没被算出来过。** 面板的 `gateFailTally`
    按门名分组，这道门在那儿只是一个 421 的整数。

    ## 归到「他资料里的哪一行」，不是归到那句自由文本

    理由格是自由文本：同一条排除写成「英语口语」「英语流利」「英语听说」
    「英语面试」的都有。照字面分组会把一条排除拆成四份，谁也看不出它最贵。
    所以按二字片段把每条理由**归到他资料里那一行** —— 判据与
    `_exclusion_anchors` 同源（宁可漏报不可误报），实测 101 条里归上 100 条。

    ## 那个数是下限，必须说出来

    325 个岗没写是哪一条，进不了这张表。不声明的话，读的人会把
    「第一条挡了 47 个」当成全貌，而真实数最多能到四倍。
    """
    user = _cli.pick_user("", root=ROOT)
    ents = _exclusion_entries(user)
    if not ents:
        return []
    fails = [e for e in seen.values()
             if "FAIL" in str(e.get("rank_verdict") or "")
             and _gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"]
    if len(fails) < 20:
        return []                       # 样本太小，排不出「哪条最贵」
    tally, blank, orphan = _cli.exclusion_tally(
        ents, [_exclusion_reason(e) for e in fails])
    if not tally:
        return []
    # 资料原文是 markdown，而这句话直接上终端 —— 走面板那份正本
    # `export_web_data.plain()`（剥标记 + 把内部词换成人话），别在这儿另写一遍。
    # 截断也不能按字数硬切：实测切出过一条排除规则的前半截，尾巴上挂着
    # 一个孤零零的开引号。按标点找一个能收住的地方。
    # 缩写走导出侧那一份（`short_rule`）—— 面板上那几个标签用的是
    # 同一个函数，两处各切各的就会出现「同一条排除，两种叫法」。
    import export_web_data as _ex

    top = "；".join(f"「{_ex.short_rule(k)}」挡掉 {n} 个"
                   for k, n in tally.most_common(3))
    return [("warn", "哪一条排除最贵",
             f"{len(fails)} 个岗死在「你自己划的排除」这道门上，"
             f"其中 {sum(tally.values())} 个写清了是哪一条，归到你资料里 "
             f"{len(tally)} 条不同的排除上。最贵的三条：{top}。"
             f"这是七道门里唯一你今天就能改的一条 —— 觉得某一条划得太宽，"
             f"跑 /job-setup --section exclusions 改它，再跑 /job-rank --all 重评。"
             # **这里只声明口径，不重讲规则。** 那条规则连同它的处置办法
             # 归「判了排除却没说是哪一条」那一条报（同一个数字挂在两处讲，
             # 两处迟早分叉 —— 这个仓库治过很多次）。
             + (f"（另有 {blank} 个岗只写了「明确排除」、没说是哪一条，"
                f"进不了这张表 —— 上面那几个数是下限，不是全貌）"
                if blank else "")
             + (f"（还有 {orphan} 个理由在你资料里对不上任何一条）"
                if orphan else ""))]


def check_referral_note_is_missing(seen, details) -> list:
    """具名直招的材料里没有内推请托 —— 那是这些岗唯一不靠海投的一条路。

    `06-outreach-templates.md` 渠道 5 与 `/job-apply` 第 1.6c 都写着这一节，
    **而它只对具名直招成立**（猎头代招的简历进的是
    猎头的库，匿名雇主连找谁都不知道）。判据是机器算得出来的：
    `isHeadhunter` 为假 + 公司名不是「某……公司」这类脱敏写法。

    实测活动用户 2026-08-25：符合这个判据、且已经出过材料的 98 个岗里，
    **只有 1 个有这一节** —— 就是规则上线当天那一个；其余 97 个全产于它之前。

    ## 这个数说的是存量

    和「「可以考虑」的深评没写要问什么」那条同样的处境：规则 2026-08-24 才上线，
    这批材料多数比它早。**存量说明不了规则灵不灵**，跑一批新的才有得比。
    报它是因为那 97 份材料多数还没投 —— 缺的不是一段可有可无的话，
    是那个岗**唯一那条能绕开简历筛的路**。

    ## 判「留意」不判「要修」

    补得上（`/job-apply` 那条 `materials` 分流现在会只补这一节），但补不补是
    用户的判断 —— 找不找得到人只有他知道，而渠道 5 那一节明写着
    「别把这一节当成默认动作催用户」。同族的「深评缺小节」也是这一级。
    """
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    # 具名直招：判据与 `/job-apply` 1.6c 同源，不在这儿另立一套。
    named = {}
    for e in seen.values():
        if not isinstance(e, dict) or not e.get("url"):
            continue
        if _cli.via_headhunter(e) is not False:
            continue
        comp = str(e.get("company") or "").strip()
        if not comp or comp.startswith("某") or "未公开" in comp:
            continue
        named[_cli.norm_url(e["url"])] = e
    if not named:
        return []
    miss, have_l = [], []
    for f in sorted(apps.glob("*/outreach.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        m = LINK_LINE.search(t)
        if not m or _cli.norm_url(m.group(1)) not in named:
            continue
        # 日期取同目录的深评抬头（话术文件自己没有那一行，见 `_dated_text`）。
        (have_l if "内推请托" in t else miss).append(
            (f.parent.name, _eval_date(_dated_text(f))))
    have = len(have_l)
    if not miss:
        return []
    n = len(miss) + have
    newest = max((d for _x, d in miss if d), default="")
    span = f"，最新一份 {newest}" if newest else ""
    return [("warn", "具名直招的材料里没有内推请托",
             f"{len(miss)}/{n} 份。内推是这些岗唯一一条不靠海投的到达方式，"
             f"而它只对"
             f"具名直招成立 —— 这几个岗恰好是全库里唯一有这条路的那批"
             f"（判据见 /job-apply 第 1.6c）。"
             f"这个数说的是存量{span}：这一节 2026-08-24 才上线，"
             f"比它晚的 {have} 份有 —— 样本这么小，说明不了规则灵不灵，"
             f"跑一批新的才有得比。补它：跑 /job-apply 全部 —— 有材料的岗现在会"
             f"只补这一节，不重跑深评、不重出简历。"
             f"例：{'、'.join(x[0][:16] for x in miss[:3])}。"
             f"⚠️ 补的是稿子，不是催你去找人 —— 渠道 5 那一节明写着"
             f"「别把这一节当成默认动作催用户」")]


#: 「强度与公司性质」那一维在 `rank_breakdown` 里的键名（含历史写法）。
_INTENSITY_KEYS = ("强度与公司性质", "工作强度与公司性质", "强度")


#: 渠道要有多少个岗，才值得对它的 JD 抓取率下结论。
#: 太小的样本上「0 个有 JD」可能只是还没轮到它抓。
_JD_RATE_MIN_JOBS = 20

#: JD 抓取率低到什么程度才**开始怀疑**。
#: 不用 0：偶尔有一两个是从别的通道补进来的（同一个岗浏览器抓过一次）。
_JD_RATE_FLOOR = 0.05

#: 一个链接底下挂几个岗，才算「这不是职位页」。
#:
#: **2 不够。** 同一个职位页被两次抓取写成两条、或者重复挂牌，都会撞出 2 来 ——
#: 猎聘 1901 个岗里就有一对（实测 2026-08-25），而猎聘的链接是好的。
#: 3 个毫不相干的岗共用一个链接才没有良性解释：实测前程无忧那一个底下是
#: 安卓研发工程师 / 运营实习生 / 后端开发实习生。
_SAME_URL_TOO_MANY = 3


#: 「个人优势」第一条里，算「可核验」的成绩写法。
#:
#: **工龄不算。** 「十年某行业」里的「十年」是个数字，却什么也证明不了 ——
#: 实测这一条最初的判据是「第一条里有没有数字」，而带数字的那两份恰恰是最弱的
#: （都是「N 年……转型 AI 产品」这一类句式），没数字的那几份反倒最硬
#: ——第一条指的是作品名，对方自己点得开。
#: **判据换成「指不指得到一件对方能自己去看的东西」。**
_LEAD_METRIC = re.compile(r"\d[\d,.]*\s*(?:万|K|k)?\s*\+?\s*(?:注册用户|用户|stars?|下载|收录)")


def _portfolio_names(user: str) -> set:
    """从资料的「作品与项目的分层」里抽作品名 —— 不在代码里硬编码任何一个。

    硬编码的下场是换个用户整条失效（这个仓库是行业无关的，见 `AGENTS.md`）。
    """
    p = ROOT / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return set()
    # **扫整份资料，不只扫「作品与项目的分层」那一节。**
    # 实测 2026-08-25：只扫那一节时，「Claude Agent Skills」抽不到 ——
    # 它写在「技能」那一节里，而它恰恰是这位用户最硬的那个作品名。
    # 资料整份都是他自己写的事实，作品名出现在哪一节不该影响判据。
    t = p.read_text(encoding="utf-8", errors="replace")
    # 1) 拉丁作品名（`Notewell`、`Some Open Toolkit` 这类），全文扫
    out = {m.strip() for m in
           re.findall(r"[A-Z][A-Za-z0-9\-]*(?: [A-Z][A-Za-z0-9\-]*){0,2}", t)}
    out = {n for n in out if len(n) >= 5}
    # 2) **中文作品名**，从「作品与项目的分层」那张表的「项目」列按顿号切。
    #
    #    只扫拉丁的话，「飞书文档批量导出」这类名字整个抽不到 —— 而这是个
    #    做中文求职的工具，中文产品名是常态不是例外（`AGENTS.md` 行业无关那条）。
    #    实测 2026-08-25：构造一个作品叫「某某工具箱」的用户，判据说它不算作品。
    #
    #    只从那张表取，不全文扫：中文没有大小写这种天然边界，全文切会把
    #    「产品定义」「多语言运营」这类普通短语一起当成作品名，判据就废了。
    #
    #    **按表头找「项目」那一列，只解析紧跟标题的那一张表。** 第一版写死
    #    `cells[3]`、扫标题往后 4000 字，于是把隔壁那张「多款受欢迎的具体数字」
    #    （列是 项目 | stars | 做什么）也卷了进来，抽出「做什么」「手机当摄像头」
    #    这类词 —— 那会让一句什么都没指的话蒙混过关。
    i = t.find("作品与项目的分层")
    if i >= 0:
        col = None
        for row in t[i:].splitlines():
            if not row.lstrip().startswith("|"):
                if col is not None:
                    break          # 表结束了就停，别漫进下一张表
                continue
            cells = [c.strip().strip("*") for c in row.strip().strip("|").split("|")]
            if col is None:
                if "项目" in cells:
                    col = cells.index("项目")
                continue
            if set("".join(cells)) <= set("-: "):
                continue           # 分隔行
            if col >= len(cells):
                continue
            # **先整段剥掉括号，再按顿号切。** 反过来的代价实测过：
            # 「Hotkey Chain（75+ 动作、5 种触发、可视化编辑器、18 语言）、Clockwork」
            # 先切顿号的话，括号里那串规格会各自成为一个「作品名」——
            # 于是「可视化编辑器」算作品，一句什么都没指的话就能蒙混过关。
            cell = re.sub(r"[（(][^（()）]*[)）]", "", cells[col])
            for name in re.split(r"[、,，]", cell):
                name = name.strip(" *")
                # 那一列偶尔写的是散文不是名单（「新建并发布 40 个开源仓库」）。
                # 带 markdown 强调或比较号的一律不是作品名。
                if any(c in name for c in ("*", "≥", "≤", "→")):
                    continue
                if 3 <= len(name) <= 20:
                    out.add(name)
    return out


def _chat_pitch(user: str) -> str:
    """`profile/hr-answers.md` 里「你最大的优势」那条答案的**第一小句**。

    读不出 / 还是占位符 → 空串（不判）。

    切法本身是纯函数 `_chat_pitch_of`，这里只负责找到那段话。
    """
    f = ROOT / "users" / user / "profile" / "hr-answers.md"
    if not f.is_file():
        return ""
    # **先剥 `<!-- -->`。** 那份文件里每条答案上面都挂着一段说明，而说明里
    # 常常举着正面例子（「这里要写作品名，比如 …」）—— 连着一起读，判据就被
    # 它自己的说明喂饱了。这个仓库栽过三次「注释满足断言」。
    t = re.sub(r"<!--.*?-->", "", f.read_text(encoding="utf-8", errors="replace"),
               flags=re.S)
    m = re.search(r"^##[^\n]*优势[^\n]*$(.*?)(?=^## |\Z)", t, re.S | re.M)
    if not m:
        return ""
    body = [l.strip() for l in m.group(1).splitlines() if l.strip()]
    if not body or body[0].startswith("["):     # `[YOUR_PITCH]` 这类占位符
        return ""
    return _chat_pitch_of(body[0])


def _chat_pitch_of(line: str) -> str:
    """一句答案的**第一小句**：到第一个 `——`／`。`／`；` 为止，引号剥掉。

    聊天框里那条答案的典型形状是「<一句总括>——<证据>」，破折号后面是佐证 ——
    而 HR 在聊天框里**先读到的是破折号前面那半**，跟简历只看第一条同理。
    """
    return re.split(r"——|。|；", line)[0].strip(" 「」《》\"\'")


def check_the_lead_advantage_points_at_something(seen, details) -> list:
    """简历「个人优势」第一条只是自我描述，没指向任何能核验的东西。

    ## 为什么是第一条

    国内 HR 扫简历以秒计。姓名与目标岗位那一行之后，**第一个被读到的句子就是
    「个人优势」第一条** —— 它是整份简历第二贵的位置。

    `05-cv-templates.md` 把「个人优势」定为**唯一按岗微调的段落**，也允许
    「调整排序」，但从没说过第一条该放什么。于是它经常被写成一句自我评价。

    ## 判据：指不指得到一件对方能自己去看的东西

    过：作品名（从资料的「作品与项目的分层」里抽，不硬编码）或成绩数
    （注册用户 / stars / 下载 / 收录）。
    不过：纯自我描述（「独立开发者，全程一人跑通」）、以及**只有工龄的**
    （「十年品牌市场与 BD 转型 AI 产品」）。

    **工龄那一条是这个判据的关键。** 实测活动用户 2026-08-25，13 份简历里
    5 份第一条不过关，其中 2 份写的正是「N 年……转型 AI 产品」——
    转型这件事被自己举到了最前面，读的人接收到的是「产品只做了三年」。

    ## 同一个问题有两个渠道，判据不能只管一个

    「你最大的优势是什么」在国内求职里被问两遍，而且是**同一批人**问的：
    一遍在简历上（他自己写的「个人优势」），一遍在聊天框里（HR 打字问出来，
    答案是 `profile/hr-answers.md` 里定过稿的那条）。

    那份文件开头写着它存在的全部理由：「同一个问题在打招呼、HR 初面、背调
    三处说法对不上，是面试官最容易抓的点」。**而此前判据只扫简历。**

    实测活动用户 2026-08-25：简历第一条刚改成「开源多组 <某某>，累计 1 万+
    stars」，而聊天框那条的第一小句还是「比纯技术更懂业务流程、比业务更懂
    AI 工具」——**复合型人才那句套话**，成绩数全排在破折号后面。同一个人、
    同一天、同一个 HR 会看到的两处，说的不是一件事。

    聊天框那一条切的是**第一小句**（到 `——`／`。`／`；` 为止），理由和简历
    取第一条一样：先读到的就那么多。

    ## 这一条不判「谁的优势更大」

    排序该按稀缺度还是按时间，是判断，不是机械题，这里不碰。
    它只查一件可机械判定的事：**第一句有没有落在一个能被点开的东西上。**

    ## 两个渠道各报各的，各给各的命令

    合成一条消息就得给两条命令，而「一条引导对应一条命令」是 `AGENTS.md` 里
    写死的（读完这句他能不能直接动手）。所以这里返回两条。
    """
    if not _USER:
        return []
    user = _USER[0]
    names = _portfolio_names(user)
    base = ROOT / "users" / user
    bad = []
    for f in sorted(base.rglob("*.typ")):
        if "template" in f.name:
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'#section\("个人优势"\)\s*\n((?:- .*\n)+)', t)
        if not m:
            continue
        first = m.group(1).splitlines()[0].lstrip("- ").strip()
        if any(n in first for n in names) or _LEAD_METRIC.search(first):
            continue
        who = "主简历" if f.name == "main.typ" else f.parent.name[:18]
        bad.append(f"{who}（「{first[:22]}…」）")
    out = []
    if bad:
        out.append(("warn", "简历第一条只是自我描述",
                    f"{len(bad)} 份简历的「个人优势」第一条没指向任何能核验的东西"
                    f"（例：{'、'.join(bad[:3])}）。姓名那行之后，第一个被读到的句子就是它 —— "
                    f"国内 HR 扫简历以秒计，这一句该落在一件对方能自己点开的东西上："
                    f"作品名，或者用户数、stars 这类成绩。"
                    f"注意工龄不算：「十年某某经验转型」里的数字什么也证明不了，"
                    f"反而把「转过岗」举到了最前面。"
                    f"改它：跑 /job-resume，把最能被核验的那条提到第一位"))
    pitch = _chat_pitch(user)
    if pitch and not (any(n in pitch for n in names) or _LEAD_METRIC.search(pitch)):
        out.append(("warn", "聊天框里那句优势也只是自我描述",
                    f"HR 在聊天框里问「你最大的优势」，你定过稿的那条第一小句是"
                    f"「{pitch[:26]}」——没指向任何能核验的东西。"
                    f"这跟简历「个人优势」第一条是同一个问题、同一批人在问，"
                    f"两处说法对不上正是面试官交叉验证时最容易抓的点"
                    f"（hr-answers.md 开头写的就是这件事）。"
                    f"破折号后面的成绩数提到最前面就行。"
                    f"改它：跑 /job-dashboard，在「HR 常问的」那一块里就地改"))
    return out


def requeue_no_jd_sellable(user: str, apply: bool = False) -> list:
    """把「没读 JD 却给了可投档位」的岗放回待评队列。判词留痕，不抹掉。

    形状与 `requeue_unfounded_gate_fails` 完全一致（`prev_verdict` / `prev_score`
    / `status` 回 `new` / 弹掉四个 `rank_*`），理由也一样：**事后要能查这个岗
    当初为什么被这样判**。两处共用同一套字段名，面板与 `/job-rank` 才认得。

    默认 dry-run，`--apply` 才落盘；落盘前先存一份 `.bak-before-requeue-nojd`。
    """
    _USER[:] = [user]
    path = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    data, stamp = _cli.load_json_stamped(path)
    seen = _cli.seen_of(data)
    # 档序只有一份正本（`_cli.VERDICTS`），**切片即子集** —— 抄一份出来，
    # 哪天档位改了这里就是静默失效。
    BANDS = _cli.VERDICTS[:3]
    hit = []
    for k, e in seen.items():
        if not isinstance(e, dict) or e.get("status") != "ranked":
            continue
        src = (e.get("rank_breakdown") or {}).get("来源") or ""
        if "读过 JD" in src or "读了 JD" in src or src.startswith("深评"):
            continue
        if any(b in (e.get("rank_verdict") or "") for b in BANDS):
            hit.append((k, e))
    if not hit or not apply:
        return [k for k, _ in hit]
    _cli.atomic_write(path.with_suffix(".json.bak-before-requeue-nojd"),
                      path.read_text(encoding="utf-8"))
    today = _dt.date.today().isoformat()
    for _k, e in hit:
        if e.get("rank_verdict") and not e.get("prev_verdict"):
            e["prev_verdict"] = {
                "判词": e.get("rank_verdict"), "分": e.get("rank_score"),
                "依据": (e.get("rank_breakdown") or {}).get("依据"),
                "退回于": today,
            }
        if e.get("rank_score") is not None and e.get("prev_score") is None:
            e["prev_score"] = e.get("rank_score")
        e["status"] = "new"
        for f in ("rank_verdict", "rank_score", "rank_date", "rank_breakdown"):
            e.pop(f, None)
    _cli.atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2),
                      expect=stamp)
    return [k for k, _ in hit]


def check_no_jd_but_sellable(seen, details) -> list:
    """没读 JD 正文，却给了「可以考虑」及以上的档位。

    ## 未抓 JD 能判什么、不能判什么

    **能判的那一半是合规的**：薪资上沿低于底线、标题明显是另一条职能线、
    地点跨城 —— 这些光看卡片就成立，`prescreen` 存在的理由就是它们。
    全库实测（2026-08-26）：477 个没读正文的判定里 **456 个是
    跳过 / 不建议 / 硬门 FAIL**，一个都不用动。

    **不能判的是往上抬。** 「可以考虑」的定义是「先问清楚关键信息再决定投不投」，
    而没读 JD 就连「关键信息是什么」都还不知道 —— 那个分只能来自标题和卡片字段，
    硬性条件一条没核过。它会把这个岗排进用户会去翻的那份名单里。

    实测（2026-08-26）：**21 个**，全部产于 2026-08-13 那一天、全部来自
    `liepin-search`、来源都写着「粗筛（未抓 JD）」。用户当天问的是
    「为什么还有 20 个没读 jd，都是必须读的」—— 他说得对，而框架里
    此前没有任何一处拦着这件事。

    ## 修法：退回待评，不是补一个分

    没有依据的档位不该原地改成另一个档位（那只是换个数字继续猜）。
    正确动作是把它们放回队列，等 JD 抓回来重新走一遍评估。
    """
    import jd_store as _st
    user = _cli.pick_user("", root=ROOT)
    # 档序只有一份正本（`_cli.VERDICTS`），**切片即子集** —— 抄一份出来，
    # 哪天档位改了这里就是静默失效。
    BANDS = _cli.VERDICTS[:3]
    bad, has_jd = [], 0
    for e in seen.values():
        if not isinstance(e, dict) or e.get("status") != "ranked":
            continue
        src = (e.get("rank_breakdown") or {}).get("来源") or ""
        if "读过 JD" in src or "读了 JD" in src or src.startswith("深评"):
            continue
        if not any(b in (e.get("rank_verdict") or "") for b in BANDS):
            continue
        bad.append(e)
        rec = _st.load(user, e.get("url") or "", e.get("title") or "")
        if ((rec or {}).get("description") or "").strip():
            has_jd += 1
    if not bad:
        return []
    days = collections.Counter(str(e.get("rank_date") or "?")[:10] for e in bad)
    when = "、".join(f"{d}（{n} 个）" for d, n in sorted(days.items()))
    tail = (f"其中 {has_jd} 个的 JD 其实已经在详情库里了，只差重评；"
            f"另外 {len(bad) - has_jd} 个要先抓正文。" if has_jd else "")
    return [("warn", "没读 JD 就给了可投档位",
             f"{len(bad)} 个岗没读过 JD 正文，判词却是「可以考虑」及以上——"
             f"那个分只能来自标题和卡片字段，硬性条件一条没核过，而它们会出现在"
             f"用户会去翻的那份名单里。产于 {when}。{tail}"
             f"没有依据的档位不该原地改成另一个档位，正确动作是退回待评、"
             f"等 JD 抓回来重走一遍：python tools/audit_pipeline.py "
             f"--requeue-no-jd --apply")]



def check_material_ready_without_a_stored_jd(seen, details) -> list:
    """材料已经备好、随时能发，而这个岗的 JD 正文库里一份都没有。

    ## 为什么这个交集要单独盯

    已经有两条在管 JD：`check_no_jd_but_sellable` 盯「来源明说没读 JD 却给了
    可投档位」，`check_jd_read_but_not_stored` 盯「来源自称读过、库里查不到」。
    **两条都不管这个交集** —— 前者把「自称读过」的排除在外，后者不看有没有材料。

    而这一批是**风险最高的那一档**：材料已经躺在那儿，而支撑这个判定的 JD 正文
    **没有任何人能再看一眼**。判错了没人拦，岗位下线之后连复核的机会都没有。

    ⚠️ **别把它说成「用户随时可能发出去」。** 那是这一段原来的写法，
    2026-08-30 现算一遍才发现说反了：26 个里 **23 个已经发出去了**。
    这条检查的判据是「可投 + 有材料」，**它不排已投的** —— 我原以为它排。
    「可能会发生」读起来是个可以往后放的风险，「已经发生了 23 次」是个
    已经付掉的代价；而**还能动的只有那 3 个**，收尾该指的是那 3 个。

    实测活动用户 2026-08-30：**37 个**。抽查最高分那个（80 分「强匹配」，
    全库最高）——JD 的硬性要求写着「具备真实的公司级 AI 变革主导经验」
    「筹建并领导公司 AI 核心团队」，而他是独立开发者、没带过团队。
    那个 80 分是在看不见这段话的情况下给的。

    ## 为什么不自动降档

    没有 JD 就没有依据，**换个数字仍然是猜**（同 `check_no_jd_but_sellable`
    那句「没有依据的档位不该原地改成另一个档位」）。正确动作是先把正文补回来。
    """
    import jd_store as _st
    import export_web_data as _ex
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    import build_dashboard as _bd
    mat = {_cli.norm_url(a["url"]) for a in _bd.find_applications(apps)
           if a.get("url") and a.get("dir")}
    bad = []
    for e in seen.values():
        if not isinstance(e, dict) or not e.get("url"):
            continue
        if _cli.norm_url(e["url"]) not in mat:
            continue
        if not _ex.is_strong(_cli.strip_triage(e.get("rank_verdict"))):
            continue
        rec = _st.load(user, e["url"], e.get("title") or "") or {}
        if (rec.get("description") or "").strip():
            continue
        bad.append((e.get("rank_score") or 0, (e.get("title") or "?")[:20], e["url"]))
    if not bad:
        return []
    bad.sort(key=lambda r: -r[0])

    def _portal(u: str) -> str:
        return ("猎聘" if "liepin" in u else "BOSS" if "zhipin" in u else
                "智联" if "zhaopin" in u else "前程无忧" if "51job" in u else "?")
    # **这一条进收尾那一档**（`--actionable`）。它盯的是全流程最险的交集：
    # 材料就绪、随时能发，而依据不在库里。
    #
    # **原来这里写的是「用户随时可能复制开场白发出去」。** 那是未来时，
    # 而 2026-08-30 现算一遍：26 个里 **23 个已经发出去了** —— 大半是过去时。
    # 我原以为这条的判据（「可投 + 有材料」）意味着命中的都还没投，
    # 算了一次才知道不是：它不排已投的。
    #
    # 这个差别不是措辞。「可能会发生」读起来是个可以往后放的风险，
    # 「已经发生了 23 次」是个已经付掉的代价 —— 后者才说得清这条为什么要盯。
    # 而**还能动的只有那 3 个**，那 3 个才是收尾该指的。
    _live, _ = _cli.live_tail(
        user, seen, [(u, t) for _s, t, u in bad], verb="补")
    _n_gone = len(bad) - len(_live)
    # **例子和补法都对着还能动的那批说。** 上一版拿 26 个的规模写整条消息 ——
    # 举的例子里有已经发出去的，按渠道那一格数的也是 26 个的分布，而
    # 「先把正文补回来」那两条路径按两家平台都列了一遍。
    # 同一个毛病 2026-08-30 在「深评缺小节」那条上刚收过一次：
    # **消息的规模要跟着「他现在动得了什么」走，不是跟着总数走。**
    _show = _live or [(u, t) for _s, t, u in bad]
    rows = "、".join(t for _u, t in _show[:3])
    portals = collections.Counter(_portal(u) for u, _t in _show)
    # 这句话直接上终端 —— 不带 markdown（`AGENTS.md`「给用户看的措辞」）。
    _still = ((f"其中 {_n_gone} 个已经发出去了（依据当时就不在库里，"
               f"补正文也复原不了当时那个判断）；"
               if _n_gone else "")
              + (f"还有 {len(_live)} 个没投、现在补得上："
                 if _live else "一个都补不回来了。"))
    return [("warn", "可投的材料备好了，而它依据的 JD 库里没有",
             f"{len(bad)} 个岗判到了可投档、材料也备好了，"
             f"而支撑这个判定的 JD 正文库里一份都没有 —— "
             f"没有任何人能再看一眼依据。{_still}"
             f"{rows}（{'、'.join(f'{k} {n}' for k, n in portals.most_common())}）。"
             f"不要自动降档 —— 没有 JD 就没有依据，换个数字仍然是猜。"
             # 补法只列**这批真用得上**的那条路：猎聘走 CLI，其余三家只能开页面。
             # 两条都列的话，读的人要先判断自己属于哪一边 ——
             # 而那个判断这里算得出来。
             + ("先把正文补回来：python tools/fetch_details.py --recheck --apply"
                "（CLI 停着时先 --clear 或改走浏览器）。"
                if set(portals) == {"猎聘"} else
                "先把正文补回来：python tools/fetch_details.py --browser-list "
                "拿名单，逐个开页面读完当场 "
                "python tools/jd_store.py --save <链接> --apply"
                + ("；猎聘那几个也可以走 python tools/fetch_details.py "
                   "--recheck --apply。" if "猎聘" in portals else "。")))]



#: 「JD 未要求 / 没提 / 没写…」这类**否定断言**。
#: 肯定句（「JD 写着 X」）错了还能被读者当场看出来；否定句错了看不出来 ——
#: 它长得和「查过了，确实没有」一模一样。
_NEGATIVE_CLAIM = re.compile(r"JD\s*(?:未|没有?|不)\s*(?:要求|提|写|设|列|涉及|限)")


def check_a_negative_claim_needs_the_jd(seen, details) -> list:
    """说「JD 没要求 X」，那就得先有那份 JD。

    ## 这条盯的是哪一类错

    2026-08-30 用浏览器补一个 77 分岗的 JD 时当场撞见：它的硬性条件表里写着

        候选人明确排除 | PASS | 国际化产品但书面英语可用；**JD 未要求口语工作语言**

    而 JD 正文补进来之后，任职要求第 9 条原文是「英文能力良好，能**支持海外客户
    沟通**、全球市场调研和跨区域协作」，平台语言栏还写着「英语、普通话」。
    **那句断言是在没有 JD 的情况下写的** —— 而它恰好放行了一道本该亮黄灯的门。

    ## 为什么否定断言特别危险

    肯定句写错了，读者对着 JD 一眼能看出来；**否定句写错了看不出来** ——
    「JD 未要求学历」和「我没查过学历」在纸面上长得一模一样，
    而前者会让七道门里的一道直接 PASS。这是本仓库反复记的那一类：
    **「没查」和「查过没有」是两件事**（同 `_annual_floor`、`_candidate_years`
    那几处的注释）。

    实测活动用户 2026-08-30：**84 份深评里 267 条**这样的断言，
    而那些岗的 JD 正文详情库里一份都没有。

    ## 修法不是删掉那句话

    删了只会让门变成「没判」。正确动作是**先把 JD 补回来**，再看那句话对不对 ——
    补回来之后多半是对的（另外 197 份有 JD 的评估里 583 条同类断言都有据可查），
    但没有 JD 时它是**构造上不可证伪**的。
    """
    import jd_store as _st
    import build_dashboard as _bd
    user = _cli.pick_user("", root=ROOT)
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    byurl = {_cli.norm_url(e.get("url") or ""): e
             for e in seen.values() if isinstance(e, dict) and e.get("url")}
    bad, ok_files, ok_claims = [], 0, 0
    for a in _bd.find_applications(apps):
        f = apps / a["dir"] / "evaluation.md"
        if not (a.get("url") and f.is_file()):
            continue
        hits = _NEGATIVE_CLAIM.findall(f.read_text(encoding="utf-8", errors="replace"))
        if not hits:
            continue
        e = byurl.get(_cli.norm_url(a["url"]))
        if e is None:
            continue
        rec = _st.load(user, e.get("url") or "", e.get("title") or "") or {}
        if (rec.get("description") or "").strip():
            ok_files += 1
            ok_claims += len(hits)
            continue
        bad.append((len(hits), a["dir"], a["url"]))
    if not bad:
        return []
    bad.sort(key=lambda r: -r[0])
    rows = "、".join(f"{d[:18]}（{n} 处）" for n, d, _u in bad[:3])
    return [("warn", "说「JD 没要求 X」，而那份 JD 库里没有",
             f"{len(bad)} 份深评里 {sum(n for n, _d, _u in bad)} 条这样的断言，"
             f"而那些岗的 JD 正文详情库里一份都没有。"
             f"肯定句写错了读者对着 JD 一眼能看出来；否定句写错了看不出来 —— "
             f"「JD 未要求学历」和「我没查过学历」在纸面上长得一模一样，"
             f"而前者会让七道门里的一道直接 PASS。"
             f"实测 2026-08-30 撞见一个：某 77 分岗写着「JD 未要求口语工作语言」，"
             f"而补回 JD 后要求第 9 条原文是「能支持海外客户沟通」。"
             f"例：{rows}。"
             f"另有 {ok_files} 份有 JD 撑着（{ok_claims} 条同类断言），那些不算。"
             f"修法不是删掉那句话（删了门就变成「没判」）—— "
             f"先把正文补回来：python tools/fetch_details.py --browser-list 拿名单，"
             f"读完当场 python tools/jd_store.py --save <链接> --apply。")]


def check_sellable_without_materials(seen, details) -> list:
    """判词是「强匹配 / 值得投」，没被任何一条排掉，却一份材料都没有。

    ## 为什么这条要有

    `/job-auto` 的出材料那一步是**无条件**跑的，选岗按 `job-apply.md` 第 0 步
    那七条。照理跑完就不该有漏网的。但那七条读的是**跑那一刻的快照** ——
    分数在这之后再变一次，就没有人回头看了。

    实测（2026-08-26）：一个岗当轮先评 58 分「可以考虑」，材料那一步照规矩
    跳过了它；随后把强度/发展落到粗筛四档（框架规定这两维只许取 30/50/70/85），
    综合分重算成 **60**，跨进「值得投」—— 而出材料那一步早已跑完。
    是本人问「为什么还有资料未准备的」才发现，**框架里此前没有任何一处拦着它**：
    自检的十几条检查没有一条问「可投的都有材料吗」。

    ## 判据必须从快照按那七条选，不许自己从 `seen_jobs.json` 再筛一遍

    这条检查的第一版就是自己筛的 —— 于是当场误报了一个 74 分的岗：
    它是**重复挂牌**（`dupOf`），材料在主贴那边。而 `dupOf` 是导出时算的
    （公司 + JD 正文哈希 + 手写的「同岗重复挂牌.md」），`seen_jobs.json` 里根本没有。

    `job-apply.md` 第 0 步早就写着「**从 `web/public/data.json` 挑，不要照着
    `seen_jobs.json` 自己再筛一遍**」，而我在写这条检查时犯的正是它拦的那个错。
    同一段还记着 2026-08-25 的一次实测代价：执行者拿公司名前缀去匹配材料目录名，
    两次报出「有 16 个 / 4 个可投的岗没材料」，真值是 **0**。

    ## 修法

    跑 `/job-apply`（不带参数就是「可以投」那一档全部出材料）。
    这条报的是**结果**不是原因：分数为什么变、要不要重评，看那个岗的
    `rank_breakdown.依据`。
    """
    import export_web_data as _ex
    snap = ROOT / "web" / "public" / "data.json"
    if not snap.is_file():
        return []
    try:
        d = json.loads(snap.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    user = _cli.pick_user("", root=ROOT)
    if (d.get("activeUser") or "") != user:
        return []          # 快照是别人的，判不了
    bad = [j for j in (d.get("jobs") or [])
           if not j.get("dupOf") and not j.get("evaluated")
           and not j.get("materials") and not j.get("applied")
           and not j.get("skipped") and not j.get("expired")
           and not _ex.is_out_verdict(j.get("verdict") or "")
           and _ex.is_strong(j.get("verdict") or "")]
    if not bad:
        return []
    rows = "、".join(f"{(j.get('company') or '')[:16]}（{j.get('score')} 分）"
                    for j in bad[:4])
    more = f"，另有 {len(bad) - 4} 个" if len(bad) > 4 else ""
    # **这一条进收尾那一档**（`--actionable`）：一轮 `/job-auto` 跑完还留着
    # 「可投却没材料」的岗，说明那一轮漏了活 —— 那正是收尾该当场看见的。
    #
    # 上面的选岗条件已经排掉了 applied / skipped / expired，看着像「命中的
    # 按定义都还没投」。**但那种推理这个仓库刚栽过一次**：
    # `check_material_ready_without_a_stored_jd` 的选岗条件也长这样，
    # 算了一遍才发现 26 个里 23 个已经发出去了（投递记录在 CSV 里，
    # 不在 `applied` 这个布尔上）。所以这里也算，不推。
    # **按状态分桶，不要二分。** 第一版用 `live_tail` 的「是不是还能发」二分，
    # 于是「对不上职位库」被算进了「已经投出去了」那一半 —— 那是句假话：
    # **「不知道」不等于「已经投了」**，而 `sendable_state` 自己的说明第一条
    # 写的就是「不知道就说不知道，别乐观地算进去」。
    # 构造用例里那个没有 `url` 的岗当场把它照出来了。
    _where = _cli.sendable_state(user, seen)
    _by = collections.Counter(_where(j.get("url") or "") for j in bad)
    _sent = _by["已经投出去了"] + _by["你标了不投"] + _by["岗位已下线"]
    _note = (f"其中 {_sent} 个其实已经出局了（投递记录里有，或你标了不投／已下线，"
             f"而快照那几个布尔没标上）。" if _sent else "")
    # 「还能发」和「对不上职位库」都还给命令：前者确定能动，后者是**不知道**，
    # 而对着不知道的收掉唯一的下一步，等于替他判了死。
    # 只有确定全部出局时才不给 —— 那时收尾那一档也会按 `_cli.NO_LIVE` 滤掉整行。
    # **记一笔。** 这条也自己拼尾巴（按状态分桶，不走 `live_tail`），
    # 所以要显式登记，否则收尾那句「去重后 N 个岗」少算它们。
    # 它们要的正是 `/job-apply` 出一份材料 —— 「一次补完」那条
    # 覆盖得了，所以不进「要改已有内容」那一批。
    _cli.note_live([j.get("url") or "" for j in bad
                    if _where(j.get("url") or "") == "还能发"])
    _worth = len(bad) - _sent
    _fix = "补它：/job-apply" if _worth else _cli.NO_LIVE + "补它没有意义。"
    return [("warn", "可投档却没材料",
             f"{len(bad)} 个岗的判词是「强匹配 / 值得投」，没被任何一条排掉，"
             f"却一份材料都没有：{rows}{more}。{_note}"
             f"出材料那一步读的是跑那一刻的快照——"
             f"分数在这之后再变一次就没人回头看了（2026-08-26 实测：一个岗先评 58 "
             f"「可以考虑」被跳过，随后落档重算成 60「值得投」，而那一步早跑完了）。"
             f"{_fix}")]


def check_jd_read_but_not_stored(seen, details) -> list:
    """判词自称「读过 JD 正文」，而详情库里查无这条正文 —— 读了没存。

    ## 为什么这条要有

    浏览器读来的 JD 只活在那一次访问里。不落库的代价不是「少个缓存」：
    **下一步（`/job-apply` 出材料）要用同一份正文，那时它得再开一次页面、
    再花一次额度** —— 而额度往往正好在评分那一轮用完了。

    规则本身 2026-08-26 已经写进 `job-rank.md` 补 JD 那一节（「读到的 JD 正文
    当场存进详情库」）。**但它只是一条文档规则，没有任何东西会红** ——
    同一天的 `/job-auto` 评了 13 个岗，落库 4 个（正好是要出材料的那 4 个），
    另外 9 个照旧只读不存。**规则只写在文档里，就等于只在有人想起来的时候生效。**

    全库实测（2026-08-26）：**191 个**岗的判词来源写着读过正文，而库里查不到，
    按渠道是猎聘 113、BOSS 48、智联 14、前程 10。存量不必逐个补回来
    （那些页面多半已经变了），这条要防的是**新增**：跑完一轮评分再看这个数，
    它涨了就说明这一轮又只读不存。

    ⚠️ 只看**自称读过**的那批。判词写着「粗筛（未抓 JD）」「标题即判据」的
    本来就没读，不在这条的范围里 —— 把它们算进来会让这个数永远下不去，
    而一个永远红的自检会被当噪音略过（`test_the_backlog_does_not_hide_the_trend`）。
    """
    import jd_store as _st
    user = _cli.pick_user("", root=ROOT)
    claim = []
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        src = (e.get("rank_breakdown") or {}).get("来源") or ""
        if not ("读过 JD" in src or "读了 JD" in src or src.startswith("深评")):
            continue
        rec = _st.load(user, e.get("url") or "", e.get("title") or "")
        if ((rec or {}).get("description") or "").strip():
            continue
        claim.append(e)
    if not claim:
        return []
    # **第三份手写的水位线，2026-08-31 一并收进 `watermark_note`。**
    #
    # 顺手修掉一个潜伏的排序坑：这里原来把缺日期的记成 `"?"` 再
    # `sorted(...)[-1]`，而 `?`（0x3F）排在数字之后 —— 只要有一条没写
    # `rank_date`，「最近一批」就会印成 `?`。助手把空日期直接丢掉。
    by_portal = collections.Counter(e.get("portal") or "?" for e in claim)
    tail = "、".join(f"{k} {v}" for k, v in by_portal.most_common(4))
    return [("warn", "读了 JD 没落库",
             f"{len(claim)} 个岗的判词写着读过 JD 正文，而详情库里查不到那条正文"
             f"（{tail}）。浏览器读来的正文只活在那一次访问里，不落库的话，"
             f"出材料时要再开一次页面、再花一次额度。"
             + watermark_note([str(e.get("rank_date") or "")[:10]
                               for e in claim])
             + 
             f"落库：读一个存一个，python tools/jd_store.py --save <职位链接> --apply（正文从标准输入进）；抓取器落了一整个目录的走 --import-from <目录> --apply")]


def check_a_portal_never_yields_a_jd(seen, details) -> list:
    """某个渠道抓了一批岗，而 JD 几乎取不到（`_JD_RATE_FLOOR` 以下）。

    ## 为什么这条要单独存在

    缺 JD 本身有人管：`fetch_details.missing_by_portal()` 会按渠道报「还缺多少」。
    但那句话答的是**还差几个**，答不了**这条路通不通** —— 一个渠道缺 900 个和
    缺 900 个且一个都没成功过，在那张表上长得一模一样。

    实测活动用户 2026-08-25（就是这条检查加进来的当天）：

        猎聘        1220 / 1901   64%
        BOSS          10 /  125    8%
        智联           5 /   72    7%
        **前程无忧      1 /  164    0.6%**

    前程无忧那一格不是「抓得慢」，是**存错了页**：抓取器把公司页
    （`jobs.51job.com/all/co<xxx>.html`）当成了职位页存进库，
    于是每个岗的链接点开都是公司简介。判据不用推理 —— 一个链接底下
    挂着三个毫不相干的岗（安卓研发工程师 / 运营实习生 / 后端开发实习生），
    真的职位页不可能是三个职位。

    根因是 `cdp-portals.md` 里**两条相反的规则**：一处写「别把 `a.comp` 当详情链接，
    它指向 `/all/co*.html` 公司页」，另一处写「详情链接必须用
    `a[href*="jobs.51job.com/all/"]` 限定」—— 后者把 `/all/co` 一起收了。
    执行者只能挑一条，他挑了错的那条（两条都已在 2026-08-25 对齐）。

    ## 撞链接是证据，不是判据

    判据只有一条：**这个渠道的 JD 抓取率**。撞链接只在报告里当佐证列出来 ——
    有的渠道天然会有少量撞车（猎聘 1901 个岗里有 2 个共用一个链接，那是重复挂牌），
    拿它当判据会误报。

    ## 判「留意」不判「要修」

    改法是改抓取规则再重抓一轮，没有 `--apply`。

    ⚠️ **这条消息第一版写了 markdown 粗体**（`**这不是抓得慢……**`），
    当场被 `test_display_wording` 抓了 —— 终端不解析 markdown，用户看到的是
    字面的星号。`AGENTS.md`「给用户看的措辞」末尾那条管的就是这个。
    """
    if not _USER:
        return []
    import collections
    try:
        import jd_store as _st
    except ImportError:
        return []
    by = collections.defaultdict(list)
    # **按「哪家网站」分组，不按 `portal` 字段。** 同一家会有好几个通道标记
    # （`51job` / `51job-cdp` / `51job-browser`），而存错页这件事是**整家**的毛病。
    # 按通道拆开的代价实测过：那个挂着 3 个岗的公司页，两个岗标 `51job`、
    # 一个标 `51job-browser`，拆开之后每边最多只撞到 2，判据当场失灵。
    for e in seen.values():
        if isinstance(e, dict) and e.get("url"):
            by[_site(e)].append(e)
    bad = []
    for portal, rows in sorted(by.items(), key=lambda x: -len(x[1])):
        if len(rows) < _JD_RATE_MIN_JOBS:
            continue
        got = sum(1 for e in rows
                  if _st.has_body(_st.load(_USER[0], e.get("url") or "",
                                           e.get("title") or "")))
        if got > len(rows) * _JD_RATE_FLOOR:
            continue
        # **低抓取率本身不是判据。** BOSS / 智联 / 前程的 JD 按设计只能在抓取当次的
        # 浏览器访问里取（`cdp-portals.md` 第 6 条），回头补不了 —— 它们的抓取率天然低，
        # 报它们等于报「你按设计做了」。误报一次，这条就会被整条忽略。
        #
        # 真正区分「存错了页」的是**撞链接**：见 `_SAME_URL_TOO_MANY`。
        c = collections.Counter(e.get("url") for e in rows)
        worst, n = c.most_common(1)[0]
        if n < _SAME_URL_TOO_MANY:
            continue
        eg = [str(e.get("title") or "")[:14] for e in rows if e.get("url") == worst][:3]
        bad.append(f"{portal}：{len(rows)} 个岗里只有 {got} 个取到过 JD，"
                   f"而一个链接底下挂着 {n} 个岗（{'、'.join(eg)}）")
    if not bad:
        return []
    return [("warn", "有个渠道几乎取不到 JD",
             "、".join(bad) + "。这不是抓得慢，多半是存错了页——"
             "一个链接底下挂着几个毫不相干的岗时，那个链接就是列表页或公司页，"
             "不是职位页。缺 JD 的岗评不了深评，只能靠标题与卡片字段粗筛。"
             "先对一遍这家的详情链接规则（cdp-portals.md 里那一家的「详情链接」那几条），"
             "改完重抓一轮：/job-scrape")]


#: 「不触发」这一档的几种写法。渠道 4 只在五种场景下生成，其余场合**写明
#: 不触发才是对的**（`job-apply.md` 渠道 4 那一节要求记一句，而不是整节不写）。
_NOT_TRIGGERED = re.compile(r"^\s*(?:不触发|不适用|不生成|无|暂无|N/?A|—|-)\b")


def _has_a_letter(text: str) -> bool:
    """那一节里真有一封信，不只是一个标题。

    **有标题不等于有内容** —— 这个仓库为同一件事立过一次判据
    （`parse_ask_before` 滤掉「无 / 暂无 / 不适用」，
    `check_maybe_tier_has_questions` 的说明里写着那句话）。这一条当时没跟上。

    实测 2026-08-31：3 份「写了求职信」的稿子，正文全是
    「不触发（BOSS 平台直聊，非校招网申、非体制内）。」—— 也就是说
    这条检查从上线起报的 **3 份全是误报**，而它给的处置是
    「对这几个岗重跑 `/job-apply`」：让他花三次深评去修三份本来就对的稿子。
    """
    # **三个标题都要试。** 上面那条正则收 `求职信 / 正式求职信 / 自荐信`
    # 三种写法（`06` 渠道 4 与真实产出里都出现过），而按 `求职信` 取节
    # 只够得着前两个 —— 一份写「## 自荐信」的稿子会被判成「没有信」，
    # 从此这条检查对它永远沉默。守卫当场把这一支照出来了。
    for kw in ("求职信", "自荐信"):
        body = _strip_wordcount(_named_section(text, kw)).strip()
        if len(body) >= 40 and not _NOT_TRIGGERED.match(body):
            return True
    return False


def check_cover_letter_never_left_the_draft(seen, details) -> list:
    """求职信写在 `outreach.md` 的小节里，独立那份 `cover-letter.md` 没落盘。

    `/job-apply` 渠道 4 那一节写着两步：「草稿先并入 `outreach.md` 的
    『求职信（场景触发）』小节……**第 4 步定稿后再落一份纯文本到**
    `documents/applications/<公司>_<岗位>/cover-letter.md`——两处内容必须一致」。

    **这条检查上线时报的 3 份全是误报。** 实测 2026-08-31：那 3 份
    「写了求职信小节」的稿子，正文全是「不触发（BOSS 平台直聊，
    非校招网申、非体制内）。」—— 写明不触发正是渠道 4 要求的做法。
    判据只看了标题，没看正文；而它给的处置是「重跑 `/job-apply`」，
    等于让他花三次深评去修三份本来就对的稿子。

    真需要一封信、而它没落成单独文件的情形，到 2026-08-31 **一次都
    还没出现过** —— 这条现在守的是那一天。

    ## 为什么那份独立文件不是可有可无的

    求职信只在**五种场景**下才生成（渠道 4 的触发清单），而那五种几乎全是
    「表单要你上传或粘贴一份」：校招网申、体制内报名系统、外企的 cover letter
    字段。他要交的就是那一份纯文本 —— 埋在一份还夹着开场白、缺口清单和自检
    元数据的 `outreach.md` 里，等于要他自己去挑出来再贴一遍，
    而那正是「两处内容必须一致」想防的事。

    ## 有标题不等于有内容

    判据走 `_has_a_letter`：那一节的正文得真是一封信。这个仓库为同一
    件事立过一次判据（`parse_ask_before` 滤掉「无 / 暂无 / 不适用」），
    这一条当时没跟上 —— 于是它报的每一份都是误报。
    """
    if not _USER:
        return []
    apps = ROOT / "users" / _USER[0] / "documents" / "applications"
    if not apps.is_dir():
        return []
    hit = []
    for f in sorted(apps.glob("*/outreach.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^#{1,3}\s*(?:求职信|正式求职信|自荐信)", t, re.M):
            continue
        if not _has_a_letter(t):
            continue
        d = f.parent
        if any((d / f"cover-letter{ext}").is_file() for ext in (".md", ".pdf", ".typ")):
            continue
        hit.append(d.name.split("_")[0][:16])
    if not hit:
        return []
    return [("warn", "求职信只有草稿，没落成单独那份",
             f"{len(hit)} 份话术里写了求职信，而同目录下没有 `cover-letter.md`"
             f"（例：{'、'.join(hit[:3])}）。求职信只在网申/报名系统/外企表单"
             f"要你交一份时才生成 —— 他要上传的就是那份纯文本，"
             f"埋在还夹着开场白与自检信息的 outreach.md 里等于要他自己挑出来。"
             f"补它：对这几个岗重跑 /job-apply <职位链接>，"
             f"照渠道 4 那一节把定稿落到 cover-letter.md")]


#: 四维的权重（`04-job-evaluation.md`「权重」）。地点是 Pass/Fail，不计权重
#: —— 所以是四维不是五维。用户在 `candidate.md` 写了自定权重就按他的，
#: 但那时评估输出里必须写明那一行，这条检查读不到就退回默认并说自己按默认算的。
_DIM_WEIGHTS = _sc.DIM_WEIGHTS


def check_score_reconciles(seen, details) -> list:
    """总分和它自己的四维对不上，而差额没有落成一条 `调整`。

    ## 总分不是四维的函数，而多出来的那一项只有 6% 记成了字段

    资料里的裁定可以在四维之外直接改综合分。本活动用户 `candidate.md` 的专业清单
    那条就写着「综合分 −5（**记为「专业减分」**）」—— **约定本来就有**。

    实测（2026-08-26）：四维齐全的 661 个岗里，总分对不上加权和的 129 个。
    记成字段的 **8** 个，只写在散文依据里的 67 个，一个字没提的 54 个
    （后者 46 个正好落在 −5/−4.x 这个签名上，就是同一条专业减分）。

    没照做不是执行者马虎：约定写在**用户资料**里，而执行者照抄的是
    `job-rank.md` 那份 `rank_breakdown` schema —— 那里原来没有这个字段。
    （2026-08-26 补上了 `调整`。同一个形状本会话已经撞过一次：
    `--annual-floor` 的取值规则在一处、可复制的例子在另一处，两处不是一个数。）

    ## 代价不是「不好看」

    **没有任何工具能查出哪些岗带了减分。** 这条裁定 2026-08-14 改过一次
    （上午按硬门、同日本人放宽为减分），当时全库翻案 11 个。下次再改还是只能
    grep 散文 —— 而散文写法实测至少三种：「专业减分 −5」「综合分已减 5」
    「专业清单不含 X，减 5」。

    ## 算得对才报

    04 允许的算法都试一遍，任何一种对上就不报：

    - 四维加权和
    - **薪资维「信息缺失」时把它的权重按比例分摊到其余三维**（04 那一节的括注）
    - 逐项四舍五入后再加（手算常见做法）
    - 以上任一 + `调整` 里各项之和

    容差 0.5 分：分数是整数，加权和常带小数。

    ## 盯的是趋势，不是存量

    存量 121 个不逐个补（那要重评）。**报总数的同时报最近一批** —— 一条永远红着
    的自检会被当噪音略过（同 `test_the_backlog_does_not_hide_the_trend`）。
    """
    def _sums(dims):
        yield sum(dims[k] * w for k, w in _DIM_WEIGHTS.items())
        rest = {k: v for k, v in dims.items() if k != "薪资与职级"}
        tot = sum(_DIM_WEIGHTS[k] for k in rest)
        if tot:
            yield sum(rest[k] * _DIM_WEIGHTS[k] for k in rest) / tot
        yield sum(round(dims[k] * w) for k, w in _DIM_WEIGHTS.items())

    bad, recent = [], []
    latest = ""
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        b = e.get("rank_breakdown") or {}
        score = e.get("rank_score")
        dims = {k: b.get(k) for k in _DIM_WEIGHTS}
        if not isinstance(score, (int, float)):
            continue
        if any(not isinstance(v, (int, float)) for v in dims.values()):
            continue
        extra = sum(_sc.adjust_of(b).values())
        if any(abs(float(score) - (w + extra)) <= 0.5 for w in _sums(dims)):
            continue
        day = str(e.get("rank_date") or "")
        bad.append((str(e.get("title") or e.get("company") or "")[:20],
                    score, round(float(score) - next(_sums(dims)), 1), day))
        latest = max(latest, day)
    if not bad:
        return []
    rows = "、".join(f"{t}（写 {sc} 分，四维算 {round(sc - d, 1)}）"
                    for t, sc, d, _ in bad[:3])
    tail = watermark_note([r[3] for r in bad])
    return [("warn", "总分和它自己的评分明细对不上",
             f"{len(bad)} 个岗的综合分不等于四维加权和，差额也没落成一条 `调整`："
             f"{rows}。资料里的裁定可以在四维之外直接改综合分（例：专业清单不符"
             f"「综合分 −5，记为专业减分」），那是允许的 —— 但只写在依据的散文里，"
             f"就没有任何工具查得出哪些岗带了减分。那条裁定改过一次就翻案了 11 个岗。"
             f"（2026-08-29：这条自检自己也栽在同一个坑里 —— 文案说「记为专业减分」，"
             f"它读的却是 `调整`，于是全库 12 个规规矩矩写了 `专业减分` 的岗被算成"
             f"「差额没落成字段」。现在两边都走 `scoring.adjust_of`。）"
             f"{tail}"
             f"写法见 job-rank.md 的 rank_breakdown schema（`调整` 那一条）；"
             f"要重算某个岗：/job-apply <职位链接>")]


#: 判词的分数档（`04-job-evaluation.md`）。从高到低，取第一个够得着的。
_VERDICT_BANDS = _sc.VERDICT_BANDS
#: 判词天花板：技能与经验这一维压得住判词，压不动分数。
#: 边界 80/60/40 是从**框架自己的语义**推的，不是从某个人的分数分布拟合的
#: —— 04 那一节把第二版的 70/50/30 判成过拟合并记下了理由。
_VERDICT_CEILINGS = _sc.VERDICT_CEILINGS
_VERDICT_ORDER = _sc.VERDICT_ORDER


def _band_of(score: float) -> str:
    return _sc.band_of(score)


def _ceiling_of(skill: float) -> str:
    return _sc.ceiling_of(skill)


def check_verdict_matches_its_score(seen, details) -> list:
    """判词比「分数档」和「判词天花板」取小的那个还高 —— 超卖。

    ## 这是框架的核心映射，而此前没有任何一处在验

    `04-job-evaluation.md` 定了两道，判词取两者**较低**的那个：

    - **分数档**：75+ 强匹配 · 60-74 值得投 · 45-59 可以考虑 · 30-44 不建议 · <30 跳过
    - **判词天花板**（按技能与经验这一维）：≥80 不封 · 60-79 封到「值得投」·
      40-59 封到「可以考虑」· <40 封到「不建议」

    天花板那条是补「传导」用的：总分里薪资占 25%，钱给够就能把技能 28 的岗
    抬到 60 分。04 举了三个实测例子，其中「技能 28 · 总分 60 · 值得投」那个
    的原话是 **「值得投三个字会让人真的去投、去定制材料、去准备面试」**。

    两个数都是执行者手写进 `rank_breakdown` 的，而自检的四十多条检查
    **没有一条在算这个映射**。

    ## 实测（2026-08-26）

    全库 664 个「分数 + 判词 + 技能与经验」齐全的岗，超卖的**只有 1 个**：
    59 分 · 技能 65 → 写着「值得投」。根因不是判错，是**半截的订正** ——
    那份评估的注脚记着「2026-08-20 校准：技能与经验 69 → 65」，
    技能一改总分就从 60 落到 59，**而结论那一行没跟着动**。
    同一个文件里当时并存着三代状态：得分 59（08-20）、结论「值得投」（08-11）、
    页脚「判词为「可以考虑」」（更早）。

    所以这条检查真正防的是**改了一处忘了另一处**，不是「打分打得准不准」。

    ## 只报超卖，不报保守

    判词**低于**上限是允许的：硬门 FLAG、信息不足、用户偏好都可能再压一档，
    而 04 没有规定「必须顶格」。实测活动用户 2026-08-26：低于上限的有 11 个 —— 一起报，
    这条就会长期红着，然后被当噪音略过（同 `test_the_backlog_does_not_hide_the_trend`）。

    判「留意」：改法是人去核那个岗（判词错了还是某一维错了），没有机械修法。
    """
    bad = []
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        score, skill = e.get("rank_score"), (e.get("rank_breakdown") or {}).get("技能与经验")
        core = _cli.strip_triage(e.get("rank_verdict"))
        if score is None or skill is None or core not in _VERDICT_ORDER:
            continue
        try:
            allowed = min(_band_of(float(score)), _ceiling_of(float(skill)),
                          key=_VERDICT_ORDER.index)
        except (TypeError, ValueError):
            continue
        if _VERDICT_ORDER.index(core) > _VERDICT_ORDER.index(allowed):
            bad.append((str(e.get("title") or e.get("company") or "")[:20],
                        score, skill, core, allowed))
    if not bad:
        return []
    rows = "、".join(f"{t}（{sc} 分 · 技能 {sk} → 最高「{al}」，写的是「{co}」）"
                    for t, sc, sk, co, al in bad[:3])
    more = f"，另有 {len(bad) - 3} 个" if len(bad) > 3 else ""
    return [("warn", "结论比分数和天花板允许的还高",
             f"{len(bad)} 个岗的判词超卖了：{rows}{more}。判词取「分数档」与"
             f"「技能与经验的天花板」里较低的那个（04 的两张表）。"
             f"最常见的成因不是判错，是改了一处忘了另一处 —— 某一维事后校准过，"
             f"分数跟着变了，而结论那一行留在原处。"
             f"核它：/job-apply <职位链接>（重跑一遍深评，两个数一起出）")]


def check_out_records_carry_their_own_date(seen, details) -> list:
    """出局的岗，日期没记在自己那条路的键上。

    出局有两条路，各有各的键：`skipped` → `skip_date`、`expired` → `expired_date`
    （判据在 `job-rank.md` 那两段 schema）。两个键不会串 —— 除非写的人写岔了。

    ## 写岔了不会有任何一处报错

    读的那几处都是 `e.get("skip_date")` 这种取法，取不到就是 None，一路静默。

    **但两种写岔的后果不一样，2026-08-26 逐条对过代码后分开写：**

    | 写成什么样 | 归档 | 面板 |
    |---|---|---|
    | 记在另一条路的键上 | **不受影响** | 那一行没有日期 |
    | 两条都没记 | 可能提前埋 | 那一行没有日期 |

    归档那一列是查 `archive._age_days` 得到的：它取的是
    `[叠加层 date, skip_date, expired_date, rank_date, first_seen]` 里**最晚**
    的一个。所以记在另一条键上照样被读到 —— 这一条原来写的是「退到抓到它的
    日子、于是提前埋掉」，**对着代码是错的**，而它举的例子恰好就是错键那一类。
    两条都没记时才会退，退到的也是 `max(rank_date, first_seen)`，通常是评分那天：
    评完隔很久才标出局的岗，这个数会把它算老，于是提前到期。

    面板那一列两类都中：`_decision_date` 对 `skipped` 只读 `skip_date`，
    于是搁置区那一行只剩「你排除的」，没有「（X-XX 标的）」。
    `Shortlist.tsx` 自己写着为什么这要紧 —— 「两周后回看会想不起当初为什么，
    那个『当初』是几号，正是判断这条结论还作不作数的依据」。

    实测活动用户 2026-08-26：库里 108 条带日期键的记录里 **3 条**有问题
    （1 条错键、2 条两条都没记）。而叠加层那 17 条（面板点出来的）**一条都没坏**
    —— 坏的全部来自手改 JSON 那条路，这就是**写入端没有约束**的证据。

    ## 判「留意」不判「要修」

    改法是人去改那条记录（或者干脆放回来重走一遍），没有 `--apply`。
    同族的 `check_tracker_columns_nobody_fills` 也是这一级。
    """
    if not _USER:
        return []
    out, missing = [], []
    for k, e in seen.items():
        if not isinstance(e, dict):
            continue
        st = str(e.get("status") or "")
        if st not in ("skipped", "expired"):
            continue
        mine, other = (("skip_date", "expired_date") if st == "skipped"
                       else ("expired_date", "skip_date"))
        who = (e.get("title") or e.get("company") or k)[:18]
        if not e.get(mine) and e.get(other):
            out.append(f"{who}（{st} 却记在 `{other}` 上）")
        elif not e.get(mine):
            missing.append(who)
    if not out and not missing:
        return []
    parts = []
    if out:
        parts.append(f"{len(out)} 个记在了另一条路的键上（例：{'、'.join(out[:3])}）")
    if missing:
        parts.append(f"{len(missing)} 个两条都没记（例：{'、'.join(missing[:3])}）")
    return [("warn", "出局记录：日期没记在自己那条路的键上",
             "、".join(parts) + "。出局有两条路、各有各的键（不投记 `skip_date`，"
             "已下线记 `expired_date`，见 job-rank.md 那两段 schema）。"
             "写岔了不会有任何一处报错，而两种写岔后果不一样："
             "记在另一条键上的，归档不受影响（它取所有日期里最晚的那个），"
             "但搁置区那一行不显示日期 —— 两周后回看，想不起当初为什么排除；"
             "两条都没记的还会被算老（退到评分那天），于是提前埋掉。"
             "改它：在总览页「不投的岗位」里把这个岗放回来，再重标一次")]


def check_foreign_degree_has_no_credential_row(seen, details) -> list:
    """资料里写着境外院校，「学历认证」那一行却没有 —— 而 offer 那一步要读它。

    三处本来是接上的：`job-setup.md` Section 2 写着「学校在境外（含港澳台）时，
    多问一句：中留服认证办了没有」，答案进 `## 教育背景` 的「学历认证」那一行，
    `job-offer.md` Step 4 读它。

    ## 断的是**先建档、后加问**的那一份

    这一问比资料本身晚。已经建过档的用户不会再被问一遍 —— 那一行于是永远不存在，
    Step 4 读到空，清单项对**唯一该触发的那个人**静默失效。
    实测活动用户 2026-08-25：层次写着境外院校，全文没有「学历认证」四个字。

    **认证有前置周期，按工作日算**（判据见 `job-setup.md` Section 2 那段引文）。
    等 HR 要材料时才发现没办，入职日期就得往后推 —— 而那时候人已经辞职了。
    这是这份资料里少数几个越早知道越值钱的事实，所以它值得单占一条。

    ## 只认「有没有这一行」，不认它填了什么

    `未办理` 也是答案，而且是最该早知道的那个答案。这里判的是**问没问过**。
    """
    if not _USER:
        return []
    p = ROOT / "users" / _USER[0] / "profile" / "candidate.md"
    if not p.is_file():
        return []
    t = p.read_text(encoding="utf-8", errors="replace")
    if "境外院校" not in t or "学历认证" in t:
        return []
    return [("warn", "资料：境外学历没写认证进度",
             "资料里的学校层次是境外院校（含港澳台），却没有「学历认证」那一行。"
             "国内单位普遍要教育部留学服务中心的《国外学历学位认证书》，"
             "入职、落户、考编都可能卡在它上面，而它按工作日算前置周期 —— "
             "等 HR 要材料时才办，入职日期就得往后推。"
             "补这一行：/job-setup --section 2")]


#: 面板把维度分进「对口的地方 / 要掂量的地方」两列的切点。
#: **正本在 `web/src/components/JobReadout.tsx` 的 `splitReasons`** ——
#: 那是个显示层的分组选择（≥70 算对口），不是 04 的档位。这里复刻一份，
#: 是为了认出「要掂量」那一列都装了什么；两边相等由
#: `test_the_dimension_note_says_why` 盯着。
#:
#: 70 这个数与粗筛四档 30/50/70/85 恰好对得上（70 = 判据偏好、50 = 没有信号），
#: 所以它对粗筛与深评两种分都讲得通 —— 改它之前先想一遍这层对应关系。
_PLUS_CUT = 70


#: 「依据」那一格只是把人指到别处去。实测 2026-08-27 全部写法：
#: 「见「优势」「缺口」两节」202 · 「见下方结论」25 · 「见下」6 ·
#: 「见下「优势」与「缺口」」2 · 「同上一条」2。
_POINTER_NOTE = re.compile(r"^(见|详见|参见|同上)")


def check_dimension_notes_explain_something(seen, details) -> list:
    """评分明细那一列写着「见某节」—— 它被渲染进面板上要解释东西的那两列。

    ## 面板拿这一格当解释用

    `JobReadout` 把每一维的 `note` 按分数分进「对口的地方」和「要掂量的地方」
    两列（判据 `splitReasons`，≥70 进前者）。那一整块的用途它自己写着：
    「为什么是这个结论（对口的地方 / 要掂量的地方，说人话）」。

    所以一句「见「优势」「缺口」两节」会**渲染在那两节旁边** —— 指路指到了
    读者已经在看的地方，等于什么都没说。

    ## 实测（2026-08-27）

    面板上 1020 条计权维度的说明里 **238 条（23%）只是指路**，「见「优势」「缺口」
    两节」一句就占 202 条。更要紧的是分布：**8 个岗**「要掂量的地方」那一列
    **整列都是指路**，而且全是 75-78 分的高分岗 —— 正是用户最会点开的那几个。

    ## 根因不在执行者

    `04-job-evaluation.md` 的输出模板里，那张表给薪资 / 强度 / 发展三维写的是
    **`...`**，只有技能与经验那格写明了要求（「必须写拆解」）。规格没说该填什么，
    填进去的就是占位。同一个形状本仓库反复栽过：`deadline` 没有落点、`调整`
    没有字段、`rank_breakdown` 不在落盘清单里 —— 值都产出来了，中间没有位置。
    模板 2026-08-27 已补齐三格要求，这一条盯存量。

    ## 与「强度那一维给了分却没说依据」不是同一条

    那一条读的是**库里** `rank_breakdown.依据` 那段散文，问它提没提这一维；
    这一条读的是 `evaluation.md` **评分明细表的说明列**。不同来源、不同字段，
    一个岗可以在那边合格、在这边只写了「见下」。
    """
    if not _USER:
        return []
    snap = ROOT / "web" / "public" / "data.json"
    if not snap.is_file():
        return []
    try:
        d = json.loads(snap.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if (d.get("activeUser") or "") != _cli.pick_user("", root=ROOT):
        return []
    n_note = n_ptr = 0
    whole = []
    # **按批次看的那一半。** 这条报的是全库累计（238/1140），而它自己那句
    # 「模板里那三格的要求 2026-08-27 已补齐」正是一次规则变更 ——
    # 累计数回答不了「那次补齐灵没灵」，只有「最近一批还犯不犯」能
    #（判据见 `batch_note` 上面那段）。
    #
    # 面板快照里没有评分日期（只有 `expiredDate` / `skipDate`），所以按链接
    # 连回职位库取 `rank_date`。**不给导出器加字段**：那会多一个只有这一处
    # 读的字段，而本文件另一条检查专管「有消费者没生产者」。
    _date_of = {_cli.norm_url(e.get("url") or ""): str(e.get("rank_date") or "")[:10]
                for e in seen.values()
                if isinstance(e, dict) and e.get("url")}
    _rows = []
    for j in d.get("jobs") or []:
        dims = [x for x in (j.get("dimensions") or [])
                if x.get("weighted") is not False]
        for x in dims:
            note = (x.get("note") or "").strip()
            if not note:
                continue
            n_note += 1
            if _POINTER_NOTE.search(note):
                n_ptr += 1
        minus = [x for x in dims
                 if x.get("score") is None or x.get("score") < _PLUS_CUT]
        _bad_here = bool(minus) and all(
            _POINTER_NOTE.search((x.get("note") or "").strip()) for x in minus)
        if _bad_here:
            whole.append((j.get("company") or j.get("title") or "", j.get("score")))
        # **一份深评算一票，票的内容是「这一份里有没有指路说明」。**
        #
        # ⚠️ 两处容易写反，第一版两处都写反了：
        # ① `batch_note` 的第二个元素是**「这份有没有问题」**（它内部 `sum(got)`
        #    数的就是它），第一版传了 `not _bad_here`；
        # ② 票不能按 `_bad_here`（整列都是指路）投 —— 那是这条检查里更严的
        #    那个子条件，全库只有 5 个岗命中，而标题报的是 238/1140 条**说明**。
        #    两个口径混着用，印出来的「最近一批 23 份里 23 份」和全库那 5 个
        #    自相矛盾，当场就看得出来。
        _d = _date_of.get(_cli.norm_url(j.get("url") or ""), "")
        if _d and dims:
            _has_ptr = any(_POINTER_NOTE.search((x.get("note") or "").strip())
                           for x in dims if (x.get("note") or "").strip())
            _rows.append((_d, _has_ptr))
    if not n_ptr:
        return []
    whole.sort(key=lambda r: -(r[1] or 0))
    rows = "、".join(f"{str(c)[:14]}（{sc} 分）" for c, sc in whole[:3])
    tail = (f"其中 {len(whole)} 个岗「要掂量的地方」整列都是指路："
            f"{rows}{'，另有 ' + str(len(whole) - 3) + ' 个' if len(whole) > 3 else ''}。"
            if whole else "")
    return [("warn", "评分明细：说明那一格只是指路",
             f"{n_ptr}/{n_note} 条维度说明只写了「见某节」。{tail}"
             f"面板把这一格渲染进「对口的地方 / 要掂量的地方」两列 —— "
             f"指到读者已经在看的地方，等于没说。"
             f"模板里那三格的要求 2026-08-27 已补齐（见 04 的「评分明细」那一节）；"
             + (f"{batch_note(_rows)}。" if batch_note(_rows) else "")
             + f"存量逐个跑 /job-apply <职位链接> 重出")]


def check_intensity_score_has_a_basis(seen, details) -> list:
    """强度那一维给了分，而依据里一个字没提它。

    `04-job-evaluation.md` 那一节把话说死了两句：

    > 判完在依据里写清「本次按什么信号判的」—— 口径要能被用户看见和纠正。
    >
    > 无论用哪套词，**JD 不提就标记未知** —— 不要因为没提就假设是轻松的。

    实测活动用户 2026-08-25：

        打过数值强度分的岗                   704
        依据里一个字没提这一维的              666（95%）
        └ 最近一批（2026-08-25，3 个）里      **0（0%）**

    **最后那一行才是要紧的**，而它在 2026-08-25 翻过来了。

    这一条 2026-08-24 上线时，最近一批（93 个）里 80 个（86%）没写依据 ——
    和全库一样差，说明规则在活着的时候就没跑过。当天下午那批深评开始逐份写
    「本次按什么信号判的」，**最近一批 3/3 全写了**。

    所以现在这 666 个是**真的存量**了，而 2026-08-24 那天它还不是。
    两句话的差别不在措辞，在能不能据此判断「规则灵不灵」：
    存量说明不了规则，最近一批才说得了 —— 这一条的整个结构就架在那一行上。

    ⚠️ **样本只有 3 个。** 3/3 不足以宣布规则站住了，只够说「不再是一样差」。
    下一批跑完再看那一行。

    ## 为什么这一维尤其不能靠猜

    它占 **20% 权重**，而 783 个分里 **83% 落在 50 和 70 两个值上** ——
    一个二值化的默认值，乘上 20% 就是最多 4 分的总分差，而这个仓库自己的尺子是
    「30 分 × 25% 权重 = 7.5 分，足以翻一整档」。

    更硬的一条：把这 783 个岗对回 `details/` 里的 JD 正文，**抓到正文的 604 个里
    有 579 个（96%）通篇没有任何可判的强度信号**，而它们全都拿到了一个数，
    **没有一个标「未知」**—— 其中 18 个给了 85 分（那是「这家很轻松」的正面主张）。
    ⚠️ 那次比对用的词是按**这个用户的强度形态**取的（04 三档里的「按项目/版本
    推进」：加班节奏、周末制度），换个形态的岗位那份词一个都不会出现 ——
    所以那 579 只是**这一次的**旁证，不是这条检查的判据。

    ## 判据只问一句：依据里提没提这一维

    **不去猜哪些词算信号。** 04 自己写着，写死一份词表就是把某一个行业的黑话
    当成通用尺子（「换成按班次运转的岗位，JD 里一个都不会出现」）。
    这里只查那一维的**名字**出没出现在依据里 —— 提了才有得纠正，
    这正是 04 那句「口径要能被用户看见和纠正」的最小可查形式。
    """
    miss_coarse, miss_deep, ok = [], [], 0
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        b = e.get("rank_breakdown") or {}
        if not isinstance(b, dict):
            continue
        k = next((k for k in b if any(x in str(k) for x in _INTENSITY_KEYS)), None)
        if not k or not isinstance(b[k], (int, float)):
            continue
        why = str(b.get("依据") or "")
        if any(x in why for x in _INTENSITY_KEYS) or "公司性质" in why:
            ok += 1
        elif e.get("evaluated"):
            miss_deep.append(e)
        else:
            miss_coarse.append(e)
    miss = miss_coarse + miss_deep
    if not miss:
        return []
    n = len(miss) + ok
    # 「集中在几个值上」**现算**，不写死一个数 —— 那个数随每一轮打分变，
    # 写死就等着它过期（这个仓库反复付过的那一类）。
    vals = collections.Counter()
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        b = e.get("rank_breakdown") or {}
        if isinstance(b, dict):
            k = next((k for k in b if any(x in str(k) for x in _INTENSITY_KEYS)), None)
            if k and isinstance(b[k], (int, float)):
                vals[b[k]] += 1
    top2 = sum(v for _x, v in vals.most_common(2))
    share = (f"而这些分 {top2 * 100 // max(1, sum(vals.values()))}% 只落在 "
             f"{'、'.join(str(x) for x, _v in vals.most_common(2))} 两个值上"
             if len(vals) > 2 else "")
    # 最近一批：`rank_date` 最大的那天。存量和「规则灵不灵」是两个问题，
    # 只有最近一批那个数答得了后者（同「深评正文里有框架词」那条的写法）。
    days = [str(e.get("rank_date"))[:10] for e in seen.values()
            if isinstance(e, dict) and e.get("rank_date")
            and isinstance((e.get("rank_breakdown") or {}).get("强度与公司性质"),
                           (int, float))]
    last = max(days) if days else ""
    last_tot = sum(1 for d in days if d == last)
    last_miss = sum(1 for e in miss if str(e.get("rank_date"))[:10] == last)
    tail = (f"最近一批（{last}，{last_tot} 个）里 {last_miss} 个 —— "
            f"这个数才说得了规则灵不灵，全库那个只会随产量涨。"
            if last and last_tot else "")
    fix = []
    if miss_coarse:
        fix.append(f"粗筛的 {len(miss_coarse)} 个跑 /job-rank --all")
    if miss_deep:
        fix.append(f"深评过的 {len(miss_deep)} 个逐个跑 /job-apply <职位链接>"
                   f"（--all 改不到深评）")
    return [("warn", "强度那一维给了分，却没说按什么判的",
             f"{len(miss)}/{n} 个打过强度分的岗，依据里一个字没提这一维。{tail}"
             f"04 那一节明写着「判完在依据里写清『本次按什么信号判的』—— "
             f"口径要能被用户看见和纠正」，还有一句「JD 不提就标记未知，"
             f"不要因为没提就假设是轻松的」。这一维占 20% 权重，"
             f"{share} —— 没有那句话，"
             f"用户既看不出它按什么判的，也就没法纠正它。修：" + "；".join(fix))]


def check_same_posting_got_different_verdicts(seen, details) -> list:
    """**同一份 JD** 挂在多处，几处拿到的判定不一样。

    ## 为什么这条要单独存在

    重复挂牌本身有人管：`export_web_data` 按归一化链接归并（`dupOf`），
    面板上只渲染一条。但归并只看**链接**——同一份 JD 换个雇主脱敏名、
    换个薪资写法挂到另一个链接上，那是两条不同的记录，归并看不见，
    于是它们可以拿到两个不同的判词，而没有任何一处会说话。

    实测 2026-09-01（这条检查加进来的当天），一轮里撞出两组：

    - 「软件产品规划经理」同一份 JD 挂了 **4 次**，拿到 **2 种门名**：
      三次「工作年限」、一次「候选人明确排除」。真正的门是行业背景 ——
      其中一次挂牌的平台字段还写着「经验不限」，门名却是「工作年限」。
    - 九方那个「智能硬件产品负责人」挂了 **5 次**，薪资从 60-80k 一路写到
      110-140k；五条职责逐字相同。

    ## 判据是 JD 正文，不是标题

    **第一版按「标题（+公司）」分组，误报得不能用**：一轮就报出 49 组，
    其中「AI 产品经理」一个标题下挂着 34 个**互不相干**的岗 —— 通用职位名
    在这个库里成百上千地重复，它压根不是「同一个岗」的判据。
    换成 JD 正文的指纹（去掉空白与平台安全提示尾巴后的前 600 字），
    这才是当初人工认出那两组时用的东西：「两份 JD 逐字相同」。

    没有 JD 正文的岗不参与 —— 没有正文就没有判据，猜一个只会把误报换个来源。

    ## 为什么算「要修」

    两条记录说的是同一个岗，而用户看到的是其中一条。哪一条被渲染取决于
    归并顺序，不取决于哪条判得对 —— 也就是说**他看到的结论是随机的**。
    """
    import collections as _c
    import hashlib as _h

    TAIL = "猎聘温馨提示"

    def _fp(body: str) -> str:
        b = re.sub(r"\s+", "", body or "")
        k = b.find(TAIL)
        if k > 0:
            b = b[:k]
        b = b[:600]
        return _h.md5(b.encode("utf-8")).hexdigest() if len(b) >= 120 else ""

    by_url = {}
    for u, d in (details or {}).items():
        f = _fp(d.get("description") or d.get("body") or "")
        if f:
            by_url[_cli.norm_url(u)] = f

    groups = _c.defaultdict(list)
    for k, e in seen.items():
        v = str(e.get("rank_verdict") or "")
        if not v or e.get("status") in ("new", "expired"):
            continue
        f = by_url.get(_cli.norm_url(e.get("url") or ""))
        if f:
            groups[f].append((e.get("title") or "", v))

    bad = []
    for f, rows in groups.items():
        if len(rows) < 2:
            continue
        vs = sorted({v for _, v in rows})
        if len(vs) > 1:
            bad.append((rows[0][0], len(rows), vs))
    if not bad:
        return []
    bad.sort(key=lambda x: -x[1])
    show = "；".join(f"「{t}」挂了 {n} 次，判成了 {' / '.join(v)}" for t, n, v in bad[:3])
    more = f"，另有 {len(bad) - 3} 组" if len(bad) > 3 else ""
    # **判「留意」不判「要修」。** 改法是逐个重跑深评（人工重判），
    # 与「判词超卖」「年限门挡掉他年限够的岗」同一档 —— 那两条也是存量、
    # 也需要人重看。「要修」留给必须当场改掉的。
    return [("warn", "同一份 JD 挂多处，判定不一致",
             f"{len(bad)} 组重复挂牌的判定对不上：{show}{more}。"
             f"归并只看链接，换个脱敏名换个薪资挂到另一个链接上就绕过了它 —— "
             f"而面板渲染哪一条取决于归并顺序，不取决于哪条判得对，"
             f"等于他看到的结论是随机的。"
             f"挑对的那条，其余对齐：/job-apply <职位链接>")]


def check_queue_left_on_a_live_channel(seen, details) -> list:
    """还有待评的岗，而它们的渠道并没有被封 —— 上一轮 auto 没跑完。

    ## 为什么这条要单独存在

    `job-auto.md` 的循环第 1 步是「队列里还有待评的 → 跑 /job-rank
    （**它自己会评到排空**）」，循环**没有任何一个出口是「队列非空」** ——
    停手条件表里唯一允许留下待评的，是「撞验证码、用户不响应 → 该渠道的岗
    保持待评」。也就是说：**队列非空 ⇒ 那些岗的渠道必须是停着的**，否则就是
    这一轮没跑完。

    而没有任何一处在验这件事。`doctor` 会说「还有 N 个没评」，但它不区分
    「评不动」和「没去评」；总账那条「队列还剩多少」同样只是照数报出来。

    实测 2026-09-01：同一天里两次停在非空队列上（先 62 个、后 66 个），
    两次渠道都已经解封，两次都反过来叫用户自己敲 `/job-rank` ——
    而那正是 auto 该替他做完的那一步。用户当场问「auto 不是该包含 rank 吗，
    为什么还提示 rank」。

    ## 判据是「渠道通不通」，不是「队列空不空」

    队列非空且渠道停着 → 正常，不报（那是停手条件表里写明的情况）。
    """
    import collections as _c
    import datetime as _dt
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import portal_budget as _pb
    except Exception:
        return []

    left = _c.Counter(e.get("portal") for e in seen.values()
                      if e.get("status") == "new")
    if not left:
        return []
    user = _cli.read_active_user()[0]
    if not user:
        return []
    try:
        data = _pb.load(user)
    except Exception:
        return []
    now = _dt.datetime.now()
    live = []
    for portal, n in left.items():
        if not portal:
            continue
        try:
            st = _pb.block_state(data, portal, now, lane=_pb.lane_of(portal))
        except Exception:
            continue
        if not st.get("blocked"):
            live.append((portal, n))
    if not live:
        return []
    live.sort(key=lambda x: -x[1])
    tot = sum(n for _, n in live)
    rows = "、".join(f"{p} {n} 个" for p, n in live)
    return [("error", "还有待评的岗，而它的渠道并没有停",
             f"{tot} 个岗还没评，而它们的渠道是通的（{rows}）。"
             f"`job-auto` 的循环里没有「队列非空」这个出口 —— "
             f"唯一允许留下待评的是撞了验证码、用户没响应的那条渠道。"
             f"渠道通着还剩着，说明这一轮没跑完。评完：/job-rank")]


def check_flag_fields_carry_a_sentence(seen, details) -> list:
    """FLAG 字段的值要是**一句人话**，不是裸 `true`。

    `job-rank.md`「FLAG 判完，结论落到哪个字段」那一节写得很明白：

    > 值写成一句人话，说清**凭什么标的、投前要问什么**。

    而实测（2026-09-02）：`学历待确认` 31 个里 **13 个**、`专业待确认` 48 个里
    **13 个**，值是裸 `True`。用户拿到的是一个「有疑问」的标记，
    **既没有理由，也没有该问的那句话** —— 而这一档的全部用途就是那句话。

    现有守卫（`test_structured_fields_feed_the_gates`）只查**有没有**这个键
    （`if bd_.get("学历待确认")`），布尔值一路绿灯。这是那一节自己的论点
    再走一步：规则写清了「产物放哪」，**没人查产物长什么样**。

    `学历已核` 那几个短串不算违规 —— 规则要的就是 `<正文原话>`，
    JD 里那句「本科及以上学历」本身就是答案。
    """
    keys = ("学历待确认", "专业待确认")
    bad = []
    for e in seen.values():
        bd = e.get("rank_breakdown") or {}
        for k in keys:
            v = bd.get(k)
            if v is None:
                continue
            if isinstance(v, bool) or (isinstance(v, str) and len(v.strip()) < 4):
                bad.append((k, e.get("title") or "", e.get("url") or ""))
    if not bad:
        return []
    per = collections.Counter(k for k, _, _ in bad)
    live = [u for _, _, u in bad if u][:3]
    return [("warn", "FLAG 字段只写了个 true，没写要问什么",
             f"{len(bad)} 处：" + "、".join(f"{k} {n}" for k, n in per.most_common())
             + "。`job-rank.md`「FLAG 判完，结论落到哪个字段」要求"
             "「值写成一句人话，说清凭什么标的、投前要问什么」——"
             "写成 `true` 的那些，用户看到一个疑问却不知道该问什么。"
             "重评这几个岗就会重写：/job-rank --all"
             + (f"（例：{live[0]}）" if live else ""))]


CHECKS = [
    ("字段：有消费者没生产者", lambda s, d: check_orphan_consumers(s, d)),
    ("去重：同一份 JD 挂多处，判定不一致", check_same_posting_got_different_verdicts),
    ("抓取：还有待评的岗，而渠道没停", check_queue_left_on_a_live_channel),
    ("字段：FLAG 只写了 true，没写要问什么", check_flag_fields_carry_a_sentence),
    ("字段：生产方与消费方名字不一致", lambda s, d: check_name_mismatch(s, d)),
    ("字段：文档声称 vs 实测", lambda s, d: check_doc_claims_vs_reality(s)),
    ("取值：薪数合理区间", lambda s, d: check_salary_months_sane(s)),
    ("取值：判词词表", lambda s, d: check_verdict_vocabulary(s)),
    ("取值：判词来源族", lambda s, d: check_source_families(s)),
    ("去重：http/https 孪生", lambda s, d: check_scheme_twins(s)),
    ("完整性：有分数没拆解", lambda s, d: check_scored_without_dims(s)),
    ("完整性：深评没写评估日期",
     lambda s, d: check_evaluations_are_dated(s, d)),
    ("依据：说的不是现在这个分",
     lambda s, d: check_basis_still_explains_the_number(s)),
    ("完整性：深评缺小节", check_evaluation_sections),
    ("评分明细：说明只是指路", check_dimension_notes_explain_something),
    ("完整性：「可以考虑」要写清问什么", check_maybe_tier_has_questions),
    ("话术与深评：正文里有框架词",
     check_documents_speak_chinese_to_the_user),
    ("话术：抬头没说清在跟谁说话",
     check_outreach_header_says_who_youre_talking_to),
    ("字段：招聘者头衔与渠道对不上",
     check_recruiter_title_contradicts_the_channel),
    ("话术：说了公司的事就要有出处", check_company_claims_have_a_source),
    ("话术：开场白有不该出现的写法", check_greeting_keeps_the_five_rules),
    ("话术：开场白的问题在好几个岗上是同一句",
     check_greeting_questions_are_about_this_job),
    ("话术：另外几个渠道的文风", check_other_channels_keep_the_style_rules),
    ("简历：正文的文风", check_resume_body_keeps_the_style_rules),
    ("硬门：七道每道都要判", check_every_gate_is_judged),
    ("硬门：FAIL 就不能判可投", check_gate_fail_blocks_the_verdict),
    ("薪资：面议不该打分", check_negotiable_salary_is_not_scored),
    ("薪资：没标薪数不该被埋", check_unknown_months_is_not_a_death_sentence),
    ("薪资：这一维只有四个取值", check_pay_dim_matches_its_own_number),
    ("评分：说扣了分却没有字段真的扣", check_the_deduction_was_actually_deducted),
    ("抓取：有渠道整条没跑", check_a_whole_channel_sat_out_the_round),
    ("抓取：CLI 停了没换道", check_the_blocked_lane_handed_over),
    ("抓取：抓完没刷词表产出", check_the_yield_table_kept_up),
    ("抓取：职位号位数不像同一族", check_job_ids_are_not_truncated),
    ("抓取：查重没连存档一起查", check_the_archive_was_consulted),
    ("面板：句子断在半截", check_panel_text_is_not_cut_off),
    ("硬门：年限判定 vs 平台字段", check_years_gate_vs_platform_field),
    ("硬门：判不了就别判死", check_gate_fail_without_evidence),
    ("硬门：排除理由要能在资料里找到出处", check_exclusions_trace_to_the_profile),
    # 检查名是 `--only` 的选择器（标识符），行标题才是印给用户的文案 ——
    # 这一条两处此前共用同一个串，2026-09-01 分开：标题改成人话，
    # 名字留在这一族里（另外 12 个同族的名字也带「硬门」）。
    ("硬门：门名没按七道正规名写", check_gate_is_one_of_the_seven),
    ("硬门：深评表里的门名没按七道正规名写",
     check_gate_table_names_are_one_of_the_seven),
    ("硬门：判了排除却没说是哪一条", check_an_exclusion_fail_must_name_the_rule),
    ("预筛：学历字段仍不配结案", check_edu_field_cannot_close),
    ("证据：判词自称读过就必须存下", check_claimed_reads_are_stored),
    ("归档：JD 快照自带正文", check_posting_snapshots_are_self_contained),
    ("简历：resume/ 底下多出来的没人读", check_extra_resumes_are_never_audited),
    ("投递记录：有人读、没人写的列", check_tracker_columns_nobody_fills),
    ("真伪信号：蓄水池那条算不算得出来", check_pool_signal_is_computable),
    ("硬门：哪一条排除最贵", check_which_exclusion_costs_the_most),
    ("话术：具名直招缺内推请托", check_referral_note_is_missing),
    ("打分：强度那一维没说按什么判的", check_intensity_score_has_a_basis),
    ("资料：境外学历没写认证进度", check_foreign_degree_has_no_credential_row),
    ("分数：总分和四维对不上", check_score_reconciles),
    ("判词：比分数和天花板允许的还高", check_verdict_matches_its_score),
    ("出局记录：日期记错了键", check_out_records_carry_their_own_date),
    ("求职信：只有草稿没落单独那份", check_cover_letter_never_left_the_draft),
    ("JD：没读就给了可投档位", check_no_jd_but_sellable),
    ("JD：可投的材料备好了，依据却不在库里",
     check_material_ready_without_a_stored_jd),
    ("JD：说「没要求 X」而 JD 不在库里",
     check_a_negative_claim_needs_the_jd),
    ("材料：可投档却没材料", check_sellable_without_materials),
    ("JD：读了没落库", check_jd_read_but_not_stored),
    ("渠道：JD 几乎取不到", check_a_portal_never_yields_a_jd),
    ("简历：第一条只是自我描述", check_the_lead_advantage_points_at_something),
]


#: 当前在审的用户。`check_years_gate_vs_platform_field` 要读他的
#: `candidate.md` 拿年限，而检查的签名只有 (seen, details)。
#: 用一个单元素列表而不是改十四个检查的签名——改签名的代价
#: 落在全部检查上，而要这个的只有一个。
_USER: list = []


def run(user: str, only: str = "", actionable: bool = False) -> list:
    """跑全部检查；`only` 给了就只跑名字里含它的那几条。

    ## 为什么要能单跑

    全量 50 多条是**收尾**用的；而有几条要在**每一批里**就验，因为它们盯的
    东西过了这一批就没了。最典型的是「判词自称读过 JD，库里却没有」——
    浏览器读来的正文只活在读它的那一刻，当批发现只要跑一次
    `jd_store.py --save`，全量跑完再发现就得重开页面。
    实测 2026-08-30：这一条积到了 145 个岗，而规则在三个工作流里都写着。
    **规则没缺，缺的是「什么时候查」。**

    ## `actionable`：只留「现在还补得上」的那几条

    `/job-auto` 收尾时跑的是这一档。全量 50 多条里，绝大多数报的是存量或结构
    问题 —— 收尾印出来会把真正还来得及的那几条淹掉（`check_greeting_…` 的
    docstring 里有完整的账：102 份踩线里 72 份已经投出去了，「等着发出去」
    对四分之三是错的）。

    **判据是行为，不是名单**：一条检查调了 `sendable_state`，就说明它分得清
    哪些还来得及补 —— 那正是收尾该说的。另立一张名单就是第二个住址，
    会和 `CHECKS` 分叉。

    **第二个信号 2026-08-31 补上：`_cli.note_round_scoped()`。**上面那条是个
    代理判据，有一整类发现它表达不了 —— **这一轮本身漏了活**，和「哪些材料
    还发得出去」不是一回事。`check_the_blocked_lane_handed_over` 就是这一类：
    猎聘 CLI 撞限流那天，闸门放行的浏览器那条 0 次查询，而那家占语料的大头。
    它进不了这一档，于是同一个错犯了两次、两次都靠人当场发现。
    新信号同样是**运行时喊一声**，不是名单。
    """
    _USER[:] = [user]
    seen, details = load(user)
    out = []
    terms = [t.strip() for t in only.split(",") if t.strip()]
    for name, fn in CHECKS:
        if terms and not any(t in name for t in terms):
            continue
        before = _SENDABLE_CALLS[0]
        before_round = _cli._ROUND_SCOPED_CALLS[0]
        rows = fn(seen, details)
        if actionable:
            if (_SENDABLE_CALLS[0] == before
                    and _cli._ROUND_SCOPED_CALLS[0] == before_round):
                continue                      # 这条检查分不清还能不能动
            # **再按行滤一遍。** 一条检查可能报两行，一行有活、一行没有 ——
            # 实测「猎头岗对着顾问说「贵司」」那 9 份全已投，印在收尾里
            # 就是一条读完什么也做不了的消息，而它挤在真有活的那几条中间。
            rows = [r for r in rows if _cli.NO_LIVE not in str(r[2])]
        out.extend(rows)
    return out


#: 凌晨几点之前，把昨天写的那一批也算进「这一批」。
#:
#: 一轮 `/job-auto` 会跨过午夜：23:55 写完、00:05 跑闸门，只认「今天」
#: 就是空集 —— 真空通过。6 小时够覆盖一轮的尾巴，又不至于把前一天整批
#: 存量拉进来（那正是这道闸门不该报的东西）。
_MIDNIGHT_GRACE_H = 6


def this_batch_days() -> set:
    """「这一批」覆盖哪几天。**两个消费方共用这一份。**

    今天算；跨午夜那一轮的尾巴也算 —— 一轮 `/job-auto` 会跨过午夜（23:55
    写完、00:05 跑闸门），只认「今天」就是空集，那一批真空通过。

    ⚠️ **2026-08-31 险些成了第二份。** `_sections_cli` 里本来就内联着同样
    三行，给收尾那一档加「这一批刚判的」时我在文件另一头又写了一遍 ——同一个
    宽限窗口两处各写一份，改一处忘一处的样子这个仓库见过太多次。
    """
    now = _dt.datetime.now()
    days = {now.date().isoformat()}
    if now.hour < _MIDNIGHT_GRACE_H:
        days.add((now.date() - _dt.timedelta(days=1)).isoformat())
    return days


def _in_this_batch(day: str) -> bool:
    """`day`（`YYYY-MM-DD`）算不算「这一批」。"""
    return bool(day) and str(day)[:10] in this_batch_days()


def _sections_cli(paths) -> int:
    """`--sections`：逐份查，缺任何一节退出码非零。

    **给路径就查那几份，不给就查今天写的那一批。** 后者是写完盘那一刻
    最省事的用法 —— 写手不必先把自己刚建的目录名抄一遍
    （抄名单正是这一节要替掉的那件事）。

    ⚠️ **「今天」按深评自己写的「评估日期」算，不按文件 mtime。**
    第一版写的是 `sorted(..., key=st_mtime)[:30]`，当场被
    `test_no_check_sorts_by_mtime` 拦下 —— **拦得对**：重新归档、批量改权限、
    同步工具都会把 mtime 推到今天，那时候「最近 30 份」就是随机 30 份。
    这个仓库为这一脚交过学费（那条检查的趋势读数就是这么读反的），
    答案早就写在 `_eval_date` 里，这里照用。
    """
    files = []
    for one in paths:
        q = Path(one)
        if q.is_dir():
            files.extend(sorted(q.glob("**/evaluation.md")))
        elif q.is_file():
            files.append(q)
        else:
            print(f"找不到：{one}")
            return 2
    if not paths:
        user = _cli.pick_user("", root=ROOT)
        apps = ROOT / "users" / user / "documents" / "applications"
        want = set(this_batch_days())
        # **一轮会跨过午夜。** 只认「今天」的话，23:55 写完那一批、00:05 跑这道
        # 闸门 —— 集合是空的，它**真空通过**，那一批的缺口直接变成存量。
        #
        # 这个仓库为同一形状付过学费：`portal_budget` 的间隔判据原来
        # 「00:00:05 跑一次，23:59 那个动作落在窗口外，`acts` 为空，
        # 整个间隔判据被跳过」。
        #
        # 所以凌晨那几个小时把昨天也算进来。**只放宽这一段**：
        # 拿「最近有产出的那一天」兜底会把三天前的存量整批报出来，
        # 而这道闸门的全部价值是「这一批」。
        # （宽限窗口在 `this_batch_days()` 里，不在这儿再写一遍。）
        # **没写日期的一律纳入。** 判不了它属于哪一批 —— 而「判不了」在这儿
        # 不能等于「不是这一批」：那样它就**永远**逃得过这道闸门。
        # 04 明写那一行「不是装饰，是所有按批次看趋势的分析唯一的依据」，
        # 并记着一次事故：3 份漏了 `- ` 前缀，当天新出的深评对每一个按日期的
        # 检查全部隐形。实测 2026-08-30 全库 1 份没有它，而那 1 份正好缺小节 ——
        # 也就是说它此前永远补不上。
        # **重跑写下的那一份也是「这一批」。** `/job-apply --stale` 会把
        # 一整批评估重写一遍，而它留的是 `重跑日期`，`评估日期` 原样不动
        # —— 只按后者挑的话，那一批整批逃过这道闸门，而它恰恰是同一个
        # 写手在同一次运行里写的（「一次跑里要么每份都写、要么每份都
        # 不写」正是这道闸门的由来）。
        #
        # **只放宽这道闸门，不动 `_eval_date`。** 批次趋势问的是
        # 「08-17 那次跑法怎么样」，把重跑件挪到今天会把那个问题答坏。
        def _mine(f) -> bool:
            t = f.read_text(encoding="utf-8", errors="replace")
            return (_eval_date(t) in want | {""}
                    or _rerun_date(t) in want)

        files = [f for f in sorted(apps.glob("*/evaluation.md"))
                 if _mine(f)]
        today = ("、".join(sorted(want))
                 + "（外加没写日期的，以及这几天重跑过的）")
        if not files:
            print(f"（{today}）还没写过深评 —— 没什么可查的。"
                  f"想查别的就把路径给我")
            return 0
        print(f"没给路径，查 {today} 写的 {len(files)} 份")
    # **动不了的岗不进退出码。** 判据不是这里新发明的 —— `--actionable` 那一档
    # 早就按 `NO_LIVE` 滤过一遍行了（`run()` 里那句「一行有活、一行没有」），
    # 而这道闸门从来没学会它。
    #
    # 代价是实测出来的（2026-09-01）：全库唯一一份没写「评估日期」的深评
    # 产于 2026-08-10，用的还是旧口径（五维打分 / 硬门检查），缺 结论、优势、
    # 建议 三节 —— 而它对应的岗**用户早就标了不投**。
    #
    # 没日期的一律纳入「这一批」（上面那段写了为什么），于是这一份**每一轮
    # 都被捞进来**，闸门永远非零。而 `job-auto.md` 对非零的要求是
    # 「当场补齐，补完重跑到零再往下走 —— 别刷快照、别开下一批」：
    # 这一份补不了（补个日期是假账，整份重跑是给一个不投的岗重开页面），
    # 于是那句话**永远兑现不了**。一道兑不了现的闸门，执行者只会学会绕过它 ——
    # 连同它本来拦得住的那几十份一起。
    #
    # 「判不了」不算动不了：`sendable_state` 那五格里「对不上职位库」要留在
    # 红的这一边（`live_tail` 为这一脚交过学费 —— 把它并进「已经出局」，
    # 数被压小了还看不见）。
    _where, _urls = (lambda _u: "对不上职位库"), {}
    if not paths:
        # **职位库读不出来时不能倒在这儿。** `load` 缺文件是直接 `SystemExit`
        # 的（它给的是 `/job-scrape` 那句引导，对这道闸门是答非所问）。
        # 读不出来就一律算「判不了」—— 那一格留在**红的那一边**，
        # 也就是宁可多拦，绝不因为读不到库而放过谁。
        try:
            _seen, _ = load(user)
            _where = _cli.sendable_state(user, _seen)
            _urls = dir_urls(user)
        except SystemExit:
            pass
    bad, moot = 0, []
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace")
        gone = missing_sections(t)
        if gone is None:
            continue
        # **这一档还多一节。** 「可以考虑」的定义就是「先问清楚再决定投不投」，
        # 没有那份清单，它和「值得投」在面板上没有区别 —— 而实测他正是这样
        # 把 26 个这一档的岗直接发了出去。判据走 `ask_before_missing`。
        if ask_before_missing(t):
            gone = list(gone) + ["投前必问"]
        if not gone:
            continue
        # **给了路径就照查。** 那是调用方点名要的这几份，不替他判该不该管。
        if not paths and _where(_urls.get(f.parent.name, "")) not in (
                "还能发", "对不上职位库"):
            moot.append(f.parent.name)
            continue
        bad += 1
        print(f"缺 {chr(12289).join(gone)}：{f.parent.name}")
    if moot:
        print(f"另有 {len(moot)} 份缺小节 —— {_cli.NO_LIVE}"
              f"补它没有意义，不计入这道闸门（{'、'.join(moot[:3])}）。")
    if not bad:
        left = len(files) - len(moot)
        print(f"{len(files)} 份小节都写全了" if not moot
              else (f"该管的 {left} 份都写全了" if left
                    else "这一批没有该管的缺口"))
        return 0
    # 这句直接上终端 —— 不带 markdown，且要说得出下一步该干什么。
    print(f"\n{bad}/{len(files)} 份缺小节。没东西可写的那一节写「同上」或「无」，"
          f"别整节删掉：标题在不在是唯一能把「没什么可说」和「这一步没做」"
          f"分开的东西。只有「建议」能写「同上」——「职位真伪信号」写「无」"
          f"的意思是「查过，确实没有」，事后补等于谎报查过一次，"
          f"那种只能整份重跑：/job-apply <职位链接>。"
          f"缺「投前必问」的更不能写「无」——写不出来就说明这个岗不属于"
          f"「可以考虑」这一档：信息够了升「值得投」，缺的是硬信息归「缺口」，"
          f"两种都要连结论一起改。")
    return 1


def rewrite_commands(links: list) -> list:
    """要改已有内容的那几个岗，各自该敲的命令（含超上限时那两行）。

    **单独成函数是为了测试能钉住它。** 内联在 `main` 里时，「超过上限」
    那一支只有喂进一份十几个岗的真数据才跑得到 —— 也就是实际上没人验过。
    `doctor.py` 里那条同样理由的注释写在前面：「测试里自己重算一遍是假绿，
    改坏这里它照样过」。
    """
    out = [f"    /job-apply {u}" for u in links[:_REWRITE_SHOWN]]
    if len(links) > _REWRITE_SHOWN:
        # 截断了要说截了多少，并给出拿到其余那些的办法 ——
        # 沉默的截断在这个仓库里是有名字的一类。
        out.append(f"    另有 {len(links) - _REWRITE_SHOWN} 个，"
                   f"改完这批再跑一次自检就会列出来：")
        out.append("    python tools/audit_pipeline.py --actionable")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="拿真实职位库审流水线自己的规则漏洞")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--only", default="",
                    help="只跑名字里含这些词的检查，逗号分隔"
                         "（每批收尾时验一两条用，全量留给整轮收尾）")
    ap.add_argument("--actionable", action="store_true",
                    help="只留「现在还补得上」的那几条（收尾用）。判据是那条检查"
                         "分不分得清哪些还没投出去——分不清的报的是存量，"
                         "印在收尾里只会把还来得及的那几条淹掉")
    ap.add_argument("--user", help=_cli.HELP_USER)
    ap.add_argument("--requeue-unfounded", action="store_true",
                    help="把判据不成立的硬门 FAIL 放回待评队列"
                         "（平台写「经验不限」的、正文与卡片两处都没依据的）")
    ap.add_argument("--requeue-no-jd", action="store_true",
                    help="把「没读 JD 却给了可投档位」的岗放回待评队列")
    ap.add_argument("--apply", action="store_true",
                    help="配合 --requeue-unfounded / --requeue-no-jd：真的落盘"
                         "（默认只报要动几个）")
    ap.add_argument("--rewrite-list", action="store_true",
                    help="只印「要改已有内容」那批的职位链接，一行一个，不截断"
                         "（/job-auto 拿它排队用；人看的那份在 --actionable 里）")
    ap.add_argument("--sections", nargs="*", metavar="路径",
                    help="逐份查深评小节写全没有（写盘之后当场跑）。"
                         "给 evaluation.md 的路径或它所在的目录都行，"
                         "不给就查今天写的那一批（按深评自己写的评估日期，"
                         "不按文件时间）；缺任何一节退出码非零")
    a = ap.parse_args(argv)
    if a.sections is not None:
        return _sections_cli(a.sections)
    user = _cli.pick_user(a.user or "", root=ROOT)
    if a.requeue_no_jd:
        hit = requeue_no_jd_sellable(user, apply=a.apply)
        if not hit:
            print("没有这一类的岗，不用动")
        elif a.apply:
            print(f"{len(hit)} 个岗放回待评队列了（旧库存成 "
                  f"seen_jobs.json.bak-before-requeue-nojd）。"
                  f"JD 抓回来之后跑 /job-rank 重评它们")
        else:
            print(f"会把 {len(hit)} 个岗放回待评队列。加 --apply 才真的动"
                  f"（判据：结论是「可以考虑」及以上，而那个分是没读 JD 正文给的）")
        return 0
    if a.requeue_unfounded:
        hit = requeue_unfounded_gate_fails(user, apply=a.apply)
        # **放回几个不等于判错几个。** 深评过的一律不碰（见那个函数），
        # 而那批同样判据不成立 —— 不说出来，用户会把上面那个数当成全部。
        n_skip = _REQUEUE_SKIPPED[0] if _REQUEUE_SKIPPED else 0
        tail = ((chr(10) + f"另有 {n_skip} 个判据同样不成立，这个工具故意没动 —— "
                 f"它们已经深评过，读过 JD 的判断比粗筛强，抹掉等于丢掉真做过的工作。"
                 f"那批的 FAIL 写在 evaluation.md 里，"
                 f"只能逐个重跑 /job-apply <职位链接> 改；"
                 f"/job-rank --all 改不了它们（它只重写职位库的分，不碰深评文件）。")
                if n_skip else "")
        if not hit:
            print("没有这一类的岗，不用动" + tail)
        elif a.apply:
            print(f"{len(hit)} 个岗放回待评队列了（旧库存成 "
                  f"seen_jobs.json.bak-before-requeue）。下一步：跑 /job-rank 重评它们"
                  + tail)
        else:
            print(f"会把 {len(hit)} 个岗放回待评队列。加 --apply 才真的动"
                  f"（判据：年限那道门判错的两档、正文与卡片两处都没依据的、"
                  f"以及按一条他资料里没有的排除杀掉的）" + tail)
        return 0
    found = run(user, only=a.only,
                actionable=a.actionable or a.rewrite_list)
    if a.rewrite_list:
        # **不截断，也不排版。** `--actionable` 那份印给人看，`_REWRITE_SHOWN`
        # 卡在 12（「再多就是一屏命令，读的人不会一条条敲」）—— 那对人是对的，
        # 而 `/job-auto` 不是人：它照那份只改得动 12 个，剩下的靠那句
        # 「改完这批再跑一次自检就会列出来」等下一轮，也就是把排队这件事
        # 交回给了用户。
        #
        # 集合走 `live_tail(verb="改")` 自己攒的那份（`_cli.LIVE_REWRITE`），
        # 不在这儿另立一份「哪几条属于改」的名单 —— 那种名单只盖得住已经
        # 想到的，而这份审计还在长。所以上面那行要带 `actionable`：
        # 不进那一档，`live_tail` 一次都不会被调到，这里恒为空。
        for _u in _cli.LIVE_REWRITE.values():
            print(_u)
        return 0
    if a.json:
        print(json.dumps([{"level": l, "kind": k, "detail": d} for l, k, d in found],
                         ensure_ascii=False, indent=1))
        return 1 if any(l == "error" for l, _, _ in found) else 0
    _terms = [t.strip() for t in a.only.split(",") if t.strip()]
    n_run = sum(1 for name, _ in CHECKS
                if not _terms or any(t in name for t in _terms))
    if a.actionable:
        # **别把「跑了 57 项」印给用户看**——`--actionable` 下真正报出来的
        # 只有那几条，说 57 会让「一条都没有」读成「全都好着呢」。
        n_run = len({r[1] for r in found})
    if a.only and not n_run:
        print(f"没有名字里含「{a.only}」的检查。全部名字："
              + "、".join(name for name, _ in CHECKS))
        return 2
    if not found:
        scope = f"{n_run} 项" + (f"（只跑了含「{a.only}」的那几条）" if a.only else "")
        print(f"流水线审计：{scope}检查全过（用户：{user}）")
        return 0
    err = [x for x in found if x[0] == "error"]
    print(f"流水线审计（用户：{user}）：{len(err)} 个要修 · {len(found) - len(err)} 个留意")
    if a.actionable and _cli.LIVE_SEEN:
        # **六条各报一个数，读的人加不出总数。** 而它们指的多半不是同一批岗
        #（实测 2026-08-30：提及 113 次、去重后 101 个，只有 12 个重叠），
        # 所以「加起来」这件事只有这里做得了。
        #
        # 一次补完给一条命令：`/job-apply 全部` 走的是同一套批量，
        # 有材料的只补缺的那一节（判据见 `job-apply.md` 那张补漏表），
        # 没材料的照常出。判词是「不投」的那一档它按设计不收 ——
        # 那几个要单独跑 `/job-apply <职位链接>`。
        #
        # ⚠️ **这一段印在明细之前。** 它原来收在最后，也就是 41 行之后 ——
        # 而这一整档的价值就在这一句。同一个毛病在单条消息里刚修过两次
        #（那串按批次的枚举、按 26 个规模写的补法），这次是在报告这一级：
        # **要动手的那句排在最前，解释排在后面。**
        print(f"\n下面这几条去重后是 {len(_cli.LIVE_SEEN)} 个岗"
              f"（同一个岗可能被两条点到）。一次补完：")
        print("    /job-apply 全部")
        print("  它对有材料的只补缺的那一节，不重跑深评、不重写已有的开场白。"
              "想挑着补就看下面每条各自给的链接。")
        # **把「补」和「改」分开说。** 上面那句已经写明它不重跑深评，
        # 可总数把两类算在了一起 —— 于是「一次补完」听起来像是全包了。
        # 「依据说错了数」「开场白踩了线」这些要重写已有内容，`全部` 一个
        # 都改不了。集合由 `live_tail(verb="改")` 自己攒（见 `_cli.LIVE_REWRITE`），
        # 不在这儿手写一张「哪几条属于改」的名单 —— 那种名单只盖得住
        # 已经想到的，而这份审计还在长。
        # 每条检查只印一个链接（live_tail 印的是第一个），所以这几条
        # 要在这儿整张印出来 —— 上一版让用户「照下面那几条各自的链接
        # 一个一个跑」，而下面根本没有那几条：10 个岗，屏幕上 2 个链接。
        # 指一件事不够，要把该敲的原样写出来（AGENTS.md 那条）。
        _rw = list(_cli.LIVE_REWRITE.values())
        if _rw:
            print(f"  其中 {len(_rw)} 个要改已有内容（不是补一节），"
                  f"上面那条不重跑深评、改不了它们。这几个一个一个跑：")
            for _line in rewrite_commands(_rw):
                print(_line)
    for lvl, kind, detail in found:
        print(f"\n  [{'要修' if lvl == 'error' else '留意'}] {kind}")
        print(f"      {detail}")
    print("")
    print("这些是规则漏洞，不是数据脏——单元测试用构造数据测不出来。")
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
