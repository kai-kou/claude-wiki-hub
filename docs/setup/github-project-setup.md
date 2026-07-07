# GitHub プロジェクト管理の初期セットアップ（1回のみ）

> `project-manager` スキルの **初回セットアップ手順** と **GitHub リソース体系のリファレンス** を切り出したもの
> （progressive disclosure・E-G #26）。日常運用（Issue 化・ステータス更新・進捗確認）は
> `.claude/skills/project-manager/SKILL.md` を参照。本ファイルはセットアップ時のみ Read する。
>
> ラベル・マイルストーンは **プロジェクト非依存の汎用例**。各プロジェクトのドメインに合わせて
> `phase:*` 等を追加・改名する（本ベースは動画制作固有のラベルを同梱しない）。

> **絶対条件**: 下記のラベル・マイルストーン・Projects V2 作成コマンドは **すべて Claude が `gh` / GitHub MCP で実行** する。ユーザーにコマンド実行を求めない（`CLAUDE.md`「絶対条件」節）。クラウドセッションでは `GH_TOKEN` で認証されるため `gh auth` も不要。セットアップ（`/onboarding`）の一部として Claude が代行できる。

## 前提条件

- `gh` CLI が認証済み（`gh auth status` で確認）。クラウドでは `GH_TOKEN` で自動認証されるため Claude がそのまま実行できる
- `gh auth refresh -s project` で project スコープ付与済み（Projects V2 を使う場合のみ）
- リポジトリ: `kai-kou/claude-wiki-hub`

---

## Step 1-1: project スコープの確認

```bash
gh auth status
# project スコープがない場合:
gh auth refresh -s project
```

## Step 1-2: ラベルの一括作成

本ベースが前提とする汎用ラベル（種別・ステータス・優先度・見積もり）を作成する。
ドメイン固有の分類（`phase:*` 等）が必要なら同じ要領で追記する。

```bash
# 種別（type:*）
gh label create "type:feature"     --color "a2eeef" --description "機能開発・ツール開発" --repo kai-kou/claude-wiki-hub
gh label create "type:bug"         --color "d73a4a" --description "バグ修正"          --repo kai-kou/claude-wiki-hub
gh label create "type:docs"        --color "0075ca" --description "ドキュメント更新"    --repo kai-kou/claude-wiki-hub
gh label create "type:improvement" --color "FBCA04" --description "改善・リファクタリング" --repo kai-kou/claude-wiki-hub
gh label create "type:retro-try"   --color "C5DEF5" --description "振り返り Try"       --repo kai-kou/claude-wiki-hub

# ステータス（status:* ・CP-4 論理ロック）
gh label create "status:waiting-user"   --color "f9d26c" --description "ユーザーのアクション待ち" --repo kai-kou/claude-wiki-hub
gh label create "status:waiting-claude" --color "0e8a16" --description "Claude の対応待ち"     --repo kai-kou/claude-wiki-hub
gh label create "status:in-progress"    --color "1d76db" --description "作業中（現セッションで対応中）" --repo kai-kou/claude-wiki-hub
gh label create "status:blocked"        --color "d93f0b" --description "外部要因でブロック中"   --repo kai-kou/claude-wiki-hub

# 優先度（priority:* ・critical は通知トリアージ A 区分・PO ロールが前提にする）
gh label create "priority:critical" --color "5A0000" --description "最優先（即対応・通知トリアージ A 区分）" --repo kai-kou/claude-wiki-hub
gh label create "priority:high"     --color "B60205" --description "高優先度" --repo kai-kou/claude-wiki-hub
gh label create "priority:medium"   --color "D93F0B" --description "中優先度" --repo kai-kou/claude-wiki-hub
gh label create "priority:low"      --color "E99695" --description "低優先度" --repo kai-kou/claude-wiki-hub

# 見積もり（sp:* ・session-sprint-rules.md §3）
gh label create "sp:1" --color "EDEDED" --description "自明な修正・データ更新"     --repo kai-kou/claude-wiki-hub
gh label create "sp:2" --color "D4D4D4" --description "小さな改善・単一スキル軽修正" --repo kai-kou/claude-wiki-hub
gh label create "sp:3" --color "BFBFBF" --description "標準タスク"               --repo kai-kou/claude-wiki-hub
gh label create "sp:5" --color "9E9E9E" --description "複合タスク"               --repo kai-kou/claude-wiki-hub
gh label create "sp:8" --color "757575" --description "大型タスク（分割を検討）"   --repo kai-kou/claude-wiki-hub

# epic（任意・大きな束ね）
gh label create "epic" --color "5319E7" --description "複数 Issue を束ねるエピック" --repo kai-kou/claude-wiki-hub
```

