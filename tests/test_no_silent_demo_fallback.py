"""真实数据缺一块时，不许静默退回演示值。

## 这次全面检查抓到的

`envItems`（要装的工具）**导出器根本没产出**，而界面写着 `d.envItems ?? demoEnv`
——于是面板上那句「要装的工具 **都装好了 4/4**」是假的：写死的 Node v22.9.0、
Typst 0.13.0，与这台机器上的实际情况无关（真实探测是 7 项、版本也不同）。

漏掉的直接原因是**字段名对不上**：`doctor.probe_env()` 给 `label`，界面要 `name`。
名字不同、字段又是可选的，两边就这么各活各的，谁也不报错。

而这个错**看起来像好消息**——「都装好了」。用户没有任何理由怀疑它。这正是
`export_web_data.py` 开头写的那条：虚构数据的问题不是不够真，而是它长得像真的。

## 规则

演示数据只允许出现在**整页都标着「演示数据（虚构）」**的那条路径上（`demo`）。
真实数据模式下缺什么就不显示什么——**空状态是诚实的，假数据不是**。
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools"))

from jsx import attr_expr, is_copyable, jsx_open_tags  # noqa: E402

LOAD = ROOT / "web" / "src" / "data" / "load.ts"


class RealModeNeverFallsBackToDemo(unittest.TestCase):

    def test_normalize_does_not_substitute_demo_values(self):
        """`normalize()` 走的是**真实数据**那条路。它里面出现 demo* 兜底，
        就意味着真实数据缺某块时，用户会看到一份虚构的替代品而毫无提示。"""
        t = LOAD.read_text(encoding="utf-8")
        seg = t[t.index("function normalize("):]
        seg = seg[:seg.index("\n}")]
        # 剥掉注释再查。记「当初为什么错」的那句注释里正好引用了 `?? demoEnv`
        # ——按本仓库的规矩那段必须留着，测试不能因此逼人删掉教训。
        code = "\n".join(ln for ln in seg.splitlines()
                         if not ln.strip().startswith("//"))
        bad = re.findall(r"\?\?\s*(demo\w+)", code)
        self.assertEqual(bad, [],
                         f"真实数据模式里静默兜底到了演示值：{bad}。"
                         "缺什么就不显示什么——空状态诚实，假数据不诚实")

    def test_env_items_are_actually_exported(self):
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('"envItems"', src, "导出器不产出 envItems，界面只能显示假的")

    def test_exported_env_uses_the_field_name_the_ui_reads(self):
        """字段名对不上是这个 bug 的直接成因：probe_env 给 label，界面要 name。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('e.get("label")', src, "没把 probe_env 的 label 映射成界面要的 name")

    def test_probe_failure_does_not_kill_the_export(self):
        """探测要起子进程。它炸了不该连带整份 data.json 出不来——
        装了什么与职位数据无关。"""
        import export_web_data as ex
        self.assertTrue(callable(ex._probe_env_safe))
        self.assertIsInstance(ex._probe_env_safe(), list)

    def test_empty_env_hides_the_panel(self):
        """空表渲染出来会是「都装好了 0 / 0」——一个看起来像好消息的空状态。

        > 原来断言的是字面串 `envItems.length > 0 && (`。后来这块改成
        > 「只有**必需项**缺失才出现」（守卫从 `envItems` 换成 `need`），它就红了
        > ——而新条件更强：探测为空时 `need` 也是空的，一样不渲染。
        > 锚在拼法上，更正确的改法反而被当成回归。这已经是第五次。
        >
        > 改成验**推导链**：守卫那个列表最终要来自 `envItems`。空表 ⇒ 空守卫 ⇒
        > 不渲染，这条链断在哪里都会红。
        """
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        code = re.sub(r"\{/\*.*?\*/\}", "", app, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)

        # 2026-08-24：这一块从正文里的折叠改成了那一排按钮里的一颗，
        # 「有才出现」的守卫也从 `{X.length > 0 && (` 挪到了 `show: X.length > 0`。
        # 两种写法都认 —— 上面那段注释说的就是这件事：**锚在拼法上，
        # 更正确的改法反而被当成回归。这已经是第六次。**
        i = code.index('key: "env"')
        guards = (re.findall(r"show: (\w+)\.length > 0", code[i:i + 300])
                  or re.findall(r"\{(\w+)\.length > 0 && \(", code[:i]))
        self.assertTrue(guards, "环境块无条件渲染，空探测时会显示成「0 / 0」")
        name = guards[0]

        # 顺着 `const X = …` 往上追，直到追到 envItems
        seen, chain = set(), [name]
        while chain[-1] != "envItems" and chain[-1] not in seen and len(chain) < 6:
            seen.add(chain[-1])
            m = re.search(rf"const {chain[-1]} = (.+?);", code)
            if not m:
                break
            nxt = re.findall(r"\b(envItems|\w+)\b", m.group(1))
            chain.append("envItems" if "envItems" in nxt else (nxt[0] if nxt else ""))
        self.assertIn(
            "envItems", chain,
            f"守卫环境块的是 {name!r}，它追不回 envItems（链：{chain}）—— "
            "探测为空时这块可能仍会渲染，显示成一句假的「都装好了 0 / 0」")


