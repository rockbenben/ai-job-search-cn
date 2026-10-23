import { useState } from "react";
import { Cmd, CopyButton, CopyIcon } from "./Cmd";
import { Button } from "antd";
// 「这道门算不算还没查到」只有一份实现，别在这里另写（`GateStamp` 是它的家）。
import { countsAsUnknown, GateGrid } from "./GateStamp";
import { InterviewLog } from "./InterviewLog";
// 判词去「粗筛：」前缀只有一份实现，别在这里另写（`Shortlist` 是它的家）。
import { plainVerdict } from "./Shortlist";
import { hasServer, postHrViewed, postStatus, postStatusUndo }
  from "../data/excluded";
import { verdictColor, type Verdict } from "../theme/tokens";
import type { Dimension, Job } from "../types";

/**
 * 岗位详情——单个职位的完整视图。
 *
 * 版面顺序回答的是用户的三个问题，按这个先后：
 *   1. 这是什么岗（头部：名称 / 公司 / 薪资 / 地点 / 年限 + 结论分）
 *   2. 怎么投（职位原始链接 + 话术 / 简历，没出材料就给 /job-apply 命令）
 *   3. 为什么是这个结论（对口的地方 / 要掂量的地方，说人话）
 * 然后才是底细：硬性条件核对、写材料不能吹的地方、待核实的信息。
 *
 * 曾经这里有一条「权重带」（段宽 = 权重、高度 = 得分）。撤掉的原因：权重是打分器的
 * 内部参数，「占 30%」对用户没有任何行动意义——他要的是投不投、为什么、怎么投。
 * 打分依据不删，但换成人话列表（每一维的 note），百分比不再上屏。
 */

/**
 * 每一维的 note 按得分分成两列：≥70 算对口，其余（含没打分的）都进「要掂量」。
 *
 * **70 的出处：粗筛四档 30 / 50 / 70 / 85**（`04-job-evaluation.md`：粗筛阶段
 * 这两维只允许取这四个值，70 = 判据偏好、50 = 没有信号）。70 是这四档里最低的
 * 那个正面值，所以切在这儿对粗筛分和深评分都讲得通。
 *
 * ⚠️ **它不是 04 各维的分档（80/60/40），别把两者混起来。** 那套分档的 60 是
 * 「主要要求命中」的下沿，而 `gap_split.py` 里有一个同样是 70 的数**被撤掉过**
 * ——那次的问题是它**冒用了 04 分档的名义**（「那张表根本没有 70」）。
 * 这里的 70 有自己的出处，不是同一个数。
 *
 * 实测 2026-08-27：真正受这个切点影响的只有深评分（1015 行里 212 行落在
 * 60-69）；粗筛分只取那四个值，60 和 70 切出来**完全一样**。
 *
 * 改它要连 `audit_pipeline._PLUS_CUT` 一起改（那是这个数的复刻件，
 * `test_the_dimension_note_says_why` 盯着两边相等）。
 *
 * **先把不计权的那些摘出去。** 评分明细表里偶尔会混进一行「地点（跨城搬迁）」
 * ——那是 Pass/Fail 的门，不是维度（`04-job-evaluation.md`：「计权的是四维……
 * 所以别再叫『五维』」）。它没有分数，于是被上面第二行一律扫进「要掂量的地方」，
 * 措辞还是「这项没打分」。实测 2026-08-23：238 份评分明细里 106 份有这一行，
 * 其中 **96 条写着「上海」** —— 他就在上海，**那是通过**，却被摆成了负面。
 *
 * 判据用 `weighted`（服务端按名字给，见 `_cli.is_weighted_dim`），
 * **不能用「没有分数」或「权重为 0」**：真维度里也有 5 条没打分、716 条权重为 0。
 */
function splitReasons(dims: Dimension[]) {
  const scored = dims.filter((d) => d.weighted !== false);
  const plus = scored.filter((d) => d.score !== null && d.score >= 70);
  const minus = scored.filter((d) => d.score === null || d.score < 70);
  /** 不计权的那些：原样列出来，不判好坏。106 条里有 3 条是真信号
   *  （「杭州（跨城，需自行拍板）」这种），丢掉不行。 */
  const gateLike = dims.filter((d) => d.weighted === false);
  return { plus, minus, gateLike };
}

/**
 * 内嵌在表格行下方时用这个：**不重复头部**。
 * 职位名、公司、分数、年包在上面那一行已经写着了，再印一遍是噪音，
 * 还会把「怎么投」这块往下推。
 */
export function JobReadoutBody({
  job,
  onExclude,
  onExpire,
  onChanged,
  reasons,
}: {
  job: Job;
  onExclude?: () => void;
  /** 标「职位已下线」。与 onExclude 是两件事：那是你的判断，这是外面的事实。 */
  onExpire?: () => void;
  /** 状态写进盘上之后叫一声，让上层重新取一次快照（计数、下一步都得跟着变）。 */
  onChanged?: (advance?: boolean, phase?: "now" | "settled") => void;
  /** 「挂了」可以点的原因。**前端不写死**——它来自 `tracker.REASONS`，
      和状态按钮同一个道理：两份词表迟早分叉。 */
  reasons?: { value: string; label: string }[];
}) {
  return <ReadoutBody job={job} onExclude={onExclude} onExpire={onExpire}
                      onChanged={onChanged} reasons={reasons} />;
}

