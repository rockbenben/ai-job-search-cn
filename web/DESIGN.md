---
version: alpha
name: 仪表舱 · 总览页设计契约
description: web/src 总览页（React 19 + antd 6 + cockpit.css）的设计系统正本。令牌取自 theme/tokens.ts 与 cockpit.css 的 :root，与代码一一对应；本文只登记已经存在或已裁定的规则，未决事项进 Open Decisions，不悄悄发明。

colors:
  bay: &bay "#0d1218"
  panel: &panel "#151c25"
  panel-raised: &panel-raised "#1c2530"
  edge: "#2a3542"
  edge-strong: "#374553"
  lit: &lit "#eaf1f7"
  dim: &dim "#a8b4c2"
  faint: &faint "#8494a5"
  data: &data "#3ccbbf"
  data-deep: "#1e6e68"
  caution: "#e8ac3a"
  lock: "#e86259"
  lock-deep: &lock-deep "#803631"

  # 下面八个不是新配色，是上面八个语义色在 antd `ThemeConfig` 里的角色名（见 tokens.ts
  # 的 colorBgBase / colorText / colorPrimary…）。值用 YAML 锚点引用，一处字面量。
  # 加 `antd-` 前缀是故意的：这些**不是 CSS 变量**，代码里只认 `--bay` 那一组。
  antd-colorBgBase: *bay
  antd-colorBgContainer: *panel
  antd-colorBgElevated: *panel-raised
  antd-colorPrimary: *data
  antd-onPrimary: *bay
  antd-colorText: *lit
  antd-colorTextSecondary: *dim
  antd-colorTextTertiary: *faint

typography:
  display-score:
    fontFamily: "var(--mono)"
    fontSize: 46px
    fontWeight: 700
    lineHeight: 0.90
    letterSpacing: 0px
  number-xl:
    fontFamily: "var(--mono)"
    fontSize: 34px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0px
  number-lg:
    fontFamily: "var(--mono)"
    fontSize: 26px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0px
  number-md:
    fontFamily: "var(--mono)"
    fontSize: 22px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0px
  title-lg:
    fontFamily: "var(--mono)"
    fontSize: 17px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: 0px
  body-md:
    fontFamily: sans
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: 0px
  label-md:
    fontFamily: sans
    fontSize: 13.5px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0px
  body-sm:
    fontFamily: sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0px
  meta-md:
    fontFamily: sans
    fontSize: 12.5px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0px
  meta-sm:
    fontFamily: sans
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0px
  number-sm:
    fontFamily: "var(--mono)"
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: 0px
  stamp-glyph:
    fontFamily: "var(--serif)"
    fontSize: 14px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0px

rounded:
  none: 0px
  xs: 1px
  base: 2px

spacing:
  xxs: 2px
  xs: 4px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 12px
  xxl: 14px
  section: 24px
  gutter: clamp(16px, 2.5vw, 34px)

components:
  stamp-pass:
    backgroundColor: "{colors.data}"
    textColor: "{colors.bay}"
    typography: "{typography.stamp-glyph}"
    rounded: "{rounded.base}"
    width: 30px
    height: 30px
  stamp-fail:
    backgroundColor: "{colors.lock-deep}"
    textColor: "{colors.lit}"
    typography: "{typography.stamp-glyph}"
    rounded: "{rounded.base}"
    width: 30px
    height: 30px
  stamp-unknown:
    backgroundColor: "color-mix(in srgb, {colors.caution} 9%, transparent)"
    textColor: "{colors.caution}"
    typography: "{typography.stamp-glyph}"
    rounded: "{rounded.base}"
    width: 30px
    height: 30px
  stamp-na:
    backgroundColor: transparent
    textColor: "{colors.faint}"
    typography: "{typography.stamp-glyph}"
    rounded: "{rounded.base}"
    width: 30px
    height: 30px
  panel-card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.lit}"
    typography: "{typography.body-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.xxl}"
  rail-cell:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.data}"
    typography: "{typography.number-xl}"
    rounded: "{rounded.none}"
    states:
      - default
      - hover
      - focus-visible
      - active
  shortlist-row:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.lit}"
    typography: "{typography.body-md}"
    rounded: "{rounded.none}"
    height: 34px
    states:
      - default
      - hover
      - selected
      - focus-visible
  chip-meta:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.dim}"
    typography: "{typography.meta-md}"
    rounded: "{rounded.base}"
    padding: "1px 6px"
    states:
      - default
      - hover
      - disabled
  button-default:
    backgroundColor: transparent
    textColor: "{colors.dim}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.base}"
    height: 34px
    states:
      - default
      - hover
      - focus-visible
      - disabled
  input-search:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.lit}"
    typography: "{typography.body-md}"
    rounded: "{rounded.base}"
    height: 34px
    states:
      - default
      - hover
      - focus-visible
      - error

