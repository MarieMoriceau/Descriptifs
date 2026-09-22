#!/usr/bin/env python3
"""
Equation SIE — PDF -> Gamma (descriptif FINI, sur le modèle MODELE 369)
Version intégrée : extraction Claude + photos (dédoublonnées) + carte Google 300 m
+ prompt validé (bandeau violet conservé, contacts Équation, étages haut->bas, sans doublon).
Remplace l'ancien app.py. Même structure Flask / jobs / imgbb / from-template.
"""
import os, json, re, base64, tempfile, time, io, math, hashlib, threading
import requests
import pdfplumber
from pypdf import PdfReader
from PIL import Image, ImageDraw
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
jobs = {}

VERSION = "2026-09-22-allphotos+plans+map"

GAMMA_API_KEY       = "sk-gamma-KLU47Xtpm0WkqYoQ4DEh0qZSKOOjcZr4hBb0G79m9Rg"
IMGBB_API_KEY       = "be39115664b38075a21de95d2ef95ba1"
GAMMA_THEME_ID      = "fo87qe3vn58hou1"
GAMMA_TEMPLATE_ID   = "g_s502jxfcibkr6kq"
GOOGLE_MAPS_API_KEY = "AIzaSyAGE65fo1453M-5CGe162Klk8NjS9K0hJA"
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL        = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# Équipe Équation — remplace systématiquement les contacts du confrère
EQUIPE = [
    {"name": "Lionel Bastian", "email": "lbastian@equation-sie.com", "phone": "07 82 83 67 43"},
    {"name": "Marine Bureau de Rotalier", "email": "mbureau@equation-sie.com", "phone": "06 18 98 23 31"},
    {"name": "Richard Abou Khalil", "email": "rabou-khalil@equation-sie.com", "phone": "06 27 86 54 71"},
]

HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF vers Gamma — Equation SIE</title>
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
  .info-title { font-weight: 600; color: #1a1a2e; font-size: 0.95rem; }
  .info-sub { color: #6b7280; font-size: 0.85rem; margin-top: 0.2rem; }
  .drop-zone { border: 2px dashed #d1d5db; border-radius: 10px; padding: 2rem 1.5rem; cursor: pointer; transition: all 0.2s; position: relative; margin-bottom: 1rem; }
  .drop-zone:hover, .drop-zone.dragover { border-color: #e53935; background: #fff5f5; }
  .drop-zone input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }
  .drop-icon { font-size: 2rem; margin-bottom: 0.5rem; }
  .drop-zone h3 { font-size: 0.95rem; color: #374151; font-weight: 500; }
  .drop-zone p { font-size: 0.82rem; color: #9ca3af; margin-top: 0.25rem; }
  .files-list { margin-bottom: 1rem; display: none; }
  .files-list.visible { display: block; }
  .file-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem; background: #f8f9fa; border-radius: 8px; margin-bottom: 0.4rem; font-size: 0.85rem; }
  .file-item .fname { flex: 1; color: #374151; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .file-item .fremove { color: #9ca3af; cursor: pointer; font-size: 1rem; padding: 0 4px; }
  .file-item .fremove:hover { color: #e53935; }
  .btn { width: 100%; padding: 0.9rem; background: #e53935; color: white; border: none; border-radius: 10px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: background 0.2s; }
  .btn:hover { background: #c62828; }
  .btn:disabled { background: #9ca3af; cursor: not-allowed; }
  .jobs-list { margin-top: 1.2rem; display: none; }
  .jobs-list.visible { display: block; }
  .job-item { padding: 0.85rem 1rem; border-radius: 8px; margin-bottom: 0.6rem; font-size: 0.88rem; text-align: left; border: 1px solid #e5e7eb; }
  .job-item .job-name { font-weight: 600; color: #1a1a2e; margin-bottom: 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .job-item .job-log { color: #6b7280; font-size: 0.78rem; }
  .job-item.running { border-color: #93c5fd; background: #f0f4ff; }
  .job-item.done { border-color: #86efac; background: #f0fdf4; }
  .job-item.error { border-color: #fca5a5; background: #fff5f5; }
  .job-item .gamma-link { display: inline-block; margin-top: 0.4rem; padding: 0.3rem 0.8rem; background: #16a34a; color: white; text-decoration: none; border-radius: 6px; font-size: 0.8rem; font-weight: 600; }
  .new-btn { background: none; border: 1px solid #d1d5db; color: #6b7280; width: 100%; padding: 0.6rem; border-radius: 8px; font-size: 0.85rem; cursor: pointer; margin-top: 0.75rem; }
  .new-btn:hover { border-color: #e53935; color: #e53935; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid rgba(59,91,219,0.3); border-top-color: #3b5bdb; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 4px; }
</style>
</head>
<body>
<div class="card">
  <div class="dots">
    <div class="dot dot-red"></div>
    <div class="dot dot-dark"></div>
    <div class="dot dot-blue"></div>
  </div>
  <h1>PDF &#8594; Gamma</h1>
  <p class="subtitle">Equation SIE &#8212; Descriptifs commerciaux</p>
  <div class="info-box">
    <div class="info-title">Convertir un ou plusieurs descriptifs</div>
    <div class="info-sub">Glissez 1 ou plusieurs PDFs &#8212; les Gammas se generent en parallele</div>
  </div>
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept=".pdf" multiple>
    <div class="drop-icon">&#128196;</div>
    <h3>Deposez vos PDFs ici</h3>
    <p>ou cliquez pour parcourir (selection multiple possible)</p>
  </div>
  <div class="files-list" id="filesList"></div>
  <button class="btn" id="launchBtn" disabled onclick="launch()">&#128202; Generer les Gammas</button>
  <div class="jobs-list" id="jobsList"></div>
</div>
<script>
let selectedFiles = [];
let activeJobs = {};
let pollInterval = null;

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  addFiles(Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf')));
});
fileInput.addEventListener('change', e => {
  addFiles(Array.from(e.target.files));
  fileInput.value = '';
});

function addFiles(files) {
  files.forEach(f => {
    if (!selectedFiles.find(sf => sf.name === f.name)) selectedFiles.push(f);
  });
  renderFilesList();
}

function removeFile(name) {
  selectedFiles = selectedFiles.filter(f => f.name !== name);
  renderFilesList();
}

function renderFilesList() {
  const list = document.getElementById('filesList');
  if (selectedFiles.length === 0) {
    list.classList.remove('visible');
    list.innerHTML = '';
    document.getElementById('launchBtn').disabled = true;
    return;
  }
  list.classList.add('visible');
  list.innerHTML = selectedFiles.map(f =>
    `<div class="file-item">
      <span>&#128206;</span>
      <span class="fname">${f.name}</span>
      <span class="fremove" onclick="removeFile('${f.name.replace(/'/g,"\\'")}')">&#10005;</span>
    </div>`
  ).join('');
  document.getElementById('launchBtn').disabled = false;
  const n = selectedFiles.length;
  document.getElementById('launchBtn').innerHTML = n > 1
    ? `&#128202; Generer ${n} Gammas en parallele`
    : '&#128202; Generer le Gamma';
}

async function launch() {
  if (selectedFiles.length === 0) return;
  document.getElementById('launchBtn').disabled = true;
  const jobsDiv = document.getElementById('jobsList');
  jobsDiv.classList.add('visible');
  jobsDiv.innerHTML = '';
  activeJobs = {};

  for (const file of selectedFiles) {
    const jobDiv = document.createElement('div');
    jobDiv.className = 'job-item running';
    jobDiv.id = 'job-' + file.name;
    jobDiv.innerHTML = `<div class="job-name">&#128196; ${file.name}</div><div class="job-log"><span class="spinner"></span>Upload en cours...</div>`;
    jobsDiv.appendChild(jobDiv);

    const fd = new FormData();
    fd.append('pdf', file);
    try {
      const res = await fetch('/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (data.job_id) {
        activeJobs[data.job_id] = file.name;
      } else {
        updateJob(file.name, 'error', 'Erreur upload: ' + (data.error || '?'));
      }
    } catch(e) {
      updateJob(file.name, 'error', 'Erreur reseau: ' + e.message);
    }
  }

  if (Object.keys(activeJobs).length > 0) startPolling();
}

function updateJob(fname, status, logMsg, gammaUrl) {
  const el = document.getElementById('job-' + fname);
  if (!el) return;
  el.className = 'job-item ' + status;
  const spinner = status === 'running' ? '<span class="spinner"></span>' : '';
  const icon = status === 'done' ? '&#10003; ' : status === 'error' ? '&#10005; ' : '';
  const link = gammaUrl ? `<br><a class="gamma-link" href="${gammaUrl}" target="_blank">Ouvrir le Gamma &#8594;</a>` : '';
  el.innerHTML = `<div class="job-name">&#128196; ${fname}</div><div class="job-log">${spinner}${icon}${logMsg}${link}</div>`;
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    const remaining = Object.keys(activeJobs);
    if (remaining.length === 0) {
      clearInterval(pollInterval);
      document.getElementById('launchBtn').disabled = false;
      document.getElementById('launchBtn').innerHTML = '&#128202; Generer de nouveaux Gammas';
      selectedFiles = [];
      renderFilesList();
      return;
    }
    for (const jobId of remaining) {
      try {
        const res = await fetch('/status/' + jobId);
        const data = await res.json();
        const fname = activeJobs[jobId];
        const lastLog = data.log?.[data.log.length - 1] || '...';
        if (data.status === 'done') {
          updateJob(fname, 'done', 'Gamma cree !', data.url);
          delete activeJobs[jobId];
        } else if (data.status === 'error') {
          updateJob(fname, 'error', lastLog);
          delete activeJobs[jobId];
        } else {
          updateJob(fname, 'running', lastLog);
        }
      } catch(e) {}
    }
  }, 3000);
}
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/version')
def version():
    """Permet de vérifier quelle version du code tourne réellement en ligne."""
    return jsonify({"version": VERSION})


@app.route('/upload', methods=['POST'])
def upload():
    if 'pdf' not in request.files:
        return jsonify({'error': 'Pas de fichier PDF'}), 400
    f = request.files['pdf']
    filename = f.filename
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    f.save(tmp.name)
    tmp.close()
    job_id = f"{int(time.time())}_{re.sub(r'[^a-zA-Z0-9]', '_', filename[:20])}"
    jobs[job_id] = {'status': 'running', 'step': 0, 'log': [], 'url': '', 'filename': filename}
    t = threading.Thread(target=run_job, args=(job_id, tmp.name, filename))
    t.daemon = True
    t.start()
    return jsonify({'job_id': job_id})


@app.route('/status/<path:job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job inconnu'}), 404
    return jsonify(jobs[job_id])


def run_job(job_id, pdf_path, filename):
    def update(step, msg):
        jobs[job_id]['step'] = step
        jobs[job_id]['log'].append(msg)
    try:
        update(1, 'Extraction du texte...')
        text = extract_text_from_pdf(pdf_path)
        update(2, 'Analyse Claude...')
        info = parse_info_with_claude(text)
        update(2, f"Adresse : {info.get('adresse','?')}")
        update(3, 'Extraction photos + plans...')
        media = extract_media(pdf_path)            # photos ET plans, dédoublonnés
        photos, plans = media["photos"], media["plans"]
        update(3, f"{len(photos)} photo(s), {len(plans)} plan(s)")
        update(4, 'Upload photos + plans + carte 300 m...')
        image_urls = []
        for path in photos:
            u = upload_image(path)
            if u: image_urls.append(u)
        plan_urls = []
        for path in plans:
            u = upload_image(path)
            if u: plan_urls.append(u)
        map_url = build_map_300(info.get('adresse', ''))
        update(4, "Carte 300 m OK" if map_url else "Carte non generee")
        update(5, 'Construction du descriptif...')
        prompt = build_prompt(info, image_urls, map_url, plan_urls)
        update(6, 'Generation Gamma (~2 min)...')
        gamma_url = create_gamma(prompt)
        jobs[job_id]['status'] = 'done'
        jobs[job_id]['url'] = gamma_url
        jobs[job_id]['log'].append('Gamma cree !')
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['log'].append(f'Erreur : {str(e)}')
    finally:
        try: os.unlink(pdf_path)
        except: pass


def extract_text_from_pdf(pdf_path):
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = (page.extract_text() or "").strip()
            if len(t) > 20:
                parts.append(t)
    return "\n\n".join(parts)


# ============ EXTRACTION CLAUDE (schéma descriptif Équation) ============
EXTRACT_SCHEMA = """Renvoie UNIQUEMENT un JSON valide (aucun texte autour) :
{
 "adresse": "N° rue — CODE Ville",
 "transaction": "location" | "vente",
 "surface_full": "…",
 "dispo": "…",
 "immeuble": ["…", ...],
 "locaux": ["…", ...],
 "recurrents": ["Label : valeur", ...],
 "entree": ["Label : valeur", ...],
 "juridiques": ["Label : valeur", ...],
 "surfaces": [["Niveau","Type","Surface"], ...],
 "desserte": ["…", ...],
 "card_titles": null
}
Règles STRICTES :
- français, chiffres AU MOT PRÈS depuis le document, n'invente rien (mets "" ou omets si absent).
- "adresse" ex : "60 Rue Jouffroy d'Abbans — 75017 Paris".
- "surfaces" : classe DU PLUS HAUT ÉTAGE AU PLUS BAS, et termine par ["","TOTAL","… m²"].
- "recurrents" : loyer, charges, taxe bureaux, impôt foncier, TEOM (selon dispo).
- "entree" : dépôt de garantie, honoraires, frais d'acte.
- "juridiques" : bail, régime fiscal, indexation, paiement.
- pour une VENTE : "card_titles" = ["Prix & charges","Acquisition","Le bien"] et mets le prix dans "recurrents".
- NE reprends PAS les coordonnées de l'agent du confrère (remplacées par l'équipe Équation)."""

def parse_info_with_claude(text):
    prompt = (f"Voici le texte brut d'un descriptif immobilier de bureaux (confrère).\n\n{EXTRACT_SCHEMA}\n\n"
              f"=== TEXTE ===\n{text[:16000]}")
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": CLAUDE_MODEL, "max_tokens": 2000,
              "messages": [{"role": "user", "content": prompt}]}, timeout=90)
    if r.status_code != 200:
        raise ValueError(f"Claude API {r.status_code}: {r.text[:200]}")
    raw = r.json()["content"][0]["text"]
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("Claude n'a pas renvoyé de JSON")
    d = json.loads(m.group(0))
    d.setdefault("transaction", "location")
    for k in ["immeuble", "locaux", "recurrents", "entree", "juridiques", "surfaces", "desserte"]:
        d.setdefault(k, [])
    return d


# ============ PHOTOS (pypdf, dédoublonnées, filtre "page-document") ============
def _palette(pil):
    im = pil.convert("RGB").resize((64, 64))
    px = list(im.getdata()); n = len(px)
    from collections import Counter
    q = [(r // 32, g // 32, b // 32) for r, g, b in px]; c = Counter(q)
    white = sum(1 for r, g, b in px if r > 225 and g > 225 and b > 225) / n
    return len(c), white


def _page_labels(pdf_path):
    """Texte (minuscule) de chaque page, pour repérer les sections « Photos » / « Plans »."""
    labels = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                labels[i] = (page.extract_text() or "").lower()
    except Exception:
        pass
    return labels


def _save(data, path):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if im.width > 1500:
        im = im.resize((1500, int(im.height * 1500 / im.width)))
    im.save(path, "JPEG", quality=85)
    return path


def extract_media(pdf_path, max_photos=12, max_plans=4):
    """Sépare PHOTOS et PLANS.
    Priorité au titre de section de la page (« Photos », « Plans ») quand le confrère
    en met un (cas JLL/BNP/CBRE) ; sinon on retombe sur l'analyse de palette.
    - photos : toutes les vraies photos (dédoublonnées), pas seulement quelques-unes ;
    - plans  : les plans d'étage (RDC/RDJ…), classiquement sur fond blanc avec des traits.
    Saute la page 1 (couverture confrère) et les logos/vignettes."""
    reader = PdfReader(pdf_path)
    labels = _page_labels(pdf_path)
    temp_dir = tempfile.mkdtemp()
    photos, plans = [], []
    seen = set()
    for pn, page in enumerate(reader.pages):
        if pn == 0:
            continue
        txt = labels.get(pn, "")
        is_plan_page = "plan" in txt
        is_photo_page = "photo" in txt
        try:
            page_imgs = list(page.images)
        except Exception:
            page_imgs = []
        for img in page_imgs:
            try:
                data = img.data
            except Exception:
                continue
            h = hashlib.md5(data).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            try:
                pil = Image.open(io.BytesIO(data)); w, ht = pil.size
            except Exception:
                continue
            if min(w, ht) < 180 or (w * ht) < 55000:   # vignettes/logos écartés
                continue
            ar = w / ht
            if not (0.55 <= ar <= 3.2):                 # bandeaux extrêmes écartés
                continue
            dist, white = _palette(pil)
            # --- classification ---
            if is_plan_page:
                kind = "plan"
            elif is_photo_page:
                kind = "photo" if dist >= 20 else None   # évite un logo sur la page photos
            else:
                # pas de titre exploitable : palette
                if dist >= 28 and white < 0.55:
                    kind = "photo"
                elif dist >= 12 and white >= 0.55 and min(w, ht) >= 450:
                    kind = "plan"                        # fond blanc + traits + GRAND = vrai plan
                else:
                    kind = None                          # petits plans-vignettes / mini-cartes exclus
            if kind == "photo":
                photos.append({"data": data, "dist": dist, "px": w * ht})
            elif kind == "plan":
                plans.append({"data": data, "px": w * ht})
    # photos : les plus « photographiques »/grandes d'abord, on les prend TOUTES (plafond de sécurité)
    photos.sort(key=lambda x: x["dist"] + x["px"] / 200000.0, reverse=True)
    plans.sort(key=lambda x: x["px"], reverse=True)
    photo_paths, plan_paths = [], []
    for i, c in enumerate(photos[:max_photos]):
        try: photo_paths.append(_save(c["data"], os.path.join(temp_dir, f"photo_{i}.jpg")))
        except Exception: pass
    for i, c in enumerate(plans[:max_plans]):
        try: plan_paths.append(_save(c["data"], os.path.join(temp_dir, f"plan_{i}.jpg")))
        except Exception: pass
    return {"photos": photo_paths, "plans": plan_paths}


def extract_photos(pdf_path, max_photos=12):
    """Compat : renvoie uniquement les chemins photos."""
    return extract_media(pdf_path, max_photos=max_photos)["photos"]


# ============ CARTE OpenStreetMap + CERCLE 300 m (100 % requests + PIL, sans dépendance) ============
_TILE_UA = "equation-sie-descriptifs/1.0 (contact: mmoriceau@equation-sie.com)"

def _deg2xy(lat, lon, z):
    """Coordonnées de tuile (fractionnaires) Web Mercator."""
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y

def build_map_300(adresse, radius_m=300):
    """Carte OpenStreetMap centrée sur le bien + cercle de 300 m, uploadée sur imgbb.
    Aucune dépendance externe (staticmap/google) : on récupère les tuiles OSM avec
    requests puis on les assemble avec PIL. Géocodage via Nominatim (OSM)."""
    if not adresse:
        return None
    q = re.sub(r"\s+", " ", adresse.replace("—", " ")).strip()
    if "france" not in q.lower():
        q += ", France"
    try:
        # 1) Géocodage
        gr = requests.get("https://nominatim.openstreetmap.org/search",
                          params={"q": q, "format": "json", "limit": 1, "countrycodes": "fr"},
                          headers={"User-Agent": _TILE_UA}, timeout=25).json()
        if not gr:
            return None
        lat = float(gr[0]["lat"]); lon = float(gr[0]["lon"])

        # 2) Assemblage des tuiles OSM (256 px) autour du centre
        W, H, z, TS = 1000, 700, 16, 256
        cx_t, cy_t = _deg2xy(lat, lon, z)
        # tuile de départ (coin haut-gauche) pour couvrir W x H centré
        px_center = cx_t * TS
        py_center = cy_t * TS
        left = px_center - W / 2
        top = py_center - H / 2
        x0 = int(math.floor(left / TS))
        y0 = int(math.floor(top / TS))
        nx = int(math.ceil((left + W) / TS)) - x0
        ny = int(math.ceil((top + H) / TS)) - y0

        canvas = Image.new("RGBA", (nx * TS, ny * TS), (235, 235, 235, 255))
        sess = requests.Session()
        sess.headers.update({"User-Agent": _TILE_UA})
        n_max = 2 ** z
        for ix in range(nx):
            for iy in range(ny):
                tx, ty = x0 + ix, y0 + iy
                if tx < 0 or ty < 0 or tx >= n_max or ty >= n_max:
                    continue
                url = f"https://a.tile.openstreetmap.org/{z}/{tx}/{ty}.png"
                try:
                    tr = sess.get(url, timeout=20)
                    if tr.status_code == 200:
                        tile = Image.open(io.BytesIO(tr.content)).convert("RGBA")
                        canvas.paste(tile, (ix * TS, iy * TS))
                except Exception:
                    continue

        # 3) Recadrage exact W x H centré sur le bien
        off_x = int(round(left - x0 * TS))
        off_y = int(round(top - y0 * TS))
        img = canvas.crop((off_x, off_y, off_x + W, off_y + H)).convert("RGBA")

        # 4) Cercle 300 m + pin central
        base_mpp = 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)
        pr = radius_m / base_mpp
        cx, cy = W / 2, H / 2
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dd = ImageDraw.Draw(ov)
        dd.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=(214, 32, 54, 55),
                   outline=(214, 32, 54, 255), width=6)
        dd.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=(214, 32, 54, 255),
                   outline=(255, 255, 255, 255), width=4)
        out = Image.alpha_composite(img, ov).convert("RGB")
        p = os.path.join(tempfile.mkdtemp(), "map.jpg"); out.save(p, "JPEG", quality=90)
        return upload_image(p)
    except Exception:
        return None


def upload_image(path):
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    r = requests.post("https://api.imgbb.com/1/upload",
                      data={"key": IMGBB_API_KEY, "image": encoded}, timeout=30)
    return r.json()["data"]["url"] if r.status_code == 200 else None


# ============ PROMPT (from-template validé) ============
def build_prompt(d, photo_urls, map_url, plan_urls=None):
    plan_urls = plan_urls or []
    vente = d.get("transaction") == "vente"
    def lst(x): return " ; ".join([str(i) for i in (x or [])])
    titles = d.get("card_titles") or ["Coûts récurrents", "Coûts à l'entrée", "Données juridiques"]
    surf = "\n".join(f"- {row[0]}/{row[1]}/{row[2]}" for row in d.get("surfaces", []) if len(row) == 3)
    dess = "\n".join(f"- {x}" for x in d.get("desserte", []))
    gal = "\n".join(f"![]({u})" for u in photo_urls)
    plans_md = "\n".join(f"![]({u})" for u in plan_urls)
    eq = " ; ".join(f"{c['name']} {c['email']} {c['phone']}" for c in EQUIPE)
    mp = f"\nCarte de situation (rayon 300 m) : ![]({map_url})" if map_url else ""
    dispo = f" — Disponibilité : {d['dispo']}" if d.get("dispo") else ""
    plans_block = (f"""

PLANS (plans d'étage du bien — crée une carte « Plans » dédiée et affiche TOUS ces plans en grand, pleine largeur, l'un sous l'autre) :
{plans_md}""" if plan_urls else "")
    return f"""Conserve la structure, l'ordre des cartes et la mise en page de ce modèle, MAIS adapte le nombre de cartes photos au nombre de photos fournies. Remplace le contenu par ce bien, en français, chiffres au mot près, et INSÈRE les images fournies aux emplacements images du modèle. SUR LA COUVERTURE : CONSERVE le bandeau violet du modèle tel quel — ne le remplace JAMAIS par une photo, garde juste le titre/adresse et le logo du modèle. PHOTOS : affiche TOUTES les photos fournies ci-dessous (n'en supprime AUCUNE), chacune UNE SEULE FOIS — AUCUN DOUBLON ; s'il y a plus de photos que d'emplacements dans le modèle, AJOUTE autant de cartes galerie que nécessaire pour toutes les montrer. PLANS : ajoute une carte « Plans » dédiée avec les plans fournis. AGRANDIS la carte de situation sur la carte « Accès » : grande, pleine largeur. NE mets AUCUN titre du type « à retravailler ».

COUVERTURE (garde le bandeau violet) : {d.get('adresse','')} — Bureaux à {'vendre' if vente else 'louer'} — {d.get('surface_full','')}{dispo}

À RETENIR SUR L'IMMEUBLE : {lst(d.get('immeuble'))}
À RETENIR SUR LES LOCAUX : {lst(d.get('locaux'))}

GALERIE — AFFICHE TOUTES CES PHOTOS ({len(photo_urls)} photos réelles du bien, aucune à retirer) :
{gal}{plans_block}

{titles[0].upper()} : {lst(d.get('recurrents'))}
{titles[1].upper()} : {lst(d.get('entree'))}
{titles[2].upper()} : {lst(d.get('juridiques'))}

TABLEAU DE SURFACES (Niveau/Type/Surface, du plus haut au plus bas) :
{surf}

ACCÈS & DESSERTE :
{dess}{mp}

CONTACTS (équipe Équation, remplacent ceux du confrère) : {eq}
"""


def create_gamma(prompt):
    headers = {"X-API-KEY": GAMMA_API_KEY, "Content-Type": "application/json"}
    payload = {"gammaId": GAMMA_TEMPLATE_ID, "prompt": prompt, "themeId": GAMMA_THEME_ID}
    r = requests.post("https://public-api.gamma.app/v1.0/generations/from-template",
                      headers=headers, json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise ValueError(f"Gamma API {r.status_code}: {r.text[:300]}")
    gid = r.json().get("generationId")
    if not gid:
        raise ValueError(f"Pas de generationId : {r.text}")
    for _ in range(70):
        time.sleep(5)
        poll = requests.get(f"https://public-api.gamma.app/v1.0/generations/{gid}",
                            headers={"X-API-KEY": GAMMA_API_KEY}, timeout=20)
        if poll.status_code == 200:
            res = poll.json()
            if res.get("status") == "completed":
                return res.get("gammaUrl", "")
            if res.get("status") in ("failed", "error"):
                raise ValueError(f"Generation echouee: {res}")
    raise ValueError("Timeout Gamma.")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
