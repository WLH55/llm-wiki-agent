---
name: wiki-setup
description: >
  初始化和管理 LLM Wiki 设置。当用户说"wiki-setup"、"setup wiki"、"初始化 wiki"、
  "安装 wiki skills"、"创建新知识库"、"setup llm-wiki"时使用。
  将全局技能安装到 Claude Code 和 OpenCode 目录，注册知识库配置，创建新的知识库项目骨架。
---

# Wiki Setup — 安装与初始化

此技能处理三项操作：安装全局技能、注册已有知识库、从头创建新知识库。

## 调度表

| 命令 | 操作 |
|---|---|
| `/wiki-setup install` | → **安装** — 将技能复制到全局目录 |
| `/wiki-setup init <路径>` | → **注册** — 注册已有知识库 |
| `/wiki-setup new` | → **新建知识库** — 创建新的知识库项目 |
| `/wiki-setup`（无参数） | → **引导设置** — 检测当前状态并引导用户 |

---

## 引导设置（默认）

无参数调用时，检测当前状态并引导：

1. 检查 `~/.llm-wiki/active` 是否存在 → 如果存在，显示当前知识库并询问要做什么
2. 如果当前目录看起来像一个 wiki 项目（有 `wiki/` 和 `tools/` 目录）→ 建议 `init .`
3. 否则 → 询问用户想要：安装技能 / 注册知识库 / 创建新知识库

---

## 安装 — 复制技能到全局目录

将所有 wiki 技能目录复制到 Claude Code 和 OpenCode 的全局技能目录。

### 第一步：定位源目录

技能源目录即当前项目的 `skills/` 目录。将其记为 `$SKILL_SOURCE`。
技能源目录必须包含以下子目录：
- `llm-wiki/SKILL.md`
- `wiki-query/SKILL.md`
- `wiki-update/SKILL.md`
- `wiki-switch/SKILL.md`
- `wiki-setup/SKILL.md`

如果缺少任何一个，告知用户并停止。

### 第二步：安装到 Claude Code（全局）

```bash
# 创建目标目录（如不存在）
mkdir -p ~/.claude/skills

# 复制每个技能目录
cp -r "$SKILL_SOURCE/llm-wiki" ~/.claude/skills/
cp -r "$SKILL_SOURCE/wiki-query" ~/.claude/skills/
cp -r "$SKILL_SOURCE/wiki-update" ~/.claude/skills/
cp -r "$SKILL_SOURCE/wiki-switch" ~/.claude/skills/
cp -r "$SKILL_SOURCE/wiki-setup" ~/.claude/skills/
```

### 第三步：安装到 OpenCode（全局）

OpenCode 兼容读取 `~/.claude/skills/`，也支持原生路径 `~/.config/opencode/skills/`。安装到 Claude Code 目录即可同时覆盖两者。

### 第四步：报告

```
技能已安装到全局：
  ~/.claude/skills/llm-wiki/
  ~/.claude/skills/wiki-query/
  ~/.claude/skills/wiki-update/
  ~/.claude/skills/wiki-switch/
  ~/.claude/skills/wiki-setup/

下一步：运行 /wiki-setup init <知识库路径> 注册你的知识库。
```

---

## 注册 — 关联已有知识库

注册一个知识库项目，使全局技能能够找到它。

### 用法

```
/wiki-setup init <路径>
```

### 步骤

1. 验证 `<路径>` 存在且包含 `wiki/` 目录。
   如果不存在，警告用户但仍继续（用户可能指向一个空的新知识库）。

2. 询问配置名称（默认：`primary`）。

3. 如果 `~/.llm-wiki/` 目录不存在，创建它。

4. 写入配置文件：

   ```bash
   echo 'LLM_WIKI_PATH=<路径>' > ~/.llm-wiki/config.<名称>
   ```

5. 设为活跃：

   ```bash
   echo '<名称>' > ~/.llm-wiki/active
   ```

6. 确认：

   ```
   知识库已注册：<名称>
   路径：<路径>
   配置：~/.llm-wiki/config.<名称>
   
   当前活跃知识库：<名称>
   试试：/wiki-query "我的知识库中有哪些主题？"
   ```

---

## 新建知识库 — 创建新知识库项目

从当前项目复制骨架结构来创建新的知识库项目。

### 用法

```
/wiki-setup new
```

### 步骤

1. 询问用户**目标路径**，新知识库的创建位置（如 `D:/AI/work-wiki`）。

2. 询问**配置名称**（如 `work`）。

3. 如果目标目录不存在，创建它。

4. 复制项目骨架（目录和文件，**不复制 `.git/` 和 `.venv/`**）：

   ```
   从当前项目复制到 <目标>：
   
   目录结构：
     wiki/               ← wiki 根目录
     wiki/sources/       ← 来源页目录
     wiki/entities/      ← 实体页目录
     wiki/concepts/      ← 概念页目录
     wiki/syntheses/     ← 综合页目录
     tools/              ← 所有 Python 工具脚本
     raw/                ← 原始文档目录
     graph/              ← 图谱输出目录
   
   文件：
     .gitignore
     pyproject.toml
     CLAUDE.md
     AGENTS.md
     GEMINI.md
     README.md
     LICENSE
   
   不复制：
     .git/
     .venv/
     .idea/
     __pycache__/
     hs_err_pid*.log
     wiki/*/中的实际内容页面（只复制空目录结构，不复制实际 wiki 页面）
   ```

5. 创建最小的 `wiki/index.md`：

   ```markdown
   # Wiki 索引
   
   ## 概览
   - [概览](overview.md) — 持续更新的综合摘要
   
   ## 来源
   
   ## 实体
   
   ## 概念
   
   ## 综合
   ```

6. 创建空的 `wiki/overview.md` 和 `wiki/log.md`。

7. 注册新知识库（同上面的**注册**）：
   - 创建 `~/.llm-wiki/config.<名称>`
   - 设为活跃

8. 确认：

   ```
   新知识库已创建：<目标>
   配置名称：<名称>
   
   结构已就绪。下一步：
   1. cd <目标>
   2. pip install -e .
   3. 将文档放入 raw/ 后运行 /wiki-ingest
   
   当前活跃知识库：<名称>
   ```
