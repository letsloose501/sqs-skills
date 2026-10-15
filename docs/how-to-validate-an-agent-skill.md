---
title: "How to validate an AI Agent Skill"
description: >-
  A practical walkthrough of validating an Agent Skill: the four failures that are
  silent, what a strict validator catches that your client does not, and the order to
  check them in. With real tool output at each step.
---

# How to validate an AI Agent Skill

*The hard part of skill validation is not the YAML. It is that the four worst failures
are all silent.*

An Agent Skill is two files and a promise: `SKILL.md` carries the instructions, the
`references/` beside it carry the detail, and the promise is that the agent will read
the second when the first tells it to. Nothing enforces the promise. When it breaks, no
exception is raised and no warning is printed - the agent simply skips a step, and the
work comes out slightly worse than it did last week.

So "validate the skill" has to mean four different checks, because they break at four
different moments.

## 1. Will anything load it

Start with the mechanical layer, because it is cheap and absolute. The
[Agent Skills specification](https://agentskills.io/specification) asks for frontmatter
with `name` and `description`, a name of lowercase letters, digits and single inner
hyphens, at most 64 characters, **equal to the folder name**, and a description at most
1024 characters.

```bash
python scripts/sqs.py spec ./my-skill
```

The trap here is not strictness, it is **inconsistency between readers**. A lenient
client warns about a mismatched `name` and loads the skill anyway; a strict reference
validator and the publication path reject it. That is the worst possible split: the
skill works on the machine where it was written and fails the first time somebody else
touches it.

The same shape repeats for an XML tag in a description, for a vendor word in a name, and
for a block-scalar description (`description: >-`) that is perfectly good YAML and is
flagged non-portable by the vendor-neutral validators.

Fix these first. They are the only findings with exactly one right answer, which is why
a fixer can apply them for you:

```
$ sqs.py fix ./my-skill --apply
fixed  renamed-folder  SP004  name: some-other-name -> renamed-folder
```

## 2. Does every pointer still resolve

This is the check that earns the tool.

A skill loads in two stages, and the second stage is a set of relative links inside the
first. Rename `references/format.md` to `references/layout.md` and the link in
`SKILL.md` becomes a pointer to nothing. The agent activates, reads `SKILL.md`, reaches
the line that says "open the house format", finds nothing, and carries on with what it
already knows.

Nobody gets an error. The only symptom is that the output no longer follows the house
format, and the obvious explanation - "the model is having a bad day" - is wrong.

```bash
python scripts/sqs.py structure ./my-skill
```

Run this immediately after **any** rename. That single moment is when almost every
defect in this class is created:

- a link to a file that is not there (`ST001`), including one resolved from a
  reference's own folder (`ST002`);
- a pointer to a **section** that has since been renamed (`ST008`) - the file is there,
  the heading is not, and the agent reads the whole file instead of the part you meant;
- an orphan (`ST005`): a file nothing links, so nothing ever loads it. Either it is
  unwired or it is no longer needed, and only you know which;
- an outbound path into a vault or repository that has moved (`ST011`).

And the quieter cousin: **budgets**. `SKILL.md` is loaded on every activation, so a
20 KB one costs tokens on every single turn whether or not the task needed them
(`ST006`). A reference is opened whole, so a 30 KB reference cancels the point of
two-stage loading (`ST007`).

## 3. Do the instructions read like instructions

A skill can pass every check above and still be a bad skill. Two failures dominate.

**The description says what, never when.** The description is the entire triggering
mechanism: it is the only part of the skill the agent sees before deciding whether to
load the rest. "An assistant for spreadsheets that reads tables and computes totals" is
a fine sentence about a skill and contains no condition under which to reach for it.

```
$ sqs.py check ./what-not-when
⚠️ what-not-when
     ⚠️  QL002 description says what the skill is and never when to reach for it (SKILL.md)
```

**The steps have no completion criterion.** "Read the diff carefully and be thorough"
cannot be finished. The agent cannot tell done from not-done, so it stops when it feels
like stopping, and the run-to-run variation gets blamed on the model:

```
     ·  QL006 be thorough, where appropriate - lines 8, 9 (SKILL.md:8)
```

Rewrite each step to end on something checkable: "stop when every modified model has an
entry", not "make sure it is complete".

Two more in this class are worth knowing because they are invisible from the inside: a
description written **about itself** ("This skill helps you...") rather than as an
instruction about when to act, and a bundled script that **waits for input** - agents
run in non-interactive shells, so `input()` hangs the run until something kills it.

These rules are heuristics, and a heuristic that cannot point at a line does not belong
in a linter. Every one of them names a file and a line, and each carries a **detection
confidence** and a **false-positive risk** so you know how much of the judgement is the
machine's:

```
$ sqs.py explain QL003
QL003  One branch written twice
severity warning
detection confidence low · false positives high
```

`--min-confidence high` keeps the filesystem and parse facts and drops the prose
heuristics. That is the setting to leave on in CI; the heuristics are for the pass you
do by hand.

## 4. Will it work anywhere but here

The check your own machine cannot make for you. A hard-coded
`~/.claude/skills/other-skill/references/x.md` works perfectly where it was written and
resolves to nothing on any other agent - silently, again, because a missing reference is
a skipped step rather than an error.

```bash
python scripts/sqs.py compat ./my-skill --harness all
```

The important discipline in this layer is what it refuses to say. Where a harness's own
documentation is silent, the verdict is `UNKNOWN`, not `NOT_SUPPORTED`. An invented
incompatibility reads exactly like a real one, and one of them makes every other row
worth less.

## The order that works

```bash
sqs.py fix   ./my-skill --apply          # the mechanical ones
sqs.py check ./my-skill                  # structure, spec, quality, compat, security
sqs.py check ./my-skill --format board   # one line per layer, for deciding
sqs.py all   ./my-skill --strict         # before it leaves your machine
```

Then the part no validator does: read the skill against a rubric, and if it matters,
**run it**. `sqs.py eval --trigger` measures how often the skill actually loads on the
wordings a human would type, and `--runtime` runs the same task with the skill and
without it. A skill that validates perfectly, fires reliably and changes nothing about
the output is still load the agent pays for.

## In CI, so it stays true

```yaml
- uses: letsloose501/sqs-skills@v2
  with:
    path: .
    strict: "true"
    harness: all
    upload-sarif: "true"
```

A skill repository with this gate cannot acquire a broken pointer without somebody
noticing, which is the whole point: the defect class this page is about is the one that
nothing else notices.

## See also

- [Skill validation reference](skill-validation.md) - the same material as a reference
- [How to secure Agent Skills](how-to-secure-agent-skills.md)
- [All 106 rules](quality-rules.md)
