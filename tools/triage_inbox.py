#!/usr/bin/env python3
"""
triage_inbox.py - idea/bookmark Issue のトリアージ支援ツール（pure query・副作用なし）

inbox-groomer スキルの「重い処理」層。GitHub API は一切叩かない（標準ライブラリのみ）。
Claude が mcp__github__list_issues で取得した Issue 一覧を JSON ファイルに保存し、
本ツールにそのパスを渡すことで、ラベル欠損・重複候補・stale 候補を機械的に列挙する。
判断（実際のラベル付与・ファイル作成・コメント・クローズ）は inbox-groomer/SKILL.md 側で
Claude が行う。本ツールは「現状をデータで可視化する」ことに徹する。

想定する Issue JSON の形（mcp__github__list_issues の代表的なフィールドをそのまま渡せる）:
  [
    {
      "number": 42,
      "title": "idea: 〇〇があったら便利そう",
      "body": "本文...",
      "state": "open",
      "labels": ["kind:idea"] または [{"name": "kind:idea"}],
      "createdAt": "2026-07-01T00:00:00Z",
      "updatedAt": "2026-07-01T00:00:00Z"
    },
    ...
  ]

使い方:
  # 1. Claude が MCP で Issue 一覧を取得し JSON 保存
  #    (mcp__github__list_issues の結果をそのまま /tmp/issues.json に書き出す想定)
  # 2. 本ツールで解析
  python3 tools/triage_inbox.py missing --issues-json /tmp/issues.json
  python3 tools/triage_inbox.py similar --issues-json /tmp/issues.json --threshold 0.6
  python3 tools/triage_inbox.py stale   --issues-json /tmp/issues.json --days 30
  python3 tools/triage_inbox.py --self-test

設計方針:
  - 副作用なし（読み取り専用）。GitHub への書き込み・API 呼び出しは一切しない
  - 標準ライブラリのみ（requests 等の外部依存なし・save-metadata-index.md §1 準拠）
  - 日時は JST 定数（表示用）+ UTC（経過時間計算用）。datetime-rules.md 準拠
  - 日本語タイトルの類似度は文字 bigram ベースの Jaccard（形態素解析なしで概算する）
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

KIND_PREFIX = "kind:"
FILE_REF_RE = re.compile(r"\b(ideas|bookmarks)/[^\s\)\]]+")


def label_names(issue):
    """Issue の labels フィールドを文字列リストに正規化する（dict / str の両対応）。"""
    out = []
    for l in issue.get("labels") or []:
        if isinstance(l, dict):
            name = l.get("name")
        else:
            name = l
        if name:
            out.append(name)
    return out


def is_open(issue):
    state = (issue.get("state") or "open").lower()
    return state in ("open", "opened")


def kind_labels(labels):
    return [l for l in labels if l.startswith(KIND_PREFIX)]


def has_file_reference(body):
    """本文に ideas/ または bookmarks/ を含むファイルパス参照行があるか。"""
    if not body:
        return False
    return bool(FILE_REF_RE.search(body))


def find_missing_kind(issues):
    """kind: ラベルの無い open Issue のうち inbox 候補を列挙する。

    タスク Issue（type: ラベル付き）は inbox 対象外なので除外する
    （kind:/type: の namespace 分離・wiki-operations.md）。タイトル先頭が
    idea:/bookmark: のもの、またはラベルが一切無いものだけを候補とする。
    """
    out = []
    for it in issues:
        if not is_open(it):
            continue
        labels = label_names(it)
        if kind_labels(labels):
            continue
        if any(l.startswith("type:") for l in labels):
            continue
        out.append({"number": it.get("number"), "title": it.get("title"), "labels": labels})
    return out


def find_missing_file_ref(issues):
    """kind: ラベル付きだが本文にファイルパス参照が無い open Issue を列挙する
    （GitHub UI から直接放り込まれ、まだファイル化されていないもの）。
    """
    out = []
    for it in issues:
        if not is_open(it):
            continue
        labels = label_names(it)
        kl = kind_labels(labels)
        if not kl:
            continue
        if not has_file_reference(it.get("body")):
            out.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "kind": kl[0],
            })
    return out


def build_missing_report(issues):
    return {
        "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "missing_kind": find_missing_kind(issues),
        "missing_file_ref": find_missing_file_ref(issues),
    }


# ---- タイトル類似度（文字 bigram ベース・日本語対応） ----

_PUNCT_RE = re.compile(r"[\[\]（）()【】「」・,，、。:：/／\-—–#\s]+")  # 数字は残す（年・版違いの誤同一視防止）


def normalize_title(title):
    """記号・空白を除去して比較しやすくする（小文字化含む・数字は保持）。"""
    t = title or ""
    t = re.sub(r"^(idea|bookmark)\s*:\s*", "", t, flags=re.IGNORECASE)
    t = _PUNCT_RE.sub("", t)
    return t.lower()


def char_bigrams(text):
    """正規化済みテキストから文字 bigram の集合を作る（形態素解析なしの概算）。
    CJK は単語分割なしでも bigram で十分な類似度が取れる（trigram だと短文で疎になりすぎる）。
    """
    t = normalize_title(text)
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def find_similar_pairs(issues, threshold=0.6):
    """open Issue のタイトル同士の Jaccard 類似度が閾値以上のペアを列挙する。"""
    open_issues = [it for it in issues if is_open(it)]
    bigrams = {it.get("number"): char_bigrams(it.get("title") or "") for it in open_issues}
    nums = [it.get("number") for it in open_issues]
    titles = {it.get("number"): it.get("title") for it in open_issues}
    pairs = []
    for i in range(len(nums)):
        a = nums[i]
        if not bigrams[a]:
            continue
        for j in range(i + 1, len(nums)):
            b = nums[j]
            if not bigrams[b]:
                continue
            score = jaccard(bigrams[a], bigrams[b])
            if score >= threshold:
                pairs.append({
                    "issues": [a, b],
                    "titles": [titles[a], titles[b]],
                    "score": round(score, 2),
                })
    pairs.sort(key=lambda p: -p["score"])
    return pairs


def build_similar_report(issues, threshold):
    return {
        "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "threshold": threshold,
        "pairs": find_similar_pairs(issues, threshold),
    }


# ---- stale 検出 ----

def _parse_ts(ts):
    if not ts:
        return None
    try:
        # "...Z" 形式を fromisoformat が解釈できる形に変換
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_stale(issues, days=30, now=None):
    """days 超 open の kind: ラベル付き Issue を列挙する（経過計算は UTC）。"""
    now = now or datetime.now(UTC)
    threshold = now - timedelta(days=days)
    out = []
    for it in issues:
        if not is_open(it):
            continue
        labels = label_names(it)
        kl = kind_labels(labels)
        if not kl:
            continue
        updated = _parse_ts(it.get("updatedAt")) or _parse_ts(it.get("createdAt"))
        if updated is None:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        if updated < threshold:
            age_days = (now - updated).days
            out.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "kind": kl[0],
                "updatedAt": it.get("updatedAt"),
                "age_days": age_days,
            })
    out.sort(key=lambda r: -r["age_days"])
    return out


def build_stale_report(issues, days):
    return {
        "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "days_threshold": days,
        "stale": find_stale(issues, days),
    }


def _load_issues(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "issues" in data:
        data = data["issues"]
    if not isinstance(data, list):
        raise ValueError("--issues-json の中身は Issue の配列（または {\"issues\": [...]}）である必要があります")
    return data


def _self_test():
    """副作用のない純粋関数のセルフテスト（3 機能: missing / similar / stale）。"""
    fail = 0

    def check(cond, msg):
        nonlocal fail
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            fail += 1

    # --- missing ---
    issues_missing = [
        {"number": 1, "title": "idea: 何か思いついた", "state": "open", "labels": [], "body": ""},
        {"number": 2, "title": "kind付きだがファイル無し", "state": "open",
         "labels": [{"name": "kind:idea"}], "body": "本文だけでファイルパス無し"},
        {"number": 3, "title": "ファイルあり", "state": "open",
         "labels": ["kind:bookmark"], "body": "ファイル: bookmarks/inbox.md 参照"},
        {"number": 4, "title": "closedなので対象外", "state": "closed", "labels": [], "body": ""},
    ]
    rep = build_missing_report(issues_missing)
    check([m["number"] for m in rep["missing_kind"]] == [1], f"missing_kind ({rep['missing_kind']})")
    check([m["number"] for m in rep["missing_file_ref"]] == [2], f"missing_file_ref ({rep['missing_file_ref']})")

    # --- similar ---
    issues_similar = [
        {"number": 10, "title": "LLM Wiki のタグ設計を見直す", "state": "open", "labels": ["kind:idea"]},
        {"number": 11, "title": "LLM Wiki のタグ設計を検討する", "state": "open", "labels": ["kind:idea"]},
        {"number": 12, "title": "まったく無関係な猫の写真集", "state": "open", "labels": ["kind:idea"]},
    ]
    pairs = find_similar_pairs(issues_similar, threshold=0.6)
    check(any(set(p["issues"]) == {10, 11} for p in pairs), f"similar pair 10-11 ({pairs})")
    check(not any(12 in p["issues"] for p in pairs), f"unrelated issue 12 should not match ({pairs})")

    # jaccard 境界値
    check(jaccard(set(), {"a"}) == 0.0, "jaccard empty set")
    check(jaccard({"ab", "bc"}, {"ab", "bc"}) == 1.0, "jaccard identical")

    # --- stale ---
    now = datetime(2026, 7, 9, tzinfo=UTC)
    issues_stale = [
        {"number": 20, "title": "古いアイデア", "state": "open", "labels": ["kind:idea"],
         "updatedAt": "2026-06-01T00:00:00Z"},  # 38日前 -> stale
        {"number": 21, "title": "最近のアイデア", "state": "open", "labels": ["kind:idea"],
         "updatedAt": "2026-07-05T00:00:00Z"},  # 4日前 -> not stale
        {"number": 22, "title": "kind無しは対象外", "state": "open", "labels": [],
         "updatedAt": "2026-05-01T00:00:00Z"},
    ]
    stale = find_stale(issues_stale, days=30, now=now)
    check([s["number"] for s in stale] == [20], f"stale detection ({stale})")

    if fail == 0:
        print("PASS: triage_inbox self-test (7 checks)")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description="idea/bookmark Issue のトリアージ支援ツール（読み取り専用・GitHub API 非依存）")
    ap.add_argument("--self-test", action="store_true", help="純粋関数のセルフテストを実行して終了")
    sub = ap.add_subparsers(dest="command")

    p_missing = sub.add_parser("missing", help="kind: ラベル欠損・ファイル未作成の Issue を列挙")
    p_missing.add_argument("--issues-json", required=True, help="Issue 一覧 JSON のパス")

    p_similar = sub.add_parser("similar", help="タイトル類似度が高い Issue ペアを列挙")
    p_similar.add_argument("--issues-json", required=True, help="Issue 一覧 JSON のパス")
    p_similar.add_argument("--threshold", type=float, default=0.6, help="Jaccard 類似度の閾値（既定 0.6）")

    p_stale = sub.add_parser("stale", help="長期未整理（stale）の Issue を列挙")
    p_stale.add_argument("--issues-json", required=True, help="Issue 一覧 JSON のパス")
    p_stale.add_argument("--days", type=int, default=30, help="stale とみなす経過日数（既定 30）")

    args = ap.parse_args()

    if args.self_test:
        sys.exit(_self_test())

    if not args.command:
        ap.print_help()
        sys.exit(1)

    issues = _load_issues(args.issues_json)

    if args.command == "missing":
        rep = build_missing_report(issues)
    elif args.command == "similar":
        rep = build_similar_report(issues, args.threshold)
    elif args.command == "stale":
        rep = build_stale_report(issues, args.days)
    else:
        ap.print_help()
        sys.exit(1)

    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
