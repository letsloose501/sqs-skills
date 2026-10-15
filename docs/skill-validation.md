---
title: "Skill validation - validating SKILL.md against the Agent Skills specification"
description: >-
  How to validate an AI Agent Skill: frontmatter against the Agent Skills
  specification, broken references, orphaned files, context budgets and the
  instruction-quality rules a strict validator does not cover.
---

# Skill validation

*An agent skill validator answers three different questions, and they fail at different
moments.*

```bash
python scripts/sqs.py check ./my-skill      # all five static modules
python scripts/sqs.py spec ./my-skill       # specification conformance alone
python scripts/sqs.py structure ./my-skill  # links, orphans, budgets
python scripts/sqs.py fix ./my-skill --apply
```

## 1. Will a loader take it

The [Agent Skills specification](https://agentskills.io/specification) requires `name`
and `description` in the YAML frontmatter, a name of lowercase letters, digits and
single inner hyphens, at most 64 characters, matching the folder, and a description at
most 1024 characters.

What actually happens is split, and that split is the reason skill validation matters:
**a lenient client warns and loads the skill anyway, while a strict validator and
publication reject it.** So the skill works on your machine and fails the moment it
leaves.

The suite reports these as `SP001`-`SP019`. The ones worth knowing:

- `SP004` - `name` does not match the folder. Works locally, refused on publication.
- `SP011` - an unclosed code fence. Everything after it reads as code, so the
  instructions that follow stop being instructions.
- `SP015` - a block scalar (`>-`) description: valid YAML, flagged non-portable by the
  vendor-neutral validators.
- `SP018` / `SP019` - an XML tag in a field, or a vendor word in the name. Both refusals
  arrive at upload, after the skill is finished.
- `SP020` - a bare `<` or `>` in the description, an arrow or a comparison. Not a tag,
  so `SP018` passes it, but the validator the reference skill-creation tooling ships
  refuses any angle bracket, and its packager runs that validator first.

## 2. Will every pointer still resolve

This is the class that breaks **today, in silence**. A skill points into
`references/`, the file was renamed, and nothing crashes: the agent skips the step, and
from outside it looks like the work came out weaker than usual.

- `ST001` / `ST002` - a link to a file that is not there, including one resolved from a
  reference's own folder.
- `ST003` / `ST004` - a link into a neighbouring skill that does not exist, or into a
  file it does not have.
- `ST005` - an orphan: a file nothing links, so nothing ever loads it.
- `ST008` - a pointer to a section that has since been renamed.
- `ST006` / `ST007` - over the context budget. `SKILL.md` is loaded on every activation;
  a reference is opened whole.
- `ST011` - an outbound path that no longer exists on disk.

Run `sqs.py structure` after any rename. That is the single moment this class of defect
is created.

## 3. Does it read like an instruction

A skill can be perfectly valid and still be a bad skill. These rules (`QL001`-`QL019`)
are heuristics, and each one names a file and a line so you can judge it:

- `QL002` - the description says *what* the skill is and never *when* to reach for it.
  The description is the entire triggering mechanism; without a "when", the skill does
  not fire.
- `QL006` - an instruction with no completion criterion ("be thorough", "as
  appropriate"). The agent cannot tell done from not-done.
- `QL010` - a description written about itself ("This skill helps you...") rather than
  as an instruction about when to act.
- `QL015` - the same mistake turned round: a skill with `disable-model-invocation: true`
  whose description is still written for the router ("trigger on", "when the user asks",
  a list of quoted wordings). The model never sees that description, so the words have
  no reader. `use when` alone does not count - it reads fine to a person too.
- `QL011` - a bundled script that waits for input. Agents run in non-interactive shells,
  so it hangs until something kills it.
- `QL016`-`QL019` - four of the skill smells catalogued in "From Anatomy to Smells"
  (arXiv 2607.01456): a procedure written as one long paragraph in a body with no steps,
  no example anywhere, output produced and never checked, and an output format named
  but never shown. The paper detects these with a model; these rules carry only the
  shape a pattern can read, so they fire far less often than the paper's prevalence
  figures (on 126 real skills: once, three times, once, never). QL016 does not ask for
  numbered steps in general - the same paper counts a rigid series of commands as a
  smell too - only for a procedure that has no structure at all. The paper's "Never
  Asks Human" was tried and withdrawn: on the installed tree it was calibrated against,
  every skill it fired on was a false positive, because the actions that call for
  asking (push, delete, publish) are also the subject matter of skills that never need
  to ask. `SE002` keeps the decidable part, a destructive command whose step should ask.

Each rule carries a **detection confidence** and a **false-positive risk**, printed by
`sqs.py explain <CODE>`. `--min-confidence high` keeps the filesystem and parse facts
and drops the prose heuristics, which is the gate you can leave switched on in CI.

## Reading and acting on the report

```
⛔ SP004  `name: video-tools` does not match the folder `video` (SKILL.md)
⚠️  ST006  SKILL.md is 21370 B > the 15000 B budget (SKILL.md)
·   QL006  as needed - lines 191, 295 (SKILL.md:191)
```

- **error** - fix it. Nothing here is cosmetic.
- **warning** - a decision, not a defect. An orphan file is either unwired or no longer
  needed, and only you know which.
- **info** - a nudge. Real, small, safe to leave.

1. `sqs.py explain <CODE>` for the reasoning, then the fix.
2. `sqs.py fix --apply` for the mechanical repairs - the ones with exactly one right
   answer. It deliberately will not shorten an over-long description: there is no single
   right shortening, and picking one for you deletes a trigger you needed.
3. The rest by hand.

For findings that are correct-and-intended there are four scopes of escape hatch:
`sqs-allow: CODE` on a line, `sqs-allow-file: CODE` in a file header, `sqs.config.json`
for the tree, and `.sqsignore` for a subtree that is not skill payload at all.

## See also

- [The full rule list](quality-rules.md), all 100, with the reasoning for each
- [Skill security](skill-security.md) - what to run before you install a stranger's skill
- [Worked examples with real output](https://github.com/letsloose501/sqs-skills/tree/main/examples)
