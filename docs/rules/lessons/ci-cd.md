# Warm 層 教訓 — CI / CD・フック

CI / CD・フック運用に関するカテゴリ別教訓（タスク依存で Read）。

---

## L-023: CI 失敗は自律修正する・フックを `--no-verify` で bypass しない（2026-06-13）

**パターン**: ① CI（本プロジェクトでは self-reviewer のワークツリー隔離 e2e）が失敗したとき、ログを読まずユーザーに「直してよいか」と確認に回す。
② コミットが Lv3 フック（pre-commit / pre-push）でブロックされた際、`git commit --no-verify` /
`git push --no-verify` でフックを **bypass** して回避する。

**根本原因**: CI 失敗・フックブロックを「ユーザー判断が必要な障害」と誤分類している（実際は
Claude が自律修正すべき作業）。フック bypass は品質ゲートの無効化であり、ハードコンストレイント
（Lv3）の意味を失わせる。

**対策**:
- CI 失敗時はログを読んで根本原因を特定し **自律修正** する（ユーザー確認不要・CP-1 / `core-principles.md` 自律実行表）
- フックブロックは正規の手順で解消する。`--no-verify` での bypass は **禁止**

**禁止 → 推奨**:
```
❌ git commit --no-verify / git push --no-verify でフックを回避
❌ CI 失敗を理由にユーザー確認へ丸投げ
✅ フックの指摘を解消してから再コミット
✅ CI ログ → 根本原因特定 → 修正 → 再実行（自律）
```

---

## L-NGA: GitHub Actions を使わない（CI は Claude Code ハーネスで代替・2026-06-26）

**背景**: 飼い主は複数リポジトリで GitHub Actions を多用しており、Actions の実行枠（アカウント共有の無料分数）がすぐ枯渇する。1 リポで Actions を増やすと他リポの CI まで止まる。

**方針**: 本プロジェクト（およびフォーク先）では **`.github/workflows/*.yml` を新規追加・利用しない**。SSOT は `docs/rules/no-github-actions.md`（Hot 層 symlink）。

**代替**:
- push/PR 時の自動テスト → **PR 作成前に self-reviewer がワークツリー隔離サブエージェントで `bash scripts/run-e2e.sh` を実行**（FAIL なら自己修正ループ・ブロックしない）
- 定期実行 → Claude Code ネイティブのルーティン機能（`docs/automation/routines.md`）
- 再発防止 → `pre-tool-use-router.sh` が `.github/workflows/*.yml` の Write/Edit を非ブロッキング警告

**禁止 → 推奨**:
```
❌ .github/workflows/ に CI ワークフローを追加する
✅ self-reviewer のワークツリー隔離 e2e ＋ フック ＋ ルーティンで CI を代替
```

---

## L-MCP-GATE: MCP 経由 PR 作成が PreToolUse ゲートを素通りする（2026-06-26）

**症状**: クラウドセッションで作成した PR で、Layer 0 機械ゲート（`self_review_check.py`）と
Layer 1 セルフレビュー（FAIR・全PR必須）が **発火せずスキップ** される。未コミット検出も働かない。

**根本原因**: `pre-pr-create-check.sh`（PR 作成前ゲート）は `PreToolUse` フックだが、
`.claude/settings.json` の matcher が `Bash|Write|Edit|MultiEdit` のみで、
`mcp__github__create_pull_request` を捕捉していなかった。クラウド環境では `gh pr create` が
proxy の GraphQL 403 で失敗するため PR 作成は **MCP ツールが主経路** になるが、その経路が
matcher 外だったため Layer 0 ゲート・未コミットチェック・Layer 1 リマインダーを **完全素通り** していた。
`gh pr create` 前提のガードがクラウドの実経路（MCP）とズレていた（L-094 型 desync）。

**対策**（実装済み・本セッション）:
- `settings.json` の `PreToolUse` matcher に `mcp__github__create_pull_request` を追加
- `pre-tool-use-router.sh` が MCP PR 作成を `pre-pr-create-check.sh` へ委譲
- `pre-pr-create-check.sh` が Bash `gh pr create` と MCP PR 作成の両方でゲート（git-clean +
  `self_review_check.py` + Layer 1 リマインダー）を実行

**禁止 → 推奨**:
```
❌ PR 作成前ガードを Bash の gh pr create だけ前提にする（クラウドは MCP が主経路）
✅ PR 作成の全経路（Bash gh pr create / mcp__github__create_pull_request）を matcher・router で捕捉する
```

**判定基準**: 「クラウドで動く実経路（MCP）と、ローカル前提のガード（Bash）がズレていないか」を
新しいガードを足すたびに確認する。`docs/rules/ai-reviewer-strategy.md`「Layer 1 の実行」も参照。
