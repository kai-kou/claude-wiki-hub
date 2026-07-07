---
name: retro-try-handler
description: type:retro-try + status:waiting-claude の未対応 Issue（レトロスペクティブが生成した Try アイテム）を自動検出・分類・実装・PR 化するスキル。「retro-try 対応して」「Try Issue を処理して」「レトロスペクティブ結果を反映して」「/retro-try-handler」と依頼された時、または日次の消化スロット（routine-dispatch）から自動起動する時に使用する。
effort: medium
model: haiku
---

# retro-try-handler スキル

`type:retro-try` + `status:waiting-claude` の未対応 Issue を自動処理し、レトロスペクティブが生成した
Try アイテムを実際の改善コードとして反映する。詳細手順は同ディレクトリの `reference.md` を参照。
関連ルールは `docs/rules/retrospective-rules.md`。

## GitHub 操作は MCP が一次経路

GitHub 操作（Issue 取得・ラベル更新・コメント・PR 作成・マージ）は **公式 GitHub MCP（`mcp__github__*`）を
一次経路** とする。クラウドでは `gh` の repo スコープ操作が 403 でブロックされるため（L-114・
`github-mcp-fallback-patterns.md`）。ローカル実行時は `reference.md` の `gh` 例で代替してよい。

## 実行フロー概要

```
Step 0: 作業ブランチ作成
  ↓
Step 1: 未対応 Try Issue の取得・優先度ソート
  ↓
Step 2: Issue を分類（doc / script / validate / skill / user）
  ↓
Step 3: 論理ロック → small/medium を実装（large は計画コメント）
  ↓
Step 4: コミット・push
  ↓
Step 5: PR 作成 → Layer 1 セルフレビュー → 自動マージ
  ↓
Step 6: lessons 昇格 → 完了サマリー（マージ後のみ）
```

---

## Step 0: 作業ブランチ作成

```bash
git branch --show-current
```

`main` または別タスクのブランチにいる場合は作業ブランチを作成する（`session-safety-rules.md` G-1）。

```bash
git fetch origin +main:refs/remotes/origin/main
git checkout -B claude/retro-try-$(date +%Y%m%d) origin/main
```

---

## Step 1: 未対応 Try Issue の取得・ソート

`type:retro-try` + `status:waiting-claude` のオープン Issue を取得する。

```
mcp__github__list_issues(owner="kai-kou", repo="claude-wiki-hub",
  labels=["type:retro-try", "status:waiting-claude"], state="OPEN",
  orderBy="CREATED_AT", direction="ASC")
```

取得後、Claude が本文・ラベルを見て優先度順に並べる。

1. `urgency:blocker` / `dep:blocking` → 最優先
2. `priority:high` → `priority:medium` → `priority:low`
3. 同優先度内は作成日時が古い順（先に発生した問題を先に解消）
4. `urgency:doc-only` のみの Issue は **月曜のみ処理**（火〜日はスキップ）

> 複雑な jq ソート式（ローカル `gh` 版）・doc-only 月曜スキップの詳細・処理量見積もりは
> `reference.md` R1 / R2 を参照。

**対象が 0 件の場合**: 「未対応の Try Issue はありません」と報告して終了する。

---

## Step 2: Issue を分類

各 Issue を本文の「改善施策」「参考ルールファイル」から以下のカテゴリに分類する。

| カテゴリ | 対象ファイル | 例 |
|---------|------------|-----|
| **doc** | `CLAUDE.md` / `docs/rules/*.md` の説明・ルール追記 | ドキュメント更新・ルール追加 |
| **script** | `tools/*.py` / `tools/*.sh` の実装修正 | スクリプトのバグ修正・機能追加 |
| **validate** | `.claude/hooks/*.sh` のチェック追加 | バリデーション追加 |
| **skill** | `.claude/skills/**/SKILL.md` の手順・フロー修正 | スキル手順の改善 |
| **user** | ユーザーの判断・操作が必要（A-1〜A-6 相当） | 実装せず Slack 通知のみ |

**1 セッションの処理上限** はバックログ残件数で動的に調整する（`reference.md` R2）。既定は 2 件。

---

## Step 3: 対応実装

各 Issue の実装前に、**論理ロック** として `status:waiting-claude` → `status:in-progress` に更新する
（並行実行・二重対応を防ぐ・CP-4）。

```
mcp__github__issue_write(method="update", owner="kai-kou", repo="claude-wiki-hub",
  issue_number={N},
  labels=[... "status:waiting-claude" を "status:in-progress" に置換した全ラベル ...])
```

> `labels` は全置換のため、既存ラベルから `status:waiting-claude` を除き `status:in-progress` を
> 加えた完全なリストを渡す。

### 3-A: user カテゴリ（スキップ）

実装せず Slack 通知のみ行う。

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" waiting \
  --issues "[Retro] ユーザー対応が必要な Try Issue: #{N1}, #{N2}" --branch "{current_branch}"
