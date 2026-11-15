---
title: Export orders as CSV
status: draft
created: 2026-11-14
---

# Export orders as CSV

## Summary

Shop admins can download the orders they are looking at as a CSV file, filtered the same way as the orders table.

## Context

The orders table already filters by date range and status on the server (F-001). Admin routes are guarded by one
middleware (F-002). There is no CSV writer in the project yet; the standard library's `encoding/csv` is available (F-003).

## Requirements

### R-001: Export endpoint

`GET /admin/orders/export.csv` MUST return the orders matching the same `from`, `to` and `status` query parameters the
orders table accepts, as `text/csv`, one row per order.

Source: A-001, F-001

Acceptance:
- With 3 orders in range and 2 outside it, the response has a header row and exactly 3 data rows.
- The response `Content-Type` is `text/csv; charset=utf-8`.
- The response `Content-Disposition` names the file `orders-<from>-<to>.csv`.

### R-002: Admins only

The export MUST be reachable only through the existing admin middleware.

Source: A-002, F-002

Acceptance:
- A request with no session gets HTTP 401 and no CSV body.
- A request from a non-admin session gets HTTP 403 and no CSV body.

### R-003: Columns

Each row MUST carry, in this order: order ID, created-at in RFC 3339 UTC, customer email, status, total in minor units.

Source: A-003

Acceptance:
- The header row is exactly `id,created_at,email,status,total_minor`.
- An order created at 09:30 in UTC+2 shows `created_at` as `07:30:00Z` on the same date.
- A customer email containing a comma is quoted, and the row still parses to 5 fields.

## Non-goals

- No export formats other than CSV.
- No background jobs; the export is generated within the request.

## Open questions

- None

## Appendix: Interview Transcript

### A-001

**Q:** Should the export follow the filters on screen, or always export everything?

**A:** Same filters as the table. Nobody wants the whole history.

### A-002

**Q:** Who may export?

**A:** Admins only, same as the orders page.

### A-003

**Q:** Which columns, and how should money and time be written?

**A:** ID, created time, email, status, total. Money in cents, times in UTC.

## Appendix: Codebase Facts

### F-001

The orders list handler parses `from`, `to` and `status` and passes them to `store.ListOrders`
(`internal/orders/handler.go:48`).

### F-002

Every `/admin` route is mounted behind `RequireAdmin` (`internal/server/routes.go:31`).

### F-003

No CSV writer exists in the repository; `go.mod:1` targets Go 1.26, whose standard library includes `encoding/csv`.
