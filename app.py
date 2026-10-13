import os
from functools import wraps
from flask import Flask, jsonify, render_template_string, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration de la base de données PostgreSQL
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///citations.db')
# Fix pour PostgreSQL sur Render (postgresql:// → postgresql+psycopg2://)
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Token d'authentification
API_TOKEN = os.getenv('API_TOKEN', 'secret-token-123')


# --- MODÈLE DE DONNÉES ---
class Citation(db.Model):
    """Modèle pour représenter une citation dans PostgreSQL."""
    id = db.Column(db.Integer, primary_key=True)
    citation = db.Column(db.String(500), nullable=False)
    auteur = db.Column(db.String(100), nullable=False)
    tags = db.Column(db.String(200), default="")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "citation": self.citation,
            "auteur": self.auteur,
            "tags": self.tags.split(",") if self.tags else [],
            "date_creation": self.date_creation.isoformat()
        }


# Créer les tables
with app.app_context():
    db.create_all()


def initialiser_base_donnees():
    """Scrape et charge les citations si la BD est vide."""
    with app.app_context():
        if Citation.query.count() == 0:
            print("Base de données vide. Scraping en cours...")
            base_url = "https://quotes.toscrape.com/page/{page}/"
            headers = {"User-Agent": "Mozilla/5.0"}

            for page in range(1, 4):
                url = base_url.format(page=page)
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                quotes = soup.find_all("div", class_="quote")

                for quote in quotes:
                    text = quote.find("span", class_="text").get_text(strip=True)
                    author = quote.find("small", class_="author").get_text(strip=True)
                    tags = [tag.get_text(strip=True) for tag in quote.find_all("a", class_="tag")]

                    nouvelle_citation = Citation(
                        citation=text,
                        auteur=author,
                        tags=",".join(tags)
                    )
                    db.session.add(nouvelle_citation)

                db.session.commit()
                print(f"Page {page} scrappée avec succès.")

            print(f"Total citations chargées : {Citation.query.count()}")


# Décorateur d'authentification
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"erreur": "Jeton d'authentification manquant"}), 401
        token = auth_header.split(" ")[1]
        if token != API_TOKEN:
            return jsonify({"erreur": "Jeton invalide"}), 403
        return f(*args, **kwargs)

    return decorated


# --- ROUTES API REST ---

@app.route("/api/citations", methods=["GET"])
def get_citations():
    auteur = request.args.get("auteur")
    tag = request.args.get("tag")
    mot_cle = request.args.get("mot_cle")

    query = Citation.query

    if auteur:
        query = query.filter(Citation.auteur.ilike(f"%{auteur}%"))
    if tag:
        query = query.filter(Citation.tags.ilike(f"%{tag}%"))
    if mot_cle:
        query = query.filter(Citation.citation.ilike(f"%{mot_cle}%"))

    citations = query.all()
    return jsonify([c.to_dict() for c in citations])


@app.route("/api/citations/<int:cit_id>", methods=["GET"])
def get_citation_by_id(cit_id):
    citation = Citation.query.get(cit_id)
    if not citation:
        return jsonify({"erreur": "Citation introuvable"}), 404
    return jsonify(citation.to_dict())


@app.route("/api/citations", methods=["POST"])
@token_required
def create_citation():
    data = request.get_json()
    if not data or "citation" not in data or "auteur" not in data:
        return jsonify({"erreur": "Les champs 'citation' et 'auteur' sont requis"}), 400

    nouvelle_citation = Citation(
        citation=data["citation"],
        auteur=data["auteur"],
        tags=",".join(data.get("tags", []))
    )
    db.session.add(nouvelle_citation)
    db.session.commit()
    return jsonify(nouvelle_citation.to_dict()), 201


@app.route("/api/citations/<int:cit_id>", methods=["PUT"])
@token_required
def update_citation(cit_id):
    citation = Citation.query.get(cit_id)
    if not citation:
        return jsonify({"erreur": "Citation introuvable"}), 404

    data = request.get_json()
    if "citation" in data:
        citation.citation = data["citation"]
    if "auteur" in data:
        citation.auteur = data["auteur"]
    if "tags" in data:
        citation.tags = ",".join(data["tags"])

    db.session.commit()
    return jsonify(citation.to_dict())


@app.route("/api/citations/<int:cit_id>", methods=["DELETE"])
@token_required
def delete_citation(cit_id):
    citation = Citation.query.get(cit_id)
    if not citation:
        return jsonify({"erreur": "Citation introuvable"}), 404

    db.session.delete(citation)
    db.session.commit()
    return jsonify({"message": "Citation supprimée"}), 200


@app.route("/api/stats", methods=["GET"])
def get_stats():
    total = Citation.query.count()
    auteurs = db.session.query(Citation.auteur, db.func.count(Citation.id)).group_by(Citation.auteur).all()

    return jsonify({
        "total_citations": total,
        "citations_par_auteur": {auteur: count for auteur, count in auteurs}
    })


