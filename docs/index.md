---
title: "SQS - Skill Quality Suite: linter, security scanner and evals for AI Agent Skills"
description: >-
  An open-source quality, linting, security and validation toolkit for AI Agent Skills.
  Validate SKILL.md against the Agent Skills specification, lint instruction quality,
  scan a skill for secrets and prompt injection, check portability across Claude Code,
  Codex, Cursor and Gemini CLI, and measure whether a skill actually helps.
---

# SQS - Skill Quality Suite

**A linter, validator, security scanner and evaluation harness for AI Agent Skills
(`SKILL.md`), which also tells you which skill to fix or write next from the work you
actually do.** One command per question, no dependencies, Python standard library only.

```bash
git clone https://github.com/letsloose501/sqs-skills
python sqs-skills/skills/skill-quality-suite/scripts/sqs.py check ./my-skill
```

## What it answers

| Question | Command | Page |
|---|---|---|
| Can it load at all? Is it valid? | `sqs.py check ./my-skill` | [Skill validation](skill-validation.md) |
| Is it safe to install? | `sqs.py security ./my-skill` | [Skill security](skill-security.md) |
| What exactly did it find? | `sqs.py explain ST008` | [Quality rules](quality-rules.md) |
| Will it work on another agent? | `sqs.py compat ./my-skill --harness all` | [Compatibility](compatibility.md) |
| What should be true of it, and is it? | `sqs.py cases ./my-skill` | [Case sets](case-sets.md) |
| Does it fire, and does it help? | `sqs.py eval ./my-skill --all` | [Evaluation](evaluation.md) |
| Is it ready to publish? | `sqs.py all ./my-skill --strict` | [Publishing](publishing.md) |
| Which skill should I fix or write next? | `sqs.py discover` | [Case sets](case-sets.md) |

[Worked examples with real output](https://github.com/letsloose501/sqs-skills/tree/main/examples)
show each of these on a good skill, a weak one and a malicious one.

## Guides

- [How to validate an AI Agent Skill](how-to-validate-an-agent-skill.md) - the four
  failures that are silent, and the order to check them in
- [How to secure Agent Skills](how-to-secure-agent-skills.md) - what to look for in a
  skill you did not write, before an agent reads it

## Why a skill needs a linter at all

A skill loads in two stages: `SKILL.md` first, then its references through the links
inside it. When a link breaks, **nothing crashes and nothing complains.** The agent
silently skips the step, and the only symptom is that the work came out worse than
usual, with no explanation.

That is the shape of almost every Agent Skill defect. It survives for months because
there is nothing to notice. An AI skill checker turns each class of silent breakage
into a loud one, and sorts them by *when* they would have bitten.

Published measurements point the same way. A skill's gain is reliability, not a better
answer: in SkillAxe's comparison, quality among tasks with output was 57.1% with and
without the skill, and the whole gain was output coverage, 46.7% to 72.7%
([arXiv 2606.10546](https://arxiv.org/abs/2606.10546)) - so a skipped step is the gain
lost. Authorship matters: curated skills added 16.2 points on SkillsBench, skills the
model wrote for itself added nothing ([arXiv 2602.12670](https://arxiv.org/abs/2602.12670)).
And a stranger's skill is a supply-chain input: 26.1% of 31,132 marketplace skills carried
a vulnerability ([arXiv 2601.10338](https://arxiv.org/abs/2601.10338)), and one audit of
3,984 found 76 confirmed malicious payloads
([Snyk](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/)).

## The two halves

**Static analysis** is free, offline, deterministic and standard library only: skill
validation against the Agent Skills specification, structure and link checking,
instruction-quality linting, cross-harness portability, and security scanning. This is
the half you can run in a git hook.

**Evaluation** runs an agent, so it costs money and never runs unless you name it: does
the skill trigger on the wordings it should, does the same task come out better with the
skill than without it, and did the last edit make any of that worse.

```
                    Agent Skill
                         |
              +----------+----------+
              |                     |
        Static analysis      Runtime evaluation
              |                     |
      spec  security  quality   trigger  task  cost
              |                     |
              +----------+----------+
                         |
                  Quality report
                         |
          local CLI  ·  CI  ·  publishing
```

## Install

Through the cross-agent installer, which works for Claude Code, Cursor, Codex,
Windsurf, Gemini and the rest of the agents `skills` supports:

```bash
npx skills@1 add letsloose501/sqs-skills
```

The installer copies `skills/skill-quality-suite/` and nothing else; the test corpus,
these pages and CI stay in the repository. By hand:

```bash
git clone https://github.com/letsloose501/sqs-skills
cp -r sqs-skills/skills/skill-quality-suite ~/.claude/skills/
```

As a plain tool: clone anywhere and call `skills/skill-quality-suite/scripts/sqs.py`. It
finds the skills folder on its own, or takes `--skills-dir`.

In CI, as a [GitHub Action from the Marketplace](https://github.com/marketplace/actions/skill-quality-suite):

```yaml
- uses: letsloose501/sqs-skills@v2
  with:
    path: .
    strict: "true"
    harness: all
    upload-sarif: "true"
```

Before the commit, as a pre-commit hook:

```yaml
repos:
  - repo: https://github.com/letsloose501/sqs-skills
    rev: v2
    hooks:
      - id: skill-quality-suite
      - id: skill-quality-suite-security
```

## Supported harnesses

Portability is classified per harness from each project's own documentation: Claude
Code, OpenAI Codex, Cursor, Gemini CLI, Antigravity, OpenCode, Cline, Roo Code,
Windsurf and GitHub Copilot.

**`UNKNOWN` is never `NOT_SUPPORTED`.** Where a project's documentation is silent, the
answer is unknown rather than an invented incompatibility. An invented one reads exactly
like a real one, and that is how a compatibility tool stops being believed.

## Project

- [Source on GitHub](https://github.com/letsloose501/sqs-skills) - Apache-2.0
- [The Agent Skills specification](https://agentskills.io/specification) it validates against
- 102 coded rules, every one of them with a test that has watched it fire
- [Support](https://github.com/letsloose501/sqs-skills/blob/main/SUPPORT.md) · [Contributing](https://github.com/letsloose501/sqs-skills/blob/main/CONTRIBUTING.md) · [NOTICE](https://github.com/letsloose501/sqs-skills/blob/main/NOTICE)
