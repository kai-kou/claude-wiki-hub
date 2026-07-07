---
description: プロジェクト現状（進行中/waiting Issue・オープンPR・レビュー待ち・直近コミット）を素早く把握して報告する
---

# /status — プロジェクト現状確認

プロジェクトの現在の状態を素早く把握するコマンドにゃ。

## 実行手順

以下を並列で取得してまとめて報告する:

```bash
# 1. 進行中 Issue
gh issue list -R kai-kou/claude-wiki-hub --label "status:in-progress" --state open --limit 1000 --json number,title,updatedAt

# 2. Claude 待ち Issue
gh issue list -R kai-kou/claude-wiki-hub --label "status:waiting-claude" --state open --limit 1000 --json number,title,updatedAt

# 3. ユーザー待ち Issue
gh issue list -R kai-kou/claude-wiki-hub --label "status:waiting-user" --state open --limit 1000 --json number,title,updatedAt

# 4. オープン PR
gh pr list -R kai-kou/claude-wiki-hub --state open --limit 1000 --json number,title,updatedAt,headRefName

# 5. レビュー待ち PR（actionable）
python3 tools/check_pending_pr_reviews.py --actionable-only --json

# 6. 最新コミット
git log --oneline -5
```

## 出力フォーマット

```
## プロジェクト現状 (YYYY-MM-DD HH:MM JST)

### 制作パイプライン
| 動画 | フェーズ | ステータス |
...

### Issue 状態
- 🔴 in-progress: N件
- 🟡 waiting-claude: N件
- 🔵 waiting-user: N件

### PR 状態
- オープン: N件（レビュー待ち: N件）

### 直近コミット
...
```
