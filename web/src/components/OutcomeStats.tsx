import { Cmd } from "./Cmd";
import type { OutcomeStats } from "../types";

/**
 * 投出去之后怎么样了 —— 统计块
 *
 * ## 为什么这一块要存在
 *
 * 这一页原来只回答「还能投谁」。而投了几十个之后，真正该问的问题变了：
 * **我投的这些到底有没有用？** 回复率多少、卡在哪一环、哪一档分数的岗才有人理。
 * 没有这块，用户只能凭印象判断——而印象在「投了几十个、一个回音都没有」这种状态下
 * 特别容易变成「是不是我哪里做错了」，其实可能只是还没到时候。
 *
 * ## 「大概率没戏」是算出来的，不是用户填的
 *
 * 用户 2026-08-13 原话：「很多是没反馈也就不会填」。这句话点出了整个设计的关键：
 * **沉默不产生事件**——没有邮件、没有电话、没有状态变化。要求用户手动记
 * 「这个没回我」，等于让他为「什么都没发生」每周点几十次，而那正是他不会做的事。
 *
 * 所以后端按投递日期算：超过 `silentDays` 天没任何动静，就归到「大概率没戏」。
 * 它**不改任何状态**，只影响这里怎么归类；用户随时可以自己点「没下文」结案。
 *
 * ## 「按分数段的回复率」是这块里最有用的一行
 *
 * 它回答的是**评分准不准**——如果 60 分以上和 50 分以下的回复率一样，
 * 那这套打分就没在起作用，该回去调 `04-job-evaluation.md` 的权重。
 * 这是整个仓库唯一能自我校准的地方。
 *
 * 数全部由 `export_web_data.outcome_stats` 算好送来，**前端不自己算**——
 * 两处各算一份必然飘，这一页已经栽过好几次（材料就绪、已投递、下一步都飘过）。
 */
/**
 * 一个「比率」怎么说出来。**`null` 不是 0%。**
 *
 * 一个回音都没有、而多数投递还在等待窗口内时，后端给 `null`
 * （判据在 `export_web_data.outcome_stats`，前端不自己判）。那时候印一个
 * 大号「0%」，读出来是「市场把你全拒了」，而实际是还没到该回的时候。
 *
 * **抽出来是因为这条规矩已经被抄到三处**（本文件两处 + `App.tsx` 折叠标题），
 * 而那第三处刚刚才从 `?? 0` 改过来——收起面板时标题印「有回音 0%」、
 * 展开后的大格子印「还没有」，同一份数据两个说法。下一个新增的比率
 * （`waitingMedian` 在排队）不该再犯一次。
 */
export function sayRate(v: number | null): string {
  return v === null ? "还没有" : `${v}%`;
}

