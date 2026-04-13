#!/usr/bin/env python3
"""
Equation SIE — PDF -> Gamma
- Titre automatique [RENDER - A RETRAVAILLER]
- Multi-PDF simultanes avec suivi par fichier
- Skip page 1 (logo confrere)
- Surfaces par etage
- Extraction photos pypdf uniquement (pas de rasterisation = pas de crash memoire)
"""
import os, json, re, base64, tempfile, time, io, threading
import requests
import pdfplumber
from pypdf import PdfReader
from PIL import Image
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
jobs = {}

GAMMA_API_KEY       = "sk-gamma-KLU47Xtpm0WkqYoQ4DEh0qZSKOOjcZr4hBb0G79m9Rg"
IMGBB_API_KEY       = "be39115664b38075a21de95d2ef95ba1"
GAMMA_THEME_ID      = "fo87qe3vn58hou1"
GAMMA_TEMPLATE_ID   = "g_s502jxfcibkr6kq"
GOOGLE_MAPS_API_KEY = "AIzaSyAGE65fo1453M-5CGe162Klk8NjS9K0hJA"
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")

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
        update(2, f"Adresse : {info.get('adresse','?')} {info.get('code_postal','')}")
        update(3, 'Extraction photos...')
        plan_paths, plan_page_idxs = detect_plans_par_texte(pdf_path)
        photos = extract_photos(pdf_path, plan_page_idxs=plan_page_idxs)
        update(3, f"{len(photos)} photos extraites")
        update(4, 'Upload photos...')
        image_urls = []
        for path in photos[:12]:
            url = upload_image(path)
            if url: image_urls.append(url)
        plan_urls = []
        for pp in plan_paths:
            url = upload_image(pp)
            if url: plan_urls.append(url)
        maps_url = upload_maps_image(info.get('adresse', ''), info.get('code_postal', ''))
        update(5, 'Construction prompt...')
        prompt = build_prompt(info, image_urls, plan_urls=plan_urls, maps_url=maps_url)
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


def parse_info_with_claude(text):
    prompt = f"""Tu es un expert en immobilier de bureaux parisien.
Analyse ce descriptif et extrais les informations au format JSON strict. Si absent, mets null.
Code postal toujours format 750XX.

IMPORTANT surfaces : si plusieurs lots ou etages, liste chaque lot separement.
Exemple : "surfaces_detail": ["301 m2 (6eme etage) - 750 euros/m2/an", "426 m2 (3eme etage) - 850 euros/m2/an"]

{{"adresse":"55 RUE D AMSTERDAM","code_postal":"75008",
"surfaces":["1576 m2"],"surfaces_detail":["1576 m2 (2eme etage) - 850 euros/m2/an"],
"loyers":["850 euros/m2/an HT HC"],"disponibilite":"Juin 2026",
"divisibilite":"Divisible a partir de 484 m2","transports":["Gare Saint-Lazare - 1 min"],
"prestations":["Climatisation","Fibre optique"],"description":"Description courte",
"confrere":"JLL","charges":"80 euros/m2/an HT","impot_foncier":"25 euros/m2/an HT",
"taxe_bureaux":"21 euros/m2/an HT","teom":null,"bail":"3/6/9 ans",
"depot_garantie":"3 mois de loyer HT","regime_fiscal":"TVA"}}

Texte :
---
{text[:8000]}
---
Reponds UNIQUEMENT avec le JSON."""
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1200,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30)
        if r.status_code == 200:
            raw = r.json()["content"][0]["text"].strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
            data = json.loads(raw)
            def s(v, default=""):
                if v is None: return default
                return str(v).strip() or default
            def norm_surfaces(lst):
                result = []
                for x in (lst or []):
                    sx = str(x).strip()
                    if not sx: continue
                    try:
                        val = float(sx.replace(" ","").replace(",",".").replace("m2","").replace("m²",""))
                        result.append(f"{int(val)} m²")
                    except:
                        result.append(sx if "m" in sx else sx + " m²")
                return result
            def norm_loyers(lst):
                result = []
                for x in (lst or []):
                    sx = str(x).strip()
                    if not sx: continue
                    try:
                        val = float(sx.replace(" ","").replace(",",".").replace("euros","")
                                      .replace("€","").replace("/m2/an","").replace("/m²/an","")
                                      .replace("HTHC","").strip())
                        result.append(f"{int(val)} euros/m2/an HT HC")
                    except:
                        result.append(sx)
                return result
            return {
                "adresse": s(data.get("adresse")).upper(),
                "code_postal": s(data.get("code_postal")),
                "surfaces": norm_surfaces(data.get("surfaces")),
                "surfaces_detail": [s(x) for x in (data.get("surfaces_detail") or []) if x],
                "loyers": norm_loyers(data.get("loyers")),
                "disponibilite": s(data.get("disponibilite")),
                "divisibilite": s(data.get("divisibilite")),
                "transports": [s(x) for x in (data.get("transports") or []) if x],
                "prestations": [s(x) for x in (data.get("prestations") or []) if x],
                "description": s(data.get("description")),
                "confrere": s(data.get("confrere")),
                "charges": s(data.get("charges"), "Nous consulter"),
                "impot_foncier": s(data.get("impot_foncier"), "En cours de determination"),
                "taxe_bureaux": s(data.get("taxe_bureaux"), "En cours de determination"),
                "teom": s(data.get("teom"), "En cours de determination"),
                "bail": s(data.get("bail"), "3/6/9 ans"),
                "depot_garantie": s(data.get("depot_garantie"), "3 mois de loyer HT HC"),
                "regime_fiscal": s(data.get("regime_fiscal"), "TVA"),
            }
    except Exception:
        pass
    return {
        "adresse": "", "code_postal": "", "surfaces": [], "surfaces_detail": [],
        "loyers": [], "disponibilite": "", "divisibilite": "", "transports": [],
        "prestations": [], "description": "", "confrere": "",
        "charges": "Nous consulter", "impot_foncier": "En cours de determination",
        "taxe_bureaux": "En cours de determination", "teom": "En cours de determination",
        "bail": "3/6/9 ans", "depot_garantie": "3 mois de loyer HT HC", "regime_fiscal": "TVA",
    }


