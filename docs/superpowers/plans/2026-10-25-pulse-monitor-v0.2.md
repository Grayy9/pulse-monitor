# Pulse Monitor v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local monitor manageable and reliable for multiple endpoints.

**Architecture:** Extend the existing SQLite store with a compatible migration and monitor state. Keep API handlers in `pulse.py`, add a bounded runner for scheduled/manual checks, and extend the existing dashboard. The same history table powers 24-hour check statistics and observed incidents.

**Tech Stack:** Python 3 standard library, SQLite, HTML, CSS, JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-25-pulse-monitor-v0.2-design.md`

## Global Constraints

- Keep old `pulse.db` files and checks intact.
- Keep the default bind address `127.0.0.1` and five-second check timeout.
- Use three consecutive failed checks for one outage webhook; recover on one success.
- Label the 24-hour percentage as check-based.
- No third-party dependencies.

## Review Focus

- Editing a URL must not show stale status or carry over alert streak.
- Pause and resume must preserve history and schedule as specified.
- Two overlapping checks for one monitor must not be permitted.
- A webhook failure must not erase a recorded check.
- No checks in 24 hours must produce an unknown percentage, not 100%.

---

### Task 1: Store, migration, and statistics

**Files:** `pulse.py`, `tests/test_pulse.py`

- [ ] Write failing tests for legacy migration, update/pause/resume, and 24-hour statistics/incidents.
- [ ] Implement store migration, edit operations, and statistics.
- [ ] Run all tests.

### Task 2: Alert and concurrent runner

**Files:** `pulse.py`, `tests/test_pulse.py`

- [ ] Write failing tests for three-failure alerting and bounded concurrent checks.
- [ ] Implement persistent alert state and runner.
- [ ] Run all tests.

### Task 3: API and dashboard

**Files:** `pulse.py`, `static/index.html`, `static/style.css`, `static/app.js`, `tests/test_pulse.py`

- [ ] Write failing API tests for edit/pause and statistics.
- [ ] Implement API routes and dashboard controls.
- [ ] Verify the user flow and run all tests.

### Task 4: Documentation and delivery

**Files:** `README.md`, project files, GitHub repository

- [ ] Document v0.2 behavior and compatibility.
- [ ] Verify tests, syntax, and staged diff.
- [ ] Commit locally, upload to GitHub, and verify remote file hashes.
