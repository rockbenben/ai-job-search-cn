import { userKey } from "./hidden";
/**
 * 「不投」标记：**有本地服务时直接写回盘上**，没有时才退回浏览器存储。
 *
 * ## 两种运行方式，行为不一样
 *
 * | 打开方式 | 点「不投」会怎样 |
 * |---|---|
 * | `python tools/serve.py` | 直接写进 `seen_jobs.json`，刷新还在，**不用再回命令行** |
 * | 双击单文件 HTML / `vite preview` | 只存 `localStorage`，要跑一条 `/job-rank --skip` 才永久生效 |
 *
 * 区别必须在界面上说清楚——静态那条路不跑命令，重新生成页面时被排除的岗会回来。
 *
 * ## 怎么知道有没有服务
 *
 * `serve.py` 在返回 index.html 时把一次性 token 注入成 `window.__API_TOKEN__`。
 * 有 token 就说明是它发的页面；静态文件里没有这个变量。
 *
 * token 同时是**写操作的锁**：没有它，你在浏览器里打开的任何网站都能往
 * `localhost:29029` 发 POST 把你的职位标成不投（跨站 POST 是允许的，只是读不到
 * 响应——而这里的破坏不需要读响应）。跨站脚本读不到本页 DOM，也就拿不到 token。
 *
 * ## 键用什么
 *
 * 用 `id`，而 `id` 是**按 URL + 职位名派生的稳定值**（见 `export_web_data.stable_id`）。
 * 早先 `id` 是枚举序号，`seen_jobs` 增删一条后面全部错位 —— 那样存下来的标记会
 * 张冠李戴：你排除了 A 岗，重新生成后被隐藏的是 B 岗。服务端按同一个函数反查条目，
 * 两边算的是同一个 id。
 */

const KEY = "jobSearchExcluded.v2";
const KEY_V1 = "jobSearchExcluded.v1";

declare global {
  interface Window {
    __API_TOKEN__?: string;
  }
}

/** 是不是由 `tools/serve.py` 提供的页面——决定「不投」能不能落盘。 */
export function hasServer(): boolean {
  return typeof window !== "undefined" && typeof window.__API_TOKEN__ === "string";
}

/**
 * 静态模式下浏览器里存的是**增量**，不是整份名单。
 *
 * `true` = 这个岗是我在这个浏览器里标的不投；`false` = 盘上标了不投、但我在这里
 * 把它放回去了。盘上的 `skipped` 是底，增量盖在上面。
 *
 * ## 为什么不能存一个扁平集合
 *
 * 原来存的是「当前被排除的全部 id」，加载时又**完全无视**快照里的 `skipped`——
 * **实测**：单文件面板把两个早就标了不投的岗又摆回「可以投的岗位」里
 * （23 行变 25 行）。
 *
 * 而只要改成「盘上的 ∪ 存的」，就会翻出一个反向的鬼状态：静态版点「放回」，
 * 存下来的集合里没有它，刷新时又被盘上那份加回去——**页面上放回了、刷新又隐藏**。
 * 一个扁平集合表达不了「加」和「减」两个方向，所以存增量。
 */
export type Delta = Map<string, boolean>;

export function loadDelta(user = ""): Delta {
  try {
    // 按活动用户分键（同 `hidden.ts` 的 `userKey`）：这份增量是**按岗位 id 存的**，
    // 而同一个岗被两个用户抓到时 id 相同——不分键，甲标的「不投」会盖在乙的名单上。
    const raw = localStorage.getItem(userKey(KEY, user))
      ?? (user ? localStorage.getItem(KEY) : null);
    if (raw) return new Map(Object.entries(JSON.parse(raw) as Record<string, boolean>));
    // v1 存的是「本机排除的 id」的扁平数组——那时盘上那份根本没参与，
    // 所以里面每一条都正好是「我在这里标的不投」，直接当 true 收下。
    const old = localStorage.getItem(KEY_V1);
    if (old) return new Map((JSON.parse(old) as string[]).map((id) => [id, true]));
  } catch {
    /* 隐私模式 / 存储被禁用时不该让整页挂掉 */
  }
  return new Map();
}

