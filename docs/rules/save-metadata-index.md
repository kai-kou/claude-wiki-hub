# 保存メタデータ・横断インデックスルール（SSOT）

> **このファイルは「ユーザー指示による各種保存（bookmark / idea / wiki / raw）のメタデータ規約と、
> 保存系横断インデックスの生成・検索・集計」の唯一の正本（SSOT）である。**
> 専門チーム議論（Issue #24・`content/discussions/save-metadata-index/whiteboard.md`）の合意設計に基づき新設。
> 本ファイルは **タスク依存**（Warm 層）。保存・検索・インデックス保守を行う時に Read する。
> 日常使いの検索経路の要点は `intent-routing.md`（Hot 層）が参照する。

---

## 0. 目的（なぜ必要か）

ユーザーが「**こういうのなかったっけ？**」と尋ねたとき、保存物（bookmarks / ideas / wiki / raw）を
1 つずつ grep して回ると検索コストが高い。**横断インデックス 1 枚** に集約することで:

1. **検索コスト削減**: Claude が `content/index/all.jsonl` を grep / 読むだけで全種別を横断検索できる。
2. **集計/分析**: kind 別件数・カテゴリ分布・タグ頻度・月次推移を `content/index/stats.json` から即座に得られる。

---

## 1. 設計原則（専門チーム議論の合意・YAGNI 厳守）

敵対的議論（schema-designer / index-architect / ops-maintainer / search-analytics）の結論:

- **インデックスは導出物**。唯一の真実源は **各ファイルの frontmatter**。`all.jsonl` を手で編集しない。
- **新フィールドは増やさない**。`category` / `saved_at` / `week` 等の専用フィールドは YAGNI 却下。
  カテゴリは **`cat:` プレフィックスのタグ** で表現する（後述）。
- **kind は path から自動導出**（`bookmarks/`→bookmark 等）。既存ファイルの編集は不要。
  frontmatter に明示的に `kind:` を書けば上書きできる（任意）。
- **依存は標準ライブラリ + PyYAML のみ**（既存 `requirements.txt`）。検索エンジン・embedding は導入しない。

---

## 2. メタデータ規約（各保存層の frontmatter）

既存の frontmatter 規約（各 `README.md`）を **壊さず** 使う。インデックスは以下を導出する:

| 概念（ユーザー要求） | 導出元フィールド（層ごと） |
|---|---|
| **いつ保存したか**（`date`） | bookmark `added` / idea・wiki `created` / raw `captured_at` |
| **どういう情報か**（`kind`） | path から導出（bookmark/idea/wiki/raw）。frontmatter `kind:` で上書き可 |
| **タイトル**（`title`） | 各層 `title` |
| **状態**（`status`） | bookmark・idea の `status`（wiki/raw は null 可） |
| **タグ**（`tags`） | 各層 `tags`（raw は任意） |
| **カテゴリ** | `tags` の中の **`cat:` プレフィックス**（例: `cat:tooling`・専用フィールドは持たない） |
| **参照**（`ref`） | bookmark `url` / raw `source_url` |

### タグ正規化ルール

インデックス生成時に `tools/build_index.py` がタグを正規化する（frontmatter 自体は自由に書いてよい）:

- **lowercase**（`LLM` → `llm`）
- **空白・アンダースコアをハイフン化**（`daily capture` / `daily_capture` → `daily-capture`）
- **重複除去**
- **`cat:` プレフィックス** はカテゴリ扱い（`cat:tooling` → 集計の `by_category` に計上）

> 表記ゆれを抑えるため、新規タグは最初から lowercase・ハイフン区切りで付けるのが望ましい。
> カテゴリとして集計したいタグには `cat:` を付ける（例: `cat:pkm`・`cat:research`）。

---

## 3. インデックスの構造

| ファイル | 形式 | 役割 |
|---|---|---|
| `content/index/all.jsonl` | JSONL（1 レコード = 1 行） | **機械可読の横断インデックス**。grep / 行単位 diff フレンドリー |
| `content/index/stats.json` | JSON | 集計/分析の派生指標（kind 別・カテゴリ・タグ・月次） |
| `wiki/index.md` | Markdown | **人間向けの目次**（役割分離・存続）。wiki 層のキュレーション |

