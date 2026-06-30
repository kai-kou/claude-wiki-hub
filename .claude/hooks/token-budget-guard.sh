#!/usr/bin/env bash
# token-budget-guard.sh — 実行中のトークン消費を監視し WARN/HARD 閾値で自動停止する。
#
# ループ工学の Token blowout アンチパターン対策（Issue #98）。
# post-tool-use-validate.sh から呼び出される（直接 PostToolUse フックには登録しない）。
#
# 環境変数:
#   CLAUDE_CODE_TOKEN_LIMIT_WARN  警告閾値（出力トークン累計・デフォルト: 350000）
#   CLAUDE_CODE_TOKEN_LIMIT_HARD  強制停止閾値（出力トークン累計・デフォルト: 380000）
#
# 終了コード:
#   0  正常（閾値未達）
#   1  WARNING: 警告メッセージを stderr に出力（Claude のコンテキストに注入される）
#   2  HARD STOP: 強制停止メッセージを stderr に出力
#
# 測定方法: セッション JSONL の assistant メッセージから output_tokens を合算する。
# JSONL が見つからない場合・jq が使えない場合はフェイルオープン（exit 0）で継続する。

set -euo pipefail

WARN_TOKENS="${CLAUDE_CODE_TOKEN_LIMIT_WARN:-350000}"
HARD_TOKENS="${CLAUDE_CODE_TOKEN_LIMIT_HARD:-380000}"

SESSION_ID="${CLAUDE_CODE_SESSION_ID:-}"
[[ -z "$SESSION_ID" ]] && exit 0

# セッション JSONL を検索（複数プロジェクトディレクトリに対応）
TRANSCRIPT=$(find /root/.claude/projects -maxdepth 2 -name "${SESSION_ID}.jsonl" 2>/dev/null | head -1)
[[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]] && exit 0

# jq が利用不可の場合はフェイルオープン
command -v jq &>/dev/null || exit 0

# アシスタントメッセージの output_tokens を合算
# JSONL 構造が想定外の行や null の場合は 0 扱い
TOTAL=$(jq -r '
  select(.type == "assistant") |
  (.message.usage.output_tokens // .usage.output_tokens // 0)
' "$TRANSCRIPT" 2>/dev/null | awk '{s+=$1} END {print int(s+0)}')
TOTAL="${TOTAL:-0}"

if [[ "$TOTAL" -ge "$HARD_TOKENS" ]]; then
  echo "⛔ [token-budget-guard] HARD STOP: 出力トークン累計 ${TOTAL} が上限 ${HARD_TOKENS} を超過。" \
       "直ちに作業をコミット & プッシュしてセッションを終了してください。" >&2
  exit 2
elif [[ "$TOTAL" -ge "$WARN_TOKENS" ]]; then
  echo "⚠️ [token-budget-guard] WARNING: 出力トークン累計 ${TOTAL} が警告閾値 ${WARN_TOKENS} に到達。" \
       "上限まで残り $((HARD_TOKENS - TOTAL)) トークン。作業をコミット & プッシュしてください。" >&2
  exit 1
fi

exit 0