states:
  hover:
    components:
      - rail-cell
      - shortlist-row
      - chip-meta
      - button-default
    requirement: cockpit.css 有 19 条 hover 规则；antd 表格行由 tokens.ts 的 rowHoverBg 接管。
  focus-visible:
    components:
      - rail-cell
      - shortlist-row
      - button-default
      - input-search
    requirement: 一律 2px solid {colors.data} + outline-offset 2px；非文字对比 8.56:1，满足 3:1。
  active:
    components:
      - rail-cell
      - chip-meta
      - button-default
    requirement: 一档静态底色（沉到 bay、字提到 lit）。这一页 motion:false，按下不能靠动画。表行与 .have-jump 故意不进这一套。
  disabled:
    components:
      - chip-meta
      - button-default
    requirement: 12 条规则；文案侧由 test_web_copy 的 ADisabledControlPromisesNothing 盯住「禁用态不许承诺还没发生的事」。
  loading:
    components:
      - button-default
      - rail-cell
    requirement: 有意不用。写操作一律乐观更新 + 可回滚，spinner / 变灰恰恰是用户报过四次的那个「点了没反应」。
  empty:
    components:
      - panel-card
    requirement: EmptySectionsSayTheyAreEmpty 断言空区块必须自陈是空的。
  error:
    components:
      - input-search
    requirement: 用 {colors.lock} 表述越界与不满足；ReassuranceIsNotStyledAsWarning 禁止把安慰渲染成警告。

rules:
  - 零圆角。borderRadius 一路压到 2（tokens.ts），判定类界面不许出现药丸形；3px 属于漂移。
  - 等宽字体只给纯数字与拉丁文，且不加字距——0.17em 摊在数字上会把一个数拆成几个。中文进 mono 类由 test_css_and_cjk_text 拦。
  - 汉字不许小于 12px（FLOOR=12.0），由 test_cjk_never_goes_below_the_floor 拦静态字面量；数据驱动的文案它测不到。
  - 颜色只用 :root 的 12 个语义变量，不在应用代码里写 hex 或 rgba。语义名而非色名。
  - 要半透明底纹就从语义色派生（color-mix(in srgb, var(--data) 8%, transparent)），不另写字面量。
  - 压暗用的黑色 alpha（方章斜纹、浮层投影）不算配色，不受上一条约束；除此之外不许出现 rgba。
  - 覆盖 antd 组件与本层控件的定点样式，作用域必须从 body 起，不能挂 .cockpit：面板（Modal）与 Tooltip 是 portal 到 body 的，挂在 .cockpit 底下的一条都进不去。钉在 test_css_and_cjk_text 的作用域判据上。
  - 分层不靠投影。boxShadow 系列令牌全为 none，靠 {colors.edge} 线、间距和底色层级分开区块；「抬起」用 inset 描边画，不用外投影。
  - 浮层是唯一的例外：盖在页面之上的那层允许一条真实外投影，用来压住背景，不用于卡片。
  - inline style 只许用于**由数据算出来的值**（进度条宽度、判词颜色）；静态样式一律进 class。
  - 写盘按钮点下去，屏幕上必须立刻有东西变（乐观更新 + 失败回滚）；不许用 spinner 或变灰冒充反馈。
  - 关掉 antd 进场动画（motion: false），因为 prefers-reduced-motion 下 antd 会把元素停在 opacity:0 那一帧。
  - 关掉 antd 的中文按钮插空格（button.autoInsertSpace: false），否则「挂了」上屏变成「挂 了」。
  - 给用户看的措辞换成内地求职者自己的话；内部框架词与判定码不上屏，由 test_display_wording 扫。
  - 从文件正文流向界面的字段要先剥掉 markdown 标记（** 与反引号），显示层负责，不让星号上屏。
  - 每一处「下一步」都要写出可以照敲的命令，且只写一条。
