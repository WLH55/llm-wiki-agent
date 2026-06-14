# LLM Wiki Pro — 产品升级计划

## Context

当前 `工作知识库/llm-wiki-agent` 是一个基于 Python 的 Markdown 知识管理工具，通过 Claude Code 终端使用。存在以下痛点：

- **黑箱状态**：知识检索准确率、编译质量、图结构正确性无法量化验证
- **仅终端可用**：没有可视化界面，不适合非技术人员（如老板）使用
- **全靠 AI 发挥**：无法作为生产级应用，缺乏评估体系

**目标**：升级为团队级知识库产品，参加公司 AI 比赛。面向两类用户——管理者（可视化界面 + 数据安全）和开发者（MCP 工具集成）。保留本地优先、纯文件存储的核心优势。

---

## 已确认的技术决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 前端框架 | React / Next.js | 全栈框架，API Routes 即后端，不分前后端项目 |
| 后端语言 | TypeScript (Next.js API) | 前后端语言统一，与 Python 工具链通过桥接调用 |
| AI 对话集成 | 后端代理转发 | WebSocket 双向通信，后端管理 CLI 子进程 |
| 向量数据库 | LanceDB | 纯文件存储，零服务进程，与 Markdown 文件架构一致 |
| 桌面打包 | Tauri | 体积小(~10MB)，用系统 WebView，双击即开 |
| 部署形态 | 本地 + 内网 Docker | 个人用桌面版，团队用内网部署 |
| 多租户 | 不做 | 参赛阶段不需要，文件系统天然隔离满足多知识库需求 |
| 评估体系 | 完整评估 | 参赛核心竞争力，量化证明系统有效 |

---

## 开发阶段与优先级

### Phase 0：Claude Code 代理转发（第 1-2 周）

**目标**：最快可验证路径——在 Web 界面里通过 Claude Code 对话。

**产出**：
- Next.js 项目骨架（`app/` 目录）
- WebSocket 对话接口（`app/src/app/api/chat/`）
- CLI 进程管理模块（`app/src/lib/cli-proxy.ts`）
- 最简对话 UI（消息输入框 + 流式输出渲染）

**原理**：
```
用户在 Web 对话框输入
  → Next.js 后端收到 WebSocket 消息
  → 后端启动/复用 Claude Code 子进程
  → 消息转发到 CLI stdin
  → CLI stdout 实时回传
  → 后端解析后通过 WebSocket 推送到前端
  → 前端渲染 AI 回复
```

**关键文件**：
- `app/package.json` — Next.js 项目配置
- `app/src/lib/cli-proxy.ts` — CLI 子进程生命周期管理（启动、通信、销毁）
- `app/src/app/api/chat/route.ts` — WebSocket 端点
- `app/src/app/chat/page.tsx` — 对话页面
- `app/src/components/ChatPanel.tsx` — 对话面板组件

---

### Phase 1：评估体系（第 2-4 周）

**目标**：量化证明知识库系统有效，参赛核心数据支撑。

#### 1.1 测试集

| 数据集 | 文件 | 内容 |
|--------|------|------|
| 检索测试集 | `eval/datasets/retrieval-test-set.json` | 每条：query + 期望命中的页面列表 + 相关度评分 |
| 编译测试集 | `eval/datasets/compilation-test-set.json` | 每条：raw 输入 + 期望 wiki 页面包含的关键信息 |
| 图结构测试集 | `eval/datasets/graph-test-set.json` | 每条：页面集合 + 期望的实体关系边 |

#### 1.2 评估指标

| 维度 | 指标 | 说明 |
|------|------|------|
| 检索准确率 | P@k, R@k, MRR, nDCG@k | 参考 gbrain 的 `src/core/eval/metric-glossary.ts` |
| 编译质量 | 信息覆盖率、冗余率 | 对比 AI 生成的 wiki 页面与期望结果的覆盖程度 |
| 图结构 | 精确率、召回率 | 对比生成图与期望图的实体关系匹配度 |