def detect_plans_par_texte(pdf_path, min_kb=30):
    """Detecte les pages de plans — skip page 0 (logo confrere)."""
    reader = PdfReader(pdf_path)
    temp_dir = tempfile.mkdtemp()
    plan_paths = []
    plan_page_idxs = set()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i == 0: continue  # skip page 1 logo confrere
            t = (page.extract_text() or "").strip()
            lignes = [l.strip() for l in t.split("\n") if l.strip()]
            titre = " ".join(lignes[:8]).lower()
            if not re.search(r"\bplan\b", titre): continue
            has_image = any(len(img.data) / 1024 >= min_kb for img in reader.pages[i].images)
            if not has_image: continue
            plan_page_idxs.add(i)
            meilleures = []
            for img in reader.pages[i].images:
                if len(img.data) / 1024 < min_kb: continue
                try:
                    pil = Image.open(io.BytesIO(img.data))
                    meilleures.append((pil.width * pil.height, img.data))
                except Exception: pass
            if meilleures:
                meilleures.sort(key=lambda x: x[0], reverse=True)
                _, data = meilleures[0]
                path = os.path.join(temp_dir, f"plan_p{i+1}.jpg")
                try:
                    Image.open(io.BytesIO(data)).convert("RGB").save(path, "JPEG", quality=88)
                except Exception:
                    with open(path, "wb") as f: f.write(data)
                plan_paths.append(path)
    return plan_paths, plan_page_idxs


def extract_photos(pdf_path, plan_page_idxs=None, min_kb=15):
    """
    Extraction photos via pypdf uniquement — pas de rasterisation PDF
    pour eviter les crashes memoire sur Render plan gratuit (512 Mo).
    Skip page 0 (logo confrere page 1).
    """
    reader = PdfReader(pdf_path)
    temp_dir = tempfile.mkdtemp()
    paths = []
    skip = set(plan_page_idxs or set())
    skip.add(0)  # toujours ignorer la page 1

    for pn, page in enumerate(reader.pages):
        if pn in skip: continue
        for idx, img in enumerate(page.images):
            if len(img.data) / 1024 < min_kb: continue
            try:
                pil = Image.open(io.BytesIO(img.data))
                w, h = pil.size
                if w < 200 or h < 150: continue
                path = os.path.join(temp_dir, f"photo_p{pn+1}_{idx}.jpg")
                pil.convert("RGB").save(path, "JPEG", quality=85)
                paths.append(path)
            except Exception: pass

    return paths[:12]


def upload_image(path):
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    r = requests.post("https://api.imgbb.com/1/upload",
                      data={"key": IMGBB_API_KEY, "image": encoded}, timeout=30)
    return r.json()["data"]["url"] if r.status_code == 200 else None


def upload_maps_image(adresse, code_postal):
    if not adresse: return None
    adresse_complete = f"{adresse}, {code_postal} Paris, France"
    params = {"center": adresse_complete, "zoom": "16", "size": "800x600",
              "maptype": "roadmap", "markers": f"color:red|{adresse_complete}",
              "key": GOOGLE_MAPS_API_KEY}
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    try:
        r = requests.get(f"https://maps.googleapis.com/maps/api/staticmap?{query}", timeout=20)
        if r.status_code != 200: return None
        encoded = base64.b64encode(r.content).decode("utf-8")
        r2 = requests.post("https://api.imgbb.com/1/upload",
                           data={"key": IMGBB_API_KEY, "image": encoded}, timeout=30)
        return r2.json()["data"]["url"] if r2.status_code == 200 else None
    except Exception: return None


