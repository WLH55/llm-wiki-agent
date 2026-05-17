---
name: wiki-switch
description: >
  在多个 LLM Wiki 知识库配置之间切换。当用户说"/wiki-switch <名称>"、"切换 wiki"、
  "换知识库"、"当前是哪个 wiki"、"列出我的知识库"、"显示我的知识库"、"创建新的知识库配置"时使用。
  管理 ~/.llm-wiki/config.<名称> 的命名配置文件，通过 ~/.llm-wiki/active 文件标记当前活跃的配置。
---

# Wiki Switch — 管理多个知识库配置

每个知识库对应 `~/.llm-wiki/config.<名称>` 一个配置文件。活跃的知识库由 `~/.llm-wiki/active`
文件中写入的名称决定。切换知识库就是改写这个文件的内容。

## 调度表

解析调用并路由到对应操作：

| 调用 | 操作 |
|---|---|
| `/wiki-switch <名称>` | → **切换** |
| `/wiki-switch list` | → **列表** |
| `/wiki-switch show [名称]` | → **显示** |
| `/wiki-switch new <名称>` | → **新建** |
| `/wiki-switch`（无参数） | → **当前** — 显示活跃知识库信息 |

---

## 当前（默认操作）

显示当前活跃的知识库配置。

1. 读取 `~/.llm-wiki/active`。如果不存在或为空，显示 `（未配置活跃知识库）`。
2. 读取 `~/.llm-wiki/config.<活跃名称>`。
3. 显示：

```
活跃知识库：<名称>
路径：<LLM_WIKI_PATH>
```

如果 `~/.llm-wiki/` 目录根本不存在，告知：

> 尚未配置知识库。请运行 `wiki-setup` 进行初始化。

---

## 切换

激活一个命名知识库配置。

1. 验证 `~/.llm-wiki/config.<名称>` 存在。如果不存在，告知用户该知识库不存在
   并列出现有的（执行**列表**）。
2. 将名称写入 active 文件：

   ```bash
   echo "<名称>" > ~/.llm-wiki/active
   ```

   （如果 `~/.llm-wiki/` 目录尚不存在，先创建。）

3. 从新激活的配置中读取 `LLM_WIKI_PATH`。
4. 确认：

   ```
   已切换到知识库：<名称>
   知识库路径：<LLM_WIKI_PATH>
   ```

---

## 列表

显示所有已注册的知识库配置及当前活跃的。

1. 列出所有匹配 `~/.llm-wiki/config.*` 的文件。
2. 读取 `~/.llm-wiki/active` 获知当前活跃的。
3. 对每个配置文件，提取 `LLM_WIKI_PATH`。
4. 显示：

```
知识库列表：
  primary   D:/AI/llm-wiki-agent        ← 活跃
  work      D:/AI/work-wiki
```

用 `← 活跃` 标记当前活跃的。如果 `active` 文件不存在或 `~/.llm-wiki/` 目录不存在，
显示 `（未配置知识库 — 请运行 wiki-setup）`。

---

## 显示

打印指定知识库的完整配置。

- 如果给出了名称，读取 `~/.llm-wiki/config.<名称>`。
- 如果未给出名称，读取活跃配置。
- 如果文件不存在，告知用户并列出现有的。
- 直接输出文件内容。无需隐藏字段（知识库配置不包含密钥）。

---

## 新建

创建一个新的知识库配置。

1. 询问用户知识库路径（如 `D:/AI/my-new-wiki`）。
2. 询问配置名称（如 `work`、`research`）。
3. 检查 `~/.llm-wiki/config.<名称>` 是否已存在。如果存在则中止。
4. 创建配置文件：

   ```
   LLM_WIKI_PATH=<路径>
   LLM_WIKI_LINK_FORMAT=wikilink
   ```

5. 确认：

   ```
   已创建：~/.llm-wiki/config.<名称>
   知识库路径：<路径>
   
   运行 /wiki-switch <名称> 来激活它。
   ```

   不要自动切换 — 让用户决定何时激活。
