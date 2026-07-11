#!/bin/bash
set -euo pipefail
# PreToolUse ルーター: Bash ツール実行前のチェックを1つのフックに統合
# トークン最適化: 複数の PreToolUse(Bash) フック → 1つに統合
#
# stdin から JSON を受け取り、コマンド内容に応じて適切なチェックスクリプトに委譲する。
# 各チェックスクリプトは引き続き独立したファイルとして存在する（保守性維持）。
#
# プロジェクト固有のチェック（画像生成モデル制約・SNS 投稿クールダウン等）を
# 追加したい場合は、本ルーターに分岐を足してチェックスクリプトを呼び出す。

INPUT=$(cat)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"

# ツール名と編集対象ファイルパスを抽出（Write/Edit 系のガード用）
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

# GitHub Actions 不使用ポリシー（docs/rules/no-github-actions.md）の非ブロッキング警告。
# Write/Edit で .github/workflows/*.yml を新規作成・編集しようとしたら警告する（ブロックはしない）。
if printf '%s' "$FILE_PATH" | grep -qE '\.github/workflows/.*\.ya?ml$'; then
  echo "WARN: 本プロジェクトは GitHub Actions を使わない方針です（docs/rules/no-github-actions.md）。" >&2
  echo "      CI は Claude Code ハーネス（self-reviewer のワークツリー隔離 e2e・フック・ルーティン）で代替してください。" >&2
  echo "      どうしても必要なら理由を Issue に記録してから追加してください。" >&2
  # 非ブロッキング: exit 0 で続行を許可する
fi

# MCP 経由の PR 作成（mcp__github__create_pull_request）も Bash の gh pr create と同じ
# 事前ゲート（未コミット検出 + セルフレビュー機械チェック + Layer 1 リマインダー）に通す。
# クラウド環境では gh pr create が proxy 403 で失敗し MCP 経由が PR 作成の主経路になるため、
# matcher 外だと Layer 0 ゲートを完全素通りしてしまう（再発防止・FAIR Layer 1 スキップの根本原因）。
if [ "$TOOL_NAME" = "mcp__github__create_pull_request" ]; then
  echo "$INPUT" | "$HOOK_DIR/pre-pr-create-check.sh"
  exit $?
fi

# コマンド文字列を抽出（JSON の tool_input.command フィールド）
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Bash 経由で .github/workflows/*.yml を作成する経路（cat >/touch/tee 等）も警告する
if printf '%s' "$COMMAND" | grep -qE '\.github/workflows/.*\.ya?ml'; then
  echo "WARN: 本プロジェクトは GitHub Actions を使わない方針です（docs/rules/no-github-actions.md）。" >&2
fi

# git push チェック（main/master 直接 push のブロック）
if echo "$COMMAND" | grep -qE 'git\s+push'; then
  echo "$INPUT" | "$HOOK_DIR/pre-git-push-check.sh"
  exit $?
fi

# PR 作成チェック（未コミット・未push 検出 + セルフレビュー機械チェック）
if echo "$COMMAND" | grep -qE '(gh\s+pr\s+create|poll_pr_reviews)'; then
  echo "$INPUT" | "$HOOK_DIR/pre-pr-create-check.sh"
  exit $?
fi

# .env ファイルへのアクセスをブロック（Bash コマンド経由: cat/source/.env 等）
# 注意: "git commit -m '... .env ...'" 等のコミットメッセージへの誤検知を防ぐため、
# ファイルアクセスコマンド直後の引数として .env が現れるパターンのみブロックする
if echo "$COMMAND" | grep -qE '(^|[[:space:];|&])(cat|less|head|tail|more|source|grep|\.)([[:space:]]+-[^[:space:];|&]+)*[[:space:]]+([^[:space:];|&]*/)?\.env([^[:space:];|&]*)?([[:space:];|&]|$)'; then
  echo "BLOCK: .env ファイルへのアクセスは禁止されています"
  exit 2
fi

# 該当なし: 許可
exit 0
