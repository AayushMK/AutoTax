"""Nepal Rastra Bank forex API client.

API: GET https://www.nrb.org.np/api/forex/v1/rates?from=YYYY-MM-DD&to=YYYY-MM-DD&page=N&per_page=100
Response: data.payload[] = {date, published_on, rates: [{currency: {iso3, unit}, buy, sell}]}
"""

from __future__ import annotations

from datetime import date

import httpx

from app.engine.fx import FxRate
from app.engine.money import D

NRB_URL = "https://www.nrb.org.np/api/forex/v1/rates"


class NrbError(RuntimeError):
    pass


def parse_payload(payload: list[dict], currencies: set[str] | None = None) -> list[FxRate]:
    out: list[FxRate] = []
    for day in payload:
        on = date.fromisoformat(day["date"])
        for r in day["rates"]:
            iso = r["currency"]["iso3"].upper()
            if currencies and iso not in currencies:
                continue
            out.append(FxRate(currency=iso, on=on, buy=D(r["buy"]), sell=D(r["sell"]), unit=int(r["currency"]["unit"])))
    return out


def fetch_rates(
    start: date,
    end: date,
    currencies: set[str] | None = None,
    client: httpx.Client | None = None,
) -> list[FxRate]:
    """Fetch all published rates between start and end (inclusive), following pagination."""
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        rates: list[FxRate] = []
        page = 1
        while True:
            resp = client.get(
                NRB_URL,
                params={"from": start.isoformat(), "to": end.isoformat(), "page": page, "per_page": 100},
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status", {}).get("code") != 200:
                raise NrbError(f"NRB API error: {body.get('errors') or body.get('status')}")
            rates.extend(parse_payload(body["data"]["payload"], currencies))
            pages = (body.get("pagination") or {}).get("pages") or 1
            if page >= pages:
                return rates
            page += 1
    finally:
        if own:
            client.close()
