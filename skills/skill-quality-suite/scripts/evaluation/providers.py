#!/usr/bin/env python3
"""The agents this suite can drive, and what one run of one comes back as.

Everything else in the suite reads text. This layer runs an agent, which makes it the
one part that costs money, takes minutes and needs something installed. It is
therefore opt-in everywhere, and absent by default: `Provider.available()` returns a
reason rather than raising, so a machine with no agent on it gets a sentence instead
of a traceback.

The envelope a headless run prints is not part of any specification, and it differs
between clients and versions. So nothing here indexes into a fixed shape: the parser
walks whatever came back looking for what it knows, and **what it does not find stays
None**. A run whose token count is None reports "not reported by the provider", never
zero - a zero is a measurement, and inventing one is how a comparison quietly starts
lying about cost.
"""
import json
import os
import shutil
import subprocess
import time


class Run:
    """One task, run once, by one agent.

    `ok` is about the run, not about the answer: a run that crashed cannot be scored
    for or against the skill, and mixing the two is how a broken provider looks like a
    bad skill.
    """

    __slots__ = ("ok", "error", "text", "tools", "skills", "duration_s",
                 "tokens_in", "tokens_out", "cost_usd", "turns", "raw", "workdir")

    def __init__(self, ok=True, error=None, text="", tools=None, skills=None,
                 duration_s=None, tokens_in=None, tokens_out=None, cost_usd=None,
                 turns=None, raw=None, workdir=None):
        self.ok = ok
        self.error = error
        self.text = text
        self.tools = tools or []            # [(tool name, input as text)]
        self.skills = skills or []          # skills the transcript shows loading
        self.duration_s = duration_s
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost_usd = cost_usd
        self.turns = turns
        self.raw = raw
        self.workdir = workdir

    @property
    def tokens(self):
        if self.tokens_in is None and self.tokens_out is None:
            return None
        return (self.tokens_in or 0) + (self.tokens_out or 0)

    def as_dict(self):
        return {"ok": self.ok, "error": self.error, "text": self.text[:4000],
                "tools": self.tools, "skills": self.skills, "duration_s": self.duration_s,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "cost_usd": self.cost_usd, "turns": self.turns}