export function JobReadout({ job }: { job: Job }) {
  const color = verdictColor[job.verdict as Verdict];

  return (
    <section className="readout" aria-label={`岗位详情：${job.title}`}>
      <header className="readout-head">
        <div>
          <h3 className="readout-title">{job.title}</h3>
          <p className="readout-meta">
            <b>{job.company}</b>
            {" · "}
            {/* `null` = 没判过。原来这里是真值判断，于是把没判过的岗印成
                「企业 HR 直招」——**给错误的信息**，不是少一条信息。 */}
            {job.viaHeadhunter == null
              ? "没判是猎头还是直招"
              : job.viaHeadhunter ? "猎头代招" : "企业 HR 直招"}
          </p>
          {/* 同上：缺的字段直接不出现，不占位 */}
          <p className="readout-facts">
            {[
              job.salary,
              job.location,
              // 平台给的原话，43 种取值：`5-10年` `10年以上` `经验不限`。
              // 最后那种（实测 255 个岗）加前缀会变成「经验 经验不限」——
              // 它自己已经带着「经验」两个字了。短名单那边不加前缀，
              // 所以只有这一处要判。
              job.experience &&
                (job.experience.startsWith("经验")
                  ? job.experience
                  : `经验 ${job.experience}`),
              job.channel && `来自${job.channel}`,
            ]
              .filter(Boolean)
              .join(" · ")}
            {job.salaryMonthsUnknown && <span className="warn">（没写几薪）</span>}
          </p>
          {/* **这家你已经投过几个了。** 放在详情里、不放列表 —— 实测 2026-08-23
              有 92 个岗带着这个数，列表上挂 92 枚标记是噪音，而这里是他真正在
              决定投不投的地方。

              两个代价都要说，因为它们不是一回事：连投多个岗对面看到的是
              「广撒网」；而**撞单**是同一家既走猎头报备、自己又直投，用人方
              那边撞成重复候选人，谁来推、推荐费算谁的都要掰扯，处理不好两条
              都卡住。后者只有一个岗也可能发生，所以不设门槛，有就说。

              判据与措辞同 `followups.py` 的同公司归组（那边是投完之后催进度时
              说的，这边是投之前）—— 公司身份走 `cluster_key`，脱敏串不算，
              否则「某知名公司」会印成「这家你已经投过 158 个岗」。

              **整句话在 Python 那边拼**（`same_company_note`），这里只渲染。
              窗口内外说的不是同一句：窗口内是「在刷屏 + 当心撞单」，窗口外是
              「重投不算刷屏，但话术里别提上次」。判「多短算短期」的那个数
              （`SAME_COMPANY_DAYS`）只许有一份，在 TSX 里再写一次 if 就是第二份。 */}
          {job.sameCompanyWarn && (
            <p className="readout-facts warn">{job.sameCompanyWarn}</p>
          )}
        </div>
        <div className="readout-score">
          <b style={{ color }}>{job.score ?? "—"}</b>
          <i style={{ color }}>{job.verdict}</i>
          {job.score !== null && (
            <em className="score-src">
              {job.evaluated ? "读过 JD、查过公司" : "只按列表信息评的 · 没读 JD、没查公司"}
            </em>
          )}
        </div>
      </header>

      <ReadoutBody job={job} />
    </section>
  );
}

//: 「建议」以什么开头就算「先别投」。**只看开头** —— 这一节里顺口提到「不投」
//  的句子太多了（「不投这一条，投那一条」「若不投也不可惜」）。
//  与 `build_dashboard._AGAINST` 同值，两边由 `test_the_advice_reaches_the_screen` 钉住。
const ADVISES_AGAINST = /^[*_ \-—·]*(不投|别投|不建议投|不要投)/;

