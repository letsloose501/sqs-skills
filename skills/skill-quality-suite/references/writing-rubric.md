# The reading pass

What no script can check. `sqs.py quality` reports what it can count and point at; this
is the rest, and it is where most of the improvement actually is.

Work through the sections in order, on one skill at a time, with the file open. Each
question is answered with evidence from the file - a line number, a quoted phrase - or
it is not answered. "Looks fine" is the answer that makes this pass worthless.

The vocabulary below (context pointer, the two loads, information hierarchy,
completion criteria, leading words, sediment) is Matt Pocock's, from
[`writing-for-agents`](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents).
The rest is what this suite has learned from skills that broke.

## 1. The pointer

The description is a **context pointer**: a reference held in the agent's context that
names material out of context and encodes the condition for reaching it. Its *wording*,
not its target, decides when the agent reaches the material and how reliably.

- Does the pointer do both jobs - say what the material is, **and** list the branches
  that should trigger reaching it? A pointer that only does the first leaves firing to
  chance.
- Is there one trigger per **branch**? A branch is a distinct case the skill handles.
  Synonyms that rename one branch are one branch written twice.
- Does each branch know **what it produces and where that lands**? A branch is fully
  specified by three things: the wording that reaches it, the outcome it owes, and the
  place the outcome ends up - a file, a section, a reply, a commit. Branches with no
  named destination are where output quietly evaporates, and the gap does not show in
  the description at all: it shows later, as a skill that "ran fine" and left nothing.
- Does the leading word come first? The front of the description is where it does its
  triggering work.
- Is there identity the body already carries - the skill's own name, a restatement of
  its purpose? Cut it. Every word of an always-loaded pointer costs on every turn.

**The trap that costs the most.** A description **attracts** on topic match; it does not
repel. Writing "this skill does not do X" names X, and the skill becomes a candidate
for X. Negation does not reliably reverse a topic match. So:

- A boundary belongs in the description **only when the neighbour can fire on its own**.
  Against a neighbour with `disable-model-invocation`, naming its topic is pure cost -
  it cannot intercept anything. `QL008` reports exactly that case.
- **Fencing off a topic instead of a neighbour is the costly version**, and the common
  one: "do not use for optimising code" puts *optimising code* into the one place the
  router reads, and hands the work to nobody. `QL013` reports it. Where the boundary has
  to stay, name the neighbour that would otherwise take the work: a name is a
  destination, a topic is only bait.
- Every other boundary goes in the **body**, which is read after activation and does
  not affect the choice.
- "Never fire on your own" is `disable-model-invocation: true`, not a sentence asking
  nicely.

After any description edit, re-run the routing checks: one word moves the routing of
every neighbouring skill.

## 2. The two loads

Every document and pointer spends one of two budgets:

- **Context load** - always-loaded material on the agent's window. A description, a line
  in `AGENTS.md`. Paid every turn whether or not it fires.
- **Cognitive load** - the cost on the human: knowing which documents exist and when to
  reach for each. Not a cost to minimise; it is the price of human agency. Spend it
  where human judgement matters.

Material behind a pointer escapes context load at the price of the pointer's own line.
Material with no pointer rides entirely on cognitive load.

Ask: is this skill model-invoked because the agent must reach it on its own, or because
that is the default? A skill that only ever fires by hand should be user-invoked and pay
no context load at all.

**That choice also changes who the description is written for**, and this is the half
people miss. A model-discoverable skill needs triggers, because a model is matching
wordings against it. A manual-only skill is read by a person picking from a list, and
trigger phrasing does nothing for them: what they need is a one-line summary of what
they are about to invoke. Writing a trigger list into a manual-only description is
writing for a reader who is not there, and the reverse - a human-facing summary on a
model-discoverable skill - is the description that never fires, which is `QL001` and
`QL002`. Decide invocation first, then write the description to the reader it just
acquired.

## 3. Where each piece sits

Three rungs, ranked by how immediately the agent needs the material:

1. **In-file step** - what the agent does, in order.
2. **In-file reference** - consulted on demand. A flat peer-set (every rule of a review
   on one rung) is a fine arrangement, not a smell.
