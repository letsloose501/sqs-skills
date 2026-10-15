#!/usr/bin/env python3
"""Does the skill actually make the agent better at the work?

Every other module reasons about the text. This one runs the task twice - once with
the skill and once without it - and reports what changed. That is the only question in
the suite whose answer can be "the skill is beautifully written and changes nothing",
and it is the question a skill exists to answer yes to.

    task
     ├── baseline   the agent with no skills at all      (`claude --bare`)
     └── treatment  the agent with this one skill loaded (`--plugin-dir`)
                    ↓
              the same grading applied to both

What it measures, per side: how many graded tasks came out right, how many runs failed
outright, how many tool calls and turns it took, how long, how many tokens and how much
it cost, and whether following the skill made the agent do something destructive or
reach for a tool the task forbade.

What it does not measure: whether the answer reads well. That is a judgement, it stays
one, and the report says `ungraded` rather than guessing.

Nothing here runs by default. It costs money and minutes, it needs an agent installed,
and `sqs.py eval --runtime` is the only way in.
"""
import os
import shutil
import statistics
import tempfile

from . import providers
from . import tasks as taskmod


def mean(values):
    """The average of what was actually reported, or None when nothing was.

    None and 0 are different answers and the difference matters: a provider that never
    reported a token count must not average out as a free run.
    """
    vals = [v for v in values if isinstance(v, (int, float))]
    return statistics.fmean(vals) if vals else None


def total(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals) if vals else None


class Side:
    """One arm of the comparison, aggregated over every run of every task.

    The treatment arm is built with the name of the skill under test, and on that arm a
    passed task counts only when the transcript shows the skill loading. Without that
    gate the arm can win a task the model would have won anyway, with the skill sitting
    unread in the plugin, and the delta is then credited to a skill that did nothing.
    The uncredited passes are still counted, as `passed_without_skill`: they are the
    model's own ability, and a reader needs that number to read the delta at all.
    """

    def __init__(self, label, skill_name=None):
        self.label = label
        self.skill_name = skill_name
        self.runs = []                       # [(task, run, grade)]

    def add(self, task, run, grade):
        self.runs.append((task, run, grade))

    @property
    def usable(self):
        return [(t, r, g) for t, r, g in self.runs if r.ok]

    def credited(self, run, grade):
        return grade.passed and (self.skill_name is None
                                 or providers.loaded(run, self.skill_name))

    def credited_process(self, run, grade):
        """The same gate on the other half: a procedure the model followed with the skill
        unread is the model's habit, not the skill's instruction."""
        return grade.process_passed and (self.skill_name is None
                                         or providers.loaded(run, self.skill_name))

    def metrics(self):
        usable = self.usable
        graded = [(t, r, g) for t, r, g in usable if g.graded]
        # process numbers are over the runs whose case carries `process` - a set where
        # half the cases say nothing about procedure must not read as half followed
        proc = [(t, r, g) for t, r, g in usable if g.process_graded]
        both = [(t, r, g) for t, r, g in proc if g.graded]
        gated = self.skill_name is not None
        m = {
            "runs": len(self.runs),
            "failed_runs": len(self.runs) - len(usable),
            "failure_rate": (len(self.runs) - len(usable)) / len(self.runs) if self.runs else None,
            "graded_runs": len(graded),
            "ungraded_runs": len(usable) - len(graded),
            "success_rate": (sum(1 for _, r, g in graded if self.credited(r, g)) / len(graded)
                             if graded else None),
            # strict: every process item met. The paper's strict score is a product of
            # item passes, and this is the same number - 1 only if all of them held.
            "process_rate": (sum(1 for _, r, g in proc if self.credited_process(r, g))
                             / len(proc) if proc else None),
            # loose: the mean share of items met. Descriptive, like `tool_calls`, and not
            # gated on the skill loading - it says how far the run got, not whose it was.
            "process_item_rate": mean([g.process_share for _, _, g in proc]),
            # strict on both halves at once: the result is right and the way there was
            "strict_rate": (sum(1 for _, r, g in both
                                if self.credited(r, g) and self.credited_process(r, g))
                            / len(both) if both else None),
            "process_graded_runs": len(proc),
            "skill_loaded_runs": (sum(1 for _, r, _ in usable
                                      if providers.loaded(r, self.skill_name))
                                  if gated else None),
            "passed_without_skill": (sum(1 for _, r, g in graded
                                         if g.passed and not self.credited(r, g))
                                     if gated else None),
            "tool_calls": mean([len(r.tools) for _, r, _ in usable]),
            "turns": mean([r.turns for _, r, _ in usable]),
            "duration_s": mean([r.duration_s for _, r, _ in usable]),
            "tokens": mean([r.tokens for _, r, _ in usable]),
            "cost_usd": total([r.cost_usd for _, r, _ in usable]),
            "unnecessary_tool_calls": sum(g.unnecessary for _, _, g in usable),
            "forbidden_tool_uses": sum(len(g.forbidden) for _, _, g in usable),
            "safety_violations": sum(len(g.unsafe) for _, _, g in usable),
        }
        return m

    def per_task(self):
        out = {}
        for t, r, g in self.runs:
            row = out.setdefault(t.id, {"runs": 0, "ok": 0, "passed": 0, "graded": g.graded,
                                        "process_passed": 0})
            row["runs"] += 1
            row["ok"] += int(r.ok)
            row["passed"] += int(self.credited(r, g))
            row["process_passed"] += int(r.ok and self.credited_process(r, g))
        for t_id, row in out.items():
            row["success_rate"] = (row["passed"] / row["ok"]) if row["ok"] else None
            has_process = any(t.id == t_id and t.process_items for t, _, _ in self.runs)
            row["process_rate"] = ((row["process_passed"] / row["ok"])
                                   if row["ok"] and has_process else None)
        return out


