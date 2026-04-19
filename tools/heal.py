#!/usr/bin/env python3
"""
图谱自愈工具

自动从 wiki 中检索"缺失的实体页面"，并使用 LLM 为其生成
全面的定义页面。
通过扫描实体被引用的现有上下文来修复断裂的实体链接。

用法:
    python tools/heal.py
"""

import os
import sys
from pathlib import Path

try:
    from litellm import completion
except ImportError:
    print("错误: 未安装 litellm。请运行: pip install litellm")
    sys.exit(1)

# 确保 tools 可被导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.lint import find_missing_entities, all_wiki_pages

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
ENTITIES_DIR = WIKI_DIR / "entities"

def call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """调用 LLM 生成文本，使用 litellm 标准环境变量。"""
    # 使用 litellm 标准环境变量
    # 例如: GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY
    model = os.getenv("LLM_MODEL", "claude-3-5-haiku-latest") # 默认使用快速模型
    
    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

def search_sources(entity: str, pages: list[Path]) -> list[Path]:
    """查找最多 15 个提及该实体的页面。"""
    sources = []
    for p in pages:
        if "entities" not in str(p.parent) and "concepts" not in str(p.parent):
            content = p.read_text(encoding="utf-8")
            if entity.lower() in content.lower():
                sources.append(p)
    return sources[:15]

def heal_missing_entities():
    """检测并自动修复 wiki 中缺失的实体页面。"""
    pages = all_wiki_pages()
    missing_entities = find_missing_entities(pages)
    
    if not missing_entities:
        print("图谱已完全连通，未发现缺失的实体！")
        return

    ENTITIES_DIR.mkdir(exist_ok=True, parents=True)
    print(f"发现 {len(missing_entities)} 个缺失的实体节点，开始自动修复...")
    
    for entity in missing_entities:
        print(f"正在修复实体页面: {entity}")
        sources = search_sources(entity, pages)
        
        context = ""
        for s in sources:
            context += f"\n\n### {s.name}\n{s.read_text(encoding='utf-8')[:800]}"
        
        prompt = f"""你正在填补个人 LLM Wiki 中的数据空白。
请为 "{entity}" 创建一个实体定义页面。

以下是该实体在当前来源中的出现情况:
{context}

格式:
---
title: "{entity}"
type: entity
tags: []
sources: {[s.name for s in sources]}
---

# {entity}

请撰写一段全面的定义，说明 `{entity}` 在本 wiki 上下文中的含义、主要意义，以及与其相关的行动或关联。
"""
        try:
            result = call_llm(prompt)
            out_path = ENTITIES_DIR / f"{entity}.md"
            out_path.write_text(result, encoding="utf-8")
            print(f" -> 已保存到 {out_path.relative_to(REPO_ROOT)}")
        except Exception as e:
            print(f" [!] 生成 {entity} 失败: {e}")

if __name__ == "__main__":
    heal_missing_entities()
