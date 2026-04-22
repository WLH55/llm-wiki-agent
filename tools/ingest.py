#!/usr/bin/env python3
"""
将源文档导入 LLM Wiki。

用法：
    python tools/ingest.py --validate-only   # 仅对现有 wiki 运行验证

导入功能由 Claude Code (/wiki-ingest) 完成。
本脚本仅提供验证工具。
"""

import sys
import json
import hashlib
import re
from pathlib import Path
from datetime import date

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_FILE = WIKI_DIR / "log.md"
INDEX_FILE = WIKI_DIR / "index.md"
OVERVIEW_FILE = WIKI_DIR / "overview.md"
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已写入: {path.relative_to(REPO_ROOT)}")


def build_wiki_context() -> str:
    parts = []
    if INDEX_FILE.exists():
        parts.append(f"## wiki/index.md\n{read_file(INDEX_FILE)}")
    if OVERVIEW_FILE.exists():
        parts.append(f"## wiki/overview.md\n{read_file(OVERVIEW_FILE)}")
    # 包含最近的几个源页面，用于矛盾检测
    sources_dir = WIKI_DIR / "sources"
    if sources_dir.exists():
        recent = sorted(sources_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        for p in recent:
            parts.append(f"## {p.relative_to(REPO_ROOT)}\n{p.read_text()}")
    return "\n\n---\n\n".join(parts)


def parse_json_from_response(text: str) -> dict:
    # 去除 markdown 代码围栏（如果存在）
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # 查找最外层的 JSON 对象
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("响应中未找到 JSON 对象")
    return json.loads(match.group())


def update_index(new_entry: str, section: str = "Sources"):
    content = read_file(INDEX_FILE)
    if not content:
        content = "# Wiki 索引\n\n## 概览\n- [概览](overview.md) — 持续更新的综合摘要\n\n## 来源\n\n## 实体\n\n## 概念\n\n## 综合\n"
    section_header = f"## {section}"
    if section_header in content:
        content = content.replace(section_header + "\n", section_header + "\n" + new_entry + "\n")
    else:
        content += f"\n{section_header}\n{new_entry}\n"
    write_file(INDEX_FILE, content)


def append_log(entry: str):
    existing = read_file(LOG_FILE)
    write_file(LOG_FILE, entry.strip() + "\n\n" + existing)


def extract_wikilinks(content: str) -> list[str]:
    """从页面内容中提取所有 [[WikiLink]] 目标。"""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def all_wiki_pages() -> set[str]:
    """返回所有 wiki 页面文件名的集合（不区分大小写）。"""
    pages = set()
    for p in WIKI_DIR.rglob("*.md"):
        if p.name not in ("index.md", "log.md", "lint-report.md"):
            pages.add(p.stem.lower())
    return pages


def validate_ingest(changed_pages: list[str] | None = None) -> dict:
    """导入后验证 wiki 完整性。

    检查项：
      1. 变更页面中的断裂 wikilink（如未指定则检查所有页面）
      2. 未在 index.md 中注册的页面

    返回包含 'broken_links' 和 'unindexed' 列表的字典。
    """
    existing_pages = all_wiki_pages()
    index_content = read_file(INDEX_FILE).lower()

    # 确定需要扫描断链的页面
    if changed_pages:
        scan_paths = [WIKI_DIR / p for p in changed_pages if (WIKI_DIR / p).exists()]
    else:
        scan_paths = [p for p in WIKI_DIR.rglob("*.md")
                      if p.name not in ("index.md", "log.md", "lint-report.md")]

    # 检查 1：断裂的 wikilink
    broken_links = []
    for page_path in scan_paths:
        content = read_file(page_path)
        rel = str(page_path.relative_to(WIKI_DIR))
        for link in extract_wikilinks(content):
            # 规范化：去除路径，仅检查文件名
            link_stem = Path(link).stem.lower() if '/' in link else link.lower()
            if link_stem not in existing_pages:
                broken_links.append((rel, link))

    # 检查 2：未索引的页面（仅检查变更页面）
    unindexed = []
    for p in (changed_pages or []):
        page_path = WIKI_DIR / p
        if page_path.exists():
            # 检查页面文件名是否出现在 index.md 中
            stem = page_path.stem.lower()
            if stem not in index_content and p not in ("log.md", "overview.md"):
                unindexed.append(p)

    return {"broken_links": broken_links, "unindexed": unindexed}


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--validate-only":
        print("正在运行 wiki 验证（不执行导入）...\n")
        result = validate_ingest()
        if result["broken_links"]:
            print(f"断裂的 wikilink: {len(result['broken_links'])} 个")
            for page, link in result["broken_links"][:20]:
                print(f"  wiki/{page} → [[{link}]]")
            if len(result["broken_links"]) > 20:
                print(f"  ... 及其他 {len(result['broken_links']) - 20} 个")
        else:
            print("未发现断裂的 wikilink。")
        print()
        pages = all_wiki_pages()
        index_content = read_file(INDEX_FILE).lower()
        unindexed_all = []
        for p in WIKI_DIR.rglob("*.md"):
            if p.name in ("index.md", "log.md", "lint-report.md", "overview.md"):
                continue
            if p.stem.lower() not in index_content:
                unindexed_all.append(str(p.relative_to(WIKI_DIR)))
        if unindexed_all:
            print(f"未在 index.md 中的页面: {len(unindexed_all)} 个")
            for up in unindexed_all[:20]:
                print(f"  wiki/{up}")
            if len(unindexed_all) > 20:
                print(f"  ... 及其他 {len(unindexed_all) - 20} 个")
        else:
            print("所有页面均已索引。")
        sys.exit(0)

    print("导入功能已迁移至 Claude Code。请使用 /wiki-ingest <文件路径> 导入源文档。")
    print("如需仅验证，请使用: python tools/ingest.py --validate-only")
