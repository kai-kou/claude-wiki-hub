---
description: ルーティン（Routines）を Claude が代行設定する。claude-code-remote MCP の create_trigger でセッション内から単一ディスパッチャ（環境 Default・毎朝 8:00 JST）を作成・検証する。セットアップ時にも「登録した Issue を定期的に処理できるようにして」等の途中からの依頼でも起動する。MCP 不在時のみ web UI 手順の案内にフォールバックする
---

# /routines-setup — ルーティン設定を Claude が代行する

定期自動化を **単一ルーティン（薄いディスパッチャ）+ リポ内 cron テーブル** で回すための設定を、
本プロジェクトの絶対条件「ユーザーは指示だけ、実行は Claude が代行」に従い **Claude 自身が作成** するコマンドにゃ。
web に作るルーティンは 1 つだけで、何を・いつ動かすかは `config/routine_jobs.yaml` で管理する
（ルーティン本体を変えずにジョブを増減できる）。設計・手順の SSOT は `docs/setup/routines-setup.md`。

## 大原則（毎回確認）

- **Claude がセッション内から代行作成できる**（2026-07-10 実機確認）。claude-code-remote MCP の
  `create_trigger` / `list_triggers` / `update_trigger` / `delete_trigger` / `fire_trigger` を使う。
  公式ドキュメント未記載の経路のため、**作成後は必ず `list_triggers` の実結果で検証** する（L-113）。
- **標準構成**: 環境 **Default**・**毎朝 8:00 JST** 発火・fresh セッション起動（`create_new_session_on_fire: true`）。
- **cron は UTC で指定する**: 8:00 JST = 23:00 UTC → `"0 23 * * *"`（既存トリガーの `next_run_at`
  実測がすべて UTC 解釈と一致・`docs/setup/routines-setup.md` §0）。
- 事実を勝手に変えて「設定しておきました」と言わない。**実結果（`list_triggers`）で確認できたことだけ** を報告する。

## 手順

1. `docs/setup/routines-setup.md`（SSOT）を Read する。
2. **MCP ツールをロードする**: `ToolSearch` で `create_trigger` / `list_triggers` / `list_environments` /
   `update_trigger` / `fire_trigger` / `delete_trigger` を取得する。**サーバー名の表記はサーフェスにより揺れる**
   （`mcp__Claude_Code_Remote__*` / `mcp__claude-code-remote__*` の両方の実績あり）ため、`select:` が空振りしたら
   キーワード検索（例: `trigger routine environments`）で取得する。**どちらでもヒットしない場合のみ** 手順 8 のフォールバックへ。
3. **冪等性チェック**: `list_triggers` で既存ルーティンを確認する。本リポ向けディスパッチャ
   （名前 `<リポ名>-dispatcher`、またはプロンプトに `routine_scheduler.py` を含むもの）が既にあれば
   **作成せず**、現状（名前・cron・`next_run_at` の JST 換算）を報告して終了する（変更依頼があれば `update_trigger`）。
4. **環境 ID を解決する**: `list_environments` から名前が `Default`（大文字小文字無視）の環境の
   `environment_id` を取る。見つからなければ `environment_id` を **省略**（呼び出し元セッションの環境を継承）し、
   その旨を報告に含める。
5. **作成する**: `create_trigger` を以下で呼ぶ:
   - `name`: `<リポ名>-dispatcher`（例: `my-wiki-dispatcher`）
   - `environment_id`: 手順 4 で解決した Default の ID
   - `cron_expression`: `"0 23 * * *"`（= 毎朝 8:00 JST。別時刻を頼まれたら JST−9h で UTC に換算する）
   - `create_new_session_on_fire`: `true`（毎回まっさらなセッションで実行）
   - `prompt`: `docs/automation/routine-dispatch.md` §1 の定型ディスパッチャプロンプト（**プロンプト本文の SSOT**。
     **リポ slug を埋め込んだ** 自己完結の指示。fresh セッションは過去文脈を持たない）
6. **検証する**: `list_triggers` を再実行し、作成したトリガーの存在と `next_run_at` を確認する。
   `next_run_at` を JST に換算し **8:00 JST ±15 分以内**（発火ジッター）であることを確かめる。
   それより大きくズレていたら cron の TZ 解釈が変わった可能性があるため `update_trigger` で補正し、
   `docs/setup/routines-setup.md` §0 の是正 Issue を起票する。
7. **報告する**: 作成結果（名前・毎朝 8:00 JST・環境名・次回発火の JST）と、
   「以後の定期実行の増減は `config/routine_jobs.yaml` の編集（Claude が代行）だけで済み、
   ルーティン本体は二度と触らない」ことを 1〜2 行で伝える。**リポジトリのバインドは自動付与されない**
   （実機確認 2026-07-11: `sources` が入らない）ため、[claude.ai/code/routines](https://claude.ai/code/routines) で
   該当ルーティンに **対象リポジトリを 1 度だけ指定する** ことを唯一のユーザー操作として必ず案内する。
   同じ画面で **モデルを Sonnet に設定**・**不要なコネクタを外す** ことも 1 行添える（無人実行の品質と最小権限）。
8. **フォールバック（MCP 不在時のみ）**: `mcp__Claude_Code_Remote__*` が ToolSearch でヒットしない
   環境では代行作成できない。`docs/setup/routines-setup.md` §6（web UI 手順）に従い、
   定型プロンプトのコピペブロックと手順を提示して対話的に支援する。

## ジョブ（何を定期実行するか）の管理

- 「登録した Issue を定期的に処理できるようにして」等の依頼は、ルーティン本体ではなく
  `config/routine_jobs.yaml` のジョブで実現する（既定で `issue-consume` ジョブを同梱済み）。
  ルーティン未作成ならまず手順 2〜7 で作成し、必要なジョブが YAML に無ければ Claude が追記して PR する。
- ジョブの追加・変更・停止はすべて YAML 編集 + PR（Claude 代行）。ルーティン本体の変更は不要。

## やってはいけないこと

- `list_triggers` の実結果を見ずに「作成しました」と報告する（L-113・confabulation）。
- 同名・同目的のディスパッチャを重複作成する（手順 3 の冪等性チェックを飛ばさない）。
- cron を JST の値のまま渡す（`"0 8 * * *"` は 17:00 JST 発火になる）。
- ユーザーの claude.ai アカウント設定・課金（A-6）を勝手に変更する（ルーティン作成・削除自体は
  `delete_trigger` で可逆なため A-6 に当たらない）。

## 参照

- `docs/setup/routines-setup.md`（設計・標準構成 + web UI フォールバックの SSOT）
- `docs/automation/routine-dispatch.md`（単一ディスパッチャの実行プロトコル + **定型プロンプト本文の SSOT**・§1）
- `docs/automation/routines.md`（自動化方針の SSOT）
- `config/routine_jobs.yaml`（cron テーブル・ジョブ定義の実体）
