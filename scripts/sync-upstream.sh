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

# Hot 層キュレーションの自己修復（#73）: 旧テンプレート由来のリポは .claude/rules/ に
# 全ルールの余剰 symlink を持ち、常駐メモリが Haiku（200k）を超過する。取り込んだ最新の
# check_rules_sync.sh --fix（余剰 prune 対応）で ESSENTIAL_RULES の構成に是正する。
if [ -f "tools/check_rules_sync.sh" ]; then
  echo ""
  echo "[sync-upstream] .claude/rules/ の Hot 層キュレーションを同期中..."
  # ブロッキング化（Haiku Context Overflow 追跡調査・議論 haiku-context-overflow-followup）:
  # 失敗を警告のみで握りつぶすと「同期成功」の誤信のまま余剰 symlink（Haiku 200k 超過）が
  # 温存されうる。失敗時は exit 1 でユーザーに気付かせる。
  if rules_sync_out="$(bash tools/check_rules_sync.sh --fix 2>&1)"; then
    echo "$rules_sync_out"
    # 旧方式（ESSENTIAL_RULES 直接編集）で Hot 化していた symlink は、直前の tools/ 上書きで
    # リストから消えた直後にここで剪定される。意図した Hot 化の復活手順を必ず案内する（#73）
    if echo "$rules_sync_out" | grep -q "余剰 symlink を削除"; then
      echo "ℹ️ [sync-upstream] 剪定されたルールを Hot 層に残したい場合は .claude/rules-extra.conf にファイル名を 1 行追加して ./tools/check_rules_sync.sh --fix を再実行してください。"
    fi
  else
    # 失敗時の詳細出力はエラー文脈として stderr に寄せる（Copilot レビュー指摘・#75）
    echo "$rules_sync_out" >&2
    echo "❌ [sync-upstream] .claude/rules/ の同期に失敗しました。Hot 層が Haiku(200k)常駐上限を超過したままの可能性があります。手動で ./tools/check_rules_sync.sh --fix を実行し成功を確認してから再実行してください。" >&2
    exit 1
  fi
fi

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
