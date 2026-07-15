# Knowledge Item Schema

## YAML Frontmatter (required fields)

```yaml
---
id: "a1b2c3"                        # unique hash
title: "Article Title"              # required
source: "cubox"                     # cubox | bookmark | secnews | secnews_archive
source_url: "https://..."           # optional
ingested_at: "2026-07-14T10:00:00Z" # ISO 8601 UTC
compiled: false                     # defaults to false

# Classification (4 dimensions)
domain: "security"                  # see _MAP.md for valid domains
topic: "zero-trust"                 # free-form, auto-suggested
type: "news"                        # news | analysis | paper | tutorial | tool | opinion
difficulty: "intermediate"          # beginner | intermediate | advanced | expert

# Tags (multi-dimensional)
tags:
  - rsa-conference
  - network-security

# Extracted concepts
concepts:
  - zero-trust-architecture

# Learning state
mastery: 0                          # 0-100
last_reviewed: null
review_count: 0

# Related items
related_items:
  - "d4e5f6"
---
```

## Concept Schema

```yaml
---
slug: "zero-trust-architecture"
title: "Zero Trust Architecture"
domain: "security"
aliases: ["Zero Trust", "ZTA"]
source_items: ["a1b2c3", "d4e5f6"]
local_wiki_ref: "wiki:local:concepts/zero-trust"
updated_at: "2026-07-14T10:00:00Z"
---
```

## Task Schema

```yaml
---
task_type: "generate_learning_plan"
status: "pending"
created_at: "2026-07-14T10:00:00Z"
params:
  item_ids: ["a1b2c3", "d4e5f6"]
  options: {}
---
```