`all.jsonl` の 1 レコード（キーは決定論のため **アルファベット順** にソートして出力）:

```json
{"date":"2026-06-25","id":"bookmark:2b944867","kind":"bookmark","path":"bookmarks/inbox.md","ref":"https://...","status":"unread","tags":["llm","wiki"],"title":"..."}
```

- `id`: 安定 ID（per-file は `<kind>:<層ルート配下の相対パス・拡張子なし>`。例 `wiki:topics/karpathy-llm-wiki`。
  層内の同名 stem でも衝突しない。inbox の各エントリは `bookmark:<url の sha1 先頭 8 桁>`）。重複検出・参照に使う。
- 行の並びは `kind → date → id → path` で決定論的、各行のキーもアルファベット順（diff ノイズを抑制）。

---

## 4. 生成・更新・desync 検出

| ツール | 役割 |
|---|---|
| `tools/build_index.py` | frontmatter 全スキャン → `all.jsonl` + `stats.json` を **全件再生成**（`--stats` で集計表示・`--quiet` で静音） |
| `tools/check_index_sync.py` | `all.jsonl` が frontmatter と一致するか検証。desync なら **exit 1**（修正方法を表示） |

### 更新タイミング（慣習）

- **保存操作（intent-routing の R-1 bookmark / R-2 idea / R-4・R-5 の wiki ingest）の直後** に
  `python3 tools/build_index.py --quiet` を呼んでインデックスを再生成する。
- `all.jsonl` は導出物なので、迷ったらいつでも再生成してよい（手編集による desync が起きない設計）。
- `tests/e2e/test_index_sync.sh` が PR 前の self-reviewer e2e（`scripts/run-e2e.sh`）で desync を検出する。

---

## 5. 検索経路（「こういうのなかったっけ？」）

ユーザーが過去の保存物を探す発話をしたら、以下の順で最短到達する:

```
1. wiki/index.md を見る（人間向け目次・キュレーション済みの知識）
2. content/index/all.jsonl を grep（全種別横断・title/tags/cat:/ref/path）
   例: grep -i "pkm" content/index/all.jsonl
   → 複合条件（kind × tag × status × date 範囲）・全文検索・集計が要るときは §5.1 のクエリ層を使う
3. git grep で本文も検索（インデックスに無い本文の語）
4. それでも無ければ Web（CP-2・新規なら ingest を提案）
```

ヒットしたら該当 `path` のファイルを開いて引用付きで答える（wiki-operations の query と同じ作法）。

### 5.1 クエリ層（grep⇄SQLite 自動切替・`tools/query_index.py`・#26）

情報量が増えて grep の線形コスト・複合条件・全文検索が辛くなる場合に備えた **統一クエリ層**。
専門チーム議論（#26・`content/discussions/cloud-native-datastore/`）の合意設計:

| 観点 | 決定 |
|---|---|
| エンジン | **SQLite（Python 標準ライブラリ・追加依存ゼロ）**。DuckDB は pip 依存が現クラウド環境で不可のため除外（将来候補） |
| 真実源 | frontmatter のまま。導出連鎖は `frontmatter → all.jsonl → all.db`。**all.db は gitignore されたエフェメラル成果物**（binary を commit しない） |
| バックエンド | **件数で自動選択**: `records < 500` は **grep**（all.jsonl 線形スキャン・成果物なし=YAGNI）、`≥ 500` は **SQLite**（B木インデックス + FTS5）。CLI は同一なので呼び出し側は無変更で切り替わる |
| CJK 全文検索 | FTS5 既定 `unicode61` は日本語を単語分割しないため不使用。**`trigram` トークナイザ**（3 文字以上）+ 1〜2 文字短語は **LIKE フォールバック** |
| 後方互換 | `all.jsonl` は tracked のまま。`check_index_sync.py` は frontmatter↔all.jsonl の検証のみで変更不要。既存 grep 検索は維持 |

