#!/usr/bin/env python3
"""
Agartracker
=====================
Hämtar aktuellt antal ägare hos Avanza och Nordnet för flera aktier,
sparar historik per aktie i data/history_<key>.json, bygger om Excel-filen
och postar en samlad uppdatering till Discord via en webhook.

Körs normalt en gång per dag via GitHub Actions, men går fint att
köra manuellt lokalt också:

    pip install -r requirements.txt
    export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
    python track_owners.py

Felsökning av Nordnet-delen (om allaaktier.se ändrat struktur):

    python track_owners.py --debug-nordnet
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import requests

# ---------------------------------------------------------------------------
# Konfiguration: lista över aktier som trackas
# ---------------------------------------------------------------------------

STOCKS = [
    {"key": "ossdsign", "name": "OssDsign", "avanza_id": "962596", "allaaktier_slug": "ossdsign"},
    {"key": "smarteye", "name": "Smart Eye", "avanza_id": "710675", "allaaktier_slug": "smart-eye"},
    {"key": "integrum", "name": "Integrum", "avanza_id": "753680", "allaaktier_slug": "integrum"},
]

DATA_DIR = Path(__file__).parent / "data"


def retry(fn, *, attempts=3, delay=10, backoff=2, label=""):
    """Kör fn() upp till `attempts` gånger, med ökande fördröjning mellan
    försöken (t.ex. 10s, 20s, 40s), innan det slutgiltiga felet kastas
    vidare. Fångar tillfälliga nätverksstrul (timeouts, tillfälligt nere
    sajter) utan att hela scriptet behöver ge upp direkt.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < attempts:
                wait = delay * (backoff ** (attempt - 1))
                print(f"    Försök {attempt}/{attempts} för {label} misslyckades "
                      f"({e}) – försöker igen om {wait}s...")
                time.sleep(wait)
    raise last_exc

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# Valfritt: länk till din GitHub Pages-graf, t.ex.
# https://reddayio.github.io/Ossdsign-tracker/
CHART_URL = os.environ.get("CHART_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Avanza
# ---------------------------------------------------------------------------

def _find_key_recursive(obj, target_key: str):
    """Letar rekursivt efter en nyckel var som helst i en nästlad dict/list."""
    if isinstance(obj, dict):
        if target_key in obj:
            return obj[target_key]
        for value in obj.values():
            found = _find_key_recursive(value, target_key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_recursive(item, target_key)
            if found is not None:
                return found
    return None


def get_avanza_owners(orderbook_id: str) -> int:
    """Hämtar antal ägare hos Avanza via pyavanza (obemannat, publikt API)."""
    import pyavanza

    async def _fetch():
        async with aiohttp.ClientSession() as session:
            return await pyavanza.get_stock_async(session, orderbook_id)

    data = asyncio.run(_fetch())

    for candidate_key in ("numberOfOwners", "numberOfShareholders", "ownerCount"):
        value = _find_key_recursive(data, candidate_key)
        if value is not None:
            return int(value)

    raise RuntimeError(
        "Hittade inget ägarantal i Avanza-svaret, oavsett nästling. "
        f"Tillgängliga toppnivåfält: {list(data.keys())}."
    )


# ---------------------------------------------------------------------------
# Nordnet (via allaaktier.se)
# ---------------------------------------------------------------------------

def _extract_owner_count_from_html(html: str, label: str):
    """Hittar ett tal följt av 'st' i närheten av en textetikett, robust mot
    HTML-taggar och specialtecken (&nbsp;, &#xA0;) mellan etikett och tal
    (t.ex. <td>Ägare Nordnet</td><td>721&nbsp;st</td>).
    """
    idx = html.find(label)
    if idx == -1:
        return None

    window = html[idx:idx + 300]
    window = re.sub(r"<[^>]+>", " ", window)
    window = (
        window.replace("&nbsp;", " ")
        .replace("&#xA0;", " ")
        .replace("&#160;", " ")
        .replace("\u00a0", " ")
    )

    m = re.search(r"([\d][\d\s]{0,12})\s*st\b", window)
    if not m:
        return None
    number = re.sub(r"\s+", "", m.group(1))
    return int(number) if number.isdigit() else None


def get_nordnet_owners(allaaktier_slug: str, debug: bool = False) -> int:
    """Hämtar antal ägare hos Nordnet från allaaktier.se/<slug>."""
    url = f"https://allaaktier.se/{allaaktier_slug}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    if debug:
        for label in ("Ägare Nordnet", "Ägare Avanza"):
            idx = html.find(label)
            print(f"---- DEBUG ({allaaktier_slug}): kontext runt '{label}' ----")
            print(html[max(0, idx - 30):idx + 250] if idx != -1 else "Hittade inte texten alls.")
            print(f"---- Tolkat värde: {_extract_owner_count_from_html(html, label)} ----")

    count = _extract_owner_count_from_html(html, "Ägare Nordnet")
    if count is None:
        raise RuntimeError(
            f"Kunde inte hitta/tolka 'Ägare Nordnet ... st' på {url}. "
            "Sidan kan ha ändrat struktur."
        )
    return count


# ---------------------------------------------------------------------------
# Historik (en fil per aktie)
# ---------------------------------------------------------------------------

def history_file(key: str) -> Path:
    return DATA_DIR / f"history_{key}.json"


def load_history(key: str) -> list:
    f = history_file(key)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return []


def save_history(key: str, history: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history_file(key).write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

def post_to_discord(results: list, failed_stocks: list = None):
    """results: lista av dicts med name, avanza, nordnet, avanza_diff, nordnet_diff"""
    if not DISCORD_WEBHOOK_URL:
        print("Ingen DISCORD_WEBHOOK_URL satt – hoppar över Discord-postning.")
        return

    def fmt_diff(diff: int) -> str:
        if diff > 0:
            return f"(+{diff})"
        if diff < 0:
            return f"({diff})"
        return "(±0)"

    embeds = []

    if failed_stocks:
        embeds.append({
            "title": "⚠️ Missade aktier idag",
            "description": (
                f"Kunde inte hämta data för: **{', '.join(failed_stocks)}** "
                "(efter flera automatiska försök). Fångas förhoppningsvis upp "
                "av nästa körning."
            ),
            "color": 0xF39C12,
        })

    for r in results:
        total = r["avanza"] + r["nordnet"]
        total_diff = r["avanza_diff"] + r["nordnet_diff"]
        embed = {
            "title": f"📊 {r['name']}",
            "color": 0x2ECC71 if total_diff >= 0 else 0xE74C3C,
            "fields": [
                {"name": "Avanza", "value": f"**{r['avanza']}** {fmt_diff(r['avanza_diff'])}", "inline": True},
                {"name": "Nordnet", "value": f"**{r['nordnet']}** {fmt_diff(r['nordnet_diff'])}", "inline": True},
                {"name": "Totalt", "value": f"**{total}** {fmt_diff(total_diff)}", "inline": True},
            ],
        }
        if CHART_URL:
            embed["url"] = CHART_URL
        embeds.append(embed)

    if not embeds:
        print("Inga resultat och inga fel att rapportera – hoppar över Discord-postning.")
        return

    if CHART_URL:
        embeds[-1]["description"] = embeds[-1].get("description", "") + \
            f"\n\n[Se Agartracker-grafen]({CHART_URL})"

    embeds[-1]["footer"] = {"text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

    payload = {"content": "**Agartracker – daglig uppdatering**", "embeds": embeds[:10]}
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    r.raise_for_status()
    print("Postat till Discord.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    debug_nordnet = "--debug-nordnet" in sys.argv
    debug_avanza = "--debug-avanza" in sys.argv

    if debug_nordnet:
        for stock in STOCKS:
            get_nordnet_owners(stock["allaaktier_slug"], debug=True)
        return

    if debug_avanza:
        import pyavanza

        async def _fetch(orderbook_id):
            async with aiohttp.ClientSession() as session:
                return await pyavanza.get_stock_async(session, orderbook_id)

        for stock in STOCKS:
            print(f"---- {stock['name']} ----")
            data = asyncio.run(_fetch(stock["avanza_id"]))
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    results = []
    failed_stocks = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for stock in STOCKS:
        name = stock["name"]
        key = stock["key"]
        print(f"=== {name} ===")

        try:
            print("  Hämtar antal ägare hos Avanza...")
            avanza = retry(lambda: get_avanza_owners(stock["avanza_id"]),
                           label=f"{name} (Avanza)")
            print(f"    Avanza: {avanza}")

            print("  Hämtar antal ägare hos Nordnet (via allaaktier.se)...")
            nordnet = retry(lambda: get_nordnet_owners(stock["allaaktier_slug"]),
                            label=f"{name} (Nordnet)")
            print(f"    Nordnet: {nordnet}")
        except Exception as e:
            print(f"  VARNING: Gav upp med {name} efter flera försök: {e}")
            print(f"  Hoppar över {name} för idag, fortsätter med nästa aktie.")
            failed_stocks.append(name)
            continue

        history = load_history(key)
        prev = history[-1] if history else None
        avanza_diff = avanza - prev["avanza"] if prev else 0
        nordnet_diff = nordnet - prev["nordnet"] if prev else 0

        entry = {"date": today, "avanza": avanza, "nordnet": nordnet}
        if prev and prev["date"] == today:
            history[-1] = entry
        else:
            history.append(entry)
        save_history(key, history)
        print(f"  Historik sparad ({len(history)} poster totalt)")

        results.append({
            "name": name, "key": key, "avanza": avanza, "nordnet": nordnet,
            "avanza_diff": avanza_diff, "nordnet_diff": nordnet_diff,
        })

    if failed_stocks:
        print(f"\nSammanfattning: {len(failed_stocks)} aktie(r) missades idag: "
              f"{', '.join(failed_stocks)}")

    try:
        import build_excel
        build_excel.main()
    except Exception as e:
        print(f"Varning: kunde inte uppdatera Excel-filen: {e}")

    post_to_discord(results, failed_stocks)


if __name__ == "__main__":
    main()
