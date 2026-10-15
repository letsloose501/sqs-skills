---
name: ordered-with-steps
description: Restores a staging database from the nightly dump. Use when staging data is broken, when the user asks to reset staging, or after a migration test left it dirty.
---

# Restore staging

Why the order matters, before the steps. First, the newest dump is the only one worth loading; the nightly job names each one after its date, so the newest is the last in the listing, and a dump older than two days means the job has been failing and is worth reporting before anything else happens. Then the application has to be stopped, because a write that lands halfway through the restore leaves a table that matches neither the dump nor the old state, and that is much harder to notice than a restore that failed outright. After that the database is recreated empty, with the same owner and encoding the old one had, which the connection settings in the deployment config list for this environment. Next comes the load, and loader errors about missing roles mean the dump came from a different cluster than the one it was meant for. Finally the application comes back, and the health page is where the restore is judged, for example by row counts within a few percent of production on the orders table, by the age of the newest order matching the date of the dump, and by the background workers reporting that their queues are drained rather than replaying a backlog the old database had left behind.

1. Find the newest dump.
2. Stop the application.
3. Recreate the database, load the dump, start the application and check the health page.
