#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relances_sync.py — Remonte les réponses & non-remises OVH vers Notion « Suivi des campagnes ».

Ce que fait le script, à chaque exécution :
  1. Se connecte en IMAP à une ou plusieurs boîtes OVH (les expéditeurs de tes campagnes).
  2. Lit les messages entrants récents (depuis LOOKBACK_DAYS jours).
  3. Classe chaque message :
        - bounce_hard   : non-remise DÉFINITIVE (boîte/domaine inexistant, 5.x.x)  -> à abandonner
        - bounce_soft   : non-remise TEMPORAIRE (boîte pleine, 4.x.x, greylisting) -> à retenter
        - absence       : auto-répondeur congés/absence (avec date de retour si trouvée)
        - desabonnement : demande explicite de retrait
        - refus         : réponse négative claire
        - reponse       : vraie réponse humaine (par défaut)
  4. Matche par email (expéditeur pour les réponses, destinataire échoué pour les bounces).
  5. Écrit dans la base Notion « Suivi des campagnes », SANS doublon
     (clé = email + date du message ; marqueur Message-ID stocké dans « commentaires »).
  6. Exporte un fichier Excel « undelivered_triage.xlsx » : à retenter vs à abandonner + raison.

Sécurité : aucun mot de passe n'est écrit ni affiché. Tout passe par variables d'environnement.

Variables d'environnement attendues
-----------------------------------
  NOTION_TOKEN            (obligatoire) token d'intégration interne Notion (secret_...)
  NOTION_DATABASE_ID      (obligatoire) id de « Suivi des campagnes »
                          défaut : 2e2e5a4bb1034c999c8ab30afc356c81
  OVH_ACCOUNTS            (recommandé) JSON : [{"user":"nicolasvial@equationsie.fr","password":"..."}, ...]
      — ou, pour une seule boîte —
  OVH_MAIL_USER / OVH_MAIL_PASS

  IMAP_HOST              défaut ssl0.ovh.net
  IMAP_PORT             défaut 993
  LOOKBACK_DAYS         défaut 30 (nombre de jours à balayer)
  DRY_RUN              "1" = n'écrit RIEN dans Notion, se contente de logguer (test)
  EXCEL_OUT           défaut undelivered_triage.xlsx

Dépendances : requests, openpyxl  (voir requirements.txt)
"""

import os
import re
import ssl
import sys
import json
import email
import imaplib
import datetime as dt
import unicodedata
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

import requests

# openpyxl est optionnel : si absent, on écrit un CSV à la place.
try:
    from openpyxl import Workbook
    HAVE_XLSX = True
except Exception:
    HAVE_XLSX = False

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
IMAP_HOST = os.environ.get("IMAP_HOST", "ssl0.ovh.net")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
# FORCE_RECLASSIFY=1 : ré-analyse et ré-écrit même les messages déjà traités
# (utile après une amélioration du classifieur, pour corriger les anciens tags).
FORCE = os.environ.get("FORCE_RECLASSIFY", "0") == "1"
EXCEL_OUT = os.environ.get("EXCEL_OUT", "undelivered_triage.xlsx")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "2e2e5a4bb1034c999c8ab30afc356c81")
NOTION_VERSION = "2022-06-28"

# Noms EXACTS des propriétés dans « Suivi des campagnes »
P_DEST = "Destinataire"      # title  (email du prospect)
P_CAMP = "Campagne"          # text
P_REPONDU = "Répondu"        # checkbox
P_DATE_REP = "Date réponse"  # date
P_STATUT = "Statut"          # select
P_HARD = "Hard bounce"       # checkbox
P_COMMENT = "commentaires"   # text
P_EXPED = "Expéditeur"       # text
P_TYPE = "Type de réponse"   # select (nouvelle colonne)

# Valeurs de l'option Statut (doivent exister dans la base)
STATUT_REPONDU = "Répondu"
STATUT_BOUNCE = "Bounce"
STATUT_SOFT = "Soft bounce"
STATUT_HARD = "Hard bounce"

# --------------------------------------------------------------------------- #
# Petites aides
# --------------------------------------------------------------------------- #
def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def decode_str(raw):
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")


def body_text(msg):
    """Concatène le texte brut d'un message (parties text/plain, sinon text/html nettoyé)."""
    chunks = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                chunks.append(_payload(part))
            elif ctype == "message/delivery-status":
                chunks.append(_payload(part))
            elif ctype == "message/rfc822":
                # message original renvoyé dans un bounce : on garde les en-têtes
                chunks.append(_payload(part))
        if not chunks:  # pas de plain : on prend le html grossièrement détagué
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    chunks.append(re.sub("<[^>]+>", " ", _payload(part)))
    else:
        chunks.append(_payload(msg))
    return "\n".join(c for c in chunks if c)


