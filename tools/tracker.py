#!/usr/bin/env python3
"""投递记录（`job_search_tracker.csv`）的读写。

## 为什么有它

求职里最高频的动作是「我投了」「约面了」——按 `/job-outcome` 的定义，它就是**改台账
status 一列、再追一条带日期的备注**。这正是 `serve.py` 自己写的那条边界：
「所有操作都是改一个字段，不需要判断力」。可它此前只接了「不投 / 放回」两个，
于是最常做的那件事仍然要回命令行敲 `/job-outcome 公司名`、再答一串问题。

serve.py 当初存在的理由就是这句：「页面上一个动作，人要在两个地方各做一遍」。
这个模块把剩下那一半接上。

**需要判断力的仍然归命令行**：谈薪区间、背调红线、offer 比较（`/job-offer`）、
面试准备（`/job-interview`）、跟进话术（`/job-outcome` 的 Step 2b）——那些要读资料、
要权衡，页面给不了。页面只负责把「发生了什么」记下来。

## 状态的走向是一条链，不是一个下拉框

界面上不该一次摆出八个状态让人挑——从「已投递」直接跳到「入职了」不是正常路径，
摆出来只会让人点错。所以按**当前状态**给下一步（见 `NEXT`）：没投的只有一个
「我投了」，投了的才有「约面了 / 挂了 / 没下文」。

这也和整个面板的取向一致：它回答的始终是「我现在该做什么」，不是「有哪些选项」。

## 改动只碰该碰的那一格

`/job-outcome` 的原话：never restructure the CSV, reorder rows, or touch other rows。
这里照办——列顺序原样写回，其它行一个字节不动，只改命中那行的 `status` 与 `notes`。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402  原子写在这儿（写台账不能先截断文件）

#: 标准列序。与 `workflows/job-outcome.md` 里建表时用的那一行一致——
#: 新建台账时按它写表头，已有台账**一律沿用文件自己的列序**，不强行改。
HEADER = ["date", "company", "sector", "role", "role_type", "channel", "status",
          "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
          "source", "outcome_reason"]

#: 域名 → 平台名。与 `portal_budget.HOME` 是同一批站，但方向相反
#: （那边是「平台 → 首页」，这边是「链接 → 平台」）。
def channel_of(row: dict) -> str:
    """这一笔投递是**从哪个平台**投出去的。取不到返回空串。

    ## 为什么要推，而不是只读 `channel` 那一列

    `channel` 是标准列、`job-outcome.md` 拿它决定跟进话术的形态（邮件 / 站内私信 /
    网申留言）、`followups.py` 也读它——**可是没有任何一处写它**。
    实测活动用户 85 行投递记录：`channel` 列 **85 行全空**。
    于是那条「按渠道调整话术形态」的规矩一天都没生效过，
    而「哪个渠道回复率高」这个中国求职里最要紧的问题，台账根本答不了。

    而**答案其实一直在表里**：`source` 存的就是那个岗的原始链接。
    实测活动用户 2026-08-23，85 行推出来是 **猎聘 66 · BOSS 直聘 16 · 智联招聘 3**，
    三家全 0 回音 —— 三个渠道一起 0，本身就说明问题不在选哪个网站。

    > 这段原来写着「85 行全是 `liepin.com`，他一个月投的 85 个岗**全在猎聘**」。
    > 那个数是错的，而且**错得不只是难看**：面板那张「投在哪个网站，那边回不回」
    > 有个 `length > 1` 的门槛（只有一个渠道时不显示，因为对比不出东西）——
    > 照那句话，这张表根本不该出现。一个实测数错到与它支撑的功能的前提相矛盾时，
    > 说明它从来没被回读过。

    **只推不写**：不去改他的 CSV。存量行照样能统计，手填过 `channel` 的以他为准。

    域名那张表原来在这里自己写了一份（`_HOSTS`），与 `outreach_header` 那份
    **已经分叉**（这边「智联招聘」、那边「智联」），后归到 `_cli.portal_of_url`。
    """
    said = (row.get("channel") or "").strip()
    if said:
        return said
    return _cli.portal_of_url(row.get("source") or "")


#: 挂了之后可以点一下记下的原因。**全部可选**——用户 2026-08-13 原话：
#: 「有些直接明确拒绝，也没具体理由」。不填是正常路径，不是漏填。
#:
#: 做成固定选项而不是自由文本，是为了**能统计**：一堆各写各的自由文本汇不出
#: 「我到底卡在哪一环」。最后一项留给真给了具体理由的少数情况。
REASONS: list[tuple[str, str]] = [
    ("no_reason",   "没说原因"),
    ("resume",      "简历没过"),
    ("experience",  "年限或经历不符"),
    ("education",   "学历不符"),
    ("salary",      "薪资谈不拢"),
    ("closed",      "岗位关了/暂停招聘"),
    # **国内最常见的那种「不算拒绝的拒绝」。**
    #
    # HR 极少写「拒绝」两个字，写的是「您的简历已进入我们人才库，后续有合适
    # 岗位会第一时间联系您」「暂时没有更合适的岗位，我们保持联系」。
    # 全仓搜过（2026-08-24）：`人才库` / `保持联系` / `再联系` / `婉拒`
    # **一个都没有** —— 也就是说这类回复此前既进不了「被拒」，也留不下原因。
    #
    # **为什么不并进「简历没过」**：那一档会把他指去重写简历
    # 而「人才库」
    # 说的多半是**这个岗没了 HC 或者已经定了人**，跟他那份简历没关系；
    # 大厂在 HC 解冻后回捞也确实会发生。
    #
    # **也不并进「岗位关了」**：那一档是「这个岗不招了」，而人才库常常是
    # 「这个岗招了别人，但你留着」—— 对下一步的含义不同（前者别再看这家，
    # 后者值得隔一阵回来看）。
    ("talent_pool", "进了人才库/让保持联系"),
    ("after_intv",  "面试之后被拒"),
    ("i_declined",  "我自己不想去了"),
    ("other",       "其它（自己写一句）"),
]
REASON_LABEL: dict[str, str] = dict(REASONS)

#: 当前状态 → 可以点的下一步 `[(写进去的值, 按钮上的字)]`。
#:
#: 空串是「台账里还没有这一行」，也就是还没投。
#:
#: 终结态（hired / rejected / no response / offer declined / withdrawn）不给按钮：
#: 已经结案了，再改就不是「记一笔」而是修订，那该走 `/job-outcome`。
#:
#: `withdrawn`（我撤回了）没做成按钮——它少见，且往往连着一段要写清楚的原因，
#: 塞进按钮会让人一句话不写就点掉。
#:
#: `interview_only`（面过没下文）同理，虽然它看着像 `applied → 没下文` 的对称位。
#: `job-outcome.md` 给它的定义是「面到了，但**流程停在那儿、或者不了了之**，
#: 始终没有明确的拒绝」—— 那是两件不同的事，而分得清它们的只有他。
#: 一个按钮会把这个判断塌成一次点击，正是撤掉终结态出口时给的同一条理由
#: （「那不是『记一笔』，是一个判断」）。面板这条路的边界是「改一个字段，
#: 不接大模型」，越过它的都归 `/job-outcome`。
#:
#: **点不到的状态必须逐个说清为什么**，`test_every_status_can_be_said`
#: 的登记表盯着这一点：2026-08-13 那次「状态机里有 4 个状态面板进不去」
#: 是人扫出来的，扫完没留下任何机械判据。
NEXT: dict[str, list[tuple[str, str]]] = {
    "": [("applied", "我投了")],
    "applied": [("interview", "约面了"), ("rejected", "挂了"),
                ("no response", "没下文")],
    "interview": [("offer", "拿到 offer"), ("rejected", "挂了")],
    "offer": [("hired", "入职了"), ("offer declined", "我拒了")],
    # **`rejected` / `no response` 故意没有出口 —— 试过加，撤回了（2026-08-23）。**
    #
    # 动机是真的：国内拒信多是同一天群发的模板，隔几天某个岗位重启或另一个部门
    # 单独捞人；而「没下文」根本是用户按 10 天线自己猜的（实测 85 笔里 76 笔够线，
    # 面板一路在劝他点它），点完那一行就永远冻住。
    #
    # 撤回有两条独立的理由，任一条都够：
    #
    # 1. **那不是「记一笔」，是一个判断。** `job-outcome.md` Step 2 写着：
    #    拒信之后来一封邀约有三种读法 —— 同一条线（后一封为准）、两次不同投递
    #    （根本不该改这一行）、看不清（不判）。一个按钮会把它塌成第一种，
    #    而那条正文自己写着「别替他判第一种」。面板这条路的边界是「改一个字段，
    #    不接大模型」，这件事越过了它。
    # 2. **`undo` 会连带丢掉拒绝原因。** 撤销时无条件清空 `outcome_reason`，
    #    而那之所以安全，靠的正是「终结态出不去」这条前提
    #    （`test_outcome_feedback_and_stats.test_terminal_states_cannot_be_left`
    #    的 docstring 明写着「哪天终结态之间可以互相转移了，那个无条件清空
    #    就得重新想」）。允许复活 → 标拒绝并记原因 → 复活 → 撤销，原因就没了。
    #
    # 要做的是**在页面上把去处说出来**，不是加按钮。
    #
    # **那句话在 `web/src/components/OutcomeStats.tsx`，不在岗位那一行。**
    # 这里原来写的是「那一行现在会印一句…」—— 名实不符：已结案的岗
    # （入职 / 挂了 / 没下文）`job.nextStep` 是 null，`JobReadout` 里
    # 整行不渲染，那一行印不出任何东西。去处落在统计面板那一段：
    # 「『挂了』和『没下文』都不是终局……会先问清是不是同一次投递」
    # 加一个 `/job-outcome <公司>` 命令块。
    #
    # `tests/test_a_terminal_state_still_has_an_exit.py` 钉着它：
    # 终结态没有按钮**是对的**，但页面上必须有一处说得出去处 ——
    # 撤按钮的那次裁定给的正是这个交换条件，它掉了就等于裁定只执行了一半。
}

#: 点完之后**还需要模型**的那一步。记完状态顺手告诉他该敲什么——
#: 这就是页面与命令行的分界：状态记在页面，判断交给命令。
AFTER: dict[str, str] = {
    "interview": "/job-interview",
    "offer": "/job-offer",
}

#: 写进 `notes` 的来源标记。撤销时靠它确认「这行是页面建的」——
#: 没有这个标记就绝不删行，那可能是用户自己手写的记录。
MARK = "在总览页记的"

#: 状态码 → 用户自己会说的话。**从 `NEXT` 派生**，不另抄一份。
#:
#: `status` 一列存的是 `applied` / `interview` 这样的英文码（`/job-outcome` 和
#: `/job-html-report` 都按它统计，不能改）。但备注是给人读的，实测漏出去过：
#: 台账里写着「改为 interview」「撤销，退回 applied」——正是 `AGENTS.md`
#: 说的「未解释的英文码不要搬到台面上」。
#:
#: 另抄一份的下场是加个新状态时按钮上是中文、备注里又漏出英文码。
LABEL: dict[str, str] = {v: t for opts in NEXT.values() for v, t in opts}

#: 终结态：到这些状态就结案，不再催、不再给下一步。**这是唯一权威的一份**——
#: 原来 `followups.py` 与 `build_dashboard.job_next_step` 各抄一份，抄到第二份时
#: 就漏了 `no_response`（下划线体）：同一条旧记录，催进度那边说「已终结不催」，
#: 面板的逐岗下一步却说「超过十天没动静可以催一次」。两种拼法都收，
#: 是因为存量 CSV 里两种真实存在（`workflows/job-outcome.md` 记过这段历史）。
FINAL_STATUSES = {"hired", "rejected", "no response", "no_response",
                  "withdrawn", "offer declined", "offer_declined",
                  "interview_only"}

#: 只给 `say()` 用的补充：**是正式状态、但不是按钮**的那几个。
#: `withdrawn` 是 `/job-outcome` 文档里的终结态（用户真会记它），可它刻意不做成
#: 按钮（见 NEXT 上面的说明）——于是从按钮表派生不出来，经 `/job-outcome` 撤回的行
#: 在总览页上就裸印英文码。不能直接塞进 LABEL：`html-report.md` 把 LABEL 钉为
#: 「按钮上的字」，塞进去按钮词表就说谎了（`test_report_wording_matches_the_panel`
#: 会红）。
SAY_EXTRA: dict[str, str] = {
    "withdrawn": "我撤回了",
    # **下划线体也要能说成人话。** `FINAL_STATUSES` 两种拼法都收（存量 CSV 里
    # 两种都真实存在，`job-outcome.md` 记过这段历史），而 `say()` 原来只认空格版
    # ——于是一条 `no_response` 的记录在面板上**裸印英文码**，正是
    # `AGENTS.md`「未解释的英文码」那条禁的东西。
    # 2026-08-13 全面检查命令逻辑时扫出来：状态机里有 4 个状态面板进不去，
    # 顺着查到这里。
    "no_response": "没下文",
    # **和空格体说成同一个词。** 这里原来写「我拒了 offer」，而按钮那一份
    # （`LABEL["offer declined"]`）写的是「我拒了」—— 同一件事，两种拼法，
    # 两个说法：同一张列表里两行相同的结局，读起来像两回事。
    # 存量 CSV 里两种拼法都真实存在（`FINAL_STATUSES` 收两种就是为这个），
    # 所以它们必须说成同一个词。按钮那一份是正本（`html-report.md` 把
    # `LABEL` 钉为「按钮上的字」），这边跟它。
    # 2026-08-31 `test_both_spellings_are_covered` 第一次跑就把它照出来了。
    "offer_declined": "我拒了",
    "interview_only": "面过没下文",
}


def say(status) -> str:
    """状态写成人话。空串是「台账里还没有这一行」；认不出的原样返回——
    宁可露出一个码，也好过把用户的状态说成别的。"""
    s = (status or "").strip()
    return LABEL.get(s) or SAY_EXTRA.get(s) or s if s else "还没投"


class Unreadable(ValueError):
    """台账不是 UTF-8，读不出原来的行。

    读侧（`build_dashboard.load_tracker`）一直把这种文件降级成空表；写侧不能
    跟着降级——那会把整份中文台账覆盖成只有本次新建的一行。所以写路径在这里
    停下并说清怎么修。
    """


def load(path: Path) -> tuple[list[str], list[dict]]:
    """`(列名, 行)`。文件不存在时返回标准列序与空表。

    用 `utf-8-sig` 是因为 Excel 存出来的 CSV 常带 BOM——`build_dashboard.load_tracker`
    也是这么读的，两边保持一致。**写路径**遇到别的编码要抛 `Unreadable`，
    不能照空表继续写（详见类说明）。
    """
    if not path.is_file():
        return list(HEADER), []
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            r = csv.DictReader(fh)
            rows = list(r)
            cols = list(r.fieldnames or HEADER)
    except UnicodeDecodeError as exc:
        raise Unreadable(
            f"投递记录 {path.name} 不是 UTF-8（{exc.reason}）——"
            "先在 Excel 或记事本里另存为 UTF-8 CSV，再试一次；这次没有写盘。"
        ) from None
    return cols, rows


def save(path: Path, cols: list[str], rows: list[dict]) -> None:
    """整表写回。列序沿用读进来的那份，不重排。

    `newline=""` 是 csv 模块的硬要求；少了它 Windows 上每行会多一个 `\\r`。

    ## 原来有 BOM 就把 BOM 写回去

    读用 `utf-8-sig`（Excel 存出来的 CSV 常带 BOM），写却一直用 `utf-8`——于是
    **用户在页面上点一下按钮，BOM 就没了**。下次他再用 Excel 打开这份台账，
    Windows 版 Excel 在没有 BOM 时按系统 ANSI（中文机器上是 GBK）解，公司名和备注
    全变乱码。而他不会想到那是「点了一下我投了」造成的。

    这里只做**往返保真**：进来有 BOM 就带 BOM 写回，没有就不加。不主动给所有文件
    加 BOM——那是改文件格式，不是修 bug。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    had_bom = path.is_file() and path.read_bytes()[:3] == b"\xef\xbb\xbf"
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for row in rows:
        w.writerow({c: row.get(c, "") for c in cols})
    _cli.atomic_write(path, buf.getvalue(),
                      encoding="utf-8-sig" if had_bom else "utf-8",
                      newline="")


