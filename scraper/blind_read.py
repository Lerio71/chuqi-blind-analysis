"""
盲测读取器 — 屏蔽赛果，只输出关键指标
- 威廉/立博/澳门/竞彩 欧赔
- 威廉/立博/澳门 亚盘
- 必发四向量占比/盈亏/冷热
- 信号检测（主客大热/盘赔反向/极端过热/盈亏信号）
"""

import json
import sys
from pathlib import Path

KEY_BOOKMAKERS_EU = ["威廉", "立博", "澳门", "竞彩", "Bet365", "Pinnacle", "易胜博", "伟德", "明升", "12BET"]
KEY_BOOKMAKERS_AH = ["威廉", "立博", "澳门", "竞彩", "伟德", "明升", "利记"]


def load_structured(match_dir: Path, mid: str) -> dict:
    json_path = match_dir / mid / f"{mid}_structured.json"
    if not json_path.exists():
        json_path = match_dir / f"{mid}_structured.json"
    if not json_path.exists():
        print(f"Data not found: {json_path}")
        sys.exit(1)
    return json.loads(json_path.read_text(encoding="utf-8"))


def find_bookmaker(odds_list: list[dict], name_keyword: str) -> dict | None:
    for item in odds_list:
        if name_keyword.lower() in item.get("supplier", "").lower():
            return item
    return None


def extract_key_eu_odds(structured: dict) -> dict:
    odds_1x2 = structured.get("parsed", {}).get("odds_1x2", [])
    result = {}
    for name in KEY_BOOKMAKERS_EU:
        item = find_bookmaker(odds_1x2, name)
        if item:
            result[name] = {k: item.get(k, "") for k in
                ["home_cp","draw_cp","away_cp","home_js","draw_js","away_js","home_change","draw_change","away_change"]}
    return result


def extract_key_ah_odds(structured: dict) -> dict:
    odds_ah = structured.get("parsed", {}).get("odds_ah", [])
    result = {}
    for name in KEY_BOOKMAKERS_AH:
        item = find_bookmaker(odds_ah, name)
        if item:
            result[name] = {k: item.get(k, "") for k in
                ["home_cp","handicap_cp","away_cp","home_js","handicap_js","away_js","handicap_change","home_water_change"]}
    return result


def extract_bifa_summary(structured: dict) -> dict:
    bifa = structured.get("parsed", {}).get("bifa", [])
    result = {}
    for item in bifa:
        result[item.get("name", "")] = {k: item.get(k, 0) for k in ["odds","amount","per","profit","hot"]}
    return result


def analyze_bifa_signals(bifa: dict) -> dict:
    home = bifa.get("主胜", bifa.get("home", {}))
    draw = bifa.get("平局", bifa.get("draw", {}))
    away = bifa.get("客胜", bifa.get("away", {}))

    total_amount = home.get("amount", 0) + draw.get("amount", 0) + away.get("amount", 0)
    if total_amount == 0:
        return {"error": "no bifa data"}

    home_per = home.get("per", 0)
    away_per = away.get("per", 0)
    home_hot = home.get("hot", 0)
    away_hot = away.get("hot", 0)
    home_profit = home.get("profit", 0)
    away_profit = away.get("profit", 0)

    signals = {
        "home_per": home_per, "draw_per": draw.get("per", 0), "away_per": away_per,
        "home_hot": home_hot, "away_hot": away_hot,
        "home_profit": home_profit, "away_profit": away_profit,
        "total_amount": total_amount,
    }

    if home_per >= 65:
        signals["home_hot_signal"] = True
        signals["home_hot_cold"] = home_hot
        signals["home_hot_reliable"] = home_hot < 1

    if away_per >= 55:
        signals["away_hot_signal"] = True
        signals["away_hot_cold"] = away_hot
        signals["away_hot_reliable"] = away_hot < 1

    if home_per >= 85 or away_per >= 85:
        signals["extreme_overheat"] = True

    if abs(home_profit) < 1 and home_per > 50:
        signals["home_profit_neutral"] = True
    if home_profit < -10000:
        signals["home_profit_negative"] = True

    return signals


