"""命令行入口的共同规矩。

## 为什么单独有这个文件

全面检查时把每个工具都敲了一遍 `--help`，结果没有一个是帮助：

- `export_web_data.py --help` **真的重跑了导出、重写了 data.json**
- `doctor.py --help` 照样把活干完
- `serve.py --help` 直接起了 HTTP 服务器**卡住不返回**

`--help` 干活只是表症。真正的毛病是这几个工具**根本不解析参数**——你敲什么它都
当没看见。而仓库里另外六个工具（`gap_split`、`prescreen`、`followups`、`jd_store`、
`fetch_details`、`template_usage`）**是认 `--user` 的**。也就是说 `--user` 已经是
这个仓库的词汇，肌肉记忆是现成的：

    python tools/export_web_data.py --user bob

多人共用一份 clone 时，这条命令会**把 alice 的数据导成 bob 的面板，并报成功**。
没有任何提示说 `--user` 被吞了。这正是本仓库反复在清的那个形状——**静默地做错，
而且看起来像成功**。

## 规矩

碰每用户数据的命令行工具，必须：

1. `--help` 只说明用法，**不干活**
2. 认 `--user`，语义与已有的六个一致（覆盖 `.active_user`，只影响这一次）
3. **不认识的参数一律报错退出**，绝不静默忽略

`tests/test_cli_contract.py` 按 `tools/*.py` 枚举检查，新加的工具自动纳入。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def force_utf8_output() -> None:
    """管道/重定向时把 stdout、stderr、stdin 定到 UTF-8。**import 本模块即生效。**

    ## 为什么需要

    Windows 上 Python 只有在 stdout 是**真终端**时才走 WriteConsoleW（Unicode 直通）。
    一旦被管道接走或重定向到文件，就回落到 `locale.getpreferredencoding()`——
    中文 Windows 上是 **cp936（GBK）**。于是：

        python tools/export_web_data.py --user 查无此人
        # stderr 实际吐出 b'\\xc3\\xbb\\xd3\\xd0...' —— GBK 字节

    而 Git Bash、VS Code 终端、Windows Terminal 都按 UTF-8 解，用户看到的是一屏乱码。
    这个仓库引导新人**全靠终端提示**（`doctor.py` 的「下一步」），乱码等于引导失效。
    更糟的是往 cp936 流里打一个它编不出的字符（emoji、特殊符号）会直接
    `UnicodeEncodeError` 崩掉，而不是显示成问号。

    ## 为什么只在非 tty 时改

    真终端那条路本来就是对的（WriteConsoleW 不受代码页影响）。如果连 tty 也强行
    reconfigure 成 UTF-8，代码页仍是 936 的传统 cmd.exe 反而会开始乱码——
    等于把问题从一群人手上挪到另一群人手上。只修真正坏掉的那条路。

    ## stdin 是同一个坑的另一半（2026-09-03 发布前实测）

    读的那头一样回落到 cp936：喂进去的 UTF-8 字节被按 GBK 解，
    **进程里拿到的是一串乱码，而且它不报错**。两个消费方都在要害上：

        python tools/check_outreach.py --stdin   # 话术闸门：乱码里一条规则都命不中 → 印 ✓
        python tools/jd_store.py --save - ...    # 粘一整段职位描述进来 → 存进去就是坏的

    第一个正是「0 和坏了长得一样」的第四次（前三次记在 `check_outreach.problems_in`）：
    闸门对一份踩线的话术印了 ✓，因为它查的是乱码。

    ## 历史

    `tests/test_doctor.py` 曾给子进程设 `PYTHONUTF8=1, PYTHONIOENCODING=utf-8` 才变绿——
    **它把用户真实遇到的条件配置掉了**。同期 `test_cli_contract` 没设、照实撞见乱码而变红，
    于是那条红的被当成「环境问题」放了很久。红的那条才是诚实的。
    """
    for s in (sys.stdout, sys.stderr, sys.stdin):
        if s is None or not hasattr(s, "reconfigure"):
            continue
        try:
            if not s.isatty():
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:      # 流已关闭/被替换成非文件对象时不该连累主流程
            pass


force_utf8_output()


def all_users(root=None) -> list[tuple[str, bool]]:
    """`users/` 下的全部目录，外加一位：**这个名字底下有没有建过档**。

    返回 `[(名字, 有 profile/candidate.md), ...]`，按名字排序。

    ## 为什么要有这个函数：目录不等于用户

    2026-08-24 在活动用户的真实仓库里数了一遍，四个地方各写各的：

        tools/doctor.py       目录就算            → 共 10 个
        tools/serve.py        目录就算            → 共 10 个
        tools/_cli.py         目录就算            → 共 10 个
        tools/export_web_data.py  要有 candidate.md → 共 8 个（面板上就是 8 个）

    同一份 clone，终端说 10 个、面板说 8 个。差的那两个是 `users/张三/` 和
    `users/谁/`——**测试留下的空壳**（前者只有一个 `portal_budget.json`，
    后者连文件都没有，只剩一个空的 `job_scraper/`；两个的时间戳都停在
    2026-08-19，正是 `fetch_details.run` 那条 `budget` 注入修掉的那个坑）。

    数字对不上只是表症，真正的代价是 doctor 那行把「谁」当成可切换的用户报出来：
    照着切过去，落进一个什么都没有的工作区，然后每条命令都说「资料还没填」——
    **是工具自己把人指进死胡同的**。

    所以判据统一到这里，并且**不是二选一地过滤掉空壳**：空壳要列出来、并标明
    它是空壳，用户才找得到它、删得掉它（`/job-user --remove <名>`）。
    半路建了一半的用户同样靠这个才看得见——直接过滤掉的话，它就永远隐身。

    面板那份仍然只列建过档的，那是**另一件事**：那个弹层里每一行都配一条
    `/job-user <名>` 让人点着切过去，而切到空壳是死胡同。理由记在
    `export_web_data` 的 `allUsers` 那里。
    """
    base = Path(root) if root is not None else ROOT
    d = base / "users"
    if not d.is_dir():
        return []
    return sorted(((p.name, (p / "profile" / "candidate.md").is_file())
                   for p in d.iterdir() if p.is_dir()),
                  key=lambda t: t[0])


def user_list_line(root=None, *, active: str = "") -> str:
    """把 `all_users()` 说成一句给用户看的话。空壳单独拎出来并给出删法。"""
    rows = all_users(root)
    if not rows:
        return "还没有任何用户"
    real = [n for n, ok in rows]
    shell = [n for n, ok in rows if not ok]
    out = "、".join(f"{n}（当前）" if n == active else n for n in real)
    line = f"共 {len(real)} 个：{out}"
    if shell:
        # 不说「空壳」——那是内部词。说它现在是什么、以及怎么处理。
        line += ("；其中" + "".join(f"「{n}」" for n in shell)
                 + "还没建档，切过去是空的 —— 不要了就 /job-user --remove "
                 + shell[0])
    return line


#: `--user` 的说明。**这一份是正本。** 11 个工具原来一字不差各写一遍，
#: 另有 5 个干脆没写 —— 那 5 个的 `--user` 在 `--help` 里是一行光杆，
#: 用户读完不知道不给它会怎样。
#:
#: `doctor` / `serve` / 本文件不用它：它们各自的说明多一句「不会改`.active_user`」，
#: 那是**它们独有的**保证（看别人的进度不该改我现在是谁），不是抄件。
HELP_USER = "活动用户，默认读 .active_user"


def help_apply(what: str = "写盘") -> str:
    """`--apply` 的说明。**「不加就是试运行」这半句不能省。**

    本仓库每个写盘的工具都默认试运行 —— 这是最要紧的一件事，而实测2026-08-31，
    12 个带 `--apply` 的工具里有 4 个（`score` / `name_the_exclusion` /
    `outreach_header` / `trim_opening`）**整份 `--help` 从头到尾没提过它**：
    那一行只写「真的写盘」，用户读完不知道裸跑会不会写。

    `what` 说的是**这个工具写什么**（写盘 / 写回 seen_jobs.json / 发请求）——
    那半句带信息，不该统一掉；统一的是后半句那个约定。
    """
    return f"真的{what}。不加就是试运行"


#: 试运行跑完那一句。**和 `help_apply` 是同一个约定的两半**：那半句在
#: `--help` 里说「不加就是试运行」，这半句在跑完时说「刚才确实没写」。
#:
#: 七个工具原来一字不差各写一遍（`archive` / `jd_store` / `name_the_exclusion` /
#: `outreach_header` / `prescreen` / `score` / `trim_opening`）。而 `archive`
#: 自己的注释里写着「仓库里**六个**工具都印」—— 数都数不准了，正是七份各活各的
#: 的样子。这句话是用户判断「刚才那一下动没动盘」的唯一依据，七处任何一处漂了，
#: 漂的那个工具就在骗人。
DRY_RUN_NOTE = "试运行，没有写盘。确认无误后加 --apply"


#: 用户名里不允许出现的字符。它们要么是路径分隔符，要么在 Windows 上会被
#: 解释成盘符/通配符；`..`、`.` 单独再挡一次。
_USER_BAD = set('/\\:*?"<>|')
#: Windows 的设备名。`users/CON` 会被解释成设备，不是目录；带扩展名
#: （`CON.txt`）也一样。
_USER_RESERVED = ({"CON", "PRN", "AUX", "NUL"}
                  | {f"COM{i}" for i in range(1, 10)}
                  | {f"LPT{i}" for i in range(1, 10)})


def valid_user_name(name: str) -> bool:
    """`name` 能不能当 `users/` 下的一个直接子目录名。

    **只看目录是否存在不够。** `Path(root) / "users" / ".."` 就是仓库根，
    `Path(root) / "users" / "/tmp"` 会整个跳出 `users/`；两者都满足
    `is_dir()`。名字错成那样时，后续的职位库、额度、token 都会跟着落到
    `users/` 之外。这里把「名字」与「路径」分开。

    **Windows 的路径归一化还有一类别名。** `users/...` 会解析成 `users/`
    本身（`Path.resolve()` 实测），而 `users/alice.` 会解析成
    `users/alice`；两者都能通过「不是 `..`、不是绝对路径」的旧判据。
    所以尾点、纯点、Windows 设备名都要单独挡掉。
    """
    name = (name or "").strip()
    if not name or name in (".", "..") or not name.strip("."):
        return False
    if name.endswith("."):
        return False
    if name != Path(name).name:
        return False
    if any(c in _USER_BAD for c in name):
        return False
    if any(ord(c) < 32 for c in name):
        return False
    if name.split(".")[0].upper() in _USER_RESERVED:
        return False
    return True


def _user_dir_is_inside(base: Path, name: str) -> bool:
    """即便名字通过了字符判据，也再验一次它解析后仍是 `users/` 的直接子目录。

    `...` 这类 Windows 别名靠字符表挡；这一道防的是还没想到的归一化规则。
    """
    try:
        root = (base / "users").resolve()
        return (root / name).resolve().parent == root
    except OSError:
        return False


def pick_user(explicit: str = "", *, root=None) -> str:
    """定出这一次操作哪个用户。**只做解析，不碰参数**——给已经有自己 argparse
    的工具用（`prescreen` / `followups` / `gap_split` / `fetch_details`）。

    ## 为什么要抽出来

    那四个工具原来各写一行 `(ROOT / ".active_user").read_text(...)`，**不判存在**。
    在一份全新 clone 上（`.active_user` 还没有）敲它们中的任何一个，得到的是一坨
    `FileNotFoundError` 栈回溯——而不是「先跑 /job-setup」。

    新用户敲错顺序是常态，第一次撞见的不该是 traceback。`doctor.py` 顶上那条约束
    说的就是这件事：「任何失败都会让新用户在第一步就撞墙——而这正是它要消除的体验」。

    找不到时**不返回**，带非零码退出并说清下一步。
    """
    base = Path(root) if root is not None else ROOT
    if explicit and explicit.strip():
        user = explicit.strip()
        if not valid_user_name(user) or not _user_dir_is_inside(base, user):
            # 名字不能当目录名，和「用户不存在」是两件事：前者要先改参数，
            # 后者可以去建。都用同一句「没有叫 X 的用户」会让用户去建一个
            # 名字本身就非法的用户。
            rows = all_users(base)
            print(f"「{user}」不能当用户名 —— 不能是路径、`..`、绝对路径、"
                  "尾点或带控制字符。" +
                  (user_list_line(base) if rows
                   else "一个用户都还没有——先跑 /job-setup"),
                  file=sys.stderr)
            raise SystemExit(2)
        if not (base / "users" / user).is_dir():
            # 列表走 `all_users`：空壳也列，但要标出来。原来这里只报名字，
            # 用户从里面挑一个空壳切过去，换来的是同一句「资料还没填」。
            rows = all_users(base)
            print(f"没有叫「{user}」的用户。" +
                  (user_list_line(base) if rows
                   else "一个用户都还没有——先跑 /job-setup"),
                  file=sys.stderr)
            raise SystemExit(2)
        return user

    user, msg = read_active_user(base)
    if msg:
        print(msg, file=sys.stderr)
        raise SystemExit(1)
    return user


def read_active_user(base=None) -> tuple[str, str]:
    """读 `.active_user`，返回 `(用户名, 毛病)` —— 没毛病时毛病是空串。

    **`.active_user` 只在这里被读一次。** 返回名字而不只是诊断，是为了让调用方
    不必「诊断完再自己读一遍」—— 那一读就是下一份实现的落点，而守卫盯的正是
    「除了本文件和 `doctor.py`（钉住的独立副本），没有第二个地方读这个指针」。

    **两种故障要分开说，因为修法不同**（`AGENTS.md`「会话开始」那节）：
    一个用户都没有 → `/job-setup` 建档；指针指着一个不存在的目录 ——
    那是**指针坏了**，`/job-setup` 修不了它（它只会再建一个新用户，
    原来那份数据仍然找不到），要跑 `/job-user`。

    抽出来是因为它有过两份。`pick_user` 分得开，而 `serve.py` 的
    `active_user()` 自己读一遍指针，把两种合成一句「还没有你的资料 ——
    先跑 /job-setup 建档；已经建过就跑 /job-user 切过去」。对**指针坏了**
    那一种，这句话两头都错：他的资料还在（只是指针找不着它），
    而排在最前面的那条命令恰恰修不了它 —— 同一份 `AGENTS.md` 里
    「一条引导对应一条命令」禁的正是这种「你自己判断该敲哪条」。

    而面板就是他读到这句话的地方：浏览器里那个 409 和 `serve.py`
    启动时的 stderr 印的都是它。
    """
    base = Path(base) if base is not None else ROOT
    ptr = base / ".active_user"
    user = ptr.read_text(encoding="utf-8").strip() if ptr.is_file() else ""
    if not user:
        return user, ("还没有活动用户 —— 你是第一次用？先跑 /job-setup 建档，"
                      "已经有用户就跑 /job-user 切换")
    if not valid_user_name(user) or not _user_dir_is_inside(base, user):
        nxt = ("/job-user 看看有哪些用户" if all_users(base)
               else "/job-user --new <名字> 新建一个（现在一个用户都没有）")
        return user, (f".active_user 里的「{user}」不是一个可用的用户名"
                      "（不能是路径、`..`、绝对路径、尾点或带控制字符）—— "
                      f"跑 {nxt}")
    if not (base / "users" / user).is_dir():
        # 一个用户都没有时，「看看有哪些用户」是条死路 —— 他敲过去是空列表。
        # `doctor.py` 早就分了这一支（改口 `--new`），这里跟上。判据是
        # `AGENTS.md`「每一处引导都要写出该敲的命令」那节的那一句：
        # 读完这句他能不能直接动手。
        nxt = ("/job-user 看看有哪些用户" if all_users(base)
               else "/job-user --new <名字> 新建一个（现在一个用户都没有）")
        return user, (f".active_user 指向「{user}」，但 users/{user}/ 不存在 —— "
                      f"跑 {nxt}")
    return user, ""


def resolve_user(argv=None, *, root=None, description: str = "", extra=None):
    """解析共同参数并定出这一次要操作哪个用户。

    `root` 是**调用方自己的仓库根**，必须由调用方在调用时传进来，不能用本模块
    这份 `ROOT` 常量。测试会把 `export_web_data.ROOT` 指到临时目录再跑导出；
    本模块的 `ROOT` 指向真实仓库，两个一打架就会出现「在临时树里找**真实**
    活动用户的目录」——报的错是「还没有职位数据」，跟真正的原因毫无关系。

    返回 `(user, args)`。用户不存在时**不返回**，直接带非零码退出——继续跑下去
    就会落到「读不到数据 → 当成这个人还没开始 → 导出一份空面板」，而那份空面板
    和「真的还没开始」长得一模一样。

    `extra(ap)` 用来加本工具自己的参数，加完仍然享受统一的 `--help` 与未知参数拒绝。

    ⚠️ **`argv=None` 表示「没有参数」，不表示「去读 sys.argv」。** 这个默认值是
    故意反过来设的：`serve.py` 在**自己的进程里**直接调 `export_web_data.main()`，
    要是默认去偷 `sys.argv`，服务器自己的 `--port 29030` 就会被导出器当成未知参数
    当场 `SystemExit(2)`——症状是面板打不开，报的错却跟端口毫无关系。
    真正的命令行入口在 `if __name__ == "__main__"` 里**显式**传 `sys.argv[1:]`。
    """
    ap = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", metavar="用户名",
                    help="这一次操作哪个用户，默认读 .active_user（不改 .active_user）")
    if extra is not None:
        extra(ap)
    args = ap.parse_args([] if argv is None else argv)

    # 解析逻辑只有 `pick_user` 一份。两处各写一套，措辞与退出码必然飘，
    # 而用户看到的正是那句措辞。
    return pick_user(args.user or "", root=root), args


def no_args(argv=None, *, description: str = "", extra=None):
    """只要 `--help` 与拒绝未知参数，不需要 `--user` 那套解析的工具用这个。

    `argv=None` 同样表示「没有参数」，理由见 `resolve_user`。
    """
    ap = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    if extra is not None:
        extra(ap)
    return ap.parse_args([] if argv is None else argv)



def no_store(path, *, then: str = "/job-scrape") -> str:
    """「还没抓过职位」这一句。**同一件事，原来五个工具五种说法。**

        archive / audit_pipeline / prescreen / writeback / jd_store
                            没有 {p} —— 先跑 /job-scrape
        build_dashboard     未找到 {p} —— 请先运行 /job-scrape 抓取职位
        export_web_data     还没有职位数据（{p} 不存在）——先跑 /job-scrape
        fetch_details       没有 {p} —— 先跑 /job-scrape 抓一轮职位
        gap_split           {user} 还没有职位数据 —— 先跑 /job-scrape 与 /job-rank

    `test_error_messages` 早就立过判据 ——「同一件事在两处发生，就该用同一句话
    说」—— 但它只盯着 `serve.py` 与 `tracker.py` 两个文件里的一种情形。
    这一件横跨九个工具，一直在网外。

    ⚠️ **怎么失败不归它管。** 各家分别是 `SystemExit` / `print`+`return 1` /
    `print`+`return 0`，那不是随手写的：流水线里「还没抓过」是**正常起点**，
    不是异常（`fetch_details` 那条注释写着这条约定）。这里只统一那句话。

    `then` 留给真的需要另一条下一步的：`gap_split` 要的是评过分的岗，
    光抓完还不够。
    """
    return f"没有 {path} —— 先跑 {then}"


def parse_today(value, *, flag: str = "--today"):
    """`--today` 给的那个值 → `datetime.date`；没给就返回 `None`。

    **默认值由调用方自己定**（多数是今天，`query_yield` 是「最近一次抓到的
    那天」）—— 这里只负责「给了的话，它得真是个日期」。

    ## 同一面旗子，五个工具三种脾气（2026-09-01 实测 `--today 不是日期`）

        archive          ValueError: Invalid isoformat string  ← 裸栈回溯
        followups        TypeError: NoneType - datetime.date   ← 裸栈回溯，
                         而且错在 `parse_date` 返回 None 之后很远的地方
        applied_jds      码 0，只有走 --apply 那条路才炸
        query_yield      码 0，**那串垃圾当成日期字符串直接参与比较**
        score            码 0，**--apply 时把它写进用户的评估正文**
                         （「⚠️ 不是日期 `score.py` 现算订正：…」，面板上看得见）

    后两个是失效在放行那一边：不报错、不停下，算出来的东西是错的，
    而 `score` 那一处会**留在盘上**。栈回溯那两个也不合规 —— `pick_user`
    的说明里写着「新用户第一次撞见的不该是栈回溯」。

    退出码 2，和 `portal_budget` 认不出渠道名时同一个：**1 是「这件事此刻
    不能做」，2 是「你打错了，改命令再来」**，两件事不共用一个码。
    """
    import datetime as _dt
    v = (value or "").strip()
    if not v:
        return None
    try:
        return _dt.date.fromisoformat(v)
    except ValueError:
        # **`raise SystemExit("一句话")` 的退出码是 1，不是 2。** 上面说明里
        # 那条分工（1 = 此刻不能做，2 = 你打错了）只有分开写才成立。
        print(f"{flag} 要的是 YYYY-MM-DD 那种日期，而给的是「{v}」。"
              + chr(10) + f"例：{flag} " + _dt.date.today().isoformat()
              + chr(10) + "（这面旗子是给测试和补算用的；平时不加就是今天。）",
              file=sys.stderr)
        raise SystemExit(2)


#: 职位库里**不是岗位条目**的顶层键。它们是工具自己写的旁路数据，
#: 值不是字典是设计内的 —— `ingest.py` 的 `data.setdefault("query_log", [])`
#: 写在顶层，而扁平格式的职位库岗位条目也在顶层，两边撞在一起。
#:
#: 后果（2026-10-13 实测）：一次带 `--query` 的入库之后，`writeback` / `archive` /
#: `prescreen` / `audit_pipeline` / `export_web_data` / `outreach_header` /
#: `stale_materials` / `doctor` 全部当场 AttributeError 或退出码 2 停下。
#:
#: **不能靠「把它挪到别的文件」解决** —— `tests/test_the_ingest_is_the_only_way_in.py`
#: 里有一条测试钉住了「query_log 就在 `seen_jobs.json` 里、两次入库留下两条」，
#: 那是仓库有意的设计（`query_yield` 靠它区分「跑了没产出」与「还没跑过」）。
#: 也不能挪进 `_meta` 之类的字典：顶层任何字典都会被当成一条岗位，
#: `decided_status` 从中读出 `"new"`，一条记账凭空变成一个待评岗位。
#:
#: 所以是**读取端**该认出它 —— 见 `JobView`。
NON_JOB_KEYS = frozenset({"query_log"})


class JobView(dict):
    """职位条目视图：读时隐去 `NON_JOB_KEYS`，写时穿透到源字典。

    **为什么需要它。** 扁平格式的职位库顶层同时住着两样东西：岗位条目，
    以及 `ingest` 写进去的 `query_log`。所有消费方都写的是
    `for k, e in seen.items(): e.get(...)`，于是一个数组值的键让八个工具
    当场 AttributeError。

    逐个给消费方加 `isinstance(e, dict)` 是**打地鼠**：`audit_pipeline` 一处文件
    就有十几处遍历，改到第八处还会遇到下一个。这正是本文件 `unreadable_rows`
    那段注释说的「散写的守卫盖不全」—— 守卫该收在这里一处。

    **实测收益（2026-10-13）。** 把那一批工具逐个跑过一遍：出问题的有七个 ——
    `writeback` / `archive` / `prescreen` / `audit_pipeline` / `export_web_data` /
    `outreach_header` / `stale_materials`，症状是 `AttributeError: 'list' object has
    no attribute 'get'` 或退出码 2。收口之后十个工具全绿。
    （测试条数的那笔账记在别处：同一个根因还让这个用户的职位库停在扁平格式上，
    把顶层条目收进 seen 子键之后全量测试从 74 条失败降到 39 条 —— 那是格式迁移的
    收益，不是这一处的。）

    **写穿透。** `writeback` / `ingest` / `serve` 都是「就地改完再把外层
    `store` 整份写回」，所以这个视图必须把写操作落到源字典上，
    否则它们的改动会丢。`__setitem__` / `update` / `pop` / `setdefault` /
    `__delitem__` / `popitem` / `clear` 逐个覆盖，`json.dumps(data)` 拿到的
    仍是完整的源字典（含 `query_log`），**账本一个字都不会少**。
    """

    def __init__(self, src: dict):
        dict.__init__(self)
        self._src = src
        self._reload()

    def _reload(self) -> None:
        dict.clear(self)
        dict.update(self, {k: v for k, v in self._src.items()
                           if k not in NON_JOB_KEYS})

    def __setitem__(self, k, v):
        self._src[k] = v
        dict.__setitem__(self, k, v)

    def __delitem__(self, k):
        self._src.pop(k, None)
        dict.pop(self, k, None)

    def update(self, *a, **kw):
        self._src.update(*a, **kw)
        self._reload()

    def setdefault(self, k, default=None):
        v = self._src.setdefault(k, default)
        self._reload()
        return v

    def pop(self, k, *d):
        v = self._src.pop(k, *d)
        self._reload()
        return v

    def popitem(self):
        k, v = self._src.popitem()
        self._reload()
        return k, v

    def clear(self):
        self._src.clear()
        self._reload()


def seen_of(store):
    """从 `seen_jobs.json` 的内容里取出岗位字典，**两代格式都认**。

    真实结构是 `{"seen": {key: {...}}}`；早期库顶层直接就是 `{key: {...}}`。
    `export_web_data` 与 `writeback` 一直显式容忍老格式，而 `serve` / `prescreen` /
    `jd_store` / `fetch_details` 直接 `store["seen"]` —— **同一个文件在一半工具里
    KeyError**：点「不投」时是一个 500，命令行上是一段 traceback。
    `writeback.py` 的注释早就点名了这个危险，只是没人把它收成一处。

    返回的是**原字典的引用**，就地改完把外层 `store` 写回去仍然对（老格式下
    外层就是它自己）。**老格式这一路额外套一层 `JobView`**：扁平库里顶层还住着
    `query_log` 这类旁路数据，而下游全都按「顶层每个值都是岗位」来遍历 ——
    判据见 `JobView` 的 docstring。新格式（岗位收在 store 的 seen 子键下）里没有
    这类顶层键，原样返回，不套壳（少一层对象、少一个行为变化面）。
    """
    if not isinstance(store, dict):
        return {}
    inner = store.get("seen")
    if isinstance(inner, dict):
        return inner
    return JobView(store)

def unreadable_rows(seen) -> list:
    """职位库里**读不出来**的那几条的键：值不是字典的。

    一条 `null`、一个字符串、一个列表 —— 每一种都会让下游的
    `e.get(...)` 当场 `AttributeError`。实测 2026-09-01：拿一条
    `null` 喂进去，16 个工具里 **9 个吐栈回溯**（`archive` /
    `audit_pipeline` / `prescreen` / `query_yield` / `stale_materials` /
    `writeback` / `export_web_data` / `outreach_header` / `doctor`）。

    ## 为什么不在 `seen_of` 里就地滤掉

    它按契约返回**原字典的引用**（「就地改完把外层 `store` 写回去仍然对」）。
    在那儿删，等于下一次写盘就把用户那几行**从盘上抹掉** —— 而坏成什么样
    只有他自己知道，删不删不归工具判。

    ## 也不该继续崩

    `isinstance(v, dict)` 这个判断此刻在这九个文件里散着写了 **69 遍**，
    而九个还是都崩了 —— 散写的守卫盖不全，正是它该收成一处的理由。
    """
    if not isinstance(seen, dict):
        return []
    return [k for k, v in seen.items() if not isinstance(v, dict)]


def stop_on_unreadable_rows(seen, path) -> None:
    """有读不出来的记录就**干净地停下**，别甩栈回溯、也别替他删。

    退出码 2，和渠道名打错、`--today` 不是日期同一个约定：
    **1 是「这件事此刻不能做」，2 是「输入坏了，改了再来」。**

    ⚠️ `doctor` 不用它 —— 那条命令的契约是「任何状态下都能跑」
    （`AGENTS.md`「会话开始」那一节），它改成数出来、报一句、接着走。
    """
    bad = unreadable_rows(seen)
    if not bad:
        return
    shown = "、".join(str(k)[:24] for k in bad[:3])
    more = f"，另有 {len(bad) - 3} 条" if len(bad) > 3 else ""
    print(f"职位库里有 {len(bad)} 条记录读不出来（{shown}{more}）——"
          f"它们的值不是一条职位记录。"
          + chr(10) + f"文件：{path}"
          + chr(10) + "这几条没有被改动。先看一眼那几个键，确认要不要留；"
          + chr(10) + "拿不准就把整份文件备份一下再删掉那几行，然后重跑这条命令。",
          file=sys.stderr)
    raise SystemExit(2)


class StaleWrite(Exception):
    """你手里那份数据已经过期了——从读到写之间，别人改过这个文件。

    **原子写防的是「写坏」，这个防的是「写旧」。** 两者是不同的故障：
    原子写保证读到的永远是完整文件，但**不保证你写回去的内容基于最新版本**。

    ## 接住它该怎么办

    **库的调用方**：重新读一次（`load_json_stamped` 拿新戳），把你的改动重新
    应用上去再写。异常消息里**不带**这句——它只陈述事实，因为指令按受众不同。

    **命令行入口**：不必自己接，走 `run_cli(main)` 就行，它会换成用户能照做的
    一句「把这条命令再跑一遍」。重跑是对的：工具每次都从盘上重新读，
    没有需要用户手工合并的东西。
    """


def run_cli(main, argv=None) -> int:
    """CLI 入口的统一收口：把 `StaleWrite` 变成一句人话，不是栈回溯。

    带戳写盘的那几个工具（`prescreen` / `writeback` / `archive` /
    `audit_pipeline`）都会撞上它，
    而且**撞上是正常的**：`/job-auto` 一跑就是几分钟，这期间用户在总览页点一下
    「不投」「我投了」完全正常。`StaleWrite` 说的是「你手里那份过期了，
    这次没写」——那是一次干净的让路，不是程序坏了。

    可它原来是未捕获异常，落到用户眼前就是几十行 Traceback 加一个英文类名。
    这个仓库对此有明确约定（见 `pick_user`：「新用户第一次撞见的不该是栈回溯」），
    而且 AGENTS.md 禁止把未解释的英文码摆到台面上——`StaleWrite` 正是一个。

    异常自带的那句话是写给**读代码的人**的（「重新读一次，把你的改动重新应用上去」）。
    对着敲命令的人要换成他能照做的一句：**重跑这条命令**。重跑是对的——
    工具每次都从盘上重新读，没有需要他手工合并的东西。

    收在这里而不是三个 `main()` 里各写一遍：三份文案迟早分叉，而这条路径
    平时跑不到，分叉了也没人发现。
    """
    try:
        return main(argv)
    except StaleWrite as exc:
        import sys as _sys
        nl = chr(10)
        _sys.stderr.write(
            f"{nl}  没有写盘：{exc}{nl}"
            f"  刚才那一下是让路，不是出错——你的数据一个字没动。{nl}"
            f"  直接把这条命令再跑一遍就行。{nl}{nl}")
        return 2


def load_json_stamped(path):
    """读 JSON，同时记下版本戳。与 `atomic_write(..., expect=...)` 配对用。

    **什么时候必须用它**：读到写之间**隔着几秒以上**的场合。典型的是
    `/job-rank`——读一次职位库、AI 评分十几分钟、再整份写回；而工作流恰恰
    让用户在这期间去总览页点「我投了」。

    ## 戳是 `(mtime_ns, size)`，不是单个 mtime

    文件系统的时间戳有分辨率下限。实测这台机器（2026-08-21）：
    **连写 50 次只产生 18 个不同的 `st_mtime_ns`** —— 也就是说两次写落在
    同一个刻度里时，光比 mtime**看不出文件被改过**。

    加上 `st_size` 是免费的（同一次 `stat()` 就有），它挡住「同一刻度里
    大小变了」的那类改动 —— 而绝大多数改动都会改大小。

    ⚠️ **仍有一个理论上的洞**：同一刻度里 + 大小完全没变（例如
    `skipped` 换成 `expired`，都是 7 个字符）。要堵死得比内容哈希，
    而那要在每次带 `expect` 的写之前把整个文件重读一遍。**没有堵**，
    因为这道保险要防的是**长窗口**（读→评分十几分钟→写回），
    那种场景两次写隔着几分钟，mtime 一定不同。把限制写在这里，
    比假装它没有强。
    """
    import json as _json
    from pathlib import Path as _P
    p = _P(path)
    # **先取戳，再读内容 —— 顺序反了这道保险就朝错的方向失效。**
    # 反过来（读完再 stat）时，若正好有人在这两句之间写了一次，
    # 你手里是**旧内容配新戳**：`expect` 比对当场通过，于是把对方刚写的
    # 那一笔静默盖掉 —— 正是这个机制存在的理由本身。
    # 先 stat 则是旧内容配旧戳：写回时戳对不上，抛 `StaleWrite`，宁可多报一次。
    stamp = _stamp_of(p)
    # 读法走 `read_json`：BOM 吃掉、别的编码给一句人话。**这里是最要紧的一处**
    # —— 八个碰主库的工具都从它进门。
    return read_json(p), stamp


def _stamp_of(p) -> tuple:
    """一个文件此刻的戳 `(mtime_ns, size)`。**取戳只许有这一份实现** ——
    读的那头（`load_json_stamped`）和写的那头（`atomic_write` 的 `expect` 比对）
    必须逐字段一致，各写一遍就等着哪天一头加了字段另一头没加，
    保险从此恒真、静默失效。

    写那头原来是一句 `(lambda st: (st.st_mtime_ns, st.st_size))(p.stat())` ——
    每次带 `expect` 的写都造一个闭包，而且把比较藏进了括号里；
    这是全仓最要紧的写路径，读的人应当一眼看得出它在比什么。
    """
    st = p.stat()
    return (st.st_mtime_ns, st.st_size)


def atomic_write(path, text: str, *, encoding: str = "utf-8",
                 newline: str | None = None,
                 expect: tuple | None = None) -> tuple:
    """写文件时**不要先把它截断**——写临时文件再原子替换。

    `expect` 传 `load_json_stamped` 给的版本戳时，会在替换前再比一次：
    文件被别人动过就抛 `StaleWrite`，**不写**。

    ## `expect` 为什么值得有：实测过的静默数据丢失

    本文件下面写着「跨进程没有锁……最后一个替换的赢」——那对**短窗口**的写是对的
    （两个进程各自读完立刻写，谁后写谁生效，本来就是无锁语义）。
    但**长窗口**不是这个语义，它是丢数据：

        命令行侧读职位库  →  ……AI 评分十几分钟……  →  整份写回
                              ↑ 用户在总览页点了「不投」，已经落盘

    命令行那份是十几分钟前的快照，写回去把用户那一下**整个抹掉，且不报错**。
    2026-08-19 实测复现：面板写入 `skipped`，命令行写回后变回 `ranked`，
    `skip_reason` 消失。用户以为点上了，刷新才发现没有。

    加了 `expect` 之后，这种情况**抛异常而不是悄悄覆盖**——调用方重读一次
    再把自己的改动应用上去即可。**把静默的数据丢失换成大声的报错**，
    是这里最省的正确做法：真造一把跨进程锁，要处理死锁、超时、残留锁文件，
    而它们每一个都比现在这个问题更难查。

    ## 为什么这条要单拎出来

    2026-08-13 第 9 轮检查发现一处方向反了的不对称：

        web/public/data.json        派生快照，丢了能重新生成   → 原子写
        users/*/job_scraper/seen_jobs.json   1246 条职位，唯一副本 → 裸 write_text
        users/*/job_search_tracker.csv       76 条投递记录        → 裸 write_text

    `Path.write_text` 走的是 `open(mode="w")`：**它先把文件截断成 0 字节，再写内容**。
    中途被打断——Ctrl+C、断电、磁盘满、进程被杀——文件就停在空的或半截的状态。
    派生快照丢了跑一次导出就回来；**原始数据丢了就是丢了**。

    而这个仓库的日常恰恰是「长跑的命令 + 随时可能 Ctrl+C」：`/job-auto` 一跑几十分钟，
    中间反复写 `seen_jobs.json`。

    `os.replace` 在同一文件系统内是原子的（POSIX rename / Windows MoveFileEx），
    并发的读要么看到旧的完整文件、要么看到新的完整文件，不存在中间态。

    临时文件与目标同目录——跨盘 `os.replace` 会退化成拷贝，失去原子性。

    **返回写完之后那个文件的戳。** 戳在 `os.replace` **之前**从临时文件上取，
    因为替换后再 `stat()` 会拿到「替换之后又被别人写了一次」的戳 —— 调用方
    拿它当下一笔的 `expect`，就会把别人的改动当成自己的基线。临时文件的
    mtime/size 会原样跟着 rename 过去。
    """
    from pathlib import Path as _P
    import os as _os
    import threading as _th
    import time as _time
    p = _P(path)
    # **临时文件名必须唯一。** 固定成 `<名>.tmp` 时，两个并发的写会踩同一个中转文件：
    # A 写完 → B 覆盖 → A 替换成功（临时文件没了）→ B 替换时
    # `FileNotFoundError: [WinError 2] 系统找不到指定的文件`。
    #
    # 2026-08-13 实测撞上：面板那个「并发点几下按钮」的测试当场抛这个异常。
    # 同进程有 `serve._WRITE_LOCK` 挡着，但**跨进程没有锁**——命令行工具
    # （`/job-rank` 写 seen_jobs.json）和面板的导出子进程完全可能同时落盘。
    #
    # 带上 pid + 线程 id：并发时各写各的中转文件，最后一个替换的赢
    # （那是「谁后写谁生效」，本来就是无锁写入的语义），但不会再有人替换一个
    # 已经被别人搬走的文件。留下的垃圾也认得出是哪个进程的。
    tmp = p.with_name(f"{p.name}.{_os.getpid()}.{_th.get_ident()}.tmp")
    # `newline` 要透传：CSV 必须用 newline="" 关掉换行转换，
    # 少这一路，台账每写一次就多出一堆空行。
    # 戳是 `(mtime_ns, size)` —— 见 `load_json_stamped` 里为什么不能只比 mtime。
    if expect is not None and p.exists() and _stamp_of(p) != expect:
        # **只陈述事实，不给指令。** 该怎么办取决于谁在听：
        # 命令行前面的人要的是「把这条命令再跑一遍」（`run_cli` 会补上这句），
        # 而库的调用方要的是「重新读一次再应用」——写在这个类的 docstring 里。
        # 原来把后者塞进了消息，于是 `run_cli` 包起来之后两句指令并排打架：
        # 「重新读一次，把你的改动重新应用上去再写」紧挨着「直接再跑一遍就行」。
        raise StaleWrite(
            f"{p.name} 在你读它之后被改过了"
            f"（多半是总览页那边点了按钮，或另一条命令在写）")
    tmp.write_text(text, encoding=encoding, newline=newline)
    # **先取戳，再替换。** 反过来会在别人恰好写了一次时把「他的戳」交回去，
    # 下一笔带 `expect` 的写就会以他的版本为基线，静默覆盖掉他。
    new_stamp = _stamp_of(tmp)
    # ── Windows 上 `os.replace` 会撞上「目标正被读」 ──
    #
    # POSIX 的 rename 可以覆盖一个正被打开的文件；**Windows 不行**：
    # Python 的 `open()` 不带 `FILE_SHARE_DELETE`，只要还有人持着读句柄，
    # `os.replace` 就抛 `PermissionError: [WinError 32] 另一个程序正在使用此文件`。
    #
    # 这不是假想。2026-08-13 换成原子写的当天，测试里那个「并发点几下按钮」的
    # 用例立刻炸出两次——一个线程在 `load()` 读台账，另一个在替换它。
    # 面板是 ThreadingHTTPServer，用户连点几下就是这个形状。
    #
    # 窗口极短（读一个几十 KB 的 CSV 是毫秒级），退避重试足够；
    # 重试完还不行就抛出去，**不要假装成功**——调用方那几处 `except` 会把
    # 真因写进日志，而静默吞掉会让盘上和页面上各说各话。
    for attempt in range(6):
        try:
            _os.replace(tmp, p)
            return new_stamp
        except PermissionError:
            if attempt == 5:
                raise
            _time.sleep(0.02 * (attempt + 1))


# ---------------------------------------------------------------------------
# 用户自己下的决定，单独存一份
# ---------------------------------------------------------------------------
#
# ## 为什么要拆出来
#
# `seen_jobs.json` 里原本塞着三种写入模式完全不同的东西：
#
#     抓来的事实（薪资、JD 字段…）  /job-scrape  每天几百条，只增
#     判断（分数、判词）            /job-rank    批量整份重写
#     用户决定（不投、已下线）      总览页       一次一条
#
# 于是「读一次库 → AI 评十几分钟 → 整份写回」会把这中间用户点的那一下**整个抹掉**
# （2026-08-19 实测复现）。`atomic_write(expect=...)` 那道保险能让它**报错**，
# 但报错之后仍要重来一遍——真正的解法是让两边根本不写同一个文件。
#
# 实测 2026-08-19 比例：2610 个岗里只有 109 个带用户决定。为了改这 109 条里的一条，
# 面板原来要重写全部 2610 个岗（3.4 MB）。拆出来之后写的是几十 KB。
#
# ## 合并契约
#
# 这份是**叠加层**，不是替代：有决定的以它为准，没有的看职位库自己的 `status`。
# 所以**不需要迁移**——库里已有的 `skipped`/`expired` 照常生效，
# 新的点击只写叠加层。
#
# 撤销就是把这个键删掉（不是写 `null`）——留一个空壳会让「有没有决定过」
# 变成三态，而它只需要两态。

def user_state_path(seen_file):
    """叠加层就放在职位库**旁边**：`seen_jobs.json` → `user_state.json`。

    **不要从「仓库根 + 用户名」去推。** 第一版就是那么写的，结果：
    职位库的路径在 `serve.py` 里是可注入的（`seen_path(user)`，测试会替换成临时目录），
    而叠加层的路径自己从 `ROOT` 推——两套解析方式，于是测试把库指到临时目录之后，
    叠加层仍然落在**真实仓库**里。实测在 `users/张三/`、`users/谁/` 下写出了
    真实文件（那是测试夹具的用户名）。

    跟着职位库走就没有这个缝：谁解析出库在哪，叠加层就在哪。
    而且这也是语义上对的——它俩是同一份数据的两半，本来就该同进同出。
    """
    from pathlib import Path as _P
    return _P(seen_file).with_name("user_state.json")


def read_json(path, *, default=None):
    """读一份 JSON。**BOM 透明吃掉，别的编码给一句人话，不甩栈回溯。**

    ## 两件事，两种处置

    - **BOM**：`utf-8` 读会直接抛
      `JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig)` ——
      Python 把答案写在错误里了。BOM 来得比想的容易：记事本存「UTF-8」带它，
      Windows PowerShell 5 的 `Out-File -Encoding utf8` 也带它，而本仓库的
      主 shell 就是 PowerShell。`utf-8-sig` 有 BOM 剥掉、没有等同 `utf-8`，
      **没有任何副作用**。
    - **别的编码**（Excel/记事本存出来的 ANSI，中文 Windows 上是 cp936）：
      猜不得 —— 猜错了是把一份中文资料读成乱码再据此判断，比停下更坏。
      所以停下（码 2），说清是哪份文件、该怎么办。

    实测 2026-09-01：职位库带 BOM 或存成 GBK 时，13 个工具里 **10 个吐栈回溯**
    （`export_web_data` 那一个 = 面板整个出不来）。

    ## ⚠️ 只给「主库那条路」用，别到处替换

    第一版拿正则把 24 处 `json.loads(x.read_text(...))` 全换成了它 —— 其中
    **14 处原来写在 `try` 里、靠 `except (ValueError, OSError)` 降级**
    （环境探测缓存、面板快照、逐岗详情……）。`SystemExit` 不被那种 except 接住，
    于是「这份文件坏了就跳过」变成「整条命令停下」，方向正好反了。

    判据：**这份文件坏了该不该让整条命令停下**。主库（`seen_jobs.json`）该停 ——
    它是一切的输入；缓存和快照不该停，它们本来就允许没有。
    """
    import json as _json
    from pathlib import Path as _Path
    p = _Path(path)
    if default is not None and not p.is_file():
        return default
    try:
        return _json.loads(p.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        print(f"{p} 不是 UTF-8 存的（{exc.reason}）——"
              + chr(10) + "多半是在 Excel 或记事本里改过并存成了 ANSI/GBK。"
              + chr(10) + "把它另存为 UTF-8 再跑一次这条命令。",
              file=sys.stderr)
        raise SystemExit(2) from None


def read_tracker_rows(path) -> list:
    """投递记录 CSV → `[{列名: 值}]`。读不了就报一句、返回空，不抛栈。

    ## 两个坑各中过一次

    - **BOM**：Excel 存出来的 CSV 常带它。用 `utf-8` 读**不会报错** ——
      BOM 只是变成第一个字符，于是第一列的列名成了 `﻿date`，
      `row.get("date")` 从此返回 `None`。**静默**。
    - **GBK**：用户在 Excel 里打开再保存，中文 Windows 上默认就是 ANSI(cp936)。
      这个会抛 `UnicodeDecodeError` —— 抛出去就是整条命令挂掉。

    ## 为什么住在这儿

    `build_dashboard.load_tracker` 早就把这两条都接住了，`export_web_data`
    的调用点还写着「**不要在这里内联一份 DictReader**」。而
    `followups.load_rows` 自己开了一份：BOM 接住了，`UnicodeDecodeError`
    没接 —— 实测 2026-09-01，台账存成 GBK 时 13 个工具里**只有它甩栈回溯**。

    它接不到那一份是因为 `build_dashboard` 反过来 import 它（取 `parse_date`），
    直接引就成环。所以搬到这里：两边都够得着，规则只剩一份。
    """
    import csv as _csv
    from pathlib import Path as _Path
    p = _Path(path)
    if not p.is_file():
        return []
    try:
        with p.open(encoding="utf-8-sig", newline="") as fh:
            return list(_csv.DictReader(fh))
    except UnicodeDecodeError as exc:
        print(f"警告: {p} 不是 UTF-8（{exc.reason}），本次跳过投递记录匹配；"
              f"请把它另存为 UTF-8 CSV", file=sys.stderr)
        return []


def load_user_state(seen_file) -> dict:
    """`{seen 的键: {"decision": "skipped"|"expired", "date": ..., "reason": ...}}`

    **每个值都保证是字典。** 上面那行只判了外层：外层是字典而**某一行是
    `null`** 时，读的人一律写 `ustate.get(k, {}).get("decision")` ——
    默认值只在「键不存在」时生效，键在而值是 `null` 就直接 `AttributeError`。

    实测 2026-09-01：叠加层里放一条 `{"a": null}`，`export_web_data` 与
    `archive` 各自甩一段栈回溯（前者 = 面板整个出不来，后者在
    `/job-auto` 收尾里）。

    这里**把那一行换成空字典，不删键** —— 和职位库那边同一条原则
    （`stop_on_unreadable_rows`：不替他删）。区别是那边的坏行可能还留着
    能看的残迹、值得让他自己看一眼，而这一层的 `null` 一个字的信息也没有，
    留着键就够了；何况这份文件**只有面板会写**（见 `set_user_decision`）。
    """
    import json as _json
    p = user_state_path(seen_file)
    if not p.is_file():
        return {}
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(d, dict):
        return {}
    return {k: (v if isinstance(v, dict) else {}) for k, v in d.items()}


def set_user_decision(seen_file, key: str, decision: str | None, **extra) -> dict:
    """写一条用户决定；`decision=None` 表示撤销（删掉这个键）。

    整份读-改-写，但这份只有几十 KB、且**只有面板会写**，窗口是毫秒级。
    """
    import json as _json
    st = load_user_state(seen_file)
    row = dict(st.get(key) or {})
    if decision is None:
        # **只撤销「决定」那三个键，别把整行删掉。** 同一行上还挂着别的标记
        # （`hr_viewed`：HR 有没有打开过这份简历），那是另一件事，
        # 不该因为「放回可以投」而一起消失。剩不下东西了才删这一行。
        for k in ("decision", "date", "reason"):
            row.pop(k, None)
        if row:
            st[key] = row
        else:
            st.pop(key, None)
    else:
        row.update({"decision": decision,
                    **{k: v for k, v in extra.items() if v is not None}})
        st[key] = row
    p = user_state_path(seen_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, _json.dumps(st, ensure_ascii=False, indent=1))
    return st


def set_hr_viewed(seen_file, key: str, viewed) -> dict:
    """记一笔「这份简历对方点开过没有」。`viewed=None` 撤销这个标记。

    ## 为什么这一个字段值得单独存

    国内平台在「投递记录 / 我的投递」里逐条标着简历有没有被打开（猎聘、智联写
    「已查看 / 未查看」，BOSS 看那条会话对面点没点开）。**这个数平台白给**，
    而它把「投了没回音」拆成两件后果完全相反的事
    （`job-outcome.md` Step 2b 那张表）：

        大多已查看、还是没回  → HR 打开了看完没往下走，这才轮到审简历
        大多未查看            → 简历根本没被打开，**改简历没用**，要换的是投什么岗

    在这之前它**只写在那一个工作流里**：让用户去平台看一眼，然后那个答案
    无处可落 —— 查一次忘一次，诊断永远停在「先催一遍」。

    **和 `decision` 同行不同键**：一个岗可以既「已查看」又被标「不投」，
    两件事互不覆盖（`set_user_decision` 现在是合并写，不是整行替换）。
    """
    return _set_flag(seen_file, key, "hr_viewed", viewed)


def _set_flag(seen_file, key: str, name: str, value) -> dict:
    import json as _json
    from datetime import date as _date
    st = load_user_state(seen_file)
    row = dict(st.get(key) or {})
    if value is None:
        row.pop(name, None)
        row.pop(name + "_date", None)
    else:
        row[name] = bool(value)
        row[name + "_date"] = _date.today().isoformat()
    if row:
        st[key] = row
    else:
        st.pop(key, None)
    p = user_state_path(seen_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, _json.dumps(st, ensure_ascii=False, indent=1))
    return st


#: 这里原来还有一个 `fold_user_state(seen_file, seen)`：把叠加层整个折进条目、
#: 让老代码原样工作。**2026-08-25 删了 —— 它一个生产调用方都没有。**
#:
#: 仓库实际收敛到了下面这个 `decided_status`：不改条目、每次显式取一次。
#: 四个消费方（archive / export / prescreen / fetch_details）走的都是它。
#: 折叠那份现在只剩**一处**引用（`doctor.py` 里的一条注释），
#: 而那条写的是「**一个生产调用方都没有**，2026-08-25 已删」—— 原来它写着
#: 「正本在 `_cli.fold_user_state`」，那次清理一并把它改掉了。
#: **而那份从来没跑过，两边早就各折各的**（它折 reason/date、doctor 那份折
#: hr_viewed，互相都没有对方那一半）。一个没有消费者的「正本」比没有更坏：
#: 它让人以为这件事已经统一了，于是不去查还有谁漏着。
#:
#: `tests/test_long_writes_do_not_clobber.py` 现在盯两条：公开判据必须有生产
#: 消费者；读状态的地方不许把叠加层那个参数传成 `None`。


def decided_status(entry: dict, overlay_row: dict | None) -> str:
    """这个岗**实际**是什么状态：用户决定优先，其次才是职位库自己的 `status`。

    所有消费方都必须走它——各自写一份 `overlay.get(k,{}).get('decision') or ...`
    的地方越多，越容易有人漏掉叠加层，表现就是「页面上标了不投，命令行还在评它」。
    """
    if overlay_row and overlay_row.get("decision"):
        return str(overlay_row["decision"])
    return str(entry.get("status") or "")

# ============================================================================
# 全仓共享的词表与判据 —— **每样只许在这里定义一次**
#
# 2026-08-20 用户点破「很多相关逻辑是同一个，但分成多组了」，对账坐实了五组：
# 判词五档在 4 个文件里各写一份、来源族两份**已经分叉**（audit 认「批量」、
# test_verdict_cap 不认——同一条数据两个守卫结论相反）、协议归一化两处手写、
# JD 正文阈值 80 两处字面量、薪数 12–24 两处字面量。
#
# 这类分叉的形状永远一样：改了一份、忘了另一份，而且**两份各自都有测试护着**，
# 谁也不红。所以收进人人都 import 的这里；`tests/test_shared_vocab_single_source.py`
# 盯住不许再散落。
#
# 例外一个：`doctor.py` 零依赖契约（全新 clone 也要能跑），它的内联副本
# 在注释里点名了正本，不算散落。
# ============================================================================

#: 判词五档，**顺序即档序**（高→低）。`04-job-evaluation.md` 是语义正本，这里是
#: 代码侧唯一定义。切片即子集：[:2] 是「可投」（强匹配/值得投），[:3] 加上可以考虑。
VERDICTS = ("强匹配", "值得投", "可以考虑", "不建议", "跳过")

#: **计权的四维**（`04-job-evaluation.md` 第二步）。评分明细表里出现的其它行
#: 不是维度，是被写到那张表里的**别的东西**。
#:
#: 眼下唯一那种是「地点」：框架自己写着
#:
#: > 计权的是**四**维……地点是 Pass/Fail 的门（跨城搬迁），不计权重——
#: > **所以别再叫「五维」**。
#:
#: 而实测活动用户 2026-08-23：238 份评分明细里 **106 份**多一行
#: 「地点（跨城搬迁）」（`score` 为 None、`weight` 为 0）。写手其实很小心 ——
#: 不给分、不给权重，那是「不计权重」的一种合理读法 —— 但面板那边
#: `splitReasons` 把「没有分数」一律归进「要掂量的地方」，
#: 于是 96 条写着「上海」（他就在上海，**那是通过**）的行被摆成了负面，
#: 措辞还是「这项没打分」—— 对一道 Pass/Fail 的门来说，不打分是设计如此。
#:
#: **判据只能按名字，不能按 `weight == 0`**：实测 2026-08-23 826 条 weight 为 0 的行里
#: 有 716 条是真维度（那一列常常没解析出来）。
WEIGHTED_DIMS = ("技能与经验", "薪资与职级", "强度与公司性质", "发展与风险")

#: **一个岗退回队列时要抹掉的那几个评分字段。** 2026-10-14 收拢：
#: 同一份四元组在 `audit_pipeline.py` 里写了两遍、在 `serve.py` 里一遍，
#: 顺序还各不一样（而顺序不影响 `pop` 的结果，所以三处一直没人发现）。
#: 加一个字段就得改三处，而漏掉的那一处会让「已退回」的岗还带着旧判词。
RANK_FIELDS = ("rank_verdict", "rank_score", "rank_date", "rank_breakdown")


def is_weighted_dim(name: str) -> bool:
    """这一行是不是**计权的四维**之一。宽进：写「技能与经验匹配」也算。"""
    n = (name or "").strip()
    return any(d in n for d in WEIGHTED_DIMS)


#: 判词天花板：技能与经验分至少要到多少，才许挂这一档判词。
#: 边界取技能维自己的分档（04 的表），不是从样本拟合的。
CAP_BANDS = (("强匹配", 80), ("值得投", 60), ("可以考虑", 40), ("不建议", 0))

#: 薪数未知时，按**最乐观**的薪数去估上沿。内地月薪岗常见 12-16 薪，个别到
#: 18-20；取 16 是「常见范围的上端」。
#:
#: **正本放这儿，是因为三处在用而三处各写了一份 16**（`prescreen` 拿它淘汰、
#: `scoring` 拿它给薪资维分档、`audit_pipeline` 拿它报「没标薪数的岗被埋掉」）。
#: 三份手写的同一个数，改一处另两处不会红 —— 而这条线对它很敏感：
#: `prescreen` 自己的注释算过，差一薪在两千个岗的库上就是几十个岗的生死。
#: 2026-08-30 收成一处。
#:
#: **那句「几十个」2026-08-31 量出来了**：活动用户的库里 193 个岗死于
#: 「未标薪数 + 按 16 薪估上沿仍低于底线 42 万」，把 16 换成 17 会救回
#: **61 个（32%）**，换成合理区间上限 24 会救回 114 个（59%）。
#:
#: 所以别顺手调它。往上调不是「宽容一点」，是把半个库重新灌进待评队列 ——
#: 而那批的真实年包多半仍在底线之下，多出来的只有 AI 的工时和用户的队列。
#: 16 的依据是**语义**（常见范围的上端），不是从某个人的语料拟合的：
#: 这份语料实测中位 15 薪、p90 是 17，取 16 恰好落在中间，但那是印证不是出处。
#: 真要按人调，该走 `profile/candidate.md` 那条「写了就按它算」的路（同「评分
#: 权重」那一节的做法），不是改这个常量。
OPTIMISTIC_MONTHS = 16

#: 判词依据 `来源` 允许的族前缀。冒出新族多半是执行者临时造词，
#: 按来源分流的守卫（复核、审计）会看不见它。
SOURCE_FAMILIES = ("粗筛", "预筛", "深评", "同岗重复", "批量")

#: `N薪` 的合理区间。超出一律当没写、退回 12 薪保守估——年薪 25/30 薪不是真实
#: 用工形态，照单全收会把年包算到 375-550 万、顶满薪资维（实测见 audit_pipeline）。
SALARY_MONTHS_SANE = (12, 24)

def salary_unstated(salary) -> bool:
    """这个薪资串**给不出任何数**吗（「薪资面议」「面议」「」「另议」…）。

    判据就一条：**串里一个阿拉伯数字都没有**。不枚举写法 —— 平台的说法五花八门
    （「面议」「薪资面议」「另议」「详谈」），枚举必漏；而只要有数字，
    折算那一侧就有东西可算（`export_web_data.annual_package` 的口径同此）。

    ## 为什么值得有个名字

    `04-job-evaluation.md` 对它有一条明确规定：

    > **薪资面议**：`salary` 为「薪资面议」时，这一维**不打分**，标记为「信息缺失」
    > ——面议本身是个信号，意味着薪资弹性大或不愿公开。

    而这条规定原来只有散文，没有任何机械检查。实测活动用户 2026-08-23：
    21 个面议岗里 19 个照做了，**2 个打了分**，其中一个给了 **0**。
    0 的意思是「薪资很差」，而真相是「不知道」—— 那一个的总分被压到 45、
    判词「不建议」。同一份文档算过这笔账：面议不计入 → 总分 76；照打 → 63。

    判据原来在 `export_web_data` 里内联了两处（`annual_of` 与
    `salary_months_unknown` 的开头守卫），字面完全一样。审计要用它是第三处 ——
    所以提到这里，三处共用一份。
    """
    t = str(salary or "").strip()
    return not t or not re.search(r"\d", t)


#: JD 正文「算抓过」的最小字数。低于它的是占位符，不能拿去打分。
JD_MIN_BODY = 80


#: 「没过硬性条件」这类**终态结论**的前缀族——它们不是五档判词，但同样是合法结案。
#: 此前 export 的 OUT_PREFIXES 与 audit 的豁免清单各写一份（差着一个「硬门FAIL」
#: 无空格变体和「已下线」），第三份长在哪天没人说得准。
GATE_FAIL_PREFIXES = ("硬门 FAIL", "硬门FAIL", "不满足硬性条件")


#: 04 第一步的**七道硬门**。键是正规名，值是该门在深评表里可能出现的写法片段
#: ——门名是自由文本（实测 10+ 种写法：「外包/驻场」152 次、「外包·驻场·派遣」57 次
#: 是同一道门），所以按片段认，不按整串。
#:
#: 前端只按 `state` 过滤、不按门名，所以散写法不伤面板；伤的是**「这道门判过没有」
#: 查不出来**——实测 257 份深评里，执业资格 75 份、户口 72 份、应届生 72 份
#: 整个没判（各约 28%），而 04 要求「每一道都要检查」。没判和没有那行长得一模一样。
GATES = {
    "学历与院校": ("学历", "院校"),
    "工作年限": ("年限", "经验年"),
    "户口与落户": ("户口", "落户"),
    "应届生与三方": ("应届",),
    "外包/驻场/派遣": ("外包", "驻场", "派遣"),
    "执业资格/证照/职称": ("执业", "证照", "职称", "资格"),
    "候选人明确排除": ("排除",),
}


#: 粗筛判词的前缀。**冒号两种都要认** —— 全角是写手打的，半角是复制粘贴带进来的。
_TRIAGE = re.compile(r"^粗筛[：:]\s*")


#: 依据里那句「……<某维>这一维给 NN」—— **认出 NN 归哪一维**。
#:
#: ## 为什么正本在这里
#:
#: 两处都要它，而它们的方向相反：
#:
#: - `writeback._basis_is_stale` —— **报**依据旧了（那句话说的数与库里存的不符）；
#: - `scoring.rewrite_pay_said` —— **改**依据，而只许改薪资那一句（2026-10-12
#:   事故：`SAID.sub` 全局替换，把「强度与公司性质这一维给 50」也换成了薪资的值）。
#:
#: 两边判的是同一件事，抄一份就是等着它们分叉 —— 与 `LINK_LINE` 六个住址同型。
#: `scoring` 是底层模块、`writeback` 是命令，让底层 import 命令会把
#: `build_dashboard`/`export_web_data` 拖进评分那条热路径；两边都已经 import
#: `_cli`，所以正本落在这儿。
#:
#: **键是维度名**（技能 / 薪资 / 强度 / 发展），组 2 是那个数。
DIM_SAID = re.compile(r"(技能|薪资|强度|发展)[^。；]{0,14}?(?:这一维|维)?[^。；]{0,6}?给\s*(\d{2})")

#: 上面那个维度名 → `rank_breakdown` 里的键名。
DIM_FULL = {"技能": "技能与经验", "薪资": "薪资与职级",
            "强度": "强度与公司性质", "发展": "发展与风险"}


def strip_triage(verdict) -> str:
    r"""`粗筛：值得投` → `值得投`。不是粗筛的原样返回（去掉首尾空白）。

    ## 为什么要有这个函数

    实测 2026-08-30：全仓库 **25 处**在处理这个前缀，**三种写法、两种行为**：

        re.sub(r"^粗筛[：:]\s*", "", …)   4 处  —— 认全角半角两种冒号，且只削前缀
        .replace("粗筛：", "")            11 处  —— 只认全角，而且是**全串替换**
        .startswith("粗筛：")              2 处

    `.replace` 那一支两处都比正则那一支弱：半角冒号削不掉，而「粗筛：」出现在
    判词中段时会被就地抹掉（`硬门 FAIL (…粗筛：…)` 这种理论上的写法）。
    库里眼下全是全角前缀，所以**这是个潜伏的分叉，不是活的 bug** ——
    但两种行为并存意味着「同一个判词，问不同的函数得到不同答案」，
    而这个仓库为这一类形状栽过太多次（`gates_in_verdict` 那次漏 22 个、
    `adjust_of` 那次丢掉 −5）。收成一处。
    """
    return _TRIAGE.sub("", str(verdict or "").strip())


def is_triage(verdict) -> bool:
    """这条判词是不是粗筛出来的（看前缀，不看 `来源` 字段）。

    ⚠️ 和 `scoring.is_triage` 不是一回事：那个读的是 `rank_breakdown["来源"]`，
    答的是「这个分怎么来的」；这个看判词前缀，答的是「显示时要不要削掉它」。
    两个问题不同源 —— 深评改判之后 `来源` 会更新而前缀可能忘了删
    （`writeback` 那一支专门在清这个）。
    """
    return bool(_TRIAGE.match(str(verdict or "").strip()))


def gate_of(name: str) -> str:
    """把深评表里的门名归到七道正规门之一。认不出返回空串。"""
    n = (name or "").strip()
    for canon, kws in GATES.items():
        if any(k in n for k in kws):
            return canon
    return ""


def gate_in_verdict(verdict: str) -> tuple:
    """从一句「没过硬性条件」的判词里拆出 `(正规门名, 括号里的原话)`。

    ⚠️ **一条判词挂两道门时，这个函数只认第一道**（见下面那段注释的理由）。
    要问「门名写得规不规范」用复数那个 `gates_in_verdict` —— 两个函数答的是
    两个不同的问题，别互相替代。实测 2026-08-29：校名那一侧误用了这个单数版，
    `硬门 FAIL (工作年限 + 行业背景硬要求)` 这种第一道合法、第二道不合法的写法
    一个都报不出来（该报 29 个，只报了 7 个）。

    两个坑，此前两个消费方各踩一个、各修一半：

    1. **括号有全角的。** 粗筛写 `硬门 FAIL (工作年限)`，深评写
       `不满足硬性条件（学历）` —— 只认半角的话，后者整批解析成空串，
       在面板上全部落进「没说是哪道」。实测 25 个岗，门名明明就写着。
    2. **前缀不止一种。** `audit_pipeline._gate_of_verdict` 只认 `硬门 FAIL`
       开头，于是深评写的那批（实测 40 个）**对每一条按门名分流的检查都是
       隐形的** —— 不是查过没问题，是从来没查过。前缀族本来就有正本
       （`GATE_FAIL_PREFIXES`），这里用它。

    返回 `("", "")` 表示这压根不是一句硬门判词；返回 `("", 原话)` 表示
    **括号里写了东西，但它不是七道门里的任何一道**——那两件事不一样，
    调用方要分开处理（见 `audit_pipeline.check_gate_is_one_of_the_seven`）。
    """
    v = str(verdict or "").strip()
    if not any(v.startswith(p) for p in GATE_FAIL_PREFIXES):
        return "", ""
    n = v.replace("（", "(").replace("）", ")")
    inner = n[n.find("(") + 1:n.rfind(")")] if "(" in n and ")" in n else ""
    # 「工作年限 + 行业背景硬要求」这种一条挂两道门的**按第一道算** ——
    # 拆成两条会让计数大于岗数，「有几个岗被挡住」就不再成立。
    return (gate_of(inner.split("+")[0]) or gate_of(inner)), inner.strip()


def gates_in_verdict(verdict: str) -> tuple:
    """判词里点到的**每一道**门。返回 `(认得的门名列表, 不在七道里的那些)`。

    和 `gate_in_verdict`（单数）分工不同，别合并：

    - **单数那个只取第一道，是对的** —— 它服务于「有几个岗被这道门挡住」，
      一条挂两道门拆成两条会让计数大于岗数。
    - **这个取全部，也是对的** —— 它服务于「门名有没有写规范」，
      而漏看第二道就等于放过它。

    实测活动用户 2026-08-29：判词里点了门名的 747 个岗里，门名不在七道里的
    **29 个**；而按「只看第一道」查只报得出 7 个 —— 差的那 22 个都是
    `硬门 FAIL (工作年限 + 行业背景硬要求)` 这种第一道合法、第二道不合法的写法。
    同一个 helper 被两个不同的问题共用，计数那一侧的取舍悄悄限制了校名那一侧。
    """
    v = str(verdict or "").strip()
    if not any(v.startswith(p) for p in GATE_FAIL_PREFIXES):
        return [], []
    n = v.replace("（", "(").replace("）", ")")
    if "(" not in n or ")" not in n:
        return [], []
    inner = n[n.find("(") + 1:n.rfind(")")]
    # 更里层的括注是理由不是门名：`明确排除（英语口语）` 点的门是「明确排除」
    inner = re.sub(r"\([^()]*\)", "", inner)
    known, off = [], []
    for part in re.split(r"[+、,，]", inner):
        p = part.strip()
        if not p:
            continue
        (known if gate_of(p) else off).append(p)
    return known, off


def is_anonymous_employer(company: str) -> bool:
    """公司名是不是平台脱敏串（「某大型…公司」「保密」）。

    最早那次抽样（195 个岗里 77 个，39%）就看出分界很干净：含「某」的全是脱敏、
    零误伤——工商注册不允许企业名含「某」这类不确定用语；「某」不限定在开头
    （平台常写「上海某大型物流公司」）。抽成函数是为了让测试**测得到它**：
    原来它是导出主循环里的行内表达式，测试只能自建一个 lambda 六正五反自测自，
    把这里改回历史上错过的 `^某` 那套测试照绿。

    **脱敏串不是公司身份，是占位符。** 热库实测 2026-10-24：1626 个岗里 738 个
    脱敏（45%），其中 90.5% 是猎头岗（`/a/` 链接）；光「某知名公司」这一个串就
    出现 78 次 —— 那是 78 家不同的用人方（78 条链接各不相同）。凡是拿公司名当键去匹配、
    分组、去重的地方，都必须先过这道判据（`match_tracker` 就为此漏过一次）。

    （这四个数由 `test_a_masked_name_is_not_a_company.TheDocstringFiguresAreRecomputed`
    现算校验，不是钉死的——语料一变它就红，改的时候连日期一起改。
    **这个比例过去只挪过一次，挪的不是判据**：同日做了两件让热库缩水的事 ——
    把 58 个「热库与存档同时在场」的重复项从热库删掉（`job-scrape.md` Step 4
    「查重还必须连存档一起查」那条，`tests/test_one_url_can_hold_several_jobs.py` 盯着，
    删掉的里脱敏串占 33 个、具名 25 个），`archive.py` 又归档了 4 个出局 56 天的岗。
    两次都只动计数、不动判断，所以脱敏占比从高 30% 挪到现在的 45%。

    2026-10-14 又缩了 5 个：4 个「热库与存档同时在场」的重复项从热库删掉，1 个
    （`AI高级产品经理(J11443)`）反过来从存档删掉——**留热库那份，因为它判的是
    2026-10-13「行业背景不作硬门」裁定之后的样子**，存档那份是 2026-09-01 按已被
    推翻的旧规则判的 FAIL。面板只读热库（`export_web_data` 不啃冷库，冷库只出一个
    计数），所以那份存档的判词不参与任何显示，留着只是让同一个岗有两套结论。

    2026-10-15 再缩 1 个：热库那条 `51job-browser_上海药明康德新药开发_AI应用开发专家(J24770)`
    ——是 71 分「值得投」那条的重复挂法，它自己 58 分粗筛、没材料没投过，`url` 却是
    空字符串，于是导出器拿不到链接就拿**键**顶上，面板上多出一行点不开的死链。
    它手写的 `dupOf` 与 `dup_note` 导出器**两个都不读**（`dupOf` 是导出时按 URL
    前缀现算的，而没链接的条目连自动去重都够不着），所以当初那次「归并到前者」
    的判断压根没生效。

    **两次比例都一个点没动**：删掉的 6 个公司名全是具名的，脱敏数仍是 736、仍是 45%。
    这也说明那五个数各自独立——库缩了不等于脱敏占比会动。

    2026-10-24 这一轮补货新增 3 个岗，其中 2 个是脱敏串：736 → 738，占比仍是 45%。
    ）
    """
    return bool(re.search(r"某|保密|未公开", company or ""))


#: **Unicode 私用区。** 平台用自定义字体把数字映射到这一段，抓取时连映射一起
#: 抄了下来 —— 肉眼是 `30-50K`，文本里是 `U+E037 U+E031 - U+E039 U+E031 K`（`cdp-portals.md`
#: 对 BOSS 那一路记着同一现象）。**凡是「文本里没有数字」这类判断都不成立**。
#: 写成转义：字面私用区字符在源码里不可见，被换掉就会静默变成「匹配不到」。
PUA_RE = re.compile("[\\ue000-\\uf8ff]")

#: 剥掉私用区之后，尾部该剩下的**只有薪资骨架**。这是「切对了地方」的判据：
#: 职位名自己带数字（`【99校招】`、`8000+`），所以光看「有没有 PUA」切不了。
SALARY_SKELETON = re.compile(r"^[\s\-–—~～至到.]*[KkWw]?\s*[·*xX]?\s*[薪元]?\s*"
                             r"(?:/\s*[天月年])?$")


def salary_split(title: str) -> tuple[str, str] | None:
    """`(该保留的头, 该换掉的尾)` —— 切不动就 `None`。

    ## 这一份是**正本**，`fix_pua_titles.salary_tail` 直接引它

    原来切点与骨架这两条判据在 `_cli.plain_title` 和 `fix_pua_titles.salary_tail`
    里**各写了一遍**。常量（`PUA_RE` / `SALARY_SKELETON`）当时搬来了，算法本身
    留在原地 —— 而那个文件自己的注释就写着「同一个值住在两个模块里，没人钉住
    它们相等」。算法比常量更容易漂：改了切点，导出侧显示的标题与那个工具写回库
    的标题就会分叉，**而两边都不报错**。

    相等由 `tests/test_a_job_title_is_not_font_obfuscated.py` 钉住。

    ## 切点为什么取「PUA 之前最近的空格」

    职位名自己可能带私用区（那是别的东西），按位切会削掉职位名本身 —— 宁可漏修。
    骨架里必须容得下小数点（形如 `3.5-4.5K`），日薪（`…元/天`）也算薪资。
    """
    t = str(title or "")
    m = PUA_RE.search(t)
    if not m:
        return None
    cut = t.rfind(" ", 0, m.start())
    head = t[:cut + 1] if cut != -1 else t[:m.start()]
    tail = t[cut + 1:] if cut != -1 else t[m.start():]
    bare = PUA_RE.sub("", tail)
    if not bare.strip() or not SALARY_SKELETON.match(bare):
        return None
    return head, tail


def plain_title(title: str, salary: str = "") -> str:
    """标题上屏/入统计之前过一遍：字体混淆的那段换成同一条记录的 `salary`。

    ## 为什么不照着映射解

    `cdp-portals.md` 写明**那个映射每轮都不一样，不可硬编码**（2026-10-13 那轮是
    `U+E03n → n-1`）。而猎聘走 JSON API，**薪资本来就是结构化字段**——所以这里
    一个映射都不写，直接用同记录的 `salary`。

    2026-10-14 实测：热库 1628 条里 **75 条**标题带私用区，全部在尾部且与本条
    `salary` 逐条对得上（`tools/fix_pua_titles.py` 是那次的数据修复）。

    ## 切不动的就原样留着

    切点与骨架的判据在 `salary_split`（正本）。尾部剥掉私用区之后若不是薪资骨架，
    **不动**——削掉职位名比显示难看更坏。留给守卫去报。
    """
    t = str(title or "")
    pay = str(salary or "").strip()
    parts = salary_split(t)
    if not (pay and parts):
        return t
    return parts[0] + pay


#: 「N 年以上 <限定> 经验」里，哪些限定词算「**没有**领域限定」。
#:
#: 「相关」是最松的一个，故意算进来——**宁可放过，不可误杀**：算成裸年限就是拿
#: 总年限比，门更容易 PASS，正是这道门该有的方向。
#:
#: **正本在这里，不在 `04` 的散文里** —— 理由见 `years_gate_is_domain_only`。
YEARS_BARE = {"", "工作", "相关", "相关工作", "以上", "以上工作"}

#: 深评依据里引的那句年限要求。`(数字, 限定词)`。
YEARS_REQ = re.compile(
    r"(\d+)\s*年(?:以上|及以上|\+|以内|-\d+\s*年)?\s*([^，。；、」\n]{0,20}?)(?:经验|经历)")


def years_gate_is_domain_only(quote: str, total_years: int) -> tuple[bool, str]:
    """`(是不是领域要求, 引文)` —— 判据是 `04-job-evaluation.md`
    「年限门：那个数带不带领域限定」那一条的**可执行版**。

    ## 为什么从散文提上来

    判据原话：「**把年数拿掉，剩下的那半句是不是一条领域要求？**」它在 `04` 里写着，
    2026-08-24 还记了实测「这道门一次都没有真正因为『年数不够』FAIL 过」——
    **而同一段时间里，它正在 14 份深评上误判**（实测 2026-10-14）。

    两句可以并存，因为**散文规则不报错**：判据是给执行者读的，读漏了没有任何东西变红。
    这不是第一次栽在这儿——`04` 里那道判据写得够清楚，栽的是「有没有被执行」。

    提上来之后，`writeback.py` 在**写盘那一刻**就能拒收这种评估（与「把结论写高」
    同一道闸门），判据不再依赖执行者记得遵守。

    ## 判法

    引文里取出 `(N, 限定词)`；**限定词不在 `YEARS_BARE` 里就是领域要求**，而
    `N ≤ 总年限` 时那道门按总年限判就是过的——两条同时成立，这一判就是错的：
    缺的是那个领域，不是年数，按 `04` 该写进业务领域分，不该一票否决。
    """
    m = YEARS_REQ.search(str(quote or ""))
    if not m:
        return False, ""
    n, qual = int(m.group(1)), re.sub(r"[*\s]", "", m.group(2))
    return (n <= total_years and qual not in YEARS_BARE), m.group(0).strip()


def candidate_years(user: str, root=None) -> tuple[int, int] | None:
    """`candidate.md` 的「工作年限说明」→ `(总年限, 方向年限)`；读不出返回 None。

    自由文本，只认「N 年」这种最稳的写法，月份忽略——硬门这一侧宁可少报不可多报。

    **正本在这里**：`audit_pipeline._candidate_years` 原先自己读一遍。现在
    `writeback.py` 也要用同一个数（拒收把领域当年数的年限门），抄一份就会分叉。

    **`root` 是接缝，不是可选参数**：调用方把仓库根换掉时（守卫用临时目录造
    夹具，`tests/test_years_gate_needs_a_number.py` 就是这么做的），本函数必须跟着
    读那个临时目录 —— 不接参数会读到真实仓库去，于是夹具「读不出年限」，
    而守卫报出来的是「候选人年限读不出来」，与被测的东西毫无关系。
    """
    p = (Path(root) if root else ROOT) / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "工作年限" not in line:
            continue
        nums = [int(m) for m in re.findall(r"(\d+)\s*年", line)]
        if len(nums) >= 2:
            return (max(nums), min(nums))
    return None


def years_row(text: str) -> tuple[str, str]:
    """深评里硬性条件表**「工作年限」那一行的 `(判定, 依据)`**。

    JD 原文就引在依据格里 —— 判断那道门判得对不对不必回头去读 JD。
    读不到（门名写法不同、这行不是 markdown 表）返回 `("", "")`。

    **判定与依据都要拿**：只有判定是 FAIL 才轮到那条判据说话。
    只看依据格的话，一份把年限门判成 **PASS**、只是照抄了 JD 原话（含领域限定）
    的评估也会被当成误判 —— 那就把「引了原文」和「判错了」混成一件事了。
    """
    m = re.search(r"^\|\s*[*]*工作年限[*]*\s*\|([^|]*)\|([^|]*)\|",
                  str(text or ""), re.M)
    return (m.group(1), m.group(2)) if m else ("", "")


#: 打招呼开场白的铁律（`06-outreach-templates.md`「这 200 字里不许出现的五类」）。
#: `类别 → 认得出的写法`。表里那几个词**就是那份文档「实际写过的」那一列**
#: 抄下来的原句片段 —— 它已经把真实犯过的错列出来了，这里只是让它可执行。
#:
#: ⚠️ **只管渠道 1（打招呼）。** 邮件、网申自评、求职信不受此限，
#: 那些场合对方在读你的完整材料，谈条件、讲缺口都正常（那份文档明写着）。
#:
#: **正本只有这一份。** 2026-08-23 一度出现两份：`export_web_data.GREETING_BANS`
#: （面板复制按钮旁的提示）和 `audit_pipeline._GREETING_BANS`（全库审计）。
#: 两份词表不一样，于是同一件事报两个数 —— 开场铺垫那一类，一边 32 份、
#: 一边 17 份。**词表就是判据，判据分叉就是两套标准。** 现在这里是唯一一份，
#: 那两处都从这里取；下次要加词，加在这里。
GREETING_BANS = {
    "开场铺垫": ("想聊一下", "看到这个", "看到贵司", "我想应聘",
                 "关注到贵", "留意到贵", "注意到贵"),
    "先谈钱": ("期望薪", "期望年包", "期望区间", "是几薪", "几薪算",
               "差距比较大", "薪资方面", "薪资期望", "薪资要求", "定级"),
    "抢答到岗时间": ("随时到岗", "目前离职", "即可到岗", "到岗时间", "可立即"),
    "给短处加引子": ("先说清楚", "要说清楚的是", "有一条要先说", "得先说",
                     "坦白说", "说句实话"),
    "套话开头": ("贵司平台", "深受吸引", "久仰", "非常荣幸",
                 "学习能力强", "踏实肯干"),
}

#: 「AI 味清单」（`03-writing-style.md`「中文文案的 AI 味清单（出现即改写）」）。
#:
#: **和上面那份不是同一份，别合并。** `GREETING_BANS` 抄的是 `06` 那张
#: 「这 200 字里不许出现的五类」，只管渠道 1；这一份的正本是 `03`，管的是
#: **所有对外文案**（三渠道话术 + 简历正文）。两份各有各的出处文档，
#: 混成一份之后谁也说不清某个词是从哪条规则来的 —— 那正是上面那段注释
#: 记着的分叉事故（同一件事报 32 和 17 两个数）。
#:
#: ⚠️ **简历正文仍然没有机械查。** 开场白走 `greeting_hits`，邮件 / 网申自评 /
#: 求职信 / 内推请托 2026-08-27 起走 `style_hits`（自检那条叫「对外文案：
#: 另外几个渠道的文风」），**只剩简历正文还没有** —— 这是覆盖不全，不是豁免。
#: 说出来，别让「查过了」被误读成「所有对外文字都查过了」。
#:
#: 简历那一处不是忘了，是**输入不对**：照 `.typ` 源文件扫，实测 41 处命中里
#: 25 处落在 Typst 注释里（永远不进 PDF）、15 处是同一句话被复制进 15 份
#: 定制版、真的只有 1 处。要接就得拿**渲染出来的文本**当输入，并按句子去重
#: 而不是按文件数 —— 判据见 `audit_pipeline` 那条检查里的同一段说明。
#:
#: 实测活动用户 2026-08-23：236 份可粘贴开场白里 **17 份（7%）**命中 ——
#: 赋能 6、闭环 5、打法 4、优秀的 1、对齐 1。
#:
#: **「套话」那一类原来没有搬过来**，理由写的是「`03` 的求职套话和 `06` 的
#: 「套话开头」是同一批词，上面那份已经有了」—— **那个前提是错的：8 个词里
#: 只重合 2 个**（`贵司平台` / `深受吸引`）。
#:
#: 另外六个（我深信、我坚信、慕名而来、恳请给予机会、不胜感激、
#: 若能加入定当全力以赴）**两张表都没有**。2026-08-31 实测演示：
#:
#:     「您好，贵司平台好，我深信自己能胜任，慕名而来，恳请给予机会，不胜感激。」
#:     greeting_problems → 只报「贵司平台」一条；style_hits → []
#:
#: 同一段话当邮件正文发出去，报的是「零问题」。而 `03` 那张清单的抬头写着
#: 「出现即改写」，适用范围是**所有对外文案**。
#:
#: 补的是那六个，不补重合的两个 —— 它们在 `GREETING_BANS` 里，
#: 而 `greeting_problems` 两张表都读，重复登记就会在开场白上报两遍。
#: 真语料 948 份材料实测这六个词 **0 命中**，补进来当天不多报任何一条；
#: 它防的是以后写出来没人拦。
#:
#: 覆盖完整性由 `tests/test_the_ai_flavour_list_is_actually_checked` 钉住：
#: `03` 那一节列的每个词都得落在这两张表之一里。
STYLE_BANS = {
    # `方法论沉淀` 在 `03` 里带一个条件豁免（「除非确实在描述一份可交付的
    # 方法论文档」）—— 机械判不了那个条件，所以照样报出来，由人看一眼。
    # 同下面「空心动词」那条：这个检查是提示，不是闸门。
    "互联网黑话": ("赋能", "抓手", "闭环", "颗粒度", "对齐", "拉齐",
                   "心智", "组合拳", "打法", "顶层设计", "生态位",
                   "方法论沉淀"),
    # `03` 原话：「后面必须跟数字或具体事实，否则删掉」——
    # 「跟没跟数字」判不准（数字可能在下一句），所以这里只报出现，由人看一眼。
    "空心动词": ("负责推动", "深度参与", "有效提升", "显著改善"),
    "万能形容词": ("优秀的", "丰富的", "良好的", "较强的"),
    # `贵司平台` / `深受吸引` 不在这里 —— 见上面那段：它们住在 `GREETING_BANS`。
    "求职套话": ("我深信", "我坚信", "慕名而来", "恳请给予机会",
                 "不胜感激", "若能加入定当全力以赴"),
}

#: 开场白字数硬上限（同一份文档：「**硬约束：≤200 字。**」）。
#: **句式**上的翻译腔。上面 `STYLE_BANS` 管的是词，这一份管的是**句子的搭法**——
#: 换词换不掉，得重写。
#:
#: ## 判据不是语感，是拿真人写的中文比出来的
#:
#: 实测 2026-08-24。参照语料是活动用户库里 **1486 份 JD** —— 那是国内 HR 与
#: 用人方自己写的中文，跟这些开场白面向的是同一批读者。逐份查，命中的份数：
#:
#:     句式                        1486 份真人 JD   236 份 outreach   其中开场白块
#:     「…，是我…的事」                  0 份           13 份           11 份
#:     「正是我在做的」                    0 份            5 份            5 份
#:     「我不是 A，是 B」                  0 份            3 份            2 份
#:
#: （最后一列是审计报的数 —— `check_greeting_keeps_the_five_rules` 只扫
#: 200 字那一块。这三条本身适用于所有对外文案，中间那列才是它的范围。）
#:
#: **一个在 1486 份母语商务写作里出现 0 次、在我们 236 份里出现 13 次的句式，
#: 不是风格偏好，是口音。**
#:
#: 而真人写同一件事的搭法就在同一份语料里：`负责 Agent 的推理调度与资源管理`、
#: `主导大模型项目落地的关键技术工作` —— **动词打头，不把动作名词化**。
#:
#: ## 第三条差点写错：「不是 A，而是 B」本身是中文的正常说法
#:
#: 第一版的正则把「我」写成可省的（`(我)?不是…，(是|而是)`）。拿去一比：
#: **1486 份真人 JD 里命中 23 份** —— 全是用人方在给岗位划边界，
#: `不是执行者，而是`、`不是功能的堆砌者，而是`、`不是传统销售执行岗，而是`。
#: 那是母语里好好的一个修辞，不是毛病。
#:
#: 把主语钉死成「我」之后：**JD 0 份，开场白 3 份**（`我不是听说过，是`、
#: `我不是了解，是`、`我不是新闻，是`）。变坏的不是句式，是**谁在辩解** ——
#: 对方在筛人，没质疑过你，先辩解等于自己把那个指控替他说出来。
#:
#: 差一个「我」字，23 份误报变 0 份。**这条规则的价值全在那个字上。**
#:
#: ## 用户原话（2026-08-24）
#:
#: > 「把智能体的功能、性能指标和交互流程定清楚，是我做自己产品时天天在干的事；
#: >  Agent 的原理和主流框架我不是听说过，是真在用。」
#: > —— 这句话根本不符合中文习惯
#:
#: 那一句同时踩了两条：先把动作名词化成主语，再接一个没人质疑过的辩解。
#: 改法见 `03-writing-style.md`「句式：中文不这么说」那张表。
#:
#: ⚠️ **类别名是印给用户看的**（面板那句「「…」是<类别>」），所以叫「翻译腔」
#: 不叫「动作名词化」—— 前者是中国人本来就在用的词，后者得先学一遍语言学。
#: 判据同 `AGENTS.md`「内部词不要搬到台面上」。
#: 内部词 → `(词, 匹配式, 换成什么)`。判据在 `AGENTS.md`「给用户看的措辞」那张表。
#:
#: ## 为什么这份要在 `_cli` 里
#:
#: 这件事此前有**四张手工维护的表**：审计的检查器（`_HEAD_JARGON`，只有词）、
#: 审计的正文表（`_DOC_JARGON`，带匹配式与替换）、话术抬头的修理工
#: （`outreach_header.INTERNAL`，带替换）、显示层（`export_web_data.INTERNAL_TERMS`）。
#:
#: 前三张里有两张管的是**同一层**（抬头）：一张负责报、一张负责改。
#: 2026-08-30 实测它们已经分叉 —— 检查器认得 `驾驶舱`，修理工不认，
#: 于是收尾报了「1 份用了内部词」，而修理工说「要改 0 份」，
#: **只好推给人手工改一份**。检查器与修理工分叉，等于把能自动做的事退回给人。
#:
#: 所以主表在这里，`_HEAD_JARGON` 和抬头修理工都从它派生。
#: 显示层那张仍然独立：它最宽（换错了顶多把「业务领域」说成「行业经验」，
#: 意思还在），判据见 `_DOC_EXCLUDE` 旁边那段「各自的误伤代价」。
#:
#: `硬门` 的匹配式要排掉 `硬门槛` —— 后者是中文里本来就有的词（实测 7 处），
#: 该换的只是框架自己造的那个简称。
HEAD_JARGON = (
    ("判词", r"判词", "结论"),
    ("四维", r"四维", "评分明细"),
    ("硬门", r"硬门(?!槛)", "硬性条件"),
    ("台账", r"台账", "投递记录"),
    ("驾驶舱", r"驾驶舱", "总览页"),
    ("短名单", r"短名单", "可以投的岗位"),
    ("读数", r"读数", "岗位详情"),
    ("能力边界", r"能力边界", "经历对不上的地方"),
)


STYLE_PATTERNS = {
    # 「把 X 定清楚，是我天天在干的事」——先把动作卷成一个名词性主语，
    # 再用「是…的事」判断。中文口语里动词直接打头就完了。
    # ⚠️ **「是我」前面允许插一个副词。** 原来写死 `，\s*是我`，于是
    # 「…任务树，**正**是我这两年一直在想的事」整句漏过去 —— 多一个「正」字就断了。
    # 2026-08-25 用户当场指出那句「根本不符合中文习惯」，而检查器说没问题：
    # **规则是对的，判据太字面。**
    "翻译腔（动作当主语）": r"[，。；]?[^，。；\n]{4,30}，\s*(?:正|就|恰|才)?是我[^，。；\n]{0,16}的事",
    # 「我不是听说过，是真在用」——回答一个没人问过的指控。
    # **「我」不能省**：省了会把 JD 里 23 份正常的「不是 A，而是 B」当成毛病，
    # 判据见上面那一节。
    "替对方先辩解": r"我不是[^，。；\n]{1,14}[，,]\s*(是|而是)",
    # 「这正是我在做的」——同一族的自我认证句。真人写的是「我在做 X」。
    # ⚠️ **中间允许插状语，动词也不止「做」。** 原来要求「正是我」紧跟「做的」，
    # 「正是我**这两年一直在想**的事」就漏了 —— 而「在想」比「在做」更虚，更该抓：
    # 对面在筛人，想过不算做过。
    #
    # 放宽的代价用同一份参照语料量过：**1497 份真人 JD 上放宽前后都是 0 命中**，
    # 没引入误报（这一族的判据本来就是「真人写作里出现 0 次」）。
    "翻译腔（自我认证）": r"(?:正|恰)是我[^，。；\n]{0,14}(?:在做|做|在想|想)的",
    # 「XX 是我这三年一直在做的事」。和上面第一条是同一族的两半：那条要求
    # `是我` 前面有逗号，而这一类多半没有，整条从它下面漏过去。
    # **正本在 `03-writing-style.md`「句式」那张表第四行**，所以住在这里
    # 而不是渠道 1 专属的那一份 —— 实测 2026-09-02，开场白之外还有 20 段同病
    # （内推请托 14、邮件 4、网申自评 2）。
    "拿年头自证": (r"[正就]?是我(?:这|近)?\s*(?:三|两|几|四|五|多)\s*年"
                 r"[^，。；\n]{0,14}(?:的事|的日常|在做的|一直在做|常规做法|主线|工作方式|常态)"
                 r"|(?:这|近|过去)\s*(?:三|两|几|四|五|多)\s*年"
                 r"(?![^。！？\n]{0,8}经验)"
                 r"[^。！？\n]{0,18}?(?:在做|在干|做|干)"),
}

GREETING_MAX = 200

#: 一次最多列几条踩线的词。列满不代表列全 —— 超出的条数由 `greeting_problems`
#: 明说出来（这个仓库不留沉默的截断）。3 是「一眼能改完」与「别把整段话
#: 抄成清单」之间取的：实测 37 份踩线的里 35 份只有 1-2 条。
GREETING_SHOW = 3

#: 「期望 45-60k」——那张表「钱」那一行的**第一个**例子（报期望），
#: 而它是「期望」直接跟数字，逐字词表抓不到。**要求带单位**（k / 万 / w）才算：
#: 「期望能在三年内…」不是在谈钱，而这类检查误报一次就会被整条忽略。
_GREETING_PAY_NUM = re.compile(r"期望\s*[\d０-９][\d０-９.,\-~－ ]*\s*[kK万wW]")

#: 问候语本身。`06` 渠道 1 那张表：「**「您好，」+ 最硬的匹配点**，中间不许有
#: 任何别的东西」，并且专门交代「「您好，」要留 —— 中文里不打招呼直接说事是失礼」。
#:
#: **标点认全，不只认逗号。** 实测活动用户 2026-10-15：405 份开场白里
#: 「您好」之后跟逗号的 368 份、**跟句号的 8 份**、不以「您好」开头的 29 份
#: （那 29 份里 23 份是「你好，」）。三项互斥，加起来正好是总数。
#: 原来只认 `[，,]`，于是那 8 份剥不掉问候语 —— 而两个消费方都建立在
#: 「剥完再看开头」之上：`opening_padding`（开场铺垫，命中最多的一类）
#: 和 `gap_before_evidence`（缺口的位置）。对那 8 份，两条检查整个空转。
#:
#: 眼下代价是零（那 8 份恰好都没踩这两条），但那是运气不是判据：
#: **一个对 2% 的写法整个不适用的检查，平时和「全都合规」长得一模一样。**
_GREETING_OPENING = re.compile(r"^[您你]好[，,。.！!～~\s]*")

#: 「开场铺垫」**只发生在开头**，而且岗位名会插在词与词中间。
#:
#: 上面 `GREETING_BANS["开场铺垫"]` 那几个是**整串**：`看到这个`、`我想应聘`……
#: 而真实写法是「看到 **AI 产品专家** 这个岗」「看到 **某某 Agent 方向** 的
#: 产品岗」—— 岗位名一插进去，整串就匹配不上。实测活动用户 2026-08-24
#: （当时语料 264 份）：**69 份**开头是铺垫，而按整串只认出 **32 份**。
#: （这正是本仓库反复栽的同一课：`fetch_details.needs_recheck` 的
#: 「按语义片段判、不能按整串」，以及判词天花板那次「读过」vs「读了」漏 613 条。）
#:
#: 反过来也修了一处**误报**：整串是全文搜的，而这一类的定义是「开头那句」。
#: 实测 3 份被误判 —— 它们开头讲的是候选人的本事，「想聊一下」出现在正文靠后
#: 的位置（那儿是正常的收尾邀约，不是铺垫）。
#:
#: 判据取「问候之后的第一小句在说什么」：说**看到了这个岗 / 想投这个岗**，
#: 那是对方已经知道的事（他写的 JD、你在给他发消息）；说**候选人干过什么**，
#: 那才是这 200 字该用的地方。
_OPENING_PADDING = re.compile(
    r"^(?:看到|注意到|留意到|关注到|拜读)[^。；\n]{0,24}(?:岗|职位|机会|招聘|贵司|JD)"
    r"|^我想(?:应聘|投|试试)"
    r"|^这个(?:岗|职位)[^。；\n]{0,12}(?:很对|不错|感兴趣|方向|我想)"
    r"|^想聊(?:一下|聊)")


def opening_padding(text: str) -> str:
    """开头那句是不是铺垫；是就返回它，好让调用方原样引出来。"""
    body = _GREETING_OPENING.sub("", (text or "").lstrip())
    m = _OPENING_PADDING.match(body)
    return m.group(0) if m else ""


#: 开场白里「点自己一条缺口」的写法。实测活动用户 2026-08-26：253 份里 96 份
#: 点了缺口，写法就这几种（`我没做过` 59、`没做过` 17、`我没接触过` 7、
#: `没碰过` 4、`不是我的强项` 2、`我没碰过` 1）。
#:
#: ⚠️ **点缺口本身是对的，不是违规。** `06-outreach-templates.md`「缺口」那一节
#: 规定「一眼可见」的必须写，还把「行业背景与 JD 点名的不符」列在第一档，
#: 例句逐字就是「保险我没做过，承保、理赔都得从头学」。这个正则不是用来抓它的。
_GREETING_GAP = re.compile(
    r"我?(?:完全)?没(?:有)?(?:做过|设计过|带过|接触过|碰过)|不是我的强项|不熟悉|零经验")


def gap_before_evidence(text: str) -> str:
    """缺口排在了匹配点前面；是就返回那一句，好让调用方引出来。

    同一节还有一条**位置**规则，它是机械可验的：

    > 一眼可见的也**不许排在匹配点前面**：把「我 <你的年龄> 岁超了线」放开头，
    > 等于让对方在读到你能干什么之前先读到一条过滤理由。

    判据：问候语之后的**第一小句**里就出现缺口写法。开场白的结构是
    「您好，+ 最硬的匹配点 → 佐证 → 缺口 → 问题」，缺口落在第一小句就意味着
    佐证还一个字没说。

    实测活动用户 2026-08-26：点了缺口的 96 份**全部**排在佐证之后，一份没犯。
    加它不是因为有存量要清，是因为**这条规则此前没有任何一处在执行**
    —— 五类禁区里四类有词表盯着，位置这条只写在散文里。
    """
    body = _GREETING_OPENING.sub("", (text or "").lstrip())
    first = re.split(r"[。！？；]", body, maxsplit=1)[0]
    m = _GREETING_GAP.search(first)
    return first.strip()[:24] if m else ""


def style_hits(text: str) -> list:
    """`03-writing-style.md` 那几条**四个渠道都适用**的风格铁律。

    ## 为什么单独拆出来

    `06-outreach-templates.md` 渠道 1 那张表的五类禁区末尾有一句 ⚠️：
    「**五条只管渠道 1。** 渠道 2（邮件）、3（网申自评）、4（求职信）不受此限
    —— 那些场合对方已经在读你的完整材料，谈条件、讲缺口都是正常的。」

    而 `03` 的铁律没有这个豁免：AI 味、互联网黑话、翻译腔，在哪个渠道都不该有。
    两套规则的适用面不同，所以拆成两个函数 —— 混在一起，新渠道要么被五类禁区
    误伤，要么整个查不上。

    实测活动用户 2026-08-27：开场白之外还有 30 段对外文案（邮件 9、网申自评 9、
    内推请托 9、求职信 3），此前**一个检查器都没有**（那条自检自己写着这句）。
    一查，**网申自评 9 段里 5 段踩线**：翻译腔 4、互联网黑话 1（「闭环」）。
    """
    t = text or ""
    out = [(cat, w) for cat, words in STYLE_BANS.items() for w in words if w in t]
    # **句式那一份是正则，不是词表** —— 翻译腔换词换不掉，得看句子怎么搭的。
    # 判据（1486 份真人 JD vs 236 份我们写的）见 `STYLE_PATTERNS`。
    for cat, pat in STYLE_PATTERNS.items():
        m = re.search(pat, t)
        if m:
            out.append((cat, m.group(0).strip()[:24]))
    return out


#: 「把他写的那半句引回去」。**判据不是措辞，是那半句话是谁写的。**
#:
#: `06-outreach-templates.md`「不要把 JD 复述给招聘方听」封的是三个措辞
#: （`JD 里` / `JD 说` / `JD 写`），于是写手换个引语动词就绕过去了。实测活动用户
#: 2026-10-15：405 份开场白里 **0 份**还在引——2026-09-02 第一次量到的是 70 份，
#: 写法分三种：
#: 换引语动词（`看到您写「…」`）、连引语动词都省掉（`「让 AI 写代码、人定规则」
#: 这件事我做了三年`）、引完再对表打勾（`JD 里「…」这条我可以直接交作业`）。
#:
#: 而当时那 70 份里有一份的自检逐条打着勾，其中一条原话是
#: 「无 JD 原文照抄**（引用那半句是刻意的，且加了引号）**✓」——
#: **写手自己把规则说服掉了，还给它记了个合格。** 散文规则挡不住这个。
#:
#: ⚠️ **提问句要放过。** 同一节留着例外：「向对方要东西或问澄清时可以提」，
#: 实测 7 句属于这一类（`想先要一份完整 JD 看任职要求`、
#: `JD 写 35 岁以下，我 2012 年本科毕业，这条卡得死吗？`）。那是在问，
#: 不是在复述 —— 所以这条**按句判**，落在问句里的一律不算，
#: 41 句陈述句才是要抓的。整段全文搜会把那 7 句一起报掉，
#: 而这类检查误报一次就会被整条忽略（判据同 `_GREETING_PAY_NUM`）。
_GREETING_JD_QUOTE = re.compile(
    r"JD"
    r"|「[^」]{8,}」"
    r"|看到[您你](?:写|提到)"
    r"|看到(?:岗位|职位|招聘)[^。；\n]{0,6}(?:写|提)"
    r"|[您你]写的那?(?:条|句|半句)")


def jd_restated(text: str) -> str:
    """把对方写的话引回去了；是就返回那一句，好让调用方原样引出来。

    按**句**判，不按全文搜：`06` 那一节留了一处例外（问澄清时可以提），
    而例外与违规的差别正在于这句话是不是在提问。
    """
    for s in re.split(r"(?<=[。！？；?!])", text or ""):
        if s.rstrip().endswith(("？", "?")):
            continue                      # 在问，不是在复述
        m = _GREETING_JD_QUOTE.search(s)
        if m:
            return s.strip()[:28]
    return ""


#: 「XX 是我这三年一直在做的事」。本人 2026-09-02 原话：「这种也没任何意义」。
#:
#: 和 `STYLE_PATTERNS["翻译腔（动作当主语）"]` 是**同一族的两半**：那条要求
#: `是我` 前面有个逗号（动作先卷成名词性主语再判断），而这一类多半没有逗号
#: —— `Agent 产品定义是我这三年一直在做的事`，整条从它下面漏过去。
#: 实测（2026-09-02，当时语料 308 份）**37 份**。这一类后来逐份改过，
#: 现算已是 0 —— 数字留着是为了说明这条判据当初为什么要立。
#:
#: 为什么它没意义：时间跨度是**关于自己的断言**，对方无从核实，
#: 而它偏偏占着第一行 —— 会话列表里他只看得到那一行。本人给的改法是把那件事
#: 直接说出来（`我以 Claude Code、DeepSeek 为主力工具，从原型到上线一个人跑完`），
#: 同样长度换成了可核的事实。
#:
#: ⚠️ **`天天在用` 不在这里。** `06` 那张表明文拿它当**推荐改法**
#: （「这几样我天天在用」），实测 2026-09-02 31 份用了它。抓它等于拿规则打规则。
#: 这条只抓「拿年头自证」那一种。
#:
#: ## 第一版的尾巴写窄了，当天就漏了 15 份
#:
#: 原来第二支要求动词是 `在做|在干|这么做|做的`，于是
#: **「这两件事我这三年一直在同时做」整句漏过去** —— 只因为末尾是光杆的
#: 「做」。同一天报了「129 → 0，全清了」，而这 15 份还在盘上，
#: 其中一份正是用户点开面板复制到的那一句。
#:
#: **规则对，判据窄** —— 和「开场铺垫」按整串匹配漏掉 36 处是同一个病
#: （见 `_OPENING_PADDING`）。这个仓库第三次栽在同一处：
#: **别把动词写死成几个固定搭配，中文的状语可以插在任何地方。**
#: 现在第二支只要求「时间状语在动词前」，动词放开到 `做|干`。
#:
#: ## 两处不抓（都不是这个毛病，抓了就是误报）
#:
#: 1. **岗位自己写的年限**：「岗位挂 1-3 年经验，我做了 13 年」——
#:    那是在点一条一眼可见的差距（`06` 的「缺口」那一节明文要写），
#:    句子里的「年」属于对方的要求，不是他的自证。实测 2 份。
#: 2. **动词在前、时长在后**：「<你的产品> 的社区我运营了三年」——
#:    那是一件具体的事带一个时长，可核；而「XX 是我这三年一直在做的事」
#:    的宾语就是那件事本身，没有东西可核。**这一类机械分不出来**
#:    （「AI native 的产品设计我做了三年」同样是动词在前，却是自证），
#:    所以这条正则不管它，靠人看 —— 说出来，别让「查过了」被读成「全查了」。
_GREETING_TENURE = re.compile(
    r"[正就]?是我(?:这|近)?\s*(?:三|两|几|四|五|多)\s*年"
    r"[^，。；\n]{0,14}(?:的事|的日常|在做的|一直在做|常规做法|主线|工作方式|常态)"
    # 时间状语在动词前 = 拿年头自证。动词放开到光杆的「做 / 干」。
    r"|(?:这|近|过去)\s*(?:三|两|几|四|五|多)\s*年"
    r"(?![^。！？\n]{0,8}经验)"          # 「岗位挂 1-3 年经验」不算
    r"[^。！？\n]{0,18}?(?:在做|在干|做|干)")

#: 「一年 40 个开源项目」。`06` 铁律 0 那张表「拿产量当卖点」那一行，
#: 2026-08-13 就定了，此前**没有任何一处在执行** —— 实测（2026-09-02，
#: 当时语料 308 份）36 份。这一类后来逐份改过，现算已是 0。
#: 改法在那一行里写着：换成 `candidate.md` 里市场验证过的数（用户量、stars）。
#:
#: **`独立开发者` 不在这里**，虽然「别自报独立开发者」是同一天定的同一族规则：
#: 那一条带一处例外（「主动说清短板时可以出现」），机械判不了。
#: ⚠️ **中间允许插动词。** 第一版写死 `\s*`，于是「一年**出了** 40 个公开仓库」
#: 漏过去 —— 和 `_GREETING_TENURE` 第一版同一天犯的同一个错。
_GREETING_YIELD = re.compile(
    r"(?:一年|每年|年均)[^，。；\n]{0,6}?[\d０-９]+\s*(?:个|多个|余个)?\s*"
    r"(?:公开)?(?:仓库|开源项目|开源仓库|项目)")


def greeting_hits(text: str) -> list:
    """开场白里踩到的 `(类别, 认出来的那个写法)`。**两个消费方共用这一个。**

    返回原写法而不只是类别：面板要把它引出来给用户看（「「我想应聘」是开场铺垫」），
    审计要按类别汇总。一个函数供两种用法，词表就不会再分叉。

    = 渠道 1 专属的五类禁区（`GREETING_BANS`）+ 四渠道通用的风格铁律
    （`style_hits`）。后者拆出去是因为渠道 2-4 只受后者约束，见它的说明。
    """
    t = text or ""
    # **「开场铺垫」不走这条全文搜的路** —— 它按定义只发生在开头，全文搜会把
    # 正文靠后那句正常的收尾邀约也算进来（实测误报 3 份）。判据见
    # `opening_padding`；这里跳过它那一类，下面单独判。
    out = [(cat, w)
           for cat, words in GREETING_BANS.items() if cat != "开场铺垫"
           for w in words if w in t]
    out += style_hits(t)
    pad = opening_padding(t)
    if pad:
        out.append(("开场铺垫", pad))
    m = _GREETING_PAY_NUM.search(t)
    if m:
        out.append(("先谈钱", m.group(0).strip()))
    # **位置也是一条铁律，不只是措辞。** 缺口本身该写（一眼可见的必须写），
    # 但排在匹配点前面就等于先递上一条过滤理由。判据见 `gap_before_evidence`。
    first = gap_before_evidence(t)
    if first:
        out.append(("缺口排在了匹配点前面", first))
    # **把他写的那半句引回去**，加不加引号都算 —— 判据见 `jd_restated`。
    jd = jd_restated(t)
    if jd:
        out.append(("复述职位描述", jd))
    # 「拿年头自证」**不在这里** —— 它 2026-09-02 起住在 `STYLE_PATTERNS`
    # （`style_hits` 已经在上面调过），因为它管的是四个渠道，不只开场白。
    # 判据与那天的实测见 `03-writing-style.md`「句式」那一节的 ⚠️。
    m = _GREETING_YIELD.search(t)
    if m:
        out.append(("拿产量当卖点", m.group(0).strip()[:24]))
    return out



#: 对着**猎头顾问**说了只有用人方才该听的话。
#: `06-outreach-templates.md` 渠道 1 那张表原话：「对面是顾问不是用人方。
#: 跟他讲『贵司如何如何』是讲错了人」——他要判断的只有一件事：这人能不能推。
WRONG_ADDRESSEE = re.compile(r"贵[司公]司?|贵团队|你们(?:公司|团队)")


def head_of(text: str) -> str:
    """`outreach.md` 第一个 `## ` 之前那块抬头。"""
    return text.split(chr(10) + "## ")[0]


def addressee_said(head: str) -> str:
    """抬头自称在跟谁说话：`猎头` / `直招` / 空串（没说）。"""
    if "直招" in head or "非猎头" in head:
        return "直招"
    return "猎头" if "猎头" in head else ""


def addressee_problem(head: str, greeting: str, is_headhunter) -> str:
    """这份话术在「跟谁说话」上有没有问题。**说给用户听的话**，没问题返回空串。

    ## 为什么这半句值得单独查

    第二轮怎么说话完全取决于它（`06`「渠道判定」那张表）：**猎头**问薪资与
    到岗时间要直接答，**HR 直招**不主动展开。写反了，第一次回话就走错方向。

    实测活动用户 2026-08-25（243 份话术）：

        没写是猎头还是直招      110 份
        **写反了**             **28 份**
        猎头岗对着顾问说「贵司」   9 份

    审计一直在报这三个数，但那是**事后**的一份清单。这个函数把同一个判据挪到他
    **按下「复制开场白」那一下**旁边 —— 和 `greeting_problems` 同一个位置，
    理由也是同一个：那才是他真正要用这段话的时刻。

    **开场白按参数传进来**，不在这儿自己切：剥尾部自检元数据那一步走的是
    `build_dashboard._strip_wordcount`，而本文件是所有工具的底座，反向 import
    会成环。两个调用方手上本来就有那段文本。

    `is_headhunter` 为 `None`（库里没判过）时**只查「贵司」那一条**，
    不报「写反了」——没判过不等于判过是「不是」。
    """
    said = addressee_said(head or "")
    out = []
    if is_headhunter is not None:
        real = "猎头" if is_headhunter else "直招"
        if said and said != real:
            out.append(f"抬头写着「{said}」，而这个岗库里是{real}——"
                       f"按写错的那个说，第二轮就走反了")
        elif not said:
            out.append(f"抬头没说在跟谁说话（这个岗是{real}）")
    elif not said:
        out.append("抬头没说在跟谁说话")
    if is_headhunter:
        m = WRONG_ADDRESSEE.search(greeting or "")
        if m:
            out.append(f"对着猎头顾问说「{m.group(0)}」——他不是用人方，"
                       f"他要判断的是「这人能不能推」")
    return "；".join(out)


#: 开场白里**对公司下断言**的迹象。命中就意味着这段话里有一条需要核实的主张。
#: 只认「说了公司的事」，不认「说了自己的事」—— 后者的出处是他的资料，
#: 不是外部来源。
#:
#: **正本搬到这里是因为第二个消费方来了**（2026-08-31）。判据原来私有在
#: `audit_pipeline`，而那个模块**反过来 import `export_web_data`** ——
#: 导出侧要共用就只能再抄一份，而「同一份文本两个读法就是两套标准」
#: 是这个仓库反复栽过的形状。
COMPANY_CLAIM = re.compile(
    r"贵司|你们|咱们|公司.{0,6}(在|已|正|刚|去年|今年)|融资|上市|发布了|推出了|布局")


def fact_items(text: str) -> list:
    """`outreach.md` 里「本次使用的公司事实」那一节列出来的条目。

    骨架里那行 `<…>` 占位说明不算内容 —— 它是模板留下的坑，不是查过的事实。
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("#") and "公司事实" in ln), None)
    if start is None:
        return []
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        if re.match(r"\s*[-*]\s+\S", ln) and "<" not in ln:
            out.append(ln)
    return out


