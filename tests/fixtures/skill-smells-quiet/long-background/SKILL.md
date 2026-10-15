---
name: long-background
description: Explains why a flaky test is flaky. Use when the user asks why a test passes locally and fails in CI, or the reverse.
---

# Flaky tests

Most flakiness in this codebase has one of three causes, and they look alike from the outside, which is why the explanation matters more than any procedure would. Shared state between tests is the commonest: a fixture that writes to a module-level cache, a temporary directory reused across cases, an environment variable one test sets and never restores. Ordering makes it visible, because the test runner shuffles on CI and keeps file order locally, so a test that depends on a neighbour having run passes at a desk and fails on the server. Time is the second cause: a test that compares against the current date passes all day and fails for an hour after midnight in one timezone, and a sleep that was long enough on a laptop is too short on a loaded runner. The network is the third, a test that reaches a real service and inherits its outages as its own. Each of these leaves a signature in the failure log, for example an assertion about a count that is off by exactly the number of items a neighbouring test created, and reading that signature is the whole skill: the cause is named from the evidence in the log, and a guess is labelled as one.
