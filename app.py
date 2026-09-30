"""
Carte de prospection terrain — Equation-sie
Lit la base Notion « Prospection terrain » à chaque ouverture (cache 60 s),
géocode les adresses via la BAN et affiche une carte par négociateur.
"""
import os
import re
import json
import time
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

import requests
from flask import Flask, jsonify, render_template, request, Response

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID", "c70e0416a7d64dd990011f222bf5a4e7")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
NOTION_TTL = int(os.environ.get("NOTION_TTL", "60"))  # secondes
FRESH_MONTHS = int(os.environ.get("FRESH_MONTHS", "2"))  # vert si vu depuis moins de N mois
SECTEURS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secteurs.json")
GEOCACHE_FILE = os.environ.get("GEOCACHE_FILE", "/tmp/geocache.json")

app = Flask(__name__)

# ---------------------------------------------------------------- auth ----
def protected(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if APP_PASSWORD:
            auth = request.authorization
            if not auth or auth.password != APP_PASSWORD:
                return Response("Accès réservé", 401,
                                {"WWW-Authenticate": 'Basic realm="Carte prospection"'})
        return f(*a, **kw)
    return wrapper

# -------------------------------------------------------------- notion ----
_notion_cache = {"at": 0, "rows": None}
_notion_lock = threading.Lock()


def _txt(prop):
    if not prop:
        return ""
    t = prop.get("type")
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in prop.get(t) or []).strip()
    if t == "select":
        return (prop.get("select") or {}).get("name", "") or ""
    if t == "date":
        return ((prop.get("date") or {}).get("start") or "")[:10]
    if t == "unique_id":
        u = prop.get("unique_id") or {}
        return f"{u.get('prefix') or 'PR'}-{u.get('number')}" if u.get("number") else ""
    return ""


