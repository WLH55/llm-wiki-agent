# Wiki Frontmatter Requirements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make wiki page frontmatter requirements explicit in docs and add lint checks that flag missing or incomplete frontmatter on non-system wiki pages.

**Architecture:** Update the repository guidance first so every generator and alternate AI model has a single documented rule set. Then add a small structural validation pass in `tools/lint.py` that inspects wiki markdown files, skips system/report files, and reports missing frontmatter or missing required fields by page type.

**Tech Stack:** Python 3.10+, Markdown docs, existing `tools/lint.py` script

---

### Task 1: Update Repository Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.claude/commands/wiki-ingest.md`
- Test: `CLAUDE.md`

- [ ] **Step 1: Write the failing documentation expectation**

Define the missing requirements before editing files. The resulting docs must explicitly state:

```text
1. `wiki/index.md` and `wiki/log.md` are special system files and do not use the standard page schema.
2. Every other wiki page must begin with YAML frontmatter.
3. `source`, `entity`, `concept`, and `synthesis` each have required minimum fields.
4. `/wiki-ingest` must require frontmatter-bearing entity and concept pages, not only source pages.
```

- [ ] **Step 2: Verify the docs currently fail this expectation**

Run: `rg -n "frontmatter|entity|concept|synthesis|index\.md|log\.md" "CLAUDE.md" ".claude/commands/wiki-ingest.md"`

Expected:
- `CLAUDE.md` documents the source-page template
- `wiki-ingest.md` mentions source-page formatting
- there is no explicit rule that all non-system wiki pages require frontmatter

- [ ] **Step 3: Update `CLAUDE.md` with the explicit page schema**

Add or revise sections so the file contains concrete templates like:

```markdown
### 页面元数据规则

- `wiki/index.md` 和 `wiki/log.md` 是系统页面，不使用标准 frontmatter。
- 其他所有 wiki 页面都必须以 YAML frontmatter 开头。

### 实体页面格式

```markdown
---
title: "实体名称"
type: entity
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```

### 概念页面格式

```markdown
---
title: "概念名称"
type: concept
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```

### 综合页面格式

```markdown
---
title: "综合标题"
type: synthesis
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```
```

Also extend the lint workflow text to mention missing or malformed frontmatter for non-system pages.

- [ ] **Step 4: Update `.claude/commands/wiki-ingest.md` to require the full schema**

Revise the command instructions so they say the command must:

```markdown
3. 写入 `wiki/sources/<slug>.md`（按照 CLAUDE.md 中的源页面格式）
6. 创建/更新关键人物、公司、项目的实体页面（wiki/entities/，必须包含 CLAUDE.md 规定的 frontmatter）
7. 创建/更新关键想法和框架的概念页面（wiki/concepts/，必须包含 CLAUDE.md 规定的 frontmatter）
```

Add one short note after the workflow stating that all created or updated normal wiki pages must follow the documented page schema.

- [ ] **Step 5: Run a grep check to verify the new rules exist**

Run: `rg -n "所有 wiki 页面都必须|type: entity|type: concept|type: synthesis|系统页面" "CLAUDE.md" ".claude/commands/wiki-ingest.md"`

Expected:
- matches for the new global frontmatter rule
- matches for entity/concept/synthesis templates
- matches for system-page exceptions

### Task 2: Add Lint Validation for Frontmatter Requirements

**Files:**
- Modify: `tools/lint.py`
- Test: `tools/lint.py`

- [ ] **Step 1: Write the failing validation design in code comments or notes**

The new lint behavior must detect:

```text
1. wiki pages missing YAML frontmatter
2. pages with frontmatter but missing required fields for their type
3. only non-system pages are checked
4. system/report files such as index.md, log.md, lint-report.md are skipped
```

- [ ] **Step 2: Run the current lint script to verify this check does not exist yet**

Run: `python tools/lint.py`

Expected:
- the script completes without reporting a dedicated frontmatter-schema section
- no explicit missing-frontmatter validation appears in the output

- [ ] **Step 3: Add a focused frontmatter validation helper in `tools/lint.py`**

Implement a small helper along these lines:

```python
REQUIRED_FIELDS_BY_TYPE = {
    "source": {"title", "type", "tags", "date", "source_file"},
    "entity": {"title", "type", "tags", "sources", "last_updated"},
    "concept": {"title", "type", "tags", "sources", "last_updated"},
    "synthesis": {"title", "type", "tags", "sources", "last_updated"},
}


def parse_frontmatter_fields(content: str) -> tuple[bool, dict[str, str]]:
    match = re.match(r"^---\n(.*?)\n---\n?", content, re.DOTALL)
    if not match:
        return False, {}
    fields = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return True, fields
```

Then integrate it into the lint flow so it collects:
- pages missing frontmatter
- pages with unknown or missing `type`
- pages missing required fields for that `type`

Keep the change small and report-oriented.

- [ ] **Step 4: Add the new lint report section**

Emit a section such as:

```text
## Frontmatter Problems
- missing frontmatter: wiki/entities/Foo.md
- missing fields (entity): wiki/entities/Bar.md -> sources, last_updated
```

If no issues are found, emit a single positive line stating there are no frontmatter problems.

- [ ] **Step 5: Run lint to verify the script still works**

Run: `python tools/lint.py`

Expected:
- exit code 0
- output includes a frontmatter validation section
- current repository pages either pass or produce concrete, actionable findings

### Task 3: Verify Current Wiki Pages Against the New Rule

**Files:**
- Modify: `wiki/**/*.md` only if lint finds real frontmatter problems in normal pages
- Test: `tools/lint.py`

- [ ] **Step 1: Run the lint script after the new validation is in place**

Run: `python tools/lint.py`

Expected:
- frontmatter findings, if any, are now visible

- [ ] **Step 2: Fix only real schema violations found by lint**

If any non-system page is missing required frontmatter, edit only the reported files and add the minimum required metadata. Use the documented templates; do not rewrite unrelated body content.

For example, an entity page should be normalized to:

```markdown
---
title: "EntityName"
type: entity
tags: []
sources: []
last_updated: 2026-04-22
---
```

- [ ] **Step 3: Run lint again to confirm the repository is clean**

Run: `python tools/lint.py`

Expected:
- no frontmatter problems reported for normal wiki pages

- [ ] **Step 4: Spot-check the graph assumptions still hold**

Run: `python tools/build_graph.py --no-infer`

Expected:
- `graph/graph.json` and `graph/graph.html` regenerate successfully
- no failures due to missing `title` or `type`

### Task 4: Final Verification

**Files:**
- Test: `CLAUDE.md`
- Test: `.claude/commands/wiki-ingest.md`
- Test: `tools/lint.py`
- Test: `tools/build_graph.py`

- [ ] **Step 1: Verify documentation and tooling together**

Run: `python tools/lint.py`

Expected:
- frontmatter validation section appears
- no syntax or runtime errors

- [ ] **Step 2: Verify graph generation still succeeds with the documented schema**

Run: `python tools/build_graph.py --no-infer`

Expected:
- graph files are written successfully
- output shows node and edge counts

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .claude/commands/wiki-ingest.md tools/lint.py wiki docs/superpowers/specs/2026-04-22-wiki-frontmatter-requirements-design.md docs/superpowers/plans/2026-04-22-wiki-frontmatter-requirements.md
git commit -m "docs: define wiki frontmatter requirements"
```