class ExportedFieldsReachTheUi(unittest.TestCase):
    """导出了却没人读 = 死数据；读了却没导出 = 死界面。两种都要拦。"""

    def test_parked_is_shown(self):
        """34 个降权泊车的岗导出了但界面从不显示，于是流水线前两格的缺口
        一直解释不通——用户会把它读成「还有这么多要做」。"""
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("parked", app, "parked 是死数据：导出了没人读")
        # 断言按**意图**而不是按措辞：原来钉的是字面串「不是积压」，
        # 一改文案就红，而改文案恰恰是对的（「积压」「结案」是公文词）。
        # 真正要保的是「显示了这个数，并且明确告诉用户不用做什么」。
        #
        # ⚠️ 必须先剥注释再匹配。第一版没剥，而 App.tsx 里解释这段改动的注释
        # 本身就含「不用管」三个字——于是把文案改成「已跳过」它照样绿。
        # 变异验证（改掉文案看测试红不红）就是拿来抓这个的。
        # **不要拿 `app.index("parked-note")` 定位。** 那个类名是「导航条下面
        # 那一族小字」共用的（降权泊车、存档、旧代码告警、待评…），谁排在前面
        # 就抓到谁 —— 2026-08-23 加了「还有 N 个没评分」之后，这条断言当场
        # 落到别人的文字上。锚在 `parked` 自己的渲染条件上。
        note = app[app.index("(parked ?? 0) > 0"):][:700]
        note = re.sub(r"/\*.*?\*/", " ", note, flags=re.S)
        note = "\n".join(ln for ln in note.splitlines()
                         if not ln.strip().startswith("//"))
        self.assertIn("{parked}", note, "显示了 parked-note 却没把数字放进去")
        self.assertTrue(
            any(w in note for w in ("不用管", "不用处理", "不用做")),
            f"parked-note 没告诉用户「不用管」，会被读成待办：{note[:160]}")

    def test_real_export_has_env_items(self):
        data = ROOT / "web" / "public" / "data.json"
        if not data.is_file():
            self.skipTest("还没导出")
        d = json.loads(data.read_text(encoding="utf-8"))
        if not d.get("isRealData"):
            self.skipTest("这份是演示数据")
        self.assertTrue(d.get("envItems"), "真实导出里没有 envItems")
        for e in d["envItems"]:
            with self.subTest(item=e.get("name")):
                self.assertTrue(e.get("name"), f"环境项没有 name：{e}")


if __name__ == "__main__":
    unittest.main()


