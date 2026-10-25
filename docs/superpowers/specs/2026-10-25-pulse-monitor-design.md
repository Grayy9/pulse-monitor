# Pulse Monitor design

Build a small, independently implemented uptime monitor inspired by Uptime Kuma. The intended user is one person running the application on a local computer or trusted network. Success means they can add HTTP/HTTPS endpoints, see current status and recent response time, inspect a history of checks, and receive an optional webhook when a status changes.

The application uses Python's standard library and SQLite, with one local web server and a responsive dashboard. It checks each endpoint at its configured interval, saves every result, and continues checking after a server restart. A failed HTTP status or network error counts as down. Webhooks fire only when a monitor changes between up and down, excluding its first check. The UI refreshes automatically and shows when data was last updated.

The default bind address is 127.0.0.1. The user can change it with HOST to make the dashboard reachable on a trusted network. There is no account system in this MVP. The webhook URL is optional and configured through an environment variable. This is a scoped reproduction of the core monitoring workflow, not a copy of Uptime Kuma's source or brand.

Out of scope: TCP/DNS/Docker checks, public multiuser hosting, SMS/email integrations, certificate monitoring, and mobile apps. Prioritize a reliable check loop, simple error messages, and readable status over decorative charts.
