# セッション安全ルール（Hot 層サマリー）

> **SSOT**: 詳細（タイムアウト種別の解説・コマンド例・確認ケース一覧・パイプライン停止テンプレート）は
> `docs/rules/session-safety-rules-detail.md` を参照。

---

> **L-077**（ユーザー確認前の必須リサーチ義務・CP-6 中核）の正本は `lessons-core.md` L-077。重複回避のため本ファイルには置かない。

---

## タイムアウト防止ルール

**ルール 1**: 1 ターンのツール呼び出しは **最大 8 個**。超える場合は中間報告して次ターンへ。

**ルール 3**: 長いタスクは「8 ツール → 中間報告 → 続き」のリズムで進める。

**ルール 4（Stream idle 防止）**: Read の limit をコンテンツ種別で調整する。

```
- シンプルなテキスト: max 200行
- コードブロック・テーブルが多い構造化 Markdown: max 80行
- Python スクリプト・大量コード: max 60行
```

大きな Read（構造化 80 行超 / コード 60 行超）の直後は **短い事実 1 行** を出力してから次のツールへ。

**ルール 5（空結果クロスチェック）**: 状態確認系コマンドがゼロ件を返したら即座にリトライ（最大 3 回）。
完了判定・存在確認は別経路（`gh` と `mcp__github__*`）でクロスチェックしてから判断する。

---

## git 操作安全則

**G-1**: squash マージ後・新ブランチ作成前に必ず origin/main を明示 refspec で同期する。

```bash
git fetch origin +main:refs/remotes/origin/main
git checkout -B <new-branch> origin/main
```

**G-2**: commit は複数 `-m` フラグを使い、直後に `git diff HEAD~1 HEAD --stat` で着地確認する。

```bash
git commit -m "件名" -m "本文"
git diff HEAD~1 HEAD --stat   # 空なら commit は着地していない
```

**G-3**: 完了報告の直前に実マージを機械検証する。

```bash
git fetch origin +main:refs/remotes/origin/main
git log origin/main --oneline | head -3
gh pr view <N> -R <owner>/<repo> --json state,mergedAt   # state=MERGED を確認
```

`state=MERGED` を確認できるまで「マージ済み」と報告しない。

---

## ユーザー確認前の基本手順

```bash
git status
git add .
git commit -m "[wip] ユーザー確認待ち（{概要}）"
git push -u origin {ブランチ名}
# push 完了後にユーザーへの確認メッセージを送る
```
