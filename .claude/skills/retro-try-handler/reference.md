# retro-try-handler リファレンス

`SKILL.md` から分離した詳細手順。必要になったステップで該当セクションだけを Read する。

---

## R1. 優先度ソート（ローカル `gh` 版の詳細）

クラウドでは `mcp__github__list_issues` で取得し、Claude が本文・ラベルを見てソートする（`SKILL.md` Step 1）。
ローカルで `gh` が直接 GitHub に到達できる環境では、以下の jq ソート式で優先度順に並べられる。

```bash
gh issue list -R kai-kou/claude-wiki-hub \
  --label "type:retro-try" --label "status:waiting-claude" \
  --state open --limit 1000 \
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

**フォールバック**: urgency ラベルなしの旧形式は priority:high→50 / medium→51 / low→52 / 未設定→53 として扱う。

### doc-only の月曜スキップルール

`urgency:doc-only` のみが対象の Issue は **月曜日のみ処理** する（火〜日はスキップ）。
`doc-only` は説明文の修正のみで品質・プロセスに影響しないため、月曜のまとめ処理で効率化する。

```bash
day_of_week=$(TZ=Asia/Tokyo LC_ALL=C date '+%A')   # 月曜=Monday
# 火〜日は urgency:doc-only を除外してソートする（月曜は全件対象）
```

---

## R2. 1 セッションの処理量見積もり

**動的処理上限（バックログ残件数に応じて調整）**:

| バックログ残件数 | 1 セッションの処理上限 | 理由 |
|--------------|-------------------|------|
| 0〜9 件 | 2 件 | 通常運用 |
| 10〜19 件 | 3 件 | 消化ペース加速 |
| 20〜29 件 | 4 件 | バックログ圧縮モード |
| 30 件以上 | 5 件 | 最大スループット |

> **セッション安全ルール**: 1 ターンのツール呼び出しは 8 個以内。処理上限を増やすときは中間報告を挟んで
> 複数ターンに分散する（`session-safety-rules.md`）。

**推定工数ごとの方針**: `small` = 処理上限まで実装（同カテゴリは PR バンドル候補） / `medium` = 1〜2 件 /
`large` = 実装計画コメントを投稿し `done_type:D-plan` を付与して次回へ。

---

## R3. PR バンドル判定（AI レビューコスト削減）

同一セッションで複数 Issue を実装した場合、PR を統合（バンドル）してセルフレビューの往復を削減する。

### バンドル可能条件（全て満たす場合のみ）

| 条件 | 詳細 |
|------|------|
| 同一カテゴリ | `doc` + `doc`・`skill` + `skill` 等（カテゴリをまたぐ場合は別 PR） |
| 推定工数 | 全て `small`（`medium` 以上が 1 件でもあれば個別 PR） |
| ファイル競合なし | 同一ファイルを複数 Issue が変更する場合は個別 PR |
| Issue 数 | 2〜3 件（1 件は個別 PR、4 件以上はカテゴリ分割して 2 PR） |

### バンドル PR の説明文テンプレート

```markdown
## 変更内容の概要

{カテゴリ} 小改善 {N}件をバンドル処理。

- Issue #{N1}: {タイトル} — {変更概要}
- Issue #{N2}: {タイトル} — {変更概要}

## セルフレビュー結果

- セルフレビュー: 実施済み（エラー: 0 件 / 警告: N 件）
- YAML/JSON 構文: エラーなし

Closes #{N1}, #{N2}
```

---

## R4. lessons 昇格フロー（昇格 = 物理削除）

Issue クローズ後、lessons との対応関係を確認してフィードバックループを完結させる。
**昇格 = 物理削除**: 昇格先（コード/フック/ルール）へ実装したら元エントリを削除する。SSOT: `lessons-management.md`。

### A: 対応エントリが lessons に存在する場合

```bash
grep -rn "{キーワード}" docs/rules/lessons-core.md docs/rules/lessons/
```

- 昇格先実装が **完了**: Hot 層エントリは常駐必須でなければ物理削除。必須なら `**保持理由**:` を付けて残す。
  Warm 層は `**昇格先**: {ファイル}（昇格日: YYYY-MM-DD）` を記載し、歴史的価値が薄ければ削除（git 履歴に残る）。
- 実装が **未完了**: `**昇格先**:` フィールドのみ更新してエントリは残す。

物理削除（prune）:

```bash
python3 tools/lessons_guard.py prune            # 候補確認（dry-run）
python3 tools/lessons_guard.py prune --apply    # Hot 層から物理削除
python3 tools/lessons_guard.py stats            # Hot 層サイズ確認
```

> `**保持理由**` を含むエントリは prune されない（常駐必須の行動規範を保護）。

### B: 対応内容が lessons に未記録の場合

**Warm 層**（`docs/rules/lessons/{カテゴリ}.md`）に新規エントリを追記する（Hot 層には原則追記しない）。

```markdown
### L-{N}: {パターン名}（{YYYY-MM-DD}）

**パターン**: {発見した問題パターン}
**根本原因**: {背景}
**対策**: {今回の修正内容}
**参照**: {Issue #{N}、修正コミット}
**昇格先**: `{修正ファイルパス}`（昇格日: YYYY-MM-DD）
```

### C: 対応関係が不明な場合

このステップをスキップし、完了サマリーに「lessons 更新なし」と明記する。

---

## R5. フィルタコマンド（参考・ローカル gh 版）

```bash
# 全 Try Issue
gh issue list -R kai-kou/claude-wiki-hub --label "type:retro-try" --state open --limit 1000
# 高優先度のみ
gh issue list -R kai-kou/claude-wiki-hub --label "type:retro-try" --label "priority:high" --state open --limit 1000
```

クラウドでは `mcp__github__list_issues(labels=["type:retro-try", "priority:high"], state="OPEN")` を使う。

---

## R6. エラーハンドリング

| エラー | 対応 |
|--------|------|
| Issue 取得失敗 | `list_issues` を再実行（最大 2 回）。それでも失敗したら STOP して Slack 通知で報告 |
| 対象ファイルが存在しない | Issue にコメントを残しスキップ |
| 編集後にコンパイル/構文エラー | 変更を戻して「エラーのため保留」コメントを投稿 |
| ブランチ push 失敗 | 指数バックオフでリトライ（最大 4 回: 2s, 4s, 8s, 16s）。それでも失敗なら `mcp__github__push_files` に切替（L-079） |
