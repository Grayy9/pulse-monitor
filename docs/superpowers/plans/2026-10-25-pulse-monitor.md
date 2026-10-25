# Pulse Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a locally runnable uptime monitor and publish it to the user's GitHub.

**Architecture:** A Python HTTP server exposes JSON endpoints and static assets. SQLite persists monitors and check history. A background loop runs due HTTP checks and sends optional transition webhooks.

**Tech Stack:** Python 3 standard library, SQLite, HTML, CSS, JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-25-pulse-monitor-design.md`

## Global Constraints

- Bind to `127.0.0.1` by default.
- Accept only HTTP and HTTPS monitor URLs.
- Send webhooks only on up/down transitions after an initial result.
- Do not add third-party dependencies.

## Review Focus

- Malformed URLs and intervals must return a helpful validation error.
- Failed HTTP status and transport errors must be stored as down.
- Checks must survive a process restart through SQLite.
- User-supplied names and URLs must render without HTML execution.
- Network timeouts must not stall checking indefinitely.

---

### Task 1: Persistence and checks

**Files:** `pulse.py`, `tests/test_pulse.py`

- [x] Write tests for monitor creation, validation, HTTP success/failure, and persisted history.
- [x] Run tests and confirm failure from missing behavior.
- [x] Implement store and one-check operation.
- [x] Run full tests and confirm success.

### Task 2: API and scheduler

**Files:** `pulse.py`, `tests/test_pulse.py`

- [x] Write API tests for add/list/check/delete and webhook transition.
- [x] Run tests and confirm failure.
- [x] Implement routes and scheduled checks.
- [x] Run full tests and confirm success.

### Task 3: Dashboard and delivery

**Files:** `static/index.html`, `static/style.css`, `static/app.js`, `README.md`, `.gitignore`

- [x] Implement responsive dashboard for overview, add, history, and manual check.
- [x] Run the application and verify the browser flow.
- [ ] Run the full test suite, inspect git diff, commit, and publish.
