import type { Verdict } from "./theme/tokens";

/**
 * ## 内部词 vs 屏幕上的词
 *
 * `workflows/` 里的框架词（硬门、能力边界、四维）是**给 AI 看的内部词汇**，不改；
 * 但屏幕上给求职者看的一律用大白话——「硬门」→「硬性条件」、「台账」→「投递记录」、
 * 「能力边界缺口」→「经历对不上的地方」。改文案时只改显示层，别去动 workflows。
 *
 * ## 四态，不是开关
 *
 * 硬性条件是**四态**，不是二态开关——这是整个项目最核心的一条规则：
 * 「还没查到」既不算通过也不算不合格，而且**永远不能被折叠成通过**。
 * 所以类型层就把它列成一等成员，不用 `boolean | null` 之类会诱人写 `?? false` 的形状。
 */
export type GateState = "pass" | "fail" | "unknown" | "na";

/**
 * 「不满足硬性条件」这个判词要在两处比较（筛名单、筛搁置区），所以**只在这里定义**，
 * 写死两遍迟早会飘。
 */
export const GATE_FAIL = "不满足硬性条件";

/**
 * 七道硬门里**根本没那一行**的那几道（正规名，由导出器按 `_cli.GATES` 归一化）。
 *
 * 「没判」和「表里没有那行」在成品上长得一模一样，所以必须单独带过来：
 * 2026-08-20 实测 236 个岗印着「这些条件都核对过了」，其中 60 个实际有 2-3 道
 * 门没查。判据只在 Python 那一份，TS 侧不重写——重写就会飘。
 */
export type UnjudgedGates = string[];

export interface Gate {
  name: string;
  state: GateState;
  /** 判定依据。unknown 时写"为什么还没查到"，assumed 时写"要你确认什么"。 */
  why: string;
  /**
   * 判定基于 profile 里未经用户确认的假设值 —— 不得渲染成静默 PASS。
   * 这条来自 apply.md 的「硬门假设值规则」。
   */
  assumed?: boolean;
  /**
   * 这一行的门名**不在七道正规硬门里**（判据在 `_cli.gate_of`，别在 TS 里
   * 再写一份词表）。`04-job-evaluation.md` 第一步：「自造的门名和没判一样」。
   *
   * 行照样渲染 —— 它是审计要人去改的证据，删掉等于把问题藏起来。但它
   * **不算一道没查的硬性条件**：`unknown` 的自造名会让页面催用户去问一件
   * 根本不是门的事（实测 6 个岗，其中两个是分最高的那两个）。
   */
  offSpec?: boolean;
}

export interface Dimension {
  /** 这一行是不是**计权的四维**之一（判据在 `_cli.is_weighted_dim`）。
   *  `false` 的是被写进评分明细表的 Pass/Fail 门（眼下只有「地点」）——
   *  它没有分数也没有权重，不该进「对口 / 要掂量」那两栏。 */
  weighted?: boolean;
  name: string;
  /** 0-100；缺失用 null（「薪资面议」时就是 null，不许猜） */
  score: number | null;
  /**
   * 权重（30/25/20/25）。**面板不渲染它**，也不该渲染——「占 30%」是打分器的
   * 内部参数，摆到屏幕上只会让人去心算，而分数本身已经是加权后的结论。
   *
   * ⚠️ **实际取值多半是 0，别当它是真权重。** 它从 `evaluation.md` 的评分明细表
   * 里按表头找「权重」列，而 238 张表里 180 张压根没有那一列——于是 0。
   * 2026-08-20 之前这里写的是「四维相加为 100」，那是一句没人兑现的承诺：
   * 真去按它算会得到 0，而且**没有任何消费者会发现**（只有 sample.ts 在填真值）。
   *
   * 留着这个字段是因为深评表带权重列时它确实有值，将来若要做「权重可调」得靠它。
   * 但在那之前：**读它之前先判 0**。
   */
  weight: number;
  /** 一句话依据——它就是给用户看的「为什么匹配 / 哪里要掂量」，别写成给机器看的码 */
  note: string;
}

/** 经历对不上的地方（内部词：能力边界缺口）。`overclaim` 是不能写进材料的说法，会被划红。
 *  `kind` 只在评估里明写了分类时才有——真实数据多是平铺 bullet，不编造分类。 */
export interface BoundaryGap {
  kind?: "核心职责" | "任职要求" | "领域空白" | "加分项" | "";
  claim: string;
  detail: string;
  overclaim?: string;
}

/** 待核实的信息。**不参与打分**——这是信息可信度问题，不是岗位本身的缺点。 */
export interface QualityNote {
  title: string;
  detail: string;
}