---

# 仪表舱 · 总览页设计契约

## Overview

这一页是**本机跑的求职流水线总览**（`tools/serve.py` 端上 `web/dist`，端口 29029），
不是公开站点。它的气质是「舱内仪表盘」：深色底、硬边、方章、数字对齐可比。
使用者是一个人独用、盯着自己的数据做决定，所以密度优先于留白，
判定结果优先于装饰。核心动作是「盖章 / 判定」，四条取向（零圆角、等宽数字、
中文优先的字号下限、靠线不靠影）都从这里派生。

## Colors

`{colors.bay}` 是舱内底，`{colors.panel}` 是面板，`{colors.panel-raised}` 是抬起的面板
（hover / 选中）。`{colors.edge}` 只作分隔线，`{colors.edge-strong}` 标可交互边界。
文字三档 `{colors.lit}` / `{colors.dim}` / `{colors.faint}`，对最亮那层底
`{colors.panel-raised}` 实测 13.58 / 7.35 / 4.98:1。
语义色四个：`{colors.data}` 青＝读数与「满足」，`{colors.caution}` 琥珀＝待确认，
`{colors.lock}` 红＝不满足与越界表述，`{colors.faint}` 兼作「跳过」。
`{colors.data-deep}` 只用作青色边框的暗调；`{colors.lock-deep}` 是红色侧的对称位——
斜纹方章的印面底色，掺黑比例照 `data-deep` 那一档，不是新色相。

对比度一律按**最亮的那层底**算——在最不利的一层成立，在 bay / panel 上自然更高。
`tests/test_contrast.py` 把这些数当断言验，注释和色值对不上就红。

frontmatter 里另有一组 `antd-color*` 键，值全是上面语义色的锚点，**不是第十三种颜色**：
它们记的是 `tokens.ts` 把哪个语义色交给了 antd 的哪个角色，顺带让预览画布的对比度配对
有名字可匹配。写代码时只用 `var(--bay)` 那一组；`antd-` 前缀就是为了让它一眼不像 CSS 变量。

## Typography

正文走 `body-md`（15px / 1.7），次要说明走 `label-md`、`body-sm`、`meta-md`、`meta-sm`。

frontmatter 里 `fontFamily` 只写三个短名，不写字面量——它们是**指向正本的引用**，
正本各只有一份，抄进本文就会和代码飘：

```
sans   antd fontFamily 令牌 = tokens.ts 的 FONT_SANS
       "Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif
mono   cockpit.css:22 --mono（tokens.ts 的 fontFamilyCode 是同族另一份字面量）
serif  cockpit.css:23 --serif，只给方章的印文用
```

`mono` / `serif` 有 CSS 变量可直接 `var(--mono)`；`sans` 没有（页面从 `body` 继承），
所以本文用 `sans` 这个名字指代它，不复制那串。

其中 `{typography.meta-md}` 12.5px 是**全页用量最大的档**（cockpit.css 出现 75 次），
`{typography.meta-sm}` 12px 是中文的地板。
`{typography.number-sm}` 11px 只许进纯数字与拉丁文（`.mono-label`、`.rail-step`）。
数字展示档 `number-md` … `display-score` 是给分数和流水线读数用的等宽大字，
不构成文字层级。

