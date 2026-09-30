# Carte prospection terrain

Carte des immeubles visités par chaque négociateur, lue en direct dans la base Notion
« 🚶🏻‍♂️ Prospection terrain ». Chaque ouverture de la page relit Notion (cache 60 s) et la page
se rafraîchit toute seule toutes les 2 minutes.

- Pastille = un immeuble, chiffre = nombre de relevés Notion à cette adresse
- Couleur = négo (camembert si plusieurs négos sont passés)
- Panneau de gauche : négo → rues → immeubles, filtre période, recherche société/rue
- Adresses introuvables listées en bas, avec lien vers la fiche Notion à corriger

## Onglet « Secteurs »

Choisis un négo : son ou ses secteurs s'affichent en pointillés, avec les immeubles qu'il a
lui-même déjà visités à l'intérieur :

- 🟢 vert : dernière visite il y a moins de 2 mois
- 🔴 rouge : plus ancien, donc à revoir

Les secteurs sont décrits dans `secteurs.json` (voir `secteurs.exemple.json`) : un nom et un contour
(liste de points latitude/longitude). Pour changer la durée « vert », ajoute la variable
`FRESH_MONTHS` sur Render (2 par défaut).

## Déploiement (≈ 10 min)

1. **Token Notion** : notion.so/profile/integrations → réutilise ton intégration existante
   (ou crée « Carte prospection », lecture seule). Dans la base Prospection terrain :
   `•••` → *Connexions* → ajoute l'intégration.
2. **GitHub** : crée le dépôt `MarieMoriceau/carte-prospection`, glisse-y tous les fichiers de ce dossier.
3. **Render** : *New → Blueprint* → choisis le dépôt (le `render.yaml` fait le reste).
   Renseigne les deux variables demandées :
   - `NOTION_TOKEN` = le secret de l'intégration (`ntn_…`)
   - `APP_PASSWORD` = un mot de passe partagé avec les négos (identifiant : n'importe quoi)
4. Ouvre l'URL `https://carte-prospection.onrender.com` → c'est en ligne.

## Bon à savoir

- Offre Free : la page met ~30 s à se réveiller après 15 min d'inactivité.
- Le géocodage (BAN) est mis en cache ; au réveil, il refait les ~100 adresses (quelques secondes).
- Fond de carte : Plan IGN (gratuit, sans clé).
