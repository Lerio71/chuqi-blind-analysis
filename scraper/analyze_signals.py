"""
v15 信号分析引擎
6 级信号优先级 + 66 条经验规则
输出五项预测：胜平负 / 比分 / 半全场 / 让球 / 大小球
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Prediction:
    match_id: str = ""
    home: str = ""
    away: str = ""
    result_1: str = ""
    result_2: str = ""
    result_prob: dict[str, float] = field(default_factory=dict)
    scores: list[str] = field(default_factory=list)
    half_full: str = ""
    handicap: str = ""
    handicap_detail: str = ""
    over_under: str = ""
    signals_matched: list[dict] = field(default_factory=list)
    confidence: str = "中"
    notes: str = ""


def analyze(blind_report: dict) -> Prediction:
    pred = Prediction(
        match_id=blind_report.get("match_id", ""),
        home=blind_report.get("home", "?"),
        away=blind_report.get("away", "?"),
    )

    bs = blind_report.get("bifa_signals", {})
    os_ = blind_report.get("odds_signals", {})
    bifa = blind_report.get("bifa", {})

    home_per = bs.get("home_per", 0)
    away_per = bs.get("away_per", 0)
    home_hot = bs.get("home_hot", 0)
    away_hot = bs.get("away_hot", 0)
    home_profit = bs.get("home_profit", 0)
    away_profit = bs.get("away_profit", 0)
    odds_reverse = os_.get("odds_ah_reverse", False)
    odds_same = os_.get("odds_ah_same", False)

    # S1: round context (needs season data)
    pred.signals_matched.append({
        "rule": "S1-round-context",
        "desc": "Check round-level home/away tendency + giant-club rebound risk",
        "action": "Contextual overlay required",
    })

    # S2: home hot cold<1 + weak opp = home win
    if bs.get("home_hot_signal") and bs.get("home_hot_reliable"):
        pred.signals_matched.append({"rule": "#2/47/48", "desc": f"Home hot({home_per}%) cold={home_hot}(<1)=real", "action": "Home win"})
        pred.result_1 = "主胜"; pred.result_2 = "平局"
        pred.result_prob = {"主胜": 0.67, "平局": 0.2, "客胜": 0.13}
        pred.scores = ["2-0","3-0","2-1"]; pred.half_full = "胜-胜"
        pred.confidence = "高"; pred.notes = "Home hot cold<1=real signal (#48)"

    # S3: away hot cold low + away strong = away win
    elif bs.get("away_hot_signal") and bs.get("away_hot_reliable"):
        pred.signals_matched.append({"rule": "#3/31", "desc": f"Away hot({away_per}%) cold={away_hot}(<1)=real", "action": "Away win"})
        pred.result_1 = "客胜"; pred.result_2 = "平局"
        pred.result_prob = {"客胜": 0.50, "平局": 0.25, "主胜": 0.25}
        pred.scores = ["0-1","0-2","1-2"]; pred.half_full = "平-负"
        pred.confidence = "中"; pred.notes = "Away hot cold<1=real (#31)"

    # S4: home hot + odds reverse = caution
    elif bs.get("home_hot_signal") and odds_reverse:
        pred.signals_matched.append({"rule": "#63", "desc": f"Home hot({home_per}%)+reverse=strongest caution", "action": "Away/Draw"})
        pred.result_1 = "客胜"; pred.result_2 = "平局"
        pred.result_prob = {"客胜": 0.45, "平局": 0.30, "主胜": 0.25}
        pred.scores = ["0-1","1-1","0-0"]; pred.half_full = "平-负"
        pred.confidence = "高"; pred.notes = "Home hot+reverse=bookmaker bearish (#63)"

    # S5: reverse + home 50% + home ground = home regression
    elif odds_reverse and 45 <= home_per <= 60:
        pred.signals_matched.append({"rule": "#66", "desc": f"Reverse+home {home_per}%(not hot)+home=regression", "action": "Home win"})
        pred.result_1 = "主胜"; pred.result_2 = "平局"
        pred.result_prob = {"主胜": 0.45, "平局": 0.30, "客胜": 0.25}
        pred.scores = ["2-1","1-0","1-1"]; pred.half_full = "胜-胜"
        pred.confidence = "中"; pred.notes = "Reverse+50%+home=validated 3 rounds (#66)"

    # S6: home hot cold>1 = draw caution
    elif bs.get("home_hot_signal") and home_hot > 1:
        pred.signals_matched.append({"rule": "#65", "desc": f"Home hot({home_per}%) cold={home_hot}(>1)=overheat draw", "action": "Draw first"})
        pred.result_1 = "平局"; pred.result_2 = "客胜"
        pred.result_prob = {"平局": 0.40, "客胜": 0.35, "主胜": 0.25}
        pred.scores = ["1-1","2-2","0-0"]; pred.half_full = "平-平"
        pred.confidence = "中"; pred.notes = "Home hot cold>1=overheat funds unreal (#65)"

    # Same direction = trap
    elif odds_same:
        pred.signals_matched.append({"rule": "#50", "desc": "Same direction(odds down+AH raise)=trap", "action": "Away first"})
        pred.result_1 = "客胜"; pred.result_2 = "平局"
        pred.result_prob = {"客胜": 0.46, "主胜": 0.38, "平局": 0.16}
        pred.scores = ["0-1","1-1","0-2"]; pred.half_full = "平-负"
        pred.confidence = "中"; pred.notes = "Same direction=bullish home=lure trap (#50)"

    # Away hot cold>=1 = snubbed
    elif bs.get("away_hot_signal") and away_hot >= 1:
        pred.signals_matched.append({"rule": "#47", "desc": f"Away hot({away_per}%) cold={away_hot}(>=1)=snubbed", "action": "Home/Draw"})
        pred.result_1 = "主胜"; pred.result_2 = "平局"
        pred.result_prob = {"主胜": 0.40, "平局": 0.35, "客胜": 0.25}
        pred.scores = ["1-0","1-1","2-1"]; pred.half_full = "胜-胜"
        pred.confidence = "中"; pred.notes = "Away hot cold>=1=overheat snubbed (#47)"

    # Extreme overheat
    elif bs.get("extreme_overheat"):
        pred.signals_matched.append({"rule": "#13/11", "desc": "Extreme overheat(>=85%)=bookmaker harvest", "action": "Caution"})
        pred.result_1 = "平局"; pred.result_2 = "客胜"
        pred.result_prob = {"平局": 0.35, "客胜": 0.35, "主胜": 0.30}
        pred.scores = ["1-1","0-0","0-1"]; pred.confidence = "中"
        pred.notes = "3-way extreme=perfect story trap (#11)"

    # Profit neutral
    elif abs(home_profit) < 1 and home_per > 50:
        pred.signals_matched.append({"rule": "#17", "desc": f"Home pnl~0({home_profit})+per={home_per}%=bookmaker ok", "action": "Home win"})
        pred.result_1 = "主胜"; pred.result_2 = "平局"
        pred.result_prob = {"主胜": 0.45, "平局": 0.30, "客胜": 0.25}
        pred.scores = ["1-0","2-1","1-1"]; pred.half_full = "胜-胜"
        pred.confidence = "中"; pred.notes = "Pnl~0=bookmaker doesn't mind (#17)"

    else:
        pred.signals_matched.append({"rule": "default", "desc": "No strong signal", "action": "Manual analysis"})
        pred.result_1 = "待定"; pred.confidence = "低"
        pred.notes = "No strong signal, manual analysis recommended"

    # Handicap
    ah_odds = blind_report.get("ah_odds", {})
    wl = ah_odds.get("威廉") or {}
    hcp_js = wl.get("handicap_js", "")
    if hcp_js:
        try:
            hcp = float(hcp_js)
            if hcp >= 1:
                pred.handicap = "输盘风险"; pred.handicap_detail = f"Deep({hcp}) hot win-no-cover (#51)"
            elif 0 < hcp < 1:
                pred.handicap = "观望"; pred.handicap_detail = f"Shallow({hcp}) TBD"
            elif hcp <= 0:
                pred.handicap = "主队难赢盘"; pred.handicap_detail = f"Drop({hcp}) bearish (#36)"
        except ValueError:
            pred.handicap = "数据不足"
    else:
        pred.handicap = "数据不足"

    # Over/Under
    if home_per >= 60 and abs(home_profit) < 1:
        pred.over_under = "大球优先"
    elif odds_reverse:
        pred.over_under = "小球优先"
    else:
        pred.over_under = "待定"

    return pred


def prediction_to_dict(pred: Prediction) -> dict[str, Any]:
    return {
        "match_id": pred.match_id, "home": pred.home, "away": pred.away,
        "result_1": pred.result_1, "result_2": pred.result_2,
        "result_prob": pred.result_prob, "scores": pred.scores,
        "half_full": pred.half_full, "handicap": pred.handicap,
        "handicap_detail": pred.handicap_detail, "over_under": pred.over_under,
        "confidence": pred.confidence, "notes": pred.notes,
        "signals_matched": pred.signals_matched,
    }


def print_prediction(pred: Prediction):
    print(f"\n{'='*60}")
    print(f"Prediction | {pred.home} vs {pred.away} | Confidence: {pred.confidence}")
    print(f"{'='*60}\n")

    print("[Signals]")
    for s in pred.signals_matched:
        print(f"  [{s['rule']}] {s['desc']} -> {s['action']}")

    print(f"\n[Result] 1st: {pred.result_1} | 2nd: {pred.result_2}")
    if pred.result_prob:
        for k, v in pred.result_prob.items():
            print(f"  {k}: {v:.0%}")
    print(f"\n[Score] {' / '.join(pred.scores) if pred.scores else 'TBD'}")
    print(f"[HF] {pred.half_full or 'TBD'}")
    print(f"[HC] {pred.handicap} ({pred.handicap_detail})")
    print(f"[O/U] {pred.over_under}")
    print(f"\n[Note] {pred.notes}")