function ReadoutBody({ job, onExclude, onExpire, onChanged, reasons = [] }: {
  job: Job;
  onExclude?: () => void;
  onExpire?: () => void;
  onChanged?: (advance?: boolean, phase?: "now" | "settled") => void;
  /** 「挂了」可以点的原因，来自服务端 `tracker.REASONS`。空数组就不渲染那一排。 */
  reasons?: { value: string; label: string }[];
}) {
  // 投递状态记在这一页点，不用回命令行。
  //
  // 能点哪几个由**服务端**给（`tracker.NEXT` 从当前状态走得到的下一步），页面只渲染
  // 它给的那几个：在 TS 里另写一套状态机，分叉的样子就是页面画出一个按钮、
  // 服务端拒绝它。
  //
  // 撤销提示留在**这个组件自己**手里，不往上抬：抬上去要多穿两层 props，
  // 而它的生命周期本来就跟着这一行的展开——收起来它就该消失。
  //: `pending`：POST 还在飞、`prev` 还是占位。**撤销必须等它落地**——
  //  `prev: null` 有两个含义，撞在一起就是丢数据：
  //    · 占位（还不知道改之前是什么）
  //    · 服务端真值「这一行是这次调用刚建的」→ `tracker.undo` 据此**删掉整行**
  //  一个已投的岗点「约面了」，在 POST 回来之前点「撤销」，送出去的是占位 null，
  //  服务端当成第二种，把那条投递记录连同投递日期、备注一起删了——
  //  用户以为撤回了一步，实际撤掉的是整次投递。
  const [marked, setMarked] = useState<
    { prev: string | null; label: string; then: string; value: string;
      pending?: boolean } | null
  >(null);
  //: 记完「挂了」之后**才**出现的可选补充。
  //
  // 为什么不做成点按钮时弹出来让人先选：**沉默和「没说原因」是常态**
  // （用户 2026-08-13：「很多是没反馈也就不会填」「有些直接明确拒绝，也没具体理由」）。
  // 把原因做成必经的一步，等于给最常见的路径加一道没有信息量的关卡。
  // 所以顺序是：先把状态记上（那一下必须立刻生效），原因愿意补就补。
  const [reason, setReason] = useState("");
  const [reasonSaved, setReasonSaved] = useState(false);
  const [busy, setBusy] = useState("");
  const [statusErr, setStatusErr] = useState("");
  const steps = hasServer() ? job.nextStatuses ?? [] : [];

  /**
   * 记一笔状态。**界面立刻变，写盘在后台跑。**
   *
   * 原来是 `await postStatus` 之后才 `setMarked`，于是点一下要等两段：
   * 一次 POST，加上 `onChanged` 触发的整份快照重取——而写盘会改台账的 mtime，
   * `serve.py` 下一次 `/data.json` 就**重新导出整份数据**（秒级）。
   * 点完盯着一个没反应的按钮等一两秒，人的第一反应是再点一次。
   *
   * 用户 2026-08-13 原话：「点了『我投了』前端应该马上变化，不用等数据处理，
   * 它们是不相关的」。**确实不相关**：这一下要表达的是「我知道你点了」，
   * 那是纯界面的事；盘上写没写成、名单要不要重排，是另一件事。
   *
   * 所以：先改界面（乐观更新），再发请求。失败了**回滚并说清楚**——
   * 乐观更新的代价就是这一条，少了它就成了「界面说记上了，盘上没有」，
   * 比慢更糟。
   */
  async function mark(value: string, label: string) {
    setStatusErr("");
    // ① 立刻。prev/then 这时还不知道，先放占位：prev 用 null（撤销时会用
    //    服务端返回的真值覆盖），then 等响应回来再补。
    setMarked({ prev: null, label, then: "", value, pending: true });
    // ①' **外面那一行也立刻。** 上面那次 setMarked 只管展开面板**里面**；
    //    「这一行还在不在名单里」「要不要打开下一条」由 `App.afterStatus` 的
    //    `justActed` / `setSelectedId` 决定，而它们挂在 `onChanged` 上。
    //    `onChanged` 原来只在下面 `await` 之后调 —— 于是那两件纯界面的事
    //    跟着写盘一起等（实测导出子进程 3.4–4.2 秒）。
    //
    //    它是被 ③ 那个修复推过去的：为了不让重取抢在写盘前面，整个 `onChanged`
    //    被挪到了 await 之后，**该立刻做的 UI 一起被带走了**。
    //    一个回调捆了两件性质相反的事，拆成两拍：
    //      "now"     —— 只动界面，不重取
    //      "settled" —— 只重取，界面上面已经动过
    //    失败那一支不带相位（默认两件都做）：既回滚界面，也重取一次对齐。
    onChanged?.(true, "now");
    // ② 后台写。不设 busy——按钮此刻已经被「已记下」那一行取代了，
    //    没有需要禁用的东西。
    try {
      const r = await postStatus(job.id, value);
      setMarked((m) => (m && m.value === value
        ? { ...m, prev: r.prev, then: r.then, pending: false } : m));
      // ③ **写完才重取。** `onChanged` 触发的是整份快照重取，原来它排在
      //    `await postStatus` 前面：GET 抢在写盘之前发出，serve 那边看源文件
      //    还没变、直接把旧快照返回，而之后再没有第二次重取——于是「已投递」
      //    的计数、「下一步」那行、投后统计全停在旧值，直到用户手动刷新。
      //    界面的即时反馈由上面的乐观更新负责，不靠这一次重取。
      onChanged?.(true, "settled");
    } catch (e) {
      setMarked(null);                       // 回滚：盘上没写成，界面不能假装写了
      setStatusErr((e as Error).message || "没写进去");
      onChanged?.();
    }
  }

  //: 原因**重发一次同样的状态**，只多带一个 reason。
  //
  // 不另开一个 `/api/reason` 接口：那要再写一遍「找到这一行、校验、写盘」，
  // 而这三步 `set_status` 已经做对了（包括存量 CSV 自动补列）。
  // 服务端认这一种：状态不变 + 带原因 = 补字段，不走 `can_go`（终结态没有后继，
  // 走 can_go 必被挡）。notes 追加一条。
  async function saveReason(value: string) {
    setBusy("reason");
    setStatusErr("");
    // 同 `mark()`：**先改界面，再发请求。** 选了哪条原因是纯界面的事，
    // 没有理由陪着写盘等（实测导出子进程 3.4-4.2 秒）。
    // 回滚要**回到点之前那一版**，不是清空 —— 他可能是在改一个已经存过的原因，
    // 清空等于把之前那次也一起抹了。
    const prevReason = reason;
    const prevSaved = reasonSaved;
    setReason(reasons.find((r) => r.value === value)?.label || value);
    setReasonSaved(true);
    try {
      await postStatus(job.id, "rejected", value);
      onChanged?.();
    } catch (e) {
      setReason(prevReason);
      setReasonSaved(prevSaved);
      setStatusErr((e as Error).message || "没写进去");
    } finally {
      setBusy("");
    }
  }

  async function undo() {
    if (!marked || marked.pending) return;   // prev 还是占位，送出去会删掉整行
    setBusy("undo");
    setStatusErr("");
    // **撤销也立刻。** 「已记下」那一行是纯界面，等写盘等于点了撤销还看着
    // 「已记下」发呆几秒 —— 而这一下正是他发现记错了、最想立刻看到反应的时候。
    // 先把 `marked` 存下来：`postStatusUndo` 要读它的 `prev`，回滚也要拿它复原。
    const snapshot = marked;
    setMarked(null);
    try {
      await postStatusUndo(job.id, snapshot.prev);
      onChanged?.();   // 撤销不挪：行会回到名单里，挪走反而把视线带离他刚撤的那个岗
    } catch (e) {
      setMarked(snapshot);                 // 盘上没撤成，界面不能假装撤了
      setStatusErr((e as Error).message || "撤不掉");
    } finally {
      setBusy("");
    }
  }

  /**
   * 「HR 点开过这份简历没有」——**乐观更新**，同上面 `mark` 那条：
   * 这一下要表达的是「我知道你点了」，写盘是另一件事。
   *
   * 本地态初值取快照。`undefined` 是「还没查过」，**不是**「没打开」——
   * 三态一路送到服务端（`postHrViewed` 的 `null`），折成布尔值就把
   * 「我还没去看」变成了「看过、对方没打开」，而这两个的结论正好相反。
   */
  const [viewed, setViewed] = useState<boolean | null | undefined>(job.hrViewed);
  async function markViewed(v: boolean | null) {
    const was = viewed;
    setViewed(v ?? undefined);
    setStatusErr("");
    try {
      await postHrViewed(job.id, v);
      onChanged?.();
    } catch (e) {
      setViewed(was);                        // 回滚：盘上没写成，界面别假装写了
      setStatusErr((e as Error).message || "没写进去");
    }
  }

  const { plus, minus, gateLike } = splitReasons(job.dimensions);
  const unknowns = job.gates.filter(countsAsUnknown);
  const m = job.materials;
  // 粗筛的岗**没有**分项数据：没查硬门、没比对能力边界、没做公司调研。
  // 这时候绝不能渲染那四个区块——它们的空状态文案会把「没有数据」说成结论：
  // 「这些条件都核对过了，没有要问的」「没有明显加分项」「这 N 项都不拖后腿」。
  // 用户会以为硬门验过了。这是本页最危险的一种错误。
  const hasDetail =
    job.dimensions.length > 0 || job.gates.length > 0 || job.gaps.length > 0;
  // 「下一步」那行**真的**渲染出一条 /job-apply 了没有。下面那句「上面那条 /job-apply」
  // 原来靠 `!m?.greeting` 当代理条件去猜，而两者并不等价：有材料、但开场白没解析
  // 出来时，它会让人去找一条屏幕上没有的命令。指针就该看被指的那个东西本身。
  const applyAbove = Boolean(job.nextStep?.command?.startsWith("/job-apply"));

  return (
      <div className="readout-body">
        {/* ---- 怎么投：这块必须排最前，它是整页存在的目的 ---- */}
        <div className="act">
          {/* 逐岗的下一步。与顶部那条流水线建议**不是一回事**：那条说整体该干什么，
              这条说**这个岗**卡在哪。展开一个岗位时，用户要的正是后者——
              「这个我投了吗、下一步该干嘛」，而不是再看一遍全局状态。 */}
          {job.nextStep && (
            <div className="act-row jobstep">
              {/* 标签是「这个岗」而不是「下一步」：页面顶部那条流水线建议
                  也叫「下一步」，两个不同层级的东西同名，读者要靠位置去猜
                  哪个管哪个。区别原本只写在上面那段注释里——用户看不到注释。 */}
              <span className="jobstep-tag">这个岗</span>
              <span className="jobstep-text">{job.nextStep.text}</span>
              {/* `/job-outcome` 做的事**就是**这几个按钮做的事——改台账的状态。
                  有服务时两个都摆出来，等于让人先挑一个再做一遍。所以按钮在场
                  就撤掉这个命令片；需要模型判断的 `/job-interview`、`/job-offer` 不撤。 */}
              {job.nextStep.command &&
                !(steps.length > 0 && job.nextStep.command.startsWith("/job-outcome")) && (
                <Cmd>{job.nextStep.command}</Cmd>
              )}
              {/* 状态按钮就长在**解释它的那句话**旁边。
                  原来它自成一行、还顶着一个「发生了什么」的小标签，排在
                  「在猎聘打开这个职位」**上面**——先让人记「投了」，再给他去投的
                  工具，顺序是反的。而回头来记那一笔时，人找的正是这条「下一步」。 */}
              {/* ① 推进这一笔：我投了 / 约面了 / 挂了 / 拿到 offer…
                  它们改的是**投递进度**，紧跟在解释这一步的那句话后面。 */}
              {/* `!marked`：记完就把这排收掉。乐观更新之后界面立刻进入「已记下」，
                  而 `steps` 来自快照、要等重取才变——不加这个条件，同一行会同时
                  出现「我投了」按钮和「已记下：我投了」，读起来像没记上。 */}
              {steps.length > 0 && !marked && (
                <span className="act-group act-advance">
                  {steps.map((s) => (
                    <Button
                      key={s.value}
                      size="small"
                      onClick={() => mark(s.value, s.label)}
                    >
                      {s.label}
                    </Button>
                  ))}
                </span>
              )}
              {/* ①b 投出去之后那一条**观察**：HR 点开过这份简历没有。
                  与①不是一回事——①推进投递进度，这一条记的是平台白给的一个
                  事实（猎聘/智联写「已查看 / 未查看」，BOSS 看对面点没点开）。
                  它决定「投了没回音」该怪谁：已查看还是没回 → 才轮到审简历；
                  大多未查看 → 改简历没用，要换的是投什么岗（`job-outcome.md`
                  Step 2b 那张表）。此前这个答案只能记在脑子里，查一次忘一次。 */}
              {job.applied && hasServer() && !marked && (
                <span className="act-group act-viewed">
                  <span className="act-viewed-q">对方点开简历了吗</span>
                  {([[true, "点开了"], [false, "还没点开"]] as const).map(
                    ([v, label]) => (
                      <Button
                        key={label}
                        size="small"
                        type={viewed === v ? "primary" : "default"}
                        title={viewed === v
                          ? "再点一下撤销"
                          : "去平台的「投递记录」页看一眼"}
                        onClick={() => markViewed(viewed === v ? null : v)}
                      >
                        {label}
                      </Button>
                    ))}
                </span>
              )}
              {/* ② 从名单里拿掉：不投 / 已下线。
                  **与①分成两组**，中间一条竖线、整组靠右、字重更轻。
                  原来这两类按钮同字重同一行，中间隔着一整句长说明——用户原话
                  「我投了、不投这个岗的按钮…现在有点混在一起」。它们是两种性质
                  的动作：①推进流程，②把这一行从名单里拿掉，混排会让人误点。
                  组内两个也要分清：「不投」是你的判断，「已下线」是外面的事实。 */}
              {(onExclude || onExpire) && !marked && (
                <span className="act-group act-remove">
                  <span className="act-sep" aria-hidden />
                  {/* 提示写在按钮自己身上，不再另起一行。原来每个展开行下面都跟着
                      一句「点『不投这个岗』直接存进本机数据，刷新还在。想反悔——
                      下面『不投的岗位』里点『放回可以投』」——一句关于按钮的说明，
                      在 24 个岗上重复 24 遍，占的还是「怎么投」这块最显眼的位置。
                      按钮的 title 本来就在说同一件事，缺的只是「去哪找回来」。 */}
                  {onExclude && (
                    <Button size="small" className="act-drop" disabled={Boolean(busy)}
                            onClick={onExclude}
                            title="我不想投这个岗。点了直接写进本机记录，刷新还在；想反悔到页面底部「不投的岗位」里放回">
                      不投这个岗
                    </Button>
                  )}
                  {/* 只在有本地服务时给：它写的是盘上的状态，没有服务写不了，
                      给一个点了没反应的按钮比不给更糟。 */}
                  {onExpire && hasServer() && (
                    <Button size="small" className="act-expire" disabled={Boolean(busy)}
                            onClick={onExpire}
                            title="这个职位已经关了 / 报名截止 / 点开是聚合页。分数与评估都留着，标错了到「不投的岗位」里放回">
                      职位已下线
                    </Button>
                  )}
                </span>
              )}
              {marked && (
                <span className="status-done">
                  {/* **必须点名记的是哪一个。** 记完之后这一排换成了「下一步」能点的
                      按钮，刚按下的那个（我投了）已经不在行里了——只写「已记下」，
                      读的人对不上它指谁。一个动作从按下到确认要用同一个名字。 */}
                  已记下：{marked.label}
                  {/* 写盘还没回来时禁掉：那一刻 `prev` 是占位 null，而服务端把
                      null 读成「这行是我刚建的，撤销＝删掉它」。窗口只有一次
                      POST 的时间，但撞上的代价是整条投递记录消失。 */}
                  <button type="button" className="status-undo" onClick={undo}
                          disabled={Boolean(busy) || Boolean(marked.pending)}
                          title={marked.pending ? "正在写入，稍等一下再撤" : "撤回这一笔"}>
                    撤销
                  </button>
                  {/* 记完还需要模型的那一步：状态归页面，判断归命令行 */}
                  {marked.then && (
                    <Cmd>{`${marked.then} ${job.company}`}</Cmd>
                  )}
                </span>
              )}
              {/* 「挂了」之后的可选补充。**只在被拒时出现**——约到面试不需要理由，
                  没下文本身就是理由。不填是正常路径，所以这里没有「保存」按钮：
                  点一下就写盘，不点就什么都不发生。 */}
              {marked && marked.value === "rejected" && reasons.length > 0 && (
                <div className="why-row">
                  <span className="why-k">
                    {reasonSaved ? "记下了" : "知道原因的话点一下（可以不填）"}
                  </span>
                  {!reasonSaved && reasons.map((r) => (
                    <button type="button" key={r.value} className="why-chip"
                            disabled={Boolean(busy)}
                            onClick={() => saveReason(r.value)}>
                      {r.label}
                    </button>
                  ))}
                  {reasonSaved && <b>{reason}</b>}
                </div>
              )}
            </div>
          )}
          {/* **没记上**这句话原来写在上面那个 `{marked && …}` 块**里面**。
              于是失败那一支的 `setMarked(null)`（回滚乐观更新）把整块卸载了，
              紧接着设置的 `statusErr` **根本没有地方显示**——页面看起来就是
              「点了没反应」。

              实测 2026-10-23：服务重启过，页面上那个写操作凭据过期了，
              点「我投了」一律 403；用户看到的零反馈就是这么来的
              （写操作那层现在会自己换新凭据重试一次，见
              `data/excluded.ts` 的 `refreshToken`；这一条是**兜底**：
              真的没写进去时，人必须看得见为什么）。

              所以它挪到 `{marked && …}` **外面**——回滚之后照常显示。 */}
          {statusErr && (
            <span className="status-err" role="alert">
              没记上：{statusErr}
            </span>
          )}
          <div className="act-row">
            <Button href={job.url} target="_blank" rel="noopener">
              {/* channel 可能是空串（认不出的平台）——「在打开这个职位」是句残话 */}
              {job.channel ? `在${job.channel}打开这个职位 ↗` : "打开这个职位 ↗"}
            </Button>
            {m?.resumePdf && (
              <Button href={m.resumePdf} target="_blank" rel="noopener">
                打开定制简历 PDF
              </Button>
            )}
            {/* **这份是不是已经过时了** —— 查在他要打开/发出这份 PDF 的
                那一下，和开场白那条警告同一个道理。导出器从 2026-08-22 起
                就在算（`materials.resumeStale`），而这里一直没读：实测
                15 份定制简历 15 份全部早于主简历，按钮照常只写
                「打开定制简历 PDF」。面试官读的就是这一份。 */}
            {m?.resumeStale && (
              <span className="act-note is-warn">
                {`这份比主简历旧（主简历改于${m.resumeStale}）——发之前重出一份：`}
                <Cmd>{`/job-cv ${job.url}`}</Cmd>
              </span>
            )}
            {m?.coverLetter && <span className="act-note">求职信已生成，在同一目录</span>}
            {/* 同一个岗在别处的挂法：链接都给出来——投哪个渠道由用户挑，
                同岗不同价还能当谈薪的参照 */}
            {job.duplicates && job.duplicates.length > 0 && (
              <span className="act-note">
                这个岗在别处也挂着，价不一样：
                {job.duplicates.map((d, i) => (
                  <a key={d.url} href={d.url} target="_blank" rel="noopener noreferrer">
                    {i > 0 && "、"}
                    {d.salary || "薪资未标"}
                  </a>
                ))}
              </span>
            )}
            {/* 同文不同名：**摆出来，不替他判**。上面那条 `duplicates` 是已经
                认定同岗、归并掉的；这一条是「正文一字不差、公司名不一样」——
                可能是一个岗两家猎头在代招（只该投一个，投两个会撞单），
                也可能是两家公司套了同一份模板（两个都该投）。判据在
                `export_web_data` 那段注释里，这里只负责让他看得见。 */}
            {job.sameJd && job.sameJd.length > 0 && (
              <span className="act-note is-warn">
                这个岗的职位描述和另外 {job.sameJd.length} 个一字不差，公司写的却不是同一家：
                {job.sameJd.map((d, i) => (
                  <a key={d.url} href={d.url} target="_blank" rel="noopener noreferrer">
                    {i > 0 && "、"}
                    {d.company || "公司未写"}
                    {d.salary ? `（${d.salary}）` : ""}
                  </a>
                ))}
                。同一个岗两家猎头代招是常事——真是同一个就只投一个，两边都投会撞单
              </span>
            )}
            {unknowns.length > 0 && (
              <span className="act-note is-warn">
                投之前先问清 {unknowns.length} 条（见下方「硬性条件」）
              </span>
            )}
            {/* 「不投这个岗」挪到上面那行、紧挨着「我投了」了。这里只在**没有
                「这个岗」那一行**时兜底——已结案的岗（入职 / 挂了 / 没下文）
                `job.nextStep` 是 null，整行不渲染，否则就没地方排除它了。 */}
            {onExclude && !job.nextStep && (
              <Button className="act-drop" onClick={onExclude}>
                不投这个岗
              </Button>
            )}
          </div>
          {/* 这里原来有一行「点『不投这个岗』直接存进本机数据，刷新还在。想反悔——
              下面『不投的岗位』里点『放回可以投』。」现在没有了，两段历史都记在这里，
              因为它们各留下一条还在生效的约束：

              ① **它是一句关于按钮的说明，却按行渲染**——展开哪个岗都跟着出现一遍，
                 占的是「怎么投」这块最显眼的位置。整句挪进了那个按钮自己的 title，
                 包括「去哪找回来」那半句（底部 `pending-bar` 没有这句，而岗位点完
                 就从列表里消失了，不说他不知道去哪找）。
              ② 更早还有一版：它**无条件**渲染静态模式那套说辞，于是有本地服务时
                 页面自相矛盾——行内说「要复制底部那条命令才永久生效」，页脚说
                 「直接存进本机数据，刷新还在」，而底部那条命令按 `App.tsx` 的
                 `!live` 判断根本不会出现。用户照着找了一圈没找到，只能得出
                 「这工具在骗我」。

              **留下的规矩**：只在一种模式下成立的话，必须挂在模式判断下，而模式
              一律现调 `hasServer()`、不从 props 传——调用点忘了传就得到 `undefined`
              （假值），正好复现 ② 那个 bug。`tests/test_web_copy.py` 的
              `STATIC_ONLY_PHRASES` 逐个渲染点扫这件事。 */}
          {/* **要问什么，摆在「复制开场白」之前。**
              列表上那枚「话术备好 · 先问清」只说了「要问」——而「问什么」
              一直躺在评估文件里，得自己打开翻。
              实测 144 个「可以考虑」里只有 7 个把这几条写进了规定的小节，
              其余散在「建议」「真伪信号」等五个不同标题下（`parse_ask_before`
              因此宽进）。位置放在这儿：他要复制那段话之前先看见。 */}
          {/* **空着的时候也要说一句 —— 只对「可以考虑」这一档。**

              这一档的定义就是「先问清楚再决定投不投」。清单空着时这一块
              整个不渲染，于是屏幕上只剩一段可复制的开场白 ——
              用户分不清是「没什么可问的」还是「深评根本没写」。

              实测 2026-08-31：活的「可以考虑」里 56 个已备开场白，
              其中 **47 个（84%）这一块是空的**，而这 47 个**全部深评过**。
              也就是说不是「还没评到」，是评了没写。

              别的档不提示：`值得投` 本来就不必等答案再投（下面那句已经
              写着），对它们喊一句「缺清单」是一条永远为真的噪音。 */}
          {/* **评估自己的结论，排在最前面。**

              它和上面那枚判词可以合法地不一致（判词是打分档，这里是读完之后
              的人话结论），而在此之前它**根本没被导出**——屏幕上只有判词那一半，
              于是「可以考虑 + 材料就绪」的岗一路催到底，评估里那句「不投」
              一个字都到不了眼前。判据与措辞见 `build_dashboard._advises_against`。 */}
          {job.advice && (
            <p className={"job-advice" + (ADVISES_AGAINST.test(job.advice)
              ? " is-against" : "")}>
              <b>评估的结论：</b>{job.advice}
            </p>
          )}
          {(job.askBefore?.length ?? 0) === 0
            && plainVerdict(job.verdict) === "可以考虑" && (
            <p className="greet-warn">
              {"这一档的意思是「先问清楚再决定投不投」，而这个岗没写要问什么。"}
              {"发之前先补一份："}
              <Cmd>{`/job-apply ${job.url}`}</Cmd>
            </p>
          )}
          {(job.askBefore?.length ?? 0) > 0 && (
            <div className="ask-before">
              <div className="kicker">投之前先问清这几条</div>
              <ul>
                {job.askBefore!.map((q) => <li key={q}>{q}</li>)}
              </ul>
              <p>
                {plainVerdict(job.verdict) === "可以考虑"
                  ? "这一档的意思就是「问清楚再决定投不投」——问完觉得行，下面的开场白再发。"
                  : "这几条不必等答案再投，可以在开场白之后的对话里问。"}
              </p>
            </div>
          )}

          {m?.greeting ? (
            <div>
              {/* **这一下是整页最常按的。** 原来它是一个 14px 的灰图标，跟在一行
                  12.5px 的说明后面，比旁边「不投这个岗」还轻——而整页存在的目的
                  就是让人把这段话复制走、去投。给它一个带字的按钮，说明退到后面。 */}
              <div className="greet-head">
                <CopyButton text={m.greeting} label="复制开场白" what="打招呼开场白" />
                {/* **别对每个岗都说「聊天框」。** 猎聘的企业直招多半只有站内信
                    或网申表单（`job-gmail-sync.md` 那张渠道表就是这么分的），
                    实测 2026-10-14：405 份里 97 份被指去找一个不存在的聊天框。
                    判据在 `_cli.send_hint`，与催进度那一侧同源。
                    旧快照没有 `sendVia` → 退回原来那句，不留空。 */}
                <span className="act-label">
                  {m.sendVia
                    ?? (job.channel ? `粘到 ${job.channel} 的聊天框直接发`
                                    : "粘到聊天框直接发")}
                </span>
              </div>
              {/* **对面是谁，决定第二轮怎么说。** 开场白这一层三档没有区别
                  （期望薪资与到岗时间一律不写），但对着用人部门老大讲职业规划
                  与稳定性，是把唯一一次直达决策人的机会说成 HR 面。
                  判据在 `_cli.counterpart_of`，与 `/job-apply` 1.5b 同源。
                  职务认不出时没有这个键 —— 不猜，也就不印。 */}
              {m.counterpart === "用人方" && (
                <p className="act-label">
                  对面是用人部门的人，不是 HR。他回你之后，讲具体怎么落地：上手第一件事、他现在卡在哪。别讲职业规划和稳定性。
                </p>
              )}
              <p className="greeting">{m.greeting}</p>
              {/* **发之前先删掉这几处。** 这几条铁律写在
                  `06-outreach-templates.md`（「这 200 字里不许出现的五类」），
                  连「实际写过的」原句都列了 —— 生成端漏过，2026-10-14 现算
                  405 份里 **0 份**踩线，「开场铺垫」那一类也已经归零。
                  查在这儿，是因为这是他按「复制开场白」的地方。
                  说「删掉」不说「有问题」：他要的是动作，不是评价。 */}
              {(m.greetingWarn?.length ?? 0) > 0 && (
                <p className="greet-warn">
                  发之前删掉：{m.greetingWarn!.join("；")}。
                  <i>开场铺垫说的都是对方已经知道的事（岗位名是他写的），一句平均吃掉 15 字；钱和到岗时间等他回话之后再谈。</i>
                </p>
              )}
              {/* **在跟谁说话** —— 和上面那条一样查在他按「复制开场白」的地方。
                  它不是文风问题：第二轮怎么说话完全取决于这半句（猎头问薪资与
                  到岗时间要直接答，HR 直招不主动展开）。写反了，第一次回话就走反。
                  审计一直在报这三个数（没写 110 / 写反 28 / 对顾问说「贵司」9），
                  但那是事后的一份清单 —— 这儿才是他要用这段话的时刻。 */}
              {m.addresseeWarn && (
                <p className="greet-warn addressee-warn">
                  发之前先看一眼：{m.addresseeWarn}。
                </p>
              )}
              {/* **这句公司的事，你从哪看来的。** 和上面两条同一个位置、
                  同一个理由：编造的代价落在对方第一轮追问的时候，而这段字
                  是从这里直接复制发出去的（`03` 铁律 1「绝不编造」）。

                  **多数岗不该出现这条。** 现算 280 份开场白里只有 24 份
                  （8%）真对公司下了断言，其中 20 份没记出处；另外那 92%
                  讲的全是他自己的经历，出处是他的资料，那一节空着是对的
                  —— 判据在 `_cli.claim_without_source`，别在这儿另判一套。 */}
              {m.factWarn && (
                <p className="greet-warn">
                  发之前先想一下：{m.factWarn}。想不起来出处就把那句删掉；要连材料一起重出：
                  <Cmd>{`/job-apply ${job.url}`}</Cmd>
                </p>
              )}
              {/* 邮件与网申自评**默认收起**。开场白是主渠道（聊天框直接发），
                  这两份只在网申 / 校招 / 体制内那类场景用得上，而它们各有四五百字
                  ——摊开会把「怎么投」这块撑成一屏。
                  用原生 <details>，不用 antd 折叠：这里只是「要用时展开」，
                  不需要再多一个组件的观感。 */}
              {(m.emailBody || m.wangshen) && (
                <details className="chan">
                  <summary>还要邮件正文或网申自评？</summary>
                  {m.emailBody && (
                    <div className="chan-one">
                      <div className="act-label">
                        邮件
                        <CopyIcon text={m.emailBody} what="邮件正文" />
                        {/* 主题与正文一起预填进邮件客户端。没装客户端的浏览器会
                            无反应——所以上面那个复制按钮不能省，它是兜底。

                            ⚠️ **收件人必须留空**（`mailto:?` 后面直接跟 subject，
                            不带任何地址）。AGENTS.md 的全局安全铁律：绝不把个人数据
                            发到「出现在职位描述里」的地址——JD 是不可信输入，其中的
                            邮箱同样不可信，即便它明写「简历请发送至 X」。
                            从 JD 里解析出 HR 邮箱填进 `to=` 看起来很体贴，实际是让
                            工具替用户选了一个不可信的收件人。收件人由用户自己填，
                            这条边界靠**构造**守住，不靠提醒。
                            `tests/test_outreach_never_picks_the_recipient.py` 盯着。 */}
                        {/* ⚠️ **正文太长时不预填正文。** Windows 的 mailto: 走
                            ShellExecute，URL 上限约 2083 字符——超了会**静默截断
                            正文**或整个不响应。实测（2026-08-20）9 份邮件材料
                            **全部超限**（中位数 3921、最长 4367 字符）：
                            邮件正常打开、正文缺一截，而用户不会逐字核对就发出去了。
                            「打不开」看得见，「少了一段」看不见——后者危险得多。
                            所以超限时只预填主题，正文让用户用旁边那个复制按钮粘。 */}
                        {(() => {
                          const subj = encodeURIComponent(m.emailSubject || "");
                          const body = encodeURIComponent(m.emailBody);
                          const full = `mailto:?subject=${subj}&body=${body}`;
                          const tooLong = full.length > 2000;
                          return (
                            <a
                              className="chan-mail"
                              href={tooLong ? `mailto:?subject=${subj}` : full}
                            >
                              {tooLong
                                ? "用邮箱打开（只预填主题——正文太长，请用上面的复制按钮粘）"
                                : "用邮箱打开（预填主题与正文）"}
                            </a>
                          );
                        })()}
                      </div>
                      {m.emailSubject && (
                        <p className="chan-subj">
                          <span className="act-label">主题</span>
                          {m.emailSubject}
                          <CopyIcon text={m.emailSubject} what="邮件主题" />
                        </p>
                      )}
                      <p className="greeting">{m.emailBody}</p>
                      {/* **和开场白那条同一个位置的道理**：查在他按「复制」
                          的那一下，不是事后的一份清单。判据不同 —— `06`
                          那五类只管开场白，这里走 `03` 的风格铁律
                          （`_cli.style_problems`）。 */}
                      {(m.emailBodyWarn?.length ?? 0) > 0 && (
                        <p className="greet-warn">
                          发之前删掉：{m.emailBodyWarn!.join("；")}。
                        </p>
                      )}
                    </div>
                  )}
                  {m.wangshen && (
                    <div className="chan-one">
                      <div className="act-label">
                        网申自评（粘进表单的自我评价栏）
                        <CopyIcon text={m.wangshen} what="网申自评" />
                      </div>
                      <p className="greeting">{m.wangshen}</p>
                      {(m.wangshenWarn?.length ?? 0) > 0 && (
                        <p className="greet-warn">
                          粘进去之前删掉：{m.wangshenWarn!.join("；")}。
                        </p>
                      )}
                    </div>
                  )}
                </details>
              )}
            </div>
          ) : null}
          {/* 这里原来有个空状态：「还没出投递材料——复制这条让 Claude Code 生成：
              /job-apply <url>」。它和上面「下一步」那行**给的是同一条命令**，而两边的
              条件恒等（都是「这个岗没有材料」），所以不是偶尔撞车——**每一个还没
              出材料的岗，展开后都会把同一条命令印两遍**，间隔不到 120px。
              新用户手上一个材料都没有，于是他展开的每一行都是这样。
              留「下一步」那行：它在最上面，且各种状态下都在同一个位置说
              「这个岗卡在哪」（还没出材料 → /job-apply；材料就绪 → 去投；已投 →
              /job-outcome）。空状态另起一句只是把同一件事换个说法再讲一遍。 */}
        </div>

        {/* 「上面那条」曾经写死。可它指的那个命令块条件是 `!m?.greeting`，而这段话
            的条件是 `!hasDetail` —— **两个不同的条件**。有话术、但 evaluation.md
            没解析出表格时（实测发生过：硬门表标题不带「硬门」二字就整张丢弃），
            上面显示的是开场白，这句话却让人去找一条屏幕上没有的命令。
            所以：命令在上面就指过去，不在就地给出——而「在不在上面」现在直接看
            上面那行渲染的是什么（`applyAbove`），不再拿另一个条件去猜。 */}
        {!hasDetail && (
          <p className="no-detail">
            这个岗只按列表信息评过——<b>硬性条件一条都还没核对</b>
            {"，也没做公司调研、没比对你的经历缺口。"}
            {applyAbove ? (
              <>
                上面那条 <Cmd>/job-apply</Cmd> 跑完才会有这些。
              </>
            ) : (
              <>
                跑 <Cmd>{`/job-apply ${job.url}`}</Cmd> 才会有这些。
              </>
            )}
          </p>
        )}

        {hasDetail && (
        <>
        {/* ---- 为什么是这个结论：人话，不上百分比 ---- */}
        <div className="reasons">
          <section className="reason-col reason-plus">
            <h4>对口的地方</h4>
            {plus.length > 0 ? (
              <ul>
                {plus.map((d) => (
                  <li key={d.name}>
                    <b>{d.name}</b>：{d.note}
                  </li>
                ))}
              </ul>
            ) : (
              /* 全都没打分 ≠ 没有加分项。实测（2026-08-20）1 个岗四维全空，
                 却会被告知「分数主要靠没踩雷撑着」——它根本没打过分，
                 那句话把「没评」讲成了「评过，平平」。 */
              /* **判据是「这几项到底打没打过分」，不是数个数。**
                 原来写的是 `minus.length === job.dimensions.length` ——
                 而这里已经在 `plus.length === 0` 的分支里，`plus + minus` 就是
                 全部计权维度，所以那个等式**恒为真**，下面那句从来没出现过。
                 实测 2026-08-23：62 个没有加分项的岗里，**61 个是打过分、
                 只是都低于 70**，它们看到的却是「都还没打分」—— 一句
                 事实上错误的话；真·全没打分的只有 1 个。 */
              minus.every((d) => d.score === null) ? (
                <p className="reason-empty">这几项都还没打分，加分项无从谈起。</p>
              ) : (
                <p className="reason-empty">没有明显加分项——分数主要靠没踩雷撑着。</p>
              )
            )}
          </section>
          <section className="reason-col reason-minus">
            <h4>要掂量的地方</h4>
            {minus.length > 0 ? (
              <ul>
                {minus.map((d) => (
                  <li key={d.name}>
                    <b>{d.name}</b>：{d.score === null ? `这项没打分——${d.note}` : d.note}
                  </li>
                ))}
              </ul>
            ) : (
              /* 不写死「四项」：维度数不是常数。实测 132 个岗四维、
                 **106 个岗五维**（多一项「地点（当前/搬迁）」）。 */
              <p className="reason-empty">这 {plus.length + minus.length} 项都不拖后腿。</p>
            )}
          </section>
        </div>
        {/* 评分明细表里混进来的 Pass/Fail 门（眼下只有「地点」）。
            **不判好坏、不说「没打分」**：对一道门来说不打分是设计如此。
            原样把写手那句话摆出来，他自己看得懂
            （「上海」= 通过；「杭州（跨城，需自行拍板）」= 要拍板）。 */}
        {gateLike.length > 0 && (
          <p className="gate-note">
            {gateLike.map((d) => `${d.name}：${d.note}`).join(" · ")}
          </p>
        )}

        <div className="sec-head is-readout">
          <h2>{"硬性条件"}</h2>
          {/* 这句原来无条件显示。7 条全过、0 条待确认时，它在提醒一个不存在的情况
              ——框架自己论证过这种形状（竞业限制那节：「一条永远为真的提醒，
              对 99% 的岗位没有判别力」）。只在真有要留意的条目时才说。 */}
          {job.gates.some(
            (g) => g.state === "fail" || countsAsUnknown(g) || g.assumed,
          ) && (
            <span className="sec-note">有一条不满足就别投 ·「还没查到」不算满足</span>
          )}
        </div>
        <GateGrid gates={job.gates} url={job.url} notJudged={job.gatesNotJudged} />

        {/* **两格都空就一句话带过，不摆两个空盒子。**
            上一版是「盒子留着、标题里改一句话」（「这个岗没有」）。实测下来那不叫
            说出结论，叫留了两个带标题的空框：左边一行小字下面 60px 空白，右边一个
            空列表加一句解释——解释的还是屏幕上不存在的东西。
            「没有对不上的地方」确实是个结论，但它值一行，不值两个框。
            只空一边时留下有内容的那个，让它独占整行，不留半张空桌子。 */}
        {job.gaps.length === 0 && job.quality.length === 0 ? (
          <p className="gate-note">
            经历上没有对不上的地方，公司和职位信息也没有要核实的——写材料时按你的真实经历写就行。
          </p>
        ) : (
        <div className="two-col" data-single={job.gaps.length === 0 || job.quality.length === 0}>
          {job.gaps.length > 0 && (
          <section className="slab">
            <div className="slab-head">
              <h3>经历对不上的地方</h3>
              <span className="sec-note">写材料时这几处不能吹</span>
            </div>
            {job.gaps.map((g) => (
              <div className="gap-item" key={g.claim}>
                {g.kind && <span className="gap-kind">{g.kind}</span>}
                <span>
                  <strong>{g.claim}</strong>
                  {/* detail 可能为空（bullet 没有「——」分隔）——别渲染出「xx —— 。」的残句 */}
                  {g.detail && <>{" —— "}{g.detail}</>}
                  {g.overclaim && (
                    <>
                      ，不能写成<s>「{g.overclaim}」</s>
                    </>
                  )}
                  。
                </span>
              </div>
            ))}
          </section>
          )}

          {job.quality.length > 0 && (
          <section className="slab">
            <div className="slab-head">
              <h3>待核实的信息</h3>
              {/* 「不算进分数」是**安抚**（这些不确定不会拖累这个岗的分），不是警示。
                  原来用 --caution（琥珀＝要留意）把信号弄反了：读的人第一眼以为
                  这里有风险，其实这句话在说没风险。语义色跟着**这句话的意思**走，
                  不跟着它所在的区块走。 */}
              <span
                className="kicker is-tag"
              >
                不算进分数
              </span>
            </div>
            <ul className="quality-list">
              {/* **标题可能是空的。** `04-job-evaluation.md` 给这一节的模板
                  就是一个纯文本项目符号（`- ...`），没有粗体标题 —— 实测 251 条
                  里多数是那个形状。无条件渲染 `<strong></strong>：` 会在行首吊
                  一个冒号，和隔壁「缺口」那条注释说的「xx —— 。」是同一族残句。

                  key 也不能再用 `q.title`：空标题会撞成一堆同 key。 */}
              {job.quality.map((q, i) => (
                <li key={`${i}-${q.title}`}>
                  {q.title ? (
                    <>
                      <strong>{q.title}</strong>：{q.detail}
                    </>
                  ) : (
                    q.detail
                  )}
                </li>
              ))}
            </ul>
            <p className="quality-foot">
              这些是信息本身没核实清楚，不是岗位的缺点，所以不扣分。投不投你自己定。
            </p>
          </section>
          )}
        </div>
        )}
        </>
        )}
        <InterviewLog job={job} />
      </div>
  );
}
