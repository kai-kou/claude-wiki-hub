---
name: retro-try-handler
description: type:retro-try ラベル（およびプロジェクト定義の更新系ラベル）の未対応 GitHub Issue を自動検出・分類・実装・PR 化するスキル。レトロスペクティブスキルが生成した Try アイテムを実際の改善コードとして反映する。
when_to_use: 「retro-try 対応して」「Try Issue を処理して」「/retro-try-handler」と依頼された時、または日次の消化スロット（プロジェクト定義）から自動起動する時に使用する。
effort: medium
model: haiku
---

# retro-try-handler スキル

`type:retro-try` + `status:waiting-claude` の未対応 Issue を自動処理する。
詳細ルールは `docs/rules/retrospective-rules.md` を参照。

## トリガー条件

- 「retro-try 対応して」「Try Issue を処理して」「レトロスペクティブ結果を反映して」
- `/retro-try-handler`
- 日次の消化スロット（プロジェクト定義）+ 週次の{親ワークフロー}（プロジェクト定義）内からの呼び出し

## 前提条件

- GitHub MCP (`mcp__github__issue_write`, `mcp__github__issue_read`) が利用可能なこと
- GitHub CLI `gh` がインストールされており、認証済みであること（`gh auth status` で確認）
- 作業ブランチ（`claude/retro-try-*`）を新規作成してから作業を開始すること

## 実行フロー概要

```
Step 0: ブランチ確認・作業ブランチ作成
  ↓
Step 1: 未対応 Try Issue の取得・ソート
  ↓
Step 2: Issue を分類（ドキュメント / スクリプト / バリデーション / スキル / ユーザー対応）
  ↓
Step 3: small / medium を優先実装（large はコメントのみ）
  ↓
Step 4: コミット・push
  ↓
Step 5: 実装済み Issue をクローズ
  ↓
Step 6: 完了サマリー出力
```

---

## Step 0: ブランチ確認・作業ブランチ作成

```bash
git branch --show-current
```

`main` または別タスクのブランチにいる場合は、新しいブランチを作成する。

```bash
git checkout main && git pull origin main
git checkout -b claude/retro-try-handler-{session_id}
```

> `{session_id}` は日付形式（例: `20260401`）を使用する。スケジューラー起動の場合は `$(date +%Y%m%d)` で取得できる。

---

### ルールファイル読み込み（トークン最適化対応）

以下のルールファイルを `docs/rules/` から Read する（`.claude/rules/` から削除済みのため自動読み込みされない）。

- `docs/rules/self-review-learnings.md`（過去のレビュー学習内容）

---

## Step 1: 未対応 Issue の取得・ソート

以下の **2 種類** の Issue を対象とする。

### 1-A: レトロスペクティブ Try Issue（従来）

```bash
gh issue list -R kai-kou/claude-wiki-hub \
  --label "type:retro-try" \
  --label "status:waiting-claude" \
  --state open \
  --limit 1000 \
  --json number,title,labels,body,createdAt \
  --jq 'sort_by([
    (if ([.labels[].name] | index("urgency:blocker"))   then 0
     elif ([.labels[].name] | index("dep:blocking"))    then 1
     elif ([.labels[].name] | index("urgency:quality")  and ([.labels[].name] | index("priority:high")))   then 2
     elif ([.labels[].name] | index("urgency:process")  and ([.labels[].name] | index("priority:high")))   then 3
     elif ([.labels[].name] | index("urgency:quality")  and ([.labels[].name] | index("priority:medium"))) then 4
     elif ([.labels[].name] | index("urgency:process")  and ([.labels[].name] | index("priority:medium"))) then 5
     elif ([.labels[].name] | index("urgency:doc-only")) then 99
     else (if ([.labels[].name] | index("priority:high")) then 50
           elif ([.labels[].name] | index("priority:medium")) then 51
           elif ([.labels[].name] | index("priority:low")) then 52
           else 53 end) end),
    .createdAt
  ])'
```

> **urgency ラベルが付与されていない Issue（旧形式）**: urgency ラベルなしの場合は priority:high→50、medium→51、low→52、未設定→53 のフォールバックとして扱う。urgency ラベルが付与されている Issue が優先処理される。

### doc-only Issue の月曜スキップルール

