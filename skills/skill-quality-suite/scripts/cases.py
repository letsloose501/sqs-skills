#!/usr/bin/env python3
"""Given a skill, produce the checks - and report where its three sources disagree.

Every expensive layer in this repository assumes a case set that already exists.
`eval --trigger` needs queries somebody wrote, `eval --runtime` needs tasks somebody
wrote, and the regression gate needs two runs of that set. A stranger's package has
no `evals/` at all and your own has whatever you had patience for on the first day, so
the gate prints "no regression" about behaviour it has never sampled. The set is the
foundation, and nothing else here helps you lay it.

Three sources say what ought to be true of a skill, and they are different sources
rather than three phrasings of one:

- **what you expect of it** - `evals/expectations.md`, one plain sentence per line.
  It is the only source that survives the skill being wrong about itself, and the only
  one that exists before the skill does. A sentence you wrote is already the claim, so
  this source needs no model;
- **each improvement** - a capability the skill just gained, which no existing case
  exercises and which you will never again remember as well as today. `--since` reads
  it out of the capability module: the trigger is a capability changing, not a file
  changing, because a typo owes nobody a check;
- **what the skill promises** - *use me when X and I will do Y*. `X` is the half
  `eval --trigger` already measures. `Y` is the half nothing measures, and it is where
  a skill that passes every check still fails to deliver.

What the disagreement means is the useful part, and the reason this is one thing
rather than three:

    expectation  promise  behaviour   reading
        yes        no        -        wrong skill: it never claimed to do what you need
        yes        yes       no       broken skill, or a description that oversold
        no         yes       yes      fine skill, not for you
        -          no        yes      undeclared capability: it does Z and says nothing

Three constraints, all of them learned from the rest of the suite:

**Generated is not trusted.** The output is a case file a human reads and edits before
it counts; every generated case carries `needs_review` and `source`, and `--apply`
refuses to overwrite a set that already exists. A set nobody can correct is a set
nobody will believe - the same mistake as a linter whose rules cannot be suppressed.

**Deterministic first, never circular.** Everything here reduces to an assertion the
existing grader already runs: a file exists, a string is present, a tool was not used,
the step count stayed under a cap. A model that invents a claim and then grades its own
claim has measured nothing, so no claim in this module comes from a model. What a regex
cannot reach is left as a `TODO` for the author rather than filled in by a guess - the
prose-to-claims layer that would need a model stays opt-in and outside `check`.

**Not a score.** "78% honest" is unactionable and is the one-number headline this
project already rejected. The rules report what disagrees and stop.
"""
import json
import os
import re

import capabilities
import quality
from core import Finding, strip_code

EXPECTATIONS = "evals/expectations.md"
CASES_FILE = "evals/evals.json"
# One list item is one expectation. Prose around them is the author's note to
# themselves and is not a claim about the skill.
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<claim>.+)$")

# A promise that the skill leaves something behind. Splitting production from
# presentation is the whole point: "print the path" and "tell the user" produce
# nothing that outlives the turn, and a description promising a file is not served by
# a body that only answers.
# Only verbs that cannot also be read as the noun beside them. `files`, `records`,
# `stores`, `copies`, `moves` and `exports` were in this list and came out: "a dated
# summary file for every meeting transcript" parsed as the verb `file` taking
# `transcript` as its object, and "when a bank export lands in the downloads folder"
# parsed as the verb `export` promising a folder. A word that is a plausible artefact in
# its own right cannot be the evidence that something produced an artefact.
MAKE = (r"writes?|creates?|saves?|appends?|generates?|renders?|"
        r"produces?|builds?|"
        r"пишет|записыва\w*|создаёт|создает|сохраня\w*|формиру\w*|оформля\w*|кладёт|кладет")
ARTEFACT = (r"file|files|note|notes|report|document|spreadsheet|workbook|folder|"
            r"directory|index|changelog|summary|transcript|draft|entry|row|table|"
            r"\.\w{2,5}\b|"
            # A format named without its dot: "saves it as a PNG" promises a file just
            # as plainly as "saves a .png", and a skill that produces a picture says
            # the first far more often than the second.
            r"png|pdf|csv|tsv|json|ya?ml|xlsx|docx|pptx|svg|html|markdown|"
            r"файл\w*|заметк\w*|отчёт\w*|отчет\w*|документ\w*|папк\w*|конспект\w*")