def prepare_workdir(task, skill, parent):
    work = tempfile.mkdtemp(prefix="sqs-run-", dir=parent)
    for rel in task.fixtures:
        src = os.path.join(skill.root, rel)
        if not os.path.exists(src):
            continue
        dst = os.path.join(work, os.path.basename(rel))
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
    return work


# What a runtime run would let the skill do to the machine. The treatment arm runs the
# agent with every permission check bypassed - the CLI's own help recommends that "only
# for sandboxes with no internet access" - and the only isolation is a fresh working
# directory. So a skill that can reach the network, spawn a process, run commands on
# load, hide what it runs, or carries text aimed at the agent gets to do all of it here.
# Reading environment variables (CB003) is not on the list: on its own it reaches
# nothing, and with a way out it is already here as CB001 or CB002.
HAZARDS = ("CB001", "CB002", "CB004", "CB005",
           "SE002", "SE003", "SE004", "SE005", "SE008")


def hazards(skill):
    """The findings that make running this skill unattended a decision, not a default.

    Read from the engines directly, not through `check`: an `sqs-allow` waiver or a
    config switch is written by the same author whose skill is in question, and a gate
    that its subject can switch off is not a gate.
    """
    import capabilities                                            # noqa: PLC0415
    import security                                                # noqa: PLC0415
    return [f for f in capabilities.check(skill) + security.check(skill)
            if f.code in HAZARDS]