`urgency:doc-only` のみが対象の場合、**月曜日のみ処理** する（火〜日はスキップ）。

```bash
# 現在の曜日を確認（月曜=Monday、LC_ALL=C でロケール非依存）
day_of_week=$(TZ=Asia/Tokyo LC_ALL=C date '+%A')

# doc-only Issue を除外するフィルタ（火〜日に適用）
if [ "$day_of_week" != "Monday" ]; then
  # urgency:doc-only の Issue はソート後に除外
  ISSUES=$(gh issue list -R kai-kou/claude-wiki-hub \
    --label "type:retro-try" \
    --label "status:waiting-claude" \
    --state open \
    --limit 1000 \
    --json number,title,labels,body,createdAt \
    --jq '[.[] | select([.labels[].name] | index("urgency:doc-only") | not)] | sort_by([...])')
else
  # 月曜: doc-only を含む全 Issue を取得
  ISSUES=$(gh issue list -R kai-kou/claude-wiki-hub \
    --label "type:retro-try" \
    --label "status:waiting-claude" \
    --state open \
    --limit 1000 \
    --json number,title,labels,body,createdAt \
    --jq 'sort_by([...])')
fi
```

**理由**: `doc-only` は説明文の修正のみで品質・プロセスに影響しない。毎日処理する必要はなく、月曜のまとめ処理で効率的に対応する。

### 1-B: 更新系 Issue（プロジェクト定義の更新ラベル）

> **プロジェクトで定義する**。上流スキル（例: ツール調査・ドメインリサーチ系スキル）が生成する「更新系」Issue を、プロジェクトが定義する `feat:*-update` ラベルで取得する。下記は汎用テンプレート。各プロジェクトは自分のドメインに合わせて更新カテゴリ（例: ツール更新 / ドメイン更新 / 戦略更新）とラベルを定義する。

```bash
# プロジェクト定義の更新ラベルごとに取得（{更新ラベル} を差し替える）
gh issue list -R kai-kou/claude-wiki-hub \
  --label "{更新ラベル}" \
  --label "status:waiting-claude" \
  --state open \
  --limit 1000 \
  --json number,title,labels,body,createdAt
```

代表的な更新カテゴリの例（プロジェクト定義）:

| カテゴリ（例） | ラベル（例） | 対象 |
|--------------|------------|------|
| ツール/SDK 更新 | `feat:tool-update` | Claude Code / 利用 SDK の新機能・破壊的変更 |
| 制作ツール更新 | `feat:dev-tool-update` | プロジェクト定義の制作ツール（例: 音声合成 / 動画レンダリング）・依存ライブラリの更新 |
| ドメイン/戦略更新 | `feat:domain-update` | 配信先・マーケ・ドメイン固有の戦略変更 |

**処理優先順位**:
1. ツール/SDK 更新 + `priority:high`（Breaking Change）
2. 制作ツール更新 + `priority:high`（重大な破壊的変更・セキュリティ修正）
3. ドメイン/戦略更新 + `priority:high`（重要な戦略変更）
4. `type:retro-try` + `priority:high`
5. 上記以外は通常の優先度順（priority:medium → priority:low）

### ソート順

1. `priority:high` → `priority:medium` → `priority:low`
2. 同優先度内は作成日時が古い順（先に発生した問題を先に解消）

### 対象なしの場合

```
未対応の retro-try Issue はありませんでした。
（type:retro-try + status:waiting-claude が 0 件）
```

を出力して終了する。

---

## Step 2: Issue を分類

各 Issue を以下のカテゴリに分類する。
本文の「改善施策」セクションと「参考ルールファイル」セクションを読んで判断する。

