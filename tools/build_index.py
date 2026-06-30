#!/usr/bin/env python3
"""build_index.py — 保存系横断インデックス生成（単一真実源 = 各ファイルの frontmatter）。

bookmarks/ ideas/ wiki/ raw/ の frontmatter を全スキャンし、機械可読インデックス
`content/index/all.jsonl` と集計 `content/index/stats.json` を **全件再生成** する。

ユーザーの「こういうのなかったっけ？」検索のコストを下げ（横断 grep の対象を 1 ファイルに集約）、
集計/分析（kind 別件数・カテゴリ分布・タグ頻度・月次推移）の材料を提供する。

## 設計（専門チーム議論 #24 で決定・SSOT: docs/rules/save-metadata-index.md）
- インデックスは **導出物**。唯一の真実源は各ファイルの frontmatter。手で all.jsonl を編集しない。
- `kind` は **path から導出**（frontmatter に `kind:` があればそれで上書き）。既存ファイルの編集は不要。
- レコードは最小フィールド: id / kind / title / date / status / tags / path / ref。
- `date` は added || created || captured_at をスクリプト側で正規化（JST 表記の日付・YYYY-MM-DD）。
- カテゴリは `cat:` プレフィックスのタグで表現（専用フィールドは持たない・YAGNI）。
- 依存は標準ライブラリ + PyYAML のみ（既存 requirements.txt）。

## 使い方
    python3 tools/build_index.py            # all.jsonl + stats.json を再生成
    python3 tools/build_index.py --stats    # 再生成し、集計サマリを stdout に表示
    python3 tools/build_index.py --quiet     # 出力抑制（保存操作からの呼び出し用）
    python3 tools/build_index.py --self-test # 内蔵テスト
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = REPO_ROOT / "content" / "index"
INDEX_PATH = INDEX_DIR / "all.jsonl"
STATS_PATH = INDEX_DIR / "stats.json"
JST = _dt.timezone(_dt.timedelta(hours=9))

# wiki/ 層で索引対象から除外するトップレベルファイル（目次・ログ・説明）
_WIKI_EXCLUDE = {"index.md", "log.md", "README.md"}
# どの層でも索引しないファイル名
_GLOBAL_EXCLUDE = {"README.md"}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
# inbox.md のメタ行として受理するキー（本文の `Note: ...` 等を meta に吸い込まないため）
_INBOX_KEYS = {"url", "title", "added", "status", "tags", "kind"}


# ---------------------------------------------------------------------------
# 正規化ヘルパー
# ---------------------------------------------------------------------------
def normalize_tag(tag: object) -> str | None:
    """タグを正規化する（lowercase・前後空白除去・空白/アンダースコア→ハイフン）。

    `cat:` 等のプレフィックスのコロンは維持する。空文字は None を返す。
    """
    if tag is None:
        return None
    s = str(tag).strip().lower()
    if not s:
        return None
    # コロン（名前空間プレフィックス cat: 等）は維持、その他の空白/アンダースコアをハイフン化
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or None


def normalize_tags(raw: object) -> list[str]:
    """frontmatter のタグ値（list / "[a, b]" 文字列 / 単一文字列）を正規化リストにする。"""
    items: list[object]
    if raw is None:
        return []
    if isinstance(raw, str):
        parsed = None
        txt = raw.strip()
        if txt.startswith("["):
            try:
                parsed = yaml.safe_load(txt)
            except yaml.YAMLError:
                parsed = None
        if isinstance(parsed, list):
            items = parsed
        elif not txt:
            return []
        else:
            items = [p for p in re.split(r"[,\s]+", txt) if p]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [raw]
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        n = normalize_tag(it)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def normalize_date(value: object) -> str | None:
    """日付値を YYYY-MM-DD 文字列に正規化する（datetime/date/文字列を受ける）。

    ISO 日付（`YYYY-MM-DD` / `YYYY/MM/DD`）以外は None を返す（by_month 等の集計汚染を防ぐ）。
    """
    if value is None:
        return None
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip().replace("/", "-")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def extract_frontmatter(text: str) -> dict | None:
    """ファイル先頭の `---\\n ... \\n---` YAML frontmatter を dict で返す。無ければ None。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _stable_id(kind: str, basis: str) -> str:
    return f"{kind}:{basis}"


# ---------------------------------------------------------------------------
# レコード生成
# ---------------------------------------------------------------------------
def _record(
    *,
    kind: str,
    title: object,
    date: str | None,
    status: str | None,
    tags: list[str],
    path: str,
    ref: str | None,
    id_: str,
) -> dict:
    # title が YAML で int/bool に化けても（例: `title: 2026`）クラッシュさせず文字列化する
    title_s = "" if title is None else str(title)
    return {
        "id": id_,
        "kind": kind,
        "title": title_s.strip() or None,
        "date": date,
        "status": status,
        "tags": tags,
        "path": path,
        "ref": ref,
    }


