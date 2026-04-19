---
title: "Artifacts"
type: concept
tags: [AI, Claude, 可视化]
sources: [claude-opus-4-7-system-prompt-notes.md]
last_updated: 2026-04-18
---

# Artifacts

Artifacts 是 [[Claude]] 的文件/可视化输出系统，允许 Claude 创建独立的可渲染内容。

## 何时创建

- 博客文章、文章、故事、社交媒体帖子
- 报告、报表、参考材料、学习指南
- 超过一定行数的代码片段或文本文档

## 支持的类型

Markdown、HTML、React（.jsx）、Mermaid 图、SVG、PDF

## React 可用库

lucide-react、recharts、mathjs、lodash、d3、plotly、three.js、papaparse、sheetjs、shadcn/ui、chart.js、tone、mammoth、tensorflow。样式仅限 Tailwind 核心工具类。

## 重要禁止项

- 禁止使用 localStorage、sessionStorage
- 禁止使用 HTML `<form>` 标签
- 必须遵循单文件原则

## 持久化存储

通过 `window.storage` API 实现跨会话数据持久化，支持个人数据和共享数据。

## 关联

- [[Claude]] — Artifacts 的提供者
- [[Anthropic]] — Artifacts API 的提供者
