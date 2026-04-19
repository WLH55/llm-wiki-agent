#!/usr/bin/env python3
"""
检测过期的 wiki 来源页面。

通过对比 raw/ 原始文档的 SHA-256 哈希值与缓存，找出有变更的文件。

用法：
    python tools/check_stale.py                  # 列出所有过期来源
    python tools/check_stale.py --json           # 输出 JSON 格式
    python tools_stale.py --update                # 列出过期来源并更新缓存
"""

import json
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
SOURCES_DIR = WIKI_DIR / "sources"
RAW_DIR = REPO_ROOT / "raw"
REFRESH_CACHE = REPO_ROOT / "graph" / ".refresh_cache.json"


def sha256(text: str) -> str:
    """计算文本的 SHA-256 哈希值（取前 16 位）。"""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    """读取文件内容，文件不存在时返回空字符串。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_cache() -> dict:
    """加载哈希缓存。"""
    if REFRESH_CACHE.exists():
        try:
            return json.loads(REFRESH_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache: dict):
    """保存哈希缓存。"""
    REFRESH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    REFRESH_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_source_file(content: str) -> str | None:
    """从 YAML frontmatter 中提取 source_file 字段。"""
    match = re.search(r"^source_file:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None


def find_stale_sources(force: bool = False) -> list[dict]:
    """返回有变更的来源列表。

    每个条目包含：wiki_page, raw_path, slug, old_hash, new_hash。
    """
    cache = load_cache()
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
            raw_path = RAW_DIR / source_file
            if not raw_path.exists():
                continue

        raw_content = read_file(raw_path)
        current_hash = sha256(raw_content)
        cached_hash = cache.get(str(raw_path))

        if force or cached_hash != current_hash:
            stale.append({
                "wiki_page": str(wiki_page.relative_to(REPO_ROOT)),
                "raw_path": str(raw_path.relative_to(REPO_ROOT)),
                "slug": wiki_page.stem,
                "old_hash": cached_hash or "(无缓存)",
                "new_hash": current_hash,
            })

    return stale


def main():
    import argparse
    parser = argparse.ArgumentParser(description="检测过期的 wiki 来源页面")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--update", action="store_true", help="列出过期来源并更新缓存")
    parser.add_argument("--force", action="store_true", help="将所有来源标记为过期")
    args = parser.parse_args()

    stale = find_stale_sources(force=args.force)

    if args.json:
        print(json.dumps(stale, ensure_ascii=False, indent=2))
    else:
        if not stale:
            print("所有来源页面均为最新，无需刷新。")
        else:
            print(f"发现 {len(stale)} 个过期来源：")
            for item in stale:
                arrow = f"{item['old_hash']} -> {item['new_hash']}"
                print(f"  {item['slug']}: {arrow}")
                print(f"    原始文档: {item['raw_path']}")

    if args.update and stale:
        cache = load_cache()
        for item in stale:
            raw_path = REPO_ROOT / item["raw_path"]
            raw_content = read_file(raw_path)
            cache[str(raw_path)] = sha256(raw_content)
        save_cache(cache)
        print(f"\n已更新 {len(stale)} 个文件的哈希缓存。")


if __name__ == "__main__":
    main()
