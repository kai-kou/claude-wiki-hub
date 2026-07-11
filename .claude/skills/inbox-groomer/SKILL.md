---
name: inbox-groomer
description: idea/bookmark の Issue オーバーレイ（kind:idea / kind:bookmark）を定期トリアージするスキル。ラベル補完・ファイル化・重複検出・stale 棚卸し・wiki ingest トリガー検出・インデックス同期確認を自律実行する。「inbox を整理して」「アイデア・ブックマーク Issue をトリアージして」「/inbox-groomer」と依頼された時、またはルーティン inbox-triage（火・金の朝・日次ディスパッチャ経由）から自動起動される時に使用する。
effort: low
model: haiku
---

# inbox-groomer — idea/bookmark Issue トリアージスキル

> **目的**: `content/discussions/ideas-bookmarks-issue-mgmt/whiteboard.md`（合意 1〜6）で確定した
> 「ファイル一次・Issue ライフサイクルオーバーレイ」モデルの定期整理レイヤー。
> `ideas/*.md` / `bookmarks/inbox.md` が真実源のまま、GitHub Issue（`kind:idea` / `kind:bookmark`）の
> open/close・ラベル・ファイル化・wiki ingest トリガーを Claude が自律的に整合させる。

## なぜ専用スキルなのか（責務境界）

idea/bookmark Issue のトリアージは「意味的分類」（kind: 推定・ファイル化・重複判断）であり、
`project-sync`（機械的衛生: Stale/Orphan/Abandoned）の守備範囲外である。この境界は
`improvement-groomer` が `project-sync` から分離された先例（whiteboard.md ラウンド 2〜3・
Architect の明示撤回）に倣う。

| スキル | 担当 | 本スキルとの違い |
|--------|------|----------------|
| **project-sync** | リポジトリ衛生（Stale Issue/Orphan PR/Abandoned ブランチ）。機械的 | `kind:` ラベルの意味的分類・ファイル化は行わない |
| **repo-watch**（ルーティン） | Issue 監視・起票全般 | `kind:idea`/`kind:bookmark` の分類ロジックは本スキルに委譲する（対象重複を避ける） |
| **improvement-groomer** | `type:improvement` の棚卸し | 対象ラベル空間が別（`type:` vs `kind:`）。パターンのみ踏襲 |

## 2 層構成（improvement-groomer / project-sync と同じパターン）

- **`tools/triage_inbox.py`（コード・副作用なし）**: `mcp__github__list_issues` の結果を Claude が
  JSON に保存し、本ツールに渡す。GitHub API は叩かない（標準ライブラリのみ）。
  ラベル欠損・ファイル未作成・タイトル類似・stale を検出して JSON を返す。**Issue を変更しない**。
- **本 SKILL.md（Claude の判断）**: レポートを読み、ファイル作成・ラベル付与・コメント・
  クローズ・wiki ingest 起動を実行する。GitHub 操作はクラウドでは `gh` の repo スコープ操作が
  403 でブロックされるため（L-114）、`mcp__github__*`（GitHub MCP）を一次経路とする。
  ローカル実行時は `gh issue edit` 等で代替してよい。

## 前提条件・早期終了

- `GH_TOKEN`（PAT）未登録の場合は Phase 1〜4（Issue 書き込み系）をスキップし、**Phase 5 のみ** 実行して終了する（`intent-routing-detail.md` の R-3 と同じフォールバック）。
- 作業ブランチで実行すること（`main` への直接 push はしない・A-1）。ファイル作成・更新は
  `claude/` ブランチ + PR 経由。

## 実行フロー（5 フェーズ）

```
Step 0: ロック取得（CP-4・任意）
  ↓
Phase 1: ラベル補完・ファイル化
  ↓
Phase 2: 重複検出
  ↓
Phase 3: stale 棚卸し
  ↓
Phase 4: ingest トリガー
  ↓
Phase 5: ファイル同期確認
```

### Step 0: ロック取得（CP-4）

トリアージは複数 Issue にまたがる書き込みを伴うため、`session-sprint-rules.md` に従い
対象を扱う作業 Issue（または当該セッションの既存タスク Issue）に `status:in-progress` を
付与してから着手する。スケジュール起動時は直近の inbox-triage 実行がオープンでないか確認する。

### Phase 1: ラベル補完・ファイル化

1. `mcp__github__list_issues(state="OPEN")` で全 open Issue を取得し JSON に保存（`/tmp/inbox_issues.json` 等）。
2. `python3 tools/triage_inbox.py missing --issues-json /tmp/inbox_issues.json` を実行。
3. `missing_kind`（`kind:` ラベル無し）: タイトル・本文から idea/bookmark を推定して
   `mcp__github__issue_write` で `kind:idea` または `kind:bookmark` を付与する。
   URL を含む・「あとで読む」等の文言 → bookmark。それ以外の断片的な願望・ネタ → idea。
4. `missing_file_ref`（`kind:` 付きだがファイル未作成＝GitHub UI 直投稿）:
   - `kind:idea` → `ideas/YYYY-MM-DD-<slug>.md` を作成（`ideas/README.md` の frontmatter 規約:
     `title`/`created`/`status: raw`/`tags`/`related_repos`）。タグは本文から推定して付与する。
   - `kind:bookmark` → `bookmarks/inbox.md` に 1 エントリ追記（`bookmarks/README.md` の
     frontmatter 規約: `url`/`title`/`added`/`status: unread`/`tags`）。
   - 作成/追記後、Issue 本文またはコメントに対応ファイルパスを記録する
     （例: `→ ファイル: ideas/2026-07-10-cafe-app.md`）。
   - `python3 tools/build_index.py --quiet` を実行して横断インデックスを更新する。
