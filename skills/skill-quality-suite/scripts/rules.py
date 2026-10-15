#!/usr/bin/env python3
"""The rule registry: one row per finding the suite can emit.

A rule code is the join key of the whole suite. `sqs.py explain ST005` looks a code
up here, a config file switches a code off here, CI annotations group by it, and the
report prints it. That only works while this file is the single place a code is
defined - an engine that invents a code without a row here fails `sqs.py rules
--audit`, which is what keeps the two from drifting.

Severity here is the DEFAULT. The structure engine (check_skills.py) decides error vs
warning itself, because it knows the case; everything else takes the default, and a
config file overrides either.

Modules map one-to-one onto code prefixes, so a finding routes to its module without
a lookup:

    SP  spec        Agent Skills specification conformance
    ST  structure   links, orphans, budgets, layout
    QL  quality     whether the instructions read like instructions
    CP  compat      which runtime reads which frontmatter field
    SE  security    secrets, dangerous commands, injection, hidden characters
    PB  publish     what has to be true before the skill leaves your machine
    EV  evals       whether the skill fires on the wording a human actually uses
    CB  capabilities what a bundled script CAN do to the machine, described not forbidden

sqs-allow-file: SE002
Every rule row spells out the pattern it is about, so this file matches its own
security rules by construction.
"""

MODULES = {
    "SP": "spec",
    "ST": "structure",
    "QL": "quality",
    "CP": "compat",
    "SE": "security",
    "PB": "publish",
    "EV": "evals",
    "CB": "capabilities",
    "CS": "cases",
}

