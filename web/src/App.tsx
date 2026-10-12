import { useCallback, useEffect, useMemo, useState } from "react";
import { Cmd } from "./components/Cmd";
import { App as AntApp, Button, Collapse, ConfigProvider, Modal } from "antd";
import zhCN from "antd/locale/zh_CN";
import { cockpitComponents, cockpitTheme } from "./theme/tokens";
import { Shortlist, ShelvedList, plainVerdict } from "./components/Shortlist";
import { ResumeRead } from "./components/ResumeRead";
import { BaseResume } from "./components/BaseResume";
import { CommandBook } from "./components/CommandBook";
import { CodeToolProvider } from "./context/CodeToolContext";
import { OutcomeStatsPanel, sayRate } from "./components/OutcomeStats";
import { HidePrefs } from "./components/HidePrefs";
import { HrAnswers } from "./components/HrAnswers";
import { loadHidden, saveHidden, isHidden, compile, appliedCompanySet,
  EMPTY as EMPTY_HIDDEN } from "./data/hidden";
import { GATE_FAIL, type Job } from "./types";
import { loadSnapshot, type Snapshot } from "./data/load";
import { Portals, blockNeedsYou } from "./components/Portals";
import { JobPrefs } from "./components/JobPrefs";
import {
  hasServer, loadDelta, saveDelta, deltaFrom, applyDelta, postSkip, postRestore,
  postExpire,
  postHrAnswer,
} from "./data/excluded";
import "./theme/cockpit.css";

/**
 * 求职总览
 *
 * 版面自上而下就是「我现在该做什么」的回答路径：
 *   我走到哪一步了 → 下一步做什么（只给一条）→ 要装的工具够不够
 *   → 有哪些能投的岗 → 这个岗到底怎么样 → 哪些被条件挡下了
 *
 * 屏幕上的措辞一律用求职者自己会说的话。`workflows/` 里的框架词
 * （硬门、能力边界、四维、台账）是给 AI 看的，不往界面上搬——见 types.ts 顶部说明。
 */
