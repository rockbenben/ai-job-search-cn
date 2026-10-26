import { useEffect, useState } from "react";
import { Tooltip } from "antd";
import type { Portal } from "../types";
import { Cmd } from "./Cmd";
import { hasServer, postPortal, postResumeRefreshed, postUnblock }
  from "../data/excluded";

/**
 * 这一家封着的通道里，有没有**要用户本人去做**的那种。
 *
 * 两种封控要他做的**不是同一件事**：浏览器那条是他的账号被要求过一次验证；
 * CLI 那条是免登录接口撞了限流，要换这台机器的网络出口 IP。
 *
 * ⚠️ 这里原来写的是「CLI 那条他做不了、也不用做，到点自动恢复」——
 * 2026-08-26 裁定封控不再自动到期之后那句话就不成立了（下面第三段自己也写着
 * 「2026-08-26 起它同样不会自动解」，**同一段 docstring 前后打架**）。
 * 这个函数分的是**要他做哪一件**，不是「要不要他做」：两条都要。
 *
 * **实测代价（2026-08-21）**：用户在手机上过完猎聘的短信验证、回来点了
 * 「我处理好了」——那一下是对的，浏览器那条确实解开了。但行标签和折叠标题
 * 对两种封控说的是同一句「被平台拦住 / 被拦住了」，于是他看到的还是原来那句，
 * 以为**白点了**。而剩下那条是 CLI 限流 —— 要他换网络出口的 IP，
 * 也是他本人才办得到（2026-08-26 起它同样不会自动解）。
 *
 * 告警条早就分开说了（`needsYou` / `needsNewIp`），标签没有 —— 收起来时
 * 标签是唯一看得见的信号。
 */
export function blockNeedsYou(p: Portal): boolean {
  const lanes = p.blockedLanes;
  // 老 data.json 没有这个数组时退到塌成一条的那个字段，别把标签整个丢掉。
  // **空数组也要走这一支。** `!lanes` 对 `[]` 是 false，于是
  // `[].some(...)` 返回 false，浏览器那条封控被标成「免登录接口被限流 · 换个网络再试」——
  // 而它只有用户本人过得了验证，页面同时还摆着一个「我处理好了」按钮，
  // 两句话互相打架。下面那条告警列表的判据写的就是 `lanes && lanes.length`，
  // 注释还说两处「同一套」，实际只有一处对。
  if (!lanes || !lanes.length) return p.blocked && p.blockedLane !== "cli";
  return lanes.some((b) => b.lane !== "cli");
}

/** 行标签上那句话。要回答的是「还要不要我做点什么」，不是「出了什么事」。
 *
 * **两条现在都要人动手。** 这里原来对 CLI 说「到点自动恢复」——
 * 2026-08-26 封控不再自动到期，那句话会让人干等一天，而等来的是同一个 IP。
 */
/** 数据里的封控原因带着内部码（`CLI` / `RATE_LIMITED`），首屏不该原样念给用户。 */
export function blockWhyText(why: string): string {
  return (why || "")
    .replace(/CLI\s*撞\s*RATE_LIMITED/g, "平台限流了")
    .replace(/RATE_LIMITED/g, "限流")
    .replace(/\bCLI\b/g, "后台抓取");
}

export function blockStreakText(streak: string): string {
  return blockWhyText(streak).replace(/出口/g, "网络");
}

export function blockLabel(p: Portal): string {
  // **这是行内 8.5em 状态格里的短标签，不是告警正文。**
  // 完整句「免登录接口被限流 · 换个网络（如手机热点）再试」放进这一格会
  // 一字一行竖排（实测 2026-10-27）；完整说明在首屏 chip 和弹窗告警正文里。
  if (blockNeedsYou(p)) return "要验证";
  return "要换网络";
}

/** 告警条里的一行 = 一条被封的通道（不是一家）。`key` 只用来做 React key 与 busy 态。 */
type BlockedRow = NonNullable<Portal["blockedLanes"]>[number] & {
  key: string;
  site: string;
};