/** /job-apply 产出的投递材料。有它 → 详情区给「复制开场白 / 打开简历」；没它 → 给 /job-apply 命令。 */
export interface Materials {
  /**
   * 三渠道话术，`/job-apply` 产出的那三份，**原样带过来不截断**——它们是要整段复制
   * 去投的东西，截一刀就等于交一份断掉的材料，而且断在哪里用户看不出来。
   *
   * 这三份原来只有单页版有。两个面板并存期间，网页版用户想拿邮件正文得另开
   * 一个页面——同一份材料，两个入口，各显示一半。
   */
  /** 打招呼开场白，≤200 字 */
  greeting?: string;
  /**
   * **这段话该怎么发出去**——按 (平台 × 猎头/直招) 分流，判据在 `_cli.send_hint`。
   *
   * 面板原来对每个岗都印同一句「粘到{平台}的聊天框直接发」，而催进度那一侧
   * （`followups.py`）早就分了流：「BOSS 是聊天框；猎聘/智联走站内信，多半
   * 没有对话入口」。**催的时候知道形态，发的时候不知道。** 实测 2026-10-14：405 份里
   * **97 份**被指去找一个多半不存在的聊天框。旧快照没这个字段 → 可选。
   */
  sendVia?: string;
  /**
   * **跟你说话的是谁**：`猎头` / `HR` / `用人方`。判据在 `_cli.counterpart_of`，
   * 与 `/job-apply` 第 1.5b 步同源。
   *
   * 开场白这一层三档没有区别，**分档是给第二轮用的**：对着用人方老大讲职业
   * 规划与稳定性，是把唯一一次直达决策人的机会说成 HR 面。实测猎聘搜索接口
   * 样本 42 张卡片，直招里认得出职务的 20 张中有 4 张对面不是 HR。
   *
   * 认不出就没有这个键 —— 面板宁可不说，也不猜一个给他。旧快照同样没有 → 可选。
   */
  counterpart?: string;
  /**
   * 这段开场白违反了哪几条铁律（`06-outreach-templates.md`「不许出现的五类」）。
   * 空或缺失 = 没问题。判据在 `export_web_data.greeting_problems`。
   */
  greetingWarn?: string[];
  /**
   * 邮件正文 / 网申自评踩了 `03-writing-style.md` 的哪几条。
   *
   * **和 `greetingWarn` 不是同一套判据**：`06` 渠道 1 那五类禁区
   * （开场铺垫、先谈钱…）只管开场白，那段 ⚠️ 明说的；而 `03` 的
   * AI 味、互联网黑话、翻译腔在哪个渠道都管。判据在
   * `_cli.style_problems`。
   *
   * 空或缺失 = 没问题。
   */
  emailBodyWarn?: string[];
  wangshenWarn?: string[];
  /**
   * 抬头那半句「在跟谁说话」有没有问题。空或缺失 = 没问题。
   *
   * 它决定**第二轮怎么说话**：猎头问薪资与到岗时间要直接答，HR 直招不主动展开
   * （`06-outreach-templates.md`「渠道判定」那张表）。写反了，第一次回话就走反。
   * 判据在 `_cli.addressee_problem`，与审计同源。
   */
  addresseeWarn?: string;
  /**
   * 开场白对公司下了断言，而「本次使用的公司事实」那一节是空的。
   * 空或缺失 = 没问题（**多数岗本来就该是空的** —— 只讲自己经历的
   * 那 92% 不算主张）。判据在 `_cli.claim_without_source`，与审计同源。
   */
  factWarn?: string;
  /** 邮件主题 */
  emailSubject?: string;
  /**
   * 邮件正文。**到这里时已经剥干净了**：没有 `> ` 引用前缀、没有代码围栏、
   * 没有「**正文**」标签，也没有「附件改名 / 收件人留空 / 正文字数」这类
   * 写给用户自己看的操作备注（`build_dashboard._clean_email_body` 负责）。
   *
   * 这条不是可选的整洁：这段字是用户**整段粘进邮件发给用人方**的，
   * 备注混进去等于把「记得给附件改个名」发给了对方。
   */
  emailBody?: string;
  /** 网申自评（纯文本，填进网申表单的那段） */
  wangshen?: string;
  /** 简历 PDF 相对路径（真实运行时指向 documents/applications/<目录>/resume.pdf） */
  resumePdf?: string;
  /**
   * **这份定制简历比主简历旧。** 值是主简历最后一次修改的日期。
   *
   * 与渠道那一层的 `resumeStale`（在线简历多久没刷，是个天数）**不是同
   * 一件事**：那个说的是招聘网站上挂着的那份，这个说的是**已经交出去的**
   * 那张纸。
   *
   * 为什么要显示：`job-interview.md` Step 1 写着「`resume.pdf` 是真正交
   * 出去的那份，面试官读的就是它们，这里准备的每一个论点都必须和它们的
   * 说法一致」。旧版意味着他按现行资料准备的说法，和对方手上那张纸对不上
   * —— 而「说法前后一致」正是背调和交叉面在查的东西。
   *
   * 导出器从 2026-08-22 起就在算它（实测当时 15 份定制简历 **15 份全部**
   * 早于主简历），而**面板一直没读**：那个按钮照常写着「打开定制简历 PDF」，
   * 旁边一个字的提示都没有。2026-08-31 接上。
   */
  resumeStale?: string;
  /** 求职信只在校招网申 / 体制内 / 外企 / 传统行业场景才出，直聊不出 */
  coverLetter?: boolean;
}

/**
 * 市场对这份简历的反馈——**不是简历点评**。
 *
 * 措辞、结构、要不要加量化，那类建议任何工具都能给，与这批评估无关，放上来就是装饰。
 * 这里只回答三个别处拿不到答案的问题：主场在哪、什么在挡你、简历要补什么。
 * 三个答案全部从已有的评估结果反推，不凭空点评。
 */
/**
 * 你的**基简历**——所有投递共用的那一份（`resume/main.typ`）。
 *
 * 与 `ResumeInsight` 是两件事：那个是「市场怎么读这份简历」（从评估语料反推），
 * 这个是简历本身。面板原来两样都只有前者，基简历连个入口都没有。
 */
