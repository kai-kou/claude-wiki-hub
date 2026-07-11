# 定期実行・自動化の方針（Claude Code ネイティブ / GitHub Actions・gh-aw 不使用）

> 本プロジェクトは定期リサーチ・リポジトリ監視・週次 wiki lint などの自動化を、
> **Claude Code のネイティブ・ルーティン機能** で回す。**GitHub Actions（`.github/workflows/*.yml`）も
> GitHub Agentic Workflows（gh-aw）も採用しない**（他リポジトリと共有の実行枠をすぐ使い切るため・
> SSOT: `docs/rules/no-github-actions.md`）。
>
> 自動化は Claude Code のルーティン機能で実装する（Actions YAML は作らない・`no-github-actions.md`）。

## なぜ gh-aw を使わないか

| 観点 | gh-aw | 本プロジェクトの判断 |
|------|-------|--------------------|
| 成熟度 | 2026-06 時点で public preview。リリース 0.68.4〜0.71.3 が課金バグでリトラクトされた実績 | preview に本番依存しない（ミッション「外部依存を増やさない」） |
| 構成 | 専用の Markdown ワークフロー記法 + `gh aw compile` で .lock.yml 生成 | 新しい記法・ビルド工程を増やさず、Claude Code の標準機能に寄せる |
| インターフェース | gh-aw 固有の仕組みが増える | **Claude Code のみ** という単一インターフェース方針に反する |

> gh-aw が GA・課金が安定し、Claude Code ネイティブで賄えない要件が出た段階で再評価する（CP-2）。

## Claude Code ネイティブの 4 系統と使い分け

| 用途 | 推奨手段 | 最小間隔 / 失効 | 備考 |
|------|---------|----------------|------|
| 週次 wiki lint（無人・確実に回す） | **Routines（クラウド）** | 1 時間 | マシン非依存。Anthropic 管理インフラで実行 |
| ローカルファイル監視・即時 lint | **Desktop Scheduled Tasks** | 1 分 | マシン起動が必要。worktree 分離可 |
| 定期リサーチ → `wiki/` 追記 | **Routines + コネクタ** | 1 時間 | GitHub/Drive 等のコネクタを継承 |
| GitHub Issue/PR 監視 → タスク化 | **GitHub Actions**（`anthropics/claude-code-action@v1`）または **Routines の GitHub トリガー** | イベント駆動 | PR/Issue/comment に反応 |
| セッション内ポーリング（CI 待ち等） | **`/loop`** | 1 分 / 7 日で失効 | 対話セッション中のみ |

### A. Routines（クラウド・推奨の主軸）

- Anthropic 管理インフラで自律実行（マシンが落ちていても動く）。
- トリガー: スケジュール（hourly/daily/weekly/one-off）/ GitHub（PR・release）/ API（HTTP POST）。
- 設定: **Claude がセッション内から代行作成する**（claude-code-remote MCP の `create_trigger`・下記）。web UI（`claude.ai/code/routines`）はフォールバック。
- 既定でブランチは `claude/` プレフィックスのみに push。
- 例: 「毎朝 8:00 に due なジョブ（wiki lint・Issue 消化 …）をディスパッチ実行する」

> **✅ 事実更新（実機確認・2026-07-10）: Claude はセッション内からルーティンの作成・更新・削除を代行できる。** claude-code-remote MCP の `create_trigger` / `list_triggers` / `update_trigger` / `delete_trigger` / `fire_trigger` が利用可能（作成分は `created_via: meta_mcp` で記録・実績複数）。旧事実（2026-06-27「web セッションからは設定不可・ユーザーの web UI 操作が必要」）はこの更新で無効。ただし公式ドキュメントは 2026-07 時点で MCP 経由の作成を未記載のため、**作成後は必ず `list_triggers` の実結果で検証** し（L-113）、ツール不在の環境では web UI 手順にフォールバックする。
> **MCP の `cron_expression` は UTC**（毎朝 8:00 JST = `"0 23 * * *"`。既存トリガーの `next_run_at` 実測で確認）。
> セットアップは「定期実行を設定して」「登録した Issue を定期的に処理できるようにして」または `/routines-setup` で Claude が代行する。**唯一のユーザー操作はリポジトリのバインド**（MCP 作成では `sources` が自動付与されないため、web UI で 1 度だけ指定・実機確認 2026-07-11）。設計・標準構成（環境 Default・毎朝 8:00 JST）の SSOT は `docs/setup/routines-setup.md`。

#### ルーティンの GitHub 認証と PAT 要否（正本・SSOT）

