#!/usr/bin/env python3
"""本地服务：让总览页能**写回** `seen_jobs.json`，而不是只在浏览器里假装。

## 为什么要它

总览页原来是静态快照——`export_web_data.py` 生成完就没有后端了。于是点「不投」
只能存进 `localStorage`，真要生效还得回命令行粘一条 `/job-rank --skip`。页面上一个
动作，人要在两个地方各做一遍，还得记住不做第二遍就会白点。

这个服务把那一步接上：点「不投」直接落到 `seen_jobs.json`，刷新还在。

反过来那半边也接上了：`data.json` 是从 `seen_jobs.json` 和投递目录导出的**派生快照**，
命令行侧（`/job-apply` 深评改分、`/job-rank`、`/job-outcome`、`/job-scrape`）改的都是上游。每次请求
`/data.json` 时比一次 mtime，上游更新就先重新导出——**刷新页面即最新**，不需要谁记得
去跑 `export_web_data.py`（见 `refresh_if_stale` 的注释）。

## 它**不是**什么

**不接大模型。** 这里所有操作都是改一个字段，不需要判断力。真正要模型的活
（找职位、深评、写简历）继续在你那家 AI 编码工具里跑——那边有模型、能开浏览器、
走的是你的订阅，三样都是这个服务给不了的。

## 安全

- **只绑 `127.0.0.1`**，不绑 `0.0.0.0`：同一局域网的其它机器连不上。
- **每次启动生成一次性 token**，注入到页面里；写操作必须带上它。没有这道锁，
  你在浏览器里打开的**任何**网站都能往 `localhost:29029` 发 POST 把你的职位标成不投
  （浏览器允许跨站发简单 POST，只是读不到响应——而这里的破坏不需要读响应）。
- **写操作还要过 Origin 校验**：非同源的一律拒。两道锁是冗余的，故意的。
- 静态文件只从 `web/dist/` 取，路径要落在该目录内（挡 `../` 穿越）。

零依赖，只用标准库。
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess          # 导出走子进程（见 `_export_now`：同进程 import 会用旧代码）
import sys
import threading
import webbrowser
import datetime as _dt
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
import build_dashboard as bd  # noqa: E402  台账匹配走它的 match_tracker，别造第二份
import export_web_data as ex  # noqa: E402  复用它的 stable_id 与导出，别造第二份
import tracker  # noqa: E402

#: 默认端口。选 29029 不是随手挑的，两条硬约束把可选范围压得很窄：
#:
#: 1. **避开操作系统的临时端口范围**——那一段是系统分配给出站连接的，我们的服务
#:    启动前就可能被随机占掉，症状是「有时起得来有时起不来」，最难查。
#:    Linux 默认 32768-60999；Windows 默认 49152-65535，**但实测有机器被改成
#:    1024-15000**（`netsh int ipv4 show dynamicport tcp`）。两边都躲开，
#:    安全窗口只剩 **15001-32767**。
#: 2. **避开知名服务与常见开发端口**。上一版用的 4317 同时踩了两条：它是
#:    OpenTelemetry OTLP gRPC 的默认端口，而且落在上面那台机器的临时端口范围内。
#:    3000/5173/8000/8080/9090/5432/6379/27017 这些同理不能用。
#:
#: 29029 在窗口内、无已知服务占用，数字里带着仓库编号 029，好记也好敲。
#: 真撞上了用 `JOBS_PORT` 覆盖即可。
PORT = int(os.environ.get("JOBS_PORT", "29029"))
TOKEN = secrets.token_urlsafe(24)

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".pdf": "application/pdf",
}


#: `--user` 钉住的用户；没给就每次现读 `.active_user`。
#: 钉住的意义在于**这一次服务从头到尾都是同一个人**——服务器活着的时候用户可能在
#: 别的终端跑 `/job-user` 切走，而每请求现读会让页面中途换人：左边还是上一个人的职位，
#: 右边已经是新用户的资料了。
_PINNED_USER: str | None = None


class NoActiveUser(Exception):
    """还没有活动用户（`.active_user` 缺失、为空，或指向一个不存在的目录）。

    **这里原来抛的是 `SystemExit`，那是个陷阱。** `SystemExit` 继承自
    `BaseException` 而不是 `Exception`，于是请求处理器那句 `except Exception`
    接不住它：异常穿出去、处理线程当场死掉、连接不带任何响应就关了。
    页面收到的是「网络错误」，用户看不到任何可读的话。

    读那一侧（`refresh_if_stale`）早就撞过一次，就地补了 `except SystemExit`
    并留了注释「别让请求崩掉」——**而写那一侧一直没补**。2026-08-20 拿干净
    clone 跑测试才露出来：`/api/skip` 直接 `RemoteDisconnected`。同一个边界
    只修了一半，正是 `tests/test_one_file_one_tolerance.py` 盯的那个形状。

    改成普通异常之后，**忘了接的后果从「断连接」降级成「一句丑话」**：
    `except Exception` 会兜住它，最差也是返回一个 500 加类名。
    退出码那件事留给 `main()` —— 命令行才是该退出的地方，请求处理器不是。
    """


def active_user() -> str:
    if _PINNED_USER:
        return _PINNED_USER
    # 诊断走 `_cli.read_active_user`（正本）。这里原来自己读一遍指针，把
    # 「一个用户都没有」和「指针指着不存在的目录」合成一句 —— 而后者
    # 他的资料还在，那句话排在最前面的 `/job-setup` 恰恰修不了它。
    user, msg = _cli.read_active_user(ROOT)
    if msg:
        raise NoActiveUser(msg)
    return user


def seen_path(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / "seen_jobs.json"


def find_entry(seen: dict, job_id: str):
    """按 `id` 找条目。

    `id` 是 `stable_id(url, title)`，与导出给页面的那份**同一个函数**算出来的。

    这里特意**不用 URL 直接匹配**：`seen` 的键是 `<url>#<职位名>` 形式的去重键，
    而 51job 实测同一个 URL 下挂着两个不同职位——按 URL 匹配会同时命中两条，
    改错一条还不报错。用 (url, title) 派生的 id 才是真正的一对一。
    """
    for key, entry in seen.items():
        # 与导出侧同一套兜底：`url` 字段缺失时用 seen 的键顶上
        # （export_web_data 就是 `e.get("url") or url` 这么算 id 的）。
        # 原来这里 `if url and …` 直接跳过无 url 条目——那些岗页面上看得见，
        # 四个写接口却全部报「找不到这个岗」。
        url = entry.get("url") or key
        title = entry.get("title") or ""
        if ex.stable_id(url, title) == job_id:
            return key, entry
    return None, None


def not_found() -> dict:
    """页面上那个岗已经不在职位库里了。

    **这句话只许有一份。** 它是给用户看的，而 2026-08-30 之前 `serve.py` 里
    逐字抄了 **6 遍** —— 六个端点各写各的，改一处等于制造分叉。
    每次返回新的 dict、不共用一个常量：调用方往里加字段是常事。
    """
    return {"ok": False, "error": "职位列表里找不到这个岗了——刷新一下页面再试"}


def _locate(job_id: str):
    """`(职位库路径, 键, 那条记录, 整份 JSON)`；找不到时记录为 `None`。

    四个改字段的端点（不投 / 已下线 / 对方看过 / 放回）开头是同样的五行：
    读活动用户、拼路径、载 JSON、`find_entry`、找不到就回同一句话。
    **抄四遍的代价不在行数**，在于其中任何一条改了读法（比如哪天要连存档
    一起找），另外三条不会跟着改 —— 而它们对用户是同一个语义。

    ⚠️ **整份 `data` 也要还回去。** 合并那一刻它看着没人用（三个端点走
    `set_user_decision`，只碰叠加层），于是第一版只返回三样 ——
    而 `apply_restore` 改的是 `entry` 这个**引用**、最后要把整份写回盘，
    当场 `NameError`。**四段代码「长得一样」不等于「作用一样」**，
    那正是抽公共段的那个坑，测试当场抓住了。
    """
    user = active_user()
    path = seen_path(user)
    data = json.loads(path.read_text(encoding="utf-8"))
    key, entry = find_entry(_cli.seen_of(data), job_id)
    return path, key, entry, data


def apply_skip(job_id: str, reason: str) -> dict:
    """标记不投。字段语义与 `/job-rank --skip` 完全一致，不多改一个。"""
    p, key, entry, data = _locate(job_id)
    if entry is None:
        return not_found()
    # **写叠加层，不写职位库。** 职位库那边 `/job-rank` 正在整份重写，
    # 两边写同一个文件，长跑的那一方会把这一下抹掉（见 `_cli.set_user_decision`）。
    # 不动 rank_score / rank_verdict / first_seen —— 分数是评估结果，
    # 不因为你不投而失效；下次回看当初为什么排除，那些还得在。
    _cli.set_user_decision(p, key, "skipped",
                           date=date.today().isoformat(),
                           reason=reason or "用户手动排除")
    return {"ok": True, "title": entry.get("title"), "key": key}


def apply_expire(job_id: str) -> dict:
    """标记职位已下线。与「不投」是两件事，不要合并。

    「不投」是**你的判断**（不合适、不想投）；「已下线」是**外面的事实**
    （职位关了、报名截止、点开是聚合页）。两者对下游的意义不同：不投的岗留在
    搁置区供回看，已下线的岗连「当初为什么不投」都没有意义可回看，它只是没了。
    `/job-apply` 的批量流程判到「职位已关闭」时写的也是这个状态，页面按钮与它同款。

    **不动 rank_score / rank_verdict**：评估结果不因职位下线而失效——万一是误判
    （比如点开恰好是聚合页而职位其实还在），放回来时分数还得在。
    """
    p, key, entry, data = _locate(job_id)
    if entry is None:
        return not_found()
    _cli.set_user_decision(p, key, "expired", date=date.today().isoformat())
    return {"ok": True, "title": entry.get("title"), "key": key}


def apply_hr_viewed(job_id: str, viewed) -> dict:
    """记一笔「这份简历对方点开过没有」。`viewed=None` 撤销。

    国内平台在「投递记录」里逐条标着已查看 / 未查看，**这个数平台白给**，
    而它把「投了没回音」拆成两件后果相反的事（`job-outcome.md` Step 2b）：
    已查看还是没回 → 才轮到审简历；大多未查看 → 改简历没用。

    在这之前它只写在那一个工作流里，答案无处可落 —— 用户去平台看一眼，
    然后查一次忘一次。这个端点就是那个落点，判据见 `_cli.set_hr_viewed`。

    **不动 `decision`、也不动台账**：这不是投递状态，是关于那次投递的一条观察。
    """
    p, key, entry, data = _locate(job_id)
    if entry is None:
        return not_found()
    _cli.set_hr_viewed(p, key, viewed)
    return {"ok": True, "title": entry.get("title"), "key": key}


def apply_unblock(name: str) -> dict:
    """把某家招聘网站的风控冷却解掉。**只由人点，工具永远不自动解。**

    2026-08-19 用户裁定：「显示封了的时候就应该停止 24 小时，除非手动点击解封。
    否则 24 小时内，即使勾选了平台，也不该使用。」

    为什么解封这件事必须归人：撞风控多半要**他本人**去过一次验证（短信、滑块、
    联系客服），过没过完只有他知道。工具按时间自动解，等于赌那 24 小时里
    平台自己消气了——而当天的实测是它没有：限流之后账号被标异常，再之后 IP 被封，
    一次比一次重。
    """
    import datetime as _d
    import portal_budget as pb
    # **名字不认识就直说，别回一句「本来就没被封」。**
    #
    # `clear()` 对认不出的名字返回 `was=False`，于是下面那两支会说
    # 「XX 的浏览器现在没有被封，不用解」—— 把「查无此渠道」说成「没封」，
    # 而用户刚过完的那个短信验证还封着，他会以为自己点错了按钮。
    #
    # 命令行那条 `--clear` 2026-09-01 已经改成认名字（打错就退出码 2）。
    # **同一件事两个入口，判据得是同一条** —— 那道不对称是那次改出来的。
    if not pb.known_channel(name):
        return {"ok": False,
                "error": f"没有叫「{name}」的渠道——刷新一下页面，"
                         f"告警条上那几条才是现在真封着的"}
    user = active_user()
    data = pb.load(user)
    # **解哪一条通道归 `portal_budget.clear()` 判**，这里再判一次就是等着两处分叉。
    #
    # 面板传过来的是**渠道名**（`liepin-browser` 这种，不是平台名），走的是
    # `clear()` 的「给渠道名就只解那一条」分支 —— 精确、没有歧义。
    # 传平台名会让 `clear()` 自己去挑（按剩余时长挑，平手偏 CLI），而告警条
    # 现在是**一条通道一行**：用户点的是他刚处理完的那一条，挑错的代价是
    # 他过完的短信验证原样封着、没人管的匿名接口反倒提前恢复。
    # 命令行的 `--clear` 仍然收平台名，那条路上用户看得见全部通道，语义不同。
    now = _d.datetime.now()
    site, lane, was = pb.clear(data, name, now)
    if lane == pb.AMBIGUOUS:
        # 面板正常情况下报的是渠道名，走不到这儿；能走到就说明前端退回了
        # 老的按平台名那条路（老 `data.json` 没有 `blockedLanes`）。
        # **那也不许猜**：两条各自因为不同的事封着，猜错就是替他解掉
        # 一个他没过的短信验证。让他刷新拿到分行的告警条，再点具体那一条。
        return {"ok": False,
                "error": f"{site} 有两条通道各自封着，而且不是同一件事——"
                         "刷新一下页面，告警条会分行列出来，点你刚处理好的那一条"}
    if not was:
        # 说的是**你点的那条通道**，不是整家 —— 另一条还封着时别说成「没被封」。
        other = [lg for lg in pb.lanes_of(site) if lg != lane
                 and pb.block_state(data, site, now, lg)["blocked"]]
        which = " CLI " if lane == "cli" else "浏览器"
        # 两支各自写全 —— 「下一步」拼在变量里的话，读这一行的人（和
        # `test_error_messages` 那条守卫）都只看得到「不行」，看不到怎么办。
        if other:
            return {"ok": False,
                    "error": f"{site} 的{which}现在没有被封，不用解；"
                             "另一条还封着——刷新一下页面，告警条会分行列出来"}
        return {"ok": False,
                "error": f"{site} 的{which}现在没有被封，不用解"
                         "——刷新一下页面看最新状态"}
    pb.save(user, data)
    return {"ok": True, "name": site}


#: 终端里那行日志说的是哪件事。原来是 `'不投' if path.endswith('skip') else '放回'`
#: ——加第三个接口时它会把「记状态」也说成「放回」。
_LOG_VERB = {"/api/skip": "不投", "/api/expire": "已下线", "/api/restore": "放回",
             "/api/status": "记状态", "/api/status/undo": "撤销",
             "/api/portals": "渠道开关", "/api/prefs": "岗位类型开关",
             "/api/unblock": "解封", "/api/hr-answer": "改常用问答",
             "/api/hr-viewed": "记简历看没看",
             "/api/resume-refreshed": "记刷了在线简历"}


def _job_and_row(job_id: str):
    """`(职位, 台账路径, 命中的行)`；找不到职位时职位为 None。

    匹配走 `build_dashboard.match_tracker`——与页面显示 `已投递` 用的**同一个函数**。
    另写一套的下场是：页面说这个岗已投、按钮却在另一行上改状态，两边永远对不齐。
    """
    user = active_user()
    data = json.loads(seen_path(user).read_text(encoding="utf-8"))
    _, entry = find_entry(_cli.seen_of(data), job_id)
    if entry is None:
        return None, None, None
    path = ROOT / "users" / user / "job_search_tracker.csv"
    job = {"company": entry.get("company") or "", "title": entry.get("title") or "",
           "url": entry.get("url") or ""}
    return job, path, bd.match_tracker(job, job["url"], bd.load_tracker(path))


def apply_status(job_id: str, status: str, reason: str | None = None) -> dict:
    """把投递状态记进台账。**只改一个字段**，判断留给命令行。

    允许的取值只能来自 `tracker.NEXT`——不是「枚举里有就行」，而是**从当前状态
    确实走得到**。少了这层，一个构造的请求能把没投过的岗直接标成 `hired`，
    而台账是 `/job-setup` 校准和 `/job-html-report` 统计的输入。
    """
    job, path, row = _job_and_row(job_id)
    if job is None:
        return not_found()
    now = (row.get("status") or "").strip() if row else ""
    # **补一条原因不是状态转移**：状态不变，只往当前这一行补一个字段。所以它不过
    # `can_go`——终结态按设计没有任何后继（`tracker.NEXT` 不给，那是 `undo` 里
    # 「无条件清空原因」的前提），补原因走 `can_go` 必然被自己挡下来，
    # 「挂了」之后那排原因就一个也点不动。放行的只有这一种：**状态不变 + 带原因**。
    # 同状态不带原因仍然拒绝，免得给终结态开出一条自环。
    if not (reason and status == now and row is not None):
        if not tracker.can_go(now, status):
            return {"ok": False,
                    "error": f"从「{tracker.say(now)}」走不到「{tracker.say(status)}」"
                             "——刷新一下页面再试"}
    # 原因只在「挂了」这类结果上有意义，且**永远可选**——用户 2026-08-13：
    # 「有些直接明确拒绝，也没具体理由」。不给就是不给，不要在这里编一个。
    if reason and reason not in tracker.REASON_LABEL:
        return {"ok": False,
                "error": f"不认识的原因「{reason}」——刷新一下页面再点，原因是服务端给的（tracker.REASONS），页面上的那份可能过期了"}
    return tracker.set_status(path, row, job, status, date.today().isoformat(),
                              reason=reason or None)


def undo_status(job_id: str, prev) -> dict:
    """撤销上一次 `apply_status`。`prev` 由那次的响应给出，页面原样送回来。"""
    job, path, row = _job_and_row(job_id)
    if job is None:
        return not_found()
    if row is None:
        return {"ok": False, "error": "投递记录里没有这一行，没什么可撤的——刷新一下页面看看最新的"}
    out = tracker.undo(path, row, prev, date.today().isoformat())
    # 谁被撤的要带上：终端那行日志按 `title`/`company` 印，不带就是「撤销：None」。
    return {**out, "company": job.get("company"), "title": job.get("title")}


# 「规则淘汰」的判据在导出侧（ex.is_rule_skipped）——那边决定显不显示
# 「放回」按钮，这边决定放回时撤不撤判词，两边必须同一份，不再抄副本。
is_rule_skipped = ex.is_rule_skipped


def apply_restore(job_id: str) -> dict:
    """放回可以投：撤销淘汰，退回它本来的状态。

    **两种淘汰要分开处理。**

    - **用户手点的不投**：结论是他自己下的，分数与依据都还作数 → 只撤 skip 标记，
      退回原状态。
    - **规则淘汰的**（预筛的「跳过」）：结论来自一份**当场传进来的词表**，而那正是
      最容易给错的东西——实测 4 个年包 72-160 万的「智能体开发产品经理」死于标题含
      「开发」，JD 一个字没读过。既然用户明确说要放回，就说明那条规则在这个岗上判错了；
      只把 status 改回去、留着「跳过」的判词和分数，它照样躺在不投的岗位里，
      放回等于没放。所以要连判词一起撤，退回 `new` 重新走评估。

    撤掉的判词存进 `prev_verdict` 留痕，不是删掉——事后要能查这个岗当初为什么被杀。
    """
    p, key, entry, data = _locate(job_id)
    if entry is None:
        return not_found()
    # **用户自己点的那两种，撤销就是把叠加层里那条删掉**，职位库一个字不动。
    # 规则淘汰的那一支不同：它要连判词一起撤，那是**改判断**，只能写职位库。
    st = _cli.load_user_state(p)
    if key in st and not is_rule_skipped(entry):
        _cli.set_user_decision(p, key, None)
        return {"ok": True, "title": entry.get("title"), "key": key}
    # 库里遗留的旧标记（拆分之前写进去的）也要能撤，所以下面那段照旧保留
    _cli.set_user_decision(p, key, None)
    if is_rule_skipped(entry):
        entry["prev_verdict"] = {
            "判词": entry.get("rank_verdict"), "分": entry.get("rank_score"),
            "依据": (entry.get("rank_breakdown") or {}).get("依据"),
            "撤销于": date.today().isoformat(),
        }
        entry["status"] = "new"
        for f in _cli.RANK_FIELDS:
            entry.pop(f, None)
    else:
        # 打过分的退回 ranked，没打过的退回 new —— 别一律退成 new，
        # 那会让已有的分数在下次 /job-rank 时被当成没评过重跑一遍。
        entry["status"] = "ranked" if entry.get("rank_score") else "new"
    entry.pop("skip_date", None)
    entry.pop("skip_reason", None)
    entry.pop("expired_date", None)   # 「已下线」也走这条放回路径
    _cli.atomic_write(p, json.dumps(data, ensure_ascii=False, indent=1))
    return {"ok": True, "title": entry.get("title"), "key": key}


# 导出会整体重写 data.json。ThreadingHTTPServer 是每请求一线程，两个并发请求
# 同时判定「过期」就会同时往同一个文件写，读到的是半截 JSON。串行化。
_REGEN_LOCK = threading.Lock()

#: 所有**写盘**的请求都串行化。
#:
#: `ThreadingHTTPServer` 是每请求一线程，而四个写入端点
#: （`/api/skip`、`/api/restore`、`/api/status`、`/api/status/undo`）做的都是
#: **读-改-写**：读出整份 `seen_jobs.json` 或台账 CSV、改一格、整份写回。
#: 两个请求同时进来就会各读到同一份、各写回自己那份，**后写的把先写的盖掉**。
#:
#: 实测：两个线程各追加一行台账，最后文件里只剩一行——用户点了两下，
#: 只生效了一下，而且**没有任何报错**。人手点按钮看似不会撞上，可页面上
#: 「我投了」是连着几个岗快速点的，两次请求相隔几十毫秒很正常。
#:
#: 与 `_REGEN_LOCK` 分开两把：这把护的是**上游数据**，那把护的是**派生快照**的
#: 重新生成。加锁顺序固定（先 `_WRITE_LOCK` 再 `_REGEN_LOCK`），不会死锁。
_WRITE_LOCK = threading.Lock()

#: 服务启动那一刻，自己这几个模块在盘上的修改时间。
#:
#: **导出走子进程解决不了这一半。** `_export_now` 改成子进程之后，导出永远用最新
#: 代码；但**写盘那一路仍然是同进程的**——`apply_status` → `tracker.set_status`
#: → `_cli.atomic_write` 全是启动时 import 进来的对象。改了它们不重启，服务照旧
#: 按旧逻辑写盘。
#:
#: 一天之内连撞三次同一个坑：新加的 `outcomeStats` 手动导出后存在、页面查无此块；
#: 进程比代码老五小时，导出把新字段覆盖回旧格式（这条改成子进程解决）；
#: 刚把 tracker 换成原子写，跑着的服务里还是裸 write_text。
#:
#: 前两次的处理都是「写一段注释提醒重启」。**三次之后该承认：注释不是机制。**
#: 这里只做最轻的一件事——发现代码变了就在终端喊一声，并给出该敲什么。
#: 不自动重启：那会在用户正编辑文件时反复重启，比问题本身更烦。
#: `portal_budget.py` 是**函数内 import**（`apply_unblock` 里），首次调用之后走
#: `sys.modules` 缓存——改了代码生不生效，取决于「服务起来之后有没有解封过一次」，
#: 不确定。而它写的是 `portal_budget.json`（封控冷却），跑旧代码等于按旧规则解封。
#: 顶层 import 和函数内 import 在这件事上没有区别，都要看住。
#: **这份名单不再手写。** 手写的会漂，而且是静默地漂 —— 实测 2026-08-24：
#: 从 `serve.py` 顺着 import 走一遍，这个进程实际会加载 11 个仓库模块，
#: 而手写名单只有 8 个，漏掉 `doctor` / `query_yield` / `archive` 三个。
#: 三个都在 `sys.modules` 里，改了不重启就是旧代码 —— 正是这份名单要拦的事，
#: 而它自己漏了（`export_web_data` 还在函数里 `import doctor`，上面那句
#: 「顶层 import 和函数内 import 在这件事上没有区别」说的就是它）。
#: `followups.py` / `gap_split.py` 后来也是一次次手工补进来的 ——
#: 补一次漂一次。改成**从 import 图现推**：只用 `ast`，零依赖，永远跟得上。
#: 下面那个手写的当**兜底下限**：真解析不出来时不能反而少看住几个。
_CODE_FLOOR = ("serve.py", "export_web_data.py", "build_dashboard.py",
               "tracker.py", "_cli.py", "portal_budget.py",
               "followups.py", "gap_split.py")


def _loaded_modules() -> tuple:
    """从 `serve.py` 顺着 import 走一遍，列出这个进程会加载的仓库模块。

    只认 `tools/` 下的模块名，标准库与第三方不看（改不动，也不归我们管）。
    解析失败就退回 `_CODE_FLOOR` —— **宁可少报一个改动，不可少看住一个文件**。
    """
    import ast
    here = ROOT / "tools"
    names = {p.stem for p in here.glob("*.py")}
    seen: set = set()

    def walk(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        f = here / (name + ".py")
        if not f.is_file():
            return
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            return
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name in names:
                        walk(a.name)
            elif isinstance(n, ast.ImportFrom) and n.module in names:
                walk(n.module)

    try:
        walk("serve")
    except RecursionError:
        return _CODE_FLOOR
    return tuple(sorted({m + ".py" for m in seen} | set(_CODE_FLOOR)))


_CODE_FILES = _loaded_modules()
_CODE_MTIME = {f: (ROOT / "tools" / f).stat().st_mtime
               for f in _CODE_FILES if (ROOT / "tools" / f).is_file()}
_STALE_WARNED = set()


def warn_if_code_changed() -> list:
    """代码比进程新就喊一声，返回变了的文件名（喊过的不重复喊）。"""
    changed = [f for f, m in _CODE_MTIME.items()
               if (ROOT / "tools" / f).is_file()
               and (ROOT / "tools" / f).stat().st_mtime > m]
    fresh = [f for f in changed if f not in _STALE_WARNED]
    if fresh:
        _STALE_WARNED.update(fresh)
        sys.stderr.write(
            "\n  [!] 这几个文件在服务启动之后改过：" + "、".join(fresh) + "\n"
            "      页面上的写入还在按启动那一刻的代码跑。要让改动生效：\n"
            "      到这个终端按 Ctrl+C 停掉，再跑一次 python tools/serve.py\n\n")
    return changed


def with_detected_tool(raw: bytes, tool: str) -> bytes:
    """把 detectedTool 盖成**起这个服务的环境**探测到的工具。

    导出器在导出那一刻把 detectedTool 烤进 data.json，而 data.json 只在
    「上游数据变了」时才重导——换个 AI 工具起服务、或并行会话（另一个工具
    先导出过一份）都不会让它失效。实测过：Claude Code 会话起的面板，
    端的是早先 Antigravity 会话导出的快照，整页命令用了那份快照所对应的工具档。
    （当时那两档的差别是斜杠；2026-10-13 起免斜杠只剩 Codex 一家，所以这一句
    只讲「按起服务的环境盖」，不再断言具体是哪种字形——那一层会再变。）
    与 with_stale_flag 同款：只改这一次响应，不动盘上的 data.json。
    纯函数，解析失败原样端出去。
    """
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return raw
    d["detectedTool"] = tool
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def with_stale_flag(raw: bytes, changed: list) -> bytes:
    """把「代码比进程新」的文件名单塞进这一次的快照响应。

    纯函数，好测。解析失败就原样端出去——一个提醒不值得把整页搞挂。
    """
    if not changed:
        return raw
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return raw
    d["staleCode"] = sorted(changed)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def _export_now() -> None:
    """真正跑导出。调用方必须已持有 `_REGEN_LOCK`。

    **子进程跑，不是同进程 import。** 这一条是被同一个坑绊倒两次之后改的。

    原来是 `ex.main([...])`，用的是**服务器启动那一刻**的 `export_web_data`。
    改了导出器而没重启服务，后果不是「新字段不生效」这么轻——它会在下一次
    自愈重导时**把带新字段的 data.json 覆盖回旧格式**，症状看起来像「前端没渲染」。

    - 第一次（2026-08-13 上午）：新加的 `outcomeStats` 手动导出后存在、页面查无此块。
      当时的处理是在这里写一段警告：「改完导出器要重启服务」。
    - 第二次（2026-08-13 晚，全面检查第 5 轮）：服务进程启动于 15:50，
      而 `export_web_data.py` 21:05 改过、`tracker.py` 21:11 改过——**进程比代码老
      五个多小时**，用户只要在面板上点一下按钮，那半天的改动就会被旧代码抹掉。

    **警告不是机制。** 这个仓库的常态是 AI 频繁改代码、用户长时间开着面板，
    「记得重启」这种要求注定失效。子进程每次都加载盘上最新的代码，**导出这一路**
    的问题从根上没了。

    ⚠️ **但只有这一路。** 当天第 10 轮收口时又撞了第三次：`tracker.py` 刚换成
    原子写，而跑着的服务里仍是启动那一刻 import 的裸 `write_text`——**写盘那条路
    还是同进程的**（`apply_status` → `tracker.set_status` → `_cli.atomic_write`
    全是启动时绑定的对象）。第 5 轮写在这里的「问题从根上没了」是句说过头的话，
    留着它会让下一个人以为整件事已经关掉。
    真正兜住另一半的是 `warn_if_code_changed()`：发现代码比进程新就在终端喊一声。

    代价是每次导出多一次解释器启动（~150ms）。导出本身要遍历上千个岗和几百个
    投递目录，本来就是几百毫秒量级，这点开销不值得为它保留一个会静默毁数据的设计。

    **参数要显式传。** `--user` 钉住谁，导出就必须导谁——否则页面标着 bob、
    数据是 alice 的。（同进程时代还有个理由：服务器的 `--port` 会被导出器的
    解析器当成未知参数直接 `SystemExit(2)`；走子进程之后这条不再适用，
    但显式传参本身仍然是对的。）

    导出器会打印一堆进度，这里吞掉——服务器日志里刷七行「下一步：…」是噪音。
    """
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "export_web_data.py"),
         "--user", active_user()],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )
    if proc.returncode != 0:
        # 抛出去，让调用方那几处 `except Exception` 把真因写进服务器日志。
        # **不要静默吞掉**——静默降级正是这一整类 bug 的成因。
        raise RuntimeError(
            f"导出器退出码 {proc.returncode}："
            f"{(proc.stderr or proc.stdout or '').strip()[-400:]}")


def regenerate() -> None:
    """重新导出 data.json，让刷新之后看到的就是盘上的真相。"""
    with _REGEN_LOCK:
        _export_now()


def sources_mtime(user: str) -> float:
    """`data.json` 的全部上游里最新的那个修改时间。

    投递目录必须**递归**遍历：目录自身的 mtime 只在增删文件时变，改 `evaluation.md`
    的内容不会动它——只看目录 mtime 会漏掉「深评改了分数」这种最常见的情况。
    """
    newest = 0.0
    base = ROOT / "users" / user
    for p in (ROOT / ".active_user", seen_path(user),
              # 2026-08-19 拆出去的三个新写入源。漏掉的后果是**陈旧页永远端下去**：
              # 点按钮后的兜底重导靠这里判断「data.json 旧没旧」，而按钮现在写的
              # 是这几个文件——某次写后重导恰好失败，之后每次刷新都判「不旧」，
              # 面板就停在写之前的样子。
              seen_path(user).with_name("user_state.json"),
              seen_path(user).with_name("portals.json"),
              seen_path(user).with_name("prefs.json"),
              # 解封是在面板上点的，写的是这个文件——不盯它，点完页面不刷新，
              # 告警条会一直挂着，用户以为没解成又去点一次。
              seen_path(user).with_name("portal_budget.json"),
              # 在线简历上次刷新（`/api/resume-refreshed` 写的）。**和上面那几个
              # 同一条理由**：它是导出的上游（`portal_rows` 的 `resumeStale`），
              # 漏掉就是「改了不刷新」。
              # 实测 2026-08-24 当场撞上：在命令行清空了这个文件，而 `data.json`
              # 里那个天数原样留着，面板显示「今天刷过」而盘上一条记录都没有 ——
              # 新加一个写入源却忘了把它挂进这张单子，是这一行存在的全部理由。
              seen_path(user).with_name("resume_refresh.json"),
              base / "job_search_tracker.csv", base / "profile" / "candidate.md",
              # 导出还读这几样，漏了它们就等于说「刷新页面即最新」是假的：
              # 重编了主简历 PDF、`/job-resume` 出了新审阅报告、`/job-scrape`
              # 抓回新的 JD 详情——页面全都不动，直到别的东西碰巧变了才刷。
              base / "resume" / "main.typ", base / "resume" / "main.pdf"):
        if p.is_file():
            newest = max(newest, p.stat().st_mtime)
    for d in (base / "documents" / "applications",
              base / "job_scraper" / "details",
              base / "reports"):
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    newest = max(newest, p.stat().st_mtime)
    return newest


def needs_reexport(data: Path, user: str, newest_source: float) -> bool:
    """这份 `data.json` 还能直接端出去吗？抽成纯函数，因为它有两条判据，
    而只写对一条的后果**在页面上看不出来**。

    要验的是**三件事**：

    1. **它是不是这个人的。** 只比时间戳会漏掉最刺眼的一种——盘上那份是别人的。
       冒烟实测 `serve.py --user 李四` 端出的是**另一个用户**的整份职位数据：
       那份 data.json 比李四的上游文件新，判定「不过期」，于是原样端出去。时间对、人不对，
       页面上没有任何异常提示。
       （只验时效不验归属，是多用户共享一份派生快照时的典型陷阱。）
    2. **它够不够新。** 严格早于才算新鲜：mtime 撞在同一刻时宁可多导一次，
       也不要卡在过期状态上。导完必然严格新于上游，不会反复触发。
    3. **它是不是今天导的。** 导出器往 `data.json` 里写的有一批**相对今天**的
       句子：逐岗的「今天投的」「昨天投的（1 天前）」「已经 11 天没动静」
       （`build_dashboard.job_next_step`）、封控的「今晚 23:14 自动恢复」
       。上游一夜没动过，前两条判据就都说「还新鲜」，
       于是第二天早上页面把昨天投的岗称作「今天投的」，刚过静默线的岗还在说
       「满 10 天还没动静可以催一次」——那件事昨晚就发生了。
       这些句子以前是静态的，看不出旧；现在它们直接断言日期，所以**跨一天就得重导**。
       代价是每天第一次打开多导一次，几百毫秒。
    > 曾经有第 4 条「它说的『封着』还成立吗」，判法在 `block_claim_is_stale`。
    > 它存在的全部理由是**冷却会悄悄到点**：解封那一刻一个字节也不写，
    > 上面三条一条也不响。2026-08-26 本人裁定封控不再自动到期
    > （「只有用户手动点继续 cli 后，才能继续 cli」），于是**每一次状态变化
    > 都伴随一次写盘**——解封写的正是 `portal_budget.json`，而它早就在
    > `sources_mtime` 的名单里（当初为「面板上点解封」加的）。第 2 条全覆盖了，
    > 第 4 条连同它的判据函数一起删掉。

    读不出归属（文件缺失、半截 JSON、没有 activeUser 字段）一律当成要重导。
    """
    if not data.is_file():
        return True
    try:
        payload = json.loads(data.read_text(encoding="utf-8"))
    except Exception:                         # noqa: BLE001
        return True
    if payload.get("activeUser", "") != user:
        return True
    stat = data.stat()
    if date.fromtimestamp(stat.st_mtime) != date.today():
        return True
    return not (newest_source < stat.st_mtime)


def _owner_of(data: Path) -> str:
    """`data.json` 是谁的。读不出来返回空串（当成「不知道」，不拦）。

    `data.json` 是一份**共用**的派生快照，而它归谁只由里面的 `activeUser` 说了算。
    """
    try:
        return json.loads(data.read_text(encoding="utf-8")).get("activeUser", "")
    except Exception:                     # noqa: BLE001 - 读不出就不拦，交给别处报
        return ""


def refresh_if_stale() -> bool:
    """上游比 `data.json` 新、或它根本是别人的，就先重新导出。返回是否真的导出了。

    **为什么放在这里而不是写进各个工作流**：面板读的是 `data.json` 这份派生快照，
    而 `/job-apply`、`/job-rank`、`/job-outcome`、`/job-scrape` 改的都是上游。靠十几个工作流各自
    记得补一句「跑导出」，只要有一个忘了，用户看到的就是旧数字却毫无提示——
    实测就这么翻过车：深评把 83 改成 82 写回了 `seen_jobs.json`，面板还显示 83。
    判定放在数据出口这一个点上，谁改的、改了什么都不必知道。
    """
    warn_if_code_changed()      # 代码比进程新就喊一声（见它的说明：注释不是机制）
    data = ROOT / "web" / "public" / "data.json"
    try:
        user = active_user()
    except NoActiveUser:
        return False                      # 没有活动用户：交给页面自己报，别让请求崩掉
    with _REGEN_LOCK:
        if not needs_reexport(data, user, sources_mtime(user)):
            return False
        try:
            _export_now()
            sys.stderr.write("  数据有更新，已重新导出 data.json\n")
            return True
        except Exception as exc:          # noqa: BLE001 - 导出失败不该让面板打不开
            # 但也**不能静默**：静默降级正是这个 bug 本身的成因。旧数据照常给出去，
            # 同时在服务器日志里说清楚，用户至少知道自己看的可能不是最新的。
            # 措辞分两种：有旧的 data.json 才谈得上「显示的是旧数据」；
            # 一次都没导出过时页面根本没有数据可显示，那句话是假的。
            what = "页面显示的是旧数据" if data.is_file() else "页面还没有数据可显示"
            # **类名不能省。** `KeyError()`、裸 `RuntimeError()` 的 `str()` 是空串，
            # 只印 `{exc}` 那这行就停在冒号上，一个字的原因都没有 ——
            # 而 `main()` 下面还写着「原因在上面那行」，指向一行空话。
            why = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            sys.stderr.write(f"  ⚠ 自动导出失败，{what}：{why}\n")
            return False


class Handler(BaseHTTPRequestHandler):
    server_version = "jobsearch-local"

    def log_message(self, fmt, *args):        # noqa: D102 - 默认那份太吵
        if "POST" in (args[0] if args else ""):
            sys.stderr.write("  %s\n" % (fmt % args))

    # ---------- 工具 ----------

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # 数据会被写操作改变，别让浏览器缓存出一个过期的视图
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   MIME[".json"])

    def _same_origin(self) -> bool:
        """写操作的来源校验。

        Origin 缺失也放行：`fetch` 同源请求本来就可能不带它，而跨站 POST 一定带。
        真正兜底的是 token。
        """
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = urlparse(origin).hostname
        return host in ("127.0.0.1", "localhost")

    # ---------- 路由 ----------

    def do_GET(self) -> None:                 # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_index()
        if path == "/data.json":
            refresh_if_stale()            # 命令行改过数据 → 刷新页面就能看到，不用记着跑导出
            f = ROOT / "web" / "public" / "data.json"
            # **重导失败时，别把上一个用户的数据发出去。**
            # `main()` 起服务前查过一次归属，但那只挡得住启动那一刻；
            # 用户在服务开着的时候跑 `/job-user 李四`，`needs_reexport` 认出
            # 归属不符、去重导、失败（李四还没有 seen_jobs.json），
            # 而 `refresh_if_stale` 只在 stderr 留一行就返回 False ——
            # 这里照旧把**张三**的岗位、薪资、投递记录发给标着「李四」的页面，
            # 接着每个状态按钮都会用张三的职位 id 往李四的台账里写。
            owner = _owner_of(f)
            if owner and owner != active_user():
                return self._send(
                    409,
                    json.dumps({"error": f"这份数据是「{owner}」的，而现在的用户是"
                                         f"「{active_user()}」——重新导出没成功。"
                                         f"到终端跑 python tools/export_web_data.py "
                                         f"看它报什么错，修好再刷新"},
                               ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")
            # 「代码比进程新」的提醒要跟着数据走到**页面**上。终端那行警告
            # nohup 一包就没人看见——实测这一天三次全靠事后翻日志才发现。
            # 只改这一次响应，不动盘上的 data.json（那是导出器的产物）。
            stale = warn_if_code_changed()
            if f.is_file():
                # detectedTool 同理要按**当前起服务的环境**盖写：盘上那份可能是
                # 别的工具 / 并行会话早先导出的（见 with_detected_tool 的说明）。
                raw = with_detected_tool(f.read_bytes(), _cli.detect_code_tool())
                if stale:
                    raw = with_stale_flag(raw, stale)
                return self._send(200, raw, "application/json; charset=utf-8")
            return self._serve_file(f)
        if path.startswith("/pdf/"):
            # PDF 与 data.json 同理，从 web/public 取——导出器每次把最新 PDF 写到
            # 那里，而 dist/ 里的是**上次 npm run build 时**拷的快照。从 dist 取的
            # 后果实测两种都发生了：新导出的 PDF 404（dist 里没有）、重编过的 PDF
            # 端出旧字节（dist 里是旧版，且 pdfStale 检测不到服务层这份旧）。
            pub = (ROOT / "web" / "public").resolve()
            target = (pub / path.lstrip("/")).resolve()
            if not target.is_relative_to(pub):
                return self._json(403, {"error": "这个路径不在页面目录里，不给看（安全限制）"})
            return self._serve_file(target)
        # 其余按静态资源处理，限制在 dist 目录内
        #
        # ⚠️ 用 `is_relative_to`，**不要用 `str().startswith()`**。
        # 前缀匹配挡不住同级目录：`DIST` 是 `web/dist` 时，
        # `/../dist-evil/secret.txt` 解析成 `web/dist-evil/secret.txt`，
        # 它的字符串确实以 `web/dist` 开头——实测放行。要的是「在这个目录**里**」，
        # 而不是「路径字符串以它开头」，两者只在同级同前缀时才分岔，
        # 而那正是穿越要利用的那一档。
        target = (DIST / path.lstrip("/")).resolve()
        if not target.is_relative_to(DIST.resolve()):
            return self._json(403, {"error": "这个路径不在页面目录里，不给看（安全限制）"})
        return self._serve_file(target)

    def do_POST(self) -> None:                # noqa: N802
        path = urlparse(self.path).path
        # **先把请求体收干净，再做任何检查。**
        #
        # 原来 Origin 校验排在读 body 之前：不合格就直接 403 并关连接，而客户端可能
        # 还在写 body。TCP 那一侧的后果是发 RST——**客户端拿到的不是 403，是一个
        # 连接被重置的异常**。于是这条本该给出清楚提示的安全拒绝，在页面上表现为
        # 「网络错误」，用户完全不知道发生了什么。
        #
        # 这也正是 `test_serve_writeback` 里那条 Origin 用例**间歇性失败**的原因
        # （全量跑实测 2/7 红，单跑必绿）：能不能在服务端关连接之前把 body 发完，
        # 取决于调度。另外两条拒绝（无 token / 错 token）不抖，因为它们本来就发生在
        # 读完 body 之后——这个差别就是病灶的指纹。
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
        except (ValueError, OSError):
            return self._json(400, {"error": "这次请求的内容发坏了——刷新一下页面再试"})
        if not self._same_origin():
            return self._json(403, {"error": "这个请求不是本页发出的，已拒绝（安全限制）"})
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "这次请求的内容发坏了——刷新一下页面再试"})
        # **定时安全比较。** 普通 `!=` 一撞上不同的字符就返回，响应时间随
        # 「猜对了几个前缀字符」变化。跨站页面 POST 不到（Origin 挡着），但
        # **它读不到响应不等于量不到耗时**——no-cors 请求的时长照样可测。
        # token 是这条写盘链唯一的凭据，`secrets` 本来就已经 import 了，
        # 换成 compare_digest 是零成本。
        # 先转成 str：compare_digest 收到非字符串会抛 TypeError，
        # 那会变成 500（把内部异常端给用户），而这里该是干脆的 403。
        if not secrets.compare_digest(str(body.get("token") or ""), TOKEN):
            return self._json(403, {"error": "这个页面的通行凭据过期了——刷新一下再试"})

        job_id = str(body.get("id") or "")
        # 渠道开关不是「针对某个职位」的操作，它没有 id。其余每一单都必须有。
        if not job_id and path not in ("/api/portals", "/api/prefs", "/api/unblock",
                                       "/api/hr-answer", "/api/resume-refreshed"):
            return self._json(400, {"error": "这次请求没说是哪个职位——刷新一下页面再试"})
        try:
            # 读-改-写整段串行化，见 `_WRITE_LOCK` 的说明。
            with _WRITE_LOCK:
                if path == "/api/skip":
                    result = apply_skip(job_id, str(body.get("reason") or ""))
                elif path == "/api/expire":
                    result = apply_expire(job_id)
                elif path == "/api/restore":
                    result = apply_restore(job_id)
                elif path == "/api/status":
                    result = apply_status(job_id, str(body.get("status") or ""),
                                          (body.get("reason") or "").strip() or None)
                elif path == "/api/prefs":
                    # 与渠道开关同理：读-改-写整份文件，必须在同一把锁里。
                    result = ex.set_pref(active_user(),
                                         str(body.get("name") or ""),
                                         bool(body.get("enabled")))
                elif path == "/api/portals":
                    # 渠道开关。与上面那几条一样是**读-改-写整份文件**，
                    # 所以必须待在同一把锁里——两个标签页同时勾，后写的会盖掉先写的。
                    result = ex.set_portal(active_user(),
                                           str(body.get("name") or ""),
                                           bool(body.get("enabled")))
                elif path == "/api/unblock":
                    # 解封。**必须是人点的**——撞风控多半要用户自己去过一次验证，
                    # 只有他知道过完没有。工具自动解冷却等于把刚学到的教训丢掉。
                    result = apply_unblock(str(body.get("name") or ""))
                elif path == "/api/hr-answer":
                    # 改一条 HR 常问的答案。**仍然是「改一个字段」那条路**
                    # （本文件的边界：不接大模型，只落一次编辑），
                    # 和渠道开关一样是读-改-写整份文件，所以在同一把锁里。
                    result = ex.set_hr_answer(active_user(),
                                              str(body.get("q") or ""),
                                              str(body.get("a") or ""))
                elif path == "/api/resume-refreshed":
                    # 记一笔「今天在这家刷了在线简历」。**这不是针对某个职位的**，
                    # 所以下面那条「必须有 job_id」的检查里放行了它。
                    # `day` 传空串是撤销（标错了要有退路，否则没人敢标第一下）。
                    result = ex.set_resume_refreshed(
                        active_user(), str(body.get("name") or ""),
                        "" if body.get("day") == "" else None)
                elif path == "/api/hr-viewed":
                    # `viewed` 三态：true / false / null（撤销）。**不要写成
                    # `bool(body.get("viewed"))`** —— 那会把「撤销」变成「没看过」，
                    # 而这两件事对诊断的意义正好相反（一个是没数据，一个是数据）。
                    _v = body.get("viewed")
                    result = apply_hr_viewed(job_id, None if _v is None else bool(_v))
                elif path == "/api/status/undo":
                    # `prev` 允许是 null——那表示「那一行是页面刚建的」，撤销即删行。
                    # 所以不能写成 `str(body.get("prev") or "")`：那会把 null 变成 ""，
                    # 而 "" 在台账里是一个合法状态，撤销就变成了「把状态清空」。
                    result = undo_status(job_id, body.get("prev"))
                else:
                    return self._json(404, {"error": "这个页面比正在跑的服务新——"
                                              "到终端按 Ctrl+C 停掉，"
                                              "再跑一次 python tools/serve.py"})
                if result.get("ok"):
                    # 写盘已经成功——重导出失败**不能把整单报成失败**：页面会回滚
                    # 乐观更新并提示「没写进去」，而盘上其实已经改了，产生
                    # 「页面一个样、盘上另一个样」的鬼状态。导出挂了就下次
                    # refresh_if_stale 再试，这单照样算成。
                    try:
                        regenerate()
                    except Exception as exc:  # noqa: BLE001
                        sys.stderr.write(f"  警告: 已写盘，但重导出失败"
                                         f"（{type(exc).__name__}: {exc}）——"
                                         f"刷新页面时会自动重试\n")
                    # 开关类端点没有职位名，打的是「哪个开关 → 开/关」
                    what = (result.get("title") or result.get("company")
                            or (f"{result.get('name')} → "
                                f"{'开' if result.get('enabled') else '关'}"
                                if "enabled" in result else ""))
                    sys.stderr.write(f"  {_LOG_VERB.get(path, path)}：{what}" + chr(10))
            return self._json(200 if result.get("ok") else 404, result)
        except NoActiveUser as exc:
            # 单独一支，不走下面那个通用兜底：那句话会把类名印给用户
            # （`AGENTS.md`「给用户看的措辞」禁的就是这类未解释的英文码）。
            # 这也不是「出错」——是这台机器上还没有资料，说清下一步就够了。
            return self._json(409, {"ok": False, "error": str(exc)})
        except Exception as exc:              # noqa: BLE001 - 要把真因回给页面
            return self._json(500, {"ok": False, "error": f"服务这边出错了：{type(exc).__name__}: {exc}。"
                        f"再试一次；还是不行就重启 serve.py"})

    # ---------- 静态 ----------

    def _serve_index(self) -> None:
        idx = DIST / "index.html"
        if not idx.is_file():
            return self._send(503, (
                "<meta charset='utf-8'><h1>页面还没构建</h1>"
                "<p>先跑 <code>cd web &amp;&amp; npm install &amp;&amp; npm run build"
                "</code>，再重启这个服务。</p>"
            ).encode("utf-8"), MIME[".html"])
        html = idx.read_text(encoding="utf-8")
        # token 注入到页面里。写操作要带上它，跨站脚本拿不到（它读不到本页 DOM）。
        #
        # **注在 `<head>` 开头**，不要注在 `<div id="root">` 后面。后者能工作只是因为
        # Vite 的 app 脚本是 `type="module"`、默认 defer，要等文档解析完才跑——
        # 一个靠 defer 语义兜住的先后关系，构建方式一改就会**静默**失效：
        # 页面读不到 token → `hasServer()` 判否 → 退回静态模式 → 点「不投」只存浏览器，
        # 而界面还照常显示成功。宁可显式。
        tag = f"<script>window.__API_TOKEN__={json.dumps(TOKEN)};</script>"
        injected = re.sub(r"(<head[^>]*>)", r"\1" + tag, html, count=1)
        if injected == html:
            # 注不进去就别装作没事——静默降级正是这里最不该有的行为
            return self._send(500, (
                "<meta charset='utf-8'><h1>页面注入失败</h1>"
                "<p><code>web/dist/index.html</code> 里找不到 <code>&lt;head&gt;</code>，"
                "token 注不进去。这样页面会以为没有服务、把「不投」只存进浏览器。</p>"
            ).encode("utf-8"), MIME[".html"])
        return self._send(200, injected.encode("utf-8"), MIME[".html"])

    def _serve_file(self, target: Path) -> None:
        if not target.is_file():
            return self._json(404, {"error": f"没有这个文件：{target.name}——页面可能没构建全，"
                                     f"跑一次 cd web && npm install && npm run build"})
        ctype = MIME.get(target.suffix, "application/octet-stream")
        return self._send(200, target.read_bytes(), ctype)


class _Server(ThreadingHTTPServer):
    """只为改一个类属性：**Windows 上不许 `SO_REUSEADDR`。**

    POSIX 上 `SO_REUSEADDR` 的意思是「TIME_WAIT 里的旧连接不挡新监听」——
    Ctrl+C 之后能立刻重起，是好事，所以那边保持 stdlib 的默认（True）。

    **Windows 上它的意思完全不同：抢占。** 第二个进程照样 bind 成功，
    两个都在监听，而连接归谁由内核决定 —— 实测归**先起的那个**。
    """

    allow_reuse_address = os.name != "nt"


def _stop_hint(port: int) -> str:
    """怎么停掉那个已经在跑的服务。**给命令，不给「去找那个终端」。**"""
    if os.name == "nt":
        return (f"  netstat -ano | findstr :{port}   ← 最后一列是进程号\n"
                f"  taskkill /PID <进程号> /F")
    return f"  kill $(lsof -ti tcp:{port})"


def probe_running(port: int, timeout: float = 1.5) -> dict | None:
    """这个端口上已经有服务了吗？有就返回它的自述，没有返回 None。

    返回 `{"ours": bool, "user": str, "stale": [文件名]}`。
    `ours` 靠 `/data.json` 里有没有 `activeUser` 认 —— 别的程序占着这个端口时
    该说「换个端口」，不是「停掉旧的总览」。
    """
    import socket
    import urllib.error
    import urllib.request

    with socket.socket() as sk:
        sk.settimeout(timeout)
        if sk.connect_ex(("127.0.0.1", port)) != 0:
            return None
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/data.json", timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return {"ours": False, "user": "", "stale": []}
    if not isinstance(d, dict) or "activeUser" not in d:
        return {"ours": False, "user": "", "stale": []}
    return {"ours": True, "user": d.get("activeUser", ""),
            "stale": d.get("staleCode") or []}


def report_running(info: dict, port: int, url: str) -> int:
    """已经有东西占着端口时说什么、退出码给多少。**纯函数，好测。**

    三种情况三条路，别混成一句「端口被占用」：

    - **别的程序占着** —— 停它没道理，换端口。
    - **我们自己在跑、代码是新的** —— 那就是用户想要的那一页，打开它，`0` 退出。
      再起一个只会在 Windows 上多一个绑同一端口的幽灵进程。
    - **我们自己在跑、但它是改代码之前起的** —— 这正是页面上那条
      「还在用旧代码跑」的来源。给停它的命令，`1` 退出。
    """
    if not info["ours"]:
        print(f"{port} 端口被别的程序占着 —— 换一个：", file=sys.stderr)
        print(f"  python tools/serve.py --port {port + 1}", file=sys.stderr)
        return 1
    who = f"（{info['user']}）" if info.get("user") else ""
    if not info["stale"]:
        print(f"总览已经在跑了{who}：{url}")
        print("  不重复起 —— 直接打开上面这个")
        return 0
    print(f"总览已经在跑{who}，但它是在你改代码之前起的 —— "
          f"页面上点按钮记的状态可能不准。", file=sys.stderr)
    print("先停掉它：", file=sys.stderr)
    print(_stop_hint(port), file=sys.stderr)
    print("停掉之后再跑一次 python tools/serve.py", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    # 从前这里不解析参数：`serve.py --help` 会**直接起服务器卡住**，
    # `--user bob` 被静默吞掉、照样端出活动用户的面板。
    global _PINNED_USER, PORT
    args = _cli.no_args(
        argv,
        description=f"本地起一个求职总览页（默认 127.0.0.1:{PORT}，只监听本机）",
        extra=lambda ap: (
            ap.add_argument("--user", metavar="用户名",
                            help="服务哪个用户的数据，默认读 .active_user（不改它）"),
            ap.add_argument("--port", type=int, default=PORT,
                            help=f"换个端口（默认 {PORT}，也可用环境变量 JOBS_PORT）")))
    if args.user:
        u = args.user.strip()
        if not (ROOT / "users" / u).is_dir():
            print(f"没有叫「{u}」的用户。" +
                  (_cli.user_list_line(ROOT) if _cli.all_users(ROOT)
                   else "先跑 /job-setup"), file=sys.stderr)
            return 2
        _PINNED_USER = u
    PORT = args.port

    # **先看这个端口上是不是已经有一个在跑。** 放在这儿（导出之前）是因为
    # 下面 `refresh_if_stale()` 要重导两千多个岗，白跑一趟没有意义。
    #
    # 这一段是用户 2026-08-24 那句「为什么一直出现『还在用旧代码跑』」的根因：
    # `ThreadingHTTPServer.allow_reuse_address` 是 stdlib 默认的 True，而
    # **Windows 上它的语义是抢占** —— 第二个进程 bind 成功、打印「求职总览：…」、
    # 打开浏览器，可连接仍然归先起的那个。于是用户看到的是「刚起好」加
    # 「还在用旧代码跑」，照页面说的按 Ctrl+C，杀掉的是**刚起的这个新的**。
    # 实测：`ThreadingHTTPServer(("127.0.0.1", 29029), ...)` 在端口已被自己
    # 占用时不抛异常，直接绑上。
    _running = probe_running(PORT)
    if _running is not None:
        _code = report_running(_running, PORT, f"http://127.0.0.1:{PORT}/")
        if _code == 0 and os.environ.get("JOBS_NO_BROWSER") != "1":
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return _code

    try:
        user = active_user()
    except NoActiveUser as exc:
        # 命令行这一侧照旧以非零退出——退出码归 main()，不归请求处理器。
        print(str(exc), file=sys.stderr)
        return 1
    if not (DIST / "index.html").is_file():
        # `npm install` 不能省。这条原来只写 `npm run build`，而**第一次用的人根本
        # 没装过依赖**，照做只会撞一个 vite 找不到的错。README、SETUP、doctor、
        # README、SETUP、doctor 三处说的都是完整那条，唯独这里漏了半截。
        print("web/dist 不存在 —— 先跑一次 cd web && npm install && npm run build",
              file=sys.stderr)
        print("  （只需要一次；之后改了数据跑 /job-dashboard 或直接起这个服务就行）",
              file=sys.stderr)
        return 1
    if not seen_path(user).is_file():
        # **全新用户建完档就来看总览，是最常见的一条路**（AGENTS.md 让助手主动起
        # 这个服务）。此前这里没有前置检查，于是一路走到下面的导出失败分支，端给
        # 用户的是「RuntimeError: 导出器退出码 1：…」加一句「手动跑一次导出器看它
        # 报什么错」——那个错就印在上一行，而且它根本不是故障，是流程的下一步。
        # 上面 `web/dist` 那一条早就是这个形状了（一句人话 + 一条命令），照它写。
        # 尾巴是这条路自己的（抓完回来打开总览），句子走正本。
        print(_cli.no_store(seen_path(user),
                            then="/job-scrape 抓一批，抓完再打开总览"),
              file=sys.stderr)
        return 1
    data = ROOT / "web" / "public" / "data.json"
    refresh_if_stale()                    # 不存在或过期都在这里补上，不必先手动跑导出
    if not data.is_file():
        # 原因已经由 refresh_if_stale 打在上面一行了。**不要再让用户「跑一次导出器
        # 看它报什么错」**——那等于让他重做一遍刚看过的事。
        print("总览页的数据没能生成 —— 原因在上面那行", file=sys.stderr)
        return 1

    # **文件在 ≠ 这份是你的。** `data.json` 是一份**共用**的派生快照，
    # 而 `refresh_if_stale()` 导出失败时只在 stderr 留一行就返回 ——
    # 下面这几行照样起服务，把**上一个用户**的岗位、薪资、投递记录发出去，
    # 页头还印着当前用户的名字。更糟的是页面上每个状态按钮都会写回：
    # 写进当前用户的台账，键却是上一个用户的职位 id。
    #
    # `needs_reexport` 的说明里把「别人的快照」列为它要挡的头一件事，
    # 而那道判据只管**要不要重导**，不管**重导失败之后还发不发**。
    try:
        belongs_to = json.loads(data.read_text(encoding="utf-8")).get("activeUser", "")
    except Exception as exc:              # noqa: BLE001
        print(f"总览页的数据读不出来（{type(exc).__name__}）—— "
              f"跑一次 python tools/export_web_data.py 看它报什么错", file=sys.stderr)
        return 1
    if belongs_to and belongs_to != user:
        print(f"总览页现有的数据是「{belongs_to}」的，重新导出又没成功 —— "
              f"不发别人的数据。先跑 python tools/export_web_data.py 看它报什么错，"
              f"修好再起服务", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{PORT}/"
    n = len(json.loads(data.read_text(encoding="utf-8")).get("jobs", []))
    print(f"求职总览：{url}")
    print(f"  用户：{user} · 职位 {n} 个")
    # 措辞跟页脚保持一字不差。原来这里写「「不投 / 放回」会直接写进 seen_jobs.json」，
    # 两处都不对：**漏了后来加的状态按钮**（我投了 / 约面了 / 挂了…也是直接落盘的），
    # 而 `seen_jobs.json` 是仓库内部的文件名——用户不该为了看懂一句提示先认识目录结构。
    # 页面上说的是「存进本机数据」，同一件事就得用同一个说法。
    print("  页面上的「我投了 / 约面了 / 不投」点了就存进本机数据，不用再回命令行")
    print("  只监听 127.0.0.1，别的机器连不上；Ctrl+C 停止")

    srv = _Server(("127.0.0.1", PORT), Handler)
    if os.environ.get("JOBS_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
