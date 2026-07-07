# Android からのブックマーク投入セットアップ（スマホ完結・外部アプリ不要）

> Android スマホで、読んでいる記事を最小手数で Claude Code に投げるための設定ガイド。
> **ブラウザで開いている記事** への主経路は **ブックマークレット**（Chrome / Brave）。
> Android / iOS / PC の統合ガイドは [`docs/setup/bookmarklet-setup.md`](bookmarklet-setup.md) を参照。
> 背景・他手段の比較は `docs/proposals/android-bookmark-friction-reduction.md` を参照。

## 主経路: ブックマークレット（Chrome / Brave for Android）

→ **登録手順・使い方・制約は [`docs/setup/bookmarklet-setup.md`](bookmarklet-setup.md) の「Android」セクションを参照。**
ブックマークレットのコードも同ファイルに記載（bootstrap 後はリポ名が自動置換済み）。

## 補助経路: 別アプリからの共有（HTTP Shortcuts・任意）

YouTube / X など、ブラウザ以外のアプリで見ているものを共有シートから送りたい場合の経路。詳細は提案ドキュメント §4 B-2 を参照。

- **[HTTP Shortcuts](https://http-shortcuts.rmy.ch/)**（無料 OSS）を入れ、共有シートに登録。
- 共有された URL を `POST /repos/kai-kou/claude-wiki-hub/issues`（`labels=bookmark`）で 1 リクエスト発行。
- 認証は **fine-grained PAT（Issues: write のみ・このリポジトリのみ）** をヘッダーに固定保持。
- 着地した `bookmark` ラベル Issue は、後段の bookmark 処理ルーティンがバッチで ingest する（将来実装）。

## 後処理（将来実装・別 Issue）

capture したものを Claude が整理する非同期処理。提案ドキュメント §8 を参照:

- `bookmark` ラベル Issue / `bookmarks/inbox.md` の未処理エントリをバッチで ingest（タイトル取得・自動タグ・重複除去・`build_index.py` 再生成・クローズ）。
- `docs/automation/routines.md` の lint ルーティンと同じ Claude Code ネイティブ経路（GitHub Actions 不使用）。
