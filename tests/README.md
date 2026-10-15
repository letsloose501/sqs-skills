# The golden corpus

Seventy rules is enough that nobody can hold them in their head, and a rule that has
never been watched firing is not a rule that works. This directory is how the suite
knows which of its own rules still do something.

```
python tests/run_tests.py              every case, then the unit checks
python tests/run_tests.py clean        one case
python tests/run_tests.py --list       what each case is for
python tests/run_tests.py --coverage   which rules no case observes firing
```

## How a case works

Each directory under `fixtures/` is a small **skills tree** - one or more skill folders -
with an `expect.json` beside it. The runner executes the suite the way a user would, in
a subprocess with `--format json`, and compares the rule codes that came back.

```json
{
  "note": "what this case is for, and why it is shaped this way",
  "command": "check",
  "args": ["--harness", "all"],
  "expect": ["SP004", "ST014"],
  "reject": ["QL002"],
  "exact": false,
  "generate": [{"path": "oversized/SKILL.md", "pad_to": 16000}]
}
```

- **`expect`** - codes the run must report. This is the positive case: proof the rule
  fires on something.
- **`reject`** - codes the run must not report. This is the negative case, and it is
  the half that catches a rule getting greedy.
- **`exact: true`** - the run must report *nothing* beyond `expect`. `clean/` and
  `escape-hatches/` use it, and they are the two cases that matter most: a linter is
  judged by what it stays quiet about.
- **`generate`** - files written at run time rather than checked in: a file big enough
  to break a budget, a line of invisible control characters. Both are built from code
  points in `run_tests.py`, where what they contain is readable. A corpus carrying a
  megabyte of filler is a corpus nobody clones.

## The cases

| Case | What it holds |
|---|---|
| `clean` | a skill with nothing wrong with it - any finding here is a false positive |
| `escape-hatches` | `sqs-allow`, `sqs-allow-file` and the quoted-span exemption, each on a pattern that is genuinely there |
| `spec-frontmatter` | no frontmatter, a renamed folder, an empty description, a reserved word, an unclosed fence, a block scalar, a reference nested too deep |
| `spec-fields` | the limits: a missing field, a name and a description over the ceiling, no body, repository furniture as payload |
| `description-shape` | one branch written twice, steering by prohibition, a user-invoked neighbour named for nothing, a description repeating its own name |
| `name-and-drift` | an off-spec name, and a description that grew away from its body |
| `quality-prose` | what, never when; a description talking about itself; TODOs; unverifiable instructions; a bundled script that waits for a human |
| `structure-links`, `link-shapes`, `sibling-link` | every shape of broken pointer: a file that is not there, a heading that moved, a neighbour's file, a skill that does not exist, an outbound path into a vault that is gone |
| `environment-paths` | a missing path into a tool's own folder (ST017, a warning) next to a missing path into the user's files (ST011) |
| `code-as-prose` | a program pasted into the text, and a skill that activates and says nothing |
| `skill-smells`, `skill-smells-quiet` | four smells from arXiv 2607.01456 (a procedure as one paragraph, no example, output never checked, a format never shown), and the near miss of each |
| `duplicate-name` | two folders claiming one `name` |
| `large-skill` | budgets and asset weight, generated at run time |
| `malicious` | every security rule at once, in the shape they arrive in: a skill that reads as helpful |
| `publish-private`, `publish-language` | what only bites once the skill leaves the machine it was written on |
| `evals-broken` | an `evals/` directory that looks like testing and is not |
| `compat-harness`, `harness-refusal` | a value no runtime accepts, a field outside the spec, a path into one harness's tree, a harness that refuses outright, and a `--harness` name with no adapter |
| `routing-static`, `routing-live` | the delegation contract with `evals/run_evals.py`, stubbed so no model is involved |

## What no fixture can reach

`coverage.json` names them, with the reason, and both `run_tests.py` and `sqs.py rules
--audit` read that one file so the two can never disagree about what is tested.

- **ST015** (no SKILL.md) - `sqs.py` builds its work list from folders that *have* one,
  so a folder without one never reaches it. A unit check calls the structure engine
  directly instead.
- **ST016** (external link unreachable) - the row documents a gap; no engine emits it
  yet. It is out of the coverage count rather than counted as covered.

## The evaluation layer

`evaluation/` is a separate fixture for the half of the suite that runs an agent. The
`fake` provider replays canned runs from a JSON script, so the confusion matrix, the
baseline/treatment split, the storage and the regression gate are all tested without a
model in the loop:

```
SQS_FAKE_RUNS=tests/evaluation/script-v1.json \
  python scripts/sqs.py eval tests/evaluation/ledger-lite --all --provider fake
```

`script-v2.json` is `script-v1.json` after a bad edit - one task stops passing, one
near-miss starts firing, tokens go up - and the unit checks assert that comparing the
two reports a regression naming all three.

What this cannot test is whether a real agent behaves the way the script says. Nothing
in `tests/evaluation/` is evidence about any skill.

## Adding a rule

A new rule needs a row in `scripts/rules.py`, a grading in `GRADES` beside it, and a
**positive case** here. If the rule is a heuristic over prose, it also needs a negative
case: the way these rules go wrong is not failing to fire, it is firing on correct work,
and `reject` is the only thing that notices.

## What only CI can check

The workflow runs the corpus on Python 3.9, 3.11 and 3.13, and that matrix is not
decoration. `publish.py` carried a backslash inside an f-string expression for months:
legal from Python 3.12, a `SyntaxError` before it, and invisible on a machine running a
newer interpreter. Everything imported, every test passed, and the suite would not start
on half the versions it claimed to support.

`ast.parse(..., feature_version=(3, 9))` does **not** catch that class - it was tried,
and it reports nothing on all three versions. Compiling locally is evidence about the
local interpreter and nothing else. The matrix is the only thing here that can see the
opposite.

Then check the harness itself still fails when it should. Break a fixture on purpose and
confirm the runner goes red - a test suite that passes no matter what it is given is the
most expensive kind of green.