def walk(node, want, out):
    """Collect every value stored under any of `want`, at any depth.

    A tolerant reader for an envelope nobody promised to keep stable. The alternative -
    indexing into a shape - fails silently on the next version: the field is absent, the
    value reads as missing, and a report of zeros looks exactly like a cheap run.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k in want and not isinstance(v, (dict, list)):
                out.setdefault(k, []).append(v)
            walk(v, want, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, want, out)


# Every tool a routing decision can need, and nothing else. `Skill` is the observation
# itself; the other three are how a skill's first steps read the files it points at.
# Nothing here can change anything on the machine.
TRIGGER_TOOLS = ("Skill", "Read", "Glob", "Grep")
# The `result` subtype a run carries when its `--max-budget-usd` ceiling ended it. That
# is the cap doing its job, not a failure, and the transcript in front of it is complete.
BUDGET_SUBTYPE = "error_max_budget_usd"


def _terminal(stdout):
    """The terminal `result` event of a stream-json transcript, or None.

    What separates "the session ended and here is what happened" from "the process died
    before saying anything" - which is what the exit code alone used to be asked to
    decide, and got wrong for every capped run.
    """
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{") or '"result"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            return event
    return None


# How much of one tool call's input is kept. `process` matchers read it, and at 300 a
# matcher on a path that came after a long `old_string`, or a command at the end of a
# heredoc, could never match - a silent false fail. 2000 covers a command and its
# arguments; long file content is `outputs.contains`' to check, not a matcher's.
TOOL_INPUT_CAP = 2000


def collect_tools(node, tools, skills):
    """Tool calls and skill loads, from anywhere in the transcript."""
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and node.get("name"):
            name = node["name"]
            arg = node.get("input") or {}
            tools.append((name, json.dumps(arg, ensure_ascii=False)[:TOOL_INPUT_CAP]))
            if name in ("Skill", "skill"):
                loaded = arg.get("skill") or arg.get("name")
                if loaded:
                    skills.append(loaded)
        for v in node.values():
            collect_tools(v, tools, skills)
    elif isinstance(node, list):
        for v in node:
            collect_tools(v, tools, skills)


def loaded(run, skill_name):
    """Whether the transcript shows this skill being loaded.

    Two spellings. A skill in a skills directory is called by its own name; the treatment
    arm hands the skill over inside a one-skill plugin, and a plugin's skills are called
    with the plugin's name in front (`sqs-under-test:ledger-lite`). Which one a given
    client prints has not been watched on a live treatment run, so both count.
    """
    return any(s == skill_name or s.endswith(":" + skill_name) for s in run.skills)


class Provider:
    """One way to run a task. Subclasses fill in `available` and `run`."""

    name = "none"
    title = "no agent"
    # Whether this provider can run a task with a named skill present and absent. A
    # provider that cannot is still usable for output quality, and its reports say so
    # instead of calling the comparison a baseline.
    isolates_skills = False

    def available(self):
        return False, "no provider selected"

    def run(self, prompt, skill=None, cwd=None, timeout=300, model=None, workdir=None,
            bare=True, max_budget_usd=None):
        """One task, once.

        `skill` loads exactly that skill and nothing else. `bare=False` runs in the
        machine's real environment instead - which is what a trigger measurement needs,
        because the question there is whether this description wins against the
        neighbours it actually competes with.

        `max_budget_usd` is a ceiling on one run, for the pass that only needs the first
        decision and not the work that follows it. A provider with no way to cap a run
        ignores it.
        """
        raise NotImplementedError


class ClaudeCodeProvider(Provider):
    """The Claude Code CLI in headless mode.

    Isolation rests on two documented flags. `--bare` skips auto-discovery of hooks,
    skills, commands, subagents, plugins and memory, which is what makes a baseline a
    baseline: without it the skill under test is installed on the machine doing the
    measuring, and both sides of the comparison can reach it. `--plugin-dir` then
    loads exactly one plugin from a directory, so the treatment side gets the skill
    under test and nothing else.

    Source: https://code.claude.com/docs/en/cli-reference
    """

    name = "claude"
    title = "Claude Code (headless)"
    isolates_skills = True

    def __init__(self, binary=None):
        self.binary = binary or os.environ.get("SQS_CLAUDE_BIN") or "claude"

    def available(self):
        if not shutil.which(self.binary):
            return False, (f"`{self.binary}` is not on PATH - install the Claude Code CLI, "
                           f"or point SQS_CLAUDE_BIN at it")
        return True, ""

    def plugin_dir(self, skill, workdir):
        """A one-skill plugin, so the treatment side loads this skill and nothing else."""
        plug = os.path.join(workdir, "sqs-plugin")
        target = os.path.join(plug, "skills", skill.name or skill.folder)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(skill.root, target,
                        ignore=shutil.ignore_patterns("__pycache__", ".git", "evals"))
        os.makedirs(os.path.join(plug, ".claude-plugin"), exist_ok=True)
        with open(os.path.join(plug, ".claude-plugin", "plugin.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"name": "sqs-under-test", "version": "0.0.0",
                       "description": "the skill under test, isolated for one run"}, f)
        return plug

    def run(self, prompt, skill=None, cwd=None, timeout=300, model=None, workdir=None,
            bare=True, max_budget_usd=None):
        cmd = [self.binary, "-p", prompt,
               "--output-format", "stream-json", "--verbose",
               "--no-session-persistence"]
        # A trigger measurement wants the real tree, so the skill competes with its
        # neighbours; a task measurement wants nothing but the skill under test.
        cmd += ["--bare"] if bare else []
        if bare:
            cmd += ["--permission-mode", "bypassPermissions"]
        else:
            # NOT plan mode, which this ran in until it was watched doing it: in plan
            # mode the model writes a plan and never calls the `Skill` tool at all.
            # Three runs against a real 29-skill tree produced zero skill loads and
            # prose about which skill would suit - so every query would have read as
            # "did not fire", recall would have come out at zero for every description,
            # and the whole trigger pass would have measured nothing while looking
            # exactly like a skill that never triggers.
            #
            # Letting it act has to be made safe, and the safety is an ALLOW-list, not
            # a deny-list: a list of tools to forbid is only ever as complete as the day
            # it was written, and these four are all a routing decision can need. With
            # no permission mode set, a tool outside the list needs an approval nobody
            # is there to give, so it is refused.
            #
            # `--restricted` looked like the better lever and was rejected after being
            # watched: it also ignores user and project settings, and the run then loads
            # the bundled skills instead of the tree under test - measured side by side,
            # the same prompt reached `konspekt` without it and a built-in skill with it.
            # A trigger pass that cannot see the skill it is measuring is worse than one
            # that costs more.
            #
            # `--strict-mcp-config` with no `--mcp-config` beside it leaves no MCP server
            # running, which is the hole the allow-list cannot close on its own: an MCP
            # server's tools are named by the server, so they cannot be enumerated here.
            cmd += ["--strict-mcp-config", "--allowed-tools"] + list(TRIGGER_TOOLS)
        # The routing decision happens in the first turn or two; everything after it is
        # the skill doing its job, which a trigger measurement pays for and throws away.
        # One uncapped run of one query cost four times a capped one.
        if max_budget_usd:
            cmd += ["--max-budget-usd", str(max_budget_usd)]
        if model:
            cmd += ["--model", model]
        if skill is not None:
            cmd += ["--plugin-dir", self.plugin_dir(skill, workdir or cwd or ".")]
        started = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, cwd=cwd)
        except subprocess.TimeoutExpired:
            return Run(ok=False, error=f"timed out after {timeout}s",
                       duration_s=time.time() - started, workdir=cwd)
        except OSError as e:
            return Run(ok=False, error=str(e), workdir=cwd)
        elapsed = time.time() - started
        # A non-zero exit is not on its own a failed run: `--max-budget-usd` ends a run
        # by exhausting its cap and exits 1 with the transcript complete behind it.
        # Reading the exit code alone turned every capped run into an unusable one, and
        # a confusion matrix of nothing but `unusable` reads exactly like a description
        # that never fires. The transcript is the evidence: a `result` event means the
        # session finished and there is something to measure.
        terminal = _terminal(r.stdout)
        if r.returncode != 0 and terminal is None:
            return Run(ok=False, error=f"exit {r.returncode}: {(r.stderr or '').strip()[:300]}",
                       duration_s=elapsed, workdir=cwd)
        return self.parse(r.stdout, elapsed, cwd)

    def parse(self, stdout, elapsed, cwd=None):
        """A stream of JSON objects, read for what it happens to carry."""
        events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        if not events:
            try:
                events = [json.loads(stdout)]
            except ValueError:
                return Run(ok=bool(stdout.strip()), text=stdout.strip(), duration_s=elapsed,
                           error=None if stdout.strip() else "the provider printed nothing",
                           workdir=cwd)
        tools, skills = [], []
        collect_tools(events, tools, skills)
        found = {}
        walk(events, {"total_cost_usd", "cost_usd", "input_tokens", "output_tokens",
                      "num_turns", "duration_ms", "result", "is_error"}, found)

        def last(key, cast=None):
            vals = found.get(key)
            if not vals:
                return None
            v = vals[-1]
            try:
                return cast(v) if cast else v
            except (TypeError, ValueError):
                return None

        text = last("result") or ""
        if not isinstance(text, str):
            text = str(text)
        ms = last("duration_ms", float)
        # A run stopped by its own spend ceiling reports `is_error` like any other early
        # end, and reading that alone made every capped run unusable - a confusion matrix
        # of nothing but `unusable` looks exactly like a description that never fires,
        # which is the failure this whole pass exists to tell apart from a real one. The
        # subtype is what distinguishes them, and the transcript behind it is complete.
        terminal = _terminal(stdout) or {}
        capped = terminal.get("subtype") == BUDGET_SUBTYPE
        failed = bool(last("is_error")) and not capped
        return Run(
            ok=not failed,
            error="the provider reported an error result" if failed else None,
            text=text,
            tools=tools,
            skills=skills,
            duration_s=(ms / 1000.0) if ms is not None else elapsed,
            tokens_in=sum(v for v in found.get("input_tokens", []) if isinstance(v, int)) or None,
            tokens_out=sum(v for v in found.get("output_tokens", []) if isinstance(v, int)) or None,
            cost_usd=last("total_cost_usd", float) or last("cost_usd", float),
            turns=last("num_turns", int),
            workdir=cwd,
        )


class FakeProvider(Provider):
    """A scripted agent, for testing the machinery rather than a skill.

    The reports, the confusion matrix and the regression diff are arithmetic over what
    an agent returned, and arithmetic deserves tests that do not cost money or need a
    model installed. This provider replays a script instead of thinking:

        SQS_FAKE_RUNS=runs.json sqs.py eval ./my-skill --all --provider fake

        {"default": {"text": "done", "tools": [["Read", "{}"]]},
         "rules": [{"contains": "receipt", "with_skill": true, "bare": true,
                    "run": {"text": "logged 12.40 on 2026-09-18", "cost_usd": 0.01}}]}

    A rule matches on a substring of the prompt and, optionally, on which arm of the
    comparison is running. First match wins; `default` covers the rest.

    It measures nothing about any skill, and every report it produces says `fake` in
    the provider line so a scripted number can never be mistaken for a measured one.
    """

    name = "fake"
    title = "scripted (testing only)"
    isolates_skills = True

    def __init__(self, script_path=None):
        self.path = script_path or os.environ.get("SQS_FAKE_RUNS")
        self.script = {}

    def available(self):
        if not self.path:
            return False, ("the fake provider replays a script - point SQS_FAKE_RUNS at a "
                           "JSON file. It exists to test this suite, not to measure a skill")
        if not os.path.isfile(self.path):
            return False, f"no script at {self.path}"
        try:
            with open(self.path, encoding="utf-8") as f:
                self.script = json.load(f)
        except (OSError, ValueError) as e:
            return False, f"{self.path}: {e}"
        return True, ""

    def run(self, prompt, skill=None, cwd=None, timeout=300, model=None, workdir=None,
            bare=True, max_budget_usd=None):
        if not self.script:
            self.available()
        spec = dict(self.script.get("default") or {})
        for rule in self.script.get("rules") or []:
            if rule.get("contains") and rule["contains"].lower() not in prompt.lower():
                continue
            if "with_skill" in rule and bool(rule["with_skill"]) != (skill is not None):
                continue
            # a trigger run and a task run both arrive with no skill attached; `bare`
            # is what tells them apart, so a script can answer them differently
            if "bare" in rule and bool(rule["bare"]) != bool(bare):
                continue
            spec.update(rule.get("run") or {})
            break
        if spec.get("error"):
            return Run(ok=False, error=spec["error"], duration_s=spec.get("duration_s"),
                       workdir=cwd)
        # `creates` names files the scripted run pretends the agent wrote, and the
        # script is a file on disk like any other. A path that climbs out of the run's
        # working directory is not a test case, it is the fake provider writing
        # wherever the script says - so the write stays inside `cwd` or does not happen.
        # An entry is a path, or {"path", "content"} when the grader reads what is inside.
        base = os.path.realpath(cwd or ".")
        for entry in spec.get("creates") or []:
            rel, body = ((entry.get("path"), entry.get("content", ""))
                         if isinstance(entry, dict)
                         else (entry, "written by the fake provider" + chr(10)))
            full = os.path.realpath(os.path.join(base, rel))
            if full != base and not full.startswith(base + os.sep):
                raise ValueError(f"`creates` path escapes the run directory: {rel!r}")
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(body)
        skills = spec.get("skills")
        if skills is None and skill is not None:
            skills = [skill.name or skill.folder]
        return Run(ok=True, text=spec.get("text", ""),
                   tools=[tuple(t) for t in (spec.get("tools") or [])],
                   skills=skills or [],
                   duration_s=spec.get("duration_s"), tokens_in=spec.get("tokens_in"),
                   tokens_out=spec.get("tokens_out"), cost_usd=spec.get("cost_usd"),
                   turns=spec.get("turns"), workdir=cwd)


PROVIDERS = {p.name: p for p in (ClaudeCodeProvider, FakeProvider)}


def get(name):
    """(provider, reason it cannot run) - never raises, so a caller can report it."""
    cls = PROVIDERS.get(name)
    if not cls:
        return None, (f"no provider `{name}` - this build carries "
                      f"{', '.join(sorted(PROVIDERS))}")
    provider = cls()
    ok, why = provider.available()
    return provider, ("" if ok else why)
