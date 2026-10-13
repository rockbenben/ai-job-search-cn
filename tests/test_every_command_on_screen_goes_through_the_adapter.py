# -*- coding: utf-8 -*-
"""屏幕上每一条 `/job-xxx`，都必须经过「按当前工具改写」那一层。

## 为什么要有

`AGENTS.md`「命令形式按当前工具给，只给一种」在面板上的落点是
`CodeToolContext` 的 `formatCommand()` 与包着它的 `<Cmd>`。但**没有任何东西钉着
「上屏的命令都走了这条路」**——`ThePanelCarriesTheSameTable` 钉的是那两张名单
（哪些家存在、哪些家吃斜杠）逐格等于 Python 的正本，它管不到「这一句文案里的命令
是谁拼的」。

于是同一个文件里能同时出现两种写法：`Shortlist.tsx` 的正文用 `<Cmd>`，
而它的悬浮提示直接把 `/job-apply` 写进字符串。**免斜杠那一档（2026-10-13 起只剩
Codex 一家）**读到的就是一个他敲不动的形式，而且是在「照着这个做」的位置上。

2026-09-30 全量审计抓到四处：`JobReadout.tsx` 的 `<code>/job-apply</code>`、
`ResumeRead.tsx` 的 `<code>/job-setup --section search</code>`，以及
`ResumeRead` / `Shortlist` 三处 tooltip。

## 判据的形状

不是「扫字符串里有没有斜杠」——那会把 `<Cmd>` 里的合法写法、注释里讲这件事的文字、
以及**拿 `/job-xxx` 当数据比对**的代码（`command?.startsWith("/job-apply")`，
它比的是 Python 导出的正本形式）一起报出来。做法是**先减掉允许的区域，
再只认「这是给中文用户看的一句文案」**：

1. 剥注释（沿用 `test_web_copy` 那三条正则）；
2. 去掉 `<Cmd>…</Cmd>` 整段；
3. 去掉 `formatCommand("…")` 里的那个串；
4. 剩下的行里，**同时**出现 `/job-` 与一个汉字的，才算上屏文案。

第 4 步那个「带汉字」的判据是把「代码」和「文案」分开的支点：这个面板的界面字全是
中文，而比对用的命令串周围不会有汉字。它不是完美的（一条纯英文的界面文案能躲过去），
所以 `test_the_detector_really_fails` 里除了正向用例，还专门钉住
「`startsWith` 那种代码不许报」——两边都钉，判据才不会往任一侧漂。

**减法式判据的代价是「允许区」写错就会静默漏掉**，所以上面那条自测把三种
允许区各破坏一次。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"

_SLASH_CMD = re.compile(r"/job-[a-z]")


# 汉字。用码点写死，不要写字面字符区间——那种写法在字符类里会被切成哪几段，
# 连写的人自己都要看两遍，而切错就是悄悄放宽判据（第一版就把 `-` 匹配进去了，
# 于是 `startsWith("/job-apply")` 这种纯代码行也被当成文案报出来）。
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _blank_out(src: str, pattern: re.Pattern) -> str:
    """把命中的片段换成等长的空格。

    **不是删掉**：删掉会让后面的行号全部前移，报错就指着一个不存在的行。
    换字符保住了换行，报出来的行号就是文件里的行号。
    """
    def sub(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return pattern.sub(sub, src)


_COMMENT_BLOCK = re.compile(r"\{/\*.*?\*/\}|/\*.*?\*/", re.S)
_COMMENT_LINE = re.compile(r"^[ \t]*//.*$", re.M)
_CMD_TAG = re.compile(r"<Cmd\b[^>]*>.*?</Cmd>", re.S)
_FORMAT_CALL = re.compile(r"""formatCommand\(\s*(["'`])[^"'`]*\1\s*\)""")


def offenders(src: str):
    """产出 (行号, 那一行) —— 绕过了适配层、又要给中文用户看的 `/job-`。"""
    body = _blank_out(src, _COMMENT_BLOCK)
    body = _blank_out(body, _COMMENT_LINE)
    body = _blank_out(body, _CMD_TAG)
    body = _blank_out(body, _FORMAT_CALL)
    for i, line in enumerate(body.splitlines(), 1):
        if _SLASH_CMD.search(line) and _CJK.search(line):
            yield i, line.strip()


class EveryCommandOnScreenGoesThroughTheAdapter(unittest.TestCase):

    def test_no_bare_command_reaches_the_screen(self):
        bad = []
        for f in sorted(SRC.rglob("*.tsx")):
            rel = f.relative_to(ROOT).as_posix()
            for line, text in offenders(f.read_text(encoding="utf-8")):
                bad.append(f"{rel}:{line}: {text[:120]}")
        self.assertEqual(bad, [], "这些 `/job-` 直接写进了界面文案，没走 "
                                  "`<Cmd>` 也没走 `formatCommand()` —— "
                                  "免斜杠那一档的用户拿到的是敲不动的形式：\n  "
                                  + "\n  ".join(bad))

    def test_the_detector_really_fails(self):
        """允许区每一条都破坏一次，证明确实是它们在放行，而不是扫了个空。"""
        # ① `<Cmd>` 里 = 走了适配层 → 干净；把外壳去掉就必须报
        self.assertEqual(list(offenders("x = <Cmd>/job-auto</Cmd>")), [])
        self.assertTrue(list(offenders("x = <code>/job-auto 就能跑</code>")),
                        "文案里的裸命令没被抓到，判据是空的")
        # ② formatCommand 放行；不调它就不放
        self.assertEqual(list(offenders('t = formatCommand("/job-auto")')), [])
        self.assertTrue(list(offenders('t = `跑 /job-auto 就行`')),
                        "模板串里的裸命令没被抓到")
        # ③ 注释不算（讲这条规则的文字自己会引用那个形式）
        self.assertEqual(list(offenders("// 别把 /job-auto 直接写进文案")), [])
        # ④ **拿命令串当数据比对的代码不算文案**——它比的是 Python 导出的正本形式，
        #    改成别的写法反而错。这条是判据往「宁滥勿缺」漂的落点，专门钉住。
        self.assertEqual(list(offenders(
            'const ok = Boolean(job.command?.startsWith("/job-apply"));')), [])
        # ⑤ 行号必须是真的：允许区用等长空格挖掉，不是删掉
        src = '第一行\n<Cmd>/job-auto</Cmd>\n第三行 跑 /job-outcome 记一笔\n'
        got = [line for line, _ in offenders(src)]
        self.assertEqual(got, [3], f"行号漂了（报 {got}，应该在第 3 行）")

    def test_it_scans_a_nontrivial_number_of_files(self):
        """扫描面不能是 0 —— 目录改名之后这条测试会绿着什么都不查。"""
        n = len(list(SRC.rglob("*.tsx")))
        self.assertGreater(n, 10, f"只扫到 {n} 个 .tsx，路径大概挪了")


if __name__ == "__main__":
    unittest.main()
