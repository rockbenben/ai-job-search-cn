import { useEffect, useMemo, useRef, useState } from "react";
import { Cmd } from "./Cmd";
import { useCodeTool } from "../context/CodeToolContext";
import { Input, Select, Table, Tooltip } from "antd";
import { JobReadoutBody } from "./JobReadout";

/**
 * 判词里的「粗筛：」前缀是**数据侧**的东西——`/job-rank` 写进 `seen_jobs.json` 时带上的，
 * 标记这条结论来自哪一档评估。屏幕上不能出现：「粗筛」是流程内部词，用户得先学会它
 * 才知道这一行和别的行差在哪，而那件事已经由「读过 JD」那个标记表达了。
 *
 * **只能有一份实现。** 原来只有分数列剥了前缀，搁置区直接用 `job.verdict`
 * ——实测「粗筛：不建议」「粗筛：跳过」在页面上出现 87 次。
 * 两处各写一遍必然飘，而飘掉的那一处没人会发现。
 */
/**
 * 窄到放不下三个数字列了吗。
 *
 * **实测（2026-08-18，Playwright 逐分辨率跑）**：390px 的手机上，表格靠
 * `min-width: 560px` 在自己盒子里横滚——分 72 + 技能 76 + 年包 108 加上内边距，
 * 三个数字吃掉 358px 可视宽里的 210px（59%），**职位名每一行都被切在右边缘**，
 * 稍长一点的职位名每一行都读不全。而职位名正是要读的那一个。
 *
 * 原来那条注释说「列有 min-width，硬压只会把中文挤成一字一行」——没错，但它
 * 只比较了「压」和「滚」。第三条路是**撤掉列**：把三个数字并进职位那一格，
 * 和标记当初从分数格搬到职位格是同一个动作。撤掉之后表格不再需要 560px，
 * 横滚连同它带来的那一串补丁（详情 sticky 钉左边缘）一起消失。
 *
 * 620px 跟 CSS 里已有的断点对齐，不另立一个。
 */
