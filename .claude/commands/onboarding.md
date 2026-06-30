---
description: 運用リポのセットアップ（bootstrap・ミッション記入・初期コミット）を Claude が代行する。「セットアップして」「初期設定して」「使い始めたい」でも起動する
---

# /onboarding — 使い始めのセットアップを Claude が代行する

本プロジェクトの絶対条件 **「ユーザーは指示だけ、実装・スクリプト実行は Claude」** に従い、
運用リポの初期セットアップ（bootstrap・ミッション記入・初期コミット → PR）を **ユーザーにコマンド実行を求めず** 代行するコマンドにゃ。

## 大原則（毎回確認）

- **ユーザーにターミナル操作を求めない。** `git clone` / `bash scripts/bootstrap.sh` / `$EDITOR` / `python3 ...` は
  すべて Claude が Bash / Edit / git で実行する。ユーザーがやるのは Web 操作だけ（テンプレ作成・PAT 発行・claude.ai 設定）。
- clone は不要（接続済みコンテナにチェックアウト済み）。
- 障害に遭遇してもユーザー確認に逃げず `docs/rules/problem-investigation-protocol.md` の 5 ステップを実施する（L-077）。

## 手順

1. `docs/setup/onboarding.md`（SSOT）を Read する。**§3「`/onboarding` の実行手順」に厳密に従う。**
2. リポ slug を検出する（`GITHUB_REPOSITORY`、または `mcp__github__get_me` 不要・`git remote get-url origin` から導出。`gh` があれば `gh repo view --json nameWithOwner` も可）。ユーザーに聞かない。
3. セットアップ済みか判定する（`CLAUDE.md` / `modules.yaml` にプレースホルダ `kai-kou/claude-wiki-hub` が残っているか）。
   - **このリポが開発リポ `kai-kou/claude-wiki-hub` 自身** なら「運用セットアップは不要（ここは開発リポ）」と伝えて終了する。
4. 未セットアップなら `bash scripts/bootstrap.sh --repo <slug> --name <表示名> --tz Asia/Tokyo` を Claude が実行する。
5. `docs/project-mission.md` を Claude が記入する（関心領域・KPI を **短く** ヒアリング・推奨案を添える・エディタは開かせない）。
6. CJK 整形・ルール symlink 同期 → `claude/` 作業ブランチにコミット（main 直 push 禁止・A-1）。マージは PAT 有無で分岐する:
   - **`GH_TOKEN` あり（自動化層）**: PR 作成 → AI レビュー → 自動マージまで代行する。
   - **`GH_TOKEN` なし（標準・最小構成）**: GitHub MCP が使えないため PR 自動化はしない。作業ブランチへ push 済みであることを伝え、**GitHub の Web UI で Compare & pull request → Merge する 1 ステップだけ** を案内する（git push は App 接続で動く）。さらに自動化したいなら任意の PAT 登録（`README.md`「自動化層を有効化する GitHub PAT を登録」）を案内する。
7. `completion-report-rules.md` に従い「ご依頼の再掲 → 何ができるようになったか」を報告し、日常使いに誘導する。

## やってはいけないこと

- ユーザーに `bash` / `python3` / `git` コマンドの実行を依頼する（テーマ違反・全部 Claude が代行する）。
- ミッションの曖昧さを理由にセットアップを止める（Simplicity First で仮定を記録して進める）。
- `main` へ直接 push する（作業ブランチ + PR + 自動マージのみ）。
- ユーザー本人の Web 作業（テンプレ作成・PAT 発行・claude.ai 接続）を「やっておきました」と事実に反して報告する。

## 参照

- `docs/setup/onboarding.md`（手順の SSOT）
- `docs/setup/operational-repo.md`（運用リポの 3 層構造・還元フロー）
- `docs/rules/core-principles.md` CP-6 Ⅲ（スクリプト実行の自律化）
- `docs/rules/user-confirmation-minimization.md` §4（ユーザーにコマンド実行を求めない）
