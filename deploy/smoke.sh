#!/bin/sh
# Checks a running production stack through Nginx: health, client-side routes, upload body cap, upload rate limit.
# Usage: deploy/smoke.sh [base url]   (default http://localhost). Sends empty uploads only; stores nothing.
set -eu
BASE=${1:-http://localhost}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
fail() { echo "FAIL: $1"; exit 1; }

[ "$(code "$BASE/api/health")" = 200 ] || fail "GET /api/health is not 200"
curl -s "$BASE/email-history" | grep -q 'id="root"' || fail "client-side route did not fall back to index.html"
curl -sI "$BASE/" | grep -qi '^content-security-policy:' || fail "security headers missing"

# Over the 105 MB cap: Nginx answers 413 before the app reads anything
big=$(head -c 120000000 /dev/zero | code -X POST -H 'Content-Type: application/octet-stream' --data-binary @- "$BASE/api/batches")
[ "$big" = 413 ] || fail "oversized upload got $big, expected 413"

# 10 a minute with a burst of 5: some of 12 quick uploads must be turned away
limited=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  [ "$(code -X POST "$BASE/api/batches")" = 429 ] && limited=$((limited + 1))
done
[ "$limited" -gt 0 ] || fail "no 429 after 12 quick uploads"

echo "OK: health, routes, headers, 413 body cap, 429 rate limit ($limited of 12 limited)"
