# インテントルーティング（日常使いの自然言語ルーティング・SSOT）

> 本プロジェクト（Claude Wiki Hub）の **日常使いの中核**。ユーザーの自然な発話を、確認の儀式なしに
> 正しい操作（bookmark / idea / task / query / research）へ自動で振り分けるためのルール。
> `.claude/rules/` 経由で常駐（Hot 層）。操作の不変条件は `wiki-operations.md` が SSOT。

## 0. 大原則: 入力ハードルをゼロにする

PKM が続かない最大の理由は「整理の摩擦」。ユーザーは **思いついたことをそのまま話す** だけでよい。
分類・タグ付け・タスク化・リサーチ・ナレッジ化は Claude が肩代わりする。

- **発話のたびに「これは何の操作か？」を分類する**（下表）。明確なら確認なしで実行する。
- **不明確なときだけ最小限の確認** をする（特に task 化の締切・スコープ）。
- 実行後は「何をしたか」を 1〜2 行で報告する（どのファイルに何を追記したか・タグ）。

## 1. インテント分類テーブル

| # | 発話パターン（例） | インテント | 操作 | 既定モデル |
|---|---|---|---|---|
| R-1 | URL だけ / 「これブックマーク」「あとで読む」 | **bookmark** | `bookmarks/` に追記 + 自動分類・タグ | Haiku |
| R-2 | 「〇〇よさそう」「〇〇いいかも」「〇〇ってアリかも」 | **idea** | `ideas/` に 1 ファイル追加 + tags/関連補完 | Haiku |
| R-3 | 「〇〇やらなきゃ」「〇〇しないと」「TODO: 〇〇」 | **task** | GitHub Issue 化（不明確なら確認） | Haiku |
| R-4 | 「〇〇ってなんだっけ？」「〇〇について教えて」 | **query** | wiki 検索 → なければ Web → 回答 → ナレッジ化 | Haiku→Sonnet |
| R-5 | 「〇〇について調べて」「〇〇をリサーチして」 | **research** | ディープリサーチ → ingest → 解説 | research-runner（Opus） |

> 判定に迷ったら、最も入力ハードルが低い解釈を採る（例: URL + 一言なら bookmark、断定形の願望なら idea）。
> 1 発話に複数インテントが混ざる場合（「この記事よさそう、あとで深掘りして」= bookmark + research）は
> 両方実行する。

> **セットアップ・初期設定・アップデート取り込み**（「セットアップして」「初期設定して」「使い始めたい」「アップデート取り込んで」）は
> 上表の日常 5 インテントとは別レイヤー。`/onboarding`（`docs/setup/onboarding.md`）で Claude が bootstrap・ミッション記入・初期コミット → PR を **代行** する。
> いずれも本プロジェクトの絶対条件「ユーザーは指示だけ、スクリプト実行は Claude」に従い、ユーザーにコマンド実行を求めない（`CLAUDE.md`「絶対条件」節）。

## 2. 各インテントの実行手順

### R-1: bookmark（URL を貼る → 自動整理）

> 「ブックマークレットの設定方法は？」「URL 保存のコードをくれ」等の **セットアップ案内発話** には、R-1 の前段として `docs/setup/bookmarklet-setup.md` の公式コードをそのまま案内する（**その場で別物を即興生成しない**・コードの SSOT は同ファイル）。

```
1. URL から WebFetch でタイトル・要点を取得（取れなければ URL のみで続行）
2. bookmarks/inbox.md に 1 エントリ追記（フォーマットは bookmarks/README.md）
   - title: 取得したタイトル
   - tags: 内容から 2〜4 個を自動付与（既存 bookmarks のタグ語彙に寄せる）
   - status: unread
   - 一言: なぜ価値がありそうか（取得要点から 1 行）
3. `python3 tools/build_index.py --quiet` で横断インデックスを再生成（§2.6）
4. 「ブックマークしたにゃ。タグ: [...]」と報告
```

価値が高い・ユーザーが「これ知識化して」と言った場合は R-4/R-5 と同様に `raw/` 取り込み → ingest へ昇格。

### R-2: idea（「〇〇よさそう」→ アイデア化）

```
1. ideas/YYYY-MM-DD-<slug>.md を作成（フォーマットは ideas/README.md）
   - title: 発話を一言サマリに
   - status: raw
   - tags: 内容から自動付与
   - related_repos: 適用できそうな既存リポジトリがあれば補完
2. 既存 ideas/ に類似があれば「これ前にも話したにゃ（#リンク）」と横断推薦（§2.6 の index を grep）
3. `python3 tools/build_index.py --quiet` で横断インデックスを再生成（§2.6）
4. 「アイデアとして残したにゃ」と報告
```

