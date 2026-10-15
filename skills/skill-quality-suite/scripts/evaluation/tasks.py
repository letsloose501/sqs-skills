#!/usr/bin/env python3
"""The task set a runtime evaluation runs, and how one run of one task is graded.

The file is the one the skill-creation guidance already asks for - `evals/evals.json` -
read a little more strictly, because a grader needs something it can check:

    {"skill_name": "pdf-to-xlsx",
     "evals": [{"id": "pdf-to-xlsx-03",
                "prompt":  "Convert quarterly.pdf into a spreadsheet",
                "expected_output": "an .xlsx with one sheet per table",
                "assertions": ["xlsx", "re:\\\\b3 tables?\\\\b", "not:could not"],
                "files": ["evals/files/quarterly.pdf"],
                "outputs": ["quarterly.xlsx",
                            {"path": "summary.md", "contains": ["re:Q[1-4]"]}],
                "forbidden_tools": ["WebSearch"],
                "max_tool_calls": 8}]}

An assertion is a substring by default, a regex behind `re:`, and a prohibition behind
`not:`. `outputs` names what the run has to have created in its working directory - the
only assertion form that survives a model rewording its answer. A bare path asks only
that the file exists; `{"path", "contains"}` also reads it as UTF-8 text and applies the
same assertion grammar to what is inside, because an empty file or a file with the
wrong rows exists just as well as the right one.

`files` means what it means in skill-creator's format: **input** paths relative to the
skill, copied into the run the way `fixtures` are. Before that was read, this module
took `files` for outputs, so a set written for skill-creator failed on both arms and
handed the agent none of its inputs. An old-style entry - one that is not a file inside
the skill - is still graded as an output, and the pre-flight says so (`EV011`), rather
than a published set changing its meaning under its author in silence.

`judge` is the third form, for correctness a substring cannot express - a total that has
to add up, a file that has to parse: a program run after the task, in the run's working
directory, whose exit code decides. It is an argv list, never a shell line, with `{python}`,
`{skill}` and `{workdir}` filled in:

    "judge": ["{python}", "{skill}/evals/check_totals.py", "{workdir}/totals.md"]

Deterministic, unlike a model judge, and it is the skill's own code, so a runtime pass
runs it only under `--trust-target`, like a tree's own routing runner (`EV006`).

A case with no assertions, no `outputs` and no `judge` is **ungraded**, and stays that way
in the report. Counting it as a pass would turn "nobody said what success is" into evidence
of success, which is the one number this module must never produce.

`process` grades the other half: not what the run left behind but how it got there. A
skill that says "read the ledger, then append one row" can be served by an answer that
appends three rows blind and still gets the total right; every check above passes it.
SkillForgeBench (arXiv 2610.14918) measures exactly this split - completion rubrics
against process rubrics - and its strict process scores sit far below its loose ones.
Each item reads the ordered tool calls the transcript recorded:

    "process": [
      {"id": "read-first", "order": ["Read:ledger.csv", "Edit|Write:ledger.csv"]},
      {"id": "verify",     "after": "Edit|Write:ledger.csv", "then": "Read:ledger.csv"},
      {"id": "one-row",    "count": "Edit|Write:ledger.csv", "max": 1},
      {"id": "offline",    "never": "WebFetch|WebSearch"}]

A matcher is `Tool` or `Tool:<assertion>`: names joined by `|`, then the same assertion
grammar as above, applied to the call's input. The paper grades its rubrics with a model;
these are deterministic for the same reason `judge` is a program, and what a tool call
cannot show - a step that is only thought - is out of their reach and stays the author's.
Process is graded apart from completion, so `success_rate` keeps meaning what it meant.
"""
import json
import os
import re
import subprocess
import sys

# How long a judge program may take. A judge reads what the run left behind; one that is
# still going after a minute is stuck, and a stuck judge must fail the case, not hang the
# pass.
JUDGE_TIMEOUT = 60

CASES = os.path.join("evals", "evals.json")


def _inside(base, rel):
    full = os.path.realpath(os.path.join(base, rel))
    return full == base or full.startswith(base + os.sep)