文字档现在落在 `cockpit.css` 的 `:root` 上：`--fs-micro` 12 / `--fs-meta` 12.5 /
`--fs-small` 13 / `--fs-label` 13.5 / `--fs-content` 14 / `--fs-body` 15，另有一枚
`--fs-stamp` 14 给方章印文（那一格见方里的单字不是文字层级，别混进标度）。
原来 20 个散取值里的 14.5 与 15.5 是纯漂移，各收进相邻一档（差 0.5px，无视觉台阶）。
**数字与拉丁的小字号 11 / 11.5px 与展示用大字（17 / 19 / 20 / 22 / 25 / 26 / 27 / 28 / 34 / 46）
仍写字面量**：前者是层级不是文字档，后者每个数都绑在它那块盒子里，
硬套一套「大字标度」是给不存在的需求让路。

## Layout

`.cockpit` 居中，`max-width: 1180px`，外边距 `{spacing.gutter}`（`clamp(16px, 2.5vw, 34px)`）。
## Spacing

组件内距从 `{spacing.xxs}` 到 `{spacing.xxl}` 取；`{spacing.section}` 用于区块之间。
**观察到的实际用量比这套标度细**：gap 出现过 1/3/5/7/9/11/13 这些奇数档。
本契约不主张把这些一次性往上取整——密集仪表盘里 1px 的差别是视觉事实，
重新对齐一遍的收益抵不上抖动。规则只立一条：新写的间距优先用上面已命名的档。

## Shapes

只有三档：`{rounded.none}`、`{rounded.xs}`、`{rounded.base}`。
出现第四个值就是漂移，不是「还有一档」——2026-09-30 那一轮 3px 就是照着这条清的。
方章的 `::before` 用 `{rounded.base}`，与 antd 侧的 `borderRadius: 2` 同一个数。无 pill。

## Elevation & Depth

没有外投影。`boxShadow` / `boxShadowSecondary` / `boxShadowTertiary` 全部 `none`，
`primaryShadow` / `defaultShadow` 也全部 `none`。层次靠三件事：底色层级
（bay → panel → panel-raised）、`{colors.edge}` 线、以及间距。
「抬起」用 `inset` box-shadow 描边画（见方章与选中行），不是投影。

**一处例外，也是有意的**：盖在整页之上的浮层留一条真实外投影——那层需要压住背景，
靠边线和间距分不出「浮在上面」。除浮层之外任何区块都不许加外投影。

## Components

实现层与本文的对应关系（详见 `web/src/components/`）：

- `GateStamp.tsx` → 四态方章 `stamp-pass` / `stamp-fail` / `stamp-unknown` / `stamp-na`，
  30px 见方、宋体单字。`data-size="sm"` 是 17px 无字版。
- `Shortlist.tsx` → `shortlist-row`（antd Table，行 `role="button"` + Enter/Space）。
- `JobReadout.tsx` → 行内详情，复用方章与 `InterviewLog`。
- `Cmd.tsx` → `chip-meta` 形态的命令复制片。
- `Portals.tsx` / `HidePrefs.tsx` / `HrAnswers.tsx` → 渠道行与全原生 button 的偏好面板。
- `App.tsx` 的 `nav.rail` → `rail-cell`（5 格流水线）；`nav.deskbar` + `Modal` → 7 个 desk。

每个族自带哪些状态，frontmatter 的 `components.*.states` 逐项列了，这里是判读口径：
可点的族（`rail-cell` / `shortlist-row` / `chip-meta` / `button-default` / `input-search`）
必须有 `default` / `hover` / `focus-visible` / `disabled` 四件，`input-search` 另加 `error`；
`:active` 是一套统一的静态底色（见 States），新控件要一起进那条选择器列表；
`loading` 这一族**不适用**——写操作走乐观更新，理由见下面 States。
方章 `stamp-*` 四态是**判定结果**不是交互态，所以它不吃 `hover` / `focus`，只吃 Tooltip 的
aria 关联。

