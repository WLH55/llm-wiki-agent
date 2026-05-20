# LLM Wiki Agent

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

一个面向代理的 Markdown 知识库工作流。

你把源文档放进 `raw/`，代理负责导入、提炼、交叉引用、构建图谱，并持续维护 `wiki/`。无数据库，无服务端，全部内容都是本地文件。

![知识图谱预览](docs/images/graph-preview.png)

## 这是什么

这个仓库同时扮演两种角色：

- 一个可直接使用的知识库项目
- 一个可复制、可扩展的知识库模板

核心目录：

```text
wiki/
├── index.md
├── overview.md
├── log.md
├── sources/
├── entities/
├── concepts/
└── syntheses/
graph/
├── graph.json
├── graph.html
└── .refresh_cache.json
raw/
tools/
```

## 安装

前置条件：任一可读取规则文件的代理，如 Claude Code、Codex、OpenCode、Gemini CLI。

Python 要求：`>=3.10, <3.14`

```bash
git clone https://github.com/WLH55/llm-wiki-agent.git
cd llm-wiki-agent
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate
# macOS / Linux
# source .venv/bin/activate
pip install -e .
```

## 代理入口

- Claude Code：读取 `CLAUDE.md` 和 `.claude/commands/`
- Codex / OpenCode：读取 `AGENTS.md`
- Gemini CLI：读取 `GEMINI.md`

工作流分两类：

| 类型 | 用途 |
|---|---|
| 仓库内工作流 | `wiki-ingest`、`wiki-lint`、`wiki-graph`、`wiki-refresh` |
| 全局 skill | `wiki-query`、`wiki-update`、`wiki-switch`、`wiki-setup` |

说明：`wiki-query`、`wiki-update`、`wiki-switch` 设计为跨项目使用；`wiki-ingest`、`wiki-lint`、`wiki-graph`、`wiki-refresh` 主要在知识库项目目录中执行。

以下示例使用 Claude 风格的 `/wiki-...` 写法；其他代理执行同名 workflow 即可。

## 第一次使用

第一次使用时，先做两件事：

1. 安装全局 skill
2. 选择一个知识库进行初始化

### 1. 安装全局 skill

```text
/wiki-setup install
```

这一步会安装：

- `llm-wiki`
- `wiki-query`
- `wiki-update`
- `wiki-switch`
- `wiki-setup`

## 初始化已有知识库

适用于：你已经有一个知识库目录，只是还没注册到 `~/.llm-wiki/`。

如果当前目录就是知识库：

```text
/wiki-setup init .
```

如果知识库在别的目录：

```text
/wiki-setup init D:/AI/my-wiki
```

初始化完成后会：

- 创建 `~/.llm-wiki/config.<名称>`
- 将该名称写入 `~/.llm-wiki/active`
- 让 `wiki-query`、`wiki-update`、`wiki-switch` 能在任意项目中找到这个知识库

## 创建新的知识库

适用于：你还没有知识库，想从零创建一个新的 wiki 项目。

```text
/wiki-setup new
```

执行时会询问：

- 目标路径，例如 `D:/AI/work-wiki`
- 配置名称，例如 `work`

创建完成后会：

- 生成新的知识库骨架：`wiki/`、`raw/`、`graph/`、`tools/` 等
- 自动注册到 `~/.llm-wiki/config.<名称>`
- 自动设为当前活跃知识库

常见后续步骤：

```text
cd <目标路径>
pip install -e .
/wiki-ingest
```

## 切换不同的知识库

当你维护多个知识库时，使用 `wiki-switch` 管理它们。

常用命令：

```text
/wiki-switch
/wiki-switch list
/wiki-switch show work
/wiki-switch work
/wiki-switch new research
```

含义：

- `/wiki-switch`：查看当前活跃知识库
- `/wiki-switch list`：列出所有已注册知识库
- `/wiki-switch show work`：查看指定配置内容
- `/wiki-switch work`：切换到名为 `work` 的知识库
- `/wiki-switch new research`：新增一个命名配置，代理会继续询问知识库路径

切换时会：

