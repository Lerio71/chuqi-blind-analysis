"""
赛后复盘报告生成器
- 揭晓赛果
- 逐项对照预测 vs 实际
- 归因分析
- 经验提取
- 生成每日复盘 JSON + 汇总报告
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from analyze_signals import prediction_to_dict
from blind_read import blind_read

CST = timezone(timedelta(hours=8))
SCORES_FILE = Path(__file__).parent.parent / "match_data" / "match_scores.json"
REVIEW_DIR = Path(__file__).parent.parent / "match_data" / "reviews"


def load_scores() -> dict[str, dict]:
    if not SCORES_FILE.exists():
        return {}
    return json.loads(SCORES_FILE.read_text(encoding="utf-8"))


def determine_result(h: int, a: int) -> str:
    if h > a: return "主胜"
    if h == a: return "平局"
    return "客胜"


def determine_half_full(hh: int, ah: int, hf: int, af: int) -> str:
    m = {"主胜":"胜","平局":"平","客胜":"负"}
    return f"{m[determine_result(hh,ah)]}-{m[determine_result(hf,af)]}"


def review_match(mid: str, prediction: dict, actual: dict) -> dict[str, Any]:
    hs, as_ = actual.get("h",0), actual.get("a",0)
    hh, ah = actual.get("hh",hs), actual.get("ah",as_)
    actual_result = determine_result(hs, as_)
    actual_hf = determine_half_full(hh,ah,hs,as_)

    checks = []
    pred_1 = prediction.get("result_1","")
    pred_2 = prediction.get("result_2","")
    checks.append({"item":"胜平负","predicted":f"首选{pred_1}"+(f"/次选{pred_2}" if pred_2 else ""),
                    "actual":actual_result,"hit":actual_result in [pred_1,pred_2],"first_hit":actual_result==pred_1})

    actual_score = f"{hs}-{as_}"
    pred_scores = prediction.get("scores",[])
    checks.append({"item":"比分","predicted":" / ".join(pred_scores) if pred_scores else "待定",
                    "actual":actual_score,"hit":actual_score in pred_scores})

    pred_hf = prediction.get("half_full","")
    checks.append({"item":"半全场","predicted":pred_hf or "待定","actual":actual_hf,
                    "hit":actual_hf==pred_hf if pred_hf else False})

    pred_hc = prediction.get("handicap","")
    checks.append({"item":"让球","predicted":f"{pred_hc} ({prediction.get('handicap_detail','')})",
                    "actual":f"比分{actual_score}","hit":None})

    total_goals = hs + as_
    ou = "大球" if total_goals > 2.5 else "小球"
    pred_ou = prediction.get("over_under","")
    checks.append({"item":"大小球","predicted":pred_ou or "待定","actual":f"{ou}({total_goals}球)",
                    "hit":ou in pred_ou if pred_ou and pred_ou!="待定" else None})

    attribution = generate_attribution(prediction, actual_result, checks)
    new_insight = extract_insight(prediction, actual_result, hs, as_)

    return {"match_id":mid,"home":prediction.get("home",""),"away":prediction.get("away",""),
            "prediction":prediction,"actual":{"home_score":hs,"away_score":as_,"result":actual_result,
            "half_full":actual_hf,"score":actual_score,"total_goals":total_goals},
            "checks":checks,"hit_count":sum(1 for c in checks if c["hit"] is True),
            "total_checks":sum(1 for c in checks if c["hit"] is not None),
            "attribution":attribution,"new_insight":new_insight,
            "review_time":datetime.now(CST).isoformat()}


def generate_attribution(pred: dict, actual: str, checks: list) -> dict[str,str]:
    rc = checks[0]
    pred_1 = pred.get("result_1","")
    signals = pred.get("signals_matched",[])
    rules = [s["rule"] for s in signals]
    att = {"direction":"","root_cause":"","lesson":""}

    if rc["hit"]:
        att["direction"] = f"Correct: pred {pred_1} hit {actual}"
        if any(r in rules for r in ["#2","#47","#48"]):
            att["root_cause"] = "Hot+cold signal effective"
        elif "#63" in rules:
            att["root_cause"] = "Reverse+hot=caution signal effective"
        elif "#66" in rules:
            att["root_cause"] = "Reverse+50%+home=regression signal effective"
        att["lesson"] = "Rule validated, maintain"
    else:
        att["direction"] = f"Miss: pred {pred_1} actual {actual}"
        if actual=="主胜" and pred_1 in ["客胜","平局"]:
            att["root_cause"] = "Underestimated home advantage or over-trusted reverse"
            att["lesson"] = "Check if home per in 50-60% range (#66), reverse may still mean home win"
        elif actual=="客胜" and pred_1=="主胜":
            att["root_cause"] = "Missed away hot real signal or reverse signal"
            att["lesson"] = "Check away cold<1 (#31) or reverse (#63)"
        elif actual=="平局":
            att["root_cause"] = "Missed overheat draw signal (#65) or history draw pattern (#35)"
            att["lesson"] = "Home hot cold>1 = draw caution"
        else:
            att["root_cause"] = "Uncovered scenario"
            att["lesson"] = "Record for iteration"
    return att


def extract_insight(pred: dict, actual: str, h: int, a: int) -> str:
    signals = pred.get("signals_matched",[])
    if not signals: return ""
    top = signals[0]
    rule = top.get("rule","")
    r1 = pred.get("result_1","")
    if r1 and actual in r1 and actual == r1:
        return f"{rule} validated: {top['desc']} -> {h}-{a} {actual}"
    elif r1 and actual not in [r1, pred.get("result_2","")]:
        return f"{rule} failed: {top['desc']} -> {h}-{a} {actual}, need additional precondition"
    else:
        return f"{rule} partial: pred {r1}/{pred.get('result_2','')} actual {actual}"


def generate_daily_review(match_ids: list[str], scores: dict[str,dict]) -> dict[str,Any]:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    match_dir = Path(__file__).parent.parent / "match_data"
    reviews = []

    for mid in match_ids:
        mid = mid.strip()
        if mid not in scores:
            print(f"Skip {mid}: no score")
            continue
        try:
            report = blind_read(mid, match_dir)
        except SystemExit:
            print(f"Skip {mid}: no data")
            continue
        from analyze_signals import analyze, print_prediction
        pred = analyze(report)
        prediction = prediction_to_dict(pred)
        review = review_match(mid, prediction, scores[mid])
        reviews.append(review)

    total = len(reviews)
    first_hits = sum(1 for r in reviews if r["checks"][0]["first_hit"])
    any_hits = sum(1 for r in reviews if r["checks"][0]["hit"])

    summary = {
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "total_matches": total,
        "first_choice_hits": first_hits,
        "any_choice_hits": any_hits,
        "first_hit_rate": f"{first_hits}/{total}" if total else "0/0",
        "any_hit_rate": f"{any_hits}/{total}" if total else "0/0",
        "reviews": reviews,
        "new_insights": [r["new_insight"] for r in reviews if r["new_insight"]],
        "generated_at": datetime.now(CST).isoformat(),
    }

    date_str = datetime.now(CST).strftime("%Y-%m-%d")
    review_path = REVIEW_DIR / f"daily_review_{date_str}.json"
    review_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Daily Review | {date_str}")
    print(f"{'='*60}")
    print(f"Total: {total}")
    if total:
        print(f"1st hit: {first_hits}/{total} ({first_hits/total*100:.0f}%)")
        print(f"Any hit: {any_hits}/{total} ({any_hits/total*100:.0f}%)")
    print(f"\nNew insights:")
    for ins in summary["new_insights"]:
        print(f"  - {ins}")
    print(f"\nSaved: {review_path}")

    return summary


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python generate_review.py <match_id>        # single review")
        print("  python generate_review.py --batch ids.txt   # batch review")
        print("  python generate_review.py --today           # today's matches")
        sys.exit(1)

    scores = load_scores()

    if sys.argv[1] == "--batch":
        ids = [l.strip() for l in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if l.strip()]
        generate_daily_review(ids, scores)
    elif sys.argv[1] == "--today":
        season_path = Path(__file__).parent.parent / "match_data" / "season_data.json"
        if season_path.exists():
            season = json.loads(season_path.read_text(encoding="utf-8"))
            today = datetime.now(CST).strftime("%Y-%m-%d")
            ids = [str(e["id"]) for e in season.get("events",[]) if today in str(e.get("scheduletime",""))]
            if ids:
                generate_daily_review(ids, scores)
            else:
                print(f"No matches today ({today})")
        else:
            print("Run first: python chuqi_pipeline.py --season")
    else:
        mid = sys.argv[1]
        if mid not in scores:
            print(f"Score not found: {mid}")
            print(f"Add to {SCORES_FILE}: {{\"{mid}\":{{\"h\":0,\"a\":0}}}}")
            sys.exit(1)

        match_dir = Path(__file__).parent.parent / "match_data"
        report = blind_read(mid, match_dir)
        from analyze_signals import analyze, print_prediction
        pred = analyze(report)
        print_prediction(pred)

        prediction = prediction_to_dict(pred)
        review = review_match(mid, prediction, scores[mid])

        print(f"\n{'='*60}")
        print(f"Post-Match | {review['home']} vs {review['away']}")
        print(f"Actual: {review['actual']['score']} ({review['actual']['result']})")
        print(f"{'='*60}\n")
        for c in review["checks"]:
            hit = "OK" if c["hit"] is True else "X" if c["hit"] is False else "?"
            print(f"  [{hit}] {c['item']}: pred[{c['predicted']}] actual[{c['actual']}]")
        print(f"\nAttribution: {review['attribution']['direction']}")
        print(f"Root cause: {review['attribution']['root_cause']}")
        print(f"Lesson: {review['attribution']['lesson']}")
        print(f"\nNew insight: {review['new_insight']}")


if __name__ == "__main__":
    main()
