"""网页版面板的界面文案：别把源码标记印上屏，别在两种模式下说同一句话。

## 为什么要有这个测试

`web/` 没有前端测试框架（package.json 里只有 tsc / vite），所以这两类问题一直没人拦。
两条都是实测被用户当场问出来的：

**① 裸 markdown 印到屏幕上。** JSX 的文本节点不是 markdown，`**一条**` 会连着星号一起
渲染。写的时候顺手按 markdown 习惯加了强调，屏幕上就多出四个星号。

**② 静态版的说辞漏了模式判断。** 面板有两种跑法：有 `serve.py` 时点「不投」直接写进
`seen_jobs.json`；纯静态快照时只能存浏览器、要复制一条 `/job-rank --skip` 命令才算数。
`JobReadout` 里那段提示原来**无条件**渲染静态版说辞，于是有服务时同一个页面自相矛盾：
行内说「要复制底部那条命令才永久生效」，页脚说「直接存进本机数据，刷新还在」——
而底部那条命令按 `App.tsx` 的 `!live` 判断根本不会出现。用户照着找了一圈没找到，
只能得出「这工具在骗我」。

扫的是 `.tsx` 源码里的 **JSX 文本节点**（标签之间、不含 `{}` 表达式的部分），
注释和字符串字面量不算——那些不上屏。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsx import attr_expr, element_color, jsx_open_tags  # noqa: E402

# 只在静态快照模式下成立的说法。出现在哪个组件里，那个组件就必须自己判断模式。
#: 「干活都在命令行」也在此列：有本地服务时「我投了/不投」点页面就落盘，
#: 这句只在静态模式为真——而它原来不在词表里，页脚那句是否挂在模式判断下
#: 无人守（控制变异实测：改成无条件渲染，全套照绿）。
STATIC_ONLY_PHRASES = ["永久生效", "只藏在", "静态快照", "重新生成页面它们会回来",
                       "干活都在命令行"]


def jsx_text_nodes(src: str):
    """产出 (行号, 文本)：**屏幕上真会出现的字**。

    ## 两类都要取

    1. **裸文本节点**（`<p>你好<b>世界</b></p>`）。
    2. **纯字符串表达式**（`{"你好"}`、`{"甲" + "乙"}`）——它们在屏幕上和裸文本
       没有区别。这一页有大量文案是**为了不产生多余空格**才搬进 `{"…"}` 的
       （JSX 会把文本里的换行折成一个空格，中文里那就是多余空格）。只取第一类，
       等于把刚整理过的那批文案全变成隐形。

    ## 剥插值只剥一层

    试过「反复剥到不动点」，**当场把整份文件吃掉**：TypeScript 的函数体、对象
    字面量也是花括号，从内向外收一遍，1063 字符只剩 126。剥一层是对的——它只吃掉
    最内层的插值，文档结构留着。

    这不是某一条检查的事：**禁用词、markdown、中英混排、工具名四条全建在这个函数
    上**，盲区是共用的。
    """
    body = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"^[ \t]*//.*$", "", body, flags=re.M)

    # 一层就够。插值换成空格而不是删掉：它代表「这里原本是别的东西」，
    # 删掉会让两侧的词粘成一个。
    flat = re.sub(r"\{[^{}]*\}", " ", body)
    for m in re.finditer(r">([^<>]*?)<", flat):
        txt = m.group(1)
        if not txt.strip():
            continue
        # 还留着花括号 = 那是**嵌套或跨行**的表达式，单层剥离没吃掉它。
        # 不能拿它当文案：`{g.assumed ? …}` 这种会把变量名当中文句子里的英文词报出来。
        # （原来的写法是在正则里排除 `{}`，那样连带把「挨着插值的文案」也整段跳过了
        # —— 盲区就是这么来的。改成先剥一层、再把剥不干净的整段丢掉。）
        if "{" in txt or "}" in txt:
            continue
        # TypeScript 泛型（`useState<"" | "materials">`）也带一对尖括号，于是 `>`
        # 之后会一路扫到下一个 `<`，把中间整段**代码**当成文本节点交出去。
        # 屏幕上的文案不会出现这些记号（中文用的是全角括号），据此排除。
        if re.search(r"===|=>|&&|\|\||;|\(|\)|=\s", txt):
            continue
        yield flat[: m.start()].count("\n") + 1, txt

    # 纯字符串表达式：`{"…"}` 或 `{"…" + "…"}`（允许跨行拼接）
    lit = r"(?:\"[^\"\n]*\"|'[^'\n]*'|`[^`]*`)"
    for m in re.finditer(r"\{\s*(" + lit + r"(?:\s*\+\s*" + lit + r")*)\s*\}", body):
        text = "".join(re.findall(r"[\"'`]([^\"'`]*)[\"'`]", m.group(1)))
        # 模板串里的 `${…}` 是插值，不是文案 —— 同样换成空格而不是删掉
        text = re.sub(r"\$\{[^}]*\}", " ", text)
        if text.strip():
            yield body[: m.start()].count("\n") + 1, text


def tsx_files():
    """面板里**会上屏的字**住的地方。

    原来只 glob `*.tsx`，于是 `data/sample.ts` 里那句写给新用户看的文案
    （「Claude Code 装了浏览器扩展即可用」）从头到尾没被扫过——连 `TOOL_NAMES`
    那份「界面上不许点名某家工具」的黑名单都管不到它。`.ts` 里没有 JSX，
    文本节点那条扫不到东西，但对象字面量里的文案（`OBJ_COPY`）扫得到。
    """
    return sorted(list(SRC.rglob("*.tsx")) + list(SRC.rglob("*.ts")))


class NoRawMarkdownOnScreen(unittest.TestCase):
    """JSX 文本节点不是 markdown —— 标记会原样显示给用户。"""

    def test_no_bold_or_code_markers_in_jsx_text(self):
        bad = []
        for f in tsx_files():
            for ln, txt in jsx_text_nodes(f.read_text(encoding="utf-8")):
                if re.search(r"\*\*|`[^`\n]+`|^\s*#{1,6}\s", txt):
                    bad.append(f"{f.relative_to(ROOT)}:{ln}  {txt.strip()[:60]}")
        self.assertEqual(bad, [], "JSX 文本里有 markdown 标记，会连符号一起印出来：\n"
                         + "\n".join(bad) + "\n用 <b>/<code> 标签，别用 ** 和反引号")


class CopyBornInPythonIsAlsoUserFacing(unittest.TestCase):
    """上一条只扫 **JSX 源码**，扫不到从 Python 端送上来的文案。

    实测漏了两处，都印在「市场怎么读你的简历」那块上：

        …你的主场岗已经够多：**认准主场投，比硬补域划算**。
        …这类模板句，按 FLAG 处理；真卡的是明确要硕士的那些。

    第一处那对星号是**真的显示在屏幕上**的（JSX 不渲染 markdown）；
    第二处 `FLAG` 是评估框架里的档位名，屏幕上从没解释过。

    这两句写在 `export_web_data.py` 里，随 `data.json` 一路送到页面——
    和「粗筛前缀漏上屏 87 次」「反馈换行被折掉」是同一个形状：
    **检查建在源码上，漏了数据。**
    """

    #: 会随数据上屏的文案，逐个字段收进来。加一处新的就往这里加。
    #: 走 `_notes()` 统一取——两处各写一份取法，迟早只扫到一半。
    SOURCE = ROOT / "tools" / "export_web_data.py"

    @staticmethod
    def _exported_strings() -> list:
        """`data.json` 里的每一条字符串。两处判据共用这一份取法。"""
        import json
        f = ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            return []
        out = []

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
            elif isinstance(node, str):
                out.append(node)
        walk(json.loads(f.read_text(encoding="utf-8")))
        return out

    @classmethod
    def _notes(cls) -> list:
        """`resume_insight` 里那些会上屏的整句。

        只取 `"note":` 与 `"tone":` 这类**送去渲染的字段**，不取变量名与注释。
        """
        src = cls.SOURCE.read_text(encoding="utf-8")
        src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
        out = []
        for m in re.finditer(r'"note":\s*((?:"[^"]*"\s*)+)', src):
            out.append("".join(re.findall(r'"([^"]*)"', m.group(1))))
        return out

    def test_there_is_something_to_check(self):
        """判据自检：真取到了句子，不是空跑一遍报绿。"""
        notes = self._notes()
        self.assertGreaterEqual(len(notes), 3, f"只取到 {len(notes)} 句上屏文案")

    def test_no_raw_markdown(self):
        bad = [n for n in self._notes() if re.search(r"\*\*|`[^`\n]+`", n)]
        self.assertEqual(
            bad, [],
            "这些句子会原样印到屏幕上，markdown 标记不会被渲染成加粗：\n"
            + "\n".join(bad) + "\n要强调就重写句子，别用 ** 和反引号")

    def _strings_or_skip(self) -> list:
        """取导出成品里的全部字符串。扫描源空了要当场说，不许默默通过。"""
        strings = self._exported_strings()
        if not strings:
            self.skipTest("还没导出过 data.json")
        self.assertGreater(len(strings), 500,
                           f"只从 data.json 取到 {len(strings)} 条字符串——扫描源空了")
        return strings

    def test_no_html_tags_in_exported_text(self):
        """HTML 标签和 markdown 是同一种毛病：**面板上这些字进的是纯文本节点**，
        浏览器不渲染标签，于是 `<br>` 原样上屏（2026-09-30 在渲染后的 DOM 里量到 3 处，
        全在硬性条件的依据里——评估正文是 markdown 写的，作者偶尔直接 `<br>` 断行）。

        ⚠️ 这条**只管导出的数据，不管 JSX 源码**：源码里 `<b>` / `<code>` 是合法的
        元素写法（上面那条 markdown 判据还专门让人改用标签）。分界是这段字
        到没到过「纯文本节点」那一侧。清理住在 `export_web_data.plain()`，
        它只剥列得出名字的标签——命令模板里的 `<职位链接>` 是要用户照敲的。
        """
        tag = re.compile(r"</?\s*(?:br|p|div|span|a|b|i|u|s|em|strong|code|pre|"
                         r"tt|kbd|mark|small|sub|sup|font|center|ul|ol|li|table|"
                         r"tr|td|th|h[1-6]|img)\b[^<>]*>", re.I)
        bad = [s[:70] for s in self._strings_or_skip() if tag.search(s)]
        self.assertEqual(bad, [],
                         "HTML 标签会原样印在屏幕上：\n  " + "\n  ".join(bad[:6]))

    def test_the_scorers_own_log_stays_off_the_screen(self):
        """`score.py` 每次现算都在依据末尾追加一段自述，那段字**也上了屏**。

        实测 2026-10-02：导出的 `data.json` 里 142 条带着
        「⚠️ 某日 score.py 现算订正：薪资与职级 90→80；综合分 77 → 77，
        结论可以考虑 → 值得投」。那三件事面板本来就显示着，而这句话的对象是
        **下一个改评估文件的人**（防手改），不是读屏幕的人。
        留在盘上，剥在显示层——`export_web_data._SCORE_LOG`。

        ⚠️ 这条量的是**本机那份成品**（`data.json` 不进版本库）：新长出第二条
        不经清洁工的通路会在这里红。清洁工本身对不对、`依据` 有没有过它，
        由下面两条管，那两条在 CI 上真跑。
        """
        bad = [s[:70] for s in self._strings_or_skip() if "现算订正" in s]
        self.assertEqual(bad, [],
                         "打分器的自述上了屏（它说的数面板本来就有）：\n  "
                         + "\n  ".join(bad[:4]))

    def test_the_reason_goes_through_the_cleaner(self):
        """接线也要钉住：清洁工自己对了，`依据` 不经过它照样上屏。

        142 条全部走 `skillWhy` 这一个出口（逐字段数过），所以钉这一处。
        """
        src = self.SOURCE.read_text(encoding="utf-8")
        self.assertRegex(src, r'"skillWhy":\s*plain\(',
                         '`依据` 到 `skillWhy` 这一段没过显示层清洁工')

    def test_plain_takes_the_log_but_not_a_real_warning(self):
        """**反向控制。** 只断言「剥掉了」，把 `plain()` 改成见到 ⚠️ 就删也照样绿。

        这一条不依赖真实数据，CI 上真跑。
        """
        sys.path.insert(0, str(ROOT / "tools"))
        import export_web_data as ex
        with_log = ("方向对得上。\n\n⚠️ 某日 `score.py` 现算订正："
                    "薪资与职级 90→80；综合分 77 → 77，结论可以考虑 → 值得投。"
                    "这三样（薪资维 / 综合分 / 结论）是确定性函数，由工具现算，不手填。")
        self.assertEqual(ex.plain(with_log), "方向对得上。")
        reminder = "⚠️ 英语只限书面、口语不行，JD 要求「能与外籍同事日常会议」。"
        self.assertIn("口语不行", ex.plain(reminder))

    def test_no_unexplained_codes_or_framework_words(self):
        """英文码与框架内部词都不该上屏——用户不该为了看懂工具先学一套词。"""
        banned = ["FLAG", "PASS", "四维", "业务域", "硬门", "能力边界",
                  "封顶", "判词", "台账", "短名单"]
        bad = []
        for n in self._notes():
            for w in banned:
                if re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", n):
                    bad.append(f"{w}  ——  {n[:56]}…")
        self.assertEqual(
            bad, [],
            "上屏文案里出现了内部词或没解释过的英文码（规则见 AGENTS.md"
            "「给用户看的措辞」）：\n" + "\n".join(bad))

    def test_the_detector_can_actually_fail(self):
        """判据自检——走的是**同一套**判断，不另抄一份。"""
        probe = "打分时业务域 <40 会**封顶**，按 FLAG 处理"
        self.assertTrue(re.search(r"\*\*|`[^`\n]+`", probe), "认不出裸 markdown")
        self.assertTrue(
            any(re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", probe)
                for w in ["FLAG", "业务域", "封顶"]),
            "认不出内部词")


class PersistenceCopyIsModeAware(unittest.TestCase):
    """「要复制命令才生效」只在静态模式为真；有服务时点一下就落盘了。"""

    @staticmethod
    def _without_comments(src: str) -> str:
        """注释里出现这些说法**不算**——用户看不到注释。

        判据原来扫整份源码。于是在 `Shortlist.tsx` 里写一句解释「+浮动 不能**只藏在**
        tooltip 里」的注释，就被当成了「这个文件宣称改动只藏在浏览器里」。
        同一个形状本轮已经踩到第三次（`/job-apply` 在注释里、`.active_user` 在
        gitignore 表里）——判据一律只看真正渲染出去的东西。
        """
        s = re.sub(r"\{/\*.*?\*/\}", " ", src, flags=re.S)      # JSX 注释
        s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)            # 块注释
        return "\n".join(ln for ln in s.splitlines()
                         if not ln.strip().startswith(("//", "*")))

    def test_static_only_copy_lives_behind_a_mode_check(self):
        """模式判断要**锚在那句话的渲染点上**，不是「文件里某处出现过」。

        原来按整文件判：`App.tsx` 另一处 `const steps = hasServer() ? …` 会永远
        满足它——把页脚那句的模式分支改成无条件渲染静态说辞，本条照样绿，
        正是本文件另一条 docstring 里记过的「锚点空转」形状。改成逐出现点：
        那句话往前 200 字符内必须有模式判断的痕迹。
        """
        bad = []
        for f in tsx_files():
            src = self._without_comments(f.read_text(encoding="utf-8"))
            for p in STATIC_ONLY_PHRASES:
                for m in re.finditer(re.escape(p), src):
                    # 窗口 450：pending-bar 那块的守卫 `!live &&` 与最里层的文案
                    # 隔着计数 span 和命令拼接，实测 337-390 字符——200 会把有
                    # 守卫的渲染点误报成没守卫。450 仍远小于两个不相干渲染点
                    # 之间的距离，控制检查（把页脚分支改成无条件）仍然红。
                    ctx = src[max(0, m.start() - 450):m.start()]
                    if not re.search(r"hasServer\s*\(|\blive\b", ctx):
                        bad.append(f"{f.relative_to(ROOT)} 的「{p[:18]}…」"
                                   "渲染点前 450 字符内没有模式判断")
        self.assertEqual(bad, [], "\n".join(bad) + "\n"
                         "有本地服务时这些说法是假的，会和页脚自相矛盾")

    def test_the_comment_stripping_still_catches_real_text(self):
        """剥注释不能把真问题一起剥掉——两头都要验。"""
        real = 'export function X() {\n  return <p>这些改动只藏在这台电脑的浏览器里</p>;\n}\n'
        kept = [p for p in STATIC_ONLY_PHRASES if p in self._without_comments(real)]
        self.assertTrue(kept, "剥注释剥过头了，正文里的说法也没了")

        commented = '{/* 说明：不能只藏在 tooltip 里 */}\n<p>正常文案</p>'
        left = [p for p in STATIC_ONLY_PHRASES if p in self._without_comments(commented)]
        self.assertEqual(left, [], "注释里的说法仍然被算进去了")

    def test_the_drop_button_says_where_to_undo(self):
        """点完「不投这个岗」，这一行就从名单里消失了 —— **必须说清去哪找回来**。

        > 这条原来断言的是**全文里有没有 `hasServer() ?`**。那个串在这个文件里
        > 还有一处（`const steps = hasServer() ? …`），跟这段提示毫无关系。
        > 后来这段提示从三元改成了 `&&`，断言照样绿——它匹配的是另一处，
        > **变成了空转**。锚点必须落在被验的那个东西上。

        话没删，位置换了：原来它是展开区里单独一行（`.act-drop-hint`），于是
        24 个岗展开 24 遍，占的还是「怎么投」那块最显眼的位置；现在写在**按钮
        自己的 title 上**——说明贴在它说明的那个东西上，需要时才出现。
        锚点跟着搬，验的仍是同一件事：反悔路径不能没有，也不能只说「存下来了」。

        不再验模式分叉：title 是按钮自带的，静态模式下那个按钮同样在、同样让
        岗位从名单里消失，这句话两种模式下都成立（存到哪由页脚那句说，
        `test_the_static_row_hint_is_gone` 管着它不往行里跑）。
        """
        src = self._without_comments(
            (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8"))
        titles = []
        for m in re.finditer(r'className="act-drop"', src):
            seg = src[m.start():m.start() + 400]
            t = re.search(r'title="([^"]*)"', seg)
            if t:
                titles.append(t.group(1))
        self.assertTrue(titles, "「不投这个岗」按钮一个 title 都没有了")
        withpath = [t for t in titles if "放回" in t and "不投的岗位" in t]
        self.assertTrue(
            withpath,
            f"没有一个 title 给出反悔路径：{titles!r} —— "
            "岗位点完就从名单里消失，用户不知道去哪找回来")

    def test_the_static_row_hint_is_gone(self):
        """静态模式下这一行**不出声**：同样的话底部那条 `pending-bar` 说得更好。

        原来它在每个展开行里、用户还没点任何东西之前就先讲一遍后果，而底部那条
        带计数、带真命令、标了才出现。两处都成立的话，留在真正相关的那一刻说。
        """
        src = self._without_comments(
            (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8"))
        for p in STATIC_ONLY_PHRASES:
            with self.subTest(phrase=p):
                self.assertNotIn(p, src,
                                 f"行内又开始讲静态模式的后果了（「{p}」）—— "
                                 "底部那条 pending-bar 已经在说同一件事")


class EmptyDataIsNeverRenderedAsAllClear(unittest.TestCase):
    """「一条都没解析到」不等于「都通过了」。

    `GateGrid` 原来没有空数组守卫：`gates` 为空时格子是空的，而下面那句走 else
    分支印出「这些条件都核对过了，没有要问的」——把**没有数据**说成**核对通过**。
    用户据此以为学历、外包、地点都验过了，这是整页最危险的一种错误。

    调用方 `JobReadout` 那层的守卫是 `dimensions || gates || gaps`（**或**），
    只挡得住三者全空；四维解析成功、硬门解析失败时它判 true，照样渲染进来。
    实测就这么发生过（硬门表标题不带「硬门」二字 → 整张表被丢弃）。所以守卫必须
    落在数据为空的那一层，而不是调用方猜「大概有数据」的那一层。
    """

    def test_gate_grid_guards_the_empty_array(self):
        src = (SRC / "components" / "GateStamp.tsx").read_text(encoding="utf-8")
        self.assertRegex(
            src, r"gates\.length\s*===?\s*0",
            "GateGrid 没有空数组守卫 —— 零条硬性条件会被渲染成「都核对过了」")
        # 用 rindex：这句话在注释里也出现（解释这个 bug 是什么），
        # 真正的渲染点是最后那次。锚到第一次会把守卫切在切片外面。
        head = src[: src.rindex("这些条件都核对过了")]
        self.assertIn("gates.length === 0", head,
                      "空数组守卫必须在那句「都核对过了」**之前**返回")

    def test_the_empty_state_says_unchecked_not_passed(self):
        src = (SRC / "components" / "GateStamp.tsx").read_text(encoding="utf-8")
        self.assertIn("还没核对过", src, "空状态得说清是「还没核对」，不能含糊过去")


class PointersMatchWhatIsActuallyRendered(unittest.TestCase):
    """「上面那条命令」得真的在上面。

    这段话的渲染条件是 `!hasDetail`，而它指的 `/job-apply` 命令块另有条件 —— 两个条件
    不等时，上面显示的是开场白，这句话却让人去找一条屏幕上没有的命令。和「页面底部
    会汇总成一条命令」而底部什么都没有，是同一个 bug。

    > 这条**原来断言的是字面拼写** `m?.greeting`——那正是当时用来「猜」上面有没有
    > 命令的代理条件。后来那条命令的来源换成了「下一步」那行（`job.nextStep`），
    > 判断也跟着换成直接看它，**指针比原来更准了，这条却红了**。
    >
    > 所以改成钉意图：这句话的分支必须**取自它所指的那个东西**，叫什么名字随便。
    """

    def test_the_apply_pointer_branches_on_whether_it_is_shown(self):
        src = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        seg = src[src.index("这个岗只按列表信息评过"):]
        seg = seg[: seg.index("</p>")]

        m = re.search(r"\{\s*([A-Za-z_$][\w$]*)\s*\?", seg)
        self.assertIsNotNone(
            m, f"这句话不再分支了——「上面那条」成了无条件断言：\n{seg}")
        name = m.group(1)
        decl = re.search(rf"const {re.escape(name)} = (.+?);", src, re.S)
        self.assertIsNotNone(decl, f"找不到 {name} 是怎么来的")
        self.assertIn(
            "nextStep", decl.group(1),
            f"「上面那条 /job-apply」的判断没看上面真正渲染的东西："
            f"{name} = {decl.group(1).strip()}")

    def test_the_command_above_really_comes_from_there(self):
        """控制用例：上面那条命令确实取自 `nextStep`。

        没有它，上面那条就可能钉在一个早已不渲染命令的字段上——两条一起绿，
        而屏幕上仍然没有那条 `/job-apply`。
        """
        src = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        self.assertIn("<Cmd>{job.nextStep.command}</Cmd>", src,
                      "「下一步」那行不再渲染 nextStep 的命令了，"
                      "上一条断言的前提没了")


class ReactTextObeysTheWordingRules(unittest.TestCase):
    """AGENTS.md 的禁用词表原来只扫单页面板和 doctor，**从没扫过 React 界面**。"""

    def _banned(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_display_wording import BANNED_CODES, BANNED_WORDS
        return BANNED_WORDS, BANNED_CODES

    def test_no_internal_jargon_in_react_text(self):
        words, codes = self._banned()
        bad = []
        for f in tsx_files():
            for ln, txt in jsx_text_nodes(f.read_text(encoding="utf-8")):
                for w in words:
                    if w in txt:
                        bad.append(f"{f.relative_to(ROOT)}:{ln} 「{w}」 {txt.strip()[:44]}")
                for c in codes:
                    if re.search(rf"\b{c}\b", txt):
                        bad.append(f"{f.relative_to(ROOT)}:{ln} 「{c}」 {txt.strip()[:44]}")
        self.assertEqual(bad, [], "React 界面上出现内部词：\n" + "\n".join(bad))

    #: 属性里的文案同样会被用户读到：`title` 是悬停提示、`aria-label` 是屏读器念的、
    #: `tooltips` 是复制按钮的两态提示。`jsx_text_nodes` 只取**文本节点**，看不见它们。
    ATTR_NAMES = ("title", "aria-label", "alt", "placeholder")

    #: 对象属性写法（`copyable={{ tooltips: [...] }}`），不是 JSX 属性，单独取。
    OBJ_COPY = re.compile(r"\b(tooltips|label)\s*:\s*(\[[^\]]*\]|[`\"'][^`\"']*[`\"'])")

    @staticmethod
    def _literals(expr: str):
        """表达式里的所有字符串字面量。

        取值不能只认 `attr="字面量"`：这一页大量属性是**三元**
        （`title={mine ? "放回可以投的岗位" : "这条是规则判的…"}`），
        两个分支都会上屏。第一版正则只认紧跟引号的那种，于是这些一条都没扫到——
        突变（往 `title` 里塞一个内部词）当场证明它是空转的。
        """
        return re.findall(r"[`\"']([^`\"'\n]*)[`\"']", expr or "")

    def _attr_strings(self):
        for f in tsx_files():
            s = f.read_text(encoding="utf-8")
            s = re.sub(r"\{/\*.*?\*/\}", " ", s, flags=re.S)
            s = "\n".join(l for l in s.splitlines() if not l.strip().startswith("//"))
            seen = set()
            for tag in jsx_open_tags(s, r"[A-Za-z][\w.]*"):
                for name in self.ATTR_NAMES:
                    expr = attr_expr(tag, name)
                    if expr is None:
                        m = re.search(rf'\b{name}\s*=\s*"([^"]*)"', tag)
                        expr = m.group(1) if m else None
                        vals = [expr] if expr else []
                    else:
                        vals = self._literals(expr)
                    for v in vals:
                        v = (v or "").strip()
                        if v and re.search(r"[一-鿿]", v) and (name, v) not in seen:
                            seen.add((name, v))
                            yield f, s[:s.index(tag)].count("\n") + 1, v
            for m in self.OBJ_COPY.finditer(s):
                for v in self._literals(m.group(2)):
                    v = v.strip()
                    if v and re.search(r"[一-鿿]", v) and ("obj", v) not in seen:
                        seen.add(("obj", v))
                        yield f, s[:m.start()].count("\n") + 1, v

    def test_the_attribute_scan_finds_something(self):
        """控制用例：属性里确实有中文文案，下面那条才不是空跑。"""
        self.assertTrue(list(self._attr_strings()),
                        "一条属性文案都没扫到？那下面那条永远绿")

    def test_attribute_copy_obeys_the_same_rules(self):
        """悬停提示、屏读器名、复制按钮的两态提示 —— 都是用户读到的字。

        禁用词表原来只扫 JSX 的**文本节点**。而「放回可以投的岗位」这类话写在
        `title=` 里，「复制 /job-apply」写在 `tooltips` 里，同样上屏，却一直没人扫。
        """
        words, codes = self._banned()
        bad = []
        for f, ln, txt in self._attr_strings():
            for w in words:
                if w in txt:
                    bad.append(f"{f.name}:{ln} 内部词「{w}」 {txt[:44]}")
            for c in codes:
                if re.search(rf"\b{c}\b", txt):
                    bad.append(f"{f.name}:{ln} 英文码「{c}」 {txt[:44]}")
            if re.search(r"\*\*[^*\n]+\*\*", txt):
                bad.append(f"{f.name}:{ln} markdown 粗体 {txt[:44]}")
        self.assertEqual(bad, [], "属性里的文案违规：\n  " + "\n  ".join(bad))

    #: 具体的 AI 工具名。面板由 Python 生成、给**任何**工具的用户看
    #: （`AGENTS.md` 开宗明义：任何 AI 编码工具都从那里进入），所以叫人去干活时
    #: 只说「命令行」。这份是**黑名单**，不是「本仓库支持哪几家」的名单 ——
    #: 已经停掉的 Gemini CLI 也留在里面：面板上点名一个用户没有的东西这件事，
    #: 不因为那家停了就变得可以。当前支持哪几家，正本在 `docs/tool-entries.md`。
    TOOL_NAMES = ("Claude Code", "Codex", "Gemini CLI", "Cursor",
                  "Qwen", "MiMo", "Antigravity", "Qoder")

    def test_instructions_do_not_name_one_specific_ai_tool(self):
        """「回命令行里跑」，不是「回某某工具里跑」。

        实测：面板用「命令行」泛指了 16 处，**只有一处**点名——
        「回 Claude Code 里跑」。用别的工具的人读到那句，被指去用一个他没有的东西。

        只扫 JSX **文本节点**：`ResumeRead` 的悬浮说明里出现过 `Cursor`，那是在举
        「你写『AI 编码工具』、JD 写『Cursor』」的例子——它是 JD 里的词，不是叫人
        去用那个工具。判据要分得开这两种。
        """
        bad = []
        for f in tsx_files():
            for ln, txt in jsx_text_nodes(f.read_text(encoding="utf-8")):
                for name in self.TOOL_NAMES:
                    if name in txt:
                        bad.append(f"{f.name}:{ln} 「{name}」 {txt.strip()[:44]}")
        self.assertEqual(
            bad, [],
            "面板上点名了具体的 AI 工具：\n  " + "\n  ".join(bad)
            + "\n这一页给任何工具的用户看，叫人去干活时说「命令行」")

    def test_the_panel_does_say_command_line_somewhere(self):
        """控制用例：它确实用「命令行」在指路，上面那条才不是「干脆什么都不说」。"""
        n = sum(1 for f in tsx_files()
                for _, t in jsx_text_nodes(f.read_text(encoding="utf-8"))
                if "命令行" in t)
        self.assertTrue(n, "面板一处都没提「命令行」——那用户不知道去哪儿干活")

    def test_no_stray_english_inside_chinese_sentences(self):
        """实测漏过：「相邻域、business 语言能迁移」——框架原文是「业务语言」。

        命令名（/job-apply）、文件名（README.md）、工具名（pdftotext）不算——那些是
        用户要认要敲的标识符，不是没翻译的行话。
        """
        allow = {"AI", "PDF", "JD", "HR", "SAAS", "API", "CLAUDE", "CODE", "GITHUB",
                 "GMAIL", "NOTION", "TYPST", "CLI", "URL", "JSON", "CSV", "HTML",
                 "BD", "PM", "PROMPT", "WORKFLOW", "ATS", "OK", "STAR", "MCP",
                 "AGENT", "SKILLS", "LLM",
                 # 浏览器/产品名，与 GMAIL、NOTION 同类。这里必须点名而不是写
                 # 「浏览器」：要的是**那个登录着的 Chrome**，换一个浏览器就没有登录态。
                 "CHROME",
                 # 键盘按键：用户要**实际按下**的东西，跟命令名同一类标识符，
                 # 不是没翻译的行话（「按 Ctrl+C 停掉」——翻译成中文反而没人看懂）。
                 "CTRL",
                 # 手机端应用：用户和 AGENTS.md 都是这么说的（「要开 APP」）。
                 "APP",
                 "IP"}
        bad = []
        for f in tsx_files():
            for ln, txt in jsx_text_nodes(f.read_text(encoding="utf-8")):
                if not re.search(r"[一-鿿]", txt):
                    continue
                # 斜杠命令与它的参数是**用户要敲的东西**，不是没翻译的行话
                # （`/job-user --new 名字`、`/job-apply <链接>`）。先把命令整体摘掉再扫，
                # 否则会把「该敲什么」这类最有用的引导判成违规。
                clean = re.sub(r"/[a-z-]+(?:\s+--?[a-z-]+)*", " ", txt)
                # 参数还要**单独摘一次**：`${formatCommand("/job-apply")} --stale` 这种
                # 写法里，插值会先被换成空格，`--stale` 就孤零零留在中文句子中间，
                # 看着像一个没翻译的英文词——而它恰恰是用户要照敲的那个旗标。
                # 只认带前导横线的，所以「business」这类真正的行话照样会被抓到。
                clean = re.sub(r"--?[a-z][a-z-]*", " ", clean)
                for w in re.findall(r"[A-Za-z]{2,}", clean):
                    if w.upper() in allow:
                        continue
                    bad.append(f"{f.relative_to(ROOT)}:{ln} 「{w}」 {txt.strip()[:44]}")
        self.assertEqual(bad, [], "中文句子里夹着未解释的英文词：\n" + "\n".join(bad))


class FooterAndRowHintCannotDisagree(unittest.TestCase):
    """两处都必须从同一个 `hasServer()` 取值，否则又会出现一处真一处假。"""

    def test_both_derive_from_has_server(self):
        for name in ("App.tsx", "components/JobReadout.tsx"):
            src = (SRC / name).read_text(encoding="utf-8")
            self.assertRegex(
                src, r"hasServer\b",
                f"{name} 没有引用 hasServer —— 模式判断会和另一处对不上")



class PunctuationNeverStartsALine(unittest.TestCase):
    """命令块后面不许直接跟中文标点 —— 那个标点会被甩到行首。

    `<Cmd>` 渲染出来是 inline-block。浏览器按 UAX-14 做的「避头点」只在
    **连续文本**里生效，跨不过一个 inline-block 边界：换行一旦落在 `</Cmd>`
    和后面那个文本节点之间，那个逗号就单独站在下一行的开头。

    实测 2026-08-26（本机 Chrome 无头，390px）：

        …直接再跑一次 [python tools/serve.py ⧉]
        ，它会告诉你怎么停掉旧的那个。

    修法不是加 CSS，是**让命令块当这句话的最后一样东西** —— 同一段里另外
    两条（存档那条、job-rank 那条）本来就是这么写的，改完三条一致。
    """

    #: 会被甩到行首的那几个。西文标点不在内：它们前面通常有空格，断得开。
    LEADING = "，。；：、）」！？…"
    #: `</Cmd>` 与正文之间允许出现的过场字符（空白，以及 JSX 的花括号、引号）。
    SKIP = {chr(32), chr(9), chr(10), chr(13), chr(123), chr(125), chr(34), chr(39), chr(96)}

    def test_no_cmd_is_followed_by_punctuation(self):
        bad = []
        for f in sorted((ROOT / "web" / "src").rglob("*.tsx")):
            src = f.read_text(encoding="utf-8")
            at = src.find("</Cmd>")
            while at != -1:
                k = at + len("</Cmd>")
                while k < len(src) and src[k] in self.SKIP:
                    k += 1
                if k < len(src) and src[k] in self.LEADING:
                    line = src[:at].count(chr(10)) + 1
                    bad.append(f"{f.name}:{line} </Cmd> 后面跟着「{src[k]}」")
                at = src.find("</Cmd>", k)
        self.assertEqual(
            bad, [], "命令块后面跟了中文标点，换行时它会落在行首："
            + chr(10) + "  " + (chr(10) + "  ").join(bad))

if __name__ == "__main__":
    unittest.main()


class ExpandingARowKeepsItInView(unittest.TestCase):
    """单开手风琴必须在展开后把那一行滚回视口，否则点第二个岗会「跳到别处」。

    受控单开的必然副作用：点第二个岗时**先收起前一个**再展开新的。前一个如果很高
    （材料齐全的岗带话术、硬性条件、评分明细、面试记录，轻松两千像素），收起的
    瞬间整页塌陷，而浏览器不会替你调整滚动位置——用户盯着的地方突然变成别处，
    看到的不是刚点的那个岗。**岗位资料越完整，这个 bug 越明显**，正好惩罚了
    准备最充分的那个岗。

    两个实现要点也一并钉住，它们都不是可选的：
      1. 等一帧再滚（rAF）——收起+展开是同一次渲染里的两处高度变化，提交前量出来
         的位置是旧的
      2. 尊重 prefers-reduced-motion——前庭敏感的人被一段平滑滚动带走会难受
    """

    SRC = ROOT / "web" / "src" / "components" / "Shortlist.tsx"

    def test_it_scrolls_after_expanding(self):
        s = self.SRC.read_text(encoding="utf-8")
        self.assertIn("scrollTo", s, "展开后没有把那一行滚回视口")
        self.assertIn("requestAnimationFrame", s,
                      "没等 DOM 提交就量位置——收起造成的高度塌陷还没发生，量到的是旧值")

    def test_it_waits_for_the_committed_layout(self):
        """rAF 回调里才读位置；在 effect 同步体里读等于读旧布局。"""
        s = self.SRC.read_text(encoding="utf-8")
        i = s.index("requestAnimationFrame")
        j = s.index("getBoundingClientRect")
        self.assertLess(i, j, "位置是在 rAF 之外量的")

    def test_reduced_motion_is_respected(self):
        s = self.SRC.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", s,
                      "平滑滚动没给前庭敏感的用户留出口")

    def test_collapsing_does_not_scroll(self):
        """收起是原地收起，视线本来就在那——再滚一次是无端把人带走。"""
        s = self.SRC.read_text(encoding="utf-8")
        seg = s[s.index("useEffect(() => {"):s.index("}, [selectedId]);")]
        self.assertIn("if (!selectedId) return", seg,
                      "收起时也触发了滚动")

    def test_the_row_is_not_pinned_to_pixel_zero(self):
        """顶死在 0 像素会把行上沿的标记切掉，看不出点的是哪一行。"""
        s = self.SRC.read_text(encoding="utf-8")
        self.assertNotIn('block: "start"', s,
                         "scrollIntoView({block:'start'}) 会把行顶死在视口顶端")
        self.assertRegex(s, r"window\.scrollY\s*-\s*\d+",
                         "没有为顶部留出偏移")


class TheAccentIsNotSpentOnFootnotes(unittest.TestCase):
    """主强调色只给「要你看的那个数」，不给脚注。

    `--data`（青）是全页的主强调：漏斗数字、下一步、段计数、技能列都在用它。
    而「同一个岗挂在多处」是一条**中性脚注**——原来它也用 `--data` 加描边，
    结果实测比它注解的公司名还宽 2.3 倍（90px vs 39px），二级信息压过主体。

    这条规则不好全站机械化（哪些算脚注要判断），所以只钉住已经判过的那几个类：
    它们是**注解**，不是数据本身。

    > 顺带记一条**没有**做成规则的：一度想加「一个段落里加粗不超过 N 处」。
    > 扫下来 9 处命中，但大多是**并列强调**——「**技能**高于总分…；**技能**低于
    > 总分…」是同一个词构成对照，「评过 **N** 个岗里 **M** 个」是成对的数据点。
    > 按数量判会把这些正当写法一起报掉。真正要判的是「这几处在互相竞争，
    > 还是在构成对照」，那不是数量能回答的。**能机械化的才做成规则。**
    """

    #: 这些类是对主体内容的注解，不是主体本身
    FOOTNOTE_CLASSES = ["dup-chip", "annual-plus"]

    def test_footnote_classes_do_not_use_the_primary_accent(self):
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
        bad = []
        for cls in self.FOOTNOTE_CLASSES:
            m = re.search(rf"^\.{re.escape(cls)}\s*\{{(.*?)\}}", css, re.S | re.M)
            if not m:
                bad.append(f".{cls} 这个类不见了")
                continue
            body = m.group(1)
            if re.search(r"color:\s*var\(--data\)", body):
                bad.append(f".{cls} 用了主强调色 --data —— 那是给数据本身的")
        self.assertEqual(bad, [],
                         "脚注用了主强调色，会盖过它注解的内容：\n" + "\n".join(bad))

    def test_the_duplicate_marker_stays_shorter_than_what_it_annotates(self):
        """脚注比被注解的东西还长，就不是脚注了。

        判的是**字数**（渲染宽度测不了静态文件）：公司名短的能到两三个字，
        脚注控制在 6 个字以内才不会压过去。完整说明留在 tooltip 里。
        """
        s = (ROOT / "web" / "src" / "components" / "Shortlist.tsx"
             ).read_text(encoding="utf-8")
        m = re.search(r'className="dup-chip">(.*?)</span>', s, re.S)
        self.assertIsNotNone(m, "dup-chip 不见了")
        text = re.sub(r"\{[^{}]*\}", "N", m.group(1)).strip()
        self.assertLessEqual(len(text), 8,
                             f"脚注「{text}」太长了（{len(text)} 字）——"
                             "完整说明放 tooltip，芯片上只留最短的那句")

    def test_the_full_explanation_is_still_available(self):
        """收短不等于删掉——tooltip 里必须还说得清是怎么回事。"""
        s = (ROOT / "web" / "src" / "components" / "Shortlist.tsx"
             ).read_text(encoding="utf-8")
        self.assertIn("这个岗还挂在另外", s, "tooltip 里的完整说明没了")


class OneActionKeepsOneName(unittest.TestCase):
    """同一个动作在流程里只能有一个名字。

    按钮叫「不投这个岗」，说明里却又叫「隐藏」、又叫「排除」——三个词指同一件事，
    用户得自己对上号。而这段文案正是被当场问出来过的那一段（「点了先在本页隐藏……
    这句话是什么意思？」）：当时修的是模式判断（有服务时那句话是假的），
    **措辞漂移一直没动**。

    这条和「内部词不上屏」是两回事：「隐藏」「排除」都是人话，问题在于**它们和
    按钮不是同一个词**。界面的词汇表就是用户的导航牌，同物异名等于把牌子改了。
    """

    #: 一个动作 → 它在界面上唯一的叫法 + 不许同时出现的同义词
    ACTIONS = {
        "不投": ["排除", "隐藏", "剔除"],
    }

    def _chrome(self) -> str:
        return " ".join(
            t for f in tsx_files()
            for _, t in jsx_text_nodes(f.read_text(encoding="utf-8"))
            if re.search(r"[一-鿿]", t))

    def test_no_synonym_drift_for_the_same_action(self):
        blob = self._chrome()
        bad = []
        for canonical, synonyms in self.ACTIONS.items():
            if canonical not in blob:
                continue
            for s in synonyms:
                if s in blob:
                    bad.append(f"「{canonical}」这个动作又被叫成「{s}」")
        self.assertEqual(bad, [],
                         "同一个动作有多个名字，用户得自己对上号：\n" + "\n".join(bad))

    def test_the_canonical_name_is_the_one_on_the_button(self):
        """规范名不能是我随口定的——它必须就是按钮上那个词。"""
        src = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        m = re.search(r'className="act-drop"[^>]*>\s*(.+?)\s*</Button>', src, re.S)
        self.assertIsNotNone(m, "找不到那个按钮")
        self.assertIn("不投", m.group(1), f"按钮文字是「{m.group(1)}」，与规范名对不上")


class NoFrameworkProcessWordsOnScreen(unittest.TestCase):
    """「粗筛」「深评」是流程内部的两档评估深度，不是用户要学的词。

    列表里原来印一个裸标记「已深评」，没有任何解释——用户得先学会这个词，
    才知道这一行和别的行差在哪。换成它**实际做过的事**：读过 JD。

    这两个词不在 `BANNED_WORDS` 里（那张表管的是「驾驶舱」「台账」这类），
    但同一条原则：**要提某个能力就说它做的事**。
    """

    PROCESS_WORDS = ["粗筛", "深评", "预筛"]

    def test_they_do_not_reach_the_screen(self):
        bad = []
        for f in tsx_files():
            for ln, txt in jsx_text_nodes(f.read_text(encoding="utf-8")):
                for w in self.PROCESS_WORDS:
                    if w in txt:
                        bad.append(f"{f.name}:{ln} 「{w}」 {txt.strip()[:40]}")
        self.assertEqual(bad, [],
                         "流程内部词印到屏幕上了——说它做的事，别让用户学这套词：\n"
                         + "\n".join(bad))

    def test_the_replacement_says_what_was_actually_done(self):
        """换掉不等于删掉——那一档到底做了什么，得说出来。"""
        s = (SRC / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        self.assertIn("读过 JD", s, "深评那一档没有用户能懂的说法")
        self.assertIn("只按列表卡片上的信息评的", s,
                      "没说清另一档差在哪 —— 只说「读过 JD」不构成对比")

    def test_data_side_stripping_still_works(self):
        """判词里带的「粗筛：」前缀是**数据**（`/job-rank` 写进去的），
        显示前要剥掉——这是另一回事，不能因为改文案把它删了。"""
        s = (SRC / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        self.assertIn(r'replace(/^粗筛[：:]\s*/', s,
                      "判词的「粗筛：」前缀不剥了，那个词会从数据侧漏上屏")


class WarningsOnlyShowWhenThereIsSomethingToWarnAbout(unittest.TestCase):
    """一条永远显示的提醒，等于没有提醒。

    「有一条不满足就别投 ·「还没查到」不算满足」原来**无条件**显示在硬性条件那一栏。
    7 条全过、0 条待确认时，它在提醒一个不存在的情况。

    框架自己论证过这个形状——竞业限制那一节：「用一条永远为真的提醒污染每一份评估，
    而它对 99% 的岗位没有任何判别力」。同一条原则，同一个仓库，界面这边没照做。
    """

    SRC_FILE = SRC / "components" / "JobReadout.tsx"

    def test_the_gate_warning_is_conditional(self):
        s = self.SRC_FILE.read_text(encoding="utf-8")
        i = s.index("有一条不满足就别投")
        head = s[max(0, i - 400):i]
        self.assertIn("job.gates.some", head,
                      "那句提醒还是无条件显示——没有可留意的条目时它是噪音")

    def test_not_applicable_gates_do_not_trigger_it(self):
        """`na`（不适用）**不是**「要留意」，而它很常见——把它算进去，
        条件就等于永远为真，改了跟没改一样。

        第一版写的是 `g.state !== "pass"`，实测一个 7 条全过的岗照样触发
        （户口那条是 `na`）。自己验一遍才发现。
        """
        s = self.SRC_FILE.read_text(encoding="utf-8")
        i = s.index("有一条不满足就别投")
        head = s[max(0, i - 400):i]
        self.assertNotIn('g.state !== "pass"', head,
                         "条件把「不适用」也算成要留意，等于永远为真")
        self.assertIn('"fail"', head, '条件里没判 "fail"')
        # 「还没查到」那一半 2026-08-31 收进了 `GateStamp.countsAsUnknown`
        # —— 它原来在三处各写一遍（这里、`unknowns` 那行、`GateGrid` 的计数）。
        # **判据跟着从字面改成路由**：钉 `"unknown"` 这个字面等于钉实现位置，
        # 收掉重复时它会把收拢本身判成违规，而这条真正守的两件事一个字没变
        # ——「na 不算要留意」由上面那条 assertNotIn 守着，「还没查到要算」
        # 由下面这条守着。
        self.assertIn("countsAsUnknown", head, "条件里没判「还没查到」")


class EmptySectionsSayTheyAreEmpty(unittest.TestCase):
    """带标题的空盒子比没有盒子更糟——读的人会以为没加载出来。

    最初的样子：「经历对不上的地方」这一格的副标题写着「写材料时这几处不能吹」，
    而 `job.gaps` 为空时它渲染出标题、副标题，body 一条没有——「这几处」指向的
    东西不存在。

    **改过两轮，两轮的判据都留在下面两条用例里。**

    第一轮把副标题改成「这个岗没有」，理由是「没有对不上的地方本身是个结论，
    把它说出来比留一个空盒子有用」。方向对，但只做了一半：盒子还在（一行小字
    下面 60px 空白），而右边那格 `job.quality` **一条守卫都没有**，为空时照样
    渲染出标题、「不算进分数」标签、空列表和一句解释不存在之物的脚注。

    第二轮才是现在的样子：两格各自守自己，都空就一句话带过。结论值一行，
    不值两个框。
    """

    def test_neither_slab_renders_empty(self):
        """两格各自守住自己：没内容就不渲染，而不是渲染一个带标题的空盒子。

        上一版是「盒子留着、副标题改一句话」（「这个岗没有」）。实测下来那不叫
        说出结论：左边一行小字下面 60px 空白，右边更糟——`job.quality` 为空时
        **一条守卫都没有**，照样渲染出标题、一个「不算进分数」的标签、一个空
        列表，外加一句解释屏幕上不存在的东西的脚注。
        """
        s = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        for anchor, guard in (("经历对不上的地方", "job.gaps.length > 0"),
                              ("待核实的信息", "job.quality.length > 0")):
            with self.subTest(section=anchor):
                i = s.index(f"<h3>{anchor}</h3>")
                head = s[max(0, i - 400):i]
                self.assertIn(guard, head,
                              f"「{anchor}」这一格没守卫，空的时候会渲染成空盒子")

    def test_both_empty_states_the_conclusion(self):
        """两格都空**是个结论**（这个岗没什么不能吹的、也没有要核实的），说出来。

        这与 `GateGrid` 的空数组守卫是同一条原则的反面：那边「空 ≠ 都通过」，
        这边「空 = 一个值得说的好消息」。区别在于它值一行，不值两个框。
        """
        s = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        i = s.index("job.gaps.length === 0 && job.quality.length === 0")
        seg = s[i:i + 400]
        self.assertIn("没有对不上的地方", seg, "两格都空时没说出结论")


class ReassuranceIsNotStyledAsWarning(unittest.TestCase):
    """「不算进分数」是安抚，不是警示——用警示色把信号弄反了。

    琥珀（`--caution`）在这一页只表示「要留意」。而这句话在说的恰恰是
    「这些不确定**不会**拖累这个岗的分」。读的人第一眼以为这里有风险，
    其实它在说没风险。

    与已修的 `.dup-chip` 是同一族：**语义色要跟着这句话的意思走，
    不跟着它所在的区块走**。
    """

    def test_the_not_scored_chip_is_neutral(self):
        """锚到**这句话实际拿到的颜色**，不管那个颜色写在哪。

        第一版用 460 字符回看，而我在 `className` 和 `style` 之间插的那段注释
        正好把 `color:` 挤出了窗口——变异把颜色改回警示色，测试照样绿。
        窗口大小是个会被无关编辑改变的量，别拿它当锚。

        第二版锚的是 `style=`，那是**绑在实现形状上**：2026-09-30 把这条静态样式
        从 inline style 收进 `.kicker.is-tag` 之后，它找不到锚、报的是「定位到的
        不是带样式的那个元素」——而颜色其实还是中性的那一档。判据要问的是
        「这句话是什么颜色」，不是「颜色写在哪」。所以现在两处都认：
        有内联就取内联，没有就按 class 去 cockpit.css 里找最后盖上的那条——
        这套解析住在 `jsx.element_color`，与本仓库另一条同族的证人共用一份实现
        （两份必然飘）。
        """
        raw = (SRC / "components" / "JobReadout.tsx").read_text(encoding="utf-8")
        # **先剥注释再定位**。解释这条规则的那段注释里也写着「不算进分数」，
        # 直接 index() 会命中注释里那处，然后往前找到一个毫不相干的 <span>。
        # 这个形状本轮已经踩到第六次——判据一律只看真正渲染出去的东西。
        s = re.sub(r"\{/\*.*?\*/\}", " ", raw, flags=re.S)
        css = (SRC / "theme" / "cockpit.css").read_text(encoding="utf-8")
        color = element_color(s, "不算进分数", css)
        self.assertIsNotNone(
            color,
            "这句话的着色来源找不到——判据看不见颜色就等于没在管，"
            "别让它对着空气绿下去")
        self.assertNotIn("var(--caution)", color,
                         "「不算进分数」用了警示色——那句话是安抚，信号反了")

    def test_the_data_path_is_stripped_too(self):
        """上一条只扫 JSX 文案，而「粗筛」是从**数据**里漏上屏的。

        `/job-rank` 把判词写成「粗筛：不建议」存进 `seen_jobs.json`，前缀标记这条结论
        来自哪一档评估。分数列剥了它，**搁置区没剥**——实测页面上出现 87 次。

        修法是抽成一个函数两处共用：两份实现必然飘，而飘掉的那一处没人会发现。
        """
        s = (SRC / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in s.splitlines()
                         if not ln.strip().startswith(("//", "*", "/*")))
        self.assertIn("export function plainVerdict", code,
                      "剥前缀没有抽成共用函数")
        # 只能有一处正则实现 —— **整棵 web/src 只有一处，不是「这个文件里只有一处」**。
        #
        # 这条判据原来只数 `Shortlist.tsx`，而 `App.tsx` 里另写了一份
        # `plainV`（同一个正则，多一个 `.trim()`），从它旁边走了过去 ——
        # 上面那句「两份实现必然飘」当时已经应验：`plainVerdict` 没 trim，
        # 而它正被用在 `plainVerdict(j.verdict) === "可以考虑"` 这种等值比较上。
        # **守卫的范围窄，等于给第二份实现留了一个它够不着的住址。**
        homes = {f.relative_to(SRC).as_posix(): t.count("replace(/^粗筛")
                 for f in SRC.rglob("*.ts*")
                 for t in [f.read_text(encoding="utf-8")]
                 if t.count("replace(/^粗筛")}
        self.assertEqual(
            sum(homes.values()), 1,
            "剥前缀有不止一份实现——两份必然飘。住址：" + repr(homes))
        self.assertEqual(list(homes), ["components/Shortlist.tsx"],
                         "唯一那份不在 plainVerdict 那里：" + repr(homes))
        # 两个用到判词的地方都得走它
        for site in ("plainVerdict(job.verdict)",
                     "plainVerdict(job.gateFailReason || job.verdict)"):
            with self.subTest(site=site[:34]):
                self.assertIn(site, code, f"这一处没走 plainVerdict：{site}")

    def test_the_helper_actually_strips(self):
        """判据自检：函数体里那个正则要真能把两种冒号都剥掉。"""
        s = (SRC / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        i = s.index("export function plainVerdict")
        body = s[i:i + 260]
        self.assertIn("[：:]", body, "只剥了一种冒号——数据里两种都出现过")


class MissingDataNeverSortsAsLowest(unittest.TestCase):
    """「没这个数」不是「最低」。

    三列的排序器原来都写 `(a.x ?? -1) - (b.x ?? -1)`——按年包升序时，一个平台
    没写薪资的岗排在最前面，读起来就是「这个最便宜」。而这一页别处（硬性条件的
    四态、`salaryMonthsUnknown`）一直把「没查到」和「不合格」分得很清楚，
    唯独排序把它们折在了一起。

    正确的行为是**两个方向都沉底**。antd 会把降序的比较结果取反，所以 null 那两支
    要乘上 flip 抵消掉。

    这里只能验源码，不能验行为：`web/` 没有 JS 测试框架（见本文件开头）。
    在 Python 里把 `nullsLast` 的语义复述一遍也不行——那就成了「我抄对了没有」。
    所以退一步验两件**改坏就一定破**的结构：每一列都走同一个比较器，
    以及那个比较器确实读了排序方向。真实行为在浏览器里实测过：
    升序末位与降序末位都是「—」。
    """

    SRC_FILE = SRC / "components" / "Shortlist.tsx"

    def test_every_sorter_goes_through_the_shared_comparator(self):
        src = self.SRC_FILE.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        sorters = re.findall(r"sorter:\s*(.+?),\n", code)
        self.assertTrue(sorters, "一个 sorter 都没找到——列定义改形状了？")
        for s in sorters:
            with self.subTest(s.strip()[:40]):
                self.assertIn("nullsLast", s,
                              f"这一列没走 nullsLast：{s.strip()!r} —— "
                              "`?? -1` 会把「没这个数」排成「最低」")

    def test_the_comparator_flips_for_descending(self):
        """null 那两支必须带方向修正，否则降序时它们会跑到最前面。"""
        src = self.SRC_FILE.read_text(encoding="utf-8")
        i = src.index("function nullsLast")
        body = src[i:src.index("\n}", i)]
        self.assertIn('order === "descend" ? -1 : 1', body,
                      "没读排序方向 —— antd 会把降序结果取反，null 就翻到最前面了")
        self.assertRegex(body, r"if \(x == null\) return flip;",
                         "x 为空时没带方向修正")
        self.assertRegex(body, r"if \(y == null\) return -flip;",
                         "y 为空时没带方向修正")


class EveryCopyButtonSaysWhatItCopies(unittest.TestCase):
    """23 个复制按钮，无障碍名全叫「复制」。

    实测：整页 23 个 `copyable` 按钮，`aria-label` 一律是「复制」。读屏用户 Tab
    过去听到二十三遍「复制」，不知道任何一个复制的是什么——而这一页的全部价值
    就在于「该敲哪条命令」，那些按钮恰恰是它的出口。

    antd 把 `tooltips[0]` 同时当作按钮的 `aria-label`，所以名字里带上要复制的
    东西，鼠标提示和读屏播报一起就都对了。

    做法是收进 `components/Cmd.tsx` 一个组件：**这条规则要成立，就不能再有人
    在别处直接写 `copyable`**。原来那行配置在 8 个文件里抄了 19 遍，改一次提示语
    要改 19 处，漏一处就不一致——这条同时把那份重复钉死。
    """

    HOME = SRC / "components" / "Cmd.tsx"

    def test_only_one_file_configures_copyable(self):
        offenders = []
        for f in sorted(SRC.rglob("*.tsx")):
            if f == self.HOME:
                continue
            src = re.sub(r"\{/\*.*?\*/\}", "", f.read_text(encoding="utf-8"), flags=re.S)
            src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
            for m in re.finditer(r"copyable=", src):
                offenders.append(f"{f.name}:{src[:m.start()].count(chr(10)) + 1}")
        self.assertEqual(
            offenders, [],
            "直接写 copyable 的地方，复制按钮的无障碍名会退回默认的「复制」——"
            "读屏那边就分不出它复制的是什么。改用 <Cmd>／<CopyIcon>：\n"
            + "\n".join(offenders))

    def test_the_name_carries_the_thing_being_copied(self):
        """光收进一个组件不够，那个组件得真把内容拼进名字里。"""
        src = self.HOME.read_text(encoding="utf-8")
        # 名字里必须是**实际复制到剪贴板**的那条（formatted），不是正本 children：
        # 免斜杠模式下显示/复制的都是 job-auto，提示写 /job-auto 就是骗读屏。
        self.assertRegex(
            src, r"const formatted = formatCommand\(children\)",
            "Cmd 没先按宿主工具把命令适配成 formatted")
        self.assertRegex(
            src, r"tooltips:\s*\[\s*`复制 \$\{formatted\}`",
            "Cmd 没把实际复制的命令拼进 tooltips[0] —— antd 拿它当 aria-label，"
            "不拼就还是二十三个「复制」")
        self.assertRegex(
            src, r"tooltips:\s*\[\s*`复制\$\{what\}`",
            "CopyIcon 没说清复制的是什么 —— 它连可见文字都没有")


class ADisabledControlPromisesNothing(unittest.TestCase):
    """按不动的控件，无障碍名里不许出现它做不了的动作。

    流水线那五格是 `<button>`。原来 `disabled` 算的是「没有筛选键**或**数为 0」，
    而 aria-label 只看有没有筛选键——于是「已投递：0 个」「面试中：0 个」这两格
    是禁用的，读屏却念「0 个，只看这些」。看得见的人看到灰掉的格子就明白了，
    只听声音的人拿到的是一个按不动的承诺。

    验的是**两个条件必须是同一个表达式**，不是验今天这个拼法：只要有人再把
    「能不能点」和「说不说得出口」分成两处算，这条就红。
    """

    @staticmethod
    def _norm(expr: str) -> str:
        """去掉外层的 `!` 与空白——`!actionable` 和 `actionable` 算同一个条件。"""
        return re.sub(r"\s+", " ", expr).strip().lstrip("!").strip()

    @staticmethod
    def _ternary_cond(expr: str):
        """`X ? A : B` 的 X；不是三元就返回 None。

        跳过 `?.` 与 `??`——那两个不是三元的问号，认错了会把条件截在半截。
        """
        m = re.match(r"(.*?)(?<!\?)\?(?!\.|\?)", expr, re.S)
        return m.group(1).strip() if m else None

    def _pairs(self):
        """产出 (文件, 元素文本, disabled 条件, label 条件)——两者都写了才算。"""
        for f in sorted(SRC.rglob("*.tsx")):
            src = f.read_text(encoding="utf-8")
            for el in jsx_open_tags(src, "button"):
                dis = attr_expr(el, "disabled")
                lab = attr_expr(el, "aria-label")
                cond = self._ternary_cond(lab) if lab else None
                if dis and cond:
                    yield f.name, el, dis, cond

    def test_disabled_and_the_label_share_one_condition(self):
        bad = []
        for name, el, dis, lab in self._pairs():
            if self._norm(dis) != self._norm(lab):
                head = re.search(r'className="([^"]+)"', el)
                bad.append(f"{name} 的 <button class={head.group(1) if head else '?'}>："
                           f"能不能点算的是 {dis!r}，无障碍名分支算的是 {lab!r}")
        self.assertEqual(
            bad, [],
            "禁用条件和无障碍名的分支条件不是同一个——按不动的控件会念出它做不了"
            "的动作，而看得见的人从灰掉的样子就知道了，只有读屏用户被骗：\n"
            + "\n".join(bad))

    def test_there_is_something_to_check(self):
        """判据自检：真扫到了带这两个属性的按钮，不是空跑一遍报绿。"""
        self.assertTrue(list(self._pairs()),
                        "一个同时写了 disabled 与条件式 aria-label 的按钮都没扫到——"
                        "要么标签扫描坏了，要么这条已经无源可验")

    def test_the_tag_scanner_survives_braces_and_gt_in_attributes(self):
        """判据自检：属性里带 `{}`、模板串、以及 **`>`** 时不能把开标签截断。

        `data-state={s.count > 0 ? …}` 里那个 `>` 正是 `<button[^>]*>` 的死穴——
        截出来的片段里没有 `disabled=`，于是「验到了」和「什么都没验到」
        看起来一模一样。`test_pipeline_counts` 就是这么栽的。
        """
        sample = ('<button\n  disabled={!ok}\n'
                  '  data-state={n > 0 ? "on" : "off"}\n'
                  '  aria-label={ok ? `有 ${n} 个` : "没有"}\n>文字</button>')
        tags = list(jsx_open_tags(sample, "button"))
        self.assertEqual(len(tags), 1)
        self.assertIn("aria-label", tags[0], "开标签被属性里的 > 或大括号截断了")
        self.assertNotIn("文字", tags[0], "扫过头了，把子节点也吞了")
        self.assertEqual(attr_expr(tags[0], "disabled"), "!ok")
        self.assertEqual(attr_expr(tags[0], "aria-label"),
                         'ok ? `有 ${n} 个` : "没有"')
        self.assertIsNone(attr_expr(tags[0], "onClick"), "没写的属性该返回 None")

    def test_optional_chaining_is_not_mistaken_for_a_ternary(self):
        """判据自检：`?.` 和 `??` 不是三元的问号，认错了条件会被截在半截。"""
        self.assertEqual(self._ternary_cond('a?.b ? "x" : "y"'), "a?.b")
        self.assertEqual(self._ternary_cond('(a ?? b) ? "x" : "y"'), "(a ?? b)")
        self.assertIsNone(self._ternary_cond('"就一句话"'))


class FilteringCollapsesAnOffscreenSelection(unittest.TestCase):
    """搜索把展开的那一行筛掉时要收起它。

    `App` 的 `effectiveId` 只挡住「这个岗离开了可投名单」（记了状态、标了不投），
    **挡不住 `Shortlist` 内部的搜索筛选**——那发生在 `jobsIn` 上，App 看不见。

    于是：展开一个岗 → 搜一个搜不到它的词 → 行没了、展开态还在，
    滚动效果的 `querySelector` 找不到那一行，静默返回（不崩）。
    清掉搜索之后会看到一个自己没再点过的岗还开着，而用户无从知道它是哪一步留下的。
    """

    def test_shortlist_clears_selection_when_filtered_out(self):
        src = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        self.assertIn("jobsIn.some((j) => j.id === selectedId)", src,
                      "筛选变化时没有检查展开的那一行还在不在")
        self.assertIn('onSelect("")', src, "筛掉之后没有收起")

    def test_the_effect_keys_on_filters_not_on_data(self):
        """依赖 jobsIn 会让每次数据刷新都重跑，把用户正看着的岗收起来。"""
        import re
        src = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        seg = src.split("jobsIn.some((j) => j.id === selectedId)")[1][:300]
        m = re.search(r"\}, \[([^\]]*)\]", seg)
        self.assertIsNotNone(m, "找不到这个 effect 的依赖数组")
        deps = {d.strip() for d in m.group(1).split(",") if d.strip()}
        self.assertEqual(deps, {"kw", "channel"},
                         f"依赖应当只有筛选条件，实际是 {deps}")

    def test_the_scroll_offset_explains_itself(self):
        """76 是魔数——必须写清它不是在避让 sticky 元素。"""
        src = (ROOT / "web" / "src" / "components" / "Shortlist.tsx").read_text(encoding="utf-8")
        seg = src.split("window.scrollY - 76")[0][-400:]
        self.assertIn("sticky", seg, "没交代这个偏移量是不是在避让吸顶元素")
        css = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
        self.assertNotIn("position: sticky", css,
                         "页面出现了 sticky 元素——那个 76px 的余量要重新算，"
                         "否则被点的行会被吸顶元素挡住")


class MailtoNeverSilentlyTruncates(unittest.TestCase):
    """邮件正文超长时不预填正文——Windows 上 mailto: 会**静默截断**。

    `mailto:` 在 Windows 走 ShellExecute，URL 上限约 2083 字符。超限的行为不是
    报错，是把正文截掉一段、或者整个不响应。实测（2026-08-20）9 份邮件材料
    **全部超限**（中位数 3921、最长 4367）。

    原注释只预见了「没装邮件客户端 → 无反应」，那种失败**看得见**；截断
    **看不见**——邮件正常打开、正文少一段，用户不会逐字核对就发出去了。
    所以超限时只预填主题，正文退回旁边那个复制按钮。
    """

    def _src(self):
        return (ROOT / "web" / "src" / "components" / "JobReadout.tsx").read_text(
            encoding="utf-8")

    def test_the_long_case_drops_the_body(self):
        src = self._src()
        self.assertIn("tooLong", src,
                      "mailto 又变回无条件预填正文了——超长会被静默截断")
        self.assertIn("mailto:?subject=${subj}`", src,
                      "超长分支必须只带 subject，不带 body")

    def test_the_copy_button_is_the_fallback(self):
        """降级后正文只剩复制这一条路，那个按钮不能省。"""
        self.assertIn('what="邮件正文"', self._src(),
                      "邮件正文的复制按钮没了——超长时用户就彻底拿不到正文")

    def test_the_ceiling_is_explained(self):
        src = self._src()
        for token in ("ShellExecute", "2083", "静默截断"):
            self.assertIn(token, src,
                          f"注释里没写 {token}——下一个人会以为 2000 是随手拍的，"
                          "顺手改大或删掉")

    def test_the_recipient_stays_empty_in_both_branches(self):
        """降级不能把安全边界一起降掉：两条分支都必须 `mailto:?` 开头。

        AGENTS.md 全局铁律——收件人绝不由工具从 JD 里挑。
        """
        src = self._src()
        self.assertNotIn("mailto:${", src, "收件人被插值了")
        # 只数**模板构造点**（反引号 + `mailto:?subject=`）。上面那段注释里也写着
        # `mailto:?`，把它算进来就是守卫误伤自己人——同 `norm_url` 那条守卫栽过的坑。
        self.assertEqual(src.count("`mailto:?subject="), 2,
                         "mailto 分支数变了——两条都得是空收件人")

    def test_the_branch_is_actually_reachable(self):
        """控制测试：真实材料里确实有超过阈值的，否则这守卫是空转。"""
        import json
        import urllib.parse
        f = ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            self.skipTest("还没导出过面板数据")
        lens = []
        for j in json.loads(f.read_text(encoding="utf-8")).get("jobs", []):
            m = j.get("materials") or {}
            if m.get("emailBody"):
                lens.append(len("mailto:?subject="
                                + urllib.parse.quote(m.get("emailSubject") or "")
                                + "&body=" + urllib.parse.quote(m["emailBody"])))
        if not lens:
            self.skipTest("还没有带邮件正文的材料")
        self.assertGreater(max(lens), 2000,
                           "没有一份材料超过阈值——要么阈值定错了，要么这守卫在空转")


class EmptyStatesDoNotInventFacts(unittest.TestCase):
    """两个维度空状态说过它们不知道的事（2026-08-20 拿全库 238 个已评岗验出来）。

    ① **「四项」是写死的，而维度数不是常数**：132 个岗四维、**106 个岗五维**
       （多一项「地点（当前/搬迁）」）。对那 106 个，「四项都不拖后腿」少数了一项。

    ② **全都没打分 ≠ 没有加分项**：1 个岗四维全空，却被告知
       「没有明显加分项——分数主要靠没踩雷撑着」。那句话把「还没评」讲成
       「评过，平平」。同一页别处（硬性条件四态、`salaryMonthsUnknown`、
       `nullsLast`）一直把这两件事分得很清楚，唯独这里折在一起——
       和 `MissingDataNeverSortsAsLowest` 是同一条原则的第二个落点。

    `hasDetail` 挡不住 ②：它只挡「三者全空」，四维在、分全是 null 时照样渲染。
    """

    SRC_FILE = SRC / "components" / "JobReadout.tsx"

    def _src(self):
        return self.SRC_FILE.read_text(encoding="utf-8")

    def test_the_count_is_not_hardcoded(self):
        src = self._src()
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        self.assertNotIn("四项都不拖后腿", code,
                         "维度个数又被写死了——真实数据里四维、五维都有")
        # **数的是「两栏里那几项」，不是原始行数。** 评分明细表里可能混进
        # 一行不计权的「地点」（Pass/Fail 的门，见 `_cli.WEIGHTED_DIMS`），
        # 它已经不进这两栏了 —— 再用 `job.dimensions.length` 就会多数一个。
        self.assertIn("这 {plus.length + minus.length} 项都不拖后腿", code,
                      "空状态没有读真实维度数（且要排掉不计权的那行）")

    #: 「全都没打分」与「没有加分项」分成两支 —— 这条判据**原来在这里也有一份**
    #: （`test_all_unscored_is_told_apart_from_no_strengths`），与正本逐字相同：
    #: 同一个 JS 表达式、同一句文案，两处各钉一遍。正本是
    #: `test_a_passfail_gate_is_not_a_weak_dimension` —— 那个文件整篇就是这件事，
    #: 还多钉了「旧那个恒为真的等式不许回来」和「两句空状态文案都要在」。
    #: 2026-08-31 删掉这一份。下面那条**留着**：它验的是另一件事 ——真实语料里
    #: 两支都还有实例，也就是这条规则没有变成一个假想问题。

    def test_the_real_corpus_still_contains_both_shapes(self):
        """控制测试：这两支在真实数据里都还有实例，不是修了个假想问题。

        判据本身在 `test_a_passfail_gate_is_not_a_weak_dimension`，这里不重复钉。"""
        import json
        f = ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            self.skipTest("还没导出过面板数据")
        sizes, all_null = set(), 0
        for j in json.loads(f.read_text(encoding="utf-8")).get("jobs", []):
            dims = j.get("dimensions") or []
            if not dims:
                continue
            sizes.add(len(dims))
            if all(d.get("score") is None for d in dims):
                all_null += 1
        if not sizes:
            self.skipTest("还没有评过分的岗")
        self.assertGreater(len(sizes), 1,
                           f"维度数现在只有一种（{sizes}）——若框架真定死了，"
                           "把这条守卫连同那个插值一起删掉，别留着假装动态")
        self.assertGreaterEqual(all_null, 1,
                                "没有全空的岗了——② 那支若已不可达，删掉它")
