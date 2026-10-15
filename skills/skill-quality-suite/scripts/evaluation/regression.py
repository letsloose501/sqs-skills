#!/usr/bin/env python3
"""Did the last edit to this skill make it worse?

An evaluation you run once is a number. An evaluation you can compare is a gate. This
module stores a run under a label and diffs two of them - so "I shortened the
description" can be answered with "trigger recall went 0.94 → 0.81 and these three
cases are the ones that stopped firing", instead of a feeling.

    sqs.py eval ./my-skill --runtime --save v1
    ... edit the skill ...
    sqs.py eval ./my-skill --runtime --save v2
    sqs.py eval ./my-skill --compare v1 v2

Runs live in `.sqs/evals/<skill>/<label>.json` beside the skills, out of the skill
itself: an evaluation result is a measurement of a version, not a file that should
ship inside it.

Two kinds of worse, deliberately kept apart. **Quality** - task success, trigger
precision and recall - fails the gate: the skill stopped doing its job. **Cost** -
tokens, money, wall time, tool calls - is reported and does not fail by default,
because a skill that got 18% more expensive and 20% more reliable is a trade somebody
has to look at, not a build to break. `--fail-on-cost` moves the line when a budget
depends on it.
"""
import datetime
import json
import os
import random

STORE = os.path.join(".sqs", "evals")
# How much worse a ratio has to get before it counts, when the run cannot say how noisy
# it is: task success, and trigger runs of one run per query. A guess, and named as one -
# trigger runs with repeats measure their own noise instead (`noise_drop`).
QUALITY_DROP = 0.05
COST_RISE = 0.15
# The trigger gate: a drop counts when it is larger than the runs' own variation in all
# but this share of resampled draws - a one-sided 95% test.
NOISE_LEVEL = 0.05
NOISE_DRAWS = 2000
THRESHOLD = 0.5                      # the same cut `triggers.confusion` fires at

QUALITY = [
    ("runtime", ("sides", "treatment", "success_rate"), "task success"),
    # Process fails the gate like completion does: a skill whose answers still come out
    # right after an edit, while the steps it prescribes stopped being followed, got
    # worse at its job. A run saved before `process` existed has neither key, `dig`
    # returns None and the row is skipped rather than read as a fall to zero.
    ("runtime", ("sides", "treatment", "process_rate"), "process followed"),
    ("runtime", ("sides", "treatment", "strict_rate"), "strict success"),
    ("trigger", ("sets", "validation", "metrics", "precision"), "trigger precision"),
    ("trigger", ("sets", "validation", "metrics", "recall"), "trigger recall"),
    ("trigger", ("sets", "all", "metrics", "precision"), "trigger precision"),
    ("trigger", ("sets", "all", "metrics", "recall"), "trigger recall"),
]
COST = [
    ("runtime", ("sides", "treatment", "tokens"), "token usage"),
    ("runtime", ("sides", "treatment", "cost_usd"), "cost"),
    ("runtime", ("sides", "treatment", "duration_s"), "wall time"),
    ("runtime", ("sides", "treatment", "tool_calls"), "tool calls"),
    ("trigger", ("cost_usd",), "trigger pass cost"),
]


def dig(payload, path):
    node = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, (int, float)) else None


def store_dir(root, skill_name):
    return os.path.join(root, STORE, skill_name)


