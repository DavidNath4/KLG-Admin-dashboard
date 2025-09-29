import re
from datetime import datetime

def kebab(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")

def parse_date(dstr: str):
    if not dstr:
        return None
    try:
        return datetime.strptime(dstr, "%Y-%m-%d")
    except Exception:
        return None

def human_bytes(n):
    if n is None: return "-"
    units = ["B","KB","MB","GB","TB","PB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.0f} {units[i]}" if i == 0 else f"{f:.2f} {units[i]}"
