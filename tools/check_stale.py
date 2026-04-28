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


def find_new_raw_files() -> list[dict]:
    """扫描 raw/ 目录，返回尚未导入 wiki 的文件列表。"""
    if not RAW_DIR.exists():
        return []

    # 收集已导入的 raw 文件路径（相对于 REPO_ROOT）
    ingested: set[str] = set()
    if SOURCES_DIR.exists():
        for wiki_page in SOURCES_DIR.glob("*.md"):
            content = read_file(wiki_page)
            source_file = extract_source_file(content)
            if source_file:
                ingested.add(source_file)

    new_files = []
    for raw_path in sorted(RAW_DIR.rglob("*")):
        if not raw_path.is_file():
            continue
        if raw_path.name == ".gitkeep":
            continue
        rel = str(raw_path.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel not in ingested:
            new_files.append({
                "raw_path": rel,
                "slug": raw_path.stem.lower().replace(" ", "-"),
            })

    return new_files


def find_deleted_raw_files() -> list[dict]:
    """返回 raw 文件已丢失的 wiki 源页面列表。"""
    if not SOURCES_DIR.exists():
        return []

    deleted = []
    for wiki_page in sorted(SOURCES_DIR.glob("*.md")):
        content = read_file(wiki_page)
        source_file = extract_source_file(content)
        if not source_file:
            continue
        raw_path = REPO_ROOT / source_file
        if not raw_path.exists():
            raw_path = RAW_DIR / source_file
            if not raw_path.exists():
                deleted.append({
                    "wiki_page": str(wiki_page.relative_to(REPO_ROOT)),
                    "missing_raw": source_file,
                    "slug": wiki_page.stem,
                })

    return deleted


def scan_all_changes(force: bool = False) -> dict:
    """综合扫描：返回 new / updated / deleted 三类变更。"""
    return {
        "new": find_new_raw_files(),
        "updated": find_stale_sources(force=force),
        "deleted": find_deleted_raw_files(),
    }


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
    parser.add_argument("--update-file", type=str, help="更新指定原始文件的哈希缓存（用于 ingest 后写入）")
    parser.add_argument("--scan", action="store_true", help="扫描 raw/ 目录，检测新增/更新/删除文件")
    args = parser.parse_args()

    if args.update_file:
        raw_path = REPO_ROOT / args.update_file
        if not raw_path.exists():
            print(f"文件未找到: {raw_path}")
            sys.exit(1)
        cache = load_cache()
        raw_content = read_file(raw_path)
        cache[str(raw_path)] = sha256(raw_content)
        save_cache(cache)
        print(f"已更新哈希缓存: {raw_path.relative_to(REPO_ROOT)}")
        return

    if args.scan:
        result = scan_all_changes(force=args.force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_scan_result(result)
        return

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


def _print_scan_result(result: dict):
    """格式化输出扫描结果。"""
    new = result["new"]
    updated = result["updated"]
    deleted = result["deleted"]

    print(f"扫描结果：{len(new)} 个新文件，{len(updated)} 个已更新，{len(deleted)} 个已删除\n")

    if new:
        print("【新增文件】（raw/ 中存在但未导入 wiki）")
        for item in new:
            print(f"  {item['raw_path']}")
        print()

    if updated:
        print("【已更新文件】（raw 文件哈希已变化）")
        for item in updated:
            arrow = f"{item['old_hash']} -> {item['new_hash']}"
            print(f"  {item['slug']}: {arrow}")
            print(f"    原始文档: {item['raw_path']}")
        print()

    if deleted:
        print("【已删除文件】（raw 文件丢失，wiki 页面孤立）")
        for item in deleted:
            print(f"  {item['slug']}: 缺失 {item['missing_raw']}")
        print()

    if not new and not updated and not deleted:
        print("无变更，所有文件均为最新。")


if __name__ == "__main__":
    main()