export interface BaseResume {
  /** 源文件最后修改日期 */
  updated: string;
  /** 章节顺序——`05-cv-templates.md` 管这个，列出来才看得出有没有被动过 */
  sections: string[];
  /**
   * 国内社招基线（`05-cv-templates.md`）里有、这份简历里没有的章节。
   *
   * **查的是「在不在」不是「排第几」**——那份文档同时允许章节顺序按行业调整。
   * 判据在 `export_web_data.missing_cv_sections`，机械比对，不靠审阅报告里那句散文
   * （实测那句话把根本不存在的「求职意向」写成了「与基线完全一致」）。
   */
  missingSections?: string[];
  /**
   * 主简历渲染出来的字里，踩了 `03` 风格铁律的那几句。
   *
   * **改一次，之后每一次投递都受益** —— 定制版是从主简历复制出去的
   * （实测那一句进了 12 份），下次 `/job-cv` 重出时跟着干净。
   * 判据在 `export_web_data.base_resume_style`，与自检同源；
   * 没装 poppler 时整条不出（拿不出结论就不说）。
   */
  styleWarn?: string[];
  /**
   * 缺的那几节里，**他在定制简历里已经写过**的原文（`节名 → 那一行`）。
   *
   * 让他从零想一句，和告诉他「你自己写过，在这儿，抄过来」，是两件事。
   * 判据在 `export_web_data.sections_written_elsewhere`。
   */
  missingWrittenElsewhere?: Record<string, string>;
  /**
   * 资料里没填、而**七道硬门要用**的取值。
   *
   * 缺一项，那道门在**每一个**岗上都判不了 —— 不是「不适用」，是判不了，
   * 而这两件事在结果上完全不同。判据在 `export_web_data.unfilled_gate_inputs`。
   *
   * 与 `doctor` 的完整度检查不重叠：那道门查的是模板占位符（`[YOUR_NAME]`），
   * 而「未提供」是真写下去的值，长得像内容，一路放行。
   */
  gateInputsMissing?: { field: string; gate: string }[];
  /** 编译出的 PDF（`web/public/` 下的拷贝，供 http:// 模式） */
  pdf?: string;
  /** 指向真实目录的相对路径，供单文件/静态模式 */
  pdfLocal?: string;
  /**
   * PDF 比源文件旧 = 改了 .typ 但没重新编译，打开的是**上一版**。
   * 这种「文件在、但内容是旧的」最容易骗人：按钮能点、PDF 能开，只是内容不对。
   */
  pdfStale?: boolean;
  /** 最近一次 `/job-resume` 审核。摘要而已，全文在 reports/ 下那个文件里 */
  audit?: {
    date: string; count: number; verdict: string;
    /** 简历在审阅之后又改过 —— 那句结论说的是上一版。 */
    stale?: boolean;
    /** 简历最后改动的日期，`stale` 为真时用来告诉用户「之后」是哪天。 */
    resumeChangedOn?: string;
  };
}

export interface ResumeInsight {
  sweetSpot: {
    /** 业务域 ≥60 的岗数 —— 「这个岗的活你熟」的那一档 */
    count: number;
    /** 参与统计的评估总数（能回读出专业能力/业务域两笔的） */
    total: number;
    /**
     * `count` 里**现在还能投出去的**（未投、未点掉、未下线、判词还在可投三档）。
     *
     * `count` 是历史统计，回答「市场里有多大一块对得上你」；而这一节末尾那句
     * 「主要靠**选对岗**解决」是库存指令。实测 2026-08-23：107 个里已投 22、
     * 点掉/下线/低判词 36，**还能投的只有 49**。只印 107 会让人以为手上
     * 还有一百来个可挑。旧快照没有这个字段 → 可选，缺就不显示那半句。
     */
    open?: number;
    /** 主场岗里有 JD 正文、真被数过词的 */
    withBody: number;
    industries: { name: string; n: number }[];
    /** inResume / inProfile 为 null = 那份文件读不到，显示「没比对」而不是「没写」。
     *  两个都要：「简历里没有」只说明忘了写，「资料里也没有」说明他真没这一项——
     *  后者绝不能建议他写进简历（`03-writing-style.md` 铁律 3）。 */
    asks: {
      term: string; n: number; of: number;
      inResume: boolean | null; inProfile?: boolean | null;
      /** 这个词是从哪儿数出来的。`正文` = JD 里提到它（他会不会）；
       *  `标题` = 职位名里就有它（**HR 会拿这个词搜人**）——后者对
       *  「简历里写没写」的分量重得多，界面上要分得开。
       *  两个词源也是那个「资料和简历里都没有」分支能渲染出来的前提：
       *  只有资料这一个词源时 `inProfile` 恒为真（见 `title_terms`）。 */
      where?: "正文" | "标题";
    }[];
    resumeChecked: boolean;
  };
  medianStack: number;
  medianDomain: number;
  /** tone: fixed=改不了的约束 / ask=投前问一句 / choose=靠选择绕开 */
  blockers: { name: string; n: number; of?: number; tone: string; note: string }[];
}

