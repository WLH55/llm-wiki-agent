#!/usr/bin/env python3
"""
查询 LLM Wiki — 查找相关页面。

用法:
    python tools/query.py "所有来源的主要主题是什么？"

综合回答由 Claude Code (/wiki-query) 完成。
本脚本仅查找相关页面并输出内容，不做 LLM 调用。
"""

import sys
import re
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
INDEX_FILE = WIKI_DIR / "index.md"
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"


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


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def query(question: str):
    # 读取索引
    index_content = read_file(INDEX_FILE)
    if not index_content:
        print("Wiki 为空。请先导入来源文件。")
        sys.exit(1)

    # 查找相关页面
    relevant_pages = find_relevant_pages(question, index_content)

    if not relevant_pages or (len(relevant_pages) == 1 and relevant_pages[0].name == "overview.md"):
        print("未通过关键词匹配到相关页面。请使用 /wiki-query 让 Claude 综合回答。")
        return

    # 输出匹配到的页面
    print(f"找到 {len(relevant_pages)} 个相关页面：\n")
    for p in relevant_pages:
        rel = p.relative_to(REPO_ROOT)
        print(f"  - {rel}")

    # 补充 raw/ 原始文档
    raw_docs = []
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
        if raw_path.exists():
            raw_docs.append(raw_path)

    if raw_docs:
        print(f"\n关联的原始文档：")
        for rp in raw_docs:
            print(f"  - {rp.relative_to(REPO_ROOT)}")

    print(f"\n综合回答请使用 Claude Code: /wiki-query {question}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python tools/query.py <问题>")
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    query(question)
