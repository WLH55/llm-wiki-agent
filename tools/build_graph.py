#!/usr/bin/env python3
"""
从 wiki 构建知识图谱。

用法:
    python tools/build_graph.py               # 构建图谱
    python tools/build_graph.py --open        # 构建后在浏览器中打开 graph.html
    python tools/build_graph.py --report      # 生成图谱健康报告

输出:
    graph/graph.json    — 节点/边数据
    graph/graph.html    — 交互式 vis.js 可视化

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
    """合并重复和双向边，保留最高置信度。"""
    best = {}  # (min(a,b), max(a,b)) -> 边
    for e in edges:
        a, b = e["from"], e["to"]
        key = (min(a, b), max(a, b))
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

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>知识图谱</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,500;9..144,700&family=Nunito+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{
    margin: 0; background: #F5F2EB;
    font-family: 'Nunito Sans', sans-serif;
    color: #2C3E3A; overflow: hidden;
  }}
  #graph {{ width: 100vw; height: 100vh; }}
  #controls {{
    position: fixed; top: 24px; left: 24px;
    background: rgba(255,255,255,0.78);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    padding: 24px; border-radius: 20px; z-index: 10; max-width: 260px;
    border: 1px solid rgba(0,0,0,0.04);
    box-shadow: 0 4px 24px rgba(44,62,58,0.06), 0 1px 2px rgba(44,62,58,0.04);
    transition: box-shadow 0.3s ease;
  }}
  #controls:hover {{
    box-shadow: 0 8px 40px rgba(44,62,58,0.08), 0 2px 4px rgba(44,62,58,0.04);
  }}
  #controls h3 {{
    font-family: 'Fraunces', serif; font-weight: 500; font-size: 18px;
    color: #2C3E3A; margin: 0 0 16px; letter-spacing: -0.02em;
  }}
  #search {{
    width: 100%; padding: 10px 14px; margin-bottom: 16px;
    background: rgba(245,242,235,0.6); color: #2C3E3A;
    border: 1px solid rgba(0,0,0,0.06); border-radius: 12px;
    font-family: 'Nunito Sans', sans-serif; font-size: 13px; outline: none;
    transition: all 0.2s ease;
  }}
  #search:focus {{
    border-color: rgba(91,138,114,0.3); background: rgba(255,255,255,0.9);
    box-shadow: 0 0 0 3px rgba(91,138,114,0.08);
  }}
  #search::placeholder {{ color: #A3B1AD; }}
  .legend-chip {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; margin: 2px; border-radius: 20px;
    font-size: 11px; font-weight: 600; color: #5A6B67;
    background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.04);
  }}
  .legend-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; flex-shrink: 0;
  }}
  .filter-group {{
    margin-top: 14px; padding-top: 14px;
    border-top: 1px solid rgba(0,0,0,0.05);
  }}
  .filter-group > label {{
    display: block; font-size: 10px; font-weight: 700;
    color: #7A8B87; margin-bottom: 8px;
    text-transform: uppercase; letter-spacing: 0.1em;
  }}
  .cb-row {{
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; color: #5A6B67; margin: 5px 0; cursor: pointer;
  }}
  .cb-row input[type="checkbox"] {{
    appearance: none; -webkit-appearance: none;
    width: 16px; height: 16px; border: 1.5px solid #C8C3BB;
    border-radius: 5px; cursor: pointer; position: relative;
    transition: all 0.15s ease; flex-shrink: 0;
  }}
  .cb-row input[type="checkbox"]:checked {{
    background: #5B8A72; border-color: #5B8A72;
  }}
  .cb-row input[type="checkbox"]:checked::after {{
    content: '\2713'; position: absolute; top: -1px; left: 2px;
    color: white; font-size: 11px; font-weight: 700;
  }}
  .slider-row {{ display: flex; align-items: center; gap: 10px; margin-top: 6px; }}
  .slider-row input[type="range"] {{
    flex: 1; -webkit-appearance: none; appearance: none;
    height: 4px; background: #E5E0D8; border-radius: 4px; outline: none;
  }}
  .slider-row input[type="range"]::-webkit-slider-thumb {{
    -webkit-appearance: none; appearance: none;
    width: 16px; height: 16px; border-radius: 50%;
    background: #5B8A72; cursor: pointer;
    border: 2px solid white; box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  }}
  .slider-val {{ font-size: 12px; color: #5B8A72; min-width: 32px; text-align: right; font-weight: 700; }}
  #controls > p {{ margin: 14px 0 0; font-size: 11px; color: #A3B1AD; line-height: 1.6; }}
  #stats {{
    position: fixed; top: 24px; right: 24px;
    background: rgba(255,255,255,0.78);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    padding: 10px 18px; border-radius: 40px;
    font-size: 12px; font-weight: 600; color: #5A6B67;
    border: 1px solid rgba(0,0,0,0.04);
    box-shadow: 0 4px 24px rgba(44,62,58,0.06); z-index: 10;
  }}
  #drawer {{
    position: fixed; top: 0; right: 0;
    width: clamp(440px, 32vw, 640px); max-width: 100vw; height: 100vh;
    background: rgba(253,252,250,0.97);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border-left: 1px solid rgba(0,0,0,0.04);
    box-shadow: -12px 0 40px rgba(44,62,58,0.06);
    z-index: 20; display: flex; flex-direction: column;
    transform: translateX(100%); opacity: 0; pointer-events: none;
    transition: transform 0.4s cubic-bezier(0.16,1,0.3,1), opacity 0.3s ease;
  }}
  #drawer.open {{
    transform: translateX(0); opacity: 1; pointer-events: auto;
  }}
  #drawer-header {{ padding: 28px 28px 20px; border-bottom: 1px solid rgba(0,0,0,0.04); }}
  #drawer-topline {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }}
  #drawer-title {{
    font-family: 'Fraunces', serif; font-weight: 500;
    font-size: 22px; line-height: 1.3; color: #2C3E3A; margin: 0;
  }}
  #drawer-close {{
    background: none; border: none; color: #A3B1AD; font-size: 22px;
    cursor: pointer; padding: 4px; line-height: 1; border-radius: 8px;
    transition: all 0.15s ease;
  }}
  #drawer-close:hover {{ background: rgba(0,0,0,0.04); color: #5A6B67; }}
  #drawer-meta {{
    margin-top: 10px; font-size: 11px; font-weight: 700;
    color: #7A8B87; text-transform: uppercase; letter-spacing: 0.06em;
  }}
  #drawer-path {{
    margin-top: 6px; font-size: 11px; color: #B8C4C0; word-break: break-all;
    font-family: 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace;
  }}
  #drawer-preview {{ margin-top: 14px; font-size: 13px; color: #7A8B87; line-height: 1.7; }}
  #drawer-related {{
    padding: 16px 28px 0; font-size: 11px; font-weight: 700;
    color: #7A8B87; text-transform: uppercase; letter-spacing: 0.06em;
  }}
  #drawer-related-list {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
  .related-chip {{
    background: rgba(91,138,114,0.08); color: #5B8A72;
    border: 1px solid rgba(91,138,114,0.15); border-radius: 20px;
    font-size: 11px; font-weight: 600; padding: 5px 12px; cursor: pointer;
    transition: all 0.15s ease; font-family: 'Nunito Sans', sans-serif;
  }}
  .related-chip:hover {{
    background: rgba(91,138,114,0.15); border-color: rgba(91,138,114,0.25);
  }}
  #drawer-content {{ flex: 1; min-height: 0; padding: 20px 28px 28px; overflow: auto; }}
  #drawer-markdown {{ font-size: 13.5px; line-height: 1.8; color: #3D4F4A; }}
  #drawer-markdown h1, #drawer-markdown h2, #drawer-markdown h3, #drawer-markdown h4 {{
    font-family: 'Fraunces', serif; font-weight: 500; color: #2C3E3A;
    margin: 1.5em 0 0.5em; line-height: 1.3;
  }}
  #drawer-markdown h1 {{ font-size: 22px; }}
  #drawer-markdown h2 {{ font-size: 18px; }}
  #drawer-markdown h3 {{ font-size: 15px; }}
  #drawer-markdown p {{ margin: 0 0 1em; }}
  #drawer-markdown ul, #drawer-markdown ol {{ margin: 0 0 1em 1.4em; padding: 0; }}
  #drawer-markdown li {{ margin: 0.3em 0; }}
  #drawer-markdown hr {{ border: 0; border-top: 1px solid rgba(0,0,0,0.06); margin: 1.5em 0; }}
  #drawer-markdown blockquote {{
    margin: 0 0 1em; padding: 0.8em 1.2em;
    border-left: 3px solid rgba(91,138,114,0.4);
    background: rgba(91,138,114,0.04); border-radius: 0 12px 12px 0; color: #5A6B67;
  }}
  #drawer-markdown pre {{
    margin: 0 0 1em; white-space: pre-wrap; word-break: break-word;
    line-height: 1.6; font-size: 12px; background: rgba(0,0,0,0.03);
    border: 1px solid rgba(0,0,0,0.05); border-radius: 12px; padding: 16px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  #drawer-markdown code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9em; background: rgba(91,138,114,0.08);
    padding: 0.15em 0.4em; border-radius: 6px; color: #5B8A72;
  }}
  #drawer-markdown pre code {{ background: transparent; padding: 0; color: inherit; border-radius: 0; }}
  #drawer-markdown .wikilink {{ color: #5B8A72; font-weight: 600; }}
  @media (max-width: 960px) {{ #drawer {{ width: 100vw; }} }}
</style>
</head>
<body>
<div id="controls">
  <h3>知识图谱</h3>
  <input id="search" type="text" placeholder="搜索节点..." oninput="searchNodes(this.value)">
  <div>{legend_items}</div>
  <div class="filter-group">
    <label>关系类型</label>
    <div class="cb-row"><input type="checkbox" id="cb-extracted" checked onchange="applyFilters()"><span style="color:#B8C4C0">—</span> 已提取 ({n_extracted})</div>
    <div class="cb-row"><input type="checkbox" id="cb-inferred" checked onchange="applyFilters()"><span style="color:#C4956A">—</span> 推断 ({n_inferred})</div>
    <div class="cb-row"><input type="checkbox" id="cb-ambiguous" onchange="applyFilters()"><span style="color:#D4CDC5">—</span> 模糊 ({n_ambiguous})</div>
  </div>
  <div class="filter-group">
    <label>最低置信度</label>
    <div class="slider-row">
      <input type="range" id="conf-slider" min="0" max="100" value="50" oninput="applyFilters()">
      <span class="slider-val" id="conf-val">0.50</span>
    </div>
  </div>
  <p>点击节点查看详情</p>
</div>
<div id="graph"></div>
<aside id="drawer">
  <div id="drawer-header">
    <div id="drawer-topline">
      <h2 id="drawer-title"></h2>
      <button id="drawer-close" onclick="clearSelection()" aria-label="关闭">x</button>
    </div>
    <div id="drawer-meta"></div>
    <div id="drawer-path"></div>
    <div id="drawer-preview"></div>
  </div>
  <div id="drawer-related">相关节点<div id="drawer-related-list"></div></div>
  <div id="drawer-content"><div id="drawer-markdown"></div></div>
</aside>
<div id="stats"></div>
<script>
const originalNodes = {nodes_json};
const originalEdges = {edges_json}.map(edge => ({{
  ...edge,
  id: edge.id || `${{edge.from}}->${{edge.to}}:${{edge.type || "INFERRED"}}`,
}}));
const nodes = new vis.DataSet(originalNodes);
const edges = new vis.DataSet(originalEdges);
const adjacency = new Map();
const searchInput = document.getElementById("search");
const stats = document.getElementById("stats");
const controls = {{
  extracted: document.getElementById("cb-extracted"),
  inferred: document.getElementById("cb-inferred"),
  ambiguous: document.getElementById("cb-ambiguous"),
  confSlider: document.getElementById("conf-slider"),
  confValue: document.getElementById("conf-val"),
}};
const nodeMap = new Map(originalNodes.map(node => [node.id, node]));
let activeNodeId = null;

function hexToRgba(color, alpha) {{
  if (!color) return `rgba(255, 255, 255, ${{alpha}})`;
  const normalized = color.replace("#", "");
  const value = normalized.length === 3
    ? normalized.split("").map(ch => ch + ch).join("")
    : normalized;
  const intValue = Number.parseInt(value, 16);
  const r = (intValue >> 16) & 255;
  const g = (intValue >> 8) & 255;
  const b = intValue & 255;
  return `rgba(${{r}}, ${{g}}, ${{b}}, ${{alpha}})`;
}}

function escapeHtml(text) {{
  return (text || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}}

function stripFrontmatter(markdown) {{
  return (markdown || "").replace(/^---\\n[\\s\\S]*?\\n---\\n?/, "");
}}

function renderInlineMarkdown(text) {{
  let html = escapeHtml(text);
  html = html.replace(/\[\[([^\]]+)\]\]/g, '<span class="wikilink">[[$1]]</span>');
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return html;
}}

function renderMarkdown(markdown) {{
  const lines = stripFrontmatter(markdown).split(/\\r?\\n/);
  const html = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let quoteLines = [];
  let inCodeBlock = false;
  let codeLines = [];

  function flushParagraph() {{
    if (!paragraph.length) return;
    html.push(`<p>${{renderInlineMarkdown(paragraph.join(" "))}}</p>`);
    paragraph = [];
  }}
  function flushList() {{
    if (!listType || !listItems.length) return;
    const items = listItems.map(item => `<li>${{renderInlineMarkdown(item)}}</li>`).join("");
    html.push(`<${{listType}}>${{items}}</${{listType}}>`);
    listType = null; listItems = [];
  }}
  function flushQuote() {{
    if (!quoteLines.length) return;
    html.push(`<blockquote>${{quoteLines.map(line => renderInlineMarkdown(line)).join("<br>")}}</blockquote>`);
    quoteLines = [];
  }}
  function flushCode() {{
    if (!codeLines.length) {{ html.push("<pre><code></code></pre>"); return; }}
    html.push(`<pre><code>${{escapeHtml(codeLines.join("\\n"))}}</code></pre>`);
    codeLines = [];
  }}

  for (const rawLine of lines) {{
    const line = rawLine.replace(/\\t/g, "    ");
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {{
      flushParagraph(); flushList(); flushQuote();
      if (inCodeBlock) {{ flushCode(); inCodeBlock = false; }} else {{ inCodeBlock = true; }}
      continue;
    }}
    if (inCodeBlock) {{ codeLines.push(rawLine); continue; }}
    if (!trimmed) {{ flushParagraph(); flushList(); flushQuote(); continue; }}
    const headingMatch = trimmed.match(/^(#{{1,6}})\s+(.+)$/);
    if (headingMatch) {{
      flushParagraph(); flushList(); flushQuote();
      const level = headingMatch[1].length;
      html.push(`<h${{level}}>${{renderInlineMarkdown(headingMatch[2])}}</h${{level}}>`);
      continue;
    }}
    if (/^(-{{3,}}|\*{{3,}})$/.test(trimmed)) {{
      flushParagraph(); flushList(); flushQuote();
      html.push("<hr>"); continue;
    }}
    const quoteMatch = trimmed.match(/^>\s?(.*)$/);
    if (quoteMatch) {{ flushParagraph(); flushList(); quoteLines.push(quoteMatch[1]); continue; }}
    flushQuote();
    const unorderedMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (unorderedMatch) {{
      flushParagraph();
      if (listType && listType !== "ul") flushList();
      listType = "ul"; listItems.push(unorderedMatch[1]); continue;
    }}
    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {{
      flushParagraph();
      if (listType && listType !== "ol") flushList();
      listType = "ol"; listItems.push(orderedMatch[1]); continue;
    }}
    flushList();
    paragraph.push(trimmed);
  }}
  if (inCodeBlock) flushCode();
  flushParagraph(); flushList(); flushQuote();
  return html.join("");
}}

function rebuildAdjacency(filteredEdges) {{
  adjacency.clear();
  for (const node of originalNodes) {{ adjacency.set(node.id, new Set()); }}
  for (const edge of filteredEdges) {{
    if (!adjacency.has(edge.from)) adjacency.set(edge.from, new Set());
    if (!adjacency.has(edge.to)) adjacency.set(edge.to, new Set());
    adjacency.get(edge.from).add(edge.to);
    adjacency.get(edge.to).add(edge.from);
  }}
}}

function currentEdgeState() {{
  const minConf = parseInt(controls.confSlider.value, 10) / 100;
  controls.confValue.textContent = minConf.toFixed(2);
  return {{
    showExtracted: controls.extracted.checked,
    showInferred: controls.inferred.checked,
    showAmbiguous: controls.ambiguous.checked,
    minConf,
  }};
}}

function passesEdgeFilters(edge, edgeState) {{
  const typeOk = (edge.type === "EXTRACTED" && edgeState.showExtracted)
    || (edge.type === "INFERRED" && edgeState.showInferred)
    || (edge.type === "AMBIGUOUS" && edgeState.showAmbiguous);
  const confOk = (edge.confidence ?? 1.0) >= edgeState.minConf;
  return typeOk && confOk;
}}

function searchNodes(q) {{ applyFilters(q, activeNodeId); }}

function clearSelection() {{
  activeNodeId = null;
  document.getElementById("drawer").classList.remove("open");
  applyFilters(searchInput.value, null);
}}

function openDrawer(node, relatedIds) {{
  document.getElementById("drawer").classList.add("open");
  document.getElementById("drawer-title").textContent = node.label;
  const communityText = Number.isInteger(node.group) && node.group >= 0 ? ` · 社区 ${{node.group}}` : "";
  document.getElementById("drawer-meta").textContent = `${{node.type}}${{communityText}}`;
  document.getElementById("drawer-path").textContent = node.path;
  document.getElementById("drawer-preview").textContent = "";
  document.getElementById("drawer-markdown").innerHTML = renderMarkdown(node.markdown || "");
  const relatedList = document.getElementById("drawer-related-list");
  relatedList.innerHTML = "";
  const relatedNodes = originalNodes
    .filter(item => relatedIds.has(item.id) && item.id !== node.id)
    .sort((a, b) => a.label.localeCompare(b.label));
  if (relatedNodes.length === 0) {{
    const empty = document.createElement("span");
    empty.textContent = "没有直接相连的节点";
    relatedList.appendChild(empty);
    return;
  }}
  for (const related of relatedNodes) {{
    const chip = document.createElement("button");
    chip.className = "related-chip";
    chip.textContent = related.label;
    chip.onclick = () => focusNode(related.id);
    relatedList.appendChild(chip);
  }}
}}

function applyFilters(query = searchInput.value, selectedNodeId = activeNodeId) {{
  const lower = (query || "").trim().toLowerCase();
  const edgeState = currentEdgeState();
  const filteredEdges = originalEdges.filter(edge => passesEdgeFilters(edge, edgeState));
  rebuildAdjacency(filteredEdges);
  const relatedIds = selectedNodeId
    ? new Set([selectedNodeId, ...(adjacency.get(selectedNodeId) || [])])
    : null;
  const filteredNodeIds = new Set();
  for (const edge of filteredEdges) {{
    filteredNodeIds.add(edge.from);
    filteredNodeIds.add(edge.to);
  }}

  let visibleNodeCount = 0;
  const nodeUpdates = originalNodes.map(node => {{
    const matchesSearch = !lower || node.label.toLowerCase().includes(lower);
    const isActive = selectedNodeId === node.id;
    const isConnected = filteredNodeIds.has(node.id);
    const isRelated = !relatedIds || relatedIds.has(node.id);
    const hidden = !selectedNodeId && !lower && !isConnected;
    const emphasized = matchesSearch && isRelated && (isConnected || !!lower || isActive);
    if (!hidden) visibleNodeCount += 1;
    return {{
      id: node.id,
      hidden,
      color: {{
        background: emphasized ? node.color : hexToRgba(node.color, hidden ? 0.08 : 0.35),
        border: emphasized ? hexToRgba(node.color, 0.8) : hexToRgba(node.color, hidden ? 0.06 : 0.3),
        highlight: {{ background: node.color, border: hexToRgba(node.color, 0.9) }},
        hover: {{ background: node.color, border: hexToRgba(node.color, 0.9) }},
      }},
      font: {{
        color: emphasized ? "#2C3E3A" : hidden ? "rgba(44,62,58,0.06)" : "rgba(44,62,58,0.25)",
      }},
      borderWidth: isActive ? 3 : 1.5,
      size: isActive ? 18 : 12,
    }};
  }});

  const edgeUpdates = originalEdges.map(edge => {{
    const enabled = passesEdgeFilters(edge, edgeState);
    if (!enabled) return {{ id: edge.id, hidden: true }};
    const matchesSearch = !lower
      || nodeMap.get(edge.from)?.label.toLowerCase().includes(lower)
      || nodeMap.get(edge.to)?.label.toLowerCase().includes(lower);
    const isRelated = !relatedIds || relatedIds.has(edge.from) || relatedIds.has(edge.to);
    const touchesActive = !!selectedNodeId && (edge.from === selectedNodeId || edge.to === selectedNodeId);
    const emphasized = matchesSearch && isRelated;
    return {{
      id: edge.id, hidden: false,
      width: 1.0,
      color: touchesActive ? "#9B59B6" : emphasized ? hexToRgba(edge.color, 0.5) : hexToRgba(edge.color, 0.04),
    }};
  }});

  nodes.update(nodeUpdates);
  edges.update(edgeUpdates);

  if (selectedNodeId) {{
    const activeNode = nodeMap.get(selectedNodeId);
    if (activeNode) openDrawer(activeNode, relatedIds || new Set([selectedNodeId]));
  }}

  const focusSuffix = selectedNodeId && nodeMap.get(selectedNodeId)
    ? ` · ${{nodeMap.get(selectedNodeId).label}}` : "";
  stats.textContent = `${{visibleNodeCount}} 个节点 · ${{filteredEdges.length}} 条边${{focusSuffix}}`;
}}

const container = document.getElementById("graph");
const nodeCount = originalNodes.length;
const gravConst = nodeCount > 80 ? -8000 : nodeCount > 30 ? -5000 : -2000;
const springLen = nodeCount > 80 ? 250 : nodeCount > 30 ? 200 : 150;

const network = new vis.Network(container, {{ nodes, edges }}, {{
  nodes: {{
    shape: "dot",
    font: {{ color: "#3D4F4A", size: 11, strokeWidth: 0 }},
    borderWidth: 1,
    scaling: {{
      min: 8, max: 36,
      label: {{ enabled: true, min: 10, max: 18, drawThreshold: 6, maxVisible: 24 }},
    }},
  }},
  edges: {{
    width: 1.0,
    smooth: {{ type: "continuous" }},
    arrows: {{ to: {{ enabled: true, scaleFactor: 0.6, type: "arrow" }} }},
    color: {{ inherit: false }},
    hoverWidth: 1.5,
  }},
  physics: {{
    stabilization: {{ iterations: 200, updateInterval: 30, fit: true }},
    barnesHut: {{ gravitationalConstant: gravConst, springLength: springLen, springConstant: 0.015, damping: 0.12 }},
    minVelocity: 0.5,
  }},
  interaction: {{ hover: true, tooltipDelay: 200, hideEdgesOnDrag: false, hideEdgesOnZoom: false }},
}});

network.once("stabilizationIterationsDone", function () {{
  network.fit({{ animation: {{ duration: 400, easingFunction: "easeInOutQuad" }} }});
}});

function focusNode(nodeId) {{
  activeNodeId = nodeId;
  applyFilters(searchInput.value, nodeId);
  const node = nodeMap.get(nodeId) || nodes.get(nodeId);
  const relatedIds = new Set([nodeId, ...(adjacency.get(nodeId) || [])]);
  openDrawer(node, relatedIds);
  network.focus(nodeId, {{
    scale: 1.1,
    animation: {{ duration: 300, easingFunction: "easeInOutQuad" }},
  }});
}}

network.on("click", params => {{
  if (params.nodes.length > 0) focusNode(params.nodes[0]);
  else clearSelection();
}});

applyFilters();
</script>
</body>
</html>"""

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
