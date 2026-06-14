# 工作知识库 · Editorial Knowledge Base 原型

> Editorial Knowledge Base 设计风格的桌面客户端原型。完全离线，无 CDN 依赖。

## 设计哲学

把"AI 工具"做成"编辑级知识档案"——给老板和评委"我们有沉淀"的感觉，而不是"做了个聊天框"。

**记忆点**：
- 中文宋体标题（系统自带 Songti SC / SimSun）
- 暖米色背景 `#FAF8F3`（不是纯白）
- 单一琥珀色强调 `#B45309`（不是蓝紫渐变）
- 编号化导航（01-04，编辑感）
- 严格 12 列网格 + 6px 圆角

## 文件结构

```
prototype/
├── index.html            ← 默认入口：知识图谱（Sidebar + 中间图谱）
├── chat.html             ← AI 对话（智能问答，慢、有 AI 综合）
├── documents.html        ← 文档管理（wiki/ 浏览 + Markdown 详情）
├── search.html           ← 全局搜索（纯检索，快、无 AI）
└── assets/
    ├── style.css         ← Editorial 设计系统
    ├── sidebar.js        ← 共享 Sidebar 组件
    └── mock-data.js      ← mock 数据（来自现有 wiki/）
```

## 四个模块的职责（重要！）

| 模块 | 职责 | 调用 AI | 延迟 | 适合场景 |
|---|---|---|---|---|
| **图谱**（默认入口） | 可视化实体关系，发现知识结构 | 否 | 即时 | 浏览全局、发现关联 |
| **对话** | AI 综合多个 wiki 页面生成自然语言回答 | ✅ Claude | 慢（秒级） | "IAP 怎么退款？" |
| **文档** | 浏览 wiki/ 树形结构，查看 Markdown 详情 | 否 | 即时 | 找特定页面、读完整内容 |
| **搜索** | 关键词/向量混合检索，返回页面列表 | 否 | 快（毫秒） | 精准定位、不想要 AI 生成 |

### 对话 vs 搜索的明确分工

**两者都会做"检索 wiki 页面"这一步**，但产出不同：

- **对话**：用户问"IAP 怎么退款？" → AI 综合多个 wiki 页面 → 输出一段自然语言答案 + `[01][02][03]` 引用
- **搜索**：用户输入"IAP 退款" → 直接返回匹配的页面列表（不生成回答）→ 用户点击进入详情

如果用户只是想找某个文档，搜索更快；如果用户想要答案，对话更智能。

## 如何打开

```bash
# Windows
start "" "D:/AI/知识库设计/prototype/index.html"

# 或者直接双击文件
D:\AI\知识库设计\prototype\index.html
```

完全离线，断网也能用（系统字体 + 内嵌 SVG + 内嵌 mock 数据）。

## 跨页面跳转关系

```
                  ┌──────────────┐
                  │  index.html  │
                  │  (知识图谱)   │
                  └──────┬───────┘
                         │
         ┌───────────────┼───────────────┬──────────────┐
         ↓               ↓               ↓              ↓
    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  chat   │←──→│documents│←──→│  graph  │←──→│ search  │
    └─────────┘    └─────────┘    └─────────┘    └─────────┘
         │              │              │              │
         └──── 引用 [01] 点击 → documents 详情 ──────┘
                        ↑
                graph 节点点击 / search 结果点击
                        ↓
                documents 详情（核心枢纽）
```

**documents 详情是核心枢纽**——其他三个页面的查询结果最终都跳转到它。

## 技术栈

- **HTML5** + **CSS3**（CSS Variables + Grid + Flexbox）
- **原生 JavaScript**（ES6+，无框架）
- **系统字体栈**（Songti SC / SimSun / Georgia / -apple-system / Consolas）
- **内嵌 SVG**（图谱可视化）
- **Mock 数据**来自现有 `工作知识库/llm-wiki-agent/wiki/`

无构建工具，无 npm install，无 CDN——双击即开。

## 后续计划

这是 **PLAN.md Phase 0** 之前的设计原型。完整产品规划见：
- `D:/AI/知识库设计/PLAN.md` — 完整升级路线图（5 个 Phase）
- `D:/AI/知识库设计/mydocs/specs/2026-06-14_12-44_知识库客户端原型设计.md` — 本原型的 SDD Spec