#### 1.3 评估工具

| 脚本 | 说明 |
|------|------|
| `tools/eval_retrieval.py` | 检索评估：计算 P@k, R@k, MRR, nDCG@k |
| `tools/eval_compilation.py` | 编译质量评估：对比生成结果与期望结果 |
| `tools/eval_graph.py` | 图结构评估：对比生成图与期望图 |
| `tools/eval_runner.py` | 统一评估运行器：执行全部评估、生成报告 |

---

### Phase 2：Next.js 可视化界面 + 向量检索（第 3-8 周）

#### 2.1 项目结构

```
app/                              ← Next.js 项目根目录
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── src/
│   ├── app/                      ← App Router 页面
│   │   ├── layout.tsx            ← 全局布局（侧边栏 + 主内容区）
│   │   ├── page.tsx              ← 首页/仪表盘
│   │   ├── documents/            ← 文档管理模块
│   │   │   ├── page.tsx          ← 文档列表（树形 + 列表视图）
│   │   │   └── [slug]/page.tsx   ← 文档详情页
│   │   ├── graph/                ← 知识图谱模块
│   │   │   └── page.tsx          ← 力导向图可视化（D3.js / react-force-graph）
│   │   ├── chat/                 ← AI 对话模块
│   │   │   └── page.tsx          ← 对话界面
│   │   ├── settings/             ← 系统设置
│   │   │   └── page.tsx          ← 知识库配置、CLI 配置
│   │   └── api/                  ← API Routes
│   │       ├── documents/        ← 文档 CRUD 接口
│   │       ├── search/           ← 混合搜索接口
│   │       ├── graph/            ← 图谱数据接口
│   │       ├── chat/             ← WebSocket 对话代理
│   │       └── mcp/              ← MCP 服务端点
│   ├── components/               ← 共享组件
│   │   ├── Sidebar.tsx           ← 导航侧边栏
│   │   ├── DocTree.tsx           ← 文档树组件（类钉钉知识库）
│   │   ├── ChatPanel.tsx         ← 对话面板
│   │   ├── GraphView.tsx         ← 图谱可视化
│   │   └── SearchBar.tsx         ← 全局搜索
│   ├── lib/                      ← 核心业务逻辑
│   │   ├── wiki-store.ts         ← Markdown 文件读写层
│   │   ├── vector-store.ts       ← LanceDB 操作层
│   │   ├── hybrid-search.ts      ← 混合检索（关键词 + 向量）
│   │   ├── cli-proxy.ts          ← CLI 进程管理
│   │   ├── graph-builder.ts      ← 图谱构建与查询
│   │   └── mcp-server.ts         ← MCP Server 实现
│   └── types/
│       └── wiki.ts               ← 知识库核心类型
```

#### 2.2 文档管理视图（类钉钉知识库）

- 读取 `wiki/` 目录结构，按 type（source/entity/concept/synthesis）分类展示
- 树形导航 + 内容预览 + Markdown 渲染
- 支持从 Web 界面触发导入、刷新、lint 操作
- 文档详情页：Markdown 渲染、元信息展示、关联页面链接

#### 2.3 知识图谱可视化

- 基于 D3.js 力导向图或 react-force-graph
- 数据源复用 `graph/graph.json`
- 支持节点点击查看详情、边类型筛选、搜索高亮

#### 2.4 AI 对话窗口

- WebSocket 双向通信
- 后端通过 `cli-proxy.ts` 管理 Claude Code 子进程
- 对话中自动注入知识库上下文（检索相关 wiki 页面后附到 prompt）

#### 2.5 MCP 工具注册

- `app/src/lib/mcp-server.ts` — 暴露标准 MCP 协议的搜索、查询接口
- 开发者在 Claude Code 中 `claude mcp add llm-wiki -- node app/dist/mcp-server.js`
- 复用 `hybrid-search.ts` 的检索能力