PROMISE_RE = re.compile(r"\b(?:" + MAKE + r")\b[^.;:\n]{0,70}?\b(?P<artefact>"
                        + ARTEFACT + r")", re.I)
# The same production verbs, looked for anywhere in the body. The body is instructions,
# so one production verb anywhere is enough to say the skill does leave something
# behind; the rule is about a body that leaves nothing at all.
BODY_MAKE_RE = re.compile(r"\b(?:" + MAKE + r")\b", re.I)

# What a skill has to say to have announced a capability, as `quality.stems()` sees it:
# the same five-letter prefixes the rest of the suite compares on, rather than a regex
# per wording. Written by hand as regexes first, and the live tree said no - `запуск\w*`
# matches `запуска` and misses `запусти`, which is the form an instruction is actually
# written in, so a skill whose every step says "run the script" read as silent about
# running scripts. Inflection is exactly what the shared stemmer exists for, and a
# second hand-rolled one beside it would have gone on being wrong in a different way.
ANNOUNCE_STEMS = {
    # `request`/`запрос` and `ссылка` are not here: "the user's request" and a wiki
    # link are what those words normally are in a skill, and a word that reads as
    # ordinary prose cannot be the evidence that something reaches the network.
    "CB001": {"netwo", "inter", "onlin", "offli", "fetch", "downl", "uploa", "https",
              "endpo", "scrap", "brows", "сеть", "сети", "сетев", "интер",
              "скача", "скачи", "загру", "онлай"},
    # `script`, `run` and `запустить` are deliberately absent, and leaving them in made
    # this arm structurally dead: `CB002` only ever fires because a *bundled* script
    # spawns something, and a skill that bundles a script almost always says so. What
    # the skill failed to mention is that the script reaches past itself to a command
    # on the machine, so only wording about an external command counts.
    "CB002": {"execu", "shell", "subpr", "spawn", "comma", "termi", "binar",
              "коман", "терми", "оболо"},
}
# `CB003` - reading the environment - is deliberately not here, and the gap is the
# finding rather than an omission. Three vocabularies were tried against the installed
# tree and each was wrong in both directions: `config`/`setting`/`key` silenced a skill
# on one stray word in a reference about something else, and `окружение`/`переменная` -
# the only words a Russian author would use - are ordinary prose in exactly the domain
# these skills are written about ("замыкание помнит окружение", "`snake_case` —
# переменные"). A capability whose announcement cannot be told from the subject matter
# is one this test cannot judge, and a fourth vocabulary would have been tuning against
# the examples rather than fixing the test - which is the thing this project's own rules
# about editing a skill forbid. `capabilities` still reports `CB003` itself; what is
# withdrawn is only the claim that nobody mentioned it.

# Words too short for the stemmer's four-letter floor, checked whole. `env` and `key`
# are how an author most often mentions exactly these two capabilities.
ANNOUNCE_WORDS = {
    "CB001": {"api", "apis", "url", "urls", "web", "http", "curl", "wget"},
    "CB002": {"cli", "bash", "zsh", "sh", "exe"},
}
SHORT_WORD_RE = re.compile(r"[^\W\d_]+", re.U)


def expectations(skill):
    """The sentences the author wrote about what they want, one claim each.

    Markdown because it is meant to be written by hand and read by a person, and **one
    list item is one claim**. Every line was a claim in the first version of this, and
    the fixture's own explanatory paragraph - the two sentences telling the author what
    the file is for - came back as three expectations the skill had failed to meet. A
    file that cannot hold a note about itself is a file nobody annotates.

    Nothing parses further than the item. A sentence you wrote is already the claim,
    and a parser that tried to improve it would be the model layer this module refuses
    to be.
    """
    path = os.path.join(skill.root, EXPECTATIONS.replace("/", os.sep))
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    out = []
    for line in strip_code(text).split("\n"):
        m = ITEM_RE.match(line)
        if not m:
            continue
        claim = m.group("claim").strip()
        if len(claim) >= 12:
            out.append(claim)
    return out


