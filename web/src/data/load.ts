import type {
  BaseResume, CommandGroup, EnvItem, Job, NextStep, OutcomeStats, PipelineStage,
  JobPref, Portal, ResumeInsight, HrAnswer,
} from "../types";
import {
  activeUser as demoUser,
  jobs as demoJobs,
  pipeline as demoPipeline,
  nextStep as demoNextStep,
  envItems as demoEnv,
} from "./sample";

/**
 * 数据来源：优先读 `public/data.json`（`python tools/export_web_data.py` 导出的**真实**
 * 数据），读不到才回退 `sample.ts` 的虚构演示数据。
 *
 * `isRealData` 必须一路传到界面上并显示出来。第一版没有这个标记，于是虚构数据
 * 长得跟真的一样——职位链接点了打不开、简历 PDF 指向不存在的文件，按钮看着能用其实
 * 是死的。**演示数据必须自己承认自己是演示数据。**
 */
export interface Snapshot {
  isRealData: boolean;
  activeUser: string;
  allUsers?: string[];
  /** HR 常问的那几句 + 写好的答案（`profile/hr-answers.md`）。 */
  hrAnswers?: HrAnswer[];
  /** 降权泊车：留在待评但排到队尾的岗数（见 prescreen 的规则分组） */
  parked?: number;
  baseResume?: BaseResume;
  pipeline: PipelineStage[];
  jobs: Job[];
  envItems: EnvItem[];
  /** 全部可用命令，按流程分组。空表 = 导出器没给，那一块不显示。 */
  commands?: CommandGroup[];
  /** 投后统计。后端算好送来，前端不自己算——两处各算一份必然飘。 */
  outcomeStats?: OutcomeStats;
  /** 卡在硬性条件上的岗按门归一计数，倒序。见 `export_web_data.gate_fail_tally`。 */
  gateFailTally?: { gate: string; n: number }[];
  /** 他自己划的那几条排除各挡掉多少个岗，倒序，最多三条。
   *  上面那个 `gateFailTally` 只给得出十一条加起来的总数，
   *  而他要决定的是**动哪一条**。见 `export_web_data.top_exclusions`。 */
  topExclusions?: { rule: string; n: number }[];
  /** 库里明写薪数的岗，薪数中位数（不足 30 个给 null）。
   *  只用来给「按 12 薪保守算」一个参照，**不参与任何折算**。 */
  observedMonths?: number | null;
  /** 在线简历多久没刷新算旧。正本在 `export_web_data.RESUME_STALE_DAYS`。 */
  resumeStaleDays?: number | null;
  /**
   * 读数据失败时的一句话原因（**空串 = 没失败**）。
   *
   * 为什么要有它：原来失败一律退回演示数据，而演示数据是**别人的求职进度** ——
   * 一个真实用户看到的是「示例用户」的 110/23/3 与 5 个虚构职位。页头那行
   * 「演示数据（虚构）」虽然诚实，却要用户先注意到它；没注意到的人会把
   * 虚构的数字当成自己的。
   *
   * 只在**服务端确实在、却没把数据交出来**时填（见 `loadSnapshot`）：
   * 服务压根没起时演示数据是一份正当的首次体验，不该报错。
   */
  loadError?: string;
  /** 「挂了」时可以点的原因，来自 `tracker.REASONS`，前端不写死。 */
  outcomeReasons?: { value: string; label: string }[];
  nextStep: NextStep;
  /** 自动探测到的宿主 AI 编码工具，正本见 _cli.detect_code_tool：antigravity / claude / mimo / qoder / qwen / generic（或 JOBS_CODE_TOOL 覆盖值） */
  detectedTool?: string;
  /** 市场怎么读这份简历。评估不足时导出器不给这个字段，面板整块不显示。 */
  resumeInsight?: ResumeInsight;
  /**
   * 面板服务启动之后被改过的后台代码文件——`serve.py` 在每次 `/data.json`
   * 响应里现塞的（不落盘）。非空 = 页面上的按钮还在按旧代码写盘，
   * 该提醒用户重启服务。终端那行警告 nohup 一包就没人看见，
   * 所以这个信号必须走到用户真正盯着的地方。
   */
  staleCode?: string[];
  /** 各招聘网站的状态与开关。导出器不给时那一块不显示。 */
  portals?: Portal[];
  /** 「这几类岗要不要看」。导出器不给时那一块不显示。 */
  prefs?: JobPref[];
  /** 收进存档的老岗数（出局超过两周的）。0 或缺省时那行说明不显示。 */
  archivedCount?: number;
  /** 该重跑一遍的岗数（判断翻了档的，或当时没读到职位描述、现在读得到的）。
   *  0 或缺省时那行说明不显示。判据在 `tools/stale_materials.py`。 */
  restaleCount?: number;
}

