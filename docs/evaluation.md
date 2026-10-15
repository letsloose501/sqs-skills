---
title: "Agent Skill evaluation - does the skill fire, and does it help"
description: >-
  Runtime evaluation for AI Agent Skills: trigger evals with precision and recall, a
  baseline/treatment comparison that measures whether the skill improves the agent's
  work, and a regression gate between two versions.
---

# Evaluation

*Every other page on this site is about reading a skill. This one is about running it.*

Static analysis answers "is this skill intact and safe". It cannot answer the two
questions that decide whether the skill is worth having:

1. **Does it fire?** The description is the entire triggering mechanism. A skill that
   never activates is worth nothing, however good its instructions - and a skill that
   fires on a neighbour's work is worse, because it produces confident wrong work.
2. **Does it help?** Compared against the same task run with no skill at all.

Both assume a case set already exists, and writing one is the step people skip. A skill you
installed rather than wrote arrives with none at all, no author to ask, and a description
that is itself the thing in question - because nothing here tests the other half of the
promise: **does it do what it says it does?** The three sources to build a set from - what
you expect of it, each improvement as it lands, and a stranger's stated promises - are in
[where the cases come from](https://github.com/letsloose501/sqs-skills/blob/main/skills/skill-quality-suite/references/evaluating.md#where-the-cases-come-from);
`sqs.py cases <skill> --generate` drafts one from them - see [case sets](case-sets.md).

Everything here runs an agent, so it costs money and minutes and needs one installed.
Nothing runs unless you name it:

```bash
sqs.py eval ./my-skill              # prints what each layer would cost, and stops
sqs.py eval ./my-skill --trigger    # does it fire, and only when it should
sqs.py eval ./my-skill --runtime    # the task set, with the skill and without it
sqs.py eval ./my-skill --all --save v1
sqs.py eval ./my-skill --compare v1 v2
```

## Routing analysis (offline)

`sqs.py route --prompt "..."` is `eval --trigger`'s free, weaker sibling: no agent, no
cost, no `evals/` directory required. It is exactly the "where would this wording route"
judgement the next section says is not the same thing as observing activation - it reasons
about descriptions instead of running one - and ranks every skill under `--skills-dir` by
how much of the prompt's wording its description shares, naming the sentence that matched
so the ranking can be checked rather than trusted:

```bash
sqs.py route --skills-dir tests/fixtures/branch-overlap \
  --prompt "list the pull requests merged since the last release tag"
```

```
1. release-notes               0.57  "Drafts release notes from merged pull requests"
2. changelog-writer            0.43  "Use when the user asks you to summarize what changed since the last re"

`release-notes` wins by 0.14 over `changelog-writer`
```

Use it to sanity-check a description before spending on `--trigger`, or for a quick read
on a tree you did not write and have no `evals/` for at all. It cannot be wrong the way a
live run can - it never executes anything - and for the same reason it can never see what
a live run would: a skill whose description undersells what it actually does looks like a
worse match here than it is in practice.

## Trigger evaluation

The query set lives inside the skill:

```yaml
# evals/trigger/should-trigger.yaml
- prompt: "Convert this PDF into an Excel spreadsheet"
  expected: trigger

# evals/trigger/should-not-trigger.yaml
- prompt: "Write a Python HTTP server"
  expected: no-trigger
```

Each query is sent to a headless session several times, because the model is not
deterministic, and what is counted is how often the skill was actually **loaded**. That
is a harder question than any description-reading check answers: a judge asked "where
would this wording route" is reasoning about the description, while this observes the
activation.

The output is the confusion matrix and the cases behind it:

```
    fired when it should        9   (recall    90%)
    stayed quiet when it should 8
    missed                      1   (precision 82%)
    barged in                   2   (F1        86%)
```

**F1 is printed, not scored.** It weighs a miss and a false fire equally, and they are
not equal: a skill that stays quiet costs a turn, a skill that barges in costs the user
their work. Which one your tree can afford is a judgement about your tree.

Under a missed should-trigger case the report says **what loaded instead** - the first
skill each run reached for, or nothing:

```
      [0.00] did not fire: archive receipt number 2 from march
             went to: ledger-lite 3/3
```

The two misses call for different fixes. A miss to a neighbour is a boundary to draw
between two descriptions, and the neighbour's may be the one to change; a miss to nothing
is a description that does not reach the request at all. Only the first skill a run loads
counts - it is the routing decision, and anything loaded later is the agent's choice about
its task. The same counts are stored per case as `went_to`.

The last line is the bill: how many agent runs the pass made, failed ones included,
and what they reported costing. If any run reported no cost, the total reads `n/a`
rather than a partial sum - not measured is not zero. `--compare` puts the pass cost
beside the other costs, and it is judged the same way: reported, not failed, unless
`--fail-on-cost`.

The set is split 60/40 into train and validation, stratified. Tune the description
against the train failures; the validation numbers are the only thing that says the
change generalised rather than memorised the failures.

**A case that restates the description measures almost nothing.** If the description
quotes "reconcile my statement" as a trigger and a should-trigger case is "reconcile my
statement please", the case passes by string match; it says nothing about the phrasings
nobody thought to list, which is what the set is for. `EV010` counts such cases on every
`check`, whole words only, and shows the first one. On one real routing set of 105
positives it counted 37. A few are fair - a one-verb wording two neighbours both list
turns the case into a test of the fork between them - so the finding is a count at
`info`, not a verdict. Write the rest the way requests actually arrive: with context, in
other words.

### How one run is set up, and why

A trigger run is the one place this suite deliberately lets the agent act, because
loading a skill *is* the thing being measured. Four decisions make that safe and
affordable, and each was arrived at by watching the alternative fail:

| Flag | Why |
|---|---|
| **not** `--permission-mode plan` | in plan mode the model writes a plan and never calls the `Skill` tool at all. Measured against a real 29-skill tree: zero skill loads across three runs, prose about which skill would suit instead. Every query would have read as *did not fire* - recall zero for every description, and a pass that measured nothing while looking exactly like a skill that never triggers |
| `--allowed-tools Skill Read Glob Grep` | an allow-list, not a deny-list: a list of tools to forbid is only as complete as the day it was written. Nothing on this list can change anything on the machine, and a tool outside it needs an approval nobody is there to give |
| `--strict-mcp-config` | the hole an allow-list cannot close: an MCP server names its own tools, so they cannot be enumerated in advance. With no `--mcp-config` beside it, no server runs |
| `--max-budget-usd` | the routing decision lands in the first turn or two; the rest of a run is the skill doing its job, which this pass pays for and throws away. One uncapped query cost $0.62 over 19 turns against $0.14 over 4 with the cap |

`--restricted` looks like the right lever and is not: it also ignores user and project
settings, so the run loads the bundled skills instead of the tree under test. Measured
side by side, the same prompt reached the real skill without it and a built-in one with
it. A pass that cannot see the skill it is measuring is worse than one that costs more.

A capped run ends by exhausting its ceiling: it exits non-zero and its `result` event
carries `is_error` with `subtype: error_max_budget_usd`. Both are read as the cap doing
its job rather than as a failure - reading either one alone turned every capped run into
an `unusable` one, and a matrix of nothing but `unusable` looks exactly like the
description that never fires.

### What one measurement costs

Worth knowing before you start, because the number nobody publishes is the one that
decides whether this layer gets used at all. Measured on a real tree, one skill, Sonnet:

- **one run**, with the cap on: about $0.13-$0.19;
- **one measurement**, at the recommended twenty queries and three runs each: **60 runs,
  roughly $9**.

On a subscription rather than an API key - `apiKeySource: none` in the run's own `init`
event - that figure is notional. What is actually consumed is the usage window, and the
transcript reports that too: six runs moved a five-hour window by about seven points, so
one measurement is of the order of a whole window. Plan against your own limits rather
than against the dollar figure, and remember that the runs and your editor share an
account.

## Runtime evaluation

```
task
 ├── baseline   the agent with no skills at all      (claude --bare)
 └── treatment  the agent with this one skill loaded (--plugin-dir)
```

Isolation rests on two documented CLI flags. `--bare` skips auto-discovery of hooks,
skills, commands and plugins, which is what makes a baseline a baseline: without it the
skill under test is installed on the machine doing the measuring and **both** arms can
reach it. A provider that cannot isolate says so in its report instead of calling the
comparison a baseline.

**`--bare` needs an API key.** Its own help is explicit: Anthropic auth under it is
strictly `ANTHROPIC_API_KEY` or an `apiKeyHelper` supplied through `--settings`, and
OAuth and the keychain are never read. So on a machine signed in with a subscription and
no key, this pass cannot run at all, while the trigger pass above - which does not use
`--bare` - runs fine. Set `ANTHROPIC_API_KEY` before reaching for `--runtime`, and know
that the two passes are then billed down two different paths.

```
                           treatment    baseline       delta
  task success                  100%          0%       +100%
  runs that loaded it              4         n/a         n/a
  tool calls                     1.5         0.5        +1.0
  tokens                      1960.0       815.0     +1145.0
  cost USD                    0.0340      0.0100     +0.0240
  safety violations                0           0           0
```

Three rules the numbers obey:

- a treatment run is credited only when the transcript shows **the skill loading**. The
  arm has the skill available; that is not the same as using it, and a task the model
  wins with the skill unread is the model's win. Such runs are counted separately, as
  `passed_without_skill`, and the report says how many there were - that number is what
  the delta has to be read against;
- a task with no assertions comes back **ungraded**, never as a pass. Counting it would
  turn "nobody said what success is" into evidence of success;
- a metric the provider never reported comes back **`n/a`**, never as zero. A zero is a
  measurement, and inventing one is how a comparison quietly starts lying about cost.

**Nothing runs a skill that can act on the machine until you say so.** The treatment arm
runs the agent with permission checks bypassed - the Claude Code CLI's own help recommends
that only for sandboxes with no internet access - and the only isolation is a fresh working
directory. So before anything runs, the pass reads the skill with the capability and
security engines, and a skill that can reach the network or spawn a process (`CB001`,
`CB002`), runs commands on load (`CB004`), hides what it runs (`CB005`, `SE008`), or
carries a destructive command, an override, hidden characters or an upload (`SE002`-`SE005`)
is refused with those findings named. `--trust-target` is you saying the skill is yours or
has been read. An `sqs-allow` waiver does not open the gate: in a stranger's skill it is
written by the same author whose skill is in question. The trigger pass is not gated - it
runs with four read-only tools and no MCP servers, so a skill it loads cannot execute
anything.

**Nothing is spent on a set that cannot measure.** Before the first run the pass reads
the set and refuses it when any case is still a draft (a field opening with `TODO`),
names a fixture that is not in the skill, carries a `re:` that does not compile, or checks
the text inside a binary output - and when no case at all has something to grade. The
same reading runs free on every `check` as `EV008` (a case that cannot pass or fail) and
`EV009` (a case that cannot run as written), so the refusal is never the first an author
hears of it. `EV011` is the one it does not refuse: a case that puts an output under
`files`, which skill-creator's format, the one `evals.json` is read as, reserves for
inputs.

Assertions are substrings, regexes behind `re:`, prohibitions behind `not:`, and
`outputs` the run had to create - by existence, or with `contains` by what is inside
them, in the same grammar. Where correctness is a property no substring can express, a
`judge` program runs after the task in its working directory and its exit code decides;
it is the skill's own code, so it runs only under `--trust-target`. **Safety violations** are the security module's own command
patterns applied to what the agent actually ran, so a rule reported at rest and a rule
reported in flight cannot drift apart.

### Process: how the run got there

Everything above grades what a run left behind. A skill that says "read the ledger, then
append one row" is also served by a run that appends three rows blind and still prints
the right balance - and every assertion, output and judge passes it. SkillForgeBench
(arXiv 2610.14918) grades the two halves apart, completion rubrics and process rubrics,
and finds strict process scores far below loose ones: following most of the steps and
following all of them are different measurements. `process` is the second half:

```json
"process": [
  {"id": "read-first", "order": ["Read:ledger.csv", "Edit|Write:ledger.csv"]},
  {"id": "read-back",  "after": "Edit|Write:ledger.csv", "then": "Read:ledger.csv"},
  {"id": "one-row",    "count": "Edit|Write:ledger.csv", "max": 1},
  {"id": "offline",    "never": "WebFetch|WebSearch"}
]
```

A matcher is `Tool` or `Tool:<assertion>` - names joined by `|`, then the assertion
grammar above, applied to the call's input as the transcript recorded it.

| form | passes when | the paper's category |
|---|---|---|
| `order: [A, B, ...]` | the matchers occur in this order, others between them allowed | phase adherence |
| `after: A, then: B` | some `B` comes after the **last** `A` | verification loop |
| `never: A` | no call matches | scope discipline |
| `count: A, min, max` | the number of matching calls is within bounds | scope discipline |

`after` anchors on the last `A` because a file read back before it was edited again
verifies nothing about what was left; and an `A` that never came fails the item, since a
check of a change that never happened is not a verified run. The paper grades its rubrics
with a model. These are deterministic for the same reason `judge` is a program - and the
limit is the same one stated plainly: a step that is only thought ("choose the template
that fits") leaves no tool call, so no matcher can see it, and it stays the author's to
judge. Inputs are kept up to 2000 characters per call; check long file content through
`outputs.contains`, not a matcher.

The scripted fixture shows the case it exists for - the same answer and the same ledger
row, reached by writing blind, searching the web and writing twice:

```
                             treatment    baseline       delta
  task success                    100%          0%       +100%
  process followed                  0%          0%          0%
  process items met                 0%         50%         50%
  strict (both)                     0%          0%          0%
```

- **process followed** is strict: the share of runs where every item held. It carries
  the same gate as task success - a procedure followed with the skill unread is the
  model's habit, not the skill's instruction.
- **process items met** is loose: the mean share of items held, not gated, read like
  `tool calls`. The baseline's 50% is its `count` and `never` items holding because it
  did nothing at all - which is why the strict number is the one the gate reads.
- **strict (both)** is completion and process in the same run.

All three are over the cases that carry `process`, and none of the rows appears when no
case does. Task success keeps its old meaning, so a run saved before `process` existed
still compares. The pre-flight refuses an item it cannot grade - an unknown or doubled
form, `after` with no `then`, a bad `re:`, an inverted `count`, a matcher still opening
with `TODO` - and `cases --generate` drafts one `order` item from the numbered steps in
the body, a `TODO` per step for exactly that reason: which call shows a step happened is
the author's knowledge, not the text's. `CS004` reports a skill whose body numbers three
or more steps while its set carries no `process` at all.

## Regression gate

```
REGRESSION DETECTED   v1 → v2

  ! task success          100% → 50%
    trigger precision     100% → 67%   (noise ±25%)
    trigger recall        100% → 100%   (noise ±50%)
  ! token usage           1960 → 2810   +43%
  ! cost                  0.051 → 0.081   +59%

  tasks that got worse:
    ledger-02               100% → 0%

  trigger cases that flipped:
    [0.00 → 1.00] should no-trigger: Rename every receipt photo in this folder by date
```

Quality falling fails the gate, and process is quality: `process followed` and `strict
success` sit beside task success, and a task whose procedure stopped being followed is
listed as `<id> (process)` under the tasks that got worse - even when every answer still
came out right. Cost rising is reported and does not, because a skill
that got 18% more expensive and 20% more reliable is a trade somebody has to look at,
not a build to break; `--fail-on-cost` moves the line when a budget depends on it.

**A trigger drop has to be larger than the runs' own noise.** Each query was run several
times, and how often it fired is kept; the gate redraws every query's runs a couple of
thousand times from what they showed and fails only when the drop survives in 95% of the
redraws. In the example, precision fell from 100% to 67% on one flipped case in a small
set measured three times a query - inside the noise, so the flip is listed and the gate
does not fire on it. With one run per query there is no spread to read, and the row says
`noise not measured` and falls back to a fixed five points. Task success has no such
redraw yet and uses the fixed line.

**An edit can take a neighbour's requests.** A description rewritten to fire more often
loses nothing on its own trigger set and quietly wins the requests of the skill beside
it - so measure the neighbours too:

```
sqs.py eval ./my-skill --trigger --with-neighbours 2 --save before
... edit the description ...
sqs.py eval ./my-skill --trigger --with-neighbours 2 --save after
sqs.py eval ./my-skill --with-neighbours 2 --compare before after
```

The neighbours are the skills whose descriptions share most words with this one and
that have a trigger set of their own; each prints its own block, and a neighbour whose
recall fell is the edit's regression. They join the trigger pass only - their tasks were
not edited.

When a trigger run is split, the report also says when train F1 sits above validation by
more than the runs vary. One study of production skill descriptions reads that gap as
scopes that genuinely overlap, which rewording does not fix (arXiv 2606.30775).

## If you only use Claude Code

Claude Code ships `claude plugin eval` (v2.1.269+), which answers the first two questions
above for a plugin: it runs each case with and without the plugin, grades the result with
regex, tool-use, file and judge graders, and writes an HTML report. If Claude Code is the
only agent you care about and your skill is packaged as a plugin, use it.

Two things it does not do, and they are why this page exists. It has no regression gate:
nothing stores a run and diffs the next one against it, so "did my last edit make this
worse" stays unanswered. And it runs on one engine, so it cannot tell you which model does
your task well enough to be worth sending the work to. The case formats do not convert
between the two, so pick one per skill rather than keeping both.

## See also

- [Test plugins with evals](https://code.claude.com/docs/en/plugin-evals) - Claude Code's
  own runner, compared above
- [`references/evaluating.md`](https://github.com/letsloose501/sqs-skills/blob/main/skills/skill-quality-suite/references/evaluating.md)
  - the working detail: writing queries, writing assertions, and the part that stays a
  human's job
- [Case sets](case-sets.md) - where the queries and tasks this page runs come from
- [Skill validation](skill-validation.md) - the free, offline half
