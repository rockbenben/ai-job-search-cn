#!/usr/bin/env python3
"""进仓库先跑这个：查环境、查进度、告诉你下一步做什么。

设计约束（改这个文件前先读）：

1. **只用标准库，不 import 本仓库的任何模块。** 它要在「什么都还没配好」的状态下能跑，
   包括 `.active_user` 不存在、`users/` 为空、profile 还是占位符的时候。任何 import
   失败都会让新用户在第一步就撞墙——而这正是它要消除的体验。
2. **绝不修改任何东西。** 只读、只打印。用户第一次跑一个陌生仓库的脚本时，
   它不该动他的文件。
3. **缺依赖不是错误，是状态。** 除了「连仓库都不对」以外一律 exit 0：缺 Typst 只是
   还不能出 PDF，不是故障。exit 1 只留给「你不在这个仓库里」。
4. **最后一定要给出「下一步做什么」，且只给一条。** 给三条并列选项等于没给。

用法：  python tools/doctor.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 管道/重定向时把输出定到 UTF-8。Windows 上 Python 只在 stdout 是真终端时才走
# WriteConsoleW；被管道接走就回落到 cp936(GBK)，而 Git Bash / VS Code / Windows
# Terminal 都按 UTF-8 解 —— 用户看到一屏乱码，引导等于失效。只改非 tty 那条路：
# 真终端本来就是对的，强行改反而会让代码页 936 的传统 cmd.exe 开始乱码。
# 与 tools/_cli.py 的 force_utf8_output() 同一份逻辑；这里内联是因为本文件
# 顶上那条约束：**不 import 本仓库的任何模块**。
for _s in (sys.stdout, sys.stderr):
    try:
        if _s is not None and hasattr(_s, "reconfigure") and not _s.isatty():
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


ROOT = Path(__file__).resolve().parent.parent


def _valid_user_name(name: str) -> bool:
    """`_cli.valid_user_name` 的内联副本：本文件不许 import 仓库模块。

    名字错成 `..` 或绝对路径时，`ROOT / "users" / name` 会整个跳出 users/；
    自检不能把仓库根当成一个用户的工作区。
    """
    name = (name or "").strip()
    if not name or name in (".", "..") or not name.strip("."):
        return False
    # Windows 把 `alice.` 归一成 `alice`，把 `...` 归一成 `users/` 本身 ——
    # 后者会让自检把整个用户目录当成一个人的工作区。
    if name.endswith("."):
        return False
    if name != Path(name).name:
        return False
    if any(c in '/\\:*?"<>|' for c in name):
        return False
    if any(ord(c) < 32 for c in name):
        return False
    reserved = ({"CON", "PRN", "AUX", "NUL"}
                | {f"COM{i}" for i in range(1, 10)}
                | {f"LPT{i}" for i in range(1, 10)})
    if name.split(".")[0].upper() in reserved:
        return False
    return True


def _user_dir_inside(name: str) -> bool:
    """名字解析后必须仍是 `users/` 的直接子目录（防 Windows 别名与符号链接）。"""
    try:
        root = (ROOT / "users").resolve()
        return (root / name).resolve().parent == root
    except OSError:
        return False


def n_processed(seen: dict) -> int:
    """流水线第 2 格「打过分」的计数：**处理完的**，不是**有分数的**。

    硬性条件没过的岗按 `apply.md` 规定 `rank_score: null`——它已经结案、永远不会
    再有分数。可原来直接数「有分数的」，把这批算成了没处理：面板显示 268 → 209，
    看起来 59 个待办，实际只有 29 个真没动过，另外 29 个早就办完了。
    **已完成的工作被渲染成积压**，队列显得比实际长一倍。

    单独成函数是为了测试能钉住它——测试里自己重算一遍是假绿，改坏这里它照样过。
    """
    return sum(1 for e in seen.values()
               if e.get("rank_score") is not None
               or (e.get("status") or "") not in ("new", "expired"))

def n_waiting(seen: dict) -> int:
    """还在**排队等着评**的岗。`n_processed` 的补集里，只有这一半是待办。

    「已抓 2638 · 已评 2450」并排印着，中间那 188 从来没被点名 —— 读的人得
    自己减，减完还不知道那是不是待办。**而它不全是待办**：实测活动用户
    2026-08-23，188 里 182 个 `status: new`（真在等着评），另外 6 个是
    **已下线且从没评过**的死岗 —— 印 188 就是把 6 个死岗说成积压。

    为什么值得印：`workflows/INDEX.md` 索引里 `/job-scrape` 的承诺是「抓完直接排出可以投的，
    **不停在待评**」，
    所以一个长期存在的待评池本身就说明那条自动衔接断过一次。而同一时刻面板
    正在说库存见底（行业对口只剩 49、备好没发的 62）—— 182 个没评的岗里
    可能就有能投的，它们却在任何一处都不出现。

    与 `n_processed` 严格互补的那一半是 `len(seen) - n_processed(seen)`；
    这里**故意更窄**，只数真待办的。两者的差就是那批死岗。
    """
    return sum(1 for e in seen.values()
               if isinstance(e, dict)
               and (e.get("status") or "") == "new"
               and e.get("rank_score") is None)


#: 在线简历多久没刷新就该说一句。**正本是 `export_web_data.RESUME_STALE_DAYS`**，
#: 这里只能重抄一遍（本文件不许 import 仓库内模块），两边相等由守卫钉住。
#: 出处是 `job-resume.md` 2.6 那句「**两周**没登录的简历，HR 翻不到第几页就停了」。
RESUME_STALE_DAYS = 14


def resume_refresh_note(udir, on: dict, today=None) -> str:
    """勾着的渠道里，在线简历最久没刷的那家。没有要说的就返回空串。

    ## 为什么这一条要出现在自检里

    `job-resume.md` 2.6 把刷新标成那张表里**唯一一件每天都要做**的事，理由是
    国内平台的简历库基本按「最近活跃」排序，而 **HR 主动搜人是唯一一条不靠他
    投递的路** —— 在 85 投 0 回音的情况下，这条路的分量只会更重。

    而这句提醒原来只挂在 `/job-auto` 的收尾，且**只在那一轮真出了材料时才说**。
    2026-08-24 那趟出了 0 份材料，按规则那句被正确地压掉了 —— 于是他那天
    什么也没被提醒，而距上一次简历审核已经过去二十多天。

    **没记过的渠道不算「很久没刷」**：那是「没查」，不是「没做」（同这个仓库
    对 `hr_viewed` 的处理）。只有记过、且超过阈值的才说。
    """
    import datetime as _dt
    import json as _json
    p = udir / "job_scraper" / "resume_refresh.json"
    if not p.is_file():
        return ""
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(d, dict):
        return ""
    t = today or _dt.date.today()
    worst, days = "", -1
    for name, day in d.items():
        if not on.get(name, True) or not isinstance(day, str):
            continue
        try:
            n = (t - _dt.date.fromisoformat(day)).days
        except ValueError:
            continue
        if n > days:
            worst, days = name, n
    if days < RESUME_STALE_DAYS:
        return ""
    return (f"{worst}上那份在线简历 {days} 天没刷新了——国内平台的简历库按"
            f"「最近活跃」排序，HR 主动搜人翻不了几页。登进去刷一下，"
            f"回来在总览页「招聘网站」那一块点一下记上。")


#: 抓取时只收这么多天内的岗（`job-scrape.md` Step 1b 第 3 条）。放到超过它，
#: 这一批里就有一部分在平台上已经关了 —— 判据同源，别在这儿另定一个数。
WAITING_FRESH_DAYS = 14


def waiting_age(seen: dict, today=None) -> dict:
    """排队等评的那批**放了多久**。返回 `{n, median, oldest, stale}`。

    ## 为什么光有个数不够

    「还有 182 个没评」印在自检和面板上，**两处都只有一个数**。而这批是会烂的：

    - 抓的时候只收 14 天内的岗（`job-scrape.md` 把范围收到最近 14 天），
      放过这条线，它就比抓它时的标准还旧；
    - 评它要花**抓详情的额度** —— 那是这套系统里最稀缺的东西（撞过限流、
      封过 9 小时）。花在一个已经关掉的岗上就是白花；
    - 面板上已经有「抓到时已 N 天没刷新」这样的标记，说明这件事本来就在意。

    实测活动用户 2026-08-24：182 个待评的**中位放了 7 天、最久 26 天**，
    其中 16 个已经超过 14 天。一个「182」说不出这里面有一批该先放弃。

    `archive.py` 帮不上：它明写「不碰待评的」—— 没评过的岗永远不会自己老去。
    所以只能在报数的地方把年龄一起说了。
    """
    import datetime as _dt
    today = today or _dt.date.today()
    days = []
    for e in seen.values():
        if not (isinstance(e, dict) and (e.get("status") or "") == "new"
                and e.get("rank_score") is None):
            continue
        d = str(e.get("first_seen") or "")[:10]
        try:
            days.append((today - _dt.date.fromisoformat(d)).days)
        except ValueError:
            continue          # 没有日期的不猜，也不算进中位
    days.sort()
    if not days:
        return {"n": 0, "median": None, "oldest": None, "stale": 0}
    return {"n": len(days), "median": days[len(days) // 2], "oldest": days[-1],
            "stale": sum(1 for d in days if d > WAITING_FRESH_DAYS)}


def waiting_note(seen: dict, today=None) -> str:
    """给用户看的那半句。没有可说的就返回空串 —— 不硬凑一句。"""
    a = waiting_age(seen, today)
    if not a["n"] or a["median"] is None:
        return ""
    tail = ""
    if a["stale"]:
        tail = (f"，其中 {a['stale']} 个超过 {WAITING_FRESH_DAYS} 天"
                f"——抓的时候只收 {WAITING_FRESH_DAYS} 天内的，"
                f"这批里有一部分在平台上已经关了")
    return f"放了中位 {a['median']} 天、最久 {a['oldest']} 天{tail}"


#: 旧名字。`doctor` 里别处按这个名字用。
_n_processed = n_processed

# 这一段和文件顶上那段**管的不是一回事，两块都要留**：
#   顶上那段只在**非 tty**（被管道接走/重定向）时把编码定到 UTF-8；
#   这一段管的是**真终端**那条路——那里编码仍是控制台代码页，动不得。
# Windows 控制台默认 cp936，中文以外的字符（✅ ❌ 之类）会直接抛 UnicodeEncodeError，
# 让脚本在最需要它的环境里崩掉。用纯 ASCII 标记，并放宽 stdout 的编码错误处理。
# （reconfigure 只传 errors 时保留当前 encoding，所以不会把顶上那段的 UTF-8 覆盖掉。）
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass

# [ok] 就绪 / [--] 没装（只影响对应命令）/ [!] 装了但有风险 / [ ] 不由本仓库决定
OK, NO, WARN, NA = "[ok]  ", "[--]  ", "[!]   ", "[ ]   "

#: 投递记录里代表「进面试」「拿到 offer」的状态值。
#: **本文件不 import 仓库任何模块**（见顶上第 1 条约束），所以这里是副本；
#: 权威定义在 `build_dashboard._INTERVIEW_STATUSES`（doctor 不 import 仓库模块，
#: 只能持副本）。两边一致由 `tests/test_application_loop.py` 钉——这行注释原来
#: 指向 `test_display_wording.py`，那里根本没有相关断言，是**虚构的守卫**；
#: 而且钉的只有 export↔build_dashboard 那对，这份副本当时谁也没钉。
INTERVIEW_STATUSES = {"interview", "offer", "hired"}
OFFER_STATUSES = {"offer"}
#: **有回音**的状态——约面或更远、以及明确被拒。口径同 `export_web_data` 的
#: 「约面或更远」+「被拒」两桶：被拒也是回音，它证明这条投递走到过人眼前。
REPLIED_STATUSES = {"interview", "offer", "hired", "interview_only",
                    "rejected", "offer declined", "offer_declined"}
#: 用户自己标的「没下文」。撤回（`withdrawn`）不算在任何一边——那是他自己收回的。
GHOST_STATUSES = {"no response", "no_response"}
#: 投出去多少天还没动静就算「决出结果了」。
#: **正本是 `followups.QUIET_DAYS`**，这里只能重抄一遍——本文件会被单独拷进
#: 临时目录跑（`test_cli_contract.CopyableToolsStayStandalone`），不许 import
#: 仓库内任何别的模块。同 `NODE_MIN` 的处境，做法也一样：
#: `test_both_next_steps_agree` 钉住这两个值必须相等。
QUIET_DAYS = 10
#: 零回音警报的门槛。判据与出处见 `build_dashboard.NO_REPLY_ALARM`（三倍法则）。
#: 这里不 import 它：`build_dashboard` 依赖 `export_web_data`，
#: 而自检必须在「什么都还没建」时也能跑。两处都改的判据写在那份注释里。
NO_REPLY_ALARM = 20


def hr(title: str = "") -> None:
    print()
    print(f"--- {title} " + "-" * max(0, 62 - len(title)) if title else "-" * 66)


def run(cmd: list[str]) -> str | None:
    """跑一条命令取首行输出；任何失败都返回 None（不抛）。"""
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        res = subprocess.run([exe] + cmd[1:], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=25)
    except Exception:
        return None
    if res.returncode != 0:
        return None
    return (res.stdout or res.stderr).strip().splitlines()[0] if (res.stdout or res.stderr) else ""


#: 跑 `node <file>.ts` 所需的最低 Node。**这个数只在这里定义一次**，
#: README / SETUP / job-scrape.md 里的写法由 `test_node_floor_is_one_number` 钉住相等。
NODE_MIN = (22, 18)
NODE_MIN_LABEL = f"Node {NODE_MIN[0]}.{NODE_MIN[1]}+"


def node_major_minor(ver: str | None):
    """'v22.18.0' -> (22, 18)；解析不出返回 None。"""
    if not ver:
        return None
    v = ver.lstrip("vV").split()[0]
    parts = v.split(".")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None


#: 回退链里任何一个族存在，中文简历就能正常渲染。与 resume/template.typ 保持一致。
CJK_FONTS = ("noto sans sc", "source han sans", "microsoft yahei", "simhei", "dengxian",
             "pingfang sc", "hiragino sans gb", "stheiti", "noto sans cjk", "wenquanyi")


def probe_env() -> list[dict]:
    """探测各项能力，返回**结构化**结果，不打印任何东西。

    `build_dashboard.py` 也 import 这个函数在面板上渲染同一份环境状态 —— 检查逻辑
    只写一遍，两处口径就不会漂。所以这里**不要**混入 print：打印交给 render_env()。

    每项：{key, label, ok(True/False/None), detail, fix, unlocks, silent_fail}
    - ok=None：不适用（例如 typst 缺失时字体项无从判断）
    - silent_fail=True：缺了**不会报错**、只会静默出坏结果的项（目前只有中文字体）
    """
    items: list[dict] = []

    node_ver = run(["node", "--version"])
    nm = node_major_minor(node_ver)
    # **22.18 不是 22.6。** 22.6 加的是 `--experimental-strip-types` 这个*开关*；
    # 默认剥离类型（也就是文档里那条不带开关的裸 `node cli.ts`）是 22.18 才有的。
    # cli.ts 的入口判据用 `import.meta.main`，那是 22.16+，取两者较大的。
    # 这个数只在这里定义一次，文档里的写法由 `test_node_floor_is_one_number` 钉住。
    node_ok = bool(nm and (nm[0], nm[1]) >= NODE_MIN)
    items.append({
        "key": "node", "label": NODE_MIN_LABEL, "ok": node_ok,
        "detail": (node_ver or "未安装") if not node_ok else node_ver,
        "unlocks": "搜职位 /job-scrape、打分 /job-rank",
        "fix": (f"升级到 v{NODE_MIN[0]}.{NODE_MIN[1]}+：https://nodejs.org（或装 Bun 作替代运行时）"
                if nm else "Claude Code 本身走 npm 安装，正常情况下 Node 应已存在；"
                           "检查 PATH 或去 https://nodejs.org 装"),
    })

    bun_ver = run(["bun", "--version"])
    items.append({
        "key": "bun", "label": "Bun（可选）", "optional": True,
        "ok": bun_ver is not None, "detail": bun_ver or "未安装",
        "unlocks": "改 CLI 代码、跑它的单元测试",
        "fix": "日常使用不需要。要装：https://bun.sh",
    })

    typst_ver = run(["typst", "--version"])
    items.append({
        "key": "typst", "label": "Typst", "ok": typst_ver is not None,
        "detail": typst_ver or "未安装",
        "unlocks": "/job-apply 编译简历 PDF",
        "fix": "winget install --id Typst.Typst（Windows，装完新开终端）"
               " / brew install typst（macOS）",
    })

    # 字体只在 typst 可用时才有意义查
    font_ok, font_detail = None, "typst 未安装，无从判断"
    if typst_ver is not None:
        listing = ""
        exe = shutil.which("typst")
        if exe:
            try:
                listing = subprocess.run([exe, "fonts"], capture_output=True, text=True,
                                         encoding="utf-8", errors="replace",
                                         timeout=40).stdout.lower()
            except Exception:
                listing = ""
        hits = [f for f in CJK_FONTS if f in listing]
        font_ok = bool(hits)
        font_detail = (f"命中 {len(hits)} 个（{hits[0]} …）" if hits
                       else "一个都没找到")
    items.append({
        "key": "cjk_font", "label": "中文字体", "ok": font_ok, "detail": font_detail,
        "unlocks": "简历 PDF 正常渲染中文",
        "fix": "装 Noto Sans SC / Noto Serif SC：https://fonts.google.com/noto",
        "silent_fail": True,
    })

    items.append({
        "key": "python", "label": "Python", "ok": True,
        "detail": sys.version.split()[0],
        "unlocks": "/job-dashboard 求职总览", "fix": "",
    })

    # 总览页的界面是 React 写的，要先构建一次才出得来。
    #
    # **这一项非查不可。** 它是这次「两套面板合并成一套」引入的新前置条件——
    # 以前总览页由一个纯 Python 脚本直接吐 HTML，不需要构建。不查的话，用户跑
    # `/job-dashboard` 才撞错，而自检的职责就是提前说清楚还差什么。
    _dist = ROOT / "web" / "dist" / "index.html"
    items.append({
        "key": "web_build", "label": "总览页前端", "ok": _dist.is_file(),
        "detail": "已构建" if _dist.is_file() else "还没构建（web/dist 不存在）",
        "unlocks": "/job-dashboard 出总览页、python tools/serve.py 打开它",
        "fix": "cd web && npm install && npm run build（只需要一次）",
    })

    # poppler 的两个命令**要分开探**。它们同属一个包，但实测有只装了 `pdftotext`
    # 没有 `pdftoppm` 的机器（本仓库的开发机就是）。而 `/job-apply` 第 5d 步「视觉检查」
    # 要用 Read 工具读 PDF —— 那一步靠 `pdftoppm` 渲染页面。只探 pdftotext 就报「已安装」，
    # 用户要到 /job-apply 跑到一半才撞上，而第 5 步标着「强制，不得跳过」。
    _t, _p = shutil.which("pdftotext"), shutil.which("pdftoppm")
    items.append({
        "key": "pdftotext", "label": "pdftotext（可选）", "optional": True,
        "ok": _t is not None,
        "detail": "已安装" if _t else "未安装",
        "unlocks": "检查简历 PDF 里的字能否被招聘系统读出",
        "fix": "装 poppler：brew install poppler（macOS）/ 各发行版包管理器",
    })
    items.append({
        "key": "pdftoppm", "label": "pdftoppm（可选）", "optional": True,
        "ok": _p is not None,
        "detail": "已安装" if _p else ("未安装（pdftotext 有，但这个没有）" if _t else "未安装"),
        "unlocks": "/job-apply 出 PDF 后检查排版（页数、孤行、溢出）",
        "fix": "和 pdftotext 同属 poppler，但有的安装方式只带其中一个；"
               "缺它时 /job-apply 的视觉检查会如实标注「未执行」，不影响出 PDF",
    })

    # 浏览器能力**不是这个仓库的依赖**，它由你所在的 AI 工具提供：
    # Claude Code 装了 Claude 浏览器扩展就有，首选走它（驱动的就是用户已登录的
    # Chrome，登录态天然带着）。web-access 那个 CDP skill 只是**没有扩展时的兜底**。
    #
    # 所以这里不能像探 typst 那样报「未检测到 → 快去装」：脚本探不到 MCP 连接，
    # 探不到 CDP skill 也不代表用户没有浏览器能力。误报会把人推去装一个第三方
    # 全局技能，而他其实已经有扩展了。ok=None 表示「这项由工具决定，不作判定」。
    home = Path(os.path.expanduser("~"))
    cdp = False
    if (home / ".claude").is_dir():
        cdp = (home / ".claude" / "skills" / "web-access").is_dir() or bool(
            list((home / ".claude" / "plugins").glob("**/web-access")))
    items.append({
        "key": "browser", "label": "浏览器取数", "optional": True,
        "ok": None,
        # 面板与终端都会原样显示这句，所以不写「CDP skill」这种未解释的英文码；
        # 「兜底技能」同理——「技能」是本仓库的内部概念，用户不该为了看懂一句提示
        # 先去认识 skill 是什么。说它做的事就够了。
        "detail": ("由你的 AI 工具提供，Claude Code 用浏览器扩展；"
                   "你另外还装了一个备用的抓取方式"
                   if cdp else "由你的 AI 工具提供，Claude Code 装了浏览器扩展即可用"),
        "unlocks": "登录后抓 BOSS 直聘、智联招聘、前程无忧",
        "fix": "",
    })
    return items


def check_env() -> dict:
    """探测 + 打印，返回 {key: ok} 便于 next_step 判断。"""
    hr("环境")
    items = probe_env()
    # 「不作判定」的项（由 AI 工具提供、无从判断）**整条移出清单**，打完再单独说。
    # AGENTS.md 的规矩是「不把它算进『还差几项』」——而只要它还带着一个方框排在
    # 一列 [ok] 中间，[ ] 和 [--] 在扫读时就是同一个意思：没过。规矩守在文字里、
    # 破在符号上。真正不算进清单的做法是让它不在清单里。
    notes = [it for it in items if it["ok"] is None]
    for it in items:
        if it["ok"] is None:
            continue
        if it["ok"]:
            print(f"{OK}{it['label']} {it['detail']} —— {it['unlocks']}")
            continue
        mark = NO
        if it.get("silent_fail"):
            print(f"{WARN}{it['label']}：{it['detail']} —— "
                  f"这是唯一会「静默出错」的依赖：")
            print("      Typst 不会报错，PDF 照样生成、文本层校验也会过，但渲染是豆腐块。")
        else:
            print(f"{mark}{it['label']}：{it['detail']} —— 影响：{it['unlocks']}")
        if it["fix"]:
            print(f"      {it['fix']}")
    for it in notes:
        print(f"\n      {it['label']}不用你装：{it['detail']}。")
        print(f"      用来{it['unlocks']}。")
    return {it["key"]: it["ok"] for it in items}


#: 判词判「出局」的写法（硬门没过 / 跳过 / 不建议）。
#:
#: 与 `build_dashboard.is_out_verdict` + `_cli.GATE_FAIL_PREFIXES` 同源。
#: 这里不 import 它 —— 本文件零依赖、不 import 仓库模块（`doctor` 存在的全部意义）。
#:
#: **提成函数是因为这个文件里它本来就要用两次**：一处按 `seen` 的
#: `rank_verdict` 数目录，一处按快照 `jobs` 的 `verdict` 挑「备好没发」。
#: `ready_rows` 自己的说明立着规矩：「同一段判断在这个文件里不许写两遍 ——
#: 2026-08-26 全量扫重复定义时它正好写了两遍……那不是设计约束，是复制粘贴。」
#:
#: **2026-08-27 改成公开名 `is_out_verdict`：文件外也要用它。**
#: `fetch_details._missing_alive` 挑「还要不要去抓 JD」时漏了这一条 ——
#: 判词已经是「跳过 / 不建议 / 硬门没过」的岗照样进了浏览器待办名单，
#: 实测那份 549 个的名单里 **362 个已经结案**。而浏览器一次只开一页、
#: 还有间隔闸门，名单里每一条假货都是一次真实的额度。
#: 这个文件是依赖链的底（只用标准库、不 import 仓库里的任何模块），
#: 所以判词的这一段判断放在这里、别处 import，方向是对的。
_OUT_PREFIXES = ("硬门 FAIL", "硬门FAIL", "不满足硬性条件")


def is_out_verdict(verdict: str) -> bool:
    # 空串（老快照没有 `verdict` 这个字段）自然返回 False —— 三个子判据一个都
    # 不匹配空串，不必再加一道 `if not v`。`ready_rows` 靠这一点退回粗口径，
    # 行为由 `test_a_snapshot_without_the_field_falls_back_to_coarse` 钉着。
    v = str(verdict or "").strip()
    # **「已下线」也是出局，而且是最确定的那种。**
    # 这一条 2026-08-23 补进了 `build_dashboard.is_out_verdict`，**这份副本没跟**
    # —— 改了一处漏了另一处，正是 `test_the_copies_in_doctor_still_match`
    # 本该拦下的事（那条守卫当时被两处注释引用着，而它一直不存在）。
    #
    # 补它 2026-08-31 实测**一行输出都没变**：那几个岗都已被状态那条路
    # 排掉了。仍然要补，理由与那边同源 —— 这个函数管的就是「判词说出局」
    # 这一侧，漏掉最确定的一种等于把正确性押在「状态那一侧一定同时也对」上，
    # 而判词是打分器写的、状态是下线探测写的，两者本来就可能不同步。
    return (v.startswith(_OUT_PREFIXES) or v.startswith("已下线")
            or "跳过" in v or "不建议" in v)


def _re_strong(verdict: str) -> bool:
    """判词是不是「可以直接发」那两档。

    与 `export_web_data.is_strong` 同源。这里不 import 它——本文件零依赖、
    不 import 仓库模块，是为了在环境半坏时仍能跑（`doctor` 存在的全部意义）。
    两处各一份的代价由 `tests/test_ready_is_split_by_verdict.py` 兜住。

    **精确匹配，不容后缀**：白名单 `is_sellable` 就是精确的，这个函数是它的子集，
    只能更严。写成 `startswith` 会让「值得投（附条件）」算进「先发这 N 个」、
    却进不了那张名单——数得到、找不着。
    """
    import re as _re
    # 正本是 `_cli.strip_triage`。这里重抄一份是本文件顶上那条契约：
    # **不 import 本仓库的任何模块**（要在什么都没配好时裸跑）。
    # 全仓库其余 17 处 2026-08-30 都收拢到那个函数了，只剩这一处 —— 它不是漏网的。
    return _re.sub(r"^粗筛[：:]\s*", "", (verdict or "").strip()) in ("强匹配", "值得投")



#: 「备好没发放太久」的阈值**这里不再留副本**。正本是
#: `export_web_data.STALE_POSTING_DAYS`（面板的 `ready_old` 用的就是它）。
#:
#: 原来这儿有个 `READY_STALE_DAYS`（14），注释写着「与
#: `export_web_data.STALE_POSTING_DAYS` 同值」，还有一条测试盯着两边相等。
#: 2026-08-25 起 `ready_age` 直接读快照里的 `queuedLong` —— 谁算得久由面板那边
#: 判完了，这边读结论。**两个副本相等，不如只有一个。**
#:
#: 本文件不 import 仓库模块（`test_cli_contract` 盯着），但读它导出的快照
#: 是本来就在做的事 —— 这条路不违反那条约束。


def ready_age(udir, today=None) -> dict:
    """备好没发的那批**放了多久**、有几个已经没了。

    返回 `{n, old, lost, median}`；读不到面板快照时返回 `{}`（**不猜**）。

    ## 为什么光有个数不够

    自检印的是「已出材料 140 份」——一个平数。而这批和待评队列一样会烂，
    **而且更贵**：一份材料是一次公司调研加起草审稿两轮，一次待评只是一次打分。

    实测活动用户 2026-08-24：

        备好没投的            157 个（岗龄中位 19 天、最久 26 天）
        全库已下线            19 个
        其中出过材料的        12 个
        **其中已经投出去的**  **0 个**

    也就是说：**所有「下线且有材料」的岗，材料全是白做的，12/12。**

    面板早就在说这件事了（`build_dashboard.season_note` 那句「已经有 N 个岗在你
    发出去之前就下线了」，还带着按岗龄分桶的实测：>14 天那一档 8/34 已下线，
    ≤14 天只有 2-7%）。**而自检这边一个字没有** —— 它偏偏是会话开始第一件事，
    也就是每次最先被看见的那份报告。

    这与本文件 `waiting_age` 是同一个形状：那次修的是待评队列的年龄，
    这次修的是它旁边那一队 —— 同样的病，只治了一半。
    """
    import datetime as _dt
    snap = udir.parent.parent / "web" / "public" / "data.json"
    if not snap.is_file():
        return {}
    try:
        import json as _json
        d = _json.loads(snap.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if (d.get("activeUser") or "") != udir.name:
        return {}
    jobs = d.get("jobs") or []
    live = ready_rows(jobs)
    # **已下线的要单独数，不能混进 `live`。** 它们已经被上面那几个条件排掉了，
    # 而这一档恰恰是最要紧的那个数：材料做完、岗先没了。
    lost = sum(1 for j in jobs
               if j.get("materials") and j.get("expired")
               and not j.get("applied") and not j.get("dupOf"))
    # **读 `queuedDays`，不是 `staleDays`。** 两个都是「天」，说的是两件事：
    #
    #   staleDays    抓到它那天，招聘方上一次刷新在多久以前
    #                （只有猎聘给；而且它**只在超阈值时才有值**）
    #   queuedDays   它进库到今天多少天（`first_seen`，备好没发的岗 100% 有）
    #
    # 上面那句话说的是「这几份材料放了多久」——那是后者。
    #
    # 实测 2026-08-25 用错字段的代价：备好没发的 60 个里只有 **10 个**有
    # `staleDays`，于是「中位 20 天」是在 10 个数上取的；而 `staleDays` 本身
    # 只在超阈值时才有值，所以那 10 个必然全部超阈值 —— **「其中 10 份排了
    # 两周以上」实际等于「有这个字段的有 10 个」**。同一时刻面板说 15。
    # 两句话措辞几乎一模一样，数字差 5 个，隔着一个会话开始的距离。
    #
    # 「够不够久」也不在这儿判：面板已经算好了 `queuedLong`
    # （阈值 `export_web_data.STALE_POSTING_DAYS`）。本文件不 import 仓库模块，
    # 但**读它导出的快照**是本来就在做的事 —— 读结论比抄一份阈值可靠。
    ages = sorted(j["queuedDays"] for j in live
                  if isinstance(j.get("queuedDays"), int))
    return {"n": len(live), "lost": lost,
            "old": sum(1 for j in live if j.get("queuedLong")),
            "median": ages[len(ages) // 2] if ages else None}


def ready_note(udir, today=None) -> str:
    """备好没发那批的一句话。没有要说的就返回空串。

    **只在真的有话说时才出现**：一个都没过期、也没有放超过两周的，
    这一行就不该占地方（同本仓库「标记要标少数派」）。
    """
    a = ready_age(udir, today)
    if not a or not a.get("n"):
        return ""
    bits = []
    if a.get("median") is not None:
        bits.append(f"这 {a['n']} 份材料放了中位 {a['median']} 天")
    if a.get("old"):
        bits.append(f"其中 {a['old']} 份排了两周以上")
    if a.get("lost"):
        bits.append(f"另有 {a['lost']} 个岗在你发出去之前就下线了，那几份白做了")
    if not a.get("old") and not a.get("lost"):
        return ""
    return "、".join(bits) + "——先发排得最久的那几个，分数没变，是它们还剩的时间少了。"


def ready_rows(jobs: list) -> list:
    """快照里「材料备好、还没投」的那几行。**兜底口径，比正本松。**

    正本是 `export_web_data.funnels_of`：它还排掉「判词说出局」的岗
    （`is_out_verdict`）和三类搁置（`is_parked`）。这里只看几个布尔字段，
    所以**偏大** —— 那是有意的：老快照可能没有那些字段，宁可多说一个，
    也不要让一个真备好的岗从「下一步」里静默消失。

    doctor 不 import 仓库模块（环境半坏时也要能跑），所以拿不到正本。
    但**同一段判断在这个文件里不许写两遍** —— 2026-08-26 全量扫重复定义时，
    它正好写了两遍（`ready_snapshot` 一处、`count_ready` 的兜底一处），
    逐字相同。那不是设计约束，是复制粘贴。
    """
    return [j for j in jobs
            if j.get("materials") and not j.get("applied")
            and not j.get("dupOf") and not j.get("skipped")
            and not j.get("expired")
            # **判词说出局的也排掉 —— 快照里带着 `verdict` 就够得着。**
            #
            # 这一条 2026-08-27 才补上。此前只看 `skipped`（用户手点的「不投」），
            # 而判词降到「跳过 / 不建议 / 不满足硬性条件」的岗照样算进「备好没发」。
            # 实测当天：自检说 65、面板说 64，多出来的那个判词正是「跳过」——
            # 而自检那句话是「先发排得最久的那几个」，等于催用户去投一个
            # 框架已经判了不投的岗。
            #
            # `is_out_verdict` 的说明里记着同一形状：「一个岗材料做完之后判词才
            # 降到『跳过』……页面一边把它算作出局、一边在详情里催『材料就绪，
            # 快去投』」。那次修的是 `job_next_step`，**这边漏了**。
            #
            # 字段缺席时（老快照）`is_out_verdict("")` 返回 False，自动退回粗口径 ——
            # 与上面那段「宁可多说一个」的取舍一致，没有把它推翻。
            and not is_out_verdict(j.get("verdict"))]


def count_ready(udir, seen: dict) -> tuple[int, int | None, int | None]:
    """材料备好、但还没投出去的岗有几个
    → `(总数, 其中可以直接发的, 「可以考虑」那批里真列了要问什么的)`。

    后两个数可能是 `None`——兜底数目录时读不到判词、也读不到那一节，
    那时只能说出总数。调用方拿到 `None` 要退回不分档的旧文案，**不要猜**。

    ## 第三个数是干什么的

    「可以考虑」那一档的定义就是「先问清楚再决定」，所以每一处劝人
    「投之前先问清楚」的话，都默认那份清单存在。实测活动用户 2026-08-30：
    这一档有材料、在跑的 56 个，**其中只有 9 个列了**。
    对另外 47 个，那句建议指向一份不存在的东西。

    面板上早就分两枚章说清了（`Shortlist.tsx` 的 `askBefore` 分支：
    「话术备好 · 先问清」vs「话术备好 · 这档得先问」），而终端那句一直没有。
    口径归导出器（`nextStep.readyAsked`），这里**只取数不重算** ——
    本文件不 import 仓库任何模块，重算一份必然和那边飘。

    ## 为什么优先读面板那份快照

    「有几个还没发」这个数要减掉三类：已经投了的、**同一个岗的重复挂牌**、
    **已经下线的**。后两类的判据只有导出器有——重复挂牌按「公司 + JD 正文前缀」
    归并，本文件既拿不到 JD 正文，也不该把那套归并逻辑抄第二遍。

    抄的代价当场就出现了（2026-08-13）：这个数试过两版 —— 按公司名匹配是
    自检 101 / 面板 107，改成 URL 精确匹配变成 132 / 107，**两版都不对，
    而且错的方向还相反**；差的 25 个正是 18 个重复挂牌加 7 个已下线。

    所以：**面板快照在就用它**（`web/public/data.json` 只是个 JSON 文件，
    读它不违反「本文件不 import 仓库模块」那条——那条防的是循环依赖）。
    ⚠️ **兜底那支比正本松**：`nextStep.ready` 由 `export_web_data.funnels_of`
    算出来，它还排掉「判词说出局」的岗和三类搁置；这里的 `ready_rows`
    只看几个布尔字段，所以偏大。差别是有意的，但要写在脸上 ——
    2026-08-26 隔壁那条守卫（`test_two_entry_points_agree`）正是因为
    自己重算了一份松口径的，报出一个 63 vs 64 的假分歧。

    快照不在（新 clone、这台机器没跑过导出）才退回目录粗数，那时它偏大，
    但方向是对的：确实有一堆材料没发。
    """
    snap = udir.parent.parent / "web" / "public" / "data.json"
    if snap.is_file():
        try:
            import json as _json
            d = _json.loads(snap.read_text(encoding="utf-8"))
            # 身份要对上，否则读的是别的用户的进度
            if (d.get("activeUser") or "") == udir.name:
                ns = d.get("nextStep") or {}
                out = ns.get("ready")
                if isinstance(out, int):
                    return out, ns.get("readyStrong"), ns.get("readyAsked")
                jobs = d.get("jobs") or []
                live = ready_rows(jobs)
                # 判词分档与 `export_web_data.is_strong` 同源（容 `粗筛：` 前缀）。
                strong = sum(1 for j in live
                             if _re_strong(j.get("verdict") or ""))
                # 这一支的口径比正本松（见上面那段），第三个数跟着它自己走。
                asked = sum(1 for j in live
                            if not _re_strong(j.get("verdict") or "")
                            and j.get("askBefore"))
                return len(live), strong, asked
        except Exception:
            pass

    # 兜底：数目录。偏大（含重复挂牌与已下线），但「有材料没发」这件事没说错。
    apps = udir / "documents" / "applications"
    if not apps.is_dir():
        return 0, None, None
    import csv as _csv
    import re as _re
    sent_urls, sent_comps = set(), set()
    tr = udir / "job_search_tracker.csv"
    if tr.is_file():
        try:
            with tr.open(encoding="utf-8-sig", newline="") as fh:
                for row in _csv.DictReader(fh):
                    u = (row.get("source") or "").strip()
                    if u:
                        sent_urls.add(u.split("#", 1)[0])
                    c = (row.get("company") or "").strip()
                    if c:
                        sent_comps.add(c)
        except Exception:
            pass
    n = 0
    for d in sorted(apps.iterdir()):
        f = (d / "outreach.md") if d.is_dir() else None
        if not f or not f.is_file():
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        m = LINK_LINE.search(txt)
        url = (m.group(1).split("#", 1)[0] if m else "")
        if url and url in sent_urls:
            continue
        if not url:
            comp = d.name.split("_", 1)[0]
            if comp and any(comp in c or c in comp for c in sent_comps):
                continue
        n += 1
    # 兜底路径读不到判词（目录里只有话术文本），第二个数交回 None。
    return n, None, None


def count_restock(udir) -> tuple[int | None, int | None]:
    """`(还能投几个, 抓到但还没评的有几个)` ——读得到就报数，读不到交回 `None`。

    这两个数是「名单见底 → 先去补货」那一支的判据，而它要分两岔：

    - 还有「抓到但没评」的积压 → `/job-rank`（先把库存评完，否则
      `/job-scrape` → `/job-scrape` 死循环：新抓的没评分，`n_sellable` 永远是 0）
    - 没有积压 → `/job-auto`（抓岗、评分、出材料一条龙）

    另一个用法在「一个材料都还没出」那支：`n_sellable == 0` 时那一句
    换成「没有几个能投的，去找更多」而不是「批量出材料」。

    ## 为什么必须是同一批数

    面板那条 `build_dashboard.next_step` 走的就是导出器传进来的
    `n_sellable` / `n_unranked`。终端自检当年没有这一支，于是「名单见底
    该不该先补货」上两个出口给相反的答案 —— 面板说「去补货」，自检说
    「先把备好的发出去」。`tests/test_both_next_steps_agree.py` 顶上把
    这个形状记成「已经栽过两次」（2026-08-13、2026-08-22，两次都是
    「一条规则加在一个出口上，另一个出口照旧」）。

    ## 口径归导出器，这里只取数

    同 `count_ready`：`doctor` 不 import 仓库任何模块（环境半坏时也要能跑），
    重算一份判词必然和那边飘 —— 而 `export_web_data.is_sellable` 那条白名单
    自己写着「判词是自由度很高的字段，每次变动的默认后果都是漏一个」。

    ## 为什么不并进 `count_ready`

    两件事：那个数是「材料备好没发」，这两个是「还能投几个 / 待评几个」；
    而且 `count_ready` 的返回元组长度被 `test_ready_is_split_by_verdict.py`
    钉成 3（那是 `ready` 分档那次修复留下的契约）。并进去会让那条守卫变成
    「签名改了也算对」—— 改契约要改测试，而这里的理由不足以动它。

    ## 一份快照读一次

    两个数在 payload 的同一个 `nextStep` 里。分成两个函数就要把
    「找快照 → 验身份 → 取键」那段抄两遍，而那段本身已经因为抄错过至少一次。

    读不到快照（新 clone、没跑过导出、或老导出没有这两个键）就返回
    `(None, None)`：调用方退回原来那条说法，不猜。
    """
    snap = udir.parent.parent / "web" / "public" / "data.json"
    if not snap.is_file():
        return None, None
    try:
        import json as _json
        d = _json.loads(snap.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    # 身份要对上，否则读的是别的用户的进度（同 `count_ready`）。
    if (d.get("activeUser") or "") != udir.name:
        return None, None
    ns = d.get("nextStep") or {}
    out, un = ns.get("nSellable"), ns.get("nUnranked")
    return (out if isinstance(out, int) else None,
            un if isinstance(un, int) else None)


#: 与 `build_dashboard.SHORTLIST_FLOOR` 同值 —— 「名单见底」的那个门槛。
#: `doctor` 不 import 仓库模块（那是它存在的理由），所以这一份是正当副本，
#: 相等由 `tests/test_both_next_steps_agree.py` 钉住 —— 与 `QUIET_DAYS`、
#: `AGENCY_WORDS`、`DATE_FORMATS` 同一族处置。
#:
#: 那个数的理由（取 5、为什么要在见底之前就提醒）写在
#: `build_dashboard` 那个常量的 docstring 里，这里不复述。
SHORTLIST_FLOOR = 5


#: 与 `_cli.LINK_LINE` 同值 —— `doctor` 不 import 仓库模块（那是它存在的理由），
#: 所以这一份是**正当副本**，相等由 `test_link_line_agrees` 钉住。
#: 本文件里原来抄了**四遍**，那四遍不是契约换来的，是复制粘贴。
#:
#: ⚠️ 上一行原来只写到文件名（`test_the_copies_in_doctor_still_match`），
#: 而那个文件里**没有任何一条断言比过这两份正则** —— 它的漏网扫描只看顶层
#: 函数，常量整类不在里面。2026-08-31 把扫描扩到常量时才露出来。
#: 引守卫要引到断言那一级，文件名这一级挡不住「同名不同事」。
LINK_LINE = re.compile(r"职位链接\s*[：:]\s*(\S+)")


def norm_url(u: str) -> str:
    """让同一个岗的不同写法指向同一个键：剥协议，并把 51job 的路径前缀归一。

    **去重前必须先过这一步。** 同一课这个仓库交过几次学费，每次换一个变量：

    - **协议**（2026-08-19 抓智联）：页面锚点给 `http://`，库里同一批岗存的是
      `https://` —— 20 个新岗里 4 个重复入库，其中两个早就判过硬门 FAIL，
      等于花账号额度把出局的岗又评了一遍。
    - **51job 的路径前缀**（2026-08-28 实测）：同一个职位号有两种挂法 ——
      `/all/<id>.html` 与 `/shanghai-<区码>/<id>.html`。历史入库的是前者，
      而 `cdp-portals.md` 记的浏览器抓取形态是后者，于是**每跑一轮前程无忧，
      已经在库里的岗就再插一遍**。热库加存档 2950 条里撞出 9 组，
      其中 8 组是当轮新插的。

    ⚠️ **收敛到职位号是安全的，因为库的键是 `<url>#<职位名>`**（`cdp-portals.md`
    第 7 条：「51job 实测同一 URL 下挂着两个不同职位，只用 URL 会静默吃掉其中
    一条」）—— 职位名还在键里，两个真不同的岗不会被并掉。

    - **查询串**（2026-09-01 抓智联）：搜索结果页给的锚点尾巴上挂着
      `?refcode=…&preactionid=…&data_identity=…`，全是埋点参数，同一个岗每次
      搜到都换一串。库里存的是干净 URL，于是 **120 个「新岗」里 43 组是已经
      在库里的**。埋点参数不参与身份。
    - **手机站前缀**（实测过一次）：从微信里点开一个岗复制出来的是
      `//m.liepin.com/job/<id>.shtml?mscid=wx_h5_001`。埋点参数上面剥掉了，
      `m.` 没人管，于是深评和话术都出好了、总览页上那个岗还是「没有材料」——
      材料目录靠 `原始链接：<URL>` 认岗，两边一个 `//m.…` 一个 `//www.…`。
    """
    s = (u or "").replace("https://", "//").replace("http://", "//")
    head, sep, tail = s.partition("#")   # 剥查询串只剥 `#` 之前那一段
    s = head.split("?", 1)[0] + sep + tail
    # 手机站前缀：`//m.liepin.com/...` 与 `//www.liepin.com/...` 是同一个岗。
    # 收敛成 `www.` 是照库里实测的形态（猎聘/BOSS/智联三家存的都是 www.）；
    # 51job 的正规形态是 `jobs.`，不在这条里。理由见 `_cli.norm_url` 那一份。
    s = re.sub(r"^//(?:m|wap)\.(?!51job\.)", "//www.", s)
    m = re.match(r"(//jobs\.51job\.com)/[^/]+/(\d+)\.html", s)
    return f"{m.group(1)}/{m.group(2)}.html" if m else s


#: 人手填的台账里出现过的日期写法。与 `followups._DATE_FORMATS` 同值 ——
#: 本文件不 import 仓库任何模块，只能持副本；两边相等由
#: `test_both_next_steps_agree` 钉住。
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日")

#: 招聘方名字里出现这些词就是中介。与 `_cli._AGENCY_WORDS` 同值，
#: 本文件的硬契约是「不 import 仓库任何模块」，所以内联一份；
#: 两边相等由 `test_both_next_steps_agree` 钉住。
#: （正本 2026-08-23 从 `export_web_data` 搬到了 `_cli` —— `followups` 也要判
#: 这件事，而它 import 不动 `export_web_data`。`export_web_data` 那两个名字
#: 现在是转出的别名，指过去仍然对，但**正本在 `_cli`**。）
AGENCY_WORDS = ("猎头", "人力资源", "人才", "咨询")


def _via_headhunter(entry: dict):
    """猎头代招 / 企业直招 / **没判过**。判据与 `_cli.via_headhunter` 同源。

    ## 这里原来写的是 `bool(e.get("isHeadhunter"))`

    那一行把「字段不在」变成了 `False` —— 也就是**「没判过」被算成「确认是直招」**。
    而正本那个函数的 docstring 专门警告过这件事：「没判过 ≠ 判过是『不是』…
    返回 False 是**给错误的信息**，不是少一条信息」。它还漏了 `recruiter`
    那条规则（招聘方叫「××猎头」「××人力资源」时，不管字段怎么写都是中介）。

    代价落在自检最要紧的那句话上。实测活动用户 2026-08-23，同一份数据：

        自检   其中 38 个投的是猎头代招……但企业直招那 38 个也是一个回音都没有
        面板   其中 43 个投的是猎头代招……但企业直招那 33 个也是一个回音都没有

    总数都是 76，分法差 5 个。而「企业直招那 N 个也是一个回音都没有，
    **这批才是信号**」是整段诊断的落点 —— 往那个分母里掺没判过的岗，
    等于用没查过的数据去加强一个结论。
    """
    if any(w in (entry.get("recruiter") or "") for w in AGENCY_WORDS):
        return True
    # 头衔那一栏只认「猎头」二字 —— 整张词表套上去会把「人力资源总监」
    # 「HRBP」这些**企业自己的 HR** 全判成中介（实测 19 个里 15 个是）。
    if "猎头" in (entry.get("recruiterTitle") or ""):
        return True
    # 显式的 `null` 也是「没判过」，不是「判过是直招」。
    if entry.get("isHeadhunter") is not None:
        return bool(entry["isHeadhunter"])
    if "/a/" in (entry.get("url") or ""):
        return True
    return None


def count_materials(udir: Path, seen: dict | None = None) -> int:
    """数**真出了材料的**投递目录，不是数目录个数。

    `/job-apply` 跑到一半会留下只含 `posting.md` 的空壳目录。按目录个数计，它也算一份，
    于是「已出材料 N 份」虚高——实测 5 个目录里只有 4 个真有话术。数字虚高还会让
    next_step 里 `materials == 0` 那条分支永远进不去。

    判据取 `outreach.md`：话术是 `/job-apply` 的核心产出，简历 PDF 反而可能因为缺 typst
    而没有。与 `build_dashboard.py` 用 `app["outreach"]` 判「材料就绪」同口径。
    """
    apps = udir / "documents" / "applications"
    if not apps.is_dir():
        return 0
    dirs = [p for p in apps.iterdir()
            if p.is_dir() and (p / "outreach.md").is_file()]
    if seen is None:
        return len(dirs)
    # **搁置的不算。** 面板的「材料就绪」那一格点开是待投列表，搁置区的岗不在里面。
    #
    # 两处都对着同一个概念，却各答各的：自检把它算进材料、不算进已评；
    # 面板反过来。谁也不比谁更对，但它们**必须说同一个数**。
    #
    # 那句话写下来之后又飘了一次（2026-08-23 实测：自检 155、面板 142）。
    # 两个原因，都在这几行里：
    #
    # 1. **只排了 `skipped`。** 面板走 `build_dashboard.is_parked`（不投 + 已下线
    #    + 重复挂法）再加判词出局。实测 2026-08-23 12 个目录的岗**已经下线**——催一个
    #    关掉的岗去投，比不催更糟（`is_parked` 的 docstring 记的就是这 12 个）。
    # 2. **按原始字符串比链接。** 同一个岗在两处存 `http://` 和 `https://` 是
    #    真实发生过的（`_cli.norm_url` 存在的理由）。比不上就漏排。
    #
    # 判据在这里**内联一份**：doctor 要能单文件拷走，不 import 仓库里别的模块
    # （`test_cli_contract.CopyableToolsStayStandalone` 盯着）。两边相等由
    # `test_material_counts_agree` 钉住 —— 光写一句「必须说同一个数」拦不住它。
    #
    # ⚠️ **只剩一类对不齐，而且对不齐是对的：重复挂法（`dupOf`）。**
    # 面板把同一个岗的多次挂牌并成一行，判据是「公司 + JD 正文前 300 字」——
    # 那要读 `details/` 里的 JD 正文，而 doctor 是零依赖、只读几个小文件的自检，
    # 不该为一个统计数字去加载几千份正文。实测活动用户 2026-08-23：
    # 自检 143、面板 142，差的那 1 个正是一份重复挂牌。
    # 上面那条测试验的是「自检多出来的每一个都必须是重复挂法」——
    # 不是「差额 == 重复挂法数」（那也是错的：有的重复挂法同时还被别的
    # 理由排掉了，实测有材料的重复挂法 2 个而差额只有 1）。
    def _key(u):
        return (u or "").strip().replace("https://", "//").replace("http://", "//")

    # 判词判「出局」走模块级的 `is_out_verdict`（同一段判断这个文件里只留一份）。
    parked = set()
    for e in seen.values():
        if not isinstance(e, dict):
            continue
        if (e.get("status") in ("skipped", "expired")
                or is_out_verdict(e.get("rank_verdict"))):
            parked.add(_key(e.get("url")))
    parked.discard("")
    if not parked:
        return len(dirs)
    n = 0
    for d in dirs:
        text = (d / "outreach.md").read_text(encoding="utf-8", errors="replace")
        m = LINK_LINE.search(text)
        if m and _key(m.group(1)) in parked:
            continue
        n += 1
    return n


def orphan_materials(udir: Path, seen: dict) -> list:
    """出了材料、但**职位链接接不回抓取结果**的那些——它们上不了总览页。

    总览页靠职位链接把投递目录接回职位列表。对一个从没被 `/job-scrape` 抓到过的职位
    跑 `/job-apply`（直接粘 URL 或 JD 正文），材料是出了，但接不回去。不说出来的话，
    用户只会看到「已出材料 4 份」而总览页上只有 3 个，以为是工具算错了。

    ⚠️ 比对的是每条职位的 **`url` 字段**，不是 `seen` 的**键**。键是
    `<url>#<职位名>` 形式的去重键（51job 实测同一 URL 下挂着两个不同职位，
    只用 URL 会静默吃掉一条，见 `workflows/reference/cdp-portals.md`）——
    拿键去比会把接得上的也判成接不上。
    """
    apps = udir / "documents" / "applications"
    if not apps.is_dir():
        return []
    urls = {norm_url(e.get("url")) for e in seen.values()
            if isinstance(e, dict) and e.get("url")}
    out = []
    for d in sorted(apps.iterdir()):
        if not d.is_dir() or not (d / "outreach.md").is_file():
            continue
        url = ""
        # 冒号全半角都认——同文件的 count_materials 和面板的 parse_outreach 都是
        # `[：:]` 宽进，这里原来只认全角字面：写「职位链接: https://…」的目录，
        # 面板接得上、自检却报「接不回」，还指导用户去补一行明明存在的东西。
        for name, pat in (("outreach.md", LINK_LINE.pattern),
                          ("posting.md", r"原始链接\s*[：:]\s*(\S+)")):
            f = d / name
            if not f.is_file():
                continue
            m = re.search(pat, f.read_text(encoding="utf-8", errors="replace"))
            if m:
                url = m.group(1)
                break
        if norm_url(url) not in urls:
            out.append(d.name)
    return out


#: 材料目录里可能出现的链接。`[^\s)\]」，,、`"'>]` 收在这里，是因为链接常被
#: markdown 或中文标点包着（`（详见 https://… ）`），不收边界会把标点吃进 URL。
_URL_IN_TEXT = re.compile(r"https?://[^\s)\]」，,、`\"'>]+")


def recoverable_link(udir: Path, dirname: str, seen: dict) -> str:
    """这个「接不回去」的目录，是不是只差一行就能接回来。

    接不回去有两种原因，**给用户的说法完全不同**：

    - 职位库里根本没有这个岗（对着粘来的 JD 跑 `/job-apply`）→ 正常，没得修。
    - 职位库里有，只是 `outreach.md` 漏了 `- 职位链接：<url>` 那一行 → 一行就修好。

    原来两种混着报，而提示只写了第一种。实测一次批量投递之后 14 个目录全是
    **第二种**——用户照着提示会以为「这些岗没抓到过，正常」，于是它们永远不上
    总览页。诊断给错原因比不给更坏。

    返回同目录别处（`evaluation.md` / `posting.md`）能与职位库对上的那个链接；
    对不上、或对上多个（不猜）时返回空串。
    """
    # 归一后比，**但返回原串**：下游要把它写进 `outreach.md` 那一行，
    # 写一个剥掉协议的地址进去，点开就打不开了。
    urls = {norm_url(e.get("url")): e.get("url") for e in seen.values()
            if isinstance(e, dict) and e.get("url")}
    d = udir / "documents" / "applications" / dirname
    found = set()
    for name in ("evaluation.md", "posting.md", "outreach.md"):
        f = d / name
        if f.is_file():
            found |= set(_URL_IN_TEXT.findall(
                f.read_text(encoding="utf-8", errors="replace")))
    hit = sorted({urls[k] for k in {norm_url(x) for x in found} if k in urls})
    return hit[0] if len(hit) == 1 else ""


#: 每一步**真正会读**的资料。这张表是「分段放行」的全部依据。
#:
#: ## 为什么不是一整块
#:
#: 原来只有一道门：`candidate.md` 里还有占位符 → 一律挡住，让人去跑 `/job-setup`。
#: 可流水线各步要的东西并不一样，而最费神的那几项（能力边界、STAR 案例、行为特质）
#: `/job-scrape` 和 `/job-rank` 根本用不到。于是新用户要先花十几二十分钟做完**全部**自我
#: 剖析，才被允许去搜第一个岗——**头半小时全是输入、零产出**。
#:
#: 现在按步放行：填够搜岗的就去搜，填够排序的就去排，剩下的等 `/job-apply`、
#: `/job-interview` 真要用时再补。
#:
#: ## 挡 vs 提醒
#:
#: `block` 是「缺了这一步就做不对」——硬性条件的取值缺了，`/job-rank` 没法判硬门，
#: 只能瞎猜或静默跳过。`warn` 是「缺了会做得差些」——目标行业没填，业务领域那一维
#: 打分就没依据，但结果不至于是错的。**只有前者挡人**。
#:
#: 值是 `(文件, 小节标题)`；小节为 None 表示整份文件。小节名对不上时**不算缺**
#: （用户改了标题不该把人卡在门外）。
#: `rank` 那一档**按框架排，不按感觉排**：`04-job-evaluation.md` 第一步（硬性门槛）
#: 点名的取值就在 `明确排除`、`执业资格与证照`、`身份`（户口/应届/语言）、`教育背景`
#: 里；第二步四维要 `技能`+`工作经历`（技能与经验）、`薪资`（薪资与职级）、
#: `求职偏好`（强度与公司性质）。第一版我把「明确排除」放去了 `apply`——那是凭印象
#: 排的，翻开框架才发现它是**一票否决**那一档。
STAGE_NEEDS = {
    "scrape": {"block": [("search-queries.md", None)], "warn": []},
    "rank": {"block": [("candidate.md", "身份"), ("candidate.md", "教育背景"),
                       ("candidate.md", "薪资"), ("candidate.md", "技能"),
                       ("candidate.md", "工作经历"), ("candidate.md", "明确排除"),
                       ("candidate.md", "执业资格与证照"),
                       ("candidate.md", "求职偏好")],
             "warn": [("candidate.md", "目标行业")]},
    "apply": {"block": [("candidate.md", "明确的能力边界"),
                        ("candidate.md", "职业目标")],
              # `behavioral.md` **挂在这一档，不是「面试准备」那一档**。
              # 它原来只列在 interview 下，于是自检对用户说的是「这一项会影响
              # 面试准备」—— 而 `job-apply.md` 有**三处**在用它：Step 1 的
              # 「行为/文化参考」、Step 3 审稿者的语域检查、Step 4 的语气修订。
              #
              # 后果不是说错一句话，是**用户按它给的信息做了个合理的决定**：
              # 手上 0 个面试，那当然先不填。而那三处检查从此静默失效。
              #
              # 实测活动用户 2026-08-24：这份文件一直是占位符，
              # **243 份话术全部是在没有语域检查的情况下写出来的**；
              # `job-apply.md` 规定的那句降级说明（「behavioral.md 未填，
              # 本轮跳过语气/文化匹配校准」）在深评里只出现 57/270（21%），
              # 在话术里 **0/237**。
              #
              # 只挂一档就够：填一次两边都有。列两档会在自检里报两遍
              # （`soft` 那段按步拼串，不去重）。
              "warn": [("candidate.md", "作品与项目的分层"),
                       ("behavioral.md", None)]},
    "interview": {"block": [("interview-star.md", None)],
                  "warn": [("candidate.md", "行为特质")]},
}

#: 哪几项能用 `/job-setup --section <名>` 单独重跑。**只列 `setup.md` 真的认得的名字**
#: ——报一个它不认识的名字，用户敲下去只会白跑一轮（`test_doctor` 会去 setup.md
#: 里核对这些名字确实存在）。其余项没有单节入口，只能整跑 `/job-setup`。
SECTION_OF = {
    "搜索配置（目标城市、岗位关键词）": "search",
    "明确的能力边界": "boundaries",
    "作品与项目的分层": "boundaries",
    # `behavioral.md` 之前没有单节入口，自检只能报整跑 `/job-setup` ——
    # 而为了一份可选文件重做一遍全部资料，没人会做。Section 6 本来就同时写
    # `## 行为特质` 和 `profile/behavioral.md`，只是 `--section` 那张表里
    # 没给它名字（表里只有编号那一行「纯数字，如 9」，而编号不好记）。
    "行为特质": "behavioral",
}


def fix_for(missing, first_time: bool = False) -> str:
    """补这几项该敲什么。

    缺项全落在同一个可单跑的小节里才报 `--section`；只要掺了别的，就老实说
    `/job-setup`。原来这里按「阶段」写死：`apply` 一律报 `--section boundaries`，
    可那一档还缺「职业目标」，而 boundaries 那节根本不问它——**指了一条到不了的路**。

    `first_time`（`candidate.md` 根本不存在）一律整跑，**不许报 `--section`**：

    - `job-setup.md` 把 `--section` 定义成 **update-only flow**，它假设那份资料
      已经在盘上；
    - `--section search` 的写入目标里就有 `profile/candidate.md` 的 `[YOUR_CITY]`
      ——文件不存在时那一步无处可写；
    - `AGENTS.md` 也是这么规定的：「`profile/candidate.md` 不存在 → 尚未初始化，
      引导用户执行 `workflows/job-setup.md`」。

    > 2026-08-13 第 7 轮检查实测：新建一个用户目录、profile 全空，自检的进度段
    > 正确地报了「资料还没建」，**下一步却给出 `/job-setup --section search`**。
    > 两段自相矛盾，而用户会照着下一步敲。
    > 根因是 `STAGE_NEEDS["scrape"]` 只查 `search-queries.md`——搜岗这一档
    > 本来就不需要 candidate.md，于是缺项里只有「搜索配置」，
    > `fix_for` 看见它们全属同一节，就报了 `--section`。
    > **这个判断缺的不是逻辑，是「有没有那份资料」这个前提。**
    """
    if first_time:
        return "/job-setup"
    secs = {SECTION_OF.get(m) for m in missing}
    if len(secs) == 1 and None not in secs:
        return f"/job-setup --section {secs.pop()}"
    return "/job-setup"

STAGE_LABEL = {"scrape": "搜岗", "rank": "排序打分",
               "apply": "出投递材料", "interview": "面试准备"}

#: 整份文件缺项的说法。屏幕上不摆文件名——用户不该为了看懂提示先认识仓库的目录结构
#: （AGENTS.md「给用户看的措辞」）。按小节挡的那些直接用小节名，它们本来就是人话。
FILE_LABEL = {
    "search-queries.md": "搜索配置（目标城市、岗位关键词）",
    "interview-star.md": "面试案例（STAR）",
    "behavioral.md": "行为特质",
    "candidate.md": "候选人资料",
}

_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9_]*\]")


def placeholders(text: str) -> set:
    """一段文字里还没填的模板占位符（`[DEGREE]`、`[YOUR_NAME]` 这种）。

    **这条规则的正本。** 原来两处各编译一份同样的正则：这里，以及
    已删的 `build_dashboard._PLACEHOLDER_RE`（墓碑与合并日期在 `build_dashboard`）—— 同值、**不同名**，所以按名字找副本的
    那条守卫看不见它（`test_the_copies_in_doctor_still_match` 比的是同名的）。

    ⚠️ **那个洞 2026-09-01 补了一半。** 同一条守卫现在多了按**值**扫的
    `test_no_unregistered_aliased_copy`，当场抓出五对同值不同名的副本
    （`DATE_FORMATS`、`_OUT_PREFIXES`、`INTERVIEW_STATUSES`、`AGENCY_WORDS`、
    `OFFER_STATUSES`），全部登记进 `ALIASED_COPIES` 逐对比值。
    **但它只扫字符串集合** —— 纯数字撞车绝大多数是巧合（14 同时是
    「简历多久算旧」和「归档多久算死」），塞进登记表只会让表变成噪音。
    所以本函数这一对（一个是函数、一个是编译好的正则）仍然靠人看着。

    而它在那边的消费点是 `profile_ready`：

        return not (tokens & set(build_dashboard._PLACEHOLDER_RE.findall(text)))

    那份正则一旦认不出占位符，`findall` 返回空、交集为空、这道门就判
    **「资料已就绪」**。面板于是接着建议去抓职位、去投递，`/job-apply`
    拿一份学历和能力边界禁区全是模板的资料去核对 —— 正是 `profile_ready`
    自己那段 docstring 花十行记着的那次事故，换个变量再来一遍。
    漏检那一侧**没有兜底**：占位符认不出来只会让门更松，不会报错。

    ⚠️ **它并不是没人盯。** `test_placeholder_families_agree` 拿三种写法
    （`[YOUR_NAME]` / `[DEGREE]` / 已填好）比过两边判得一样，变异实测也确实红。
    溜得掉的是**那三种之外的**：模板哪天加一种新形状的占位符，两份正则各认
    一半时那条守卫照样绿 —— 它比的是「两边一致」，不是「两边都认得全」。

    后来合成一份。`build_dashboard` 本来就 import 本模块（依赖是单向的：
    它可以用这里，这里不能用它），所以这个方向是现成的。
    """
    return set(_PLACEHOLDER.findall(text))



def template_tokens(name: str) -> set:
    """`profile.example/<name>` 里的占位符，**现抽**，不在代码里另抄一份清单。

    抄一份的下场是模板加了新占位符、检查还认着旧的。而这正是原来那道门的毛病：
    它只认 `[YOUR_` 开头的，可模板里还有 `[DEGREE]`、`[JOB_TITLE]`、
    `[COMPANY_TYPE]` 这一大类——**实测 `candidate.md` 74 种占位符里它只看得见
    38 种，`interview-star.md` 的 20 种一种都看不见**。于是学历、院校层次这些
    硬门取值整行还是模板，自检照样说「求职资料已就绪」。

    模板不在（有人删了 `profile.example/`）就返回空集：那时这一项无从判断，
    宁可放行也不要凭一个猜出来的正则去挡人。
    """
    p = ROOT / "profile.example" / name
    if not p.is_file():
        return set()
    return placeholders(p.read_text(encoding="utf-8", errors="replace"))


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def section_of(text: str, title: str) -> str | None:
    """取标题为 `title` 的那一节正文；没有这一节返回 None。

    ## 不能挑层级，也不能要求标题一字不差

    第一版写死「只认二级标题、且标题必须等于 `title`」。**实测当场空转**：真实用户
    的 `candidate.md` 用的是 `## 候选人资料` + `### 身份 / ### 薪资 …`，比模板整整
    深一级；而「能力边界」那节的标题还带括注
    （`#### 明确的能力边界（硬缺口，绝不可在材料中含糊或夸大）`）。两条都对不上，
    于是每一节都「找不到」，按「找不到就不挡人」的兜底一路放行——**分段放行整个
    变成空转，四档全都挡不住任何东西**。

    所以：任何层级都认，标题按**前缀**比（括注、补充说明不影响识别）。

    小节的结束位置是**下一个同级或更浅的标题**——`技能` 底下的
    `#### 明确的能力边界` 是它的子节，不该把它切走；反过来，`工作经历` 里的
    `### [JOB_TITLE] - [COMPANY]` 那一行本身就全是占位符，更不能丢。
    """
    lines = text.splitlines()
    start = depth = None
    for i, ln in enumerate(lines):
        m = _HEADING.match(ln)
        if m and m.group(2).strip().startswith(title):
            start, depth = i, len(m.group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _HEADING.match(lines[j])
        if m and len(m.group(1)) <= depth:
            end = j
            break
    return "\n".join(lines[start:end])


def still_template(udir: Path, fname: str, title=None) -> bool:
    """这份资料（或其中一节）还是模板吗。

    判据是「模板里的占位符原样还在」，不是「像不像占位符」——用户自己写的
    `[TODO]` 之类不该被当成没填完。文件不存在 = 还没填。
    """
    p = udir / "profile" / fname
    if not p.is_file():
        return True
    text = p.read_text(encoding="utf-8", errors="replace")
    if title is not None:
        seg = section_of(text, title)
        if seg is None:
            return False           # 小节改名/删了：无从判断，不挡人
        text = seg
    toks = template_tokens(fname)
    if title is not None:
        tmpl = ROOT / "profile.example" / fname
        if tmpl.is_file():
            tseg = section_of(tmpl.read_text(encoding="utf-8", errors="replace"), title)
            if tseg is not None:
                toks = placeholders(tseg)
    return any(t in text for t in toks)


def profile_gaps(udir: Path, stage: str) -> dict:
    """`{"block": [...], "warn": [...]}` —— 这一步还差哪几项，人话的名字。"""
    need = STAGE_NEEDS.get(stage) or {"block": [], "warn": []}
    out = {}
    for kind in ("block", "warn"):
        out[kind] = [title or FILE_LABEL.get(fname, fname)
                     for fname, title in need[kind]
                     if still_template(udir, fname, title)]
    return out


def check_repo(want_user: str = "") -> dict:
    """返回仓库/用户状态，并逐行打印。

    `want_user` 是 `--user` 指定的人；空则读 `.active_user`。**看别人的进度不改
    指针**——`.active_user` 是「我现在是谁」，不该因为瞄一眼队友的进度就被改掉。
    """
    hr("你的进度")
    st = {"in_repo": (ROOT / "AGENTS.md").is_file() and (ROOT / "workflows").is_dir()}
    if not st["in_repo"]:
        print(f"{NO}这里不像是本项目的仓库根（缺 AGENTS.md 或 workflows/）")
        return st

    # 正本是 `_cli.read_active_user`。这里重抄一份是本文件顶上那条契约：
    # **不 import 本仓库的任何模块**（要在什么都没配好时裸跑）。
    # `test_cli_contract.test_one_implementation_of_user_resolution` 把这一处
    # 连同 `_cli.py` 一起列成仅有的两个住址 —— 它是钉住的，不是漏网的。
    au = ROOT / ".active_user"
    user = (want_user or (au.read_text(encoding="utf-8") if au.is_file() else "")).strip()
    st["user"] = user
    #: **目录不等于用户。** 判据（有没有 `profile/candidate.md`）与
    #: `_cli.all_users` 同一份，本文件不 import 仓库模块所以持副本；
    #: 两边相等由 `test_a_directory_is_not_a_user` 钉住。
    #: 空壳**要列出来**，不过滤——过滤掉的东西用户就再也找不到、删不掉。
    rows = sorted(((p.name, (p / "profile" / "candidate.md").is_file())
                   for p in (ROOT / "users").iterdir() if p.is_dir()),
                  key=lambda t: t[0]) if (ROOT / "users").is_dir() else []
    users = [n for n, _ok in rows]
    st["users"] = users
    st["user_shells"] = [n for n, ok in rows if not ok]

    if not user:
        print(f"{NO}还没有活动用户 —— 你是第一次用")
        st.update(profile_ok=False, scraped=0, ranked=0, materials=0, applied=0)
        return st

    if not _valid_user_name(user) or not _user_dir_inside(user):
        print(f"{WARN}「{user}」不是一个可用的用户名"
              "（不能是路径、`..`、绝对路径、尾点或带控制字符）")
        st.update(user_missing=True, user_invalid=True,
                  user_missing_via_flag=bool(want_user),
                  profile_ok=False, scraped=0, ranked=0, materials=0, applied=0)
        return st

    udir = ROOT / "users" / user
    if not udir.is_dir():
        if want_user:
            # 名字是 --user 传进来的，别怪罪 .active_user——指针没坏，是参数打错了。
            # 诊断给错原因比不给更坏：用户会去修一个没坏的东西。
            print(f"{WARN}--user 指定的「{user}」不存在" +
                  (f"。现有用户：{'、'.join(users)}" if users else "，且还没有任何用户"))
            if st.get("user_shells"):
                print(f"{WARN}（其中"
                      + "".join(f"「{n}」" for n in st["user_shells"])
                      + "还没建档，切过去是空的）")
        else:
            print(f"{WARN}.active_user 指向「{user}」，但 users/{user}/ 不存在")
        # 这是「指针/参数错了」，不是「资料没填」——修法是切/建用户，不是跑 /job-setup 补资料。
        st.update(user_missing=True, user_missing_via_flag=bool(want_user),
                  profile_ok=False,
                  scraped=0, ranked=0, materials=0, applied=0)
        return st

    # 空壳单独说一句。原来它们混在「共 N 个」里，用户照着切过去落进一个
    # 什么都没有的工作区，然后每条命令都说「资料还没填」——**是自检把人
    # 指进死胡同的**。实测 2026-08-24：这里报 10 个，面板上只有 8 个，
    # 差的两个正是测试留下的空目录。
    shells = st.get("user_shells") or []
    print(f"{OK}当前用户：{user}" + (f"（共 {len(users)} 个：{'、'.join(users)}）"
                                     if len(users) > 1 else ""))
    if shells:
        print(f"{WARN}其中" + "".join(f"「{n}」" for n in shells)
              + "还没建档，切过去是空的 —— 不要了就 /job-user --remove "
              + shells[0])

    st["gaps"] = {s: profile_gaps(udir, s) for s in STAGE_NEEDS}
    # 一整块「填完了没」已经不成立了——各步要的东西不一样。这里报的是**走到哪一步
    # 为止的资料够了**，因为那正好是用户下一步能不能动的依据。
    ready = [s for s in ("scrape", "rank", "apply", "interview")
             if not st["gaps"][s]["block"]]
    st["profile_ok"] = not st["gaps"]["scrape"]["block"]
    # **「一次都没建过」和「建过但缺一节」要分开**，否则会指一条走不通的路：
    # `--section` 是 update-only 流程（`job-setup.md` 的原话），它假设
    # `candidate.md` 已经在那儿——而 `--section search` 恰恰要往 candidate.md 里
    # 写 `[YOUR_CITY]`。文件都没有，那一步无处可写。
    st["profile_missing"] = not (udir / "profile" / "candidate.md").is_file()
    if st["profile_missing"]:
        print(f"{NO}资料还没建（users/{user}/profile/candidate.md 不存在）")
    elif len(ready) == len(STAGE_NEEDS):
        print(f"{OK}求职资料已就绪（搜岗、排序、出材料、面试准备都够了）")
    elif ready:
        nxt = next(s for s in ("scrape", "rank", "apply", "interview")
                   if s not in ready)
        print(f"{OK}求职资料够用到「{STAGE_LABEL[ready[-1]]}」了")
        print(f"      再往后的「{STAGE_LABEL[nxt]}」还差："
              f"{'、'.join(st['gaps'][nxt]['block'])}")
    else:
        print(f"{WARN}求职资料还是没填完的模板 —— "
              f"先补「{STAGE_LABEL['scrape']}」要的那几项就能开始")

    # 「会做得差些」的那几项：提醒，不挡人。只报**已经能动的那些步**的，
    # 否则一上来就把四步的次要缺项全倒出来，正是这个文件第 4 条要避免的。
    soft = [f"{STAGE_LABEL[s]}：{'、'.join(st['gaps'][s]['warn'])}"
            for s in ready if st["gaps"][s]["warn"]]
    if soft:
        # 「这几项」在只有一项时是错的——实测就是这个情形（只缺一项行为特质）。
        量 = "这几项" if (len(soft) > 1 or "、" in soft[0]) else "这一项"
        print(f"{WARN}{量}没填不挡事，但会影响质量 —— " + "；".join(soft))
        # **这一行原来不给命令。** 仓库那条「凡是告诉用户接下来该做什么的地方，
        # 都要把命令原样写出来」对它同样成立：他读完知道少了什么，
        # 却不知道该敲什么，只能去翻文档 —— 而这正是那条规则要替他省掉的一步。
        _names = [n for s in ready for n in st["gaps"][s]["warn"]]
        print(f"      补它：{fix_for(_names)}")

    seen_path = udir / "job_scraper" / "seen_jobs.json"
    seen = {}
    if seen_path.is_file():
        try:
            _raw = json.loads(seen_path.read_text(encoding="utf-8"))
            # **两代格式都要认。** 真实结构是 `{"seen": {…}}`，早期库顶层直接就是
            # `{key: {…}}`。正本是 `_cli.seen_of`（八个碰这个文件的工具都走它），
            # 但本文件的硬契约是「不得 import 本仓库任何模块」——所以跟下面那段
            # 折叠叠加层一样，这里内联一份。
            #
            # 少这一行的代价是**静默的**：老格式的库上 `.get("seen", {})` 恒为空，
            # 自检会说「已抓 0 个职位」并把下一步指成 `/job-scrape`——而库里可能
            # 有几千个岗。2026-08-21 实测同一个文件：`_cli.seen_of` 数出 2，这里数出 0。
            seen = _raw.get("seen", _raw) if isinstance(_raw, dict) else {}
            # **读不出来的记录在这儿就摘掉，并数一笔。**
            #
            # 值不是字典的（一条 `null`、一个字符串、一个列表）会让下游每一个
            # `e.get(...)` 当场 `AttributeError`。实测 2026-09-01：喂一条 `null`，
            # 16 个工具里 9 个吐栈回溯，本文件也在其中 —— 而它是**会话第一条**
            # 命令，契约写着「任何状态下都能跑（包括 .active_user 不存在、
            # users/ 为空、profile 还是占位符）」。崩在这儿等于把入口整个堵死。
            #
            # 别处那八个走 `_cli.stop_on_unreadable_rows`：干净地停下、不替他删。
            # **本文件不能停**，所以摘掉之后接着走，把数报出来（下面那一行）。
            # 判据是同一条，只是这儿的契约不许停 —— 不是两套判据。
            st["unreadable_rows"] = [k for k, v in seen.items()
                                     if not isinstance(v, dict)]
            if st["unreadable_rows"]:
                seen = {k: v for k, v in seen.items() if isinstance(v, dict)}
            # 用户在总览页点的「不投/已下线」在叠加层里（user_state.json），
            # 不折进来的话，自检报的数和面板对不上——「两处必须说同一个数」
            # 正是下面 skipped_urls 那段注释立的规矩。
            #
            # **语义正本是 `_cli.decided_status`**：用户决定优先，其次才是职位库
            # 自己的 `status`。别处（archive / export / prescreen / fetch_details）
            # 都是逐条调它；只有这里整批折，因为本文件的硬契约是「不得 import
            # 本仓库任何模块」（要在什么都没配好的机器上裸跑）。
            #
            # 这里原来写着「`_cli.fold_user_state` 的内联复刻，正本在那边」——
            # 而那个函数**一个生产调用方都没有**，2026-08-25 已删。
            # 指着一份没跑过的实现说「改语义时两处一起改」，等于给了颗定心丸：
            # 真正漏着叠加层的是 `fetch_details`（同一天查出来的），
            # 而没有人会去查一件「已经统一了」的事。
            try:
                _us = json.loads(seen_path.with_name("user_state.json")
                                 .read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _us = {}
            for _k, _row in (_us if isinstance(_us, dict) else {}).items():
                _e = seen.get(_k)
                if _e is None:
                    continue
                if _row.get("decision"):
                    _e["status"] = _row["decision"]
                # 「对方点开简历了吗」不是决定，是关于那次投递的一条观察 ——
                # 挂到条目上，下面统计直招那组时按 url 取得到。
                if "hr_viewed" in _row:
                    _e["hr_viewed"] = _row["hr_viewed"]
        except Exception:
            print(f"{WARN}seen_jobs.json 读不出来（JSON 损坏？），当作 0 条处理")
    st["scraped"] = len(seen)
    # **走面板那个函数，不自己数。** 原来这里是 `status == "ranked"`，把用户手标
    # 「不投」的岗排除在外——而面板的「打过分」把它们算进去（它们确实评过）。
    # 于是同一份数据，自检说 193、面板说 195，用户没有任何线索知道差在哪。
    # `_n_processed` 是同文件函数的别名，永远为真——原来这里还挂着一个
    # `if _n_processed else 自己数 ranked` 的死分支，那份「自己数」正是注释里
    # 说已经修掉的旧口径，留着只会误导下一个读的人。
    st["ranked"] = _n_processed(seen)
    st["waiting"] = n_waiting(seen)
    #: 这批放了多久。光有个数说不出「有一批该先放弃」——判据见 `waiting_age`。
    st["waiting_note"] = waiting_note(seen)
    st["waiting_stale"] = waiting_age(seen)["stale"]

    st["materials"] = count_materials(udir, seen)
    # 在线简历多久没刷。判据见 `resume_refresh_note`；勾着的渠道才算。
    try:
        import json as _j
        _pf = udir / "job_scraper" / "portals.json"
        _on = _j.loads(_pf.read_text(encoding="utf-8")) if _pf.is_file() else {}
        _on = _on if isinstance(_on, dict) else {}
    except (OSError, ValueError):
        _on = {}
    st["resume_note"] = resume_refresh_note(udir, _on)

    tracker = udir / "job_search_tracker.csv"
    n_applied = n_intv = n_offer = 0
    n_replied = n_decided = 0
    # 直招那批单拆一份。判据与已删的 `build_dashboard._why_silent` 同源：
    # 猎头代招的沉默说明不了简历的事，混在一起算会得出错的诊断。
    n_direct_decided = n_direct_replied = 0
    # 直招那组里，简历被打开过 / 没被打开过各有几个（面板上标的）。
    # 判据是 seen 里的 `hr_viewed` 字段；没标过的两边都不进。
    n_viewed = n_unviewed = 0
    hv = {e.get("url"): e.get("hr_viewed")
          for e in seen.values() if isinstance(e, dict) and e.get("url")}
    # 台账的 `source` 列存的就是原始链接，和 seen 里的 url 精确对得上
    # （实测 85 行 85 中）。对不上的**不猜**，两边都不计。
    hh = {e.get("url"): _via_headhunter(e)
          for e in seen.values() if isinstance(e, dict) and e.get("url")}
    # 哪些岗**有开场白**——零回音的诊断靠它分「简历到底有没有到对方手上」。
    # 判据见下（`outreach.md` 里有 `职位链接：` 那一行）；口径要和 `export_web_data.outcome_stats` 的
    # `chatDecided` 一致（那边看 `materials.greeting`，而那个串就是从这个
    # 文件的渠道 1 小节解析出来的，所以「有这个文件」≈「有开场白」）。
    #
    # ⚠️ **只是「≈」，而且是故意往少了算。** 这边认的是「`outreach.md` 里有
    # `职位链接：` 那一行」，面板那边还能从别处把链接找回来（`recoverable_link`
    # 管的就是这种漏了一行的目录）。实测 2026-08-24：面板 236、这边 235。
    # 少认一个的方向是安全的 —— 它只会让「大多是打招呼」这个判断更难成立，
    # 不会把没打过招呼的说成打过。**别为了对齐这一个数把面板的解析抄一份过来**：
    # 本文件不许 import 仓库内模块，抄一份就是又一处会各自漂的实现。
    greeted = set()
    _apps = udir / "documents" / "applications"
    if _apps.is_dir():
        for _d in _apps.iterdir():
            _f = _d / "outreach.md"
            if not _f.is_file():
                continue
            _m = LINK_LINE.search(
                _f.read_text(encoding="utf-8", errors="replace"))
            if _m:
                greeted.add(norm_url(_m.group(1)))
    n_chat_decided = 0
    if tracker.is_file():
        try:
            import csv
            # utf-8-sig：Excel 存出来的带 BOM，用 utf-8 读不报错但第一列列名会带上它
            from datetime import date, datetime
            today = date.today()

            def parse_date(v):
                # 人手填的 tracker 里四种写法都出现过。宽进到此为止：
                # 拿不准就返回 None，不猜 —— 同 `followups.parse_date`。
                #
                # **这行注释原来就写着「同 followups」，而它只认前两种。**
                # 少认一种的后果是静默的：解析不出 → 这条投递不计入
                # `n_decided`，而那正是零回音警报的门槛和猎头/直招分母的来源。
                # 同一行 `2026.07.12`，`/job-outcome followup` 判「该催了」、
                # 面板也数得着，自检这里当它不存在。
                # 格式表与正本相等由 `test_both_next_steps_agree` 钉住。
                v = (v or "").strip()
                for f in DATE_FORMATS:
                    try:
                        return datetime.strptime(v, f).date()
                    except ValueError:
                        continue
                return None

            with tracker.open(encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    n_applied += 1
                    s = (row.get("status") or row.get("Status") or "").strip().lower()
                    if s in OFFER_STATUSES:
                        n_offer += 1
                    elif s in INTERVIEW_STATUSES:
                        n_intv += 1
                    if s in REPLIED_STATUSES:
                        decided = replied = True
                    elif s == "withdrawn":
                        decided = replied = False   # 自己撤回的，两边都不算
                    elif s in GHOST_STATUSES:
                        decided, replied = True, False
                    else:
                        d = parse_date(row.get("date") or "")
                        decided = bool(d and (today - d).days >= QUIET_DAYS)
                        replied = False
                    if not decided:
                        continue
                    n_decided += 1
                    n_replied += replied
                    # `None` = 这条投递在库里找不到对应的岗，**不猜**它是哪种，
                    # 两边都不计。`False` 才是「确认过是企业直招」。
                    if norm_url((row.get("source") or "").strip()) in greeted:
                        n_chat_decided += 1
                    is_hh = hh.get((row.get("source") or "").strip())
                    if is_hh is False:
                        n_direct_decided += 1
                        n_direct_replied += replied
                        _v = hv.get((row.get("source") or "").strip())
                        if _v is True:
                            n_viewed += 1
                        elif _v is False:
                            n_unviewed += 1
        except Exception:
            pass
    st["applied"] = n_applied
    # 「材料备好、还没发」——`next_step` 靠它把「去发」排在「去抓」前面。
    # 直接数，不减：手动投的岗有投递记录却没有材料目录，减法会把它多减一次
    # （同 `build_dashboard.next_step` 的 `ready`，那边 2026-08-12 实测报 104 实际 105）。
    st["ready"], st["ready_strong"], st["ready_asked"] = count_ready(udir, seen)
    # 「还能投几个」「抓到但没评的有几个」——「名单见底 → 先去补货」那一支用它分岔，
    # 「一个材料都还没出」那一支用它第一岔。读不到就是 `None`，退回旧文案
    # （见 `count_restock`）。
    st["n_sellable"], st["n_unranked"] = count_restock(udir)
    # 这批放了多久、有几个已经没了。光有个数说不出「有一批该先发」——
    # 判据见 `ready_age`；那 12 个白做的材料就是这一行存在的理由。
    st["ready_note"] = ready_note(udir)
    # 投后阶段要分开数，`next_step` 才挑得出**唯一**那一条最该做的事。
    # 只有总数时它只能列一串「常用命令」，而那正是本文件第 4 条约束禁止的。
    st["interviewing"] = n_intv
    st["offers"] = n_offer
    # 零回音警报要的两个数。口径同 `build_dashboard`：只数**已经决出结果的**。
    st["replied"], st["decided"] = n_replied, n_decided
    st["direct_replied"] = n_direct_replied
    st["direct_decided"] = n_direct_decided
    st["chat_decided"] = n_chat_decided
    st["viewed_direct"] = n_viewed
    st["unviewed_direct"] = n_unviewed

    # 「已抓 2638 · 已评 2450」并排印着，中间那 188 从来没被点名 —— 读的人得
    # 自己减，减完还不知道那是不是待办（其中 6 个是已下线的死岗，见 `n_waiting`）。
    # **有才说**：正常情况下抓完就自动评了，这一段本该是空的。
    _wait = (f"（还有 {st['waiting']} 个没评，跑 /job-rank）"
             if st.get("waiting") else "")
    print(f"{OK}已抓 {st['scraped']} 个职位 · 已评 {st['ranked']} 个{_wait} · "
          f"已出材料 {st['materials']} 份 · 投递记录 {st['applied']} 条")
    # **年龄单独一行，而且只在真放旧了才出现。**
    #
    # 这批是会烂的：抓的时候只收 14 天内的（`job-scrape.md` Step 1b），而评它
    # 要花抓详情的额度 —— 这套系统里最稀缺的东西。只印一个数，读的人分不出
    # 「昨天抓的 182 个」和「放了半个月的 182 个」；后者里有一批已经在平台上
    # 关掉了，评它是白评。`archive.py` 帮不上：它明写「不碰待评的」。
    #
    # 不并进上面那行：并进去之后「跑 /job-rank」被挤到一长串从句后面，
    # 而那五个字才是这一行的用处（第一版就是那样，念起来找不到落点）。
    # **这一段要排在下面那几行提醒之前，也不许插进任何一对中间。**
    # 它说的是「底下这些数都少算了几条」—— 先说清这个，后面那些数才读得对。
    # 第一版插在「待评那一队」与「材料那一队」中间，把它们拆开了：
    # 那两行是同一个病的两半（`test_it_sits_next_to_the_waiting_note`
    # 按源码距离盯着），当场红。
    #
    # **读不出来的记录要说出来。** 上面把它们摘掉了才没崩，可摘掉不等于没事：
    # 那几行还在盘上，而且此后每一条统计都少算了它们。别处八个工具会直接
    # 停下（`_cli.stop_on_unreadable_rows`），本文件的契约不许停，所以只报。
    _bad = st.get("unreadable_rows") or []
    if _bad:
        _shown = "、".join(str(k)[:24] for k in _bad[:3])
        print(f"{WARN}职位库里有 {len(_bad)} 条记录读不出来"
              f"（{_shown}{'，另有 %d 条' % (len(_bad) - 3) if len(_bad) > 3 else ''}）"
              f"——下面的数都没算它们。这几条没被改动；"
              f"别的命令碰到它会直接停下。先看一眼那几个键，确认要不要留。")
    if st.get("waiting_stale"):
        print(f"{WARN}这 {st['waiting']} 个{st['waiting_note']}")
    # **在线简历刷新是唯一一条不靠他投递的路**（`job-resume.md` 2.6）。
    # 这一行只在真的过了阈值时出现 —— 没记过的、刚刷过的都不说。
    if st.get("ready_note"):
        print(f"{WARN}{st['ready_note']}")
    if st.get("resume_note"):
        print(f"{WARN}{st['resume_note']}")
    orphans = orphan_materials(udir, seen)
    if orphans:
        print(f"{WARN}其中 {len(orphans)} 份材料接不回职位列表、上不了总览页："
              f"{'、'.join(orphans)}")
        fixable = [n for n in orphans if recoverable_link(udir, n, seen)]
        if fixable:
            print(f"      其中 {len(fixable)} 个只是漏写了一行——职位库里有这个岗，"
                  "材料里少了「- 职位链接：<url>」。")
            print("      在对应目录的 outreach.md 头部补上这一行就接回去了"
                  "（链接在同目录 evaluation.md 里）。")
        if len(fixable) < len(orphans):
            print("      其余是对没被 /job-scrape 抓到过的职位跑的 /job-apply；不影响材料本身。")
    return st






#: 这里原来还有 `resume_unopened` / `chat_first` / `_why_silent` / `NUDGE`
#: 四件，专为「零回音 → 先催一遍，再回头审简历」那一支服务。那一支
#: 2026-08-29 按用户裁定撤掉（见 `AGENTS.md`「跟进归用户，工具不催」），
#: 它们随之没了调用方，一并删掉。
#:
#: **判据本身是对的、也验证过**（简历没被打开时改简历改不到那一份；
#: 会话渠道里对方只看得到开场白第一行）—— 撤的是「据此推一个动作」，
#: 不是这些事实。真要再用，从 git 历史里取回来比重写省事。


#: 这里原来抄着 `CHAT_FIRST_SHARE` / `VIEWED_BAD_SHARE` 两个阈值（正本在
#: `build_dashboard`）。它们只服务「零回音 → 先催一遍，再回头审简历」那一支，
#: 那一支 2026-08-29 按用户裁定撤了（`AGENTS.md`「跟进归用户，工具不催」），
#: 抄件随之没了读者。**抄件比正本更该早删** —— 正本至少还有一条自检在拿它
#: 量数据，抄件连那个都没有。


def _restock_lines(st: dict) -> list[str] | None:
    """名单见底时先说补货；没有材料时也成立。

    `build_dashboard.next_step` 的 `SHORTLIST_FLOOR` 那一支是同一件事。
    这原本写在 `ready > 0` 里面，于是「一个材料都还没出、可投只剩 1–4 个」
    这个状态漏掉了补货，自检会叫用户去 `/job-apply`，面板却说 `/job-auto`。
    用户 2026-10-14 的裁定是**名单见底时补货优先于先发**，前提不是手上
    有没有材料，而是名单够不够投一轮。
    """
    ns = st.get("n_sellable")
    if not (isinstance(ns, int) and ns < SHORTLIST_FLOOR
            and st.get("ranked", 0) > 0):
        return None
    if st.get("n_unranked", 0):
        return [f"可以投的名单快见底，而还有 {st['n_unranked']} 个抓到没评的："
                f"先跑 /job-rank 把库存评完，不够再抓", ""]
    left = f"只剩 {ns} 个" if ns else "一个都不剩了"
    lines = [f"可以投的岗位{left}——越少越不该停下找岗。"
             f"下一步：跑 /job-auto 补货，抓完会自动评分排序，接着出材料"]
    ready = st.get("ready", 0)
    if ready:
        lines += ["",
                  f"手上那 {ready} 个备好的先放着（投完回来记一笔：/job-outcome <公司>）；"]
    lines += ["", "补货有前置时间，先跑这一轮，投递才不会停摆。"]
    return lines


def next_step(env: dict, st: dict) -> list[str]:
    """只给一条下一步。顺序即优先级——先能跑起来，再往下走流水线。"""
    if not st.get("in_repo"):
        return ["先 cd 到本项目的仓库根目录再跑一次。"]

    if not st.get("user"):
        return [
            "你是第一次用。下一步：",
            "",
            "    /job-setup          # 在你的 AI 编码工具里输入这条，它会问你一串问题",
            "",
            "先在这个目录下启动你的工具——工作流、命令入口、你的资料都在这个目录里，",
            "从别的目录启动它看不到。用的是哪一家都一样。",
            "不必一次答完。先问目标城市和岗位关键词，答完这两项（约 3 分钟）就能去搜岗；",
            "薪资、学历、硬性条件在下一轮，要出投递材料时才问「你明确不做/不会什么」。",
            "最后这一项是后面所有材料诚实的前提，到时候值得如实答。",
        ]

    if st.get("user_missing"):
        users = st.get("users") or []
        if st.get("user_invalid"):
            # 名字本身非法，和「目录不存在」的修法不同：先改名字，
            # 别让他去建一个叫 `...` 的用户。
            who = ("--user 指定的" if st.get("user_missing_via_flag")
                   else "`.active_user` 里的")
            lines = [f"{who}「{st['user']}」不是一个可用的用户名"
                     "（不能是路径、`..`、绝对路径、尾点或带控制字符）。下一步：", ""]
            if users:
                lines.append(f"    /job-user 看看有哪些用户（现有：{'、'.join(users)}）")
            else:
                lines.append("    /job-user --new <名字>   # 新建一个用户（现在一个用户都没有）")
            return lines
        if st.get("user_missing_via_flag"):
            lines = [f"--user 指定的「{st['user']}」不存在。下一步："]
        else:
            lines = [f"`.active_user` 指向「{st['user']}」，但那个用户目录不存在。下一步："]
        # 推荐名从**建过档的**里挑。原来直接取 `users[0]`，而排序是按名字的——
        # 排在最前的完全可能是个空壳，那条「下一步」就把人从一个坏指针
        # 换到了另一个空目录。
        real = [n for n in users if n not in (st.get("user_shells") or [])]
        if real:
            lines += ["", f"    /job-user {real[0]}      # 切到已有用户（现有：{'、'.join(real)}）"]
        elif users:
            lines += ["", f"    /job-user --new <名字>   # 现有的 {'、'.join(users)} 都还没建档"]
            # 不再插空行：这两条是**一对备选**，中间空一行就读成了两段。
            lines += ["    /job-user --new <名字>   # 或者新建一个用户"]
        else:
            # 没有「已有用户」那一条时，「**或者**新建」就成了吊在半空的下半句。
            # 实测（干净 clone + 一个指向不存在用户的 .active_user）：整段只印出
            # 「/job-user --new <名字>   # 或者新建一个用户」——或者什么？
            lines += ["", "    /job-user --new <名字>   # 新建一个用户（现在一个用户都没有）"]
        if st.get("user_missing_via_flag"):
            lines += ["", "（多半是名字打错了——上面列了现有用户，对一眼再跑。）"]
        else:
            lines += ["", "（这是用户指针的问题，不是资料没填——跑 /job-setup 补资料修不了它。）"]
        return lines

    # 每一步问**自己**那道门，不再共用一个「资料填完了没」。
    # 原来那道门是一整块：`candidate.md` 里还有占位符就一律挡住。可它既太紧
    # （最费神的能力边界、STAR 搜岗根本用不到，却拦着不让搜），又太松
    # （`/job-scrape` 真正要的 `search-queries.md` 它压根不看——实测：自检说
    # 「资料已就绪，下一步跑 /job-scrape」，而 /job-scrape 一上来就停下说「先跑 /job-setup」）。
    def gate(stage: str):
        missing = ((st.get("gaps") or {}).get(stage) or {}).get("block") or []
        if not missing:
            return None
        first = bool(st.get("profile_missing"))
        if first:
            # 一次都没建过：说「先建档」，别说「还差这几项」——后者听起来像
            # 已经填了大半，而实际上一个字都没有。
            return [f"这个用户的资料还没建过（要{STAGE_LABEL[stage]}就得先有它）。下一步：",
                    "", f"    {fix_for(missing, first_time=True)}",
                    "", "（分四轮问，答完第一轮就能往下走，不必一次答完。）"]
        return [f"要{STAGE_LABEL[stage]}，还差这几项：{'、'.join(missing)}。下一步：",
                "", f"    {fix_for(missing)}",
                "", "（只问缺的那些，已填的不会重问。填完再跑一次自检看下一步。）"]

    if st.get("scraped", 0) == 0:
        blocked = gate("scrape")
        if blocked:
            return blocked
        tip = "" if env.get("node") else "（没有 Node，本轮会退到网络搜索兜底，结果会少一些）"
        # **给的是脊梁那条，不是它的分解。** `AGENTS.md`「一次跑到头：只有三条命令」
        # 写着新用户走 `/job-setup → /job-auto → /job-outcome`，并且专门警告
        # 「别把这条脊梁说成四步……多教一步的代价不是多敲一次，是让人以为不敲
        # 就会漏东西」。这里原来印 `/job-scrape` —— 它抓完会自动评分，但**不出材料**，
        # 敲完他手上是一排没材料的岗，还得再敲一条才走得到能发的那一步。
        return [f"资料好了，还没搜过职位。下一步：跑 /job-auto —— "
                f"抓岗、评分、出材料一条龙，中途不用盯着{tip}"]

    if st.get("ranked", 0) == 0:
        blocked = gate("rank")
        if blocked:
            return blocked
        return ["抓到职位了但还没打分。下一步：跑 /job-rank，产出带理由的排序名单。"]

    # **补货先于「先发」，且不要求手上先有材料。** 规则的正本在
    # `build_dashboard.next_step` 的 `SHORTLIST_FLOOR` 那一支；这里只是
    # 同一份规则在终端的出口。详见 `_restock_lines`。放在 `materials == 0`
    # 之前，才能覆盖「一个材料都没有、能投的只剩 1–4 个」。
    _restock = _restock_lines(st)
    if _restock:
        return _restock

    if st.get("materials", 0) == 0:
        blocked = gate("apply")
        if blocked:
            return blocked
        # 原来这里只有一句「从名单里挑一个，跑 /job-apply <职位URL>」——不可执行。
        # 排序结果写在 `seen_jobs.json` 里（机器读的），人能看的只有总览页。
        # 当场跑完 /job-rank 的人手上有那份清单，可第二天回来跑自检的人没有，
        # 而自检正是给「不知道该干什么」的人用的。整条链就这一处说不出该敲什么。
        #
        # 而且它只会一个一个教。「挑一个」在有几十个可投岗时等于叫他敲几十次；
        # `/job-apply 全部`（「除了不投的都准备好」）才是这个状态下唯一的一次敲完。
        #
        # `n_sellable` 是 0 时才走第二岔——全评了、一个都不能投，那一句该说的是
        # 「去找更多」，不是「批量出材料」（出材料那一步会一条都产不出来）。
        # 读不到（没有快照）就退回原来那句，不猜（同 `count_ready` 的约定）。
        if st.get("n_sellable") == 0:
            # 命令是 `/job-auto`，不是 `/job-scrape`（2026-10-14）。
            # 一个能投的都没有、手上也没有材料 —— `/job-scrape` 抓完自动评分
            # 却不出材料，敲完还是一排没材料的岗。`/job-auto` 一条龙跑到材料。
            # 面板那条「名单见底」的分支也刚改成同一个命令，两个出口不再分岔。
            return ["抓到职位了、也评过，但没有几个能投的（硬性条件没过，或者分太低）。"
                    "下一步：跑 /job-auto 接着找 —— 抓岗、评分、出材料一条龙，"
                    "中途不用盯着；或者回头调整 profile 里的硬性条件与期望。"]
        lines = ["排好了，排序名单在总览页上。下一步："]
        if not env.get("web_build"):
            lines += ["",
                      "    cd web && npm install && npm run build   # 只需要一次",
                      "    cd .. && python tools/serve.py           # 打开总览页"]
        else:
            lines += ["", "    python tools/serve.py      # 打开总览页，看排序和该问的问题"]
        lines += ["",
                  "    /job-apply 全部           # 把除了不投的都备好料",
                  "",
                  "（总览页上「不投 / 我投了」这类记号点一下就写回盘上。）"]
        return lines

    if st.get("applied", 0) == 0:
        # 原来这里写「下一步二选一」并列了 /job-outcome 与 /job-dashboard —— 违反本文件
        # 第 4 条约束。两者不等价：记一笔是**后面所有环节的前提**（跟进、备面、
        # 报表都靠它），看总览只是可选。挑那条要紧的。
        return [
            "材料写好了，但一条投递记录都还没有。下一步：",
            "",
            "    /job-outcome <公司>     # 投出去之后回来记一笔",
            "",
            "后面的跟进、面试准备、投后报表都从这条记录长出来；不记就都接不上。",
        ]

    # 投出去之后还是只给一条 —— 顺序即优先级，钱 > 面试 > 补充名单。
    # 原来这里一次列了 /job-scrape · /job-outcome · /job-interview · /job-dashboard 四条，
    # 正是本文件第 4 条说的「给三条并列选项等于没给」。
    if st.get("offers", 0):
        return [f"有 {st['offers']} 个 offer 在手。下一步：跑 /job-offer <公司> —— "
                "算可守区间、过一遍背调红线（报的数字要和个税记录对得上）。"]
    if st.get("interviewing", 0):
        blocked = gate("interview")
        if blocked:
            return [f"有 {st['interviewing']} 个岗进了面试。"] + blocked
        return [f"有 {st['interviewing']} 个岗进了面试。下一步：跑 "
                "/job-interview <公司> 备面，它会出题并陪你练。"]
    # ── 零回音**不再给出「下一步」** —— 用户 2026-08-29 裁定 ──
    #
    # 原话：「job-outcome followup 是干嘛的，我之前不是说了没必要 followup 吗，
    # 真有反馈，应该用户自己去跟进，在这里记录意义不大」。
    #
    # 这里原来有一整支：投出去一片、一个回音都没有时，把「先催一遍」
    # （`/job-outcome followup`）印成唯一的下一步，后面还接一段解读
    # （是简历的问题 / 是开场白的问题 / 是时机的问题）。整支撤掉，
    # 状态交给下面的流水线判据（有材料没发 → 先发；没有 → 接着抓）。
    #
    # **注意这条裁定此前说过一次，而谁也没写下来** —— 于是它今天原样冒了
    # 出来，用户第二次说同一句话。规则只活在一次会话里，换一轮就整条丢掉；
    # 正本现在在 `AGENTS.md`「跟进归用户，工具不催」那一节。
    #
    # 撤的是**推动作**，不是数据：`decided` / `replied` / `_why_silent`
    # 都还在，投后分析（`/job-html-report`）照常算回复率。
    # `/job-outcome followup` 这条命令本身也保留 —— 他想催的时候敲得到，
    # 只是工具不再替他决定该催了。

    # **发出去优先于再去抓。** 这一条原来不存在：只要投过一次、又没在面试，
    # 就无条件说「跑 /job-scrape 补充名单」——手上 107 份材料备好没发也照说。
    # 而同一时刻面板说的是「还有 107 个岗材料就绪但没投」。
    # 两个入口给相反的建议，用户看哪个算哪个（2026-08-13 实测撞上）。
    #
    # 口径与 `build_dashboard.next_step` 的 `ready` 一致：**直接数「有材料且没投」**，
    # 不拿 materials − applied 去减（手动投的岗有投递记录却没材料目录，减法会多减）。
    ready = st.get("ready", 0)
    if ready > 0:
        def _send_and_record() -> list[str]:
            """「发出去 → 记一笔」那套收尾。

            它只有备好的发得出去时才成立 —— 所以它是一个函数、
            由 `ready_strong` 那一支挑，而不是这一支默认的尾巴。
            全是「可以考虑」时用它，等于在同一屏里说「别当群发名单」
            又说「发完点一下我投了」。
            """
            return [
                "    python tools/serve.py     # 打开总览页，展开一个岗，开场白点一下就复制",
                "",
                "发完在那一行点「我投了」就记上了（也可以跑 /job-outcome <公司>）。",
                "名单见底了再去 /job-auto 补货，先把备好的用掉。",
            ]
        # **按判词分两档说。** 「可以考虑」那一档按框架的定义是「先问清楚关键信息
        # 再决定」，不是可以直接发；和「值得投」加成一个数去催人发，等于替用户
        # 做了他还没做的决定。2026-08-13 实测：这里报的 63 里有 59 个是「可以考虑」，
        # 真正备好能直接发的只有 4 个。
        strong = st.get("ready_strong")
        if strong is None or strong == ready:
            head = f"有 {ready} 个岗材料备好了还没发出去。下一步：把它们发出去 —— "
            tail_lines = _send_and_record()
        elif strong == 0:
            head = (f"备好的 {ready} 个都是「可以考虑」这一档——先问清楚再决定，"
                    f"不是直接发。下一步：")
            # 一个都发不出去时，不能把他推向「发完记一笔」。
            # 那一档缺的是「投前必问」——`04` 规定写不出来就说明它不属于这一档，
            # 所以 `/job-apply 可以考虑` 逼每个岗自己结一次案。
            # 都列了要问什么的话没有什么可敲的，而这一支的判据是「给他一条命令」。
            asked = st.get("ready_asked")
            if isinstance(asked, int) and asked >= ready:
                tail_lines = ["    python tools/serve.py     # 打开总览页，挨个看过去",
                              "",
                              "这些岗的评估里都列了要问什么——先问清楚，再决定投不投。",
                              "名单见底了再去 /job-auto 补货。"]
            else:
                tail_lines = ["    /job-apply 可以考虑         # 一次补齐那几个岗缺的「投前必问」",
                              "",
                              "（补完挨个看过去：问清楚关键信息，再决定投不投。"
                              "这一档不是群发名单。）"]
        else:
            # **「投之前先问清楚」默认那份清单存在，而多数岗上没有。**
            # 实测活动用户 2026-08-30：这一档 56 个里只有 9 个列了要问什么。
            # 指一份不存在的东西，比不提更坏 —— 他会去找，找不到，
            # 然后连带不信这一整句。面板上早就分两枚章说清了，终端这句没有。
            # 数从导出器来（`nextStep.readyAsked`），拿不到就不多说这半句。
            maybe = ready - strong
            asked = st.get("ready_asked")
            # **「展开看那一行会说怎么补」不是下一步。** 那是指一个地方，
            # 而 `AGENTS.md`「每一处引导都要写出该敲的命令」的判据是
            # 「读完这句他能不能直接动手」—— 指地方要他先去找，而这件事
            # 只有一个答案（`/job-apply 可以考虑`：已有材料的只补缺的那一节，
            # 不重跑深评）。同一个形状 2026-08-31 刚在自检收尾修过一次
            # （那句「照下面那几条各自的链接一个一个跑」，而下面只有两条）。
            #
            # 「下一步」仍然只有一条（把它们发出去）；这是括号里的次要建议，
            # 按 `doctor` 顶上第 4 条的说法「写进正文即可，别和它并列」。
            tail = ("" if not isinstance(asked, int) or asked >= maybe else
                    f"——不过只有 {asked} 个的评估里真列了问题，"
                    f"其余 {maybe - asked} 个没写；一次补完：/job-apply 可以考虑")
            head = (f"有 {strong} 个「值得投」的材料备好了，先发这批"
                    f"（另外 {maybe} 个是「可以考虑」，投之前先问清楚{tail}）"
                    f"。下一步：把它们发出去 —— ")
            tail_lines = _send_and_record()
        return [head, "", *tail_lines]
    # **这一句踩了 2026-08-29 那条裁定的两半。** 原文（`AGENTS.md`
    # 「跟进归用户，工具不催」）：「**终端与面板的「下一步」都不提投递与回音**，
    # 状态照常按流水线判：有材料没发 → 先发；没有 → `/job-auto` 接着抓。」
    #
    # 而它原来写的是「投出去了，在等回复。下一步：跑 `/job-scrape` 补充名单」——
    # 前半句正是那条裁定不许提的东西（国内回音基本走平台站内信，这个工具一条都
    # 读不到，据一个读不全的数去解读用户的处境本来就不成立），后半句给的命令
    # 也和裁定点名的那条不一样。**同一个文件上面那支已经写对了**
    # （「名单见底了再去 /job-auto 补货」）—— 两支相邻，答案不同。
    return ["手上没有备好的材料了。下一步：跑 /job-auto 接着抓 —— "
            "抓岗、评分、出材料一条龙，中途不用盯着。"]

def detect_code_tool() -> str:
    """探测当前跑在哪个 AI 编码工具里。

    正本是 `_cli.detect_code_tool`。本文件顶上的契约不许 import 仓库模块，
    这里保一份**逐字副本**；两份判得一样由
    `tests/test_code_tool_detection.py` 钉死，改一处必须改另一处。
    信号怎么来的（全是实测、不许写「看着像」的变量名）见正本 docstring。
    """
    override = os.environ.get("JOBS_CODE_TOOL")
    if override:
        return override.strip().lower()
    if (os.environ.get("ANTIGRAVITY_AGENT")
            or os.environ.get("ANTIGRAVITY_AGENTAPI_EXE")
            or os.environ.get("ANTIGRAVITY_LS_VERSION")):
        return "antigravity"
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if os.environ.get("QODERCN_CLI") or os.environ.get("QODER_AGENT_SDK_ENTRYPOINT"):
        return "qoder"
    if os.environ.get("QWEN_CODE"):
        return "qwen"
    if os.environ.get("MIMOCODE"):
        return "mimo"
    if os.environ.get("MAVIS_SESSION_TRANSFER_CLIENT"):
        return "mavis"
    return "generic"


#: 自检末尾那一行要叫得出工具名（每家都印，见 `main` 那段）。
#: （cursor / codex 自动探测分不出来，只能手工指定；qoder 两边都在。）
_TOOL_LABELS = {
    "antigravity": "Antigravity（agy）",
    "claude": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "mavis": "MCode",
    "mimo": "MiMo Code",
    "qoder": "Qoder",
    "qwen": "Qwen Code",
}

#: 给用户敲的斜杠命令。前面贴着单词 / 点 / 斜杠 / 连字符的不动——
#: 那是路径（workflows/job-apply.md）或 URL 里的片段，不是命令。
_SLASH_CMD = re.compile(r"(?<![\w./-])/(job-[a-z][a-z-]*)")

#: 每家工具的命令语法。逐家实测过：认得出来的那些**几乎都吃斜杠**，只有 Codex
#: 把 `/` 留给自己的内置指令（最新一轮的数与翻过来的理由见下面那段）。各家怎么认的：
#: Claude Code 的技能进它的斜杠表；Qoder 的 harness 自己写着技能可按 `/<名>` 请求；
#: agy 的 `/` 面板用户当场测过（`/job-scrape` 能匹配）；Qwen Code 0.24.7 起把技能
#: 注册成 `/<技能名>`；MiMo Code 的技能以 `source: "skill"` 进它的命令表；
#: MCode 同形态（2026-10-13 用户确认，`MAVIS_SESSION_TRANSFER_CLIENT`
#: 是量出来的信号）。Codex 那条是它二进制自己印着的：
#: `Unrecognized command '/-'. Type "/" for a list of supported commands.`
#: 这一格原来只把 `claude` 放进 `"slash"`、其余全去斜杠，理由写的正是「斜杠会被
#: 客户端当成内置指令拦掉」——**那句话对逐家实测出来吃斜杠的那几家全是错的**，
#: 白扣了斜杠这一层形式。Gemini CLI 那家已停（后继是 agy），它的格子已整档删掉。
#: Codex 没有可用的探测信号（`CODEX` 这个变量不存在），自动探测落 `"generic"`。
#
#: ## 2026-10-13：`generic` 从免斜杠翻成带斜杠
#:
#: **原来 `generic` 是免斜杠那一档**，理由是「裸形式各家都敲得动（触发词接得住），
#: 留着一个敲不动的斜杠则每一条引导都作废」。前半句在 harness 里不成立：
#: 裸形式不是命令，只是聊天框里的一段文字——触发词接得住的是**模型**，
#: 不是**宿主**，而这一页给的每一条都是「敲这个」。
#:
#: 后果当场可见（同一屏两种形态）：流水线格子与弹层里的 `<Cmd>` 走了
#: `formatCommand`、被剥成 `job-scrape`，而「下一步」那行是纯文本、
#: 原样留着 `/job-outcome <公司>`。实测这台机器跑在 MCode 里
#: （`detect_code_tool()` 返回 `generic`），复制按钮复制下来的是**敲不动的命令**。
#:
#: 翻过来的三条理由：
#:   1. `docs/tool-entries.md` 量过 12 家，**8 家吃斜杠**；「认不出来」更可能
#:      落在吃斜杠的那一边。
#:   2. 两种错法的**可见性不同**：带错斜杠，工具会报错或列出命令；
#:      缺斜杠，用户根本不知道有这条命令（`AGENTS.md`「用户不知道该敲什么」）。
#:   3. 真拦的那一家（Codex）现在**自己一格**，不再靠 generic 兜底。
#:
#: 代价说清楚：**探测不到 Codex 的人会拿到敲不动的斜杠**——它没有可用的环境变量，
#: 只能 `JOBS_CODE_TOOL=codex` 或用面板上的开关（`CodeToolContext.setSlashMode`，
#: 2026-10-13 把它接上了界面；此前它零调用点，是条死路）。
#: `cursor` 同理：`_TOOL_LABELS` 里有它，吃不吃斜杠没实测过，所以**不给它格子**，
#: 让它落 generic（带斜杠）—— 与「认不出来按多数派」同一条判据，不是漏了。
#:
#: `detect_code_tool` 自动探测能返回的每一个值都要在这里有一格，见
#: `tests/test_slash_survives_where_the_palette_is_the_skill_list.py`
#: （它把那张表的键与探测函数源码里的 `return` 字面量逐条对拍 —— 值是从源码数的，
#: 不是比另一份手抄名单，加一档忘了给格子就会红；同一个文件还钉着面板那份抄件）。
COMMAND_SYNTAX = {
    "claude": "slash",
    "antigravity": "slash",
    "mimo": "slash",
    "mavis": "slash",
    "qoder": "slash",
    "qwen": "slash",
    "generic": "slash",
    "codex": "no-slash",
}


def command_syntax(tool: str) -> str:
    """这一档给不给斜杠。

    **没实测出来的工具按 `"generic"` 那一档走，而它 2026-10-13 起是带斜杠**：
    实测 12 家里 8 家吃斜杠，而认不出来的那一批更可能落在吃斜杠的一边；
    真拦的（Codex）自己一格。这段理由的完整版在 `COMMAND_SYNTAX` 上方。
    """
    return COMMAND_SYNTAX.get(tool, COMMAND_SYNTAX["generic"])


def adapt_commands(text, tool: str) -> str:
    """把文档正本的斜杠命令改写成当前工具能敲的形式。

    **文档正本（`AGENTS.md`、`workflows/`、`workflows/INDEX.md`）里一律保留斜杠**
    ——那是标准形式；改写只发生在给用户看的最终渲染层。实测吃斜杠的六家
    （Claude Code / agy / MiMo / MCode / Qoder / Qwen）与认不出来的那一批原样返回，
    只有 Codex 那一档去斜杠。
    """
    if not isinstance(text, str):
        return text
    if command_syntax(tool) == "slash":
        return text
    return _SLASH_CMD.sub(r"\1", text)


class _CommandStream:
    """包一层 stdout，让整份 doctor 输出统一按工具适配。

    全文有 48 个 print 调用点、70 处命令字符串，逐处改必漏；适配逻辑只有
    一处，就该只有一个落点。除 write/writelines 外的属性全部委托原流。
    """

    def __init__(self, raw, tool: str):
        self.raw = raw
        self.tool = tool

    def write(self, s):
        return self.raw.write(adapt_commands(s, self.tool))

    def writelines(self, lines):
        self.raw.writelines(adapt_commands(s, self.tool) for s in lines)

    def flush(self):
        self.raw.flush()

    def __getattr__(self, name):
        return getattr(self.raw, name)


def main(argv=None) -> int:
    # argparse 是标准库，不违反本文件顶上第 1 条约束（不 import 本仓库的模块）。
    # 从前这里不解析参数：`doctor.py --help` 会**照常跑完整个自检**，而
    # `--user 张三` 被静默吞掉、报的是活动用户的进度。
    import argparse
    ap = argparse.ArgumentParser(
        description="查环境、查进度、告诉你下一步做什么（只读，不改任何东西）")
    ap.add_argument("--user", metavar="用户名",
                    help="看某个用户的进度，默认读 .active_user（不会改它）")
    # `argv=None` 表示**没有参数**，不是「去读 sys.argv」。别的模块（测试、
    # 导出器）会直接调 `main()`；默认去偷 sys.argv 的话，它吃到的是 pytest
    # 自己的命令行，当场 `SystemExit(2)`。真正的入口在下面显式传 sys.argv[1:]。
    args = ap.parse_args([] if argv is None else argv)

    # 在任何输出之前定工具、包 stdout：自检的每一段（环境、建档引导、下一步）
    # 都可能出现命令，包裹必须覆盖全程。
    tool = detect_code_tool()
    raw_stdout = sys.stdout
    if command_syntax(tool) != "slash":
        sys.stdout = _CommandStream(raw_stdout, tool)
    try:
        return _main_body(args, tool)
    finally:
        sys.stdout = raw_stdout


def _main_body(args, tool: str) -> int:
    print()
    print("=" * 66)
    print("  AI 求职助手 —— 环境与进度自检")
    print("=" * 66)

    st = check_repo((args.user or "").strip())
    if not st.get("in_repo"):
        for line in next_step({}, st):
            print(line)
        return 1
    env = check_env()

    hr("下一步做什么")
    for line in next_step(env, st):
        print(line)

    # 「这批命令是按哪家工具的形式给的」这一行，每家都印。
    # 原来只有去斜杠那几家印 —— 于是探测错了的人在输出里
    # 找不到任何线索，而 `JOBS_CODE_TOOL` 那条手工纠正正是给他准备的。
    # 措辞上只说他看到的这一种，**不并列另一种形式让他挑**：那等于把
    # 「你的工具是哪一家」这道判断退回给用户。
    print()
    label = _TOOL_LABELS.get(tool)
    if command_syntax(tool) == "slash":
        print(f"💡 已识别为 {label}：上面的命令带开头的斜杠（如 /job-auto），"
              "直接粘进对话框即可。")
    elif label:
        print(f"💡 已识别为 {label}：上面的命令不带开头的斜杠，"
              "直接粘进对话框即可；也可以直接把要办的事说出来，比如「自动跑一轮」。")
    else:
        print("💡 没认出你在用哪家助手：上面给的是不带开头斜杠的写法，哪家都敲得动；"
              "也可以直接把要办的事说出来，比如「自动跑一轮」。")
    # 这串可选值**从 `COMMAND_SYNTAX` 派生**，不是手抄的字面量 —— 手抄那版
    # 在删掉 gemini、加上 qwen/mimo 之后不会有任何测试变红，印出的纠正办法
    # 就会指向一个已经删掉的档。
    print("   认错了手工指定：JOBS_CODE_TOOL="
          + "|".join(COMMAND_SYNTAX))

    print()
    print("完整说明：README.md（快速开始） · 安装细节：SETUP.md · 全部命令：AGENTS.md")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