使い方（少件数では自動的に grep で動くため、いつ使ってもよい）:

```bash
python3 tools/query_index.py search "比較"                 # 全文/部分一致（自動バックエンド）
python3 tools/query_index.py search wiki --kind bookmark --status unread   # 複合フィルタ
python3 tools/query_index.py sql "SELECT kind,COUNT(*) FROM records GROUP BY kind"  # SQLite
python3 tools/query_index.py stats          # kind/status/tag/月次の集計
python3 tools/query_index.py backend        # 現在の自動選択バックエンドと件数を確認
```

> **段階導入（議論 #26）**: Phase 0（今）= grep バックエンド + CLI + .gitignore 安全網。
> Phase 1 = SQLite activation（`records ≥ 500` かつ P95 grep ≥ 200ms 実測で自動切替）。
> Phase 2 = FTS5 trigram 全文検索の本格運用。Phase 3 = DuckDB 動的集計（将来保留）。

---

## 6. 集計/分析

`content/index/stats.json`（`build_index.py` が生成）から以下が即座に得られる:

- `total` / `by_kind`（bookmark・idea・wiki・raw の件数）
- `by_status`（unread・read・triaged 等の分布）
- `by_category`（`cat:` タグの分布）
- `by_tag`（タグ頻度・降順）
- `by_month`（保存の月次推移）

新しい指標が欲しくなったら、**新 frontmatter フィールドを足さず** `all.jsonl` から導出する
（タグ共起・週次集計などは `all.jsonl` を読む小ツールで後付け可能）。

---

## 7. スコープ外（現フェーズ）

- **task 層（GitHub Issue）**: Issues は GitHub 側で検索・集計できるため、現フェーズはインデックス対象外（YAGNI）。
- **embedding / ベクトル検索（意味検索）**: 件数が少ないうちは grep / SQLite FTS5 で足りる（`ideas/2026-06-25-wiki-search-ux.md` の将来案）。導入は別 Issue（議論 #26 では「将来保留」）。
- **DuckDB による動的集計**: pip 追加依存が現クラウド環境で不可のため現フェーズ除外（議論 #26 Phase 3 候補）。

> **解消済み**: 「複合条件クエリ・全文検索・件数増大時の検索コスト」は §5.1 のクエリ層（`tools/query_index.py`・SQLite 標準ライブラリ）で対応する（旧 §7 の BM25 課題を含む）。

---

## 8. 完了・成功の定義

- [ ] `tools/build_index.py` が bookmarks/ideas/wiki/raw を全スキャンし `all.jsonl` + `stats.json` を生成する
- [ ] `tools/check_index_sync.py` が desync を exit 1 で検出する
- [ ] `tests/e2e/test_index_sync.sh` が `scripts/run-e2e.sh` で実行され PASS する
- [ ] 「なかったっけ？」検索が wiki/index → all.jsonl grep の 2 ステップで横断できる
- [ ] 集計指標（kind/category/tag/月次）が stats.json から得られる
- [ ] 既存 frontmatter を壊していない（rename・必須フィールド追加ゼロ）

---

## 9. 参照

| ドキュメント | 関係 |
|---|---|
| `docs/rules/intent-routing.md` | 保存（R-1/R-2/R-4/R-5）と検索経路の Hot 層。本ファイルの検索経路を参照 |
| `docs/rules/wiki-operations.md` | wiki ingest/query/lint。インデックスは lint のデータギャップ検出と同根 |
| `docs/rules/datetime-rules.md` | 日付は JST（表示・記録）。`date` フィールドは YYYY-MM-DD |
| `tools/build_index.py` / `tools/check_index_sync.py` | 生成・desync 検出の実体 |
| `tools/query_index.py` | §5.1 クエリ層（grep⇄SQLite 自動切替・全文検索・複合フィルタ・読取専用 SQL・集計） |
| `content/discussions/save-metadata-index/whiteboard.md` | 専門チーム議論の全履歴（メタデータ規約の根拠） |
| `content/discussions/cloud-native-datastore/whiteboard.md` | 専門チーム議論の全履歴（§5.1 クエリ層設計の根拠・#26） |