export function OutcomeStatsPanel({ s }: { s: OutcomeStats }) {
  if (!s.total) return null;
  const pct = (n: number, d: number) => (d ? Math.round((n / d) * 100) : 0);

  return (
    <div className="ostats">
      <div className="ostats-top">
        <div className="ostats-big">
          <b className="mono-label">{s.total}</b>
          <span>投出去</span>
        </div>
        {/* 判据在 `sayRate`（上面）。下面那张图早就为同一件事让过路，
            头条这里一直没有。 */}
        <div className="ostats-big">
          {/* **中文不进 `mono-label`**：那个类带字距，只给数字用；
              中文套上去会被拉成散字（AGENTS.md「等宽只留给纯数字」）。
              所以两支各用各的标签。 */}
          {s.repliedRate === null
            ? <b>{sayRate(s.repliedRate)}</b>
            : <b className="mono-label">{sayRate(s.repliedRate)}</b>}
          <span>有回音</span>
        </div>
        <div className="ostats-big">
          {s.interviewRate === null
            ? <b>{sayRate(s.interviewRate)}</b>
            : <b className="mono-label">{sayRate(s.interviewRate)}</b>}
          <span>约到面试</span>
        </div>
        {s.waitingMedian !== null && (
          <div className="ostats-big">
            <b className="mono-label">{s.waitingMedian}</b>
            {/* **必须点明是「还在等」那一小撮的中位。** 只写「已等的中位天数」
                会和下面的「大概率没戏 121」打架：那 121 个都已等过静默线，
                中位却写 3 天，读者只会怀疑哪个数是真的。这个 3 只算还在等的。 */}
            <span
              title="只算「还在等」的那几个岗，不含已经归入「大概率没戏」的"
            >
              还在等的中位天数
            </span>
          </div>
        )}
      </div>

      <div className="ostats-bar">
        {s.buckets.map((b) => (
          <span key={b.k} className={`ob ob-${b.k}`}
                style={{ flexGrow: b.n }} title={`${b.k} ${b.n} 个`}>
            <i>{b.k}</i>
            <b className="mono-label">{b.n}</b>
          </span>
        ))}
      </div>
      <p className="ostats-note">
        {"「大概率没戏」是按投递日期算的：投出去超过 "}
        <b className="mono-label">{s.silentDays}</b>
        {" 天还没任何动静就归到这里，不用你去点。真确认没了想结案，" +
         "展开那个岗点「没下文」。"}
      </p>
      {/* **上面那句只说了进去的路。** 点完「没下文」那一行就没有按钮了
          （`tracker.NEXT` 里它没有出口，那是有意的），而这个状态是**按天数
          判出来的、不是雇主说的**——国内拒信多是同一天群发的模板，隔几天
          某个岗位重启或另一个部门单独捞人；沉默几周后 HR 回信也常见。
          不说一句，他会以为点下去就是终局。

          **只在这里说一次，不逐行说。** 逐行加会长出几十条一模一样的话，
          而那正是 `test_closed_cases_have_no_next_step` 那条守卫防的
          「硬凑一条下一步让人做无用功」——试过逐行加，撤回了（2026-08-23）。

          **也不给按钮。** 拒信之后来一封邀约有三种读法（同一条线 / 两次不同
          投递 / 看不清），`job-outcome.md` Step 2 自己写着「别替他判第一种」；
          按钮会把它塌成第一种。而且那条路上 `undo` 会连带清掉拒绝原因。 */}
      <p className="ostats-note">
        {"「挂了」和「没下文」都不是终局：拒信常是群发的，岗位重启、别的部门" +
         "捞人、HR 隔很久回信都真会发生。后来有动静回来记一笔就行——记的时候" +
         "会先问清是不是同一次投递，再决定改不改那一行。"}
        <Cmd>/job-outcome &lt;公司&gt;</Cmd>
      </p>

      {/* **一个回音都没有时不画这张图。**
          这一块的判据是「各档回复率如果差不多，说明这套打分没帮上忙」——
          而 0 个回音的时候各档**恰好都是 0%**，图上两条空轨加两个 0%，
          读出来正是「打分没起作用」。那是反的：0% 对 0% 不是打分失效的证据，
          是还没有人回。实测（2026-08-18）：82 个投出去、0 回音，页面就是这么画的
          ——而刚开始投的人全都处在这个状态，等于人人先被泼一盆假冷水。
          没数据时给方向，不给一张读得出错误结论的图。 */}
      {s.byBand.length > 0 && s.byBand.some((b) => b.replied > 0) ? (
        <div className="ostats-band">
          <div className="kicker">哪一档分数的岗真有人理</div>
          <table>
            <tbody>
              {s.byBand.map((b) => (
                <tr key={b.band}>
                  <th>{b.band}</th>
                  <td className="mono-label">{b.sent}</td>
                  <td>
                    <span className="ob-track">
                      <i style={{ width: `${pct(b.replied, b.sent)}%` }} />
                    </span>
                  </td>
                  <td className="mono-label">{pct(b.replied, b.sent)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* 这一行是给判断用的，不是装饰：分数分不出回复率，就说明打分没起作用。 */}
          {/* 整句一行：JSX 里两个汉字之间的换行会被折成空格，中文里那就是错字。
              只有标签边界是安全的断点。 */}
          <p className="ostats-note">
            <span>各档回复率如果差不多，说明这套打分没帮上忙——那就该回去改它看的那些东西，而不是继续按它排序。</span>
          </p>
        </div>
      ) : s.byBand.length > 0 ? (
        <div className="ostats-band">
          <div className="kicker">哪一档分数的岗真有人理</div>
          <p className="ostats-note">
            <span>
              {`还一个回音都没有，这一栏得等有人回了才有内容。多数回音在投出去 ${s.silentDays} 天内`}
              {"出现——到那时这里会告诉你：分高的岗是不是真的更容易有人理。是，说明这套打分帮上了忙；不是，就说明它看的东西和你真实收到的回复对不上，得回去改它看的那些东西。"}
            </span>
          </p>
        </div>
      ) : null}

      {/* ── 有多少简历根本没到用人方手里 ──
          国内特有的一条：猎聘这类平台上很大一部分岗是**猎头代招**，
          简历投过去先进猎头的库，由他决定推不推、什么时候推；岗位可能早就关了，
          也可能只是在攒简历。**同一份简历，直招三天有回音，猎头那边可能永远没有**
          —— 这是「投了没回音」最常见的一种，而且怪不到简历头上。

          只报个数不拆回复率：两边都是 0% 的表说不出任何东西，
          而「一半的简历没到用人方手里」这个事实本身就是答案。
          过半才说 —— 少数几个猎头岗是正常的，不值得单开一行。 */}
      {s.viaAgency != null && s.total > 0 && s.viaAgency * 2 > s.total && (
        <div className="ostats-band">
          <div className="kicker">有多少没到用人方手里</div>
          <p className="ostats-note">
            <span>
              {`投出去的 ${s.total} 个里，${s.viaAgency} 个是猎头代招——简历先进猎头的库，由他决定推不推、什么时候推，岗位也可能早就关了。这一半慢或者没回音，多半不是简历的问题。`}
              {/* **这句话只说了一半，而缺的那一半会把人带反。**
                  「猎头占了一半，不怪简历」→ 读者合理地推出「所以简历没问题，
                  多投直招就行」。可如果直招那批**自己也是 0 回音**，
                  这个推论就是错的，而它正是这一栏原来的结尾
                  （「想快一点，就多找企业直招的岗」）在鼓励的事。
                  实测活动用户 2026-08-22：直招 22 个、0 回音——他已经走过这条路了。
                  同一时刻「下一步」那一行说的是「回头审一遍简历」，
                  两处给的暗示相反。
                  判据在 `tools/export_web_data.py` 的 `outcome_stats`，措辞同 `tracker`。 */}
              {/* `?? 20` 那个兜底值就是刚收拢掉的抄件本身——门槛缺了就
                  **不下这个结论**，而不是拿一个可能已经过时的数硬判
                  （同 `build_dashboard` 的「裸 import，不给兜底」）。 */}
              {s.directReplied === 0 && s.noReplyAlarm != null
                && (s.directDecided ?? 0) >= s.noReplyAlarm
                ? <b>{`但企业直招那 ${s.directDecided} 个也是一个回音都没有——那批才说明问题，别把它一起算进猎头这笔账里。`}</b>
                : (s.directDecided ?? 0) > 0
                  ? `想快一点就多找企业直招的岗：那批已经有 ${s.directDecided} 个到了该有结论的时候，${s.directReplied} 个有回音。`
                  : "想快一点，就多找企业直招的岗。"}
            </span>
          </p>
        </div>
      )}

      {/* ── 不是简历不行，是投的地方不对 ──
          上面两条讲的是**怎么到达**（一半没到用人方手里、三个网站都是 0），
          这一条讲的是**投给了谁**。两者指向的动作完全不同，而这一条此前
          整个不在面板上 —— 它只活在 `gap_split.py --applied` 里，
          由 `/job-upskill` 调用，而那条命令他一次都没跑过。

          实测 2026-08-22：投出去的 78 份可回读评估里，49 个（63%）是
          「专业能力够、行业经验对不上」，主场只有 17 个。
          对「投了 85 个 0 回音」来说，这是目前最直接的一条解释，
          而且它给的动作最具体：**下一批往主场那个方向投**。

          过半才说 —— 少数几个跨行业投递是正常的试探，不值得单开一行。 */}
      {s.appliedFit && s.appliedFit.pick * 2 > s.appliedFit.total && (
        <div className="ostats-band">
          <div className="kicker">投的地方对不对</div>
          <p className="ostats-note">
            <span>
              {/* **分母要说清是哪一批。** 这四格只数「评分拆得出两笔分」的岗，
                  而句子原来说「投出去的 78 个里」—— 投出去的其实是 85 个，
                  另外 7 个拆不出分（早期评估用的是旧口径）。差得不多，
                  但这一栏产出的正是「不是简历写得不好，是投的地方不对」那个结论，
                  分母是它的全部依据。同一族：本仓库反复修的「把子集说成全体」。 */}
              {`投出去的 ${s.appliedFit.total} 个里（评分拆得出来的那些`
               + (s.total > s.appliedFit.total
                  ? `，另有 ${s.total - s.appliedFit.total} 个拆不出、没算` : "")
               + `），${s.appliedFit.pick} 个是「你的专业能力够、但这个岗要的行业经验你没做过」——不是简历写得不好，是投的地方不对。真正对得上的只有 ${s.appliedFit.home} 个。`}
            </span>
            {/* **「往主场投」得先问一句：手上挑得出来吗。**
                实测 2026-08-22：还没投的 227 个可投岗里主场只有 11 个，
                分数 54-59，一个都没进「值得投」。那句建议真正的意思是
                **去改搜索词多抓这类**，不是从现有名单里挑 ——
                一个是今晚能做的事，一个是明天才有的结果，别混成一句话。
                手上够挑（主场过一成）时才说「从现有的里挑」。 */}
            {s.appliedFit.open && s.appliedFit.open.home * 10 < s.appliedFit.open.total ? (
              <span>
                {/* 同上：这个数也是「拆得出分的那些」。实测 231 个还能投，
                    其中 227 个拆得出 —— 不说清楚，读的人会拿它和这一页
                    别处的「还能投 231」对不上。 */}
                {`而手上还没投的 ${s.appliedFit.open.total} 个里（同样只算拆得出分的），这类只有 ${s.appliedFit.open.home} 个——不够挑的。想多抓这类，先跑 `}
                <Cmd>/job-setup --section search</Cmd>
                {" 改搜索词，改完再跑 "}
                <Cmd>/job-scrape</Cmd>
              </span>
            ) : (
              <span>
                {`手上还没投的里面，这类有 ${s.appliedFit.open?.home ?? "一些"} 个——下一批先发它们，比再改一版简历管用。`}
              </span>
            )}
            <span>
              {"想看这四格具体是哪些岗，跑 "}
              <Cmd>/job-upskill --applied</Cmd>
            </span>
          </p>
        </div>
      )}

      {/* ── 换一种到达方式 ──
          这是诊断链的最后一环，前两环在上面：一半是猎头代招（没到用人方手里）、
          三个网站都是 0（不是选哪个网站的问题）。那剩下的就不是「再投一次」，
          而是**换一种到达方式**。

          内推是这些岗唯一不靠海投的一条路（**回复率谁也没量过**：一条内推记录都
          没有，`06-outreach-templates.md` 对「哪条路回复率高」的答案就是「没数据」）
          —— 而这个仓库此前
          **一次都没把它当作建议说过**（只在两份报表文档里作为 `channel` 的
          一个可能取值出现）。

          落到具体的家上才有用：猎头岗和匿名岗没有人可找，只有具名的直招公司
          才谈得上找人引荐。所以给的是那个数和几个例子，不是一句「去找内推」。 */}
      {(s.directCos ?? 0) >= 3 && s.repliedRate === 0 && (
        <div className="ostats-band">
          <div className="kicker">还有一条没试过的路</div>
          <p className="ostats-note">
            <span>
              {`投过的公司里有 ${s.directCos} 家是具名的企业直招（${(s.directCosSample ?? []).join("、")}…）——这些是找得到人的。国内内推的回复率比网申高一个量级，而你这 ${s.total} 个投递里一次都没走过这条路。与其再投一个，不如在这 ${s.directCos} 家里找一个能说上话的人。`}
            </span>
          </p>
        </div>
      )}

      {/* ── 力气花在哪个网站，那个网站回不回 ──
          分数段回答「该投多高分的岗」，渠道回答「该在哪个网站花力气」——
          国内求职里后者往往更要紧：同一份简历在不同平台的回复率能差好几倍。
          这一栏此前不存在，因为台账的 `channel` 列**从来没人写过**；
          现在它从职位链接推得出来（`tracker.channel_of`）。

          **一个渠道时不显示**：那时这张表只有一行，说不出任何对比，
          而它要回答的问题就是「哪个更值得」。 */}
      {s.byChannel && s.byChannel.length > 1 && (
        <div className="ostats-band">
          <div className="kicker">投在哪个网站，那边回不回</div>
          <table>
            <tbody>
              {s.byChannel.map((c) => (
                <tr key={c.channel}>
                  <th>{c.channel}</th>
                  <td className="mono-label">{c.sent}</td>
                  <td>
                    <span className="ob-track">
                      <i style={{ width: `${pct(c.replied, c.sent)}%` }} />
                    </span>
                  </td>
                  <td className="mono-label">{pct(c.replied, c.sent)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="ostats-note">
            {/* **这一段原来自己列了两个可能，然后挑了没有数据的那个。**
                原话：「问题多半不在选哪个网站，而在简历或岗位匹配——先审简历。」
                而上面那栏（`appliedFit`）手上就有数：投出去的 63% 是
                「专业能力够、行业经验对不上」—— 它刚说完「不是简历写得不好」，
                这一段紧接着说「先审简历」。**两段隔着不到一屏，结论相反。**
                有数据的那一边说了算：能拆出来时就指过去，拆不出来才回到两条并列。 */}
            <span>
              {!s.byChannel.every((c) => c.replied === 0)
                ? "哪个高就往哪个多投一点。差得远时，别在回复率低的那个上耗时间。"
                : s.appliedFit && s.appliedFit.pick * 2 > s.appliedFit.total
                  ? "每个网站都是 0，那问题多半不在选哪个网站——上面那栏已经拆出来了：多数是投的岗行业经验对不上，先按那条走。"
                  : "每个网站都是 0，那问题多半不在选哪个网站，而在简历或岗位匹配这两样上。"}
            </span>
            {/* **这两栏不能直接横着比。** 上面头条已经说过「猎头那批没动静
                说明不了你简历的事」，而各渠道的猎头占比差得极远（实测
                2026-08-23：猎聘 43/66，BOSS 直聘 1/16）—— 不说这一句，
                读者会把「猎聘 0%」当成猎聘不行，而那 66 个里三分之二
                根本没到用人方手里。判据同导出侧 `by_channel` 那段注释。

                **只在真的差得远时才说**：占比都差不多时这句话是噪音，
                而且它每多出现一次，头条那句就被稀释一次。 */}
            {(() => {
              const withA = s.byChannel!.filter((c) => (c.agency ?? 0) > 0);
              if (!withA.length || s.byChannel!.length < 2) return null;
              const share = (c: { sent: number; agency?: number }) =>
                c.sent ? (c.agency ?? 0) / c.sent : 0;
              const hi = [...s.byChannel!].sort((a, b) => share(b) - share(a))[0];
              const lo = [...s.byChannel!].sort((a, b) => share(a) - share(b))[0];
              if (share(hi) - share(lo) < 0.3) return null;
              return (
                <span>
                  {`但这几栏不能直接比：${hi.channel}那 ${hi.sent} 个里有 `
                    + `${hi.agency ?? 0} 个是猎头代招，${lo.channel}只有 `
                    + `${lo.agency ?? 0} 个。简历进猎头的库，推不推由他定，`
                    + `那批没动静说明不了这个网站行不行。`}
                </span>
              );
            })()}
          </p>
        </div>
      )}

      <div className="ostats-band">
        <div className="kicker">被拒的原因</div>
        {s.reasons.length > 0 ? (
          <div className="ostats-reasons">
            {s.reasons.map((r) => (
              <span key={r.k}>{r.k}<b className="mono-label">{r.n}</b></span>
            ))}
          </div>
        ) : (
          <p className="ostats-note">
            还没有记过原因。挂了的岗展开之后，点「挂了」下面那排就能记一下——
            <b>不填也没关系</b>，多数拒信本来就不说理由。
          </p>
        )}
      </div>
    </div>
  );
}
