#!/usr/bin/env bash
# Production smoke test (§11.11): ./scripts/smoke_test.sh https://news-dc.atinus.co
# Checks health, frontend, feed, search, article detail, assistant (one paid call), admin
# protection and export. Exits non-zero on the first failure.
set -euo pipefail
base="${1:?usage: smoke_test.sh https://<domain>}"
api="$base/api/v1"
check() { echo "ok   $1"; }
fail() { echo "FAIL $1"; exit 1; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

[ "$(code "$api/ready")" = 200 ] && check ready || fail ready
curl -s "$base/" | grep -q '<div id="root">' && check frontend || fail frontend
id=$(curl -s "$api/items?page_size=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["id"])') \
  && check "feed (item $id)" || fail feed
[ "$(code "$api/items/$id")" = 200 ] && check article || fail article
[ "$(code "$api/search?q=cooling")" = 200 ] && check search || fail search
curl -sN --max-time 120 -X POST "$api/ask" -H 'Content-Type: application/json' \
  -d '{"question":"What is new in liquid cooling?"}' | grep -q '^event: done' && check ask || fail ask
[ "$(code "$api/admin/runs")" = 401 ] && check "admin protected" || fail "admin protected"
[ "$(code "$api/export?format=json&limit=5")" = 200 ] && check export || fail export
echo "all checks passed"