def claim_without_source(greeting: str, facts: list) -> str:
    """开场白对公司下了断言、而出处那一节是空的。没有问题就返回空串。

    `03-writing-style.md` 铁律 1 是「绝不编造」，而一条没有出处的公司主张
    **没有任何办法验证**：审稿者验不了，用户两周后自己也想不起来是从哪看的。

    ## 范围是量出来的，不是拍的

    第一版查的是「那一节空不空」，报 228/236 —— 大部分是假阳性。现算
    （2026-10-15）：405 份开场白里对公司下断言的只有 **19 份（5%）**，
    其中 9 份没记出处（这两个分子由 `audit_pipeline` 的「说了公司的事就要有出处」现算，
    与分母同日）。另外那 95% 讲的全是他自己的经历怎么对上这个岗，
    那些主张的出处是 `profile/candidate.md`，不在这一节里，空着是对的。

    40 字那道下限同理：太短的那几段还没成句，判不出主张。

    ## 两个消费方，一个判据

    审计事后报一份清单（「开场白说了公司的事，却没记从哪看来的」），
    面板报在他按「复制开场白」的那一下 —— 和 `addressee_problem`、
    `style_problems` 同一个位置、同一个理由。
    """
    if len(greeting or "") < 40 or not COMPANY_CLAIM.search(greeting or ""):
        return ""
    if facts:
        return ""
    return "说了公司的事，却没记从哪看来的"


