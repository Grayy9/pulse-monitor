# Pulse Monitor v0.3: Reports and charts

The user chose reports and charts and delegated the detailed choices. This release helps a single local operator answer whether a monitor has been reliable recently and whether response times are changing. It builds on the existing dark dashboard and Python standard-library stack.

## Scope

- A monitor detail view offers **24 hours** and **7 days**. The 24-hour view has 24 rolling one-hour buckets; the 7-day view has seven rolling 24-hour buckets. Every bucket exposes its exact UTC start and end timestamps.
- Each view shows successful checks / total checks as a check-based availability percentage, failed-check count, and mean response time of successful checks. Empty windows and buckets show "no data", never 100% or zero latency. Partial buckets are based only on recorded checks.
- A compact availability chart and response-time chart share the same buckets. Labels, tooltips, and an accessible per-bucket data table expose values without relying only on color or hover.
- The selected range can be exported as UTF-8 CSV containing raw recorded checks in timestamp order, with UTC timestamps, result, HTTP status, response time, and error. The export uses the same time boundary as the report and includes a UTF-8 BOM for spreadsheet compatibility. Text cells are protected from spreadsheet formula execution.
- Retain at least 21,000 checks per monitor, enough to cover seven days at the shortest 30-second interval with a margin. Existing databases open without losing data.

## Boundaries and meanings

All percentages are based on checks, not elapsed uptime. Failed checks have no contribution to mean successful response time. The 7-day view means the rolling previous 168 hours, grouped into rolling 24-hour periods. A chart bucket with no checks is a gap. Existing 24-hour incident observations and the rest of the monitoring workflow stay available.

No PDF, scheduled email, public sharing, authentication, third-party chart package, or new network service is introduced. v0.3 succeeds when the API and UI agree on bucket counts, absent data is honest, CSV matches the selected range, and a user can read the report on desktop and mobile.
