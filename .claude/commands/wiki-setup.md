初始化和管理 LLM Wiki 设置。

用法：
- `/wiki-setup install` — 将 wiki Skill 安装到全局目录
- `/wiki-setup init <路径>` — 注册已有知识库
- `/wiki-setup new` — 创建新的知识库项目
- `/wiki-setup` — 无参数时检测当前状态并引导用户

根据 `$ARGUMENTS` 分支执行。

---

## 默认模式（`$ARGUMENTS` 为空）

1. 检查 `~/.llm-wiki/active` 是否存在。
2. 如果存在：
   - 读取当前活跃配置名。
   - 如果对应的 `~/.llm-wiki/config.<名称>` 存在，读取其中的 `LLM_WIKI_PATH`。
   - 告知用户当前活跃知识库名称和路径。
   - 询问用户下一步要执行：`install`、`init <路径>` 还是 `new`。
3. 如果不存在活跃配置，但当前目录同时存在 `wiki/` 和 `tools/` 目录：
   - 告知用户当前目录看起来就是一个 wiki 项目。
   - 优先建议执行 `/wiki-setup init .`。
   - 询问是否要注册当前项目。
4. 否则：询问用户要执行哪一种操作：安装技能、注册已有知识库、创建新知识库。

---

## 安装模式（`/wiki-setup install`）

1. 将当前项目的 `skills/` 目录视为 `$SKILL_SOURCE`。
2. 验证以下路径都存在，否则告知用户缺失项并停止：
   - `skills/llm-wiki/SKILL.md`
   - `skills/wiki-query/SKILL.md`
   - `skills/wiki-update/SKILL.md`
   - `skills/wiki-switch/SKILL.md`
   - `skills/wiki-setup/SKILL.md`
3. 确保 `~/.claude/skills/` 存在。
4. 将上述 5 个技能目录复制到 `~/.claude/skills/` 下；若目标目录已存在，则覆盖更新该目录内容。
5. 告知用户安装结果：

```
技能已安装到全局：
  ~/.claude/skills/llm-wiki/
  ~/.claude/skills/wiki-query/
  ~/.claude/skills/wiki-update/
  ~/.claude/skills/wiki-switch/
  ~/.claude/skills/wiki-setup/

下一步：运行 /wiki-setup init <知识库路径> 注册你的知识库。
```

说明：OpenCode 兼容读取 `~/.claude/skills/`，因此无需额外复制到 `~/.config/opencode/skills/`。

---

## 注册模式（`/wiki-setup init <路径>`）

1. 获取 `<路径>`；如果用户未提供路径，询问用户。
2. 验证该路径是否存在且包含 `wiki/` 目录：
   - 如果存在且包含 `wiki/`，继续。
   - 如果不存在，或不存在 `wiki/` 目录，明确警告用户，但仍继续，因为用户可能正在注册一个空的新知识库。
3. 询问配置名称，默认 `primary`。
4. 确保 `~/.llm-wiki/` 目录存在。
5. 写入 `~/.llm-wiki/config.<名称>`：

```
LLM_WIKI_PATH=<绝对路径>
```

6. 将 `~/.llm-wiki/active` 写为该配置名称。
7. 向用户确认：

```
知识库已注册：<名称>
路径：<路径>
配置：~/.llm-wiki/config.<名称>

当前活跃知识库：<名称>
试试：/wiki-query "我的知识库中有哪些主题？"
```

---

## 新建模式（`/wiki-setup new`）

1. 询问用户目标路径，例如 `D:/AI/work-wiki`。
2. 询问配置名称，例如 `work`。
3. 如果目标目录不存在，则创建它。
4. 复制项目骨架到目标目录：
   - 复制 `tools/` 目录。
   - 创建空目录：`wiki/`、`wiki/sources/`、`wiki/entities/`、`wiki/concepts/`、`wiki/syntheses/`、`raw/`、`graph/`。
   - 复制文件：`.gitignore`、`pyproject.toml`、`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`README.md`、`LICENSE`。
   - 不复制：`.git/`、`.venv/`、`.idea/`、`__pycache__/`、`hs_err_pid*.log`。
   - 不复制任何实际 wiki 内容页面；`wiki/` 下只保留空目录结构和后续创建的系统页面。
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
7. 复用注册流程：
   - 创建 `~/.llm-wiki/config.<名称>`
   - 写入 `LLM_WIKI_PATH=<目标路径>`
   - 将其设为当前活跃配置
8. 向用户确认：

```
新知识库已创建：<目标>
配置名称：<名称>

结构已就绪。下一步：
1. cd <目标>
2. pip install -e .
3. 将文档放入 raw/ 后运行 /wiki-ingest

当前活跃知识库：<名称>
```