const demo: Snapshot = {
  isRealData: false,
  activeUser: demoUser,
  pipeline: demoPipeline,
  jobs: demoJobs,
  envItems: demoEnv,
  nextStep: demoNextStep,
};

/**
 * 读 `data.json` 的上限。**没有它这一格可以永远转下去。**
 *
 * `fetch` 只有在**拿到响应头**之后才 resolve；正文那一段断了（连接被重置、
 * 服务进程被杀、`Content-Length` 说好了多少却没送够），它既不 resolve 也不
 * reject —— 只是永远不 settle。实测 2026-10-12：这一格停在
 * 「正在读取本机数据…」两分钟不动，浏览器控制台连一条错都没有，
 * 而 `python tools/serve.py` 那边的日志是一串
 * `ConnectionAbortedError`。
 *
 * **`try/catch` 抓不到这种「悬着」** —— 它不是异常，是没结束。
 * 所以那道闸门必须是一个真的会响的东西：超时主动 abort。
 *
 * 取 20 秒：这份数据现在 2.4 MB，本机实测直连取回 0.2 秒、浏览器里渲染
 * 约 7 秒。20 秒给慢机器留了三倍余量，又不至于让人以为页面死了。
 */
const LOAD_TIMEOUT_MS = 20000;

export async function loadSnapshot(): Promise<Snapshot> {
  // 只有 fetch 这一条路：数据一律由 `serve.py` 提供。曾经并存的「把数据内联进单文件
  // HTML、file:// 直开」那条已删——原委见 `web/README.md`。
  //
  // `reached` 记的是**服务端有没有接上**这一个事实：连不上（`serve.py` 没起）
  // 与接上了却没交出数据（500 / 正文断在半路 / 超时），对用户是两件不同的事，
  // 前者退回演示数据是正当的首次体验，后者必须说出来 —— 见 `loadError`。
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), LOAD_TIMEOUT_MS);
  let reached = false;
  try {
    const res = await fetch("data.json", { cache: "no-store", signal: ctl.signal });
    reached = true;
    if (!res.ok) return { ...demo, loadError: `数据接口回了 ${res.status}` };
    const d = (await res.json()) as Partial<Snapshot>;
    // **「导出器没跑过」和「跑过，但这个人还没抓职位」是两回事。**
    //
    // 原来一律按 `jobs.length === 0` 退回演示数据。而那正是**每个新用户跑完
    // `/job-setup` 之后的状态**——他会看到「示例用户」的 110/23/3 和 5 个虚构职位，
    // 而导出器已经为他算好的那句「还没抓职位：跑 /job-scrape 找新岗」被整个丢掉。
    //
    // 页头那行「演示数据（虚构）」是诚实的，但它救不了这件事：新用户第一次打开
    // 面板，看到的是别人的求职进度，而唯一该告诉他的那句话不见了。
    //
    // 判据：`isRealData` 是导出器自己盖的章。有它就说明这份数据是这个人的，
    // 哪怕一个职位都没有——空状态是他真实的状态，如实显示。
    if (d.isRealData) return { ...normalize(d), isRealData: true };
    if (!Array.isArray(d.jobs) || d.jobs.length === 0) return demo;
    return { ...normalize(d), isRealData: true };
  } catch {
    // ⚠️ **`AbortError` 是这里唯一会「悬着」的那一种的解药**，不是超时了就算了：
    // 悬着的话这一格永远不结束，而用户能做的只有刷新或干等。
    return reached
      ? { ...demo, loadError: `等了 ${LOAD_TIMEOUT_MS / 1000} 秒还没读完数据` }
      : demo;          // 服务压根没起 → 演示数据（页头会标出来），不是错误
  } finally {
    clearTimeout(timer);
  }
}

