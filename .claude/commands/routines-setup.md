---
description: ルーティン（Routines）設定をユーザーに案内する。web セッションからは設定不可のため、web UI 手順 + コピペ用ルーティン定義を提示して対話的に設定を支援する
---

# /routines-setup — ルーティン設定の案内

定期自動化を **単一ルーティン（薄いディスパッチャ）+ リポ内 cron テーブル** で回すための設定を、ユーザーが迷わず行えるよう丁寧かつ詳細に案内するコマンドにゃ。web に作るルーティンは 1 つだけで、何を・いつ動かすかは `config/routine_jobs.yaml` で管理する（web 設定を変えずにジョブを増減できる）。

## 大原則（毎回確認）

**Claude（このセッション）はルーティンを代行設定できない。** 本セッションは Claude Code on the web（`CLAUDE_CODE_REMOTE=true`）で、公式仕様上 `/schedule` が使えず、作成/更新 API も無い。設定は **ユーザー自身が web UI で行う** 必要がある（根拠・経路は `docs/setup/routines-setup.md` §0）。

> 事実を勝手に変えて「設定しておきました」と言わない。代行できないことを正直に伝え、**ユーザーが迷わず自分で設定できる状態** を作るのがこのコマンドのゴール。

## 手順

1. `docs/setup/routines-setup.md`（SSOT）と `docs/automation/routine-dispatch.md`（実行プロトコル）を Read する。
2. ユーザーに以下を **この順で** 簡潔に提示する:
   - 「本セッションからは設定できない」事実と理由（1〜2 行・§0 の根拠を要約）。
   - 設計（web は単一ディスパッチャ 1 つ・中身は `config/routine_jobs.yaml` で管理＝web を二度と編集しない）。
   - **唯一作る単一ルーティンの定型プロンプト**（`routines-setup.md` §2 のコピペブロック）をそのまま提示する。
   - web UI の手順（New routine → 名前 → 定型プロンプト貼付 → リポ選択 → 環境 Default → Schedule 毎日 1 回 → Create → Run now）。
3. 「定期実行を増やす/変える/止めるときは `config/routine_jobs.yaml` を編集して PR するだけで、web 設定は変更不要」と必ず伝える。ジョブ追加を頼まれたら Claude が YAML を編集 → PR で対応する。
4. 設定後の確認（Run now でテスト・緑ステータスの注意・`routine_scheduler.py --due` でのローカル確認）を案内する。
5. 1 日複数回など時刻の精密制御が要る場合のみ、`window_hours: 1` + web 毎時 cron への 1 度きりの切替（§3）を案内する。

## やってはいけないこと

- 「ルーティンを作成しました/更新しました」と事実に反する報告をする（代行不可）。
- `/schedule` をこのセッションで実行しようとする（web セッションでは無効）。
- ユーザーの claude.ai アカウント設定・課金（A-6）を勝手に変更する。

## 参照

- `docs/setup/routines-setup.md`（手順 + コピペ定義の SSOT）
- `docs/automation/routines.md`（自動化方針の SSOT）
