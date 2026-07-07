---
name: project-sync
description: リポジトリ衛生管理スキル。Stale Issue（4時間超 in-progress）検出・Orphan PR（24時間超放置）解消・Abandoned ブランチ検出・ログ衛生スナップショット・lessons Hot 層ガードを Claude が GitHub MCP で直接実行する。「project-sync して」「リポジトリを整理して」「/project-sync」で起動する。
effort: low
model: haiku
---

# project-sync スキル

GitHub Issues / PR / ブランチの衛生状態を自動点検・修正するメンテナンススキル。
**CP-3（リポジトリの衛生管理）** に基づき、放置された Issue・PR・ブランチを検出して解消する。

## 実行モデル（Claude が MCP で直接実行する単層構成）

本スキルは **Claude が GitHub MCP（`mcp__github__*`）・実在ツール・git で直接実行する手順** のみで構成される。
専用の Python オーケストレーター（旧 `sync_project.py`）は持たない。GitHub 操作はクラウドで 403 になる
`gh` の repo スコープ操作を避け、MCP を一次経路とする（L-114・`github-mcp-fallback-patterns.md`）。
ローカル実行時は各手順に併記した `gh` 例で代替してよい。

## トリガー

- `/project-sync` コマンドで手動実行
- 「project-sync して」「リポジトリを整理して」

> 定期自動実行は Claude Code ネイティブのルーティン（`config/routine_jobs.yaml` / routine-dispatch・
> `docs/automation/routine-dispatch.md`）で回す。衛生ジョブを定期化する場合は同 YAML に job を追加する
> （現時点では未登録・手動起動が既定）。

## 前提条件

- GitHub MCP（`mcp__github__list_issues` / `issue_write` / `list_pull_requests` 等）が利用可能なこと
- 作業ブランチで実行すること（`main` への直接 push はしない・A-1）

## 実行フロー

```
Step 1: Stale Issue 検出・リセット（in-progress 4時間超）
  ↓
Step 2: ラベル不整合の是正（status: 二重付与の除去）
  ↓
Step 3: waiting-user 誤分類の再分類（user-confirmation-minimization.md §5）
  ↓
Step 4: Orphan PR 検出（24時間超放置）
  ↓
Step 5: Abandoned ブランチ検出（月曜のみ・リスト出力）
  ↓
Step 6: ログ衛生スナップショット + lessons Hot 層ガード
  ↓
Step 7: 衛生レポート出力
```

## Step 1: Stale Issue 検出・リセット

`status:in-progress` のオープン Issue を取得し、**最終更新が 4 時間以上前** のものを検出する。
別セッションがスタックした論理ロックとみなし、`status:waiting-claude` にリセットする。

```
mcp__github__list_issues(owner="kai-kou", repo="claude-wiki-hub",
  labels=["status:in-progress"], state="OPEN",
  orderBy="UPDATED_AT", direction="ASC")
```

各 Issue の `updatedAt` が現在時刻（UTC 内部計算）から 4 時間超なら:

```
mcp__github__issue_write(method="update", owner="kai-kou", repo="claude-wiki-hub",
  issue_number={N},
  labels=[... "status:in-progress" を "status:waiting-claude" に置換した全ラベル ...])
```

> `issue_write` の `labels` は **全置換** のため、既存ラベルから `status:in-progress` を除き
> `status:waiting-claude` を加えた完全なリストを渡す。直近まで動いていた自セッションのロックは
> リセットしない（10 分ルール・`session-concurrency-rules.md`）。
> ローカル代替: `gh issue edit {N} --remove-label status:in-progress --add-label status:waiting-claude -R kai-kou/claude-wiki-hub`

## Step 2: ラベル不整合の是正

同一 Issue に `status:` ラベルが **2 つ以上** 付与されている場合、実態に合う 1 つだけを残す。
`get_labels` で確認し、余分な `status:` を除いたラベルセットで `issue_write(update)` する。

## Step 3: waiting-user 誤分類の再分類（§5 連携）

`status:waiting-user` のオープン Issue を全件取得し、`user-confirmation-minimization.md` §5 の
C カテゴリ（ルール整備で自律処理可能）に該当するものを再分類する。**動画・採番運用のプレースホルダは扱わない。**