def _payload(part):
    try:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace")
    except Exception:
        return ""


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def first_email(text):
    m = EMAIL_RE.search(text or "")
    return m.group(0).lower() if m else ""


def _norm(s):
    """minuscule + sans accents/cédilles, pour comparer les mots-clés de façon robuste."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _has(words, text_n):
    """True si un des mots-clés (normalisé) est présent dans le texte déjà normalisé."""
    return any(_norm(w) in text_n for w in words)


def _other_email(text, exclude):
    """Premier email du corps différent de l'expéditeur et non 'no-reply' (adresse alternative probable)."""
    exclude = (exclude or "").lower()
    for m in EMAIL_RE.finditer(text or ""):
        e = m.group(0).lower()
        if e != exclude and not any(h in e for h in NOREPLY_HINTS):
            return e
    return ""


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
DAEMON_HINTS = ("mailer-daemon", "postmaster", "mail delivery", "maildaemon")
BOUNCE_SUBJECTS = (
    "undelivered mail", "delivery status notification", "mail delivery failed",
    "returned to sender", "delivery failure", "failure notice", "avis de non-remise",
    "échec de remise", "message non remis", "n'a pas pu être remis",
)
OOO_HEADERS = ("auto-submitted", "x-autoreply", "x-autorespond", "x-auto-response-suppress")
OOO_WORDS = (
    "absent", "absence", "congé", "congés", "en vacances", "vacances",
    "out of office", "réponse automatique", "reponse automatique", "de retour le",
    "je serai de retour", "actuellement absent", "away from", "off until",
)
UNSUB_WORDS = (
    "désabonn", "desabonn", "unsubscribe", "se désinscrire", "desinscrire",
    "ne plus recevoir", "retirez-moi", "retirez moi", "me retirer", "stop",
)
REFUS_WORDS = (
    "pas intéressé", "pas interesse", "ne suis pas intéressé", "sans suite",
    "pas concerné", "pas concerne", "non merci", "not interested", "no interest",
    "ne donnerai pas suite", "ne souhaite pas",
)
SOCIETE_WORDS = (
    "ne fait plus partie", "ne fais plus partie", "ne fait plus parti",
    "no longer with", "no longer works", "is no longer", "has left the", "left the company",
    "quitté l'entreprise", "quitte l'entreprise", "quitté la société", "quitté la societe",
    "quitté le cabinet", "quitté le groupe", "quitté cost", "quitté ses fonctions",
    "quitté nos effectifs", "ai quitté le cabinet",
    "changé de cabinet", "changé de société", "changé d'entreprise", "changé de poste",
    "n'est plus dans l'entreprise", "n'est plus dans la société", "n'est plus en charge",
    "ne travaille plus", "plus en poste", "parti de la société", "a quitté nos",
    # départs à la retraite (le contact ne reviendra pas)
    "retraite", "en retraite", "à la retraite", "depart en retraite", "retired", "retiring",
    "fait valoir ses droits", "fait valoir mes droits",
    # mutations / nouveau poste ailleurs
    "muté", "mutation", "a rejoint", "nouveau poste", "rejoint une nouvelle",
)


