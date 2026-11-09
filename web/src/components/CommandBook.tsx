import { Radio } from "antd";
import { Cmd } from "./Cmd";
import type { CommandGroup, CommandItem } from "../types";
import { useCodeTool } from "../context/CodeToolContext";

/**
 * 全部命令——图形界面里的那份「帮助」
 *
 * ## 为什么必须有这一块
 *
 * 这个仓库的判断力全在命令行侧：找职位要浏览器扩展、评估与写材料要模型、
 * 都走用户自己的订阅。面板只负责**看得见**。所以面板不说出命令，两边就是断的
 * ——用户看着一页数据，不知道自己还能做什么。
 *
 * 实测面板只露过 18 个工作流里的 7 个。`/job-outcome`（投完记录结果，投递之后最该做的
 * 一件事）、`/job-offer`（拿到 offer 谈薪与背调红线）、`/job-upskill` 连提都没提过。
 * 它们各自有完整的工作流文件、有入口壳、有测试——唯独在界面上查无此人。
 *
 * ## 光有命令名还不够
 *
 * 第二版只印了「命令 + 一句话」。可这些命令**大多能带参数**，而参数才是它们真正
 * 好用的地方：`/job-apply --top 20` 能一次备齐 20 个岗的材料、`/job-outcome followup`
 * 直接告诉你该催哪几个、`/job-reset profile` 只清资料而不动投递记录。这些在
 * 工作流文件里都写着，用户却只有把它们挨个读一遍才知道。所以每条命令都带上
 * **真实支持**的敲法举例——照抄就能跑，不必先读文档。
 *
 * ## 这张表从哪来
 *
 * `workflows/INDEX.md` 的「工作流索引」，由 `build_dashboard.parse_commands()` 解析，
 * 说明取「任务」列、举例取第三列（按 ` · ` 分条）。
 * **不在这里写死**：写死必然跟索引飘——加一个工作流、改一句说明，面板还停在
 * 上一版，而用户没有任何理由怀疑面板漏了东西。
 *
 * 分组（开始之前 / 找岗 / 投一个岗 / 投出去之后 / …）是展示层的编排，跟着流程走
 * 而不是字母序。成员完整性与举例的真实性由 `tests/test_command_reference.py` 兜底。
 */

/** `/job-setup --section search（只补搜索词）` → 命令本体 + 括号里的补充。 */
function splitNote(ex: string): { text: string; note: string } {
  const m = ex.match(/^(.*?)（(.+)）$/);
  return m ? { text: m[1].trim(), note: m[2] } : { text: ex, note: "" };
}

function Examples({ it }: { it: CommandItem }) {
  // 第一条就是上面那个命令片，重复印一遍只是噪音。
  const extra = (it.examples ?? []).slice(1);
  if (!extra.length) return null;
  return (
    <div className="cmdbook-ex">
      {extra.map((raw) => {
        const { text, note } = splitNote(raw);
        return (
          <span className="cmdbook-ex-i" key={raw}>
            {/* 有斜杠的才是命令；「投这个岗」这种是直接说的话，做成可复制的
                命令片会骗人——它不是敲进去的东西。 */}
            {text.startsWith("/") ? <Cmd>{text}</Cmd>
              : <span className="cmdbook-say">直接说{text}也行</span>}
            {note && <span className="cmdbook-note">{note}</span>}
          </span>
        );
      })}
    </div>
  );
}

/** `spineOnly`：只出「日常就这三条」那一块，不出下面那张全表。
 *
 *  **给还没建过档的人用。** 整张表摊在他面前时，能敲的只有 `/job-setup`
 *  和 `/job-user` 两条 —— 实测 2026-08-24（拿一份空快照渲染），首屏从
 *  220px 一直到底部全是那张表，而他此刻要做的事只有一件。
 *  全集不删也不藏：建完档之后从「能敲哪些命令」那颗按钮进，一条不少。 */
