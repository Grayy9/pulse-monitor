# Pulse Monitor v0.2 design

The first release proves a local monitoring workflow. v0.2 makes that workflow dependable enough for several endpoints used daily, while keeping the single-user, local-first model and Python standard-library stack.

Users can edit a monitor's name, URL, and interval without losing checks. Changing the URL clears the displayed current status and alert streak, then schedules a fresh check. Users can pause and resume a monitor; a paused monitor keeps its history and can still be checked manually. Resuming schedules an immediate automatic check.

An outage webhook is sent once after three consecutive failed checks. A single successful check resets the failure streak and sends one recovery webhook only if an outage webhook had been sent. The initial successful check and intermittent failures do not send a webhook. Latest check status remains visible even before the alert threshold. The existing global `WEBHOOK_URL` stays in place.

Due checks run in a bounded worker pool so a slow endpoint cannot block other endpoints. A monitor cannot have overlapping checks, including manual and scheduled checks. The HTTP request timeout remains five seconds.

For each monitor, the UI shows its successful-check percentage over the last 24 hours, labeled as a check-based estimate rather than time-weighted uptime. It also groups consecutive failed checks into observed incident periods, ending an incident at the next successful check. An incident's timestamps are observation times, not proof of the exact outage start and end. Keep enough raw checks to cover 24 hours at the minimum 30-second interval.

No account system or public sharing is introduced. Existing `pulse.db` files migrate in place without deleting checks. Success means the old data opens, edits and pauses work through the UI and API, alert noise is reduced, slow monitors run concurrently, and the 24-hour figures match recorded checks.
