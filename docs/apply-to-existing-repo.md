# 既存リポジトリへルール・スキル・ハーネスを適用する（ワンコマンド）

> **目的**: 他リポジトリで毎回手動指示していた
> 「gh で `kai-kou/claude-code-base` を参照し、ルール・スキル定義・ハーネスを全部適用して」
> を **1 コマンド** に置き換える。`scripts/apply-to-repo.sh` がベースを取得して対象リポジトリへ展開する。

`scripts/bootstrap.sh` が「ベースを clone してから新規プロジェクトに馴染ませる」初期化用なのに対し、
本スクリプトは **逆方向 ——「既存リポジトリ側で叩くと、ベースの設定が取り込まれる」適用ツール** である。

---

## TL;DR（対象リポジトリのルートで実行）

```bash
# A. リモートから直接（最も手軽。git だけで動く）
curl -fsSL https://raw.githubusercontent.com/kai-kou/claude-code-base/main/scripts/apply-to-repo.sh | bash

# B. オプションを付けたい場合（ローカルにスクリプトを置いて実行）
curl -fsSLO https://raw.githubusercontent.com/kai-kou/claude-code-base/main/scripts/apply-to-repo.sh
bash apply-to-repo.sh --tz Asia/Tokyo --prune
```

実行すると以下が対象リポジトリに展開される:

- **ルール**: `docs/rules/`（実体）+ `.claude/rules/`（常駐 symlink を自動再生成）
- **スキル定義**: `.claude/skills/`
- **ハーネス**: `.claude/hooks/` + `.claude/settings.json`（フック登録）
- **エージェント / コマンド**: `.claude/agents/` / `.claude/commands/`
- **ツール / 補助**: `tools/` / `scripts/` / `modules.yaml` / `.mcp.json` / `.claude-plugin/`

対象リポジトリの slug は `git remote origin` から自動判定し、プレースホルダ（`kai-kou/claude-wiki-hub` 等）を置換する。

---

## オプション

| オプション | 既定 | 説明 |
|-----------|------|------|
| `--base owner/repo` | `kai-kou/claude-code-base` | ベースリポジトリ |
| `--ref <branch\|tag\|sha>` | `main` | 取得する ref |
| `--repo owner/repo` | git remote から自動判定 | 対象リポジトリ slug（プレースホルダ置換用） |
| `--name "..."` | リポジトリ名 | プロジェクト名（`{{PROJECT_NAME}}` 置換） |
| `--desc "..."` | プロジェクト名 | プロジェクト説明（`{{PROJECT_DESCRIPTION}}` 置換） |
| `--tz Asia/Tokyo` | （空） | タイムゾーン |
| `--prune` | off | `modules.yaml` で `enabled:false` のモジュール資産を除去 |
| `--overwrite-project` | off | `CLAUDE.md` / `docs/project-mission.md` も上書き（既定は保護） |
| `--keep-settings` | off | `.claude/settings.json` を上書きしない（既定はバックアップして導入） |
| `--dry-run` | off | コピーせず適用対象を表示するだけ |

---

## 何が保護され、何が上書きされるか

| 区分 | 挙動 |
|------|------|
| ルール / スキル / ハーネス / ツール（`docs/rules`・`.claude/{rules,hooks,skills,agents,output-styles,commands}`・`tools`・`scripts`・`modules.yaml`・`.mcp.json`・`.claude-plugin`） | **常に最新で上書き・更新**（再実行で同期できる） |
| `.claude/settings.json` | ハーネス本体のため導入。既存があれば `.claude/settings.json.pre-base.bak` に退避してから上書き（`--keep-settings` で維持） |
| `CLAUDE.md` / `docs/project-mission.md` | **プロジェクト固有のため既定では上書きしない**。既存があれば維持し、ベース版を `*.base` として横に配置（差分を手動で取り込む）。`--overwrite-project` で上書き |

> **`*.base` の扱い**: `CLAUDE.md.base` は応答スタイル・PR 自律化方針・大原則参照などの雛形。
> 既存 `CLAUDE.md` に必要な節（応答スタイル / 必読ルール表 / PR 自律化）をマージする。
> `docs/project-mission.md.base` はミッション・KPI の雛形。

---

## 再実行＝最新へ同期

本スクリプトは **冪等**。ベースのルール・スキル・ハーネスを更新したら、対象リポジトリで同じコマンドを
再実行するだけで最新へ同期できる（プロジェクト固有ファイルは保護されたまま）。定期的な追従にそのまま使える。

---

## Claude に依頼する場合（自然文だけ・コマンド不要）

対象リポジトリで Claude Code セッションを開始し、**次の自然文を伝えるだけ** でよい
（ユーザーがコマンドを打つ必要も、スクリプト名を知る必要もない）:

```
claude-code-base の内容を本リポジトリに反映して
```

同梱の `apply-base` スキルがこの自然文（「反映して」「適用して」「ベースを取り込んで」等）で
自動起動し、private 前提で `gh` 経由でベースを取得して適用する。初回（対象リポジトリにまだ
スキルが無い状態）でも、Claude がベース README 冒頭の「エージェントへ」の入口を辿って同じ
`gh api ... | bash` を実行するため、自然文指示だけで反映できる。初回適用後は `apply-base`
スキル自体が対象に入るため、以降の再同期も同じ自然文で起動する。

> どの環境でも自然文起動を効かせたい場合は、`.claude/skills/apply-base/` をユーザーの
> グローバル設定（`~/.claude/skills/`）に一度置いておくと、ベース未適用の新規リポジトリでも
> 自然文だけで初回適用が起動する（任意）。

---

## 前提・トラブルシュート

- **git は必須**、`gh` は任意（あれば認証・clone に利用）。`gh` 未インストールでも git で動作する。
- ベースが private の場合は `GH_TOKEN` を環境変数に設定するか `gh auth login` 済みであること。
- `--ref` にタグ / SHA を指定した場合も浅い fetch で取得する（ブランチ clone が失敗したら自動フォールバック）。
- 対象が git リポジトリでない（`.git` が無い）場合はエラーで停止する。
- 適用後はそのまま git でコミットすれば、対象リポジトリにベース設定が定着する。

---

## 参照

| ドキュメント | 関係 |
|------------|------|
| `scripts/apply-to-repo.sh` | 本スクリプト本体 |
| `scripts/bootstrap.sh` | プレースホルダ置換 + symlink 同期 + prune（apply-to-repo が内部で呼ぶ） |
| `modules.yaml` | モジュール単位の opt-out 定義（`--prune` 対象） |
| `README.md` | ベース全体の使い方 |