# --- FRONTEND ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Gestionnaire de Citations</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 30px auto; padding: 20px; background: #f4f4f9; }
        h1 { color: #2c3e50; }
        .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        input, button { padding: 8px; margin: 5px 0; font-size: 14px; }
        button { background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #2980b9; }
        .danger { background: #e74c3c; }
        .danger:hover { background: #c0392b; }
        .tag { background: #ecf0f1; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-right: 4px; }
        ul { padding-left: 20px; }
        li { margin-bottom: 10px; }
        .online { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🌐 Gestionnaire de Citations (API & Frontend)</h1>
    <p class="online">✅ En ligne sur Render avec PostgreSQL</p>

    <div class="card">
        <h2>Authentification (Token API)</h2>
        <label>Token Bearer : </label>
        <input type="text" id="apiToken" value="secret-token-123" style="width: 250px;">
    </div>

    <div class="card">
        <h2>Statistiques & Actions</h2>
        <button onclick="chargerStats()">Voir les Statistiques</button>
        <button onclick="chargerCitations()">Rafraîchir la liste</button>
        <div id="statsResult" style="margin-top: 10px; font-weight: bold;"></div>
    </div>

    <div class="card">
        <h2>Ajouter une Citation (Protégé)</h2>
        <input type="text" id="newCitation" placeholder="Texte de la citation" style="width: 100%;"><br>
        <input type="text" id="newAuteur" placeholder="Auteur"><br>
        <input type="text" id="newTags" placeholder="Tags (séparés par des virgules)"><br>
        <button onclick="ajouterCitation()">Ajouter</button>
    </div>

    <div class="card">
        <h2>Liste des Citations</h2>
        <input type="text" id="searchInput" placeholder="Filtrer par auteur ou mot-clé..." onkeyup="filtrerListe()" style="width: 100%;">
        <ul id="citationsList">Chargement...</ul>
    </div>

    <script>
        let toutesLesCitations = [];

        async function chargerCitations() {
            const res = await fetch('/api/citations');
            toutesLesCitations = await res.json();
            afficherCitations(toutesLesCitations);
        }

        function afficherCitations(citations) {
            const list = document.getElementById('citationsList');
            list.innerHTML = '';
            if (citations.length === 0) {
                list.innerHTML = '<li>Aucune citation trouvée.</li>';
                return;
            }
            citations.forEach(q => {
                let tagsHtml = (q.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');
                let li = document.createElement('li');
                li.innerHTML = `<strong>#${q.id} - ${q.auteur}</strong>: "${q.citation}" <br>${tagsHtml} 
                                <button class="danger" onclick="supprimerCitation(${q.id})">Supprimer</button>`;
                list.appendChild(li);
            });
        }

        async function chargerStats() {
            const res = await fetch('/api/stats');
            const stats = await res.json();
            const auteurs = Object.keys(stats.citations_par_auteur).length;
            document.getElementById('statsResult').innerText = `Total citations : ${stats.total_citations} | Auteurs uniques : ${auteurs}`;
        }

        async function ajouterCitation() {
            const token = document.getElementById('apiToken').value;
            const citation = document.getElementById('newCitation').value;
            const auteur = document.getElementById('newAuteur').value;
            const tags = document.getElementById('newTags').value.split(',').map(t => t.trim()).filter(t => t);

            if (!citation || !auteur) {
                alert('Veuillez remplir tous les champs.');
                return;
            }

            const res = await fetch('/api/citations', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify({ citation, auteur, tags })
            });

            if (res.ok) {
                alert('Citation ajoutée avec succès !');
                document.getElementById('newCitation').value = '';
                document.getElementById('newAuteur').value = '';
                document.getElementById('newTags').value = '';
                chargerCitations();
            } else {
                const err = await res.json();
                alert('Erreur : ' + (err.erreur || 'Action non autorisée'));
            }
        }

        async function supprimerCitation(id) {
            const token = document.getElementById('apiToken').value;
            if (!confirm('Voulez-vous vraiment supprimer cette citation ?')) return;

            const res = await fetch(`/api/citations/${id}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': 'Bearer ' + token
                }
            });

            if (res.ok) {
                chargerCitations();
            } else {
                const err = await res.json();
                alert('Erreur : ' + (err.erreur || 'Action non autorisée'));
            }
        }

        function filtrerListe() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const filtrees = toutesLesCitations.filter(q => 
                q.citation.toLowerCase().includes(query) || q.auteur.toLowerCase().includes(query)
            );
            afficherCitations(filtrees);
        }

        chargerCitations();
        chargerStats();
    </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    initialiser_base_donnees()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='127.0.0.1', port=port)