/** 补齐可选字段，两条加载路径共用一套，免得两处各写一遍必然飘。 */
function normalize(d: Partial<Snapshot>): Snapshot {
  return {
    isRealData: true,
    activeUser: d.activeUser || "",
    allUsers: d.allUsers ?? [],
    hrAnswers: d.hrAnswers ?? [],
    parked: d.parked ?? 0,
    baseResume: d.baseResume,
    // 同理不许兜底到 demoPipeline：流水线是**计数**，显示一份演示的假数字
    // 比空着糟得多——用户会以为自己有 268 个岗、5 份材料。拿不到就给空表，
    // 那一栏自己不渲染（`pipeline.map` 空数组即无输出）。
    pipeline: d.pipeline ?? [],
    jobs: d.jobs ?? [],
    // **不要 `?? demoEnv`。** 真实数据里拿不到环境探测时退回演示值，面板会显示
    // 一份与这台机器无关的「都装好了」——写死的 Node v22.9.0、Typst 0.13.0。
    // 实测就这么假了很久：导出器压根没产出 envItems（字段名 label/name 对不上），
    // 而界面默默兜底，看不出任何异常。拿不到就给空表，那一块自己不显示。
    // 演示数据只在 `demo` 那条路径上用（整页都标着「演示数据（虚构）」）。
    envItems: d.envItems ?? [],
    // 同样不许兜底到写死的表：面板显示一份与这个仓库实际工作流不符的命令清单，
    // 用户照着敲会撞到「没有这个命令」。拿不到就不显示那一块。
    commands: d.commands ?? [],
    outcomeStats: d.outcomeStats,
    gateFailTally: d.gateFailTally,
    topExclusions: d.topExclusions,
    observedMonths: d.observedMonths,
    resumeStaleDays: d.resumeStaleDays,
    // 读到真实数据时**不该**还有失败原因；留着是为了这一格只有一个来源
    // （`loadError` 只在失败那条路上被填上），而不是在这里手工清一遍。
    loadError: d.loadError,
    outcomeReasons: d.outcomeReasons ?? [],
    // **`normalize` 是手写白名单——漏掉一个字段，那块界面就永远不出现。**
    // `resumeInsight` 就这么漏了：导出器算好了、`data.json` 里有、`Snapshot`
    // 类型里也声明了，而这里没抄，于是「市场怎么读你的简历」整块从没被渲染过。
    // 类型系统拦不住：所有可选字段缺了都合法。
    // `tests/test_no_silent_demo_fallback.py` 按 `Snapshot` 的字段逐条比对。
    resumeInsight: d.resumeInsight,
    // 服务在响应里现塞的「后台代码更新过、还没重启」名单——不映射，横幅永远不出现。
    // （2026-08-14 实测又踩了一次这行注释说的坑：类型加了、这里没抄，
    // e2e 看 /data.json 有 staleCode、页面就是不渲染。）
    staleCode: d.staleCode,
    // 渠道开关与状态。漏在这里的后果和 staleCode 一样：`/data.json` 里有、
    // 页面就是不渲染——`normalize` 是手写白名单。
    portals: d.portals,
    prefs: d.prefs,
    archivedCount: d.archivedCount,
    restaleCount: d.restaleCount,
    detectedTool: d.detectedTool,
    nextStep: d.nextStep ?? { text: "从下面的名单里挑一个岗，点开看详情", command: "" },
  };
}
