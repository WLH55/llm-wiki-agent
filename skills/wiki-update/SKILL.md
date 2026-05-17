---
name: wiki-update
description: >
  将当前项目的知识同步到 LLM Wiki 知识库。当用户说"更新 wiki"、"同步到 wiki"、
  "保存到我的知识库"、或者想要将工作中的收获提炼到知识库时使用。
  可从任意项目目录工作。
---

# Wiki Update — 从任意项目同步知识

你正在将当前项目的知识提炼到用户的 LLM Wiki 知识库中。
此技能可在任意项目目录下工作。

## 开始之前

1. **解析配置** — 遵循 `llm-wiki/SKILL.md` 中的配置解析协议，获取 `$LLM_WIKI_PATH`。
2. 读取 `$LLM_WIKI_PATH/wiki/index.md` 了解知识库已有的内容。
3. 读取 `$LLM_WIKI_PATH/wiki/overview.md` 获取当前综合上下文。

## 第一步：理解项目

通过扫描当前工作目录弄清楚这个项目是什么：

- `README.md`、docs/、任何 markdown 文件
- 源代码结构（框架、语言、关键抽象）
- `package.json`、`pyproject.toml`、`go.mod`、`Cargo.toml` 等定义项目的文件
- Git log（关注标志决策的 commit 信息，而非"修复拼写"类）
- Claude 记忆文件（如果项目中存在 `.claude/`）

从目录名派生一个清晰的项目名称，用作来源页的 slug。

## 第二步：判断值得提炼的知识

核心问题：**如果你三个月后零上下文地回到这个项目，你会想知道什么？**

值得提炼：

- 架构决策及其*为什么*这样做
- 构建过程中发现的模式（你以后会重新 Google 的东西）
- 项目依赖的工具、服务、API 以及它们如何连接
- 关键抽象及其连接方式、心智模型
- 评估过的权衡方案，最终选择了什么及其原因
- 构建中学到的东西，仅读代码看不出来

不值得提炼：

- 文件列表、样板代码、显而易见的配置
- 没有广泛教训的单个 bug 修复
- 依赖版本号、lock 文件内容
- 代码本身已经说清楚了的实现细节
- 任何人读 diff 就能理解的日常修改

判断标准：**如果读代码就能回答，不要写进 wiki。如果要翻 20 个 commit 的 git blame 才能推导出推理过程，写进 wiki。**

## 第三步：提炼为 Wiki 页面

### 项目特定知识

放入 `$LLM_WIKI_PATH/wiki/sources/` 作为来源页：

- 用项目名作为 slug（kebab-case）：`wiki/sources/<项目名>.md`
- 遵循 `llm-wiki/SKILL.md` 中的**来源页格式**
- `source_file` 字段引用项目路径或关键文件

### 通用知识

非项目特有的内容放入全局分类：

| 发现的内容 | 存放位置 |
|---|---|
| 学到的通用概念 | `wiki/concepts/` |
| 可复用的模式或技术 | `wiki/concepts/` |
| 工具/服务/人物 | `wiki/entities/` |
| 跨项目分析 | `wiki/syntheses/` |

### 一个概念一个页面

如果页面已经存在，**合并**新信息进去。不要创建重复页面。
如果向已有页面添加内容，更新 `last_updated` 日期，并将当前项目添加到 `sources:` 列表。

创建新页面之前，先检查 `$LLM_WIKI_PATH/wiki/index.md` 看什么已经存在。

## 第四步：交叉链接

创建/更新页面后：

- 从新页面向已有相关页面添加 `[[wikilinks]]`
- 从已有页面向新页面添加回链（相关的）
- 检查 `## 矛盾` 章节 — 如果新知识与已有页面矛盾，记录下来

## 第五步：更新索引和概览

- 在 `$LLM_WIKI_PATH/wiki/index.md` 的相应章节中添加新页面的条目
- 如果更新改变了某个主题的整体理解，修订 `overview.md`

## 第六步：更新日志

追加到 `$LLM_WIKI_PATH/wiki/log.md`：

```
## [YYYY-MM-DD] update | 从 <项目名> 同步知识
```

## 第七步：验证

```bash
python $LLM_WIKI_PATH/tools/ingest.py --validate-only
```

修复发现的断链或未索引页面。

## 第八步：重建图谱

```bash
python $LLM_WIKI_PATH/tools/build_graph.py
```

这会用新页面和边更新 `graph/graph.json` 和 `graph/graph.html`。

## 第九步：报告

告知用户完成了什么：
- 创建的页面（含路径）
- 更新的页面
- 新增的 `[[wikilinks]]`
- 发现的矛盾
- 验证结果

## 提示

- **积极合并。** 如果项目使用 React Server Components，不要创建新页面如果 `concepts/ReactServerComponents.md` 已存在。更新已有的。
- **不要复制代码。** 提炼的是*知识*，不是实现。"这个项目使用了 300ms 延迟的 debounced 搜索模式"是有用的。粘贴 debounce 函数本身不是。
- **使用 wiki 的命名规范。** 实体和概念用 TitleCase。来源用 kebab-case。
- **frontmatter 是强制的。** 每个新页面必须有其类型对应的必需 YAML frontmatter（参见 `llm-wiki/SKILL.md`）。