---

### Phase 2（并行）：向量检索能力（第 2-4 周）

#### 检索架构

```
用户查询
  ├── 关键词检索（BM25 / 现有 query.py）
  ├── 向量检索（LanceDB 语义相似度）
  └── 融合排序（Reciprocal Rank Fusion）
      └── 返回 Top-K 结果
```

参考 gbrain 的 `docs/architecture/RETRIEVAL.md` 和 `src/core/search/hybrid.ts` 的融合思路，但用 LanceDB 替代 pgvector。

#### 关键文件

| 文件 | 说明 |
|------|------|
| `app/src/lib/vector-store.ts` | LanceDB 抽象层：建表、写入向量、相似度搜索 |
| `app/src/lib/hybrid-search.ts` | 混合检索：关键词 + 向量，RRF 融合排序 |
| `tools/embed.py` | 为现有 wiki 页面生成 embedding，初始化 LanceDB |

#### 与现有 Python 工具链的桥接

前期 TypeScript 后端通过 `child_process` 调用现有 Python 脚本，保留已有代码。后续根据需要逐步将核心模块迁移到 TypeScript。

---

### Phase 3：Mini Agent（第 6-8 周）

**目标**：替换 Claude Code 代理，降低 token 消耗 3-5 倍。

**原理**：
```
Claude Code（通用编程 Agent）：
  系统提示词 ~10k+ tokens（编程、文件操作、Git...）
  20+ 工具（bash, edit, glob, grep...）
  → 大量 token 浪费在无关上下文

Mini Agent（知识库专用）：
  系统提示词 ~2-3k tokens（仅知识库操作规则）
  5-8 个专用工具（search_wiki, ingest, build_graph...）
  → 精准、快速、低成本
```

**实现方式**：
- 直接调用 Claude API（Anthropic SDK），自定义系统提示词 + 工具定义
- 工具：`search_wiki`、`ingest_document`、`build_graph`、`lint_wiki`、`refresh_wiki`、`get_page`、`list_pages`
- 对话窗口直接对接 Mini Agent，不再走 Claude Code 中转

---

### Phase 4：桌面打包 + 内网部署（第 7-9 周）

#### 4.1 Tauri 桌面应用

**原理**：
```
Tauri 壳（Rust，~3MB）
  ├── 启动 Next.js 服务器进程（localhost:3000）
  └── 打开系统 WebView 窗口，加载 localhost:3000
      → 用户看到的是普通桌面应用窗口
      → 看不到浏览器地址栏
      → 看不到终端黑窗口
```

用户双击图标 → 自动启动服务 → 自动打开窗口。关闭窗口 = 关闭整个应用。

**构建**：
```bash
npm run build          # 构建 Next.js
npm run tauri build    # 打包为 .exe 安装包（~5-10MB）
```

#### 4.2 Docker 内网部署

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 应用镜像 |
| `docker-compose.yml` | 一键启动：Next.js + LanceDB |
| `DEPLOY.md` | 内网部署文档 |

---

## 可插拔、可备份、快速迁移

### 知识库包标准结构

```
my-knowledge-base/              ← 一个知识库 = 一个这样的目录
├── manifest.json               ← 元信息（名称、版本、引擎配置、统计）
├── wiki/                       ← Markdown 知识页面
├── graph/                      ← 图谱数据（JSON + HTML）
├── raw/                        ← 原始文档
└── vectors/                    ← LanceDB 向量数据（也是本地文件）
```

### 核心操作