function useNarrow() {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 620px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia?.("(max-width: 620px)");
    if (!mq) return;
    const on = (e: MediaQueryListEvent) => setNarrow(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

export function plainVerdict(v: string): string {
  return (v || "").replace(/^粗筛[：:]\s*/, "").trim();
}
import type { ColumnsType } from "antd/es/table";
import type { SortOrder } from "antd/es/table/interface";
import { verdictColor, type Verdict } from "../theme/tokens";
import type { Job } from "../types";

/**
 * 可以投的岗位
 *
 * antd Table 在这里是有价值的底座：排序、键盘导航、行选中、
 * `rowClassName`/`onRow` 的可达属性都免费拿到。视觉全部由 cockpit.css 覆盖，
 * 表头被压成等宽小标签，行分隔只留一条 hairline。
 */
/**
 * 排序比较器：**没有值的永远沉底**，升序降序都一样。
 *
 * 原来三列都写 `(a.x ?? -1) - (b.x ?? -1)`，等于把「没这个数」当成了「最低」——
 * 按年包升序时，一个平台没写薪资的岗排在最前面，读起来就是「这个最便宜」。
 * 而「没写」和「很低」是两件事，这一页别处（硬性条件的四态、`salaryMonthsUnknown`）
 * 一直分得很清楚，唯独排序把它们折在一起了。
 *
 * antd 会把降序时的比较结果取反，所以这里对 null 那两支乘上 `flip` 抵消掉，
 * 它们才能两个方向都留在最后。
 */
function nullsLast(
  x: number | null | undefined,
  y: number | null | undefined,
  order?: SortOrder,
): number {
  const flip = order === "descend" ? -1 : 1;
  if (x == null && y == null) return 0;
  if (x == null) return flip;
  if (y == null) return -flip;
  return x - y;
}

export function Shortlist({
  jobs,
  selectedId,
  recommendedId,
  onSelect,
  onExclude,
  onExpire,
  onChanged,
  filtered,
  namedDirectBelow,
  observedMonths,
  reasons,
  byDate,
  hideColumns,
  appliedCompanies,
  hiddenCount,
}: {
  jobs: Job[];
  selectedId: string;
  /** 推荐先投的那一个岗——工具的职责是给出推荐，不是摆一张排序表让人自己猜 */
  recommendedId?: string;
  onSelect: (id: string) => void;
  /** 把这个岗移出「可以投」——存在本机浏览器，见 data/excluded.ts */
  onExclude: (id: string) => void;
  /** 标「职位已下线」。与 onExclude 是两件事，只在有本地服务时可用 */
  onExpire?: (id: string) => void;
  /** 投递状态写进盘上之后叫一声，让上层重取快照（计数、下一步都要跟着变）。
   *  `advance` 为真表示这一行做完了、多半要离开名单，上层应把展开挪到下一行。 */
  onChanged?: (advance?: boolean, id?: string,
               phase?: "now" | "settled") => void;
  /** 是否处于流水线筛选视图（已投递/面试中/材料就绪）。空表文案要认它：
   *  筛选把表清空时说「去找岗（/job-scrape）」是指错路——岗有的是，只是这个筛选下没有。 */
  filtered?: boolean;
  /** 「可以考虑」那一档里有几个是具名公司的直招 —— 内推够得着的那批在哪。 */
  namedDirectBelow?: number;
  /** 库里明写薪数的岗，薪数中位数。给「按 12 薪保守算」一个参照量级。 */
  observedMonths?: number | null;
  /** 「挂了」可以点的原因，原样透给 JobReadoutBody。 */
  reasons?: { value: string; label: string }[];
  /**
   * 这份名单看的是**已经投出去的**吗。
   *
   * 是的话默认按投递时间倒序（最近投的在最上面），不按分数——分数是用来挑
   * 「接下来投谁」的，对已经投掉的岗没有决策价值；那时人要找的是
   * 「我上周投的那个」。同一张表两种用途，默认排序得跟着用途走。
   */
  byDate?: boolean;
  /** 要关掉的列（key 取自 `data/hidden.ts` 的 HIDEABLE_COLUMNS）。
   *  分数列不可关——那是这张表存在的理由。 */
  hideColumns?: string[];
  /** 已经投过的公司名（归一化）。用来给同公司的其它岗打「这家投过」标记。 */
  appliedCompanies?: Set<string>;
  /** 被「不想看什么」藏掉了几个。空表时要靠它说清是「没有岗」还是「被你滤掉了」。 */
  hiddenCount?: number;
}) {
  // 已投视图的排序在**数据源**上做，不靠列的 defaultSortOrder：
  // 投递日期不是一列（它挤在职位那格的角标里），没有列就挂不上 sorter。
  const narrow = useNarrow();
  // 悬浮提示里的命令也得走适配层：tooltip 是用户读到的字，免斜杠那一档
  // 在这里拿到 `/job-apply` 就是照着敲不动的那一种。
  const { formatCommand } = useCodeTool();

  // ---- 搜索与筛选 ----
  //
  // **为什么放在这一层而不是 antd 的列筛选。** 用户想找「上次看到的那个整车厂的岗」时，
  // 记得的是**只言片语**（公司一半的名字、地点、判词），不是某一列的确切值。
  // 列筛选要求他先知道该点哪一列、再从下拉里挑一个精确值——那是给「按维度收窄」用的，
  // 不是给「我要找那个岗」用的。一个横跨职位名/公司/地点/判词的搜索框才对得上。
  //
  // 来源那一项用下拉：它是**闭集**（就四家），闭集用下拉比让人打字准。
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState<string>("");
  const channels = useMemo(
    () => [...new Set(jobs.map((j) => j.channel).filter(Boolean))].sort() as string[],
    [jobs],
  );
  const kw = q.trim().toLowerCase();
  // 搜索面 = **表上看得见的每一列**。少一列，用户搜他明明看得到的字却搜不到，
  // 而他不会怀疑是搜索框的问题，只会以为那个岗不在了。
  // 2026-08-20 实测漏了两列：搜「猎聘」只命中 2 个（而来源是猎聘的有 2194 个，
  // 那 2 个还是公司名里恰好带「猎聘」二字）；搜「16薪」命中 1 个（薪资里带
  // 16薪 的有几百个）。渠道那一项虽然另有下拉，但下拉是「按维度收窄」，
  // 打字找是另一件事——两条路都要通。
  const hit = (j: Job) =>
    (!channel || j.channel === channel)
    && (!kw || [j.title, j.company, j.location, j.verdict, j.channel, j.salary]
      .some((v) => (v || "").toLowerCase().includes(kw)));
  const jobsIn = kw || channel ? jobs.filter(hit) : jobs;

  // **搜索把展开的那一行筛掉时，要收起它。**
  // `App` 那边的 `effectiveId` 只挡住「这个岗离开了可投名单」（记了状态、标了不投），
  // 挡不住这里的搜索筛选——筛选发生在 `jobsIn`，它看不见。
  // 于是：展开一个岗 → 搜一个搜不到它的词 → 行没了，展开态还在，
  // 滚动效果的 `querySelector` 找不到那一行、静默返回。不崩，但清掉搜索之后
  // 会看到一个自己没再点过的岗还开着——用户不会知道它是从哪一步留下来的。
  useEffect(() => {
    if (selectedId && !jobsIn.some((j) => j.id === selectedId)) onSelect("");
    // 只在筛选条件变化时判：依赖 jobsIn 会让每次数据刷新都重跑一遍。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kw, channel]);

  const rows = byDate
    ? [...jobsIn].sort((a, b) =>
        (b.applied?.date || "").localeCompare(a.applied?.date || "")
        // 同一天投的按分数排——那天投了十几个时，这个次序比随机顺序有用
        || (b.score ?? -1) - (a.score ?? -1))
    // 窄屏撤掉了分数列，`defaultSortOrder` 跟着没了挂靠处——**默认按分排是这张表
    // 存在的理由**，不能因为换了个布局就丢。和上面已投视图同一个做法：排在数据源上。
    : narrow
      ? [...jobsIn].sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
      : jobsIn;

  const columns: ColumnsType<Job> = [
    {
      title: "分",
      dataIndex: "score",
      key: "score",
      // 标记搬到职位那格之后，这一格只剩「分 + 判词」两行，88px 是给三四枚
      // 竖着堆的标记留的宽度，现在用不上了。
      width: 72,
      align: "center",
      // 分数可排序是真实需求：用户要按分挑，也要回看被压低的那些
      sorter: (a, b, order) => nullsLast(a.score, b.score, order),
      // **只有「还能投谁」这份名单默认按分排。** 看已投的那些时按分排没有意义
      // ——那时你要的是「最近投的在最上面」（用户 2026-08-13）。
      // 一个静态的默认排序服务不了两种视图，所以让它跟着视图走。
      defaultSortOrder: byDate ? null : "descend",
      render: (_, job) => {
        // 判词去掉「粗筛：」前缀再显示（见 plainVerdict）。带前缀会在这个窄格里折成两行，
        // 84 行每行都多占一行高；而「是不是深评」已经由下面的「已深评」标记表达了
        // ——**标记要标少数派**：84 行里 80 行是粗筛，标它等于满屏噪音。
        const label = plainVerdict(job.verdict);
        const color = verdictColor[label as Verdict] ?? undefined;
        return (
          <div className="score">
            <b style={{ color }}>{job.score ?? "—"}</b>
            {/* **整份名单判词都一样时不再逐行重复**（判据见 `constants`）。
                上面那段注释自己写着「标记要标少数派」——同一条道理对判词也成立：
                9 行里 9 行都写着「值得投」时，这一行字一个比特都没给出去，
                而它占的是分数正下方那个位置。表头说一次就够，
                分数的颜色仍然带着它的语义。混着别的判词时照旧逐行显示。 */}
            {!constants?.verdict && <i style={{ color }}>{label}</i>}
          </div>
        );
      },
    },
    {
      // 签名列。总分把四维揉成一个数，20 个岗挤在 58-78 分时它分不出高下；
      // 技能与经验回答的是「你干不干得了这个活」——求职者真正要判断的那件事。
      // 颜色规则只表达一件事：这个总分主要是谁撑起来的。
      // 列名带解释：这一列的颜色规则是全表最不直观的一处，而唯一说明它的那行
      // 提示在表头上方——滚两屏就看不见了，偏偏往下翻才是最需要它的时候。
      // 挂在表头上，只要列还在，解释就够得着。
      title: (
        <Tooltip title="这个岗的活你干不干得了（0-100）。比总分高＝活对口但钱少；比总分低＝钱好但活未必干得了。">
          <span>技能</span>
        </Tooltip>
      ),
      dataIndex: "skill",
      key: "skill",
      width: 76,
      align: "center",
      sorter: (a, b, order) => nullsLast(a.skill, b.skill, order),
      render: (_, job) => {
        if (job.skill == null) return <span className="skill-none">—</span>;
        const gap = job.score == null ? 0 : job.skill - job.score;
        // ≥8 分的背离才算「明显」，小于这个数是打分噪音
        const tone = gap >= 8 ? "up" : gap <= -8 ? "down" : "flat";
        const why =
          tone === "up"
            ? `活对口（技能 ${job.skill}），但薪资/公司这些条件把总分拖下来了`
            : tone === "down"
              ? `总分 ${job.score} 主要是薪资等条件撑的，技能只有 ${job.skill}`
              : `技能与总分基本一致`;
        return (
          <Tooltip title={job.skillWhy ? `${why}。${job.skillWhy}` : why}>
            <span className="skill" data-tone={tone}>
              {job.skill}
            </span>
          </Tooltip>
        );
      },
    },
    {
      // 年包折算好再显示。原始串四种口径混用，跨岗没法比——
      // 「25-35k·20薪」的 60-84 万其实高过「40-70k」按 12 薪的下沿 48 万。
      title: "年包",
      key: "annual",
      width: 108,
      align: "right",
      sorter: (a, b, order) => nullsLast(a.annual?.low, b.annual?.low, order),
      render: (_, job) =>
        job.annual ? (
          <Tooltip
            title={[
              // **「保守」得说清保守到什么程度。** 平台只在薪数 >12 时才标
              // `·N薪`（那是卖点），没标的按 12 折是对的 —— 但实测他库里明写
              // 薪数的 1346 个岗**一个 12 薪都没有**，中位 15。不给这个参照，
              // 「保守算」听起来像「差不多」，而它大概率低两三成。
              // 数从他自己的库里现算（`observed_months`），不写死 —— 各行业的
              // 薪数惯例差得远，写死一个就成了行业预设。
              job.annual.assumed12
                && (observedMonths
                  ? `平台只给了月薪、没写几薪，这里按 12 薪保守算。你库里明写薪数的岗中位是 ${observedMonths} 薪——真实数多半比这里显示的高。`
                  : "平台只给了月薪、没写几薪，这里按 12 薪保守算。"),
              job.annual.estimated &&
                "这个数是推算的：原文要么按日/小时结算（按法定月计薪天数 21.75 天、"
                  + "每日 8 小时折），要么只写了「万」没写按月还是按年（数值到了这个量级"
                  + "只可能是年包）。都不是读到的确切值。",
              job.annual.variable &&
                "原文带提成/绩效/计件——这个数只是底薪，浮动部分没算进去。",
              `原文：${job.salary}`,
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span
              className="annual"
              data-assumed={job.annual.assumed12 || job.annual.estimated}
            >
              {job.annual.low}-{job.annual.high}
              <em>万</em>
              {/* 「另有浮动」必须显示在**表格里**，不能只藏在 tooltip 里：
                  销售、律师、中介、保险的大头就在提成上，一个 6 万的底薪
                  被读成「这岗只值 6 万」，人就直接划过去了。 */}
              {job.annual.variable && <em className="annual-plus">+浮动</em>}
            </span>
          </Tooltip>
        ) : (
          <span className="skill-none">—</span>
        ),
    },
    {
      title: "职位",
      dataIndex: "title",
      key: "title",
      render: (_, job) => (
        <div>
          {/* 窄屏把撤掉的三列并到这里。顺序跟原来的列序一致（分 · 技能 · 年包），
              这样从桌面切到手机时读法不用重学。判词跟着分数走，不单独占位。 */}
          {narrow && (
            <div className="job-nums">
              <b style={{ color: verdictColor[plainVerdict(job.verdict) as Verdict] }}>
                {job.score ?? "—"}
              </b>
              {/* 整份名单判词都一样时，这一行不再重复 —— 表头说过了。
                  分数本身的颜色仍然带着判词的语义，图例在表头那句里。 */}
              {!constants?.verdict && (
                <i style={{ color: verdictColor[plainVerdict(job.verdict) as Verdict] }}>
                  {plainVerdict(job.verdict)}
                </i>
              )}
              {/* 标签用正文字体、数值才用等宽：等宽加在汉字上会把「技能」拉成散字
                  （AGENTS.md「等宽只留给纯数字」）。「万」同理，且不留空格
                  ——桌面那一列也是紧挨着的 `<em>万</em>`。 */}
              {job.skill != null && (
                <span className="jn-k">技能<b>{job.skill}</b></span>
              )}
              {job.annual && (
                <span className="jn-k">
                  <b>{job.annual.low}-{job.annual.high}</b>万
                  {job.annual.variable && "+浮动"}
                </span>
              )}
            </div>
          )}
          <div className="job-title" data-open={job.id === selectedId}>
            {job.title}
          </div>
          <div className="job-meta">
            <b>{job.company}</b>
            {/* **公司名自己已经说了的，不再说第二遍。** 平台把不公开的雇主写成
                「某上海知名公司」——实测 1369 个匿名岗里**每一个**都含「某」
                （1355 个在开头，另外 14 个在中间：「上海某新能源汽车公司」），
                后面再缀「（公司未公开）」是同一件事说两次，六个字乘以一千多行。
                名字里没写的那十几个才需要这个标注，那时它是真信息。 */}
            {!constants?.anon && job.anonymousEmployer
              && !(job.company || "").includes("某") && "（公司未公开）"}
            {/* **标少数，不标多数。**
                整份都是猎头 → 表头说一次，逐行标 0 比特（`agencyAll`）。
                绝大多数是猎头（这份 9 个里 8 个）→ 逐行标那 8 个还是 0 比特，
                真正带信息的是**剩下那一个不是**——而它恰恰是最值钱的一个
                （具名直招才找得到人内推）。所以这一档反过来标少数。
                实测栽过：占比判据刚落地时沿用了「有表头就不标行」，
                结果那唯一的直招岗和 8 个猎头岗长得一模一样，表头说「8 个是猎头」
                却看不出是哪 8 个。 */}
            {constants?.agencyAll
              ? null
              : constants?.agency
                ? (job.viaHeadhunter === false && "（企业直招）")
                : (job.viaHeadhunter === true && "（猎头代招）")}
            {/* 同一个岗挂在多个地方：数字要说出来，同岗不同价是职级未定的信号。
                措辞不用「投放」——那是广告业的词，求职者读到「+2 投放」不会想到
                「这个岗在别处也挂着」。说它做的事。 */}
            {job.duplicates && job.duplicates.length > 0 && (
              <Tooltip
                title={`这个岗还挂在另外 ${job.duplicates.length} 个地方：${job.duplicates
                  .map((d) => d.salary || "薪资未标")
                  .join("、")}——各家挂的价不同，详情里有链接`}
              >
                <span className="dup-chip">另挂 {job.duplicates.length} 处</span>
              </Tooltip>
            )}
            {/* 只拼有内容的字段。平台没给薪资/地点/年限是常事，
                印「未标」会把「没抓到」当成一条信息摆在那儿。 */}
            {/* 薪资已经折算成年包放进独立一列，这里不再重复原始串 */}
            {[constants?.city ? "" : job.location, job.experience]
              .filter(Boolean).map((x) => ` · ${x}`)}
            {/* **标记跟着职位走，不再堆在分数那一格里。**
                原来这四五枚标记竖着塞在 88px 宽的分数格里，一行能堆到四层——
                行高被撑到 130px，24 行就是 3100px 的滚动；而右边职位那一列
                在 1440px 宽下有五百多像素是空的。实测「材料就绪」的行比只有
                「读过 JD」的行高出 25px，整张表的行距全是乱的。
                标记说的本来也是这个岗的事（投没投、读没读 JD、有没有材料），
                长在职位后面比长在分数下面更讲得通。 */}
            <span className="job-chips">
              {/* 「已投」排在最前，而且投过之后不再显示「推荐先投」——
                  求职最容易犯的错就是重复投同一家，而原来投递记录只被数了个总数、
                  从没回接到岗位上：面板说「已投递 1」，可哪一个投了完全看不出来，
                  那个岗照旧躺在可以投的列表里，和没投过的长得一模一样。 */}
              {job.applied && (
                <Tooltip title={`${job.applied.date} 通过${job.applied.channel || "未记录渠道"}投递`}>
                  {/* statusLabel 是中文说法；status 是英文码，直接印就是
                      「已投 · applied」——AGENTS.md 禁的那种 */}
                  <span className="sent-chip">已投 · {job.applied.statusLabel || job.applied.status}</span>
                </Tooltip>
              )}
              {/* **这家公司投过，但这个岗没投。**
                  用户 2026-08-13：「投过的公司也显示，不过提示该公司投过，
                  让用户自己选择是否屏蔽」——**藏掉等于替他做决定**，
                  标记才是把事实给他、选择留给他（要藏在「不想看什么」里勾）。
                  和「已投」互斥：那一个说的是这个岗，这一个说的是这家公司。 */}
              {!job.applied && appliedCompanies?.has((job.company || "").trim().toLowerCase()) && (
                <Tooltip title="这家公司你投过别的岗了。同一家同时联系两个招聘方容易撞车——要不要投，你自己定；不想再看到可以在「不想看什么」里勾掉。">
                  <span className="co-chip">这家投过</span>
                </Tooltip>
              )}
              {!job.applied && job.id === recommendedId && (
                <span className="rec-chip">推荐先投</span>
              )}
              {/* 原来这里印的是「已深评」——一个框架内部词，裸露在列表里，
                  没有任何解释。用户得先学会这个词才知道它和别的行差在哪。
                  换成它**实际做过的事**：读过 JD（粗筛只看列表卡片）。

                  **2026-08-22 反过来标：标没读过的那个。** 实测 8/9 行都挂着
                  「读过 JD」—— 一个 89% 的行都有的标记不是信息，是底噪，
                  而它是这一行里最扎眼的青色方章。真正要提醒的恰恰是**没读过**
                  的那一行：它的分只按列表卡片评的，硬性条件没核对过，
                  你照它去投是在赌。原来那件事只由「没有章」表示 ——
                  **用缺席去编码最要紧的信息**，是最弱的一种写法。 */}
              {/* **「没做深评」和「没读 JD」是两件事，此前由同一枚章代表。**
                  这枚章的判据是 `!evaluated`，而它的字面写着「没读 JD」、
                  悬浮提示写着「完整 JD 没读、硬性条件没核对、公司没查」。
                  实测 2026-08-26：会挂这枚章的 1416 个岗里 **940 个的判词来源
                  明写「粗筛（读过 JD 正文）」** —— 对这 940 个，那三条里有两条
                  是假的，真正没做的只有公司调研与双角色审稿。
                  **屏幕上说的必须是真的**，所以按 `jdRead` 分成两枚。 */}
              {!job.evaluated && !job.jdRead && (
                <Tooltip title="这个岗只按列表卡片上的信息评的：完整 JD 没读、硬性条件没核对、公司没查。分数仅供排序参考，投之前先自己看一眼原文。">
                  <span className="raw-chip">没读 JD</span>
                </Tooltip>
              )}
              {!job.evaluated && job.jdRead && (
                <Tooltip title="完整 JD 读过了，硬性条件也逐条核对过。还没做的是公司调研和双角色审稿——出材料时会补上。">
                  <span className="raw-chip raw-chip-soft">没查公司</span>
                </Tooltip>
              )}
              {/* **「材料就绪」在「可以考虑」这一档是句过头话。**
                  那一档的定义就是「先问清楚关键信息再决定投不投」
                  （`04-job-evaluation.md`），`/job-apply` 的判词闸门也写着
                  这一档只落评估、不出开场白。可实测 99 个「可以考虑」全都有
                  开场白，而它们挂的章和「值得投」一模一样 —— 用户看到
                  「材料就绪」，读到的是「可以发了」。
                  **他已经这样投出去 26 个了**，占全部投递的三成。
                  话术确实备好了，这没错；错的是让它看起来像已经可以发。 */}
              {/* **「评估里列了要问什么」这句话不能无条件说。**
                  实测 2026-08-22：99 个有材料的「可以考虑」里，只有 52 个的深评
                  真留下了「投前必问」那一节——**另外 47 个，这句话是假的**。
                  （那一节是后来才写进 `04` 的输出格式的，早于它的深评没有。）
                  一枚章保证「打开有东西」，打开却是空的，比不说更坏：
                  下次有东西时他也不会再打开了。所以两种情况分开说。 */}
              {job.materials && (
                plainVerdict(job.verdict) === "可以考虑" ? (
                  (job.askBefore ?? []).length > 0 ? (
                    <Tooltip title="开场白已经写好了，但这一档的意思是「先问清楚再决定投不投」——评估里列了这个岗还没弄明白的地方，投之前先把那几条问了。问清楚之后觉得行，再把开场白发出去。">
                      <span className="ask-chip">话术备好 · 先问清</span>
                    </Tooltip>
                  ) : (
                    <Tooltip title={`开场白已经写好了，但这一档的意思是「先问清楚再决定投不投」。这个岗的评估里没留下要问什么（那一节是后来才要求的，早先出的那份没写）——想让它补一份，重跑 ${formatCommand("/job-apply")} 加这个岗的链接。`}>
                      <span className="ask-chip" data-thin>话术备好 · 这档得先问</span>
                    </Tooltip>
                  )
                ) : <span className="mat-chip">材料就绪</span>
              )}
              {/* **这个岗多久没人动了。** 国内平台自己就按周分桶（猎聘、BOSS
                  都把「本周活跃」摆在筛选里），两周没刷新意味着招聘方连着跳过了
                  两个周期——多半招到人了、编制冻了，或者没人在跟这个岗。
                  投它不是运气差，是投了个没人看的地方。

                  实测：他排第一第二的两个 66 分岗，分别是 18 天和 15 天前刷新的，
                  而面板把它们摆在最前面、一个字不说。

                  **只标超过阈值的**（同「标记要标少数派」）：「3 天前刷新」是噪音，
                  「18 天没刷新」才是要人改主意的信息。没有日期时什么都不显示——
                  「很新」和「不知道」不是一回事。 */}
              {/* **顶上那句「从它们开始」指的就是这几个。** 那句话一直在印，
                  而名单按分数排、没有任何东西标出是哪几个 —— 要照它做，
                  他得逐个点开 60 次（点开也看不到，这个数没上过屏）。

                  和下面那个「没刷新」是两件事：那个是招聘方多久没动这个岗，
                  这个是**你压了它多久**。两个都可能出现，各说各的。 */}
              {job.queuedLong && job.queuedDays != null && (
                <Tooltip title={`这个岗 ${job.queuedDays} 天前就抓到了，材料也备好了，一直没发出去。分数不会因为放久了变低——变少的是它还挂在平台上的时间（实测已经有岗在发出去之前就下线了）。先发排得最久的这几个。`}>
                  <span className="queued-chip">排了 {job.queuedDays} 天没发</span>
                </Tooltip>
              )}
              {/* **顶上那句「N 个岗的判断该重跑一遍」指的就是这几个。**
                  同一个形状这一页修过一次：「从它们开始」那句一直在印，而名单
                  按分数排、没有任何东西标出是哪几个 —— 照它做，他得逐个点开
                  60 次（点开也看不到，那个数当时没上过屏）。
                  这一次别再让它重演：顶上给了数，名单上就要认得出。

                  值本身就是理由（「翻档」/「当时没读全，得先抓 JD」），
                  直接显示，不在这里另起一套说法 —— 判据在
                  `tools/stale_materials.py`，那是唯一住址。 */}
              {job.restale && (
                <Tooltip title={`这个岗的判断现在不该再信：${job.restale}。重跑它会把职位描述读回来、重新判一遍，材料也跟着重出。一次一个跑 ${formatCommand("/job-apply")} 加这个岗的链接；这一批一起跑是 ${formatCommand("/job-apply")} --stale。`}>
                  <span className="ask-chip" data-thin>该重跑 · {job.restale}</span>
                </Tooltip>
              )}
              {job.staleDays != null && (
                <Tooltip title={`我们抓到这个岗的时候，它上一次刷新是 ${job.staleDays} 天前。国内平台上超过两周没动的岗，多半是招到人了、编制冻了，或者没人在跟——投之前先点开看看它还在不在。注意两点：这个时间是抓到那天记下的，之后没再查过（它后来被刷新过我们看不到）；而且只有猎聘给这个日期，其余平台没有，不代表它们更新。`}>
                  <span className="stale-chip">抓到时已 {job.staleDays} 天没刷新</span>
                </Tooltip>
              )}
            </span>
          </div>
        </div>
      ),
    },
    // 「硬性条件」这一列撤了：只有深评过的岗才有硬门数据，19 行里只有 2 行有章，
    // 剩下 17 行是空白——一整列的宽度换两枚章不值得。详情区里它是完整展示的。

  ];

  // 详情直接展开在**这一行下面**，而不是甩到表格外一千像素处 ——
  // 点第 15 行还要滚下去看详情，回来又找不到刚才那行，是最容易丢失上下文的做法。
  // **同时只开一个**：受控的 expandedRowKeys 只放一个 id，点别的自动收起前一个。
  const toggle = (id: string) => onSelect(id === selectedId ? "" : id);

  // ── 展开后把这一行滚回视口顶部 ──
  //
  // 单开手风琴有个必然的副作用：点第二个岗时，**先收起前一个**再展开新的。
  // 前一个如果很高（材料齐全的岗带话术、硬性条件、评分明细、面试记录，轻松
  // 两千像素），收起的瞬间整页塌陷，而浏览器不会替你调整滚动位置——于是你
  // 盯着的地方突然变成了别处，看到的不是刚点的那个岗。岗位越完整越明显。
  //
  // 所以展开后主动把那一行的表头对齐到视口顶部。要点两个：
  //   1. 必须等 DOM 提交后再滚——收起+展开是同一次渲染里的两处高度变化，
  //      提交前量出来的位置是旧的。用 rAF 等一帧。
  //   2. 尊重 prefers-reduced-motion：前庭敏感的人被一段平滑滚动带走会难受。
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!selectedId) return;          // 收起不滚：原地收起，视线本来就在那
    const id = requestAnimationFrame(() => {
      const row = listRef.current?.querySelector<HTMLElement>(
        `tr[data-row-key="${CSS.escape(selectedId)}"]`,
      );
      if (!row) return;
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      // 不用 scrollIntoView({block:"start"})——它把行顶死在视口第 0 像素，
      // 上一行的分数与「已投/材料就绪」标记全被切掉，看不出自己点的是哪一行。
      // 留一段余量，让被点的那行完整露出、且上方还能瞥见一点表格上下文。
      // 76 不是在避让什么——这一页**没有任何 sticky 元素**（2026-08-20 核过）。
      // 它是纯视觉余量：留出约一行表格的高度，让上一行的分数与「已投/材料就绪」
      // 标记还露得出来，看得出自己点的是这一行而不是最上面那行。
      // 改它只影响观感，不会遮住内容。
      const top = row.getBoundingClientRect().top + window.scrollY - 76;
      window.scrollTo({ top: Math.max(top, 0), behavior: reduce ? "auto" : "smooth" });
    });
    return () => cancelAnimationFrame(id);
  }, [selectedId]);

  /**
   * 整份名单里**每一行都一样**的那几个值。
   *
   * 实测（2026-08-22，用户真实数据 9 行）：`上海` 9/9、`值得投` 9/9、
   * `（公司未公开）` 8/9、`读过 JD` 8/9 —— **一行里最扎眼的四样东西，
   * 有四样从不变化。** 它们占着位置、抢着注意力，却一个比特都没给出去；
   * 真正有差别的（分数、技能分、年包、职位名、材料就绪）反倒要跟它们抢。
   *
   * 判据是**数据说了算**，不是写死某个城市或某个判词：全都一样才抽走，
   * 抽走的在表头说一次。少于 3 行不抽 —— 两行「都一样」不算规律，
   * 抽了反而让人以为那一栏没数据。
   */
  const constants = useMemo(() => {
    // **看的是 `jobs`（整份名单），不是 `rows`（搜索/渠道过滤之后那几行）。**
    // 用 `rows` 会造出一个很怪的现象：搜索框里打「上海」，命中的三行当然都在上海，
    // 于是「地点」这一栏**在他刚搜过的那个字段上**整列消失，只剩表头一句
    // 「这 3 个都在上海」；清空搜索它又自己回来。抽走的前提是「这本来就没差别」，
    // 而过滤出来的一致是**他自己筛的结果**，不是名单的性质。
    if (jobs.length < 3) return null;
    //: `=== true` 而不是真值判断 —— `null` 是「没判过」，两边都不算。
    const agencyN = jobs.filter((j) => j.viaHeadhunter === true).length;
    const all = (f: (j: Job) => unknown) => {
      const first = f(jobs[0]);
      return first && jobs.every((j) => f(j) === first) ? String(first) : "";
    };
    return {
      verdict: all((j) => plainVerdict(j.verdict)),
      city: all((j) => j.location),
      anon: jobs.every((j) => j.anonymousEmployer) ? "公司都没公开" : "",
      // 猎头代招在国内是多数（全库 52%、这份名单 67%），逐行标是对的 ——
      // 剩下那几个直招才是更值得优先投的，靠对比才看得出来。
      // 但**整份几乎都是猎头**时它一个比特都不给，那就抽到表头说一次。
      //
      // **判据从 `every` 改成占比。** `every` 的毛病是「一个例外整条提示就消失」：
      // 实测 2026-08-22 这份名单 9 个里 8 个猎头代招，恰好躲过 —— 而 8/9 给用户的
      // 信息和 9/9 没有区别。占比过八成就说，并把真实个数说出来
      // （「9 个里 8 个」比「都是」既更准也更有用）。
      agency: agencyN * 5 < jobs.length * 4
        ? ""
        : agencyN === jobs.length ? "都是猎头代招" : `${agencyN} 个是猎头代招`,
      //: 全是猎头 —— 逐行标记该整个撤掉（标一个人人都有的属性等于没标）。
      agencyAll: jobs.length > 0 && agencyN === jobs.length,
    };
  }, [jobs]);
  const constNote = constants
    ? [constants.verdict && `都是「${constants.verdict}」`,
       constants.city && `都在${constants.city}`,
       constants.anon, constants.agency].filter(Boolean).join(" · ")
    : "";

  return (
    <div className="shortlist" ref={listRef}>
      {/* 抽走的那几样在这儿说一次。**不是省略，是换个地方说** ——
          原来它们在每一行里各占一份墨，加起来是这一句的三十几倍。 */}
      {constNote && <p className="sl-const">这 {jobs.length} 个{constNote}</p>}
      {/* ── 猎头压满这一档时，说出具名直招的那批在哪 ──
          猎头代招不等于差岗，但它决定了**能不能找到人**：简历先进猎头的库，
          你没有第二条路。而内推是具名公司那批唯一不靠海投的一条路（回复率没量过，
          别当成测出来的排序），内推只对具名公司成立。
          投后统计那一栏已经在劝他「与其再投一个，不如找个能说上话的人」——
          可这一档里一个具名公司都没有，那句话就落不了地。
          两条建议必须在同一屏上接得上，否则用户按哪条都对不上另一条。 */}
      {constants?.agency && (namedDirectBelow ?? 0) > 0 && (
        <p className="sl-const sl-const-alt">
          {`猎头代招是简历先进他的库，推不推由他定，你没有第二条路。想找人内推的话，下面「可以考虑」那一档里有 ${namedDirectBelow} 个具名公司的直招岗——那批才有人可找。跑这一档，产出里会多一段发给在职员工的内推请托（已经有材料的只补那一段）：`}
          {/* **每处引导都要写出命令。** 不写的话这一行只是个感慨：
              「那批才有人可找」——然后呢？内推请托那段话由 `/job-apply` 出
              （具名直招才生成，判据在 `job-apply.md` 的 1.6c）。

              ⚠️ **原来给的是裸 `/job-apply`，而那条只取「强匹配 / 值得投」。**
              这一句指的恰恰是「可以考虑」那一档 —— 命令一个都不会碰到它们。
              他敲完发现没动，然后连带不信这一整句。

              同一个形状 2026-08-30 在面板上一共撞到五处（阻塞那一栏、自检的
              三条、这里）：**一句话给了命令，而命令的选岗条件和这句话说的事
              对不上。** 判据很简单：命令选的那批，包不包含句子指的那批。 */}
          <Cmd>/job-apply 可以考虑</Cmd>
        </p>
      )}
      {/* 搜索条只在表够长时出现——十几行的表上，一个搜索框比直接扫一眼更慢。 */}
      {jobs.length >= 12 && (
        <div className="sl-searchbar">
          <Input.Search
            allowClear
            placeholder="搜职位名、公司、地点、薪资、结论、来源"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="sl-search"
          />
          {channels.length > 1 && (
            <Select
              allowClear
              placeholder="哪个网站来的"
              value={channel || undefined}
              onChange={(v) => setChannel(v ?? "")}
              options={channels.map((c) => ({
                value: c,
                label: `${c}（${jobs.filter((j) => j.channel === c).length}）`,
              }))}
              className="sl-filter"
            />
          )}
          {(kw || channel) && (
            <span className="sl-search-n">
              {rows.length === 0
                ? "一个都没搜到"
                : <>搜到 <b>{rows.length}</b> 个 / 共 {jobs.length} 个</>}
            </span>
          )}
        </div>
      )}
      <Table<Job>
        /* **随视图重挂。** antd Table 把排序状态存在自己内部，只改
           `defaultSortOrder` 不会让已经挂载的表重新排——实测切到「已投递」
           之后仍是按分数降序。key 一变组件重挂，内部状态跟着清掉。 */
        key={`${byDate ? "by-date" : "by-score"}-${narrow ? "narrow" : "wide"}`}
        rowKey="id"
        /* 关掉的列在这里滤，不在定义处加条件——定义处加条件会让
           每个列对象都缠上一句 `hideColumns?.includes(...)`，读起来全是噪音。 */
        columns={columns.filter(
          (c) => !(hideColumns ?? []).includes(String(c.key))
            // 窄屏：三个数字列的值已经并进职位格了，列本身撤掉
            && !(narrow && ["score", "skill", "annual"].includes(String(c.key))),
        )}
        dataSource={rows}
        pagination={false}
        showSorterTooltip={false}
        expandable={{
          expandedRowKeys: selectedId ? [selectedId] : [],
          onExpand: (_, job) => toggle(job.id),
          expandedRowRender: (job) => (
            <JobReadoutBody
              job={job}
              onExclude={() => onExclude(job.id)}
              onExpire={onExpire ? () => onExpire(job.id) : undefined}
              onChanged={(advance, phase) =>
                onChanged?.(advance, job.id, phase)}
              reasons={reasons}
            />
          ),
          // **不要那一列**。整行本来就可点，为一个三角形单开一列等于把「交互提示」
          // 当成「一列数据」——结构上是类别错误，视觉上在分数左边留一道空荡荡的边。
          // 展开状态改用已有元素表达：左侧强调条 + 职位名变色，零新增元素。
          showExpandColumn: false,
        }}
        onRow={(job) => ({
          onClick: () => toggle(job.id),
          // 表格行默认不可聚焦，补上 tabIndex + Enter/Space，键盘用户才能展开
          tabIndex: 0,
          // 整行就是展开控件（没有单独的箭头按钮了），所以要让屏读器当按钮播报
          role: "button",
          "data-selected": job.id === selectedId,
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              toggle(job.id);
            }
          },
          "aria-expanded": job.id === selectedId,
        })}
        locale={{
          // 新用户跑完 `/job-setup` 之后看到的就是这一屏——它是第一印象，
          // 不能只说「空的」。命令要**可复制**：让人对着屏幕手打是在制造错字，
          // 而这恰恰是最需要照做的一刻。
          // 空表有**三种**原因，说错一种就是把用户指向错的地方。
          // 第三种是 2026-08-13 加「不想看什么」时漏的：屏蔽把表滤空了，
          // 页面却说「还没有职位可以看，下一步是去找岗」——而库里有 1204 个岗，
          // 照它去 /job-scrape 只会抓回更多看不见的岗。
          // **搜索没搜到是第四种空。** 上面那段注释自己写着「说错一种就是把用户
          // 指向错的地方」——而搜索是 2026-08-19 加的，加完没补这一支：
          // 用户搜了个词、没搜到，页面却说「还没有职位可以看，下一步去找岗」，
          // 而库里两千多个岗好好躺着。这一支必须排在最前面：它是**当下这一刻**
          // 表为什么空，比库里有没有岗更近。
          emptyText: (kw || channel) ? (
            <div className="shortlist-empty">
              <p className="se-lead">
                <span>{`没有匹配「${[kw, channel].filter(Boolean).join(" · ")}」的岗。换个词，或者把上面的搜索清空。`}</span>
              </p>
            </div>
          ) : hiddenCount ? (
            <div className="shortlist-empty">
              <p className="se-lead">
                <span>岗都在，只是被你自己的屏蔽规则藏起来了——点上面的「不想看什么」，里面有「全部清掉」。</span>
              </p>
            </div>
          ) : filtered ? (
            <div className="shortlist-empty">
              <p className="se-lead">这个筛选下没有岗——点上面的「×」取消筛选看全部。</p>
            </div>
          ) : (
            <div className="shortlist-empty">
              <p className="se-lead">还没有职位可以看——资料建好了，下一步是去找岗。</p>
              <div className="se-steps">
                <div className="se-step">
                  <Cmd>/job-scrape</Cmd>
                  <span>按你资料里的目标岗位和城市去各平台搜一轮</span>
                </div>
                <div className="se-step">
                  <Cmd>/job-rank</Cmd>
                  <span>给搜到的岗打分排序，能投的会出现在这里</span>
                </div>
              </div>
              <p className="se-foot">两条都在命令行里跑。跑完刷新这一页就有了。</p>
            </div>
          ),
        }}
      />
    </div>
  );
}

/** 不投的岗：硬性条件没过、方向不对、分太低，以及**你自己排除掉的**。 */
export function ShelvedList({
  jobs,
  excluded,
  onRestore,
}: {
  jobs: Job[];
  /** 你手动排除的那些——要能区分出来，也要能放回去 */
  excluded?: Set<string>;
  onRestore?: (id: string) => void;
}) {
  if (jobs.length === 0) {
    return <p className="shelf-why">没有被挡下的职位。</p>;
  }
  // 你自己排除的排在最前——那是你刚做的动作，最可能要撤销；
  // 其次是还能放回去的（已下线、规则判的），最后才是硬性条件没过那一大批。
  const rank = (j: Job) =>
    (excluded?.has(j.id) ? 0 : (j.expired || j.ruleSkipped) ? 1 : 2);
  const sorted = [...jobs].sort((a, b) => rank(a) - rank(b));
  // **不能整份铺出来。** 实测这个用户有 2086 个被挡下的岗，全渲染出来页面高
  // 164000px、DOM 一万六千个节点——展开那一下浏览器直接卡死（这次改版就是在那儿
  // 卡住的）。而这份名单里真有事可做的只有能放回的那 90 个，剩下 1996 个是
  // 「硬性条件没过」的存档：翻不动，也没有按钮可按。
  //
  // 所以按上面的次序取前 CAP 个，剩下的用一句话交代清楚是什么、有多少。
  // 不做「全部展开」：点开就是同一次卡死，把炸弹换个位置放不算修好。
  const CAP = 60;
  // **手点的那一档要限量，不然它会把窗口占满。**
  //
  // 上面那句「你自己排除的排在最前」写的时候他只手点过几个；实测 2026-08-23
  // 已经有 89 个 —— 60 个窗口全被它占满，**规则淘汰的 720 个一行都露不出来**。
  // 而按同一段注释自己的说法，规则淘汰才是「最容易错、最该给撤销口」的那批
  // （「实测 4 个年包 72-160 万的岗死于标题含『开发』」）。
  //
  // 手点的留一小截就够：他要撤的多半是刚点的那几个，不是三周前那批。
  // 剩下的窗口留给规则判的 —— 那批才需要人再看一眼。
  const MINE_CAP = 12;
  const mineRows = sorted.filter((j) => excluded?.has(j.id));
  const restRows = sorted.filter((j) => !excluded?.has(j.id));
  const shown = [...mineRows.slice(0, MINE_CAP),
                 ...restRows.slice(0, CAP - Math.min(mineRows.length, MINE_CAP))];
  const rest = sorted.length - shown.length;
  return (
    <div>
      {shown.map((job) => {
        const mine = excluded?.has(job.id) ?? false;
        // 已下线：外面的事实，不是判断。它自己一档——「你排除的」还能回看当初
        // 为什么，「已下线」没什么可回看的，它只是不在了。标错了（比如点开恰好
        // 是聚合页而职位其实还在）同样能放回，分数与评估都留着。
        const gone = job.expired ?? false;
        // 规则淘汰的（预筛判「跳过」）同样能撤。原来只有 `mine` 才给「放回可以投」，
        // 于是规则杀掉的 103 个岗（占 38%）在界面上没有任何回头路。而规则最容易错：
        // 实测 4 个年包 72-160 万的「智能体开发产品经理」死于标题含「开发」，
        // JD 一个字没读过。谁下的结论谁最可能错，就更要留撤销口。
        const canRestore = mine || gone || (job.ruleSkipped ?? false);
        // 自己排除的显示当初写的原因；没写原因才退回一句「你排除的」。
        // 一律显示「你排除的」等于把已有的信息扔掉——两周后回看会想不起为什么。
        const why = gone
          ? `已下线${job.expiredDate ? `（${job.expiredDate} 标的）` : ""}`
          : mine
          // **和上面「已下线」对称地带上日期。** 原来这一支永远没有日期，
          // 而它恰恰是最需要的那一支：「已下线」没什么可回看的，
          // 「你排除的」两周后回看会想不起当初为什么 —— 那个「当初」是几号，
          // 正是判断这条结论还作不作数的依据。
          ? `${job.skipReason || "你排除的"}${job.skipDate ? `（${job.skipDate} 标的）` : ""}`
          // **规则淘汰的也有原因，而且写得很具体。** 这一支原来直接落到判词，
          // 于是 720 行的悬浮全是两个字「跳过」——而理由一直在盘上
          // （`rank_breakdown.依据`，例：「年包上沿约 32 万，低于底线 42 万
          // （原文：20-25k·13薪）」），导出侧现在把它填进 `skipReason`。
          // 和硬门那次是同一类：数据在、断在最后一层。
          : job.skipReason
          ? job.skipReason
          : plainVerdict(job.gateFailReason || job.verdict);
        const tip =
          gone && job.expiredReason ? `${why}：${job.expiredReason}` : why;
        return (
          <div className="shelf-row" key={job.id} data-mine={mine} data-gone={gone}>
            {/* **可见标签用 `why`，悬浮提示用 `tip`。** 已下线那一支的原因是
                整句话（「浏览器打开跳到职位聚合页，岗位已不在」），摆进行里
                会撑爆版式；而它恰恰是「放回」那个按钮问的那句
                「职位其实还在？」的唯一依据。 */}
            <Tooltip title={tip}>
              <span
                className="stamp"
                data-state={gone ? "unknown" : mine ? "na" : "fail"}
                data-size="sm"
                role="img"
                aria-label={gone ? `已下线：${job.title}`
                  : mine ? `你排除的：${job.title}` : `不投：${why}`}
              >
                <span aria-hidden>{gone ? "停" : mine ? "无" : "否"}</span>
              </span>
            </Tooltip>
            <span>
              {job.title} · {job.company}
              {job.annual && ` · ${job.annual.low}-${job.annual.high}万`}
            </span>
            {canRestore && onRestore ? (
              <>
                {(!mine || gone) && <span className="shelf-why">{why}</span>}
                <button
                  type="button"
                  className="shelf-restore"
                  onClick={() => onRestore(job.id)}
                  title={gone ? "职位其实还在？放回可以投的岗位，分数与评估都还在"
                    : mine ? "放回可以投的岗位"
                    : "这条是规则判的（没读 JD）。放回后它会回到待评，重新走一遍评估"}
                >
                  放回可以投
                </button>
              </>
            ) : (
              <span className="shelf-why">{why}</span>
            )}
          </div>
        );
      })}
      {rest > 0 && (
        <p className="shelf-more">
          另外 {rest} 个不列了——都是<b>硬性条件没过</b>
          {"或分太低的，页面上也没有可点的东西。上面这些是你自己标的、已下线的、" +
           "以及只按规则判掉的：需要复核的是这几类。"}
        </p>
      )}
    </div>
  );
}
