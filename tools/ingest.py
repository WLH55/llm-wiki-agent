#!/usr/bin/env python3
"""
将源文档导入 LLM Wiki。

用法：
    python tools/ingest.py <源文件路径>
    python tools/ingest.py raw/articles/my-article.md
    python tools/ingest.py --validate-only   # 仅对现有 wiki 运行验证

LLM 读取源文档，提取知识并更新 wiki：
  - 创建 wiki/sources/<slug>.md
  - 更新 wiki/index.md
  - 更新 wiki/overview.md（如有必要）
  - 创建/更新实体和概念页面
  - 追加到 wiki/log.md
  - 标记矛盾之处
  - 运行导入后验证（断链检查、索引覆盖）
"""

import os
import sys
import json
import hashlib
import re
from pathlib import Path
from collections import defaultdict
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


def call_llm(prompt: str, max_tokens: int = 8192) -> str:
    try:
        from litellm import completion
    except ImportError:
        print("错误：未安装 litellm。请运行：pip install litellm")
        sys.exit(1)
        
    model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-latest")
    
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = completion(**kwargs)
    return response.choices[0].message.content


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


def ingest(source_path: str):
    source = Path(source_path)
    if not source.exists():
        print(f"错误：文件未找到: {source_path}")
        sys.exit(1)

    source_content = source.read_text(encoding="utf-8")
    source_hash = sha256(source_content)
    today = date.today().isoformat()

    print(f"\n正在导入: {source.name}  (哈希: {source_hash})")

    wiki_context = build_wiki_context()
    schema = read_file(SCHEMA_FILE)

    prompt = f"""你正在维护一个 LLM Wiki。请处理此源文档，并将其中的知识整合到 wiki 中。

Schema 和约定：
{schema}

当前 wiki 状态（索引 + 近期页面）：
{wiki_context if wiki_context else "（wiki 为空 — 这是第一个源文档）"}

待导入的新源文档（文件：{source.relative_to(REPO_ROOT) if source.is_relative_to(REPO_ROOT) else source.name}）：
=== 来源开始 ===
{source_content}
=== 来源结束 ===

今天的日期：{today}

仅返回一个合法的 JSON 对象，包含以下字段（不要使用 markdown 代码围栏，不要在 JSON 之外添加任何文字说明）：
{{
  "title": "此源文档的人类可读标题",
  "slug": "用于文件名的 kebab-case-slug",
  "source_page": "wiki/sources/<slug>.md 的完整 markdown 内容 — 使用 schema 中的源页面格式。关键要求：积极地将关键人物、产品、概念和项目在文本中转换为 [[Wikilinks]] 链接。遗漏已知术语的 [[ ]] 标记视为失败。",
  "index_entry": "- [标题](sources/slug.md) — 一句话摘要",
  "overview_update": "wiki/overview.md 的完整更新内容，如果不需要更新则为 null",
  "entity_pages": [
    {{"path": "entities/EntityName.md", "content": "完整 markdown 内容"}}
  ],
  "concept_pages": [
    {{"path": "concepts/ConceptName.md", "content": "完整 markdown 内容"}}
  ],
  "contradictions": ["描述与现有 wiki 内容的任何矛盾之处，如无矛盾则为空列表"],
  "log_entry": "## [{today}] ingest | <title>\\n\\n已添加来源。关键声明：..."
}}
"""

    print(f"  正在调用 API（模型: ...）")
    raw = call_llm(prompt, max_tokens=8192)
    try:
        data = parse_json_from_response(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"解析 API 响应时出错: {e}")
        print("原始响应已保存至 /tmp/ingest_debug.txt")
        Path("/tmp/ingest_debug.txt").write_text(raw)
        sys.exit(1)

    # 写入源页面
    slug = data["slug"]
    write_file(WIKI_DIR / "sources" / f"{slug}.md", data["source_page"])

    # 写入实体页面
    for page in data.get("entity_pages", []):
        write_file(WIKI_DIR / page["path"], page["content"])

    # 写入概念页面
    for page in data.get("concept_pages", []):
        write_file(WIKI_DIR / page["path"], page["content"])

    # 更新概览
    if data.get("overview_update"):
        write_file(OVERVIEW_FILE, data["overview_update"])

    # 更新索引
    update_index(data["index_entry"], section="Sources")

    # 追加日志
    append_log(data["log_entry"])

    # 报告矛盾
    contradictions = data.get("contradictions", [])
    if contradictions:
        print("\n  ⚠️  检测到矛盾：")
        for c in contradictions:
            print(f"     - {c}")

    # --- 导入后验证 ---
    created_pages = [f"sources/{slug}.md"]
    for page in data.get("entity_pages", []):
        created_pages.append(page["path"])
    for page in data.get("concept_pages", []):
        created_pages.append(page["path"])
    updated_pages = ["index.md", "log.md"]
    if data.get("overview_update"):
        updated_pages.append("overview.md")

    validation = validate_ingest(created_pages)

    print(f"\n{'='*50}")
    print(f"  ✅ 已导入: {data['title']}")
    print(f"{'='*50}")
    print(f"  已创建 : {len(created_pages)} 个页面")
    for p in created_pages:
        print(f"           + wiki/{p}")
    print(f"  已更新 : {len(updated_pages)} 个页面")
    for p in updated_pages:
        print(f"           ~ wiki/{p}")
    if contradictions:
        print(f"  警告: {len(contradictions)} 个矛盾")
    if validation["broken_links"]:
        print(f"  ⚠️  断裂链接: {len(validation['broken_links'])} 个")
        for page, link in validation["broken_links"][:10]:
            print(f"           wiki/{page} → [[{link}]]")
        if len(validation["broken_links"]) > 10:
            print(f"           ... 及其他 {len(validation['broken_links']) - 10} 个")
    if validation["unindexed"]:
        print(f"  ⚠️  未在 index.md 中: {len(validation['unindexed'])} 个")
        for p in validation["unindexed"][:10]:
            print(f"           wiki/{p}")
        if len(validation["unindexed"]) > 10:
            print(f"           ... 及其他 {len(validation['unindexed']) - 10} 个")
    if not validation["broken_links"] and not validation["unindexed"]:
        print("  ✓ 验证通过 — 无断裂链接，所有页面已索引")
    print()


if __name__ == "__main__":
    # 处理 --validate-only 标志
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

    if len(sys.argv) < 2:
        print("用法: python tools/ingest.py <源文件路径> [路径2 ...] [目录1 ...]")
        print("      python tools/ingest.py --validate-only")
        sys.exit(1)
        
    paths_to_process = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_file() and p.suffix == ".md":
            paths_to_process.append(p)
        elif p.is_dir():
            for f in p.rglob("*.md"):
                if f.is_file():
                    paths_to_process.append(f)
        else:
            import glob
            for f in glob.glob(arg, recursive=True):
                g_p = Path(f)
                if g_p.is_file() and g_p.suffix == ".md":
                    paths_to_process.append(g_p)
                    
    # 去重并保持顺序
    unique_paths = []
    seen = set()
    for p in paths_to_process:
        abs_p = p.resolve()
        if abs_p not in seen:
            seen.add(abs_p)
            unique_paths.append(p)

    if not unique_paths:
        print("错误：未找到可导入的 markdown 文件。")
        sys.exit(1)

    if len(unique_paths) > 1:
        print(f"批量模式：找到 {len(unique_paths)} 个文件待导入。")
        
    for p in unique_paths:
        ingest(str(p))
