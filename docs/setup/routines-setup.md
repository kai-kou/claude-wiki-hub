# ルーティン（Routines）セットアップガイド

> 本プロジェクトの定期自動化（週次 wiki lint・定期リサーチ・リポジトリ監視 …）を **Claude Code の Routines**（Anthropic 管理クラウドで無人実行される自動化）で回すための、ユーザー向けセットアップ手順。
> **設計方針: web の Routines は「1 つだけ」**。何を・いつ動かすかはリポジトリ内の cron テーブルで管理し、
> 定期実行の追加・変更で **web 設定を触らずに済む** ようにする（実行プロトコルの SSOT は `docs/automation/routine-dispatch.md`）。
> Claude にいつでも案内させたいときは `/routines-setup` を実行する。

---

## 0. 重要な事実：ルーティンは「web セッションからは設定できない」

**Claude（本リポジトリで動く Claude Code セッション）は、ルーティンの追加・更新を代行できない。** ルーティンの作成・更新は **あなた自身の操作** が必要。

### 根拠（公式ドキュメント + 実機確認・2026-06-27）

| 確認項目 | 結果 |
|---------|------|
| 実行環境 | Claude Code on the web セッション（`CLAUDE_CODE_REMOTE=true` / `CLAUDE_CODE_ENTRYPOINT=remote`） |
| 公式ドキュメントの記述 | [routines docs](https://code.claude.com/docs/en/routines) のトラブルシュート: 「**web セッション内では `/schedule` は使えない。web UI から管理せよ**」 |
| 作成/更新 API | **存在しない**（公開 API は既存ルーティンを発火する `/fire` のみ。設定ファイル経路もなし） |
| `/schedule` を無効化する他要因 | API キー設定・CLI 旧版（< 2.1.81）・テレメトリ無効化系 env は **いずれも非該当**＝唯一の阻害要因は「web セッションであること」自体 |

> なぜ既約か: ルーティンは **あなた個人の claude.ai アカウント** に属し、あなたの GitHub / コネクタ権限で動く。アカウント権限の設定変更はユーザー操作が物理的に必要（`user-confirmation-minimization.md` A-6 相当）。

### 設定できる経路（いずれか 1 つ）

| 経路 | 手順 | 備考 |
|------|------|------|
| **web UI（推奨）** | [claude.ai/code/routines](https://claude.ai/code/routines) → New routine | 全トリガー種別（schedule / API / GitHub）に対応。**本ガイドはこれを前提** |
| Desktop アプリ | サイドバー **Routines** → **New routine** → **Remote** を選ぶ | Local を選ぶと Desktop Scheduled Task（ローカル実行）になる点に注意 |
| CLI `/schedule` | **web セッション以外の** 対話 CLI で `/schedule`（claude.ai ログイン要・API キー利用時は不可） | schedule トリガーのみ。API/GitHub トリガーは web UI で追加 |

---

## 0.5. PAT（`GH_TOKEN`）は要る？ — PR を生む定期自動化は PAT 前提

**方針: PR 作成 → AI レビュー対応 → 自動マージまで Claude が自律実行する**（人間がマージ作業をする運用は想定しない・`docs/rules/pr-review-flow.md`）。自動マージは GitHub MCP（要 PAT）依存のため、**PR を生む定期自動化（wiki-lint / research-ingest 等）は PAT 登録を前提** とする。ルーティンは [Claude Code on the web と同じ GitHub 認証基盤](https://code.claude.com/docs/en/claude-code-on-the-web#github-authentication-options) を使う（公式・2026-06）。

| ルーティンがやること | PAT |
|---|---|
| clone / push（`claude/` ブランチ）・PR の作成（open pull requests） | 不要（GitHub App） |
| **PR 自動マージ** / Issue 作成・コメント・ラベル / PR レビュー操作 | **必要**（GitHub MCP/REST） |
| Slack 等コネクタの読み書き | 不要（コネクタ権限） |

- **PAT を登録して使う（PR を生む定期自動化の標準）**: 「PR 作成 → AI レビュー対応 → 自動マージ」「タスクの Issue 化」まで Claude が無人で完走する。登録手順は [`README.md`](../../README.md#任意-自動化層を有効化する-github-pat-を登録)。
- **PAT 未登録の最小構成**: 日常 wiki 利用（bookmark / idea / wiki の **ファイル直コミット**）で完結し PR マージを伴わない。PR を生む定期自動化は実行せず、検出事項は `ideas/` / `wiki/log.md` に `TODO:` で記録するに留める。
- ジョブ別の挙動は `config/routine_jobs.yaml` の各 `instructions` を参照。SSOT は `docs/automation/routines.md`「ルーティンの GitHub 認証と PAT 要否」。

---

## 1. 設計：単一ルーティン + リポ内 cron テーブル

**web に作るルーティンは 1 つだけ**。そのプロンプトは「リポジトリの cron テーブルを読んで、いま動かすべきジョブを実行する」という **薄いディスパッチャ** にする。

```
web の単一ルーティン（薄いプロンプト・恒久的に安定 = 二度と編集しない）
  └─ 毎回: python3 tools/routine_scheduler.py --due
        └─ config/routine_jobs.yaml（cron テーブル）から「いま due なジョブ」を取得
              └─ Claude が各ジョブの instructions に従って作業（claude/ ブランチ + PR）
```

**メリット**: 定期実行を増やす・止める・中身を変えるとき、**`config/routine_jobs.yaml` を編集して PR するだけ** で完結し、web のルーティン設定を変更しなくてよい。

---

## 2. web UI でのセットアップ手順（1 回だけ）

1. [claude.ai/code/routines](https://claude.ai/code/routines) を開き **New routine** をクリック。
2. **名前**: `wiki-hub-dispatcher`（任意）。**プロンプト** に下記の **定型ディスパッチャ** をそのまま貼る（**今後ジョブが増減してもこのプロンプトは変えない**）。プロンプト欄の **モデルセレクタ** は **Sonnet** を選ぶ（個別ジョブは instructions の model 指定でサブエージェントに委譲される）。

   **コピペするプロンプト:**

   ```
   このリポジトリの定期メンテナンスを実行します。

   1. `python3 tools/routine_scheduler.py --due` を実行し、いま実行すべきジョブ一覧（JSON）を取得する。
   2. due_count が 0 なら「実行対象なし」とだけ報告して終了する。
   3. 各ジョブについて、その instructions に厳密に従って作業する。ジョブの model 指定が
      メインと異なる場合は、その作業を該当モデルのサブエージェント（Agent ツール）に委譲する。
   4. すべての変更は claude/ ブランチ + PR で行う（main へ直接 push しない）。日時表記は JST。
   5. 各ジョブ完了後、何をしたかを 1〜2 行で要約する。

   詳細プロトコルは docs/automation/routine-dispatch.md を参照。
   ```

3. **リポジトリ**: 運用リポジトリ（本テンプレートをフォークした自分の private リポ。開発リポ `kai-kou/claude-wiki-hub` 自体でも可）を選ぶ。
4. **環境**: 既定の **Default**（Trusted ネットワーク）でよい。
5. **トリガー**: **Schedule** を選び、**毎日 1 回**（推奨: 毎日 20:00 ローカル）に設定する。
   → これが「日次運用（window 24h）」。`config/routine_jobs.yaml` の `window_hours: 24` と一致させる（既定で一致済み）。
6. **Connectors / Permissions**: 不要なコネクタは外す。`main` 直 push は **不要**（`claude/` ブランチ + PR のまま）。
7. **Create** → 詳細ページの **Run now** で 1 回テスト実行。

> **これで完了。以降、何を定期実行するかは `config/routine_jobs.yaml` だけで管理する。** web のルーティンは二度と編集不要。

---

## 3. 定期実行ジョブ（`config/routine_jobs.yaml`）の管理

初期収録ジョブ（編集・追加・停止はこのファイルだけ。web 変更不要）:

| id | cron（JST） | モデル | 内容 |
|----|------------|--------|------|
| `wiki-lint` | `0 20 * * 0`（日曜） | Sonnet | 週次 wiki lint（矛盾・孤立ページ・データギャップ是正） |
| `research-ingest` | `0 7 * * 3`（水曜） | Opus | 関心トピックのディープリサーチ → wiki ingest |
| `repo-watch` | `0 8 * * 1-5`（平日） | Haiku | Issue/PR/コミット監視 → 取りこぼしを ideas/Issue 化 |

**ジョブを足す**: `jobs:` に 1 ブロック追記（`id` / `cron` / `model` / `title` / `instructions`）して PR するだけ。

```yaml
  - id: monthly-retro
    cron: "0 9 1 * *"        # 毎月 1 日 9:00 JST
    enabled: true
    model: sonnet
    title: 月次レトロスペクティブ
    instructions: |
      ここに作業指示を自己完結で書く（無人実行のため）。
```

**一時停止**: そのジョブの `enabled: false`（行は残す）。**やめる**: ブロックを削除。

> **時刻の精密制御（1 日複数回など）が要るとき**: `config/routine_jobs.yaml` の `window_hours: 1` にして、
> web ルーティンの schedule を **毎時 cron** へ 1 度だけ変更する（`/schedule update`）。これで cron の時フィールドも厳密に効く。
> 以降のジョブ増減は再び YAML だけで完結。詳細は `docs/automation/routine-dispatch.md` §2。

---

## 4. 設定後の確認

- 詳細ページの **Run now** で 1 回テスト実行（その時刻に due なジョブがあれば走る。無ければ「実行対象なし」）。
- 実行結果はセッションとして残る。**緑のステータスは「インフラ的に正常終了」を意味するだけ** でタスク成功を保証しない（公式注記）。中身はセッションを開いて確認する。
- ローカルで due 判定を試す: `python3 tools/routine_scheduler.py --due --now "2026-06-28 21:00"`。

## 5. 上限・注意

- ルーティンはサブスク利用枠を消費し、**アカウント単位で 1 日あたりの実行回数上限** がある（[claude.ai/code/routines](https://claude.ai/code/routines) / [usage](https://claude.ai/settings/usage) で確認）。日次運用なら 1 日 1 回なので上限に優しい。
- one-off（1 回限り）実行は日次上限にカウントされない。
- Team/Enterprise では Owner がルーティンを組織全体で無効化している場合がある（その場合は Owner に有効化を依頼）。

## 6. 参照

| ドキュメント | 関係 |
|------------|------|
| `docs/automation/routine-dispatch.md` | **単一ルーティンの実行プロトコル SSOT**（プロンプト・due セマンティクス・スキーマ） |
| `config/routine_jobs.yaml` | cron テーブル（ジョブ定義の実体） |
| `tools/routine_scheduler.py` | cron ディスパッチャ（--due / --list / --self-test） |
| `docs/automation/routines.md` | 自動化方針の SSOT（4 系統の使い分け・gh-aw/Actions 不使用） |
| `docs/rules/wiki-operations.md` | lint / ingest 操作の定義 |
| `docs/rules/intent-routing.md` | R-2/R-3/R-5 |
| `.claude/commands/routines-setup.md` | `/routines-setup`（本ガイドを Claude が対話提示する仕組み） |
| [公式: Routines](https://code.claude.com/docs/en/routines) | 一次情報 |
