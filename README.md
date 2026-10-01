# Descriptifs — PDF → Gamma (Équation SIE)

Outil interne qui transforme automatiquement le PDF d'un confrère (JLL, BNP, CBRE…)
en un **descriptif Gamma éditable**, au format du MODELE 369 d'Équation.

Application en ligne : https://descriptifs.onrender.com

---

## Ce que fait l'outil

À partir d'un PDF déposé, il produit un Gamma fini qui reprend le modèle Équation :

- **Couverture** avec le bandeau aubergine conservé
- **Photos réelles** du bien (toutes, dédoublonnées — pas de doublon ni de triplon)
- **Plans d'étage** (les vrais plans ; les cartes et pages de conditions sont écartées)
- **Conditions financières, coûts à l'entrée, données juridiques** (3 cartes du modèle)
- **Tableau des surfaces**, de l'étage le plus haut au plus bas
- **Carte de situation** OpenStreetMap avec un cercle de 300 m autour du bien
- **Contacts de l'équipe Équation** (remplacent ceux du confrère)

Il gère les trois grands formats de confrères :
- plaquettes **texte** (JLL),
- plaquettes **texte longues** (BNP),
- plaquettes **tout en image** (CBRE) — lues par Claude en vision.

---

## Comment l'utiliser (au quotidien)

1. Ouvrir https://descriptifs.onrender.com
2. Glisser un ou plusieurs PDF de confrère
3. Cliquer sur « Générer les Gammas »
4. Patienter ~2–3 min par descriptif (le message « Génération Gamma » reste affiché, c'est normal)
5. Cliquer sur « Ouvrir le Gamma » → le descriptif est dans l'espace Gamma, éditable sans code

---

## Fichiers du dépôt

Seuls ces fichiers servent à l'application :

| Fichier            | Rôle                                                        |
|--------------------|-------------------------------------------------------------|
| `app.py`           | Toute la logique (extraction, photos, plans, carte, Gamma)  |
| `requirements.txt` | Les librairies à installer                                   |
| `render.yaml`      | Configuration de déploiement Render                          |
| `README.md`        | Ce fichier                                                   |

Les autres fichiers éventuels (scripts de prospection, etc.) n'ont aucun effet sur l'outil.

---

## Déployer une mise à jour (en 3 étapes)

> ⚠️ Ne jamais « tout remplacer d'un coup ». On ne touche qu'aux fichiers indiqués.

1. Sur GitHub, ouvrir **`app.py`** → crayon ✏️ → tout sélectionner, effacer, coller la nouvelle version → **Commit changes**.
   (Et seulement si demandé : faire pareil pour `requirements.txt`.)
2. Render redéploie automatiquement (~3 min).
3. Vérifier : ouvrir **https://descriptifs.onrender.com/version** — le numéro de version doit correspondre à la nouvelle. Puis relancer un descriptif pour contrôler.

---

## Réglages techniques

- Clé Claude : variable d'environnement `ANTHROPIC_API_KEY` (dans les réglages Render).
- Modèle Claude : `CLAUDE_MODEL` (par défaut `claude-haiku-4-5`).
- Les autres clés (Gamma, hébergement d'images, thème/modèle Gamma) sont dans `app.py`.
