---
name: templated-format
description: Summarises an incident channel into a post-mortem draft. Use when an incident is closed and the user asks for the write-up.
---

# Incident summary

1. Read the incident channel from the first alert to the all-clear.
2. Draft the summary in the format below, then compare every time in it with the
   channel's timestamps. The timeline rules are in [timeline.md](references/timeline.md).

## Output format

```markdown
# <service> incident, <YYYY-MM-DD>

**What users saw:** <one paragraph>
**Cause:** <one paragraph>
**What changed:** <one paragraph>
```