class Task:
    __slots__ = ("id", "prompt", "expected", "assertions", "outputs", "legacy_outputs",
                 "fixtures", "forbidden_tools", "max_tool_calls", "timeout",
                 "expectations", "judge", "process")

    def __init__(self, raw, index, skill_root=None):
        self.id = str(raw.get("id") or index)
        self.prompt = raw.get("prompt") or ""
        self.expected = raw.get("expected_output") or ""
        self.assertions = [a for a in (raw.get("assertions") or []) if isinstance(a, str)]
        # input files, copied from inside the skill into the run's working directory:
        # a task about a PDF needs the PDF, and a task the agent cannot start is not a
        # measurement of anything
        self.fixtures = [f for f in (raw.get("fixtures") or []) if isinstance(f, str)]
        # a path, or {"path", "contains"} - kept raw here, so a malformed entry reaches
        # the pre-flight and is refused there with a reason instead of vanishing
        self.outputs = list(raw.get("outputs") or [])
        # skill-creator's `files` are inputs. An entry that is a file inside the skill
        # can only be one; an entry that is not is this suite's old meaning, an output.
        # Existence decides, because it is the one reading both formats agree on.
        base = os.path.realpath(skill_root) if skill_root else None
        self.legacy_outputs = []
        for f in raw.get("files") or []:
            if not isinstance(f, str):
                continue
            if base and _inside(base, f) and os.path.isfile(os.path.join(base, f)):
                self.fixtures.append(f)
            else:
                self.legacy_outputs.append(f)
        self.outputs += self.legacy_outputs
        # skill-creator's model-graded statements. Not read here - noted, so a case that
        # carries only these is reported as ungraded *for that reason*
        self.expectations = bool(raw.get("expectations"))
        self.forbidden_tools = raw.get("forbidden_tools") or []
        self.max_tool_calls = raw.get("max_tool_calls")
        self.timeout = raw.get("timeout") or 300
        # kept raw, like `outputs`: a malformed judge is refused by the pre-flight
        self.judge = raw.get("judge")
        # kept raw too: an item the grader cannot read is the pre-flight's to refuse
        self.process = raw.get("process")

    @property
    def graded(self):
        """Whether anything decides completion. Process is counted on its own."""
        return bool(self.assertions or self.outputs or self.judge)

    @property
    def process_items(self):
        return [p for p in self.process if isinstance(p, dict)] \
            if isinstance(self.process, list) else []


# ---- process: how the run got there -----------------------------------------------

PROCESS_FORMS = ("order", "after", "never", "count")


def parse_matcher(m):
    """(tool names, assertion or None, problem) for one `Tool[|Tool]:assertion` string.

    Split at the first colon only: a tool name never carries one (`mcp__server__tool`
    included), and the assertion after it may - `re:` and `not:` are themselves prefixes.
    """
    if not isinstance(m, str) or not m.strip():
        return None, None, f"matcher {m!r} is not a non-empty string"
    tool, sep, rest = m.partition(":")
    names = [n.strip() for n in tool.split("|")]
    if not all(names):
        return None, None, f"matcher `{m}` has an empty tool name"
    return set(names), (rest if sep else None), ""


def matches(m, call):
    names, assertion, problem = parse_matcher(m)
    if problem:
        return False
    name, arg = call
    if name not in names:
        return False
    return assertion is None or check_text(assertion, arg or "", "the call")[0]


def process_problem(item):
    """Why this process item cannot be graded as written, or ""."""
    if not isinstance(item, dict):
        return f"process item {item!r} is not an object"
    forms = [f for f in PROCESS_FORMS if f in item]
    if len(forms) != 1:
        return (f"process item {item.get('id', '?')!r} needs exactly one of "
                f"{', '.join(PROCESS_FORMS)}, has {', '.join(forms) or 'none'}")
    form = forms[0]
    if form == "order":
        seq = item["order"]
        if not isinstance(seq, list) or len(seq) < 2:
            return "`order` needs a list of at least two matchers - one is `count` with `min: 1`"
        used = seq
    elif form == "after":
        if "then" not in item:
            return "`after` without `then` - nothing says what has to follow it"
        used = [item["after"], item["then"]]
    elif form == "count":
        lo, hi = item.get("min"), item.get("max")
        if lo is None and hi is None:
            return "`count` needs `min`, `max` or both"
        for v in (lo, hi):
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                return f"`count` bound {v!r} is not a whole number >= 0"
        if lo is not None and hi is not None and lo > hi:
            return f"`count` has min {lo} above max {hi}"
        used = [item["count"]]
    else:
        used = [item["never"]]
    for m in used:
        _, assertion, problem = parse_matcher(m)
        if problem:
            return problem
        if PLACEHOLDER_RE.match(m):
            return f"matcher `{m}` is still a draft - it opens with `TODO`"
        if assertion is not None:
            bad = _bad_regex(assertion)
            if bad:
                return bad
    return ""