export function saveDelta(d: Delta, user = ""): void {
  try {
    localStorage.setItem(userKey(KEY, user), JSON.stringify(Object.fromEntries(d)));
  } catch {
    /* 存不进去也继续 —— 本次会话内仍然生效，只是刷新后回来 */
  }
}

/** 由「盘上标了不投的」和「现在实际排除的」反推增量——只记两者不一样的地方。 */
export function deltaFrom(onDisk: Set<string>, effective: Set<string>): Delta {
  const d: Delta = new Map();
  for (const id of effective) if (!onDisk.has(id)) d.set(id, true);
  for (const id of onDisk) if (!effective.has(id)) d.set(id, false);
  return d;
}

/** 把增量盖到盘上那份上，得到实际要排除的。 */
export function applyDelta(onDisk: Set<string>, d: Delta): Set<string> {
  const out = new Set(onDisk);
  for (const [id, skip] of d) if (skip) out.add(id); else out.delete(id);
  return out;
}

/** 服务端回的错误，带一个**机器能认**的 code。 */
export class ApiError extends Error {
  code?: string;
  constructor(message: string, code?: string) {
    super(message);
    this.code = code;
  }
}

/**
 * 写操作的通行凭据过期了（服务重启过）→ **自己去把新凭据取回来**。
 *
 * `serve.py` 每次启动注入的 token 变了，页面上那个旧的就废了：于是每一个
 * 写操作都撞 403。2026-10-23 实测，用户点「我投了」没反应——**错误文案本来
 * 是有的**，但它被渲染在一块刚被回滚卸载掉的区域里（见 `JobReadout.tsx`），
 * 于是用户既看不到原因、也不知道下一步该做什么。
 *
 * 这里的修法是**不打扰用户**：同源再取一次 `/`，那上面注着当前有效的 token，
 * 把这一下**原样重发**。跨站页面读不到本源的 `/`（同源策略），所以这没有
 * 削弱 `serve.py` 那道锁——它挡的从来是「别的源头的页面替你写盘」。
 */
async function refreshToken(): Promise<boolean> {
  try {
    const html = await fetch("/", { cache: "no-store" }).then((r) => r.text());
    const m = html.match(/__API_TOKEN__\s*=\s*"([^"]+)"/);
    if (!m) return false;
    window.__API_TOKEN__ = m[1];
    return true;
  } catch {
    return false;
  }
}

async function post<T = unknown>(
  path: string,
  body: Record<string, unknown>,
  retry = true,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, token: window.__API_TOKEN__ }),
    });
  } catch {
    // 浏览器的异常原文是 `Failed to fetch`，不该原样印给中文用户看。
    throw new ApiError("连不上本机服务——确认它还在跑", "network");
  }
  // 服务端把真因放在 error 里；**别把失败咽掉**——咽掉的结果是页面显示已排除、
  // 盘上其实没改，下次刷新它又回来，而用户不知道为什么。
  const data = (await res.json().catch(() => ({}))) as
    { ok?: boolean; error?: string; code?: string };
  if (!res.ok || !data.ok) {
    // **凭据过期：换新的，再重发一次。** 只重试一次，免得来回打转。
    if (data.code === "token_expired" && retry) {
      if (await refreshToken()) return post<T>(path, body, false);
    }
    throw new ApiError(data.error || `服务返回 ${res.status}`, data.code);
  }
  return data as T;
}

/** 标记不投。字段语义与 `/job-rank --skip` 一致：只改状态，不动分数。 */
export function postSkip(id: string, reason?: string): Promise<void> {
  return post("/api/skip", { id, reason });
}

/**
 * 标记职位已下线（关了 / 报名截止 / 点开是聚合页）。
 *
 * 与 `postSkip` 是两件事：那是「我不想投」，这是「它已经没了」。分数与判词
 * 都不动——万一判错，放回来时还得在。放回走 `postRestore`（同一条路）。
 */
export function postExpire(id: string): Promise<void> {
  return post("/api/expire", { id });
}

/** 放回可以投。「不投」与「已下线」共用这一条。 */
export function postRestore(id: string): Promise<void> {
  return post("/api/restore", { id });
}

