---
title: "Claude"
type: entity
tags: [AI, LLM, Anthropic]
sources: [claude-opus-4-7-system-prompt-notes.md]
last_updated: 2026-04-18
---

# Claude

Claude 是由 [[Anthropic]] 开发的 AI 助手产品系列。当前最新版本为 Claude Opus 4.7，定位为当前公开可用的最先进、最智能模型。

## 访问渠道

- **claude.ai**：网页端、移动端、桌面端
- **API / Claude Platform**：开发者直接调用（模型字符串：claude-opus-4-7）
- **Claude Code**：命令行工具，面向开发者的 Agentic 编程场景
- **Claude in Chrome**（Beta）：浏览器代理
- **Claude in Excel**（Beta）：电子表格代理
- **Cowork**（Beta）：面向非开发者的桌面文件与任务自动化工具

## 其他可用模型

- claude-opus-4-6
- claude-sonnet-4-6
- claude-haiku-4-5-20251001

## 核心行为原则

Claude 的默认立场是"尽量帮助"，只有在帮助会带来具体、特定的严重伤害时才拒绝。其系统提示词包含搜索优先原则（对事实性问题必须先搜索再回答）和工具发现机制（工具列表部分可见，通过 tool_search 动态加载）。

关于广告：Claude 产品本身不投放广告，不允许广告商付费在对话中推广产品。

## 关联

- [[Anthropic]] — 开发公司
- [[系统提示词]] — Claude 的行为规范体系
- [[ClaudeCode]] — Claude 的命令行工具
- [[Artifacts]] — Claude 的文件输出系统