export interface Job {
  /** 这个岗属于「这几类岗要不要看」的哪几类。判据在导出器里算好，前端只按它过滤 */
  prefTags?: string[];
  id: string;
  /** 职位原始链接。整个工具的终点是「去投」，这个链接必须永远可达。 */
  url: string;
  title: string;
  company: string;
  /** 平台给的雇主字符串可能是脱敏描述（「某大型互联网电商平台上市公司」），照用不改写 */
  anonymousEmployer?: boolean;
  /**
   * 你自己标了「不投」的（盘上 `status: "skipped"`）。
   *
   * 有本地服务时这个标记来自**盘上的真实状态**，刷新之后还在；静态模式下盘上写不了，
   * 排除只存在浏览器里（见 `data/excluded.ts`）。两种模式的区别在页脚说明。
   */
  skipped?: boolean;
  /**
   * 职位已下线（关了 / 报名截止 / 点开是聚合页）。
   *
   * 与 `skipped` **是两件事**：那是你的判断（不合适），这是外面的事实（没了）。
   * 两者都只进搁置区，但搁置区里要分开显示——「你排除的」可以回看当初为什么，
   * 「已下线」没什么可回看的，它只是不在了。分数与判词照旧保留：万一判错
   * （点开恰好是聚合页而职位其实还在），放回来时那些还得在。
   */
  expired?: boolean;
  /** 标为已下线的日期 */
  expiredDate?: string;
  /**
   * **为什么下线**，执行者标的时候写的那句。
   *
   * 上面那句「已下线没什么可回看的」对**页面确认**的那种成立
   * （「页面顶部写着该职位已暂停招聘」「详情页 404」），对**推断**的那种
   * 不成立（「浏览器打开跳到职位聚合页，岗位已不在」）—— 后者正是可能
   * 标错的那批，而「放回」按钮问的就是「职位其实还在？」。
   *
   * 只进悬浮提示，不进可见标签：原因是整句话，摆进行里会撑爆版式。
   */
  expiredReason?: string;
  /**
   * 被**规则**淘汰的（预筛判「跳过」），不是你手点的不投。
   *
   * 两者都要能放回，但撤销语义不同：手点的只撤标记、分数还作数；规则判的连判词
   * 一起撤、退回待评重走评估——因为它的结论来自一份当场传进来的词表，用户要放回
   * 就说明那条规则在这个岗上判错了，留着判词等于没放回。见 `serve.py:apply_restore`。
   */
  ruleSkipped?: boolean;
  /** 标不投时写的原因。放回时会连它一起清掉。 */
  skipReason?: string;
  /**
   * **什么时候标的不投**，与 `expiredDate` 对称。
   *
   * 面板点的来自叠加层，命令行 `/job-rank --skip` 来自库里的 `skip_date`。
   * 求职拖久了标准自己会动 —— 第一周否掉的和上周否掉的不是一回事，
   * 而搁置区里它们长得一模一样。旧快照没这个字段 → 可选。
   */
  skipDate?: string;
  /**
   * 已投递的记录，来自 `job_search_tracker.csv`（按公司名 + 岗位名匹配）。
   *
   * 原来投递记录只被数了个总数：流水线显示「已投递 1」，但**哪一个投了看不出来**，
   * 那个岗照旧躺在可以投的列表里。求职最容易犯的错就是重复投同一家，而一个
   * 只报总数、不报是哪个的计数器正好帮不上这个忙。匹配不上的岗不带这个字段——
   * 宁可少标，也不要贴错到别人头上。
   */
  /** `statusLabel` 是 `status` 码的中文说法（tracker.say 译好带来）——
   *  上屏用它；`status` 是给统计的英文码，不直接渲染（AGENTS.md 措辞规则）。 */
  applied?: { date: string; status: string; statusLabel?: string; channel: string };
  /**
   * 从当前状态**走得到**的下一步，由 `tools/tracker.py` 的 `NEXT` 算好带过来。
   *
   * 不在 TS 里另写一套状态机：两份迟早分叉，而分叉的样子是页面画出一个按钮、
   * 服务端拒绝它。`then` 是记完之后还需要模型的那条命令（约面了 → `/job-interview`），
   * 空串表示记完就完了。
   *
   * 已结案的岗为空数组——再改就不是「记一笔」而是修订，那该走 `/job-outcome`。
   */
  nextStatuses?: { value: string; label: string; then: string }[];
  /**
   * HR 有没有点开过这份简历。**三态**：`true` / `false` / 不在（还没查过）。
   *
   * 国内平台在「投递记录」里逐条标着已查看 / 未查看，这个数平台白给，
   * 而它把「投了没回音」拆成两件后果相反的事（`job-outcome.md` Step 2b）：
   * 已查看还是没回 → 才轮到审简历；大多未查看 → 改简历没用，要换的是投什么岗。
   *
   * **`undefined` 和 `false` 不是一回事** —— 一个是没查，一个是查过、没打开。
   */
  hrViewed?: boolean;
  /**
   * 这个岗在流水线的哪几格里（`materials` / `applied` / `interview`）。
   *
   * 由 `export_web_data.funnels_of` 算好带过来，**格子上的数和点开的筛选用的
   * 是同一个字段**。两边各判一次的下场实测过：三个格子的数字和点开看到的行数
   * 全对不上，而且都要等真有投递之后才显形。
   */
  funnels?: string[];
  /**
   * **这个岗**卡在哪、下一步做什么。与顶部那条 `nextStep` 不是一回事：
   * 那条回答「整体该干什么」，这条回答「这个岗该干什么」——同一时刻两者可以
   * 指向不同的事（整体也许该去投别的岗，而这个岗正等着记面试结果）。
   * 已结案（录用/被拒/无回复）与硬性条件没过的岗没有下一步，字段缺席。
   */
  nextStep?: { text: string; command?: string };
  /**
   * 模拟面的问答记录，按轮次累加（`documents/applications/<…>/interview_log.md`）。
   *
   * **只读**：练习在你那家 AI 编码工具里进行（那边才有模型），面板负责回看。
   * 回看的价值在于「上次哪几题答得含糊」——所以答案是**原话记录、不润色**，
   * 润色过的记录看着漂亮，回看时一点用没有。
   */
  interviewLog?: {
    round: string; date: string; stage: string; scene: string;
    qa: { q: string; a: string; feedback: string }[];
  }[];
  /**
   * 同一个岗的其它投放（同 JD 被多个猎头挂出）。只出现在**主投放**（组内分最高的
   * 那条）上；被归并的投放带 `dupOf` 指向主投放，列表里不再单独占一行。
   *
   * 不归组的话「值得投 N 个」是虚的——实测同一份供应链 JD 有五个投放。
   * 同岗不同价（35k vs 90k）本身是职级未定/广撒网的信号，要摆出来。
   */
  duplicates?: { url: string; salary: string; via: string; score: number | null }[];
  /** 这条是某主投放的重复投放；列表里隐藏，细节在主投放的详情里看。 */
  dupOf?: string;
  /**
   * JD 正文一字不差、**公司名却不一样**的其它岗。
   *
   * 和 `duplicates` 是两回事：那批已经判定是同一个岗（公司也相同），归并掉了；
   * 这批**判不了**——可能是一个岗两家猎头各自脱敏后代招，也可能是两家公司
   * 套了同一份 JD 模板。两种的下一步正好相反（前者只投一个，后者两个都投），
   * 所以这里只摆出来给人看，不归并、不隐藏、不替他决定。
   *
   * 要紧的是前一种：同一个岗投给两家猎头会撞单，对候选人是减分的。
   */
  sameJd?: { url: string; company: string; salary: string; score: number | null }[];
  /** 这家公司你已经投过几个岗、最近一次多久以前 —— **整句话由 Python 拼好**
   *  （`export_web_data.same_company_note`），只给还没投的岗带。
   *
   *  拼在那边是因为窗口内外说的话不一样，而「短期内是多短」
   *  （`SAME_COMPANY_DAYS`）只许有一份。原来这里是个数字、句子在 TSX 里拼，
   *  于是那句「同一家**短期内**连投几个」对着一个**全库累计数**说 ——
   *  实测 2026-08-24 碰巧是对的（85 条投递全在 14 天内），三个月后就不是了。
   *
   *  公司身份走 `followups.cluster_key`，脱敏串不算 —— 「某知名公司」库里
   *  158 次，裸比会印成「这家你已经投过 158 个岗」。 */
  sameCompanyWarn?: string;
  /** 原样保留平台给的薪资串，不做归一化——月薪/年薪/几薪三种口径混用 */
  salary: string;
  /**
   * 折算好的年包区间（万）。原始薪资串口径很多（`25-35k·20薪`、`40-70k`、
   * `3.5-5万`、`10-15万/年`、`300-400元/天`），跨岗没法直接比——
   * 心算不是用户该干的事。
   *
   * - `assumed12` 平台没写几薪，按 12 薪保守算的
   * - `estimated` 日薪/时薪折的，用了法定月计薪天数 21.75 与每日 8 小时
   * - `variable`  带提成/绩效/计件，**这里只是底薪**，大头没算进去
   *
   * 后两个字段对非互联网职业才要紧：产线与建筑按日结、销售与律师大头在提成。
   * 不说出来，一个 6 万的底薪会被读成「这岗只值 6 万」。
   */
  annual?: {
    low: number; high: number; assumed12: boolean;
    estimated?: boolean; variable?: boolean;
  };
  /** 平台没写几薪 → 年包算不出来，要显式说出来 */
  salaryMonthsUnknown?: boolean;
  /** 平台没给就是空串——空串不渲染，不要填「未标」这种占位符 */
  location: string;
  experience: string;
  channel: string;
  /** 猎头 or HR 直招，决定话术策略 */
  viaHeadhunter: boolean;
  /**
   * 投之前要问清的几条（深评的「投前必问」）。
   *
   * 「可以考虑」那一档的定义就是「先问清楚再决定投不投」——列表上那枚
   * 「话术备好 · 先问清」的章说了要问，这里是**要问什么**。
   * 判据在 `export_web_data.parse_ask_before`。
   */
  askBefore?: string[];
  /**
   * 评估里「建议」那一节 —— **读完这个岗之后写下的结论**。
   *
   * 和 `verdict` 可以合法地不一致：判词是打分器给的档，这一节是人话结论，
   * 常见的是「不投。同一个岗有薪资更高的挂法，投那一条」。
   *
   * 它在此之前**没有任何消费方**：导出里没有这个字段，于是屏幕上只剩判词
   * 那一半。实测 2026-09-02：50 份深评的「建议」以「不投」开头，其中 13 个
   * 的「下一步」还印着「材料就绪，还没投，快去投」。
   */
  advice?: string;
  /** 这个岗的判断该重跑一遍，值就是理由（「翻档」/「当时没读全，得先抓 JD」）。
   *  判据在 `tools/stale_materials.py`，导出时贴成这一个字段。
   *  顶上那句「N 个岗的判断该重跑一遍」数的就是有这个字段的岗。 */
  restale?: string;
  /**
   * 这个岗**多久没刷新**了（天）。只有超过阈值（`STALE_POSTING_DAYS`）时才有值，
   * 没有值分两种：这个岗很新，或者平台压根没给日期——**两者不能长得一样**，
   * 所以缺值时什么都不显示，不显示「很新」。
   *
   * 只有猎聘给这个字段，且它自己也不是每条都给（实测覆盖约 10%）。
   */
  staleDays?: number | null;
  /**
   * 这个岗**在你手上排了多久**（天）。和 `staleDays` 不是一回事：那个说的是
   * 「抓到它那天，招聘方上一次刷新在多久以前」（只有猎聘给，覆盖约 10%）；
   * 这个说的是「它进库到今天多少天」（`first_seen`，100% 有）。
   *
   * **只有「材料备好、还没投」的岗才有值**（那批 100% 都有）——别的岗排多久
   * 都不构成一个动作。**够不够久是另一个字段**（`queuedLong`）：这里给原始
   * 天数，标不标由那个说了算（「排了 3 天」是噪音，同 `staleDays` 那条
   * 「标记要标少数派」）。
   *
   * 这个数一直在算 —— 顶上那句「其中 N 个排了两周以上，从它们开始」用的就是它。
   * 而它此前**只作为一个计数出去**，名单上没有任何东西标出是哪 N 个：
   * 实测 2026-08-25，60 份备好没投的里 15 个排了 15-32 天，
   * 面板一边说「从它们开始」，一边按分数排给他看。
   */
  queuedDays?: number | null;
  /**
   * 上面那个天数**够不够久**（超过 `STALE_POSTING_DAYS`）。名单上的小标读它，
   * 不自己拿天数去比 —— 阈值只许有一份，在 Python 那边
   * （同 `Gate.offSpec`、`Dimension.weighted` 的做法）。
   *
   * 为什么不干脆只在够久时才给 `queuedDays`：那样等于把判据烧进数据，
   * 拿不到原始天数的消费方就只能另找字段去算 —— `doctor.ready_age` 当初
   * 就是这么退去读了 `staleDays`，报出一个和面板差 5 个的数。
   */
  queuedLong?: boolean;
  score: number | null;
  /**
   * 这个分是不是 `/job-apply` 深评给的（做过公司调研 + 能力边界比对）。
   * false = `/job-rank` 粗筛分，判词会带「粗筛：」前缀。两者信息量差一个量级，
   * 用户必须能一眼分辨——实测同一个岗粗筛 76「强匹配」、深评只有 62。
   */
  evaluated?: boolean;
  /** JD 正文读过没有。**与 `evaluated` 是两件事**：粗筛也可能读过完整 JD，
   *  只是没做公司调研与双角色审稿。短名单那两枚章按它分。 */
  jdRead?: boolean;
  /**
   * 技能与经验（0-100）。**这一页第二重要的数。**
   * 总分把四维揉成一个数，20 个岗挤在 58-78 分时它已经分不出高下；
   * 而「技能 82」与「技能 45」是两回事——一个真对口，一个是被年包托上去的。
   */
  skill?: number;
  /** 这个分怎么来的，一句话。鼠标悬停时给出。 */
  skillWhy?: string;
  verdict: Verdict | typeof GATE_FAIL;
  gates: Gate[];
  /** 七道硬门里**没判**的那几道（见 `UnjudgedGates`）。空数组 = 七道都判过。
   *  缺省时按「不知道」处理，不按「都判过」——两者的默认后果不对称。 */
  gatesNotJudged?: UnjudgedGates;
  dimensions: Dimension[];
  materials?: Materials;
  gaps: BoundaryGap[];
  quality: QualityNote[];
  /** 不满足硬性条件时，记下是哪一条 + JD 原文 */
  gateFailReason?: string;
  /** `/job-apply --top N` 批量时缺东西留下的待办。批量不回头在对话里问，问题攒到面板上。 */
  blocked?: { 环节: string; 需要: string; 日期?: string };
}

