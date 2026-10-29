from __future__ import annotations

import hmac
import os
import secrets
from datetime import datetime
from functools import wraps

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

db = SQLAlchemy()


class Citation(db.Model):
    # Keep the original table/column names so the existing citations database remains usable.
    __tablename__ = "citation"

    id = db.Column(db.Integer, primary_key=True)
    citation = db.Column(db.String(500), nullable=False)
    auteur = db.Column(db.String(100), nullable=False)
    tags = db.Column(db.String(200), nullable=False, default="")
    date_creation = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "citation": self.citation,
            "auteur": self.auteur,
            "tags": [tag.strip() for tag in (self.tags or "").split(",") if tag.strip()],
            "date_creation": self.date_creation.isoformat() if self.date_creation else None,
        }


def _database_url():
    url = os.getenv("DATABASE_URL", "sqlite:///citations.db").strip()
    # Flask-SQLAlchemy resolves relative SQLite URLs from the instance folder.
    # Normalize the old "instance/<file>" form to avoid instance/instance/<file>.
    if url.startswith("sqlite:///instance/"):
        url = url.replace("sqlite:///instance/", "sqlite:///", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _error(message, status):
    return jsonify({"erreur": message}), status


def _payload():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _normalize_tags(value):
    if value is None:
        return "", None
    if isinstance(value, str):
        tags = value.split(",")
    elif isinstance(value, list) and all(isinstance(tag, str) for tag in value):
        tags = value
    else:
        return None, "Les tags doivent être une liste de textes."

    cleaned = []
    for tag in tags:
        normalized = tag.strip().lstrip("#")
        if normalized and normalized.casefold() not in {item.casefold() for item in cleaned}:
            if len(normalized) > 40:
                return None, "Chaque tag doit contenir au maximum 40 caractères."
            cleaned.append(normalized)
    if len(cleaned) > 12:
        return None, "Une citation peut contenir au maximum 12 tags."
    result = ",".join(cleaned)
    if len(result) > 200:
        return None, "La liste de tags est trop longue."
    return result, None


def _citation_fields(data, partial=False):
    if data is None:
        return None, "Le corps de la requête doit être un objet JSON."
    values = {}

    if not partial or "citation" in data:
        quote = data.get("citation")
        if not isinstance(quote, str) or not quote.strip():
            return None, "Le texte de la citation est obligatoire."
        if len(quote.strip()) > 500:
            return None, "La citation ne peut pas dépasser 500 caractères."
        values["citation"] = quote.strip()

    if not partial or "auteur" in data:
        author = data.get("auteur")
        if not isinstance(author, str) or not author.strip():
            return None, "Le nom de l’auteur est obligatoire."
        if len(author.strip()) > 100:
            return None, "Le nom de l’auteur ne peut pas dépasser 100 caractères."
        values["auteur"] = author.strip()

    if not partial or "tags" in data:
        tags, error = _normalize_tags(data.get("tags", []))
        if error:
            return None, error
        values["tags"] = tags

    if partial and not values:
        return None, "Aucun champ à modifier n’a été fourni."
    return values, None


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=_database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        API_TOKEN=os.getenv("API_TOKEN", "").strip(),
        SKIP_SCRAPING=os.getenv("SKIP_SCRAPING", "1").lower() in {"1", "true", "yes"},
        DEBUG=os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"},
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'",
        )
        return response

    def token_required(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            expected = app.config.get("API_TOKEN", "")
            if not expected:
                return _error("Les actions d’administration ne sont pas configurées.", 503)
            authorization = request.headers.get("Authorization", "")
            supplied = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
            if not supplied:
                return _error("Jeton d’authentification manquant.", 401)
            if not hmac.compare_digest(supplied, expected):
                return _error("Jeton invalide.", 403)
            return view(*args, **kwargs)

        return decorated

    with app.app_context():
        db.create_all()

    @app.get("/")
    def index():
        return render_template("index.html", page_title="Le carnet des citations")

    @app.get("/api/auth/check")
    @token_required
    def check_token():
        return jsonify({"authenticated": True})

    @app.get("/api/citations")
    def get_citations():
        query = select(Citation)
        author = request.args.get("auteur", "").strip()[:100]
        tag = request.args.get("tag", "").strip().lstrip("#")[:40]
        keyword = (request.args.get("mot_cle") or request.args.get("q") or "").strip()[:120]

        if author:
            escaped = author.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Citation.auteur.ilike(f"%{escaped}%", escape="\\"))
        if tag:
            escaped_tag = tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Citation.tags.ilike(f"%{escaped_tag}%", escape="\\"))
        if keyword:
            escaped_keyword = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped_keyword}%"
            query = query.where(or_(Citation.citation.ilike(pattern, escape="\\"), Citation.auteur.ilike(pattern, escape="\\")))

        sort = request.args.get("sort", "recent")
        ordering = [Citation.auteur.asc(), Citation.id.desc()] if sort == "author" else [Citation.date_creation.desc(), Citation.id.desc()]
        query = query.order_by(*ordering)

        # The original endpoint still returns a JSON list. Pagination is opt-in.
        if "page" not in request.args and "per_page" not in request.args:
            citations = db.session.scalars(query).all()
            return jsonify([citation.to_dict() for citation in citations])

        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(60, max(1, request.args.get("per_page", 12, type=int)))
        total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        citations = db.session.scalars(query.offset((page - 1) * per_page).limit(per_page)).all()
        return jsonify({
            "items": [citation.to_dict() for citation in citations],
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        })

    @app.get("/api/citations/<int:cit_id>")
    def get_citation_by_id(cit_id):
        citation = db.session.get(Citation, cit_id)
        if not citation:
            return _error("Citation introuvable.", 404)
        return jsonify(citation.to_dict())

    @app.post("/api/citations")
    @token_required
    def create_citation():
        fields, error = _citation_fields(_payload())
        if error:
            return _error(error, 400)
        citation = Citation(**fields)
        db.session.add(citation)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Échec de création d’une citation.")
            return _error("La citation n’a pas pu être enregistrée.", 500)
        return jsonify(citation.to_dict()), 201

    @app.put("/api/citations/<int:cit_id>")
    @token_required
    def update_citation(cit_id):
        citation = db.session.get(Citation, cit_id)
        if not citation:
            return _error("Citation introuvable.", 404)
        fields, error = _citation_fields(_payload(), partial=True)
        if error:
            return _error(error, 400)
        for key, value in fields.items():
            setattr(citation, key, value)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Échec de modification d’une citation.")
            return _error("La citation n’a pas pu être modifiée.", 500)
        return jsonify(citation.to_dict())

    @app.delete("/api/citations/<int:cit_id>")
    @token_required
    def delete_citation(cit_id):
        citation = db.session.get(Citation, cit_id)
        if not citation:
            return _error("Citation introuvable.", 404)
        db.session.delete(citation)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Échec de suppression d’une citation.")
            return _error("La citation n’a pas pu être supprimée.", 500)
        return jsonify({"message": "Citation supprimée."})

    @app.get("/api/stats")
    def get_stats():
        total = db.session.scalar(select(func.count(Citation.id))) or 0
        authors = db.session.execute(
            select(Citation.auteur, func.count(Citation.id)).group_by(Citation.auteur).order_by(func.count(Citation.id).desc())
        ).all()
        tag_counts = {}
        for raw_tags in db.session.scalars(select(Citation.tags)).all():
            for tag in (raw_tags or "").split(","):
                normalized = tag.strip()
                if normalized:
                    tag_counts[normalized] = tag_counts.get(normalized, 0) + 1
        return jsonify({
            "total_citations": total,
            "citations_par_auteur": {author: count for author, count in authors},
            "tags_populaires": [
                {"tag": tag, "count": count}
                for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:10]
            ],
        })

    @app.get("/health")
    def health():
        try:
            db.session.execute(select(1))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Contrôle de santé de la base en échec.")
            return jsonify({"status": "error", "database": "unavailable"}), 503
        return jsonify({"status": "ok", "database": "ok"})

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return _error("Ressource introuvable.", 404)
        return render_template("404.html", page_title="Page introuvable"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.exception("Erreur interne du serveur.")
        if request.path.startswith("/api/"):
            return _error("Une erreur interne est survenue.", 500)
        return render_template("500.html", page_title="Erreur serveur"), 500

    return app


app = create_app()


def initialiser_base_donnees():
    """Charge des citations de démonstration depuis Quotes to Scrape si demandé."""
    if app.config["SKIP_SCRAPING"]:
        return
    with app.app_context():
        if db.session.scalar(select(func.count(Citation.id))):
            return
        try:
            for page in range(1, 4):
                response = requests.get(
                    f"https://quotes.toscrape.com/page/{page}/",
                    headers={"User-Agent": "LeCarnetCitations/1.0"},
                    timeout=8,
                )
                if response.status_code != 200:
                    continue
                soup = BeautifulSoup(response.text, "html.parser")
                for quote in soup.select("div.quote"):
                    text = quote.select_one("span.text")
                    author = quote.select_one("small.author")
                    if not text or not author:
                        continue
                    tags = [tag.get_text(strip=True) for tag in quote.select("a.tag")]
                    db.session.add(Citation(citation=text.get_text(strip=True)[:500], auteur=author.get_text(strip=True)[:100], tags=",".join(tags)[:200]))
                db.session.commit()
        except (requests.RequestException, SQLAlchemyError):
            db.session.rollback()
            app.logger.exception("Impossible de récupérer les citations de démonstration.")


if __name__ == "__main__":
    if not app.config["SKIP_SCRAPING"]:
        initialiser_base_donnees()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=app.config["DEBUG"])