export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  useEffect(() => {
    loadSnapshot().then(setSnap);
  }, []);
  // 投递状态写进盘上之后**重新取一次快照**，不在这边照着算一遍。
  // 一次「我投了」会牵动流水线计数、这个岗的下一步、它还在不在待投区——
  // 那些推导全在 Python 里，在 TS 里复刻一份就是第二套真相，迟早对不上。
  // serve.py 在响应之前已经重生成过 data.json，这一取拿到的就是新的。
  /**
   * 状态按钮（我投了 / 约面了 / 挂了…）写完盘之后的回调。
   *
   * **记一笔就该自动前进到下一个。** 「我投了」会把这个岗移出可以投的名单，
   * 而 `selectedId` 还钉在它身上——`effectiveId` 于是变空，整块塌成收起态，
   * 用户看到的是「点了没反应」（2026-08-12 实测反馈原话：「怎么没自动切到下一个」）。
   * 复用标「不投」那条路已经验证过的做法：同一次提交里换到下一行。
   */
  /**
   * 刚点过「我投了」的那些 —— **本地先记一笔，让行立刻走**。
   *
   * 上一版只让展开面板里的内容立刻变成「已记下」，而**这一行还在不在名单里**
   * 是 `snap.jobs` 算出来的，得等重导回来（写盘改了台账 mtime，`serve.py`
   * 下一次 `/data.json` 要重新导出整份数据，秒级）。于是用户点完看到的是：
   * 里面写着「已记下」，外面那行还杵在「可以投的岗位」里
   * ——2026-08-13 原话「点了 我投了，它怎么没消失？」。
   *
   * 「不投」那条路早就这么做了（`excluded` 是同样的本地增量），状态按钮一直没跟上。
   * 写失败或撤销时把 id 拿掉，行就回来——乐观更新必须配一条回滚路径。
   */
  const [justActed, setJustActed] = useState<Set<string>>(new Set());
  //: 视图过滤偏好。**不改任何岗的状态**——见 `data/hidden.ts` 顶上那段。
  // 挂载时还不知道活动用户（快照没到），先给空偏好；`activeUser` 一到就换成
  // 他自己那份。**不能在 useState 初值里读**——那一刻读到的会是上一个用户的。
  const [hidden, setHidden] = useState(EMPTY_HIDDEN);
  const setHiddenSaved = (p: typeof hidden) => { setHidden(p); saveHidden(p, activeUser); };
  const afterStatus = (advance?: boolean, id?: string,
                       phase?: "now" | "settled") => {
    // **两拍，因为捆在一起的是两件性质相反的事。**
    //   界面（justActed 让行走、setSelectedId 打开下一条）—— 纯本地，必须立刻；
    //   refreshAnd 重取快照 —— 必须等写盘，早了会拿回旧数据。
    // 原来它们同在这一个回调里，而回调只在 `mark()` 的 `await` 之后调 ——
    // 于是纯界面那两件跟着写盘一起等（实测导出子进程 3.4–4.2 秒）。
    // 用户为这件事报了**四次**，前三次修的都是这个函数**体内**的顺序，
    // 这次的病灶在它**被调用的时刻**。
    // 不带相位 = 两件都做（`undo`、`saveReason`、写失败回滚走这条，行为不变）。
    if (phase !== "settled" && id) {
      setJustActed((prev) => {
        const next = new Set(prev);
        if (advance) next.add(id);
        else next.delete(id);          // 撤销 / 写失败：放回来
        return next;
      });
    }
    // **跳也要立刻。** 上面那次 setJustActed 已经让这一行消失了，
    // 「塌下去和跳过去在同一次提交」这条（见 `refreshAnd`）要求跳跟着它走 ——
    // 压进下面的 `.then()` 里就成了「先塌，2 秒后才跳」：实测记完状态那一次
    // `/data.json` 要 2.13s（台账 mtime 变了，serve 整份重导），平时只要 0.18s。
    // 用户为这件事报了三次，前两次修的是同一件事的另外两层。
    // **撤销那一支要把展开位置挪回去。** `undo()` 那行注释写着「撤销不挪：
    // 行会回到名单里，挪走反而把视线带离他刚撤的那个岗」—— 可视线**早就不在
    // 那个岗上了**：记状态成功时这里已经跳到下一条。不挪 = 停在下一条，
    // 于是他撤销完看到的是那个岗回到列表里，而展开区开在别人身上。
    if (phase !== "settled" && id) setSelectedId(advance ? nextInList(id) : id);
    if (phase === "now") return;      // 界面这一拍做完了，重取留给写盘回来那一拍
    return refreshAnd();
  };
  /**
   * 重取快照；给了 `next` 就顺便把展开的那一行挪过去。
   *
   * **只给「行是随快照消失」的那条路用**（`expire`）。有乐观移除的两条
   * （`afterStatus` 的 justActed、`exclude` 的 excluded）**在它们自己那一次提交里
   * 就把选中挪好了** —— 塌和跳同一次提交，这条规矩看的是「哪一次提交让行消失」，
   * 不是「哪个函数里」。压进这里的 `.then()` 就成了「先塌，两秒后才跳」。
   *
   * **两件事必须在同一次提交里做完。** 分两步（先 setSnap、再 setSelectedId）
   * 会先塌一下再跳：被移除的那行连同它两千像素的展开区一起消失，页面高度骤减，
   * 浏览器不会替你调整滚动位置，视线当场落到不相干的地方，然后才跳到新的一行。
   * 一次提交里换过去，看起来就是「这一行没了，下一行接上」。
   */
  const refreshAnd = (next?: string) =>
    loadSnapshot().then((s) => {
      setSnap(s);
      if (next !== undefined) setSelectedId(next);
    });

  const jobs = snap?.jobs ?? [];
  const { pipeline, envItems, nextStep, activeUser, allUsers, parked } = snap ?? {
    pipeline: [], envItems: [], nextStep: { text: "" }, activeUser: "",
    allUsers: [], parked: 0,
  };
  // 视图偏好按**这个用户**读。挂载时 `activeUser` 还是空串（快照没到），
  // 所以初值给空偏好、这里再换——在 useState 初值里读会读到上一个用户那份。
  useEffect(() => {
    if (activeUser) setHidden(loadHidden(activeUser));
  }, [activeUser]);
  const portals = snap?.portals ?? [];
  //: 有网站被平台拦住 —— **只用来点亮按钮上那枚标记**，不弹窗、不自动展开。
  //
  //: 原来这里还有一套受控的折叠展开（`portalsOpen` + 一个「没封 → 有封」
  //: 只开一次的 effect），那是折叠时代的东西：2026-08-21 猎聘 CLI 封了 9 小时，
  //: 而告警整块埋在收起来的折叠里，面板上一个字都看不到。
  //: 现在那句话印在「招聘网站」那颗按钮上，那排按钮就在「下一步」下面 ——
  //: **比原来更靠前，也就不需要替用户展开什么了。**
  const jobPrefs = snap?.prefs ?? [];
  //: **开关必须真的滤，否则它就是个装饰品。** 关掉的那几类从这里被滤掉——
  //: 判据不在这儿算，用的是导出器给每个岗打好的 `prefTags`：两处各写一份判据，
  //: 就会出现「说会滤掉 1361 个、实际滤掉 1290 个」这种对不上的数。
  //: 现在开着的是哪一块（`null` = 都没开）。
  //
  //: **这几块原来是页面正文里的折叠区**（招聘网站、岗位类型、要装的工具、
  //: 你的简历、市场怎么读你的简历、投出去的那些、能敲哪些命令）。它们回答的
  //: 都不是「我今天该投谁」—— 是设置、统计、说明。收起来也各占一行加外边距，
  //: 七块叠起来就把名单挤下去了。
  //
  //: 中间试过一版侧边抽屉，用户 2026-08-24 直接否掉：**改成看得懂的文字按钮，
  //: 点一下开 Modal**。按钮上带着原来折叠标题里那句结论 —— 那几句是刻意写的
  //: （「上次审于 X，之后改过没再审」「有回音 0%」），不点开也要看得见。
  const [desk, setDesk] = useState<string | null>(null);
  const prefOff = useMemo(
    () => new Set(jobPrefs.filter((p) => !p.enabled).map((p) => p.key)),
    [jobPrefs]);
  const passesPrefs = useCallback(
    (j: Job) => prefOff.size === 0 || !(j.prefTags ?? []).some((t) => prefOff.has(t)),
    [prefOff]);
  const [userPanel, setUserPanel] = useState(false);
  // 用户弹层：**Esc 关、点外面关**。
  //
  // 它是 `position: absolute; z-index: 20`，展开时**盖住下面的内容**，而原来
  // 只能再点一次「换个用户」才关得掉——盖住了正文，出口却只有来时那一个。
  // 实测按 Esc 没反应、点页面别处也没反应。
  //
  // 顺带把 `role="dialog"` 去掉了：它不是模态对话框，是一个「按钮展开一块面板」
  // 的 disclosure，触发按钮上的 `aria-expanded` 已经把这件事说清楚了。
  // 挂 dialog 这个 role 等于向读屏承诺焦点会被托管、Esc 会生效——而两样都没有。
  useEffect(() => {
    if (!userPanel) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setUserPanel(false);
    const onDown = (e: MouseEvent) => {
      // 点在触发按钮上不管——那次点击本来就会 toggle，这里再关一次就成了
      // 「关了又开」，看起来像没反应。
      const t = e.target as HTMLElement;
      if (!t.closest(".mast-user")) setUserPanel(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [userPanel]);
  // 你自己排除掉的岗。见 data/excluded.ts：有本地服务就写回盘上，没有才存浏览器。
  const live = hasServer();
  const [excluded, setExcluded] = useState<Set<string>>(() => new Set<string>());
  const [saveError, setSaveError] = useState("");
  // 盘上标了「不投」的那些——导出那一刻的事实，两种模式下都是底。
  const onDisk = useMemo(
    () => new Set((snap?.jobs ?? []).filter((j) => j.skipped).map((j) => j.id)),
    [snap],
  );
  // 排除名单从哪来，取决于跑在哪种模式下：
  //
  //   有服务 → **只看盘上的**。绝不能再叠一层 localStorage：点「不投 / 放回」
  //            当场就写盘了，再叠一层就会出现「盘上已放回、页面仍隐藏」的鬼状态。
  //   静态   → 盘上的，**盖上**这个浏览器自己改的那几笔（静态版写不回盘）。
  //
  // 静态那条原来只读 localStorage，把快照里的 `skipped` 整个无视了。**实测**：
  // 单文件面板把两个早就标了「不投」的岗又摆回「可以投的岗位」里（23 行变 25 行）。
  // 增量为什么不能压成一个集合，见 `data/excluded.ts`。
  useEffect(() => {
    if (!snap) return;
    setExcluded(live ? new Set(onDisk) : applyDelta(onDisk, loadDelta(activeUser)));
  }, [live, snap, onDisk]);

  const exclude = (id: string, on: boolean) => {
    // 先乐观更新——点了就该立刻消失，不该等一个来回。
    setExcluded((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      if (!live) saveDelta(deltaFrom(onDisk, next), activeUser);
      return next;
    });
    if (!live) return;
    setSaveError("");
    // 成功后重取快照——流水线计数、skipReason、搁置区都在 Python 里派生，
    // 不取的话它们停在旧值直到用户手动刷新（状态按钮那条路早就这么做了）。
    // 标「不投」时顺手把展开挪到下一条（见 `nextInList`）；「放回」不挪——
    // 那时没有行消失，挪反而把用户的视线从他刚放回的那个岗上带走。
    // 同 `afterStatus`：上面的 setExcluded 已经把行拿掉了，跳必须在同一次提交里，
    // 不能等写盘回来（那一次要两秒）。**「放回」时不挪** —— 那时没有行消失，
    // 挪反而把视线从他刚放回的那个岗上带走。
    if (on) setSelectedId(nextInList(id));
    (on ? postSkip(id, "在总览页标的不投") : postRestore(id))
      .then(() => refreshAnd()).catch(
      (err: Error) => {
        // 写失败就把界面改回去。留着「已排除」的样子是最坏的：
        // 页面说排除了、盘上没有，刷新一下它又回来，而用户不知道为什么。
        setExcluded((prev) => {
          const back = new Set(prev);
          if (on) back.delete(id);
          else back.add(id);
          return back;
        });
        // **跳也要回滚。** 跳现在发生在 POST **之前**（要和塌同一次提交），
        // 所以写失败时它已经跳掉了：行回到列表、错误条也弹了，而展开区开在
        // 下一个岗上 —— 用户看到的是三样对不上的东西。回到他点的那一个。
        if (on) setSelectedId(id);
        setSaveError(err.message || "没写进去");
      },
    );
  };

  // 标「职位已下线」。与 `exclude` 分开：那是本机可以离线记的判断（静态模式下
  // 落 localStorage），而「已下线」是**盘上的事实**，只有服务在时才写得了——
  // 没有服务就不给这个按钮，而不是记一个刷新就没的假状态。
  const expire = (id: string) => {
    if (!live) return;
    setSaveError("");
    // 标完这一行就从名单里消失了，把展开挪到下一条——连着清理已下线的岗时，
    // 每标一个都要重新找位置是最累的部分。
    const next = nextInList(id);
    postExpire(id).then(() => refreshAnd(next)).catch((err: Error) => {
      setSaveError(err.message || "没写进去");
    });
  };

  /**
   * 名单里紧跟在 `id` 后面的那个岗——它马上要顶上被移除的那一行。
   *
   * 在**当前可见的那份列表**里找（主表或「可以考虑」折叠区），不跨列表跳：
   * 用户在哪一段里清理，就顺着那一段往下走。最后一行被移除时退回上一行；
   * 整段清空就返回空串（收起，不硬找一个）。
   *
   * 这里能奏效是因为 `Shortlist` 已经有一个挂在 `selectedId` 上的效果：
   * 展开后把那一行滚回视口顶部。选中一换，滚动就跟着走，不必另写一套。
   */
  function nextInList(id: string) {
    for (const list of [mainList, restList]) {
      const i = list.findIndex((j) => j.id === id);
      if (i >= 0) return list[i + 1]?.id ?? list[i - 1]?.id ?? "";
    }
    return "";
  }

  // 「可以投的岗位」只放真的可以投的。判词是「跳过」「不建议」的岗混在里面，
  // 会让这份名单从 19 条涨到 72 条——用户滚半天，看到的多半是不该投的。
  //: 能进「可以投的岗位」的判词**只有这三个**。
  //
  // 原来这里是**黑名单**：`v === GATE_FAIL || v.includes("跳过") || v.includes("不建议")`
  // ——列出不许进的，其余一律放行。两天里被它漏进来两次：
  //
  //   「粗筛：待定」          新造的判词，不在黑名单里 → 混进主表最显眼处
  //   「不满足硬性条件 (学历)」 带了门名后缀，`=== GATE_FAIL` 精确匹配落空 → 硬门没过的岗进了可投名单
  //
  // 用户 2026-08-13：「这个的规则应该更改，应该控制，而不是有新规则都能进入」。
  // **默认放行是错的方向**：判词是人写的自由度很高的字段，加一档、加个后缀、
  // 改个措辞都是常事，而每一次变动的默认后果都是「混进最显眼的那张表」。
  // 白名单反过来——不认识就不进，代价是漏掉一个岗（看得见、能查），
  // 而不是把不该投的摆到第一行（看不见、会浪费一次投递）。
  const SELLABLE = ["强匹配", "值得投", "可以考虑"];
  /** 能不能进「可以投的岗位」。**白名单：不认识就不进。** */
  const canSell = (v: string) => SELLABLE.includes(plainVerdict(v));
  /**
   * 出局：进不进搁置区。**黑名单，且容后缀。**
   *
   * 和 `canSell` 不是一个问题的反面：一个硬门没过的岗不进可投名单（`canSell` 假），
   * 但它**已经投出去**时不该被塞进搁置区（`isOut` 也假）——搁置区是「不打算投的」，
   * 不是「所有没进名单的」。判词认不出来的岗同理：不进名单，也不进搁置区，
   * 就让它待在已投/漏斗那边，别凭空替用户下结论。
   *
   * 后缀容错是这次的直接教训：`v === GATE_FAIL` 遇上「不满足硬性条件 (学历)」落空。
   */
  const isOut = (v: string) => {
    const p = plainVerdict(v);
    return p.startsWith(GATE_FAIL) || p.startsWith("硬门")
      || p.includes("跳过") || p.includes("不建议");
  };
  // 同一个岗在别处的重复挂法（dupOf 指向主条目）不单独占行——研究一遍就够了。
  // 它们的链接和薪资在主条目的详情里列出。
  // 流水线那几格原来是**假按钮**：渲染成 <button>、屏读器播报成按钮、键盘能聚焦，
  // 按下去却什么都不发生。而它们本该是这一页最自然的导航——「下一步」说
  // 「材料就绪，去投递」，那 5 个岗却埋在 54 行里要自己一行行找。
  // 把后三格接成真筛选：引导说什么，点一下就能到那儿。
  const [funnel, setFunnel] =
    useState<"" | "materials" | "ready" | "applied" | "interview">("");
  const FUNNEL_OF: Record<number, typeof funnel> = {
    3: "materials", 4: "applied", 5: "interview",
  };
  // 筛选**不在这边判**，直接看导出时算好的 `funnels`。
  // 原来这三条各写各的，和 Python 那三个计数全对不上：材料就绪的数含已投的、
  // 筛选又排除已投的；已投递数的是台账行数、筛的是匹配上的岗；面试中的数认
  // hired、筛不认。而流水线格子是**可点开的**，数字必须等于点开看到的行数。
  // 三处都要等真有投递才显形——所以在页面能记状态之前，谁也没发现。
  const matchFunnel = (j: Job) =>
    funnel === "" || (j.funnels ?? []).includes(funnel);


  // **投过的岗不进「可以投的岗位」。** 这份名单回答的是「现在还能投谁」，
  // 而一个已经投出去的岗——不管是在等回复、还是已经挂了/没下文——都不在这个答案里。
  //
  // 原来只给它挂一枚「已投」小标就留在名单里。那是半个修法：标记解决了「哪一个投了
  // 看不出来」，却没解决**标题在说谎**。实测用户点完「我投了」再点「没下文」，
  // 那一行照旧躺在「可以投的岗位」里，原话是「怎么该项还在可以投」。
  //
  // 只在**没开筛选时**排除：点了流水线的「已投递 / 材料就绪 / 面试中」就是专门来看
  // 它们的，那时必须显示——而且 Python 侧的计数口径是「材料就绪含已投的」，
  // 格子里的数字必须等于点开看到的行数。
  const applied = (j: Job) => Boolean(j.applied);
  //: 真正「现在还能投」的那些——不看流水线筛选。`shortlist` 在它上面再叠筛选；
  //: 「前 N 个备了几份材料」也从它数。三处共用的那四条见下面的 `inPlay`。
  //: 已下线的岗（`expired`）在这四条里都要排掉：它不是「不合适」，是**没了**。
  //: 导出器保留它只为了能在搁置区放回来，任何名单与计数都不该算它。
  //: **这四条是所有「还在场上」判断的共同底**，只写这一处。
  //:
  //: 它原来被抄了三份（`sellable` / `shortlist` / `isAppliedRow`）。
  //: 下面那段注释记着这个形状犯过一次：「另有 5 个已投出去」点开只有 3 行 ——
  //: 计数用黑名单、名单用白名单，两边对不上。**当时的修法是再抄一份对齐**，
  //: 于是同一个底变成了三份：往任何一份里加第五个条件，另外两份都不会跟。
  const inPlay = useCallback(
    (j: Job) => !j.dupOf && canSell(j.verdict) && !excluded.has(j.id) && !j.expired,
    [excluded],
  );
  const sellable = useMemo(
    () => jobs.filter((j) => inPlay(j) && !applied(j) && !justActed.has(j.id)),
    [jobs, inPlay, justActed],
  );
  //: 已经投过的公司（归一化）。跟着快照走，不缓存——投完一个就该立刻生效。
  const appliedCos = useMemo(() => appliedCompanySet(jobs), [jobs]);
  //: 关键词只归一化一次（见 `hidden.ts` 的 compile）。
  const hidePrefs = useMemo(() => compile(hidden), [hidden]);

  //: 后三格的实际行数——**按当前生效的过滤链现算**，不用导出时那个数。
  //:
  //: `funnels_of` 的注释写着「计数和筛选共用这一个判断」，而 2026-08-19 加的
  //: 「这几类岗要不要看」（prefs）是**后来叠上去的一层**，只作用在列表、
  //: 没作用到格子。实测：关掉「猎头代招」后「材料就绪」仍显示 146，
  //: 点开只有 77 行——差 69 行，正是那条注释警告过的形状又犯了一次。
  //:
  //: 只算后三格：前两格（搜到职位/打过分）不接筛选，本来就是整库口径。
  const funnelCounts = useMemo(() => {
    const c: Record<string, number> = { materials: 0, ready: 0, applied: 0, interview: 0 };
    for (const j of jobs) {
      if (excluded.has(j.id) || !passesPrefs(j) || isHidden(j, hidePrefs, appliedCos)) continue;
      for (const f of j.funnels ?? []) if (f in c) c[f] += 1;
    }
    return c;
  }, [jobs, excluded, passesPrefs, hidePrefs, appliedCos]);

  const shortlist = useMemo(
    () => jobs.filter((j) => inPlay(j) && matchFunnel(j)
                            && !(funnel === "" && applied(j))
                            // 「已投递」视图下**不滤**——那时它恰恰该出现在这里
                            && !(funnel !== "applied" && justActed.has(j.id))),
    [jobs, inPlay, funnel, justActed],
  );

  // ── 头部几个岗的材料备得够不够 ──
  //
  // 实测：可以投的岗位 145 个，**前 20 里只有 2 个有材料**。名单再长也没用——
  // 真要投的那一刻，材料不在手上就投不出去，而出一份材料要走完整条 `/job-apply`
  // （深评、公司调研、审稿、Typst 编译），不是点一下就有的。
  //
  // 所以这里不只报数字，**要给出那条能敲的命令**（面板的通例：每处引导都写出命令，
  // 别让用户自己猜该敲什么）。命令是 `/job-apply --top N`，它自带一道闸门：
  // 深评不过的岗只落评估、不出材料，不把最贵的那段花在不该投的岗上。
  const TOP_N = 20;
  // 低于这个数就提示。5 是「够投一轮」的量级。
  //
  // **这个 5 和 Python 侧 `build_dashboard.SHORTLIST_FLOOR` 是同一个数**——
  // 那边管「名单快见底了，去补货」，这边管「材料缺口」，问的是同一件事：
  // 手上够不够投一轮。改一处必须改两处，
  // `tests/test_one_number_per_concept.py::EnoughToKeepGoingHasOneDefinition` 钉着。
  const MATERIALS_FLOOR = 5;
  const topReady = useMemo(() => {
    const top = [...sellable]
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
      .slice(0, TOP_N);
    return {
      size: top.length,
      ready: top.filter((j) => j.materials).length,
      // **这前 20 名里有多少是粗筛分。**
      //
      // 分数把两种深度混着排了：粗筛分只看标题和卡片字段，深评分读过 JD 正文。
      // 实测 2026-08-22：这前 20 名里 **14 个是粗筛**（最高的那个 72 分连 JD
      // 都没读），而深评过的「值得投」最高才 66 —— 于是「有材料的 0 个」这句话
      // 看着像名单全空，可同一屏的短名单上明明有 4 行挂着「材料就绪」。
      //
      // 不改排序（粗筛分是现有的唯一排序依据，换掉是另一件事），
      // **但要说清这个 0 是怎么来的** —— 也正好解释了为什么该跑 `--top 20`：
      // 那条命令干的就是把这批猜测变成读过 JD 的评估。
      raw: top.filter((j) => !j.evaluated && !j.jdRead).length,
    };
  }, [sellable]);
  //: 名单本身太短时不提示——只有 3 个可投的岗，「前 20 里只有 2 个有材料」是句废话。
  const materialsThin =
    topReady.size >= MATERIALS_FLOOR && topReady.ready < MATERIALS_FLOOR;
  //: **手上已经备好、还没发出去的**。上面那个 `topReady.ready` 是局部数
  //: （只看分最高的 20 个），而屏幕上那句「只有 0 个备好了材料」是这一页
  //: 关于材料的**唯一一句话** —— 读起来就是「我什么都没有」。
  //:
  //: 实测 2026-08-23：前 20 里确实 0 个，而全表 **62 个岗材料是齐的**
  //: （58 个在「可以考虑」那一档、4 个「值得投」），中位放了 3 天、最久 6 天。
  //: 它们不是积压，是**随时能发的存货** —— 而发出去是整条流水线里唯一
  //: 要人做的那一步（`AGENTS.md`「只有一处要人：投出去那一下」）。
  //: 一个局部的 0 盖住一个全局的 62，指的方向正好反了：它让人去补材料，
  //: 而该做的是先把手上这批发掉。
  const readyToSend = useMemo(
    () => sellable.filter((j) => j.materials && !applied(j)).length,
    [sellable, applied],
  );
  //: 批量跑下来卡住的岗。不看筛选、不看已投——它们是待办，不是名单的一部分。
  const blocked = useMemo(() => jobs.filter((j) => j.blocked?.需要), [jobs]);
  //: 默认视图里因为「已投过」而被收起来的那些。数量要说出来——一行凭空消失
  //: 和「我的数据丢了」在用户那里是同一件事。
  //
  //: **判据必须和点开之后看到的那批逐字一致。** 这个数是可点的，点下去就是
  //: `setFunnel("applied")`，那时 `shortlist` 用的是白名单 `canSell` 加
  //: `funnels` 里有没有 `applied`。这里原来用黑名单 `!isOut` 加 `applied(j)`
  //: 数——导出侧对没有 rank_verdict 的岗会填 `"已评分"`（见 export 的
  //: `verdict or "已评分"`），它 `isOut` 假、`canSell` 也假：**进得了这个数，
  //: 进不了那份名单**。于是「另有 5 个已投出去」点开只有 3 行，正是本文件
  //: 上面 funnels 那段注释写的「数字必须等于点开看到的行数」又犯一次。
  const isAppliedRow = (j: Job) =>
    inPlay(j) && (j.funnels ?? []).includes("applied");
  const hiddenApplied = useMemo(
    () => jobs.filter(isAppliedRow).length,
    [jobs, inPlay],
  );
  const shelved = useMemo(
    () => jobs.filter((j) => !j.dupOf
                            && (isOut(j.verdict) || excluded.has(j.id) || j.expired)),
    [jobs, excluded],
  );

  // 「可以投的岗位」原来是一条 54 行的长队，而工具**已经知道**它们分三档：
  // 强匹配 1 · 值得投 22 · 可以考虑 31。把三档摊平成一个数，新用户看到的是
  // 「有 54 个要看」，于是往下滚 4391px（全页 85%）——它告诉了你先投哪个，
  // 却没告诉你什么时候可以停。
  //
  // 这一页别处都很克制：不投的岗位折叠、命令表折叠、简历块没内容就不渲染。
  // 唯独最长的那张表没有停止点。
  //
  // **没有「值得投」以上的岗时不切。** 那时主表会空着、内容全躲进折叠里，
  // 而主表的空状态说的是「还没有职位可以看——下一步是去找岗」，那是错的：
  // 岗有的是，只是都在「可以考虑」这一档。切分只在它真能帮上忙时才发生。
  const maybeOnly = (j: Job) => plainVerdict(j.verdict) === "可以考虑";
  //: 屏蔽在**切档之前**做，两档的数才都对。切完再滤会让「可以考虑」那档的
  //: 计数漏掉被藏起来的，两个数对不上。
  //: **必须 useMemo。** 原来是裸函数调用，于是每次渲染（包括每敲一个字）
  //: 都把 1200 个岗过一遍全部关键词——实测关键词加到 50 多个时渲染进程直接无响应。
  const visible = useMemo(
    () => shortlist.filter((j) => passesPrefs(j) && !isHidden(j, hidePrefs, appliedCos)),
    [shortlist, hidePrefs, appliedCos, passesPrefs]);
  //: 藏了几个要说出来——一个开着的筛选器最危险的失败模式是用户忘了它开着。
  const hiddenCount = shortlist.length - visible.length;
  const worth = visible.filter((j) => !maybeOnly(j));
  const cut = worth.length > 0;
  const mainList = cut ? worth : visible;
  const restList = cut ? visible.filter(maybeOnly) : [];
  //: 「可以考虑」那一档里有几个是**具名公司的直招**。
  //:
  //: 这个数存在，是因为面板此前在同一屏上说了两句对不上的话：投后统计说
  //: 「与其再投一个，不如在这些具名公司里找个能说上话的人」——而它同时递上来的
  //: 「值得投」名单里**一个具名公司都没有**（实测 2026-08-22：9 个里 8 个猎头代招、
  //: 1 个具名，而 43 个具名直招岗全压在「可以考虑」那一档）。
  //: 内推这条路只对具名公司成立，所以「那批在哪」必须说得出来，
  //: 否则上面那句建议就是一句没有落点的话。
  const namedDirectInRest = restList.filter(
    //: `=== false` —— 「没判过」的岗不算具名直招（内推够不够得着，
    //: 取决于它到底是不是猎头挂的，而那正是没判的那件事）。
    (j) => j.viaHeadhunter === false && !j.anonymousEmployer
      && (j.company || "").trim(),
  ).length;

  //: 搁置区那 2000 多行是**五类**东西，动作差得很远。
  //:
  //: 标题那句原来列了四类（硬性条件没过、方向不对、分太低、已下线）——
  //: **漏掉的两类恰恰是带「放回可以投」按钮的那两类**：规则判的（实测 719 个，
  //: 而规则最容易错）和他自己点的（93 个）。一个 2105 的总数配四个笼统的词，
  //: 读者不知道里面有七百个一句话就能捞回来的。
  //:
  //: 判据和逐行那枚戳同源（`expired` / `skipped` / `ruleSkipped` / 判词），
  //: 顺序按「能不能回头」排：能放回的在前。
  const shelfKinds = useMemo(() => {
    const k = { rule: 0, mine: 0, gate: 0, low: 0, gone: 0 };
    for (const j of shelved) {
      const v = plainVerdict(j.verdict);
      if (j.expired) k.gone += 1;
      else if (j.skipped) k.mine += 1;
      else if (j.ruleSkipped) k.rule += 1;
      else if (v.includes("不满足硬性条件")) k.gate += 1;
      else k.low += 1;
    }
    return k;
  }, [shelved]);

  //: 这一档里**真没读过 JD** 的有几个。判据同逐行那枚「没读 JD」硬章
  //: （`!evaluated && !jdRead`），两处必须用同一条——不然标题说 142、
  //: 点开数出来是别的数。
  //:
  //: **原来只看 `evaluated`，那是错的。** 粗筛也会读完整 JD（来源写着
  //: 「粗筛（读过 JD 正文）」），它只是没做公司调研与双角色审稿。实测
  //: 2026-08-26：没深评的 1429 个里 946 个其实读过 JD —— 按旧判据，
  //: 这行字会把它们全数说成「还没读过 JD」。
  const nRestRaw = restList.filter((j) => !j.evaluated && !j.jdRead).length;
  //: 这一档里**判断该重跑**的有几个。逐行有那枚「该重跑」的章兜着，
  //: 可这一整档是**折叠起来的** —— 章在折叠后面等于没标：顶上那句
  //: 「N 个岗的判断该重跑一遍」照样落不到具体哪几个。
  //:
  //: 实测 2026-08-30：那 7 个**全部**落在这一档（45-53 分的「可以考虑」），
  //: 首屏一个都看不到。这和上面 `nRestRaw` 那条是同一件事、同一种解法：
  //: **这行字是他决定「要不要点开」时唯一读到的东西**，该说的都得在这儿说。
  const nRestStale = restList.filter((j) => j.restale).length;
  const restScores = restList
    .map((j) => j.score)
    .filter((n): n is number => n !== null);

  // 推荐 = 名单里分最高的那一个。工具的职责是给出「先投哪个」，不是只排个序。
  //
  //: **「名单」指的是屏幕上那份（`visible`）**，不是叠屏蔽之前的 `shortlist`。
  //: 拿 `shortlist` 算时，被屏蔽的岗照样能当选，而它那一行根本不渲染——
  //: 于是整页一个「先投这个」的标记都没有，用户不知道是没推荐还是标记坏了。
  const recommended = useMemo(
    () =>
      visible.reduce<(typeof visible)[number] | null>(
        (best, j) =>
          j.score !== null && (best === null || (j.score ?? -1) > (best.score ?? -1))
            ? j
            : best,
        null,
      ),
    [visible],
  );

  // 数据是异步来的，选中项要跟着推荐走一次；用户点过之后就不再自动改
  // 进页面时**不预先展开任何一行**：先看全貌，要看细节自己点。
  // 预展开第一行会把下面 18 行推到屏幕外，反而看不到名单。
  const [selectedId, setSelectedId] = useState("");
  //: 校验对象必须是**真正渲染出来的那份**（`visible`），不是叠屏蔽之前的 `shortlist`。
  //: `mainList ∪ restList` 恰好等于 `visible`（`cut` 的两支都成立），所以只有它对得上屏幕。
  //:
  //: 拿 `shortlist` 校验时漏的是这条路径：展开一个岗 → 在「这几类岗要不要看」里关掉
  //: 它所属的那一类（或把它公司加进屏蔽词）→ 那一行从名单里消失，而 `selectedId`
  //: 还指着它。展开态没人收，等他把那一类打开，那一行**已经是展开的**——
  //: 他没点过。`Shortlist` 内部那道收起闸只认自己的搜索框（`kw`/`channel`），
  //: 看不见 App 这一层的屏蔽，两层各管各的那一半。
  const effectiveId = visible.some((j) => j.id === selectedId) ? selectedId : "";

  // ok === null 是「不由本仓库决定」，**不算缺失**（浏览器能力由 AI 工具提供）
  const missing = envItems.filter((e) => e.ok === false);
  // **可选项也不算。** pdftotext / Bun 不装完全能用，算进「还差几项」会让新用户
  // 以为出了大问题，然后去装一堆不需要的东西。单页版一直守着这条；网页版原来
  // 守不住，因为导出器把 `optional` 字段丢了，这边只能按 `ok === false` 数。
  const need = missing.filter((e) => !e.optional);
  const optMissing = missing.filter((e) => e.optional);


  //: 「招聘网站」那颗按钮要不要点亮，以及点亮时写哪一句。
  //
  //: **这几句话原来长在折叠标题里。** 那是 2026-08-21 那次事故的修法：猎聘 CLI
  //: 封了 9 小时，面板上一个字都看不到，因为整块都在收起来的折叠区里。当时的
  //: 结论写在下面「招聘网站」那一块的注释里 ——「要顶到最上面，不能只在自己
  //: 那一行里加个小字」。（这里**不写那个块的 key 字面量**：两条测试拿它当锚点
  //: 去切窗口，注释里再出现一次就把窗口切到注释上了。同一个自陷本仓库栽过五次。）
  //
  //: 落点变过两次：折叠标题 → 抽屉外那颗固定按钮 → 现在这一排文字按钮。
  //: **这一排就在「下一步」下面，本来就在首屏** —— 比原来那个要滚到第三屏才
  //: 露头的折叠标题更靠前。
  //
  //: 这一句只决定「点不点亮」，按「要你做点什么」排序：被平台拦住 > 要换出口 >
  //: 环境缺项。**具体印哪几枚标记走 `desks` 里那份 `chips`**（那里三枚分开，
  //: 包括「你自己关掉了一家」—— 它不进这一句，因为那不是待办）。
  //
  //: ⚠️ **CLI 那条原来排在环境缺项后面，措辞是「在限流冷却」。**
  //: 那是 2026-08-26「封控不再自动到期」之前的说法：那时它确实到点自己好，
  //: 归进「等一等」是对的。裁定之后**两条都要人动手**，只是动的不是同一件事
  //: （一个去过验证、一个换网络出口）—— `blockLabel` 当天就改了，
  //: 这一句和下面那枚标记没跟上。
  //
  //: 代价写在 `AGENTS.md`「「等」不是下一步」那一条里：猎聘限流那次，
  //: 工具连印三天「还剩约 8 小时」，用户照它等，而限的是这个出口的 IP ——
  //: **那句话三天里一直是对的，也一直没用。** 把「要换出口」降级成「等着」，
  //: 是同一个错的另一半。
  const blockedNeedsYou = portals.filter((p) => p.blocked && blockNeedsYou(p));
  const blockedNeedsIp = portals.filter((p) => p.blocked && !blockNeedsYou(p));
  const settingsAlarm =
    blockedNeedsYou.length
      ? `${blockedNeedsYou.map((p) => p.name).join("、")} 被拦住了`
      : blockedNeedsIp.length
        ? `${blockedNeedsIp.map((p) => p.name).join("、")} 要你换个网络出口`
        : need.length
          ? `还差 ${need.length} 项要装`
          : "";

  //: ⚠️ **这两个 hook 必须留在下面那个提前 `return` 之前。**
  //: 第一版放在了它后面 —— `snap === null` 那一支先 return，hook 调用次数
  //: 就跟着数据状态变，React 直接不渲染：实测页面整个空白（`#root` 零子节点、
  //: `document.body.innerText` 空串），而构建是绿的。
  //: **「下一步」拆成「首屏那一句」和「点开才看的理由」。**
  //:
  //: 切在**第一个句号**上。它切出来的是现状（「投出去 85 个，76 个已经过了
  //: 10 天，一个回音都没有。」），不是动作 —— 动作在旁边那颗命令上，
  //: 那才是他要敲的东西。两样并排，首屏就够他决定动不动手。
  //:
  //: **切不动就整段留在首屏**（没有句号、或第一句本身就很长）——
  //: 宁可长一次，也不要把一句话拦腰截断。60 是「一句话」的上限：
  //: 超过它说明那个句号不在该在的地方，切了反而更难读。
  const [nsHead, nsWhy] = useMemo(() => {
    const t = (nextStep.text || "").trim();
    const i = t.indexOf("。");
    if (i < 0 || i + 1 >= t.length || i + 1 > 60) return [t, ""];
    return [t.slice(0, i + 1), t.slice(i + 1).trim()];
  }, [nextStep.text]);
  const [nsOpen, setNsOpen] = useState(false);

  if (snap === null) {
    return (
      <ConfigProvider theme={cockpitTheme} locale={zhCN} button={cockpitComponents.button}>
        <div className="cockpit">
          {/* 这句话会停在这儿很久（数据两兆多，本机实测浏览器里约 7 秒），
              所以它得说清「在等什么」——否则用户分不清是在加载还是卡死了。
              ⚠️ 别写「2.4 MB」：字母单位夹在中文句子里会被措辞守卫判成
              散落英文（`test_web_copy` 那条）。说「两兆多」就够。 */}
          <p className="loading">
            正在读取本机数据…（两兆多，等十几秒）
          </p>
        </div>
      </ConfigProvider>
    );
  }

  //: 读到了、但那份是**演示数据**，而 `loadError` 说清了为什么。
  //:
  //: 原来这条路上直接把演示数据铺开：110/23/3 与 5 个虚构职位，每一处都长得
  //: 像真的。页头那行「演示数据（虚构）」是诚实的，但要用户**注意到**它 ——
  //: 而他刚打开页面，正等着看自己的进度。
  //:
  //: 这里只拦**服务端接上了却没交出数据**那一种（500 / 正文断在半路 / 超时）。
  //: 服务压根没起时演示数据是一份正当的首次体验，下面 `isRealData` 的横幅管它。
  if (snap.loadError) {
    return (
      <ConfigProvider theme={cockpitTheme} locale={zhCN} button={cockpitComponents.button}>
        <div className="cockpit">
          <p className="loading">读不到本机数据：{snap.loadError}</p>
          {/* 刻意不用 `sec-note`：那是段头旁注的样式（配 `{(\w+).length > 0 && (`
              那道守卫），而这里是一个整屏的失败态，套段头样式会让
              `test_the_column_legend_waits_for_rows` 的锚点落到这里。 */}
          <p>
            面板要连着本机服务才有数据。先确认它还在跑，跑不起来就重开一次：
          </p>
          <Cmd>python tools/serve.py</Cmd>
        </div>
      </ConfigProvider>
    );
  }


  //: 那一排按钮：`key` · 按钮上的名字 · 那句结论 · 弹窗标题 · 有没有内容。
  //
  //: **每颗按钮都带一句结论，不点开也看得见。** 这几句原来长在折叠标题里，
  //: 是逐条推敲过的（「上次审于 X，之后改过没再审」不是「上次审于 X」；
  //: 「有回音 0%」在还没到时候时要说「还没有」）—— 换成按钮不能把它们丢掉，
  //: 否则这一排就成了七个没有信息的词。
  const desks: {
    key: string; name: string; note: string; title: string;
    alarm?: string; chip?: string; show: boolean;
    /** 按钮上那几枚标记。`tone`：`alarm` 要你处理 ·
     *  `off` 你自己关的（不是待办，是让那个决定看得见代价）。
     *
     *  **原来还有一个 `wait`（「等它自己好」）。** 2026-08-26 裁定封控不再自动
     *  到期之后，这一屏上**没有任何东西是等的**了 —— 两种封控都要人动手，
     *  只是动的不是同一件事，那个差别由**文案**承担（「被拦住了」/
     *  「要你换个网络出口」），不再由颜色承担。
     *
     *  留着一个没人用的「等着就行」色，下一个人会拿它去标别的东西 ——
     *  而 `AGENTS.md`「「等」不是下一步」正是不许在待办面上给「等」留位置。 */
    chips?: { text: string; tone: "alarm" | "off" }[];
  }[] = [
    {
      key: "portals", name: "招聘网站", show: portals.length > 0,
      title: "从哪些招聘网站找岗",
      note: `${portals.filter((p) => p.enabled).length} / ${portals.length} 个在用`,
      alarm: settingsAlarm,
      // 「3 / 4 个在用」说不出「有一家是被平台拦住的」—— 那是「你要不要去做点
      // 什么」，和「你自己关掉了一家」是两回事。**而「要你做点什么」和「等它
      // 自己好」也是两回事**：两种封控共用一句「被拦住了」，用户处理完那条要
      // 他处理的、回来看到的还是同一句，会以为白点了（2026-08-21 实测）。
      chips: [
        ...(portals.some((p) => p.blocked && blockNeedsYou(p))
          ? [{ tone: "alarm" as const,
               text: portals.filter((p) => p.blocked && blockNeedsYou(p))
                            .map((p) => p.name).join("、") + " 被拦住了" }]
          : []),
        // **这一枚原来是 `tone: "wait"` + 「在限流冷却」。** 2026-08-26 裁定
        // 封控不再自动到期之后，它就不是「等它自己好」了 —— 要用户换网络出口
        // （`blockLabel` 说的就是这句）。`wait` 的色和字都在说「不用管」，
        // 而这条不动手它永远不会好。
        ...(portals.some((p) => p.blocked && !blockNeedsYou(p))
          ? [{ tone: "alarm" as const,
               text: portals.filter((p) => p.blocked && !blockNeedsYou(p))
                            .map((p) => p.name).join("、") + " 要你换个网络出口" }]
          : []),
        // **自己关掉的那家，也要把价钱摆出来。** 上面两枚说的是「平台拦你」，
        // 这一枚说的是「你关了它」—— 不是催他打开（那是他的决定），是让那个
        // 决定看得见代价。实测活动用户 2026-08-23：猎聘关着，而它供了库里
        // 2232/2638 个岗（85%）、9 个可投里的 8 个，而「3 / 4 个在用」
        // 一个字都说不出这件事。
        // **只在它确实还抓得动时才说**（`canScrape` 且没被拦）：一个既关着
        // 又封着的渠道，说「关着」会盖住「封着」，而后者才是要他做点什么的。
        ...(portals.some((p) => !p.enabled && !p.blocked && p.canScrape
                                && p.jobs > 0)
          ? [{ tone: "off" as const,
               text: portals
                 .filter((p) => !p.enabled && !p.blocked && p.canScrape
                                && p.jobs > 0)
                 .map((p) => {
                   const all = portals.reduce((n, x) => n + x.jobs, 0);
                   const pct = all ? Math.round((p.jobs / all) * 100) : 0;
                   return pct >= 10
                     ? `${p.name} 你关着（占库里 ${pct}%）`
                     : `${p.name} 你关着`;
                 })
                 .join(" · ") }]
          : []),
        // 手机 APP 刷新提示：网页端无法刷新的平台（如 BOSS、前程无忧）今天还没刷
        ...(portals.some((p) => p.enabled && p.webRefresh === false && p.resumeStale !== 0)
          ? [{ tone: (portals.some((p) => p.enabled && p.webRefresh === false && (p.resumeStale ?? 0) >= (snap?.resumeStaleDays ?? 14))
                       ? "alarm" as const : "off" as const),
               text: portals.filter((p) => p.enabled && p.webRefresh === false && p.resumeStale !== 0)
                            .map((p) => p.name).join("、") + " 需开 APP 刷新" }]
          : []),
      ],
    },
    {
      key: "jobprefs", name: "岗位类型", show: jobPrefs.length > 0,
      title: "这几类岗要不要看",
      note: jobPrefs.filter((p) => !p.enabled).length === 0
        ? "都看"
        : `关了 ${jobPrefs.filter((p) => !p.enabled).length} 类`,
    },
    {
      key: "env", name: "要装的工具", show: need.length > 0,
      title: "要装的工具",
      // 可选的没装顺带说一句 —— 既然人已经要去装东西了，一次装齐。
      note: `还差 ${need.map((e) => e.name).join("、")}`
            + (optMissing.length
               ? `（另有 ${optMissing.length} 个可选的没装，不影响正常使用）` : ""),
      alarm: `还差 ${need.length} 项`,
    },
    {
      key: "baseresume", name: "你的简历", show: !!snap.baseResume,
      title: "你的简历",
      // **「上次审于 2026-08-01」读起来是安心，而它可能是假的**：简历在那之后
      // 改过，报告审的是一个已经不存在的版本，现在这份从没被审过。
      // 实测活动用户 2026-08-23：报告 08-01，简历 08-12。这半句必须留在按钮上。
      note: snap.baseResume
        ? (snap.baseResume.audit
            ? `上次审于 ${snap.baseResume.audit.date}`
              + (snap.baseResume.audit.stale ? "，之后改过没再审" : "")
            : "还没审过")
        : "",
      chip: snap.baseResume?.pdfStale ? "PDF 是旧的" : undefined,
    },
    {
      key: "resume", name: "市场怎么读你的简历", show: !!snap.resumeInsight,
      title: "市场怎么读你的简历",
      note: snap.resumeInsight
        ? `行业对口 ${snap.resumeInsight.sweetSpot.count} 个岗`
          + (snap.resumeInsight.blockers[0]
             ? ` · 挡你最多的是${snap.resumeInsight.blockers[0].name}`
               + `（${snap.resumeInsight.blockers[0].n}）`
             : "")
        : "",
      chip: (() => {
        const n = (snap.resumeInsight?.sweetSpot.asks ?? [])
          .filter((a) => a.inResume === false).length;
        return n > 0 ? `简历待补 ${n}` : undefined;
      })(),
    },
    {
      key: "ostats", name: "投出去的那些", show: (snap.outcomeStats?.total ?? 0) > 0,
      title: "投出去的那些怎么样了",
      // `?? 0` 会把「还没到时候」印成「0%」—— 判据与措辞都在 `sayRate`。
      note: snap.outcomeStats
        ? `投了 ${snap.outcomeStats.total} 个 · 有回音 `
          + sayRate(snap.outcomeStats.repliedRate)
        : "",
    },
    {
      // HR 聊天框里反复问的那几句。**排在命令表前面**：它是每天都要用的东西，
      // 而命令表是想不起来时才翻的。
      key: "hrqa", name: "HR 常问的",
      show: (snap.hrAnswers ?? []).length > 0,
      title: "HR 常问的那几句",
      note: (() => {
        const all = snap.hrAnswers ?? [];
        const n = all.filter((x) => x.empty).length;
        return n ? `${all.length} 条 · 还有 ${n} 条没写` : `${all.length} 条都写好了`;
      })(),
      // 没写的那几条要点亮按钮 —— HR 问到时手上没说法，那是待办不是提示。
      alarm: (snap.hrAnswers ?? []).some((x) => x.empty)
        ? `${(snap.hrAnswers ?? []).filter((x) => x.empty).length} 条没写` : "",
    },
    {
      // **还没建过档的人不进这一排。** 他最需要这张表，而这一排的前提是
      // 「你已经知道自己在看什么」。原来那版折叠对这类用户是默认展开的
      //（`defaultActiveKey={activeUser ? [] : ["cmds"]}`）—— 换成按钮之后
      // 那个照顾就没了，而自动弹一个 Modal 比不弹更糟。所以这一档改成**内联**：
      // 见下面 `firstRun` 那一段。
      key: "cmds", name: "能敲哪些命令",
      // **新用户也给这颗。** 上面那份摊开的只剩脊梁三条，全集就得有地方进；
      // 原来这里挡着 `!!activeUser`，是因为那时摊开的就是全集，两份重复。
      show: (snap.commands ?? []).length > 0,
      title: "能敲哪些命令",
      note: live
        ? "记状态在这一页点就行，要动脑子的才回命令行"
        : "这一页只显示，干活都在命令行",
      chip: `${(snap.commands ?? []).reduce((n, g) => n + g.items.length, 0)} 条`,
    },
  ].filter((d) => d.show);

  return (
    <ConfigProvider theme={cockpitTheme} locale={zhCN} button={cockpitComponents.button}>
      <AntApp>
        <CodeToolProvider initialTool={snap.detectedTool}>
          <div className="cockpit">
          <header className="mast">
            <span className="mast-word">求职总览</span>
            <span className="kicker">全在你自己电脑上跑，数据不上传</span>
            {/* 演示数据必须自己承认——否则死链接和不存在的 PDF 会被当成真的 */}
            {/* 演示态其实有两种，指路不一样，混成一句会把新用户支使去跑一条
                注定失败的命令：还没建过用户时 `export_web_data.py` 直接退出 1
                （没有活动用户），叫他跑它等于让他撞一次错误再回来问。
                `activeUser` 为空就是「还没建过档」——那一步是 /job-setup。 */}
            {!snap.isRealData && (
              <span className="demo-flag">
                {/* **这三条命令要可复制。** 这是新用户看到的第一屏 ——
                    他要做的第一件事就是把 `/job-setup` 敲进去，而它原来是个
                    不可复制的行内 `<code>`，和同一页上「第 1 步 /job-scrape」
                    那些带复制按钮的块两种待遇。
                    用户 2026-08-21 点名说过「命令不明显」，顺着查出五处，
                    这三处在最要紧的位置上。 */}
                {activeUser ? (
                  <>
                    演示数据（虚构）· 链接与简历 PDF 都是假的，跑{" "}
                    <Cmd>python tools/export_web_data.py</Cmd> 换成你的真实数据
                  </>
                ) : (
                  <>
                    还没有你的资料，现在看到的是<b>虚构</b>演示数据。到命令行跑{" "}
                    <Cmd>/job-setup</Cmd> 建档，再跑 <Cmd>/job-scrape</Cmd>{" "}
                    {"找职位——这一页会自动换成你自己的数据。"}
                  </>
                )}
              </span>
            )}
            <div className="mast-user">
              <span className="kicker">当前用户</span>
              <b>{activeUser || "（还没建）"}</b>
              {/* 这个按钮原来**没有 onClick** —— 是个死按钮：既列不出这个 clone 下
                  有哪些用户，也不说怎么建第二个。而多人共用一份 clone 是
                  AGENTS.md 明确支持的用法。
                  切换与新建都留在命令行：`.active_user` 是**全局状态**，页面上点一下
                  改掉它，别的标签页和正在跑的命令都不知道自己已经换了人。
                  所以这里只做一件事——让人看得见有哪些用户、以及该敲什么。 */}
              <Button
                size="small"
                onClick={() => setUserPanel((v) => !v)}
                aria-expanded={userPanel}
              >
                换个用户
              </Button>
              {userPanel && (
                <div className="userpop" aria-label="切换或新建用户">
                  <p className="userpop-h">这个仓库里的用户</p>
                  <ul className="userpop-list">
                    {(allUsers ?? []).map((u) => (
                      <li key={u} data-active={u === activeUser}>
                        <span>{u}</span>
                        {u === activeUser ? (
                          <em>当前</em>
                        ) : (
                          <Cmd>{`/job-user ${u}`}</Cmd>
                        )}
                      </li>
                    ))}
                    {(allUsers ?? []).length === 0 && (
                      <li className="userpop-empty">还没有任何用户</li>
                    )}
                  </ul>
                  <p className="userpop-h">再建一个</p>
                  <Cmd>/job-user --new 名字</Cmd>
                  <p className="userpop-note">
                    {"每个人的资料、职位、投递记录都各自独立。" +
                     "命令在命令行里跑，跑完刷新这一页就换过来了。"}
                  </p>
                </div>
              )}
            </div>
          </header>

          <nav className="rail" aria-label="求职进度">
            {pipeline.map((s) => {
              // 前两格不接筛选：「搜到职位」含 73 个没上表的（待评/降权/已过期），
              // 点了给不出对应的行；「打过分」就是整张表本身。硬接会让点击结果
              // 与数字对不上——那比不能点更糟。
              const key = FUNNEL_OF[s.step];
              const on = Boolean(key) && funnel === key;
              // 「能不能点」只算一次。之前 disabled 算的是「没有筛选键**或**数为 0」，
              // 而 aria-label 只看有没有筛选键——于是 0 个的那两格是禁用的，读屏却
              // 念「0 个，只看这些」，等于给一个按不动的按钮许诺了一个动作。
              //: 格子上的数按当前过滤链现算，和点开看到的行数永远相等。
              //: 被过滤压低时把原数一并说出来——否则用户会以为岗位凭空少了。
              const shown = key ? funnelCounts[key] ?? s.count : s.count;
              const filtered = key ? s.count - shown : 0;
              const actionable = Boolean(key) && shown > 0;
              // 「下一步」点名的那一格高亮。**不另立一条判据**：谁被点名由
              // `next_step` 说了算，这里只按命令的头一个词对上号。于是顶上的
              // 五格和那句唯一的下一步永远指向同一件事，不会各说各的。
              const nudged =
                Boolean(s.cmd) && Boolean(nextStep.command) &&
                s.cmd!.split(" ")[0] === nextStep.command!.split(" ")[0];
              return (
              <div
                key={s.step}
                className="rail-cell"
                data-state={shown > 0 ? "active" : "zero"}
                data-filter={key ? (on ? "on" : "off") : undefined}
                data-nudge={nudged ? "on" : undefined}
              >
                <button
                  type="button"
                  className="rail-hit"
                  /* 那句说明从常驻改成只给当前格之后，其余四格的全文留在这儿 ——
                     「收起来」不等于「删掉」（同这一页对待折叠内容的一贯做法）。 */
                  title={s.does || undefined}
                  disabled={!actionable}
                  onClick={() => key && setFunnel(on ? "" : key)}
                  aria-pressed={key ? on : undefined}
                  aria-label={
                    actionable
                      ? `第 ${s.step} 步 ${s.label}：${shown} 个${
                          filtered > 0 ? `（另有 ${filtered} 个被你的筛选挡住了）` : ""
                        }，${on ? "取消筛选" : "只看这些"}`
                      : `第 ${s.step} 步 ${s.label}：${shown} 个`
                  }
                >
                  {/* 序号来自真实先后顺序（找→评→写→投→面），不是排版装饰 */}
                  <span className="rail-step" aria-hidden>
                    {s.step}
                  </span>
                  <div className="rail-v">{shown}</div>
                  <div className="rail-n">{s.label}</div>
                </button>
                {filtered > 0 && (
                  <p className="rail-filtered">
                    另有 {filtered} 个被你在「这几类岗要不要看」里关掉了
                  </p>
                )}
                {/* 「投了多少」这一页有两个数：这一格走 funnels（排掉搁置区的），
                    「投出去的那些」那颗按钮走投递记录行数。差在哪儿要说出来 ——
                    否则用户只能自己猜哪个是真的。说法在导出器里现拼（`parkedNote`）。 */}
                {s.parkedNote && (
                  <p className="rail-filtered">{s.parkedNote}</p>
                )}
                {/* 这一格在做什么 + 该敲什么。命令在**按钮外面**——套在按钮里
                    既是嵌套可交互元素，点「复制」还会顺手触发筛选。

                    **只给「现在轮到的那一格」。** 五格全带这两行时，这一条
                    2026-08-24 实测占 222px —— 是首屏最高的一块，而
                    「可以投的岗位」要滚到 831px 才开始。五条说明里，
                    有四条讲的是他这一刻不做的事。
                    没删任何一条：`title` 里全文照旧，鼠标停上去就有；
                    弹窗那边的「能敲哪些命令」也一条不少。
                    判据不新造：`nextStep.command` 指的就是现在该敲的那条，
                    它本来就在这一页的最上面 —— 两处指同一件事，不许各判各的。 */}
                {/* **每一格都留着「该敲什么」，只把那两行散文收进悬浮提示。**

                    原来这里是「说明两行 + 命令」（`rail-guide`）。五格是等高
                    栅格，那 96px 把每一格都撑到 220px —— 实测 2026-08-24，
                    「可以投的岗位」要滚到 1061px 才开始。

                    **但命令不能跟着散文一起收走。** `test_pipeline_counts` 那条
                    守的就是这件事，理由是实测来的：用户问「可以投的不多了，
                    怎么让你继续抓取」时，五格就在他眼前，而**每一格该敲什么
                    从来没写在格子上**。所以这一版留命令、收散文：
                    命令一行 ≈ 22px，散文进 `title`（上面那个按钮）。 */}
                {/* **还敲不动的格子不给命令。**

                    新用户那一屏实测 2026-08-24（拿一份空快照渲染）：五格全是 0，
                    却各挂一条命令 —— `/job-rank`「给抓到还没评的打分」、
                    `/job-apply`「给想投的岗出材料」…… **一条都敲不动**（没资料、
                    没岗），而正确答案只有一条 `/job-setup`，它就在下面那句
                    「下一步」里。`AGENTS.md`：「一条引导对应**一条**命令。
                    给两条以上，用户就要先做一次选择 —— 那正是引导要替他省掉的
                    那一步。」

                    判据两个都是现成的，不新造：`shown > 0`（这一格有东西了）
                    或 `nudged`（「下一步」点名的就是它）。有数据的用户五格照旧
                    都写着该敲什么 —— `test_pipeline_counts` 守的那条不受影响。 */}
                {s.cmd && (shown > 0 || nudged) && (
                  <div className="rail-guide">
                    <Cmd>{s.cmd}</Cmd>
                  </div>
                )}
              </div>
              );
            })}
          </nav>

          {/* 那个缺口里**真是待办的那一半**。
              `AGENTS.md` 的承诺是「抓完直接排出可以投的，不停在待评」——
              所以这一段本该是空的；它有数，说明那条自动衔接断过一次
              （实测 2026-08-23：182 个，而同一屏正在说库存见底）。
              下面那条 `parked` 说的是「不用管的那一半」，两句管的不是一件事：
              一个是待办、一个是已经放下的。 */}
          {/* **「下一步」排在那几条提醒之前。**
              原来的顺序是：待评队列 → 服务用的是旧代码 → 归档里有可复活的
              → 下一步。三段散文（实测 2026-08-24 共 122px）压在那一句上面，
              而这一页存在的理由就是那一句。提醒一条没删，只是排到它后面 ——
              它们说的都是「顺便处理」，不是「现在做什么」。 */}
          {/* ── 下一步：**一句结论 + 一条命令**，理由收在「为什么」后面 ──

              这一块 2026-08-24 实测长到 **206px、8 行**，是首屏最大的一块 ——
              而「可以投的岗位」那一节要滚到 1061px 才开始（视口 1271px，
              笔记本上整个名单在首屏之外）。用户当天的原话：
              「dashboard 应该主要出现职位吧……保持首屏的简易」。

              **它长成这样不是意外**：这段话是逐轮加出来的（催一遍 → 猎头/直招
              拆分 → 会话打招呼 → 季节 → 手上备好的别等 → 排最久的那几个 →
              旺季补新的 → 你把某个渠道关掉了）。每一条单看都该说，叠起来就是墙。

              **砍的是位置，不是内容。** 那些句子是逐条推敲过的判据，一条都没删；
              首屏只留第一句（现状）加那条命令 —— 动作本来就在命令上 ——
              其余点开就在原地展开。不做成 Modal：它和「下一步」是同一件事，
              弹窗会把它变成「另一页」。 */}
          <div className="nextstep">
            <span className="kicker">
              下一步
            </span>
            <span className="nextstep-text">{nsHead}</span>
            {nextStep.command && (
              <Cmd>{nextStep.command}</Cmd>
            )}
            {nsWhy && (
              <button
                type="button"
                className="nextstep-more"
                aria-expanded={nsOpen}
                onClick={() => setNsOpen((v) => !v)}
              >
                {nsOpen ? "收起" : "为什么"}
              </button>
            )}
          </div>
          {nsWhy && nsOpen && <p className="nextstep-why">{nsWhy}</p>}

          {pipeline.some((s) => (s.waiting ?? 0) > 0) && (() => {
            const st = pipeline.find((s) => (s.waiting ?? 0) > 0)!;
            return (
              <p className="parked-note">
                {"还有 "}
                <b>{st.waiting} 个抓回来没评分</b>
                {"：能不能投还不知道，它们不在上面任何一份名单里。"}
                {/* **这批是会烂的，而原来这里只有一个数。**
                    抓的时候只收 14 天内的岗，而评它要花抓详情的额度 ——
                    这套系统里最稀缺的东西。读的人分不出「昨天抓的 182 个」
                    和「放了半个月的 182 个」，后者里有一批在平台上已经关了，
                    评它是白评。判据与实测见 `doctor.waiting_age`；
                    **有旧的导出器才给这个字段**，所以这一句平时不出现。 */}
                {st.waitingNote && (
                  <span className="parked-stale">{st.waitingNote}。</span>
                )}
                <Cmd>/job-rank</Cmd>
              </p>
            );
          })()}

          {/* 「搜到职位」与「打过分」之间的缺口，用户会读成「还有这么多要做」。
              其中一部分只是**只看了标题就先放一边**：标题显示方向不对、留着没结案，抓详情的
              额度轮不到它们。这个数原来导出了却没人显示——缺口就一直解释不通。 */}
          {(parked ?? 0) > 0 && (
            <p className="parked-note">
              {/* 结论放最前并加粗。原来是「上面两格的差额里有 34 个……它们不是积压，
                  不用管」——三个毛病：① 让读者做减法（268−195 是 73，不是 34，
                  对不上就更困惑）；②「结案」「积压」是公文词，「抓详情」是内部词
                  （用户不知道抓取分两趟）；③ 用一整句解释一件「不用管」的事，
                  却摆在第一屏最显眼处。现在先说不用管，再说为什么。 */}
              另有 <b>{parked} 个不用管</b>
              {"：只看标题就放一边了——方向明显不对，没再去读完整描述。"}
            </p>
          )}

          {/* 收进存档的老岗。不显示的话，「搜到职位」的数字会在某次归档后凭空变小，
              用户第一反应是丢数据了。写清楚去哪了、怎么拉回来（面板每处引导都要带命令）。

              **`--apply` 不能省。** 2026-08-31 起 `--revive` 也认那面旗子
              （在那之前它敲一次就当场搬 1074 个岗，而同一个工具的 help 写着
              「不加就是试运行」）。这里印的是给用户复制去跑的命令 —— 少了
              `--apply`，他跑完只会看到「会拉回 N 个」，然后以为面板骗了他。 */}
          {(snap?.archivedCount ?? 0) > 0 && (
            <p className="parked-note">
              另有 <b>{snap!.archivedCount} 个老岗位收进了存档</b>
              {"：出局超过两周、没投过也没出过材料的，不占上面的计数。存档文件在 "}<code>job_scraper/archive.json</code>{"；改了硬性条件想重新评它们时先跑 "}
              <Cmd>python tools/archive.py --revive --apply</Cmd>
            </p>
          )}

          {/* 「有几个岗的判断现在不该信了」。用户 2026-08-30 问的是「有没有一个
              按钮或命令」——**按钮做不成**：`serve.py` 那条路只改一个字段、
              不接大模型（它自己的边界），而重评要读职位描述再判。
              命令做得成，所以这里把它印出来。
              此前这条队列只在 `/job-auto` 收尾的终端输出里一闪而过，
              而终端日志没人看——和上面 staleCode 那条是同一课。 */}
          {(snap?.restaleCount ?? 0) > 0 && (
            <p className="parked-note">
              有 <b>{snap!.restaleCount} 个岗的判断该重跑一遍</b>
              {"：要么材料写的档位和现在的对不上，要么当初评它时就没读到完整的职位描述。已经投出去的不在里面。重跑一批 "}
              <Cmd>/job-apply --stale</Cmd>
            </p>
          )}

          {/* 这一页背后的服务在启动之后代码被改过——按钮还在按旧逻辑写盘。
              2026-08-13 一天撞了三次，前两次都只在终端警告，而终端日志没人看；
              信号必须走到用户真正盯着的地方，也就是这里。
              提醒本身由 serve.py 现塞进 /data.json 响应（staleCode），
              前端只负责显示；服务重启后字段消失，这块自动不渲染。 */}
          {(snap?.staleCode?.length ?? 0) > 0 && (
            /* **文件名不上屏。** 这条原来把改过的五个 `.py` 逐个列了出来
               （`_cli.py、build_dashboard.py、export_web_data.py…`）——
               AGENTS.md「给用户看的措辞」禁的就是这个：用户对着 `_cli.py`
               什么也做不了，那是仓库的内部结构，不是他要处理的东西。
               他需要知道的只有两件：**现在点按钮可能记不准**、**怎么修**。
               文件名留在终端那份告警里（`serve.py` 里那行 `[!] 这几个文件…`），
               在那儿它是给开发者看的，位置对。
               顺带从 156 字压到 44 字 —— 它排在「下一步」上面，
               而「下一步」才是这一页要人看的那一句。 */
            <p className="parked-note">
              {/* **命令块必须是这句的最后一样东西。** 原来它后面跟着一个以「，」
                  开头的文本节点，而 `<Cmd>` 是 inline-block —— 换行一旦落在这个
                  边界上，那个逗号就单独站在下一行的行首（中文排版的避头点，
                  浏览器的 UAX-14 断行只在连续文本里生效，跨不过 inline-block）。
                  实测 390px 上就是这样。同一段里另外两条（存档那条、job-rank
                  那条）本来就是以命令收尾的，这条改完与它们一致。 */}
              <b>这一页的服务还在用旧代码跑</b>
              {"：现在点按钮记的状态可能不准。再跑一次下面这条，它会告诉你怎么停掉旧的那个。"}
              <Cmd>python tools/serve.py</Cmd>
            </p>
          )}



          {/* ── 设置 / 统计 / 说明：一排文字按钮，点开是弹窗 ──

              这七块原来是正文里的七段折叠。收起来也各占一行加外边距，叠起来
              把名单挤下去；而它们回答的都不是「我今天该投谁」。
              中间试过侧边抽屉，用户 2026-08-24 否掉了 —— 现在是**能看懂的
              文字按钮**，点一下开 Modal。

              **每颗按钮都带那句结论。** 折叠标题上那几句是逐条推敲过的
              （「上次审于 X，之后改过没再审」「有回音 0%」还是「还没有」），
              换成按钮不能把它们丢掉，否则这一排就是七个没有信息的词。
              告警（被平台拦住、还差几项要装）点亮整颗按钮 —— 这排就在
              「下一步」下面，本来就在首屏。 */}
          {/* **还没建过档的人：命令表直接摊开，不放进那一排按钮。**
              他最需要这张表，而按钮那一排的前提是「你已经知道自己在看什么」。
              上一版折叠时代这里是 `defaultActiveKey={activeUser ? [] : ["cmds"]}`
              —— 换成按钮之后那个照顾会消失，而为它自动弹一个 Modal 比不弹更糟。 */}
          {!activeUser && (snap.commands ?? []).length > 0 && (
            <section className="firstrun" aria-label="先跑这三条">
              {/* **只摊脊梁那三条，不摊 20 条全集。**
                  全集对还没建档的人是噪音：里面能敲的只有 `/job-setup` 和
                  `/job-user`（实测 2026-08-24 空快照渲染，那张表从 220px
                  一直铺到页面底部）。全集没删 —— 下面那颗「能敲哪些命令」
                  按钮对他也开着了，点一下就有。 */}
              <p className="firstrun-h">先跑这三条</p>
              <CommandBook groups={snap.commands ?? []} spineOnly />
            </section>
          )}
          {desks.length > 0 && (
            <nav className="deskbar" aria-label="设置、统计与说明">
              {desks.map((d) => (
                <button
                  key={d.key}
                  type="button"
                  className="deskbtn"
                  data-desk={d.key}
                  data-alarm={d.alarm ? "1" : undefined}
                  aria-haspopup="dialog"
                  onClick={() => setDesk(d.key)}
                >
                  <span className="deskbtn-name">{d.name}</span>
                  {/* **那句结论只留给要你处理的那几颗。**
                      七颗都带一句，这一排 2026-08-24 实测占 203px、排成两行，
                      而它整体回答的不是「我今天该投谁」。所以：有告警的照旧
                      带着（那句话就是告警的上下文），其余只留名字 —— 点开
                      弹窗里一个字都没少。
                      判据不新写：`d.alarm || d.chips` 就是「这颗要你处理」，
                      它本来就在决定整颗按钮点不点亮。 */}
                  {d.note && (d.alarm || (d.chips ?? []).length > 0) && (
                    <span className="deskbtn-note">{d.note}</span>
                  )}
                  {(d.chips ?? []).map((c) => (
                    <span className="deskbtn-alarm" data-tone={c.tone} key={c.text}>
                      {c.text}
                    </span>
                  ))}
                  {d.alarm && (d.chips ?? []).length === 0 && (
                    <span className="deskbtn-alarm">{d.alarm}</span>
                  )}
                  {d.chip && <span className="deskbtn-chip">{d.chip}</span>}
                </button>
              ))}
            </nav>
          )}
          <Modal
            open={desk !== null}
            title={desks.find((d) => d.key === desk)?.title ?? ""}
            onCancel={() => setDesk(null)}
            footer={null}
            /* **宽度跟着视口走，不写死。** 原来是 `760`，而这几块里最宽的两块
               本来就装不下：「能敲哪些命令」是 20 行 × 4 列的表，「投出去的那些」
               是分档与分渠道两张表并排 —— 760px 下都在换行。
               `min()` 让它在窄屏自动缩回去，不必再写一条断点规则。 */
            width="min(1180px, 92vw)"
            className="desk-modal"
            /* **两个空的 transitionName 不是可有可无的。**
               实测 2026-08-24（浏览器开着「减少动态效果」）：不给它们，弹窗
               **根本不出现** —— DOM 里在、标题也对、遮罩也上来了，只有弹窗本身
               的 `opacity` 卡在 0，class 停在 `ant-zoom-appear-prepare`。
               antd 把 `opacity: 0` 写在进场动画的起始状态里，而 `cockpit.css`
               在 `prefers-reduced-motion` 下关掉了动画，rc-motion 就永远等不到
               那个 `animationend`，也就永远不摘掉那两个 class。
               改时长（0.01ms）试过，一样收不到事件；`theme.token.motion: false`
               也只挡住了遮罩那一半。**空串是 antd 自己给的关法**，从源头不进
               动画流程。这一页本来就是静态设计，没有动画可损失。 */
            transitionName=""
            maskTransitionName=""
            /* 关掉就销毁：里面几块都有自己的 busy/err 局部状态，留在树上等于
               把上一次打开的中间状态带到下一次。状态本身还在 App 这一层。 */
            destroyOnHidden
          >
            {desk === "portals" && (
              <Portals portals={portals} onChanged={() => void refreshAnd()}
                       staleDays={snap?.resumeStaleDays ?? null} />
            )}
            {desk === "jobprefs" && (
              <JobPrefs prefs={jobPrefs} onChanged={() => void refreshAnd()} />
            )}
            {desk === "env" && (
            <>
            {/* **会静默失败的那一项要单独说一句。** 中文字体缺了不报错、
                PDF 照样生成、ATS 文本层校验也过，但渲染出来是一页豆腐块
                ——只和别的项并排列在下面的表里，用户不会意识到严重性。
                这条规则原来只有单页版守着（`env-silent`），网页版没有；
                而 `doctor.py` 一直在标 `silent_fail`，是导出器把它丢了。 */}
            {envItems.filter((e) => e.silentFail && e.ok === false).map((e) => (
              <p className="env-silent" key={e.name} role="alert">
                <b>{e.name}没装</b>——这一项缺了<b>不会报错</b>
                {"：简历 PDF 照样生成、招聘系统的文本层校验也过，" +
                 "但打开是一页方块。"}
                {e.fix && <span className="env-fix">装法：{e.fix}</span>}
              </p>
            ))}
            <div className="env-grid">
              {envItems.map((e) => (
                <div
                  className="env-item"
                  key={e.name}
                  data-ok={e.ok === null ? "na" : String(e.ok)}
                >
                  <i className="env-led" />
                  <div>
                    <div className="env-name">{e.name}</div>
                    <div className="env-detail">{e.detail}</div>
                    <div className="env-unlock">{e.unlocks}</div>
                    {/* **怎么装只给缺的那几项。** 装好了还挂个安装链接是噪音，
                        而缺了不给装法就等于只说「你缺东西」不说怎么办。 */}
                    {e.ok === false && e.fix && (
                      <div className="env-fix">{e.fix}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {/* 面板和命令行互相指路：在哪一边都能找到另一边。
                这一块只在缺东西时出现，装完想再查一遍就只剩这条路。 */}
            <p className="env-cli">
              想在命令行里再查一遍：<Cmd>python tools/doctor.py</Cmd>
            </p>
            </>
            )}
            {desk === "baseresume" && snap.baseResume && (
              <BaseResume data={snap.baseResume} user={activeUser} />
            )}
            {desk === "resume" && snap.resumeInsight && (
              <ResumeRead data={snap.resumeInsight} />
            )}
            {desk === "ostats" && snap.outcomeStats && (
              <OutcomeStatsPanel s={snap.outcomeStats} />
            )}
            {desk === "hrqa" && (
              <HrAnswers
                items={snap.hrAnswers ?? []}
                live={live}
                onSave={async (q, a) => {
                  // 不 catch：真因要走到组件那边显示出来（见 HrAnswers 的
                  // `onSave` 签名）。这里原来吞成 `false`，于是三种完全不同
                  // 的失败在界面上长一个样。
                  await postHrAnswer(q, a);
                  await refreshAnd();
                }}
              />
            )}
            {desk === "cmds" && <CommandBook groups={snap.commands ?? []} />}
          </Modal>

          {/* `/job-apply --top N` 批量跑下来攒的待办。**排在最前面**：它们是「你答一句
              就能继续」的东西，而批量已经因为它们跳过了那几个岗。
              批量不回头在对话里问——一次长跑被十几个问题切碎，用户要做的事就从
              「批准一次」变成「按二十次继续」。问题攒到这儿，有空时一次答完。 */}
          {blocked.length > 0 && (
            <div className="mat-gap" role="status">
              <b>有 {blocked.length} 个岗卡住了，等你一句话</b>
              {/* 整句一行：JSX 里两个汉字之间的换行会被折成空格，而中文句号
                  也算汉字，所以断在标点后同样会中招。只有标签边界是安全的。 */}
              <span>
                批量出材料时碰到缺东西的地方没有回头问你，跳过继续跑了。答完这几条，逐个跑下面这条把它们补上（每次换成那一行的链接）。
              </span>
              <ul className="blocked-list">
                {blocked.map((j) => (
                  <li key={j.id}>
                    <b>{j.title}</b>
                    <i>{j.company}</i>
                    <span>{j.blocked!.需要}</span>
                    <em>{j.blocked!.环节}</em>
                  </li>
                ))}
              </ul>
              {/* **原来给的是 `/job-apply --top N`，而那条按分数取前 N。**
                  卡住的岗不一定在里面：它可能是「可以考虑」那一档，也可能排在
                  第 45 —— 那时「再跑一次下面的命令就会把它们补上」是句假话，
                  他敲完发现没动，然后连带不信这一整块。

                  改成指名道姓那一个岗。批量命令在这里天然不对：这一栏的每一行
                  都是一个**具体的、被具体东西卡住的**岗，而批量的选岗条件与
                  「谁被卡住了」毫无关系。 */}
              <Cmd>{`/job-apply ${blocked[0].url}`}</Cmd>
            </div>
          )}

          {/* 头部的材料备得太少就顶在名单上方。**位置要在表格之前**：
              它说的是「这份名单现在还投不出去」，读完名单才看到就晚了。
              和顶部那条流水线「下一步」不冲突——那条说整体该干什么
              （现在是「把备好的 3 个投出去」），这条说的是这份名单本身缺什么。 */}
          {materialsThin && (
            <div className="mat-gap" role="status">
              {/* **不说「可以投的岗」** —— 屏幕上那个段头就叫「可以投的岗位 9」，
                  而这里数的是 `sellable` 按分排的前 20（含「可以考虑」那一档，
                  实测 231 个）。同一句话两个集合，同一屏上。 */}
              <b>
                {/* 「只有 0 个」没人这么说话。零是这条提示最常见的取值
                    （它恰恰是「一个都没备」时才出现的），所以零单独给一句。 */}
                分最高的 {topReady.size} 个里，
                {topReady.ready === 0
                  ? "一个备好材料的都没有"
                  : `只有 ${topReady.ready} 个备好了材料`}
                {topReady.raw > 0 && `（其中 ${topReady.raw} 个还没读过 JD，分是粗筛给的）`}
              </b>
              {/* 换行只许落在标点或标签边界上：JSX 里两个汉字之间的换行会被折成
                  一个空格，屏幕上就是「有的 下面」。同 sec-note 那条注释。
                  措辞上少说一层：原来这里还解释了「出一份材料要读 JD、查公司、
                  起草、审稿，不是点一下就有的」和「这条命令自带闸门」——前者是在
                  替工具辩解为什么慢，后者「闸门」是流程内部词（AGENTS.md 禁的那类）。
                  用户在这一刻要知道的只有一件事：敲哪条能把材料补上。 */}
              <span>没材料就投不出去。下面这条按分数从高往低补，查完公司发现不该投的只留评估。</span>
              <Cmd>{`/job-apply --top ${TOP_N}`}</Cmd>
              {/* 上面那个 0 是「分最高的 20 个里」的局部数。全表还有多少备好的
                  必须在同一句里说完 —— 否则用户按着一个 0 去补货，而手上那批
                  一个都没发。补材料花的是机器的工时，发出去花的是他的。 */}
              {readyToSend > 0 && (
                <span className="mat-gap-have">
                  {"不过你手上已经有 "}
                  {/* **把这个数变成入口。** 它是整条流水线唯一要人做的那一步
                      （发出去）的清单，而它此前只是一句话 —— 用户读完得自己去
                      222 行的「可以考虑」里翻。点一下就只看这批；再点取消。
                      筛选开着时上面那枚 `funnel-chip` 会说「只看备好还没发的」，
                      有一条明确的回头路（那枚 chip 存在的理由见它自己的注释）。 */}
                  <button type="button" className="have-jump"
                          aria-pressed={funnel === "ready"}
                          onClick={() => setFunnel(funnel === "ready" ? "" : "ready")}>
                    {readyToSend}
                  </button>
                  {/* 这里原来分两句：零回音时改口说「先别发，多半是同一个结果」。
                      那句撤了（2026-08-29 用户裁定，见 `AGENTS.md`「跟进归用户，
                      工具不催」）—— 它指的「上面那件事」正是同时撤掉的那一支，
                      留着就指向了一个不存在的建议。回音的解读归用户，这里只说
                      手上有什么。 */}
                  {` 个岗材料是齐的，随时能发。它们分数没进前 ${TOP_N}，`
                    + `多在「可以考虑」那一档——补货之前先把这批发掉。`}
                </span>
              )}
            </div>
          )}



          <div className="sec-head">
            <h2>可以投的岗位</h2>
            <b className="sec-count">{mainList.length}</b>
            {/* 屏蔽偏好挨着计数放：那个数变小的原因就在旁边，一眼能对上。 */}
            <HidePrefs prefs={hidden} onChange={setHiddenSaved} hiddenCount={hiddenCount} />
            {/* 筛选开着时必须说出来。数字从 54 变成 5 而没有解释，用户第一反应是
                「我的岗怎么少了」——把筛选状态藏起来，等于制造一个假的数据丢失。 */}
            {funnel && (
              <button
                type="button"
                className="funnel-chip"
                onClick={() => setFunnel("")}
                aria-label="取消筛选，看全部可以投的岗位"
              >
                只看
                {/* 「材料就绪」视图**包含已投的**（见上面 shortlist 的口径注释）——
                    标签原来写「材料就绪没投的」，和实际行为相反 */}
                {funnel === "materials" ? "材料就绪的"
                  : funnel === "ready" ? "备好还没发的"
                  : funnel === "applied" ? "已投递的" : "面试中的"}
                <span aria-hidden>×</span>
              </button>
            )}
            {/* 这是**列的图例**——一行都没有时它在解释屏幕上不存在的东西。
                新用户跑完 /job-setup 的第一屏就是空表，那时最不该做的是先教他读一张
                他还看不到的表。与硬性条件那句「有一条不满足就别投」同一条原则：
                提醒只在有可提醒的对象时才出现。 */}
            {/* 「技能」和它后面的字之间**不能有空格**——`</b>` 不产生断字，
                屏幕上就是「技能 高于总分」。空格要落在标点或中英交界处。
                （这条注释放在 `&&(` 外面：那对括号里只能有一个表达式，
                 塞个 JSX 注释进去整个文件就编译不过。） */}
            {/* 投过的岗被收起来了就说一声，并且给一条回去看它们的路。
                默认视图里少了一行而没有解释，用户第一反应永远是「我的数据呢」——
                与上面那个筛选标同一条原则。 */}
            {funnel === "" && hiddenApplied > 0 && (
              <button
                type="button"
                className="funnel-chip"
                onClick={() => setFunnel("applied")}
                aria-label={`看已经投出去的 ${hiddenApplied} 个岗`}
              >
                另有 {hiddenApplied} 个已投出去，不在这份名单里 · 看这批
              </button>
            )}
            {/* 段头右上角只留**一句**。
                原来这里挤着两条不相干的提示：「点任意一行展开详情」（怎么操作）
                和一整段技能列的配色规则（怎么读那一列）。后者**列头 tooltip 里
                已经有一份**，而且那份就挂在它解释的那一列上、滚到哪都够得着；
                印在段头的这份只在首屏出现一次，位置离它说的东西还最远。
                同一句解释印两遍，长的那遍还占着最显眼的位置。 */}
            {mainList.length > 0 && (
              <span className="sec-note">点任意一行看详情</span>
            )}
          </div>
          <Shortlist
              reasons={snap.outcomeReasons}
            jobs={mainList}
            namedDirectBelow={namedDirectInRest}
            observedMonths={snap.observedMonths ?? null}
            selectedId={effectiveId}
            recommendedId={recommended?.id}
            onSelect={setSelectedId}
            onExclude={(id) => exclude(id, true)}
            onExpire={live ? expire : undefined}
            onChanged={afterStatus}
            filtered={funnel !== ""}
            // 看已投的那些时按投递时间倒序——分数是用来挑「接下来投谁」的，
            // 对已经投掉的岗没有决策价值，那时人要找的是「我上周投的那个」。
            byDate={funnel === "applied"}
            hideColumns={hidden.columns}
            appliedCompanies={appliedCos}
            hiddenCount={hiddenCount}
          />

          {/* 「可以考虑」这一档收起来。和「不投的岗位」同一种形态——**里面的行
              完全一样**，展开、记状态、标不投都照旧，只是不占默认的视线。
              标题里给出分数区间：不点开也知道这一堆大概在什么水平。 */}
          {restList.length > 0 && (
            <Collapse
              // `panel-flush`：正文就是上面那张表本身，两侧不要内缩，否则它和
              // 「可以投的岗位」那张主表对不齐（见 cockpit.css 的 .panel-flush）。
              className="panel-collapse panel-flush is-gap"
              ghost
              // 筛选开着时默认展开。流水线格子的契约是「格子上的数 = 点开看到的
              // 行数」（见 export_web_data.funnels_of），而这一档默认收起时
              // **要再点一次才数得齐**：实测点「材料就绪 19」，标题只写 16，
              // 剩下 3 个躲在这个折叠里。默认视图不展开——那时它的作用正是
              // 给长名单一个停止点。
              //
              // `key` 是必须的：`defaultActiveKey` **只在挂载时读一次**，而切筛选
              // 时这个组件早就挂着了。只改 defaultActiveKey 能过类型检查、能构建、
              // 在页面上一点效果都没有——实测就是这样，靠真点一遍才发现。
              // 换 key 强制重挂载，展开状态才跟着筛选走，之后用户仍可自己收起。
              key={funnel || "all"}
              defaultActiveKey={funnel ? ["maybe"] : []}
              items={[
                {
                  key: "maybe",
                  // **「可以考虑」这一档里混着两种完全不同的东西。**
                  //
                  //   读过 JD 的：评估看完正文，结论是「先问清楚再决定投不投」
                  //   没读 JD 的：只看了标题和卡片字段，分是粗筛给的
                  //
                  // 后者不是一个关于这个岗的结论，是**关于工具自己覆盖到哪儿**的
                  // 陈述——和这个仓库反复立的那条「『没查』与『查过没有』是两件事」
                  // 同一族。数据里本来分得开（判词就是「粗筛：可以考虑」，
                  // 实测 141/142 都带这个前缀），是 `plainVerdict` 把前缀剥掉了。
                  //
                  // 逐行还有「没读 JD」那枚章兜着，但**标题上这个数是合起来的**：
                  // 实测 2026-08-22 写着「还有 222 个『可以考虑』的」，
                  // 而其中 142 个工具根本没看过正文。
                  // 这个数是他决定「要不要点开」时唯一读到的东西。
                  label: `还有 ${restList.length} 个「可以考虑」的`
                    + (restScores.length
                      ? `（分 ${Math.min(...restScores)}-${Math.max(...restScores)}）`
                      : "")
                    + (nRestRaw > 0
                      ? ` · 其中 ${nRestRaw} 个还没读过 JD`
                      : "")
                    + (nRestStale > 0
                      ? ` · ${nRestStale} 个的判断该重跑`
                      : ""),
                  children: (
                    <Shortlist
              reasons={snap.outcomeReasons}
                      jobs={restList}
                      selectedId={effectiveId}
                      onSelect={setSelectedId}
                      onExclude={(id) => exclude(id, true)}
                      onExpire={live ? expire : undefined}
                      onChanged={afterStatus}
                      filtered={funnel !== ""}
                      byDate={funnel === "applied"}
            hideColumns={hidden.columns}
            appliedCompanies={appliedCos}
            hiddenCount={hiddenCount}
                    />
                  ),
                },
              ]}
            />
          )}

          {/* 一个都没有时整块不渲染。空的折叠面板点开是空的，
              而它的标题还在承诺里面有东西。 */}
          {shelved.length > 0 && (
          <Collapse
            // 同上：正文是一列整行卡片，自己撑满宽度
            className="panel-collapse panel-flush"
            ghost
            items={[
              {
                key: "shelf",
                label: `不投的岗位（${shelved.length}）· 硬性条件没过、方向不对、分太低，或已下线`,
                children: (
                  <>
                    {/* ── 这 2000 多行是五类东西 ──
                        标题那句原来列了四类（硬性条件没过、方向不对、分太低、
                        已下线），**漏掉的两类恰恰是带「放回可以投」按钮的那两类**：
                        规则判的（实测 719 个，而规则最容易错）和他自己点的（93 个）。
                        一个 2105 的总数配四个笼统的词，读者不知道里面有七百个
                        一句话就能捞回来的。能放回的排在前面。 */}
                    <p className="shelf-tally">
                      {`这 ${shelved.length} 个里：`}
                      {([[shelfKinds.rule, "规则判的（点一下就能放回）"],
                         [shelfKinds.mine, "你自己点的不投"],
                         [shelfKinds.gate, "硬性条件没过"],
                         [shelfKinds.low, "分太低"],
                         [shelfKinds.gone, "已下线"]] as [number, string][])
                        .filter(([n]) => n > 0)
                        .map(([n, label]) => `${label} ${n}`).join(" · ")}
                    </p>
                    {/* ── 卡在硬性条件上的，是哪几道门 ──
                        门名一直存着（1136 条里 1135 条带），可它此前只出现在
                        下面每一行那个小戳的悬浮提示里 —— 要看清全貌得悬停一千多次。
                        而全貌才指得出动作：四成死在年限说明「层级整体够不着」，
                        两成六死在他**自己设的排除列表**上——那一档是唯一想通了
                        就能改的，必须让他看见它在收多少钱。 */}
                    {(snap.gateFailTally ?? []).length > 0 && (
                      <p className="shelf-tally">
                        {`卡在硬性条件上的 ${(snap.gateFailTally ?? []).reduce((a, x) => a + x.n, 0)} 个：`}
                        {(snap.gateFailTally ?? [])
                          .map((x) => `${x.gate} ${x.n}`).join(" · ")}
                        {(snap.gateFailTally ?? []).some(
                          (x) => x.gate === "你资料里写明不要的") && (
                          <span className="shelf-tally-note">
                            {"「你资料里写明不要的」是你自己设的那份清单，"
                              + "其余几道是市场那边的门、改不了。"}
                            {/* **说到哪一条，不止说「那份清单」。**
                                上面那个数是十一条加起来的；他打开清单，
                                十一条一样长，看不出该动哪一条。而实测最贵
                                的一条一个人挡掉 98 个（实测 2026-08-31），
                                是第二名的 2.6 倍。这道门是七道里唯一他今天
                                就能改的，所以这几个
                                数是这一页上最能换来岗位的信息。 */}
                            {(snap.topExclusions ?? []).length > 0 && (
                              <>
                                {"其中最贵的是："}
                                {(snap.topExclusions ?? [])
                                  .map((x) => `「${x.rule}」挡掉 ${x.n} 个`)
                                  .join("；")}
                                {"。"}
                              </>
                            )}
                            {"想改这份清单，跑 "}
                            <Cmd>/job-setup --section exclusions</Cmd>
                            {" 改完再跑 "}
                            <Cmd>/job-rank --all</Cmd>
                            {" 重评。"}
                          </span>
                        )}
                      </p>
                    )}
                    <ShelvedList
                      jobs={shelved}
                      excluded={excluded}
                      onRestore={(id) => exclude(id, false)}
                    />
                  </>
                ),
              },
            ]}
          />
          )}

          {/* 写失败要当场说，而且要说清「界面已经改回去了」——
              否则用户不知道该重点一次还是该去查服务。 */}
          {saveError && (
            <div className="pending-bar" role="alert" data-tone="error">
              <span className="pending-text">
                没写进去：{saveError}。界面已经改回原样，本地服务还在跑的话再点一次。
              </span>
            </div>
          )}

          {/* 这条只在**静态模式**下出现。有本地服务时点一下就落盘了，
              再让用户去粘一条命令是白让他做第二遍。
              数的是**本机新标的**（excluded 减去盘上已有的），不是 excluded 全集——
              全集包含盘上早就生效的 skipped，拿它数的话：盘上有 10 个不投、
              浏览器一笔没标，条子也宣称「10 个岗只藏在浏览器里」，命令里还塞着
              10 条早就落盘的冗余 URL。 */}
          {!live && jobs.some((j) => excluded.has(j.id) && !j.skipped) && (
            <div className="pending-bar" role="status">
              <span className="pending-n">
                {jobs.filter((j) => excluded.has(j.id) && !j.skipped).length}
              </span>
              <span className="pending-text">
                个岗你标了「不投」，现在只藏在这台电脑的浏览器里。
                <b>复制这条命令</b>让它永久生效——不然重新生成页面它们会回来。
              </span>
              <Cmd>{`/job-rank --skip ${jobs
                  .filter((j) => excluded.has(j.id) && !j.skipped)
                  .map((j) => j.url)
                  .join(" ")}`}</Cmd>
            </div>
          )}

          <p className="cockpit-foot">
            本页读的是这台电脑上的职位数据和投递记录 ·{" "}
            {live ? (
              "「我投了 / 约面了 / 不投」点了就存进本机数据，刷新还在"
            ) : (
              <>
                {/* 静态快照里点什么都不算数。光说这句不够——得告诉他怎么换成
                    能点的那个版本。`serve.py` 此前在**任何**用户可见的文字里都
                    没出现过，只写在代码注释里，等于没有引导。 */}
                这是一份静态快照，点了不算数——用{" "}
                <Cmd>python tools/serve.py</Cmd>{" "}
                打开，投递状态就能直接在这一页点
              </>
            )}
          </p>
        </div>
        </CodeToolProvider>
      </AntApp>
    </ConfigProvider>
  );
}