def promises(skill):
    """(clause, artefact) for each outcome the description commits to.

    The `Y` of *use me when X and I will do Y*, read out of the part of the description
    before `TRIGGER_RE`'s lead-in. `X` - the trigger branch after it - is the half
    `eval --trigger` already measures, and reading a promise out of it produces
    nonsense: "Use when a bank export lands in the downloads folder" parsed as a
    promise to produce a folder. The same split `EV007` makes for the same reason, from
    the same pattern, so the two cannot drift apart.

    The artefact is kept separately because the useful question is not whether the body
    produces *something* - almost every body does - but whether it produces the thing
    that was promised.
    """
    desc = skill.description or ""
    m = quality.TRIGGER_RE.search(desc)
    outcome = desc[:m.start()] if m else desc
    return [(mm.group(0).strip(), mm.group("artefact"))
            for mm in PROMISE_RE.finditer(outcome)]


HEADING_RE = re.compile(r"^#{1,6}[ \t].*$", re.M)


def instructions(skill):
    """The body with its headings and code taken out: what the agent is told to do.

    A heading restates the skill's own subject by construction - `# Summary writer`
    over a skill that promises a summary - so it can never be evidence that some step
    produces one. Watched silencing this rule on a skill written to fail it, which is
    the same shape as `EV007`'s trigger lead-in: wording that repeats because of how
    skills are written, not because of what this one does.
    """
    return strip_code(HEADING_RE.sub("", skill.body or ""))


def unserved(skill):
    """(clause, why) for each promise the body has no instruction behind.

    Two readings, and the first alone was not enough. "Does any step produce
    anything" was the first version of this test, and a body whose only match was the
    ordinary verb in "every decision it records" read as producing a file - watched
    happening on a skill written to fail this rule, which is the cheapest place to
    find out a test does not test. So the promised artefact has to be in the body too:
    a description promising a file, over a body that never says `file` anywhere, is
    the shape the rule is named after.
    """
    body = instructions(skill)
    makes = bool(BODY_MAKE_RE.search(body))
    body_stems = quality.stems(body)
    low = body.casefold()
    out = []
    for clause, artefact in promises(skill):
        if not makes:
            out.append((clause, "no step in the body writes, saves or files anything"))
            continue
        art = artefact.casefold()
        present = (quality.stems(artefact) & body_stems) if quality.stems(artefact) \
            else art in low
        if not present:
            out.append((clause, f"nothing in the body mentions `{artefact}`"))
    return out


NUMBERED_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<n>\d+)[.)][ \t]+(?P<text>\S.*)$")
# The fewest steps that make a procedure rather than a pair of alternatives.
MIN_STEPS = 3
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")


def procedure(skill):
    """The longest run of numbered steps in the body, `1.` upward, as their texts.

    Read off the raw body, not `instructions()`: that view strips code, and a step whose
    whole point is "run `scripts/plot.py`" would lose the one span that says how to see
    it in a transcript. A run ends at the first line that is neither the next number,
    blank, nor indented under the item before it; renumbering from 1 starts a new run.

    What this cannot tell apart is a numbered list of *options* from a list of *steps* -
    "1. a CSV 2. a JSON file 3. a table" is the same shape. That is why `CS004` is info.
    """
    best, run, last = [], [], 0
    for line in (skill.body or "").split("\n"):
        m = NUMBERED_RE.match(line)
        if m and not m.group("indent"):
            n = int(m.group("n"))
            if n == 1:
                run, last = [m.group("text").strip()], 1
            elif run and n == last + 1:
                run.append(m.group("text").strip())
                last = n
            else:
                run, last = [], 0
        elif run and (not line.strip() or line[:1] in (" ", "\t")):
            continue
        else:
            run, last = [], 0
        if len(run) > len(best):
            best = list(run)
    return best if len(best) >= MIN_STEPS else []