def build_prompt(info, image_urls, plan_urls=None, maps_url=None):
    adresse  = info.get("adresse") or "Adresse a preciser"
    cp       = info.get("code_postal", "")
    surfaces_detail = info.get("surfaces_detail", [])
    surfaces_simple = " / ".join(info.get("surfaces", [])) or "A preciser"
    if surfaces_detail:
        surfaces_bloc = "\n".join(f"  - {s}" for s in surfaces_detail)
        surfaces_txt = f"DETAIL DES SURFACES :\n{surfaces_bloc}\n  Total : {surfaces_simple}"
    else:
        surfaces_txt = f"SURFACE : {surfaces_simple}"
    loyers   = " | ".join(info.get("loyers", [])) or "Nous consulter"
    dispo    = info.get("disponibilite") or "A preciser"
    div      = info.get("divisibilite", "")
    desc     = info.get("description") or "Bureau de qualite dans un immeuble moderne."
    trans    = "\n".join(f"- {t}" for t in info.get("transports", [])) or "- A completer"
    prest    = "\n".join(f"- {p}" for p in info.get("prestations", [])) or "- A completer"
    photos   = ("PHOTOS :\n" + "\n".join(f"- {u}" for u in image_urls[:12])) if image_urls else ""
    plans    = ("PLANS :\n" + "\n".join(f"- {u}" for u in plan_urls)) if plan_urls else ""
    maps_s   = f"CARTE 300m :\n- {maps_url}" if maps_url else ""
    titre    = f"[RENDER - A RETRAVAILLER] {adresse} — {cp} PARIS — {surfaces_simple}"

    return f"""Utilise la structure exacte de ce template pour creer un nouveau descriptif immobilier.
REGLES ABSOLUES A RESPECTER :
- Conserver EXACTEMENT la mise en page du template sans aucune modification
- Conserver le logo Equation SIE A SA TAILLE ORIGINALE dans le template, ne pas l'agrandir
- La page de couverture doit garder le logo petit, en haut a droite uniquement
- Conserver la derniere page de contact sans modification
- Ne jamais dupliquer ou redimensionner le logo
ADRESSE : {adresse}
LOCALISATION : {adresse}, {cp} PARIS
{surfaces_txt}
DISPONIBILITE : {dispo}
{f"DIVISIBILITE : {div}" if div else ""}
DESCRIPTION : {desc}
TRANSPORTS :
{trans}
PRESTATIONS :
{prest}
PAGE 4 COUTS RECURRENTS :
Loyer bureaux : {loyers}
Charges bureaux : {info.get('charges', 'Nous consulter')}
Impot foncier : {info.get('impot_foncier', 'En cours de determination')}
Taxe bureaux : {info.get('taxe_bureaux', 'En cours de determination')}
PAGE 4 DONNEES JURIDIQUES :
Bail : {info.get('bail', '3/6/9 ans')}
Regime fiscal : {info.get('regime_fiscal', 'TVA')}
Depot de garantie : {info.get('depot_garantie', '3 mois de loyer HT HC')}
{photos}
{plans}
{maps_s}
TITRE : {titre}
INSTRUCTIONS FINALES :
- Code postal toujours {cp}, jamais "Paris Xe"
- Ne pas inclure logos des confreres (Knight Frank, CBRE, JLL, BNP, Cushman)
- Le titre doit commencer par [RENDER - A RETRAVAILLER]
- Logo Equation SIE : conserver uniquement celui du template, a sa taille originale, ne pas l'agrandir ni le dupliquer"""


def create_gamma(prompt):
    headers = {"X-API-KEY": GAMMA_API_KEY, "Content-Type": "application/json"}
    payload = {"gammaId": GAMMA_TEMPLATE_ID, "prompt": prompt, "themeId": GAMMA_THEME_ID}
    r = requests.post("https://public-api.gamma.app/v1.0/generations/from-template",
                      headers=headers, json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise Exception(f"Gamma API erreur {r.status_code}: {r.text[:200]}")
    generation_id = r.json().get("generationId")
    if not generation_id:
        raise Exception(f"Pas de generationId: {r.text}")
    for _ in range(60):
        time.sleep(5)
        poll = requests.get(f"https://public-api.gamma.app/v1.0/generations/{generation_id}",
                            headers={"X-API-KEY": GAMMA_API_KEY}, timeout=20)
        if poll.status_code == 200:
            result = poll.json()
            if result.get("status") == "completed":
                return result.get("gammaUrl", "")
            elif result.get("status") == "failed":
                raise Exception(f"Generation echouee: {result}")
    raise Exception("Timeout apres 5 minutes.")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