def evaluate(skill, provider, runs=1, model=None, with_baseline=True, task_filter=None,
             on_event=None, trusted=False):
    """Run the task set on both sides. Returns (report dict, problem).

    Every run gets its own empty working directory, so an `outputs:` assertion is about
    what this run created and not about what the last one left behind.

    `trusted` is `--trust-target`: the person says the skill is theirs or has been read.
    Without it a skill with any of `HAZARDS` is refused before anything runs.
    """
    if not trusted:
        found = hazards(skill)
        if found:
            head = "; ".join(f"{f.code} {f.where}:{f.line} {f.msg}" for f in found[:3])
            more = f" and {len(found) - 3} more" if len(found) > 3 else ""
            return None, (f"{len(found)} finding(s) say this skill can act on the machine - "
                          f"{head}{more}. The runtime pass runs it with permission checks "
                          f"bypassed, so nothing was run. Read them; if the skill is yours "
                          f"or you have read it, pass --trust-target")
    task_list, problem = taskmod.load(skill.root)
    if problem:
        return None, problem
    if task_filter:
        task_list = [t for t in task_list if t.id in task_filter]
        if not task_list:
            return None, f"no task matches {', '.join(sorted(task_filter))}"

    # The pre-flight gate: nothing is spent on a set that cannot produce a measurement.
    # One case that cannot run as written stops the pass, because the alternative is a
    # report that mixes measured cases with a skipped fixture or a grader crash halfway
    # through. An ungraded case alone does not - it still says something about cost and
    # tool use - but a set where every case is ungraded measures nothing at all.
    blocked = taskmod.preflight(skill.root, task_list)
    unrunnable = [(i, why) for i, kind, why in blocked if kind == "unrunnable"]
    if unrunnable:
        head = "; ".join(f"{i}: {why}" for i, why in unrunnable[:3])
        more = f" and {len(unrunnable) - 3} more" if len(unrunnable) > 3 else ""
        return None, (f"{len(unrunnable)} case(s) cannot run as written, nothing was "
                      f"spent - {head}{more}")
    if len({i for i, kind, _ in blocked if kind == "ungraded"}) == len(task_list):
        return None, ("no case carries `assertions`, `outputs`, `judge` or `process`, so no "
                      "run could pass or fail - nothing was spent")
    # A judge is a program from the skill, run on this machine after every run; reading a
    # skill is not a reason to execute one - the rule `EV006` applies to a tree's runner.
    judged = [t.id for t in task_list if t.judge is not None]
    if judged and not trusted:
        return None, (f"{len(judged)} case(s) are graded by a judge program from the skill "
                      f"({', '.join(judged[:3])}), which would run on this machine - nothing "
                      f"was run. If the skill is yours or you have read the judge, pass "
                      f"--trust-target")

    sides = {"treatment": Side("treatment", skill.name or skill.folder)}
    if with_baseline:
        sides["baseline"] = Side("baseline")

    with tempfile.TemporaryDirectory(prefix="sqs-eval-") as parent:
        for task in task_list:
            for attempt in range(runs):
                for name, side in sides.items():
                    work = prepare_workdir(task, skill, parent)
                    if on_event:
                        on_event(task, name, attempt + 1, runs)
                    run = provider.run(task.prompt,
                                       skill=skill if name == "treatment" else None,
                                       cwd=work, timeout=task.timeout, model=model,
                                       workdir=work)
                    side.add(task, run, taskmod.grade(task, run, skill.root))

    report = {
        "skill": skill.name or skill.folder,
        "provider": provider.name,
        "model": model,
        "runs_per_task": runs,
        "isolated": provider.isolates_skills,
        "tasks": [t.id for t in task_list],
        "ungraded_tasks": [t.id for t in task_list if not t.graded and not t.process_items],
        "sides": {name: side.metrics() for name, side in sides.items()},
        "per_task": {name: side.per_task() for name, side in sides.items()},
        "failures": [
            {"side": name, "task": t.id, "error": r.error,
             # the reason travels with the check: "file:x.csv 12.40" alone does not say
             # whether the file was missing, unreadable, or there with the wrong rows
             "failed_checks": ([f"{w} ({d})" if d else w for w, ok, d in g.checks if not ok]
                               + [f"step:{i} ({d})" if d else f"step:{i}"
                                  for i, ok, d in g.process if not ok])}
            for name, side in sides.items() for t, r, g in side.runs
            if not r.ok or (g.graded and not g.passed)
            or (g.process_graded and not g.process_passed)
        ],
    }
    return report, ""


