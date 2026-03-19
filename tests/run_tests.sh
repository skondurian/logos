#!/usr/bin/env bash
# Run all Logos integration tests
# Usage: ./tests/run_tests.sh
# Exit code: 0 if all pass, 1 if any fail

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$SCRIPT_DIR/logos"

PASS=0
FAIL=0
SKIP=0

LOGOSCC="$REPO_ROOT/bin/logoscc"

if [[ ! -x "$LOGOSCC" ]]; then
    echo "ERROR: $LOGOSCC not found. Run 'make' first." >&2
    exit 1
fi

for logos_file in "$TEST_DIR"/*.logos; do
    base="${logos_file%.logos}"
    expected_file="${base}.expected"
    test_name="$(basename "$base")"

    if [[ ! -f "$expected_file" ]]; then
        echo "SKIP $test_name (no .expected file)"
        SKIP=$((SKIP + 1))
        continue
    fi

    # Compile to temp binary
    tmp_bin="$(mktemp /tmp/logos_test_XXXXXX)"
    trap 'rm -f "$tmp_bin"' EXIT

    if ! "$LOGOSCC" "$logos_file" -o "$tmp_bin" 2>/tmp/logoscc_test_err.txt; then
        echo "FAIL $test_name (compilation error)"
        grep -v 'lex-file\|slab\|cons slab\|\[logos-debug\]' /tmp/logoscc_test_err.txt | head -5 >&2
        FAIL=$((FAIL + 1))
        continue
    fi

    # Run and capture stdout
    actual="$("$tmp_bin" 2>/dev/null || true)"
    expected="$(cat "$expected_file")"

    rm -f "$tmp_bin"
    trap - EXIT

    if [[ "$actual" == "$expected" ]]; then
        echo "PASS $test_name"
        PASS=$((PASS + 1))
    else
        echo "FAIL $test_name"
        echo "  expected: $(echo "$expected" | head -3)"
        echo "  actual:   $(echo "$actual" | head -3)"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "Results: $PASS passed, $FAIL failed, $SKIP skipped"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
