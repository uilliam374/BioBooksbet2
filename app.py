import os
import psycopg
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

# =========================================================
# CONFIGURAÇÃO BÁSICA
# =========================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")

DATABASE_URL = os.environ.get("DATABASE_URL")

# =========================================================
# GHOSTSPAY (ENV VARS)
# =========================================================

GHOSTSPAY_API_KEY = os.environ.get("GHOSTSPAY_API_KEY")
GHOSTSPAY_COMPANY_ID = os.environ.get("GHOSTSPAY_COMPANY_ID")
GHOSTSPAY_WEBHOOK_SECRET = os.environ.get("GHOSTSPAY_WEBHOOK_SECRET")

# =========================================================
# DATABASE (psycopg v3)
# =========================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurada")
    return psycopg.connect(DATABASE_URL, sslmode="require")

# =========================================================
# INIT DB (opcional – só se INIT_DB=true)
# =========================================================

INIT_DB = os.environ.get("INIT_DB", "false").lower() == "true"

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    balance NUMERIC DEFAULT 0
                );
            """)
            conn.commit()

if INIT_DB:
    init_db()

# =========================================================
# ROTAS
# =========================================================

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM users WHERE username=%s AND password=%s",
                    (username, password)
                )
                user = cur.fetchone()

        if user:
            session["user_id"] = user[0]
            return redirect(url_for("index"))

        return "Login inválido"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =========================================================
# GHOSTSPAY – EXEMPLO DE ENDPOINT
# =========================================================

@app.route("/ghostspay/webhook", methods=["POST"])
def ghostspay_webhook():
    data = request.json
    # Aqui você valida assinatura e processa pagamento
    return jsonify({"status": "ok"})

# =========================================================
# HEALTHCHECK (RENDER)
# =========================================================

@app.route("/health")
def health():
    return "OK", 200

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

@app.route("/create-admin")
def create_admin():
    from werkzeug.security import generate_password_hash
    from models import User, db

    # MUDE ESSES DADOS AGORA
    username = "admin"
    email = "admin@admin.com"
    password = "7D"

    # verifica se já existe admin
    existing = User.query.filter_by(username=username).first()
    if existing:
        return "Admin já existe", 400

    admin = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        is_admin=True
    )

    db.session.add(admin)
    db.session.commit()

    return "Admin criado com sucesso"


