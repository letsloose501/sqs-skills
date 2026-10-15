# The evaluation fixture

`sqs.py eval` runs an agent, so the arithmetic on top of it - the confusion matrix, the
baseline/treatment comparison, the regression diff - would otherwise be the only part
of the suite with no tests at all.

This directory is that test. `ledger-lite` is an ordinary small skill with both eval
sets filled in; `script-v1.json` and `script-v2.json` are scripts for the `fake`
provider, which replays canned runs instead of calling a model. v2 is v1 after a bad
edit: one task stops passing, one trigger case starts firing when it should not, and
the token count goes up.

`script-process-good.json` and `script-process-bad.json` are the pair for `process`. Both
give the same answer and leave the same ledger row, so completion cannot tell them apart:
the good one reads the ledger, edits it once and reads it back; the bad one writes blind,
searches the web and writes twice, and breaks each of the four process items in
`run_tests.py`'s `PROCESS_CASE` for a different reason.

What this tests: the metrics, the split, the storage and the regression gate.
What it cannot test: whether a real agent behaves the way the script says. Nothing
here is evidence about any skill.

    SQS_FAKE_RUNS=tests/evaluation/script-v1.json \
      python scripts/sqs.py eval tests/evaluation/ledger-lite --all --provider fake
