from datetime import datetime, timedelta

class AuthExpired(Exception):
    pass

def missing_range(latest_date, today, lookback_days=3, default_start="20251201"):
    """Return (start, end) YYYYMMDD range to pull. latest_date may be None."""
    if not latest_date:
        return (default_start, today)
    d = datetime.strptime(latest_date, "%Y%m%d") - timedelta(days=lookback_days - 1)
    return (d.strftime("%Y%m%d"), today)

def is_auth_expired(resp: dict) -> bool:
    """Heuristic: True if API response signals auth failure or empty data."""
    if not isinstance(resp, dict):
        return True
    code = str(resp.get("code", "")).lower()
    if code in ("401", "302") or "login" in code or resp.get("error"):
        return True
    data = resp.get("data", {})
    inner = data.get("data", data) if isinstance(data, dict) else data
    return not inner