- 更新全局默认配置 `~/.llm-wiki/active`
- 如果当前项目命中了 `.env`，同步更新其中的 `LLM_WIKI_PATH`

## 日常使用

### 在知识库项目目录中

```text
/wiki-ingest raw/my-notes.md
/wiki-ingest
/wiki-lint
/wiki-graph
/wiki-refresh
/wiki-refresh --force
```

用途：

- `/wiki-ingest`：导入一个文件，或批量处理 `raw/` 中的变更
- `/wiki-lint`：做结构健康检查，结构问题直接修，语义问题只报告
- `/wiki-graph`：构建或重建图谱
- `/wiki-refresh`：按 `check_stale.py` 的结果刷新新增、更新、删除来源

说明：

- 导入前会先运行 `python tools/check_stale.py --scan --json`
- 刷新流程以 `python tools/check_stale.py` 为准
- `python tools/refresh.py` 只用于列出候选，不执行实际刷新

### 在任意项目中

```text
/wiki-query "知识库中有哪些关于 xxx 的内容？"
/wiki-update
/wiki-switch list
/wiki-switch work
```

用途：

- `/wiki-query`：查询并综合回答，可选择保存为 synthesis 页面
- `/wiki-update`：把当前项目中值得长期保留的知识提炼进 wiki
- `/wiki-switch`：切换当前项目使用的知识库

## 配置模型

所有需要 `LLM_WIKI_PATH` 的流程按以下优先级解析：

1. 当前项目向上查找 `.env` 中的 `LLM_WIKI_PATH`
2. 若未找到，读取 `~/.llm-wiki/active`
3. 再读取 `~/.llm-wiki/config.<名称>`

示例：

```bash
echo 'LLM_WIKI_PATH=D:/AI/my-special-wiki' > .env
```

这意味着：

- 没有 `.env` 的项目，使用全局活跃知识库
- 有 `.env` 的项目，优先绑定自己的知识库
- `wiki-switch` 会在切换全局配置时同步更新当前项目命中的 `.env`

多知识库场景示例：

```text
project-a/.env  -> LLM_WIKI_PATH=D:/AI/wiki-a
project-b/.env  -> LLM_WIKI_PATH=D:/AI/wiki-b
无 .env 的项目   -> 使用 ~/.llm-wiki/active
```

这允许你同时打开两个不同项目，并让它们分别查询不同的知识库。

## Wiki 规则

- 系统页面：`wiki/index.md`、`wiki/overview.md`、`wiki/log.md`、`wiki/lint-report.md`
- 其他页面必须带 YAML frontmatter
- 页面之间使用 `[[PageName]]` 交叉引用
- 新信息优先合并到已有页面，不创建重复页面

命名规则：

- 源页面：严格匹配原始文件主名的 kebab-case
- 实体页面：`TitleCase.md`
- 概念页面：`TitleCase.md`

## 工具脚本

| 脚本 | 用途 |
|---|---|
| `python tools/ingest.py --validate-only` | 验证 wiki 完整性 |
| `python tools/query.py "问题"` | 关键词匹配候选页面 |
| `python tools/lint.py` | 结构健康检查 |
| `python tools/build_graph.py` | 构建图谱 |
| `python tools/check_stale.py --scan` | 检测 raw 的新增/更新/删除 |
| `python tools/check_stale.py` | 检测已导入来源是否过期 |
| `python tools/check_stale.py --update` | 刷新完成后更新缓存 |
| `python tools/refresh.py` | 仅列出过期来源候选 |
| `python tools/pdf2md.py <pdf/arxiv>` | PDF/arXiv 转 Markdown |
| `python tools/file_to_markdown.py <目录>` | 批量转换非 md 文件 |

## 模式文件

这些文件定义代理在不同环境下的工作规则：

| 代理 | 文件 |
|---|---|
| Claude Code | `CLAUDE.md` |
| Codex / OpenCode | `AGENTS.md` |
| Gemini CLI | `GEMINI.md` |

## 许可证

MIT，见 [LICENSE](LICENSE)。

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=WLH55/llm-wiki-agent&type=date)](https://star-history.com/#WLH55/llm-wiki-agent&Date)
