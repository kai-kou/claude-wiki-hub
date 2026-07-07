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

R-1（bookmark）〜R-5（research）の具体的な実行手順・横断インデックス（`content/index/all.jsonl`）の
詳細は `docs/rules/intent-routing-detail.md` 参照。要点: 保存系（R-1/R-2）は該当ディレクトリに1エントリ
追記 + `python3 tools/build_index.py --quiet` で横断インデックス更新。task化（R-3）は GitHub Issue 化
（PAT 未登録時はファイル直コミットにフォールバック）。query（R-4）は wiki→横断インデックス→Web の順で検索。
research（R-5）は research-runner 経由でディープリサーチ→ingest。

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
- [ ] 保存後に横断インデックス（`content/index/all.jsonl`）が更新され「なかったっけ？」検索を 1 ファイルで横断できる（詳細は `intent-routing-detail.md`）

## 5. 参照

| ドキュメント | 関係 |
|---|---|
| `docs/rules/intent-routing-detail.md` | R-1〜R-5 の実行手順・横断インデックス詳細（§2 が呼び出す先） |
| `docs/rules/wiki-operations.md` | ingest/query/lint の操作 SSOT（本ルールが呼び出す先） |
| `docs/rules/user-instruction-issue-rules.md` | task 化（R-3）の Issue 化基準 |
| `docs/rules/agent-team-summary.md` | モデル選択・サブエージェント使い分け |
| `.claude/skills/research-runner/SKILL.md` | research（R-5）の実行エンジン |
| `docs/setup/bookmarklet-setup.md` | ブックマークレット登録手順・公式コード（R-1 前段のセットアップ案内先・即興生成禁止） |
| `bookmarks/README.md` / `ideas/README.md` | bookmark/idea のフォーマット |
| `docs/rules/save-metadata-index.md` | 横断インデックス・メタデータ規約・検索/集計の SSOT |