def _as_problems(hits: list) -> list:
    """把命中列表说成给用户看的话。**措辞与截断只有这一份。**

    截断了要说截了多少 —— 原来直接 `[:3]` 收尾：用户把列出来的三条删完，
    以为这段干净了，而第四条还在里面。**沉默的截断**在这个仓库里是有名字
    的一类（审计每条都写「另有 N 份没算」）。

    抽出来是因为第二个消费方来了（`style_problems`）：两份各写一遍，
    改一处另一处不会红，而用户在同一块屏幕上会看见两种说法。
    """
    out = [f"「{w}」是{cat}" for cat, w in hits[:GREETING_SHOW]]
    if len(hits) > GREETING_SHOW:
        out.append(f"还有 {len(hits) - GREETING_SHOW} 条同类的，一并看一遍")
    return out


#: `candidate.md` 里哪几节构成「他自己划的排除」。`04` 把能力边界与明确排除
#: 同权（资料里原话「与『明确排除』同权」），所以两节都算出处。
EXCLUSION_SECTIONS = ("明确排除", "明确的能力边界", "补充确认")


def exclusion_entries(user: str, root=None) -> list:
    """他资料里那几节排除条款的**逐条**原文。读不出返回空表。

    和 `audit_pipeline._exclusion_anchors` 读同样几节，但切法不同：
    那边把整片文字揉成一袋二字片段（只答「找不找得到出处」），
    这边要**分得出是哪一条** —— 因为要数的正是「每条各挡掉了多少」。
    """
    p = (root or ROOT) / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return []
    out, on = [], False
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.lstrip().startswith("#"):
            on = any(s in ln for s in EXCLUSION_SECTIONS)
            continue
        t = ln.strip()
        if on and t.startswith(("-", "*", "·")) and len(t) > 6:
            out.append(t.lstrip("-*· ").strip())
    return out