def unchecked_procedure(skill):
    """The procedure, when the skill has a runtime set and no case checks its steps."""
    steps = procedure(skill)
    if not steps:
        return []
    path = os.path.join(skill.root, CASES_FILE.replace("/", os.sep))
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        # no set, or one that does not parse - `EV002`/`EV004` speak to those, and a
        # skill nobody evaluates at all is not missing *process* checks in particular
        return []
    raw = data.get("evals") if isinstance(data, dict) else data
    if not isinstance(raw, list) or any(isinstance(c, dict) and c.get("process")
                                        for c in raw):
        return []
    return steps


def unannounced(skill, cfg=None):
    """(code, how many scripts carry it) for capabilities the skill never mentions.

    One entry per capability, not per import. A skill with eight bundled scripts that
    all read the environment is silent about one thing, and reporting it eight times
    is how a rule with a high false-positive risk gets a whole module switched off.

    Read against the raw text, fences included, rather than `strip_code`'s prose-only
    view, and across every text file the skill carries rather than `SKILL.md` alone:
    the question this rule asks is *were you told*, and a command block showing `curl`
    in a reference page does tell you. Everywhere else in the suite a fenced literal
    is a quotation rather than an instruction, so this difference is stated here
    rather than assumed.
    """
    text = "\n".join(t for _, t in skill.texts())
    # Not `quality.WORD_RE`: that one has a four-letter floor, and every word in
    # `ANNOUNCE_WORDS` is there precisely because it is shorter than that. Reusing it
    # would have made this whole branch unreachable without ever failing.
    words = set(SHORT_WORD_RE.findall(text.casefold()))
    st = quality.stems(text)
    seen = {}
    for finding in capabilities.check(skill, cfg):
        stem_set = ANNOUNCE_STEMS.get(finding.code)
        if stem_set is None:
            continue
        if st & stem_set or words & ANNOUNCE_WORDS.get(finding.code, set()):
            continue
        seen.setdefault(finding.code, []).append(finding)
    return sorted(seen.items())


def check(skill, cfg=None, registry=None):
    """CS001-CS003: the three disagreements that need no agent run to see."""
    cfg = cfg or {}
    out = []
    if not skill.ok:
        return out

    # CS001 - the description promises an artefact and the body never makes one. This
    # is the narrow, checkable half of what `QL004` reports as a statistic: not "the
    # description and the body barely overlap" but "this promised outcome has no
    # instruction behind it". It passes `--trigger`, it passes a hand-written
    # `--runtime` set, and it is the skill that wastes your time most quietly.
    for clause, why in unserved(skill)[:1]:
        out.append(Finding("CS001", f"the description promises `{clause[:60]}` and "
                                    f"{why}"))

    # CS002 - a sentence in `evals/expectations.md` this skill never claimed. The top
    # row of the table, and the one that must not read as a defect: the skill is fine,
    # it is the wrong skill for what was written beside it.
    for want in expectations(skill):
        score, _ = quality.prompt_match(skill.description or "", quality.stems(want))
        if score > 0:
            continue
        near = _nearest(want, registry, skill)
        out.append(Finding("CS002",
                           f"expected `{want[:60]}` - the description shares no wording "
                           f"with it" + (f"; `{near}` is closer" if near else "")
                           + ". Not a defect: the wrong skill for this expectation",
                           where=EXPECTATIONS))

    # CS003 - the bottom row: it does `Z` and says nothing about it. `capabilities`
    # says what a skill CAN do to the machine; this says that it never told you.
    for code, found in unannounced(skill, cfg):
        where = ", ".join(sorted({f.where for f in found if f.where})[:3])
        out.append(Finding("CS003", f"{found[0].msg} - and no wording in the skill "
                                    f"announces it"
                                    + (f" ({len(found)} script(s): {where})"
                                       if len(found) > 1 else ""),
                           where=found[0].where, line=found[0].line))

    # CS004 - the body prescribes numbered steps, a runtime set exists, and no case in
    # it says anything about whether the steps were followed. Every case grades the
    # answer; none grades the way there. SkillForgeBench's strict process scores are
    # where agent reliability fell apart, and a set like this cannot see that happen.
    steps = unchecked_procedure(skill)
    if steps:
        out.append(Finding("CS004", f"the body numbers {len(steps)} steps and no case in "
                                    f"{CASES_FILE} carries `process`, so a run that "
                                    f"skips or reorders them still passes",
                           where=CASES_FILE))
    return out


