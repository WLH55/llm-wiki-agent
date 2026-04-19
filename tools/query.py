#!/usr/bin/env python3
"""
查询 LLM Wiki。

用法:
    python tools/query.py "所有来源的主要主题是什么？"
    python tools/query.py "概念A与概念B有何关联？" --save
    python tools/query.py "总结关于某实体名称的所有信息" --save synthesis/my-analysis.md

参数:
    --save              将回答保存回 wiki（会提示输入文件名）
    --save <path>       保存到指定的 wiki 路径
"""

import sys
import re
import json
import argparse
from pathlib import Path
from datetime import date

import os

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
INDEX_FILE = WIKI_DIR / "index.md"
LOG_FILE = WIKI_DIR / "log.md"
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已保存: {path.relative_to(REPO_ROOT)}")


def call_llm(prompt: str, model_env: str, default_model: str, max_tokens: int = 4096) -> str:
    try:
        from litellm import completion
    except ImportError:
        print("错误: 未安装 litellm。请运行: pip install litellm")
        sys.exit(1)
        
    model = os.getenv(model_env, default_model)
    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content


def find_relevant_pages(question: str, index_content: str) -> list[Path]:
    """从索引中提取与问题相关的链接页面。
    使用字符级匹配以兼容 CJK 文字。"""
    md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', index_content)
    question_lower = question.lower()
    relevant = []

    for title, href in md_links:
        title_lower = title.lower()
        # CJK：检查标题中任意 2 个及以上字符的子串是否出现在问题中
        has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in title)
        if has_cjk:
            # 滑动窗口：检查标题中任意 2 字符 CJK 二元组是否存在于问题中
            matched = any(
                title_lower[j:j+2] in question_lower
                for j in range(len(title_lower) - 1)
                if any('\u4e00' <= c <= '\u9fff' for c in title_lower[j:j+2])
            )
        else:
            # 拉丁文字：基于词语的匹配（阈值降至 >2）
            matched = any(word in question_lower for word in title_lower.split() if len(word) > 2)

        if matched:
            p = WIKI_DIR / href
            if p.exists() and p not in relevant:
                relevant.append(p)

    # 同时尝试基于图的扩展：查找已匹配页面的邻居节点
    graph_json = REPO_ROOT / "graph" / "graph.json"
    if graph_json.exists() and relevant:
        try:
            graph_data = json.loads(graph_json.read_text())
            page_ids = {p.relative_to(WIKI_DIR).as_posix().replace('.md', '') for p in relevant}
            neighbors = set()
            for edge in graph_data.get('edges', []):
                if edge.get('confidence', 0) >= 0.7:
                    if edge['from'] in page_ids:
                        neighbors.add(edge['to'])
                    elif edge['to'] in page_ids:
                        neighbors.add(edge['from'])
            for nid in neighbors:
                np = WIKI_DIR / f"{nid}.md"
                if np.exists() and np not in relevant:
                    relevant.append(np)
        except (json.JSONDecodeError, KeyError):
            pass

    # 始终包含 overview 页面
    overview = WIKI_DIR / "overview.md"
    if overview.exists() and overview not in relevant:
        relevant.insert(0, overview)
    return relevant[:15]  # 限制数量以避免上下文溢出


def append_log(entry: str):
    existing = read_file(LOG_FILE)
    LOG_FILE.write_text(entry.strip() + "\n\n" + existing, encoding="utf-8")


