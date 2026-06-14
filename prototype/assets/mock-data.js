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

  /* ---------- 对话历史 ---------- */
  conversations: [
    { id: 'c1', title: 'IAP 退款流程', time: '12:34', active: true },
    { id: 'c2', title: '投放策略优化', time: '昨天', active: false },
    { id: 'c3', title: '钉钉多维表格', time: '昨天', active: false },
    { id: 'c4', title: '支付系统异常', time: '3 天前', active: false },
  ],

  /* ---------- 当前对话的消息 ---------- */
  messages: [
    {
      sender: 'user',
      time: '12:34',
      content: 'IAP 系统怎么处理退款？',
    },
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

  /* ---------- 引用的来源页面（chat 抽屉展示） ---------- */
  sources: [
    { num: '01', title: 'IAP退款流程',     type: 'source',     file: 'iap-refund-flow.md',   score: 0.91 },
    { num: '02', title: 'PaymentSystem',   type: 'entity',     file: 'PaymentSystem.md',     score: 0.74 },
    { num: '03', title: 'UserCenter',      type: 'entity',     file: 'UserCenter.md',        score: 0.68 },
  ],

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