/**
 * 「招聘网站」：每个网站抓了多少、最近哪天抓的、还开着没。
 *
 * **为什么这一块要存在。** 面板原来只说「搜到 2600 个岗」，不说这些岗来自哪儿。
 * 于是两件事用户看不见：
 *
 * 1. **某个网站根本没在抓。** 取消勾选的整家跳过，而词表算出来的「最值钱的格子」
 *    可能恰恰在那几家——用户不知道自己漏了什么。
 *    （2026-08-19 之前更糟：浏览器三家默认关着、要 `--browser-scrape` 才开，
 *    于是这里勾上也不会抓——勾选框只有否决权没有启动权。现在它是唯一开关。）
 * 2. **某个网站抓得到岗、却打不出分。** 前程无忧的列表页没有逐岗详情链接，
 *    JD 正文拿不到，硬门无从判断，那些岗会一直停在「待评」。只看总数的话，
 *    这表现为「抓了两百多个，可投的一个也没多」，像是工具坏了。
 *
 * **开关落在盘上**（`job_scraper/portals.json`），不是浏览器 localStorage——
 * 读它的是命令行侧的 `/job-scrape`，存在浏览器里抓取时根本看不见。
 * 没有本地服务时只显示状态、不给开关（点了也写不回去，给了就是骗人）。
 */