/**
 * 记一笔投递状态（我投了 / 约面了 / 挂了…）——写进 `job_search_tracker.csv`。
 *
 * 这一步此前只能回命令行敲 `/job-outcome 公司名`，而它做的事按 `/job-outcome` 自己的
 * 定义就是**改 status 一列、追一条带日期的备注**，正落在 `serve.py` 那条
 * 「只改字段、不接模型」的边界之内。真正要判断的（谈薪、背调、offer 比较、
 * 备面）仍然走命令行。
 *
 * 能点哪些按钮由**服务端**决定（`tracker.NEXT`），页面只渲染它给的那几个：
 * 两份状态机迟早分叉，而分叉的样子是页面画出一个按钮、服务端拒绝它。
 */
export function postStatus(id: string, status: string, reason?: string) {
  // `reason` 只在「挂了」这类结果上有意义，且**永远可选**——不给就是不给，
  // 服务端不会替它编一个（`tools/serve.py` 的 apply_status）。
  return post<{ prev: string | null; then: string }>(
    "/api/status", { id, status, ...(reason ? { reason } : {}) });
}

/**
 * 撤销上一次 `postStatus`，`prev` 原样送回服务端。
 *
 * `prev` 为 `null` 表示那一行是页面刚建的，撤销即删行——所以这里**不能**把 null
 * 折成空串：空串在台账里是一个合法状态，那会把「删掉这行」变成「把状态清空」。
 */
export function postStatusUndo(id: string, prev: string | null) {
  return post<{ deleted: boolean }>("/api/status/undo", { id, prev });
}

/**
 * 记一笔「今天在这家刷了在线简历」。`day` 传空串是撤销。
 *
 * 它不针对某个职位，针对的是**平台上那份在线简历** —— 国内 HR 有很大一部分工作
 * 是反过来在简历库里搜人，而那个库按「最近活跃」排序。
 */
export function postResumeRefreshed(name: string, day?: "") {
  return post<{ name: string; day: string | null }>(
    "/api/resume-refreshed", { name, ...(day === "" ? { day: "" } : {}) });
}

/**
 * 记一笔「HR 点开过这份简历没有」。`viewed` 传 `null` 撤销这个标记。
 *
 * 三态送到底：`null` 是「我还没去平台看过」，`false` 是「看过了，没打开」——
 * 两者对诊断的意义正好相反，折成布尔值就把前者变成了后者。
 */
export function postHrViewed(id: string, viewed: boolean | null) {
  return post<{ title: string }>("/api/hr-viewed", { id, viewed });
}

/**
 * 开关某个招聘网站。**开关落在盘上**（`job_scraper/portals.json`），不是浏览器里——
 * 读它的是命令行侧的 `/job-scrape`，存进 localStorage 的话抓取时根本看不见。
 */
export function postPortal(name: string, enabled: boolean): Promise<void> {
  return post("/api/portals", { name, enabled });
}

/**
 * 解掉某家招聘网站的风控冷却。**只有人能点这个**——工具永远不自动解。
 *
 * 撞风控多半要用户本人去过一次验证（短信、滑块、联系客服），过没过完只有他知道。
 * 按时间自动解等于赌平台自己消气了，而实测是一次比一次重：限流 → 账号异常 → IP 封禁。
 */
export function postUnblock(name: string): Promise<void> {
  return post("/api/unblock", { name });
}

/**
 * 存一条 HR 常问的答案，落回 `profile/hr-answers.md`。
 *
 * **只换那一节的正文**：文件顶上的说明和每节里给填表人看的注释都留着 ——
 * 它们是下次改的时候要看的（判据在 `export_web_data.set_hr_answer`）。
 */
export function postHrAnswer(q: string, a: string): Promise<void> {
  return post("/api/hr-answer", { q, a });
}

/** 开关「这几类岗要不要看」。同样落盘——命令行侧的 /job-rank、/job-apply 也读它。 */
export function postPref(name: string, enabled: boolean): Promise<void> {
  return post("/api/prefs", { name, enabled });
}