```

### 3-B: large 工数（計画コメントのみ）

実装計画を投稿し `done_type:D-plan` を付与して次回に回す（`status:in-progress` に上げず維持）。

```
mcp__github__add_issue_comment(owner="kai-kou", repo="claude-wiki-hub", issue_number={N},
  body="## 実装計画\n\nこの Try は large のため本セッションでは計画のみ記載します。\n\n### 実装ステップ\n1. ...\n\n### 影響ファイル\n- ...")
```

### 3-C: doc / skill カテゴリ

対象ファイルを **Read** し、Issue の「改善施策」に従って **Edit** で修正する。

- 変更は最小限（Issue で指示されていない箇所は変更しない）
- **1 Issue = 1 コミット** を原則とする
- `.md` を修正したら `python3 tools/check_cjk_markdown.py --fix --changed` を実行する

### 3-D: validate カテゴリ

`.claude/hooks/*.sh` にチェックを追加する。既存パターンを **Read** してから追記し、`bash -n` で構文確認する。

### 3-E: script カテゴリ

`tools/*.py` / `tools/*.sh` を修正する。既存コードを **Read** してから編集し、実行可能なら動作確認する。
`encoding` 未指定・エラー握りつぶし等の `docs/rules/self-review-checklist.md` のパターンに注意する。

---

## Step 4: コミット・push

実装した Issue ごとに個別コミットを作成する。

```bash
git add {変更したファイル}
git commit -m "[Retro] {カテゴリ}: {Issue タイトルの要約}（Closes #{number}）"
git push -u origin {current_branch}
```

同一カテゴリ・全て `small`・ファイル競合なしの複数 Issue は PR バンドルで統合する（`reference.md` R3）。

---

## Step 5: PR 作成・セルフレビュー・自動マージ

**全ての変更は PR を作成して `main` にマージする**（`main` 直 push は禁止・A-1）。

### 5-1: PR 作成

```
mcp__github__create_pull_request(owner="kai-kou", repo="claude-wiki-hub",
  head="{current_branch}", base="main",
  title="[Retro] Try Issue 対応（{N}件）",
  body="## 対応した Try Issue\nCloses #{N1}, #{N2}\n\n## 変更内容\n{変更概要}\n\n## セルフレビュー結果\n{Error 0件 / Warning N件}\n\nSession-Id: {$CLAUDE_CODE_SESSION_ID}")
```

作成後、Slack に PR 作成通知を送る。

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" pr \
  --pr-url "https://github.com/kai-kou/claude-wiki-hub/pull/{pr_number}" \
  --pr-title "[PR作成] [Retro] Try Issue 対応（{N}件）" --branch "{current_branch}"
```

### 5-2: Layer 1 セルフレビュー（必須・外部依頼なし）

`/code-review --comment` を必ず実行する（Layer 1・全 PR 必須）。指摘に対応（修正コミット or スキップ + 返信 + Resolve）する。
❌ Copilot（`request_copilot_review`）・Gemini（`/gemini review`）への依頼はしない（`ai-reviewer-strategy.md`）。

### 5-3: 自動マージ

Layer 0（機械ゲート）+ Layer 1 通過後は即マージしてよい（外部レビュアーの応答待ちはない）。
任意で `mcp__github__subscribe_pr_activity` により CI・人手コメントを監視し、あれば対応してからマージする。

```
mcp__github__merge_pull_request(owner="kai-kou", repo="claude-wiki-hub",
  pullNumber={pr_number}, merge_method="squash")
```

`state=MERGED` を `mcp__github__pull_request_read(method="get")` で確認してから次へ進む（G-3・L-113）。
Issue は PR 本文の `Closes #N` で自動クローズされる（マージ前は `status:in-progress` を維持）。

---

## Step 6: lessons 昇格・完了サマリー（マージ後のみ）

> **完了報告は必ずマージ後に出力する。** マージ前に完了報告を出してはならない（L-056）。

### 6-1: lessons 昇格（昇格 = 物理削除）

対応内容が lessons と対応するか確認し、昇格先へ実装済みなら元エントリを物理削除する。
手順（grep 検索・prune・Warm 層追記）は `reference.md` R4 を参照。

### 6-2: 完了サマリー

```
## retro-try-handler 完了サマリー

### アウトカム（ユーザー視点）
- {このタスクにより何ができるようになったか・何が改善されたか}

### 対応済み Issue
| # | タイトル | カテゴリ | コミット |
|---|---------|---------|---------|

### スキップ（large / user）
| # | タイトル | 理由 |
|---|---------|------|
```

マージ完了後、Slack に完了通知を送る（`--outcome` は初回指示のアウトカム 1 文・`completion-report-rules.md`）。

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" pr \
  --pr-url "https://github.com/kai-kou/claude-wiki-hub/pull/{pr_number}" \
  --pr-title "[完了] [Retro] Try Issue 対応（{N}件）" \
  --outcome "{アウトカム1文}" --branch "{current_branch}"
```

---

## 既存スキルとの関係

| 関連スキル | 関係 |
|-----------|------|
| `retrospective` | Try Issue を生成する上流スキル |
| `self-reviewer` | PR 作成前のセルフレビュー |
| `pr-review-watcher` | PR 作成後のレビュー対応・自動マージ |

エラーハンドリング（Issue 取得失敗・push 失敗のフォールバック等）は `reference.md` R6 を参照。
