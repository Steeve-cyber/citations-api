# Le Carnet — gestionnaire de citations

Le Carnet est une application Flask qui rassemble, recherche et organise des citations. Son interface éditoriale utilise une palette crème, terracotta et sauge, avec une mise en page responsive.

## Fonctions

- Consultation publique des citations avec recherche, filtres par thème et tri.
- Favoris locaux, copie rapide et citation mise à la une.
- Ajout, modification et suppression protégés par un jeton Bearer.
- Statistiques sur les citations, les auteurs et les thèmes.
- API REST conservant les routes historiques /api/citations, /api/citations/<id> et /api/stats.
- Chargement facultatif de citations de démonstration, désactivé par défaut.

## Lancer dans PyCharm ou PowerShell

Ouvrez le dossier du projet, puis dans son terminal :

~~~powershell
.\.venv\Scripts\python.exe app.py
~~~

Ouvrez ensuite http://127.0.0.1:5000.

Si les dépendances ne sont pas installées :

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

## Configuration

Le fichier .env existant n’a pas besoin d’être remplacé. Conservez ses valeurs et vérifiez seulement qu’il contient un API_TOKEN défini par vous. Sans jeton, la consultation fonctionne, mais l’espace éditeur reste désactivé.

| Variable | Rôle |
| --- | --- |
| DATABASE_URL | URL SQLAlchemy ; par défaut sqlite:///citations.db |
| API_TOKEN | Jeton Bearer pour les opérations d’écriture |
| SKIP_SCRAPING | 1 désactive la récupération web de démonstration ; 0 l’autorise |
| PORT | Port d’écoute fourni par l’hébergeur |

Le jeton n’est pas intégré au HTML. Dans l’application, le bouton Espace éditeur demande le jeton et le conserve uniquement dans sessionStorage pour l’onglet courant.

Si une ancienne configuration contient DATABASE_URL=sqlite:///instance/citations.db, l’application normalise ce chemin vers le dossier instance déjà utilisé par Flask-SQLAlchemy. Il n’est pas nécessaire de modifier le .env.

## Données existantes

Le modèle conserve la table SQLite historique citation et ses colonnes citation, auteur, tags et date_creation. db.create_all() ne supprime ni ne remplace les tables existantes. Les tables de l’essai précédent de gestion de projet, si elles ont déjà été créées, restent simplement inutilisées.

L’import de citations depuis Quotes to Scrape est facultatif et ne s’exécute que lorsque SKIP_SCRAPING=0, que la base ne contient encore aucune citation et que l’application est lancée avec python app.py.

## API

- GET /api/citations — liste JSON historique ; filtres auteur, tag, mot_cle ou q.
- GET /api/citations?page=1&per_page=12 — variante paginée.
- GET /api/citations/<id> — détail.
- GET /api/stats — nombre de citations et répartition par auteur.
- POST /api/citations, PUT /api/citations/<id>, DELETE /api/citations/<id> — actions protégées par Authorization: Bearer <API_TOKEN>.
- GET /health — contrôle de disponibilité.

Le Procfile démarre Gunicorn pour le déploiement.