def next_steps(status: str) -> list[dict]:
    """当前状态能点的下一步，给页面用。"""
    return [{"value": v, "label": t, "then": AFTER.get(v, "")}
            for v, t in NEXT.get((status or "").strip().lower(), [])]


def can_go(now: str, nxt: str) -> bool:
    """从 `now` 走得到 `nxt` 吗。

    规则放在 `NEXT` 旁边，不放在服务端——**页面画什么按钮和服务端放什么请求过，
    必须是同一张表**。分成两处写，分叉的样子是页面画出一个按钮、服务端拒绝它，
    而两边看起来都没错。

    这不是「枚举里有就行」：没投过的岗不能一步标成 `hired`。台账是 `/job-setup`
    校准和 `/job-html-report` 统计的输入，凭空多出一段录用记录会把两边都带偏。
    """
    return nxt in [v for v, _ in NEXT.get((now or "").strip().lower(), [])]


def note(day: str, status: str) -> str:
    """追加进 `notes` 的那句话。

    建行与改状态**不再分两种说法**：来源标记已经说明这行的来历，撤销也只看
    `prev` 和标记（见 `undo`），措辞不承担任何逻辑。分开写反而让备注串出现
    「投了」与「我投了」两种叫法，指的却是同一件事。

    所以这里**不收 `created`**。它曾经是个参数，而函数体从不看它——留着会让
    下一个人以为存在一条按「新建/改状态」分岔的措辞。
    """
    return f"{day} {MARK}：{say(status)}"