```
mcp__github__list_issues(owner="kai-kou", repo="claude-wiki-hub",
  labels=["status:waiting-user"], state="OPEN")
```

| 検出パターン | 処理 |
|------------|------|
| 定期レポート系タイトル（例: `[週次レポート]`）で 7 日以上更新なし | Slack 通知済みとみなし「7日経過のため自動クローズ」コメント → クローズ（上限 3 件/回） |
| 自律実行可能なタスク（例: リサーチ実行依頼）が waiting-user 誤分類 | `status:waiting-user` を除去し `status:waiting-claude` を付与（担当スキルが自律実行） |
| 本文に「ローカル実行が必要」を含む | §4 のクラウド実行可能リソースに該当するか注記コメント（自動クローズはしない・B カテゴリ振替候補） |

処理結果を「誤分類リセット: report-close N件 / phase-reset N件 / local-flag N件」の形で出力する。

## Step 4: Orphan PR 検出

24 時間以上更新のない放置 PR を検出し、pr-review-watcher フローに復帰させる。

```
python3 tools/check_pending_pr_reviews.py --actionable-only --json
```

- `needs_response`（AI レビュー指摘・CI 失敗が未対応）→ pr-review-watcher のフローで指摘対応 → マージ
- `awaiting_review`（レビュー未着）→ 作成セッションが対応中なら待機。24h 超なら `/code-review` を実行して自マージ
- `active_session=true` の PR は別セッションが現役対応中のため介入しない（CP-4・除外済み）

## Step 5: Abandoned ブランチ検出（月曜のみ）

`main` にマージ済みのリモートブランチを削除候補としてリスト出力する（**自動削除はしない**・ユーザー判断）。

```bash
git fetch origin +main:refs/remotes/origin/main
git branch -r --merged origin/main | grep -v -E 'origin/main$|origin/HEAD'
```

## Step 6: ログ衛生スナップショット + lessons Hot 層ガード

```bash
python3 tools/log_hygiene_snapshot.py --slot "project-sync" --slack
python3 tools/lessons_guard.py check
```

- `log_hygiene_snapshot.py`: 衛生指標を `content/pipeline-state/snapshots/` に永続化し、
  滞留閾値超過（waiting-claude 過多・最古 7 日超・Orphan PR）で Slack アラートを出す。
- `lessons_guard.py check`: Hot 層（`lessons-core.md`）が上限内かを検証する（超過で exit 1）。
  超過時は `python3 tools/lessons_guard.py prune --apply` で昇格済みエントリを物理削除する
  （SSOT: `lessons-management.md`）。

## Step 7: 衛生レポート出力

以下の衛生指標をまとめて出力する（`log_hygiene_snapshot.py` の出力も参照）。

```
リポジトリ衛生レポート:
- オープン Issue 数 / status 別内訳（in-progress・waiting-claude・waiting-user・blocked）
- 最古 waiting-claude の滞留日数
- オープン PR 数（うち Orphan）
- マージ済み未削除ブランチ数（月曜のみ）
- lessons Hot 層: 上限内 / 超過（超過時は prune 実行）
```

## 完了条件

- 4 時間超の `status:in-progress` がゼロ（全て `waiting-claude` にリセット済み）
- Orphan PR が全て検出・対応されている
- （月曜）Abandoned ブランチがリスト化されている
- ログ衛生スナップショット・lessons ガードが実行されている
- 記載した全コマンド・参照ファイルが実在し、クラウドセッションで手順どおり最後まで実行できる

## 検知・修正の対象外

| ケース | 対応方法 |
|--------|---------|
| バックログ分類の優先順位付け（`priority:*` / `sp:*`） | `owner` サブエージェント（PO ロール）が担当 |
| Issue の実装・クローズ判断 | 各パイプラインスキル・`next` スキルが担当 |

## 既存スキルとの関係

| 関連スキル | 関係 |
|-----------|------|
| `pr-review-watcher` | Orphan PR（Step 4）の指摘対応・自動マージを担う |
| `workflow-health-check` | ワークフロー健全性の詳細監査（本スキルは軽量な衛生に特化） |
| `waiting-user-handler` | waiting-user Issue の深いトリアージ（本スキルは §5 の機械的再分類のみ） |
