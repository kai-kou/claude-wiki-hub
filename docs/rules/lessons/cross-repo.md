# クロスリポジトリ参照の教訓（Warm 層）

> `apply-base` スキル・`claude-wiki-hub-sync-rules.md` 使用時のみ関連する Warm 層教訓。
> Hot 層ダイエット（`haiku-context-overflow-followup` 議論・2026-07-03）で lessons-core.md から降格。

## L-115: タスク実行モードによっては `add_repo` 自体が提供されず、クロスリポ参照が git/MCP 双方で 403 になる

**症状**: GitHub Issue/PR 対応のリモートタスク実行モード（システムプロンプト冒頭に「Repository Scope」が
タスク起動元の単一リポジトリで明示される形態）では、`mcp__claude-code-remote__add_repo` がツールリストに
存在しない（ToolSearch でもヒットしない）。この状態でスコープ外リポジトリへ `git ls-remote` / `git clone`
を実行すると **403** で失敗する（実機検証 2026-06-30: `claude-code-base` / `claude-wiki-hub` への
`git ls-remote` がいずれも 403、対してスコープ内リポジトリは成功）。`apply-base` SKILL.md・
`claude-wiki-hub-sync-rules.md` が前提とする「git clone は常に通る」という想定はこのモードでは成立しない。

**根本原因**: Anthropic は 2026-06-30 時点で、1 セッション/タスクに複数リポジトリを恒久的に紐付ける
公式機能を提供していない（`anthropics/claude-code` issue #23627 がオープンの feature request。
類似要望の #27934 は #23627 の重複としてクローズ済み・2026-06-30 確認）。
`add_repo` によるスコープ動的拡張は **インタラクティブな claude.ai/code Web セッション限定の機能** であり、
GitHub Issue/PR からの自動トリガー型タスクには搭載されない。

**対策**:
- クロスリポ参照（`apply-base` での claude-code-base 取得・claude-wiki-hub 同期）が必要な作業は、
  `add_repo` が使えるインタラクティブな claude.ai/code セッション（ユーザーが直接「claude-code-base を
  反映して」等を指示する通常のチャットセッション）で実行する。
- GitHub Issue/PR 自動対応タスクの中で `git ls-remote`/`git clone` がスコープ外リポジトリに対し 403 を
  返したら、GH_TOKEN・ネットワーク設定の問題と誤診断してリトライを繰り返さない。直ちに
  「このタスク実行モードでは未対応。通常の claude.ai/code セッションで再実行が必要」と判定し、
  ユーザーにその旨を案内する（A-6 ではなく、Anthropic 側の機能制約として報告する）。
- 恒久的な複数リポジトリアクセスの公式機能がリリースされたら、本エントリと `apply-base` SKILL.md・
  `claude-wiki-hub-sync-rules.md` の前提を更新する（CP-2）。

**保持理由**: クロスリポ参照は claude-code-base 反映・claude-wiki-hub 公開同期という中核運用に必須で、
誤診断によるリトライ浪費・誤った A-6 エスカレーションを招きやすい。`apply-base`・`claude-wiki-hub-sync-rules.md`
使用時のみ発生するため Warm 層に留める（全セッション常駐ではない）。
