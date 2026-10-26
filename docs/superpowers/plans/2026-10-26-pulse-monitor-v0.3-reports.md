# Pulse Monitor v0.3 Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each monitor a readable 24-hour or 7-day check-based report with charts and CSV export.

**Architecture:** Aggregate retained SQLite checks into fixed rolling buckets in `Store`; expose JSON and CSV through the existing HTTP server. Render dependency-free chart elements and an accessible bucket table in the existing detail view.

**Tech Stack:** Python 3 standard library, SQLite, HTML, CSS, vanilla JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-26-pulse-monitor-v0.3-reports-design.md`

## Global Constraints

- Keep the app local-first and dependency-free.
- 24 hours means 24 rolling one-hour buckets; 7 days means seven rolling 24-hour buckets.
- Availability is successful checks / recorded checks, not elapsed uptime.
- Empty buckets have null percentages and latency.
- Keep at least 21,000 checks per monitor.

## Review Focus

- Boundary checks belong to exactly one bucket; test start inclusive and end exclusive.
- Failed checks do not skew successful-response averages; test mixed results.
- No checks yield null metrics and a visible empty state; test empty report.
- CSV matches the selected range and escapes spreadsheet formulas; test an error beginning with `=`.
- A non-existent monitor or unsupported range returns an HTTP error; test both.

---

### Task 1: Retention and report model

**Files:** `pulse.py`, `tests/test_pulse.py`

- [ ] Add failing tests for 24-hour and 7-day buckets, boundaries, missing data, and successful-response averages.
- [ ] Implement `Store.report(mid, range_name, now=None)` and retain 21,000 checks.
- [ ] Run focused and full tests.

### Task 2: Report and CSV routes

**Files:** `pulse.py`, `tests/test_pulse.py`

- [ ] Add failing API tests for range validation, missing monitor, and CSV rows/formula protection.
- [ ] Implement `GET /api/monitors/<id>/report?range=24h|7d` and `/report.csv?range=24h|7d`.
- [ ] Run focused and full tests.

### Task 3: Dashboard charts

**Files:** `static/app.js`, `static/index.html`, `static/style.css`

- [ ] Add range controls, report summary, availability/response charts, CSV action, and accessible per-bucket table to the detail view.
- [ ] Keep empty data and partial-range copy explicit; check JavaScript syntax.
- [ ] Browser-check desktop and narrow viewport flows.

### Task 4: Documentation and delivery

**Files:** `README.md`, GitHub repository

- [ ] Document metric meanings, retention, and CSV fields.
- [ ] Run all tests and diff checks, commit locally, upload changed files, and verify remote hashes.
