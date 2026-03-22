---
type: index
status: active
created: "{{created}}"
updated: "{{updated}}"
---

# Knowledge Base Progress Dashboard

> Last updated: {{updated}}

## Overall Progress

| Metric | Count |
|--------|-------|
| Total source files | {{total_files}} |
| Converted | {{converted_count}} |
| Split into notes | {{split_count}} |
| Linked | {{linked_count}} |
| Done | {{done_count}} |
| Errors | {{error_count}} |
| **Completion** | **{{completion_pct}}%** |

## Pipeline Phase

Current phase: **{{current_phase}}**

```
init ─▶ scan ─▶ convert ─▶ split ─▶ link ─▶ summary ─▶ registry ─▶ view ─▶ done
{{phase_marker}}
```

## Per-Category Status

<!-- kb-creator:category-progress:start -->

| Category | Total | Pending | Converted | Split | Linked | Done | Error | % |
|----------|-------|---------|-----------|-------|--------|------|-------|---|
{{#categories}}
| {{name}} | {{total}} | {{pending}} | {{converted}} | {{split}} | {{linked}} | {{done}} | {{error}} | {{pct}}% |
{{/categories}}
| **Total** | **{{total_files}}** | **{{total_pending}}** | **{{total_converted}}** | **{{total_split}}** | **{{total_linked}}** | **{{total_done}}** | **{{total_error}}** | **{{completion_pct}}%** |

<!-- kb-creator:category-progress:end -->

## Quality Issues

<!-- kb-creator:quality-issues:start -->

{{#issues}}
- [ ] **{{severity}}** — [[{{note_name}}]]: {{description}}
{{/issues}}
{{^issues}}
No quality issues detected.
{{/issues}}

<!-- kb-creator:quality-issues:end -->

## Recent Activity

<!-- kb-creator:activity-log:start -->

{{#activity}}
- `{{timestamp}}` {{action}}: {{detail}}
{{/activity}}

<!-- kb-creator:activity-log:end -->