/** HR 聊天框里反复问的那几句，连同事先写好的答案。
 *
 *  `empty` = 还没写：正文空的，**或者占位符没换掉** —— 后者更危险，
 *  它看着像准备过了。判据在 `export_web_data.hr_answers`。 */
export interface HrAnswer { q: string; a: string; empty: boolean }

export interface PipelineStage {
  /** 第几步。五个阶段有真实先后顺序，序号是信息不是装饰 */
  step: number;
  label: string;
  count: number;
  /**
   * 还在**排队等着评**的（只有第 2 步给）。
   *
   * 「搜到 2638 → 打过分 2450」并排画着，中间那 188 从来没被点名 ——
   * 而它也不全是待办：6 个是已下线且从没评过的死岗。判据在 `doctor.n_waiting`，
   * 那边和这边共用同一个函数（`build_dashboard` 从 doctor import）。
   * **有才给**：正常抓完就自动评了，这个键平时不出现。
   */
  waiting?: number;
  /** 这批放了多久。**只有出现了超过 14 天的才给** —— 平时不显示，
   *  判据与实测见 `doctor.waiting_age`。 */
  waitingNote?: string;
  /**
   * **投过、却落在搁置区的岗**（只有第 4 步给）。
   *
   * 这一格的数走 `funnels_of`，它排掉判词出局与三类搁置 —— 那是对的：
   * 格子上的数必须等于点开看到的行数。可「投了多少」在**同一屏上有
   * 第二个数**：「投出去的那些」那颗按钮走投递记录行数。
   * 实测 2026-08-31 一个 85、一个 88，上下摆着，差 3 而没有一个字解释。
   * **有差就要说出来**（同这一格已有的「另有 N 个被你关掉了」）。
   * **有才给**：一个都不在搁置区时这两个键不出现。
   */
  parked?: number;
  /** 上面那个数的说法，理由是**现数**出来的（判词出局 / 你标了不投 /
   *  岗位已下线），不写死。 */
  parkedNote?: string;
  /** 这一步在做什么。一句话，说事不说术语 */
  does?: string;
  /** 这一步该敲的命令。必须可照抄——投递那步没有命令，就给「投完记一笔」那条 */
  cmd?: string;
}