> **要点: 本プロジェクトの定期自動化は PR 作成 → AI レビュー対応 → 自動マージまで Claude が自律実行する。** 自動マージは GitHub MCP/REST 経由（要 PAT）のため、**PR を生む定期自動化は PAT（`GH_TOKEN`）登録を前提** とする（人間がマージ作業をする運用は想定しない）。認証経路の内訳は下表のとおり: `git` の clone/push・PR の作成（オープン）は GitHub App で PAT 不要、Issue 化・PR 自動マージ・レビュー操作は GitHub MCP/REST で PAT 必要。ルーティンは [Claude Code on the web と同じ GitHub 認証基盤](https://code.claude.com/docs/en/claude-code-on-the-web#github-authentication-options)（GitHub App / PAT の 2 経路）を使う（公式・2026-06 / research preview）。

| ルーティンがやること | 認証経路 | PAT |
|---|---|---|
| clone / push（`claude/` ブランチ）/ ファイル編集・コミット | **GitHub App** | **不要** |
| **PR を開く**（draft / 通常 PR の作成）| **GitHub App** | **不要** |
| Issue 作成・コメント・ラベル操作 | GitHub MCP / REST | **必要** |
| PR 自動マージ | GitHub MCP / REST | **必要** |
| PR レビュースレッド操作・Copilot レビュー依頼 | GitHub MCP / REST | **必要** |
| Slack / Drive 等のコネクタ | claude.ai コネクタ | 不要（PAT 無関係・コネクタ権限で動く） |

- **根拠（公式 GitHub authentication options）**: GitHub App（recommended）は「clone, push, **and open pull requests**」を PAT なしで付与する。PAT は「**additional tools and APIs beyond what the app provides**」用 = Issue 操作・自動マージなど MCP/REST 経由の操作に要る（本プロジェクトの GitHub 操作 primary が MCP/トークンであることと整合・`docs/rules/env-vars.md`）。
- **自律マージ方針（標準）**: 本プロジェクトの定期自動化は **PR 作成 → AI レビュー対応 → 自動マージまで Claude が自律実行** する（`docs/rules/pr-review-flow.md`・`CLAUDE.md`「PR 作成の完全自律化」）。**人間がマージ作業をする運用は想定しない**。自動マージは GitHub MCP 依存のため、PR を生む定期自動化（wiki-lint / research-ingest 等）は **PAT 登録を前提** とする。
- **PAT 未登録の最小構成**: 日常 wiki 利用（bookmark / idea / wiki の **ファイル直コミット**）で完結し、PR マージを伴わない。PR を生む定期自動化は実行しない（検出事項は `ideas/` または `wiki/log.md` に `TODO:` で記録するに留める）。`git` の clone/push・PR の作成（オープン）自体は GitHub App で PAT 不要に行える。
- **PAT 登録で解禁される範囲**: PR 作成 → AI レビュー → **自動マージ** の完全自律フロー、タスクの **GitHub Issue 化**、ラベル/コメント自動化。`GH_TOKEN` を環境変数に登録すると有効化される（`README.md`「任意の PAT 登録」）。
- ジョブ別の PAT 要否と PAT 未登録時のフォールバックは `config/routine_jobs.yaml` の各 `instructions` に明記する。

### B. Desktop Scheduled Tasks

- 自分のマシン上で実行。ローカルファイル・git worktree に直接アクセス。
- マシン起動が前提（スリープ中はスキップ、起床時に catch-up）。最小 1 分間隔。

### C. `/loop`（セッション内）

- 対話セッション中のみ。`/loop 5m "<prompt>"` で固定間隔、bare `/loop` で動的間隔。
- 7 日で自動失効。CI 待ち・PR コメント対応の常駐ポーリングに使う。
- 既定プロンプトは `.claude/loop.md` で差し替え可能。

### D. GitHub Actions（`anthropics/claude-code-action@v1`・GA）

- リポジトリイベント（issue_comment の `@claude` メンション / schedule / pull_request / issues）で起動。
- セットアップ: 対話セッションで `/install-github-app`。
- 必要シークレット: `ANTHROPIC_API_KEY`（または Bedrock/Vertex の OIDC）。
- CI ランナー費 + API トークン費が発生するため、頻度とコストを必ず計測する。

## 本プロジェクトでの想定運用（単一ルーティン + リポ内 cron テーブル）

> **Routines は「1 つだけ」**（薄いディスパッチャ・環境 Default・**毎朝 8:00 JST**）にし、何を・いつ動かすかは
> リポジトリ内の cron テーブル `config/routine_jobs.yaml` で一元管理する。定期実行の追加・変更は
> YAML を編集して PR するだけで完結し、**ルーティン本体を変更しなくて済む**。
> 実行プロトコル・セットアップは `docs/automation/routine-dispatch.md` / `docs/setup/routines-setup.md`（SSOT）。

単一ルーティン（毎朝 8:00 JST）が毎回 `python3 tools/routine_scheduler.py --due` を実行し、いま due なジョブだけを走らせる。初期ジョブ:

1. **Issue 定期消化**（毎日・Sonnet）: `status:waiting-claude` の Issue を 1 件、PR 自律化まで処理。
2. **週次 wiki lint**（日曜・Sonnet）: 矛盾・孤立ページ・データギャップを是正 → PR（`wiki-operations.md`）。
3. **定期リサーチ**（水曜・Opus）: 関心トピックを research-runner でリサーチ → `wiki/` に ingest。
4. **リポジトリ監視**（平日・Haiku）: Issue/PR/コミットを監視 → 取りこぼしを `ideas/` or Issue 化。

> いずれも **Claude Code の標準機能のみ** で完結し、外部常駐サービスを増やさない。
> 頻度・コスト計測の結果は `content/analytics/` に記録し、ノイズ/コスト過大なら頻度・対象を絞る。

## 出典（2026-06 時点・公式ドキュメント）

- Routines: https://code.claude.com/docs/en/routines
- Desktop Scheduled Tasks: https://code.claude.com/docs/en/desktop-scheduled-tasks
- `/loop`（Scheduled Tasks）: https://code.claude.com/docs/en/scheduled-tasks
- Claude Code on the web: https://code.claude.com/docs/en/claude-code-on-the-web
- GitHub Actions: https://code.claude.com/docs/en/github-actions
- Headless mode: https://code.claude.com/docs/en/headless
