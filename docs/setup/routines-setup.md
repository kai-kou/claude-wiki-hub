# ルーティン（Routines）セットアップガイド — Claude が代行作成する

> 本プロジェクトの定期自動化（週次 wiki lint・定期リサーチ・Issue 定期消化 …）を **Claude Code の Routines**（Anthropic 管理クラウドで無人実行される自動化）で回すためのセットアップガイド。
> **設計方針: Routines は「1 つだけ」**。何を・いつ動かすかはリポジトリ内の cron テーブルで管理し、
> 定期実行の追加・変更で **ルーティン本体を触らずに済む** ようにする（実行プロトコルの SSOT は `docs/automation/routine-dispatch.md`）。
> セットアップは「**定期実行を設定して**」「**登録した Issue を定期的に処理できるようにして**」と話しかけるか `/routines-setup` で、**Claude が代行実行** する。

---

## 0. 重要な事実：ルーティンは「Claude がセッション内から代行作成できる」（2026-07-10 更新）

**Claude（本リポジトリで動く Claude Code セッション）は、claude-code-remote MCP 経由でルーティンの作成・更新・削除を代行できる。** ユーザーの操作は **リポジトリのバインド（web UI で 1 度だけ・§2 末尾）のみ** で、それ以外は指示するだけでよい（本プロジェクトの絶対条件・CP-6 Ⅲ）。

### 根拠（実機確認・2026-07-10）

