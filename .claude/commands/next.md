---
description: 次にやるべきタスクを優先度順に自律判定して実行する（PR レビュー対応 → 進行中 Issue 再開 → waiting-claude Issue → プロジェクト固有バックログ）
---

# /next — 次にやるべきタスクを特定

優先度順に次のアクションを自律判定して実行するコマンドにゃ。

## 判断フロー

以下の順序でチェックし、最初に該当したものを実行する:

### 1. レビュー待ち PR のチェック（最優先）

```bash
python3 tools/check_pending_pr_reviews.py --actionable-only --json
```

- `ready_to_merge` → 即マージ
- `needs_response` → 指摘対応再開
- `needs_prompt` → 催促コメント投稿
- `awaiting_review` → subscribe_pr_activity で待機継続

### 2. 進行中 Issue の確認

```bash
gh issue list -R kai-kou/claude-wiki-hub --label "status:in-progress" --state open --limit 1000
```

- [wip] コミットがあれば前回の停止箇所を確認して再開
- Issue コメントの「次回再開ステップ」を参照

### 3. Claude 待ち Issue の実行

```bash
gh issue list -R kai-kou/claude-wiki-hub --label "status:waiting-claude" --state open --limit 1000 --json number,title,labels
```

- `status:in-progress` ラベルを先付けしてから作業開始（CP-4）
- パイプライン系 Issue は対応するスキルの SKILL.md を Read してから実行

### 4. 何もない場合

- プロジェクト固有のバックログ（refinement・スケジュールタスク等）を確認する
- 該当がなければ no-op として理由を 1 行記録して終了する

## 出力フォーマット

```
## 次のアクション

**優先度1（PR レビュー対応）**: PR #N - {タイトル}
→ {具体的なアクション}

**優先度2（進行中 Issue 再開）**: Issue #N - {タイトル}
→ {停止箇所と次のステップ}
...
```