def _is_departure(body_n):
    """Vrai départ de la société (≠ simple absence), sur texte déjà normalisé (sans accents)."""
    if _has(SOCIETE_WORDS, body_n):
        return True
    # « quitté … » + passation de contact, SAUF si c'est manifestement des vacances.
    if ("quitt" in body_n
            and _has(("contacter", "joindre", "reprend", "remplac", "successeur",
                      "desormais", "dorenavant", "prendra le relais", "a repris",
                      "transfer", "transmis", "nouvelle adresse", "coordonnees suivantes"), body_n)
            and not _has(("vacances", "conge", "de retour le", "back on", "jusqu'au"), body_n)):
        return True
    return False
ADRESSE_WORDS = (
    "nouvelle adresse", "nouvel email", "nouvel e-mail", "nouvelle adresse mail",
    "nouvelle adresse e-mail", "nouvelle adresse électronique", "mon nouveau mail",
    "me joindre à", "me joindre a", "me contacter à", "me contacter a", "please use",
    "reach me at", "désormais à", "desormais a", "adresse a changé", "adresse a change",
    "à privilégier", "a privilegier",
)
NOREPLY_HINTS = ("no-reply", "noreply", "ne-pas-repondre", "nepasrepondre", "mailer-daemon", "postmaster")
RETURN_DATE_RE = re.compile(
    r"(?:jusqu'au|de retour le|retour le|back on|until|from)\s+"
    r"(\d{1,2}(?:er)?[\s/\-]*"
    r"(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|décembre|decembre|"
    r"janv|févr|fevr|avr|juil|sept|oct|nov|déc|dec|\d{1,2})"
    r"[a-zàâéèêëîïôûùç.]*[\s/\-]*\d{0,4})",
    re.IGNORECASE,
)


def classify(msg, from_email, subject, body):
    """Retourne (type, failed_email_or_None, raison, extrait, return_date_or_None)."""
    subj_l = (subject or "").lower()
    body_l = (body or "").lower()
    from_l = (from_email or "").lower()
    subj_n = _norm(subject)      # sans accents/cédilles
    body_n = _norm(body)

    # ---- 1. NON-REMISE (bounce) ----
    is_report = False
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "message/delivery-status":
            is_report = True
            break
    looks_daemon = any(h in from_l for h in DAEMON_HINTS)
    looks_bounce_subj = any(s in subj_l for s in BOUNCE_SUBJECTS)
    if is_report or looks_daemon or looks_bounce_subj:
        failed = _failed_recipient(msg, body)
        code = _smtp_code(body)
        reason = _bounce_reason(body)
        hard = code.startswith("5") if code else _looks_permanent(body)
        btype = "bounce_hard" if hard else "bounce_soft"
        return btype, failed, reason or ("permanente" if hard else "temporaire"), _extract(body), None

    # ---- 2. CHANGEMENT DE SOCIÉTÉ / DÉPART (prioritaire : un départ est souvent
    #         un auto-répondeur, mais ce n'est PAS une simple absence de vacances) ----
    if _is_departure(body_n):
        new = _other_email(body, from_email)
        reason = f"départ — contact : {new}" if new else "changement de société / départ"
        return "societe", None, reason, _extract(body), None

    # ---- 3. AUTO-RÉPONDEUR ABSENCE ----
    header_ooo = any(msg.get(h) for h in OOO_HEADERS)
    if header_ooo or _has(OOO_WORDS, subj_n) or _has(OOO_WORDS, body_n):
        m = RETURN_DATE_RE.search(body or "")
        rdate = m.group(1) if m else None
        return "absence", None, "auto-répondeur d'absence", _extract(body), rdate

    # ---- 4. NOUVELLE ADRESSE MAIL ----
    if _has(ADRESSE_WORDS, body_n):
        new = _other_email(body, from_email)
        reason = f"nouvelle adresse : {new}" if new else "changement d'adresse mail"
        return "adresse_mail", None, reason, _extract(body), None

    # ---- 5. DÉSABONNEMENT ----
    if _has(UNSUB_WORDS, body_n) and "je suis absent" not in body_n:
        return "desabonnement", None, "demande de retrait", _extract(body), None

    # ---- 6. REFUS ----
    if _has(REFUS_WORDS, body_n):
        return "refus", None, "réponse négative", _extract(body), None

    # ---- 7. VRAIE RÉPONSE CLIENT ----
    return "reponse", None, "réponse humaine", _extract(body), None


