#!/usr/bin/env python3
"""
从 wiki 构建知识图谱。

用法:
    python tools/build_graph.py               # 构建图谱
    python tools/build_graph.py --open        # 构建后在浏览器中打开 graph.html
    python tools/build_graph.py --report      # 生成图谱健康报告

输出:
    graph/graph.json    — 节点/边数据
    graph/graph.html    — 交互式 force-graph 可视化

边类型:
    EXTRACTED   — 页面中显式的 [[wikilink]]
    INFERRED    — Claude 通过 /wiki-graph 推断的隐式关系
    AMBIGUOUS   — 低置信度的推断关系

语义推断由 Claude Code (/wiki-graph) 完成，脚本本身不做 LLM 调用。
"""

import re
import json
import argparse
import statistics
import webbrowser
from pathlib import Path
from datetime import date

try:
    import networkx as nx
    from networkx.algorithms import community as nx_community
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("警告: 未安装 networkx，社区检测已禁用。请运行: pip install networkx")

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
GRAPH_DIR = REPO_ROOT / "graph"
GRAPH_JSON = GRAPH_DIR / "graph.json"
GRAPH_HTML = GRAPH_DIR / "graph.html"
LOG_FILE = WIKI_DIR / "log.md"
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"

# 节点类型 → 颜色映射
TYPE_COLORS = {
    "source": "#7BA07A",
    "entity": "#6A9BC3",
    "concept": "#C4956A",
    "synthesis": "#9B84B8",
    "unknown": "#A3B1AD",
}

EDGE_COLORS = {
    "EXTRACTED": "#B8C4C0",
    "INFERRED": "#C4956A",
    "AMBIGUOUS": "#D4CDC5",
}


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def all_wiki_pages() -> list[Path]:
    return [p for p in WIKI_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md", "lint-report.md")]


def extract_wikilinks(content: str) -> list[str]:
    return list(set(re.findall(r'\[\[([^\]]+)\]\]', content)))


def extract_frontmatter_type(content: str) -> str:
    match = re.search(r'^type:\s*(\S+)', content, re.MULTILINE)
    return match.group(1).strip('"\'') if match else "unknown"


def page_id(path: Path) -> str:
    return path.relative_to(WIKI_DIR).as_posix().replace(".md", "")


def edge_id(src: str, target: str, edge_type: str) -> str:
    return f"{src}->{target}:{edge_type}"


def build_nodes(pages: list[Path]) -> list[dict]:
    nodes = []
    for p in pages:
        content = read_file(p)
        node_type = extract_frontmatter_type(content)
        title_match = re.search(r'^title:\s*"?([^"\n]+)"?', content, re.MULTILINE)
        label = title_match.group(1).strip() if title_match else p.stem
        body = re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL)
        preview_lines = [line.strip() for line in body.splitlines() if line.strip()]
        preview = " ".join(preview_lines[:3])[:220]
        nodes.append({
            "id": page_id(p),
            "label": label,
            "type": node_type,
            "color": TYPE_COLORS.get(node_type, TYPE_COLORS["unknown"]),
            "path": str(p.relative_to(REPO_ROOT)),
            "markdown": content,
            "preview": preview,
        })
    return nodes


def build_extracted_edges(pages: list[Path]) -> list[dict]:
    """第一遍: 确定性的 wikilink 边。"""
    # 构建 stem（小写）→ page_id 的映射，用于解析链接
    stem_map = {p.stem.lower(): page_id(p) for p in pages}
    edges = []
    seen = set()
    for p in pages:
        content = read_file(p)
        src = page_id(p)
        for link in extract_wikilinks(content):
            target = stem_map.get(link.lower())
            if target and target != src:
                key = (src, target)
                if key not in seen:
                    seen.add(key)
                    edges.append({
                        "id": edge_id(src, target, "EXTRACTED"),
                        "from": src,
                        "to": target,
                        "type": "EXTRACTED",
                        "color": EDGE_COLORS["EXTRACTED"],
                        "confidence": 1.0,
                    })
    return edges


def _load_existing_inferred_edges() -> list[dict]:
    """从已有的 graph.json 中保留 Claude 推断的边。"""
    if not GRAPH_JSON.exists():
        return []
    try:
        old_data = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
        return [
            e for e in old_data.get("edges", [])
            if e.get("type") in ("INFERRED", "AMBIGUOUS")
        ]
    except (json.JSONDecodeError, IOError):
        return []


