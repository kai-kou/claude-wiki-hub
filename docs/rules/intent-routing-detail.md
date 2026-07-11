# インテントルーティング実行手順詳細（Warm 層）

> `intent-routing.md`（Hot 層 SSOT）§1 の分類テーブルに対応する、各インテント（R-1〜R-5）の
> 具体的な実行手順・横断インデックスの詳細。Hot 層は分類判断に必要な情報のみを保持し、
> 実行時の手順詳細はここを参照する（Haiku Context Overflow 再発防止・Hot 層ダイエット #2026-07-03）。

## R-1: bookmark（URL を貼る → 自動整理）

> 「ブックマークレットの設定方法は？」「URL 保存のコードをくれ」等の **セットアップ案内発話** には、R-1 の前段として `docs/setup/bookmarklet-setup.md` の公式コードをそのまま案内する（**その場で別物を即興生成しない**・コードの SSOT は同ファイル）。

```
1. URL から WebFetch でタイトル・要点を取得（取れなければ URL のみで続行）
2. bookmarks/inbox.md に 1 エントリ追記（フォーマットは bookmarks/README.md）
   - title: 取得したタイトル
   - tags: 内容から 2〜4 個を自動付与（既存 bookmarks のタグ語彙に寄せる）
   - status: unread
   - 一言: なぜ価値がありそうか（取得要点から 1 行）
3. `python3 tools/build_index.py --quiet` で横断インデックスを再生成（下記「横断インデックス」参照）
4. GitHub Issue を作成（`kind:bookmark` ラベル・タイトル = ブックマークタイトル・本文に URL とファイルパスを記載）
   ※ PAT（`GH_TOKEN`）未登録時は Issue 作成を **省略** し、ファイルのみで続行する（R-3 と同型のフォールバック）
5. 「ブックマークしたにゃ。タグ: [...]（Issue #N）」と報告
```

価値が高い・ユーザーが「これ知識化して」と言った場合は R-4/R-5 と同様に `raw/` 取り込み → ingest へ昇格
（昇格したら Issue に `status:ingested` を付けて「→ Ingested: wiki/...」コメントでクローズする）。

## R-2: idea（「〇〇よさそう」→ アイデア化）

```
1. ideas/YYYY-MM-DD-<slug>.md を作成（フォーマットは ideas/README.md）
   - title: 発話を一言サマリに
   - status: raw
   - tags: 内容から自動付与
   - related_repos: 適用できそうな既存リポジトリがあれば補完
2. 既存 ideas/ に類似があれば「これ前にも話したにゃ（#リンク）」と横断推薦（横断インデックスを grep）
3. `python3 tools/build_index.py --quiet` で横断インデックスを再生成
4. GitHub Issue を作成（`kind:idea` ラベル・タイトル = アイデア一言サマリ・本文にファイルパスを記載）
   ※ PAT 未登録時は Issue 作成を省略しファイルのみで続行（R-1 と同じ）
5. 「アイデアとして残したにゃ（Issue #N）」と報告
```

> **Issue ライフサイクル（#77 設計）**: idea/bookmark Issue は open = 未処理。クローズは 3 区別 —
> タスク派生（新タスク Issue 作成 + 元 Issue に「→ Promoted: #N」コメント）/ wiki 昇格（`status:ingested`）/
> 棚上げ（`status:archived`）。open 中の同ラベルは「遷移待ち/候補」の意味（open + `ingested` = 昇格予約 →
> トリアージが ingest してクローズ。open + `archived` = 棚卸し候補・クローズ確定はユーザー判断）。
> GitHub UI テンプレートから直接投稿された Issue（ファイル未作成）は
> `inbox-groomer` スキルの定期トリアージがファイル・タグを補完する。
> **拡張ポイント**: 全 R-1/R-2 発話の Issue 化で Issue が増えすぎる場合、ユーザーが「Issue 化しなくていい」と
> 言えばファイルのみの運用に切り替えられる（`kind:` フィルタで混在の実害は限定的なため MVP は全件 Issue 化）。

## R-3: task（「〇〇やらなきゃ」→ タスク化）

```
1. GitHub Issue を作成（type ラベルを内容から推定・sp 付与）
2. 締切・スコープが不明確なら、ここだけ最小限確認する:
   「いつまで？」「どこまでやれば完了？（Done 条件）」
   → 答えやすいよう推奨案を添える（例: 「今週中でよい？」）
3. 明確なら確認なしで Issue 化し「タスク化したにゃ（#N）」と報告
```

> task 化は `user-instruction-issue-rules.md` の Issue 化基準に従う。締切・Done 条件の確認は
> A-1〜A-6 の確認ではなく「仕様確定（Think Before Coding）」なので、推奨案つきで素早く聞く。

