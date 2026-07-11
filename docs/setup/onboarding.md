# オンボーディング（使い始め）ガイド — セットアップは Claude が代行する

> 運用リポジトリ（テンプレートから作った自分の private リポ）を **Claude Code に接続したあと**、
> 「セットアップして」と話しかけるだけで、bootstrap・ミッション記入・初期コミットまで **Claude が自律実行** するためのガイド。
> Claude にいつでも実行させたいときは `/onboarding` を実行する。
>
> **本プロジェクトの絶対条件: ユーザーは指示だけ。実装・スクリプト実行はすべて Claude Code が行う**
> （`CLAUDE.md` 大原則・`docs/rules/core-principles.md` CP-6 Ⅲ・`docs/rules/user-confirmation-minimization.md` §4）。
> 下記「ユーザーがやること」は **アカウント権限が物理的に必要な Web 操作だけ**（A-6 相当）に絞ってある。

---

## 0. 役割分担（最重要）

セットアップを「ユーザー本人にしかできないこと」と「Claude が代行すること」に分ける。
**コマンド実行・ファイル編集はすべて Claude 側**。ユーザーにターミナル操作を求めない。

| 区分 | 作業 | なぜその区分か |
|------|------|--------------|
| **ユーザー本人**（Web 操作のみ） | ① テンプレから private リポ作成（GitHub の "Use this template"）<br>② GitHub PAT（Classic・`repo` スコープ）を発行<br>③ claude.ai プロジェクト設定の Environment Variables に `GH_TOKEN` を登録<br>④ claude.ai プロジェクトを運用リポに接続 | GitHub / claude.ai の **アカウント権限が物理的に必要**（A-6 相当・Claude は代行不可） |
| **Claude が代行**（ユーザーは「セットアップして」と言うだけ） | ⑤ `bash scripts/bootstrap.sh`（プレースホルダ置換・ルール symlink 同期）<br>⑥ `docs/project-mission.md` のミッション記入（対話ヒアリング）<br>⑦ 初期コミット → 作業ブランチ → PR → 自動マージ | clone 不要（接続済みコンテナにチェックアウト済み）。スクリプト・編集・git は **Claude が自律実行** |

> **clone はなぜ不要か**: claude.ai プロジェクトを運用リポに接続すると、Claude Code のセッションコンテナに
> リポジトリが **すでにチェックアウト済み** で起動する。ユーザーが手元で `git clone` する必要はない。

---

## 1. ユーザーがやること（Web 操作だけ・4 ステップ）

> ここだけがユーザー本人の作業。**ターミナルは開かない**。

