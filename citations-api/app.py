import os
from flask import Flask, render_template, send_from_directory, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    favicon_path = os.path.join(app.root_path, "static", "favicon.ico")
    if os.path.exists(favicon_path):
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon"
        )
    return "", 204

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.errorhandler(404)
def not_found(error):
    try:
        return render_template("404.html"), 404
    except Exception:
        return "Page not found", 404

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )