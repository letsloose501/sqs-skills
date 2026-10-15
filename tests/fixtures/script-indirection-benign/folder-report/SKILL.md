---
name: folder-report
description: Lists what is in a folder and how big it is. Use when the user asks what is taking up space in a directory.
---

# Folder report

1. Run `scripts/report.py` on the folder or directory the user named, to list what is
   in it and how big each entry is.
2. If the folder came as a base64 dump, run `scripts/unpack.sh` first.
3. Print the report, largest first, so what is taking up space is at the top - for
   example, `node_modules  1.2 GB` above `src  4 MB`.
