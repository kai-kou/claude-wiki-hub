#!/usr/bin/env python3
"""detect_pr_diff_type.py — PR の差分が「コード変更」を含むかを判定する（#2880）。

audio/image/video パイプラインの Step 8（PR 作成前）で実行し、
差分が VOICEVOX 自動生成データのみ（content/scripts/V*_timed.json 等）の場合は
重い Layer 2（敵対的多観点議論）をスキップして PR 所要時間を削減する。
外部 AI レビュアー（Copilot / Gemini）への依頼は廃止済みで、レビューは常に Claude 自身の
/code-review セルフレビュー（Layer 1・全 PR 必須）で完結する（SSOT: docs/rules/ai-reviewer-strategy.md）。

判定ロジック:
- コード拡張子（.py/.ts/.tsx/.js/.jsx/.sh/.yaml/.yml/.toml/.md）を含むか
- 拡張子マッチでは拾えない critical な設定・依存関係ファイル名（package.json / Dockerfile /
  requirements.txt / pyproject.toml / .gitignore / Makefile 等）も code 扱い（CRITICAL_FILENAMES）
- ただし以下のパス配下は auto-gen データ扱いで code 変更とみなさない（DATA_PATH_PREFIXES）:
  - `content/` 配下（自動生成された台本・素材・分析データ）
  - `docs/research/` 配下（Deep Research 出力）
  - `remotion/src/data/` 配下（image-pipeline が生成する imageMap.ts / scene data）

使い方:
    python3 tools/detect_pr_diff_type.py                  # JSON 出力（既定）
    python3 tools/detect_pr_diff_type.py --base origin/main
    python3 tools/detect_pr_diff_type.py --head HEAD --base origin/main

出力例:
    {
      "has_code": false,
      "data_only": true,
      "review_strategy": "claude_only",
      "code_files": [],
      "data_files": ["content/scripts/V183_timed.json"]
    }

review_strategy（外部レビュアー依頼は廃止。Claude セルフレビュー前提）:
- "claude_only": Layer 0 機械ゲート + Layer 1 /code-review セルフレビューのみ（Layer 2 スキップ）
- "full": Layer 0 + Layer 1 /code-review + 条件付き Layer 2（敵対的多観点議論）を起動

終了コード: 常に 0（判定情報を JSON で返す。スキル側で分岐する）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

CODE_EXTENSIONS = re.compile(r"\.(py|ts|tsx|js|jsx|sh|ya?ml|toml|md)$")
# 自動生成データの配置先（コード拡張子でもコード変更とみなさない）
# - content/: 自動生成された台本・素材・分析データ
# - docs/research/: リサーチ成果（Deep Research 出力）
# - remotion/src/data/: image-pipeline が生成する imageMap.ts / scene data（auto-gen TS）
DATA_PATH_PREFIXES = ("content/", "docs/research/", "remotion/src/data/")
# 拡張子マッチでは拾えない critical な設定・依存関係ファイル名（コード変更と同等に扱う）
# package.json は .json 拡張子だがコード変更と同等の影響を持つため除外できない
CRITICAL_FILENAMES = frozenset({
    "package.json", "package-lock.json", "pnpm-lock.yaml",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock",
    ".gitignore", ".gitattributes",
    "Makefile",
})


def get_diff_files(base: str, head: str) -> list[str] | None:
    """base...head の差分ファイル一覧を取得する。

    エラー時は None を返し、呼び出し側で安全側（full レビュー）にフォールバックさせる。
    空リスト [] は「正常に取得できたが差分が 0 件」を示し、None と意味が異なる。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...{head}"],
            capture_output=True, text=True, check=True,
        )
    except Exception as e:
        # subprocess.CalledProcessError（base 不在等）/ FileNotFoundError（git 未インストール）等を広く捕捉
        stderr_msg = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) else str(e)
        print(f"⚠️  git diff failed: {stderr_msg}", file=sys.stderr)
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def classify(files: list[str]) -> dict:
    """ファイルリストを「コード変更」と「データのみ変更」に分類する。"""
    code_files: list[str] = []
    data_files: list[str] = []
    for path in files:
        filename = path.rsplit("/", 1)[-1]
        is_code = bool(CODE_EXTENSIONS.search(path)) or filename in CRITICAL_FILENAMES
        is_data_path = any(path.startswith(p) for p in DATA_PATH_PREFIXES)
        if is_code and not is_data_path:
            code_files.append(path)
        else:
            data_files.append(path)

    has_code = len(code_files) > 0
    return {
        "has_code": has_code,
        "data_only": not has_code and len(data_files) > 0,
        "review_strategy": "full" if has_code else "claude_only",
        "code_files": code_files,
        "data_files": data_files,
        "total_files": len(files),
    }


def _full_review_fallback() -> dict:
    """get_diff_files が None を返した時の安全側フォールバック（full レビュー）。"""
    return {
        "has_code": True,
        "data_only": False,
        "review_strategy": "full",
        "code_files": [],
        "data_files": [],
        "total_files": 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="PR 差分タイプ判定（#2880）")
    ap.add_argument("--base", default="origin/main", help="比較元ブランチ（既定: origin/main）")
    ap.add_argument("--head", default="HEAD", help="比較先（既定: HEAD）")
    ap.add_argument("--strategy-only", action="store_true",
                    help="review_strategy のみ出力（シェルスクリプトでの利用向け）")
    args = ap.parse_args()

    files = get_diff_files(args.base, args.head)
    if files is None:
        # エラー時は安全側で full レビュー（Layer 2 をスキップしない）
        result = _full_review_fallback()
    else:
        result = classify(files)

    if args.strategy_only:
        print(result["review_strategy"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