def _failed_recipient(msg, body):
    xfr = msg.get("X-Failed-Recipients")
    if xfr:
        return first_email(xfr)
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "message/delivery-status":
            ds = _payload(part)
            m = re.search(r"Final-Recipient:\s*[^;]+;\s*(.+)", ds, re.IGNORECASE)
            if m:
                return first_email(m.group(1))
            m = re.search(r"Original-Recipient:\s*[^;]+;\s*(.+)", ds, re.IGNORECASE)
            if m:
                return first_email(m.group(1))
    # dernier recours : premier email plausible dans le corps
    return first_email(body)


def _smtp_code(body):
    m = re.search(r"\b([45]\d\d)\b(?:[ \-]\d\.\d\.\d)?", body or "")
    if m:
        return m.group(1)
    m = re.search(r"\bstatus:\s*([45])\.\d+\.\d+", body or "", re.IGNORECASE)
    return (m.group(1) + "00") if m else ""


def _looks_permanent(body):
    b = (body or "").lower()
    perm = ("user unknown", "no such user", "does not exist", "utilisateur inconnu",
            "adresse n'existe", "mailbox unavailable", "domain not found",
            "host or domain name not found", "aucune boîte", "recipient rejected",
            "550")
    return any(p in b for p in perm)


def _bounce_reason(body):
    b = (body or "").lower()
    table = [
        ("user unknown", "destinataire inconnu"),
        ("no such user", "destinataire inconnu"),
        ("does not exist", "adresse inexistante"),
        ("utilisateur inconnu", "destinataire inconnu"),
        ("mailbox full", "boîte pleine"),
        ("quota", "quota dépassé"),
        ("over quota", "quota dépassé"),
        ("domain not found", "domaine introuvable"),
        ("host or domain name not found", "domaine introuvable"),
        ("greylist", "greylisting (temporaire)"),
        ("timed out", "délai dépassé"),
        ("spam", "rejeté (spam)"),
        ("blocked", "expéditeur bloqué"),
    ]
    for k, v in table:
        if k in b:
            return v
    return ""


def _extract(body, n=280):
    """Extrait lisible : premières lignes utiles, sans citations ni signatures lourdes."""
    if not body:
        return ""
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s or s.startswith(">") or s.startswith("--") or s.startswith("__"):
            continue
        if s.lower().startswith(("le ", "on ", "de :", "envoyé", "à :", "objet :")):
            continue
        lines.append(s)
        if sum(len(x) for x in lines) > n:
            break
    return " ".join(lines)[:n].strip()