1. **テンプレから private リポを作成**: [claude-wiki-hub](https://github.com/kai-kou/claude-wiki-hub) の
   **"Use this template" → "Create a new repository"** をクリック。**Private** を選び、リポ名を決める（例: `my-wiki`）。
2. **GitHub PAT を発行**: GitHub → Settings → Developer settings → **Personal access tokens (Classic)** で
   `repo` スコープのトークンを生成（org で teams 機能を使うなら `read:org` も追加）。
3. **claude.ai に GH_TOKEN を登録**: [claude.ai](https://claude.ai) → プロジェクト設定 →
   **Environment Variables** に `GH_TOKEN` として貼り付け。
4. **claude.ai プロジェクトを運用リポに接続**: 新規プロジェクト → **"Connect a GitHub repository"** →
   作成した `<あなた>/<your-wiki>` を選ぶ。

---

## 2. Claude に話しかける（これだけ）

運用リポを接続した claude.ai プロジェクトのチャットで、こう言うだけ:

```
セットアップして
```

（または `/onboarding`、「初期設定して」「使い始めたい」でも起動する）

→ Claude が §3 の手順を **確認を最小化して自律実行** し、完了したら「何ができるようになったか」を報告する。
ミッション（関心領域・KPI）だけは Claude が短くヒアリングする（最も単純な合理的解釈で進め、答えやすい推奨案を添える）。

---

## 3. `/onboarding` の実行手順（Claude 向け・このセクションは Claude が読んで実行する）

> 大原則: **ユーザーにコマンド実行を求めない**。下記はすべて Claude が Bash / Edit / git で実行する。
> 障害に遭遇したらユーザー確認に逃げず `problem-investigation-protocol.md` の 5 ステップを実施する（L-077）。

1. **リポ slug を検出する**（ユーザーに聞かない）:
   ```bash
   # クラウド接続なら GITHUB_REPOSITORY、無ければ gh で取得
   REPO_SLUG="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)}"
   echo "$REPO_SLUG"
   ```
2. **セットアップ済みか判定する**: `kai-kou/claude-wiki-hub` などテンプレ既定のプレースホルダが
   `CLAUDE.md` / `modules.yaml` に残っていれば **未セットアップ**。残っていなければ bootstrap 済みなので §3-3 をスキップして §3-4 へ。
   ```bash
   grep -l "kai-kou/claude-wiki-hub" CLAUDE.md modules.yaml 2>/dev/null
   ```
   - **このリポが開発リポ `kai-kou/claude-wiki-hub` 自身** の場合は運用セットアップ対象ではない。
     「ここは開発リポなので運用セットアップは不要」と伝えて終了する（ドッグフーディングの実運用は別の private 運用リポで行う）。
3. **bootstrap を実行する**（未セットアップのときのみ）。`--name` はリポ名から導出し、`--tz` は
   ミッションヒアリング時に確認（既定 `Asia/Tokyo`）:
   ```bash
   bash scripts/bootstrap.sh --repo "$REPO_SLUG" --name "<リポ名から導出した表示名>" --tz Asia/Tokyo
   ```
   - bootstrap はプレースホルダ置換とルール symlink 同期を行う。
   - 不要モジュールの opt-out をユーザーが希望した場合のみ `modules.yaml` を Claude が編集して `--prune` を付ける
     （`wiki-core` / `core-principles` / `session-safety` は required で外せない）。
4. **ミッションを記入する**: `docs/project-mission.md` を読み、ユーザーに **短く** ヒアリングする
   （「どんな分野のナレッジを貯めたい？」「重視する KPI は？」）。答えやすいよう推奨案を添える。
   ヒアリング結果を Claude が `docs/project-mission.md` に記入する（ユーザーにエディタを開かせない）。
5. **環境変数の状態を確認・案内する**: `GH_TOKEN` はユーザーが §1-3 で設定済みのはず。未設定が疑われる場合のみ、
   設定方法を 1〜2 行で案内する（A-6・ユーザー本人作業）。他の env は `gh variable set` で Claude が登録できる。
6. **inbox ラベルを整備する**: idea/bookmark の Issue 管理（`intent-routing.md`・#77 設計）に使う
   `kind:idea` / `kind:bookmark` / `status:ingested` / `status:archived` の 4 ラベルを作成する。
   ```bash
   bash scripts/setup-labels.sh   # gh があれば色・説明つきで作成（冪等）
   ```
   クラウド（gh の repo 操作が 403）では本スクリプトは案内のみで終了するが、ラベルは
   **Issue 作成時の `labels` 指定で自動作成される** ため機能はブロックされない（色の正規化は後からで可）。
7. **定期自動化（ルーティン）を提案・代行作成する**: ミッションヒアリングの流れで
   「毎朝 8:00 JST の定期メンテ（Issue 消化・wiki lint 等）を動かすか」を 1 問だけ確認する（推奨 = 有効）。
   希望があれば `/routines-setup` の手順（`.claude/commands/routines-setup.md`）で **Claude が
   `create_trigger`（claude-code-remote MCP）により単一ディスパッチャ（環境 Default・毎朝 8:00 JST）を
   代行作成** し、`list_triggers` の実結果で検証する。MCP ツール不在時は `docs/setup/routines-setup.md` §6
   の web UI 手順を案内する（後から「定期実行を設定して」でいつでも設定可能・スキップしてよい）。
8. **CJK 整形・ルール同期・初期コミット → PR**:
   ```bash
   python3 tools/check_cjk_markdown.py --fix --changed
   ./tools/check_rules_sync.sh --fix
   ```
   変更を `claude/` 作業ブランチにコミットし、PR を作成する（**main 直 push は禁止**・A-1）。
   self-reviewer → AI レビュー → 自動マージまで `pr-review-flow-summary.md` に従って自律実行する。
9. **完了報告**: `completion-report-rules.md` に従い「ご依頼の再掲 → 何ができるようになったか」を出す。
   そのまま日常使い（URL を貼る・「〇〇よさそう」・「〇〇やらなきゃ」・「〇〇ってなんだっけ？」）に誘導する。

---

## 4. やってはいけないこと（Claude 向け）

- ユーザーに `git clone` / `bash scripts/bootstrap.sh` / `$EDITOR` / `python3 ...` の **実行を求める**
  （= テーマ違反。すべて Claude が代行する）。
- ミッションが曖昧なことを理由にセットアップを止める（Simplicity First で仮定を記録して進め、後から調整する）。
- `main` ブランチへ直接 push する（A-1・作業ブランチ + PR + 自動マージのみ）。
- ユーザー本人作業（テンプレ作成・PAT 発行・claude.ai 設定）を「やっておきました」と事実に反して報告する
  （代行不可。正直に案内する）。

---

## 5. 参照

> 🔴 **`/onboarding` は初回セットアップ専用**。2 回目以降の **アップデート取り込み（更新・upstream 追従）** は
> `/onboarding` ではなく **`sync-upstream` 経路**（`scripts/sync-upstream.sh`・upstream = claude-wiki-hub）を使う。
> ユーザーが「アップデートを取り込んで」と言ったら Claude が sync-upstream を代行する（`intent-routing.md` ②・
> `operational-repo.md`「アップストリーム追従」）。claude-code-base を被せる `apply-base` に倒さない（#87）。

| ドキュメント | 関係 |
|------------|------|
| `README.md` クイックスタート | 入口（本ガイドへ誘導） |
| `docs/setup/operational-repo.md` | 運用リポの 3 層構造・アップストリーム追従・還元フロー |
| `.claude/skills/sync-upstream/SKILL.md` | 2 回目以降のアップデート取り込み（本ガイドの範囲外・更新は sync-upstream 経路） |
| `docs/setup/routines-setup.md` | セットアップ後の定期自動化（`/routines-setup`） |
| `docs/setup/bookmarklet-setup.md` | ブックマークレット設定（Android / iOS / PC・スマホからの URL 投入） |
| `docs/setup/github-project-setup.md` | ラベル・Projects V2 の初期化（Claude 代行可能な範囲） |
| `docs/rules/core-principles.md` | CP-6 Ⅲ スクリプト実行の自律化（本ガイドの根拠） |
| `docs/rules/user-confirmation-minimization.md` | §4 ユーザーにコマンド実行を求めないアンチパターン |
| `docs/rules/intent-routing.md` | セットアップ発話の振り分け |
| `.claude/commands/onboarding.md` | `/onboarding`（本ガイドを Claude が実行する仕組み） |
