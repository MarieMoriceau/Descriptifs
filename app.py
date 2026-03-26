#!/usr/bin/env python3
"""
Equation SIE — PDF → Gamma
Version synchrone : une seule requête, pas de polling
"""
import os, json, re, base64, tempfile, time, io
import requests
import pdfplumber
from pypdf import PdfReader
from PIL import Image
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

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
<title>Equation SIE — PDF → Gamma</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --gold: #C9A84C; --gold-light: #E8D5A3; --dark: #1A1A1A; --mid: #2D2D2D;
    --surface: #242424; --text: #F0EDE8; --muted: #888; --success: #4CAF7D; --error: #E05252;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--dark); color: var(--text); font-family: 'DM Sans', sans-serif; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2rem; }
  .header { text-align: center; margin-bottom: 3rem; }
  .logo { font-family: 'Playfair Display', serif; font-size: 1rem; letter-spacing: 0.3em; text-transform: uppercase; color: var(--gold); margin-bottom: 0.5rem; }
  h1 { font-family: 'Playfair Display', serif; font-size: 2.4rem; font-weight: 400; line-height: 1.2; }
  h1 span { color: var(--gold); }
  .subtitle { color: var(--muted); font-size: 0.95rem; margin-top: 0.75rem; font-weight: 300; }
  .card { background: var(--surface); border: 1px solid #333; border-radius: 16px; padding: 2.5rem; width: 100%; max-width: 560px; }
  .drop-zone { border: 2px dashed #3D3D3D; border-radius: 12px; padding: 3rem 2rem; text-align: center; cursor: pointer; transition: all 0.3s; position: relative; background: var(--mid); }
  .drop-zone:hover, .drop-zone.dragover { border-color: var(--gold); background: #2A2520; }
  .drop-icon { font-size: 2.5rem; margin-bottom: 1rem; display: block; }
  .drop-zone h3 { font-weight: 500; font-size: 1rem; margin-bottom: 0.4rem; }
  .drop-zone p { color: var(--muted); font-size: 0.85rem; }
  .drop-zone input[type=file] { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }
  .file-selected { display: none; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem; background: #2A2520; border: 1px solid var(--gold); border-radius: 8px; margin-top: 1rem; font-size: 0.9rem; }
  .file-selected.visible { display: flex; }
  .file-name { flex: 1; color: var(--gold-light); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .btn { width: 100%; padding: 1rem; background: var(--gold); color: var(--dark); border: none; border-radius: 10px; font-family: 'DM Sans', sans-serif; font-size: 1rem; font-weight: 600; cursor: pointer; margin-top: 1.5rem; transition: all 0.2s; }
  .btn:hover { background: var(--gold-light); transform: translateY(-1px); }
  .btn:disabled { background: #444; color: #777; cursor: not-allowed; transform: none; }
  .loading { display: none; text-align: center; margin-top: 1.5rem; padding: 1.5rem; background: var(--mid); border-radius: 10px; }
  .loading.visible { display: block; }
  .spinner { width: 40px; height: 40px; border: 3px solid #333; border-top-color: var(--gold); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 1rem; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading p { color: var(--muted); font-size: 0.9rem; }
  .loading strong { color: var(--gold); display: block; margin-bottom: 0.5rem; }
  .result { display: none; margin-top: 1.5rem; padding: 1.25rem; background: #1A2E1E; border: 1px solid var(--success); border-radius: 10px; text-align: center; }
  .result.visible { display: block; }
  .result-icon { font-size: 2rem; margin-bottom: 0.5rem; }
  .result h3 { color: var(--success); font-size: 1rem; margin-bottom: 0.75rem; }
  .result a { display: inline-block; padding: 0.6rem 1.5rem; background: var(--success); color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 0.9rem; }
  .error-box { display: none; margin-top: 1.5rem; padding: 1rem; background: #2E1A1A; border: 1px solid var(--error); border-radius: 10px; color: var(--error); font-size: 0.875rem; text-align: center; }
  .error-box.visible { display: block; }
  .new-btn { background: none; border: 1px solid #444; color: var(--muted); width: 100%; padding: 0.7rem; border-radius: 8px; font-family: 'DM Sans', sans-serif; font-size: 0.875rem; cursor: pointer; margin-top: 0.75rem; transition: all 0.2s; }
  .new-btn:hover { border-color: var(--gold); color: var(--gold); }
</style>
</head>
<body>
<div class="header">
  <div class="logo">Equation SIE</div>
  <h1>PDF <span>→</span> Gamma</h1>
  <p class="subtitle">Glissez un descriptif confrère — obtenez un Gamma en 3 minutes</p>
</div>
<div class="card">
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept=".pdf">
    <span class="drop-icon">📄</span>
    <h3>Déposez votre PDF ici</h3>
    <p>ou cliquez pour parcourir</p>
  </div>
  <div class="file-selected" id="fileSelected">
    <span>📎</span>
    <span class="file-name" id="fileName"></span>
  </div>
  <button class="btn" id="launchBtn" disabled onclick="launch()">Générer le Gamma</button>
  <div class="loading" id="loading">
    <div class="spinner"></div>
    <strong>Traitement en cours...</strong>
    <p>Extraction → Analyse IA → Upload photos → Génération Gamma<br>Environ 3 minutes, ne fermez pas cette page.</p>
  </div>
  <div class="result" id="result">
    <div class="result-icon">✅</div>
    <h3>Gamma créé avec succès !</h3>
    <a id="gammaLink" href="#" target="_blank">Ouvrir le Gamma →</a>
    <button class="new-btn" onclick="reset()">Traiter un autre PDF</button>
  </div>
  <div class="error-box" id="errorBox">
    <strong>Erreur</strong><br>
    <span id="errorMsg"></span>
    <button class="new-btn" onclick="reset()">Réessayer</button>
  </div>
</div>
<script>
let selectedFile = null;
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('dragover'); const f = e.dataTransfer.files[0]; if (f && f.name.endsWith('.pdf')) setFile(f); });
fileInput.addEventListener('change', e => { if (e.target.files[0]) setFile(e.target.files[0]); });
function setFile(f) { selectedFile = f; document.getElementById('fileName').textContent = f.name; document.getElementById('fileSelected').classList.add('visible'); document.getElementById('launchBtn').disabled = false; }
async function launch() {
  if (!selectedFile) return;
  document.getElementById('launchBtn').disabled = true;
  document.getElementById('loading').classList.add('visible');
  document.getElementById('result').classList.remove('visible');
  document.getElementById('errorBox').classList.remove('visible');
  const formData = new FormData();
  formData.append('pdf', selectedFile);
  try {
    const res = await fetch('/generate', { method: 'POST', body: formData, signal: AbortSignal.timeout(600000) });
    const data = await res.json();
    document.getElementById('loading').classList.remove('visible');
    if (data.url) { document.getElementById('gammaLink').href = data.url; document.getElementById('result').classList.add('visible'); }
    else { showError(data.error || 'Erreur inconnue'); }
  } catch(e) { document.getElementById('loading').classList.remove('visible'); showError('Délai dépassé ou erreur réseau. Réessayez.'); }
}
function showError(msg) { document.getElementById('errorMsg').textContent = msg; document.getElementById('errorBox').classList.add('visible'); document.getElementById('launchBtn').disabled = false; }
function reset() { selectedFile = null; fileInput.value = ''; document.getElementById('fileSelected').classList.remove('visible'); document.getElementById('loading').classList.remove('visible'); document.getElementById('result').classList.remove('visible'); document.getElementById('errorBox').classList.remove('visible'); document.getElementById('launchBtn').disabled = true; }
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/generate', methods=['POST'])
def generate():
    if 'pdf' not in request.files:
        return jsonify({'error': 'Pas de fichier PDF'}), 400
    f = request.files['pdf']
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    f.save(tmp.name)
    tmp.close()
    try:
        text = extract_text_from_pdf(tmp.name)
        info = parse_info_with_claude(text)
        plan_paths, plan_page_idxs = detect_plans_par_texte(tmp.name)
        photos = extract_photos(tmp.name, plan_page_idxs=plan_page_idxs)
        image_urls = []
        for path in photos[:10]:
            url = upload_image(path)
            if url: image_urls.append(url)
        plan_urls = []
        for pp in plan_paths:
            url = upload_image(pp)
            if url: plan_urls.append(url)
        maps_url = upload_maps_image(info["adresse"], info["code_postal"])
        prompt = build_prompt(info, image_urls, plan_urls=plan_urls, maps_url=maps_url)
        gamma_url = create_gamma(prompt)
        return jsonify({'url': gamma_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try: os.unlink(tmp.name)
        except: pass


def extract_text_from_pdf(pdf_path):
    try:
        from pdf2image import convert_from_path
        import pytesseract
        ocr_ok = True
    except ImportError:
        ocr_ok = False
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            t = (page.extract_text() or "").strip()
            if len(t) > 20:
                parts.append(t)
            elif ocr_ok:
                try:
                    imgs = convert_from_path(pdf_path, dpi=200, first_page=i+1, last_page=i+1)
                    if imgs:
                        t_ocr = pytesseract.image_to_string(imgs[0], lang="fra").strip()
                        if len(t_ocr) > 20:
                            parts.append(t_ocr)
                except Exception:
                    pass
    full_text = "\n\n".join(parts)
    if len(full_text) < 200 and ocr_ok:
        try:
            from pdf2image import convert_from_path
            import pytesseract
            imgs = convert_from_path(pdf_path, dpi=250, first_page=1, last_page=3)
            ocr_parts = [pytesseract.image_to_string(img, lang="fra").strip() for img in imgs if len(pytesseract.image_to_string(img, lang="fra").strip()) > 20]
            if ocr_parts: full_text = "\n\n".join(ocr_parts)
        except Exception:
            pass
    return full_text


def parse_info_with_claude(text):
    prompt = f"""Tu es un expert en immobilier de bureaux parisien.
Analyse ce descriptif et extrais les informations au format JSON strict. Si absent, mets null.
Code postal toujours format 750XX. Loyers en €/m²/an uniquement. Surfaces > 100m².
Divisibilite : "Non divisible" seulement si explicitement mentionné.

{{"adresse":"55 RUE D'AMSTERDAM","code_postal":"75008","surfaces":["1576 m²"],"loyers":["850 €/m²/an HT HC"],"disponibilite":"Juin 2026","divisibilite":"Divisible à partir de 484 m²","transports":["Gare Saint-Lazare - 1 min"],"prestations":["Climatisation","Fibre optique"],"description":"Description courte","confrere":"JLL","charges":"80 €/m²/an HT","impot_foncier":"25 €/m²/an HT","taxe_bureaux":"21 €/m²/an HT","teom":null,"bail":"3/6/9 ans","depot_garantie":"3 mois de loyer HT","regime_fiscal":"TVA"}}

Texte :
---
{text[:8000]}
---
Réponds UNIQUEMENT avec le JSON."""
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]},
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
                        val = float(sx.replace(" ","").replace(",",".").replace("m²","").replace("m2",""))
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
                        val = float(sx.replace(" ","").replace(",",".").replace("€","").replace("/m²/an","").replace("HTHC","").strip())
                        result.append(f"{int(val)} €/m²/an HT HC")
                    except:
                        result.append(sx if "€" in sx else sx)
                return result
            return {"adresse": s(data.get("adresse")).upper(), "code_postal": s(data.get("code_postal")),
                    "surfaces": norm_surfaces(data.get("surfaces")), "loyers": norm_loyers(data.get("loyers")),
                    "disponibilite": s(data.get("disponibilite")), "divisibilite": s(data.get("divisibilite")),
                    "transports": [s(x) for x in (data.get("transports") or []) if x],
                    "prestations": [s(x) for x in (data.get("prestations") or []) if x],
                    "description": s(data.get("description")), "confrere": s(data.get("confrere")),
                    "charges": s(data.get("charges"), "Nous consulter"),
                    "impot_foncier": s(data.get("impot_foncier"), "En cours de détermination"),
                    "taxe_bureaux": s(data.get("taxe_bureaux"), "En cours de détermination"),
                    "teom": s(data.get("teom"), "En cours de détermination"),
                    "bail": s(data.get("bail"), "3/6/9 ans"),
                    "depot_garantie": s(data.get("depot_garantie"), "3 mois de loyer HT HC"),
                    "regime_fiscal": s(data.get("regime_fiscal"), "TVA")}
    except Exception:
        pass
    return {"adresse": "", "code_postal": "", "surfaces": [], "loyers": [], "disponibilite": "",
            "divisibilite": "", "transports": [], "prestations": [], "description": "", "confrere": "",
            "charges": "Nous consulter", "impot_foncier": "En cours de détermination",
            "taxe_bureaux": "En cours de détermination", "teom": "En cours de détermination",
            "bail": "3/6/9 ans", "depot_garantie": "3 mois de loyer HT HC", "regime_fiscal": "TVA"}


def detect_plans_par_texte(pdf_path, min_kb=30):
    try:
        from pdf2image import convert_from_path
        import pytesseract
        ocr_ok = True
    except ImportError:
        ocr_ok = False
    reader = PdfReader(pdf_path)
    temp_dir = tempfile.mkdtemp()
    plan_paths = []
    plan_page_idxs = set()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            t = (page.extract_text() or "").strip()
            if len(t) < 20 and ocr_ok:
                try:
                    imgs = convert_from_path(pdf_path, dpi=150, first_page=i+1, last_page=i+1)
                    if imgs:
                        w, h = imgs[0].size
                        t = pytesseract.image_to_string(imgs[0].crop((0, 0, w, h // 3)), lang="fra").strip()
                except Exception:
                    pass
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


def extract_photos(pdf_path, plan_page_idxs=None, min_kb=20):
    reader = PdfReader(pdf_path)
    temp_dir = tempfile.mkdtemp()
    paths = []
    skip = plan_page_idxs or set()
    for pn, page in enumerate(reader.pages):
        if pn in skip: continue
        for idx, img in enumerate(page.images):
            if len(img.data) / 1024 < min_kb: continue
            try:
                pil = Image.open(io.BytesIO(img.data))
                w, h = pil.size
                if w < 200 or h < 150: continue
                path = os.path.join(temp_dir, f"photo_p{pn+1}_{idx}.jpg")
                pil.convert("RGB").save(path, "JPEG", quality=88)
                paths.append(path)
            except Exception: pass
    return paths


def upload_image(path):
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    r = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBB_API_KEY, "image": encoded}, timeout=30)
    return r.json()["data"]["url"] if r.status_code == 200 else None


def upload_maps_image(adresse, code_postal):
    if not adresse: return None
    adresse_complete = f"{adresse}, {code_postal} Paris, France"
    params = {"center": adresse_complete, "zoom": "16", "size": "800x600",
              "maptype": "roadmap", "markers": f"color:red|{adresse_complete}", "key": GOOGLE_MAPS_API_KEY}
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    try:
        r = requests.get(f"https://maps.googleapis.com/maps/api/staticmap?{query}", timeout=20)
        if r.status_code != 200: return None
        encoded = base64.b64encode(r.content).decode("utf-8")
        r2 = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBB_API_KEY, "image": encoded}, timeout=30)
        return r2.json()["data"]["url"] if r2.status_code == 200 else None
    except Exception: return None


def build_prompt(info, image_urls, plan_urls=None, maps_url=None):
    adresse  = info.get("adresse") or "Adresse a preciser"
    cp       = info.get("code_postal", "")
    surfaces = " / ".join(info.get("surfaces", [])) or "A preciser"
    loyers   = " | ".join(info.get("loyers", [])) or "Nous consulter"
    dispo    = info.get("disponibilite") or "A preciser"
    div      = info.get("divisibilite", "")
    desc     = info.get("description") or "Bureau de qualite dans un immeuble moderne."
    trans    = "\n".join(f"- {t}" for t in info.get("transports", [])) or "- A completer"
    prest    = "\n".join(f"- {p}" for p in info.get("prestations", [])) or "- A completer"
    photos   = ("PHOTOS :\n" + "\n".join(f"- {u}" for u in image_urls[:10])) if image_urls else ""
    plans    = ("PLANS :\n" + "\n".join(f"- {u}" for u in plan_urls)) if plan_urls else ""
    maps_s   = f"CARTE 300m :\n- {maps_url}" if maps_url else ""
    return f"""Utilise la structure exacte de ce template pour creer un nouveau descriptif immobilier.
Conserve le logo Equation SIE, la mise en page, et la derniere page de contact sans les modifier.
ADRESSE : {adresse}
LOCALISATION : {adresse}, {cp} PARIS
SURFACE : {surfaces}
DISPONIBILITE : {dispo}
{f"DIVISIBILITE : {div}" if div else ""}
DESCRIPTION : {desc}
TRANSPORTS : {trans}
PRESTATIONS : {prest}
PAGE 4 — COUTS RECURRENTS :
Loyer bureaux : {loyers}
Charges bureaux : {info.get('charges', 'Nous consulter')}
Impôt foncier : {info.get('impot_foncier', 'En cours de détermination')}
Taxe bureaux : {info.get('taxe_bureaux', 'En cours de détermination')}
TEOM : {info.get('teom', 'En cours de détermination')}
PAGE 4 — COUTS A L ENTREE :
Honoraires de location : A la charge du preneur
Frais de rédaction d'actes : A la charge du preneur
Frais d'état des lieux : A prévoir
PAGE 4 — DONNEES JURIDIQUES :
Bail : {info.get('bail', '3/6/9 ans')}
Régime fiscal : {info.get('regime_fiscal', 'TVA')}
Dépôt de garantie : {info.get('depot_garantie', '3 mois de loyer HT HC')}
Indexation annuelle : ILAT
Type de paiement : Trimestriel et d'avance
{photos}
{plans}
{maps_s}
TITRE : {adresse} — {cp} PARIS — {surfaces}
INSTRUCTIONS : Code postal toujours {cp}. Ne pas inclure logos confrères."""


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
                raise Exception(f"Génération échouée: {result}")
    raise Exception("Timeout après 5 minutes.")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
