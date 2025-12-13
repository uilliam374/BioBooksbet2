import os
import json
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from datetime import datetime

# =====================================================
# APP
# =====================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# =====================================================
# DATABASE (Postgres Render / SQLite local)
# =====================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if DATABASE_URL:
        url = DATABASE_URL.replace("postgres://", "postgresql://")
        return psycopg2.connect(url, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect("casino.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def query(sql, params=(), fetchone=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    data = cur.fetchone() if fetchone else cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    return data


def init_db():
    conn = get_db()
    cur = conn.cursor()
    with open("schema.sql", "r", encoding="utf-8") as f:
        cur.execute(f.read())
    conn.commit()
    cur.close()
    conn.close()

# =====================================================
# GHOSTSPAY CONFIG
# =====================================================

GHOSTSPAY_SECRET = os.environ.get("GHOSTSPAY_SECRET_KEY")
GHOSTSPAY_COMPANY = os.environ.get("GHOSTSPAY_COMPANY_ID")
GHOSTSPAY_API = "https://api.ghostspay.com/v1/payments"

# =====================================================
# AUTH
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        sql = "SELECT * FROM users WHERE email=%s" if DATABASE_URL else \
              "SELECT * FROM users WHERE email=?"

        user = query(sql, (email,), fetchone=True)

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect("/")
        return render_template("login.html", error="Usuário ou senha inválidos")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        sql = """
        INSERT INTO users (name, email, password, balance)
        VALUES (%s,%s,%s,0)
        """ if DATABASE_URL else """
        INSERT INTO users (name, email, password, balance)
        VALUES (?,?,?,0)
        """

        query(sql, (name, email, password))
        return redirect("/login")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


def get_user():
    if "user_id" not in session:
        return None

    sql = "SELECT * FROM users WHERE id=%s" if DATABASE_URL else \
          "SELECT * FROM users WHERE id=?"

    return query(sql, (session["user_id"],), fetchone=True)

# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():
    user = get_user()
    if not user:
        return redirect("/login")
    return render_template("index.html", user=user)

# =====================================================
# DEPOSIT - GHOSTSPAY
# =====================================================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    user = get_user()
    if not user:
        return redirect("/login")

    if request.method == "POST":
        amount = float(request.form["amount"])

        payload = {
            "company_id": GHOSTSPAY_COMPANY,
            "amount": amount,
            "currency": "BRL",
            "method": "PIX",
            "metadata": {
                "user_id": user["id"]
            },
            "callback_url": url_for("ghostspay_webhook", _external=True)
        }

        headers = {
            "Authorization": f"Bearer {GHOSTSPAY_SECRET}",
            "Content-Type": "application/json"
        }

        response = requests.post(GHOSTSPAY_API, json=payload, headers=headers)
        data = response.json()

        return render_template("deposit.html", user=user, payment=data)

    return render_template("deposit.html", user=user)

# =====================================================
# GHOSTSPAY WEBHOOK (ANTI DUPLICAÇÃO)
# =====================================================

@app.route("/webhook/ghostspay", methods=["POST"])
def ghostspay_webhook():
    data = request.json

    payment_id = str(data.get("id"))
    status = data.get("status")
    amount = float(data.get("amount"))
    user_id = int(data["metadata"]["user_id"])

    if status not in ["approved", "paid", "confirmed"]:
        return "ignored", 200

    # 1. verificar duplicação
    sql_check = """
    SELECT id FROM payments WHERE provider_payment_id = %s
    """ if DATABASE_URL else """
    SELECT id FROM payments WHERE provider_payment_id = ?
    """

    exists = query(sql_check, (payment_id,), fetchone=True)
    if exists:
        return "already processed", 200

    # 2. registrar pagamento
    sql_insert = """
    INSERT INTO payments
    (user_id, provider, provider_payment_id, amount, status, raw_payload, confirmed_at)
    VALUES (%s,'ghostspay',%s,%s,'confirmed',%s,NOW())
    """ if DATABASE_URL else """
    INSERT INTO payments
    (user_id, provider, provider_payment_id, amount, status, raw_payload, confirmed_at)
    VALUES (?,'ghostspay',?,?, 'confirmed', ?, datetime('now'))
    """

    query(sql_insert, (
        user_id,
        payment_id,
        amount,
        json.dumps(data)
    ))

    # 3. atualizar saldo
    sql_balance = """
    UPDATE users SET balance = balance + %s WHERE id = %s
    """ if DATABASE_URL else """
    UPDATE users SET balance = balance + ? WHERE id = ?
    """

    query(sql_balance, (amount, user_id))

    return "ok", 200

# =====================================================
# GAMES
# =====================================================

@app.route("/tiger")
def tiger():
    return render_template("game_tiger.html", user=get_user())

@app.route("/ox")
def ox():
    return render_template("game_ox.html", user=get_user())

@app.route("/crash")
def crash():
    return render_template("game_crash.html", user=get_user())

@app.route("/mines")
def mines():
    return render_template("game_mines.html", user=get_user())

# =====================================================
# INIT DB (PRIMEIRO DEPLOY)
# =====================================================

if __name__ == "__main__":
    if os.environ.get("INIT_DB") == "true":
        init_db()
    app.run(debug=True)

