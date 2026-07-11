#!/usr/bin/env python3
"""routine_scheduler.py — 単一ルーティン用の cron ディスパッチャ。

web 側のルーティンは **1 つだけ**（薄いディスパッチャ）にし、「何を・いつ動かすか」は
リポジトリ内の cron テーブル `config/routine_jobs.yaml` で管理する。ジョブの追加・変更・停止は
YAML を編集して PR するだけで済み、**web のルーティン設定を変更する必要がない**。

単一ルーティンの実行手順（docs/automation/routine-dispatch.md）:
  1. `python3 tools/routine_scheduler.py --due` を実行し、いま due なジョブ一覧（JSON）を得る。
  2. 各ジョブの instructions に従って作業する（モデルは job.model を尊重）。
  3. due が無ければ「実行対象なし」と報告して終了。

## due 判定（stateless・croniter 非依存）

各ジョブの cron（5 フィールド: 分 時 日 月 曜日・JST 基準）に対し、
「**直近 window_hours 時間 (now-window, now] に発火予定があったか**」を分単位で走査して判定する。
`--window-hours` は web ルーティンの実行間隔に合わせる（既定 24＝日次ルーティン。毎時なら 1）。
window をルーティン間隔に一致させれば、各 cron 発火はちょうど 1 回だけ due になる。

## cron 構文（標準 5 フィールド）

  *            すべて
  5            固定値
  1,3,5        リスト
  1-5          範囲
  */2          ステップ
  1-5/2        範囲 + ステップ
曜日は 0=日 .. 6=土（7 も日として受理）。月/曜日のフィールドは数値のみ（名前略称は非対応）。

使い方:
  python3 tools/routine_scheduler.py --due                 # いま due なジョブを JSON 出力
  python3 tools/routine_scheduler.py --due --window-hours 1
  python3 tools/routine_scheduler.py --list                # 全ジョブ（enabled/cron）を表示
  python3 tools/routine_scheduler.py --self-test           # 内蔵テスト
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS = REPO_ROOT / "config" / "routine_jobs.yaml"
JST = _dt.timezone(_dt.timedelta(hours=9))


# ---- cron パーサ / マッチャ（標準ライブラリのみ） ----

_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "dom": (1, 31),
    "month": (1, 12),
    "dow": (0, 6),  # 0=日
}


def _parse_field(expr: str, lo: int, hi: int) -> set[int]:
    """1 つの cron フィールドを取りうる整数集合へ展開する。"""
    values: set[int] = set()
    for part in expr.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"空の cron フィールド要素: {expr!r}")
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"step は正の整数: {part!r}")
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            start_s, end_s = base.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(base)
        if start < lo or end > hi or start > end:
            raise ValueError(f"cron フィールド範囲外: {part!r}（許容 {lo}-{hi}）")
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expr: str) -> dict[str, set[int]]:
    """5 フィールド cron をフィールド名→整数集合の dict にする。"""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron は 5 フィールド必須（分 時 日 月 曜日）: {expr!r}")
    names = ["minute", "hour", "dom", "month", "dow"]
    parsed: dict[str, set[int]] = {}
    for name, f in zip(names, fields):
        lo, hi = _FIELD_RANGES[name]
        if name == "dow":
            # 7 を日(0)として正規化してから展開
            f = ",".join("0" if tok in ("7",) else tok for tok in f.split(","))
        parsed[name] = _parse_field(f, lo, hi)
    return parsed


def cron_matches(parsed: dict[str, set[int]], dt: _dt.datetime) -> bool:
    """単一の datetime が cron にマッチするか。

    標準 cron 同様、日(dom) と 曜日(dow) はどちらかが * でなければ OR 条件。
    両方制約があれば「dom OR dow」のいずれか一致で真。
    """
    if dt.minute not in parsed["minute"]:
        return False
    if dt.hour not in parsed["hour"]:
        return False
    if dt.month not in parsed["month"]:
        return False
    dom_full = parsed["dom"] == set(range(1, 32))
    dow_full = parsed["dow"] == set(range(0, 7))
    dow = (dt.weekday() + 1) % 7  # Python: 月=0..日=6 → cron: 日=0..土=6
    dom_ok = dt.day in parsed["dom"]
    dow_ok = dow in parsed["dow"]
    if dom_full and dow_full:
        return True
    if dom_full:
        return dow_ok
    if dow_full:
        return dom_ok
    return dom_ok or dow_ok


def is_due(cron_expr: str, now: _dt.datetime, window_hours: float) -> bool:
    """(now-window, now] に cron 発火予定が 1 回でもあれば due。"""
    parsed = parse_cron(cron_expr)
    now = now.replace(second=0, microsecond=0)
    minutes = int(round(window_hours * 60))
    # t = now, now-1min, ... , now-(minutes-1)min を走査（now を含む半開区間 (now-window, now]）
    for i in range(minutes):
        t = now - _dt.timedelta(minutes=i)
        if cron_matches(parsed, t):
            return True
    return False


# ---- ジョブテーブル ----

def load_jobs(path: Path) -> tuple[list[dict], float]:
    import yaml  # PyYAML（requirements.txt）
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = data.get("jobs", []) or []
    window = float(data.get("window_hours", 24))
    # 妥当性チェック（cron 構文を事前に弾く）
    for j in jobs:
        if "id" not in j or "cron" not in j:
            raise ValueError(f"ジョブには id と cron が必須: {j!r}")
        parse_cron(j["cron"])  # 構文エラーならここで例外
    return jobs, window


def due_jobs(jobs: list[dict], now: _dt.datetime, window_hours: float) -> list[dict]:
    out = []
    for j in jobs:
        if not j.get("enabled", True):
            continue
        if is_due(j["cron"], now, window_hours):
            out.append(j)
    return out


# ---- CLI ----

def _now(args) -> _dt.datetime:
    if args.now:
        # テスト用: "YYYY-MM-DD HH:MM"（JST 解釈）
        return _dt.datetime.strptime(args.now, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    return _dt.datetime.now(JST)


def main() -> int:
    ap = argparse.ArgumentParser(description="単一ルーティン用 cron ディスパッチャ")
    ap.add_argument("--jobs", default=str(DEFAULT_JOBS), help="ジョブ定義 YAML")
    ap.add_argument("--due", action="store_true", help="いま due なジョブを JSON 出力")
    ap.add_argument("--list", action="store_true", help="全ジョブを表示")
    ap.add_argument("--window-hours", type=float, default=None,
                    help="due 判定窓（時間）。既定は YAML の window_hours")
    ap.add_argument("--now", help="現在時刻を上書き（テスト用・'YYYY-MM-DD HH:MM' JST）")
    ap.add_argument("--self-test", action="store_true", help="内蔵テストを実行")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    path = Path(args.jobs)
    if not path.exists():
        print(f"ジョブ定義が見つかりません: {path}", file=sys.stderr)
        return 1
    jobs, window = load_jobs(path)
    window = args.window_hours if args.window_hours is not None else window
    now = _now(args)

    if args.list:
        for j in jobs:
            state = "on " if j.get("enabled", True) else "off"
            print(f"[{state}] {j['id']:<20} cron={j['cron']!r:<18} model={j.get('model','-')}  {j.get('title','')}")
        return 0

    if args.due:
        due = due_jobs(jobs, now, window)
        result = {
            "now_jst": now.strftime("%Y-%m-%d %H:%M JST"),
            "window_hours": window,
            "due_count": len(due),
            "jobs": [
                {
                    "id": j["id"],
                    "title": j.get("title", j["id"]),
                    "model": j.get("model"),
                    "instructions": j.get("instructions", "").strip(),
                }
                for j in due
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    ap.print_help()
    return 0


def _self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  {'PASS' if cond else 'FAIL'} {name}")

    # フィールド展開
    check("'*' minute = 0..59", _parse_field("*", 0, 59) == set(range(60)))
    check("'1-5' = {1..5}", _parse_field("1-5", 0, 59) == {1, 2, 3, 4, 5})
    check("'*/15' minute", _parse_field("*/15", 0, 59) == {0, 15, 30, 45})
    check("'1,3,5'", _parse_field("1,3,5", 0, 59) == {1, 3, 5})

    # 日曜 20:00 のジョブ
    sun = _dt.datetime(2026, 6, 28, 20, 0, tzinfo=JST)  # 2026-06-28 は日曜
    mon = _dt.datetime(2026, 6, 29, 20, 0, tzinfo=JST)  # 月曜
    check("日曜 cron は日曜にマッチ", cron_matches(parse_cron("0 20 * * 0"), sun))
    check("日曜 cron は月曜に非マッチ", not cron_matches(parse_cron("0 20 * * 0"), mon))

    # 平日 08:00（1-5）
    check("平日 cron は月曜にマッチ", cron_matches(parse_cron("0 8 * * 1-5"), mon.replace(hour=8)))
    check("平日 cron は日曜に非マッチ", not cron_matches(parse_cron("0 8 * * 1-5"), sun.replace(hour=8)))

    # window: 日次(24h)で日曜ジョブは日曜の実行で due・月曜では非 due
    check("window24h: 日曜20:00 は日曜21:00 実行で due",
          is_due("0 20 * * 0", _dt.datetime(2026, 6, 28, 21, 0, tzinfo=JST), 24))
    check("window24h: 日曜20:00 は火曜実行で非 due",
          not is_due("0 20 * * 0", _dt.datetime(2026, 6, 30, 21, 0, tzinfo=JST), 24))
    # window1h: 毎時運用で 20:00 のジョブは 20:30 で due・21:30 で非 due
    check("window1h: 20:00 は 20:30 で due",
          is_due("0 20 * * *", _dt.datetime(2026, 6, 28, 20, 30, tzinfo=JST), 1))
    check("window1h: 20:00 は 21:30 で非 due",
          not is_due("0 20 * * *", _dt.datetime(2026, 6, 28, 21, 30, tzinfo=JST), 1))

    # dom OR dow セマンティクス（両制約は OR）
    check("dom/dow OR: 1日 or 日曜",
          cron_matches(parse_cron("0 0 1 * 0"), _dt.datetime(2026, 6, 1, 0, 0, tzinfo=JST)))  # 6/1 は月曜だが dom=1 一致

    # 不正 cron
    try:
        parse_cron("0 20 * *")  # 4 フィールド
        check("4 フィールドは例外", False)
    except ValueError:
        check("4 フィールドは例外", True)

    print("=> ALL PASS" if ok else "=> FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