def _first(m, calls, start=0):
    return next((i for i in range(start, len(calls)) if matches(m, calls[i])), None)


def grade_process_item(item, calls):
    """(ok, detail) for one item against the run's ordered tool calls."""
    if "order" in item:
        pos, prev = 0, None
        for m in item["order"]:
            i = _first(m, calls, pos)
            if i is None:
                if prev is not None and _first(m, calls) is not None:
                    return False, f"`{m}` came only before `{prev}`"
                return False, f"`{m}` never came"
            pos, prev = i + 1, m
        return True, ""
    if "after" in item:
        hits = [i for i, c in enumerate(calls) if matches(item["after"], c)]
        if not hits:
            # Nothing to verify is not a verified run: the step that should have been
            # checked never happened, and a pass here would hide that.
            return False, f"`{item['after']}` never came, so nothing could follow it"
        if _first(item["then"], calls, hits[-1] + 1) is None:
            return False, f"no `{item['then']}` after the last `{item['after']}`"
        return True, ""
    if "never" in item:
        i = _first(item["never"], calls)
        return (True, "") if i is None else (False, f"call {i + 1} was `{calls[i][0]}`")
    n = sum(1 for c in calls if matches(item["count"], c))
    lo, hi = item.get("min"), item.get("max")
    if lo is not None and n < lo:
        return False, f"{n} call(s), at least {lo} required"
    if hi is not None and n > hi:
        return False, f"{n} call(s), at most {hi} allowed"
    return True, ""


def item_id(item, index):
    form = next((f for f in PROCESS_FORMS if f in item), "item")
    return str(item.get("id") or f"{form}-{index}")


def judge_argv(judge, skill_root, workdir):
    """The judge's argv with its three placeholders filled, or None if it is malformed."""
    if not isinstance(judge, list) or not judge or not all(isinstance(a, str) for a in judge):
        return None
    fill = {"{python}": sys.executable, "{skill}": os.path.abspath(skill_root or "."),
            "{workdir}": os.path.abspath(workdir or ".")}
    out = []
    for arg in judge:
        for key, value in fill.items():
            arg = arg.replace(key, value)
        out.append(arg)
    return out


