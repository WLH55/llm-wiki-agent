/**
 * Mock 数据 — 内容来自现有 wiki/
 * 数据分类：IAP系统、投放系统、钉钉自动化、工作积累
 *
 * 这些数据用于原型演示，反映真实知识库的内容
 * 实际生产中由后端从 wiki/ 目录读取
 */

const MOCK = {
  /* ---------- 知识库元信息 ---------- */
  knowledgeBase: {
    name: '工 作 知 识 库',
    subtitle: 'editorial knowledge base',
    version: 'v1.0',
    description: '沉淀团队的工作积累，构建可检索、可关联、可演化的知识档案。',
    stats: {
      sources: 12,
      entities: 8,
      concepts: 15,
      syntheses: 2,
      lastUpdated: '2 天前',
    },
  },

  /* ---------- 多知识库（顶部切换器） ---------- */
  knowledgeBases: [
    { id: 'kb1', name: '工作知识库', active: true,  pages: 37, desc: 'IAP/投放/钉钉/工作积累' },
    { id: 'kb2', name: '技术文档库', active: false, pages: 124, desc: 'API/SDK/架构设计' },
    { id: 'kb3', name: '产品需求库', active: false, pages: 56, desc: 'PRD/设计稿/评审记录' },
  ],

  /* ---------- 推荐问题 chip（首次进入空状态） ---------- */
  suggestedQuestions: [
    { label: 'IAP 退款流程是什么？',           category: '业务流程' },
    { label: '投放策略有哪些优化方向？',       category: '运营决策' },
    { label: '钉钉多维表格怎么自动化？',       category: '工具使用' },
    { label: '最近更新的文档有哪些？',         category: '知识动态' },
  ],

  /* ---------- 对话历史（侧栏列表，可切换） ---------- */
  conversations: [
    { id: 'c1', title: 'IAP 退款流程',   time: '12:34',   active: true  },
    { id: 'c2', title: '投放策略优化',   time: '昨天',   active: false },
    { id: 'c3', title: '钉钉多维表格',   time: '昨天',   active: false },
    { id: 'c4', title: '支付系统异常',   time: '3 天前', active: false },
  ],

  /* ---------- 多组对话（点击侧栏历史切换显示） ---------- */
  conversationData: {
    c1: {
      messages: [
        { sender: 'user', time: '12:34', content: 'IAP 系统怎么处理退款？' },
        {
          sender: 'ai',
          time: '12:34',
          content: `退款流程分为三个步骤：

① 用户在订单页发起退款请求，需提供订单 ID、退款金额、退款原因。[01]

② 系统校验订单状态与退款资格。检查订单是否在 7 天退款期内、是否已发货。[02]

③ 退款通过原支付渠道返回。通常 3-5 工作日到账。[02][03]

如果用户对退款结果有异议，可以通过用户中心的"退款申诉"入口提交工单，由财务团队人工审核。`,
          streaming: false,
        },
      ],
      sources: [
        { num: '01', title: 'IAP退款流程',   type: 'source', file: 'iap-refund-flow.md', score: 0.91 },
        { num: '02', title: 'PaymentSystem', type: 'entity', file: 'PaymentSystem.md',   score: 0.74 },
        { num: '03', title: 'UserCenter',    type: 'entity', file: 'UserCenter.md',      score: 0.68 },
      ],
    },
    c2: {
      messages: [
        { sender: 'user', time: '昨天 14:20', content: '投放策略有哪些优化方向？' },
        {
          sender: 'ai',
          time: '昨天 14:20',
          content: `基于近期投放数据，建议从三个方向优化：

① 渠道结构：当前头部渠道占比 78%，建议引入 2-3 个新渠道分散风险。[01][02]

② 出价策略：日预算低于 5000 元的计划建议用 oCPM，高于则用 tROAS。[03]

③ 素材迭代：素材生命周期平均 5.2 天，建议每周更新 3 条创意。`,
          streaming: false,
        },
      ],
      sources: [
        { num: '01', title: '投放策略优化',   type: 'source',    file: 'ad-strategy.md',         score: 0.88 },
        { num: '02', title: 'AdChannel',     type: 'concept',   file: 'AdChannelSelection.md',  score: 0.72 },
        { num: '03', title: '出价策略',       type: 'concept',   file: 'BidStrategy.md',         score: 0.65 },
      ],
    },
    c3: {
      messages: [
        { sender: 'user', time: '昨天 16:10', content: '钉钉多维表格怎么自动化？' },
        {
          sender: 'ai',
          time: '昨天 16:10',
          content: `钉钉多维表格自动化主要靠"自动化规则"+"扩展脚本"两种方式：

① 自动化规则：字段变更、定时触发、表单提交等事件，可触发通知/字段更新/记录创建。[01]

② 扩展脚本：复杂逻辑用 JavaScript 写，调用钉钉 OpenAPI 实现跨表/跨应用联动。[02]

典型案例：每日 9 点拉取昨日投放数据 → 计算ROI → 低ROI 自动标红 → 推送给运营。[01][02]`,
          streaming: false,
        },
      ],
      sources: [
        { num: '01', title: '钉钉多维表格自动化', type: 'source', file: 'dingtalk-table.md', score: 0.92 },
        { num: '02', title: '钉钉OpenAPI',       type: 'entity', file: 'DingtalkAPI.md',    score: 0.71 },
      ],
    },
    c4: {
      messages: [
        { sender: 'user', time: '3 天前 10:30', content: '支付系统异常如何排查？' },
        {
          sender: 'ai',
          time: '3 天前 10:30',
          content: `支付系统异常排查遵循"由外到内、由近到远"原则：

① 入口检查：确认是单用户还是全量，确认是某个支付方式还是全部。[01]

② 网关层：检查支付网关返回码，常见 4001/5002/8003 对应不同问题。[02]

③ 业务层：检查订单状态机是否卡住，幂等性是否破坏。[03]

④ 资金层：调用对账接口核对流水，必要时人工介入。`,
          streaming: false,
        },
      ],
      sources: [
        { num: '01', title: 'PaymentSystem',    type: 'entity',  file: 'PaymentSystem.md',  score: 0.85 },
        { num: '02', title: '支付网关错误码',    type: 'concept', file: 'PaymentGateway.md', score: 0.78 },
        { num: '03', title: '订单状态机',        type: 'concept', file: 'OrderStateMachine.md', score: 0.69 },
      ],
    },
  },

  /* ---------- 当前对话的消息（默认 c1，兼容旧引用） ---------- */
  get messages() {
    return this.conversationData.c1.messages;
  },
  get sources() {
    return this.conversationData.c1.sources;
  },

  /* ---------- 文档列表（documents 页面） ---------- */
  documents: [
    { title: 'IAP退款流程',          type: 'source',    date: '2024-03-15', tags: ['IAP', '退款'],         file: 'iap-refund-flow.md' },
    { title: 'PaymentSystem',         type: 'entity',    date: '2024-03-10', tags: ['支付', 'IAP'],         file: 'PaymentSystem.md' },
    { title: 'UserCenter',            type: 'entity',    date: '2024-03-08', tags: ['用户'],                file: 'UserCenter.md' },
    { title: '投放策略优化',          type: 'source',    date: '2024-02-28', tags: ['投放', '广告'],         file: 'ad-strategy.md' },
    { title: '钉钉多维表格自动化',     type: 'source',    date: '2024-02-20', tags: ['钉钉', '自动化'],       file: 'dingtalk-table.md' },
    { title: 'RefundPolicy',          type: 'concept',   date: '2024-02-15', tags: ['退款', '政策'],         file: 'RefundPolicy.md' },
    { title: 'AdChannelSelection',    type: 'concept',   date: '2024-02-10', tags: ['投放', '渠道'],         file: 'AdChannelSelection.md' },
    { title: 'IAP系统综合分析',        type: 'synthesis', date: '2024-03-20', tags: ['IAP', '总结'],         file: 'IAP系统综合分析.md' },
  ],

  /* ---------- 当前文档详情（documents 详情区） ---------- */
  documentDetail: {
    title: 'IAP退款流程',
    type: 'source',
    date: '2024-03-15',
    sourceFile: 'raw/IAP系统/退款流程.md',
    tags: ['IAP', '退款', '支付'],
    summary: 'IAP 系统退款流程包括用户发起、系统校验、退款执行三个核心步骤，需在 7 天退款期内完成。',
    sections: [
      {
        heading: '核心论点',
        body: `退款必须在订单创建后 7 天内发起；退款金额按原支付金额原路返回；已发货订单需先回收货物才能退款；退款失败自动重试 3 次，超限转人工处理。`,
      },
      {
        heading: '重要引述',
        body: `"退款流程的设计目标是让用户在最少的操作步骤内完成退款，同时保证商家资金安全。" — IAP 系统设计文档`,
      },
      {
        heading: '关键流程',
        body: `1. 用户在订单列表选择需要退款的订单，点击"申请退款"。
2. 填写退款原因、退款金额，提交申请。
3. 系统校验订单状态（已支付、未超过退款期、未发货或已退货）。
4. 校验通过后，退款进入处理队列，由支付网关执行原路返回。
5. 用户在 3-5 工作日后查看退款到账状态。`,
      },
    ],
    relations: {
      outgoing: ['PaymentSystem', 'UserCenter', 'RefundPolicy'],
      incoming: ['IAP系统综合分析'],
    },
  },

  /* ---------- 图谱节点（graph 页面） ---------- */
  graphNodes: [
    { id: 'n1', label: 'IAP退款',       type: 'source',    x: 400, y: 240, size: 28 },
    { id: 'n2', label: 'PaymentSystem', type: 'entity',    x: 200, y: 340, size: 26 },
    { id: 'n3', label: 'UserCenter',    type: 'entity',    x: 600, y: 340, size: 26 },
    { id: 'n4', label: 'RefundPolicy',  type: 'concept',   x: 300, y: 480, size: 22 },
    { id: 'n5', label: 'IAP系统综合',   type: 'synthesis', x: 400, y: 100, size: 30 },
    { id: 'n6', label: '投放策略',      type: 'source',    x: 750, y: 180, size: 26 },
    { id: 'n7', label: 'AdChannel',     type: 'concept',   x: 850, y: 380, size: 22 },
    { id: 'n8', label: '钉钉自动化',    type: 'source',    x: 150, y: 150, size: 24 },
  ],

  graphEdges: [
    { source: 'n1', target: 'n2', type: '引用' },
    { source: 'n1', target: 'n3', type: '引用' },
    { source: 'n1', target: 'n4', type: '关联' },
    { source: 'n5', target: 'n1', type: '综合' },
    { source: 'n5', target: 'n2', type: '关联' },
    { source: 'n6', target: 'n7', type: '关联' },
    { source: 'n8', target: 'n3', type: '提到' },
  ],

  /* ---------- 搜索结果（search 页面） ---------- */
  searchQuery: 'IAP 退款流程',
  searchMode: 'hybrid',
  searchScope: ['source', 'entity', 'concept', 'synthesis'],
  searchResults: [
    {
      num: '01',
      title: 'IAP退款流程',
      type: 'source',
      file: 'iap-refund-flow.md',
      score: 0.91,
      snippet: 'IAP 系统退款流程包括用户发起、系统校验、退款执行三个核心步骤，需在 7 天退款期内完成。退款金额按原支付金额原路返回，通常 3-5 工作日到账...',
    },
    {
      num: '02',
      title: 'PaymentSystem',
      type: 'entity',
      file: 'PaymentSystem.md',
      score: 0.74,
      snippet: '支付系统，处理 IAP、投放、订阅等所有支付场景。包含支付网关、订单管理、退款处理等核心模块...',
    },
    {
      num: '03',
      title: 'UserCenter',
      type: 'entity',
      file: 'UserCenter.md',
      score: 0.68,
      snippet: '用户中心，管理用户账号、订单、退款记录等。提供统一的用户视图与历史查询接口...',
    },
    {
      num: '04',
      title: 'IAP系统综合分析',
      type: 'synthesis',
      file: 'IAP系统综合分析.md',
      score: 0.62,
      snippet: '综合 IAP 系统设计、退款流程、用户体验等维度的整体分析。提出三项优化建议：缩短退款周期、增加进度通知、提供多渠道退款...',
    },
    {
      num: '05',
      title: 'RefundPolicy',
      type: 'concept',
      file: 'RefundPolicy.md',
      score: 0.55,
      snippet: '退款政策概念页。定义 7 天退款期、原路返回、人工审核触发条件等核心规则。适用于所有支付场景的退款...',
    },
  ],

  /* ---------- 搜索历史 ---------- */
  searchHistory: [
    'IAP 退款流程',
    '投放策略优化',
    '钉钉多维表格',
    '支付系统异常处理',
    '用户中心字段定义',
  ],
};

// 暴露到全局
window.MOCK = MOCK;
