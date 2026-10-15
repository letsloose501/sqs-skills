---
title: "Writing a skill's case set - what should be true of it, and is it"
description: >-
  Where the checks for an AI Agent Skill come from: what you expect of it, each
  improvement it gains, and what its description promises - and what it means when those
  three disagree.
---

# The case set

*Every expensive layer in this suite assumes a case set that already exists. This is
the one that helps you write it.*

```bash
python scripts/sqs.py cases ./my-skill                      # the three disagreements
python scripts/sqs.py cases ./my-skill --generate           # the draft case file
python scripts/sqs.py cases ./my-skill --generate --apply   # write it
python scripts/sqs.py cases ./my-skill --from-history       # trigger queries you typed
```

## Why this comes first

`eval --trigger` needs queries somebody wrote. `eval --runtime` needs tasks somebody
wrote. The regression gate needs two runs of that set - it is a working gate with
nothing underneath it, and over a set that never grows it prints *no regression* about
behaviour it has never sampled. A stranger's package has no `evals/` at all; your own
has whatever you had patience for on the first day.

Two ways a skill wastes your time, and nothing else here catches either:

- **it passes every check and still does not deliver.** Intact, safe, well written,
  visibly doing *something* - and not the thing it advertised. That skill is worse than
  no skill: it occupies the routing slot, costs context on every turn, and the failure
  is silent, because nothing about it looks broken;
- **you improve it and the improvement is a downgrade.** It answers worse, or burns
  three times the tokens for the same answer, and the only detector is you noticing
  months later, twenty commits after the change that did it.

## Three sources, not three phrasings of one

| Source | Where it lives | What it is good for |
|---|---|---|
| what you expect | `evals/expectations.md`, one list item per claim | the only source that survives the skill being wrong about itself, and the only one that exists before the skill does |
| each improvement | a capability gained since `--since` | the cheapest moment to write a case is while you still remember what you changed |
| what it promises | the description's outcome clause | when you have neither the author nor a written expectation, this is all there is |

`evals/expectations.md` is plain markdown you write by hand. **One list item is one
claim**; prose around the items is your note to yourself and is never read as an
expectation.

```markdown
# What I want this skill to do for me

- Pick out every decision a pasted transcript records and tell me who owns it.
- Never ask me to paste the transcript a second time.
```

The improvement source is the composition of two other things the suite already does:
`--since` (a git ref, or a directory holding an earlier copy - see
[Publishing](publishing.md)) and the capability module. The trigger is a **capability**
changing, not a file changing: a typo owes nobody a check.

## What the disagreement means

| expectation | promise | behaviour | reading |
|---|---|---|---|
| ✓ | ✗ | - | **wrong skill** - it never claimed to do what you need |
| ✓ | ✓ | ✗ | **broken skill**, or a description that oversold |
| ✗ | ✓ | ✓ | **fine skill, not for you** |
| - | ✗ | ✓ | **undeclared capability** - it does `Z` and says nothing about it |

Three of those four rows are visible without running anything, and those are the rules:

| Rule | Row | What it reads |
|---|---|---|
| `CS001` | broken skill | the description commits to leaving something behind, and no step in the body writes, saves or files it |
| `CS002` | wrong skill | an expectation whose wording the description shares none of - and the sibling skill that does, when the tree holds one |
| `CS003` | undeclared capability | a bundled script reaches the network or spawns a process, and no wording anywhere in the skill says so |

The fourth row - *broken skill* proved by behaviour rather than by reading - is what
`eval --runtime` is for, over the case set this command drafts.

```
· chart-plotter
     ·  CS002 expected `Pick out every decision a pasted meeting transcript records ` -
        the description shares no wording with it; `summary-writer` is closer.
        Not a defect: the wrong skill for this expectation (evals/expectations.md)
     ·  CS003 imports `subprocess` - can spawn a process - and no wording in the skill
        announces it (scripts/plot.py:8)
⚠️ summary-writer
     ⚠️  CS001 the description promises `Writes a dated summary` and no step in the body
        writes, saves or files anything
```

`CS002` is `info` on purpose and says *not a defect* in its own message. The skill is
fine; it is the wrong skill for what you wrote beside it, and a report that graded that
as a fault would be teaching you to ignore it.

## Steps nobody checks

