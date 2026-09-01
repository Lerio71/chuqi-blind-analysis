"""
盲测分析管道 — 由 GitHub Actions 调用
输入: match_ids（逗号分隔）
输出: match_data/<mid>/prediction.json + data/analysis_<date>.json
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

# 确保能 import scraper 模块
sys.path.insert(0, str(Path(__file__).parent))

from blind_read import blind_read
from analyze_signals import analyze, prediction_to_dict, print_prediction

MATCH_DIR = Path(__file__).parent.parent / "match_data"
DATA_DIR = Path(__file__).parent.parent / "data"


def run_blind_analysis(match_ids: list[str]) -> list[dict]:
    """对每场比赛执行盲测分析，保存 prediction.json"""
    MATCH_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for mid in match_ids:
        mid = mid.strip()
        if not mid:
            continue

        print(f"\n{'='*60}")
        print(f"Blind Analysis: {mid}")
        print(f"{'='*60}")

        try:
            report = blind_read(mid, MATCH_DIR)
            pred = analyze(report)
            print_prediction(pred)

            pred_dict = prediction_to_dict(pred)
            out = MATCH_DIR / mid / "prediction.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(pred_dict, ensure_ascii=False, indent=2), encoding="utf-8")

            results.append(pred_dict)
            print(f"\nSaved: {out}")

        except SystemExit as e:
            print(f"SKIP {mid}: {e}")
        except Exception as e:
            print(f"ERROR {mid}: {e}")

    return results


def generate_analysis_report(predictions: list[dict]):
    """生成分析报告 JSON"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(CST)
    report = {
        "date": now.strftime("%Y-%m-%d"),
        "total_matches": len(predictions),
        "predictions": predictions,
        "generated_at": now.isoformat(),
    }

    out = DATA_DIR / f"analysis_{now.strftime('%Y-%m-%d_%H%M')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAnalysis report: {out}")
    return out


def main():
    if len(sys.argv) < 2:
        # 无参数时从 season_data.json 获取今日比赛
        season_path = MATCH_DIR / "season_data.json"
        if season_path.exists():
            season = json.loads(season_path.read_text(encoding="utf-8"))
            today = datetime.now(CST).strftime("%Y-%m-%d")
            ids = [
                str(e["id"])
                for e in season.get("events", [])
                if today in str(e.get("scheduletime", ""))
            ]
            if not ids:
                ids = [str(e["id"]) for e in season.get("events", [])][-5:]
        else:
            print("No match IDs provided and no season_data.json found")
            sys.exit(1)
    else:
        ids = sys.argv[1].split(",") if "," in sys.argv[1] else sys.argv[1:]

    print(f"Match IDs: {ids}")
    predictions = run_blind_analysis(ids)
    generate_analysis_report(predictions)
    print(f"\nDone: {len(predictions)} predictions generated")


if __name__ == "__main__":
    main()
