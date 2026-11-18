#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复核职位原链接还在不在，把「确认已下线」写回面板状态。

    python tools/check_links.py                  # 试运行，只报不写
    python tools/check_links.py --apply         # 确认下线才写「已下线」
    python tools/check_links.py --urls-file X   # 只查指定链接（回归用）
    python tools/check_links.py --confirm-file X  # 导入有权限通道/人工确认的下线结论
    python tools/check_links.py --undo          # 把本工具写过的状态全部撤回

## 为什么要有它

面板上「材料备好、可以发」的名单里混着大量死链。此前 `export_web_data` 只用
`queuedDays`（在我手上排了多久）当代理指标，`stale_materials.py` 只查
「材料与判断一致否」，全库没有任何一处去测「这个岗还在不在」这个事实。

## 准确是第一要求：只认正向硬证据（2026-11-13 用户裁定）

最容易做错的，是把**没权限**当成**下线**。实测：

- 猎聘把没权限的请求一律甩到 `wow.liepin.com/t1012695/transit.html`，
  再跳一个约 1 KB 的通用落地页。**活岗、下线岗、6 天前刚抓的新岗，跳的是同一个页。**
  同一个活岗这次请求落通用页、换个通道就有完整 JD +「90天前更新」。
- 「整页只剩别家公司的相似职位推荐」「没有 JD」同样可能只是页面降级，不能当证据。
- 验证码页 / `Verification` / BOSS 的「XX是什么职位_…前景待遇」SEO 聚合页，同理。

所以判据只有一条：**页面自己正向写出下线状态**——「该职位已暂停招聘」
「当前职位审核中或已下线」「职位已下线」等文案，或 `job-expired` / `stop-apply`
这类下线模板标记。没拿到 JD、页面变小、只剩推荐位，一律判不了，绝不写状态。

反过来，**有完整 JD 一票否决**：拿得到「职位介绍 + 岗位职责/任职要求」就是还活着。

三道保险：
1. **通道权限自检** —— 本轮一个 `alive` 都没有，说明整条通道没权限，
   本轮所有 `expired` 一律不写（宁可漏标，不可错标）。
2. **双次一致** —— 判 `expired` 的隔 `--sleep` 秒重查一次，两次都命中硬文案才确认。
3. **不覆盖人的决定** —— 叠加层里已有 `skipped` / `expired` 等 decision 的行跳过；
   写时带 `reason` 留痕，`--undo` 可整批撤回（分数与结论始终不动）。

## 判不了 ≠ 还活着：没权限会漏标，必须留复核入口

实测（2026-11-13 用户确认的样本）：这个岗在登录态页面明写
「该职位已暂停招聘」，确实下线了；但两条只读通道拿到的都只是 1 KB 通用落地页，
**连硬文案都取不到**。所以「没权限」是漏标（false negative），不是终态：

- `no_permission` 的行不进「N 天内查过就跳过」的缓存，每轮重查；
- 汇总里单列「待复核」，交给你在登录态浏览器里看；
- 你在有权限的页面上看到明写下线，把 `URL<TAB>那一句原文` 写进一个文件，
  `--confirm-file` 导入即可落状态（可覆盖早先的「不投」，但 reason 留痕原决定）。

## 取页通道

默认走只读的公开页面读取服务（`https://r.jina.ai/<url>`）：不碰登录态、不占
`portal_budget` 的抓取额度、不算 `AGENTS.md`「取数渠道的顺位」里那四层抓岗通道。
`--base` 可换成自建代理。请求之间限速 `--sleep`（默认 3 秒）。

结果落 `job_scraper/link_check_state.json`（个人数据目录，已 gitignore），
按 URL 记住 `linkStatus` / `linkCheckedAt` / `evidence`；`--max-age` 天内查过的不重查。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

DEFAULT_BASE = "https://r.jina.ai/"
DEFAULT_SLEEP = 3.0
DEFAULT_MAX_AGE = 7