class ARealUserWithZeroJobsIsNotDemoData(unittest.TestCase):
    """「导出器没跑过」和「跑过，但这个人还没抓职位」是两回事。

    `load.ts` 原来一律按 `jobs.length === 0` 退回演示数据。而那正是**每个新用户
    跑完 `/job-setup` 之后的状态**——实测：一个真实用户（资料齐全、0 个职位）打开面板，
    看到的是「示例用户」的 110/23/3 和 5 个虚构职位，而导出器**已经为她算好的**
    那句「还没抓职位：跑 /job-scrape 找新岗」被整个丢掉。

    页头那行「演示数据（虚构）」是诚实的，但它救不了这件事：新用户第一次打开面板，
    看到的是别人的求职进度，而唯一该告诉他的那句话不见了。

    判据是 `isRealData`——导出器自己盖的章。有它就说明这份数据是这个人的，
    哪怕一个职位都没有：**空状态是他真实的状态**。
    """

    LOAD = ROOT / "web" / "src" / "data" / "load.ts"

    def test_real_data_is_kept_even_with_no_jobs(self):
        t = self.LOAD.read_text(encoding="utf-8")
        i = t.index("async function loadSnapshot")
        seg = t[i:i + 2200]
        # 只问顺序，不钉那一行长什么样：写成 `if (d.isRealData) { return … }`
        # 语义没变而逐字钉会红（`test_a_guard_pins_behaviour_not_a_line.py` 数的那种）。
        # 顺序判据同时要求这个判断**存在**——`index` 找不到直接报错。
        self.assertLess(seg.index("d.isRealData"), seg.index("d.jobs.length === 0"),
                        "isRealData 的判断排在长度判断之后，等于没判")

    def test_the_exporter_still_stamps_it(self):
        """这条判据依赖导出器盖的那个章。章没了，判断就落空。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('"isRealData": True', src, "导出器不盖 isRealData 了")


class EmptyStatesPointAtTheNextCommand(unittest.TestCase):
    """空状态是新用户的第一屏，它得说清下一步敲什么，而且命令要能复制。

    让人对着屏幕手打命令是在制造错字——而这恰恰是最需要照做的一刻。
    """

    SHORTLIST = ROOT / "web" / "src" / "components" / "Shortlist.tsx"

    def test_the_empty_table_gives_copyable_commands(self):
        s = self.SHORTLIST.read_text(encoding="utf-8")
        i = s.index("emptyText")
        seg = s[i:i + 1600]
        # **逐条验**。只查「seg 里有 copyable」时，两条命令改坏一条还剩一条，
        # 断言照样通过——按存在性判，改一半跟没改一样。
        for cmd in ("/job-scrape", "/job-rank"):
            with self.subTest(cmd=cmd):
                self.assertNotEqual(seg.find(cmd), -1, f"空状态没给出 {cmd}")
                # 原来是「往前 200 字符里有没有 copyable」——那种固定窗口会被后来
                # 插进去的注释顶出去，而且把配置收进 `<Cmd>` 组件后当场失效。
                # 改问意图：这条命令在不在某个可复制块里。
                self.assertTrue(
                    is_copyable(seg, cmd),
                    f"{cmd} 不在可复制块里——让人手打命令是在制造错字")

    def test_it_says_what_each_command_does(self):
        """只给命令不说它干什么，用户不知道为什么要按顺序跑这两条。"""
        s = self.SHORTLIST.read_text(encoding="utf-8")
        i = s.index("emptyText")
        seg = s[i:i + 1600]
        self.assertIn("搜一轮", seg)
        self.assertIn("打分排序", seg)


class NothingIsExplainedBeforeItExists(unittest.TestCase):
    """没有数据时，不要先解释数据。

    空表上方原来还挂着列的图例（「技能高于总分＝活对口、钱少…」）——新用户第一屏
    就是空表，那时最不该做的是先教他读一张他还看不到的表。
    「不投的岗位（0）」同理：空的折叠面板，标题却在承诺里面有东西。

    与展开详情里那句「有一条不满足就别投」是同一条：**提醒只在有可提醒的对象时
    才出现**。
    """

    APP = ROOT / "web" / "src" / "App.tsx"

    def test_the_column_legend_waits_for_rows(self):
        """图例要跟着**它解释的那张表**走。

        > 原来断言的是字面串 `shortlist.length > 0`，而且靠「往前 300 字符」
        > 那种固定窗口。把主表改成只放「值得投以上」之后当场红了——图例的条件
        > 跟着改成了 `mainList.length > 0`，那是**更正确**的写法。
        > 锚在拼法上，正当的改动就会被当成回归。改成验：**守卫图例的那个列表，
        > 必须就是主表拿到的那个列表。**
        """
        t = self.APP.read_text(encoding="utf-8")
        code = re.sub(r"\{/\*.*?\*/\}", "", t, flags=re.S)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)

        main = next((attr_expr(tag, "jobs") for tag in jsx_open_tags(code, "Shortlist")), None)
        self.assertIsNotNone(main, "找不到主表的 <Shortlist jobs={…}>")

        # 锚在 class 上，不锚在文案上。2026-08-13 那句从
        # 「点任意一行展开详情 · 技能高于总分＝…」精简成「点任意一行看详情」，
        # 守卫当场 ValueError——它守的规矩（图例只在有行时出现）一个字没变，
        # 红的只是我把锚点钉在了会改的那半边。
        i = code.index('className="sec-note"')
        guards = re.findall(r"\{(\w+)\.length > 0 && \(", code[:i])
        self.assertTrue(guards, "列的图例无条件显示——空表时它在解释屏幕上不存在的东西")
        self.assertEqual(
            guards[-1], main,
            f"图例守在 {guards[-1]!r} 上，主表拿到的却是 {main!r} —— "
            "两者不是同一份名单时，图例会在一张空表上解释怎么读它的列")

    def test_the_empty_shelf_does_not_render(self):
        t = self.APP.read_text(encoding="utf-8")
        i = t.index("不投的岗位（${shelved.length}）")
        head = t[max(0, i - 420):i]
        self.assertIn("shelved.length > 0", head,
                      "一个都没有时还渲染折叠面板，点开是空的")


class NormalizeCarriesEveryDeclaredField(unittest.TestCase):
    """`normalize()` 是**手写白名单**——漏抄一个字段，那块界面就永远不出现。

    `resumeInsight` 就这么漏了：导出器算好了、`data.json` 里有、`Snapshot` 类型里
    也声明了，而 `normalize` 的返回值里没抄这一行。于是「市场怎么读你的简历」
    整块**从没被渲染过**——而它的内容很实（「评过的 97 个岗里 12 个是你的主场」
    「挡你最多的是英语要求，17 个岗」）。

    **类型系统拦不住这个**：所有可选字段缺了都合法，`tsc` 一声不吭。
    这条按 `Snapshot` 接口的字段逐条比对。
    """

    LOAD = ROOT / "web" / "src" / "data" / "load.ts"

    def _declared_fields(self) -> set:
        t = self.LOAD.read_text(encoding="utf-8")
        i = t.index("export interface Snapshot {")
        body = t[i:t.index("\n}", i)]
        # 去掉注释再取字段名
        body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
        body = "\n".join(ln for ln in body.splitlines()
                         if not ln.strip().startswith(("*", "//")))
        return set(re.findall(r"^\s*(\w+)\??:", body, re.M))

    def _normalized_fields(self) -> set:
        t = self.LOAD.read_text(encoding="utf-8")
        i = t.index("function normalize(")
        body = t[i:t.index("\n}", i)]
        body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
        body = "\n".join(ln for ln in body.splitlines()
                         if not ln.strip().startswith(("*", "//")))
        return set(re.findall(r"^\s*(\w+):", body, re.M))

    def test_every_snapshot_field_is_normalized(self):
        declared, carried = self._declared_fields(), self._normalized_fields()
        missing = sorted(declared - carried)
        self.assertEqual(
            missing, [],
            f"`Snapshot` 声明了这些字段，但 `normalize` 没抄：{missing}\n"
            "——导出器算了、传了，在这一步被静默丢掉，那块界面永远不出现。"
            "tsc 拦不住：可选字段缺了都合法。")

    def test_the_scan_finds_something(self):
        """判据自检：两边都得真解析出字段来，否则上一条在比两个空集。"""
        self.assertGreaterEqual(len(self._declared_fields()), 8)
        self.assertGreaterEqual(len(self._normalized_fields()), 8)

    def test_resume_insight_specifically_reaches_the_ui(self):
        """这一块是被这条规则抓出来的那个。单独钉一次，防它再掉。"""
        self.assertIn("resumeInsight", self._normalized_fields())
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("<ResumeRead data=", app, "组件没被渲染")