def deduplicate_edges(edges: list[dict]) -> list[dict]:
    """合并完全重复边，保留最高置信度。不同 type 的边视为不同边，不互相覆盖。"""
    best = {}  # (from, to, type) -> 边
    for e in edges:
        a, b = e["from"], e["to"]
        t = e.get("type", "EXTRACTED")
        key = (a, b, t)
        existing = best.get(key)
        if not existing or e.get("confidence", 0) > existing.get("confidence", 0):
            best[key] = e
    deduped = []
    for edge in best.values():
        rel_type = edge.get("type", "INFERRED")
        edge["id"] = edge.get("id", edge_id(edge["from"], edge["to"], rel_type))
        edge["color"] = edge.get("color", EDGE_COLORS.get(rel_type, EDGE_COLORS["INFERRED"]))
        edge["confidence"] = float(edge.get("confidence", 0.7 if rel_type != "EXTRACTED" else 1.0))
        edge.setdefault("title", "")
        edge.setdefault("label", "")
        deduped.append(edge)
    return deduped


def detect_communities(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """使用 Louvain 算法为节点分配社区 ID。"""
    if not HAS_NETWORKX:
        return {}

    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        G.add_edge(e["from"], e["to"])

    if G.number_of_edges() == 0:
        return {}

    try:
        communities = nx_community.louvain_communities(G, seed=42)
        node_to_community = {}
        for i, comm in enumerate(communities):
            for node in comm:
                node_to_community[node] = i
        return node_to_community
    except Exception:
        return {}


def generate_report(nodes: list[dict], edges: list[dict], communities: dict[str, int]) -> str:
    """生成结构化的图谱健康报告。

    分析图谱中的孤立节点、枢纽页面（超级节点）、
    脆弱的跨社区桥接以及整体连通性健康状况。
    """
    today = date.today().isoformat()
    n_nodes = len(nodes)
    n_edges = len(edges)

    if n_nodes == 0:
        return f"# 图谱洞察报告 — {today}\n\nWiki 为空 — 没有可报告的内容。\n"

    # 构建 NetworkX 图用于分析
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        G.add_edge(e["from"], e["to"])

    # --- 指标 ---
    degrees = dict(G.degree())
    edges_per_node = n_edges / n_nodes if n_nodes else 0
    density = nx.density(G)

    # 健康评级
    if edges_per_node >= 2.0:
        health = "✅ 健康"
    elif edges_per_node >= 1.0:
        health = "⚠️ 警告"
    else:
        health = "🔴 危险"

    # 孤立节点: 度 == 0
    orphans = sorted([n for n, d in degrees.items() if d == 0])
    orphan_count = len(orphans)
    orphan_pct = (orphan_count / n_nodes * 100) if n_nodes else 0

    # 超级节点: 度 > 均值 + 2*标准差
    deg_values = list(degrees.values())
    mean_deg = statistics.mean(deg_values) if deg_values else 0
    std_deg = statistics.stdev(deg_values) if len(deg_values) > 1 else 0
    god_threshold = mean_deg + 2 * std_deg
    god_nodes = sorted(
        [(n, d) for n, d in degrees.items() if d > god_threshold],
        key=lambda x: x[1],
        reverse=True,
    )

    # 社区统计
    community_count = len(set(communities.values())) if communities else 0
    comm_members: dict[int, list[str]] = {}
    for node_id, comm_id in communities.items():
        comm_members.setdefault(comm_id, []).append(node_id)

    # 脆弱桥接: 仅通过 1 条边连接的社区对
    cross_comm_edges: dict[tuple[int, int], list[dict]] = {}
    for e in edges:
        ca = communities.get(e["from"], -1)
        cb = communities.get(e["to"], -1)
        if ca >= 0 and cb >= 0 and ca != cb:
            key = (min(ca, cb), max(ca, cb))
            cross_comm_edges.setdefault(key, []).append(e)
    fragile_bridges = [
        (pair, edge_list[0])
        for pair, edge_list in sorted(cross_comm_edges.items())
        if len(edge_list) == 1
    ]

    # --- 构建报告 ---
    lines = [
        f"# 图谱洞察报告 — {today}",
        "",
        "## 健康概览",
        f"- **{n_nodes}** 个节点，**{n_edges}** 条边（{edges_per_node:.2f} 边/节点 — {health}）",
        f"- **{orphan_count}** 个孤立节点（{orphan_pct:.1f}%）— 目标: <10%",
        f"- **{community_count}** 个社区",
        f"- 链接密度: {density:.4f}",
        "",
    ]

    # 孤立节点部分
    lines.append(f"## 🔴 孤立节点（{orphan_count} 个页面，{orphan_pct:.1f}%）")
    if orphans:
        lines.append("这些页面没有任何图谱连接。建议添加 [[wikilinks]]：")
        for o in orphans:
            lines.append(f"- `{o}`")
    else:
        lines.append("没有孤立节点 — 非常好！")
    lines.append("")

    # 超级节点部分
    lines.append("## 🟡 超级节点（枢纽页面）")
    if god_nodes:
        lines.append("这些节点承载了不成比例的连接量（度 > μ+2σ）。请验证它们的内容是否全面：")
        lines.append("")
        lines.append("| 节点 | 度 | 边占比 | 社区 |")
        lines.append("|---|---|---|---|")
        for node_id, deg in god_nodes:
            edge_pct = (deg / (2 * n_edges) * 100) if n_edges else 0
            comm = communities.get(node_id, -1)
            lines.append(f"| `{node_id}` | {deg} | {edge_pct:.1f}% | {comm} |")
    else:
        lines.append("未检测到超级节点 — 度分布均衡。")
    lines.append("")

    # 脆弱桥接部分
    lines.append("## 🟡 脆弱桥接")
    if fragile_bridges:
        lines.append("仅通过 1 条边连接的社区对 — 删除一条链接就会断开连接：")
        for (ca, cb), edge in fragile_bridges:
            lines.append(f"- 社区 {ca} ↔ 社区 {cb}，经由 `{edge['from']}` → `{edge['to']}`")
    else:
        lines.append("没有脆弱桥接 — 所有社区连接都有冗余。")
    lines.append("")

    # 社区概览
    lines.append("## 🟢 社区概览")
    if comm_members:
        lines.append("")
        lines.append("| 社区 | 节点数 | 核心成员 |")
        lines.append("|---|---|---|")
        for comm_id in sorted(comm_members.keys()):
            members = comm_members[comm_id]
            # 按度降序排列，优先展示核心成员
            members_sorted = sorted(members, key=lambda m: degrees.get(m, 0), reverse=True)
            key_members = ", ".join(members_sorted[:5])
            if len(members_sorted) > 5:
                key_members += ", …"
            lines.append(f"| {comm_id} | {len(members)} | {key_members} |")
    else:
        lines.append("未检测到社区。")
    lines.append("")

    # 建议操作
    lines.append("## 建议操作")
    actions = []
    if orphans:
        actions.append(f"1. 为排名靠前的孤立页面添加 wikilinks（潜在影响最大: {orphans[0]}）")
    if god_nodes:
        actions.append(f"{len(actions)+1}. 审查超级节点，区分内容单薄与真正的枢纽页面")
    if fragile_bridges:
        actions.append(f"{len(actions)+1}. 通过交叉引用加强脆弱桥接")
    if not actions:
        actions.append("1. 图谱状态良好 — 继续保持当前的链接习惯")
    lines.extend(actions)
    lines.append("")

    return "\n".join(lines)


COMMUNITY_COLORS = [
    "#7BA07A", "#6A9BC3", "#C4956A", "#9B84B8", "#D4887C",
    "#89ACB0", "#B8A088", "#7C9CB5", "#A8C090", "#C4A87C",
]


def render_html(nodes: list[dict], edges: list[dict]) -> str:
    """生成有机极简风格的知识图谱可视化页面。"""
    nodes_json = json.dumps(nodes, indent=2, ensure_ascii=False).replace('`', '\\`')
    edges_json = json.dumps(edges, indent=2, ensure_ascii=False).replace('`', '\\`')

    type_labels = {"source": "源文档", "entity": "实体", "concept": "概念", "synthesis": "综合"}
    legend_items = "".join(
        f'<span class="legend-chip"><span class="legend-dot" style="background:{color}"></span>{type_labels.get(t, t)}</span>'
        for t, color in TYPE_COLORS.items() if t != "unknown"
    )

    n_extracted = len([e for e in edges if e.get('type') == 'EXTRACTED'])
    n_inferred = len([e for e in edges if e.get('type') == 'INFERRED'])
    n_ambiguous = len([e for e in edges if e.get('type') == 'AMBIGUOUS'])

    template_path = Path(__file__).parent / "graph_template.html"
    template = template_path.read_text(encoding="utf-8")
    return template.replace("{nodes_json}", nodes_json) \
                   .replace("{edges_json}", edges_json) \
                   .replace("{legend_items}", legend_items) \
                   .replace("{n_extracted}", str(n_extracted)) \
                   .replace("{n_inferred}", str(n_inferred)) \
                   .replace("{n_ambiguous}", str(n_ambiguous))


def append_log(entry: str):
    log_path = WIKI_DIR / "log.md"
    entry_text = entry.strip()
    if not log_path.exists():
        log_path.write_text(
            "# Wiki 日志\n\n"
            "> 记录项目知识层的重要增补、修订和澄清。以追加模式维护，供智能体和人类追溯。\n\n"
            f"{entry_text}\n",
            encoding="utf-8",
        )
        return

    existing = read_file(log_path).rstrip()
    if not existing:
        existing = (
            "# Wiki 日志\n\n"
            "> 记录项目知识层的重要增补、修订和澄清。以追加模式维护，供智能体和人类追溯。"
        )
    log_path.write_text(existing + "\n\n" + entry_text + "\n", encoding="utf-8")


def build_graph(open_browser: bool = False, report: bool = False, save: bool = False):
    pages = all_wiki_pages()
    today = date.today().isoformat()

    if not pages:
        print("Wiki 为空。请先导入一些源文件。")
        return

    print(f"正在从 {len(pages)} 个 wiki 页面构建图谱...")
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    # 提取 wikilink 边
    print("  正在提取 wikilinks...")
    nodes = build_nodes(pages)
    edges = build_extracted_edges(pages)
    print(f"  → {len(edges)} 条已提取边")

    # 保留已有的推断边（来自 Claude 的 /wiki-graph 推断）
    existing_inferred = _load_existing_inferred_edges()
    if existing_inferred:
        edges.extend(existing_inferred)
        print(f"  → 保留了 {len(existing_inferred)} 条已有推断边")

    # 边去重
    before_dedup = len(edges)
    edges = deduplicate_edges(edges)
    if before_dedup != len(edges):
        print(f"  去重: {before_dedup} → {len(edges)} 条边")

    # 社区检测
    print("  正在运行 Louvain 社区检测...")
    communities = detect_communities(nodes, edges)
    for node in nodes:
        comm_id = communities.get(node["id"], -1)
        if comm_id >= 0:
            node["color"] = COMMUNITY_COLORS[comm_id % len(COMMUNITY_COLORS)]
        node["group"] = comm_id

    # 计算基于度的节点大小（value）用于 vis.js 缩放
    degree_map: dict[str, int] = {}
    for e in edges:
        degree_map[e["from"]] = degree_map.get(e["from"], 0) + 1
        degree_map[e["to"]] = degree_map.get(e["to"], 0) + 1
    for node in nodes:
        node["value"] = degree_map.get(node["id"], 0) + 1  # +1 使孤立节点仍然可见

    # 保存 graph.json
    graph_data = {"nodes": nodes, "edges": edges, "built": today}
    GRAPH_JSON.write_text(json.dumps(graph_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  已保存: graph/graph.json  ({len(nodes)} 个节点, {len(edges)} 条边)")

    # 保存 graph.html
    html = render_html(nodes, edges)
    GRAPH_HTML.write_text(html, encoding="utf-8")
    print(f"  已保存: graph/graph.html")

    n_ext = len([e for e in edges if e['type']=='EXTRACTED'])
    n_inf = len([e for e in edges if e['type'] in ('INFERRED', 'AMBIGUOUS')])
    append_log(f"## [{today}] graph | 知识图谱已重建\n\n{len(nodes)} 个节点, {len(edges)} 条边（{n_ext} 条已提取, {n_inf} 条推断）。")

    # 生成健康报告
    if report:
        if not HAS_NETWORKX:
            print("警告: 未安装 networkx，无法生成报告。")
        else:
            report_text = generate_report(nodes, edges, communities)
            print("\n" + report_text)
            if save:
                report_path = GRAPH_DIR / "graph-report.md"
                report_path.write_text(report_text, encoding="utf-8")
                print(f"  已保存: {report_path.relative_to(REPO_ROOT)}")
            append_log(f"## [{today}] report | 图谱健康报告已生成\n\n分析了 {len(nodes)} 个节点。")

    if open_browser:
        webbrowser.open(f"file://{GRAPH_HTML.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建 LLM Wiki 知识图谱")
    parser.add_argument("--open", action="store_true", help="在浏览器中打开 graph.html")
    parser.add_argument("--report", action="store_true", help="生成图谱健康报告")
    parser.add_argument("--save", action="store_true", help="将报告保存到 graph/graph-report.md")
    args = parser.parse_args()
    build_graph(open_browser=args.open, report=args.report, save=args.save)