# 正向硬证据：页面 / 模板自己说「这个岗没了」
_OFFLINE_WORD = re.compile(
    r"该职位已暂停招聘|当前职位审核中或已下线|该职位已下线|职位已下线|"
    r"该职位已结束|职位已结束|已停止招聘|停止招聘|该职位已关闭|职位不存在|"
    r"该职位已失效|职位已过期")
_OFFLINE_MARKUP = re.compile(r"job-expired|stop-apply|下线图片")
# 活岗证据
_JD_TITLE = re.compile(r"职位介绍|职位描述")
_JD_BODY = re.compile(r"岗位职责|任职要求|岗位描述|职位要求|Who You Are")
# 明确的没权限 / 拦截
_NO_PERMISSION = re.compile(
    r"captchaPage|安全中心-验证码|Verification|验证中心|"
    r"t1012695/transit\.html|t1012695/4410f519\.html|请稍候|正在加载中")
_SEO_AGG = re.compile(r"是什么职位_|就业前景_|前景待遇-BOSS直聘")

ALIVE, EXPIRED, NO_PERMISSION, UNKNOWN = "alive", "expired", "no_permission", "unknown"
WRITABLE = "本工具写入"


def classify(body: str, final_url: str = "", title: str = "") -> tuple[str, str]:
    """`(状态, 证据)`。判不了的一律不写状态——这是整个工具的核心。"""
    probe = "\n".join((title, final_url, body[:4000]))

    # 1) 有完整 JD 就是活着，一票否决所有下线暗示
    if _JD_TITLE.search(body) and _JD_BODY.search(body):
        return ALIVE, "有完整职位介绍 + 岗位职责/任职要求"

    # 2) 明确的拦截页 / SEO 聚合页：不是下线，判不了
    if _NO_PERMISSION.search(probe):
        return NO_PERMISSION, "没权限或页面被降级（通用落地页/验证码），不能当证据"
    if _SEO_AGG.search(title):
        return UNKNOWN, "搜索引擎聚合页，不是职位详情页"

    # 3) 唯一可写状态的一档：页面正向写出下线。
    #    ⚠ 必须排在「短页面 = 没权限」之前 —— 下线页本身也只有 18 KB 上下的
    #    推荐卡片，标题常常就是空的。形态推断永远不能盖过页面明说的事实。
    m = _OFFLINE_WORD.search(body)
    if m:
        return EXPIRED, f"页面明写「{m.group(0)}」"
    m2 = _OFFLINE_MARKUP.search(body)
    if m2 and not _JD_TITLE.search(body):
        return EXPIRED, f"下线模板标记 {m2.group(0)}（且无 JD）"

    # 4) 短通用页 = 没权限；其余全部判不了：没有 JD、只剩推荐位都不算
    if len(body) < 2000 and title.strip() in ("", "猎聘"):
        return NO_PERMISSION, "通用落地页（没权限），不是下线"
    return UNKNOWN, "既没有下线明示，也没有完整 JD（可能是没权限）"


def fetch(url: str, base: str = DEFAULT_BASE, timeout: int = 35) -> tuple[str, str, str]:
    """`(正文, 最终跳转, 标题)`。网络失败抛异常，由调用方记错误。"""
    req = urllib.request.Request(base + url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "text/plain"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "ignore")
    m = re.search(r"Final URL:\s*(\S+)", body)
    t = re.search(r"^Title:\s*(.+)$", body, re.M)
    return body, (m.group(1) if m else ""), (t.group(1).strip() if t else "")


def check_one(url: str, *, base: str, sleep: float, confirm: bool = True):
    """单条复核。判下线的，隔一会儿再查一次，两次一致才算数。"""
    try:
        body, final, title = fetch(url, base)
        verdict, evidence = classify(body, final, title)
    except Exception as e:
        return {"status": UNKNOWN, "evidence": f"取页失败 {type(e).__name__}", "url": url}
    rec = {"status": verdict, "evidence": evidence, "url": url,
           "size": len(body), "title": title[:100], "finalUrl": final}
    if verdict == EXPIRED and confirm:
        time.sleep(sleep)
        try:
            body2, final2, title2 = fetch(url, base)
            v2, e2 = classify(body2, final2, title2)
        except Exception as e:
            v2, e2 = UNKNOWN, f"复核取页失败 {type(e).__name__}"
        rec["second"] = v2
        if v2 != EXPIRED:
            rec["status"] = UNKNOWN
            rec["evidence"] = f"两次不一致（首次 {evidence} / 复核 {e2}），不写"
    return rec


