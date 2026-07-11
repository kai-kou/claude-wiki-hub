#!/usr/bin/env bash
# check_rules_sync.sh
# docs/rules/ と .claude/rules/ の同期状態を検証するスクリプト
#
# 使い方:
#   ./tools/check_rules_sync.sh          # 不足・リンク切れ・余剰 symlink を報告して終了コードで示す
#   ./tools/check_rules_sync.sh --fix    # 不足 symlink を作成・リンク切れと余剰 symlink を削除する
#
# 終了コード:
#   0: 全ファイルが同期済み
#   1: 不足・リンク切れ・余剰あり（--fix なしの場合）
#
# 「余剰 symlink」= docs/rules/ を指すのに ESSENTIAL_RULES に含まれない symlink（#73）。
# .claude/rules/ の常駐ファイルはセッション開始時に全てメモリとしてロードされるため、
# 全ルールを symlink すると CLAUDE.md 込みで ~213k tok となり Haiku（200k）が溢れる。
# --fix が prune するのは docs/rules/ を指す symlink のみで、実ファイル・docs/rules/ 以外を
# 指す symlink はプロジェクト独自ルールとして温存する。

set -euo pipefail

# pwd -P: 物理パスで解決する。論理 pwd のままだとリポジトリを symlink 経由で開いたとき
# （例: macOS の /tmp → /private/tmp）余剰判定の実体パス比較が常に不一致になり剪定が無効化する（#73）
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
DOCS_RULES="$REPO_ROOT/docs/rules"
CLAUDE_RULES="$REPO_ROOT/.claude/rules"
FIX_MODE=false

if [[ "${1:-}" == "--fix" ]]; then
  FIX_MODE=true
fi

missing=()
broken=()
extra=()
mispointed=()

# トークン最適化: .claude/rules/ に配置するのは「常時必要」なルールのみ。
# タスク依存のルールは docs/rules/ に実体のみ配置し、スキルが必要時に Read する。
# この ESSENTIAL_RULES リストに含まれないファイルは .claude/rules/ に symlink を作成しない。
ESSENTIAL_RULES=(
  "completion-report-rules.md"
  "core-principles.md"
  "wiki-operations.md"
  "intent-routing.md"
  "datetime-rules.md"
  "lessons-core.md"
  "pr-review-flow-summary.md"
  "session-safety-rules.md"
  "session-sprint-rules.md"
  "user-confirmation-minimization.md"
)