One more source sits in the body itself: numbered steps. A skill that says *check
`payables.csv` for the invoice number, then append the row* has a procedure, and a set
that grades only the row passes a run that appends first and never checks. `CS004`
reports a body with three or more numbered steps, a runtime set beside it, and no case in
that set carrying [`process`](evaluation.md#process-how-the-run-got-there). It is `info`:
a numbered list of options reads exactly like a list of steps, and two numbered lines are
not counted at all.

`--generate` drafts the missing case: one `order` item, one matcher per step, each a
`TODO` with the step's text and any code span in it as a hint. For the scripted
`ledger-lite`:

```json
"process": [{"id": "steps-in-order", "order": [
  "TODO: step 1 - Read the amount, the date and the counterparty off whatever ",
  "TODO: step 2 - Append one row to ledger.csv in that order. Stop when the ro (hint: ledger.csv)",
  "TODO: step 3 - Print the new balance, with the currency, on its own line."]}]
```

The pre-flight refuses it until each one names the tool call that shows the step
happened. That call is the author's knowledge, not the text's: step 3 above leaves no
call at all and belongs in `assertions`, so it is deleted from the item rather than
guessed at.

## The draft is a draft

```
chart-plotter: 3 case(s) drafted
  expectation  chart-plotter-exp-01   Pick out every decision a pasted meeting transcript
  promise      chart-plotter-pro-01   TODO: a request that should make the skill `saves it as
  improvement  chart-plotter-imp-01   TODO: a request that exercises `CB002 imports `subproces
  would write evals/evals.json (pass --apply)
```

Every generated case carries `source` and `needs_review`, and an assertion appears only
where the source text named something checkable - a file extension, a literal the answer
has to carry. Everything else is `TODO`, because a case that passes without having
tested anything is the one output the grader already refuses to produce, and a heap of
them would be worse than the empty `evals/` it replaced. A case with no assertion and no
file stays `ungraded` in every report.

`--apply` never overwrites an existing `evals/evals.json`. Generated is not trusted: a
set nobody can correct is a set nobody will believe, which is the same mistake as a
linter whose rules cannot be suppressed.

## Trigger queries in your own words

A trigger set the author writes tends to restate the description - `EV010` counts how
often, and on one real routing set it was 37 of 105 positives. The phrasings that test a
description are the ones people actually typed, and Claude Code already keeps them: a
JSONL transcript per session under `~/.claude/projects/`. `--from-history` reads those,
locally and read-only, and drafts `evals/eval_queries.json`:

- a **positive** is a prompt whose *first* tool call loaded this skill. The first call is
  the routing decision; a skill loaded after other work in the same turn was the agent's
  choice about its task;
- a **near miss** is a prompt whose first call loaded a neighbour, ranked by how much of
  it this skill's description also covers - the wording a neighbour won and this skill
  could plausibly have claimed;
- left out: a typed `/command`, a prompt that names the skill it loaded (that is a
  lookup, not routing), a subagent's sidechain, and anything over 400 characters, which is
  a pasted document rather than a wording.

On the transcripts of one real machine the positives restated their skill's description
far less often than the hand-written set did (0 of 38 for the busiest skill), and the
near misses for a video skill came out as exactly the fork with its neighbour: "разбери
видео как творчество" went to the neighbour, as it should. The history also turned up a
real misroute - a link with "разгрузи видео" whose first load was a notes skill.

It is a draft, and more so than the others: a reply like "yes, go ahead" can be the
prompt a skill loaded after, and out of context it is not a wording. Everything it prints
is your own words, so it is printed for review and written only with `--apply`, and only
where the skill has no trigger set yet.

## Which skill to fix or write next

`--from-history` needs a skill to harvest for. `discover` asks the question one level up:
across all your sessions, where does the work go?

```bash
python scripts/sqs.py discover
```

It reads the same transcripts, but from the agent's actions rather than the prompt's
wording - which skill loaded, which scripts ran, which files changed - because a first
attempt at classifying prompts by their words was measured as noise on 1,058 real ones.
Two lists come out:

- **skills whose own scripts ran in sessions that never loaded them.** A script inside
  `.claude/skills/<skill>/` run from the shell, before that skill loaded anywhere in the
  session, in a session that did not edit the skill (a session editing a skill is testing
  it). Either the description missed those requests, or something else - a `CLAUDE.md`, a
  hook - sends the agent to the script directly. `improve <skill>` lists the prompts;
- **work repeated with no skill loaded.** A document changed, or a script run, in two or
  more sessions that had loaded no skill up to that turn. Left out: a script that was
  itself edited somewhere (the project being built, not a tool being used), source code,
  the harness's own files (`MEMORY.md`, `CLAUDE.md`, `.claude/`), scratch files, and a
  script name that only appears inside a heredoc or a commit message.

On one real history of 678 sessions, the first list named a notes skill whose link checker
ran in 27 sessions that never loaded it, and the second list was led by a planning
document edited in nine sessions with no skill loaded - a task nobody had written a skill
for. Every row prints the prompts that led to it, because whether two rows are one task
is a judgement, and the skill's instructions leave it to the agent running it, in
conversation: propose, and write nothing until the user says yes.

With a mistakes journal configured (`"mistakes": "path"` in `sqs.config.json`, or
`--mistakes-dir`), `discover` adds a third list: the skills the journal names, and how
often, counting the entries a review already cleared from the folder but git still has.
`improve <skill>` prints their patterns. The journal's format and the review that turns
repeats into rules and gates are in
[mistakes-journal.md](https://github.com/letsloose501/sqs-skills/blob/main/skills/skill-quality-suite/references/mistakes-journal.md).

## What this is not

- **not a score.** "78% honest" is unactionable, and the one-number headline this
  project rejected everywhere else;
- **not a model.** Nothing here asks a model what a description means. A model that
  invents a claim and then grades its own claim has measured nothing, so every claim
  above comes from a pattern you can read in `scripts/cases.py` or from a sentence you
  wrote yourself. The prose-to-claims layer that would need one stays opt-in and outside
  `check`;
- **not a case per edit.** The trigger is a capability changing, not a file.

## The limits, stated

`CS001` reads the outcome clause of a description with a pattern, so a promise phrased
in a way the pattern does not carry is a promise it will not see. It reads the part of
the description **before** the trigger lead-in: *use when a bank export lands in the
downloads folder* is when the skill fires, not what it produces, and reading a promise
out of it produced exactly that nonsense before the split went in.

`CS003` covers reaching the network and spawning a process. Reading the environment is
out of scope on purpose: the words an author announces it with - *environment*,
*variable*, *config* - are ordinary prose in the same breath in both languages the
corpus is written in, so the test cannot tell an announcement from the subject matter.
`sqs.py capabilities` still reports the capability itself; what is withdrawn is only the
claim that nobody mentioned it.

## See also

- [Evaluation](evaluation.md) - running the set this page drafts
- [Publishing](publishing.md) - `--since`, shared with the version rules
- [Quality rules](quality-rules.md) - `CS001` to `CS004` in the registry
