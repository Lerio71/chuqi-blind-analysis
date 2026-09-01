"""
楚奇网核心抓取库
- 并发抓取比赛数据页（12线程）
- 自动解 gzip
- 提取内联 JS 数据块
- 解析欧赔(20家)/亚盘(17家)/必发数据
"""

import gzip
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

CST = timezone(timedelta(hours=8))

SEASON_URL = "https://data.chuqi.com/football/comp-match/15354/?sid=54875"
MATCH_DETAIL_URL = "https://live.chuqi.com/football/live-detail/{mid}/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://data.chuqi.com/",
}

SECTIONS = [
    "schedule", "lineup", "vs", "stats",
    "odds1x2", "oddsah", "bifa",
]


def fetch_url(url: str, timeout: int = 15) -> str:
    if requests is None:
        raise ImportError("pip install requests")

    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    content = resp.content

    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)

    return content.decode("utf-8", errors="replace")


def extract_ai_param(html: str) -> dict[str, Any]:
    patterns = [
        r"__dataAiClientParam\s*=\s*({.*?});\s*</script>",
        r"__dataAiClientParam\s*=\s*({.*?})\s*</script>",
        r"window\.__dataAiClientParam\s*=\s*({.*?});",
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    match = re.search(r'"groups"\s*:\s*\{', html)
    if match:
        start = html.rfind("{", 0, match.start())
        if start >= 0:
            brace_count = 0
            end = start
            for i in range(start, len(html)):
                if html[i] == "{":
                    brace_count += 1
                elif html[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            try:
                return json.loads(html[start:end])
            except json.JSONDecodeError:
                pass
    return {}


def extract_inline_data(html: str) -> dict[str, Any]:
    result = {}

    patterns = [
        r"boards\s*=\s*({.*?})\s*;\s*</script>",
        r"var\s+boards\s*=\s*({.*?})\s*;",
        r"window\.boards\s*=\s*({.*?})\s*;",
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if result:
                    return result
            except json.JSONDecodeError:
                continue

    odds1x2 = _extract_section(html, "odds1x2")
    if odds1x2:
        result.setdefault("boards", {})["odds1x2"] = odds1x2

    oddsah = _extract_section(html, "oddsah")
    if oddsah:
        result.setdefault("boards", {})["oddsah"] = oddsah

    bifa = _extract_bifa(html)
    if bifa:
        result.setdefault("boards", {})["bifa"] = bifa

    detail = _extract_detail(html)
    if detail:
        result.setdefault("boards", {})["detail"] = detail

    return result


def _extract_section(html: str, section_name: str) -> dict[str, Any] | None:
    patterns = [
        rf'"{section_name}"\s*:\s*(\{{[^}}]*\}})',
        rf"{section_name}\s*=\s*(\{{.*?\}})\s*;",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _extract_bifa(html: str) -> dict[str, Any] | None:
    patterns = [
        r'allData\s*=\s*(\[.*?\])\s*[;<]',
        r'"allData"\s*:\s*(\[.*?\])',
        r"allData\s*:\s*(\[.*?\])",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return {"allData": json.loads(match.group(1))}
            except json.JSONDecodeError:
                continue
    return None


def _extract_detail(html: str) -> dict[str, Any] | None:
    patterns = [
        r'"info"\s*:\s*(\{.*?\})\s*[,}]',
        r"info\s*=\s*(\{.*?\})\s*;",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return {"info": json.loads(match.group(1))}
            except json.JSONDecodeError:
                continue
    return None


def parse_teams(ai_param: dict[str, Any]) -> dict[int, str]:
    teams = {}
    teams_data = ai_param.get("teams", {})

    if isinstance(teams_data, dict):
        fields = teams_data.get("fields", [])
        values = teams_data.get("values", [])
        id_idx = None
        name_idx = None
        for i, f in enumerate(fields):
            if f == "id":
                id_idx = i
            elif f in ("zh_hans", "name", "zh"):
                name_idx = i
        if id_idx is not None and name_idx is not None:
            for row in values:
                if len(row) > max(id_idx, name_idx):
                    teams[row[id_idx]] = row[name_idx]
    elif isinstance(teams_data, list):
        for team in teams_data:
            if isinstance(team, dict):
                tid = team.get("id")
                name = team.get("zh_hans") or team.get("name") or team.get("zh")
                if tid and name:
                    teams[tid] = name
    return teams


def parse_events(ai_param: dict[str, Any]) -> list[dict[str, Any]]:
    events_data = ai_param.get("events", {})
    events = []

    if isinstance(events_data, dict):
        fields = events_data.get("fields", [])
        values = events_data.get("values", [])
        field_map = {f: i for i, f in enumerate(fields)}
        for row in values:
            event = {key: row[idx] for key, idx in field_map.items() if idx < len(row)}
            events.append(event)
    elif isinstance(events_data, list):
        events = events_data

    events.sort(key=lambda x: x.get("scheduletime", ""))
    return events


def get_round(event_index: int) -> int:
    return (event_index // 10) + 1


def fetch_match_data(mid: str) -> dict[str, Any]:
    url = MATCH_DETAIL_URL.format(mid=mid)
    html = fetch_url(url)
    data = extract_inline_data(html)

    detail = data.get("boards", {}).get("detail", {}).get("info", {})
    if not detail and BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        home_el = soup.select_one(".home-name, .team-home .name, [data-home]")
        away_el = soup.select_one(".away-name, .team-away .name, [data-away]")
        detail = {
            "home": home_el.get_text(strip=True) if home_el else "",
            "away": away_el.get_text(strip=True) if away_el else "",
        }
    elif not detail:
        detail = {"home": "", "away": ""}

    data.setdefault("boards", {}).setdefault("detail", {})["info"] = detail
    data["match_id"] = mid
    data["fetch_time"] = datetime.now(CST).isoformat()
    return data


def fetch_season_data() -> dict[str, Any]:
    html = fetch_url(SEASON_URL)
    ai_param = extract_ai_param(html)
    teams = parse_teams(ai_param)
    events = parse_events(ai_param)
    for i, event in enumerate(events):
        event["round"] = get_round(i)

    return {
        "teams": teams,
        "events": events,
        "total_matches": len(events),
        "fetch_time": datetime.now(CST).isoformat(),
    }


def batch_fetch_matches(match_ids: list[str], max_workers: int = 12) -> dict[str, dict[str, Any]]:
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_mid = {executor.submit(fetch_match_data, mid): mid for mid in match_ids}
        for future in as_completed(future_to_mid):
            mid = future_to_mid[future]
            try:
                results[mid] = future.result()
            except Exception as e:
                results[mid] = {"error": str(e), "match_id": mid}
    return results


def parse_odds_1x2(boards: dict[str, Any]) -> list[dict[str, Any]]:
    data = boards.get("odds1x2", {}).get("data", {})
    odds_list = data.get("odds", [])
    suppliers = data.get("supplier", [])

    result = []
    for odd, supplier in zip(odds_list, suppliers):
        cp = odd.get("cp", {})
        js = odd.get("js", {})
        result.append({
            "supplier": supplier,
            "home_cp": cp.get("a", ""), "draw_cp": cp.get("b", ""), "away_cp": cp.get("c", ""),
            "home_js": js.get("a", ""), "draw_js": js.get("b", ""), "away_js": js.get("c", ""),
            "home_change": _calc_change(cp.get("a"), js.get("a")),
            "draw_change": _calc_change(cp.get("b"), js.get("b")),
            "away_change": _calc_change(cp.get("c"), js.get("c")),
        })
    return result


def parse_odds_ah(boards: dict[str, Any]) -> list[dict[str, Any]]:
    data = boards.get("oddsah", {}).get("data", {})
    odds_list = data.get("odds", [])
    suppliers = data.get("supplier", [])

    result = []
    for odd, supplier in zip(odds_list, suppliers):
        cp = odd.get("cp", {})
        js = odd.get("js", {})
        result.append({
            "supplier": supplier,
            "home_cp": cp.get("a", ""), "handicap_cp": cp.get("c", ""), "away_cp": cp.get("b", ""),
            "home_js": js.get("a", ""), "handicap_js": js.get("c", ""), "away_js": js.get("b", ""),
            "handicap_change": _calc_change(cp.get("c"), js.get("c")),
            "home_water_change": _calc_change(cp.get("a"), js.get("a")),
        })
    return result


def parse_bifa(boards: dict[str, Any]) -> list[dict[str, Any]]:
    all_data = boards.get("bifa", {}).get("allData", [])
    result = []
    for item in all_data:
        summary = item.get("summary", {})
        result.append({
            "name": item.get("name", ""),
            "odds": summary.get("odds", -1),
            "amount": summary.get("amount", 0),
            "per": summary.get("per", 0),
            "profit": summary.get("profit", 0),
            "hot": summary.get("hot", 0),
        })
    return result


def _calc_change(old: Any, new: Any) -> float | str:
    try:
        old_f = float(old)
        new_f = float(new)
        if old_f == 0:
            return ""
        return round((new_f - old_f) / old_f, 4)
    except (ValueError, TypeError):
        return ""


def build_structured(match_data: dict[str, Any]) -> dict[str, Any]:
    boards = match_data.get("boards", {})
    detail = boards.get("detail", {}).get("info", {})
    return {
        "match_id": match_data.get("match_id", ""),
        "fetch_time": match_data.get("fetch_time", ""),
        "boards": {
            "odds1x2": {"data": boards.get("odds1x2", {}).get("data", {})},
            "oddsah": {"data": boards.get("oddsah", {}).get("data", {})},
            "bifa": {"allData": boards.get("bifa", {}).get("allData", [])},
            "detail": {"info": detail},
        },
        "parsed": {
            "odds_1x2": parse_odds_1x2(boards),
            "odds_ah": parse_odds_ah(boards),
            "bifa": parse_bifa(boards),
        },
    }


def save_match_data(match_data: dict[str, Any], output_dir: Path) -> Path:
    mid = match_data.get("match_id", "unknown")
    match_dir = output_dir / mid
    match_dir.mkdir(parents=True, exist_ok=True)

    structured = build_structured(match_data)
    json_path = match_dir / f"{mid}_structured.json"
    json_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path