export interface EnvItem {
  name: string;
  /**
   * `null` = 不由本仓库决定（例如浏览器能力由 AI 工具提供）。
   * 这种项**不能算进「还差几项」**——误报会把人推去装他其实不需要的东西。
   */
  ok: boolean | null;
  detail: string;
  unlocks: string;
  /**
   * 可选依赖（不装也能正常用）。**不算进「还差几项」。**
   *
   * pdftotext / Bun / 浏览器取数不装完全能用，算进去会让新用户以为出了大问题，
   * 然后去装一堆不需要的东西。单页版一直守着这条，网页版原来守不住——
   * 因为导出器把这个字段丢了，这边只能按 `ok === false` 数。
   */
  optional?: boolean;
  /**
   * 缺了**不报错**的那一项。
   *
   * 中文字体是唯一这样的依赖：缺了 Typst 不报错、PDF 照样生成、ATS 文本层校验
   * 也过，但渲染出来是一页豆腐块。只和别的项并排列在表里，用户不会意识到严重性
   * ——所以它要单独说一句。
   */
  silentFail?: boolean;
  /** 怎么装（官网 / 命令）。缺项时给出去，省得用户自己去搜。 */
  fix?: string;
}

/**
 * 这个 clone 下有哪些用户（只有名字，不含任何人的数据）。
 *
 * 多人共用一份 clone 是 `AGENTS.md` 明确支持的用法，但面板原来只知道「当前是谁」
 * ——「换个用户」是个没有 onClick 的死按钮，既列不出可选项，也说不出怎么新建。
 * 切换与新建都在命令行做（`/job-user <名>` / `/job-user --new <名>`），这里只负责
 * **让人看得见有哪些、以及该敲什么**。
 */