# --------------------------------------------------------------------------- #
# Notion
# --------------------------------------------------------------------------- #
class Notion:
    def __init__(self, token, database_id):
        self.h = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        self.db = database_id

    def find_page(self, email_addr):
        """Cherche une page dont le titre Destinataire contient l'email. Renvoie (page_id, props) ou (None, None)."""
        url = f"https://api.notion.com/v1/databases/{self.db}/query"
        payload = {
            "filter": {"property": P_DEST, "title": {"contains": email_addr}},
            "page_size": 5,
        }
        r = requests.post(url, headers=self.h, data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        for res in r.json().get("results", []):
            title = _notion_plain(res["properties"].get(P_DEST, {}))
            if email_addr.lower() in title.lower():
                return res["id"], res["properties"]
        return None, None

    def already_done(self, props, marker):
        return marker in _notion_plain(props.get(P_COMMENT, {}))

    def update(self, page_id, props, *, statut, type_reponse, date_iso, reponduish, comment_add):
        existing = _notion_plain(props.get(P_COMMENT, {}))
        mk = re.search(r"⟨[^⟩]+⟩", comment_add)
        marker = mk.group(0) if mk else None
        if existing and marker and marker in existing:
            new_comment = comment_add            # re-run : on remplace pour éviter les doublons
        elif existing:
            new_comment = (existing + " · " + comment_add).strip(" ·")
        else:
            new_comment = comment_add
        body = {"properties": {
            P_STATUT: {"select": {"name": statut}},
            P_TYPE: {"select": {"name": type_reponse}},
            P_COMMENT: {"rich_text": [{"text": {"content": new_comment[:1900]}}]},
        }}
        if date_iso:
            body["properties"][P_DATE_REP] = {"date": {"start": date_iso}}
        if reponduish:
            body["properties"][P_REPONDU] = {"checkbox": True}
        if statut == STATUT_HARD:
            body["properties"][P_HARD] = {"checkbox": True}
        url = f"https://api.notion.com/v1/pages/{page_id}"
        r = requests.patch(url, headers=self.h, data=json.dumps(body), timeout=30)
        r.raise_for_status()


def _notion_plain(prop):
    if not prop:
        return ""
    t = prop.get("type")
    arr = prop.get(t) or []
    if isinstance(arr, list):
        return "".join(x.get("plain_text", "") for x in arr)
    return ""


# --------------------------------------------------------------------------- #
# IMAP
# --------------------------------------------------------------------------- #
def imap_accounts():
    """Trois formats acceptés, du plus simple au plus complet.
    1) OVH_USER_1 / OVH_PASS_1, OVH_USER_2 / OVH_PASS_2 …  (recommandé, incassable)
    2) OVH_MAIL_USER / OVH_MAIL_PASS                       (un seul compte)
    3) OVH_ACCOUNTS = JSON [{"user":..,"password":..}, …]  (tolérant sur le nom de clé)
    """
    accts = []
    # --- 0) variables AUTOLOGIN_n_EMAIL / AUTOLOGIN_n_PASSWORD (mêmes que l'app relances-chauffe) ---
    i = 1
    while i <= 20:
        u = os.environ.get(f"AUTOLOGIN_{i}_EMAIL")
        p = os.environ.get(f"AUTOLOGIN_{i}_PASSWORD")
        if u and p:
            accts.append({"user": u.strip(), "password": p.strip()})
        i += 1
    if accts:
        return accts
    # --- 1) paires numérotées OVH_USER_n / OVH_PASS_n ---
    i = 1
    while True:
        u = os.environ.get(f"OVH_USER_{i}")
        p = os.environ.get(f"OVH_PASS_{i}")
        if not u and not p:
            break
        if u and p:
            accts.append({"user": u.strip(), "password": p})
        else:
            log(f"⚠️ OVH_USER_{i}/OVH_PASS_{i} incomplet — compte ignoré")
        i += 1
    if accts:
        return accts
    # --- 2) compte unique ---
    u, p = os.environ.get("OVH_MAIL_USER"), os.environ.get("OVH_MAIL_PASS")
    if u and p:
        return [{"user": u.strip(), "password": p}]
    # --- 3) JSON (tolérant : password / pass / mdp / pwd) ---
    raw = os.environ.get("OVH_ACCOUNTS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except Exception as e:
            log(f"⛔ OVH_ACCOUNTS n'est pas un JSON valide : {e}")
            return accts
        for d in (data or []):
            user = d.get("user") or d.get("email") or d.get("login")
            pwd = d.get("password") or d.get("pass") or d.get("mdp") or d.get("pwd")
            if user and pwd:
                accts.append({"user": str(user).strip(), "password": str(pwd)})
            else:
                log(f"⚠️ compte OVH sans user/password exploitable : {user or '?'}")
    return accts


def fetch_recent(acct):
    """Renvoie une liste d'objets email.message pour les messages depuis LOOKBACK_DAYS."""
    ctx = ssl.create_default_context()
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx)
    M.login(acct["user"], acct["password"])
    out = []
    since = (dt.date.today() - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    for box in ("INBOX",):
        try:
            M.select(box, readonly=True)
        except Exception:
            continue
        typ, data = M.search(None, f'(SINCE {since})')
        if typ != "OK":
            continue
        ids = data[0].split()
        for i in ids:
            typ, msgdata = M.fetch(i, "(RFC822)")
            if typ != "OK" or not msgdata or not msgdata[0]:
                continue
            out.append(email.message_from_bytes(msgdata[0][1]))
    try:
        M.logout()
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #
STATUT_MAP = {
    "reponse": STATUT_REPONDU,
    "absence": STATUT_REPONDU,   # répondu (auto) — voir commentaire ABSENCE
    "refus": STATUT_REPONDU,
    "desabonnement": STATUT_REPONDU,
    "adresse_mail": STATUT_REPONDU,
    "societe": STATUT_REPONDU,
    "autre": STATUT_REPONDU,
    "bounce_soft": STATUT_SOFT,
    "bounce_hard": STATUT_HARD,
}
# Type interne -> valeur EXACTE de la colonne Notion « Type de réponse »
TYPE_REPONSE = {
    "reponse": "Réponse client",
    "absence": "Absence / vacances",
    "refus": "Refus",
    "desabonnement": "Désabonnement",
    "adresse_mail": "Nouvelle adresse mail",
    "societe": "Changement de société",
    "autre": "Autre",
    "bounce_soft": "Non-remise",
    "bounce_hard": "Non-remise",
}
LABEL = {
    "reponse": "RÉPONSE CLIENT",
    "absence": "ABSENCE",
    "refus": "REFUS",
    "desabonnement": "DÉSABONNEMENT",
    "adresse_mail": "NOUVELLE ADRESSE",
    "societe": "CHANGEMENT SOCIÉTÉ",
    "autre": "AUTRE",
    "bounce_soft": "SOFT BOUNCE",
    "bounce_hard": "HARD BOUNCE",
}


def main():
    if not NOTION_TOKEN:
        log("⛔ NOTION_TOKEN manquant."); sys.exit(2)
    accounts = imap_accounts()
    if not accounts:
        log("⛔ Aucun compte OVH (définis OVH_ACCOUNTS ou OVH_MAIL_USER/PASS)."); sys.exit(2)

    notion = Notion(NOTION_TOKEN, NOTION_DATABASE_ID)
    undelivered = []          # pour l'Excel de tri
    counts = {k: 0 for k in LABEL}
    matched = unmatched = skipped = 0

    for acct in accounts:
        log(f"📥 Connexion IMAP {acct['user']} …")
        try:
            msgs = fetch_recent(acct)
        except Exception as e:
            log(f"   ⚠️ échec {acct['user']}: {e}"); continue
        log(f"   {len(msgs)} message(s) depuis {LOOKBACK_DAYS} j")

        for msg in msgs:
            subject = decode_str(msg.get("Subject", ""))
            from_email = parseaddr(msg.get("From", ""))[1].lower()
            body = body_text(msg)
            msg_id = (msg.get("Message-ID") or "")[:60]
            try:
                mdate = parsedate_to_datetime(msg.get("Date"))
                date_iso = mdate.date().isoformat()
            except Exception:
                date_iso = dt.date.today().isoformat()

            btype, failed, reason, extrait, rdate = classify(msg, from_email, subject, body)
            counts[btype] += 1

            # email du prospect concerné
            target = failed if btype.startswith("bounce") else from_email
            if not target:
                unmatched += 1; continue

            # note pour l'Excel des non-remises
            if btype.startswith("bounce"):
                undelivered.append({
                    "email": target,
                    "type": "hard" if btype == "bounce_hard" else "soft",
                    "raison": reason,
                    "verdict": "à abandonner" if btype == "bounce_hard" else "à retenter",
                    "alt": suggest_alt(target, reason),
                    "boite": acct["user"],
                    "date": date_iso,
                })

            marker = f"msg:{msg_id[-12:]}" if msg_id else f"{btype}:{date_iso}"
            comment = f"[{LABEL[btype]}] {extrait}".strip()
            if rdate:
                comment = f"[ABSENCE→ retour {rdate}] {extrait}".strip()
            comment = f"{comment}  ⟨{marker}⟩"

            if DRY_RUN:
                log(f"   (dry) {btype:12s} {target}  {reason}")
                continue

            try:
                page_id, props = notion.find_page(target)
            except Exception as e:
                log(f"   ⚠️ Notion query {target}: {e}"); continue
            if not page_id:
                unmatched += 1
                log(f"   ? non trouvé dans Notion : {target} ({btype})")
                continue
            if not FORCE and notion.already_done(props, marker):
                skipped += 1
                continue
            try:
                notion.update(
                    page_id, props,
                    statut=STATUT_MAP[btype],
                    type_reponse=TYPE_REPONSE[btype],
                    date_iso=date_iso,
                    reponduish=not btype.startswith("bounce"),
                    comment_add=comment,
                )
                matched += 1
            except Exception as e:
                log(f"   ⚠️ Notion update {target}: {e}")

    # ---- Excel de tri des non-remises ----
    if undelivered:
        write_triage(undelivered, EXCEL_OUT)
        log(f"📄 {len(undelivered)} non-remise(s) → {EXCEL_OUT}")

    log("──────── RÉCAP ────────")
    for k, v in counts.items():
        log(f"  {LABEL[k]:14s} : {v}")
    log(f"  Notion écrits   : {matched}   déjà à jour : {skipped}   non matchés : {unmatched}")
    if DRY_RUN:
        log("  (DRY_RUN : rien n'a été écrit dans Notion)")


def suggest_alt(email_addr, reason):
    """Heuristique simple d'adresse alternative plausible (à valider à la main)."""
    if "domaine" in (reason or ""):
        # domaine mort : on ne propose rien d'automatique fiable
        return "vérifier domaine actuel de la société"
    try:
        local, domain = email_addr.split("@", 1)
    except ValueError:
        return ""
    # variantes de format courantes si "destinataire inconnu"
    if "inconnu" in (reason or "") or "inexistante" in (reason or ""):
        parts = re.split(r"[._\-]", local)
        if len(parts) >= 2:
            p, n = parts[0], parts[-1]
            return f"essayer {p}.{n}@{domain} / {p[0]}{n}@{domain} / {p}@{domain}"
        return f"essayer prenom.nom@{domain}"
    return ""


def write_triage(rows, path):
    rows.sort(key=lambda r: (r["verdict"], r["email"]))
    headers = ["email", "type", "verdict", "raison", "adresse alternative à tester", "boîte", "date"]
    if HAVE_XLSX:
        wb = Workbook(); ws = wb.active; ws.title = "Non-remises"
        ws.append(headers)
        for r in rows:
            ws.append([r["email"], r["type"], r["verdict"], r["raison"], r["alt"], r["boite"], r["date"]])
        for col, w in zip("ABCDEFG", (34, 8, 14, 26, 42, 28, 12)):
            ws.column_dimensions[col].width = w
        wb.save(path)
    else:
        import csv
        with open(path.replace(".xlsx", ".csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(headers)
            for r in rows:
                w.writerow([r["email"], r["type"], r["verdict"], r["raison"], r["alt"], r["boite"], r["date"]])


if __name__ == "__main__":
    main()