export function Portals({ portals, onChanged, staleDays }: {
  portals: Portal[];
  onChanged?: () => void;
  /** 多久没刷新算旧。**正本在 `export_web_data.RESUME_STALE_DAYS`**，
   *  经 payload 的 `resumeStaleDays` 传进来 —— 这里原来写死 `14`，
   *  同一行的提示语还写着「两周」，加上 `doctor.py` 那份有据的复刻，
   *  一个数四份，而守卫只盖住了 Python 那两份。 */
  staleDays?: number | null;
}) {
  const stale = staleDays ?? 14;
  const live = hasServer();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  /**
   * 乐观覆盖：**先按点下去的样子显示，props 追上来就自动退位。**
   *
   * 这三个按钮的显示状态全来自重取回来的快照，而写盘那一下 `serve.py` 在响应
   * 之前同步跑导出子进程（实测 3.4-4.2 秒）—— 原来这几秒里控件不动、还变灰。
   * 和用户 2026-09-02 报的「点了我投了，怎么没乐观更新」是同一个形状，换了控件。
   *
   * 退位规则是「props 和我说的一样了就删掉这一条」，不是「重取回来就清空」：
   * 后者会把这期间新点的那一下一起抹掉，控件当场跳回去。
   */
  const [ovOn, setOvOn] = useState<Record<string, boolean>>({});
  //: 只覆盖「今天刷过」这一个方向。**撤销那一边不猜** —— 撤掉今天这笔之后
  //  真正该显示的是「上一次刷是几天前」，那个数只有服务端知道；本地瞎填一个
  //  就成了「界面说得斩钉截铁，而它是编的」，比等两秒糟。
  const [ovFresh, setOvFresh] = useState<string[]>([]);
  const [ovUnblocked, setOvUnblocked] = useState<string[]>([]);
  useEffect(() => {
    setOvOn((o) => {
      const next = Object.fromEntries(Object.entries(o).filter(
        ([k, v]) => portals.find((p) => p.name === k)?.enabled !== v));
      // 没变就返回原对象 —— 每次都新建会让这个 effect 自己触发自己。
      return Object.keys(next).length === Object.keys(o).length ? o : next;
    });
    setOvFresh((o) => {
      const next = o.filter(
        (n) => portals.find((p) => p.name === n)?.resumeStale !== 0);
      return next.length === o.length ? o : next;
    });
  }, [portals]);
  //: 屏幕上该显示的值 = 本地覆盖优先，没有就用快照里的。
  //  **每一处显示都要走它**，漏一处就是「半个乐观更新」——
  //  勾选框动了而它旁边那行字没动，比全都不动更让人confused。
  const shownOn = (p: Portal) => ovOn[p.name] ?? p.enabled;
  const shownStale = (p: Portal) =>
    ovFresh.includes(p.name) ? 0 : p.resumeStale;
  if (!portals.length) return null;

  const on = portals.filter((p) => shownOn(p)).length;
  const total = portals.reduce((n, p) => n + p.jobs, 0);

  const toggle = async (p: Portal) => {
    if (!live || busy) return;
    const want = !shownOn(p);
    setBusy(p.name);
    setErr(null);
    setOvOn((o) => ({ ...o, [p.name]: want }));      // ① 立刻
    try {
      await postPortal(p.name, want);                // ② 后台写
      onChanged?.();
    } catch (e) {
      setOvOn((o) => {                               // 回滚：盘上没改成
        const { [p.name]: _drop, ...rest } = o;
        return rest;
      });
      setErr(e instanceof Error ? e.message : "没改成，刷新一下再试");
    } finally {
      setBusy(null);
    }
  };

  /**
   * 记一笔「今天在这家刷了在线简历」。
   *
   * **为什么这一格值得存在**：国内平台的简历库基本按「最近活跃」排序，HR 主动
   * 搜人翻不了几页 —— `job-resume.md` 2.6 把刷新标成那张表里唯一一件**每天都要
   * 做**的事。而在这之前没有任何地方记他做过没有：提醒只在 `/job-auto` 收尾、
   * 且只在那一轮真出了材料时才响，于是既校准不了也升级不了。
   *
   * 已经记了今天的话再点一下是撤销 —— 标错了要有退路，否则没人敢标第一下。
   */
  const markRefreshed = async (p: Portal) => {
    if (!live || busy) return;
    const undoing = shownStale(p) === 0;
    setBusy("r:" + p.name);
    setErr(null);
    // 标记这一下立刻显示；撤销那一下不猜（见 `ovFresh` 的说明），照旧等写盘。
    if (!undoing) setOvFresh((o) => [...o, p.name]);
    try {
      await postResumeRefreshed(p.name, undoing ? "" : undefined);
      onChanged?.();
    } catch (e) {
      if (!undoing) setOvFresh((o) => o.filter((n) => n !== p.name));
      setErr(e instanceof Error ? e.message : "没记上，刷新一下再试");
    } finally {
      setBusy(null);
    }
  };

  // **报的是渠道名，不是平台名。** 平台名会让 `clear()` 自己去挑「哪一条」
  // （按剩余时长挑，平手偏 CLI），而用户点的是他刚处理完的那一条 ——
  // 两条各自封着时挑错的代价是：他过完的短信验证原样封着，没人管的匿名接口提前恢复。
  const unblock = async (r: BlockedRow) => {
    if (!live || busy) return;
    setBusy(r.key);
    setErr(null);
    setOvUnblocked((o) => [...o, r.key]);            // ① 立刻：这条告警先撤下
    try {
      await postUnblock(r.channel);
      onChanged?.();
    } catch (e) {
      setOvUnblocked((o) => o.filter((k) => k !== r.key));   // 回滚：还封着
      setErr(e instanceof Error ? e.message : "没解成，刷新一下再试");
    } finally {
      setBusy(null);
    }
  };

  // 被平台拦住的那几家要**顶到最上面**，不能只在自己那一行里加个小字。
  // 用户看到的现象只是「怎么最近都没新岗了」——不主动说，他不会知道该做什么。
  //
  // **一行 = 一条被封的通道，不是一家。** 猎聘有两条，各自因为不同的事封着是常态
  // （CLI 撞限流 + 浏览器要短信验证）。按家渲染时导出端会把一家塌成一条，
  // 另一条在界面上就**不存在** —— 而它照样拦着抓取，用户看不见也就无从处理。
  //
  // **没有这个数组时要退回塌成一条的那几个字段**，和上面 `blockNeedsYou` 同一套
  // 兜底。少这一路的后果不是「显示得差一点」，是**整块告警连同解封按钮一起消失**，
  // 而每一行的标签还在说「被平台拦住」：用户看见它被拦住了，却没有任何地方
  // 可以处理。两种 data.json 会走到这儿——上一版导出器写的那份（`needs_reexport`
  // 只比上游数据的 mtime，代码更新了它不会重导），以及导出器在极短的时间窗里
  // 恰好判出「封着但没有一条通道封着」的那份。
  const blocked: BlockedRow[] = portals.flatMap((p) => {
    const lanes = p.blockedLanes;
    if (lanes && lanes.length) {
      return lanes.map((b) => ({
        key: `${p.name}/${b.lane}`, site: p.name, ...b,
        why: blockWhyText(b.why),
      }));
    }
    if (!p.blocked) return [];
    return [{
      key: `${p.name}/${p.blockedLane || "browser"}`,
      site: p.name,
      lane: p.blockedLane || "browser",
      channel: p.name,          // 老数据没带渠道名，只能报平台名
      why: blockWhyText(p.blockedWhy),
      heldHours: p.blockedHeldHours,
      streak: "",              // 老 data.json 没有这一条
      url: p.blockedUrl,
      alsoSlows: p.blockedAlsoStops ?? "",
    }];
    // 点过「我处理好了」的那几条先撤下去，别等导出跑完（同 ovOn 的理由）。
  }).filter((b) => !ovUnblocked.includes(b.key));
  // **两种封控要说完全不同的话，但都要人动手。**
  //
  // 浏览器那条是他的账号被要求过一次验证，只有他本人过得了；
  // CLI 那条是免登录接口撞了限流，而限的是**这个网络出口的 IP** ——
  // 要他换掉网络出口，工具同样帮不上。
  //
  // 这个变量原来叫 `justWaiting`，配的文案是「不用你做什么……到点自动恢复」。
  // 2026-08-26 本人裁掉了那句：「cli 被封后……只有用户手动点继续 cli 后，
  // 才能继续 cli」。等是等不来的 —— 08-24、08-25 各撞一次，第二次就是
  // 冷却刚过撞的，换的还是同一个 IP。
  const needsYou = blocked.filter((b) => b.lane !== "cli");
  const needsNewIp = blocked.filter((b) => b.lane === "cli");
  const sites = [...new Set(blocked.map((b) => b.site))];
  // **「这家抓不了」和「这家有一条被拦住了」是两回事。** 前者才配 role="alert"
  // 的那句断言。判据不在这儿推 —— 后端的 `canScrape` 就是回答它的那一个
  // （`portal_budget.check()`，裸平台名落到此刻真走得通的那条）。
  // 老 data.json 没这个字段时退到「有封控就算抓不了」，与改动前一致。
  const dead = (n: string) => portals.find((p) => p.name === n)?.canScrape === false
    || portals.find((p) => p.name === n)?.canScrape === undefined;
  const allDown = sites.filter(dead);
  const partly = sites.filter((n) => !dead(n));

  return (
    <div className="portals">
      <div className="sec-head">
        <span className="kicker">招聘网站</span>
        <span className="sec-note">
          {on}/{portals.length} 个在用 · 一共抓到 <b>{total}</b> 个岗
        </span>
      </div>

      {/* 手机 APP 刷新提示：明确说明哪些平台网页端没有刷新按钮 */}
      {portals.some((p) => shownOn(p) && p.webRefresh === false) && (
        <div className="portal-app-tip" role="note">
          <span className="portal-app-icon">📱</span>
          <span className="portal-app-text">
            <b>手机 APP 刷新提示：</b>
            {portals.filter((p) => shownOn(p) && p.webRefresh === false).map((p) => p.name).join("、")}
            {" 网页端没有简历刷新按钮（排序看移动端在线活跃与打招呼，或仅在手机端开放刷新）。请打开手机 APP 活跃或刷新简历，完成后在下方点击按钮记上一笔。"}
          </span>
        </div>
      )}

      {blocked.length > 0 && (
        <div className="portal-alarm" role="alert">
          {/* **标题也要说在通道上。** `blocked` 现在是一条通道一项，而这句话
              原来断言的是整家：猎聘只有 CLI 在冷却时，终端说「可以抓（CLI停）
              …本轮 0/3…放慢中」，面板却顶着一条 role="alert" 说「猎聘 这家
              现在抓不了」——同一份数据两个界面给相反的答案，用户（或读面板的
              助手）据此把猎聘停一天，那正是这套不对称闸门要防的事。

              判据是**这家还剩没剩能走的通道**：一条都不剩才说「抓不了」。 */}
          <b>
            {allDown.length > 0 && (
              <>
                {allDown.join("、")} 这
                {allDown.length > 1 ? `${allDown.length}家` : "家"}现在抓不了
              </>
            )}
            {allDown.length > 0 && partly.length > 0 && "；"}
            {partly.length > 0 && (
              <>
                {partly.join("、")} 有一种抓取方式被拦住了，另一种还能抓（会自动放慢）
              </>
            )}
          </b>
          <ul>
            {blocked.map((b) => (
              <li key={b.key}>
                {/* **先说是哪条通道。** 用户问过「猎聘 cli 和浏览器不是要分开
                    处理吗」—— 是分开的，但光写「猎聘」看不出分在哪儿。 */}
                <b>
                  {b.site}
                  {b.lane === "cli" ? " · 免登录接口"
                    : b.lane === "browser" ? " · 浏览器（要登录那条）" : ""}
                </b>
                ：{b.why}
                {/* **不说「还剩多久」。** 2026-08-26 起封控不会自动解开，
                    倒计时那个数从此没有意义 —— 摆在屏幕上就是在教用户等，
                    而 CLI 那条等到点换的还是同一个 IP。 */}
                <i>已经停了约 {b.heldHours} 小时 · 不会自动恢复，要你点下面那个按钮</i>
                {/* **撞过不止一次就说出来。** 「停了 16 小时」读起来像个刚发生
                    的小毛病，而「三天撞了 3 次、每次放行后几分钟又中」说的是
                    「这个出口不会好了」—— 两者导出相反的决定。 */}
                {b.streak && (
                  <em className="portal-streak">{blockStreakText(b.streak)}</em>
                )}
                {/* **连带放慢的那条要说出来**，否则用户以为「分开处理」=
                    另一条完全照常，按原速换过去，正好撞上升级成账号风控那条路。 */}
                {b.alsoSlows && (
                  <em className="portal-also">
                    {b.alsoSlows}那边不停、但会自动放慢（间隔拉长到 3 倍）：同一家、同一个网络，按原速换另一种抓取方式会把限流升级成账号风控
                  </em>
                )}
                {b.url && (
                  <a className="portal-fix" href={b.url}
                     target="_blank" rel="noreferrer">
                    去处理
                  </a>
                )}
              </li>
            ))}
          </ul>
          {needsYou.length > 0 && (
            <p>
              要验证的，<b>只有你本人能过</b>——点上面的「去处理」在 Chrome
              里打开（用的就是你登录着的那个），按提示走完；<b>处理完回来点「我处理好了」</b>
              才会恢复抓取。不点就一直停着，<b>哪怕这家的勾选是开着的</b>。其余网站照常抓。
            </p>
          )}
          {needsNewIp.length > 0 && (
            <>
              <p>
                {[...new Set(needsNewIp.map((b) => b.site))].join("、")} 是
                <b>免登录接口被平台限流了</b>——你的账号没被碰，也没有验证要过，其余网站照常抓。
              </p>
              {/* **这一段 2026-08-26 整个换过。** 原文是「不用你做什么」+
                  「从撞上那一刻起 24 小时，到点自动恢复，不用你操作」。
                  两句都是错的，而且是最贵的那种错：照它做就是干等一天，
                  一天后换的还是同一个 IP，探一次限一次。 */}
              <p>
                但<b>它不会自己好</b>：平台按你当前的网络限流，
                {"不是某个账号。干等没用——换个网络（换个无线网络、开手机热点、重拨宽带都行），"}
                <b>换完回来点下面那个按钮</b>{"才会继续用它。不点就一直停着，"}
                <b>哪怕这家的勾选是开着的</b>。
              </p>
              {needsNewIp.map((b) => (
                <div key={b.key}>
                  <p className="portal-probe">
                    换好网络想先确认 {b.site} 通没通，在对话里跑：
                  </p>
                  <Cmd>{`/job-scrape health ${b.channel}`}</Cmd>
                  <p>
                    它做的事：<b>朝{b.site}发一次搜索请求，看接口通没通</b>。通了就当场解掉、恢复抓取；不通就照实告诉你还在限流。
                    <b>没换网络之前别探</b>——同一个网络探一次限一次，白撞。
                  </p>
                </div>
              ))}
            </>
          )}
          {live && (
            <div className="portal-alarm-acts">
              {blocked.map((b) => (
                <button key={b.key} type="button" className="portal-unblock"
                        disabled={busy === b.key}
                        onClick={() => void unblock(b)}>
                  {b.lane === "cli"
                    ? `${b.site}${blocked.length > sites.length ? " 免登录接口" : ""}：我换好网络了，继续抓`
                    : `${b.site}${blocked.length > sites.length ? " 浏览器" : ""}：我处理好了，恢复抓取`}
                </button>
              ))}
            </div>
          )}
          {/* 静态模式没有解封按钮，这几行命令就是**唯一**的出路——所以封着几条
              就要给几条。原来只写 `blocked[0]`：两条各自封着时，用户在手机上过完
              的那个短信验证恰恰可能是第二条，而页面上没有任何地方教他怎么解它。
              上面那份告警列表和按钮行早就是逐条渲染的，这里当时没跟上。 */}
          {!live && blocked.map((b) => (
            <p className="portal-foot" key={b.key}>
              {b.site}
              {b.lane === "cli" ? " 免登录接口" : " 浏览器"}
              处理完要恢复：终端里跑{" "}
              <Cmd>{`python tools/portal_budget.py --clear ${b.channel}`}</Cmd>
            </p>
          ))}
        </div>
      )}

      <div className="portal-rows">
        {portals.map((p) => (
          <div key={p.name}
               className={"portal-row" + (shownOn(p) ? "" : " is-off")
                          + (p.blocked ? " is-blocked" : "")}>
            <label className="portal-sw">
              <input
                type="checkbox"
                checked={shownOn(p)}
                disabled={!live || busy === p.name}
                onChange={() => void toggle(p)}
              />
              <b>{p.name}</b>
              {/* 封了就是封了：勾着也不抓，这件事必须在勾选框旁边说，
                  否则用户看到勾是开的，会以为它在抓。
                  **说「被平台拦住」不说「已停用」**：勾选框自己已经在说
                  「用不用」了，而这两件事的下一步完全不同 ——
                  没勾上勾上就行，被拦住要么等、要么去探一次。
                  实测（2026-08-21）猎聘正好两者兼有：勾是关的、又封着，
                  一个「已停用」把两个原因说成了一件事。
                  用词和上面那条告警、折叠标题上的那枚标记对齐。

                  **而且要分清是哪一种**（`blockLabel`）：浏览器那条要他去过验证，
                  CLI 那条要他换网络出口。两者共用一句「被平台拦住」的后果实测过 ——
                  他处理完浏览器那条回来，标签一个字没变，以为白点了。

                  ⚠️ 这里原来给 CLI 那条挂 `is-waiting`（淡色，读作「等着就行」），
                  依据是「CLI 那条到点自己好」—— 2026-08-26 裁定封控不再自动到期，
                  那句话就不成立了。**两条现在都要人动手，颜色不该分轻重。** */}
            </label>

            <span className="portal-how">
              {/* **状态标签放在说明列，不放在勾选标签里。** 第一个格子只有
                  8.5em，checkbox + 平台名之后剩不下几像素；把标签塞在那里，
                  「猎聘」和标签都会被挤成一字一行（实测 2026-10-27）。
                  说明列有 11em，且标签自己 nowrap，够放四个字。 */}
              {p.blocked && (
                <em className="portal-halt">
                  {blockLabel(p)}
                </em>
              )}
              {p.how}
              {p.needsLogin && <i>· 要你先登录</i>}
            </span>

            <span className="portal-n">
              <b>{p.jobs}</b> 个岗
              {/* **两个口径分开印。** `sellable` 是「现在还剩几个能投」——
                  投过的、下线的、你自己跳过的都减掉了，所以**越给力的渠道
                  这个数被吃得越干净**。单印它会得出反的结论：实测 2026-08-24
                  猎聘 2232→5 看着最差，而它累计判过能投 104 个，占全部的 83%。
                  判据与两个数的来历见 `export_web_data.portal_rows` 的 `ever_ids`。 */}
              {p.everSellable > 0 && <i>· 累计 {p.everSellable} 个能投</i>}
              {p.sellable > 0 && <i>· 现在还剩 {p.sellable} 个</i>}
            </span>

            {/* 职位描述存下来了多少。低了要自己喊——静默的 0% 谁也发现不了 */}
            {p.jobs > 0 && (
              <Tooltip
                title={
                  p.withJd / p.jobs < 0.2
                    ? "抓回来的岗大多没把职位描述存下来。后果：算能力差距、复查原文、职位下线后回查，都拿不到。抓的时候要顺手存，回头补等于再开一次页面。"
                    : "抓回来的岗里，有多少把职位描述一起存下来了。"
                }
              >
                <span className={"portal-jd" + (p.withJd / p.jobs < 0.2 ? " is-thin" : "")}>
                  职位描述存了 {Math.round((p.withJd / p.jobs) * 100)}%
                </span>
              </Tooltip>
            )}

            {/* **关掉的那家，要说出关掉的代价。**

                这一块存在的第一条理由就是「某个网站根本没在抓 —— 用户不知道
                自己漏了什么」（见本文件开头）。而现在关掉只是给行加个 `is-off`
                变灰 —— 变灰恰恰把「漏了什么」那部分信息压下去了。

                只在**真的有代价时**才出这一句：这家的职位描述覆盖比**在用的
                每一家都高**。覆盖率决定的是「抓回来的岗能不能打分」（同下面
                那条 `读不到职位详情`），所以它是这里唯一值得比的一维；
                比岗位数会把「抓得多」误当成「捞得多」，那正是各家 `note`
                里已经在提醒的反面。

                实测活动用户 2026-08-24：关着的那家覆盖 66%，而在用的三家是
                0.8% / 5% / 0% —— 他关掉的是四家里唯一打得出分的。屏幕上
                只有一个灰掉的勾选框。 */}
            {(() => {
              if (shownOn(p) || !p.jobs) return null;
              const cov = (q: Portal) => (q.jobs ? q.withJd / q.jobs : 0);
              const bestOn = Math.max(
                0, ...portals.filter((q) => shownOn(q) && q.jobs).map(cov));
              if (cov(p) <= bestOn) return null;
              return (
                <Tooltip title="职位描述拿不到，抓回来的岗就停在「待评」，打不出分。这家关着，而在用的那几家覆盖都比它低——现在抓回来的岗多半评不了。">
                  {/* **这句不许断行。** JSX 会把换行加缩进折成一个空格，
                      中文里那个空格是看得见的（`…%， 在用的…`）——
                      `test_css_and_cjk_text` 盯着这个，我这次就栽在这儿。 */}
                  <span className="portal-warn">
                    {`关着的这家职位描述覆盖最高（${Math.round(cov(p) * 100)}%，在用的最高才 ${Math.round(bestOn * 100)}%）`}
                  </span>
                </Tooltip>
              );
            })()}

            {/* 拿不到 JD 的渠道要单独说——它决定抓回来的岗能不能打分 */}
            {!p.jd && (
              <Tooltip title="这个网站的列表页没有逐个职位的链接，读不到完整职位描述。抓回来的岗会停在「待评」，要打分得手动打开职位页。">
                <span className="portal-warn">读不到职位详情</span>
              </Tooltip>
            )}

            <span className="portal-last">
              {p.lastRun
                ? <>最近 {p.lastRun.slice(5)}{p.newLastRun > 0 && ` · 新增 ${p.newLastRun}`}</>
                : "还没抓过"}
            </span>

            {/* 在线简历刷新。**只对勾着的渠道显示** —— 关掉那家的简历刷不刷
                不影响任何事，多一格就是噪音。 */}
            {shownOn(p) && live && (
              <Tooltip
                title={
                  shownStale(p) === undefined
                    ? (p.webRefresh === false
                        ? `${p.name} 网页端没有刷新按钮，排序看在线活跃与打招呼。请在手机 APP 里活跃或刷新简历，操作后点这里记一笔`
                        : "还没记过。国内平台的简历库基本按「最近活跃」排序，HR 主动搜人翻不了几页——登进去刷一下，回来点这里记一笔")
                    : shownStale(p) === 0
                      ? (p.webRefresh === false
                          ? `${p.name} 今天已在手机 APP 刷过/活跃。再点一下撤销`
                          : "今天刷过了。再点一下撤销")
                      : (p.webRefresh === false
                          ? `${shownStale(p)} 天前刷的。超过 ${stale} 天没登录的简历，HR 就翻不到了。${p.name} 需在手机 APP 活跃或刷新简历，操作后点此记上`
                          : `${shownStale(p)} 天前刷的。超过 ${stale} 天没登录的简历，HR 就翻不到了`)
                }
              >
                <button
                  type="button"
                  className="portal-refresh"
                  data-stale={((st) => st === undefined
                    ? "unknown"
                    : st === 0
                      ? "today"
                      : st >= stale ? "old" : "ok")(shownStale(p))}
                  disabled={busy === "r:" + p.name}
                  onClick={() => void markRefreshed(p)}
                >
                  {shownStale(p) === undefined
                    ? "简历没记过刷新"
                    : shownStale(p) === 0
                      ? "简历今天刷过"
                      : `简历 ${shownStale(p)} 天没刷`}
                  {p.webRefresh === false && (
                    <span className="portal-app-badge">（需手机 APP）</span>
                  )}
                </button>
              </Tooltip>
            )}

            <Tooltip title={p.note}>
              <span className="portal-note">{p.note}</span>
            </Tooltip>
          </div>
        ))}
      </div>

      {!live && (
        <p className="portal-foot">
          开关要本地服务才能改：终端里跑 <Cmd>python tools/serve.py</Cmd> 打开这一页。
        </p>
      )}
      {err && <p className="portal-foot portal-err">{err}</p>}
    </div>
  );
}
