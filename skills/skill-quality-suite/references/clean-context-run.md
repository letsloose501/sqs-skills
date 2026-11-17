# Clean-context runs: the mirror and the replay

Two questions about a skill can only be answered by an agent that has **not** been in the
session where the skill was written or edited:

- **Which lines are no-ops?** (writing-rubric §6) A line the model already follows by default
  pays load to say nothing. You cannot tell from inside: having just read the skill, you
  "would know" every line, and that feeling is exactly the one that cuts the wrong lines.
- **Does the edit fix the old case?** (writing-rubric §8) An edit is closed by replaying an
  older case, and the session that made the edit has already seen the fix; replaying it
  inline is grading your own homework.

Both are answered by a **subagent**, whose context is empty of this session. An inline
"imagine you have not read the skill" is not a clean context: the text is still in the window.

## What a subagent still sees

"Clean" means clean of **this session**, not empty. A general-purpose subagent still loads the
always-on context: `CLAUDE.md` and what it imports, the memory index, and the skill listing,
including **this skill's description**. So the mirror measures the environment minus the skill's
body, which is the right baseline (the description and `CLAUDE.md` are loaded on every real run
too), with two consequences:

- A body line the mirror states **because `CLAUDE.md` or a rule file says it** is a duplicate,
  not a pretraining no-op: the cut is still right, by single source of truth (writing-rubric §6).
  Ask the mirror to say where each pitfall came from, so the two can be told apart.
- Traps the description names reach the mirror as facts **without their details**. Compare the
  details: on the first run (`commit`, 18.11.2026) the mirror knew "the key lives in the Windows
  ssh-agent" from the description and concluded "push only from PowerShell, set
  `GIT_SSH_COMMAND`", which the body contradicts (`core.sshCommand` is already set; push works from
  any shell). The body line earned its load exactly where the description's summary misled.

## Which model

The model that will run the skill. The no-op test is model-relative: a line Opus follows
unprompted may be needed by Haiku. If the skill sets `model:` in its frontmatter, pass that;
otherwise the session's model (omit the override).

## The mirror: what the model writes without the skill

Launch `Agent`, `subagent_type: "general-purpose"`, with the task the skill covers and **no
access to the skill**:

```
Do not use the Skill tool and do not open anything under ~/.claude/skills/<name>/.
Task: <one paragraph: the job the skill does, in the user's words, the inputs it gets,
where its output lands - taken from the description, not from the body>.
Write the procedure you would follow, step by step, including the checks you would run
and the pitfalls you would watch for. Be concrete: commands, files, order. For each pitfall,
say where you know it from (general knowledge, CLAUDE.md, the skill listing, memory).
Do not run anything that changes state.
```

Then compare, line by line, against the section of the skill under review. Each line lands
in one of three columns:

| Column | Meaning | Action |
|---|---|---|
| **stated** | the mirror says it, in substance, unprompted | no-op candidate: cut the whole sentence |
| **missed** | the mirror does not say it | the line earns its load: keep |
| **contradicted** | the mirror does the opposite | the line earns the most: keep, and consider making it more prominent |

Cut only what lands in **stated**, and only by that evidence. "I'd know this anyway" is not a
column. A mirror that states nearly everything means the section is generic procedure; a
mirror that misses nearly everything means the section is the skill's real expertise (the
machine-specific trap, the convention no config confesses).

One mirror run is one sample. Before cutting a line that guards against a costly failure
(data loss, a push, a publish), run the mirror a second time; cut only if both state it.

## The replay: the edited skill on an old case

Launch `Agent`, `subagent_type: "general-purpose"`, with **the edited skill and the old case's
input**, and nothing about the fix:

```
Use the <name> skill for this task. <the old case's input, verbatim: his words, the file,
the link>. Do the work as far as <the point where the old failure happened>, then stop and
report what you did and what you would do next.
```

Put in the prompt: the input and where to stop. Leave out: what went wrong last time, what
the edit changed, what a good answer looks like. Those are the author's context, and with
them the replay passes by being told the answer.

Compare the report with the old failure. **Fixed** only if the replay does not repeat it, by
evidence in the report (the step it took, the file it read), not by its saying it was careful.
When the old case needs side effects (a push, a message, a purchase), stop the replay before
them; the report of what it would do next is the evidence.

## Cost

Each run is one subagent call on the skill's model. The mirror is worth it before a cut of
more than a few lines; the replay is the standard way to close an edit (§8). Neither is a
paid layer of this suite: both are ordinary agent calls the user is already paying for in the
session.
