#!/usr/bin/env bash
# run-e2e.sh — Claude Wiki Hub e2e テストランナー
#
# 使い方:
#   bash scripts/run-e2e.sh           # 全テスト実行
#   bash scripts/run-e2e.sh --verbose  # 詳細出力
#
# 終了コード:
#   0: 全テスト PASS
#   1: 1 件以上 FAIL

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VERBOSE=false
if [[ "${1:-}" == "--verbose" ]]; then
  VERBOSE=true
fi

SUITE_PASS=0
SUITE_FAIL=0
SUITE_TOTAL=0

echo "╔══════════════════════════════════════════════╗"
echo "║   Claude Wiki Hub — E2E テスト                  ║"
echo "╚══════════════════════════════════════════════╝"
echo "実行日時: $(TZ="${PROJECT_TZ:-Asia/Tokyo}" date '+%Y-%m-%d %H:%M %Z')"
echo "対象ブランチ: $(git branch --show-current 2>/dev/null || echo 'unknown')"
echo ""

run_suite() {
  local script="$1"
  local suite_name="$(basename "$script" .sh)"
  ((SUITE_TOTAL++)) || true

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if $VERBOSE; then
    if bash "$script"; then
      echo "  🟢 ${suite_name}: PASS"
      ((SUITE_PASS++)) || true
    else
      echo "  🔴 ${suite_name}: FAIL"
      ((SUITE_FAIL++)) || true
    fi
  else
    local EXIT_CODE=0
    local OUTPUT
    OUTPUT=$(bash "$script" 2>&1) || EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 0 ]; then
      echo "  🟢 ${suite_name}: PASS"
      ((SUITE_PASS++)) || true
    else
      echo "  🔴 ${suite_name}: FAIL"
      echo "$OUTPUT" | sed 's/^/  /'
      ((SUITE_FAIL++)) || true
    fi
  fi
}

# 全テストスイートを実行
for test_script in tests/e2e/test_*.sh; do
  if [ -f "$test_script" ]; then
    run_suite "$test_script"
  fi
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$SUITE_TOTAL" -eq 0 ]; then
  echo "⚠️  テストスイートが 0 件です。tests/e2e/test_*.sh を確認してください。"
  exit 1
fi

echo "📊 テスト結果: ${SUITE_PASS}/${SUITE_TOTAL} スイート PASS"
echo ""

if [ "$SUITE_FAIL" -gt 0 ]; then
  echo "❌ ${SUITE_FAIL} スイートが FAIL しています"
  echo "   詳細は: bash scripts/run-e2e.sh --verbose"
  exit 1
else
  echo "✅ 全テスト PASS にゃ！"
fi
