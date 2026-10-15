---
name: stepless-runbook
description: Restores a staging database from the nightly dump. Use when staging data is broken, when the user asks to reset staging, or after a migration test left it dirty.
---

# Restore staging

**The restore.** First, find the newest dump in the backups bucket; the nightly job names each one after its date, so the newest is the last in the listing, and a dump older than two days means the job has been failing and is worth reporting before anything else happens. Then stop the staging application so nothing writes to the database while it is being replaced, because a write that lands halfway through the restore leaves a table that matches neither the dump nor the old state, and that is much harder to notice than a restore that failed outright. After that, drop the staging database and create it again empty, with the same owner and encoding the old one had, which the connection settings in the deployment config list for this environment. Next, load the dump into the new database and watch the loader output for errors about missing roles, which mean the dump came from a different cluster than the one it was meant for. Finally, start the application again, open the health page, and check that it reports the database as reachable and the row counts as roughly what production had the night before, for example within a few percent on the orders table.