def query(question: str, save_path: str | None = None):
    today = date.today().isoformat()

    # 步骤 1：读取索引
    index_content = read_file(INDEX_FILE)
    if not index_content:
        print("Wiki 为空。请先导入来源文件: python tools/ingest.py <source>")
        sys.exit(1)

    # 步骤 2：查找相关页面
    relevant_pages = find_relevant_pages(question, index_content)

    # 如果没有关键词匹配，通过 Claude API 从索引中识别相关页面
    if not relevant_pages or len(relevant_pages) <= 1:
        print("  通过 API 选择相关页面...")
        prompt = f"给定以下 wiki 索引：\n\n{index_content}\n\n哪些页面与回答以下问题最相关：\"{question}\"\n\n仅返回一个 JSON 数组，包含相对文件路径（如索引中所列），例如 [\"sources/foo.md\", \"concepts/Bar.md\"]。最多 10 个页面。"
        raw = call_llm(prompt, "LLM_MODEL_FAST", "claude-3-5-haiku-latest", max_tokens=512)
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            paths = json.loads(raw)
            relevant_pages = [WIKI_DIR / p for p in paths if (WIKI_DIR / p).exists()]
        except (json.JSONDecodeError, TypeError):
            pass

    # 步骤 3：读取相关页面
    pages_context = ""
    for p in relevant_pages:
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{p.read_text(encoding='utf-8')}"

    if not pages_context:
        pages_context = f"\n\n### wiki/index.md\n{index_content}"

    # 步骤 3.5：补充 raw/ 原始文档上下文
    raw_docs_added = set()
    for p in relevant_pages:
        if p.parent.name != "sources":
            continue
        content = p.read_text(encoding="utf-8")
        match = re.search(r"^source_file:\s*(.+)$", content, re.MULTILINE)
        if not match:
            continue
        source_file = match.group(1).strip().strip('"').strip("'")
        raw_path = REPO_ROOT / source_file
        if not raw_path.exists():
            raw_path = REPO_ROOT / "raw" / source_file
        if raw_path.exists() and str(raw_path) not in raw_docs_added:
            raw_content = raw_path.read_text(encoding="utf-8")
            if raw_content:
                pages_context += f"\n\n### [原始文档] {raw_path.relative_to(REPO_ROOT)}\n{raw_content}"
                raw_docs_added.add(str(raw_path))

    schema = read_file(SCHEMA_FILE)

    # 步骤 4：综合回答
    print(f"  正在从 {len(relevant_pages)} 个页面综合回答...")
    prompt = f"""你正在查询一个 LLM Wiki 以回答问题。请使用下方的 wiki 页面来综合出一个详尽的回答。使用 [[PageName]] wikilink 语法引用来源。

Schema:
{schema}

Wiki 页面:
{pages_context}

问题: {question}

请撰写一个结构良好的 Markdown 回答，包含标题、列表和 [[wikilink]] 引用。在末尾添加一个 ## 来源 部分，列出你所引用的页面。
"""
    answer = call_llm(prompt, "LLM_MODEL", "claude-3-5-sonnet-latest", max_tokens=4096)
    print("\n" + "=" * 60)
    print(answer)
    print("=" * 60)

    # 步骤 5：可选保存回答
    if save_path is not None:
        if save_path == "":
            # 提示输入文件名
            slug = input("\n保存为（slug，例如 'my-analysis'）: ").strip()
            if not slug:
                print("跳过保存。")
                return
            save_path = f"syntheses/{slug}.md"

        full_save_path = WIKI_DIR / save_path
        frontmatter = f"""---
title: "{question[:80]}"
type: synthesis
tags: []
sources: []
last_updated: {today}
---

"""
        write_file(full_save_path, frontmatter + answer)

        # 更新索引
        index_content = read_file(INDEX_FILE)
        entry = f"- [{question[:60]}]({save_path}) — synthesis"
        if "## Syntheses" in index_content:
            index_content = index_content.replace("## Syntheses\n", f"## Syntheses\n{entry}\n")
            INDEX_FILE.write_text(index_content, encoding="utf-8")
        print(f"  已索引: {save_path}")

    # 追加到日志
    append_log(f"## [{today}] query | {question[:80]}\n\n从 {len(relevant_pages)} 个页面综合回答。" +
               (f" 已保存到 {save_path}。" if save_path else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询 LLM Wiki")
    parser.add_argument("question", help="要向 wiki 提出的问题")
    parser.add_argument("--save", nargs="?", const="", default=None,
                        help="将回答保存到 wiki（可指定路径）")
    args = parser.parse_args()
    query(args.question, args.save)