def save(root, skill_name, label, payload):
    d = store_dir(root, skill_name)
    os.makedirs(d, exist_ok=True)
    payload = dict(payload, saved=datetime.datetime.now().isoformat(timespec="seconds"),
                   label=label)
    path = os.path.join(d, f"{label}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def load(root, skill_name, label):
    path = os.path.join(store_dir(root, skill_name), f"{label}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def labels(root, skill_name):
    d = store_dir(root, skill_name)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def affected_tasks(before, after):
    """Task ids whose success rate or process rate fell between the two runs.

    A process drop is labelled `<id> (process)`: the same task can keep its answer and
    lose its procedure, and the report has to say which half moved.
    """
    out = []
    b = ((before.get("runtime") or {}).get("per_task") or {}).get("treatment") or {}
    a = ((after.get("runtime") or {}).get("per_task") or {}).get("treatment") or {}
    for task_id, row in sorted(a.items()):
        for key, label in (("success_rate", task_id), ("process_rate", f"{task_id} (process)")):
            old = (b.get(task_id) or {}).get(key)
            new = row.get(key)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and new < old:
                out.append((label, old, new))
    return out


def affected_queries(before, after):
    """Trigger cases whose verdict flipped the wrong way."""
    def index(payload):
        out = {}
        for block in ((payload.get("trigger") or {}).get("sets") or {}).values():
            for case in block.get("cases", []):
                out[case["prompt"]] = case
        return out
    old, new = index(before), index(after)
    flipped = []
    for prompt, case in new.items():
        was = old.get(prompt)
        if not was or case["rate"] is None or was["rate"] is None:
            continue
        want = case["expected"] == "trigger"
        before_ok = (was["rate"] > 0.5) == want
        after_ok = (case["rate"] > 0.5) == want
        if before_ok and not after_ok:
            flipped.append((prompt, was["rate"], case["rate"], case["expected"]))
    return flipped


def _trigger_cases(payload, set_label):
    block = (((payload.get("trigger") or {}).get("sets") or {}).get(set_label) or {})
    return [c for c in block.get("cases", []) if c.get("rate") is not None and c.get("runs")]


def _ratio(cases, rates, metric):
    tp = fp = fn = 0
    for c, rate in zip(cases, rates):
        fired, want = rate > THRESHOLD, c["expected"] == "trigger"
        tp += fired and want
        fp += fired and not want
        fn += (not fired) and want
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if metric == "precision":
        return precision
    if metric == "recall":
        return recall
    if precision is None or recall is None:
        return None
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _resample(cases, rng):
    """One redraw of every query's firing rate, from what its own runs showed.

    A query that fired h times in n runs is redrawn as n runs of a rate drawn from
    Beta(h + 1/2, n - h + 1/2) - the runs' own uncertainty, smoothed so that three
    identical runs are not read as a rate of exactly 0 or 1. Without the smoothing a
    set where every query agreed with itself would claim no noise at all.
    """
    out = []
    for c in cases:
        n = int(c["runs"])
        h = round(c["rate"] * n)
        p = rng.betavariate(h + 0.5, n - h + 0.5)
        out.append(sum(rng.random() < p for _ in range(n)) / n)
    return out


def noise_drop(before, after, set_label, metric, seed=0):
    """(lower bound of the drop, how wide the noise was) or None when it cannot be told.

    The drop is before minus after, resampled on both sides independently; its lower
    `NOISE_LEVEL` quantile above zero means the metric fell by more than the runs vary.
    None when either run has a query measured once - one run has no spread to read, and
    reporting "no noise" there would be the zero that is really "not measured".
    """
    return _noise(_trigger_cases(before, set_label), _trigger_cases(after, set_label),
                  metric, seed)


def split_gap(report, metric="f1", seed=0):
    """(lower bound of train minus validation, noise width) for one trigger report, or None.

    The study behind this reads a large train-validation gap as its own diagnosis:
    descriptions that genuinely overlap, which rewording does not fix (arXiv 2606.30775).
    Judged against the same resampled noise as the gate, so a gap is only reported when
    it is larger than the runs vary.
    """
    wrapped = {"trigger": report}
    return _noise(_trigger_cases(wrapped, "train"), _trigger_cases(wrapped, "validation"),
                  metric, seed)


def _noise(b_cases, a_cases, metric, seed=0):
    if not b_cases or not a_cases or any(int(c["runs"]) < 2 for c in b_cases + a_cases):
        return None
    rng = random.Random(seed)
    drops = []
    for _ in range(NOISE_DRAWS):
        b = _ratio(b_cases, _resample(b_cases, rng), metric)
        a = _ratio(a_cases, _resample(a_cases, rng), metric)
        if b is not None and a is not None:
            drops.append(b - a)
    if len(drops) < NOISE_DRAWS // 2:
        return None
    drops.sort()
    lower = drops[int(NOISE_LEVEL * len(drops))]
    width = drops[int((1 - NOISE_LEVEL) * len(drops)) - 1] - lower
    return lower, width


def compare(before, after, quality_drop=QUALITY_DROP, cost_rise=COST_RISE):
    """What moved between two stored runs, split into quality and cost.

    Trigger precision and recall are judged against the runs' own noise when both runs
    repeated each query; everything else against `quality_drop`, and each row says which.
    """
    moves, regressions, cost_moves = [], [], []
    seen = set()
    for section, path, label in QUALITY:
        b = dig(before.get(section) or {}, path)
        a = dig(after.get(section) or {}, path)
        if b is None or a is None or label in seen:
            continue
        seen.add(label)
        noise = (noise_drop(before, after, path[1], path[-1])
                 if section == "trigger" else None)
        if noise is not None:
            worse = noise[0] > 0
            basis = f"noise ±{noise[1] / 2:.0%}"
        else:
            worse = b - a > quality_drop
            basis = (f"noise not measured, fixed {quality_drop:.0%}"
                     if section == "trigger" else "")
        moves.append((label, b, a, basis, worse))
        if worse:
            regressions.append((label, b, a))
    for section, path, label in COST:
        b = dig(before.get(section) or {}, path)
        a = dig(after.get(section) or {}, path)
        if b is None or a is None or not b:
            continue
        rise = (a - b) / b
        cost_moves.append((label, b, a, rise))
    return {
        "before": before.get("label"), "after": after.get("label"),
        "quality": moves,
        "regressions": regressions,
        "cost": cost_moves,
        "cost_regressions": [row for row in cost_moves if row[3] > cost_rise],
        "tasks": affected_tasks(before, after),
        "queries": affected_queries(before, after),
        "environments": _environment_change(before, after),
    }


def _environment_change(before, after):
    """(before, after) when the two runs were measured in different settings, else None.

    A run records its provider, model and runs. When they differ, what moved may be the
    model and not the skill; the gate still reports the numbers, and says so above them.
    Runs saved before environments were recorded carry none and are not second-guessed.
    """
    b, a = before.get("environment"), after.get("environment")
    if not b or not a:
        return None
    keys = ("provider", "model", "runs")
    if all(b.get(k) == a.get(k) for k in keys):
        return None
    spell = lambda e: ", ".join(f"{k} {e.get(k)}" for k in keys)  # noqa: E731
    return spell(b), spell(a)


def render(diff, fail_on_cost=False):
    head = "REGRESSION DETECTED" if diff["regressions"] or (
        fail_on_cost and diff["cost_regressions"]) else "no regression"
    lines = [f"{head}   {diff['before']} → {diff['after']}", ""]
    if diff.get("environments"):
        was, now = diff["environments"]
        lines += [f"  measured in different settings - {was}  →  {now}.",
                  "  What moved may be the setting, not the skill.", ""]
    for label, b, a, basis, worse in diff["quality"]:
        mark = "! " if worse else "  "
        tail = f"   ({basis})" if basis else ""
        lines.append(f"  {mark}{label:<22}{b:.0%} → {a:.0%}{tail}")
    for label, b, a, rise in diff["cost"]:
        mark = "! " if rise > COST_RISE else "  "
        sign = "+" if rise >= 0 else ""
        lines.append(f"  {mark}{label:<22}{b:.4g} → {a:.4g}   {sign}{rise:.0%}")
    if diff["tasks"]:
        lines += ["", "  tasks that got worse:"]
        for task_id, old, new in diff["tasks"]:
            lines.append(f"    {task_id:<24}{old:.0%} → {new:.0%}")
    if diff["queries"]:
        lines += ["", "  trigger cases that flipped:"]
        for prompt, was, now, expected in diff["queries"]:
            lines.append(f"    [{was:.2f} → {now:.2f}] should {expected}: {prompt[:56]}")
    if not diff["regressions"] and diff["cost_regressions"] and not fail_on_cost:
        lines += ["", "  Cost rose past the threshold and quality did not fall. That is a "
                      "trade, not a break;",
                  "  `--fail-on-cost` makes it one when a budget depends on it."]
    return "\n".join(lines)


def failed(diff, fail_on_cost=False):
    return bool(diff["regressions"]) or (fail_on_cost and bool(diff["cost_regressions"]))