| 操作 | 命令 | 说明 |
|------|------|------|
| 挂载 | `llm-wiki plug <路径>` | 挂载一个知识库目录 |
| 卸载 | `llm-wiki unplug` | 卸载当前知识库（数据不动） |
| 列出 | `llm-wiki list` | 列出已注册的知识库 |
| 切换 | `llm-wiki switch <名称>` | 切换到指定知识库 |
| 快照 | `llm-wiki snapshot` | 打包整个知识库为 .zip |
| 恢复 | `llm-wiki restore <zip>` | 从快照恢复 |
| 导出 | `llm-wiki export` | 导出知识内容（不含应用配置） |
| 导入 | `llm-wiki import <zip>` | 导入到另一个实例 |

### manifest.json 示例

```json
{
  "name": "工作知识库",
  "id": "kb-work-2026",
  "version": "1.0.0",
  "created": "2026-01-15",
  "engine": {
    "type": "lancedb",
    "embedding_model": "text-embedding-3-small",
    "dimension": 1536
  },
  "stats": {
    "sources": 12,
    "entities": 8,
    "concepts": 15,
    "syntheses": 2
  }
}
```

---

## 对 gbrain 的参考与借鉴

| gbrain 的做法 | 是否采纳 | 我们的方案 |
|---------------|---------|-----------|
| pgvector 向量检索 | ❌ 不采纳 | LanceDB（文件存储，零服务） |
| 全数据库存储 | ❌ 不采纳 | 保持 Markdown 文件 + LanceDB 文件 |
| 混合搜索（关键词 + 向量 + RRF 融合）| ✅ 采纳 | 相同思路，LanceDB 替代 pgvector |
| 可插拔引擎（Engine 接口） | ✅ 借鉴 | 应用与数据分离，知识库即数据包 |
| 15 种页面类型 | ❌ 不采纳 | 保持现有 4 种（source/entity/concept/synthesis），按需扩展 |
| OAuth 2.1 多租户 | ❌ 不采纳 | 文件系统级隔离，多知识库切换 |
| 评估方法论（metric glossary + eval） | ✅ 借鉴 | 建立自己的评估体系和测试集 |
| 知识图谱（自动提取关系边） | ✅ 采纳 | 复用现有 build_graph.py，增加正确性验证 |

---

## 时间线总览

| 周 | 阶段 | 产出 |
|----|------|------|
| 1-2 | Phase 0：Claude Code 代理 | Web 对话界面 + CLI 代理转发 |
| 2-4 | Phase 1：评估体系 | 测试集 + 评估脚本 + 基线数据 |
| 2-4 | Phase 2（并行）：向量检索 | LanceDB 集成 + 混合搜索 + 检索对比报告 |
| 3-8 | Phase 2：可视化界面 | 文档管理 + 图谱 + 对话 + MCP |
| 6-8 | Phase 3：Mini Agent | 自建轻量 AI Agent 替换 Claude Code 代理 |
| 7-9 | Phase 4：部署打包 | Tauri 桌面版 + Docker 内网部署 |

---

## 验证方式

### Phase 0 验证
- 在浏览器打开 `http://localhost:3000/chat`，能发送消息并收到 Claude Code 的流式回复
- 关闭页面后 CLI 进程自动清理

### Phase 1 验证
- `python tools/eval_runner.py` 输出完整评估报告
- 检索 P@5 > 0.6（目标值，后续根据基线调整）
- 编译信息覆盖率 > 0.8
- 图结构 F1 > 0.7

### Phase 2 验证
- 文档管理页面能展示 wiki 目录树，点击可查看 Markdown 渲染内容
- 知识图谱页面展示力导向图，节点可点击
- MCP 注册后在 Claude Code 中能调用 `search_wiki` 工具
- 混合搜索的检索准确率优于纯关键词（评估集验证）

### Phase 3 验证
- Mini Agent 对话响应延迟 < Claude Code 代理的 50%
- Token 消耗 < Claude Code 代理的 1/3
- 功能覆盖：查询、导入、图谱构建、lint

### Phase 4 验证
- Tauri 打包后的 .exe 双击可正常打开
- Docker 部署后团队成员可浏览器访问
- 知识库 export → import 后数据完整无损