def _kind_from_path(rel_path: str, fm: dict) -> str:
    """frontmatter の kind を優先し、無ければ path から層を導出する。"""
    if isinstance(fm.get("kind"), str) and fm["kind"].strip():
        return fm["kind"].strip().lower()
    top = rel_path.split("/", 1)[0]
    return {
        "bookmarks": "bookmark",
        "ideas": "idea",
        "wiki": "wiki",
        "raw": "raw",
    }.get(top, top)


def _id_basis_from_rel(rel: str) -> str:
    """層ルート配下の相対パス（拡張子なし）を id の basis にする。

    `wiki/topics/rag.md` → `topics/rag`、`ideas/2026-x.md` → `2026-x`。
    層内の同名 stem（topics/rag と entities/rag）でも id が衝突しない。
    """
    parts = rel.split("/", 1)
    inner = parts[1] if len(parts) > 1 else parts[0]
    if inner.endswith(".md"):
        inner = inner[:-3]
    return inner


def record_from_file(abs_path: Path) -> dict | None:
    """単一 Markdown ファイル（frontmatter 付き）からレコードを生成する。"""
    rel = abs_path.relative_to(REPO_ROOT).as_posix()
    text = abs_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(text) or {}
    kind = _kind_from_path(rel, fm)
    date = (
        normalize_date(fm.get("added"))
        or normalize_date(fm.get("created"))
        or normalize_date(fm.get("captured_at"))
    )
    status = fm.get("status")
    status = str(status).strip() if status not in (None, "") else None
    ref = fm.get("source_url") or fm.get("url") or None
    if ref is not None:
        ref = str(ref).strip() or None
    return _record(
        kind=kind,
        title=fm.get("title"),
        date=date,
        status=status,
        tags=normalize_tags(fm.get("tags")),
        path=rel,
        ref=ref,
        id_=_stable_id(kind, _id_basis_from_rel(rel)),
    )


def records_from_inbox(abs_path: Path) -> list[dict]:
    """bookmarks/inbox.md（1 ファイル複数エントリ）をパースしてレコード列にする。

    `---` 区切りの各ブロック先頭の `key: value` 行を読み、`url:` を持つブロックを 1 エントリとする。
    """
    rel = abs_path.relative_to(REPO_ROOT).as_posix()
    text = abs_path.read_text(encoding="utf-8")
    out: list[dict] = []
    for block in re.split(r"^---\s*$", text, flags=re.MULTILINE):
        meta: dict[str, str] = {}
        for line in block.splitlines():
            if not line.strip():
                if meta:  # メタ行ブロックが終わったら本文に入る
                    break
                continue
            m = _KV_RE.match(line)
            if m and m.group(1).lower() in _INBOX_KEYS:
                meta[m.group(1).lower()] = m.group(2).strip()
            elif meta:
                break
        url = meta.get("url")
        if not url:
            continue
        status = meta.get("status") or None
        out.append(
            _record(
                kind=meta.get("kind", "bookmark").lower(),
                title=meta.get("title"),
                date=normalize_date(meta.get("added")),
                status=status,
                tags=normalize_tags(meta.get("tags")),
                path=rel,
                ref=url.strip() or None,
                id_=_stable_id("bookmark", hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]),
            )
        )
    return out


def _iter_layer_files() -> list[Path]:
    """索引対象の Markdown ファイル一覧（inbox.md を除く・README/index/log を除外）。"""
    files: list[Path] = []
    # bookmarks: 個別ファイル（inbox.md は別パーサ）
    bm = REPO_ROOT / "bookmarks"
    if bm.is_dir():
        for p in sorted(bm.glob("*.md")):
            if p.name not in _GLOBAL_EXCLUDE and p.name != "inbox.md":
                files.append(p)
    # ideas
    ideas = REPO_ROOT / "ideas"
    if ideas.is_dir():
        files += [p for p in sorted(ideas.glob("*.md")) if p.name not in _GLOBAL_EXCLUDE]
    # wiki（topics/entities/glossary。index/log/README は除外）
    wiki = REPO_ROOT / "wiki"
    if wiki.is_dir():
        for p in sorted(wiki.rglob("*.md")):
            if p.name in _WIKI_EXCLUDE or p.name in _GLOBAL_EXCLUDE:
                continue
            files.append(p)
    # raw（samples 含む。README は除外・immutable だが読むのみ）
    raw = REPO_ROOT / "raw"
    if raw.is_dir():
        files += [p for p in sorted(raw.rglob("*.md")) if p.name not in _GLOBAL_EXCLUDE]
    return files


def build_records() -> list[dict]:
    """全保存層をスキャンして決定論的に整列したレコード列を返す。"""
    records: list[dict] = []
    inbox = REPO_ROOT / "bookmarks" / "inbox.md"
    if inbox.is_file():
        records += records_from_inbox(inbox)
    for p in _iter_layer_files():
        rec = record_from_file(p)
        if rec is not None:
            records.append(rec)
    # 決定論的整列（kind → date → id → path）。date 欠落は末尾寄せ。path を最終 tiebreak に入れて安定化。
    records.sort(key=lambda r: (r["kind"], r["date"] or "9999-99-99", r["id"], r["path"]))
    return records