| 確認項目 | 結果 |
|---------|------|
| 利用ツール | claude-code-remote MCP: `create_trigger` / `list_triggers` / `update_trigger` / `delete_trigger` / `fire_trigger` / `send_later`（ToolSearch でロード） |
| 実機確認 | web セッション内から `list_triggers` / `list_environments` / `create_trigger` の実行に成功。セッション内作成のトリガーは `created_via: meta_mcp` として記録される（作成実績複数） |
| 公式ドキュメントの記述 | [routines docs](https://code.claude.com/docs/en/routines) は web UI を正規経路として記載し、**MCP 経由の作成は未記載**（2026-07 時点）。CLI `/schedule` が web セッションで使えない事実は従前どおり |
| cron のタイムゾーン | **UTC**。既存トリガーの `next_run_at` 実測がすべて UTC 解釈と一致（例: `0 8,12,15,20 * * *` → next_run 12:05Z ≒ cron 12:00 UTC + 発火ジッター数分。JST 解釈なら 03:00Z/23:00Z 等になるため不一致）。web UI のフォーム入力はローカル TZ 自動換算だが、**MCP の `cron_expression` は UTC で渡す**。検証時は ±15 分以内のズレをジッターとして正常扱いする |

> **注意（ドリフト検知）**: MCP 経由は公式未記載の経路のため、作成後は必ず `list_triggers` の実結果で
> 存在と `next_run_at`（JST 換算で意図どおりか）を検証する（L-113）。ツールが見つからない環境では
> §6 の web UI 手順にフォールバックする。
> 旧事実（2026-06-27「web セッションからは設定不可」）は本節をもって更新済み。

### なぜ「作成の代行」は A-6（アカウント設定変更）に当たらないか

ルーティンはユーザーの claude.ai アカウントに属するが、作成・削除は `delete_trigger` で **可逆** であり、
課金・認証・公開のような不可逆操作を伴わない。既約境界外（A-1〜A-6）には該当せず自律実行してよい
（`user-confirmation-minimization.md` §1）。実行枠（§5 の日次上限）を消費する点だけ報告に含める。

---

## 0.5. PAT（`GH_TOKEN`）は要る？ — PR を生む定期自動化は PAT 前提

**方針: PR 作成 → AI レビュー対応 → 自動マージまで Claude が自律実行する**（人間がマージ作業をする運用は想定しない・`docs/rules/pr-review-flow.md`）。自動マージは GitHub MCP（要 PAT）依存のため、**PR を生む定期自動化（wiki-lint / research-ingest / issue-consume 等）は PAT 登録を前提** とする。ルーティンは [Claude Code on the web と同じ GitHub 認証基盤](https://code.claude.com/docs/en/claude-code-on-the-web#github-authentication-options) を使う（公式・2026-06）。

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

**作るルーティンは 1 つだけ**。そのプロンプトは「リポジトリの cron テーブルを読んで、いま動かすべきジョブを実行する」という **薄いディスパッチャ** にする。

```
単一ルーティン（薄いプロンプト・恒久的に安定 = 二度と編集しない・毎朝 8:00 JST 発火）
  └─ 毎回: python3 tools/routine_scheduler.py --due
        └─ config/routine_jobs.yaml（cron テーブル）から「いま due なジョブ」を取得
              └─ Claude が各ジョブの instructions に従って作業（claude/ ブランチ + PR）
```

**メリット**: 定期実行を増やす・止める・中身を変えるとき、**`config/routine_jobs.yaml` を編集して PR するだけ**（これも Claude が代行）で完結し、ルーティン本体を変更しなくてよい。

---

## 2. セットアップ：Claude に話しかけるだけ（標準経路）

チャットでこう言うだけ（`/routines-setup` でも同じ）:

```
定期実行を設定して
```

（「登録した Issue を定期的に処理できるようにして」「毎朝の定期メンテを動かして」等でも起動する・`intent-routing.md` ③）

→ Claude が以下の **標準構成** でルーティンを作成し、`list_triggers` の実結果で検証して報告する
（実行手順の詳細は `.claude/commands/routines-setup.md`）:

| 項目 | 標準値 |
|------|--------|
| 名前 | `<リポ名>-dispatcher` |
| 環境 | **Default**（`list_environments` から名前解決。無ければセッションの環境を継承） |
| スケジュール | **毎朝 8:00 JST** = `cron_expression: "0 23 * * *"`（**UTC 指定**・§0） |
| セッション | `create_new_session_on_fire: true`（毎回まっさらな新規セッション） |
| プロンプト | 定型ディスパッチャ（**本文の SSOT は `docs/automation/routine-dispatch.md` §1**。`{owner}/{repo}` を実リポ slug に置換して `create_trigger` の `prompt` に渡す・以後変更しない） |

> **リポジトリのバインド（唯一のユーザー操作・1 分）**: セッション内（MCP 経由）で作成したルーティンには
> リポジトリが **自動でバインドされない**（実機確認 2026-07-11: `job_config` に `sources` が入らない）。
> プロンプトにリポ slug を明記してあるが、確実に動かすため、作成後に
> [claude.ai/code/routines](https://claude.ai/code/routines) → 該当ルーティン → **リポジトリに運用リポを 1 度だけ指定** する。
> 同じ画面で **モデルセレクタを Sonnet に**（個別ジョブは instructions の model 指定でサブエージェント委譲）、
> **不要なコネクタを外す**（無人実行に余計な権限を持たせない）ことも併せて行うとよい。
> Claude はこの案内を完了報告に必ず含める（「やっておきました」と偽らない）。

---

## 3. 定期実行ジョブ（`config/routine_jobs.yaml`）の管理

初期収録ジョブの概要（**正は YAML 本体**。編集・追加・停止はこのファイルだけ。ルーティン本体の変更不要）:

| id | cron（JST） | モデル | 内容 |
|----|------------|--------|------|
| `issue-consume` | `0 7 * * *`（毎日） | Sonnet | **登録済み Issue の定期消化**（`status:waiting-claude` を 1 件、PR 自律化まで） |
| `wiki-lint` | `0 7 * * 0`（日曜） | Sonnet | 週次 wiki lint（矛盾・孤立ページ・データギャップ是正） |
| `research-ingest` | `0 7 * * 3`（水曜） | Opus | 関心トピックのディープリサーチ → wiki ingest |
| `repo-watch` | `0 7 * * 1-5`（平日） | Haiku | Issue/PR/コミット監視 → 取りこぼしを ideas/Issue 化 |
| `inbox-triage` | `0 7 * * 2,5`（火・金） | Haiku | idea/bookmark Issue の定期トリアージ |

> ⚠️ ジョブ cron の時刻は **ディスパッチャ発火（毎朝 8:00 JST）より前（推奨 07:00）** に書く。
> 08:00 以降にすると「その曜日の翌日の発火」で拾われ、意図した曜日の翌日に実行される（YAML ヘッダー参照）。
> 実際の実行時刻はいずれも毎朝 8:00 JST 頃（cron の時・分は「どの日に走るか」の選択にのみ効く）。

**ジョブを足す**: `jobs:` に 1 ブロック追記（`id` / `cron` / `model` / `title` / `instructions`）して PR するだけ（Claude が代行）。

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

> **YAML 内の cron は JST**（due 判定は `routine_scheduler.py` が JST で行う）。**ルーティン本体の
> `cron_expression` だけが UTC** である点に注意（§0）。
> **時刻の精密制御（1 日複数回など）が要るとき**: `config/routine_jobs.yaml` の `window_hours: 1` にして、
> ルーティン本体の cron を毎時（`0 * * * *`）へ 1 度だけ変更する（`update_trigger` で Claude が代行）。
> 以降のジョブ増減は再び YAML だけで完結。詳細は `docs/automation/routine-dispatch.md` §2。

---

## 4. 設定後の確認

- Claude が `list_triggers` で存在と `next_run_at`（JST 換算で翌朝 8:00 前後・数分のジッターあり）を検証して報告する。
- すぐ 1 回試したい場合は「いま実行してみて」→ Claude が `fire_trigger` で即時発火する（その時刻に due なジョブがあれば走る。無ければ「実行対象なし」）。
- 実行結果はセッションとして残る。**緑のステータスは「インフラ的に正常終了」を意味するだけ** でタスク成功を保証しない（公式注記）。中身はセッションを開いて確認する。
- ローカルで due 判定を試す: `python3 tools/routine_scheduler.py --due --now "2026-06-28 21:00"`。

## 5. 上限・注意

- ルーティンはサブスク利用枠を消費し、**アカウント単位で 1 日あたりの実行回数上限** がある（[claude.ai/code/routines](https://claude.ai/code/routines) / [usage](https://claude.ai/settings/usage) で確認）。日次運用なら 1 日 1 回なので上限に優しい。
- one-off（1 回限り）実行は日次上限にカウントされない。
- 最小間隔は 1 時間（それより短い cron は拒否される）。
- Team/Enterprise では Owner がルーティンを組織全体で無効化している場合がある（その場合は Owner に有効化を依頼）。

## 6. フォールバック：web UI での手動セットアップ（MCP 不在時のみ）

claude-code-remote MCP ツールが利用できない環境では、従来どおりユーザーが web UI で作成する
（Desktop アプリからも作成可: サイドバー **Routines** → **New routine** → **Remote** を選ぶ。
**Local を選ぶと Desktop Scheduled Task（マシン起動時のみ動くローカル実行）になる** 点に注意）:

1. [claude.ai/code/routines](https://claude.ai/code/routines) を開き **New routine** をクリック。
2. **名前**: `<リポ名>-dispatcher`。**プロンプト** に `docs/automation/routine-dispatch.md` §1 の定型ディスパッチャを貼る（リポ slug を自分のものに置換）。モデルセレクタは **Sonnet**。
3. **リポジトリ**: 運用リポジトリ（本テンプレートから作った自分の private リポ）を選ぶ。
4. **環境**: 既定の **Default** でよい。
5. **トリガー**: **Schedule** で **毎日 08:00**（web UI はローカル時刻で入力できる）。
6. **Connectors / Permissions**: 不要なコネクタは外す。`main` 直 push は不要（`claude/` ブランチ + PR のまま）。
7. **Create** → 詳細ページの **Run now** で 1 回テスト実行。

## 7. 参照

| ドキュメント | 関係 |
|------------|------|
| `.claude/commands/routines-setup.md` | `/routines-setup`（Claude 代行の実行手順） |
| `docs/automation/routine-dispatch.md` | **単一ルーティンの実行プロトコル SSOT**（プロンプト・due セマンティクス・スキーマ） |
| `config/routine_jobs.yaml` | cron テーブル（ジョブ定義の実体） |
| `tools/routine_scheduler.py` | cron ディスパッチャ（--due / --list / --self-test） |
| `docs/automation/routines.md` | 自動化方針の SSOT（4 系統の使い分け・gh-aw/Actions 不使用） |
| `docs/rules/wiki-operations.md` | lint / ingest 操作の定義 |
| `docs/rules/intent-routing.md` | ③ 定期実行セットアップ発話の振り分け |
| [公式: Routines](https://code.claude.com/docs/en/routines) | 一次情報（MCP 経由作成は未記載・§0 参照） |
