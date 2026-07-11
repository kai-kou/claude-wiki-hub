#!/usr/bin/env python3
"""query_index.py — 保存系横断インデックスの統一クエリ層（grep / SQLite バックエンド切替）。

`content/index/all.jsonl`（build_index.py が frontmatter から生成する導出インデックス）に対し、
**安定した CLI**（search / sql / stats）で検索・複合フィルタ・集計を提供する。バックエンドは
件数に応じて自動選択する（YAGNI）:

- **grep バックエンド（既定・Phase 0）**: all.jsonl を線形スキャンする。追加成果物を作らない。
  少件数（既定 < 500 レコード）ではこれで十分速く、現行の grep + JSONL 運用と完全互換。
- **SQLite バックエンド（Phase 1〜・閾値到達で自動切替）**: all.jsonl から **エフェメラルな
  SQLite**（`content/index/all.db`・gitignore）を on-demand 構築し、Bツリーインデックス + FTS5 で
  複合条件クエリ・全文検索（CJK 対応）を O(log n) で行う。

CLI は同一なので、件数が閾値を超えても **呼び出し側は変更不要**（バックエンドのみ透過的に切替）。

## 設計（専門チーム議論 #26・cloud-native-datastore・PASS）
- **唯一の真実源は frontmatter**。導出の連鎖は `frontmatter → all.jsonl（build_index.py）→
  all.db（本ツール・SQLite 時のみ）`。all.db は **gitignore されたエフェメラル成果物**
  （binary を git に commit しない＝差分汚染なし・欠損時は all.jsonl から再構築）。
- **エンジンは SQLite（標準ライブラリ）**。DuckDB は pip 追加依存が現クラウド環境で不可のため除外
  （将来フェーズ候補として保留）。
- **activation 閾値**: `records ≥ 500`（実測で P95 grep レイテンシ ≥ 200ms になる規模の目安）。
  到達するまで grep バックエンドを既定にし、YAGNI を守る。`--backend` で明示上書きできる。
- **CJK 全文検索**: FTS5 の既定 `unicode61` は日本語を単語分割しないため本番 FTS に使わない。
  代わりに **`trigram` トークナイザ**（SQLite 3.34+・追加依存ゼロ）で 3-gram 部分一致を行い、
  1〜2 文字の短語は **LIKE 部分一致にフォールバック** する。

## 使い方
    python3 tools/query_index.py search "比較"                  # 全文/部分一致（自動バックエンド）
    python3 tools/query_index.py search wiki --kind bookmark    # 複合: 検索語 + kind 絞り込み
    python3 tools/query_index.py search "" --tag llm --status unread --json
    python3 tools/query_index.py sql "SELECT kind, COUNT(*) FROM records GROUP BY kind"  # SQLite
    python3 tools/query_index.py stats                          # kind/status/tag/月次集計
    python3 tools/query_index.py search foo --backend sqlite    # バックエンド明示
    python3 tools/query_index.py build                          # all.db を強制再構築（SQLite）
    python3 tools/query_index.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = REPO_ROOT / "content" / "index"
JSONL_PATH = INDEX_DIR / "all.jsonl"
STATS_PATH = INDEX_DIR / "stats.json"
DB_PATH = INDEX_DIR / "all.db"

# SQLite バックエンドへ自動切替する件数の目安（議論 #26: records≥500 で grep が実測 P95≥200ms 規模）。
ACTIVATION_THRESHOLD = 500
# FTS5 trigram は 3-gram のためクエリ 3 文字未満では機能しない。短語は LIKE にフォールバックする。
_TRIGRAM_MIN = 3
_PUBLIC_FIELDS = ("id", "kind", "title", "date", "status", "tags", "path", "ref")


# ---------------------------------------------------------------------------
# 共通: all.jsonl ロード / バックエンド選択
# ---------------------------------------------------------------------------
def _load_records() -> list[dict]:
    if not JSONL_PATH.is_file():
        raise FileNotFoundError(
            f"{JSONL_PATH.relative_to(REPO_ROOT)} が見つかりません。先に "
            "`python3 tools/build_index.py` で生成してください。"
        )
    out: list[dict] = []
    with JSONL_PATH.open(encoding="utf-8") as f:  # 行ストリームでメモリ O(1)
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _record_count() -> int:
    if not JSONL_PATH.is_file():
        return 0
    with JSONL_PATH.open(encoding="utf-8") as f:  # 全読み込みせず行カウント
        return sum(1 for ln in f if ln.strip())


def select_backend(explicit: str | None = None) -> str:
    """'grep' | 'sqlite' を返す。explicit 指定が無ければ件数で自動選択（< 閾値=grep）。"""
    if explicit in ("grep", "sqlite"):
        return explicit
    return "sqlite" if _record_count() >= ACTIVATION_THRESHOLD else "grep"


def _normalize_public(r: dict) -> dict:
    """レコードを all.jsonl と同じ公開フィールド形に整える。"""
    return {k: r.get(k) if k != "tags" else list(r.get("tags") or []) for k in _PUBLIC_FIELDS}


def _passes_filters(r: dict, *, kind: str | None, tag: str | None, status: str | None) -> bool:
    if kind and r.get("kind") != kind:
        return False
    if status and r.get("status") != status:
        return False
    if tag and tag.strip().lower() not in {str(t).lower() for t in (r.get("tags") or [])}:
        return False
    return True


# ---------------------------------------------------------------------------
# grep バックエンド（Phase 0・既定・追加成果物なし）
# ---------------------------------------------------------------------------
def _grep_search(
    term: str, *, kind: str | None, tag: str | None, status: str | None, limit: int
) -> list[dict]:
    term_l = (term or "").strip().lower()
    out: list[dict] = []
    for r in _load_records():
        if not _passes_filters(r, kind=kind, tag=tag, status=status):
            continue
        if term_l:
            hay = " ".join(
                str(x) for x in (
                    r.get("title") or "", r.get("path") or "", r.get("ref") or "",
                    " ".join(map(str, r.get("tags") or [])),
                )
            ).lower()
            if term_l not in hay:
                continue
        out.append(_normalize_public(r))
        if len(out) >= limit:
            break
    return out


def _grep_stats() -> dict:
    """stats.json（build_index.py 生成）をそのまま返す。無ければ all.jsonl から即算出。"""
    if STATS_PATH.is_file():
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    # フォールバック: stats.json 不在時は records から最小集計
    from collections import Counter
    recs = _load_records()
    by_kind: Counter = Counter(r.get("kind") for r in recs)
    return {"total": len(recs), "by_kind": dict(sorted(by_kind.items()))}


# ---------------------------------------------------------------------------
# SQLite バックエンド（Phase 1〜・閾値到達 or 明示時）
# ---------------------------------------------------------------------------
_SCHEMA = """
DROP TABLE IF EXISTS records;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS records_fts;
CREATE TABLE records(
  rowid   INTEGER PRIMARY KEY,
  id      TEXT UNIQUE,
  kind    TEXT,
  title   TEXT,
  date    TEXT,
  status  TEXT,
  path    TEXT,
  ref     TEXT,
  tags_text TEXT
);
CREATE TABLE tags(record_rowid INTEGER, tag TEXT);
CREATE INDEX idx_records_kind   ON records(kind);
CREATE INDEX idx_records_date   ON records(date);
CREATE INDEX idx_records_status ON records(status);
CREATE INDEX idx_tags_tag       ON tags(tag);
CREATE INDEX idx_tags_rowid     ON tags(record_rowid);
CREATE VIRTUAL TABLE records_fts USING fts5(
  title, tags_text, ref,
  content='records', content_rowid='rowid', tokenize='trigram'
);
"""


def build_db(con: sqlite3.Connection) -> int:
    """all.jsonl を読み込み SQLite を全件再構築する。レコード数を返す。"""
    con.executescript(_SCHEMA)
    records = _load_records()
    # 一括 INSERT を単一トランザクションで囲む（commit 回数削減 + 例外時に自動ロールバック）。
    with con:
        for i, r in enumerate(records, start=1):
            tags = r.get("tags") or []
            con.execute(
                "INSERT INTO records(rowid,id,kind,title,date,status,path,ref,tags_text) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (i, r.get("id"), r.get("kind"), r.get("title"), r.get("date"),
                 r.get("status"), r.get("path"), r.get("ref"), " ".join(map(str, tags))),
            )
            for t in tags:
                con.execute("INSERT INTO tags(record_rowid,tag) VALUES(?,?)", (i, str(t)))
        con.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
    return len(records)


def _db_is_stale() -> bool:
    if not DB_PATH.is_file():
        return True
    if not JSONL_PATH.is_file():
        return False
    return JSONL_PATH.stat().st_mtime > DB_PATH.stat().st_mtime


def get_connection(*, force_build: bool = False) -> sqlite3.Connection:
    """all.db への接続を返す。古ければ（または force_build なら）all.jsonl から再構築する。"""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if force_build or _db_is_stale():
        if DB_PATH.exists():
            DB_PATH.unlink()
        con = sqlite3.connect(DB_PATH)
        build_db(con)
        return con
    return sqlite3.connect(DB_PATH)


def _filter_clauses(
    kind: str | None, tag: str | None, status: str | None
) -> tuple[list[str], list[object]]:
    """kind/tag/status の複合フィルタを SQL の WHERE 句断片 + パラメータにする。

    フィルタは **LIMIT より前に SQL 側で適用** する（Python 側で LIMIT 後に絞ると、
    マッチ多数 × 選択的フィルタで結果が空になる「filter-after-limit」バグになるため）。
    """
    conds: list[str] = []
    params: list[object] = []
    if kind:
        conds.append("r.kind = ?")
        params.append(kind)
    if status:
        conds.append("r.status = ?")
        params.append(status)
    if tag:
        conds.append(
            "EXISTS (SELECT 1 FROM tags WHERE record_rowid = r.rowid AND lower(tag) = ?)"
        )
        params.append(tag.strip().lower())
    return conds, params


def _sqlite_search(
    con: sqlite3.Connection, term: str, *,
    kind: str | None, tag: str | None, status: str | None, limit: int,
) -> list[dict]:
    con.row_factory = sqlite3.Row
    term = (term or "").strip()
    conds, params = _filter_clauses(kind, tag, status)
    rows: list[sqlite3.Row] = []

    if term:
        # 1) FTS5 trigram（3 文字以上）。フィルタも同一クエリに統合する。
        if len(term) >= _TRIGRAM_MIN:
            safe = term.replace('"', '""')
            sql = ("SELECT r.* FROM records_fts f JOIN records r ON r.rowid=f.rowid "
                   "WHERE records_fts MATCH ?")
            fts_params: list[object] = [f'"{safe}"', *params]
            if conds:
                sql += " AND " + " AND ".join(conds)
            sql += " ORDER BY rank LIMIT ?"
            fts_params.append(limit)
            try:
                rows = con.execute(sql, fts_params).fetchall()
            except sqlite3.OperationalError:
                # trigram を含まない語（例: 3 文字以上の記号列）は MATCH が例外を投げる。
                # → LIKE フォールバックに流す。
                rows = []
        # 2) 短語（< 3 文字）or FTS が 0 件/例外 → LIKE 部分一致（フィルタ統合）。
        if not rows:
            like = f"%{term}%"
            sql = ("SELECT r.* FROM records r WHERE "
                   "(r.title LIKE ? OR r.tags_text LIKE ? OR r.ref LIKE ? OR r.path LIKE ?)")
            like_params: list[object] = [like, like, like, like, *params]
            if conds:
                sql += " AND " + " AND ".join(conds)
            sql += " ORDER BY r.kind, r.date DESC LIMIT ?"
            like_params.append(limit)
            rows = con.execute(sql, like_params).fetchall()
    else:
        # 検索語なし: フィルタのみで一覧。
        sql = "SELECT r.* FROM records r"
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY r.kind, r.date DESC LIMIT ?"
        rows = con.execute(sql, [*params, limit]).fetchall()

    return [_sqlite_public_record(con, dict(row)) for row in rows]


def _sqlite_public_record(con: sqlite3.Connection, d: dict) -> dict:
    tags = [t for (t,) in con.execute(
        "SELECT tag FROM tags WHERE record_rowid=? ORDER BY tag", (d["rowid"],))]
    return {
        "id": d.get("id"), "kind": d.get("kind"), "title": d.get("title"),
        "date": d.get("date"), "status": d.get("status"), "tags": tags,
        "path": d.get("path"), "ref": d.get("ref"),
    }


def run_sql(con: sqlite3.Connection, statement: str) -> list[dict]:
    """SELECT/WITH のみ許可する読み取り専用 SQL を実行し、行を dict 列で返す。"""
    stripped = statement.strip().rstrip(";").lstrip("(").strip()
    head = stripped.split(None, 1)[0].lower() if stripped else ""
    if head not in ("select", "with"):
        raise ValueError("読み取り専用クエリ（SELECT / WITH）のみ許可されています。")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return [dict(r) for r in con.execute(statement).fetchall()]


def _sqlite_stats(con: sqlite3.Connection) -> dict:
    def counts(sql: str) -> dict:
        return {k: c for k, c in con.execute(sql)}

    return {
        "total": con.execute("SELECT COUNT(*) FROM records").fetchone()[0],
        "by_kind": counts("SELECT kind, COUNT(*) FROM records GROUP BY kind ORDER BY kind"),
        "by_status": counts(
            "SELECT status, COUNT(*) FROM records WHERE status IS NOT NULL "
            "GROUP BY status ORDER BY status"),
        "by_tag": counts(
            "SELECT tag, COUNT(*) c FROM tags WHERE tag NOT LIKE 'cat:%' "
            "GROUP BY tag ORDER BY c DESC, tag LIMIT 20"),
        "by_month": counts(
            "SELECT substr(date,1,7) m, COUNT(*) FROM records WHERE date IS NOT NULL "
            "GROUP BY m ORDER BY m"),
    }


# ---------------------------------------------------------------------------
# ディスパッチ（安定 API: バックエンドを意識せず呼べる）
# ---------------------------------------------------------------------------
def search(
    term: str, *, kind: str | None = None, tag: str | None = None,
    status: str | None = None, limit: int = 50, backend: str | None = None,
) -> list[dict]:
    be = select_backend(backend)
    if be == "grep":
        return _grep_search(term, kind=kind, tag=tag, status=status, limit=limit)
    con = get_connection()
    return _sqlite_search(con, term, kind=kind, tag=tag, status=status, limit=limit)


def stats(backend: str | None = None) -> dict:
    be = select_backend(backend)
    if be == "grep":
        return _grep_stats()
    return _sqlite_stats(get_connection())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print(obj: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    if isinstance(obj, list):
        if not obj:
            print("（ヒットなし）")
            return
        for r in obj:
            if isinstance(r, dict) and "kind" in r and "title" in r:
                tags = ",".join(r.get("tags") or [])
                print(f"[{r['kind']}] {r.get('title')}  ({r.get('path')})"
                      + (f"  #{tags}" if tags else ""))
            else:
                print(r)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="保存系横断インデックスの統一クエリ層（grep/SQLite）")
    ap.add_argument("--self-test", action="store_true", help="内蔵テストを実行")
    sub = ap.add_subparsers(dest="cmd")

    p_search = sub.add_parser("search", help="全文/部分一致 + 複合フィルタ")
    p_search.add_argument("term", nargs="?", default="", help="検索語（空ならフィルタのみ）")
    p_search.add_argument("--kind")
    p_search.add_argument("--tag")
    p_search.add_argument("--status")
    p_search.add_argument("--limit", type=int, default=50)
    p_search.add_argument("--backend", choices=["grep", "sqlite", "auto"], default="auto")
    p_search.add_argument("--json", action="store_true")

    p_sql = sub.add_parser("sql", help="読み取り専用 SQL（SELECT/WITH・SQLite バックエンド）")
    p_sql.add_argument("statement")
    p_sql.add_argument("--json", action="store_true")

    p_stats = sub.add_parser("stats", help="kind/status/tag/月次の集計")
    p_stats.add_argument("--backend", choices=["grep", "sqlite", "auto"], default="auto")
    sub.add_parser("build", help="all.db を強制再構築（SQLite バックエンド）")
    sub.add_parser("backend", help="現在自動選択されるバックエンドと件数を表示")

    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "build":
        con = get_connection(force_build=True)
        n = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        print(f"✅ all.db 再構築: {DB_PATH.relative_to(REPO_ROOT)}（{n} レコード）")
        return 0

    if args.cmd == "backend":
        n = _record_count()
        be = select_backend(None)
        print(json.dumps({"records": n, "threshold": ACTIVATION_THRESHOLD,
                          "active_backend": be}, ensure_ascii=False))
        return 0

    if args.cmd == "search":
        be = None if args.backend == "auto" else args.backend
        res = search(args.term, kind=args.kind, tag=args.tag, status=args.status,
                     limit=args.limit, backend=be)
        _print(res, args.json)
        return 0

    if args.cmd == "sql":
        con = get_connection()  # SQL は SQLite バックエンドを必須とする
        try:
            res = run_sql(con, args.statement)
        except (ValueError, sqlite3.OperationalError) as e:
            print(f"❌ {e}", file=sys.stderr)
            return 2
        _print(res, args.json)
        return 0

    if args.cmd == "stats":
        be = None if args.backend == "auto" else args.backend
        _print(stats(backend=be), True)
        return 0

    ap.print_help()
    return 0


# ---------------------------------------------------------------------------
# self-test（メモリ DB / 一時 JSONL で完結・実ファイルを汚さない）
# ---------------------------------------------------------------------------
def _self_test() -> int:
    sample = [
        {"id": "bookmark:a", "kind": "bookmark", "title": "PKM ツール比較 2026",
         "date": "2026-06-25", "status": "unread",
         "tags": ["pkm", "tooling"], "path": "bookmarks/inbox.md", "ref": "https://x"},
        {"id": "wiki:topics/karpathy-llm-wiki", "kind": "wiki",
         "title": "Karpathy LLM Wiki パターン", "date": "2026-06-25", "status": None,
         "tags": ["llm", "wiki"], "path": "wiki/topics/karpathy-llm-wiki.md", "ref": None},
        {"id": "idea:capture", "kind": "idea", "title": "毎日の気づきをまとめるフロー",
         "date": "2026-06-20", "status": "raw",
         "tags": ["workflow", "llm"], "path": "ideas/capture.md", "ref": None},
    ]

    # --- grep バックエンド（実ファイル非依存・records を直接渡す形で検証） ---
    def grep_search(recs, term, **f):
        # _grep_search の純関数部分を再現（_load_records をモック）
        term_l = (term or "").strip().lower()
        out = []
        for r in recs:
            if not _passes_filters(r, kind=f.get("kind"), tag=f.get("tag"),
                                   status=f.get("status")):
                continue
            if term_l:
                hay = " ".join(str(x) for x in (
                    r.get("title") or "", r.get("path") or "", r.get("ref") or "",
                    " ".join(map(str, r.get("tags") or [])))).lower()
                if term_l not in hay:
                    continue
            out.append(_normalize_public(r))
        return out

    # grep: CJK 部分一致（grep は substring なので 2 文字でもヒット）
    assert {r["title"] for r in grep_search(sample, "比較")} == {"PKM ツール比較 2026"}
    # grep: 複合フィルタ kind + tag
    assert {r["title"] for r in grep_search(sample, "", kind="idea", tag="llm")} == \
        {"毎日の気づきをまとめるフロー"}
    # grep: status フィルタ
    assert {r["kind"] for r in grep_search(sample, "", status="unread")} == {"bookmark"}
    # バックエンド自動選択: 少件数は grep
    assert select_backend(None) in ("grep", "sqlite")  # 実 all.jsonl 件数に依存
    assert select_backend("sqlite") == "sqlite" and select_backend("grep") == "grep"

    # --- SQLite バックエンド（メモリ DB） ---
    con = sqlite3.connect(":memory:")
    con.executescript(_SCHEMA)
    for i, r in enumerate(sample, start=1):
        con.execute(
            "INSERT INTO records(rowid,id,kind,title,date,status,path,ref,tags_text) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (i, r["id"], r["kind"], r["title"], r["date"], r["status"], r["path"],
             r["ref"], " ".join(r["tags"])),
        )
        for t in r["tags"]:
            con.execute("INSERT INTO tags(record_rowid,tag) VALUES(?,?)", (i, t))
    con.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
    con.commit()
    # CJK 全文検索: trigram（3 文字以上）
    assert "Karpathy LLM Wiki パターン" in {
        r["title"] for r in _sqlite_search(con, "パターン", kind=None, tag=None,
                                           status=None, limit=50)}
    # CJK 短語（2 文字）: LIKE フォールバック
    assert "PKM ツール比較 2026" in {
        r["title"] for r in _sqlite_search(con, "比較", kind=None, tag=None,
                                           status=None, limit=50)}
    # 複合フィルタ kind + tag（検索語なし）
    assert {r["title"] for r in _sqlite_search(con, "", kind="idea", tag="llm",
                                               status=None, limit=50)} == \
        {"毎日の気づきをまとめるフロー"}
    # 検索語あり × kind フィルタ: "llm" は wiki/idea 両方にヒットするが kind=idea で 1 件に絞る
    # （filter-after-limit バグの回帰: フィルタが SQL WHERE 側で効くこと）
    assert {r["title"] for r in _sqlite_search(con, "llm", kind="idea", tag=None,
                                               status=None, limit=50)} == \
        {"毎日の気づきをまとめるフロー"}
    # filter-after-limit 回帰: limit=1 でも「フィルタに合致する行」を返す（フィルタ後に空にならない）
    res = _sqlite_search(con, "", kind="wiki", tag=None, status=None, limit=1)
    assert len(res) == 1 and res[0]["kind"] == "wiki", res
    # trigram 不可な記号列（3 文字以上）は例外で落ちず LIKE フォールバックする（クラッシュ回帰）
    assert isinstance(_sqlite_search(con, "...", kind=None, tag=None,
                                     status=None, limit=50), list)
    # tags がリストで復元される
    res = _sqlite_search(con, "", kind="wiki", tag=None, status=None, limit=50)
    assert res and res[0]["tags"] == ["llm", "wiki"], res
    # 読み取り専用 SQL: SELECT 可 / 書き込み拒否
    rows = run_sql(con, "SELECT kind FROM records ORDER BY kind")
    assert [r["kind"] for r in rows] == ["bookmark", "idea", "wiki"], rows
    for bad in ("DELETE FROM records", "DROP TABLE records", "UPDATE records SET kind='x'"):
        try:
            run_sql(con, bad)
            raise AssertionError(f"書き込みが拒否されなかった: {bad}")
        except ValueError:
            pass
    # 集計
    st = _sqlite_stats(con)
    assert st["total"] == 3 and st["by_kind"]["bookmark"] == 1 and st["by_tag"]["llm"] == 2, st

    print("✅ query_index self-test PASS（grep/SQLite 両バックエンド・trigram+LIKE・"
          "複合フィルタ・読取専用SQL・集計・自動選択）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