def analyze_odds_signals(eu_odds: dict, ah_odds: dict) -> dict:
    signals = {}
    jc = eu_odds.get("竞彩") or eu_odds.get("Bet365") or {}
    if jc:
        home_change = jc.get("home_change", "")
        if isinstance(home_change, (int, float)):
            if home_change > 0.15:
                signals["jc_home_up"] = True
                signals["jc_home_up_pct"] = home_change
            elif home_change < -0.15:
                signals["jc_home_down"] = True
                signals["jc_home_down_pct"] = home_change

    wl = ah_odds.get("威廉") or {}
    if wl:
        hc_change = wl.get("handicap_change", "")
        hw_change = wl.get("home_water_change", "")
        if isinstance(hc_change, (int, float)):
            if hc_change < 0:
                signals["wl_handicap_drop"] = True
            elif hc_change > 0:
                signals["wl_handicap_raise"] = True
        if isinstance(hw_change, (int, float)) and hw_change > 0:
            signals["wl_home_water_up"] = True

    if signals.get("jc_home_up") and signals.get("wl_handicap_drop"):
        signals["odds_ah_reverse"] = True
    if signals.get("jc_home_down") and signals.get("wl_handicap_raise"):
        signals["odds_ah_same"] = True

    return signals


def blind_read(mid: str, match_dir: Path) -> dict:
    structured = load_structured(match_dir, mid)
    detail = structured.get("boards", {}).get("detail", {}).get("info", {})
    eu_odds = extract_key_eu_odds(structured)
    ah_odds = extract_key_ah_odds(structured)
    bifa = extract_bifa_summary(structured)
    bifa_signals = analyze_bifa_signals(bifa)
    odds_signals = analyze_odds_signals(eu_odds, ah_odds)

    return {
        "match_id": mid,
        "home": detail.get("home", "?"),
        "away": detail.get("away", "?"),
        "eu_odds": eu_odds,
        "ah_odds": ah_odds,
        "bifa": bifa,
        "bifa_signals": bifa_signals,
        "odds_signals": odds_signals,
    }


def print_blind_report(report: dict):
    print(f"\n{'='*60}")
    print(f"Blind Report | {report['home']} vs {report['away']}")
    print(f"{'='*60}\n")

    print("--- Key EU Odds ---")
    for name, odds in report["eu_odds"].items():
        print(f"  {name}: H{odds['home_cp']}->{odds['home_js']}({odds['home_change']}) "
              f"D{odds['draw_cp']}->{odds['draw_js']} "
              f"A{odds['away_cp']}->{odds['away_js']}({odds['away_change']})")

    print("\n--- Key AH Odds ---")
    for name, odds in report["ah_odds"].items():
        print(f"  {name}: H{odds['home_cp']}->{odds['home_js']} "
              f"HC{odds['handicap_cp']}->{odds['handicap_js']}({odds['handicap_change']}) "
              f"A{odds['away_cp']}->{odds['away_js']}")

    print("\n--- Bifa ---")
    for name, data in report["bifa"].items():
        print(f"  {name}: odds={data['odds']} amt={data['amount']} per={data['per']}% "
              f"pnl={data['profit']} hot={data['hot']}")

    print("\n--- Signals ---")
    bs = report["bifa_signals"]
    os_ = report["odds_signals"]
    if bs.get("home_hot_signal"):
        print(f"  [HOME HOT] per={bs['home_per']}% hot={bs['home_hot']} "
              f"{'RELIABLE' if bs.get('home_hot_reliable') else 'OVERHEAT-CAUTION'}")
    if bs.get("away_hot_signal"):
        print(f"  [AWAY HOT] per={bs['away_per']}% hot={bs['away_hot']} "
              f"{'RELIABLE' if bs.get('away_hot_reliable') else 'SNUBBED'}")
    if bs.get("extreme_overheat"):
        print("  [!] EXTREME OVERHEAT (>=85%): HIGH RISK")
    if os_.get("odds_ah_reverse"):
        print("  [REVERSE] Odds up + AH drop = bearish home")
    if os_.get("odds_ah_same"):
        print("  [SAME] Odds down + AH raise = TRAP (bullish home = lure)")
    if os_.get("jc_home_down"):
        print(f"  [JC DOWN] JC home -{os_.get('jc_home_down_pct', '')} = bullish home")


def main():
    if len(sys.argv) < 2:
        print("Usage: python blind_read.py <match_id>")
        sys.exit(1)
    mid = sys.argv[1]
    match_dir = Path(__file__).parent.parent / "match_data"
    report = blind_read(mid, match_dir)
    print_blind_report(report)


if __name__ == "__main__":
    main()
