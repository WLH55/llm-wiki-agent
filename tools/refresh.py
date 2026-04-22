#!/usr/bin/env python3
"""
通过重新导入原始文档来刷新过期的来源页面。

用法:
    python tools/refresh.py                     # 仅刷新有变更的来源
    python tools/refresh.py --force             # 强制重新导入所有来源
    python tools/refresh.py --page sources/X    # 刷新指定页面

通过对比原始文档哈希值与已存储的哈希值来检测变更。
重新导入有变更的文档，以更新 wiki/sources/ 页面中的准确信息。
"""

import sys
import json
import hashlib
import re
from typing import Optional
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
RAW_DIR = REPO_ROOT / "raw"
SOURCES_DIR = WIKI_DIR / "sources"
REFRESH_CACHE = REPO_ROOT / "graph" / ".refresh_cache.json"


def sha256(text: str) -> str:
    """计算文本的 SHA-256 哈希值（取前 16 位）。"""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    """读取文件内容，文件不存在时返回空字符串。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_refresh_cache() -> dict:
    """加载刷新缓存文件。"""
    if REFRESH_CACHE.exists():
        try:
            return json.loads(REFRESH_CACHE.read_text())
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_refresh_cache(cache: dict):
    """保存刷新缓存到文件。"""
    REFRESH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    REFRESH_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def extract_source_file(content: str) -> Optional[str]:
    """从 YAML frontmatter 中提取 source_file 字段。"""
    match = re.search(r'^source_file:\s*(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None


def find_stale_sources(force: bool = False) -> list[tuple[Path, Path]]:
    """返回需要刷新的 (wiki 来源页面, 原始文档) 对列表。"""
    cache = load_refresh_cache()
    stale = []

    if not SOURCES_DIR.exists():
        return stale

    for wiki_page in sorted(SOURCES_DIR.glob("*.md")):
        content = read_file(wiki_page)
        source_file = extract_source_file(content)
        if not source_file:
            continue

        raw_path = REPO_ROOT / source_file
        if not raw_path.exists():
            # 尝试相对于 raw/ 目录查找
            raw_path = RAW_DIR / source_file
            if not raw_path.exists():
                continue

        raw_content = read_file(raw_path)
        current_hash = sha256(raw_content)
        cached_hash = cache.get(str(raw_path))

        if force or cached_hash != current_hash:
            stale.append((wiki_page, raw_path))

    return stale


def refresh_page(wiki_page: Path, raw_path: Path) -> bool:
    """输出待刷新的来源页面信息。实际刷新由 Claude Code (/wiki-refresh) 完成。"""
    print(f"  过期: {wiki_page.name} ← {raw_path.relative_to(REPO_ROOT)}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="刷新过期的 wiki 来源页面")
    parser.add_argument("--force", action="store_true", help="强制重新导入所有来源")
    parser.add_argument("--page", type=str, help="刷新指定的 wiki 来源页面（如 sources/my-page）")
    parser.add_argument("--dry-run", action="store_true", help="仅列出过期页面，不执行刷新")
    args = parser.parse_args()

    if args.page:
        # 刷新单个指定页面
        wiki_page = WIKI_DIR / args.page
        if not wiki_page.suffix:
            wiki_page = wiki_page.with_suffix(".md")
        if not wiki_page.exists():
            print(f"页面未找到: {wiki_page}")
            sys.exit(1)
        content = read_file(wiki_page)
        source_file = extract_source_file(content)
        if not source_file:
            print(f"在 {wiki_page.name} 的 frontmatter 中未找到 source_file")
            sys.exit(1)
        raw_path = REPO_ROOT / source_file
        if not raw_path.exists():
            raw_path = RAW_DIR / source_file
        if not raw_path.exists():
            print(f"原始文档未找到: {source_file}")
            sys.exit(1)
        stale = [(wiki_page, raw_path)]
    else:
        stale = find_stale_sources(force=args.force)

    if not stale:
        print("所有来源页面均为最新，无需刷新。")
        return

    print(f"发现 {len(stale)} 个过期的来源页面:\n")
    for wiki_page, raw_path in stale:
        refresh_page(wiki_page, raw_path)

    print(f"\n请使用 Claude Code (/wiki-refresh) 执行刷新。")
    print(f"刷新完成后运行: python tools/check_stale.py --update")


if __name__ == "__main__":
    main()
