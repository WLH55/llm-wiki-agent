#!/usr/bin/env python3
"""
将 PDF 或 arXiv 来源转换为 Markdown，输出到 raw/ 目录。

用法：
    python tools/pdf2md.py <input> [--output raw/papers/output.md] [--backend auto]

输入类型：
    arXiv ID      →  2401.12345
    arXiv URL     →  https://arxiv.org/abs/2401.12345
    本地 PDF      →  /path/to/paper.pdf

后端：
    auto          →  arXiv 输入使用 arxiv2md；PDF 使用 marker（备选：pymupdf4llm）
    arxiv2md      →  最适合 arXiv 论文（使用结构化源文件，非 PDF）
    marker        →  最适合复杂的多栏学术论文 PDF
    pymupdf4llm   →  快速、轻量、无需 GPU — 适合原生文本 PDF

示例：
    python tools/pdf2md.py 2401.12345
    python tools/pdf2md.py https://arxiv.org/abs/2401.12345
    python tools/pdf2md.py paper.pdf --backend marker
    python tools/pdf2md.py paper.pdf -o raw/papers/my-paper.md
"""

import argparse
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "raw" / "papers"

ARXIV_PATTERNS = [
    re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$"),                          # 2401.12345
    re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})(v\d+)?"),              # URL form
    re.compile(r"arxiv\.org/pdf/(\d{4}\.\d{4,5})(v\d+)?"),              # PDF URL
]


def extract_arxiv_id(source: str) -> str | None:
    """如果输入是 arXiv 引用则返回 arXiv ID，否则返回 None。"""
    for pattern in ARXIV_PATTERNS:
        m = pattern.search(source)
        if m:
            return m.group(1)
    return None


def check_dependency(package: str, pip_name: str | None = None) -> bool:
    """检查 Python 包是否可导入。"""
    try:
        importlib.import_module(package)
        return True
    except ImportError:
        return False


def install_hint(pip_name: str) -> str:
    return f"  请通过以下命令安装：pip install {pip_name}"


# ─── 后端：arxiv2md ──────────────────────────────────────────────

