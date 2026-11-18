"""扫 JSX 源码的共用件。

只放**多个测试文件都要用**的东西。单个文件自己用的解析留在那个文件里。

## 为什么不用正则找开标签

`<button[^>]*>` 看着够用，实际不行——属性里的表达式常带 `>`：

    <button
      data-state={s.count > 0 ? "active" : "zero"}   ← 这个 > 会提前收尾
      aria-label={ok ? `有 ${n} 个` : "没有"}
    >

栽过两次：`test_pipeline_counts` 的断言就是这么截断的，截出来的片段里没有
`disabled=`，于是「验到了」和「什么都没验到」看起来一样。所以按 `{}` 深度扫。
"""

import re


#: 投递进度切换那一排的按钮（「待投 / 材料已备 / 已投递 / 面试中」）。
#:
#: 两家都要它：一家验「切过去之后还回得来」，一家验「材料已备这一档有自己的名字」。
#: 逐字钉两遍，改一次两家一起红——提成共用常量，改一处两家都跟着走
#: （`test_a_guard_pins_behaviour_not_a_line` 的 OneLineOneGuard 就是这个用途）。
POSITION_VIEW = 'aria-pressed={funnel === id} onClick={() => changeFunnel(id)}'

#: 「工具与设置」那一排入口的容器。
#:
#: 两家各钉一遍：一家问「它在不在侧栏里」，一家问「告警按钮那排还在不在」。
#: 同一行字符串住两家 = 一起红，所以收在这里。
DESKBAR = 'className="deskbar"'


#: 还没建过档的人那块内联命令表的锚点。
#:
#: 原来**三个测试文件、六条断言**逐字钉着它外面那行 JSX 条件
#: （`{!activeUser && (snap.commands ?? []).length > 0 && (`）——换个行、多个空格、
#: 把条件提成一个变量，六条一起红，而页面一个像素都没变。
#: 判据要钉**行为**，不钉那一行长什么样（`CONTRIBUTING.md` 有这一条）。
#: `firstrun` 是给这一块起的名字 —— 改名才该红。
FIRSTRUN = '<section className="firstrun"'


def desk_entry(src: str, key: str) -> str:
    """「设置/统计/说明」那一排里某一格的定义正文，**注释已剥掉**。

    剥注释是必须的：这几格的注释里逐字写着历史上的闸门
    （`!!activeUser`、`defaultActiveKey={activeUser ? [] : ["cmds"]}`）。
    「这一格没有闸门」这条断言如果按原文查，会被讲它为什么没有闸门的那段话绊倒。

    ⚠️ 查闸门要查 `activeUser` **这个名字**，别查 `&& !!activeUser` 那一种写法 ——
    原来三个文件都是后者，而 `&& Boolean(activeUser)`、`&& activeUser != null`
    照样是同一道闸门，三条却会一起绿。**假绿比脆更坏。**
    """
    from _srcscan import strip_comments
    s = strip_comments(src)
    i = s.index(f'key: "{key}"')
    return s[i:i + 400]


def between(src: str, start: str, end: str) -> str:
    """从 `start` 切到 `end`（不含），**而不是猜一个字符宽度的窗口**。

    定宽窗口是这个仓库反复栽的坑：量的时候刚好够，后面内容一长就溢出到
    不相关的段落里，而**溢出区里往往正好也有要查的那个字符串** —— 于是
    判据永远绿，它本该抓的删除抓不到。

    实测两次（2026-09-03 同一天）：
    - `CommandBook.tsx` 的脊梁块真实长度约 1005 字，窗口开了 1800，
      多切近 800 字；当时没炸只是因为溢出区里没有别的命令名 —— 运气。
    - `README.md` 的快速开始表窗口开了 1200，**已经溢出到了**后面
      「之后就是 `/job-auto` 补货 → 你自己发 → `/job-outcome` 记账的循环」
      那句话上：把表里 `/job-outcome` 那一行整行删掉，判据照样绿 ——
      而那正是它 docstring 里写着要防的那次事故。

    找不到标记就 `ValueError`：让调用方先用 `assertIn(标记, …)` 说清楚
    「这一块没了」，而不是在这里抛一个读不懂的异常。
    """
    i = src.index(start)
    return src[i:src.index(end, i)]


def firstrun(src: str) -> str:
    """那一块的正文（到 `</section>` 为止）。"""
    return between(src, FIRSTRUN, "</section>")


def jsx_open_tags(src: str, tag: str):
    """产出每个 `<tag …>` 开标签的**完整文本**（含跨行属性，不含子节点）。

    按 `{}` 深度扫到深度 0 的那个 `>`，所以属性里带对象、三元、模板串都不会截断。
    也不用「往前找 N 个字符」那种窗口——窗口会被后来插进去的注释顶出去，
    这个仓库栽过一次：断言还在，命中的却已经不是那个元素了。
    """
    for m in re.finditer(rf"<{tag}\b", src):
        depth, i = 0, m.end()
        while i < len(src):
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                yield src[m.start():i + 1]
                break
            i += 1


