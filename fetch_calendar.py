from __future__ import annotations
import csv
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from dateutil import parser as dtparser

TZ = ZoneInfo("America/New_York")
OUT = Path("calendar/current_week.json")
ARCHIVE = Path("calendar/archive")
ROUTES = [
    ("json", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"),
    ("csv",  "https://nfs.faireconomy.media/ff_calendar_thisweek.csv"),
    ("xml",  "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"),
    ("ics",  "https://nfs.faireconomy.media/ff_calendar_thisweek.ics"),
]
HEADERS = {
    "Accept": "*/*",
    "User-Agent": "FKX-Calendar-Mirror/2.0 (+weekly Sunday fetch)"
}

def week_bounds(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(TZ)
    start = (local - timedelta(days=(local.weekday() + 1) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=6, hours=23, minutes=59, seconds=59)

def classify(title: str) -> str | None:
    s = title.strip()
    excluded = [
        r"\btreasury\b", r"\bauction\b", r"\bTIC\b", r"foreign bond investment",
        r"federal budget balance", r"crude oil inventories", r"natural gas storage",
        r"gasoline inventories", r"distillate inventories", r"API weekly statistical bulletin"
    ]
    if any(re.search(x, s, re.I) for x in excluded):
        return None
    rules = [
        ("INFLATION", r"\bCPI\b|consumer price|core CPI|\bPPI\b|producer price|core PPI|\bPCE\b|personal consumption expenditures|inflation expectations?|import prices?|export prices?"),
        ("FOMC / FED", r"\bFOMC\b|federal funds rate|Federal Reserve|Fed Chair|Fed Governor|Fed President|Jerome Powell|Powell speaks|Beige Book|FOMC minutes|rate decision|Fed press conference"),
        ("LABOR", r"nonfarm payroll|non-farm payroll|payrolls?|employment change|employment report|unemployment|jobless|unemployment claims|JOLTS|ADP|average hourly earnings|wages?|employment cost|labor productivity|unit labor costs?"),
        ("MORTGAGES", r"mortgage|MBA applications?|refinance|mortgage delinquenc|30-year mortgage rate"),
        ("HOUSING", r"housing starts?|building permits?|new home sales|existing home sales|pending home sales|home sales|home price|Case-Shiller|FHFA house price|NAHB|housing market index"),
        ("ACTIVITY", r"\bGDP\b|retail sales|durable goods|industrial production|capacity utilization|\bPMI\b|\bISM\b|leading index|leading indicators?|trade balance|business inventories|wholesale inventories|factory orders|productivity"),
        ("CONSUMER", r"consumer confidence|consumer sentiment|University of Michigan sentiment"),
    ]
    for category, rx in rules:
        if re.search(rx, s, re.I):
            return category
    return None

def parse_json(text: str):
    raw = json.loads(text)
    return [{"title": x.get("title",""), "country": x.get("country",""), "date": x.get("date","")} for x in raw]

def parse_csv(text: str):
    rows = csv.DictReader(io.StringIO(text))
    out = []
    for r in rows:
        out.append({
            "title": r.get("Title") or r.get("title") or r.get("Event") or r.get("event") or "",
            "country": r.get("Country") or r.get("country") or "",
            "date": r.get("Date") or r.get("date") or r.get("Datetime") or r.get("datetime") or "",
        })
    return out

def parse_xml(text: str):
    root = ET.fromstring(text)
    out = []
    for item in root.findall(".//event") + root.findall(".//item"):
        def pick(*names):
            for n in names:
                node = item.find(n)
                if node is not None and node.text:
                    return node.text
            return ""
        out.append({"title": pick("title","event"), "country": pick("country"), "date": pick("date","datetime")})
    return out

def parse_ics(text: str):
    out, current = [], None
    for line in text.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            out.append({"title": current.get("SUMMARY",""), "country": current.get("COUNTRY","USD"), "date": current.get("DTSTART","")})
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";",1)[0]] = value
    return out

PARSERS = {"json": parse_json, "csv": parse_csv, "xml": parse_xml, "ics": parse_ics}

def normalize(rows, source_name):
    events = []
    for r in rows:
        country = str(r.get("country","")).upper()
        if country and country not in ("USD", "US", "USA", "UNITED STATES"):
            continue
        title = str(r.get("title","")).strip()
        category = classify(title)
        if not category:
            continue
        try:
            dt = dtparser.parse(str(r.get("date","")))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            dt = dt.astimezone(TZ)
        except Exception:
            continue
        events.append({
            "dateTime": dt.isoformat(),
            "category": category,
            "title": title,
            "source": source_name,
            "eventKey": f"{dt:%Y-%m-%d}|{dt:%H:%M}|{title}"
        })
    dedup = {e["eventKey"]: e for e in events}
    return sorted(dedup.values(), key=lambda e: e["dateTime"])

def fetch():
    diagnostics = []
    for fmt, url in ROUTES:
        for attempt in range(2):
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                diagnostics.append({"route": fmt, "url": url, "attempt": attempt+1, "http": r.status_code, "bytes": len(r.content)})
                if r.status_code == 200:
                    events = normalize(PARSERS[fmt](r.text), f"FairEconomy-{fmt.upper()}")
                    if events:
                        return events, diagnostics, fmt
                if r.status_code == 429:
                    retry = int(r.headers.get("Retry-After","0") or 0)
                    if 0 < retry <= 30:
                        time.sleep(retry)
            except Exception as exc:
                diagnostics.append({"route": fmt, "url": url, "attempt": attempt+1, "error": str(exc)[:160]})
    raise RuntimeError(json.dumps(diagnostics))

def main():
    now = datetime.now(TZ)
    start, end = week_bounds(now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    try:
        events, diagnostics, route = fetch()
        in_week = [e for e in events if start <= dtparser.parse(e["dateTime"]).astimezone(TZ) <= end]
        if not in_week:
            raise RuntimeError("Source returned no selected events inside governed week")
        payload = {
            "schemaVersion": "2.0",
            "status": "CURRENT",
            "generatedAt": now.isoformat(),
            "weekStart": start.date().isoformat(),
            "weekEnd": end.date().isoformat(),
            "source": f"Fair Economy via {route.upper()}",
            "diagnostics": diagnostics,
            "events": in_week
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        OUT.write_text(text, encoding="utf-8")
        (ARCHIVE / f"{start.date().isoformat()}.json").write_text(text, encoding="utf-8")
    except Exception as exc:
        if OUT.exists():
            old = json.loads(OUT.read_text(encoding="utf-8"))
            old["status"] = "RETAINED"
            old["lastAttemptAt"] = now.isoformat()
            old["lastAttemptError"] = str(exc)[:2000]
            OUT.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return
        raise

if __name__ == "__main__":
    main()
