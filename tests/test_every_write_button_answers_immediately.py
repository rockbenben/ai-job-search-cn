# -*- coding: utf-8 -*-
"""面板上每个写盘按钮，点下去屏幕上**必须立刻有东西变**。

## 为什么要一条扫描，而不是再写一条钉某个按钮的判据

用户为同一件事报了四次（`test_marking_applied_is_instant.py` 记着前三次，
2026-09-02 是第四次：「点了 我投了，怎么没乐观更新，还是要等几秒」）。
那份判据把「我投了」这一条钉得很死 —— 而修完之后机械扫一遍才发现：
**八个写盘按钮里只有两个是乐观的**，另外六个点下去屏幕上一个字不变：

    Portals.toggle / JobPrefs.toggle          开关不动、还变灰
    Portals.markRefreshed / Portals.unblock   同上
    JobReadout.undo / JobReadout.saveReason   同上

一条一条钉，只会在用户报第五次、第六次的时候才补上第五条、第六条。
所以这里钉的是**形状**：凡是往 `post…()` 写盘，那之前必须已经动过界面。

## 2026-10-14：这条自己空转过一轮，而它的说明还写着「全是乐观的」

`App.tsx` 的 `expire()`（面板上「职位已下线」）当时**根本不是乐观的**：
`postExpire(id).then(...)`，写盘回来之前屏幕上一个字不变 —— 写盘要等
`serve.py` 同步跑完导出子进程（实测 3.4-4.2 秒）。「我投了」和「不投」
早就各有一层本地覆盖，只有它没有，于是三个并排的按钮里有一个是慢的。

**它没被抓到，是因为探测器两半都够不着：** `_FN` 只认 `async function f(`
与 `const f = async (`，而 `expire` 是**同步**箭头；`_POST` 又要求 `await`，
而它走的是 `.then(`。一个形状不合的函数在这条里等于不存在。

所以改两处：

1. `_FN` 连**同步**箭头与 `function` 声明一起认。
2. 回滚那条认 `} catch` **和** `.catch(`——`exclude()` / `expire()` 走的是
   `postX().then().catch()`，上一版只找前者，于是这两个连"有没有回滚"都没验过。

## 这条仍然看不见的（写下来，别假装没有）

2026-10-14 试过加一条「每一处写盘调用都要有交代」的覆盖控制，**又撤掉了**：
变异验证不通过。`App.tsx` 里那个组件函数的声明到文件末尾几乎是一整段，
于是任何加进去的调用都算"落在某个被检查的处理函数体内"，而匿名 async 箭头
（JSX 属性 `onSave={async () => …}`）本来就没有具名宿主可归。**它给出的绿
是自己造出来的**，比不写更坏。

所以本文件的覆盖范围仍然是「**具名**处理函数」。挂匿名箭头上的写盘路径
（今天只有 `postHrAnswer`，见下面）不在其中。

## 判据的宽窄，说清楚

「动过界面」= 写盘之前出现过 `setXxx(` 或 `onChanged?.(`，**但 `setBusy` /
`setErr` / `setStatusErr` 这类不算**：它们只把控件转起来或变灰，屏幕上的内容
一个字没变——那正是用户说的「点了没反应」。

⚠️ 它**不区分「这一行消失」和「展开位置挪了」**：把 `expire()` 的
`setJustExpired(...)` 删掉、只留 `setSelectedId(next)`，这条照样绿。判据守的是
「屏幕有变化」，不是「那一行走得掉」——后者要的是行为断言，代价是另一条守卫。

## 已知不验的一条（写清理由）

`postHrAnswer` 挂在匿名 async 箭头（JSX 属性 `onSave=`）上，探测器配不出具名
宿主。**豁免的理由不是「它不重要」，是它在别处已经变了**：用户先在受控输入框
里打字（`setDraft`），屏幕在写盘之前就已经变了；保存按钮另外把控件置灰、
失败时显示服务端真因。豁免的是「先打字、再保存」这个形状。

⚠️ **乐观更新必须配回滚**，否则就是「界面说记上了，盘上没有」，比慢更糟。
回滚由 `catch` 里那一支负责，这条一并钉。

## 那几秒是从哪来的

`serve.py` 写完盘在**响应之前**同步跑导出子进程（`regenerate()`），
2026-09-02 实测 3.4-4.2 秒（起进程 + import 只占 353ms，其余是真在算）。
这条判据不管它快不快 —— **快慢是服务端的事，点下去有没有反应是前端的事**，
把两者绑在一起正是那四次报障的根源。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"

#: `async function foo(` / `function foo(` / `const foo = (` / `const foo = async (`
#: **同步箭头也算** —— 2026-10-14 就是这里漏了 `const expire = (id: string) =>`，
#: 而它恰好是当时唯一不乐观的那个按钮。
_FN = re.compile(
    r"(?:async function (\w+)|function (\w+)"
    r"|const (\w+)\s*=\s*async"
    # 同步箭头：**只到 `=` 为止**，左括号由下面共享的那个 `\s*\(` 吃。
    # 这里原来多写了一个 `\(`，于是 `const exclude = (` 匹配不上、而 App.tsx
    # 一个处理函数都收不到 —— 一次「以为放宽了、其实收得更紧」的静默失效。
    r"|const (\w+)\s*=\s*(?!async))\s*\("
)
#: **不要求 `await`。** 要求了就会漏掉 `.then(post…)` 那一种写法，
#: 而那一种恰好是最容易写成同步箭头、也就最容易漏做乐观更新的一种。
_POST = re.compile(r"\b(post[A-Z]\w*)[ \t]*\(")
#: 「我在忙」不是「内容变了」。
_SPIN = re.compile(r"set(Busy|StatusErr|Err|Error|Loading|Saving|Pending)\(")
_TOUCH = re.compile(r"set[A-Z]\w*\(|onChanged\?\.\(")

#: 豁免要写理由，且要写清楚**用户点下去看到的是什么**。
#: 空着是件好事：现在十个具名写盘处理函数全是乐观的。
EXEMPT: dict[str, str] = {}


def _code(body: str) -> str:
    """剥掉 `//` 注释。

    这个仓库的常客：断言撞上**解释这条规则的那句注释**。本文件正文里就写着
    `setBusy`、`onChanged?.(` 这些词，不剥就会把注释当成代码读。
    """
    return re.sub(r"//[^\n]*", "", body)


def _handlers():
    """(文件名, 函数名, 函数体在文件内的 [起, 止), 写盘前的片段, 函数体)。"""
    out = []
    for path in sorted(WEB.rglob("*.tsx")):
        # **偏移一律在剥掉注释的文本上算。** 原来处理函数体用原文、而写盘调用用
        # 剥过注释的文本，两套偏移互相对不上——于是明明在 `mark()` / `saveReason()`
        # 里的两处 `postStatus` 被算成「没人管」。
        text = _code(path.read_text(encoding="utf-8"))
        for m in _FN.finditer(text):
            name = next(g for g in m.groups() if g)
            body = "\n".join(text[m.start():].splitlines()[:70])
            end = body.find("\n  }")
            body = body[:end] if end > 0 else body
            post = _POST.search(body)
            if post:
                lo = m.start()
                out.append((path.name, name, (lo, lo + len(body)),
                            body[:post.start()], body))
    return out


class EveryWriteButtonAnswersImmediately(unittest.TestCase):

    def test_there_are_handlers_to_check(self):
        """控制组：真扫到了东西。

        没有它，哪天正则跟不上写法的变化，这条会一声不响地变成永远绿 ——
        而它守的正是「静默失效」这一类。**2026-10-14 真的发生过一次**：
        放宽 `_FN` 时在第四个分支里多写了一个 `\\(`，`const exclude = (` 因此
        匹配不上，App.tsx 一个处理函数都收不到，而这条还在绿。
        """
        found = list(_handlers())
        self.assertGreaterEqual(
            len(found), 10,
            f"只扫到 {len(found)} 个写盘处理函数 —— 多半是正则跟不上写法了")

    def test_the_screen_changes_before_the_write(self):
        for file, name, _span, before, _body in _handlers():
            with self.subTest(handler=f"{file}:{name}"):
                if name in EXEMPT:
                    continue
                touched = [t for t in _TOUCH.findall(_code(before))
                           if not _SPIN.match(t)]
                self.assertTrue(
                    touched,
                    f"{file} 的 {name}() 在写盘之前什么都没改 —— "
                    f"点下去屏幕上一个字不变，要等写盘回来（实测 3.4-4.2 秒）。"
                    f"照 `Portals.tsx` 的 `ovOn` 加一层本地覆盖，"
                    f"或在本文件 EXEMPT 里写清为什么这一个不需要")

    def test_it_rolls_back(self):
        """乐观更新配回滚：`catch` 里要把界面改回去，不能只报个错。"""
        for file, name, _span, _before, body in _handlers():
            with self.subTest(handler=f"{file}:{name}"):
                if name in EXEMPT:
                    continue
                code = _code(body)
                # `} catch` **和** `.catch(` 都算。上一版只认前者，而
                # `exclude()` / `expire()` 走的是 `postX().then().catch()` ——
                # 又是「写法不同就等于没验过」，于是这两个当时都查不到回滚。
                starts = [i for i in (code.find("} catch"), code.find(".catch("))
                          if i != -1]
                catch = code[min(starts):] if starts else ""
                rolled = [t for t in _TOUCH.findall(catch)
                          if not _SPIN.match(t)]
                self.assertTrue(
                    rolled,
                    f"{file} 的 {name}() 乐观更新了却没有回滚 —— "
                    f"写盘失败时界面会一直说它成了，而盘上没有。"
                    f"那比慢更糟：他不会再去看第二眼")


if __name__ == "__main__":
    unittest.main()