# 運用リポジトリのセットアップ（テンプレートから使い始める）

本リポジトリ（`kai-kou/claude-wiki-hub`）は **GitHub Template Repository**。実際にナレッジを蓄積するのは、"Use this template" で作成した **あなた専用の private リポジトリ**。

> 初回セットアップの完全手順は [`README.md`](../../README.md#クイックスタート3ステップで使い始めるpat-不要) と [`onboarding.md`](onboarding.md)（**Claude が代行するセットアップ** の SSOT）を参照。本ドキュメントは詳細・補足・運用継続に関する SSOT。
>
> **絶対条件**: ユーザーは指示だけ。bootstrap・ミッション記入・コミット等のスクリプト実行は **すべて Claude が代行** する（`CLAUDE.md`「絶対条件」節）。下記のコマンド例は「ローカル CLI で手動実行する場合の参考」であり、通常はユーザーが打つ必要はない。

## 層構造とカスタマイズ境界（重要）

`sync-upstream.sh` によるアップデート取得は以下の **3 層** に分けて扱う。

| 層 | パス | 役割 | upstream sync の扱い |
|----|------|------|---------------------|
| **ハーネス層** | `.claude/hooks/` `.claude/skills/` `.claude/agents/` `.claude/output-styles/` `docs/rules/` `tools/` `scripts/` `.github/` `.gitignore` `requirements.txt` | Claude の自律動作を支えるフレームワーク | **自動上書き**（カスタマイズ禁止） |
| **ユーザー編集層** | `CLAUDE.md` `modules.yaml` `.claude/settings.json` | リポ固有の設定（リポ名・モデル・応答スタイルなど） | **手動マージ推奨**（差分表示のみ） |
| **データ層** | `raw/` `wiki/` `ideas/` `bookmarks/` `docs/project-mission.md` `content/` | あなた個人のナレッジ・タスク・アイデア | **一切触れない**（個人データ保護） |

**ハーネス層をカスタマイズしない** ことで、`sync-upstream.sh` による定期アップデートがスムーズに取り込める。プロジェクト固有のカスタマイズはユーザー編集層（`CLAUDE.md` `modules.yaml`）と `docs/project-mission.md` に集約する。

## 1. 運用リポジトリを作る（ユーザーは Web 操作だけ）

**推奨**: GitHub 上の **"Use this template"** → "Create a new repository" で private リポを作成する。

- テンプレートから作成した場合、コミット履歴は引き継がれず最新ファイル状態のみがコピーされる。
- 個人情報・機微情報が入るため **private** を選択する。
- 作成後、claude.ai プロジェクトをこのリポに接続すれば **コンテナにチェックアウト済みで起動するため `git clone` は不要**。

```bash
# ローカル CLI で使う場合のみ（クラウド接続なら不要）
git clone https://github.com/<あなた>/<your-wiki> && cd <your-wiki>
git remote add upstream https://github.com/kai-kou/claude-wiki-hub
```

## 2. セットアップは Claude が代行する（「セットアップして」と言うだけ）

運用リポを接続した claude.ai プロジェクトで **「セットアップして」**（または `/onboarding`）と言えば、Claude が以下をすべて代行する（**ユーザーはコマンドを打たない**・SSOT: [`onboarding.md`](onboarding.md)）:

- bootstrap 相当: `kai-kou/claude-wiki-hub` 等のプレースホルダを自分のリポ名に一括置換、`.claude/rules/` の symlink を `docs/rules/` 実体に同期。
- ミッション（`docs/project-mission.md`）の対話ヒアリングと記入。
- 初期コミット → 作業ブランチへ push → PR 作成。**PR 作成 → AI レビュー対応 → 自動マージまで Claude が自律実行する**（要 PAT・§4）。PAT 未登録の最小構成では、**この初回 PR のマージのみ** ブートストラップとして GitHub Web UI で 1 度承認が要る（PAT 登録後は以降すべて自律マージ・人間のマージ作業は不要）。

不要モジュールを opt-out したい場合は Claude に伝えれば `modules.yaml` を編集して `--prune` する（`wiki-core` `core-principles` `session-safety` は required で外せない）。

```bash
# ローカル CLI で手動実行したいときのみ（通常は Claude が代行）
bash scripts/bootstrap.sh --repo <あなた>/<your-wiki> --name "My Wiki" --tz Asia/Tokyo
git add -A && git commit -m "chore: bootstrap" && git push
```

## 3. ミッション・CLAUDE.md を自分用に（Claude がヒアリングして記入）

- `docs/project-mission.md`: 自分の関心領域・KPI・判断基準。**最初に書くべき最重要ファイル** だが、Claude が「どんな分野のナレッジを貯めたい？」と短くヒアリングして記入するので、ユーザーがエディタを開く必要はない。
- `CLAUDE.md`「応答スタイル」: ねこキャラ日本語が既定。変えたい場合は Claude に「敬体にして」等と伝えれば書き換える。

## 4. Claude Code 環境変数（クラウド実行する場合）

- **標準構成は PAT 不要**。git の clone/push は Claude GitHub App / `/web-setup` 接続が担うため、個人 wiki の日常利用はトークン設定なしで動く（`docs/rules/env-vars.md` §0）。
- `GH_TOKEN`（PAT・`repo` スコープ）は **自動化層を使うときだけの任意のアップグレード**。Issue/PR の完全自動化（GitHub MCP）・Slack/R2 等の secrets 一元管理（Repository Variables）・クロスリポ同期を使う場合のみ、Claude.ai の Environment Variables に登録する（org の teams 機能を使うなら `read:org` も追加）。
- PAT を登録すると、他の env は GitHub Repository Variables に置けば `session-start` フックが自動ロードする（登録・取得は `GH_TOKEN` だけで動く・`gh_vars.py`・urllib）。
- **`gh` CLI のインストール・`gh auth login` はユーザー作業ではない**（ハーネス内部の任意アクセラレータ。無い/失敗しても MCP・`gh_vars.py` に自動フォールバック）。
- なぜ App だけでは PAT を置換できないか: Claude Code のリモート GitHub MCP は **PAT 認証** で、Claude GitHub App（git 接続用）とは別レイヤーだから（`docs/rules/env-vars.md`「App と GH_TOKEN の役割分担」）。

## 5. 使い始める

| やりたいこと | 操作 |
|------------|------|
| ソースを知識化 | `raw/` に Markdown を置き、Claude に「これを ingest して」 |
| アイデアを残す | Claude に「〇〇よさそう」と話しかける（`ideas/` に自動追記） |
| あとで読む | Claude に URL を貼るだけ（`bookmarks/` に自動タグ付け） |
| 調べ物 | Claude に質問（wiki 優先 → なければ Web → ナレッジ化） |
| タスク把握 | 「今日やること教えて」で open Issue を要約 |
| 健全性チェック | 「wiki を lint して」または週次 Routine（`docs/automation/routines.md`） |

## プライバシー / データの扱い

- 運用リポジトリは **private** にする。
- 外部に出したくないファイルは `.gitignore` で除外する（`.gitignore` は secrets 除外設定を含む）。
- `raw/` に機微情報を入れる場合、リポジトリの可視性とアクセス権を必ず確認する。
- 開発リポジトリ（`kai-kou/claude-wiki-hub`）には個人データを **コミットしない**。

## アップストリーム追従（アップデートの取得）

> 🟢 **通常はコマンド不要**。Claude に **「アップデートを取り込んで」**（「更新して」「最新を取り込んで」でも可）と
> 話しかければ、Claude が `sync-upstream` スキル（`scripts/sync-upstream.sh`）を **代行実行** して差分を確認し PR を作る
> （絶対条件・`intent-routing.md` ②）。運用フォークの upstream は **claude-wiki-hub**。取り込み元を名指さない更新依頼を
> `apply-base`（claude-code-base 追従）に倒さないこと（#87）。以下の CLI 例はローカルで手動実行したい場合の参考。

`kai-kou/claude-wiki-hub` のリリースを **"Watch → Releases only"** でフォローしておくと更新通知を受け取れる。

> 旧ハーネスのフォークで「アップデートを取り込んで」が誤動作する場合の脱出手順は `README.md`
> 「ハーネスが古いフォークで〜」を参照（`bash scripts/sync-upstream.sh --yes` の明示指示が確実な迂回路）。

```bash
# 差分の確認のみ（--dry-run）
bash scripts/sync-upstream.sh --dry-run

# 取り込み実行（対話的に確認）
bash scripts/sync-upstream.sh

# 確認なしで即実行
bash scripts/sync-upstream.sh --yes
```

取り込み後は diff を確認してコミットする:

```bash
git diff --stat
git add -A && git commit -m "chore: sync harness from upstream claude-wiki-hub"
```

`CLAUDE.md` `modules.yaml` `.claude/settings.json` はユーザー編集層のため自動上書きされない。upstream の差分を手動で確認してマージする:

```bash
git diff upstream/main -- CLAUDE.md
git show upstream/main:CHANGELOG.md | head -50
```

## 改善を配布元（claude-wiki-hub）へ還元し、公開テンプレート（claude-wiki-hub）に反映するメンテナ向け

### リポジトリ構成（B 案・dev / template / operational 3 層分離）

```
kai-kou/claude-wiki-hub（private 開発リポジトリ）
   │ ドッグフーディング実運用 + ハーネス改善
   │ scripts/publish-template.sh で同期（gh CLI + GH_TOKEN）
   ↓
kai-kou/claude-wiki-hub（public テンプレートリポジトリ・Template Repository）
   │ "Use this template"
   ├─→ あなたの private 運用リポ … 実運用＆改善
   │       │ ハーネス層の汎用改善だけ還元（データ層は除く）
   │       └──────────────────────────────────→ claude-wiki-hub へ PR
   └─→ 他ユーザーの private 運用リポ … sync-upstream.sh で改善を取り込む
```

**メンテナ自身も `claude-wiki-hub`（private）で実運用（ドッグフーディング）** し、個人情報を公開リポに入れずに済む。
汎用的な改善は `claude-wiki-hub` main にマージ後、`publish-template.sh` で `claude-wiki-hub`（パブリックテンプレート）へ同期する。

### claude-wiki-hub への同期手順（publish-template.sh）

**前提**: `gh CLI` がインストール・認証済み（`gh auth login`）、または `GH_TOKEN` / `GITHUB_TOKEN` 環境変数に `claude-wiki-hub` への write 権限があるトークンが設定されていること。

```bash
# 変更内容の確認のみ（推奨: 初回は必ず --dry-run）
bash scripts/publish-template.sh --dry-run

# 実際に同期・push
bash scripts/publish-template.sh
```

`publish-template.sh` がやること:
- `gh repo clone` で `claude-wiki-hub` を取得（gh コマンドで認証）
- `kai-kou/claude-wiki-hub` → `kai-kou/claude-wiki-hub`（参照・slug）を全更新
- `Claude Wiki Hub` → `Claude Wiki Hub`（表示名）
- `docs/project-mission.md`（個人設定・データ層）を除去してから push
- `bootstrap.sh`: `sync-upstream.sh` を置換除外リストに追加（UPSTREAM_URL 保護）
- `sync-upstream.sh`: UPSTREAM_URL を `claude-wiki-hub` に固定
- `publish-template.sh` 自身はテンプレートに含めない（dev 専用ツール）
- `gh auth token` を使って push 認証（GH_TOKEN へフォールバック）

### 還元の手順（私的運用リポ → claude-wiki-hub）

1. private 運用リポで汎用改善を行う（**データ層 `raw/` `wiki/` `ideas/` `bookmarks/` は含めない**）。
2. ハーネス層の差分だけを取り出す:

   ```bash
   git checkout -b contrib/<改善名> upstream/main
   git checkout <自分の運用ブランチ> -- .claude docs/rules tools scripts CLAUDE.md modules.yaml
   # データ層（raw/wiki/ideas/bookmarks）は checkout 対象に含めない
   ```

3. **個人情報・プロジェクト固有値が紛れていないか確認** してから `claude-wiki-hub` へ PR する（bootstrap のプレースホルダに戻すべき箇所は戻す）。

   > セルフチェック: `git diff upstream/main` に `raw/` `wiki/` `ideas/` `bookmarks/` の実データや、自分のリポ名・トークン・個人名が含まれていないこと。

4. claude-wiki-hub にマージ後、`bash scripts/publish-template.sh` を実行して `claude-wiki-hub` に反映（gh CLI または GH_TOKEN が必要）。
5. 他ユーザーは `sync-upstream.sh` で改善を `claude-wiki-hub` から取り込む。
