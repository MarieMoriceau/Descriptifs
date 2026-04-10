import os
import uuid
import threading
import time
import io
import base64
import json
import re
import requests

from flask import Flask, request, jsonify, render_template_string
import pdfplumber
from pypdf import PdfReader
from PIL import Image
import anthropic

app = Flask(__name__)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
IMGBB_API_KEY       = "be39115664b38075a21de95d2ef95ba1"
GOOGLE_MAPS_API_KEY = "AIzaSyAGE65fo1453M-5CGe162Klk8NjS9K0hJA"
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
GAMMA_API_KEY       = "sk-gamma-KLU47Xtpm0WkqYoQ4DEh0qZSKOOjcZr4hBb0G79m9Rg"
GAMMA_THEME_ID      = "fo87qe3vn58hou1"
GAMMA_TEMPLATE_ID   = os.environ.get("GAMMA_TEMPLATE_ID", "")

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── JOB STORE ───────────────────────────────────────────────────────────────
jobs = {}

# ─── HTML TEMPLATE ───────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF → Gamma — Location | Equation SIE</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 2rem; }
.card { background: white; border-radius: 16px; padding: 2.5rem 2rem; width: 100%; max-width: 560px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); text-align: center; }
.dots { display: flex; justify-content: center; gap: 8px; margin-bottom: 1.5rem; }
.dot { width: 12px; height: 12px; border-radius: 50%; }
.dot-red { background: #e53935; }
.dot-dark { background: #37474f; }
.dot-blue { background: #90a4ae; }
h1 { font-size: 1.6rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.4rem; }
.subtitle { color: #6b7280; font-size: 0.95rem; margin-bottom: 2rem; }
.info-box { background: #f8f9fa; border-left: 4px solid #e53935; border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 2rem; text-align: left; }
.btn { width: 100%; padding: 0.9rem; background: #e53935; color: white; border: none; border-radius: 10px; font-size: 1rem; font-weight: 600; cursor: pointer; }
.btn:hover { background: #c62828; }
.btn:disabled { background: #9ca3af; cursor: not-allowed; }
.file-input { width: 100%; margin-bottom: 1rem; padding: 0.7rem; border: 2px dashed #e53935; border-radius: 8px; cursor: pointer; font-size: 0.9rem; color: #6b7280; }
#jobs-container { margin-top: 1.5rem; display: flex; flex-direction: column; gap: 0.75rem; }
.job-item { border: 1px solid #e5e7eb; border-radius: 10px; padding: 1rem; text-align: left; font-size: 0.88rem; }
.job-item.running { border-color: #93c5fd; background: #f0f4ff; }
.job-item.done { border-color: #86efac; background: #f0fdf4; }
.job-item.error { border-color: #fca5a5; background: #fff5f5; }
.job-title { font-weight: 600; margin-bottom: 0.4rem; color: #1a1a2e; }
.job-logs { font-size: 0.78rem; color: #6b7280; max-height: 100px; overflow-y: auto; margin-top: 0.4rem; font-family: monospace; background: rgba(0,0,0,0.03); padding: 0.4rem; border-radius: 4px; }
.gamma-link { display: inline-block; margin-top: 0.6rem; padding: 0.4rem 0.9rem; background: #16a34a; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
.status-badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 99px; font-size: 0.75rem; font-weight: 600; margin-left: 0.4rem; }
.badge-running { background: #dbeafe; color: #1d4ed8; }
.badge-done { background: #dcfce7; color: #15803d; }
.badge-error { background: #fee2e2; color: #dc2626; }
</style>
</head>
<body>
<div class="card">
  <div class="dots">
    <div class="dot dot-red"></div>
    <div class="dot dot-dark"></div>
    <div class="dot dot-blue"></div>
  </div>
  <h1>PDF → Gamma — Location</h1>
  <p class="subtitle">Equation SIE — Produits à la location</p>
  <div class="info-box">
    <strong>Convertir un ou plusieurs descriptifs de location</strong><br>
    <small>Sélectionnez un ou plusieurs PDF confrères — les jobs tournent en parallèle.</small>
  </div>
  <input type="file" id="pdf-input" class="file-input" multiple accept=".pdf">
  <button class="btn" id="upload-btn" onclick="uploadFiles()">🚀 Lancer la conversion</button>
  <div id="jobs-container"></div>
</div>
<script>
const polls = {};
function uploadFiles() {
  const input = document.getElementById('pdf-input');
  const btn = document.getElementById('upload-btn');
  if (!input.files.length) { alert('Sélectionnez au moins un PDF.'); return; }
  btn.disabled = true;
  btn.textContent = '⏳ Envoi en cours...';
  Array.from(input.files).forEach(file => {
    const formData = new FormData();
    formData.append('file', file);
    fetch('/upload', { method: 'POST', body: formData })
      .then(r => r.json())
      .then(data => {
        if (data.job_id) addJobCard(data.job_id, file.name);
        else alert('Erreur: ' + (data.error || 'inconnue'));
      })
      .catch(e => alert('Erreur réseau: ' + e));
  });
  setTimeout(() => { btn.disabled = false; btn.textContent = '🚀 Lancer la conversion'; }, 2000);
}
function addJobCard(jobId, filename) {
  const container = document.getElementById('jobs-container');
  const div = document.createElement('div');
  div.className = 'job-item running';
  div.id = 'job-' + jobId;
  div.innerHTML = `
    <div class="job-title">${filename} <span class="status-badge badge-running" id="badge-${jobId}">⏳ En cours</span></div>
    <div class="job-logs" id="logs-${jobId}">Démarrage...</div>
    <div id="link-${jobId}"></div>
  `;
  container.prepend(div);
  polls[jobId] = setInterval(() => pollJob(jobId), 3000);
}
function pollJob(jobId) {
  fetch('/status/' + jobId)
    .then(r => r.json())
    .then(data => {
      const card = document.getElementById('job-' + jobId);
      const badge = document.getElementById('badge-' + jobId);
      const logs = document.getElementById('logs-' + jobId);
      const linkDiv = document.getElementById('link-' + jobId);
      logs.textContent = (data.logs || []).join('\n');
      logs.scrollTop = logs.scrollHeight;
      if (data.status === 'done') {
        clearInterval(polls[jobId]);
        card.className = 'job-item done';
        badge.className = 'status-badge badge-done';
        badge.textContent = '✅ Terminé';
        if (data.gamma_url) linkDiv.innerHTML = `<a class="gamma-link" href="${data.gamma_url}" target="_blank">🎨 Ouvrir dans Gamma</a>`;
      } else if (data.status === 'error') {
        clearInterval(polls[jobId]);
        card.className = 'job-item error';
        badge.className = 'status-badge badge-error';
        badge.textContent = '❌ Erreur';
      }
    });
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier reçu"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".pdf"):
        return jsonify({"error": "Fichier PDF requis"}), 400
    job_id = str(uuid.uuid4())
    path = os.path.join(UPLOAD_FOLDER, f"{job_id}.pdf")
    f.save(path)
    jobs[job_id] = {"status": "running", "logs": ["📄 PDF reçu, démarrage..."], "gamma_url": None, "filename": f.filename}
    threading.Thread(target=run_job, args=(job_id, path), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job introuvable"}), 404
    return jsonify(job)


def log(job_id, msg):
    jobs[job_id]["logs"].append(msg)
    print(f"[{job_id[:8]}] {msg}")


def run_job(job_id, pdf_path):
    try:
        log(job_id, "📝 Extraction du texte (skip page 0)...")
        text = extract_text(pdf_path)

        log(job_id, "🤖 Analyse via Claude Haiku...")
        data = extract_data_with_claude(text)
        surface_info = data.get('surfaces', ['?'])[0] if data.get('surfaces') else '?'
        log(job_id, f"✅ {data.get('adresse', '?')} — {surface_info}")

        log(job_id, "🖼️  Extraction des photos PDF...")
        photos = extract_photos(pdf_path)
        log(job_id, f"✅ {len(photos)} photo(s) trouvée(s)")

        photo_urls = []
        for i, img_bytes in enumerate(photos[:6]):
            log(job_id, f"☁️  Upload photo {i+1}/{min(len(photos), 6)}...")
            url = upload_to_imgbb(img_bytes)
            if url:
                photo_urls.append(url)

        map_url = None
        adresse = data.get("adresse", "")
        cp = data.get("code_postal", "")
        if adresse and cp:
            log(job_id, "🗺️  Génération carte Google Maps...")
            map_url = get_google_map_url(adresse, cp)
            if map_url:
                log(job_id, "✅ Carte générée")
            else:
                log(job_id, "⚠️  Carte indisponible, on continue sans")

        log(job_id, "✍️  Construction du prompt Gamma...")
        gamma_title = build_gamma_title(data)
        gamma_prompt = build_gamma_prompt(data, photo_urls, map_url)

        log(job_id, "🎨 Appel API Gamma...")
        gamma_url = call_gamma_api(gamma_title, gamma_prompt)

        jobs[job_id]["gamma_url"] = gamma_url
        jobs[job_id]["status"] = "done"
        log(job_id, "🎉 Terminé !")

    except Exception as e:
        jobs[job_id]["status"] = "error"
        log(job_id, f"❌ Erreur: {str(e)}")
        import traceback
        log(job_id, traceback.format_exc()[:600])
    finally:
        try:
            os.remove(pdf_path)
        except Exception:
            pass


def extract_text(pdf_path):
    """Extrait le texte en skippant la page 0 (logo confrère)."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i == 0:
                continue
            t = page.extract_text()
            if t:
                pages.append(t)
    return "\n\n".join(pages)


def extract_data_with_claude(text):
    """Extraction structurée via Claude Haiku — ne retourne QUE ce qui est dans le texte."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Tu es un expert en immobilier d'entreprise. Extrais les données du descriptif suivant.
Retourne UNIQUEMENT un JSON valide, sans texte avant ni après, sans balises markdown.

RÈGLES ABSOLUES :
- N'invente AUCUNE donnée absente du texte source
- Si une info est absente, mets null (jamais une valeur inventée)
- Ne déduis pas, ne complètes pas : seulement ce qui est littéralement écrit
- Pas de plan, pas de carte si non mentionnés

Format attendu :
{{
  "adresse": null,
  "code_postal": null,
  "surfaces": [],
  "surfaces_detail": [],
  "loyer_annuel": null,
  "loyer_mensuel": null,
  "charges": null,
  "honoraires": null,
  "disponibilite": null,
  "transports": [],
  "prestations": [],
  "description": null,
  "confrere": null,
  "dpe": null,
  "regime_fiscal": null,
  "bail": null,
  "depot_garantie": null,
  "indexation": null,
  "taxe_bureaux": null,
  "type_bien": null
}}

Texte source :
{text[:6000]}"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"JSON invalide: {raw[:300]}")


def extract_photos(pdf_path):
    """
    Extraction images via pypdf uniquement (pas de rasterisation — évite crash 512Mo Render).
    Skip page 0. Filtre les petites images < 200px (logos/icônes).
    """
    photos = []
    reader = PdfReader(pdf_path)
    for page_num, page in enumerate(reader.pages):
        if page_num == 0:
            continue
        if "/Resources" not in page:
            continue
        resources = page["/Resources"]
        if "/XObject" not in resources:
            continue
        xobject = resources["/XObject"].get_object()
        for name, obj in xobject.items():
            obj = obj.get_object()
            if obj.get("/Subtype") != "/Image":
                continue
            try:
                width = int(obj.get("/Width", 0))
                height = int(obj.get("/Height", 0))
                if width < 200 or height < 200:
                    continue
                data = obj.get_data()
                filter_type = obj.get("/Filter", "")
                if filter_type in ("/DCTDecode", ["/DCTDecode"]):
                    photos.append(data)
                    continue
                color_space = obj.get("/ColorSpace", "")
                if isinstance(color_space, list):
                    color_space = str(color_space[0])
                mode = "L" if "/DeviceGray" in str(color_space) else "CMYK" if "/DeviceCMYK" in str(color_space) else "RGB"
                img = Image.frombytes(mode, (width, height), data)
                if img.mode == "CMYK":
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                photos.append(buf.getvalue())
            except Exception:
                continue
    return photos


def upload_to_imgbb(img_bytes):
    try:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        resp = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBB_API_KEY, "image": b64}, timeout=30)
        result = resp.json()
        if result.get("success"):
            return result["data"]["url"]
    except Exception as e:
        print(f"imgbb error: {e}")
    return None


def get_google_map_url(adresse, cp):
    if not GOOGLE_MAPS_API_KEY:
        return None
    try:
        full_address = f"{adresse}, {cp} Paris, France"
        encoded = requests.utils.quote(full_address)
        map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap"
            f"?center={encoded}&zoom=15&size=600x400"
            f"&markers=color:red%7C{encoded}"
            f"&key={GOOGLE_MAPS_API_KEY}"
        )
        img_resp = requests.get(map_url, timeout=15)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            return upload_to_imgbb(img_resp.content)
    except Exception as e:
        print(f"Maps error: {e}")
    return None


def build_gamma_title(data):
    adresse = data.get("adresse") or "ADRESSE INCONNUE"
    cp = data.get("code_postal") or ""
    surfaces = data.get("surfaces") or []
    surface_str = surfaces[0] if surfaces else "?"
    return f"[RENDER - A RETRAVAILLER] {adresse} — {cp} PARIS — {surface_str}"


def build_gamma_prompt(data, photo_urls, map_url):
    """
    Construit le prompt Gamma.
    RÈGLE STRICTE : inclure uniquement les données présentes (non-null) — aucune invention.
    """
    lines = []

    adresse = data.get("adresse") or ""
    cp = data.get("code_postal") or ""
    surfaces = data.get("surfaces") or []
    surface_str = surfaces[0] if surfaces else ""
    type_bien = data.get("type_bien")

    lines.append(f"# {adresse}")
    if cp:
        lines.append(f"**{cp} PARIS**")
    if surface_str:
        lines.append(f"**{surface_str}**")
    if type_bien:
        lines.append(f"*{type_bien}*")
    lines.append("")

    description = data.get("description")
    if description:
        lines.append("## Désignation")
        lines.append(description)
        lines.append("")

    dispo = data.get("disponibilite")
    if dispo:
        lines.append(f"**Disponibilité : {dispo}**")
        lines.append("")

    surfaces_detail = data.get("surfaces_detail") or surfaces
    if surfaces_detail:
        lines.append("## Surfaces")
        for s in surfaces_detail:
            lines.append(f"- {s}")
        lines.append("")

    prestations = data.get("prestations") or []
    if prestations:
        lines.append("## Prestations")
        for p in prestations:
            lines.append(f"- {p}")
        lines.append("")

    transports = data.get("transports") or []
    if transports:
        lines.append("## Accès")
        for t in transports:
            lines.append(f"- {t}")
        lines.append("")

    # Carte uniquement si effectivement générée
    if map_url:
        lines.append("## Localisation")
        lines.append(f"![Carte]({map_url})")
        lines.append("")

    # Photos uniquement celles extraites du PDF
    if photo_urls:
        lines.append("## Photos")
        for url in photo_urls:
            lines.append(f"![Photo]({url})")
        lines.append("")

    # Conditions financières
    has_finance = any([
        data.get("loyer_annuel"), data.get("loyer_mensuel"),
        data.get("charges"), data.get("honoraires"), data.get("taxe_bureaux")
    ])
    if has_finance:
        lines.append("## Conditions financières")
        for key, label in [
            ("loyer_annuel", "Loyer"), ("loyer_mensuel", "Loyer mensuel"),
            ("charges", "Charges"), ("honoraires", "Honoraires"), ("taxe_bureaux", "Taxe bureaux")
        ]:
            val = data.get(key)
            if val:
                lines.append(f"**{label} : {val}**")
        lines.append("")

    # Données juridiques
    juridique_keys = ["bail", "regime_fiscal", "depot_garantie", "indexation", "dpe"]
    juridique_labels = {
        "bail": "Bail", "regime_fiscal": "Régime fiscal",
        "depot_garantie": "Dépôt de garantie", "indexation": "Indexation", "dpe": "DPE"
    }
    has_juridique = any(data.get(k) for k in juridique_keys)
    if has_juridique:
        lines.append("## Données juridiques")
        for key in juridique_keys:
            val = data.get(key)
            if val:
                lines.append(f"{juridique_labels[key]} : {val}")
        lines.append("")

    lines.append("---")
    lines.append("*Document non contractuel — Equation SIE*")
    lines.append("")
    lines.append("CONSIGNES MISE EN FORME :")
    lines.append("- Logo Equation SIE : conserver à taille originale, ne pas agrandir ni dupliquer")
    lines.append("- Ne pas inclure de logos de confrères")
    lines.append("- Ne rien ajouter qui ne soit pas dans ce contenu (pas de plan inventé, pas de carte fictive)")

    return "\n".join(lines)


def call_gamma_api(title, prompt_text):
    headers = {
        "Authorization": f"Bearer {GAMMA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"title": title, "text": prompt_text, "theme": GAMMA_THEME_ID, "mode": "text_to_deck"}
    if GAMMA_TEMPLATE_ID:
        payload["templateId"] = GAMMA_TEMPLATE_ID

    resp = requests.post("https://api.gamma.app/v1/generate", headers=headers, json=payload, timeout=120)
    if resp.status_code not in (200, 201):
        raise ValueError(f"Gamma API {resp.status_code}: {resp.text[:300]}")

    result = resp.json()
    gamma_url = (
        result.get("url")
        or result.get("deck", {}).get("url")
        or result.get("presentation", {}).get("url")
        or result.get("data", {}).get("url")
    )
    if not gamma_url:
        raise ValueError(f"URL Gamma introuvable: {json.dumps(result)[:300]}")
    return gamma_url


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
