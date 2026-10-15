# -*- coding: utf-8 -*-
"""把话术抬头里能算出来的那几样现算：渠道、分数与档名、内部词。

    python tools/outreach_header.py            # 只看，不写盘
    python tools/outreach_header.py --apply    # 改 outreach.md 的抬头

## 它替执行者做什么

`06-outreach-templates.md` 那一节把抬头钉成四条：有没有对话方 + 猎头还是
HR 直招、这一档是什么（分数 + 档名）、链接与日期、不许出现内部词。
四条里有三条**根本不需要判断** —— 渠道看 `isHeadhunter`（或猎聘的 `/a/`
路径），分数与档名看 `rank_score` / `rank_verdict`，内部词是一张固定的词表。

**这不是「多一道检查」，是把这件事从手里拿走。** 实测活动用户 2026-08-30，
280 份话术里：

    没写是猎头还是直招   115 份   ← 第二轮怎么说话完全取决于这半句
    抬头里没有分数       247 份   ← 打开文件看不出该不该发
    抬头里写着「判词」   109 份   ← 明令禁止的内部词

而这三样在职位库里都是现成的。同一件事此前的补救全是事后的：审计报出来、
人再逐份改 —— 一份一份改 280 次，和薪资维那次一模一样。

## 它不碰什么

- **算不出渠道的**（`isHeadhunter` 为空且链接不是猎聘 `/a/`）：跳过并报数。
  猜一个的代价是让他按错误的路数谈 —— 猎头问薪资要直接答，HR 直招不主动展开。
- **抬头以外的一个字都不动。** 开场白、邮件正文、内推请托都是判断产物。
- **已经写对的**：不重写，如实报「不用改」。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402


#: 抬头里不许出现的内部词。**正本在 `_cli.HEAD_JARGON`**，这里不再抄一份。
#:
#: 原来这里手写着五对，而同一层的检查器（`audit_pipeline._HEAD_JARGON`）
#: 手写着八个 —— 差的三个（`驾驶舱`、`读数`、`能力边界`）报得出来改不了。
#: 实测 2026-08-30 的收尾：审计报「1 份用了内部词（驾驶舱）」，
#: 这个工具同一刻说「要改 0 份」，那一份只好推给人手工改。
INTERNAL = tuple((w, fix) for w, _rx, fix in _cli.HEAD_JARGON)

_CHANNEL = re.compile(r"^(-\s*渠道判定：\s*)(.*)$", re.M)
_SCORE = re.compile(r"^-\s*评分：\s*\d+\s*分", re.M)
_LINK = re.compile(r"^-\s*职位链接：.*$", re.M)
_NAMES_SIDE = re.compile(r"猎头|直招|HR|用人方")


def portal_of(url: str) -> str:
    """抬头那句「…的聊天框」要说清是哪个平台的。

    域名表原来在这里自己写了一份，且**与 `tracker` 那份（已删）分叉**：
    这边写「智联」，那边写「智联招聘」，而这两个名字都要进用户眼睛。
    2026-08-31 一起归到 `_cli.portal_of_url`。
    """
    return _cli.portal_of_url(url)


#: 抬头里表示「哪一侧」的写法，**按具体到笼统排**，第一个命中的就是它写的那个。
#: 每条给 `(那一侧, 要找的词)` —— 改的时候替换的是**找到的那个词**，
#: 不是那一侧的标准名（盘上 22 份写的是「HR 直招」，拿「企业直招」去替换替不着）。
_WRITTEN = (("企业直招", "企业直招"), ("HR 直招", "企业直招"), ("HR直招", "企业直招"),
            ("用人方直招", "企业直招"), ("猎头代招", "猎头代招"), ("猎头", "猎头代招"),
            ("直招", "企业直招"), ("HR", "企业直招"), ("用人方", "企业直招"))

#: 「非猎头」「不是猎头」是在**否定**，不是在说这是猎头岗。不先剥掉它，
#: 6 份写着「（HR 直招，非猎头）」的会被判成「写了猎头」——而它们写得完全正确。
_NEGATED = re.compile(r"(非|不是|不属于)\s*猎头")


def side_written(val: str) -> tuple[str, str]:
    """抬头那一行**写的是哪一侧**，以及它用的原词。判不出返回两个空串。"""
    v = _NEGATED.sub("", val or "")
    for phrase, side in _WRITTEN:
        if phrase in v:
            return side, phrase
    return "", ""


def side_of(entry: dict) -> str:
    """猎头代招 / 企业直招。判不出返回空串 —— **不猜**。

    判据整个在 `_cli.via_headhunter`，这里只把它翻成抬头那两个词。

    原来这里是自己写的一份：读裸的 `isHeadhunter`，外加一条猎聘 `/a/`。
    正本那份多两条（招聘者名头里的中介词、头衔里的「猎头」二字），这份都没有 ——
    于是 4 个头衔明写「猎头顾问」的岗，每一轮 `--apply` 都被这里写成「企业直招」，
    **而那半句正是第二轮怎么说话的全部依据**（`06` 渠道判定）。
    `/a/` 那一条反过来只有这份有，一并搬进了正本。
    """
    hh = _cli.via_headhunter(entry)
    if hh is None:
        return ""
    return "猎头代招" if hh else "企业直招"


def fix_header(head: str, entry: dict) -> tuple[str, list[str]]:
    """改抬头，返回 `(新抬头, 改了哪几处)`。改不动就原样返回。"""
    out, notes = head, []

    side = side_of(entry)
    m = _CHANNEL.search(out)
    if side and m:
        val = m.group(2)
        cur, phrase = side_written(val)
        if not cur:
            # 只写了一半：`**有对话方 · 猎聘聊天框**` → 补上后半句。
            # 平台名也可能缺（`· 聊天框`），一起补 —— 补在星号里面，
            # 不然渲染出来是「…聊天框**（猎头代招）」，星号裸露在屏幕上。
            v = val.rstrip()
            portal = portal_of(entry.get("url") or "")
            if portal and "聊天框" in v and portal not in v:
                v = v.replace("聊天框", f"{portal}聊天框", 1)
            v = (v[:-2] + f"（{side}）**") if v.endswith("**") else v + f"（{side}）"
            out = out[:m.start(2)] + v + out[m.end(2):]
            notes.append(f"补渠道：{side}")
        elif cur != side:
            # **替换的是「它实际写的那个词」，不是那一侧的标准名。**
            # 第一版拿 `val.replace("企业直招", "猎头代招")` 去改，而盘上 22 份
            # 写的是「HR 直招」—— 替不着，静默无操作：工具报「改了 37 份」，
            # 审计照旧报「28 份写反」。**认出来了不等于改成了。**
            v = val.replace(phrase, side, 1)
            out = out[:m.start(2)] + v + out[m.end(2):]
            notes.append(f"渠道写反了：{phrase} → {side}")

    score, verdict = entry.get("rank_score"), entry.get("rank_verdict") or ""
    verdict = _cli.strip_triage(verdict)
    if (isinstance(score, (int, float)) and verdict
            and not _SCORE.search(out) and _cli.gate_of(verdict) is not None):
        line = f"- 评分：{score} 分，属于「{verdict}」"
        m2 = _LINK.search(out)
        if m2:
            out = out[:m2.end()] + "\n" + line + out[m2.end():]
        else:
            out = out.rstrip() + "\n" + line + "\n"
        notes.append(f"补分数：{score} 分 · {verdict}")

    # **按匹配式换，不按字面换。** 主表里 `硬门` 写的是 `硬门(?!槛)` ——
    # 「硬门槛」是中文本来就有的词（实测 7 处），字面替换会把它变成
    # 「硬性条件槛」。原来这里是 `out.replace(bad, good)`，正好踩这一脚。
    for bad, rx, good in _cli.HEAD_JARGON:
        new = re.sub(rx, good, out)
        if new != out:
            out = new
            notes.append(f"内部词：{bad} → {good}")
    return out, notes


def plan(user: str) -> tuple[list, dict]:
    import build_dashboard as bd
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    seen = _cli.seen_of(_cli.read_json(p))
    _cli.stop_on_unreadable_rows(seen, p)
    byurl = {_cli.norm_url(v.get("url") or ""): v for v in seen.values() if v.get("url")}
    apps = ROOT / "users" / user / "documents" / "applications"
    rows, skip = [], {"库里找不到这个岗": 0, "抬头已经写对了": 0, "判不出渠道": 0}
    for a in bd.find_applications(apps):
        f = apps / a["dir"] / "outreach.md"
        if not f.is_file():
            continue
        entry = byurl.get(_cli.norm_url(a.get("url") or ""))
        if entry is None:
            skip["库里找不到这个岗"] += 1
            continue
        text = f.read_text(encoding="utf-8")
        cut = text.find("\n## ")
        head, rest = (text[:cut], text[cut:]) if cut > 0 else (text, "")
        new, notes = fix_header(head, entry)
        if not notes:
            skip["抬头已经写对了"] += 1
            if not side_of(entry) and not _NAMES_SIDE.search(head):
                skip["判不出渠道"] += 1
                skip["抬头已经写对了"] -= 1
            continue
        rows.append({"file": f, "dir": a["dir"], "text": new + rest, "notes": notes})
    return rows, skip


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap.add_argument("--user", default="", help=_cli.HELP_USER)
    a = ap.parse_args(argv)
    user = _cli.pick_user(a.user or "", root=ROOT)
    rows, skip = plan(user)
    print(f"话术抬头里算得出来的那几样现算（用户：{user}）")
    print(f"  要改 {len(rows)} 份；跳过：" +
          "、".join(f"{k} {n}" for k, n in skip.items() if n))
    kinds = {}
    for r in rows:
        for n in r["notes"]:
            kinds[n.split("：")[0]] = kinds.get(n.split("：")[0], 0) + 1
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"    {k} {n} 份")
    for r in rows[:8]:
        print(f"  {r['dir'][:36]:<38}{'；'.join(r['notes'])[:60]}")
    if len(rows) > 8:
        print(f"  …另有 {len(rows) - 8} 份")
    if not a.apply:
        print(chr(10) + _cli.DRY_RUN_NOTE)
        return 0
    for r in rows:
        _cli.atomic_write(r["file"], r["text"])
    print(f"\n已改 {len(rows)} 份")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