3. **Disclosed reference** - pushed into a separate file behind a pointer, loaded only
   when the pointer fires.

**Progressive disclosure** is the move down the ladder so the top stays legible. The
cleanest test is branching: inline what *every* branch needs, disclose what only *some*
branches reach. When a document has steps, in-file reference that should be disclosed
buries them and turns attending to them into a coin-flip.

- **The body starts with the work.** Routing conditions belong in the description and
  nowhere else; by the time the body is read, the decision to read it has been made. A
  body that opens by restating when to use the skill spends its most-attended lines on a
  question already answered, and the restatement drifts out of sync with the description
  it copies.
- **Co-location**: the ladder decides how far down a piece sits; co-location decides
  what sits beside it. A concept's definition, rules and caveats belong under one
  heading. The test: the file should read like documentation written for the agent.
- **Sprawl** is the failure here - a document simply too long, even when every line is
  live. Attention thins across the excess. The cure is the ladder, plus splitting by
  branch so each path carries only what it needs.

`ST006` and `ST007` are the byte-count shadow of this section. They tell you something
is too big; only this pass tells you what to move.

## 4. Steps and completion criteria

Every step ends on a **completion criterion** - the condition that tells the agent the
work is done. Two properties make it a lever:

- **Clarity**: can the agent tell done from not-done? A vague bound ("understanding
  reached") invites **premature completion**, the step ending while attention slips to
  being done. The visible steps still ahead supply the pull; the criterion's clarity is
  the resistance. Sharpen the bound first - it is local and cheap. Only if the bound is
  irreducibly fuzzy *and* you observe the rush, split the sequence so the later steps
  are out of view, and only across a real context boundary (a hand-off or a subagent);
  an inline call leaves them in context and clears nothing.
- **Demand**: how much it requires. "Every modified model accounted for" forces thorough
  work where "produce a change list" does not. Demand is not step-bound: "every rule
  applied" binds a body of flat reference the same way.

The strongest criteria are both checkable and exhaustive. `QL006` catches the crudest
failures of clarity by vocabulary; the rest is here.

## 5. Leading words, and the negation trap

A **leading word** is a compact concept already in the model's pretraining that the
agent thinks with while running the document (*lesson*, *tracer bullets*, *tight*,
*red*). Repeated as a token, never as a sentence, it anchors a region of behaviour in
the fewest tokens by recruiting priors the model already holds. Coining your own works
if you define it clearly, but a made-up word recruits nothing: you pay in definition
tokens what a pretrained word gives free.

Hunt for passages begging to collapse into one token: a triad spelled out at three
sites, a pointer spending a sentence to gesture at one idea.

- "fast, deterministic, low-overhead" -> *tight*
- "a loop you believe in" -> *red*, which turns a fuzzy gate into a binary observable

**Negation** is the failure mode beside this lever. Steering by prohibition drags the
forbidden behaviour into context and makes it *more* available. The negation is a weak
modifier the strongly-activated concept overruns, so the ban half-reads as an
instruction to do the thing. Prompt the **positive**: state the target behaviour so the
banned one is never spoken. Keep a prohibition only as a hard guardrail you cannot
phrase positively - and pair it with the positive target. `QL005` counts prohibitions;
deciding which of them are guardrails is this pass.

## 6. Pruning

- **Single source of truth.** Each meaning lives in one authoritative place, so changing
  the behaviour is a one-place edit. Duplication costs maintenance and tokens, and
  inflates a meaning's rank on the ladder past its real one.
- **The environment is a source of truth too** - `package.json` scripts, config files,
  the directory layout, `--help` output. A document that restates it is a **cache**,
  earning its load only when the lookup is expensive. Cache what the agent cannot find
  by looking: the unwritten convention, the reason behind a choice, the gotcha no config
  confesses.
- **Relevance, line by line.** A line loses it by never bearing on the task, or by going
  stale. Without pruning the default fate is **sediment**: stale layers that settle
  because adding feels safe and removing feels risky.
- **No-ops.** An instruction the model already obeys by default pays load to say
  nothing. The test - does it change behaviour versus the default? - is model-relative,
  not reader-relative, and is settled by running the document, not by debate. When a
  sentence fails, delete the whole sentence rather than trim words from it. The test
  also grades leading words: a word too weak to beat the default (`be thorough`, when
  the agent is already thorough-ish) is a no-op, and the fix is a stronger word, not a
  different technique.
  "Settled by running" means a **mirror**: a subagent that never saw the skill writes the
  procedure for the same task, and only the lines it states unprompted are cut. Prompt and
  the three-column comparison: [clean-context-run.md](clean-context-run.md).

## 7. How the skill was built

These four decide whether the skill keeps working, and no script sees any of them.

- **Written from a run, not from an idea of a run.** The skill is drafted after one real
  piece of the work has been done with the user, and the rules are extracted from that
  run. Rules derived from finished work carry the traps; rules derived from imagining
  the work carry good intentions only.
- **Fix the principle, not the example.** When the skill misbehaves, find the passage
  that produced the behaviour and rewrite it so the whole class of cases falls under it.
  Appending "and if X arrives, do Y" is overfitting the scaffolding: cheaper now, and in
  six months the patches argue with each other and nobody dares touch the file.
  More than two or three new "and if" clauses in one edit means the edit should have
  been a general rule.
- **Unverifiable requirements become pairs.** "Write vividly", "be honest, not
  flattering" pass or fail on the author's opinion. Replace each with a *bad -> good*
  pair plus the reason they differ: a pair can be compared.
- **A step always performed the same way is a script.** Prose that describes a fixed
  procedure is retyped by the model every run - probabilistically, and for tokens. It
  cannot be run, and it cannot be fixed once. `ST012` catches the blatant case; this
  pass catches the procedure written as paragraphs.

## 8. Closing the edit

An edit is finished when you can name what it fixes: today's case **and at least one
older one**. If it only fixes today's, it is a patch, not a rule - go back to section 7.
Replay the older case in a **subagent** with the edited skill and the case's input, never
inline: the session that wrote the fix already knows the answer. Prompt and what counts as
fixed: [clean-context-run.md](clean-context-run.md).

Before starting, search the history for the same trap: it may already have been analysed
once, and the second analysis will disagree with the first.

## 9. What the official guidance adds

The sections above are one school of thought about writing for agents. The
[Agent Skills best-practices page](https://agentskills.io/skill-creation/best-practices)
is another, and where they overlap they agree. Four things it says that the rest of this
file does not:

- **Start from real expertise.** A skill generated by asking a model to write one,
  with no domain context, comes out as generic procedure - "handle errors
  appropriately", "follow best practices". The valuable material is the specific API
  pattern, the edge case, the project convention. Extract it from a task you actually
  did, or synthesise it from real artefacts: runbooks, schemas, code review comments,
  the patches that fixed real failures. Generic references produce generic skills.

- **A gotchas section is often the highest-value content.** Not general advice, but
  concrete corrections to mistakes the agent will make otherwise: this table uses soft
  deletes so every query needs `WHERE deleted_at IS NULL`; the same id is `user_id`,
  `uid` and `accountId` in three services; `/health` returns 200 while the database is
  down, use `/ready`. Keep them in SKILL.md, where the agent reads them **before** it
  hits the situation - behind a pointer it may not recognise the trigger.
  When you correct the agent on something, that correction is a gotcha.

- **Provide a default, not a menu.** "You can use pypdf, or pdfplumber, or PyMuPDF, or
  pdf2image" makes the agent choose, and it chooses differently each run. Pick one, show
  it, and mention the alternative only where it is genuinely needed.

- **Favour procedures over declarations.** Teach how to approach the class of problem,
  not what to produce for one instance. "Join `orders` to `customers` on `customer_id`,
  filter `region = EMEA`" answers one question; "read the schema, join on the `_id`
  convention, apply the user's filters as WHERE clauses" answers any of them.

One calibration point worth holding beside §4: **match specificity to fragility.** Where
several approaches work, explain the *why* and let the agent choose. Where the operation
is fragile or the sequence matters, be exact and say so - "run exactly this, do not add
flags". Most skills need both, in different sections.