# code: (severity, title, why it matters, how to fix, fixable by `sqs.py fix`)
_ROWS = {
    # ---- SP: Agent Skills specification -------------------------------------
    "SP001": ("error", "No frontmatter",
              "Without a `---` block the file is plain markdown and never loads as a skill.",
              "Open the file with `---`, put `name` and `description` inside, close with `---`.", False),
    "SP002": ("error", "Required field `name` missing",
              "The loader keys the skill by `name`; without it there is nothing to invoke.",
              "Add `name: <folder-name>`.", True),
    "SP003": ("error", "Required field `description` missing",
              "The description is the skill's only context pointer. No description, no triggering.",
              "Add a description stating what the skill does and when to reach for it.", False),
    "SP004": ("error", "`name` does not match the folder",
              "The specification requires them equal. What actually happens is split, and the "
              "client-implementation guide states both halves: a lenient client warns and "
              "loads the skill anyway, while `skills-ref validate` and publication reject it. "
              "So it works on your machine and fails the moment the skill leaves it.",
              "Rename the folder or the field so the two agree.", True),
    "SP005": ("warning", "`name` longer than 64 characters",
              "Over the spec limit. Claude Code tolerates it, `skills-ref validate` and "
              "publication do not.", "Shorten the name.", False),
    "SP006": ("warning", "`name` off-spec",
              "The spec allows lowercase latin letters, digits and single inner hyphens only.",
              "Rewrite as `lower-case-with-hyphens`.", True),
    "SP007": ("error", "`description` empty",
              "An empty description is the same as none: the skill never triggers.",
              "Write the description.", False),
    "SP008": ("warning", "`description` over 1024 characters",
              "Over the spec limit. It works locally and is rejected on publication.",
              "Cut restated identity and synonym triggers; keep one trigger per branch.", False),
    "SP009": ("warning", "`compatibility` over 500 characters",
              "Over the spec limit.", "Shorten it.", False),
    "SP010": ("warning", "Unknown frontmatter key",
              "A typo in a key is not a syntax error: the field silently vanishes along with "
              "its meaning, and the skill keeps loading as if nothing happened.",
              "Fix the spelling, or drop the key.", False),
    "SP011": ("error", "Unclosed code fence",
              "Everything after the unclosed fence reads as code, so the instructions that "
              "follow it stop being instructions.", "Close the fence.", False),
    "SP012": ("info", "Directory outside the conventions",
              "The specification permits any directory beside SKILL.md and calls "
              "`scripts/`, `references/` and `assets/` recommendations, so this is not a "
              "violation. It is a portability note: tools that walk the conventional "
              "layout will not see the directory, and harnesses document different sets - "
              "Cline names `docs/` and `templates/`, Antigravity names `examples/` and "
              "`resources/`.",
              "Leave it if the skill links it from SKILL.md; `compat` says what each "
              "harness makes of it. Add the name to `allow_dirs` to stop being told.", False),
    "SP013": ("info", "Extraneous file at the skill root",
              "README.md, CHANGELOG.md, Makefile and friends are repository furniture. Inside a "
              "published skill they ship as payload nobody reads.",
              "Keep them outside the skill folder, or accept the cost knowingly.", False),
    "SP014": ("error", "No body",
              "Frontmatter present, instructions absent: the skill activates and says nothing.",
              "Write the instructions.", False),
    "SP015": ("info", "Multiline description",
              "A folded or literal block scalar (`>-`, `|`) is valid YAML and Claude Code reads "
              "it. It is flagged as non-portable by the vendor-neutral validators, which is as "
              "far as the evidence goes: whether a given other runtime reads it has to be tried, "
              "not assumed.",
              "Put the description on one line if the skill has to be portable; leave it if "
              "Claude Code is the only target.", False),
    "SP016": ("warning", "Oversized or binary asset",
              "Every byte in the skill folder travels with it. A large binary is paid for by "
              "everyone who installs the skill and read by nobody.",
              "Host it elsewhere and link, or shrink it.", False),
    "SP017": ("warning", "Reference nested too deep",
              "Progressive disclosure is one hop: SKILL.md names the file. Three levels down, "
              "nothing reaches the file but a reader who already knew it was there.",
              "Flatten to `references/<file>.md`, or link the intermediate level explicitly.", False),

    "SP018": ("error", "XML tag in `name` or `description`",
              "The Agent Skills validation rules forbid XML tags in either field. The "
              "description is injected into a system prompt, where a stray tag changes how "
              "the surrounding text is read.",
              "Remove the angle brackets; name the tag in prose instead.", False),
    "SP019": ("error", "Reserved word in `name`",
              "`anthropic` and `claude` are reserved in a skill name by the validation rules, "
              "and the refusal comes at upload time, after the skill is finished.",
              "Rename the skill after what it does.", False),
    "SP020": ("warning", "Bare angle bracket in `description`",
              "Not a tag, so `SP018` stays quiet - but the validator the reference "
              "skill-creation tooling ships refuses any `<` or `>` in a description, and its "
              "packager runs that validator before packaging. An arrow or a `<10MB` is enough "
              "for a skill that works locally to be refused there.",
              "Write it out: \"to\" for an arrow, \"under 10 MB\" for a comparison.", False),

    # ---- ST: structure -------------------------------------------------------
    "ST001": ("error", "Link to a file that does not exist",
              "The agent does not crash on a broken pointer: it skips the step in silence, and "
              "the only symptom is that the work came out worse than usual.",
              "Restore the file or correct the link.", False),
    "ST002": ("error", "Broken sibling link",
              "Same silent skip, in the short `[text](neighbour.md)` form that a path-shaped "
              "check cannot see.", "Restore the file or correct the link.", False),
    "ST003": ("error", "Link to a skill that does not exist",
              "A rename elsewhere left this pointer aimed at nothing.",
              "Point at the new name, or drop the link.", False),
    "ST004": ("error", "Linked skill has no such file",
              "The skill is there, the file inside it is not.",
              "Correct the path, or restore the file in the other skill.", False),
    "ST005": ("warning", "Orphan file",
              "Nothing links to it. Either it was never wired up, or it is no longer needed. An "
              "orphan is a pruning candidate, not a defect.",
              "Link it from SKILL.md, or delete it.", False),
    "ST006": ("warning", "SKILL.md over budget",
              "SKILL.md is loaded whole on every activation, so its length is a permanent tax on "
              "the context window.",
              "Move what only some branches need into `references/`, and keep the routing - "
              "which reference to open when - in SKILL.md.", False),
    "ST007": ("warning", "Reference over budget",
              "A reference is opened whole too, just later. A 30 KB file cancels the point of "
              "two-stage loading.", "Split it by branch.", False),
    "ST008": ("warning", "Pointer to a section that is gone",
              "The file is in place, so an ordinary link check stays quiet while the agent opens "
              "the reference and does not find what it came for. Renaming a heading is enough.",
              "Restore the heading, or correct the pointer - copying the section name from the "
              "file verbatim, never from memory.", False),
    "ST009": ("warning", "Path naming no folder in this skill",
              "Almost always an example path from somebody else's repository rather than a route "
              "of your own.", "Leave it if it is an example; fix it if it was meant to be a route.", False),
    "ST010": ("warning", "Path with no skill name",
              "The file lives in a different skill, and the bare relative path resolves there "
              "only by accident.", "Spell out `~/.claude/skills/<skill>/<path>`.", False),
    "ST011": ("error", "Outbound path does not exist",
              "A skill that reads a note before working degrades silently when the note is "
              "renamed: the theory is gone and the work goes on anyway.",
              "Update the path. Cyrillic is compared NFC/NFD-insensitively, so a hit here is a "
              "real miss, not a normalisation artefact.", False),
    "ST012": ("warning", "Code as prose",
              "A long executable block sitting in the text is retyped by the model every run - "
              "probabilistically, and for tokens. It cannot be run, and it cannot be fixed once.",
              "Move it into `scripts/`; leave the call and how to read its output in the text.", False),
    "ST013": ("warning", "Body nearly empty",
              "Enough text to load, not enough to act on.", "Write the instructions.", False),
    "ST014": ("error", "Duplicate `name` across skills",
              "One shadows the other and which one wins is not knowable in advance.",
              "Rename one of them.", False),
    "ST015": ("error", "No SKILL.md",
              "The folder is in the skills tree and holds no skill.",
              "Add SKILL.md, or move the folder out.", False),
    "ST017": ("warning", "Path into a tool's folder not on this machine",
              "A path under `~/.claude`, `~/.config/<tool>`, a dot-folder or a platform config root "
              "exists only where that tool is installed. On a CI runner or a fresh machine it is "
              "missing, and a missing install cannot be told from a broken path.",
              "Check it on a machine with the tool installed. If the file only describes install "
              "locations, waive it for the file with `sqs-allow-file: ST017`.", False),
    "ST016": ("warning", "External link unreachable",
              "A dead URL in a reference sends the agent to fetch nothing.",
              "Update or remove the link. 403 is reported separately: it usually means the site "
              "blocks bots, not that the page is gone.", False),

    # ---- QL: instruction quality --------------------------------------------
    "QL001": ("warning", "Description too short to carry triggers",
              "Trigger conditions are the only thing the agent uses to decide whether to open "
              "the skill. Two words hold none.",
              "State what the skill is and list the distinct branches that should reach it.", False),
    "QL002": ("warning", "Description states what, never when",
              "A pointer does two jobs: name the material and list the branches that trigger "
              "reaching it. This one does the first only, so firing is left to chance.",
              "Add the trigger conditions: `Use when ...`, `Trigger on ...`.", False),
    "QL003": ("warning", "One branch written twice",
              "Two trigger phrases that name the same branch cost context on every turn and "
              "sharpen nothing. The rule prints the pair, so you can judge it.",
              "Collapse the pair into one trigger. Deliberately high-precision and therefore "
              "low-recall: it catches word-level repetition only, and the judgement-level pass "
              "over a description lives in `references/writing-rubric.md`.", False),
    "QL004": ("info", "Description and body barely overlap",
              "The skill fires on wording that its own instructions never mention, which usually "
              "means the description drifted from what the skill grew into.",
              "Re-read the body and rewrite the description from it.", False),
    "QL005": ("warning", "Steering by prohibition",
              "A ban drags the forbidden behaviour into context and makes it more available, not "
              "less. The negation is a weak modifier that the strongly-activated concept "
              "overruns, so the ban half-reads as an instruction to do the thing.",
              "State the target behaviour positively, so the banned one is never spoken. Keep a "
              "prohibition only as a hard guardrail you cannot phrase positively - and pair it "
              "with the positive target.", False),
    "QL006": ("info", "Unverifiable instruction",
              "`be thorough`, `write clearly`, `as needed`: the agent cannot tell done from "
              "not-done, and neither can you.",
              "Replace with a checkable bound, or with a `bad -> good` pair the reader can "
              "compare.", False),
    "QL007": ("warning", "TODO or placeholder left in the text",
              "The agent reads it as instruction, not as a note to self.",
              "Finish the sentence or cut it.", False),
    "QL008": ("info", "Disclaimer naming a neighbouring skill's topic",
              "A description is a shop window, not a fence. Naming a neighbour's topic makes "
              "this skill a candidate for it; negation does not reliably reverse that.",
              "Move the boundary into the body, which is read after activation and does not "
              "affect the choice. Keep it in the description only when the neighbour can fire "
              "on its own.", False),
    "QL009": ("info", "Description repeats the skill's own name",
              "Identity the body already carries, paid for on every turn.",
              "Cut the restatement and spend the room on a trigger.", False),

    "QL010": ("warning", "Description talks about itself",
              "The description is an instruction to the agent about when to act, not a "
              "paragraph about the skill. `Use when the user ...` outperforms `This skill "
              "does ...`, and first or second person (`I can help you ...`) is injected "
              "into a system prompt where the point of view does not fit.",
              "Rewrite in the imperative, third person: what it does, then the situations "
              "that should reach it.", False),
    "QL011": ("error", "Bundled script waits for input",
              "Agents run in non-interactive shells. A script that blocks on a prompt does "
              "not fail - it hangs until something kills it, and the skill looks broken for "
              "reasons nothing explains.",
              "Take every input from flags, environment variables or stdin, and fail with a "
              "message naming the missing one.", False),
    "QL012": ("info", "Unpinned one-off command",
              "`npx eslint` resolves to whatever is newest today. The skill's behaviour then "
              "changes without the skill changing, which is the hardest kind of drift to "
              "trace.", "Pin the version: `npx eslint@9.0.0`.", False),
    "QL013": ("info", "Description rules out a topic",
              "A description is matched on topic, and a negation does not reverse a match. "
              "Spelling out the work the skill will not take puts that work's vocabulary in "
              "the one place the router reads, so the clause meant as a fence reads as one "
              "more reason to fire. `QL008` is this same trap when a neighbouring skill is "
              "named; this is the version with only a topic in it, which is the common one.",
              "Move the boundary into the body, which is read after the skill has already "
              "been chosen. Keep it in the description only when a model-invoked neighbour "
              "would otherwise take the work, and then name that neighbour rather than its "
              "topic.", False),
    "QL015": ("warning", "User-invoked skill's description is written for the router",
              "With `disable-model-invocation: true` the description is not in the model's "
              "context at all. Trigger wordings, orders to fire or not to fire, and the user "
              "spoken of in the third person are addressed to a reader who never sees them - "
              "and they take the place of the one thing the remaining reader needs: what the "
              "command does when you run it.",
              "Rewrite the description as a one-line menu entry for a person. Keep the "
              "routing boundary, if it matters, in the body.", False),
    "QL014": ("warning", "Fuzzy boundary between fire and do-not-fire",
              "An exclusion clause in the description shares its topic words with a clause "
              "that claims the work. A description can separate its branches well on average "
              "and still be misrouted by one pair like this, because the router matches "
              "wording and a negation does not reverse a match. `QL003` compares two clauses "
              "that agree and calls the second redundant; this compares two that disagree, "
              "where the second reads as a reason to fire rather than a reason to stay quiet.",
              "Make the two sides differ in topic words, not only in the negation - or move "
              "the exclusion into the body, which is read after the skill has been chosen.",
              False),
    "QL016": ("info", "Procedure written as one block of prose",
              "The body has no steps - no numbered item, no step heading - and one paragraph "
              "of 200 words or more carries an order (`first`, `then`, `finally`). An agent "
              "reading a procedure that way has to find the step boundaries itself, and a "
              "step buried mid-sentence is the one it skips. The Stepless Workflow smell of "
              "arXiv 2607.01456, which found it in 32% of 238 marketplace skills with a "
              "model; this check sees only the extreme shape.",
              "Split the paragraph at its steps, each one saying what it is for. Numbered or "
              "bulleted both work. Keep each step a goal, not a fixed command line: the same "
              "paper counts a rigid series of commands as a smell of its own (62%), so the "
              "fix is structure, not a script.", False),
    "QL017": ("info", "No example anywhere in the skill",
              "Neither SKILL.md nor any reference gives an example: no `for example`, no "
              "fenced block, no `bad` / `good` pair, no quoted wording. The agent works from "
              "the description of a thing alone, and fills what it has not seen with a "
              "guess. Missing Example in arXiv 2607.01456 (34% of 238 skills by a model).",
              "Add one worked example of the input and what the skill makes of it - in "
              "SKILL.md if it is short, in a reference the body links if it is long.", False),
    "QL018": ("info", "Output produced, never checked",
              "The body tells the agent to write, create, render or build something, and no "
              "text in the skill mentions checking the result in any form - verify, test, "
              "compare, review, a checklist. The output is treated as done the moment it "
              "exists. No Validation Step in arXiv 2607.01456 (69% of 238 skills by a "
              "model); this check fires only where checking is never mentioned at all.",
              "Add the check that would catch this output being wrong - run it, render it "
              "and look, compare it with the source - and what to do when it fails.", False),
    "QL019": ("info", "Output format required, no template shown",
              "A section is headed as the output or report format, or a sentence promises "
              "\"the following format:\", and what follows is prose: no fenced block, table, "
              "list of parts, sample or linked file. The agent invents a layout each run, "
              "and two runs disagree. Missing Template in arXiv 2607.01456 (25% of 238 "
              "skills by a model).",
              "Put the template under the heading - a fenced skeleton with the parts filled "
              "by placeholders - or link the file that holds it.", False),

    # ---- CP: agent compatibility --------------------------------------------
    "CP001": ("warning", "Field value the runtime cannot read",
              "The field is read; the value is not one of the ones it accepts, so the runtime "
              "falls back to its default and says nothing.",
              "Use one of the accepted values.", False),
    "CP002": ("warning", "Field rejected by the strict reference validator",
              "`skills-ref` refuses unknown top-level fields. Real clients warn and load anyway, "
              "so the breakage only shows on publication.",
              "Nest it under `metadata:`, which is the spec's escape hatch.", False),

    "CP006": ("warning", "Feature that does not travel",
              "The feature is real on one harness and inert or absent on another target. "
              "Nothing fails loudly: the instruction simply has no effect there.",
              "Keep it if that harness is the only target; otherwise state the behaviour in "
              "the instructions, where every harness reads it.", False),
    "CP007": ("info", "Undocumented on a target harness",
              "The harness's official documentation does not say what it does with this. "
              "That is a gap in the documentation, not a defect in the skill, and it is "
              "reported as unknown rather than as an incompatibility.",
              "Try it once on that harness and record what happened, or avoid relying on it.",
              False),
    "CP008": ("error", "Target harness refuses the skill",
              "A rule the harness publishes is broken - a required field missing, a "
              "documented ceiling exceeded, a name that has to match its folder and does not.",
              "Fix the field, or drop the harness from the targets.", False),
    "CP009": ("warning", "No adapter for the named harness",
              "The target is not in the registry, so nothing about it was checked. Silence "
              "here would read as a pass.",
              "Use a name from `sqs.py harnesses`, or add an adapter under "
              "`scripts/harnesses/`.", False),

    # ---- SE: security --------------------------------------------------------
    "SE001": ("error", "Secret in the skill text",
              "An API key, token or private key committed into a skill travels with every copy "
              "of it.", "Revoke the credential, then remove it and read it from the environment.", False),
    "SE002": ("warning", "Destructive command in an instruction",
              "A recursive delete, a download piped into a shell, world-writable permissions, a "
              "force push: the agent runs what the skill "
              "tells it to run.",
              "Narrow the command, or make the step ask the human first.", False),
    "SE003": ("error", "Instruction-override text",
              "An instruction to disregard what came before, a claimed change of role, an order to "
              "keep something from the user. In a "
              "skill you wrote it is a mistake; in a skill you installed it is the payload.",
              "Remove it. If the skill came from elsewhere, read the whole file before using it.", False),
    "SE004": ("error", "Hidden or bidirectional Unicode",
              "Zero-width and bidi control characters make the rendered text differ from the text "
              "the model reads - the Trojan Source trick.",
              "Strip the characters. `sqs.py fix` removes them.", True),
    "SE005": ("warning", "Outbound network call carrying local data",
              "A step that posts file contents to a host is exfiltration whether or not it was "
              "meant as one.", "Confirm the host is yours and that the human agreed to the send.", False),
    "SE006": ("info", "Absolute path naming a user account",
              "`C:\\Users\\<name>`, `/home/<name>`: the skill only works on one machine, and it "
              "publishes whose machine that is.",
              "Use `~`, or an environment variable.", False),
    "SE007": ("info", "Skill vouches for itself",
              "A guarantee of safety, an endorsement by a named vendor, a count of users who "
              "trust it, or an invitation to skip review. Nothing in a skill can certify the "
              "skill: whoever wrote the files wrote the badge too. It is aimed at the router "
              "choosing between skills and at the person deciding whether to install, and it "
              "asks both to take on faith what they should check. The router's half is a "
              "description that ranks the skill above its neighbours (\"the best tool\", "
              "\"better than any other\"): rewriting a tool's description that way moved its "
              "selection rate from about 20% to 81% in one published attack.",
              "Remove the claim, or replace it with something a reader can verify - a link to "
              "an audit, a test suite, a repository with history. In a description, say when "
              "the skill applies, not how it compares.", False),
    "SE008": ("error", "Code decoded before it runs",
              "A script or an instruction decodes text - base64, hex, a compressed or "
              "marshalled blob - and executes the result: a decoder piped into a shell, "
              "PowerShell's encoded-command switch, `eval` over a decoded string, or Python's "
              "`exec`/`eval` over a decoder's output. Nothing on the page says what runs, which "
              "is the purpose of writing it that way; no instruction a person has to trust "
              "needs to be unreadable to them.",
              "Put the code in the file in plain text. If it is a vendored binary or data, ship "
              "it as a file with its source named, not as a string that is executed.", False),

    # ---- PB: publishing ------------------------------------------------------
    "PB001": ("warning", "No license",
              "Without one, nobody may legally reuse the skill.",
              "Add a `license:` field, or a LICENSE file beside the skill.", False),
    "PB002": ("info", "No README",
              "The SKILL.md talks to the agent. A human deciding whether to install needs a page "
              "that talks to them.", "Add README.md next to the skill folder.", False),
    "PB003": ("error", "Personal path in a skill about to be published",
              "It leaks your directory layout and breaks on every other machine.",
              "Replace with `~`, or with a path the reader supplies.", False),
    "PB004": ("warning", "Text not in the declared publication language",
              "A published skill documented in another language than its repository is read by "
              "nobody it was published for.",
              "Translate, or drop `--lang`.", False),
    "PB005": ("warning", "Version drift",
              "The version in the plugin or marketplace manifest disagrees with the skill's own.",
              "Make them agree; the manifest is usually the one that went stale.", False),
    "PB006": ("info", "Private material in a skill about to be published",
              "A path into a personal vault, a private repository name, an email address.",
              "Strip it, or keep the skill unpublished.", False),
    "PB007": ("info", "Package wires hooks beside this skill",
              "`hooks/hooks.json` runs a command on its event whether or not the model ever "
              "routes to this skill. A clean verdict on SKILL.md next to an unread hooks/ "
              "directory is the most convincing wrong answer the suite can give.",
              "Not a defect - read hooks/hooks.json before trusting the package, the way you "
              "would read a script this skill calls.", False),
    "PB008": ("warning", "Skill points at a package sibling",
              "A command, agent or script one directory above `skills/<name>/`, or a path "
              "through `${CLAUDE_PLUGIN_ROOT}`. The structure rules only resolve pointers "
              "inside the skill, so this one is invisible to them and breaks in silence the "
              "moment the skill is copied out of the plugin.",
              "Declare the dependency in prose, or bring what it needs inside the skill.", False),
    "PB009": ("info", "Package installed from an unreviewed checkout",
              "The marketplace entry's `source` names a remote repository, archive or command "
              "- the files under review may be a checkout nobody has looked at.",
              "Not a defect - a fact about where the package came from.", False),
    "PB010": ("warning", "Instructions changed, the version did not",
              "A skill that was improved and still carries its old version is a skill nobody "
              "can tell apart from the one they installed. `PB005` catches two files "
              "contradicting each other; this catches a number that contradicts nothing and "
              "describes nothing, which is why it goes unnoticed for months.",
              "Bump the patch, `0.0.1` at a time. Nothing rewrites it for you - the version "
              "is your claim about your own work.", False),
    "PB011": ("warning", "Call surface changed, the version moved by a patch",
              "`name`, the invocation mode and `allowed-tools` decide how a skill is called. "
              "Moving one of them and bumping only the patch tells every reader the upgrade "
              "is safe to take without reading it.",
              "Bump the minor or the major, whichever the break deserves.", False),
    "PB012": ("warning", "Update reaches further than the version before it",
              "A skill keeps the trust it earned when somebody read it and installed it, while "
              "its content moves underneath. This update pre-approves a tool or a scope the "
              "earlier copy did not, or a bundled script gained network access or started "
              "spawning processes. Either one is a decision the person who installed the "
              "earlier copy never made.",
              "Read the new reach before taking the update. If it is yours and intended, say "
              "so in the changelog and bump the minor - the reader deciding whether to update "
              "is the one who needs to know.", False),
    "PB013": ("warning", "Version went backwards",
              "The declared version is lower than the one at `--since`. Replacing a patched "
              "release with an older one that still looks correctly published is how a fixed "
              "hole comes back without anybody editing anything.",
              "If the rollback is deliberate, ship it as a new, higher version that carries "
              "the old content. A number that only ever rises is what lets a reader trust it.",
              False),
    "PB014": ("warning", "README installs from somewhere this does not ship",
              "An install command in the README names this project under an owner its own git "
              "remotes and marketplace entry do not know, or installs this plugin from a "
              "marketplace other than the one listing it. A project that moved while its "
              "instructions did not sends every new user to an account that is no longer the "
              "author's, and whoever takes that name next receives the installs.",
              "Point the command at where the project lives now. If this is a fork telling "
              "people to install upstream, add upstream as a git remote and the finding goes "
              "away on its own.", False),

    "PB015": ("warning", "Repository material ships inside the skill",
              "SKILL.md sits at the root of its git repository, beside tests, docs, examples or "
              "CI. An installer copies the skill's folder, which here is the whole repository: "
              "the test corpus and the documentation land in every user's skills directory, and "
              "every marketplace scanner reads them as the skill. A fixture of an attack that "
              "tests a scanner reads, to the next scanner, as an attack.",
              "Move the skill into `skills/<name>/` and keep the repository's own material "
              "beside it. `.sqsignore` does not help: it hides a directory from this suite, not "
              "from the installer or anybody else's scanner.", False),

    # ---- EV: evals -----------------------------------------------------------
    "EV001": ("error", "Routing invariant broken",
              "Two skills claim the same wording and only one can win, or a skill claims wording "
              "its own instructions do not serve.",
              "Run `run_evals.py` for the detail; the fix is in the descriptions, not here.", False),
    "EV002": ("info", "Skill has no routing cases",
              "Nothing verifies that this skill fires on the wording a human would actually use, "
              "so every description edit moves it blind.",
              "Add cases to `evals/cases/`.", False),
    "EV003": ("error", "Live routing run below threshold",
              "The judge sent wording to the wrong skill.",
              "Read the failing cases: usually one description is claiming a neighbour's branch.", False),
    "EV004": ("warning", "Malformed evals",
              "An `evals/` directory that does not parse is worse than none: it looks like "
              "the skill is tested.",
              "`evals/evals.json` is `{skill_name, evals: [{id, prompt, expected_output, "
              "assertions}]}`; `evals/eval_queries.json` is `[{query, should_trigger}]`.",
              False),
    "EV005": ("info", "Thin trigger set",
              "A trigger set with few cases on one side measures almost nothing. The "
              "negatives matter most, and the useful ones are near-misses: queries sharing "
              "keywords with the skill that need something else.",
              "Aim for about twenty queries, eight to ten on each side.", False),
    "EV006": ("info", "Routing runner in the tree was not executed",
              "The routing report comes from a script that lives in the tree being "
              "checked. Running it would mean executing code out of the directory the "
              "suite was handed to read, which is the thing reading it was meant to "
              "avoid.",
              "If the tree is yours, pass `--trust-target`. If it is not, a missing "
              "routing report is the correct outcome.", False),
    "EV007": ("warning", "Semantic overlap between two skills",
              "Two skills' trigger branches cover the same wording, so only one of them can "
              "win a request that names it - this is `EV001`'s claim made without executing "
              "the tree's own `run_evals.py`, so it works on any skill tree, not only one "
              "that ships its own routing runner.",
              "Read the two descriptions named in the finding; usually one needs to name the "
              "other and defer, the way `QL008` and `QL013` already ask for.", False),
    "EV008": ("warning", "Eval case cannot pass or fail",
              "A case in `evals/evals.json` carries no `assertions`, `outputs` or `judge`, so "
              "nothing decides whether a run of it passed. `eval --runtime` would run it on "
              "both arms, spend the money, and report it as `ungraded`. skill-creator's "
              "`expectations` do not count: a model grades them there, and nothing reads "
              "them here.",
              "Add one checkable assertion - a literal the answer must contain, a `re:` "
              "pattern, an output the run has to create, with `contains` for what has "
              "to be in it, or a `judge` program whose exit code decides.", False),
    "EV009": ("error", "Eval case cannot run as written",
              "A case is still a draft (a field opens with `TODO`), names a fixture that is "
              "not in the skill, carries a `re:` assertion that does not compile, or has an "
              "output that is malformed, outside the run's directory, or a binary format "
              "checked with `contains`, or a `judge` that is not an argv list or names a "
              "script the skill does not have. The first measures nothing, the second hands the "
              "agent a task about a file it never receives, and the rest crash the grader "
              "or fail every run on both arms. `eval --runtime` refuses the whole set until "
              "it is fixed.",
              "Fill the draft, add the fixture under the skill or drop it, fix the pattern; "
              "check a binary output by existence, or have the task also write a text "
              "summary and check that.", False),

    "EV010": ("info", "Trigger cases repeat the description",
              "A should-trigger case that contains, word for word, a wording the description "
              "quotes as a trigger can pass by string match alone. It shows the listed words "
              "are there; it says nothing about the phrasings a person uses that the author "
              "did not think to list, which is what a trigger set is for. Measured on a real "
              "routing set of 105 positives: 37 were this.",
              "Keep one such case per branch as a sanity check if you like, and write the rest "
              "the way the requests actually arrive - with context, in other words, without "
              "the listed phrase.", False),
    "EV011": ("warning", "Eval case uses `files` for an output",
              "In skill-creator's `evals.json`, which this set is read as, `files` are input "
              "paths inside the skill. This suite used to read them as outputs, so an entry "
              "that is not a file in the skill is still graded that way - the case runs - "
              "but the same file means something else to every other tool that reads it, "
              "and a missing input looks exactly like an old-style output.",
              "Move outputs to `outputs`. If the entry was an input, put the file under the "
              "skill at that path.", False),

    # ---- CB: capabilities ------------------------------------------------------
    "CB001": ("info", "Bundled script can reach the network",
              "An import or a command a bundled script carries - `requests`, `socket`, "
              "`curl` - gives it the ability to reach the network, independent of whether "
              "the specific call looks dangerous. `security` flags a call that is dangerous "
              "on its own; this names the capability so an installer can decide before "
              "reading every line.",
              "Not a defect - confirm the destination matches what the skill claims to do.",
              False),
    "CB002": ("info", "Bundled script can spawn a process",
              "An import of `subprocess`/`multiprocessing`, or a call to `os.system`/"
              "`os.popen`/`os.exec*`, gives the script the ability to run another program "
              "with the permissions the agent has.",
              "Not a defect - confirm the process it spawns matches what the skill claims "
              "to do.", False),
    "CB004": ("info", "Commands run when the skill loads",
              "`!`command`` in the body, and every line of a block opened with ```!, runs on "
              "the machine before the model is sent the skill - the output replaces the "
              "placeholder. It never prompts: a permission rule or the skill's own "
              "`allowed-tools` lets it through, or the invocation aborts. A skill that "
              "pre-approves its own injected commands runs them silently on every load, "
              "before anything in it has been read. A plain code block does not stop "
              "it: watched, an injection inside one ran like any other.",
              "Read each command as you would a hook. If the skill pre-approves them in "
              "`allowed-tools`, that approval is the author's, not yours.", False),
    "CB003": ("info", "Bundled script can read the environment",
              "`os.environ`/`os.getenv` gives a script access to whatever the process's "
              "environment carries, which commonly includes API keys and tokens set for "
              "other tools.",
              "Not a defect - confirm the script only reads the variables it names needing.",
              False),
    "CB005": ("warning", "Bundled script's capabilities cannot be read",
              "The script imports a module by a name it computes, reaches into `os`, "
              "`subprocess` or `builtins` by a computed attribute name, or passes code built "
              "at run time to `exec`/`eval`. Whatever that line does is decided by data, not "
              "by the file, so the other capability rules stay silent about it - and a silent "
              "manifest reads as \"can do nothing\". The same indirection written with "
              "constants is followed and reported as the capability it spells.",
              "Write the import or the call out plainly. If the name really has to come from "
              "data, check it against a fixed list first, and say in the skill what the list "
              "is.", False),
    "CB006": ("warning", "Bundled script needs a package the skill never names",
              "A script imports a package outside the standard library, outside `try: ... "
              "except ImportError`, and neither the skill's text, a requirements file nor the "
              "script's inline PEP 723 block names it. The agent finds out halfway through the "
              "task, as a traceback, on every machine that does not happen to have it - and "
              "the author's machine always does.",
              "Name the package where the agent reads before running the script - a line in "
              "SKILL.md (\"needs `pymupdf`: `pip install pymupdf`\"), a requirements file, or "
              "a PEP 723 block the script runs under with `uv run`. If the script can do "
              "without it, import it inside `try`/`except ImportError`.", False),

    # ---- CS: the case set, and where its three sources disagree ---------------
    "CS001": ("warning", "Promise with no instruction behind it",
              "The description commits to leaving something behind - a file, a note, a "
              "report - and no step in the body writes, saves or files anything. This "
              "skill passes `--trigger`, passes a hand-written `--runtime` set, and still "
              "does not deliver what it advertised, which is the failure nothing else here "
              "catches because nothing about it looks broken.",
              "Either the body is missing the step that produces it, or the description is "
              "promising work the skill does not do. `QL004` reports the same gap as a "
              "statistic; this names the clause.", False),
    "CS002": ("info", "Expectation the description never claimed",
              "A sentence in `evals/expectations.md` shares no wording with the description. "
              "The top row of the disagreement table: not a broken skill, the wrong skill "
              "for what you wrote beside it.",
              "Not a defect. Either you are adopting the wrong skill, or the expectation "
              "belongs beside a different one - the finding names the closer skill when "
              "the tree holds one.", False),
    "CS003": ("info", "Capability the skill never announces",
              "A bundled script reaches the network (`CB001`) or spawns a process (`CB002`) "
              "and no wording anywhere in the skill says so. The bottom row of the "
              "disagreement table: it does `Z` and never mentioned it. `capabilities` says "
              "what a skill CAN do to the machine; this says you were not told. Reading "
              "the environment (`CB003`) is out of scope on purpose - the words an author "
              "would announce it with are ordinary prose in the same breath, so the test "
              "cannot tell an announcement from the subject matter.",
              "Not a defect - say so in the body, in the sentence that sends the agent to "
              "the script.", False),
    "CS004": ("info", "Numbered steps no case checks",
              "The body prescribes a procedure - three or more numbered steps - and "
              "`evals/evals.json` exists, but no case in it carries `process`. Every case "
              "grades what the run left behind; none grades how it got there, so a run "
              "that skips a step or does them out of order passes as long as the answer "
              "comes out right. SkillForgeBench (arXiv 2610.14918) separates the two and "
              "finds strict process scores far below loose ones: following most steps and "
              "following every step are different measurements.",
              "Add a `process` item to the case that exercises the procedure: `order` for "
              "the steps that must come in sequence, `after`/`then` for a check that must "
              "follow the last change. `sqs.py cases <skill> --generate --format json` "
              "drafts one with a `TODO` matcher per step. A numbered list of options rather "
              "than steps reads the same to this check - suppress it there.", False),
}