## Step 1-3: マイルストーンの作成（任意）

GitHub ネイティブのマイルストーンを使う場合（`milestone:M*` ラベル運用でも代替可）:

```bash
gh api --method POST repos/kai-kou/claude-wiki-hub/milestones \
  -f title="M1: {マイルストーン名}" -f description="{達成目標・推定期間}" -f state="open"
gh api --method POST repos/kai-kou/claude-wiki-hub/milestones \
  -f title="M2: {マイルストーン名}" -f description="{達成目標・推定期間}。前提: M1完了" -f state="open"
```

## Step 1-4: GitHub Projects V2 の作成（任意）

```bash
# プロジェクト作成（OWNER は kai-kou に読み替え）
gh project create --owner kai-kou --title "{プロジェクト名}" --format json

# プロジェクト番号を取得（後続コマンドで使用）
gh project list --owner kai-kou --format json
```

カスタムフィールドの作成（`PROJECT_NUMBER` は上記で取得した番号に置換）:

```bash
gh project field-create PROJECT_NUMBER --owner kai-kou --name "Assignee Type" \
  --data-type "SINGLE_SELECT" --single-select-options "user,claude,both"
gh project field-create PROJECT_NUMBER --owner kai-kou --name "Priority" \
  --data-type "SINGLE_SELECT" --single-select-options "critical,high,medium,low"
# ドメイン固有フィールド（例: 工程・カテゴリ）が必要ならここで追加する
```

## Step 1-5: 既存タスクの Issue 移行

既存のタスク定義から Issue を作成し、マイルストーン（使う場合）に紐付ける:

```bash
gh issue create \
  --title "{タスク名}" \
  --body "## 概要
{概要}

## 完了条件
{完了条件}" \
  --label "type:feature,priority:high,sp:3" \
  --repo kai-kou/claude-wiki-hub
```

**重要**: 完了済みタスクも Issue 化して即 close する（履歴のトレーサビリティ確保）。

```bash
gh issue close ISSUE_NUMBER --repo kai-kou/claude-wiki-hub
gh project item-add PROJECT_NUMBER --owner kai-kou --url ISSUE_URL  # Projects V2 を使う場合
```

---

## リファレンス: GitHub リソース体系

### Milestones
時間軸でのリリース・達成管理。各マイルストーンが複数 Issue を束ねる。
ネイティブのマイルストーン、または `milestone:M*` ラベルで運用する。

### Projects V2（Kanban ボード・任意）

| ステータス | 意味 |
|-----------|------|
| Backlog | 未着手・将来のタスク |
| Todo | 次にやるべきタスク |
| In Progress | 作業中 |
| In Review | PR 作成済み・レビュー待ち |
| Done | 完了 |

| カスタムフィールド例 | 型 | 用途 |
|-------------|-----|------|
| Assignee Type | Single Select | user / claude / both |
| Priority | Single Select | critical / high / medium / low |

### Labels の体系

| 区分 | プレフィックス | 例 |
|------|--------------|-----|
| 種別 | `type:` | feature / bug / docs / improvement / retro-try |
| ステータス | `status:` | waiting-user / waiting-claude / in-progress / blocked |
| 優先度 | `priority:` | critical / high / medium / low |
| 見積もり | `sp:` | 1 / 2 / 3 / 5 / 8 |
| 束ね | `epic` / `milestone:M*` | — |

> `priority:*` と `sp:*` の付与・変更は PO ロール（`.claude/agents/owner.md`）の権限。
> `status:*` は CP-4 論理ロックのため PO でも操作しない。
