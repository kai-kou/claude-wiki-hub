# クラウドでの GitHub 操作: 公式 MCP 一次経路パターン（SSOT）

> **このファイルは「クラウド実行環境で GitHub をどう操作するか」の唯一の正本（SSOT）である。**
> 旧版は「`gh` 不在時（FileNotFoundError）の代替」を前提にしていたが、実態は **`gh` は存在するのに
> egress プロキシが repo スコープ操作を 403 でブロックする** という別問題である（2026-06-30 実機検証・Issue #121）。

## 0. 結論（最重要・常駐）

クラウド実行環境（`CLAUDE_CODE_REMOTE=true`）では、**repo スコープの GitHub 操作は公式 GitHub MCP
（`mcp__github__*`）が唯一の実働経路** である。`gh` CLI は存在する（`gh --version` は通る）が、
選択中リポジトリに対する操作は egress プロキシにブロックされる。

- ❌ **repo スコープ REST**: `gh api repos/{o}/{r}/...` → 403「GitHub access is not enabled for this session. An org admin must connect the Claude GitHub App for this organization.」
- ❌ **GraphQL 全般**: `gh issue/pr list`・`gh repo view`・`gh api graphql`（および `--json` を伴う高レベル gh コマンド）→ 403「GraphQL proxying is not enabled.」
- ❌ **urllib 直叩きフォールバックは効かない**: `urllib.request` で `api.github.com/graphql` や `/repos/...` を呼んでも **同一プロキシを通るため同じ 403**。「GraphQL は urllib で代替」は誤り（旧版の記述を撤去）。
- ✅ **公式 MCP**: `mcp__github__*` は repo スコープ操作（Issue・PR・レビュー・マージ・ファイル取得・スレッド解決等）が動作する。
- ✅ **git 操作は別系統で生存**: `git clone https://github.com/...`・`git fetch/pull/push`（origin）は git プロキシ経由で動作する。

## 1. 実機検証マトリクス（cloud_default・2026-06-30・Issue #121）

| 操作 | 結果 | 備考 |
|------|------|------|
| `gh --version` | ✅ | 2.45.0 が存在 |
| `gh auth status` | ⚠️ exit 0 | stderr に「token invalid」と出るが終了コードは 0（前提チェックは誤爆しない） |
| `gh api user`（非 repo REST） | ✅ | 認証ユーザー情報は取得可 |
| `gh search repos` | ✅ | search API は通る |
| `gh api repos/{o}/{r}`（repo REST） | ❌ 403 | 「connect the Claude GitHub App」 |
| `gh api repos/{o}/{r}/issues`・`/pulls`・`/contents/...` | ❌ 403 | 同上 |
| `gh issue list`・`gh pr list`・`gh repo view` | ❌ 403 | 「GraphQL proxying is not enabled」 |
| `gh api graphql -f query=...` | ❌ 403 | GraphQL |
| urllib → `api.github.com/graphql` | ❌ 403 | GraphQL（プロキシ） |
| urllib → `api.github.com/repos/...` | ❌ 403 | connect GitHub App（プロキシ） |
| `gh repo clone {o}/{r}` | ❌ exit 1 | 内部で API 解決を伴うため失敗 |
| `git clone https://github.com/{o}/{r}.git` | ✅ | git プロキシ経由 |
| `git fetch/pull/push origin` | ✅ | git プロキシ経由 |
| `mcp__github__get_me` | ✅ | |
| `mcp__github__list_issues` / `pull_request_read` / `get_file_contents` | ✅ | repo スコープも動作 |

## 2. コマンド別 代替パターン（gh → MCP）

repo スコープの `gh` は全てクラウドで 403 になるため、以下を **一次経路** として使う。

