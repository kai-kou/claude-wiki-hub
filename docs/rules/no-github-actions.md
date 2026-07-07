# GitHub Actions 不使用ポリシー（SSOT）

> **このファイルは「本プロジェクトおよびフォーク先で GitHub Actions を使わない」方針の唯一の正本（SSOT）である。**
> 飼い主の明示決定（2026-06-26）に基づき新設。**Warm 層（タスク依存・#69 で降格）**: `.github/workflows` 編集時に Read する。
> 要点は `CLAUDE.md`「やってはいけないこと」（常駐）に記載され、`pre-tool-use-router.sh` が編集時に警告する。

---

## 0. 大原則: GitHub Actions を使わない

**本プロジェクト（および本ベースをフォークした運用リポジトリ）では、GitHub Actions（`.github/workflows/*.yml` の CI/CD）を新規追加・利用しない。**

理由（飼い主決定）:

- 飼い主は **複数リポジトリで GitHub Actions を多用** しており、Actions の実行時間がすぐにアカウント全体のリミット（無料枠の分数上限）に達する。
- 1 リポジトリで Actions を増やすと、他リポジトリの CI まで巻き込んで止まる（共有リミットの枯渇）。
- 本プロジェクトの方針は **「Claude Code を唯一のインターフェースにする」**（`CLAUDE.md`・`docs/automation/routines.md`）。CI も Claude Code のハーネス（フック・スキル・ルール）で完結させるのが一貫している。

> 関連: `docs/automation/routines.md` は既に **gh-aw（GitHub Actions 上で LLM ワークフローを回す仕組み）を使わない** ことを定めている。本ファイルはそれを **GitHub Actions 全般** に拡張する。

---

## 1. 代替: Claude Code ハーネスで CI を完結させる

GitHub Actions でやっていた検証は、以下の Claude Code ネイティブ機構で代替する。

| 旧 GitHub Actions の役割 | 代替（Claude Code ハーネス） |
|------------------------|---------------------------|
| push/PR 時の自動テスト（例: e2e フォーマット検証） | **PR 作成前に self-reviewer スキルがワークツリー隔離サブエージェントで `bash scripts/run-e2e.sh` を実行**（§2） |
| Lint・フォーマットチェック | pre-pr-create フック（`pre-pr-create-check.sh`）＋ self-reviewer の非ブロッキング検査 |
| 定期実行（スケジュール CI） | Claude Code ネイティブのルーティン機能（`docs/automation/routines.md`） |
| CI アノテーション出力（`GITHUB_STEP_SUMMARY`） | 不要（Claude がチャット / PR スレッドに直接報告） |

---

## 2. e2e テストの実行モデル（ワークツリー隔離サブエージェント）

PR 作成は「実装 → self-reviewer → PR → AI レビュー → 自動マージ」の自律フローで進む（`pr-review-flow.md`）。テストはこのフローの **self-reviewer ステップ** に組み込む。

```
実装完了
  → self-reviewer スキル起動（PR 作成直前の関門）
      └→ 変更が e2e 対象（bookmarks/ ideas/ raw/ wiki/ tests/ scripts/run-e2e.sh
         docs/rules/wiki-operations.md docs/rules/intent-routing.md
         tools/check_cjk_markdown.py tools/build_index.py tools/check_index_sync.py
         content/index/）に触れているか判定
            └→ 触れていれば Agent ツールで「ワークツリー隔離サブエージェント」を起動:
               - isolation: "worktree"（メインの作業ディレクトリ・コンテキストと分離）
               - subagent_type: general-purpose（model: haiku 可）
               - タスク: `bash scripts/run-e2e.sh --verbose` を実行し、PASS/FAIL と
                 FAIL 時の該当チェック・該当ファイルだけを 1,000〜2,000 トークンで要約して返す
               - 結果:
                   ├─ PASS → そのまま PR 作成へ進む
                   └─ FAIL → メインが自己修正 → 再度サブエージェントで再テスト（自律ループ）
```

**設計意図**:

- **ブロックしない**: フックで PR 作成を止める方式（作業性が悪い）ではなく、「FAIL なら直して PASS させてから進む」自律ループにする。
- **コンテキスト分離**: テスト実行をワークツリー隔離サブエージェントに委譲し、メインセッションのコンテキストにテスト出力を流し込まない（要約だけ受け取る）。
- e2e テストは現状ファイルを変更しない読み取り専用検証だが、隔離により将来テストが副作用（ファイル生成等）を持っても安全に拡張できる。

> サブエージェント・ワークツリー隔離の一般原則は `docs/rules/agent-team-summary.md`「ワークツリー隔離」を参照。

---

## 3. 再発防止（機械ガード）

| 層 | 実装 | 挙動 |
|----|------|------|
| ルール | 本ファイル（Warm 層）＋ `CLAUDE.md`「やってはいけないこと」（常駐） | 明文化 |
| フック | `pre-tool-use-router.sh` が Write/Edit による `.github/workflows/*.yml` の新規作成・編集を検知 | **警告（warn）**。ハードブロックはしない |

- フックは **非ブロッキングの警告** に留める（飼い主決定）。将来どうしても Actions が必要になったときの例外を完全には塞がない。
- 警告が出たら、本ファイル §1 の代替（Claude Code ハーネス）で実現できないかを必ず先に検討する。

---

## 4. 完了・成功の定義

- [ ] `.github/workflows/` に実ワークフロー（`*.yml`）が存在しない（`.gitkeep` のみ）
- [ ] PR 作成前にワークツリー隔離サブエージェントが e2e を実行する手順が self-reviewer スキルに定義されている
- [ ] GitHub Actions 不使用方針が本ファイル（Warm 層）＋ `CLAUDE.md` に明文化されている
- [ ] `.github/workflows/*.yml` 新規作成時に `pre-tool-use-router.sh` が警告する
- [ ] `./tools/check_rules_sync.sh` が PASS（本ファイルは Warm 層＝symlink 不要。Hot 化したい場合は `.claude/rules-extra.conf` に 1 行追加・#73）

---

## 5. 参照

| ドキュメント | 関係 |
|------------|------|
| `docs/automation/routines.md` | gh-aw 不使用・定期実行は Claude Code ネイティブ（本ファイルの母体方針） |
| `docs/rules/pr-review-flow.md` | PR 自律フロー（self-reviewer ステップに e2e を組み込む） |
| `.claude/skills/self-reviewer/SKILL.md` | e2e 実行ステップの実装場所 |
| `docs/rules/agent-team-summary.md` | ワークツリー隔離サブエージェントの一般原則 |
| `tests/README.md` | e2e テストの構成・実行方法 |
