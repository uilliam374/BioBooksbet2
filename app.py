import os
import psycopg
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# =========================================================
# CONFIGURAÇÃO BÁSICA
# =========================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")

DATABASE_URL = os.environ.get("DATABASE_URL")
INIT_DB = os.environ.get("INIT_DB", "false").lower() == "true"

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
# INIT DB + ADMIN (RODA SÓ SE INIT_DB=true)
# =========================================================

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

def create_admin_if_not_exists():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE username = %s",
                ("admin",)
            )
            exists = cur.fetchone()

            if exists:
                return

            cur.execute("""
                INSERT INTO users (username, password, balance)
                VALUES (%s, %s, %s)
            """, (
                "admin",
                generate_password_hash("7D"),
                0
            ))
            conn.commit()

if INIT_DB:
    init_db()
    create_admin_if_not_exists()

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
                    "SELECT id, password FROM users WHERE username = %s",
                    (username,)
                )
                user = cur.fetchone()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            return redirect(url_for("index"))

        return "Login inválido", 401

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =========================================================
# GHOSTSPAY – WEBHOOK
# =========================================================

@app.route("/webhook/ghostspay", methods=["POST"])
def ghostspay_webhook():
    data = request.json

    # 👉 Aqui você valida assinatura usando GHOSTSPAY_WEBHOOK_SECRET
    # 👉 Depois processa pagamento, atualiza saldo etc.

    return jsonify({"status": "ok"})

# =========================================================
# HEALTHCHECK (RENDER)
# =========================================================

@app.route("/health")
def health():
    return "OK", 200