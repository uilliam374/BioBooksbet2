import os, json, sqlite3
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
import stripe

DATABASE='casino.db'
SECRET_KEY=os.environ.get('SECRET_KEY','dev_secret')
app=Flask(__name__)
app.config['SECRET_KEY']=SECRET_KEY

# stripe config
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY','')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY','')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET','')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(q, args=(), one=False):
    cur = get_db().execute(q, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.route('/')
def index():
    user=None; balance=0
    if 'user_id' in session:
        user = query_db('SELECT id, username, balance FROM users WHERE id = ?', (session['user_id'],), one=True)
        balance = int(user['balance'] or 0)
    return render_template('index.html', user=user, balance=balance, stripe_pk=STRIPE_PUBLISHABLE_KEY)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form['username'].strip(); p=request.form['password']
        db=get_db()
        try:
            db.execute('INSERT INTO users (username,password) VALUES (?,?)', (u, generate_password_hash(p)))
            db.commit(); flash('Conta criada','success'); return redirect(url_for('login'))
        except Exception as e:
            flash('Erro: '+str(e),'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form['username'].strip(); p=request.form['password']
        user = query_db('SELECT * FROM users WHERE username = ?', (u,), one=True)
        if user and check_password_hash(user['password'], p):
            session['user_id']=user['id']; flash('Bem-vindo','success'); return redirect(url_for('index'))
        flash('Usuário ou senha inválidos','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

@app.route('/deposit')
def deposit():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = query_db('SELECT id, username, balance FROM users WHERE id = ?', (session['user_id'],), one=True)
    return render_template('deposit.html', user=user, balance=int(user['balance'] or 0), stripe_pk=STRIPE_PUBLISHABLE_KEY)

@app.route('/stripe/create-checkout-session', methods=['POST'])
def stripe_create_checkout():
    if 'user_id' not in session: return jsonify({'error':'login required'}), 403
    data = request.get_json() or {}
    amount = float(data.get('amount',0))
    if amount <= 0: return jsonify({'error':'invalid amount'}), 400
    amount_cents = int(amount * 100)
    try:
        session_stripe = stripe.checkout.Session.create(
            payment_method_types=['card','pix'],
            line_items=[{
                'price_data': {
                    'currency': 'brl',
                    'unit_amount': amount_cents,
                    'product_data': {'name': 'Depósito Cassino'}
                },
                'quantity': 1
            }],
            mode='payment',
            success_url=request.host_url + 'deposit_success',
            cancel_url=request.host_url + 'deposit_cancel',
            metadata={'user_id': session['user_id'], 'amount': amount_cents}
        )
        db = get_db()
        db.execute("INSERT INTO deposits (user_id, amount, method, status, external_id) VALUES (?,?,?,?,?)",
                   (session['user_id'], amount_cents, 'stripe', 'pending', session_stripe.id))
        db.commit()
        return jsonify({'checkout_url': session_stripe.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/deposit_success')
def deposit_success():
    return render_template('deposit_success.html')

@app.route('/deposit_cancel')
def deposit_cancel():
    return render_template('deposit_cancel.html')

@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', None)
    secret = os.environ.get('STRIPE_WEBHOOK_SECRET','')
    if not secret:
        return 'webhook not configured', 400
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception:
        return abort(400)
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        metadata = session_obj.get('metadata') or {}
        user_id = int(metadata.get('user_id') or 0)
        amount = int(metadata.get('amount') or 0)
        external_id = session_obj.get('id')
        db = get_db()
        dep = query_db('SELECT * FROM deposits WHERE external_id = ?', (external_id,), one=True)
        if dep and dep['status'] != 'completed':
            row = query_db('SELECT balance FROM users WHERE id = ?', (user_id,), one=True)
            current = int(row['balance'] or 0)
            new_balance = current + amount
            db.execute('UPDATE users SET balance = ? WHERE id = ?', (new_balance, user_id))
            db.execute('UPDATE deposits SET status = ? WHERE external_id = ?', ('completed', external_id))
            db.commit()
    return '', 200

@app.route('/game/crash')
def game_crash():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('game_crash.html')

@app.route('/game/tiger')
def game_tiger():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('game_tiger.html')

@app.route('/game/ox')
def game_ox():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('game_ox.html')

@app.route('/game/mines')
def game_mines():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('game_mines.html')

@app.route('/play', methods=['POST'])
def play():
    if 'user_id' not in session: return jsonify({'error':'login required'}), 403
    data = request.get_json() or {}
    user_id = session['user_id']
    game = data.get('game','unknown')
    bet = int(data.get('bet') or data.get('amount') or 0)
    result = data.get('result', {})
    db = get_db()
    user = query_db('SELECT balance FROM users WHERE id=?', (user_id,), one=True)
    if not user: return jsonify({'error':'user not found'}),404
    balance = int(user['balance'])
    if bet <= 0:
        return jsonify({'error':'invalid bet','balance':balance}),400
    if balance < bet:
        return jsonify({'error':'insufficient balance','balance':balance}),403
    new_balance = balance - bet
    db.execute('UPDATE users SET balance=? WHERE id=?', (new_balance, user_id))
    winnings = 0
    try:
        if isinstance(result, dict):
            if float(result.get('cashed', 0)) > 0:
                winnings = int(bet * float(result.get('cashed',0)))
            elif result.get('win'):
                winnings = int(bet * float(result.get('multiplier',1)))
        else:
            if str(result).lower() == 'win':
                winnings = bet * 2
    except:
        winnings = 0
    if winnings > 0:
        new_balance += winnings
        db.execute('UPDATE users SET balance=? WHERE id=?', (new_balance, user_id))
    db.execute('INSERT INTO games_history (user_id, game, payload, result) VALUES (?,?,?,?)', (user_id, game, json.dumps(data), json.dumps(result)))
    db.commit()
    return jsonify({'ok':True, 'balance': new_balance})

def init_db():
    with app.app_context():
        with open('schema.sql','r') as f: get_db().executescript(f.read())
        cur = query_db('SELECT COUNT(*) as c FROM users WHERE is_admin=1', one=True)
        if cur['c'] == 0:
            get_db().execute('INSERT INTO users (username, password, is_admin, balance) VALUES (?,?,?,?)', ('admin', generate_password_hash('admin123'), 1, 10000000))
            get_db().execute('INSERT INTO users (username, password, is_admin, balance) VALUES (?,?,?,?)', ('demo', generate_password_hash('demo123'), 0, 100000))
            get_db().commit()

if __name__ == '__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='init-db':
        init_db(); print('DB initialized')
    else:
        app.run(debug=True)
