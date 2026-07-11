# 単一ルーティン・ディスパッチプロトコル

> Routines を **1 つだけ**（薄いディスパッチャ）にし、「何を・いつ動かすか」はリポジトリ内の
> cron テーブル `config/routine_jobs.yaml` で一元管理するための実行プロトコル。
> 目的: 定期実行の追加・変更のたびに **ルーティン本体を変更しなくて済む** ようにする。
> ルーティン本体の作成は Claude が `create_trigger`（claude-code-remote MCP）で代行する（`docs/setup/routines-setup.md`）。

---

## 0. 全体像

```
単一ルーティン（薄いプロンプト・恒久的に安定・毎朝 8:00 JST 発火）
  └─ 毎回実行: python3 tools/routine_scheduler.py --due
        └─ config/routine_jobs.yaml の cron テーブルを読み、いま due なジョブを JSON で返す
              └─ Claude が各ジョブの instructions に従って作業（claude/ ブランチ + PR）
```

- **ジョブの追加・変更・停止 = `config/routine_jobs.yaml` を編集して PR するだけ**（ルーティン本体は不変）。
- ルーティンのプロンプトには **具体的なタスクを書かない**（下記の定型のみ）。

---

## 1. ルーティンに設定する定型プロンプト（これだけ・更新不要・**本文の SSOT**）

`{owner}/{repo}` は実リポ slug に置換する（ルーティンは毎回まっさらな新規セッションで動くため自己完結に書く）:

```
リポジトリ {owner}/{repo} の定期メンテナンスを実行します。

1. `python3 tools/routine_scheduler.py --due` を実行し、いま実行すべきジョブ一覧（JSON）を取得する。
2. due_count が 0 なら「実行対象なし」とだけ報告して終了する。
3. 各ジョブについて、その instructions に厳密に従って作業する。ジョブの model 指定が
   メインと異なる場合は、その作業を該当モデルのサブエージェント（Agent ツール）に委譲する。
4. すべての変更は claude/ ブランチ + PR で行う（main へ直接 push しない）。日時表記は JST。
5. 各ジョブ完了後、何をしたかを 1〜2 行で要約する。

詳細プロトコルは docs/automation/routine-dispatch.md を参照。
```

> このプロンプトは **ジョブが増減しても変えない**。変わるのは `config/routine_jobs.yaml` だけ。

---

## 2. due 判定のセマンティクス（重要）

`routine_scheduler.py` は各ジョブの cron に対し「**直近 `window_hours` 時間 (now-window, now] に発火予定があったか**」で due を判定する（stateless）。

- **`window_hours` はルーティンの実行間隔に一致させる**。`config/routine_jobs.yaml` の `window_hours` で設定（既定 24）。
- **推奨運用 = 日次ルーティン（window 24h・標準構成）**:
  - ルーティンを **1 日 1 回・毎朝 8:00 JST**（`cron_expression: "0 23 * * *"`・UTC 指定）に設定する。
  - 各ジョブの cron の **日・月・曜日フィールドが「どの日に走るか」** を決める。
    例: `0 7 * * 0`（日曜 7:00）→ 日曜朝 8:00 の発火の窓（土 8:00, 日 8:00] に入り、日曜に 1 回だけ due。
  - ⚠️ ジョブの時刻は **発火時刻（8:00）より前（推奨 07:00）** に書く。08:00 以降に書くと
    その曜日の「翌日の発火」の窓で拾われ、意図した曜日の翌日に実行される。
  - cron の **時・分は実行日選択には影響するが、実際の実行時刻はルーティンの単一発火時刻** になる
    （時刻の精密制御が要らない定期メンテ向き）。各 cron 発火は **ちょうど 1 回** due になる。
- **毎時運用（window 1h）にしたい場合**:
  - `window_hours: 1` にして、ルーティン本体を **毎時 cron** にする（Claude が `update_trigger` で代行）。
  - これで cron の **時フィールドも厳密に効く**（1 日複数回・時刻精密）。ただし毎時実行は
    アカウントの 1 日あたりルーティン実行上限を消費する（大半は no-op）。

> **増やすときの原則**: 日次運用の粒度（1 日 1 回）で足りる限り、ジョブ追加は YAML だけで完結し
> ルーティン変更は不要。1 日複数回など細かい時刻が要るときだけ、Claude が **1 度だけ** ルーティンの cron と
> `window_hours` を毎時運用へ切り替える（以降の増減は再び YAML だけ）。

---

## 3. ジョブ定義スキーマ（`config/routine_jobs.yaml`）

```yaml
window_hours: 24            # due 判定窓（= ディスパッチャの実行間隔）
jobs:
  - id: <一意ID>            # 必須
    cron: "分 時 日 月 曜日" # 必須（5 フィールド・JST・曜日 0=日..6=土）
    enabled: true           # 省略時 true。false で一時停止（行は残す）
    model: sonnet|opus|haiku # 作業を委譲するモデル（任意）
    title: <表示名>
    instructions: |         # Claude が従う作業指示（自己完結に書く）
      ...
```

cron 構文: `*` `5` `1,3,5` `1-5` `*/2` `1-5/2` をサポート。曜日は `0`=日（`7` も日として受理）。

---

## 4. 動作確認・運用コマンド

```bash
python3 tools/routine_scheduler.py --self-test            # cron マッチ・window の回帰テスト
python3 tools/routine_scheduler.py --list                 # 全ジョブ（enabled/cron/model）
python3 tools/routine_scheduler.py --due                  # いま due なジョブ（JSON）
python3 tools/routine_scheduler.py --due --now "2026-06-28 21:00"   # 時刻を上書きしてシミュレート
python3 tools/routine_scheduler.py --due --window-hours 1 # 毎時運用での due 判定
```

`tests/e2e/test_routine_scheduler.sh` が PR 前 e2e で `--self-test` と代表ケースを検証する。

---

## 5. 参照

| ドキュメント | 関係 |
|------------|------|
| `docs/setup/routines-setup.md` | 単一ルーティンのセットアップ（Claude 代行・標準構成の SSOT） |
| `docs/automation/routines.md` | 自動化方針の SSOT |
| `config/routine_jobs.yaml` | cron テーブル（ジョブ定義の実体） |
| `tools/routine_scheduler.py` | cron ディスパッチャ（--due / --list / --self-test） |