# プロジェクト独自の Hot 層追加（#73）: 本スクリプトは upstream 同期（sync-upstream.sh の
# HARNESS_PATHS "tools"）で上書きされるため、ESSENTIAL_RULES への直接追記はフォークでは
# 同期のたびに消える。フォークが Hot 層へ常駐させたいルールは同期対象外の設定ファイル
# .claude/rules-extra.conf（1 行 1 ファイル名・# コメント可）に書く。
EXTRA_ESSENTIAL_FILE="$REPO_ROOT/.claude/rules-extra.conf"
if [[ -f "$EXTRA_ESSENTIAL_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line//[[:space:]]/}"
    [[ -n "$line" ]] || continue
    # typo や docs/rules 未配置のエントリは symlink が作られず Hot 化が無音で失敗するため警告する
    if [[ ! -f "$DOCS_RULES/$line" ]]; then
      echo "[WARN] rules-extra.conf のエントリ '$line' は docs/rules/ に存在しません（typo の可能性・symlink は作成されません）" >&2
    fi
    ESSENTIAL_RULES+=("$line")
  done < "$EXTRA_ESSENTIAL_FILE"
fi

# Warm 降格済み（既定では Hot 層に常駐させない）:
#   - progress-reporting-rules.md: 制作系の長時間処理を行うときに該当パイプラインスキルが冒頭で Read する
#   - session-concurrency-rules.md: Scheduled Tasks（マルチセッション並行運用）を使うプロジェクトのみ symlink する
#   - ai-reviewer-strategy.md: Warm 降格済み（#88）。現行 FAIR 構成の要点は圧縮版 + pr-review-flow-summary.md に記載
#   - autonomous-operation-policy.md: Warm 降格済み（#89）。user-confirmation-minimization.md / core-principles.md と大幅重複
#   - session-sprint-rules-detail.md: session-sprint-rules.md の詳細版（Warm 専用・#90）
#   - session-safety-rules-detail.md: session-safety-rules.md の詳細版（Warm 専用・#91）
#   - user-notification-triage.md: Warm 降格済み（#69）。Slack @mention 発火時のみ Read。境界の SSOT は user-confirmation-minimization.md（常駐）
#   - no-github-actions.md: Warm 降格済み（#69）。.github/workflows 編集時のみ。pre-tool-use-router.sh が警告し CLAUDE.md にも要点あり
#   - agent-team-summary.md: Warm 降格済み（#69）。サブエージェント/専門チーム使用時のみ Read
#   - user-instruction-issue-rules.md: Warm 降格済み（#69）。ユーザー指示の Issue 化時のみ Read。要点は intent-routing.md R-3（常駐）
# これらを Hot 層に戻したいプロジェクトは .claude/rules-extra.conf に 1 行追加して --fix を実行する
# （upstream 同期で消えない。本ファイルの ESSENTIAL_RULES 直接追記は同期で上書きされるため非推奨）。

# symlink の実体絶対パス（物理）を解決する。readlink -f は BSD readlink（macOS 12.3 未満）に
# 存在しないため、readlink（1 ホップ）+ cd/pwd -P の POSIX 構成で解決する（#73 レビュー指摘）。
resolve_link_physical() {
  local link="$1" target dir
  target="$(readlink "$link")" || return 1
  case "$target" in
    /*) : ;;
    *) target="$(dirname "$link")/$target" ;;
  esac
  dir="$(cd "$(dirname "$target")" 2>/dev/null && pwd -P)" || return 1
  printf '%s/%s\n' "$dir" "$(basename "$target")"
}

# ESSENTIAL_RULES に含まれるファイルのみを同期対象にする（トークン最適化）
is_essential() {
  local filename_to_check="$1"
  for ess in "${ESSENTIAL_RULES[@]}"; do
    if [[ "$filename_to_check" == "$ess" ]]; then
      return 0
    fi
  done
  return 1
}

for docs_file in "$DOCS_RULES"/*.md; do
  filename="$(basename "$docs_file")"
  is_essential "$filename" || continue  # 常時必要なファイルのみチェック

  claude_target="$CLAUDE_RULES/$filename"

  if [[ ! -e "$claude_target" ]]; then
    if [[ -L "$claude_target" ]] && ! $FIX_MODE; then
      # 検証モードのリンク切れ symlink は後半の逆方向チェックが [BROKEN] として報告する
      # （ここで [MISSING] も出すと同一ファイルを二重カウントするため委ねる）
      continue
    fi
    missing+=("$filename")
    if $FIX_MODE; then
      # -f: 宛先がリンク切れ symlink（-e は false になる）でも上書きして自己修復する。
      # 実ファイルが存在する場合は上の [[ ! -e ]] ガードでこの分岐に入らないため上書きされない。
      ln -sf "../../docs/rules/$filename" "$claude_target"
      echo "[FIXED] シンボリックリンクを作成: .claude/rules/$filename"
    else
      echo "[MISSING] .claude/rules/$filename が存在しません"
    fi
  fi
done

# 逆方向チェック: .claude/rules/ 側の異常（リンク切れ・ESSENTIAL_RULES 外の余剰 symlink）
for claude_file in "$CLAUDE_RULES"/*.md; do
  filename="$(basename "$claude_file")"

  # シンボリックリンクのリンク先が存在するか確認
  if [[ -L "$claude_file" ]] && [[ ! -e "$claude_file" ]]; then
    echo "[BROKEN] .claude/rules/$filename はリンク切れのシンボリックリンクです"
    broken+=("$filename")
    if $FIX_MODE; then
      rm "$claude_file"
      echo "[FIXED] リンク切れを削除: .claude/rules/$filename"
    fi
    continue
  fi

  # essential symlink の誤ポイント検出（#73）: 名前は essential なのに実体が別ファイルを
  # 指していると、誤った内容が essential 名で常駐する。正しい実体に張り直す。
  # （実ファイルで置き換えている場合はプロジェクトの意図的な上書きとして温存する）
  if [[ -L "$claude_file" ]] && is_essential "$filename"; then
    target_abs="$(resolve_link_physical "$claude_file" || true)"
    if [[ -n "$target_abs" && "$target_abs" != "$DOCS_RULES/$filename" ]]; then
      mispointed+=("$filename")
      if $FIX_MODE; then
        ln -sf "../../docs/rules/$filename" "$claude_file"
        echo "[FIXED] 誤った実体を指す essential symlink を張り直し: .claude/rules/$filename"
      else
        echo "[MISPOINTED] .claude/rules/$filename が $target_abs を指しています（期待: docs/rules/$filename）"
      fi
    fi
    continue
  fi

  # 余剰 symlink の剪定（#73）: docs/rules/ 配下を指すのに ESSENTIAL_RULES 外のものは
  # Hot 層キュレーション対象外（常駐メモリ肥大 = Haiku 200k 超過の原因）なので削除する。
  # 実ファイル・docs/rules/ 外を指す symlink はプロジェクト独自ルールとして温存する。
  # 判定は物理パス比較で行う（"my-docs/rules/" 等の suffix 誤マッチ防止。
  # リンク切れは前段で処理済みなのでここに来る symlink は必ず解決できる）。
  if [[ -L "$claude_file" ]] && ! is_essential "$filename"; then
    target_abs="$(resolve_link_physical "$claude_file" || true)"
    if [[ -n "$target_abs" && "$target_abs" == "$DOCS_RULES"/* ]]; then
      extra+=("$filename")
      if $FIX_MODE; then
        rm "$claude_file"
        echo "[FIXED] ESSENTIAL_RULES 外の余剰 symlink を削除: .claude/rules/$filename（実体は docs/rules/ に残る）"
      else
        echo "[EXTRA] .claude/rules/$filename は ESSENTIAL_RULES 外の余剰 symlink です（常駐トークン浪費・#73）"
      fi
    fi
  fi
done

# --- Hot 層サイズガード（Haiku Context Overflow 再発防止・haiku-context-overflow-followup 議論）---
# ESSENTIAL_RULES を全て symlink しても、CLAUDE.md + Hot 層の合計文字数自体が大きいと
# Haiku(200k)の常駐マージンを圧迫する（余剰 symlink 剪定だけでは解消しない独立リスク）。
# 保守的なトークン推定（CJK×1.5 + EN×0.40・議論の token-budget-forensics 実測係数）で
# 閾値超過を警告する（exit code には影響させない・既存の symlink 同期チェックとは別軸）。
if command -v python3 &>/dev/null; then
  if ! python3 - "$REPO_ROOT" <<'PYEOF'
import sys, re, glob, os
repo_root = sys.argv[1]
paths = [os.path.join(repo_root, "CLAUDE.md")] + glob.glob(os.path.join(repo_root, ".claude/rules/*.md"))
combined = ""
for p in paths:
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="ignore") as f:
            combined += f.read()
cjk = len(re.findall(r'[　-鿿＀-￯]', combined))
en = len(combined) - cjk
tok_conservative = cjk * 1.5 + en * 0.40
THRESHOLD = 50000
if tok_conservative > THRESHOLD:
    print(f"[WARN] Hot 層（CLAUDE.md + .claude/rules/）推定 {tok_conservative:.0f} tok（保守推定）が閾値 {THRESHOLD} tok を超過しています。Haiku(200k)の常駐マージンが薄い可能性があります。docs/rules/ の内容圧縮・Warm 降格を検討してください。", file=sys.stderr)
else:
    print(f"[OK] Hot 層サイズ: 推定 {tok_conservative:.0f} tok（保守推定・閾値 {THRESHOLD} tok 以下）")
PYEOF
  then
    # サイレント失敗防止（Copilot レビュー指摘）: exit code は維持しつつ推定できなかったことを可視化する
    echo "[WARN] Hot 層サイズ推定の実行に失敗しました（python3 エラー）。手動で内容量を確認してください。" >&2
  fi
else
  echo "[WARN] python3 が見つからないため Hot 層サイズ推定をスキップしました。" >&2
fi

if [[ ${#missing[@]} -eq 0 && ${#broken[@]} -eq 0 && ${#extra[@]} -eq 0 && ${#mispointed[@]} -eq 0 ]]; then
  echo "[OK] docs/rules/ と .claude/rules/ は同期されています"
  exit 0
else
  if $FIX_MODE; then
    echo "[OK] 不足 ${#missing[@]} 件を作成、リンク切れ ${#broken[@]} 件・余剰 ${#extra[@]} 件を削除、誤ポイント ${#mispointed[@]} 件を張り直しました"
    exit 0
  else
    total=$(( ${#missing[@]} + ${#broken[@]} + ${#extra[@]} + ${#mispointed[@]} ))
    echo "[NG] 不足 ${#missing[@]} 件 / リンク切れ ${#broken[@]} 件 / 余剰 ${#extra[@]} 件 / 誤ポイント ${#mispointed[@]} 件（合計 ${total} 件）"
    echo "自動修正するには: ./tools/check_rules_sync.sh --fix"
    exit 1
  fi
fi
