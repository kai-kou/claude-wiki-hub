# Claude Wiki Hub

**GitHub をデータストア、Claude Code を唯一のインターフェースとする、個人エンジニア向けのナレッジ/タスク/アイデア管理ハブ。**

Andrej Karpathy の「LLM Wiki」パターン（LLM が永続 wiki をインクリメンタルに構築・維持する）を中核に、ナレッジ・タスク・アイデア・ブックマークを 1 つのリポジトリに集約する。整理の摩擦は Claude が肩代わりする。

> このリポジトリは **GitHub Template Repository** です。右上の **"Use this template"** → "Create a new repository" で
> あなた専用の private リポジトリを作成してすぐに使い始められます（[クイックスタート](#クイックスタート)）。

## クイックスタート（3ステップで使い始める・PAT 不要）

> **前提**: [Claude.ai](https://claude.ai) のアカウントと GitHub アカウントが必要。
>
> **このプロジェクトの絶対条件**: **ユーザーは指示だけ・実装やスクリプト実行は Claude が代行**。
> ユーザーの作業は GitHub / claude.ai の **Web 設定（Step 1〜2）だけ**。`git clone` や `bash bootstrap.sh` を手元のターミナルで実行する必要はなく、セットアップは Claude に「セットアップして」と言うだけ（Step 3）。
>
> **標準構成は GitHub PAT 不要**。Claude Code on the web の GitHub 接続（Claude GitHub App / `/web-setup`）が clone/push を担うため、**個人 wiki を育てる日常利用はトークン設定なしで完結** します。Issue/PR の自動化や Slack 連携など自動化層を使うときだけ、後述の[任意の PAT 登録](#任意-自動化層を有効化する-github-pat-を登録)を行います。

### Step 1 — テンプレートからリポを作成

1. このページ右上の **"Use this template"** → **"Create a new repository"** をクリック
2. Repository name を入力（例: `my-wiki`）
3. **Private** を選択（個人データが入るため推奨）
4. **"Create repository"** をクリック

### Step 2 — claude.ai プロジェクトを運用リポに接続（Claude GitHub App・Web のみ）

claude.ai → 新規プロジェクト → **"Connect a GitHub repository"** → `<あなた>/<your-wiki>` を選択し、**Claude GitHub App** を承認する。

- 接続するとコンテナにリポがチェックアウト済みで起動するため、**`git clone` は不要**。
- この App 接続が **clone/push（git 操作）の認証を担う** ため、**標準構成では GitHub PAT を発行・登録する必要はありません**（[Claude Code on the web 公式](https://code.claude.com/docs/en/claude-code-on-the-web)）。
- `gh` CLI のインストール・`gh auth login` も不要（ハーネスが内部で使う任意ツール）。

### Step 3 — Claude に「セットアップして」と言うだけ

接続したプロジェクトのチャットで、こう言うだけ:

```
セットアップして
```

→ Claude が **bootstrap（プレースホルダ置換・ルール symlink 同期）・ミッション記入（対話ヒアリング）・初期コミット** を代行します（`/onboarding`・[`docs/setup/onboarding.md`](docs/setup/onboarding.md)）。
**ユーザーがターミナルで `git clone` や `bash bootstrap.sh`、`$EDITOR` を実行する必要はありません。** ミッション（関心領域・KPI）だけ Claude が短くヒアリングします。

> **方針: PR 作成 → AI レビュー対応 → 自動マージまで Claude が自律実行します**（確認なし・`CLAUDE.md`「PR 作成の完全自律化」）。この完全自律フローは自動マージが GitHub MCP（要 PAT）依存のため **PAT 登録を前提** とします。PAT 未登録の最小構成は **日常 wiki 利用（ファイル直コミットで完結・PR マージを伴わない）** が対象で、`git` の clone/push・PR の作成（オープン）までは GitHub App で PAT 不要に実行できます（[公式: GitHub authentication options](https://code.claude.com/docs/en/claude-code-on-the-web#github-authentication-options)）。**PR を生む自動化（レビュー対応・自動マージ・タスクの Issue 化）を使うなら PAT を登録** してください（人間がマージ作業をする運用は想定しません）。この区分は[ルーティン定期実行](#定期実行自動化)でも同じです。

### Step 4 — 話しかけるだけ（日常使い）

あとは日本語で話しかけるだけ（[日常使い](#日常使い)）。URL を貼る・「〇〇よさそう」・「〇〇やらなきゃ」・「〇〇ってなんだっけ？」——分類・整理・ナレッジ化は Claude が肩代わりします。

### （任意）— 自動化層を有効化する GitHub PAT を登録

以下を使いたいときだけ、PAT（`GH_TOKEN`）を **任意のアップグレード** として登録します（標準の wiki 利用には不要）:

- **Issue/PR の完全自動化**（タスクの Issue 化・PR レビュー → 自動マージ）
- **GitHub Repository Variables 経由の secrets 一元管理**（Slack 通知・R2 メディア等）
- **クロスリポ操作**（メンテナ向け: 公開テンプレートへの同期）

手順:

1. GitHub → Settings → Developer settings → **Personal access tokens (Classic)** → `repo` スコープで Generate（org の teams 機能を使う場合は `read:org` も追加）
2. [claude.ai](https://claude.ai) → プロジェクト設定 → **Environment Variables** に `GH_TOKEN` として貼り付け

> なぜ PAT が要るのか: Claude Code のリモート GitHub MCP（`mcp__github__*`）は **PAT 認証** で、Claude GitHub App（git 接続用）とは別物だからです（[GitHub 公式](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-claude.md)）。詳細は [`docs/rules/env-vars.md`](docs/rules/env-vars.md)。

---

### アップデートの取得（今後）

新しいハーネスを取り込みたくなったら、Claude に **「アップデートを取り込んで」** と言うだけ。Claude が `sync-upstream.sh` を実行して差分を確認し、PR を作成します（ユーザーがコマンドを打つ必要はありません）。

[claude-wiki-hub のリリース](https://github.com/kai-kou/claude-wiki-hub/releases) を **Watch → Releases only** でフォローすると更新通知を受け取れます。

## コンセプト

- **チャット = 入力ハードルゼロ**: Claude Code に話しかける感覚でアイデア・メモ・リンクを放り込む。分類・整理・横断推薦は Claude が担う。
- **GitHub native**: バージョン管理・diff・PR レビュー・grep がすべて効く。ローカル DB もクラウド SaaS も持たない。
- **シンプル**: インターフェースは **Claude Code のみ**。LINE/Slack 等の常駐 Bot は持たない。

## アーキテクチャ（LLM Wiki 3 層）

```
┌─ raw/        生ソース（immutable）         … Claude は読むだけ。真実の源
│
├─ wiki/       知識層（Claude が所有）        … LLM 生成の Markdown
│   ├─ index.md   全ページのカタログ
│   ├─ log.md     追記専用の時系列ログ
│   ├─ topics/    トピック解説
│   └─ entities/  人物・ツール・組織
│
├─ ideas/      アイデアストック（人間が投稿 → Claude が整理）
├─ bookmarks/  あとで読むリンク
│
└─ GitHub Issues + Labels  … タスク管理
```

Claude は 3 つの操作で wiki を維持する（詳細は [`docs/rules/wiki-operations.md`](docs/rules/wiki-operations.md)）:

- **Ingest** — ソースを読み、要約ページを作り、index/相互参照を更新し、log に追記する。
- **Query** — wiki を検索・統合して引用付きで答える。良い回答は wiki に還元する。
- **Lint** — 矛盾・陳腐化・孤立ページ・データギャップを検出する（ハルシネーション蓄積の防止）。

## ハーネス（claude-code-base 由来）

自律運用の土台として [`kai-kou/claude-code-base`](https://github.com/kai-kou/claude-code-base) のルール・スキル・フック・エージェント・ツールを取り込んでいる（「全部入りで配布 → 不要なものを opt-out」方式）。

- **ルール**（`.claude/rules/` 常駐 + `docs/rules/` 実体）: 大原則 CP-1〜6 / 確認最小化 / セッション安全 / PR レビューフロー / 教訓管理 ほか + 本プロジェクト中核の `wiki-operations.md`
- **スキル**（`.claude/skills/`）: pr-review-watcher / self-reviewer / project-manager / research-runner / retrospective / skill-creator ほか
- **フック**（`.claude/hooks/`）: main 直 push ブロック / PR 前チェック / 圧縮時の自動保存 / 完了報告チェック ほか
- **コマンド**（`.claude/commands/`）: `/onboarding`（セットアップ代行）/ `/next`（次タスク自律判定）/ `/status`（現状把握）

モジュールの有効/無効は [`modules.yaml`](modules.yaml) で管理する。

## 定期実行・自動化

Claude Code ネイティブのルーティン機能（Routines / Desktop Scheduled Tasks / `/loop`）で回す。**GitHub Actions・gh-aw は採用しない**（他リポジトリと共有の実行枠をすぐ使い切るため・[`docs/rules/no-github-actions.md`](docs/rules/no-github-actions.md)）。方針は [`docs/automation/routines.md`](docs/automation/routines.md) を参照。

> **ルーティンと PAT**: ルーティンの定期自動化は「ファイル更新 → PR を開く」までなら **PAT 不要**（GitHub App が clone/push/PR 作成を担う）。**Issue 化・PR 自動マージ・PR レビュー操作だけ** が PAT（`GH_TOKEN`）で解禁されます。要否の正本表は [`docs/automation/routines.md`](docs/automation/routines.md#ルーティンの-github-認証と-pat-要否正本ssot)、運用手順は [`docs/setup/routines-setup.md`](docs/setup/routines-setup.md) を参照。

## 日常使い

整理の摩擦はゼロ。思いついたことをそのまま話すと、Claude が操作を判断して実行する（詳細: [`docs/rules/intent-routing.md`](docs/rules/intent-routing.md)）。

| あなたの発話 | Claude がやること |
|---|---|
| `https://...`（URL だけ貼る） | ブックマーク化 + タイトル取得 + 自動タグ付け |
| 「〇〇ってよさそう」 | アイデアとして `ideas/` に記録 + 類似アイデアを横断推薦 |
| 「〇〇やらなきゃ」 | GitHub Issue 化（締切・完了条件が不明確なときだけ確認） |
| 「〇〇ってなんだっけ？」 | wiki から回答。無ければ最新情報をリサーチ → 回答 → ナレッジ化 |
| 「〇〇について調べて」 | ディープリサーチ → wiki に ingest → 分かりやすく解説 |

モデルは処理の重さで **自動使い分け**（手動指定不要）: 日常の軽い操作は Haiku、知識生成は Sonnet、ディープリサーチは Opus。

**スマホ・PC からのブックマーク**: ブラウザで開いている記事を数タップで Claude Code に送るブックマークレットが使える。Android / iOS / PC（Chrome・Firefox・Safari）に対応（[設定ガイド](docs/setup/bookmarklet-setup.md)）。

詳細・運用上の注意（個人データの扱い・private 運用）は [`docs/setup/operational-repo.md`](docs/setup/operational-repo.md) を参照。

## dev / template / 運用の分離

| | 開発リポジトリ | テンプレートリポジトリ | 運用リポジトリ |
|---|---|---|---|
| 例 | `kai-kou/claude-wiki-hub`（本リポ） | `kai-kou/claude-wiki-hub`（**public**） | `<you>/<your-wiki>`（**private 推奨**） |
| 役割 | ハーネスの開発・ドッグフーディング | ユーザーが "Use this template" で使い始める入口 | 個人のナレッジ・アイデアを実際に蓄積 |
| `raw/` `wiki/` 等 | 空（`.gitkeep` のみ） | 空（`.gitkeep` のみ）で配布 | 自分のデータが入る |
| 公開範囲 | **private**（個人データのドッグフーディングが可能） | **public**（Template Repository） | **private**（個人情報を含む） |

**メンテナ自身も `claude-wiki-hub` で実運用（ドッグフーディング）** しながら改善できる（private にしたため個人データを入れても安全）。汎用改善は `scripts/publish-template.sh` で `claude-wiki-hub`（パブリックテンプレート）へ同期する。

- テンプレート → 運用リポ: "Use this template" から作成後、`sync-upstream.sh` で更新を取り込む。
- 開発リポ → テンプレート: `bash scripts/publish-template.sh` で同期する（gh CLI または GH_TOKEN が必要）。
- 運用リポ → 開発リポ: ハーネス層の汎用改善だけを PR で還元する（手順は [`docs/setup/operational-repo.md`](docs/setup/operational-repo.md#改善を配布元claude-wiki-hubへ還元し公開テンプレートclaude-wiki-hubに反映するメンテナ向け)）。

## 将来の拡張ポイント（本リポには含めない）

シンプルさ維持のため、以下は別フェーズ/別リポジトリで検討する: `qmd` 等の横断検索基盤 / 2 つ目以降のインターフェース。

## ライセンス

MIT License（[`LICENSE`](LICENSE)）。フォーク・改変・再配布を歓迎する。

## 出自

ハーネス部分は `kai-kou/claude-code-base`（汎用 Claude Code 自律運用ベース）由来。
コンセプトは Andrej Karpathy「LLM Wiki」（2026-04）に着想を得ている。
