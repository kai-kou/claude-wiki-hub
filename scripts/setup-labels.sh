#!/usr/bin/env bash
# setup-labels.sh — idea/bookmark の Issue 管理化に必要な新設ラベル 4 件をセットアップする
#
# 概要:
#   content/discussions/ideas-bookmarks-issue-mgmt/whiteboard.md「合意 2」で確定した
#   新設ラベル 4 件（kind:idea / kind:bookmark / status:ingested / status:archived）を
#   作成・色/説明を正規化する冪等スクリプト。既存ラベルは --force で上書きする。
#
# 使い方:
#   bash scripts/setup-labels.sh [--repo <owner/repo>]
#
# 前提:
#   - gh CLI がインストール済み・認証済み（gh auth login）であること
#   - クラウド実行環境（Claude Code on the web）では gh の repo スコープ操作が
#     agent-proxy に 403 でブロックされるため（L-114）、本スクリプトはそこでは
#     実行しない。ラベルは Issue テンプレート/issue_write の labels 指定時に
#     REST が自動作成するため、色の正規化のみ後回しになる（下記メッセージ参照）。
#
# 参考: tools/triage_improvements.py の resolve_repo()（env → git remote → プレースホルダ）
set -euo pipefail

REPO=""

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

resolve_repo() {
  for env in PROJECT_REPO GITHUB_REPOSITORY; do
    v="${!env:-}"
    if [ -n "$v" ] && [[ "$v" == */* ]]; then
      echo "$v"
      return 0
    fi
  done
  local url
  url="$(git remote get-url origin 2>/dev/null || true)"
  if [ -n "$url" ]; then
    # 例: git@github.com:owner/repo.git / https://github.com/owner/repo
    local slug
    slug="$(echo "$url" | sed -E 's#\.git$##; s#^.*[:/]([^/]+/[^/]+)$#\1#')"
    if [[ "$slug" == */* ]]; then
      echo "$slug"
      return 0
    fi
  fi
  echo "kai-kou/claude-wiki-hub"
}

if [ -z "$REPO" ]; then
  REPO="$(resolve_repo)"
fi

echo "[setup-labels] 対象リポジトリ: $REPO"

if ! command -v gh &>/dev/null; then
  echo ""
  echo "ℹ️ gh CLI が見つかりません。"
  echo "  ラベル（kind:idea / kind:bookmark / status:ingested / status:archived）は"
  echo "  Issue 作成時に labels 指定すると GitHub REST が自動作成するため、"
  echo "  Issue 管理化フロー自体は動作します（デフォルト色のまま）。"
  echo "  色・説明の正規化は、後で本スクリプトを gh CLI のあるローカル環境で"
  echo "  実行するか、GitHub UI（Settings > Labels）から手動設定してください。"
  exit 0
fi

if ! gh auth status &>/dev/null; then
  echo ""
  echo "ℹ️ gh CLI は認証されていません（gh auth login が必要）。"
  echo "  ラベルは Issue 作成時に自動作成されるため、Issue 管理化フロー自体は動作します。"
  echo "  色の正規化は認証後に本スクリプトを再実行するか GitHub UI から設定してください。"
  exit 0
fi

# name|color|description
LABELS=(
  "kind:idea|7C3AED|アイデア Issue（ideas/*.md に対応）"
  "kind:bookmark|2563EB|ブックマーク Issue（bookmarks/inbox.md に対応）"
  "status:ingested|16A34A|wiki に取り込み済み（ingest トリガー兼完了マーク）"
  "status:archived|9CA3AF|棚上げ・削除候補（close 理由の区別用）"
)

for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color desc <<< "$entry"
  echo "[setup-labels] $name を作成/更新中..."
  if gh label create "$name" --color "$color" --description "$desc" --force -R "$REPO"; then
    echo "  ✅ $name"
  else
    echo "  ⚠ $name の作成/更新に失敗しました（権限を確認してください）" >&2
  fi
done

echo ""
echo "✅ ラベルセットアップ完了（$REPO）"