export interface NextStep {
  text: string;
  command?: string;
}

/** 一条命令：敲什么、干什么。来自 workflows/INDEX.md 的工作流索引表，不在前端写死。 */
export interface CommandItem {
  /** workflow 名（= 文件名去掉 .md），用作 key */
  name: string;
  /** 可复制的那一串，含参数提示，如 `/job-apply <职位链接>` */
  cmd: string;
  /** 它干什么 */
  does: string;
  /**
   * 这个命令还能怎么敲。第一条就是 `cmd`，界面上不重复显示。
   *
   * 有斜杠的是命令（渲染成可复制的片），没斜杠的是自然语言触发语
   * （「投这个岗」——直接说也行，不必记命令名）。括号里的补充说明跟着
   * 各自那条走。来源同样是 AGENTS.md 的索引表，前端不写死。
   */
  examples: string[];
  /**
   * 什么都不给时它会干什么。索引表第四列，**可能为空**（老表只有三列）。
   *
   * 这是用户敲下裸命令之前最想知道的一件事，而它原来只有读
   * `workflows/<名>.md` 才有答案——那正是面板存在的意义要消灭的动作。
   */
  bare?: string;
}

/** 投出去之后的统计。由 `export_web_data.outcome_stats` 算好送过来。 */
export interface OutcomeStats {
  /** 匹配上职位的投递数 */
  total: number;
  /** 分类计数，`n` 为 0 的已在后端剔除 */
  buckets: { k: string; n: number }[];
  /** 有回音的占比（%）。没投过时为 null */
  repliedRate: number | null;
  /** 约到面试的占比（%） */
  interviewRate: number | null;
  /** 按分数段的回复率——它回答「评分准不准」 */
  byBand: { band: string; sent: number; replied: number }[];
  /**
   * 按**投递渠道**拆的回复率。渠道从台账的 `channel` 列取，取不到就从职位链接
   * 推（`tracker.channel_of`）——那一列历来全空，而链接一直都在。
   *
   * 分数段回答「该投多高分的岗」，这一栏回答「该在哪个网站花力气」。
   */
  byChannel?: {
    channel: string; sent: number; replied: number;
    /** 这个渠道的 `sent` 里有几个是猎头代招。各渠道差得极远（实测 2026-08-23：
     *  猎聘 43/66，BOSS 直聘 1/16），不带上它这张表就不能横着比。 */
    agency?: number;
  }[];
  /** 投出去的里面有几个是**猎头代招**。简历进的是猎头库，不是用人方。 */
  viaAgency?: number;
  /** 投出去那批按「专业能力 / 行业经验」分的四格。见 `export_web_data.applied_fit`。 */
  appliedFit?: {
    total: number; home: number; pick: number; learn: number; off: number;
    /** 还没投的可投岗同一套分法 —— 「往主场投」挑不挑得出来，看这个。 */
    open?: { total: number; home: number; pick: number; learn: number; off: number } | null;
  };
  /** 企业直招那批单拆的分母与分子：已决出结果的、其中有回音的。
   *  「猎头占了一半，所以不是简历的问题」这句话只说了一半——直招那批
   *  如果也全军覆没，那才是简历的信号。
    * 判据在 `tools/export_web_data.py` 的 `outcome_stats`（同源措辞见 `tracker`）。 */
  directDecided?: number;
  directReplied?: number;
  /** 零回音警报的样本量门槛（三倍法则）。跟着数据下发，TS 侧不另抄一个。 */
  noReplyAlarm?: number;
  /** 投过的**具名企业直招**公司有几家——这是「内推够得着」的范围。 */
  directCos?: number;
  /** 上面那些公司里的几个例子，用来把建议落到具体的家上。 */
  directCosSample?: string[];
  /** 拒绝原因分布。用户没填就是空的，这很正常 */
  reasons: { k: string; n: number }[];
  /** 超过这个天数没动静就算「大概率没戏」 */
  silentDays: number;
  /** 还在等的那些，已经等了多少天（中位数） */
  waitingMedian: number | null;
}

/** 按流程分的一组命令。分组是展示层的编排，成员完整性由测试兜底。 */
export interface CommandGroup {
  group: string;
  items: CommandItem[];
}

/**
 * 一个招聘网站的状态。
 *
 * `jd` 那一项**不是可有可无的装饰**：拿不到 JD 正文的渠道，抓回来的岗过不了硬门，
 * 会一直停在「待评」。用户看到「抓了 231 个却一个可投的都没有」时，
 * 需要知道是这个原因，而不是以为工具坏了。
 */
