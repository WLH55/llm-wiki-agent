#!/usr/bin/env python3
"""
图谱自愈工具 — 检测缺失的实体页面。

用法:
    python tools/heal.py

检测 wiki 中被引用 3 次以上但没有独立页面的实体，
输出缺失实体列表及上下文。实体页面的生成由 Claude Code 完成。
"""

from pathlib import Path

# 确保 tools 可被导入
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.lint import find_missing_entities, all_wiki_pages

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"


def search_sources(entity: str, pages: list[Path]) -> list[Path]:
    """查找最多 15 个提及该实体的页面。"""
    sources = []
    for p in pages:
        if "entities" not in str(p.parent) and "concepts" not in str(p.parent):
            content = p.read_text(encoding="utf-8")
            if entity.lower() in content.lower():
                sources.append(p)
    return sources[:15]


def detect_missing_entities():
    """检测 wiki 中缺失的实体页面并输出。"""
    pages = all_wiki_pages()
    missing_entities = find_missing_entities(pages)

    if not missing_entities:
        print("图谱已完全连通，未发现缺失的实体！")
        return

    print(f"发现 {len(missing_entities)} 个缺失的实体节点：\n")

    for entity in missing_entities:
        sources = search_sources(entity, pages)
        source_names = [s.name for s in sources]
        print(f"  [[{entity}]] — 被引用于: {', '.join(source_names[:5])}")

    print(f"\n请使用 Claude Code 生成缺失的实体页面。")


if __name__ == "__main__":
    detect_missing_entities()