def run_judge(judge, skill_root, workdir):
    """(passed, detail) - the judge program's verdict on what the run left behind."""
    argv = judge_argv(judge, skill_root, workdir)
    if argv is None:
        return False, "the judge is not a list of strings"
    try:
        r = subprocess.run(argv, cwd=workdir or ".", capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=JUDGE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"the judge ran past {JUDGE_TIMEOUT}s"
    except OSError as e:
        return False, f"the judge could not start: {e}"
    if r.returncode == 0:
        return True, ""
    said = (r.stdout + r.stderr).strip().splitlines()
    return False, f"exit {r.returncode}" + (f": {said[-1][:120]}" if said else "")


def output_spec(entry):
    """(path, [assertion], problem) for one `outputs` entry."""
    if isinstance(entry, str):
        return entry, [], ""
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        return None, [], f"output {entry!r} is neither a path nor {{\"path\": ...}}"
    contains = entry.get("contains") or []
    if isinstance(contains, str):
        contains = [contains]
    if not isinstance(contains, list) or not all(isinstance(c, str) for c in contains):
        return entry["path"], [], f"output `{entry['path']}`: `contains` is not a list of strings"
    return entry["path"], contains, ""


class Grade:
    __slots__ = ("checks", "graded", "passed", "unnecessary", "forbidden", "unsafe",
                 "process", "process_graded", "process_passed")

    def __init__(self, checks, graded, unnecessary=0, forbidden=(), unsafe=(), process=()):
        self.checks = checks                # [(what, ok, detail)]
        self.graded = graded
        self.passed = graded and all(ok for _, ok, _ in checks)
        self.unnecessary = unnecessary
        self.forbidden = list(forbidden)
        self.unsafe = list(unsafe)
        # [(item id, ok, detail)] - apart from `checks`, so `passed` stays completion
        self.process = list(process)
        self.process_graded = bool(self.process)
        self.process_passed = self.process_graded and all(ok for _, ok, _ in self.process)

    @property
    def process_share(self):
        """The loose score: the share of process items met, or None with none to meet."""
        if not self.process:
            return None
        return sum(1 for _, ok, _ in self.process if ok) / len(self.process)

    def as_dict(self):
        return {"graded": self.graded, "passed": self.passed,
                "process_passed": self.process_passed if self.process_graded else None,
                "process": [{"id": i, "ok": ok, "detail": d} for i, ok, d in self.process],
                "checks": [{"what": w, "ok": ok, "detail": d} for w, ok, d in self.checks],
                "unnecessary_tool_calls": self.unnecessary,
                "forbidden_tools_used": self.forbidden,
                "safety_violations": self.unsafe}


def _dangerous_patterns():
    """The security module's own command patterns, reused on what the agent actually ran.

    A static check reads what a skill *says*; this reads what following the skill made
    the agent *do*. Same patterns, so a rule that is reported at rest is the same rule
    that is reported in flight - and neither list can drift away from the other.
    """
    try:
        from security import DANGEROUS
        return DANGEROUS
    except ImportError:                                            # pragma: no cover
        return []


def check_text(a, text, where):
    """(ok, detail) - one assertion against one text; `where` names it in the detail."""
    if a.startswith("not:"):
        body = a[4:]
        if body.startswith("re:"):
            hit = re.search(body[3:], text, re.I | re.S) is not None
        else:
            hit = body.lower() in text.lower()
        return not hit, f"found in {where}" if hit else ""
    if a.startswith("re:"):
        hit = re.search(a[3:], text, re.I | re.S) is not None
        return hit, "" if hit else f"no match in {where}"
    hit = a.lower() in text.lower()
    return hit, "" if hit else f"not in {where}"


def read_text(full):
    """(text, problem) - a created file as UTF-8, or why it cannot be read as text."""
    try:
        with open(full, "rb") as f:
            data = f.read()
    except OSError as e:
        return None, f"unreadable: {e}"
    if b"\0" in data:
        return None, "not text - `contains` reads UTF-8 text"
    try:
        return data.decode("utf-8-sig"), ""
    except UnicodeDecodeError:
        return None, "not UTF-8 text - `contains` reads UTF-8 text"


def grade(task, run, skill_root=None):
    checks = []
    text = run.text or ""
    if task.judge is not None:
        ok, detail = run_judge(task.judge, skill_root, run.workdir)
        checks.append(("judge", ok, detail))
    for a in task.assertions:
        ok, detail = check_text(a, text, "the answer")
        checks.append((a, ok, detail))
    for entry in task.outputs:
        rel, contains, _ = output_spec(entry)
        if rel is None:
            continue                                  # refused by the pre-flight
        full = os.path.join(run.workdir or ".", rel)
        there = os.path.exists(full)
        checks.append((f"file:{rel}", there, "" if there else "never created"))
        # A file that is not there fails once, on existence, and not once more per
        # assertion: the content checks would only repeat the same fact.
        if not contains or not there:
            continue
        body, problem = read_text(full)
        for a in contains:
            if body is None:
                checks.append((f"file:{rel} {a}", False, problem))
            else:
                ok, detail = check_text(a, body, f"`{rel}`")
                checks.append((f"file:{rel} {a}", ok, detail))

    used = [name for name, _ in run.tools]
    forbidden = sorted({t for t in task.forbidden_tools if t in used})
    unnecessary = 0
    if task.max_tool_calls is not None and len(run.tools) > task.max_tool_calls:
        unnecessary = len(run.tools) - task.max_tool_calls

    unsafe = []
    for label, rx in _dangerous_patterns():
        for name, arg in run.tools:
            if rx.search(arg):
                unsafe.append(f"{label} (via {name})")
                break

    process = []
    for i, item in enumerate(task.process_items, 1):
        if process_problem(item):
            continue                                  # refused by the pre-flight
        ok, detail = grade_process_item(item, run.tools)
        process.append((item_id(item, i), ok, detail))
    return Grade(checks, task.graded, unnecessary, forbidden, sorted(set(unsafe)), process)


# A field that still opens with the placeholder `sqs.py evals --init` and `sqs.py cases
# --generate` write. Anchored at the start, because a real task may well mention a
# TODO list; a draft never starts any other way.
PLACEHOLDER_RE = re.compile(r"TODO\b")

# Formats that are archives or images on disk: a substring of their bytes is not a
# substring of what a person sees in them, so `contains` on one can never pass honestly.
BINARY_RE = re.compile(r"\.(xlsx|xlsm|docx|pptx|odt|ods|pdf|zip|png|jpe?g|gif|webp)$", re.I)


def _bad_regex(a):
    body = a[4:] if a.startswith("not:") else a
    if body.startswith("re:"):
        try:
            re.compile(body[3:])
        except re.error as e:
            return f"`{a}` is not a valid regex ({e})"
    return ""


def preflight(skill_root, task_list):
    """[(task id, "ungraded" | "unrunnable" | "legacy", why)] - what a run would waste
    money on, or read differently from what its author meant.

    Everything here is found today only after the money is spent: an ungraded case shows
    up as `ungraded` in the report, a fixture that is not there is skipped in silence and
    the agent starts a task about a file it was never given, and a broken `re:` raises in
    the grader after both arms have already run. All of it is readable off the file.
    A case can come back twice - `legacy` with either of the others.
    """
    out = []
    base = os.path.realpath(skill_root)
    for t in task_list:
        why = []
        specs = [output_spec(e) for e in t.outputs]
        fields = ([t.prompt, t.expected] + t.assertions + t.fixtures
                  + [p for p, _, _ in specs if p] + [c for _, cs, _ in specs for c in cs])
        if any(PLACEHOLDER_RE.match(f) for f in fields):
            why.append("still a draft - a field opens with `TODO`")
        for rel in t.fixtures:
            if not _inside(base, rel):
                why.append(f"fixture `{rel}` is outside the skill")
            elif not os.path.exists(os.path.join(base, rel)):
                why.append(f"fixture `{rel}` does not exist")
        for path, contains, problem in specs:
            if problem:
                why.append(problem)
            if path is None:
                continue
            # the run directory stands in for `base`: any directory shows the escape
            if os.path.isabs(path) or not _inside(base, path):
                why.append(f"output `{path}` is outside the run's working directory")
            if contains and BINARY_RE.search(path):
                why.append(f"output `{path}` is a binary format - `contains` reads text, "
                           f"so it could never pass")
        why += [w for w in map(_bad_regex, t.assertions + [c for _, cs, _ in specs
                                                          for c in cs]) if w]
        if t.judge is not None:
            argv = judge_argv(t.judge, skill_root, ".")
            if argv is None:
                why.append("`judge` is not a non-empty list of strings - write it as argv, "
                           "e.g. [\"{python}\", \"{skill}/evals/check.py\"]")
            else:
                # a script the judge names inside the skill has to be there, or every
                # run of the case fails on both arms for a reason that is not the skill
                for arg in t.judge:
                    if arg.startswith("{skill}/"):
                        rel = arg[len("{skill}/"):]
                        if not os.path.isfile(os.path.join(base, rel)):
                            why.append(f"judge script `{rel}` does not exist")
        if t.process is not None:
            if not isinstance(t.process, list) or not t.process:
                why.append("`process` is not a non-empty list of items")
            else:
                why += [p for p in map(process_problem, t.process) if p]
        if why:
            out.append((t.id, "unrunnable", "; ".join(why)))
        elif not t.graded and not t.process_items:
            extra = (" - its skill-creator `expectations` are graded by a model there and "
                     "are not read here" if t.expectations else "")
            out.append((t.id, "ungraded", "no `assertions`, `outputs`, `judge` or `process` "
                                          f"- nothing decides whether it passed{extra}"))
        if t.legacy_outputs:
            names = ", ".join(f"`{f}`" for f in t.legacy_outputs)
            out.append((t.id, "legacy",
                        f"`files` entry {names} is not a file in the skill, so it is graded "
                        f"as an output the run must create - the old meaning. In "
                        f"skill-creator's format `files` are inputs: move outputs to "
                        f"`outputs`, and if an input was meant, it is missing"))
    return out


def load(skill_root, path=None):
    """(tasks, problem) - the task set, or why there is none to run."""
    full = path or os.path.join(skill_root, CASES)
    if not os.path.isfile(full):
        return [], (f"no {CASES} - `sqs.py evals <skill> --init` scaffolds one, and it "
                    f"has to hold real tasks before a runtime run means anything")
    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return [], f"{CASES} does not parse: {e}"
    raw = data.get("evals") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        return [], f"{CASES} carries no cases"
    tasks = [Task(r, i + 1, skill_root) for i, r in enumerate(raw) if isinstance(r, dict)]
    tasks = [t for t in tasks if t.prompt]
    if not tasks:
        return [], f"{CASES}: no case carries a `prompt`"
    return tasks, ""
