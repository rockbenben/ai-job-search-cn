import { Tooltip } from "antd";
import { Cmd } from "./Cmd";
import { useCodeTool } from "../context/CodeToolContext";
import type { ResumeInsight } from "../types";

/**
 * 市场对这份简历的反馈。
 *
 * ## 为什么不是「简历点评」
 *
 * 措辞、结构、要不要加量化——这类建议任何工具都能给，跟这个仓库攒下的上百份
 * 比对没有关系，放上来只是装饰。这里只放**攒够评估才说得出来**的三件事：
 *
 *   1. 哪些行业对得上（业务域 ≥60 的岗长什么样）→ 直接改搜索词
 *   2. 什么在挡你（硬门与低分的成因）→ 哪样能改、哪样只能绕开
 *   3. 简历要补什么（行业对口的岗要的词 ↔ 简历里有没有）→ 具体改哪一句
 *
 * ## 位置
 *
 * 只在侧栏「市场怎么读你的简历」那颗按钮打开的弹窗里渲染，不占正文。它解释
 * 短名单为什么长这样——那是「理解」不是「行动」，所以不该占首屏；结论仍写在
 * 标题行上，点开就看见。
 */
/** 一个缺词旁边那行小字。
 *
 * **两个词源说的不是同一件事**，所以不能共用一句「N/M 个行业对口的岗要」：
 * 正文里提到 → 这些岗**要**这项能力；职位名里就有 → **HR 会拿这个词搜人**，
 * 简历里没有等于在那批搜索里不出现。后者是「被搜到」那条路上的事
 * （`job-resume.md` 2.6），前者是「投出去」那条路上的事。
 */
function askNote(a: ResumeInsight["sweetSpot"]["asks"][number]) {
  return a.where === "标题"
    ? `${a.n}/${a.of} 个岗的职位名里就有它 · HR 搜人打的是这个词`
    : `${a.n}/${a.of} 个行业对口的岗要`;
}