| カテゴリ | 対象ファイル | 例 |
|---------|------------|-----|
| **doc** | `CLAUDE.md` / `docs/rules/*.md` / `SKILL.md` の説明・ルール追記 | ドキュメント更新、ルール追加 |
| **script** | `tools/*.py` / `tools/*.sh` の実装修正 | スクリプトのバグ修正、機能追加 |
| **validate** | `.claude/hooks/post-tool-use-validate.sh` のチェック追加 | バリデーション追加 |
| **skill** | `.claude/skills/**/SKILL.md` の手順・フロー修正 | スキル手順の改善 |
| **user** | `assignee:user` の Issue | ユーザー通知のみ（実装はしない） |
| **tool-update** | `docs/rules/claude-code-optimization.md` / `CLAUDE.md` など | Claude Code/SDK 新機能の反映 |
| **dev-tool** | プロジェクト定義の制作ツール関連ルール（例: レンダリング/音声合成のルールファイル） | 制作ツール更新の反映 |
| **domain** | プロジェクト定義の戦略・リサーチドキュメント / 設定ファイル（例: `config/*.yaml`） | ドメイン固有の戦略・配信戦略の更新 |

### 1回のセッションで対応できる量の見積もり

**動的処理上限（バックログ残件数に応じて調整）**:

| バックログ残件数 | 1セッションの処理上限 | 理由 |
|--------------|-------------------|------|
| 0〜9件 | 2件 | 通常運用 |
| 10〜19件 | 3件 | 消化ペース加速 |
| 20〜29件 | 4件 | バックログ圧縮モード |
| 30件以上 | 5件 | 最大スループット（セッション安全ルール優先） |

> **セッション安全ルール（L-022）**: 1ターンのツール呼び出しは 8 個以内。処理上限を増やすときは中間報告を挟んで複数ターンに分散する。

**推定工数ごとの処理方針**:

| 推定工数 | 対応方針 |
|---------|---------|
| `small` | 処理上限まで実装する（同カテゴリは PR バンドル候補） |
| `medium` | 1〜2件まで実装する（残りは次回） |
| `large` | 実装計画コメントを投稿し `done_type:D-plan` ラベルを付与して次回に回す |

---

## Step 3: 対応実装

各 Issue の実装を開始する前に、**論理ロック** として `status:waiting-claude` → `status:in-progress` に更新する。
これにより並行実行・二重対応を防ぐ（週次スケジューラーと手動実行が重複する場合に有効）。

```bash
gh issue edit {number} \
  --remove-label "status:waiting-claude" \
  --add-label "status:in-progress" \
  -R kai-kou/claude-wiki-hub
```

### 3-A: ユーザー対応 Issue のスキップ

`assignee:user` の Issue は実装せず、Slack 通知のみ行う。

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" waiting \
  --issues "[Retro] ユーザー対応が必要な Try Issue があります: #{N1}, #{N2}" \
  --branch "{current_branch}"
```

### 3-B: large 工数 Issue への対応（コメントのみ）

実装計画をコメントとして投稿し、ステータスを `status:waiting-claude` のまま維持する（次回セッションに委ねる）。

```bash
gh issue comment {number} \
  --body "## 実装計画

この Try は工数が large のため、本セッションでは実装計画のみ記載します。

### 実装ステップ
1. {具体的なステップ 1}
2. {具体的なステップ 2}
3. ...

### 影響ファイル
- {ファイルパス 1}
- {ファイルパス 2}

次回セッションで対応します。" \
  -R kai-kou/claude-wiki-hub