def bigrams(s: str) -> set:
    t = "".join(re.findall(r"[一-鿿A-Za-z]+", s))
    return {t[i:i + 2] for i in range(len(t) - 1)}


def exclusion_reason(verdict: str) -> str:
    """`硬门 FAIL (明确排除（生物医药）)` → `生物医药`。没细分返回空串。

    **两层括号。** 拿宽松的 `[^）)]+` 去配外层会在第一个 `）` 上停住，
    把 `明确排除（生物医药` 当成第一组，里层就再也配不出来 ——
    第一版栽在这儿：415 个全被判成「没说是哪一条」。只取最内层。

    ⚠️ 这和 `gate_in_verdict` 的第二个返回值**不是一回事**：那个给的是
    整段内层文本（`候选人明确排除(行业背景硬要求)`），这个再剥一层，
    给的是**哪一条排除**。实测 2026-08-31：315 条上两者一条都不相等 ——
    导出侧想复用前者会把 315 个岗全归到同一条上。
    """
    for g in re.findall(r"[（(]([^（()）]+)[)）]", str(verdict or "")):
        g = g.strip()
        if g and "明确排除" not in g:
            return g
    return ""


def exclusion_tally(entries: list, reasons: list) -> tuple:
    """每条排除各挡掉了多少个岗 → `(Counter, 没写是哪条的, 对不上任何一条的)`。

    ## 归到「他资料里的哪一行」，不是归到那句自由文本

    理由格是自由文本：同一条排除写成「英语口语」「英语流利」「英语听说」
    「英语面试」的都有。照字面分组会把一条排除拆成四份，谁也看不出它最贵。
    所以按二字片段把每条理由**归到他资料里那一行**（宁可漏报不可误报），
    实测 2026-08-31：213 条里归上 200 条。

    ## 为什么这个数值得单独算

    `04` 那一节自己写着：这是七道门里**唯一他能改的**那道 ——
    学历、年限、户口、应届身份都不是他今天能动的，而排除项是他自己
    下的结论，随时可以放宽一条。但要决定放宽哪一条，他得先知道
    **每条各挡掉了多少个岗**。实测 2026-08-31：315 个岗死在这道门上，
    最贵的一条一个人就挡掉 102 个。

    ## 两个消费方，一份判据

    审计事后报一份清单，面板报在他看得见的那一格（`topExclusions`）——
    和 `claim_without_source`、`style_problems` 同一个理由。
    """
    import collections

    keyed = [(x, bigrams(x)) for x in entries]
    tally, blank, orphan = collections.Counter(), 0, 0
    for r in reasons:
        if not (r or "").strip():
            blank += 1
            continue
        rb = bigrams(r)
        best, k = None, 0
        for txt, bag in keyed:
            n = len(rb & bag)
            if n > k:
                best, k = txt, n
        if best:
            tally[best] += 1
        else:
            orphan += 1
    return tally, blank, orphan


