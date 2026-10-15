---
name: quoted-wordings
description: Rewrites a commit subject into the house style. Use when the user asks to fix a commit message or whether a subject line is acceptable.
---

# Commit subjects

1. Read the subject the user gave and the diff it describes.
2. Rewrite it in the imperative, under sixty characters: "add retry to upload",
   "fix export of empty tables", "drop the legacy importer".
3. Check the rewritten subject against the diff: every claim in it is in the change.
   The longer rules are in [style.md](references/style.md).