export function ResumeRead({ data }: { data: ResumeInsight }) {
  const { sweetSpot: ss, blockers } = data;
  const { formatCommand } = useCodeTool();
  // **两类分开。** 「简历里没有」只说明忘了写；「资料里也没有」说明他真没这一项。
  // 原来合成一类，引导句直接断言「你资料里写过……是你会但没写上去」——
  // 而那个前提**从没被验证过**（`inResume` 只查简历）。对一个资料里也没有的词，
  // 那句话就成了「你会，去写上」，而他并不会：往简历里加一条兜不住的东西，
  // 正是 `03-writing-style.md` 铁律 3 要挡的事。
  const notWritten = ss.asks.filter((a) => a.inResume === false && a.inProfile);
  const notHad = ss.asks.filter(
    (a) => a.inResume === false && a.inProfile === false);

  return (
    <div className="rread">
      {/* ---- 1. 主场 ---- */}
      <div className="rread-sec">
        {/* **不叫「主场」。** 这一格的判据只有**行业经验 ≥60** 一维，
            专业能力那一维压根没看。而「主场」在这个仓库的另一处
            （`gap_split` 的四格、`/job-upskill`、`query_yield` 的「其中主场」）
            指的是**两样都对得上**。同一个词两个定义，而且两边的行业阈值都是 60，
            看着更像该一致。
            实测 2026-08-22：这里叫「主场」的 107 个岗里，**66 个（61%）
            专业能力其实不够**——名过其实 3.7 倍。叫它量到的那件事就行。 */}
        <div className="kicker">行业对口的岗</div>
        <p className="rread-lead">
          {/* **不能只说「评过的」。** 页面顶部漏斗写着「打过分：2626 个」，
              而这里是 687 —— 同一个词、同一页、差四倍，读的人只会以为
              哪个坏了。两边数的其实是不同的东西：漏斗那个含**被粗筛和
              硬性条件挡掉**的（实测 1930 个：粗筛跳过 708 + 硬性条件没过 979），
              它们没走到打分那一步。用词要把这件事说出来。 */}
          有完整评分的 <b>{ss.total}</b>
          {" 个岗里（含你点过「不投」的——市场是什么样不因为你拒绝而改变），"}
          <b className="lg-up">{ss.count}</b>
          {" 个的行业经验你是熟的（评分 ≥60，即同一个领域做过、"}
          {"或相邻领域业务语言能迁移）。"}
          其余多数不是你亏了——它们要的专业能力通常也不是你的。
        </p>
        <div className="rread-inds">
          {ss.industries.map((i) => (
            <span className="rread-ind" key={i.name}>
              {i.name}
              <em>{i.n}</em>
            </span>
          ))}
        </div>
        <p className="rread-note">
          专业能力中位数 <b>{data.medianStack}</b> · 行业经验中位数{" "}
          <b className="lg-down">{data.medianDomain}</b>
          {"——差距在后者，而它主要靠"}<b>选对岗</b>{"解决，不是靠补课。"}
        </p>
        {/* **「选对岗」是库存指令，就得说库存还剩多少。** 上面那个 107 把已投的、
            点掉的、下线的都算在里面（它回答的是「市场有多大一块对得上你」，
            放在这一节里没错）。可读者会把它当成「还有一百来个可挑」——
            实测同一时刻还能投的只有 49 个。少了就该去补货，而补货得给出命令
            （面板通例：每处引导都写出命令）。 */}
        {typeof ss.open === "number" && (
          <p className="rread-open" data-thin={ss.open < ss.count / 2 || undefined}>
            {"这 "}<b>{ss.count}</b>{" 个里，现在还能投的是 "}
            <b className="lg-up">{ss.open}</b>
            {`——其余的你投过了、点掉了或者已下线。挑着投很快会见底，`}
            {"要补这一类的货，改搜索词比多抓一轮管用："}
            <Cmd>/job-setup --section search</Cmd>
          </p>
        )}
      </div>

      {/* ---- 2. 挡你的 ---- */}
      <div className="rread-sec">
        <div className="kicker">什么在挡你</div>
        {blockers.map((b) => (
          <div className="rread-block" key={b.name} data-tone={b.tone}>
            <span className="rread-bn">
              {b.name}
              <em>
                {b.n}
                {b.of ? `/${b.of}` : ""}
              </em>
            </span>
            <span className="rread-bnote">{b.note}</span>
          </div>
        ))}
      </div>

      {/* ---- 3. 简历要补什么 ---- */}
      <div className="rread-sec">
        <div className="kicker">
          简历要补什么
          {/* 边界必须说出来：字面比对看不到「你的说法 ≠ 市场的说法」那类 */}
          <Tooltip title={`词来自你自己资料里的「技能」一节，拿去在行业对口的岗的 JD 正文里数，再和简历比对。所以它只回答「你写过的这些能力，市场提了几次、简历写没写」。它看不到两类：一是你的说法和 JD 的说法不一样（你写「AI 编码工具」、对方写「大模型应用工程师」）；二是市场反复要而你根本没接触过的。那两类要跑 ${formatCommand("/job-upskill")}，它有模型能做语义比对。`}>
            <span className="rread-q">怎么算的</span>
          </Tooltip>
        </div>

        {!ss.resumeChecked ? (
          <p className="rread-note">
            没找到 <code>resume/main.typ</code>
            {"，这一块只统计了行业对口的岗要什么，没跟简历比对。" +
             "第一次投某个岗时会顺手生成它："}
            <Cmd>/job-apply &lt;职位链接&gt;</Cmd>
          </p>
        ) : notWritten.length === 0 && notHad.length === 0 ? (
          <p className="rread-note">行业对口的岗反复要的词，简历里都提到了。</p>
        ) : (
          <>
            {notWritten.length > 0 && (
              <>
                <p className="rread-lead">
                  你资料里写过、行业对口的岗也在要、而简历里<b className="lg-down">没出现</b>
                  {"的——这些"}<b>不是学习任务</b>
                  {"，是你会但没写上去，改简历就能补："}
                </p>
                <div className="rread-gaps">
                  {notWritten.map((a) => (
                    <span className="rread-gap" key={a.term}>
                      {a.term}
                      <em>{askNote(a)}</em>
                    </span>
                  ))}
                </div>
              </>
            )}
            {/* **这一类不许说「改简历就能补」。** 资料里也没有，说明他真没这一项；
                建议他写进简历就是让他去写一条兜不住的东西
                （`03-writing-style.md` 铁律 3）。这里给的是**取舍**：
                要么去补这项能力，要么认了、别投反复要它的那批岗。 */}
            {notHad.length > 0 && (
              <>
                <p className="rread-lead">
                  行业对口的岗在要、而你<b className="lg-down">资料和简历里都没有</b>
                  {"的——这些"}<b>别直接写进简历</b>
                  {"，资料里没有就是真没有："}
                </p>
                <div className="rread-gaps">
                  {notHad.map((a) => (
                    <span className="rread-gap" data-hard key={a.term}>
                      {a.term}
                      <em>{askNote(a)}</em>
                    </span>
                  ))}
                </div>
                <p className="rread-note">
                  {"确实会、只是资料里漏了 → 跑 "}
                  <Cmd>/job-setup --section skills</Cmd>
                  {" 补进资料，再改简历；真没有 → 跑 "}
                  <Cmd>/job-upskill</Cmd>
                  {" 看值不值得补，或者认了、别投反复要它的那批岗。"}
                </p>
              </>
            )}
            {/* 原来到这里就断了：说了「改简历就能补」，却不说改完怎么验。
                /job-resume 会逐条比对简历与资料，报数字对不对、结构合不合规。 */}
            <p className="rread-note">
              改完 <code>resume/main.typ</code> 跑一次审核，它会逐条比对数字与经历：
              <Cmd>/job-resume</Cmd>
            </p>
          </>
        )}

        {ss.asks.some((a) => a.inResume) && (
          <p className="rread-note">
            已经写到的：
            {ss.asks
              .filter((a) => a.inResume)
              .map((a) => a.term)
              .join("、")}
          </p>
        )}
      </div>
    </div>
  );
}
