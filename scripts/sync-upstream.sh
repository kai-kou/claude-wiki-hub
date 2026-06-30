#!/usr/bin/env bash
# sync-upstream.sh — claude-wiki-hub の最新ハーネス層をフォーク先へ選択的に取り込む
#
# 使い方:
#   bash scripts/sync-upstream.sh [--dry-run] [--upstream-remote <name>] [--upstream-url <url>]
#
# 既定:
#   upstream remote: "upstream"
#   upstream URL:    https://github.com/kai-kou/claude-wiki-hub
#
# 取り込み対象（ハーネス層）:
#   .claude/hooks/  .claude/skills/  .claude/agents/  .claude/output-styles/
#   docs/rules/  tools/  scripts/  .github/  .gitignore  requirements.txt
#
# 取り込まない（データ層 + プロジェクト固有ファイル）:
#   raw/  wiki/  ideas/  bookmarks/  content/  docs/project-mission.md
#
# 手動マージ推奨（プロジェクト固有設定が含まれる可能性あり）:
#   CLAUDE.md  modules.yaml  .claude/settings.json
set -euo pipefail

UPSTREAM_REMOTE="upstream"
UPSTREAM_URL="https://github.com/kai-kou/claude-wiki-hub"
DRY_RUN=false
YES=false

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)          DRY_RUN=true; shift;;
    --yes|-y)           YES=true; shift;;
    --upstream-remote)  UPSTREAM_REMOTE="$2"; shift 2;;
    --upstream-url)     UPSTREAM_URL="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

# upstream remote がなければ追加
if ! git remote get-url "$UPSTREAM_REMOTE" &>/dev/null; then
  echo "[sync-upstream] upstream remote を追加: $UPSTREAM_URL"
  git remote add "$UPSTREAM_REMOTE" "$UPSTREAM_URL"
fi

echo "[sync-upstream] fetch $UPSTREAM_REMOTE ..."
git fetch "$UPSTREAM_REMOTE" --quiet

UPSTREAM_REF="$UPSTREAM_REMOTE/main"

# ハーネス層: 安全に上書き可能
HARNESS_PATHS=(
  ".claude/hooks"
  ".claude/skills"
  ".claude/agents"
  ".claude/output-styles"
  "docs/rules"
  "tools"
  "scripts"
  ".github"
  ".gitignore"
  "requirements.txt"
)

# 手動マージ推奨（プロジェクト固有設定が入りうる）
MERGE_REQUIRED=(
  "CLAUDE.md"
  "modules.yaml"
  ".claude/settings.json"
)

# 変更有無を確認
has_changes=false
for path in "${HARNESS_PATHS[@]}"; do
  if ! git diff --quiet HEAD "$UPSTREAM_REF" -- "$path" 2>/dev/null; then
    has_changes=true
    break
  fi
done

echo ""
echo "═══════════════════════════════════════════════════"
echo "  upstream: $UPSTREAM_URL"
echo "  branch:   $UPSTREAM_REF"
echo "═══════════════════════════════════════════════════"

if ! $has_changes; then
  echo ""
  echo "✅ ハーネス層はすでに最新です（変更なし）"
else
  echo ""
  echo "📦 取り込み対象の変更（ハーネス層）:"
  for path in "${HARNESS_PATHS[@]}"; do
    diff_stat=$(git diff HEAD "$UPSTREAM_REF" -- "$path" --stat 2>/dev/null | grep -v "^$" || true)
    if [ -n "$diff_stat" ]; then
      echo ""
      echo "  $path"
      echo "$diff_stat" | sed 's/^/    /'
    fi
  done
fi

echo ""
echo "⚠️  手動マージ推奨（プロジェクト固有設定が含まれる可能性あり）:"
merge_needed=false
for path in "${MERGE_REQUIRED[@]}"; do
  if ! git diff --quiet HEAD "$UPSTREAM_REF" -- "$path" 2>/dev/null; then
    echo "  - $path"
    merge_needed=true
  fi
done
if ! $merge_needed; then
  echo "  なし（変更なし）"
fi

echo ""
echo "🚫 取り込まないファイル（データ層・プロジェクト固有）:"
echo "  raw/  wiki/  ideas/  bookmarks/  content/  docs/project-mission.md"

if $DRY_RUN; then
  echo ""
  echo "✅ --dry-run 完了。実際に取り込むには --dry-run を外して再実行してください。"
  exit 0
fi

if ! $has_changes; then
  exit 0
fi

if ! $YES; then
  echo ""
  read -rp "ハーネス層を取り込みますか？ [y/N] " reply
  if [[ ! $reply =~ ^[Yy]$ ]]; then
    echo "キャンセルしました。"
    exit 0
  fi
fi

# 取り込み実行
echo ""
echo "[sync-upstream] ハーネス層を取り込み中..."
for path in "${HARNESS_PATHS[@]}"; do
  git checkout "$UPSTREAM_REF" -- "$path" 2>/dev/null || true
done

echo ""
echo "✅ ハーネス層を取り込みました"

if $merge_needed; then
  echo ""
  echo "次のステップ（手動マージ推奨ファイルの確認）:"
  for path in "${MERGE_REQUIRED[@]}"; do
    if ! git diff --quiet HEAD "$UPSTREAM_REF" -- "$path" 2>/dev/null; then
      echo "  git diff HEAD $UPSTREAM_REF -- $path"
    fi
  done
fi

echo ""
echo "変更を確認してからコミットしてください:"
echo "  git diff --stat"
echo "  git add -p   # 変更を選択的にステージ"
echo "  git commit -m 'chore: sync harness from upstream claude-wiki-hub'"