5. ファイル作成・更新は `claude/` ブランチにコミット → PR 作成（`main` 直 push 禁止・A-1）。

### Phase 2: 重複検出

1. `python3 tools/triage_inbox.py similar --issues-json /tmp/inbox_issues.json --threshold 0.6` を実行。
2. 出力された類似ペア（Jaccard ≥ 0.6）について、両 Issue に相互参照コメントを付ける
   （例: `重複候補: #{other} と類似度 {score}。人間判断で統合/クローズを検討してください`）。
3. **自律クローズは禁止**（人間判断に委ねる・whiteboard.md 合意 5）。

### Phase 3: stale 棚卸し

1. `python3 tools/triage_inbox.py stale --issues-json /tmp/inbox_issues.json --days 30` を実行。
2. 30 日超 open の `kind:` Issue に `status:archived` ラベルを付与し、「棚卸し候補（{age_days} 日未更新）」
   とコメントする。**クローズはしない**（ユーザーまたは明示指示があるときのみクローズする）。

### Phase 4: ingest トリガー

> open + `status:ingested` は「wiki 昇格の予約」（`wiki-operations.md`「open 中のラベルは遷移待ち/候補」）。
> ユーザーが GitHub UI でラベルを付ける・チャットで「これ wiki 化して」と言って Claude が付ける、の
> どちらでも予約できる。本フェーズがその予約を回収して ingest → クローズ（確定マーク化）する。

1. `status:ingested` ラベル付き open Issue を検出する（`mcp__github__list_issues(labels=["status:ingested"], state="OPEN")`）。
2. `docs/rules/wiki-operations.md` の Ingest 操作を実行する:
   - `kind:bookmark` → 対応ファイルの URL 内容を `raw/` に取り込み → `wiki/topics/` or `wiki/entities/` にページ化。
   - `kind:idea` → アイデア本文をそのまま `wiki/` ページ化（頻度が高ければ `raw/` 経由も可）。
3. 対応ファイルの frontmatter `status:` を `ingested`（bookmark）/ `promoted`（idea・wiki 化の場合）に更新し、
   `python3 tools/build_index.py --quiet` を実行する。
4. Issue をクローズし、コメントに `→ Ingested: wiki/topics/xxx.md` を記録する。

### Phase 5: ファイル同期確認

```bash
python3 tools/check_index_sync.py
```

desync が検出された場合は `python3 tools/build_index.py --quiet` で修復する。

**PAT 未登録時はここから開始する**（Phase 1〜4 をスキップした場合の唯一の実行ステップ）。

## タスク派生（idea → task）

ユーザーが「これタスクにして」と明示した idea Issue について:

1. 新規 Issue を作成する（`type:feature` 等・適切な `sp:`/`priority:` を付与）。
2. 元の idea Issue をクローズし、コメントに `→ Promoted: #{N}` を記録する。
3. 対応する `ideas/*.md` の frontmatter `status:` を `promoted` に更新する。

## 自律度と境界（CP-6）

| 自律実行してよい | ユーザー確認が必要（A-1〜A-6 のみ） |
|----------------|--------------------------------|
| kind: ラベル推定・付与 | （該当なし。トリアージは境界外に当たらない） |
| ファイル作成（ideas/*.md・bookmarks/inbox.md 追記） | — |
| 重複候補への相互参照コメント | — |
| stale Issue への `status:archived` 付与 | — |
| wiki ingest 起動・Issue クローズ | — |
| タスク派生（Promoted コメント + 新 Issue） | — |

Issue の **自律クローズ** は「重複」「stale」検出時には行わない（人間判断）。ingest 完了時・
タスク派生時のクローズはライフサイクルの正常遷移として自律実行する（whiteboard.md 合意 3）。

## 日時

JST（`datetime-rules.md`）。stale 判定の経過日数計算は UTC で行い、コメント表示は JST。

## トリガー

- 「inbox を整理して」「アイデア・ブックマーク Issue をトリアージして」等の明示依頼
- `/inbox-groomer` コマンド
- ルーティン `inbox-triage`（`config/routine_jobs.yaml`・火・金の朝 8:00 JST 発火・週 2 回）

## 禁止パターン

```
❌ triage_inbox.py のレポートを見ずに勘でラベル付与・クローズする
❌ 重複候補を自律クローズする（人間判断に委ねる・whiteboard.md 合意 5）
❌ ideas/bookmarks ファイルを介さず Issue 本文のみで完結させる（ファイル一次モデル違反）
❌ build_index.py / all.jsonl のスキーマを変更する（本スキルのスコープ外）
❌ PAT 未登録時に Phase 1〜4 を強行する（Issue 書き込みは全て失敗する）
✅ ツールで可視化 → ファイル一次でファイル化 → Issue はオーバーレイとして同期 → サイレントに記録
```

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `tools/triage_inbox.py` | ラベル欠損・重複・stale の検出（副作用なし） |
| `content/discussions/ideas-bookmarks-issue-mgmt/whiteboard.md` | 設計 SSOT（合意 1〜6・最終判定） |
| `docs/rules/wiki-operations.md` | Ingest 操作の SSOT |
| `docs/rules/intent-routing.md` | R-1（bookmark）/ R-2（idea）のチャット発話ルーティング |
| `ideas/README.md` / `bookmarks/README.md` | frontmatter 規約 |
| `scripts/setup-labels.sh` | 新設 4 ラベルのセットアップ（フォーク先で未実行だとフローが動かない） |
| `.claude/skills/improvement-groomer/SKILL.md` | パターンの踏襲元（2 層構成・自律クローズ境界） |
| `.claude/skills/project-sync/SKILL.md` | 機械的衛生（重複しない別レーン） |
