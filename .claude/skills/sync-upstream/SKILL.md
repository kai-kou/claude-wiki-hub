---
name: sync-upstream
description: 運用リポ（claude-wiki-hub からテンプレート作成したフォーク）に、upstream のハーネス層更新を取り込む。**「アップデートを取り込んで」「更新して」「最新を取り込んで」「ハーネスを更新して」「upstream に追従して」等、取り込み元を名指さない汎用的な更新依頼のときに使用する**（既定の更新経路）。upstream = claude-wiki-hub（フォーク）/ claude-wiki-hub（dev リポ）。⚠️ これは claude-code-base 追従の `apply-base` とは別物。「claude-code-base」「ベース」を明示的に名指したときだけ `apply-base` を使い、名指さない更新は本スキル。`scripts/sync-upstream.sh` を Claude が代行実行するため、ユーザーがコマンドを打つ必要はない。
model: sonnet
effort: low
---

# アップストリーム追従スキル（sync-upstream）

運用リポ（`claude-wiki-hub` から "Use this template" で作った private フォーク）に、
upstream のハーネス層（`.claude/` `docs/rules/` `tools/` `scripts/` `.github/` 等）の更新を
選択的に取り込む。ユーザーは「アップデートを取り込んで」と伝えるだけでよく、コマンド実行は不要。

> **なぜ apply-base と分けるか（#87 根本原因）**: 「取り込んで」という汎用動詞は claude-code-base 適用スキル
> `apply-base` のトリガーと語彙衝突しやすい。**取り込み元を名指さない更新依頼は必ず本スキル（upstream = claude-wiki-hub）**
> に向ける。`apply-base`（claude-code-base）は「claude-code-base」「ベース」を明示したときだけ。

## 0. 前提と方針

- 取り込み元（upstream）は `scripts/sync-upstream.sh` の `UPSTREAM_URL`（フォークでは publish-template により **claude-wiki-hub** に固定）。
- 取り込むのは **ハーネス層のみ**。データ層（`raw/` `wiki/` `ideas/` `bookmarks/` `content/` `docs/project-mission.md`）は一切触れない。
- ユーザー編集層（`CLAUDE.md` `modules.yaml` `.claude/settings.json`）は自動上書きせず差分提示に留める（`operational-repo.md` の 3 層構造 SSOT）。
- 冪等。`main` 直 push はしない（A-1）。作業ブランチ → PR → 自動マージ。

## 1. リポ文脈チェック（自律実行）

```bash
# カレントが対象リポジトリのルートであること
[ -z "$(git rev-parse --show-prefix 2>/dev/null)" ] || { echo "エラー: リポジトリのルートで実行してください" >&2; exit 1; }
# 取り込み元を確認（フォークでは claude-wiki-hub に固定されているはず）
grep -n '^UPSTREAM_URL=' scripts/sync-upstream.sh
```

- `scripts/sync-upstream.sh` が存在しない場合は運用リポのハーネスが古い可能性がある。その場合は
  `docs/rules/problem-investigation-protocol.md` に従って自己解決を試みる（`apply-base` に安易に倒さない）。
- **dev リポ（`claude-wiki-hub`・`scripts/publish-template.sh` が存在）で「アップデート取り込んで」と言われた場合**:
  dev リポの upstream は claude-code-base（apply-base 経路）だが、通常 dev リポは自分が配布元なので更新取り込みは
  稀。文脈を確認し、claude-code-base の汎用更新なら `apply-base`、そうでなければ本スキルを使う。

## 2. 取り込みの実行（コア手順）

```bash
# 1) 差分の確認（--dry-run）
bash scripts/sync-upstream.sh --dry-run

# 2) 取り込み実行（作業ブランチ上で）
git checkout -b claude/sync-upstream-$(TZ=Asia/Tokyo date +%Y%m%d)
bash scripts/sync-upstream.sh --yes
```

- `sync-upstream.sh` は upstream remote 追加 → ハーネス層のみを checkout → ユーザー編集層は差分表示、を自律実行する。
- クラウド実行環境では git 操作（clone/fetch/pull）は生存する（別系統プロキシ）。push が 403 になる場合は
  `mcp__github__push_files` にフォールバックする（L-079）。

## 3. 取り込み後の処理

1. `git diff --stat` で取り込み内容を確認する。
2. ユーザー編集層（`CLAUDE.md` `modules.yaml` `.claude/settings.json`）に upstream 差分があれば、
   既存のプロジェクト固有設定を壊さない範囲で **手動マージを提案・実施** する（自動上書きしない）。
3. `.md` を変更したら `python3 tools/check_cjk_markdown.py --fix --changed` を実行する。
4. 作業ブランチにコミット → PR 作成 → AI レビュー → 自動マージ（`pr-review-flow-summary.md`）。
5. 完了報告は「何が新しく使えるようになったか」を中心に（`completion-report-rules.md`）。

## 4. やってはいけないこと

- 取り込み元を名指さない更新依頼を `apply-base`（claude-code-base）に倒す（#87 の再発）。
- データ層（`raw/` `wiki/` `ideas/` `bookmarks/` `content/`）を上書きする。
- `main` へ直接 push する（A-1）。
- ユーザー編集層（`CLAUDE.md` 等）を差分確認なしで自動上書きする。

## 5. 参照

| ドキュメント | 関係 |
|------------|------|
| `docs/setup/operational-repo.md` | アップストリーム追従の実行詳細 SSOT（3 層構造・還元フロー） |
| `docs/rules/intent-routing.md` | ② アップデート取り込みの入口ルーティング（本スキルへ振る） |
| `.claude/skills/apply-base/SKILL.md` | claude-code-base 追従（明示名指し時のみ・本スキルとは別経路） |
| `scripts/sync-upstream.sh` | 実行の実体（UPSTREAM_URL・ハーネス層選択取り込み） |