export function CommandBook(
  { groups, spineOnly = false }: { groups: CommandGroup[]; spineOnly?: boolean },
) {
  const { commandMode, setCommandMode } = useCodeTool();

  return (
    <div className="cmdbook">
      <div className="cmdbook-bar">
        <span className="cmdbar-label">{"命令调用方式："}</span>
        <Radio.Group
          size="small"
          value={commandMode}
          onChange={(e) => setCommandMode(e.target.value)}
          buttonStyle="solid"
        >
          <Radio.Button value="auto">自动</Radio.Button>
          <Radio.Button value="dollar">$ 技能</Radio.Button>
          <Radio.Button value="bare">自然语言</Radio.Button>
          <Radio.Button value="slash">{"斜杠模式"}</Radio.Button>
        </Radio.Group>
        <span className="cmdbar-note">
          {{ auto: "按当前 AI 工具自动选择引用形式", dollar: "以 $ 引用技能，适用于 Codex 各端", slash: "通过客户端的 / 菜单选择技能", bare: "明确指定工作流文件，请助手读取并执行" }[commandMode]}
        </span>
      </div>
      {/* 这里原来是两段开场白，第一段还是**假的**：「这一页只负责让你看得见。真正
          干活的命令都在命令行里敲」——「我投了 / 约面了 / 不投」点这一页就落盘了。
          上面那个折叠标题早就按模式分了真假话（`App.tsx` 有整段注释讲这事），
          修的人没往下看两行，同一句假话在正文里又活了一遍。
          `test_web_copy` 的 `STATIC_ONLY_PHRASES` 本该拦住它，可词表里是
          「干活都在命令行」，这里写的是「干活**的命令**都在命令行」——差两个字，绕过去了。
          所以正文干脆不再复述分工：标题已经说了，而且它是按模式说的。

          剩下的合成一段。这是张**用来查的表**，不是读物；把「带 <…> 要自己填」
          从页脚提到前面，因为那是看第一行时就会撞上的问题，写在 5000px 之后没用。 */}
      <p className="cmdbook-lead">
        {"点一下命令就复制。带 "}<code>&lt;…&gt;</code>{" 的要自己填："}
        <code>&lt;职位链接&gt;</code>{" 贴招聘网站上那个岗的网址，"}
        <code>&lt;整段职位描述&gt;</code>{" 是没链接时把 JD 全文粘进去，"}
        <code>&lt;公司&gt;</code>
        {" 写简称就行。命令后面跟的那几个是它还能怎么敲——不带参数直接跑也行，" +
         "带参数只是为了少问你几轮。命令跑完，刷新本页就更新了。"}
      </p>

      {/* 其余那些平铺，新用户不知道从哪下手。**先把日常那三条单独摆出来**——
          剩下的都是「碰到那件事才用」，不该和它们平权排在一起。
          文案与 `AGENTS.md`「一次跑到头：只有三条命令」同源，脊梁是
          `/job-setup` → `/job-auto` →（你自己发）→ `/job-outcome`。改一处要改两处，
          `test_the_spine_is_three_commands` 现在连这块 .tsx 一起盯（此前只盯三份 md，
          于是这里悄悄停在「两条」、漏了 `/job-outcome`，而催进度/备面/谈薪全从那一笔长出来）。 */}
      <div className="cmdbook-spine">
        <div className="kicker">日常就这三条</div>
        <div className="cmdbook-rows">
          <div className="cmdbook-row">
            <Cmd>/job-setup</Cmd>
            <span className="cmdbook-does">
              填一次你的经历、期望薪资、硬性条件。分四轮问，答完第一轮就能往下走
            </span>
          </div>
          <div className="cmdbook-row">
            <Cmd>/job-auto</Cmd>
            <span className="cmdbook-does">
              抓岗 → 打分 → 给能投的出话术，一直跑到挖不动为止，中途不用盯着
            </span>
          </div>
          <div className="cmdbook-row">
            <span className="cmdbook-say">然后你自己去招聘网站把材料发出去</span>
            <span className="cmdbook-does">
              {/* 这一格说的是「发完之后那一下」，对应的正是总览页 ""→applied
                  那颗「我投了」（`tools/tracker.py` 的 `NEXT` 表）。下面那行
                  /job-outcome 讲的是再往后的约面/挂了/没下文，两回事，别混。 */}
              全流程唯一要人的一步。发完点这一页那个岗上的「我投了」，这一笔就记上了
            </span>
          </div>
          <div className="cmdbook-row">
            <Cmd>/job-outcome</Cmd>
            <span className="cmdbook-does">
              {/* 单行写完，别让文本跨两行断在中文里——JSX 会把换行折成一个
                  空格插进句子中间（`test_no_space_between_cjk_in_jsx_text`
                  盯着这个坑）。另外「我投了」只对应总览页 ""→applied 那个按钮
                  （见 `tools/tracker.py` 的 `NEXT` 表）；这一行说的是已投之后的
                  结果，对应岗位那一行此时按钮已经是「约面了/挂了/没下文」，
                  不该再说「我投了」——那句名字说错了。 */}
              约面了 / 挂了 / 没下文这几个状态，点这一页对应岗位那一行的按钮也行；要写清经过（归档、该催谁、面试复盘）才用这条命令
            </span>
          </div>
        </div>
      </div>

      {!spineOnly && groups.map((g) => (
        <div className="cmdbook-g" key={g.group}>
          <div className="kicker">{g.group}</div>
          <div className="cmdbook-rows">
            {g.items.map((it) => (
              <div className="cmdbook-row" key={it.name}>
                <Cmd>{it.cmd}</Cmd>
                <span className="cmdbook-does">{it.does}</span>
                {/* 「什么都不给会怎样」——敲裸命令之前最想知道的一件事。
                    索引表没写第四列的就不渲染，不要编一个出来。 */}
                {it.bare && (
                  <div className="cmdbook-bare">
                    <span className="cmdbook-bare-k">不填参数</span>
                    <span>{it.bare}</span>
                  </div>
                )}
                <Examples it={it} />
              </div>
            ))}
          </div>
        </div>
      ))}

      <p className="cmdbook-foot">
        {"不确定现在该做哪一步：看本页顶上那条「下一步」，或者跑一次自检——" +
         "它也只给一条，且不需要联网、不改任何东西："}
        <Cmd>python tools/doctor.py</Cmd>
      </p>
    </div>
  );
}