def style_row(cat: str, word: str, sentence: str, cap: int = 34) -> str:
    """「「深度参与」是空心动词：· 发起「365 开源计划」…」—— 这一行的写法。

    **只有一份。** 自检那条（简历正文的文风）与面板那条（基简历那一块）
    印的是同一件事，各写一份格式就会出现「同一句话两种叫法」。
    """
    return f"「{word}」是{cat}：{(sentence or '').strip()[:cap]}"


def style_problems(text: str) -> list:
    """开场白**之外**那几段对外文案的文风问题（邮件正文、网申自评…）。

    ## 和 `greeting_problems` 差在哪

    差在**判据的来源**，不在严格程度：

    - `06` 渠道 1 那五类禁区（开场铺垫、先谈钱、抢答到岗时间…）**只管开场白**
      —— 那段 ⚠️ 明说的：「渠道 2（邮件）、3（网申自评）、4（求职信）不受此限
      —— 那些场合对方已经在读你的完整材料，谈条件、讲缺口都是正常的。」
    - `03` 的风格铁律（AI 味、互联网黑话、翻译腔）**在哪个渠道都管**。

    所以这里只走 `style_hits`（`03` 那两张表），不带 `GREETING_BANS`，
    也不带 200 字上限（那是渠道 1 的硬约束）。

    ## 为什么要有

    审计 2026-08-27 起在查这几段（「对外文案：另外几个渠道的文风」），
    但那是**事后的一份清单**。而开场白的警告查在他按「复制」那一下 ——
    同一块屏幕上，开场白印着「发之前删掉：…」，紧挨着的网申自评什么都不印。

    实测 2026-08-31：面板上 10 段网申自评里 **5 段**踩了 03 的铁律
    （互联网黑话「闭环」1、翻译腔 4），10 段邮件正文 0 段。
    也就是说**一半的网申自评可以被原样复制发出去，没有任何提示**。
    """
    if not (text or "").strip():
        return []
    return _as_problems(style_hits(text))