def _state_path(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / "link_check_state.json"


def _load_state(p: Path) -> dict:
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (ValueError, OSError):
        return {}


def _candidates(user: str, urls_file: str | None, limit: int, max_age: int):
    """待查链接：默认取热库里还没下线、没投、有材料的，久的在前。"""
    seen_f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    seen = _cli.seen_of(json.loads(seen_f.read_text(encoding="utf-8")))
    if urls_file:
        urls = [x.strip() for x in Path(urls_file).read_text(encoding="utf-8").splitlines()
                if x.strip() and not x.startswith("#")]
    else:
        rows = [(k, e) for k, e in seen.items()
                if e.get("status") not in ("expired", "skipped") and e.get("url")]
        rows.sort(key=lambda kv: str(kv[1].get("first_seen") or ""))
        urls = [e["url"] for _, e in rows]
    state = _load_state(_state_path(user))
    today = _dt.date.today()
    fresh = []
    for u in urls:
        s = state.get(u) or {}
        # 没权限是漏标，不是结论 —— 不进缓存，每轮重查
        if s.get("linkStatus") != NO_PERMISSION:
            try:
                age = (today - _dt.date.fromisoformat(s.get("linkCheckedAt", ""))).days
            except ValueError:
                age = 10 ** 6
            if age < max_age:
                continue
        fresh.append(u)
    return seen, fresh[:limit], state


def write_expired(user: str, seen: dict, urls: list[str], state: dict) -> int:
    """只写确认下线的；跳过任何已有的人为决定；留痕、可撤回。"""
    seen_f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    st = _cli.load_user_state(seen_f, strict=True)
    url2key = {str(e.get("url") or ""): k for k, e in seen.items()}
    n = 0
    for u in urls:
        key = url2key.get(u)
        if not key or st.get(key, {}).get("decision"):
            continue  # 不覆盖「不投」、已有的「已下线」等任何人的决定
        _cli.set_user_decision(
            seen_f, key, "expired", date=_dt.date.today().isoformat(),
            reason=f"{WRITABLE}：{state[u]['evidence']}")
        n += 1
    return n


def confirm_manual(user: str, rows: list[dict]) -> tuple[int, int]:
    """导入有权限通道 / 人工确认的下线结论。`(写回数, 找不到的数)`。

    这一路允许覆盖早先的「不投」——那是本人拿页面明写的文案确认过的事实，
    但必须把原决定记进 reason，且 reason 带 `本工具写入`，`--undo` 撤得回来。
    """
    seen_f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    seen = _cli.seen_of(json.loads(seen_f.read_text(encoding="utf-8")))
    st = _cli.load_user_state(seen_f, strict=True)
    url2key = {str(e.get("url") or ""): k for k, e in seen.items()}
    n, missing = 0, 0
    for r in rows:
        key = url2key.get(r["url"])
        if not key:
            missing += 1
            continue
        prev = st.get(key, {}).get("decision")
        if prev == "expired":
            continue
        note = f"{WRITABLE}：人工确认「{r.get('evidence') or '页面明写下线'}」"
        if prev:
            note += f"（原为 {prev}，已按确认改）"
        _cli.set_user_decision(seen_f, key, "expired",
                               date=_dt.date.today().isoformat(), reason=note)
        n += 1
    return n, missing


def undo(user: str) -> int:
    """撤回本工具写过的全部状态（只认自己留的 reason）。"""
    seen_f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    st = _cli.load_user_state(seen_f, strict=True)
    keys = [k for k, v in st.items()
            if v.get("decision") == "expired" and WRITABLE in str(v.get("reason") or "")]
    for k in keys:
        _cli.set_user_decision(seen_f, k, None)
    return len(keys)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="复核职位链接，只把页面明写下线的标成已下线")
    ap.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap.add_argument("--undo", action="store_true", help="撤回本工具写过的全部已下线状态")
    ap.add_argument("--user", help=_cli.HELP_USER)
    ap.add_argument("--urls-file", help="只查这些链接，一行一个（回归测试用）")
    ap.add_argument("--confirm-file",
                    help="人工/登录态确认下线的结果，每行：URL<TAB>页面原文那一句")
    ap.add_argument("--limit", type=int, default=60, help="这一轮最多查几条，默认 60")
    ap.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE,
                    help="几天内查过的不重查，默认 7")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help="请求间隔秒数，默认 3")
    ap.add_argument("--base", default=DEFAULT_BASE, help="只读取页服务前缀")
    a = ap.parse_args(argv)
    user = _cli.pick_user(a.user or "", root=ROOT)

    if a.undo:
        n = undo(user)
        print(f"已撤回本工具写的 {n} 条「已下线」。分数和结论一直没动。")
        return 0

    if a.confirm_file:
        rows = []
        for line in Path(a.confirm_file).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t", 1)
            rows.append({"url": parts[0].strip(),
                         "evidence": parts[1].strip() if len(parts) > 1 else "页面明写下线"})
        n, missing = confirm_manual(user, rows)
        print(f"已按有权限通道的确认写回 {n} 个「已下线」；库里找不到 {missing} 个。")
        print("撤销：python tools/check_links.py --undo")
        return 0

    seen, urls, state = _candidates(user, a.urls_file, a.limit, a.max_age)
    if not urls:
        print("没有要复核的链接（都在 --max-age 天内查过，或热库里没有候选）。")
        return 0
    print(f"复核 {len(urls)} 个链接（用户：{user}）· 间隔 {a.sleep} 秒\n")

    results = []
    for i, u in enumerate(urls, 1):
        r = check_one(u, base=a.base, sleep=a.sleep)
        results.append(r)
        state[u] = {"linkStatus": r["status"], "evidence": r["evidence"],
                    "linkCheckedAt": _dt.date.today().isoformat(),
                    "title": r.get("title", "")}
        print(f"[{i:>3}/{len(urls)}] {r['status']:<14} {r['evidence'][:52]}", flush=True)
        if i < len(urls):
            time.sleep(a.sleep)

    from collections import Counter
    c = Counter(r["status"] for r in results)
    print("\n=== 结果 ===")
    for k in (ALIVE, EXPIRED, NO_PERMISSION, UNKNOWN):
        print(f"  {k:<16} {c.get(k, 0):>4}")
    pending = c.get(NO_PERMISSION, 0) + c.get(UNKNOWN, 0)
    if pending:
        print(f"\n没权限/页面降级共 {pending} 个 —— 这只是漏标，不代表还活着；"
              "登录态看到明写下线的，用 --confirm-file 导入。")

    # 权限自检：整轮一个活岗都没拿到 → 这一轮的「下线」不能信
    confident = [r["url"] for r in results if r["status"] == EXPIRED]
    if c.get(ALIVE, 0) == 0:
        confident = []
        print("\n⚠ 这一轮一个还活着的岗都没取到 —— 整条通道可能没权限，"
              "本轮所有「下线」判定一律不写。")

    state_p = _state_path(user)
    state_p.parent.mkdir(parents=True, exist_ok=True)
    _cli.atomic_write(state_p, json.dumps(state, ensure_ascii=False, indent=1))
    print(f"逐条结果已记到 {state_p.relative_to(ROOT)}")

    if a.apply:
        n = write_expired(user, seen, confident, state)
        print(f"已把 {n} 个「页面明写下线」的岗标成已下线（跳过了已有的人为决定）。")
        print("撤销：python tools/check_links.py --undo")
    else:
        print(f"确认下线 {len(confident)} 个 · 试运行，加 --apply 生效 · {_cli.DRY_RUN_NOTE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
