# TODOs

## SOP Control Plane

- What: Consolidate duplicated workflow-policy prose into one live policy document, then convert `AGENTS.md`, `CLAUDE.md`, and `docs/reference-configs/*` into pointers or reference-only docs.
  Why: The control plane still has too many truth-adjacent documents, which increases cold-start ambiguity for agents.
  Pros: Cleaner source-of-truth hierarchy, lower drift, easier future review.
  Cons: Touches multiple repo-meta docs and needs careful wording cleanup.
  Context: This review intentionally left full document consolidation out of the immediate implementation scope so active-plan and handoff safety could land first.
  Depends on / blocked by: Land the shared workflow-state changes and regression tests first so the live semantics are stable before rewriting docs.

## Root Promotion

- What: Add automatic conflict ranking and merge policies for root-promotion worksets.
  Why: Two-tier promotion now fails closed when multiple books want to update the same root note, which is safe but creates manual curator work as the corpus grows.
  Pros: Lower review load, smoother multi-book promotion, better scaling across shared topic directories.
  Cons: Higher merge complexity and a real risk of silently wrong root knowledge if heuristics are sloppy.
  Context: The first delivery keeps root promotion single-writer and explicit. Conflict reports are durable artifacts, but conflict resolution is still manual by design.
  Depends on / blocked by: Keep the permit-artifact gate, lineage metadata, and root-promotion worksets stable first.