#: 面板点了按钮、而盘上那一行已经不在了。**`set_status` 与 `undo` 各写过一份。**
#:
#: 两处都是回给面板的 `error`，用户读到的就是这句话。写两份的代价不是显示不一致 ——
#: 是**改一处忘一处**：同一个失败，撤销那条路上的说法哪天变了，用户会以为
#: 自己撞上了另一件事。
ROW_GONE = "投递记录里找不到这一行了——刷新一下页面再试"


def set_status(path: Path, row, job: dict, status: str, day: str,
               reason: str | None = None) -> dict:
    """把 `status` 写进台账。`row` 是 `match_tracker` 找到的行，没有就传 None。

    返回 `{ok, prev, created, ...}`：`prev` 是改之前的状态（新建行时为 None），
    页面拿它做「撤销」。
    """
    cols, rows = load(path)
    created = row is None
    if created:
        hit = {c: "" for c in cols}
        hit["date"] = day
        hit["company"] = (job.get("company") or "").strip()
        hit["role"] = (job.get("title") or "").strip()
        hit["source"] = (job.get("url") or "").strip()
        # sector / role_type / channel 留空——**不猜**。台账是给人回看的，
        # 填一个「大概是这个行业」进去，下次 /job-setup 校准就按它算了。
        rows.append(hit)
        prev = None
    else:
        # 调用方那份 `row` 来自**它自己那次**读盘，这里必须在**本次**读到的
        # `rows` 里重新认一遍——不然改的是一个不会被写回去的副本，
        # 接口报成功而盘上什么都没变。认不到就报错，不要静默追加一行。
        hit = next((r for r in rows if _same(r, row)), None)
        if hit is None:
            return {"ok": False, "error": ROW_GONE}
        prev = (hit.get("status") or "").strip()
    hit["status"] = status
    hit["notes"] = "; ".join(x for x in [(hit.get("notes") or "").strip(),
                                         note(day, status)] if x)
    if reason is not None:
        # 存量 CSV 没这一列（2026-08-13 才加）。**在这里补上**，不然
        # `save()` 按 `cols` 写盘，值会被静默丢掉——写成功了、盘上没有。
        if "outcome_reason" not in cols:
            cols.append("outcome_reason")
            for r in rows:
                r.setdefault("outcome_reason", "")
        hit["outcome_reason"] = reason
        lab = REASON_LABEL.get(reason)
        if lab and reason != "other":
            hit["notes"] = "; ".join(x for x in [hit["notes"], f"原因：{lab}"] if x)
    save(path, cols, rows)
    return {"ok": True, "prev": prev, "created": created,
            "company": hit.get("company"), "role": hit.get("role"),
            "then": AFTER.get(status, "")}