gh issue edit {number} --add-label "done_type:D-plan" -R kai-kou/claude-wiki-hub
```

### 3-C: doc / skill カテゴリの実装

対象ファイルを **Read** ツールで読み込み、Issue の「改善施策」に従って **Edit** ツールで修正する。

**実装の原則**:
- 変更は最小限にとどめる（Issue で指示されていない箇所は変更しない）
- 変更前後の差分を確認してからコミットする
- **1 Issue = 1 コミット** を原則とする（複数 Issue を対応する場合も Issue ごとに個別コミットを作成する）

### 3-D: validate カテゴリの実装

`.claude/hooks/post-tool-use-validate.sh` にチェックを追加する。

- 既存のチェックパターンを **Read** ツールで確認してから追記する
- 追加するチェックは `WARNING` または `ERROR` レベルで区別する
- チェックが正常に動作することをシェル構文で確認する（`bash -n`）

### 3-E: script カテゴリの実装

`tools/*.py` / `tools/*.sh` を修正する。

- 修正前に既存のコードを **Read** ツールで確認する
- テスト実行可能な場合は実行して動作確認する
- P-14（`encoding` 未指定）・P-11（エラー握りつぶし）等の self-review-learnings.md のパターンに注意する

### 3-F: tool-update カテゴリの実装（Claude Code / Anthropic SDK 新機能）

Issue の「参照」セクションにある URL を WebFetch / WebSearch で取得し、変更内容を把握してから対応する。

**対応優先順位**:
1. `priority:high`（Breaking Change / Deprecated API）: 当日中に対応。影響範囲を調査してから修正
2. `priority:medium`（新機能追加）: 週次スケジュール内で対応
3. `priority:low`（マイナー更新）: 月次確認で対応

**更新対象の判断フロー**:
```
Issue の変更内容を確認
  ├─ Claude Code の新機能・仕様変更
  │     → docs/rules/claude-code-optimization.md を Read → 更新内容を Edit
  ├─ CLAUDE.md に記載されているモデル名・機能の変更
  │     → CLAUDE.md を Read → 当該箇所を Edit（モデルID・料金・機能名）
  ├─ MCP / Agent SDK の仕様変更
  │     → docs/rules/agent-team.md を Read → 更新内容を Edit
  └─ API Deprecated（破壊的変更）
        → 全ルールファイルを grep して旧 API 参照を検出 → 修正
```

**実装の原則**:
- 変更は **確認できた情報のみ** 反映する（推測で古い情報を削除しない）
- 不確かな情報は `<!-- TODO: 要確認 -->` コメントを添えて残す
- 更新後は `docs/rules/claude-code-optimization.md` の先頭の「最終更新」日付を更新する

### 3-G: domain カテゴリの実装（ドメイン/戦略更新 Issue・プロジェクト定義）

ドメインリサーチ系スキル（プロジェクト定義）が生成した戦略更新 Issue を対応する。

**優先度別の対応方針**:

| 優先度 | 対応内容 |
|--------|---------|
| `priority:high` | Issue の「推奨アクション」を当日中に実施。取り消し困難な変更（A-2/A-6 相当）はユーザーに Slack 通知も行う |
| `priority:medium` | 週次の{親ワークフロー}内で対応。戦略ドキュメントの更新が中心 |
| `priority:low` | Issue にコメントで「確認済み・参考情報として記録」と記載してクローズ |

**対応フロー（参照先はプロジェクト定義）**:
```
Issue の「対象」と「推奨アクション」を確認
  ├─ 配信先のアルゴリズム / 収益化条件の変更
  │     → プロジェクト定義の戦略ルール（KPI 管理）を更新
  │     → priority:high の場合: Slack でユーザーに通知
  ├─ 配信戦略の変更（配信先・プロジェクト定義）
  │     → 配信スキル（プロジェクト定義）の配信戦略セクションを更新
  │     → 関連設定ファイル（例: config/*.yaml）を更新
  ├─ 収益機会（アフィリエイト・スポンサー 等）
  │     → 戦略ドキュメントの収益化セクションに追記
  │     → 取り消し困難な設定が必要な場合はユーザーに Slack 通知
  └─ 競合動向
        → 戦略ドキュメントの競合分析セクションを更新
        → 戦略見直しが必要な場合は新規 Issue を起票してユーザーに報告
```

### 3-H: dev-tool カテゴリの実装（制作ツール / 新ライブラリ・プロジェクト定義）

```
Issue の変更内容を確認
  ├─ 制作ツール（例: 動画レンダリング）の新バージョン・API 変更
  │     → プロジェクト定義の該当ルールファイルを Read → 変更点を Edit
  │     → 関連スキル（プロジェクト定義）も確認して必要なら更新
  ├─ 制作ツール（例: 音声合成）の新バージョン・設定追加
  │     → プロジェクト定義の該当ルールファイルを Read → 更新
  │     → 関連設定ファイル（プロジェクト定義）の確認
  └─ 新ライブラリ（依存追加候補）
        → Issue の「対応提案」を確認
        → 採用する場合: tools/ への追加 or requirements.txt / package.json の更新を提案
        → 採用しない場合: Issue にコメントして「採用見送り」でクローズ
```

---

## Step 4: コミット・push

実装した Issue ごとに個別コミットを作成する。

```bash
git add {変更したファイル}
git commit -m "[Retro] {カテゴリ}: {Issue タイトルの要約}（Closes #{number}）"
```

### コミットメッセージ例

```
[Retro] doc: CLAUDE.md の skills リストに retrospective を追記（Closes #{N1}）
[Retro] validate: ドメイン固有の検証フラグの空配列チェックを追加（Closes #{N2}）
[Retro] skill: 各パイプライン（プロジェクト定義）のチェック手順を明確化（Closes #{N3}）
```

全 Issue の実装が完了したら push する。

```bash
git push -u origin {current_branch}
```

---

## Step 4.5: PR バンドル判定（AI レビューコスト削減）

同一セッションで複数 Issue を実装した場合、**PR を統合（バンドル）することで AI レビューの往復コストを削減** する。

### バンドル可能条件（全て満たす場合のみ）

| 条件 | 詳細 |
|------|------|
| 同一カテゴリ | `doc` + `doc`、`skill` + `skill` など（カテゴリをまたぐ場合は別 PR） |
| 推定工数 | 全て `small`（`medium` 以上が1件でもあれば個別 PR） |
| ファイル競合なし | 同一ファイルを複数 Issue が変更する場合は個別 PR |
| Issue 数 | 2〜3件（1件は個別 PR、4件以上はカテゴリを分割して 2PR） |

### バンドル PR のコミットメッセージ形式

```
[Retro] {カテゴリ}(bundle): {Issue 1 の要約}・{Issue 2 の要約}（Closes #{N1}, #{N2}）
```

### バンドル PR の説明文テンプレート

```markdown
## 変更内容の概要

{カテゴリ} 小改善 {N}件をバンドル処理。

- Issue #{N1}: {タイトル} — {変更概要}
- Issue #{N2}: {タイトル} — {変更概要}

## セルフレビュー結果

- セルフレビュー: 実施済み（エラー: 0件 / 警告: N件）
- YAML/JSON 構文: エラーなし

Closes #{N1}, #{N2}
```

**バンドルの効果**: 個別 PR（1件ずつ）では AI レビュー 25分 × 件数 = 75分（3件）かかるが、バンドル PR にすることで 25分（1回）に圧縮できる。

---

## Step 5: Issue クローズ

Issue のクローズタイミングは、変更の種別によって異なる。

### PR を作成した場合（3件以上 / main ブランチへのマージが必要）

PR 本文に `Closes #N` を含めておく（Step 6 参照）。PR が `main` にマージされると GitHub が自動でクローズする。
**マージ前は `status:in-progress` のまま維持**（誤クローズを防ぐ）。

### 直接 push した場合（2件以下のドキュメントのみ変更）

フィーチャーブランチから PR を作成してマージした後、PR 本文の `Closes #N` で自動クローズされる。
自動クローズが働かない場合のみ、以下のコマンドで手動クローズする。

```bash
gh issue close {number} \
  --comment "対応完了。PR #{pr_number} のマージで修正済み。

修正内容: {変更ファイル} に {概要} を追加しました。" \
  -R kai-kou/claude-wiki-hub
```

---

## Step 5.5: lessons 昇格フロー（昇格=物理削除）

Issue クローズ（Step 5）の後、lessons との対応関係を確認してフィードバックループを完結させる。
**昇格 = 物理削除**: 昇格先（コード/フック/ルール）へ実装したら元エントリを削除する（archive への「移動」は総トークン量を減らさないのでしない）。SSOT: `docs/rules/lessons-management.md`。

### A: 対応した Issue に対応する lessons エントリが存在する場合

対応エントリを検索する（全 lessons ファイルを grep してパターン名・キーワードで照合）:
```bash
grep -rn "{キーワード}" docs/rules/lessons-core.md docs/rules/lessons/
```

1. 昇格先への実装が **完了** した場合:
   - Hot 層（`lessons-core.md`）のエントリなら、全セッション横断で常駐必須かを判定する。不要なら **物理削除**（下記 prune）。常駐必須なら本文に `**保持理由**:` を付けて残す
   - Warm 層（`lessons/{カテゴリ}.md`）のエントリなら、`**昇格先**: {実装ファイル}（昇格日: YYYY-MM-DD）` を記載し、歴史的価値が薄ければ手動削除する（git 履歴に残る）
2. 実装が **未完了** の場合 → `**昇格先**:` フィールドのみ更新してエントリは残す
3. 変更後にコミット:
   ```bash
   git add docs/rules/lessons-core.md docs/rules/lessons/{カテゴリ}.md
   git commit -m "docs: lessons L-{N} 昇格=物理削除（{対応Issue番号}）"
   git push
   ```

### 物理削除（prune）の手順

`tools/lessons_guard.py` で Hot 層の昇格済みエントリを物理削除する（旧 prune_lessons.py の archive 移動は廃止）。

```bash
# 物理削除候補（昇格済み・実装済み・30日経過）を確認（dry-run）
python3 tools/lessons_guard.py prune

# 実際に Hot 層から物理削除（git 履歴に残る・対象に未コミット変更がないこと）
python3 tools/lessons_guard.py prune --apply

# Hot 層サイズ・分類の確認
python3 tools/lessons_guard.py stats
```

> 本文に `**保持理由**` を含むエントリは prune されない（常駐必須の行動規範を保護）。

### B: 対応した内容が lessons に未記録の場合

対応した retro-try Issue の内容を **Warm 層**（`docs/rules/lessons/{カテゴリ}.md`）に新規エントリとして追記する（`retrospective/SKILL.md` の Step 6 で未記録だった場合）。**Hot 層には原則追記しない**。

```markdown
### L-{N}: {パターン名}（{YYYY-MM-DD}）

**パターン**: {Issue で発見した問題パターン}
**根本原因**: {Issue の「背景」セクションから抜粋}
**試して失敗したアプローチ**:
該当なし（初回発見のため記録なし）
**対策**: {今回実施した修正内容}
**参照**: {Issue #{N}、修正コミット}
**昇格先**: `{修正したファイルパス}`（昇格日: YYYY-MM-DD）
```

### C: lessons との対応関係が不明な場合

このステップをスキップする。完了サマリー（Step 6）に「lessons 更新なし」と明記する。

---

## Step 6: PR 作成・AIレビュー・自動マージ

> **⚠️ 完了報告は必ず PR マージ後に出力すること。** Step 5.5 完了後に「完了報告」を出すのは禁止（L-056対策）。

**全ての変更（件数・種別を問わず）は PR を作成して `main` にマージする**（`main` への直接 push は禁止）。

### Step 6-1: セルフレビュー

```bash
# self-reviewer スキルに従ってセルフレビューを実施
# （変更がドキュメント・シェルスクリプトのみの場合は簡易チェックでよい）
for f in tools/*.sh; do [ -e "$f" ] && bash -n "$f"; done 2>&1  # シェルスクリプト構文チェック（ファイル未存在時の glob 未展開エラー対策）
python3 -c "
import json, glob
for p in glob.glob('**/*.json', recursive=True):
    if '.git' not in p and 'node_modules' not in p:
        with open(p, encoding='utf-8') as fh:
            json.load(fh)