# ---- rule metadata ---------------------------------------------------------
#
# Two gradings per rule, and they answer different questions:
#
#   confidence      does the check reliably find the thing it names? A filesystem
#                   fact or a parse is `high`; a regex over prose is `medium`; a
#                   similarity heuristic is `low`.
#   false_positive  when the thing IS there, how often is it nonetheless intended?
#                   `README.md` inside a skill folder is a finding and also exactly
#                   what a repository-shaped skill does, so SP013 is `high`.
#
# Both are about the mechanism, not about how much the finding matters - severity
# already carries that. They exist so a report can be filtered by how much a machine
# should be trusted with the judgement: `--min-confidence high` is a gate you can
# leave on in CI, and a `high` false-positive rule is one to read before believing.
#
# A code with no row here fails `sqs.py rules --audit`. `unrated` is the honest value
# for a rule whose engine has not been written yet, and it is not the same as `high`.
GRADES = {
    # spec: frontmatter parsing and filesystem layout, so the detection is a fact
    "SP001": ("high", "low"),    "SP002": ("high", "low"),    "SP003": ("high", "low"),
    "SP004": ("high", "low"),    "SP005": ("high", "low"),    "SP006": ("high", "low"),
    "SP007": ("high", "low"),    "SP008": ("high", "low"),    "SP009": ("high", "low"),
    "SP010": ("high", "medium"),  # a key this suite does not know may be a new one
    "SP011": ("high", "low"),
    "SP012": ("high", "medium"),  # `allow_dirs` exists because the spec permits any
    "SP013": ("high", "high"),    # a repository-shaped skill ships its own README
    "SP014": ("high", "low"),    "SP015": ("high", "low"),
    "SP016": ("high", "medium"), "SP017": ("high", "medium"),
    "SP018": ("high", "low"),    "SP019": ("high", "low"),
    "SP020": ("high", "low"),    # a character test against the reference validator's own rule

    # structure: links resolved against the filesystem, except the text heuristics
    "ST001": ("high", "low"),    "ST002": ("high", "low"),    "ST003": ("high", "low"),
    "ST004": ("high", "low"),
    "ST005": ("high", "medium"),  # an orphan a bundled script opens is not an orphan
    "ST006": ("high", "low"),    "ST007": ("high", "low"),
    "ST008": ("medium", "medium"),
    "ST009": ("medium", "medium"), "ST010": ("medium", "medium"),
    "ST011": ("high", "low"),    "ST017": ("high", "medium"),  # medium: a deleted tool folder reads as a missing install
    "ST012": ("medium", "high"),  # prose that looks like code is a judgement call
    "ST013": ("high", "low"),    "ST014": ("high", "low"),    "ST015": ("high", "low"),
    "ST016": ("unrated", "unrated"),  # documented gap: no engine emits it yet

    # quality: mostly regex over prose, and two similarity heuristics
    "QL001": ("high", "low"),
    "QL002": ("medium", "medium"),
    "QL003": ("low", "high"),     # stem overlap between two trigger phrases
    "QL004": ("low", "high"),     # stem overlap between description and body
    "QL005": ("medium", "high"),  # a hard guardrail is a legitimate prohibition
    "QL006": ("medium", "medium"),
    "QL007": ("high", "low"),
    "QL008": ("medium", "medium"),
    "QL009": ("high", "medium"),
    "QL010": ("medium", "low"),
    "QL011": ("medium", "medium"),
    "QL012": ("high", "low"),
    "QL013": ("medium", "medium"),
    # the exclusion side is read off a pattern of three grammatical roles rather than
    # off any negation, which is what makes it more confident than QL003's blanket
    # polarity flag - but the overlap threshold above it is still a stem heuristic
    "QL014": ("medium", "medium"),
    # the invocation flag is read exactly; the wording is a pattern, kept narrow so that
    # "use when" - fine for a person too - never counts
    "QL015": ("medium", "low"),
    # arXiv 2607.01456's smells, by pattern where the paper used a model. The shapes are
    # read exactly; whether the shape is the smell is the judgement left over. QL016's
    # paragraph length is a measured gap in 149 skills, not a published number. QL017 and
    # QL018 report an absence, so an example or a check in a shape the vocabulary does not
    # know (an italic sample reply, "watch the device log") reads as missing. QL018's
    # vocabulary is also ordinary prose in a skill about checking, which can only silence it.
    "QL016": ("medium", "medium"),
    "QL017": ("medium", "medium"),
    "QL018": ("low", "medium"),
    "QL019": ("medium", "low"),     # a heading or a promise, and the block after it

    # compat: every verdict comes from an adapter's declared support table
    "CP001": ("high", "low"),    "CP002": ("high", "low"),
    "CP006": ("medium", "medium"),
    "CP007": ("high", "low"),     # "undocumented" is a statement about the docs
    "CP008": ("high", "low"),    "CP009": ("high", "low"),

    # security: shaped secrets and codepoints are facts, command patterns are not
    "SE001": ("high", "medium"), "SE002": ("medium", "medium"),
    "SE003": ("medium", "medium"), "SE004": ("high", "low"),
    "SE005": ("medium", "medium"), "SE006": ("high", "medium"),
    # the shapes are narrow and every match is the claim itself; recall stops at the
    # vendors and phrasings the pattern names
    "SE007": ("medium", "low"),
    # the Python half is read off the syntax tree; the shell, PowerShell and JavaScript
    # half is a pattern, and recall there stops at the decoders it names
    "SE008": ("medium", "low"),

    # publish: half of these are correct-and-intended for a skill that stays home
    "PB001": ("high", "low"),    "PB002": ("high", "low"),    "PB003": ("high", "low"),
    "PB004": ("high", "medium"), "PB005": ("high", "low"),    "PB006": ("medium", "medium"),
    "PB007": ("high", "low"),    # hooks.json is read, not inferred
    "PB008": ("medium", "medium"),  # a sibling path can be prose about the pattern, not a use of it
    "PB009": ("high", "low"),    # the source shape is read straight off the manifest
    # the diff is a fact; whether the diff was worth a number is a judgement about the
    # author's work, and that gap is the whole false-positive risk in PB010
    "PB010": ("high", "medium"),
    "PB011": ("medium", "medium"),  # "how it is called" is three fields, not the whole truth
    # as reliable as `capabilities`' own CB001 is; and a reach the author gained on
    # purpose is still a finding, because the reader it is for did not decide it
    "PB012": ("medium", "medium"),
    "PB013": ("high", "low"),    # two parsed numbers compared; unparseable is silence
    # both sides are read off disk; the risk is a fork with no `upstream` remote, and
    # recall stops at the install spellings the pattern knows
    "PB014": ("medium", "medium"),
    "PB015": ("high", "low"),    # git's own toplevel and a directory listing - both exact

    # evals: file parsing and a delegated runner
    "EV001": ("high", "low"),    "EV002": ("high", "low"),    "EV003": ("high", "low"),
    "EV004": ("high", "low"),    "EV005": ("high", "low"),
    "EV006": ("high", "low"),
    "EV007": ("low", "high"),    # same stem-overlap heuristic as QL003, graded the same way
    "EV008": ("high", "low"),    # the absence of two keys, read off the file
    "EV009": ("high", "low"),    # a placeholder, a path and a compile - all exact
    "EV010": ("high", "medium"), # whole-word match is exact; a one-verb fork wording is a fair case
    "EV011": ("high", "low"),    # a path looked up in the skill - exact

    # capabilities: `ast` reads an import or a call exactly, CB002/CB003 only ever fire
    # that way. CB001 also fires off a command-name regex for non-Python scripts, the
    # same reliability `security`'s own DANGEROUS patterns are graded at (SE002), so its
    # grade is the blend of the two paths, not the AST half alone.
    "CB001": ("medium", "medium"), "CB002": ("high", "low"), "CB003": ("high", "low"),
    "CB004": ("high", "low"),    # the documented syntax, read exactly; the fence question is stated, not guessed
    "CB005": ("high", "low"),    # a computed name or code string, read off the tree; limited to capability-bearing modules
    "CB006": ("high", "low"),    # imports read exactly; "named" is any word in the skill's text, generous by design

    # cases: a promise clause and a production verb are both matched by pattern, and a
    # body with no production verb anywhere is a strong signal - but "the description
    # oversold" and "the body says it differently" look alike from outside. CS002 and
    # CS003 both report a silence, which is the reading most easily argued with, and
    # both are `info` for that reason.
    "CS001": ("medium", "medium"),
    "CS002": ("low", "medium"),   # stem overlap, the same test route and EV007 run on
    "CS003": ("low", "high"),     # an author who mentioned it once, elsewhere, is not silent
    "CS004": ("medium", "medium"),  # the numbering is exact; options numbered like steps are not
}