export interface Portal {
  name: string;
  /** 开着没。关掉之后 `/job-scrape` 跳过它 */
  enabled: boolean;
  /** 怎么取数：免登录接口 / 浏览器读页面 */
  how: string;
  /** 要不要你在 Chrome 里登录 */
  needsLogin: boolean;
  /** 能不能拿到 JD 正文（决定抓回来的岗能不能打分） */
  jd: boolean;
  note: string;
  /** 库里来自这个渠道的岗数 */
  jobs: number;
  /** 现在**还剩**几个能投（已投/已下线/已跳过都减掉了）。
   *  它不是「这家给过我几个」—— 越给力的渠道这个数被吃得越干净。 */
  sellable: number;
  /** 累计判过「能投」的个数（不减已投/已下线/已跳过）。**这个才是产能。**
   *  两个数分开印的理由见 `Portals.tsx` 那处注释：只印 `sellable` 会得出
   *  相反的结论（实测猎聘 2232→5 看着最差，累计却占全部可投岗的 83%）。 */
  everSellable: number;
  /**
   * 其中**职位描述已经存下来**的个数。
   *
   * 和上面那个 `jd`（这个网站能不能读到 JD）是两件事：那个是能力，这个是实际做到了多少。
   * 2026-08-19 实测两者差得极远——猎聘 66%，而浏览器三家 0%~1%：JD 在会话里读完就扔了。
   * 存不下来的代价是后面全都拿不到：算能力差距、复查原文、职位下线后回查。
   */
  withJd: number;
  /**
   * 这家现在是不是被平台拦着（撞了风控 / 要短信验证 / 限流冷却里）。
   *
   * **要显眼**：被拦的那一刻起这家一个岗也抓不到，而多数情况**只有用户本人能解**
   * （去手机上过一条短信）。工具停手是对的，不告诉他是错的——他看到的现象会是
   * 「怎么最近都没新岗了」，根本不知道要去点一下手机。
   */
  blocked: boolean;
  /**
   * **这家现在还抓不抓得动。** 与 `blocked` 不是一回事：`blocked` 说「有通道被封」，
   * 这个说「还有没有路可走」。猎聘只封了 CLI 时 `blocked` 为真、而它照样抓得动
   * （浏览器那条放慢不停）—— 把两者混成一句「这家现在抓不了」，
   * 面板就会和终端对同一份数据给相反的答案。判据在 `portal_budget.check()`。
   */
  canScrape?: boolean;
  /** 为什么被拦，原样给用户看 */
  blockedWhy: string;
  /** **已经**停了几小时。不是「还剩几小时」——2026-08-26 起封控不会自动解，
   *  没有「还剩」这回事了（本人裁定：只有用户手动点继续才能继续）。 */
  blockedHeldHours: number;
  /**
   * 去哪儿处理。优先是撞上时那个拦截/验证页的原地址，拿不到就退到平台首页。
   * **面板要把它做成可点的链接**——只告诉用户「要短信验证」而不给入口，
   * 等于把最后一步又扔回给他去翻。
   */
  blockedUrl: string;
  /** 被封的是哪条通道：`browser`（账号要过验证）| `cli`（匿名接口在限流）。
   *  两者在面板上的说法完全不同——见 `Portals.tsx` 的告警条。空串 = 没被封。 */
  blockedLane: string;
  // `blockedUntil` / `blockedTotalHours` 2026-08-26 撤掉了：它们答的是
  // 「到几点自动恢复」，而封控不再自动恢复。屏幕上摆一个会过期的时刻，
  // 就是在教用户等 —— 而 CLI 那条等到点换的还是同一个 IP。
  /** 被它**连带放慢**的另一条通道名（CLI 被封时是「浏览器」）；没有就是空串。
   *  注意是放慢不是停 —— 2026-08-21 起浏览器那条只降密度（间隔 ×3）。 */
  blockedAlsoStops?: string;
  /**
   * **每一条被封的通道各一项。** 上面那几个 `blocked*` 字段是把一家塌成一条的
   * 结果（取剩余时长最长的），两条各自因为不同的事封着时它只说得出其中一条，
   * 另一条在界面上就不存在 —— 而用户要解的恰恰可能是看不见的那条。
   *
   * 面板按这个数组渲染告警行与按钮；`channel` 是**解它要报的渠道名**
   * （`liepin-browser` 这种），按钮和 `--clear` 都报它，不报平台名 ——
   * 平台名会让后端自己去挑「哪一条」，挑错就等于解了他没处理的那一条。
   */
  blockedLanes?: {
    lane: string;
    channel: string;
    why: string;
    /** 已经停了几小时（不是「还剩」，封控不会自动解） */
    heldHours: number;
    /** 「这条不是第一次撞了」那句话；只撞过一次时是空串。
     *  正本在 `portal_budget.streak_note`，前端不自己数。 */
    streak: string;
    url: string;
    /** 被这条**连带放慢**的通道名；没有就是空串 */
    alsoSlows: string;
  }[];
  /** 最近一次抓取日期；从没抓过就是 null */
  lastRun: string | null;
  /** 那一天新增了多少 */
  newLastRun: number;
  /**
   * 在线简历上次刷新是几天前。**没记过时这个字段不在**——
   * 「没记过」和「刷过很久了」是两件事，给个 0 或 null 都会被渲染成一个假的数。
   *
   * 为什么这件事要占一格：国内平台的简历库基本按「最近活跃」排序，
   * HR 主动搜人翻不了几页 —— `job-resume.md` 2.6 把刷新标成那张表里
   * **唯一一件每天都要做**的事，而它此前没有任何落点。
   */
  resumeStale?: number;
  /** 网页版有没有「刷新简历」按钮（false 表示网页端无入口，需在手机 APP 活跃或刷新） */
  webRefresh?: boolean;
  /** 刷新入口说明（来自 resume_refresh.WEB_REFRESH） */
  refreshHow?: string;
  /** 怎么算刷新成功 */
  refreshSuccess?: string;
}

/**
 * 「这几类岗要不要看」的一项。
 *
 * **只管看不看见，不改判词。** 关掉是把这类岗从可投名单里滤掉，
 * 分数与判词原样留在库里，随时开得回来。
 */
export interface JobPref {
  key: string;
  enabled: boolean;
  label: string;
  note: string;
  /** 现在库里有多少个这类岗——不给这个数，用户没法判断开关值不值得动 */
  n: number;
}
