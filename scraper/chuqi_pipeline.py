"""
楚奇网数据提取管道
- 单场/批量提取
- 输出 structured.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from chuqi_lib import (
    CST, batch_fetch_matches, build_structured, fetch_match_data,
    fetch_season_data, save_match_data,
)

DATA_DIR = Path(__file__).parent.parent / "match_data"


def process_single_match(mid: str) -> dict:
    print(f"[{datetime.now(CST).strftime('%H:%M:%S')}] 抓取比赛 {mid} ...")
    t0 = time.time()
    match_data = fetch_match_data(mid)
    elapsed = time.time() - t0

    if "error" in match_data:
        print(f"  FAIL: {match_data['error']}")
        return match_data

    save_match_data(match_data, DATA_DIR)
    structured = build_structured(match_data)
    odds_1x2 = structured["parsed"]["odds_1x2"]
    odds_ah = structured["parsed"]["odds_ah"]
    bifa = structured["parsed"]["bifa"]
    detail = structured["boards"]["detail"]["info"]
    home = detail.get("home", "?")
    away = detail.get("away", "?")
    print(f"  OK {home} vs {away} | EU{len(odds_1x2)} AH{len(odds_ah)} BIFA{len(bifa)} | {elapsed:.1f}s")
    return structured


def process_batch(match_ids: list[str]) -> list[dict]:
    print(f"\n{'='*60}\nBatch: {len(match_ids)} matches\n{'='*60}\n")
    t0 = time.time()
    results = []
    for i, mid in enumerate(match_ids, 1):
        print(f"[{i}/{len(match_ids)}] ", end="")
        results.append(process_single_match(mid))
    elapsed = time.time() - t0
    success = sum(1 for r in results if "error" not in r)
    print(f"\n{'='*60}\nDone: {success}/{len(match_ids)} | {elapsed:.1f}s total\n{'='*60}")
    return results


def update_season_data():
    print("Fetching season data ...")
    season = fetch_season_data()
    print(f"  {season['total_matches']} matches | {len(season['teams'])} teams")
    season_path = DATA_DIR / "season_data.json"
    season_path.parent.mkdir(parents=True, exist_ok=True)
    season_path.write_text(json.dumps(season, ensure_ascii=False, indent=2), encoding="utf-8")

    rounds = {}
    for event in season["events"]:
        r = event.get("round", 0)
        rounds.setdefault(r, []).append(event)
    print(f"  {len(rounds)} rounds")
    for r in sorted(rounds.keys()):
        print(f"  R{r}: {len(rounds[r])} matches")
    return season


def main():
    parser = argparse.ArgumentParser(description="Chuqi data pipeline")
    parser.add_argument("match_ids", nargs="*", help="Match IDs")
    parser.add_argument("--batch", help="Read IDs from file")
    parser.add_argument("--season", action="store_true", help="Update season data")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.season:
        update_season_data()
        return

    if args.batch:
        ids_path = Path(args.batch)
        if not ids_path.exists():
            print(f"File not found: {ids_path}")
            sys.exit(1)
        ids = [line.strip() for line in ids_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        process_batch(ids)
        return

    if args.match_ids:
        if len(args.match_ids) == 1:
            process_single_match(args.match_ids[0])
        else:
            process_batch(args.match_ids)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