def undo(path: Path, row, prev, day: str) -> dict:
    """撤销一次 `set_status`。

    `prev is None` 表示那一行是页面刚建的 —— 撤销就是删掉它。**但只删带来源标记
    的行**：没有标记说明它是用户自己手写的记录，那种情况下宁可不撤也不能删。
    """
    cols, rows = load(path)
    hit = next((r for r in rows if _same(r, row)), None)
    if hit is None:
        return {"ok": False, "error": ROW_GONE}
    if prev is None:
        if MARK not in (hit.get("notes") or ""):
            return {"ok": False,
                    "error": "这行不是在总览页记的，撤销不会动它 —— 用 /job-outcome 改"}
        rows.remove(hit)
    else:
        hit["status"] = prev
        # **原因也要撤掉，不只是状态。** 2026-08-13 实测：
        # 点「挂了」选原因「简历没过」→ 点「撤销」→ 状态回到 `applied`，
        # 而 `outcome_reason` 还留着 `resume`——一条「已投递」却带着拒绝原因的记录。
        # `outcome_stats()` 统计拒绝原因分布时会数到它，用户回看台账也讲不通。
        #
        # 无条件清空是安全的：原因只写在终结态上，而 `NEXT` 里终结态的可达集是空的
        # （`rejected`/`ghosted` 出不去），所以一行的原因只可能来自**刚被撤销的那一次**
        # `set_status`，不存在「撤销后该恢复成上一个原因」的情形。
        # 这一列是 2026-08-13 加的，加的时候只改了写入侧、漏了撤销侧。
        if "outcome_reason" in hit:
            hit["outcome_reason"] = ""
        hit["notes"] = "; ".join(
            x for x in [(hit.get("notes") or "").strip(),
                        f"{day} {MARK}：撤销，退回「{say(prev)}」"] if x)
    save(path, cols, rows)
    return {"ok": True, "deleted": prev is None}


def _same(a: dict, b: dict) -> bool:
    """同一行。按 source + company + role 认，不用对象身份 —— `load` 每次都
    重新读盘，拿到的是新对象。"""
    keys = ("source", "company", "role")
    return all((a.get(k) or "").strip() == (b.get(k) or "").strip() for k in keys)