def greeting_problems(text: str) -> list:
    """这段开场白违反了哪几条铁律，**说成给用户看的话**。没有就返回空列表。

    ## 为什么要机械查

    那几条写得极死 —— 连「实际写过的」原句都列在表里了 —— 可它是**散文**：
    执行者写的时候凭记忆遵守，写完没人回头查。实测活动用户 2026-09-02
    加检查那一刻，129 份至少犯一条、共 201 处；同日逐份改完，现算 2026-10-15：
    405 份开场白里 **0 份至少犯一条**（共 0 处）。
    而开场铺垫那条自己写着「实测一句平均吃掉 15 字，信息量为零」——
    200 字的预算里白丢 7%。

    （分母 2026-08-23 从 234 更正到 236 时，**这个 24 忘了跟着改** ——
    同一句话里一半是新数一半是旧数，比两个都旧更难发现。
    现算的守卫见 `test_the_greeting_stats_are_not_stale`。）

    ⚠️ **这条台阶记过十次，一次都不是话术变差。** 前四次是检查范围扩了，
    第五、七次是语料变多了，第六、八次是变了别的而这个数没动 ——
    第九、十次是**真的变好**：先删掉 48 句铺垫加 5 句抢答到岗时间
    （103 → 65，2026-08-30），再把「整句都是铺垫」那 16 份整句删掉
    （65 → 51，2026-08-31）。

    （**抬头说的是「记过几次」不是「涨过几次」。** 第六格是 `102 → 102`、
    第八格是 `103 → 103`：一次是判据加了一类，一次是语料长了 6 份，
    而这个数两回都一动没动。写「涨过六次」就是一句假话，而守卫原来正是
    按「涨过」在钉 —— 判据钉着错的东西时，守规矩的唯一办法就是说谎。
    同一课 `CONTRIBUTING.md`「判据可能钉着**错的东西**」记着。）

      37 → 51（2026-08-23）：把 `03-writing-style.md` 的「AI 味清单」接进
      `greeting_hits`（见 `STYLE_BANS`），多认出「互联网黑话」18 处、
      「万能形容词」1 处。
      51 → 80（2026-08-24）：「开场铺垫」从整串匹配改成按开头判（见
      `opening_padding`），那一类从 32 份变成 69 份 —— 岗位名插在
      「看到」和「这个岗」中间时，整串永远对不上。
      80 → 95（2026-08-24）：接进 `STYLE_PATTERNS` 那三条**句式**正则
      （翻译腔 11 + 5、替对方先辩解 2）。前两次加的都是词，这一次加的是
      句子的搭法 —— 词表看不见它。
      95 → 99（2026-08-25）：把那两条句式正则放宽 —— 「，**正**是我…的事」
      多一个副词就断、「正是我**这两年一直在想**的」中间插状语就断。
      用户读到一份刚生成的开场白，指出那句「根本不符合中文习惯」，
      而判据说它干净：**规则是对的，判据太字面。**
      99 → 102（2026-08-26）：语料本身长了 6 份（当轮 /job-auto 新出的话术），
      判据一个字没动。**这一格是分母变了，不是判据变严了** —— 台阶上
      前三格记的都是「判据抓得更全」，只有这一格记的是「语料变多」，
      别把它读成又发现了一批违规。
      102 → 102（2026-08-27）：加了第六类「缺口排在了匹配点前面」
      （见 `gap_before_evidence`），**而这个数一动没动**。
      加它不是因为有存量要清 —— 点了缺口的 96 份实测全部排在佐证之后，
      一份没犯 —— 是因为那条规则此前没有任何一处在执行：五类禁区里四类有
      词表盯着，位置这条只写在散文里。**判据变了、数没变，这一格照样要记**：
      不记的话，下次谁看到「六类」和「102」对不上，会以为漏了一批。
      102 → 103（2026-08-27）：语料又长了 10 份（当轮 /job-auto 新出的话术），
      其中 1 份踩线。**和上一格同一回事：分母变了，判据没动。**
      103 → 103（2026-08-29）：语料又长了 6 份（当轮 /job-auto 新出的话术），
      **一份没踩线**，所以这个数一动没动。
      103 → 65（2026-08-30）：**头一次是话术真的变好了。**
      `tools/trim_opening.py` 把 48 句开场铺垫删了（省出 720 字，平均一份 15 字，
      而一份的预算只有 200 字）—— 这一类从 71 份降到 23 份；
      同日第二遍又删了 5 句「抢答到岗时间」，那一类 9 → 0。
      **「先谈钱」那 3 份没删** —— 「30-50k 按几薪算」是该问的问题，
      只是不该问在打招呼里；实测那几份里只有一半的「投前必问」已经收了它，
      自动删会真的丢掉一个他想问的事。**删掉零信息的，报出走错地方的。**
      当时剩下的 23 份删不动：铺垫后面接的是逗号而不是句号，删了会剩半句，
      那种要人重写 —— **而次日发现其中 16 份是可以机械删的，见下一格。****判据是拿这个检查器自己当验收**：改完的必须是改前的
      真子集，少了铺垫且没多出任何一条；达不到就整条跳过（实测拦下 1 份）。
      值得记一笔的是**这 6 份是怎么变干净的**：初稿有 4 份踩线（复述 JD 1、
      谈钱 1、框架词 1、翻译腔 1），是跑测试时被拦下来才改的 —— 写的时候
      同样以为自己遵守了。**这正是这套检查存在的理由**：台阶前七格记的是
      「判据抓得更全」，这一格记的是判据第一次在**新料入库前**就拦住了它。
      （其中「谈钱」那条最值得说：初稿问的是「30-50k 是几薪」，理由写着
      「问口径不算问薪资」—— 而 06 渠道 1 那条是「一个字都不提薪资」，
      没有留这个缺口。**自己给规则开的例外，正是规则要防的东西。**）
      65 → 51（2026-08-31）：**「整句都是铺垫」的那 16 份，整句删掉。**
      前一天记着「剩下的 23 份删不动」，判据是「铺垫后面不是句号或冒号」。
      次日把那 23 份摊开看，才发现 22 份里匹配到的那一截**根本不是独立的
      铺垫句，而是真句子的开头**：

          我想应聘 + 智能体平台资深产品经理。   ← 整句都是铺垫，该删整句
          看到岗   + 位写「不要求编程基础…」    ← 有内容，一个字都不该删

      只删匹配那一截确实会剩半句（那条判据是对的），而**整句删掉**之后
      剩下的正是该占第一行的东西 —— 那 16 份删完从「Claude、Cursor、Dify
      这些平台我每天…」「JD 那句「技术是门票…」」起头，省出 248 字。
      另外 6 份第一句里带着正文，按 `_PAD_SENTENCE_MAX` 拦下，一个字没动。
      **判据窄不等于判据对**：它挡住了会出错的那一半，也挡住了本来能修的那一半。

      51 → 59（2026-09-01）：**这一格是语料变差，不是判据变松。** 判据一个字没改；
      当天两轮 `/job-auto` 新出了 28 份材料，新写的那批里就有 14 处踩线
      （「JD 里说…」3 处、框架词「那一层」「能力边界」3 处、拿仓库数量自证 8 处）。
      同日逐条改完之后落在 59 —— 也就是说，**存量的 45 份一直在那儿，
      涨的那一截全是当天新产的**。这正是这道台阶要防的：不逐条报，
      新写的和存量的会混成一个数，看起来像「这批话术在退化」。

      59 → 129（2026-09-02）：**判据效应，语料一个字没动**（当天没跑 /job-auto）。
      本人看着一份产出直接给了改法，两条裁定各接了一条检查：
      「复述职位描述」63、「拿年头自证」38；顺带把 06 铁律 0 里 2026-08-13 就定下、
      却从来没有任何一处在执行的「拿产量当卖点」也接上，36。
      **三条加起来 137 处，占新总数 201 的七成。**

      值得记的是这三条**都不是新规则** —— 06 里全都写着，最早的一条写了 20 天。
      漏过去的方式各不相同：「复述 JD」那条封的是三个措辞（`JD 里`/`说`/`写`），
      写手换个引语动词（`看到您写「…」`）就绕过去了；「拿年头自证」和
      `STYLE_PATTERNS` 那条翻译腔是同一族的两半，那条要求 `是我` 前面有逗号，
      而这一类没有；「拿产量当卖点」压根没人给它写过检查。
      **散文规则的漏法是可以枚举的，而枚举不出来的那部分就是这 137 处。**

      129 → 0（2026-09-02）：**同一天全改完了。** 判据没动，129 份逐份重写，
      靠的是把这个检查器当验收 —— 改完必须 `greeting_hits` 为空、≤200 字、
      以「您好，」开头，达不到就整条跳过不写盘（照 `trim_opening.py` 的老规矩）。
      实测拦下 1 份：新写的那句里带了「对齐」，是 `STYLE_BANS` 的互联网黑话。
      **写的时候同样以为自己遵守了** —— 和上面第八格记的是同一件事，
      只是这回拦的是我自己刚写的那一句。

      两处顺带修的，都不在这几条判据里、只有逐份看才发现：
      **7 份点了 `candidate.md` 里没有的工具**（Cursor），
      **3 份把他写成了在企业内部推 AI 的人** —— 而资料里那条 ⚠️ 身份口径
      明写着「不是」，2026-08-12 就为同一件事改过一批。

      0 → 24 → 0（2026-09-02，同日晚些）：**上一格那个 0 是假的。**
      当天新加的两条正则都写窄了，24 份从底下漏过去：
      「拿年头自证」的尾巴只认 `在做|在干|这么做|做的`，于是
      **「这两件事我这三年一直在同时做」整句漏掉** —— 只因为末尾是光杆的
      「做」；「拿产量当卖点」在「一年」和数字之间只允许空白，于是
      **「一年出了 40 个公开仓库」**漏掉 —— 只因为中间插了个「出了」。

      **是怎么发现的：在浏览器里点了一下「复制开场白」，看剪贴板里是什么。**
      复制回来的第一句就是「这两件事我这三年一直在同时做」—— 而检查器
      当时说 0 命中。**没有那一下，这 24 份会一直挂着，而记录写着「全清了」。**

      三条教训，前两条这个仓库都记过：
      1. **别把动词写死成固定搭配**（同 `_OPENING_PADDING` 按整串匹配漏 36 处、
         `fetch_details.needs_recheck` 的「读过 vs 读了」漏 613 条）——
         中文的状语能插在任何地方。
      2. **判据窄和判据对是两回事**（同上一格 `trim_opening` 那句
         「它挡住了会出错的那一半，也挡住了本来能修的那一半」）。
      3. **新加的检查器自己要被验一次**，而验它的办法不是再读一遍正则，
         是**拿真产出走一遍用户真实的那条路**。检查器说 0 的时候最危险：
         它和「真的干净」长得一模一样。


    前四次都验过是判据效应，不是语料变差：第四次那天有 6 份开场白同时被重写，
    所以**特意在同一份新语料上跑了一遍旧正则** —— 旧 95、新 99，**+4 全部来自放宽**。
    （前三次的语料一个字没改，本来就不用分离。）

    **判据变了就要说一声，而且要说清是不是判据的功劳** —— 否则下一个读到这里的人
    会以为这批话术在两天里烂了一截。

    **查在这里，是因为这是他复制那段话的地方。** 生成端已经被明确告知过了、
    还是漏一成多；那就在他按下「复制开场白」之前再说一次。全库那一遍由
    `audit_pipeline.check_greeting_keeps_the_five_rules` 做，两处共用
    `greeting_hits`，所以不会再出现「面板说没问题、审计说有」。
    """
    if not (text or "").strip():
        return []
    hits = greeting_hits(text)
    out = _as_problems(hits)
    # **截断了要说截了多少。** 原来直接 `[:3]` 收尾：用户把列出来的三条删完，
    # 以为这段干净了，而第四条还在里面。实测活动用户 2026-08-23：37 份踩线的
    # 开场白里 1 份有 4 条（`是几薪` / `随时到岗` / `目前离职` / `期望 45-60k`
    # —— 五类里踩了四类），面板只印前三条。
    # 一份只有 1-2 条是常态，所以上限本身留着；但**沉默的截断**在这个仓库里
    # 是有名字的一类（审计每条都写「另有 N 份没算」），不能只有这里例外。
    n = len(re.sub(r"\s", "", text))
    if n > GREETING_MAX:
        out.append(f"{n} 字，超了 {GREETING_MAX} 字的上限")
    return out


