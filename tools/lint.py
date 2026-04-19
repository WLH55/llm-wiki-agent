#!/usr/bin/env python3
from __future__ import annotations

"""
对 LLM Wiki 进行健康检查。

用法:
    python tools/lint.py
    python tools/lint.py --save          # 将检查报告保存到 wiki/lint-report.md

检查项:
  - 孤立页面（没有来自其他页面的入站 wikilink）
  - 失效的 wikilink（指向不存在的页面）
  - 缺失的实体页面（在 3 个以上页面中被提及但没有独立页面）
  - 页面之间的矛盾
  - 数据缺口和建议的新来源
"""

import re
import sys
import json
import argparse
import statistics
from pathlib import Path
from collections import defaultdict
from datetime import date

import os

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
GRAPH_DIR = REPO_ROOT / "graph"
GRAPH_JSON = GRAPH_DIR / "graph.json"
LOG_FILE = WIKI_DIR / "log.md"
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def call_llm(prompt: str, model_env: str, default_model: str, max_tokens: int = 4096) -> str:
    try:
        from litellm import completion
    except ImportError:
        print("错误: litellm 未安装。请运行: pip install litellm")
        sys.exit(1)
        
    model = os.getenv(model_env, default_model)
    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content


def all_wiki_pages() -> list[Path]:
    return [p for p in WIKI_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md", "lint-report.md")]


def extract_wikilinks(content: str) -> list[str]:
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def page_name_to_path(name: str) -> list[Path]:
    """尝试将 [[WikiLink]] 解析为文件路径。"""
    candidates = []
    for p in all_wiki_pages():
        if p.stem.lower() == name.lower() or p.stem == name:
            candidates.append(p)
    return candidates


def find_orphans(pages: list[Path]) -> list[Path]:
    inbound = defaultdict(int)
    for p in pages:
        content = read_file(p)
        for link in extract_wikilinks(content):
            resolved = page_name_to_path(link)
            for r in resolved:
                inbound[r] += 1
    return [p for p in pages if inbound[p] == 0 and p != WIKI_DIR / "overview.md"]


def find_broken_links(pages: list[Path]) -> list[tuple[Path, str]]:
    broken = []
    for p in pages:
        content = read_file(p)
        for link in extract_wikilinks(content):
            if not page_name_to_path(link):
                broken.append((p, link))
    return broken


def find_missing_entities(pages: list[Path]) -> list[str]:
    """查找在 3 个以上页面中被提及但缺少独立页面的实体名称。"""
    mention_counts: dict[str, int] = defaultdict(int)
    existing_pages = {p.stem.lower() for p in pages}
    for p in pages:
        content = read_file(p)
        links = extract_wikilinks(content)
        for link in links:
            if link.lower() not in existing_pages:
                mention_counts[link] += 1
    return [name for name, count in mention_counts.items() if count >= 3]


# ── 图感知检查 ──────────────────────────────────────────────

def load_graph_data() -> dict | None:
    """加载 graph.json（如存在）。文件缺失时返回 None（优雅降级）。"""
    if not GRAPH_JSON.exists():
        return None
    try:
        return json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        print("  [警告] graph.json 已损坏 — 跳过图感知检查")
        return None


def _build_degree_map(graph_data: dict) -> dict[str, int]:
    """根据图的边构建 node_id -> degree 映射。"""
    degrees: dict[str, int] = {}
    for node in graph_data.get("nodes", []):
        degrees[node["id"]] = 0
    for edge in graph_data.get("edges", []):
        degrees[edge["from"]] = degrees.get(edge["from"], 0) + 1
        degrees[edge["to"]] = degrees.get(edge["to"], 0) + 1
    return degrees


def _build_community_map(graph_data: dict) -> dict[str, int]:
    """根据图的节点构建 node_id -> community_id 映射。"""
    return {
        node["id"]: node.get("group", -1)
        for node in graph_data.get("nodes", [])
    }


def check_hub_stubs(graph_data: dict, pages: list[Path], min_content_chars: int = 500) -> list[dict]:
    """查找度数超过均值+2倍标准差且内容过短的核心节点。"""
    degrees = _build_degree_map(graph_data)
    deg_values = list(degrees.values())
    if len(deg_values) < 2:
        return []

    mean_deg = statistics.mean(deg_values)
    std_deg = statistics.stdev(deg_values)
    threshold = mean_deg + 2 * std_deg

    # 构建 node_id -> 页面路径的映射
    node_to_path: dict[str, Path] = {}
    for p in pages:
        nid = p.relative_to(WIKI_DIR).as_posix().replace(".md", "")
        node_to_path[nid] = p

    results = []
    for node_id, deg in degrees.items():
        if deg <= threshold:
            continue
        path = node_to_path.get(node_id)
        if not path:
            continue
        content_len = len(read_file(path))
        if content_len < min_content_chars:
            results.append({
                "node_id": node_id,
                "degree": deg,
                "content_len": content_len,
                "path": str(path.relative_to(REPO_ROOT)),
            })
    return sorted(results, key=lambda x: x["degree"], reverse=True)


def check_fragile_bridges(graph_data: dict) -> list[dict]:
    """查找仅通过 1 条边连接的社区对。"""
    comm_map = _build_community_map(graph_data)
    cross_comm: dict[tuple[int, int], list[dict]] = {}

    for edge in graph_data.get("edges", []):
        ca = comm_map.get(edge["from"], -1)
        cb = comm_map.get(edge["to"], -1)
        if ca < 0 or cb < 0 or ca == cb:
            continue
        key = (min(ca, cb), max(ca, cb))
        cross_comm.setdefault(key, []).append(edge)

    return [
        {
            "comm_a": pair[0],
            "comm_b": pair[1],
            "bridge_from": edges[0]["from"],
            "bridge_to": edges[0]["to"],
        }
        for pair, edges in sorted(cross_comm.items())
        if len(edges) == 1
    ]


def check_isolated_communities(graph_data: dict) -> list[dict]:
    """查找没有外部边的社区（知识孤岛）。"""
    comm_map = _build_community_map(graph_data)

    # 构建 community -> 成员列表
    comm_members: dict[int, list[str]] = {}
    for node_id, comm_id in comm_map.items():
        if comm_id < 0:
            continue
        comm_members.setdefault(comm_id, []).append(node_id)

    # 追踪哪些社区有外部边
    has_external = set()
    for edge in graph_data.get("edges", []):
        ca = comm_map.get(edge["from"], -1)
        cb = comm_map.get(edge["to"], -1)
        if ca >= 0 and cb >= 0 and ca != cb:
            has_external.add(ca)
            has_external.add(cb)

    results = []
    for comm_id, members in sorted(comm_members.items()):
        if len(members) < 2:  # 跳过单节点"社区"
            continue
        if comm_id not in has_external:
            results.append({
                "community_id": comm_id,
                "node_count": len(members),
                "members": members[:10],  # 限制显示数量
            })
    return results


def run_lint():
    pages = all_wiki_pages()
    today = date.today().isoformat()

    if not pages:
        print("Wiki 为空，无需检查。")
        return ""

    print(f"正在检查 {len(pages)} 个 wiki 页面...")

    # 确定性检查
    orphans = find_orphans(pages)
    broken = find_broken_links(pages)
    missing_entities = find_missing_entities(pages)

    print(f"  孤立页面: {len(orphans)}")
    print(f"  失效链接: {len(broken)}")
    print(f"  缺失实体页面: {len(missing_entities)}")

    # ── 图感知检查 ──
    graph_data = load_graph_data()
    hub_stubs: list[dict] = []
    fragile_bridges: list[dict] = []
    isolated_comms: list[dict] = []

    if graph_data and graph_data.get("nodes") and graph_data.get("edges"):
        print("  正在运行图感知检查...")
        hub_stubs = check_hub_stubs(graph_data, pages)
        fragile_bridges = check_fragile_bridges(graph_data)
        isolated_comms = check_isolated_communities(graph_data)
        print(f"    核心节点内容不足: {len(hub_stubs)}")
        print(f"    脆弱桥接: {len(fragile_bridges)}")
        print(f"    孤立社区: {len(isolated_comms)}")
    elif graph_data:
        print("  [跳过] graph.json 无数据 — 跳过图感知检查")
    else:
        print("  [跳过] 没有 graph.json — 请先运行 build_graph.py 以启用图感知检查")

    # 构建语义检查的上下文（矛盾、缺口）
    # 使用页面样本以保持在上下文限制内
    sample = pages[:20]
    pages_context = ""
    for p in sample:
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{read_file(p)[:1500]}"  # 截断过长的页面

    print("  正在通过 API 运行语义检查...")
    prompt = f"""你正在对一个 LLM Wiki 进行健康检查。请审阅以下页面并识别:
1. 页面之间的矛盾（相互冲突的论断）
2. 过时内容（已被更新来源取代的摘要）
3. 数据缺口（wiki 无法回答的重要问题 — 建议具体的查找来源）
4. 被提及但缺乏深度的概念

Wiki 页面（共 {len(sample)} 个页面的样本）:
{pages_context}

请返回一份 markdown 格式的检查报告，包含以下章节:
## 矛盾
## 过时内容
## 数据缺口与建议来源
## 需要深化的概念

请具体说明 — 列出涉及的确切页面和论断。
"""
    semantic_report = call_llm(prompt, "LLM_MODEL", "claude-3-5-sonnet-latest", max_tokens=3000)

    # 组装完整报告
    report_lines = [
        f"# Wiki 健康检查报告 — {today}",
        "",
        f"共扫描 {len(pages)} 个页面。",
        "",
        "## 结构性问题",
        "",
    ]

    if orphans:
        report_lines.append("### 孤立页面（没有入站链接）")
        for p in orphans:
            report_lines.append(f"- `{p.relative_to(REPO_ROOT)}`")
        report_lines.append("")

    if broken:
        report_lines.append("### 失效的 Wikilink")
        for page, link in broken:
            report_lines.append(f"- `{page.relative_to(REPO_ROOT)}` 链接到 `[[{link}]]` — 未找到目标页面")
        report_lines.append("")

    if missing_entities:
        report_lines.append("### 缺失的实体页面（被提及 3 次以上但没有独立页面）")
        report_lines.append("> [!warning] 需要处理\n> 运行 `python3 generate_missing_entities.py` 可自动生成这些缺失的核心页面。")
        for name in missing_entities:
            report_lines.append(f"- `[[{name}]]`")
        report_lines.append("")

    if not orphans and not broken and not missing_entities:
        report_lines.append("未发现结构性问题。")
        report_lines.append("")

    # ── 图感知问题章节 ──
    report_lines.append("## 图感知问题")
    report_lines.append("")

    if not graph_data:
        report_lines.append("> [!tip]")
        report_lines.append("> 图感知检查已跳过。请先运行 `python tools/build_graph.py`，然后重新执行检查。")
        report_lines.append("")
    elif not graph_data.get("nodes") or not graph_data.get("edges"):
        report_lines.append("> [!tip]")
        report_lines.append("> 图数据为空。请导入来源并运行 `python tools/build_graph.py` 以填充数据。")
        report_lines.append("")
    else:
        # 核心节点内容检查
        report_lines.append(f"### 内容不足的核心页面（{len(hub_stubs)} 个页面）")
        if hub_stubs:
            report_lines.append("这些核心节点承载了不均衡的连接度，但内容过于单薄:")
            report_lines.append("")
            report_lines.append("| 页面 | 度数 | 内容长度 | 状态 |")
            report_lines.append("|---|---|---|---|")
            for hs in hub_stubs:
                status = "🔴 存根" if hs["content_len"] < 250 else "🟡 单薄"
                report_lines.append(f"| `{hs['path']}` | {hs['degree']} | {hs['content_len']} 字符 | {status} |")
        else:
            report_lines.append("未检测到内容不足的核心页面 — 所有高度数节点均有充足内容。")
        report_lines.append("")

        # 脆弱桥接
        report_lines.append(f"### 脆弱桥接（{len(fragile_bridges)} 个社区对）")
        if fragile_bridges:
            report_lines.append("这些社区连接仅依赖单条边 — 一旦断开即可导致社区隔离:")
            for fb in fragile_bridges:
                report_lines.append(f"- 社区 {fb['comm_a']} ↔ 社区 {fb['comm_b']}，经由 `{fb['bridge_from']}` → `{fb['bridge_to']}`")
        else:
            report_lines.append("无脆弱桥接 — 所有社区连接均有冗余链接。")
        report_lines.append("")

        # 孤立社区
        report_lines.append(f"### 孤立社区（{len(isolated_comms)} 个社区）")
        if isolated_comms:
            report_lines.append("这些社区没有任何外部连接 — 属于知识孤岛:")
            report_lines.append("")
            report_lines.append("| 社区 | 节点数 | 成员 |")
            report_lines.append("|---|---|---|")
            for ic in isolated_comms:
                members_str = ", ".join(ic["members"][:5])
                if ic["node_count"] > 5:
                    members_str += ", …"
                report_lines.append(f"| {ic['community_id']} | {ic['node_count']} | {members_str} |")
        else:
            report_lines.append("无孤立社区 — 所有集群均有外部连接。")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append(semantic_report)

    report = "\n".join(report_lines)
    print("\n" + report)
    return report


def append_log(entry: str):
    existing = read_file(LOG_FILE)
    LOG_FILE.write_text(entry.strip() + "\n\n" + existing, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="对 LLM Wiki 进行健康检查")
    parser.add_argument("--save", action="store_true", help="将检查报告保存到 wiki/lint-report.md")
    args = parser.parse_args()

    report = run_lint()

    if args.save and report:
        report_path = WIKI_DIR / "lint-report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n已保存: {report_path.relative_to(REPO_ROOT)}")

    today = date.today().isoformat()
    append_log(f"## [{today}] lint | Wiki 健康检查\n\n已执行健康检查。详见 lint-report.md。")