## States

`hover`、`focus-visible`、`disabled` 三件成体系，`empty` 与 `error` 有专门的文案断言在盯。
**`:active` 是一档静态底色**：底色沉到 `{colors.bay}`、字提到 `{colors.lit}`，
统一挂在 `body` 上（面板里的按钮与主页面同源）。表行走整行展开、`.have-jump` 的底色是
筛选开/关的**状态色**，两者都不叠这一下。
`loading` **不算缺口，是不该有**——`serve.py` 写完盘要在响应前同步跑导出子进程
（实测 3.4-4.2 秒），那几秒用乐观更新吸收；`tests/test_every_write_button_answers_immediately.py`
明写「把控件转起来或变灰」不算反馈，那正是用户报过四次「点了没反应」的东西。
所以这一页不引 spinner，写操作一律**点下去立刻变 + 失败回滚**。
键盘可达性上 `tabIndex` 全仓只有 1 处（表格行），其余交互件都是原生 `<button>`，
浮层有 Esc 与外点出口。

## Accessibility

文字：三档灰阶在最亮底上 ≥4.98:1，全部达 AA。
非文字：焦点环取 `{colors.data}`，对 `panel` 8.56:1，满足 1.4.11 的 3:1；
antd 侧由 `colorPrimaryBorder` 显式钉成同一个色。
**已知不达标一处**：`{colors.edge-strong}` 对 `panel` 1.75:1，当它是「这里可以点」的
唯一线索时不够（WCAG 1.4.11 要 3:1）；靠它划**分隔**的地方不受这条约束，那是装饰。
方章那一处已经修掉了：`stamp-fail` 原来是白字压 `{colors.lock}`，纯色底只有 3.32:1，
而 14px 不算大号字、AA 要 4.5；现在印面走 `{colors.lock-deep}`、字走 `{colors.lit}`，
实测 7.40:1。斜纹（26% 黑）只会让暗底更暗，所以对亮字是**只帮不害**——
这一族的配色前提是「暗底亮字」，反过来用就把斜纹的余量吃干了。
触屏目标按**渲染后的盒子**量，不按 CSS 里写的数猜：2026-09-30 首屏加七个面板全量扫完，
低于 24px 的只剩两类——antd 的复制图标（13×15，全页 141 颗）和四个文字型小控件
（`.nextstep-more` 21、`.have-jump` 23、`.portal-refresh` 21、`.portal-sw` 22）。
复制图标那批不是尺寸不够，是**作用域进不了面板**（见 Rules）；两者都按同一个办法修：
内边距撑开命中区、等量负边距抵掉，版面一个像素不动。现在复测：图标 27×29，四颗全 ≥24。
`controlHeight: 34` 本身已过 2.5.8，不为 AAA 的 44px 整体拉高。
中文地板同理——静态扫不到「从数据来的文案」，实测只有漏斗图例一处 11px，已抬到 12.5。

## Motion

`motion: false`。原因写在 `tokens.ts`：antd 的 `ant-zoom-appear` / `ant-fade-appear`
把 `opacity: 0` 放在动画起始帧，而本页在 `prefers-reduced-motion` 下关掉动画，
元素会永远透明——所以从源头关，而不是缩短时长。这一页本来没有需要动画传达的信息。

## Copy Rules

措辞的正本不在这里，在 `workflows/reference/03-writing-style.md`（铁律 / AI 味清单 /
句式 / 语气）与 `AGENTS.md`「给用户看的措辞」那张内部词对照表。这一节只记**这一页**
特有的三件事：

- **同一把尺子要量三个出口。** 上屏的字有三个来源：导出的 `data.json`、
  `serve.py` 打给终端的字、以及**组件里写死的 JSX 文本节点**。
  判据原来只量前两个，于是 `OutcomeStats` 里「就该回去调权重」这类句子一直绿着
  （2026-09-30 是在渲染后的 DOM 里量出来的，不是读源码读出来的）。
  新写文案时按这三个出口想一遍，别假设有人在管。