CONFIDENCE_ORDER = ("unrated", "low", "medium", "high")


class Rule:
    """One row of the registry, with its metadata attached.

    Indexable like the tuple it grew out of, so the older unpacking still reads the
    same: `severity, title, why, how, fixable = RULES[code]`.
    """

    __slots__ = ("code", "severity", "title", "why", "how", "fixable",
                 "confidence", "false_positive_risk")

    def __init__(self, code, row, grade):
        self.code = code
        self.severity, self.title, self.why, self.how, self.fixable = row
        self.confidence, self.false_positive_risk = grade or ("unrated", "unrated")

    @property
    def module(self):
        return module_of(self.code)

    @property
    def category(self):
        return module_of(self.code)

    @property
    def autofix(self):
        return self.fixable

    def __getitem__(self, i):
        return (self.severity, self.title, self.why, self.how, self.fixable)[i]

    def __iter__(self):
        return iter((self.severity, self.title, self.why, self.how, self.fixable))

    def as_dict(self):
        return {"id": self.code, "severity": self.severity, "category": self.category,
                "title": self.title, "confidence": self.confidence, "autofix": self.fixable,
                "false_positive_risk": self.false_positive_risk}


RULES = {code: Rule(code, row, GRADES.get(code)) for code, row in _ROWS.items()}


def module_of(code):
    return MODULES.get(code[:2], "?")


def severity_of(code, default="warning"):
    row = RULES.get(code)
    return row.severity if row else default


def confidence_of(code, default="unrated"):
    row = RULES.get(code)
    return row.confidence if row else default


def at_least(confidence, floor):
    """Whether `confidence` clears the `floor` on the confidence ladder."""
    if floor not in CONFIDENCE_ORDER:
        return True
    return CONFIDENCE_ORDER.index(confidence) >= CONFIDENCE_ORDER.index(floor)


def audit(emitted):
    """Codes an engine emitted that have no row here. Empty means the two agree."""
    return sorted(c for c in emitted if c not in RULES)


def ungraded():
    """Codes with no metadata row. A rule nobody has graded is a rule nobody has read."""
    return sorted(c for c in _ROWS if c not in GRADES)