def _nearest(want, registry, skill):
    """The other skill whose description does share wording with this expectation."""
    if not registry:
        return None
    st = quality.stems(want)
    best, best_score = None, 0.0
    for name, desc in registry.items():
        if name == (skill.name or skill.folder) or not isinstance(desc, str):
            continue
        score, _ = quality.prompt_match(desc, st)
        if score > best_score:
            best, best_score = name, score
    return best


# ---- the generator ------------------------------------------------------------------

TODO = "TODO"


def _case(source, ident, prompt, expected, assertions=(), outputs=()):
    return {"id": ident, "prompt": prompt, "expected_output": expected,
            "assertions": list(assertions), "outputs": list(outputs),
            "source": source, "needs_review": True}


EXT_RE = re.compile(r"\.(md|txt|json|csv|tsv|ya?ml|xlsx|docx|pptx|pdf|html|svg|png)\b", re.I)


def generate(skill, gained=()):
    """The case set this skill's three sources ask for, ready for a human to correct.

    Nothing here is graded as written. An assertion appears only where the source text
    named something checkable - a file extension, a literal the answer has to carry -
    and everything else is left as `TODO`, because the alternative is a case that
    passes without having tested anything, which is the one output the grading rules
    already refuse to produce.
    """
    name = skill.name or skill.folder
    out = []
    for i, want in enumerate(expectations(skill), 1):
        ext = EXT_RE.search(want)
        out.append(_case("expectation", f"{name}-exp-{i:02d}", want,
                         f"{TODO}: what the answer has to contain for this to be met",
                         outputs=[f"{TODO}{ext.group(0)}"] if ext else ()))
    for i, (claim, _) in enumerate(promises(skill), 1):
        ext = EXT_RE.search(claim)
        out.append(_case("promise", f"{name}-pro-{i:02d}",
                         f"{TODO}: a request that should make the skill `{claim}`",
                         f"the skill {claim}",
                         outputs=[f"{TODO}{ext.group(0)}"] if ext else ()))
    for i, cap in enumerate(gained, 1):
        out.append(_case("improvement", f"{name}-imp-{i:02d}",
                         f"{TODO}: a request that exercises `{cap}`",
                         f"the new capability is used and reported: {cap}"))
    steps = procedure(skill)
    if steps:
        # One `order` item, one matcher per step, every one a `TODO` the pre-flight
        # refuses until a person writes it. Which tool call shows a step happened is
        # the author's knowledge, not the text's: "choose the axis range" leaves no call
        # at all, and a guessed matcher would grade a run on the guess. A code span in
        # the step is the one thing the text does say, so it rides along as a hint.
        matchers = []
        for n, step in enumerate(steps, 1):
            hints = CODE_SPAN_RE.findall(step)
            matchers.append(f"{TODO}: step {n} - {step.replace('`', '').strip()[:60]}"
                            + (f" (hint: {', '.join(hints[:2])})" if hints else ""))
        case = _case("procedure", f"{name}-proc-01",
                     f"{TODO}: a request that makes the skill run its numbered steps",
                     "the steps are followed in the order the body gives them")
        case["process"] = [{"id": "steps-in-order", "order": matchers}]
        out.append(case)
    return {"skill_name": name, "evals": out}


def gained_capabilities(skill, previous_findings, cfg=None):
    """Capability lines present now and absent at `--since` - one check each.

    A capability is the trigger rather than a file, so the comparison is between two
    sets of capability findings, not between two trees of text. An edit that moved a
    paragraph gains nothing and asks for no case; an edit that made the skill reach
    the network asks for exactly one.
    """
    before = {f"{f.code} {f.msg}" for f in previous_findings}
    return [f"{f.code} {f.msg}" for f in capabilities.check(skill, cfg)
            if f"{f.code} {f.msg}" not in before]