# ---- rendering -------------------------------------------------------------

ROWS = [
    ("success_rate", "task success", "pct"),
    ("process_rate", "process followed", "pct"),
    ("process_item_rate", "process items met", "pct"),
    ("strict_rate", "strict (both)", "pct"),
    ("skill_loaded_runs", "runs that loaded it", "int"),
    ("failure_rate", "runs that failed", "pct"),
    ("tool_calls", "tool calls", "num"),
    ("turns", "turns", "num"),
    ("duration_s", "seconds", "num"),
    ("tokens", "tokens", "num"),
    ("cost_usd", "cost USD", "money"),
    ("unnecessary_tool_calls", "calls over budget", "int"),
    ("forbidden_tool_uses", "forbidden tools used", "int"),
    ("safety_violations", "safety violations", "int"),
]
OPTIONAL_ROWS = {"process_rate", "process_item_rate", "strict_rate"}


def fmt(value, kind):
    if value is None:
        return "n/a"
    if kind == "pct":
        return f"{value:.0%}"
    if kind == "money":
        return f"{value:.4f}"
    if kind == "int":
        return str(int(value))
    return f"{value:.1f}"


def render(report):
    sides = report["sides"]
    have_baseline = "baseline" in sides
    lines = [f"Runtime evaluation: {report['skill']}",
             f"  provider {report['provider']}"
             + (f" · model {report['model']}" if report.get("model") else "")
             + f" · {report['runs_per_task']} run(s) per task"
             + f" · {len(report['tasks'])} task(s)", ""]
    if not report.get("isolated"):
        lines.append("  The provider cannot run a task with this skill absent, so the "
                     "baseline column is not")
        lines.append("  a baseline. Read the treatment column alone.")
        lines.append("")

    head = f"  {'':<24}{'treatment':>12}"
    if have_baseline:
        head += f"{'baseline':>12}{'delta':>12}"
    lines += [head, "  " + "-" * (24 + 12 * (3 if have_baseline else 1))]
    for key, label, kind in ROWS:
        # three rows of `n/a` on every set written before `process` existed would read
        # as something measured and missing; with no case carrying it, they are left out
        if key in OPTIONAL_ROWS and all(s.get(key) is None for s in sides.values()):
            continue
        t = sides["treatment"].get(key)
        row = f"  {label:<24}{fmt(t, kind):>12}"
        if have_baseline:
            b = sides["baseline"].get(key)
            row += f"{fmt(b, kind):>12}"
            if isinstance(t, (int, float)) and isinstance(b, (int, float)):
                d = t - b
                sign = "+" if d > 0 else ""
                row += f"{sign + fmt(abs(d) if kind == 'pct' else d, kind):>12}"
            else:
                row += f"{'n/a':>12}"
        lines.append(row)

    treat = sides["treatment"]
    if treat.get("passed_without_skill"):
        lines += ["", f"  {treat['passed_without_skill']} treatment run(s) passed without "
                      f"loading the skill and were not counted",
                  "  as success: that is the model's own ability, not the skill's."]
    if treat.get("skill_loaded_runs") == 0 and treat.get("runs"):
        lines += ["", "  The skill loaded in no treatment run. This column measures the "
                      "model alone."]

    ungraded = report.get("ungraded_tasks") or []
    if ungraded:
        lines += ["", f"  {len(ungraded)} task(s) carry no assertions and no expected outputs "
                      f"({', '.join(ungraded[:4])}):",
                  "  they ran and were not scored. A task nobody said the success "
                  "condition for cannot pass."]

    failures = report.get("failures") or []
    if failures:
        lines += ["", "  what went wrong:"]
        for f in failures[:12]:
            what = f["error"] or ("failed: " + ", ".join(f["failed_checks"][:3]))
            lines.append(f"    {f['side']:<10}{f['task']:<14}{what[:70]}")
        if len(failures) > 12:
            lines.append(f"    ... and {len(failures) - 12} more")
    return "\n".join(lines)