def render_jsonl(records: list[dict]) -> str:
    """レコード列を決定論的な JSONL 文字列にシリアライズする（末尾改行付き）。"""
    return "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records
    )


def build_stats(records: list[dict]) -> dict:
    """集計/分析用の派生指標を算出する（新 frontmatter フィールド不要・JSONL から導出）。"""
    by_kind: Counter = Counter()
    by_status: Counter = Counter()
    by_category: Counter = Counter()
    by_tag: Counter = Counter()
    by_month: Counter = Counter()
    for r in records:
        by_kind[r["kind"]] += 1
        if r["status"]:
            by_status[r["status"]] += 1
        for t in r["tags"]:
            if t.startswith("cat:"):
                by_category[t[4:]] += 1
            else:
                by_tag[t] += 1
        if r["date"]:
            by_month[r["date"][:7]] += 1
    # generated_at 等の非決定論的フィールドは持たせない（再生成のたびに diff チャーンを生み、
    # かつ check_index_sync.py で stats.json も同期検証できるようにするため）。
    return {
        "total": len(records),
        "by_kind": dict(sorted(by_kind.items())),
        "by_status": dict(sorted(by_status.items())),
        "by_category": dict(sorted(by_category.items(), key=lambda x: (-x[1], x[0]))),
        "by_tag": dict(sorted(by_tag.items(), key=lambda x: (-x[1], x[0]))),
        "by_month": dict(sorted(by_month.items())),
    }


def render_stats(records: list[dict]) -> str:
    """集計を決定論的な JSON 文字列にシリアライズする（末尾改行付き）。"""
    return json.dumps(build_stats(records), ensure_ascii=False, indent=2) + "\n"


def write_index(records: list[dict]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(render_jsonl(records), encoding="utf-8")
    STATS_PATH.write_text(render_stats(records), encoding="utf-8")


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    assert normalize_tag("LLM Wiki") == "llm-wiki"
    assert normalize_tag(" Foo_Bar ") == "foo-bar"
    assert normalize_tag("cat:tooling") == "cat:tooling"
    assert normalize_tag("") is None
    assert normalize_tags("[llm, wiki]") == ["llm", "wiki"]
    assert normalize_tags(["A", "a", "b"]) == ["a", "b"]  # 重複除去
    assert normalize_date("2026-06-25") == "2026-06-25"
    assert normalize_date("2026/06/25") == "2026-06-25"  # スラッシュ区切りも正規化
    assert normalize_date("soon") is None  # 非日付は None（集計汚染を防ぐ）
    assert normalize_date(_dt.date(2026, 6, 25)) == "2026-06-25"
    assert normalize_date(None) is None
    fm = extract_frontmatter("---\ntitle: x\ntags: [a, b]\n---\nbody\n")
    assert fm == {"title": "x", "tags": ["a", "b"]}, fm
    assert _kind_from_path("ideas/2026-x.md", {}) == "idea"
    assert _kind_from_path("wiki/topics/x.md", {"kind": "Topic"}) == "topic"
    # title が非文字列でもクラッシュせず文字列化する（`title: 2026` 対策）
    assert _record(kind="x", title=2026, date=None, status=None, tags=[], path="p", ref=None, id_="x:p")["title"] == "2026"
    # 層内の同名 stem でも id が衝突しない（topics/rag と entities/rag）
    assert _id_basis_from_rel("wiki/topics/rag.md") == "topics/rag"
    assert _id_basis_from_rel("wiki/entities/rag.md") == "entities/rag"
    assert _id_basis_from_rel("ideas/2026-x.md") == "2026-x"
    recs = build_records()
    txt = render_jsonl(recs)
    assert txt == render_jsonl(build_records()), "build is non-deterministic"
    assert render_stats(recs) == render_stats(build_records()), "stats is non-deterministic"
    for r in recs:
        assert set(r) == {"id", "kind", "title", "date", "status", "tags", "path", "ref"}
        json.loads(json.dumps(r))  # JSON serializable
    assert len({r["id"] for r in recs}) == len(recs), "id 重複あり"  # id 一意性
    build_stats(recs)  # 例外なく算出できる
    print(f"✅ build_index self-test PASS（現在 {len(recs)} レコード）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="保存系横断インデックスを再生成する")
    ap.add_argument("--stats", action="store_true", help="再生成後に集計サマリを表示")
    ap.add_argument("--quiet", action="store_true", help="出力を抑制（保存操作からの呼び出し用）")
    ap.add_argument("--self-test", action="store_true", help="内蔵テストを実行")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    records = build_records()
    write_index(records)
    if not args.quiet:
        rel = INDEX_PATH.relative_to(REPO_ROOT).as_posix()
        print(f"✅ インデックス再生成: {rel}（{len(records)} レコード）")
    if args.stats:
        print(json.dumps(build_stats(records), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