#: 招聘者职务里，指向 **HR 那一侧**的词。判在前面 —— 「HR经理」两边都命中，
#: 而它当然是 HR。
COUNTERPART_HR = ("HR", "人事", "人力", "招聘", "绩效", "薪酬", "行政")

#: 指向**用人方本人**的词（他自己就是要人的那个部门，或干脆是老板）。
COUNTERPART_BOSS = ("总监", "总裁", "总经理", "经理", "主管", "负责人", "合伙人",
                    "创始人", "老板", "法人", "CEO", "CTO", "COO", "VP",
                    "架构师", "工程师", "组长", "LEADER")


def counterpart_of(recruiter_title: str, is_headhunter=None) -> str:
    """跟你说话的是谁：`猎头` / `HR` / `用人方` / 空串（认不出）。

    ## 为什么两档不够

    `06-outreach-templates.md`「渠道判定」只分猎头和 HR 直招，判据是
    `isHeadhunter` 一个字段。可猎聘搜索接口**每张卡片都带着招聘者职务**
    （`recruiterTitle`），实测样本 42 张：猎头顾问 16、HR 那一侧 16、
    **用人方本人 4**（研发总监、运营经理、商务主管、法人）、认不出 6。
    直招里认得出职务的 20 张，**五分之一对面根本不是 HR**。

    这在国内不是细微差别：HR 筛的是硬条件与稳定性，而用人方老大关心的是
    「你能不能干活」，**他当场就能拍板**。对着他讲职业规划与稳定性，
    是把唯一一次直达决策人的机会说成了 HR 面。

    ## 两边都要命中才下结论

    认不出就返回空串，不猜。样本里真有一张职务写着 `sfsf` —— 只判「不含 HR
    词就算用人方」的话，它会被说成研发总监同一档，而下一步的话术全按这个走。

    ## 这个字段此前被整个否掉了

    `cdp-portals.md` 那张表里写着它「既当不了外包硬门要的招聘主体名称，
    也当不了跟进消息里的称呼」—— **两句都对**（它是角色不是人，同一个
    「猎头顾问」挂在十几个不同招聘者身上）。但「当不了人名」不等于没用：
    它回答的是另一个问题。一个字段按一种用途否掉之后就没人再看它，
    是这个仓库反复踩的形状。
    """
    if is_headhunter:
        return "猎头"
    s = (recruiter_title or "").strip().upper()
    if not s:
        return ""
    # **头衔自己写着「猎头」时，它盖过下面两张词表。**
    #
    # 传进来的 `is_headhunter` 是职位库里那个裸字段，实测活动用户 2026-08-30
    # 有 4 个岗它记着 `False` 而头衔明写「某某 · 猎头顾问」。这 4 个里
    # **有一个被判成了 HR** —— 头衔里的公司名叫「某某人力资源」，
    # 「人力」撞上了 `COUNTERPART_HR`。于是 `/job-apply` 第 1.5 步会照着
    # 给一个猎头顾问写 HR 直招版的话术（不主动谈薪资与到岗时间），
    # 而对猎头那两样恰恰要直接答（`06` 渠道判定）。
    #
    # 词表是按**角色名**写的，可这一栏常常是「公司名 · 角色名」——
    # 公司名里的行业词会喧宾夺主。「猎头」二字出现在这一栏里只有一种解释。
    # 同样只认这一个方向：反过来「头衔像用人方 ⇒ 不是猎头」不成立
    # （见 `via_headhunter` 里那段实测 2026-08-30：19 个里 15 个是企业自己的 HR）。
    if "猎头" in s:
        return "猎头"
    if any(h in s for h in COUNTERPART_HR):
        return "HR"
    if any(b in s for b in COUNTERPART_BOSS):
        return "用人方"
    return ""


#: 哪些平台的投递入口**本身就是聊天框**。`job-gmail-sync.md` 那张
#: 「回音一般走哪儿」的表把它写死了：BOSS 直聘「站内聊天框，全程不发邮件」。
#: 那张表是正本，这里是它的机器可读副本，`test_the_send_hint_knows_the_channel`
#: 逐行比对两者，防止分叉。
CHAT_PORTALS = ("BOSS", "BOSS 直聘", "BOSS直聘")


#: 招聘方名头里带这些字的，是中介不是用人方（猎聘的 `recruiter` 长这样：
#: 「<姓>先生 · 猎头顾问 · 某某人才科技有限公司」——真名不进仓库，
#: `test_no_maintainer_data_in_repo` 盯着这一条，写举例时用占位）。
_AGENCY_WORDS = ("猎头", "人力资源", "人才", "咨询")


def via_headhunter(entry: dict) -> bool | None:
    """这个岗是**猎头代招**还是用人方直招。

    ## 为什么这件事在国内要单独说

    简历投给猎头 ≠ 投给用人方：它先进猎头的库，由他决定推不推、什么时候推；
    岗位可能早就关了、也可能是猎头在攒简历。同样一份简历，直招那边三天有回音，
    猎头那边可能永远没有——**这是「投了没回音」最常见的一种，而且怪不到简历头上**。

    ## 这个函数原来不存在，而它要答的问题被答反了

    抓取器一直在存 `isHeadhunter`（猎聘 2232 个岗里 **1358 个是 True**，61%），
    而导出那一行读的是 `via_headhunter` —— **驼峰对下划线，字段名对不上**。
    于是 `viaHeadhunter` 全库 0，而 `JobReadout.tsx` 那一行不是留空，
    是照着 `false` 印出**「企业 HR 直招」**：1358 个猎头岗，每一个都在面板上
    被写成直招。缺数据只是少一条信息，**印反了是给错误的信息**。

    判据与 `pref_tags` 的 `agency` 标记共用这一份：两处各写一遍，
    「面板说直招、而它被 agency 规则滤掉了」这种自相矛盾迟早出现。
    """
    if any(w in (entry.get("recruiter") or "") for w in _AGENCY_WORDS):
        return True
    # **头衔那一栏也要看，而且只认「猎头」二字。**
    #
    # 上面那行查的是 `recruiter`（猎聘长这样：「X先生 · 猎头顾问 · 某某人才
    # 科技有限公司」，公司名里就带着中介词）。可 BOSS 那边 `recruiter` 是空的，
    # 头衔单独落在 `recruiterTitle` 里 —— 实测活动用户 2026-08-30，
    # **4 个岗**头衔明写「某某企业管理咨询 · 猎头顾问」而这个函数照样返回
    # `False`，面板、`doctor`、`followups`、话术抬头四处一起印「企业直招」。
    #
    # ⚠️ **不许把 `_AGENCY_WORDS` 整张表套到头衔上。** 实测 2026-08-30 那样会翻 19 个，
    # 其中 15 个是「人力资源总监」「人力资源伙伴(HRBP)」「人力资源专员」
    # 「人才招聘经理」—— **企业自己的 HR**。词表能用在 `recruiter` 上是因为
    # 那串里含公司名；头衔是纯角色名，「人力资源」正是在职 HR 的写法。
    # 判据不对称：头衔含「猎头」⇒ 一定是代招，反过来不成立
    # （`audit_pipeline.check_recruiter_title_contradicts_the_channel` 的
    # 说明里记着第一版双向检测当场误报 6 条的实测）。
    if "猎头" in (entry.get("recruiterTitle") or ""):
        return True
    # **显式的 `null` 也是「没判过」。** 这里原来写 `"isHeadhunter" in entry`，
    # 于是抓取器写下 `"isHeadhunter": null` 时 `bool(None)` = `False`，
    # 「没判过」当场塌成「确认是直招」—— 正是这个函数下面那段注释警告的那件事，
    # 只是从「字段缺失」换成了「字段在、值是空」。真数据里现在 0 个
    # （2026-08-30 实测：显式 null 0 个、字段整个缺 32 个），
    # 但判据得先对，不能等哪个渠道开始写 null 才发现。
    if entry.get("isHeadhunter") is not None:
        return bool(entry["isHeadhunter"])
    # 猎聘的 `/a/` 是猎头岗的路径，字段没抓到时它一样确凿。
    # 这条原来只长在 `outreach_header.side_of` 里 —— 一个判据两份实现，
    # 而那一份还漏了上面两条。搬过来之后 `side_of` 只剩一句转调。
    if "/a/" in (entry.get("url") or ""):
        return True
    # **没判过 ≠ 判过是「不是」。** 抓取器没给这个字段时（实测 2026-08-30 2638 个岗里 66 个，
    # 集中在浏览器抓的 BOSS / 智联 / 前程），返回 `False` 会让面板照着印
    # 「企业 HR 直招」——那是**给错误的信息**，不是少一条信息，正是本函数上面
    # 那段注释记的「1358 个猎头岗被印成直招」的同一类事故。
    #
    # 而这枚标记现在是有分量的：短名单上「（企业直招）」是「内推够得着」的信号
    # （见 `Shortlist.tsx` 的「标少数不标多数」），零回音诊断也拿它分猎头/直招的
    # 分母。把没判过的岗算进直招，等于让他去一个可能是猎头挂的岗上找人内推。
    return None


def has_chat_box(portal: str, via_headhunter=None):
    """这个岗**发出去的时候有没有聊天框**。拿不准返回 None —— 不猜。

    此前面板对每一个岗都印同一句「粘到{平台}的聊天框直接发」，而
    `followups.py` 早就分了流：「BOSS 是聊天框，随时能追一句；猎聘/智联走
    站内信，多半没有对话入口」。**催的时候知道形态，发的时候不知道。**

    实测活动用户 2026-10-15，405 份开场白按 (平台, 猎头/直招) 分布：

        猎聘 · 猎头代招   230   有对话入口（找的是顾问）
        猎聘 · 企业直招    86   多半只有站内信 / 网申表单
        猎聘 · 没判过       1   不猜
        BOSS · 企业直招    37   聊天框
        BOSS · 猎头代招    12   聊天框
        BOSS · 没判过      24   不猜
        智联 · 企业直招     6   站内信为主
        智联 · 没判过       3   不猜
        前程 · 企业直招     4   站内信为主
        前程 · 没判过       1   不猜

    也就是 **97 个岗被告知「粘到聊天框」，而那里多半没有聊天框**。

    判据两条，顺序不能换：

    1. **猎头代招一律算有** —— 猎头本人是可联系的（`followups.py` 那句
       「顾问有推荐费驱动，多半会回」建立在同一个前提上）。平台不影响这一条。
    2. 其余按平台：`CHAT_PORTALS` 里的有，其余的没有。

    `via_headhunter` 是三态（`export_web_data.via_headhunter`）：没判过时
    **不落到第 2 条**，返回 None —— 对一个可能是猎头挂的岗说「这里没有聊天框」，
    和当初把 1358 个猎头岗印成直招是同一类事故。
    """
    if via_headhunter is True:
        return True
    p = (portal or "").strip()
    if any(c in p for c in CHAT_PORTALS):
        return True
    if via_headhunter is None or not p:
        return None
    return False


def send_hint(portal: str, via_headhunter=None) -> str:
    """「这段话该怎么发出去」——一句给用户看的话。

    发出去是整条流水线里唯一要人做的那一步（`AGENTS.md`「只有一处要人」），
    这句话就是那一步的说明书。说错了，他会去找一个不存在的聊天框。
    """
    chat = has_chat_box(portal, via_headhunter)
    if via_headhunter is True:
        return "粘到和猎头顾问的对话框，直接发"
    if chat is True:
        if not portal:
            return "粘到聊天框，直接发"
        # **只在拉丁那一侧补空格。** 「粘到BOSS 直聘的」挤在一起，
        # 而无脑两边都补会得到「粘到 BOSS 直聘 的」——「的」前面不该有空格，
        # 它是中文助词不是拉丁词。平台名以字母开头才补前面那个。
        lead = " " if portal[:1].isascii() and portal[:1].isalnum() else ""
        return f"粘到{lead}{portal}的聊天框，直接发"
    if chat is False:
        return f"{portal or '这个平台'}的企业直招多半没有聊天框——投完简历，把这段用站内信发过去"
    return "先看这个岗有没有沟通入口：有就贴进去，没有就随投递用站内信发"


#: `sendable_state` 被调用的次数。**用它认出「还能动」的检查** ——
#: 一条检查问了「这几份还发得出去吗」，就意味着它分得清哪些还来得及补；
#: 反过来，没问过的那些报的是存量或结构问题，收尾时印出来只会淹掉前者。
#:
#: 为什么不另立一张「哪几条算 actionable」的名单：**那就是第二个住址**，
#: 会和 `CHECKS` 分叉（拼错一个名字就静默少跑一条）。这里的判据是
#: **行为**不是名字 —— 新加的检查只要调了 `sendable_state`，自动就进这一档。
_SENDABLE_CALLS = [0]

#: 「我报的是**刚跑完那一轮**的事」——检查自己声明一次。
#:
#: `--actionable` 原来只认一个信号：调没调过 `sendable_state`（分得清哪些材料
#: 还发得出去）。那是个**代理判据**，而有一整类发现它表达不了：
#: **这一轮本身漏了活**。
#:
#: 实测 2026-08-31：`check_the_blocked_lane_handed_over`（猎聘 CLI 撞限流那天，
#: 闸门放行的浏览器那条 0 次查询 —— 这家占语料的大头）报的正是这一类，
#: 而它**进不了收尾那一档** —— 于是同一个错犯了两次，两次都靠人当场发现。
#:
#: 判据仍然是**行为**，不是名单：检查在运行时喊一声，不去维护第二张表
#: （`run()` 的说明里那句「另立一张名单就是第二个住址，会和 `CHECKS` 分叉」）。
_ROUND_SCOPED_CALLS = [0]


def note_round_scoped() -> None:
    """检查用它声明：我这一条说的是刚跑完那一轮的事，收尾该看见。

    **只在真报出东西那一支里喊。** 没东西可报时喊了，等于把一条空检查
    塞进收尾那一档（`run()` 按调用次数判，不看返回值）。
    """
    _ROUND_SCOPED_CALLS[0] += 1


def sendable_state(user: str, seen: dict):
    """一份材料现在**还发得出去吗**。返回 `url -> 状态词` 的那个函数。

    状态只有五种：`已经投出去了` / `岗位已下线` / `你标了不投` /
    `对不上职位库` / `还能发`。

    ## 为什么要单独有它

    印一个「N 份有问题」的总数，读的人做不了任何事 —— 实测四分之三根本动不了
    （已经投出去的改也来不及、标了不投的不会再发）。**只有「还能发」那一格
    能动，而且要点名。** 这一课记在 `check_greeting_keeps_the_five_rules`
    的 docstring 里，那里有完整的账。

    这段判定原来整个内联在那一条检查里。第二条检查要用同一件事时，
    **抄一份就等着它们分叉** —— 这个仓库反复栽在这上面
    （词表分叉过一次：同一类一边数出 32 份、一边 17 份）。

    ⚠️ **对不上职位库的不算「还能发」。** 不知道就说不知道，别乐观地算进去。
    """
    _SENDABLE_CALLS[0] += 1
    by_url = {norm_url(e.get("url") or ""): e
              for e in seen.values() if isinstance(e, dict) and e.get("url")}
    by_url_raw = {e.get("url"): e for e in seen.values()
                  if isinstance(e, dict) and e.get("url")}
    applied = set()
    tr = ROOT / "users" / user / "job_search_tracker.csv"
    # 台账可能是 Excel 存出来的（BOM/GBK）；读法只留 `read_tracker_rows` 一份。
    for r in read_tracker_rows(tr):
        u = (r.get("source") or "").strip()
        if u:
            applied.add(u)
    applied = {u for u in applied if u in by_url_raw}

    def state(url: str) -> str:
        e = by_url.get(norm_url(url or "")) if url else None
        if e is None:
            return "对不上职位库"
        if e.get("url") in applied:
            return "已经投出去了"
        st = str(e.get("status") or "")
        if st == "expired":
            return "岗位已下线"
        if st == "skipped":
            return "你标了不投"
        return "还能发"

    return state


#: 「一个都动不了」那句话的开头。**收尾按它把整行滤掉** ——
#: 判据要收到**行**这一级：一条检查可能报两行，一行有活、一行没有。
#: 提成常量而不是在别处再写一遍那句中文：那就是第二个住址，
#: 改一个字两边就对不上了。
NO_LIVE = "这些都已经投出去、标了不投或下线了，"

#: `live_tail` 点过名的岗（规范化链接）。**收尾要报去重后的总数** ——
#: 六条检查各报一个数，读的人加不出总数，也不知道是不是同一批岗。
#: 实测 2026-08-30：提及合计 113 次，**去重后 101 个岗**（12 个被两条同时点到）。
#:
#: 收集放在这里而不是让调用方各自返回：那六条的返回值形状各不相同，
#: 让每条都多带一个集合出来，等于把同一件事写六遍。
LIVE_SEEN: set = set()

#: 其中**要改已有内容**的那些（`live_tail(verb="改")`）：
#: 归一化链接 -> 原样链接。
#:
#: **键归一是为了数对，值留原样是为了敲得出来。** 这里原来是个 set，
#: 只喂给 `len()`；而收尾那句让用户「照下面那几条各自的链接一个一个跑」
#: —— 下面每条检查只印**一个**链接（`live_tail` 印的是 `live[0]`）。
#: 实测 2026-08-31：10 个岗要改，屏幕上只有 2 个链接，另外 8 个
#: **一处都没印过**。那句引导对其中八成的岗根本没法执行。
#:
#: 收尾那句「一次补完：`/job-apply 全部`」只对**补缺的那一节**成立 ——
#: 它按设计不重跑深评。而「依据说错了数」「开场白踩了线」这类要的是
#: **重写已有内容**，`全部` 一个都改不了。两类混在同一个总数里，
#: 那句「一次补完」就是在许一个做不到的诺（2026-08-30 实测：110 个里
#: 有一批属于后者）。这个集合让那句话自己把两类分开，不靠手写名单。
LIVE_REWRITE: dict = {}


def note_live(urls, rewrite: bool = False) -> None:
    """把这几个「还能动」的岗记进收尾那两个集合。

    `live_tail` 自己会调它。**手写尾巴的检查也必须调** ——
    `check_greeting_keeps_the_five_rules` 要报一份完整的状态分布
    （已投 21 / 不投 12 / 下线 3），那半被 `live_tail` 压掉了，所以它
    自己拼那句话；而拼完就绕过了这里的记账。

    后果有两层，都在收尾那一段：

    1. 「下面这几条去重后是 N 个岗」**少算它们** —— 那个数自称是总数。
    2. 「其中 M 个要改已有内容」也点不到它们，于是它们被并进
       「一次补完：`/job-apply 全部`」—— 而那条命令明写着
       **不重写已有的开场白**，对这一批一份都动不了。

    实测 2026-08-31：那条检查报「还发得出去的 15 份」，15 份全在两个集合外。
    """
    for u in urls:
        if not u:
            continue
        LIVE_SEEN.add(norm_url(u))
        if rewrite:
            LIVE_REWRITE[norm_url(u)] = u


