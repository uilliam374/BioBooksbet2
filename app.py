import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg
import requests
from werkzeug.security import generate_password_hash, check_password_hash

# ==============================
# CONFIGURAÇÃO BÁSICA
# ==============================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

DATABASE_URL = os.environ.get("DATABASE_URL")

# GhostsPay
GHOSTSPAY_API_KEY = os.environ.get("GHOSTSPAY_API_KEY")
GHOSTSPAY_COMPANY_ID = os.environ.get("GHOSTSPAY_COMPANY_ID")
GHOSTSPAY_WEBHOOK_SECRET = os.environ.get("GHOSTSPAY_WEBHOOK_SECRET")

INIT_DB = os.environ.get("INIT_DB", "false").lower() == "true"

# ==============================
# CONEXÃO COM O BANCO
# ==============================

def get_db():
    return psycopg.connect(DATABASE_URL)

# ==============================
# INIT DB (RODA APENAS 1 VEZ)
# ==============================

def init_db():
    with open("schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()

if INIT_DB:
    init_db()

# ==============================
# ROTAS PRINCIPAIS
# ==============================

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")

# ==============================
# AUTH
# ==============================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (email, password, balance) VALUES (%s, %s, 0)",
                    (email, password),
                )
            conn.commit()

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, password FROM users WHERE email = %s",
                    (email,),
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

# ==============================
# DEPÓSITO (GhostsPay)
# ==============================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        amount = float(request.form["amount"])

        payload = {
            "amount": amount,
            "company_id": GHOSTSPAY_COMPANY_ID,
            "description": "Depósito Cassino",
        }

        headers = {
            "Authorization": f"Bearer {GHOSTSPAY_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            "https://api.ghostspay.com/v1/payments",
            headers=headers,
            json=payload,
            timeout=30,
        )

        data = response.json()
        return redirect(data["payment_url"])

    return render_template("deposit.html")

# ==============================
# WEBHOOK GhostsPay
# ==============================

@app.route("/webhook/ghostspay", methods=["POST"])
def ghosts_pay_webhook():
    signature = request.headers.get("X-Signature")

    if signature != GHOSTSPAY_WEBHOOK_SECRET:
        return "Unauthorized", 401

    event = request.json

    if event.get("status") == "paid":
        user_id = event["metadata"]["user_id"]
        amount = float(event["amount"])

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE id = %s",
                    (amount, user_id),
                )
            conn.commit()

    return jsonify({"status": "ok"})

# ==============================
# JOGOS (EXEMPLO)
# ==============================

@app.route("/game/<name>")
def game(name):
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(f"game_{name}.html")

# ==============================
# START
# ==============================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)


