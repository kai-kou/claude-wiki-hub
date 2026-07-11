# Wiki 操作ルール（LLM Wiki スキーマ・SSOT）

> 本プロジェクト（Claude Wiki Hub）固有のクリティカル規範。Karpathy「LLM Wiki」パターンに基づき、
> Claude が **規律ある wiki 管理者** として振る舞うための操作定義。`.claude/rules/` 経由で常駐（Hot 層）。

## 3 層アーキテクチャ（不変条件）

| 層 | パス | 所有 | 規約 |
|----|------|------|------|
| Raw sources | `raw/` | 人間 | **immutable**。Claude は読むだけ。真実の源 |
| Wiki | `wiki/` | **Claude** | LLM 生成。`index.md`（目次）+ `log.md`（追記ログ）を含む |
| Inbox | `ideas/` `bookmarks/` **+ GitHub Issue（`kind:` ラベル）** | 人間が投稿 → Claude が整理 | 気軽な入力の受け皿。ファイルが真実源・Issue はライフサイクル層 |

**鉄則: `raw/` を書き換えない。** `wiki/` と `raw/` が矛盾したら、常に `raw/` を正として `wiki/` を直す。

### Inbox 層の Issue ライフサイクルオーバーレイ（#77 設計）

- **ファイル（frontmatter）が真実源**: `ideas/*.md` / `bookmarks/inbox.md` に本文・メタデータを保存し、
  横断インデックス（`build_index.py` → `all.jsonl`）は従来どおりファイルから導出する。
- **GitHub Issue はライフサイクル管理層**: 1 エントリ = 1 Issue（`kind:idea` / `kind:bookmark` ラベル）。
  open = 未処理、close はコメントで 3 区別する — タスク派生（「→ Promoted: #N」）/ wiki 昇格
  （`status:ingested` + 「→ Ingested: wiki/...」）/ 棚上げ（`status:archived`）。
- **open 中のラベルは「遷移待ち/候補」の意味**: open + `status:ingested` = wiki 昇格の予約
  （ユーザー・Claude のどちらが付けてもよい。`inbox-groomer` が検出して ingest → close する）。
  open + `status:archived` = 棚卸し候補（`inbox-groomer` が 30 日超 stale に付与。**クローズの確定は
  ユーザー判断または明示指示** — 自律クローズはしない）。close 時に同ラベルが確定マークになる。
- **入口は 2 チャネル**: チャット発話（`intent-routing.md` R-1/R-2・ファイル + Issue を Claude が同時作成）と
  GitHub UI の Issue テンプレート（`idea.yml` / `bookmark.yml`・ファイルは定期トリアージが補完）。
- **定期トリアージ**: `inbox-groomer` スキル（ルーティン `inbox-triage`）がラベル/ファイル補完・重複検出・
  stale 棚卸し・ingest トリガー・インデックス同期確認を行う。
- 既存ラベル `type:` / `status:waiting-*` / `sp:` は **タスク Issue 専用**。`kind:` ラベルの有無で
  inbox Issue とタスク Issue を判別する（namespace 分離・ラベル爆発防止）。

## 操作 1: Ingest（取り込み）

ソース（`raw/` の新規ファイル、または `bookmarks/` 経由で取り込んだ本文）を wiki に統合する。

手順:
1. ソースを読み、要点をユーザーと（必要なら）議論する。
2. `wiki/topics/` or `wiki/entities/` に要約ページを作る（frontmatter: title/created/updated/tags/sources/related）。
3. **1 ソースが 10〜15 ページに波及しうる**。関連する既存ページの相互参照（`related`）を更新する。
4. `wiki/index.md` に新ページを登録する（孤立ページを作らない）。
5. `wiki/log.md` に追記する: `## [YYYY-MM-DD] ingest | <要約>`（影響ページ・ソースを列挙）。

## 操作 2: Query（問い合わせ）

ユーザーの質問に wiki を検索・統合して答える。

- 回答は **引用付き**（どの wiki ページ / `raw/` ソースに基づくか）で示す。
- wiki に答えがなければそう言い、必要なら ingest を提案する。
- 価値ある回答は **新しい wiki ページとして還元** してよい（その場合 index/log も更新）。

## 操作 3: Lint（健全性チェック）

ハルシネーション蓄積を防ぐ最重要機構。RAG と違い、LLM Wiki では誤りがリンクページ群に焼き付くため、定期実行する。

検出対象:
- **矛盾**: ページ間で食い違う主張。`raw/` と突き合わせて是正。
- **陳腐化**: 古くなった主張・リンク切れ。
- **孤立ページ**: `wiki/index.md` からも他ページからもリンクされていないページ。
- **欠落した相互参照**: 関連するのに `related` で繋がっていないページ。
- **データギャップ**: index に載るが実体がない / 実体があるが index にない。

出力: 検出した問題を一覧化し、自動修正できるものは直し、判断が要るものは GitHub Issue（`type:improvement`）化する。

> lint の定期自動実行は Claude Code のルーティン機能で回す（`docs/automation/routines.md`）。gh-aw は使わない。

## frontmatter 規約（再掲）

- `raw/`: `title` / `source_url` / `captured_at` / `type`
- `wiki/`: `title` / `created` / `updated` / `tags` / `sources` / `related`
- `ideas/`: `title` / `created` / `status` / `tags` / `related_repos`
- `bookmarks/`: `url` / `title` / `added` / `status` / `tags`

日時はすべて JST（`datetime-rules.md`）。

## CJK Markdown

wiki/ideas 等の `.md` を新規作成・修正したら、PR 前に `python3 tools/check_cjk_markdown.py --fix --changed` を実行する（CLAUDE.md「Markdown 出力ルール」）。