def fetch_notion(force=False):
    with _notion_lock:
        if not force and _notion_cache["rows"] is not None and time.time() - _notion_cache["at"] < NOTION_TTL:
            return _notion_cache["rows"]
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        rows, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            r = requests.post(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
                              headers=headers, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            for p in data["results"]:
                pr = p["properties"]
                rows.append({
                    "ref": _txt(pr.get("Réf")),
                    "societe": _txt(pr.get("Société")) or "(sans nom)",
                    "adresse": _txt(pr.get("Adresse")),
                    "etage": _txt(pr.get("Étage")),
                    "nego": _txt(pr.get("Négo")) or "Non renseigné",
                    "date": _txt(pr.get("Date de visite")) or p.get("created_time", "")[:10],
                    "recherche": _txt(pr.get("En recherche")),
                    "type": _txt(pr.get("Type de société")),
                    "url": p.get("url", ""),
                })
            if not data.get("has_more"):
                break
            cursor = data["next_cursor"]
        _notion_cache.update(at=time.time(), rows=rows)
        return rows

# ------------------------------------------------------- normalisation ----
ORDINAUX = {"premier": 1, "deuxième": 2, "deuxieme": 2, "troisième": 3, "troisieme": 3,
            "quatrième": 4, "quatrieme": 4, "cinquième": 5, "cinquieme": 5, "sixième": 6,
            "septième": 7, "huitième": 8, "huitieme": 8, "neuvième": 9, "neuvieme": 9,
            "dixième": 10, "dixieme": 10, "onzième": 11, "douzième": 12}


def normalize(addr):
    """Nettoie une adresse saisie sur le terrain avant géocodage."""
    s = (addr or "").replace("’", "'").replace("`", "'").strip()
    s = re.sub(r"\briue\b", "rue", s, flags=re.I)
    s = re.sub(r"\bbd\b\.?", "boulevard", s, flags=re.I)
    s = re.sub(r"\bfbg\b\.?", "faubourg", s, flags=re.I)
    s = re.sub(r"^(\d+)\s*(?:bis|ter)\b", r"\1", s, flags=re.I)          # « 10 bis » → « 10 » (même immeuble)
    postcode = None
    # « 3e arrondissement », « deuxième arrondissement », « , 9e »
    m = re.search(r"(\d{1,2})\s*(?:e|er|ème|eme)\s*(?:arr\w*)?\s*(?:,|$)", s, flags=re.I)
    if m and "étage" not in s[m.end():m.end() + 8].lower():
        postcode = f"750{int(m.group(1)):02d}"
        s = s[:m.start()] + s[m.end():]
    for mot, n in ORDINAUX.items():
        m2 = re.search(rf"\b{mot}\s+arrondissement\b", s, flags=re.I)
        if m2:
            postcode = f"750{n:02d}"
            s = s[:m2.start()] + s[m2.end():]
    s = re.sub(r",?\s*\d+\s*(?:e|er|ème|eme)\s*étage", "", s, flags=re.I)   # « 4e étage »
    s = re.sub(r"\barrondissement\b", "", s, flags=re.I)
    # « 31-33 rue » / « 17 21 rue » → premier numéro
    s = re.sub(r"^(\d+)\s*(?:-|/|\s)\s*\d+\s+(?=[a-zA-Zéè])", r"\1 ", s)
    s = re.sub(r"\s*,\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    m3 = re.search(r"\b(75\d{3})\b", s)
    if m3:
        postcode = postcode or m3.group(1)
        s = s.replace(m3.group(1), "")
    s = re.sub(r"\bparis\b", "", s, flags=re.I).strip(" ,")
    q = f"{s} {postcode or ''} Paris".replace("  ", " ").strip()
    return q, postcode


# ----------------------------------------------------------- géocodage ----
_geocache = {}
_geo_lock = threading.Lock()
try:
    with open(GEOCACHE_FILE) as fh:
        _geocache = json.load(fh)
except Exception:
    pass


def _ban(q, postcode):
    params = {"q": q, "limit": 1, "lat": 48.8695, "lon": 2.3470}
    if postcode:
        params["postcode"] = postcode
    for url in ("https://api-adresse.data.gouv.fr/search/",
                "https://data.geopf.fr/geocodage/search"):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.ok:
                feats = r.json().get("features") or []
                return feats[0] if feats else None
        except Exception:
            continue
    raise ConnectionError("BAN injoignable")


def geocode(addr):
    key = (addr or "").strip().lower()
    if not key:
        return None
    if key in _geocache:
        return _geocache[key]
    q, postcode = normalize(addr)
    q_sans = re.sub(r"\b75\d{3}\b", "", q).replace("  ", " ")
    res = None
    tries = [(q_sans, None)] + ([(q, postcode)] if postcode else [])
    # 1) sans arrondissement (les négos se trompent souvent d'arrondissement)
    # 2) avec l'arrondissement saisi, en secours
    for qq, pc in tries:
        try:
            f = _ban(qq, pc)
        except ConnectionError:
            return None          # pas mis en cache : on retentera au prochain chargement
        if not f:
            continue
        p = f["properties"]
        precise = p.get("type") == "housenumber"
        ok = (p.get("postcode", "").startswith("75")
              and p.get("score", 0) >= (0.6 if precise else 0.65)
              and p.get("type") in ("housenumber", "street"))
        if ok:
            lon, lat = f["geometry"]["coordinates"]
            cand = {
                "key": p.get("id"),
                "label": p.get("label"),
                "street": p.get("street") or p.get("name"),
                "postcode": p.get("postcode"),
                "lat": lat, "lon": lon,
                "precise": precise,
                "score": round(p.get("score", 0), 2),
            }
            if precise:
                res = cand
                break
            res = res or cand
    with _geo_lock:
        _geocache[key] = res
        try:
            with open(GEOCACHE_FILE, "w") as fh:
                json.dump(_geocache, fh)
        except Exception:
            pass
    return res


# ---------------------------------------------------------------- routes --
@app.route("/")
@protected
def index():
    return render_template("index.html")


@app.route("/api/data")
@protected
def api_data():
    force = request.args.get("force") == "1"
    try:
        rows = fetch_notion(force=force)
    except requests.HTTPError as e:
        return jsonify(error=f"Notion : {e.response.status_code} — vérifier le token et le partage de la base"), 502
    todo = list({r["adresse"].strip().lower(): r["adresse"] for r in rows
                 if r["adresse"] and r["adresse"].strip().lower() not in _geocache}.values())
    if todo:
        with ThreadPoolExecutor(max_workers=5) as ex:
            list(ex.map(geocode, todo))
    buildings, records, unlocated = {}, [], []
    for r in rows:
        g = geocode(r["adresse"]) if r["adresse"] else None
        if not g:
            unlocated.append(r)
            continue
        buildings[g["key"]] = {k: g[k] for k in ("label", "street", "postcode", "lat", "lon", "precise")}
        records.append({**r, "b": g["key"]})
    try:
        with open(SECTEURS_FILE, encoding="utf-8") as fh:
            secteurs = json.load(fh)
    except Exception:
        secteurs = {}
    return jsonify(updated_at=int(_notion_cache["at"] * 1000),
                   secteurs=secteurs, fresh_months=FRESH_MONTHS,
                   records=records, buildings=buildings, unlocated=unlocated)


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