def live_tail(user: str, seen: dict, items, cmd: str = "/job-apply",
              verb: str = "补", unit: str = "份") -> tuple:
    """把「其中还没投的 N 个（例：…）。补它：… <链接>」那句话拼出来。

    `items` 是 `(链接, 目录名或标题)` 的序列。返回 `(还能动的那几条, 那句话)`。

    ## 为什么要有它

    这句话的形状是固定的，而**内容三条都不一样**（补哪一节、敲哪条命令），
    于是 2026-08-30 一天之内被手写了三遍（「投前必问」「深评缺小节」「写回」）。
    第四条来的时候它就该分叉了 —— 这个仓库反复栽在同一件事上。

    它同时把两条规矩固定下来，让新加的检查不必再各自想一遍：

    1. **只点还能动的。** 印一个总数读的人做不了任何事：实测四分之三的文件
       已经投出去或标了不投，而给出的命令若指向其中之一，他敲一次、发现没意义，
       下次整条就不看了。完整的账在 `sendable_state` 的 docstring 里。
    2. **一个都动不了时直说**，不给一条白敲的命令 —— 那比不给更坏。

    公司名去重：同一家挂两个岗时 `A、A、B` 读起来像凑数 ——
    实测印出过同一家猎头公司连着占掉三个例子里的两个。
    """
    where = sendable_state(user, seen)
    state = [(u, k, where(u)) for u, k in items]
    live = [(u, k) for u, k, w in state if w == "还能发"]
    note_live([u for u, _k in live], rewrite=(verb == "改"))
    # **「对不上职位库」既不是「还能发」，也不是「已经出局」。**
    #
    # 上一版把它并进后者：`live` 里没有它，于是一条全是这种的检查会印出
    # 「这些都已经投出去、标了不投或下线了」—— 而实情是**判不了**。
    # 实测 2026-08-30：「深评缺小节」那条喂进来的 128 个里有 **29 个**是这种，
    # 「投前必问」那条 103 个里有 14 个。数被压小了，而且压得看不见。
    #
    # `sendable_state` 的说明写着「不知道就说不知道，别乐观地算进去」——
    # 那是说别把它算成「还能发」，不是说可以算成「已经出局」。
    # 两个方向都要留住那个「不知道」。
    unknown = sum(1 for _u, _k, w in state if w == "对不上职位库")
    note = f"（另有 {unknown} 个在职位库里对不上，判不了还能不能发）" if unknown else ""
    if not live:
        # 全都判不了时，不许说「都出局了」—— 那是假话，而且会把唯一的下一步收掉。
        if unknown:
            return [], (f"{unknown} 个在职位库里对不上，判不了还能不能发；"
                        f"真要{verb}就一次一个跑 {cmd} 加那个岗的链接。")
        return [], NO_LIVE + f"{verb}它没有意义。"
    names = []
    for _u, k in live:
        nm = str(k).split("_")[0][:16]
        if nm not in names:
            names.append(nm)
        if len(names) >= 3:
            break
    nl = chr(10)
    return live, (f"其中还没投、现在{verb}还来得及的 {len(live)} {unit}"
                  f"（例：{'、'.join(names)}）{note}。{verb}它：一次一个跑{nl}"
                  f"    {cmd} {live[0][0]}{nl}  ")


def archived(user: str, root=None) -> dict:
    """存档里那些岗（`job_scraper/archive.json` 的 `seen`）。读不出就给空的。

    ## 为什么这一层要共用

    归档不是删除：存档与热库同 schema，出局超过两周的岗被 `archive.py` 挪进去。
    于是**任何「这个岗见过没有 / 这个词带来过什么」的问题都要问两个文件**，
    而每个问的人都要自己写一遍「读文件、解析、`seen_of`、兜住坏文件」。

    实测这段被抄了两份（`query_yield` 算词表产出、`audit_pipeline` 查两边重复），
    而**第三个该问的地方压根没问**：抓取入库时的查重只对了热库，
    28 个已归档的岗被当新岗插回，两份随后各自演化（一个记 55「可以考虑」、
    一个记「硬门 FAIL」）。那次的原话是「规则在，没人验」。

    2026-08-30 复查：热库 1839 个键，存档另有 1074 个 ——
    **漏掉这一步时会被重新抓一遍的就是那 1074 个。**

    坏文件不抛异常，只当没有存档：宁可少认几个键（多抓一个岗），
    也不要在这里把整轮抓取停掉。

    ⚠️ **别拿它的键去查重**（原来这里教的正是 `set(seen) | set(archived(user))`，
    2026-10-12 判定作废）：两边存过三代键，重键之前存档 3163 条里 3040 条挂着旧形态，
    而现在入库算的是 `stable_id(url, title)` —— 按键比等于对 96% 的存档视而不见。
    查重用 `seen_index(user)`，判据是「链接 + 职位名」，从**条目字段**算。
    """
    import json as _json
    f = store_dir(user, root) / "archive.json"
    try:
        return seen_of(_json.loads(f.read_text(encoding="utf-8"))) or {}
    except (OSError, ValueError):
        return {}


def store_dir(user: str, root=None) -> Path:
    """某个用户的数据目录 `users/<用户>/job_scraper/`。

    这一句原来在几处各拼一遍；这里收的是 `_cli.archived` 与 `seen_index` 两处
    （它们同属「问这个岗见过没有」，必须指向同一个地方）。
    `archive.paths` 与 `serve.seen_path` 暂时没并进来：测试按**各自模块的 ROOT**
    打桩（`archive.ROOT`、`serve.ROOT`），改成走这里会让桩落回真实仓库——
    那是 `user_state_path` 的 docstring 记过的那类事故。
    拼错路径不会报错，只会**读到一个不存在的文件然后当它是空的**——
    对存档来说就是「查重当成没归档过」。
    """
    return (root or ROOT) / "users" / user / "job_scraper"


def stable_id(url: str, title: str) -> str:
    """按 URL + 职位名派生的**稳定** id。**这条算式的正本。**

    原来住在 `export_web_data`，2026-10-12 搬到这里：`_cli` 要给 `seen_index`
    和 `rekey` 用，而 `_cli` 是底层，不能反过来 import 导出器（会把
    `build_dashboard`/`followups` 整串拖进每条命令的启动路径）。
    `export_web_data.stable_id` 留了一份别名，与 `DIM_SAID` 同一种处理。

    原来用枚举序号（`f"j{i}"`）——`seen_jobs` 增删一条，后面所有 id 全部错位。
    浏览器里按 id 存的任何状态（「已发」勾选、「不投」标记）就会张冠李戴：
    你排除了 A 岗，下次重新生成后被隐藏的是 B 岗。

    带上职位名是因为 51job 实测同一 URL 下挂着两个不同职位
    （见 `workflows/reference/cdp-portals.md`），只用 URL 会让两个岗共用一个 id。
    """
    h = hashlib.sha1(f"{url}#{title}".encode("utf-8")).hexdigest()
    return "j" + h[:10]


def job_key(entry) -> str | None:
    """一条岗**应当**用的库键；没有链接的给 `None`。

    兜底键 `<渠道>_<公司>_<职位名>` 里多数其实带着链接（2026-10-12 重键之前数出来的：
    热库 48 条兜底键全带、存档 228 条里 221 条带），那些照常换成 `stable_id`；
    真正一条链接都没有的（存档那 7 条）维持原键——别拿公司名去编一个：
    `is_anonymous_employer` 记着脱敏串当键的后果。
    """
    if not isinstance(entry, dict):
        return None
    url = str(entry.get("url") or "")
    if not url:
        return None
    return stable_id(url, str(entry.get("title") or ""))


def job_token(url, title) -> str:
    """「同一个岗」的身份证据：归一化链接 + 职位名。

    形状故意做成历史上库键的样子（`<url>#<职位名>`），差别只在**链接那一截
    过了 `norm_url`** —— 那正是旧键漏掉的一步（协议、`?refcode=` 埋点、
    51job 路径前缀、`m.` 子域，`norm_url` 的 docstring 记了四次）。
    """
    return f"{norm_url(str(url or ''))}#{str(title or '').strip()}"


def seen_index(user: str, root=None) -> dict:
    """热库 ∪ 存档，按 `job_token` 索引：`{令牌: 键}`。**入库查重要用这个。**

    ## 为什么不是并一下两边的键

    `job-scrape.md` Step 4 原来给的是 `set(seen) | set(_cli.archived(user))`，
    两个名字都对着，结果两边存着**三代键**（裸 URL → `url#职位名` → `stable_id`），
    而新入库的岗一律算 `stable_id`。模拟过一遍（2026-10-12，活动用户）：
    把存档 3156 条各当「下一轮又搜到了」，那两行只命中 **116 条（3.7%）**，
    剩下 3040 条会被当新岗插回热库 —— 两份随后各自演化。

    同一天用 `tools/rekey.py` 把两边的键收成了一代，**但那不等于比键是对的路子**：
    候选的链接换个写法（协议、`?refcode=` 埋点、`m.` 子域），`stable_id` 跟着变，
    而这里的令牌过 `norm_url`，那些变体一律认得。

    **键是给机器记路的，不是给岗定身份的。** 身份在条目的 `url` + `title` 里，
    所以这里从字段算令牌，两边都算，与 `audit_pipeline._same_job` 同一判据。

    同链接挂两个职位**不算见过**（`tests/test_one_url_can_hold_several_jobs.py`），
    所以令牌带着职位名。没有链接的条目在这里索引不到——
    那种岗本来就认不出「搜到的这条是不是它」，宁可多抓一次。
    """
    import json as _json
    idx = {}
    base = store_dir(user, root)
    for f in (base / "seen_jobs.json", base / "archive.json"):
        try:
            rows = seen_of(_json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue                     # 读不到就少认几个，别把整轮抓取停掉
        for k, e in rows.items():
            if not isinstance(e, dict) or not e.get("url"):
                continue
            idx.setdefault(job_token(e.get("url"), e.get("title")), k)
    return idx


#: 四家平台：内部短名 → **给用户看的名字**。这条规则的正本。
#:
#: 两种拼法此前同时出现在面板上：岗位那一行的渠道章写「智联招聘」「BOSS 直聘」
#: （`export_web_data.PORTAL_NAMES`），而同一页「招聘网站」那一块写「智联」「BOSS」
#: （`PORTAL_FACTS` 的键，那是落盘的偏好键，不能改）。实测 2026-08-31 的快照里
#: 长名 272 处、短名 21 处，指的是同四家。
#:
#: **短名留作键，长名留给屏幕** —— 分工写在这里，别再各处各拼一遍。
PORTAL_DISPLAY = {"猎聘": "猎聘", "BOSS": "BOSS 直聘",
                  "智联": "智联招聘", "前程无忧": "前程无忧"}

#: 链接域名 → 平台短名。**这条规则的正本。**
#:
#: 原来有两份：`tracker._HOSTS`（判这一笔投递从哪投的）与 `outreach_header.PORTALS`
#: （抬头那句「…的聊天框」）。两份**已经分叉**：前者写「智联招聘」，后者写「智联」，
#: 而它们答的是同一个问题。前者还多一条永远匹配不到的 `jobs.51job.com`（`51job.com`
#: 是它的子串，先命中）。
PORTAL_HOSTS = (("liepin.com", "猎聘"), ("zhipin.com", "BOSS"),
                ("zhaopin.com", "智联"), ("51job.com", "前程无忧"))


def portal_of_url(url: str) -> str:
    """链接 → 给用户看的平台名；认不出交回空串。"""
    u = (url or "").lower()
    for host, short in PORTAL_HOSTS:
        if host in u:
            return PORTAL_DISPLAY[short]
    return ""


#: 材料里那一行「- 职位链接：<url>」。**这条规则的正本。**
#:
#: 深评与话术都靠这一行认回它说的是哪个岗 —— 「这份材料属于哪个岗」
#: 整个由它回答。
#:
#: **四个住址。** `_cli.LINK_LINE`（这里，正本）、
#: `audit_pipeline.LINK_LINE`（别名）、`doctor.LINK_LINE`（内联副本 —— 但那一份
#: 是「不得 import 本仓库任何模块」那条硬契约换来的**正当**副本，不是复制粘贴），
#: 以及 `outreach_header._LINK`（另一套形状，不与这三条共用）。
#: **`doctor` 那三遍并成了一遍** —— 剩下的那一份是硬契约换来的正当副本。
#: 四份此刻同字同序，所以谁也不红；而分叉的样子永远是
#: 「改了一份、忘了其余几份，且每份都有测试护着」。
LINK_LINE = re.compile(r"职位链接\s*[：:]\s*(\S+)")


def norm_url(u: str) -> str:
    """让同一个岗的不同写法指向同一个键：剥协议，并把 51job 的路径前缀归一。

    **去重前必须先过这一步。** 同一课这个仓库交过几次学费，每次换一个变量：

    - **协议**（2026-08-19 抓智联）：页面锚点给 `http://`，库里 08-11 存的同一批
      岗是 `https://` —— 20 个新岗里 4 个重复入库，其中两个早就判过硬门 FAIL，
      等于花账号额度把出局的岗又评了一遍。
    - **51job 的路径前缀**（2026-08-28 实测）：同一个职位号有两种挂法 ——
      `/all/<id>.html` 与 `/shanghai-<区码>/<id>.html`。历史入库的是前者，
      而 `cdp-portals.md` 记的浏览器抓取形态是后者，于是**每跑一轮前程无忧，
      已经在库里的岗就再插一遍**。热库加存档 2950 条里撞出 9 组，
      其中 8 组是当轮新插的。

    - **查询串**（2026-09-01 抓智联）：搜索结果页这一轮给的锚点尾巴上挂着
      `?refcode=…&srccode=…&preactionid=…&data_identity=…` —— 全是埋点参数，
      同一个岗每次搜到都换一串。库里存的是干净 URL，于是 **120 个「新岗」里
      43 组是已经在库里的**，其中一部分早就判过。埋点参数不参与身份。

    ⚠️ **收敛到职位号是安全的，因为库的键是 `<url>#<职位名>`**（`cdp-portals.md`
    第 7 条：「51job 实测同一 URL 下挂着两个不同职位，只用 URL 会静默吃掉其中
    一条」）—— 职位名还在键里，两个真不同的岗不会被并掉。
    **同理，剥查询串只剥 `#` 之前那一段**，职位名在 `#` 后面，不会被剥掉
    （51job 那一支例外，它本来就只收敛到职位号——那是另一件事，这次不动）。
    """
    s = (u or "").replace("https://", "//").replace("http://", "//")
    head, sep, tail = s.partition("#")
    head = head.split("?", 1)[0]
    s = head + sep + tail
    #: **手机站前缀**（2026-09-02 实测）：用户从微信里点开一个岗，复制出来的是
    #: `//m.liepin.com/job/<id>.shtml?mscid=wx_h5_001` —— 埋点参数上面已经剥掉了，
    #: 而 `m.` 没人管。后果不是重复入库（对着粘贴的 URL 跑 `/job-apply` 本来就
    #: 不新增条目，见 `job-apply.md` 收尾那条），是**材料接不回岗位行**：
    #: 目录靠 `原始链接：<URL>` 认岗，两边一个 `//m.…` 一个 `//www.…`，
    #: 于是深评和话术都出好了，总览页上那个岗还是「没有材料」。
    #:
    #: 收敛成 `www.` 而不是剥掉子域，是照库里实测的形态来的：猎聘 / BOSS /
    #: 智联三家存的都是 `www.<host>`（1127 / 192 / 172 条）。
    #: ⚠️ **51job 不在这条里** —— 它的正规形态是 `jobs.51job.com`，不是 `www.`，
    #: 所以 `m.51job.com` 收敛过去会落到一个谁也不用的主机上。它维持现状
    #: （仍是各算各的键，和这次改动之前一样，不是新增的退步）；真撞上了再按
    #: 下面那条 51job 分支的办法收敛到职位号。
    s = re.sub(r"^//(?:m|wap)\.(?!51job\.)", "//www.", s)
    m = re.match(r"(//jobs\.51job\.com)/[^/]+/(\d+)\.html", s)
    return f"{m.group(1)}/{m.group(2)}.html" if m else s


def detect_code_tool() -> str:
    """自动探测当前跑在哪个 AI 编码工具里。

    返回值：
    - "antigravity": Antigravity CLI (agy)
    - "claude": Claude Code
    - "mimo": MiMo Code（小米；opencode 的分支）
    - "mavis": MCode
    - "qoder": Qoder（实测吃斜杠：技能可按 `/<名>` 请求）
    - "qwen": Qwen Code（阿里）
    - "generic": 其它终端 / 普通命令行 / 认不出来的助手

    信号全部经过实测取证（对本机真实安装逐个核对；Qoder 那两个是
    2026-09-29 在一个真 Qoder CN 会话里 `env | grep -i qoder` 现测的；
    Qwen 与 MiMo 是读各自源码/bundle 定的，出处见下），
    **不要加「看着像」的变量名**——上一版写的 `CLAUDE_CODE`、`CLAUDE`、
    `CURSOR_VERSION`、`CODEX` 在对应工具里根本不存在，结果是真 Claude Code
    会话被认成 generic。
    - Claude Code 给所有子进程注入 `CLAUDECODE=1`（另有 CLAUDE_CODE_ENTRYPOINT）。
    - agy.exe 里有字面量 `ANTIGRAVITY_AGENT=1`。
    - Qoder CN：`QODERCN_CLI=1`（`QODER_PRODUCT_ID=qoder-cn` 那份构建的 CLI 标记）
      与 `QODER_AGENT_SDK_ENTRYPOINT=sdk-ts`（它的 agent SDK 给自己起的进程，
      对位 Claude 的 CLAUDE_CODE_ENTRYPOINT）。⚠️ 这两个是不是桌面端也注入，
      从会话内部**测不出来**（能看到的只有「在当前这个 Qoder 会话里它在」）。
      **这不妨碍用它**：本函数的返回值只往一个下游流（`doctor.COMMAND_SYNTAX`
      那张表），而 Qoder 那一格是 2026-09-29 在真会话里实测出来的 —— 它的 harness
      自己写着技能可按 `/<名>` 请求，所以给斜杠。剩下的偏差最坏是自检里那行工具名
      不准：真敲不动的时候还有触发词，把要办的事说出来照样接得住。反过来说，
      国际版的标记名**没实测过**：计划文档 §6 写着还有个 `QODER_CLI=1`，2026-09-29
      在真会话里复现不出来（只有 `-cn` 那份），所以不用它——将来真测到再加，
      别为凑一家去猜。
    - Qwen Code：它的 ShellExecutionService 给自己起的每个子 shell 注入
      `QWEN_CODE: "1"`（本机 0.14.0 的 `cli.js:183705` 与 `:183862`，两处 `cpSpawn`
      的 `env:` 块里；0.24.7 同一信号出现在更多起进程的地方）。
    - MiMo Code：主进程里直接 `process.env.MIMOCODE = "1"`
      （`packages/opencode/src/index.ts:116`，紧邻 `AGENT=1` 与 `MIMOCODE_PID`），
      子进程继承，所以比「只注给子 shell」那种更稳。MiMo 是 opencode 的分支，
      但它**不设** `OPENCODE`（同文件 grep 无命中），`MIMOCODE` 因此能唯一认出它。
    - MCode：2026-10-13 在一个真会话里 `os.environ`
      逐个量出来的，注了三个 `MAVIS_*`：
      `MAVIS_SESSION_TRANSFER_CLIENT`、`MAVIS_ELECTRON_LOCALE`、
      `MAVIS_SESSION_RESULT_DOWNLOADS_DIR`。取第一个是因为它最像会话级的
      （另两个一个跟着 Electron 语言、一个跟着下载目录），而这一档认的
      本来就是「跑在哪个 agent 里」，不是「装在哪」。
      它吃斜杠（技能注册成 `/<名>`，用户 2026-10-13 当场确认）。
    - **Gemini CLI 那一档 2026-09-30 整条删掉。** `GEMINI_CLI=1` 是**真信号**
      （它也给子 shell 注入），跟上面那批凭空写的假变量不是一回事；删它的理由是
      那家已停：包还在发版（0.61.0），但个人版登录通道被关了
      （登录返回 `reasonCode: "UNSUPPORTED_CLIENT"` / `tierId: "free-tier"`），
      官方把命令行这条线指向 Antigravity CLI（用户 2026-09-30 告知）。
      认一个装不上的工具没有意义 —— 探测出来的名字是用户判断「探测对不对」的
      唯一线索，印错了比不印更坏。它的技能目录（`.gemini/skills`）与 `.agents/skills`
      本来就都由 agy 接手，删掉这一档不丢任何覆盖面。
      ⚠️ 教训同时记一条：**「本机这一版的行为」不是「这家工具的行为」**。
      Qwen 那次就是据 0.14.0 下了「不扫 `.agents/skills`、不认斜杠」的结论，
      被 2026-09-29 发的 0.24.7 当场打回（`PROJECT_SKILL_DIRS = [".qwen", ".agents"]`）。
      下结论前先看版本，改判据前先看是不是新版已经改了。
    - Cursor 没有可识别的标记（集成终端里 TERM_PROGRAM 是 "vscode" 不是 "cursor"）；
      Codex CLI 也没有；OpenCode 有 `OPENCODE=1` 但**没实测**它认不认斜杠
      （源码里技能是以 `source: "skill"` 进命令表的，文档却写成「agent 直接调用的
      工具」，两边打架），按「没实测过 → generic」处理，不为它开档。
      Cursor 与 OpenCode 都落 `generic`，而认不出来的那一批**从 2026-10-13 起吃斜杠**
      ——**代价就是它们会拿到敲不动的斜杠**，见下面那段。要救只能手工指定。
      Codex 不用落 generic：它是实测过唯一拦斜杠的那一家，二进制里那句
      `Unrecognized command` 就是出处，所以 2026-10-13 给它单独立了一格 `no-slash`
      （探测不到，靠 `JOBS_CODE_TOOL=codex` 或面板上那个开关进）。
      认不出来就落 generic —— 理由见 `doctor.COMMAND_SYNTAX` 那段：实测 12 家里
      8 家吃斜杠，「认不出来」更可能落在吃斜杠的那一边；而真拦的 Codex 已有自己一格。
      识别错了可用环境变量 JOBS_CODE_TOOL 手工覆盖（doctor 的工具名提示仍认它），
      面板上也有开关（`CodeToolContext` 的 `setSlashMode`）。

    doctor.py 因「只用标准库、不 import 仓库模块」的契约保有一份逐字副本，
    两份判得一样由 tests/test_code_tool_detection.py 钉住。
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