> **PAT 未登録の最小構成（標準）でのフォールバック**: GitHub Issue 化は GitHub MCP（`mcp__github__*`）を使うため
> `GH_TOKEN` が要る。未登録なら Issue を作らず、リポ内の軽量 TODO（例: `ideas/` または `wiki/log.md` に
> `TODO:` 行を追記）として **git コミットで** 記録し、「自動化層（PAT 登録）を入れると GitHub Issue 化・
> PR 自動化が使えるにゃ」と 1 行案内する。bookmark/idea/wiki（R-1/R-2/R-4）はファイル＝コミットのみで動くため
> PAT 不要。R-5 のディープリサーチ成果物も同様にファイルとして残る。

## R-4: query（「〇〇ってなんだっけ？」→ 検索 → 回答 → ナレッジ化）

```
1. まず wiki/ を検索（wiki/index.md → 該当 topics/entities ページ）
2. wiki でミス → 横断インデックスを grep（bookmarks/ideas/raw も含め全種別を 1 ファイルで横断）
   例: grep -i "<キーワード>" content/index/all.jsonl
3. ヒット → 引用付きで回答（どの wiki ページ / 保存物に基づくか明示）
4. ミス → WebSearch/WebFetch で最新の一次情報を取得して回答（CP-2）
   - 回答が再利用価値を持つなら wiki/ に新ページとして還元（ingest・index/log + build_index.py）
5. 「wiki に無かったので調べて答えたにゃ。ナレッジ化しておく？」と提案（または自動 ingest）
```

> 「**こういうの保存したことなかったっけ？**」型の発話は本フローの入口。検索経路の SSOT は
> `save-metadata-index.md` §5。wiki/index.md → `content/index/all.jsonl` grep → git grep → Web の順。

合成・複数ソースの突合が必要なら Sonnet サブエージェントにエスカレーションする。

## R-5: research（「〇〇について調べて」→ ディープリサーチ → ナレッジ化）

```
1. research-runner スキルを起動（既定で /deep-research・Opus orchestrator）
   → 軽微・コスト優先のときだけ理由を 1 行述べて WebSearch 簡易リサーチに切替（CLAUDE.md SSOT）
2. 成果物（content/research/）を wiki/ に ingest（要約ページ + index/log 更新 + 相互参照 + build_index.py）
3. ユーザーには「分かりやすい解説」を本文で提示（専門用語は噛み砕く）
```

## 横断インデックス（保存物の検索コスト削減・SSOT: `save-metadata-index.md`）

保存（R-1/R-2/R-4/R-5）した bookmark / idea / wiki / raw を **1 枚に束ねた機械可読インデックス**
`content/index/all.jsonl` を維持する。「こういうのなかったっけ？」検索と集計/分析の土台。

- **更新**: 保存操作の直後に `python3 tools/build_index.py --quiet` を呼ぶ（frontmatter から全件再生成。
  インデックスは導出物なので手編集しない・迷ったら再生成してよい）。
- **検索**: `grep -i "<語>" content/index/all.jsonl` で全種別を横断（title/tags/`cat:`/ref/path）。
  複合条件（kind × tag × status × date）・全文検索・集計が要るときは `python3 tools/query_index.py search/sql/stats`
  を使う（少件数では自動的に grep バックエンドで動くので常用してよい・件数増大で SQLite に自動切替・#26）。
- **集計**: `content/index/stats.json`（kind 別・カテゴリ・タグ頻度・月次）を読む。
  または `python3 tools/query_index.py stats`（同等の集計をクエリ層から取得）。
- **メタデータ**: いつ（date）/ 何（kind）/ カテゴリ（`cat:` タグ）/ タグ / status を frontmatter から導出。
  カテゴリは専用フィールドを持たず **`cat:` プレフィックスのタグ** で表す（例: `cat:pkm`）。
- **desync 防止**: `tools/check_index_sync.py` が PR 前 e2e（`test_index_sync.sh`）で不一致を exit 1 検出。

> 詳細（フィールド定義・タグ正規化・検索経路・集計）は `docs/rules/save-metadata-index.md` が SSOT。

## 参照

| ドキュメント | 関係 |
|---|---|
| `docs/rules/intent-routing.md` | Hot 層 SSOT（インテント分類テーブル・モデル使い分け） |
| `docs/rules/wiki-operations.md` | ingest/query/lint の操作 SSOT |
| `docs/rules/user-instruction-issue-rules.md` | task 化（R-3）の Issue 化基準 |
| `.claude/skills/research-runner/SKILL.md` | research（R-5）の実行エンジン |
| `docs/setup/bookmarklet-setup.md` | ブックマークレット登録手順・公式コード |
| `docs/rules/save-metadata-index.md` | 横断インデックス・メタデータ規約・検索/集計の SSOT |