### R-3: task（「〇〇やらなきゃ」→ タスク化）

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

### R-4: query（「〇〇ってなんだっけ？」→ 検索 → 回答 → ナレッジ化）

```
1. まず wiki/ を検索（wiki/index.md → 該当 topics/entities ページ）
2. wiki でミス → 横断インデックスを grep（§2.6・bookmarks/ideas/raw も含め全種別を 1 ファイルで横断）
   例: grep -i "<キーワード>" content/index/all.jsonl
3. ヒット → 引用付きで回答（どの wiki ページ / 保存物に基づくか明示）
4. ミス → WebSearch/WebFetch で最新の一次情報を取得して回答（CP-2）
   - 回答が再利用価値を持つなら wiki/ に新ページとして還元（ingest・index/log + build_index.py）
5. 「wiki に無かったので調べて答えたにゃ。ナレッジ化しておく？」と提案（または自動 ingest）
```

> 「**こういうの保存したことなかったっけ？**」型の発話は本フローの入口。検索経路の SSOT は
> `save-metadata-index.md` §5。wiki/index.md → `content/index/all.jsonl` grep → git grep → Web の順。

合成・複数ソースの突合が必要なら Sonnet サブエージェントにエスカレーションする。

### R-5: research（「〇〇について調べて」→ ディープリサーチ → ナレッジ化）

```
1. research-runner スキルを起動（既定で /deep-research・Opus orchestrator）
   → 軽微・コスト優先のときだけ理由を 1 行述べて WebSearch 簡易リサーチに切替（CLAUDE.md SSOT）
2. 成果物（content/research/）を wiki/ に ingest（要約ページ + index/log 更新 + 相互参照 + build_index.py）
3. ユーザーには「分かりやすい解説」を本文で提示（専門用語は噛み砕く）
```

## 2.6 横断インデックス（保存物の検索コスト削減・SSOT: `save-metadata-index.md`）

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

## 3. モデル自動使い分け（手動指定不要）

「基本 Haiku、重い処理だけ自動エスカレーション」を実現する。ユーザーがモデルを指定する必要はない。

| 処理の重さ | 担当 | モデル |
|---|---|---|
| 分類・bookmark/idea 追記・明確な task 化・wiki ヒット時の回答 | メインセッション | **Haiku**（既定） |
| 複数ソースの合成・wiki ページ生成（ingest）・矛盾解消 | サブエージェント | Sonnet |
| ディープリサーチ（多段検索・出典検証・長文統合） | research-runner | Opus（orchestrator） |

- メインセッションの既定モデルは `.claude/settings.json` の `model`（本テンプレートは `claude-haiku-4-5`）。
- エスカレーションは **このルールに基づき Claude が自動判断** する（`Agent` ツールの `model` 指定・スキルの内部モデル）。
- 重い処理を Haiku のメインで抱え込まない。質を要する生成は Sonnet 以上のサブエージェントに必ず委譲する。
- コスト最優先で「全部 Haiku」にしたい日は、ユーザーが「軽めで」と言えば R-5 も簡易リサーチに倒す。

## 4. 完了・成功の定義

- [ ] URL を貼るだけで bookmark + 自動タグが付く
- [ ] 「〇〇よさそう」で idea ファイルが残る
- [ ] 「〇〇やらなきゃ」で Issue 化され、不明確なときだけ Done 条件を確認する
- [ ] 「〇〇ってなんだっけ？」で wiki 優先 → なければ Web → ナレッジ化される
- [ ] 「〇〇について調べて」で research-runner が動きナレッジ化 + 解説される
- [ ] モデルが処理の重さで自動的に Haiku/Sonnet/Opus に振り分けられる（手動指定不要）
- [ ] 保存後に横断インデックス（`content/index/all.jsonl`）が更新され「なかったっけ？」検索を 1 ファイルで横断できる（§2.6）

## 5. 参照

| ドキュメント | 関係 |
|---|---|
| `docs/rules/wiki-operations.md` | ingest/query/lint の操作 SSOT（本ルールが呼び出す先） |
| `docs/rules/user-instruction-issue-rules.md` | task 化（R-3）の Issue 化基準 |
| `docs/rules/agent-team-summary.md` | モデル選択・サブエージェント使い分け |
| `.claude/skills/research-runner/SKILL.md` | research（R-5）の実行エンジン |
| `docs/setup/bookmarklet-setup.md` | ブックマークレット登録手順・公式コード（R-1 前段のセットアップ案内先・即興生成禁止） |
| `bookmarks/README.md` / `ideas/README.md` | bookmark/idea のフォーマット |
| `docs/rules/save-metadata-index.md` | 横断インデックス（§2.6）・メタデータ規約・検索/集計の SSOT |