- **标记一律由显示层剥。** markdown 的 `**` 与反引号、以及 `<br>` 这类 HTML 标签，
  进的都是纯文本节点与 `title=`，浏览器不渲染——清理住在 `export_web_data.plain()`，
  一处生效于三个出口。它只剥**列得出名字的标签**：命令模板里的 `<职位链接>`
  是用户要照敲的内容，通吃版会把它吃掉。
- **人称。** 要发出去的话用「我」；给他看的分析（评估结论、打分说明、判定依据）
  用「你」；两种都不许用「他」。判据见 03 的「语气」一节。
- **工具自己的话不上屏。** 打分器在依据末尾追加的那段自述（「⚠️ 某日 `score.py`
  现算订正：…」）是写给**下一个改评估文件的人**的——防手改，不是给他看的分析，
  而它说的那三个数面板本来就有。留在盘上，剥在显示层（`_SCORE_LOG`）。
  认「现算订正」这四个字，**不认 ⚠️**：别的 ⚠️ 段是真提醒，一个都不许跟着剥。

## Do's and Don'ts

Do：只用 12 个语义色变量；新间距优先取已命名档；焦点环统一 `{colors.data}`；
中文标签走 `.kicker`，等宽只给数字；给用户看的下一步必须是一条可照敲的命令。

Don't：不要在应用代码里写 hex 或 `rgba()`；不要写 `border-radius: 3px`；
不要用 `var(--不存在的变量)`（不会报错，只会让整条声明静默失效，
`CommandBook.tsx` 的 `--text-secondary` / `--text-tertiary` 就是这么活下来的）；
不要把 markdown 的 `**` 和反引号送上屏；不要用红色表述「安慰」类文案。

## Responsive

四个宽度断点：900 / 720 / 620 / 560（`max-width`），集中在 cockpit.css 的一节里，
由 `BreakpointsStayTogether` 盯住不许散落。媒体查询选择器必须比被覆盖规则多一层特异性
（`test_media_queries_actually_win`）。
**已知不足**：没有 ≥1180 的宽屏档，`.cockpit` 在宽屏上只是两侧留白变宽。
窄屏的塌缩规则原来有 9 条挂在 `.cockpit` 下、进不了面板（含 `.portal-row`、`.cmdbook-row`
那批），2026-09-30 改到 `body` 作用域后 390px 实测：`.portal-row` 两列、`.cmdbook-row` 一列。
同一次实测还量到面板内容 2px 的假溢出（313>311）——与 cockpit.css 里那条
「0.01px 溢出长出两条滚动条」同根源，缩放小数取整造成，没有长出滚动条。

## Known Gaps

以下按 `needs-design-decision` 登记，不在文档里悄悄定策：

- needs-design-decision: `loading` 反馈用 spinner、骨架，还是沿用「只改按钮文案」这一家做法。
- needs-design-decision: `edge-strong` 作为可控件边界不达标时，是加边框宽度还是抬亮。
- needs-design-decision: 宽屏（≥1180）要不要用多列而非留白。
- 已裁定（2026-10-02，用户原话「不用改存量」）：**存量评估正文不改。**
  那批字里仍以第三人称写着使用者本人（「他的产品一直是一个人用 AI 跑完」），
  夹着「硬门槛」「权重」这类框架词；另有 8 条职位记录的 `location` 字段存着
  判定码 `PASS`（城市被同名键挤掉了）。措辞规则只管**新写出去的字**
  （03 的「语气」一节），显示层负责不再把标记、判定码和工具自述送上屏。
  **这条不是待办**：要改那批字只能动 `users/` 里的个人数据，或重跑那批评估
  （会连带改动分数上下文）——两条都已否。读到一句老写法就照旧，
  宁可如此，也不去改用户的文件。
