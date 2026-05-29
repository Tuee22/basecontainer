---
name: documentation-standards
description: Authoritative documentation conventions for the hostbootstrap repo.
type: standard
---

# Documentation standards

These rules govern every file under `documents/`. They are deliberately
opinionated; consistency lets readers skim and lets writers stop
second-guessing.

## File naming

* Use `snake_case.md` for every file **except** `README.md`, `AGENTS.md`, and
  `CLAUDE.md`, which are the conventional UPPERCASE/Mixed names readers expect.
* Avoid dates, version numbers, and project names in filenames — they rot.
  Describe the topic, not the moment.

## Required header metadata

Every Markdown file starts with a YAML front-matter block:

```yaml
---
name: short-kebab-case-slug
description: One-line summary used by tools and indexes.
type: standard | reference | guide | index
---
```

Files missing this header are rejected by future linting.

## Structure

* One H1 (`# …`) per document, matching the topic exactly.
* Lead with a short paragraph (the *why*); save mechanics for sections below.
* Use H2 / H3 for navigation; do not go deeper than H4 unless absolutely
  necessary.

## WRONG vs. RIGHT examples

When a rule is non-obvious, illustrate it with a tight pair of examples:

> **WRONG**
>
> ```sh
> docker buildx build --platform linux/amd64,linux/arm64 ...
> ```
>
> The plan forbids manifest lists; multi-platform `buildx` invocations produce
> exactly the cross-arch artefact the tool is designed to avoid.
>
> **RIGHT**
>
> ```sh
> hostbootstrap base build --flavor cpu --arch amd64
> ```
>
> Single-arch, host-native, with versions/URLs computed on the host.

The point of the contrast is *to make the reasoning visible* — never include a
WRONG without explaining why it is wrong.

## Linking

Link liberally. Every claim that depends on another document should hyperlink
to it. Internal links use repo-relative paths
(`../engineering/base_image.md`), not absolute URLs, so the tree survives
forks and rebases.

## Brevity

If a document grows past ~300 lines, ask whether it should split. Two
focused documents are easier to skim than one combined one. The plan
(`HOSTBOOTSTRAP_REFACTOR_PLAN.md`) is the exception — it is intentionally one
long source-of-truth file.