| やりたいこと（旧 gh コマンド） | クラウド一次経路（MCP） |
|----------------|----------------|
| `gh pr list --state open` | `mcp__github__list_pull_requests(owner, repo, state="open")` |
| `gh pr view {N}` | `mcp__github__pull_request_read(method="get", pullNumber=N)` |
| `gh pr view {N} --json reviews` | `mcp__github__pull_request_read(method="get_reviews", pullNumber=N)` |
| `gh pr view {N} --json comments` | `mcp__github__pull_request_read(method="get_comments", pullNumber=N)` |
| `gh pr view {N} --json files` | `mcp__github__pull_request_read(method="get_files", pullNumber=N)` |
| `gh pr diff {N}` | `mcp__github__pull_request_read(method="get_diff", pullNumber=N)` |
| `gh pr create` | `mcp__github__create_pull_request(owner, repo, title, head, base, body)` |
| `gh pr merge {N} --squash` | `mcp__github__merge_pull_request(owner, repo, pullNumber=N, merge_method="squash")` |
| `gh pr list --head {ブランチ}` | `mcp__github__list_pull_requests(owner, repo, head="{owner}:{ブランチ}", state="open")` |
| `gh issue list --label "X"` | `mcp__github__list_issues(owner, repo, labels=["X"], state="OPEN")` |
| `gh issue view {N}` | `mcp__github__issue_read(method="get", issue_number=N)` |
| `gh issue create` | `mcp__github__issue_write(method="create", title, body, labels)` |
| `gh issue comment {N} --body "..."` | `mcp__github__add_issue_comment(owner, repo, issue_number=N, body="...")` |
| `gh issue edit {N} --add-label "..."` | `mcp__github__issue_write(method="update", issue_number=N, labels=[...])` |
| `gh api repos/.../contents/{path}` | `mcp__github__get_file_contents(owner, repo, path)` |
| ファイル commit/push（CLI 失敗時） | `mcp__github__create_or_update_file` / `mcp__github__push_files` |
| `gh api graphql`（resolveReviewThread 等） | `mcp__github__resolve_review_thread` / `mcp__github__unresolve_review_thread` |
| `gh repo view` / repo メタデータ | `mcp__github__search_repositories` または `mcp__github__list_branches` 等の個別 MCP |

> **GraphQL 専用操作**: `gh api graphql` の独自 mutation/query はクラウドで実行不能（urllib も不可）。
> review thread の resolve/unresolve は MCP に専用ツール（`resolve_review_thread` / `unresolve_review_thread`）が
> あるためそれを使う。MCP に等価が無い GraphQL 専用処理は、**ローカル実行に切り出す** か、必要なら
> ツール改修 Issue（B カテゴリ・`user-confirmation-minimization.md`）として起票する。

## 3. git 操作（クラウドで生存）

`git` は API プロキシとは別の git プロキシを通るため、以下は **そのまま使える**:

```bash
git clone --depth 1 https://github.com/kai-kou/claude-wiki-hub.git   # ✅ gh repo clone の代わり
git fetch origin <branch>                                             # ✅
git pull origin <branch>                                              # ✅
git push -u origin <branch>                                           # ✅（push が 403/413/502 のときは L-079 のフォールバック）
```

`gh repo clone` は内部で API を叩くため **クラウドでは失敗する**。リポジトリ取得は
`git clone https://github.com/...`（認証はプロキシが付与）を使う。

## 4. Python スクリプトからの GitHub アクセス

`tools/*.py` が `subprocess` で `gh api repos/...` や `gh pr/issue` を呼んでいる場合、クラウドでは 403 になる。

- 取得系（read）: スクリプトが `gh` で失敗（403/非 0）したら、メインセッションの `mcp__github__*` ツールで直接操作する。
- GraphQL 系: **urllib で `api.github.com/graphql` を直叩きしない**（同一プロキシで 403）。MCP の等価ツールへ置換する。
- `check_pending_pr_reviews.py` 等が `FileNotFoundError`（gh 不在）や 403 を返した場合の代替フロー:

```
1. mcp__github__list_pull_requests(state="open") でオープン PR を取得
2. 各 PR について:
   a. mcp__github__pull_request_read(method="get_reviews") でレビュー取得
   b. mcp__github__pull_request_read(method="get_review_comments") でスレッド確認
   c. mcp__github__pull_request_read(method="get") で作成日時確認
3. needs_response / ready_to_merge をメインセッション側で判定する
```

## 5. ローカル実行との違い

`gh` が GitHub に直接到達できるローカル環境では、repo スコープ操作も `gh` で動く。その場合は従来どおり:

- repo 指定に `-R kai-kou/claude-wiki-hub` を付与する
- `gh pr create` に `--head {現在のブランチ}` `--base main` を付与する

クラウドかどうかは `CLAUDE_CODE_REMOTE` で判定できる（`true` ならクラウド = MCP 一次経路）。

## 6. 参照

| ドキュメント / ツール | 関係 |
|------------------------|------|
| `CLAUDE.md`「gh CLI / GitHub 操作」節 | 要約（本ファイルが SSOT） |
| `docs/rules/lessons-core.md` L-114 | クラウド gh ブロックの Hot 層 lesson |
| `docs/rules/lessons-core.md` L-079 | git push が 403/413/502 のときのフォールバック |
| `.claude/skills/apply-base/SKILL.md` | ベース取得を git clone / MCP 経路で行う（gh api contents 非依存） |
