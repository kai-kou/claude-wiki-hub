#!/usr/bin/env python3
"""check_index_sync.py — 横断インデックスの desync 検出（CI/e2e ガード）。

`content/index/all.jsonl` が各保存層の frontmatter（唯一の真実源）と一致しているかを検証する。
不一致（保存後に build_index.py を回し忘れた・ファイルを編集した・削除した）を検出したら exit 1。

これは wiki-operations.md「lint のデータギャップ検出」をインデックス層に適用したもの。

## 使い方
    python3 tools/check_index_sync.py          # PASS=exit0 / desync=exit1
    python3 tools/check_index_sync.py --quiet   # 出力抑制（exit code のみ）

desync 時の修正:
    python3 tools/build_index.py               # 再生成して解消
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 起動方法に依存せず build_index を import できるよう、自身のディレクトリ（tools/）を sys.path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_index import (  # noqa: E402
    INDEX_PATH,
    REPO_ROOT,
    STATS_PATH,
    build_records,
    render_jsonl,
    render_stats,
)


def check(quiet: bool = False) -> int:
    rel = INDEX_PATH.relative_to(REPO_ROOT).as_posix()
    stats_rel = STATS_PATH.relative_to(REPO_ROOT).as_posix()
    records = build_records()
    expected = render_jsonl(records)

    if not INDEX_PATH.is_file():
        if not quiet:
            print(f"❌ {rel} が存在しません。`python3 tools/build_index.py` で生成してください。")
        return 1

    actual = INDEX_PATH.read_text(encoding="utf-8")
    if actual != expected:
        if not quiet:
            exp_lines = set(expected.splitlines())
            act_lines = set(actual.splitlines())
            missing = exp_lines - act_lines  # 真実源にあるが index に無い
            stale = act_lines - exp_lines    # index にあるが真実源に無い
            print(f"❌ インデックス desync を検出（{rel}）")
            print(f"   不足（未反映の保存）: {len(missing)} 件 / 余分（陳腐化）: {len(stale)} 件")
            for line in sorted(missing)[:5]:  # 出力を決定論的にソート
                print(f"   + {line[:160]}")
            for line in sorted(stale)[:5]:
                print(f"   - {line[:160]}")
            print("   修正: python3 tools/build_index.py")
        return 1

    # stats.json も同期検証する（all.jsonl だけ再生成して stats が古いままの取りこぼしを防ぐ）
    expected_stats = render_stats(records)
    if not STATS_PATH.is_file() or STATS_PATH.read_text(encoding="utf-8") != expected_stats:
        if not quiet:
            print(f"❌ 集計 desync を検出（{stats_rel}）。修正: python3 tools/build_index.py")
        return 1

    if not quiet:
        print(f"✅ インデックス同期 OK（{len(records)} レコードが frontmatter と一致・stats も整合）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="横断インデックスの desync を検出する")
    ap.add_argument("--quiet", action="store_true", help="出力抑制（exit code のみ）")
    args = ap.parse_args(argv)
    return check(quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