def convert_arxiv(arxiv_id: str, output: Path) -> Path:
    """使用 arxiv2md 转换 arXiv 论文（基于结构化源文件，非 PDF）。"""
    pip_name = "arxiv2markdown"
    if not check_dependency("arxiv2md", pip_name):
        print(f"错误：arxiv2md 未安装。\n{install_hint(pip_name)}")
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["arxiv2md", arxiv_id, "-o", str(output)]
    print(f"  正在执行：{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"错误：arxiv2md 执行失败：\n{result.stderr}")
        sys.exit(1)

    print(f"  ✓ 已转换 arXiv {arxiv_id} → {output.relative_to(REPO_ROOT)}")
    return output


# ─── 后端：marker ────────────────────────────────────────────────

def convert_marker(pdf_path: Path, output: Path) -> Path:
    """使用 marker 转换 PDF（高保真，支持复杂排版）。"""
    pip_name = "marker-pdf"
    if not check_dependency("marker", pip_name):
        print(f"错误：marker 未安装。\n{install_hint(pip_name)}")
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    # marker 输出到一个目录；我们将结果移动到目标路径
    tmp_dir = output.parent / f".marker_tmp_{output.stem}"
    cmd = ["marker_single", str(pdf_path), "--output_dir", str(tmp_dir)]
    print(f"  正在执行：{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"错误：marker 执行失败：\n{result.stderr}")
        sys.exit(1)

    # marker 在 output_dir 内创建 <pdf_name>/<pdf_name>.md
    md_files = list(tmp_dir.rglob("*.md"))
    if not md_files:
        print("错误：marker 未生成 markdown 输出。")
        sys.exit(1)

    # 将第一个 .md 文件移动到目标路径，并清理临时目录
    md_files[0].rename(output)
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"  ✓ 已转换 {pdf_path.name} → {output.relative_to(REPO_ROOT)}")
    return output


# ─── 后端：pymupdf4llm ───────────────────────────────────────────

def convert_pymupdf(pdf_path: Path, output: Path) -> Path:
    """使用 pymupdf4llm 转换 PDF（快速、轻量、适合原生文本 PDF）。"""
    pip_name = "pymupdf4llm"
    if not check_dependency("pymupdf4llm", pip_name):
        print(f"错误：pymupdf4llm 未安装。\n{install_hint(pip_name)}")
        sys.exit(1)

    import pymupdf4llm

    output.parent.mkdir(parents=True, exist_ok=True)
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    output.write_text(md_text, encoding="utf-8")

    print(f"  ✓ 已转换 {pdf_path.name} → {output.relative_to(REPO_ROOT)}")
    return output


# ─── 自动检测与分发 ─────────────────────────────────────────

BACKENDS = {
    "arxiv2md": convert_arxiv,
    "marker": convert_marker,
    "pymupdf4llm": convert_pymupdf,
}


def slugify(name: str) -> str:
    """将文件名或 arXiv ID 转换为安全的 kebab-case 格式。"""
    name = Path(name).stem if "." in name else name
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", name).strip("-")


def resolve_output(source: str, arxiv_id: str | None, output_arg: str | None) -> Path:
    """确定输出路径。"""
    if output_arg:
        p = Path(output_arg)
        return p if p.is_absolute() else REPO_ROOT / p

    if arxiv_id:
        slug = slugify(arxiv_id)
    else:
        slug = slugify(Path(source).stem)

    return DEFAULT_OUTPUT_DIR / f"{slug}.md"


def main():
    parser = argparse.ArgumentParser(
        description="将 PDF/arXiv 转换为 Markdown，输出到 raw/ 目录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="arXiv ID、arXiv URL 或 PDF 文件路径")
    parser.add_argument("-o", "--output", help="输出 .md 路径（默认：raw/papers/<slug>.md）")
    parser.add_argument(
        "-b", "--backend",
        choices=["auto", "arxiv2md", "marker", "pymupdf4llm"],
        default="auto",
        help="转换后端（默认：自动检测）",
    )
    args = parser.parse_args()

    arxiv_id = extract_arxiv_id(args.input)
    output = resolve_output(args.input, arxiv_id, args.output)
    backend = args.backend

    print(f"\npdf2md — LLM Wiki Agent")
    print(f"  输入：   {args.input}")
    print(f"  输出：  {output.relative_to(REPO_ROOT)}")

    # ── 自动选择后端 ──
    if backend == "auto":
        if arxiv_id:
            backend = "arxiv2md"
        elif check_dependency("marker"):
            backend = "marker"
        elif check_dependency("pymupdf4llm"):
            backend = "pymupdf4llm"
        else:
            print("\n错误：未找到可用的转换后端。")
            print("请安装以下之一：")
            print("  pip install arxiv2markdown   # 用于 arXiv 论文")
            print("  pip install marker-pdf       # 用于复杂 PDF")
            print("  pip install pymupdf4llm      # 用于简单/快速的 PDF 转换")
            sys.exit(1)

    print(f"  后端：{backend}")
    print()

    # ── 分发执行 ──
    if backend == "arxiv2md":
        if not arxiv_id:
            print("错误：arxiv2md 后端需要 arXiv ID 或 URL。")
            sys.exit(1)
        convert_arxiv(arxiv_id, output)
    else:
        pdf_path = Path(args.input)
        if not pdf_path.exists():
            print(f"错误：文件未找到：{args.input}")
            sys.exit(1)
        BACKENDS[backend](pdf_path, output)

    print(f"\n完成。接下来可以使用以下命令导入：")
    print(f"  python tools/ingest.py {output.relative_to(REPO_ROOT)}")
    print(f"  — 或者在 agent 中：ingest {output.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