def copyable_texts(src: str) -> list:
    """这个文件里所有**能一键复制**的内容。

    命令片一律走 `components/Cmd.tsx` 的 `<Cmd>` / `<CopyIcon>`（见那里的说明：
    23 个复制按钮原来的无障碍名全是「复制」）。所以「这条命令能不能复制」
    只要问一句「它在不在 `<Cmd>` 里」。

    ## 为什么要有这个函数

    四处断言原来各自锚在 `copyable=\\{\\{[^}]*\\}\\}>` 这段**标记**上。把配置收进
    一个组件之后，四处同时红了——而它们要验的事（命令必须能复制、不能让人手打）
    一个字没变。锚点挂在拼法上，正当的重构就会被当成回归。

    改成问「意图」：`assertIn("/job-resume", copyable_texts(src))`。
    """
    out = []
    for m in re.finditer(r"<Cmd>(.*?)</Cmd>", src, re.S):
        out.append(m.group(1).strip())
    for m in re.finditer(r"<CopyIcon\b[^>]*?\btext=\{([^}]*)\}", src, re.S):
        out.append(m.group(1).strip())
    return out


def is_copyable(src: str, cmd: str) -> bool:
    """`cmd` **整条**是某个可复制块的内容吗。

    ⚠ **精确比，不是子串。** 子串会踩回原来那个坑：`BaseResume.tsx` 里既有
    `<Cmd>/job-resume</Cmd>`，也有 `<Cmd>typst compile …/resume/main.typ</Cmd>`
    ——后者含 `/job-resume` 这三个字。用子串判的话，把真正那条命令片整个换成
    `<code>` 也照样绿（突变当场证明了）。而那处测试的 docstring 本来就写着
    「不是全文搜 `/job-resume`——那个串在路径里也出现」。

    命令带参数（`/job-interview 某游戏公司`）时不要用这个函数，用 `copyable_texts`
    自己判前缀。
    """
    return cmd in copyable_texts(src)


def attr_expr(open_tag: str, name: str):
    """开标签里 `name={…}` 的表达式原文；没写这个属性返回 None。

    同样按深度取，`aria-label={ok ? \\`有 ${n} 个\\` : "没有"}` 里的 `}` 不会误收。
    """
    m = re.search(rf"\b{re.escape(name)}=\{{", open_tag)
    if not m:
        return None
    depth, i, start = 1, m.end(), m.end()
    while i < len(open_tag):
        if open_tag[i] == "{":
            depth += 1
        elif open_tag[i] == "}":
            depth -= 1
            if depth == 0:
                return open_tag[start:i].strip()
        i += 1
    return None


def element_color(src: str, needle: str, css: str):
    """包着 `needle` 的那个元素，最终拿到哪个颜色令牌（返回 `var(--x)` 形状）。

    判据该问「这句话是什么颜色」，不该问「颜色写在哪」。2026-09-30 把静态
    inline style 收进 class 之后，两条按 `style=` 或固定字符窗口找颜色的证人
    当场失效——而颜色其实一个字没变。所以这里两条路都认：

      1. 元素自己带 `style={{ color: "var(--x)" }}` → 取它（内联压过一切）；
      2. 否则拿它的 class 去 CSS 里找**最后**一条盖住它的 `color: var(--x)`
         （文件里后写的赢，同特异性时贴近层叠顺序）。

    `src` 要先剥过 JSX 注释（`_srcscan.strip_comments` 就够）——解释某条规则的
    注释里常常也写着那句话，`index()` 会先命中注释。这个坑本仓库记过好几轮。
    找不到来源时返回 **None**：调用方要把它当失败断言，不能当「没问题」。
    """
    i = src.index(needle)
    start = src.rindex("<", 0, i)
    tag = src[start:src.index(">", start)]
    m = re.search(r"color:\s*[\"']?(var\(--[a-z0-9-]+\))", tag)
    if m:
        return m.group(1)
    cm = re.search(r'className="([^"]+)"', tag)
    if not cm:
        return None
    classes = set(re.findall(r"[a-zA-Z][\w-]*", cm.group(1)))
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = None
    for sel, block in re.findall(r"([^{}]+)\{([^{}]*)\}", body):
        sel_cls = set(re.findall(r"\.([a-zA-Z][\w-]*)", sel))
        if not sel_cls or not sel_cls <= classes:
            continue
        c = re.search(r"color:\s*var\((--[a-z0-9-]+)\)", block)
        if c:
            found = "var(" + c.group(1) + ")"
    return found