"  # JSON 構文チェック（with open でFDクローズ保証）
```

### Step 6-2: PR 作成

```bash
gh pr create \
  --head {current_branch} \
  --base main \
  --title "[Retro] Try Issue 対応（{N}件）" \
  --body "## 対応した Try Issue

{対応済み Issue の一覧（Closes #N1, #N2, ...）}

## 変更内容

{変更ファイルと変更概要}

## セルフレビュー結果

{セルフレビューの結果（Error 0件 / Warning N件）}" \
  -R kai-kou/claude-wiki-hub
```

### Step 6-3: PR 存在確認（L-050 対策）

```bash
gh pr list --head {current_branch} -R kai-kou/claude-wiki-hub \
  --limit 1 --json number,url,state \
  --jq '.[0] | select(.url != null) | "PR #\(.number) \(.state): \(.url)"'
```

### Step 6-4: Slack PR 作成通知

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" pr \
  --pr-url "https://github.com/kai-kou/claude-wiki-hub/pull/{pr_number}" \
  --pr-title "[PR作成] [Retro] Try Issue 対応（{N}件）" \
  --branch "{current_branch}"
```

### Step 6-5: Layer 1 セルフレビュー（必須・外部依頼なし）

**`/code-review --comment` を必ず実行** する（Layer 1・全 PR 必須）。
❌ Copilot 依頼（`--add-reviewer @copilot` / `request_copilot_review`）・Gemini 依頼（`/gemini review`）はしない。
diff ≥300行 / `type:security` / `type:breaking-change` の PR は Layer 2（`discussion_review_trigger.py --pr {pr_number}`）も起動する。

### Step 6-6: レビュー対応・自動マージ

`docs/rules/pr-review-flow.md` に従う。外部レビュアーの応答待ちはない。

- `/code-review` の指摘対応（修正コミット or スキップ + 返信 + Resolve）
- Layer 0（機械ゲート）+ Layer 1 通過後は即マージ可
- 任意で `subscribe_pr_activity` により CI / 人手コメントを監視し、あれば対応してからマージ

マージコマンド（全指摘解消 or 問題なし判定後）:
```bash
# GitHub MCP ツールでマージ
mcp__github__merge_pull_request(owner="kai-kou", repo="claude-wiki-hub", pull_number={pr_number}, merge_method="squash")
```

---

## Step 7: 完了サマリー出力（マージ後のみ実行）

> **マージが完了してから** 以下の完了サマリーを出力すること。PR 作成直後・マージ前に完了報告を出してはならない（L-056 対策）。

```
## retro-try-handler 完了サマリー

### アウトカム（ユーザー視点）
- {このタスクにより何ができるようになったか・何が改善されたか}

### 対応済み Issue
| # | タイトル | カテゴリ | コミット |
|---|---------|---------|---------|
| #{N1} | {タイトル} | {doc/skill/validate/script} | {hash} |
| #{N2} | {タイトル} | {doc/skill/validate/script} | {hash} |

### スキップ（large / ユーザー対応）
| # | タイトル | 理由 |
|---|---------|------|
| #{N3} | {タイトル} | large: 実装計画コメントを投稿済み |
| #{N4} | {タイトル} | user: Slack 通知済み |

### 残存 Try Issue
gh issue list -R kai-kou/claude-wiki-hub --label "type:retro-try" --state open
```

### マージ完了後 Slack 通知

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" pr \
  --pr-url "https://github.com/kai-kou/claude-wiki-hub/pull/{pr_number}" \
  --pr-title "[完了] [Retro] Try Issue 対応（{N}件）" \
  --outcome "{アウトカム1文}" \
  --branch "{current_branch}"
```

---

## エラーハンドリング

| エラー | 対応 |
|--------|------|
| Issue 取得失敗 | `gh issue list` を再実行（最大2回）。それでも失敗したら STOP してユーザーに Slack 通知して報告 |
| 対象ファイルが存在しない | Issue にコメントを残し、スキップ |
| 編集後に TypeScript/Python コンパイルエラー | 変更を元に戻して Issue に「コンパイルエラーのため保留」コメントを投稿 |
| ブランチ push 失敗 | 指数バックオフでリトライ（最大4回: 2s, 4s, 8s, 16s） |

---

## 既存スキルとの関係

| 関連スキル | 関係 |
|-----------|------|
| `retrospective` | Try Issue を生成する上流スキル |
| `self-reviewer` | 実装後のセルフレビューに使用（PR 作成時） |
| `pr-review-watcher` | PR 作成後の AIレビュー監視に使用 |
| `project-manager` | Projects V2 のステータス更新が必要な場合に使用 |

---

## フィルタコマンド（参考）

```bash
# 全 Try Issue を取得
gh issue list -R kai-kou/claude-wiki-hub --label "type:retro-try" --state open --limit 1000

# Claude 担当のみ
gh issue list -R kai-kou/claude-wiki-hub \
  --label "type:retro-try" --label "assignee:claude" --state open --limit 1000

# 高優先度のみ
gh issue list -R kai-kou/claude-wiki-hub \
  --label "type:retro-try" --label "priority:high" --state open --limit 1000

# 特定パイプラインのみ（タイトル検索: {pipeline} を実際のパイプライン名に置き換える）
# ※ "[Retro][{pipeline}]" は Issue タイトルのパイプライン種別（プロジェクト定義）を検索する
# ※ このスキルの内部カテゴリ（doc/script/validate/skill/user）とは異なる
gh issue list -R kai-kou/claude-wiki-hub \
  --label "type:retro-try" --search "[Retro][{pipeline}]" --limit 1000
```
