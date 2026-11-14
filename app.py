import os
import jwt
import datetime
import hmac
import hashlib
import json
import threading
import time
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from urllib.parse import parse_qsl
from dotenv import load_dotenv

# ✅ MAKTABADDA SAXDA AH EE PAYERURL
from binance_and_crypto_payment import CryptoPaymentClient

load_dotenv()

app = Flask(__name__)
CORS(app)

# ==========================================
# 1. LOCAL DATABASE SETUP (JSON File)
# ==========================================
DB_FILE = 'database.json'

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {'users': {}, 'transactions': {}}

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

db = load_db()

# ==========================================
# 2. RATE LIMITING
# ==========================================
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per 15 minutes"], storage_uri="memory://")

# ==========================================
# 3. HELPERS & CONFIG
# ==========================================
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID', '5738022147')
JWT_SECRET = os.getenv('JWT_SECRET', 'super-secret')

# PayerURL Keys
PAYERURL_PUBLIC_KEY = os.getenv('PAYERURL_PUBLIC_KEY', '539abb836b1165830194c5c47e8830e4')
PAYERURL_SECRET_KEY = os.getenv('PAYERURL_SECRET_KEY', '2d3de9443631f27f36f107f65367c7ac')

# 🚀 DOMAIN-KAAGA RENDER OO LA GALAY
YOUR_DOMAIN = os.getenv('YOUR_DOMAIN', 'https://cryptnexa-backend.onrender.com') 

payer_client = CryptoPaymentClient(
    public_key=PAYERURL_PUBLIC_KEY,
    secret_key=PAYERURL_SECRET_KEY
)

def verify_telegram_data(init_data):
    try:
        parsed_data = dict(parse_qsl(init_data))
        if "hash" not in parsed_data: return False
        hash_val = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return calculated_hash == hash_val
    except Exception:
        return False

def generate_token(user_id):
    return jwt.encode({'id': user_id, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)}, JWT_SECRET, algorithm='HS256')

def auth_middleware(f):
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token: return jsonify({'error': 'No token'}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = data['id']
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def send_tg_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    if reply_markup: payload['reply_markup'] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def answer_callback(callback_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    requests.post(url, json={'callback_query_id': callback_id, 'text': text})

# ==========================================
# 4. ROUTES
# ==========================================
@app.route('/')
def home(): return render_template('index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    init_data = request.json.get('initData')
    if init_data == "demo":
        user_id, name, username = "123456789", "Demo", "@demo"
    else:
        if not verify_telegram_data(init_data): return jsonify({'error': 'Invalid data'}), 401
        parsed_data = dict(parse_qsl(init_data))
        tg_user = json.loads(parsed_data['user'])
        user_id, name, username = str(tg_user['id']), tg_user.get('first_name', ''), '@' + tg_user.get('username', 'User')

    if user_id not in db['users']:
        db['users'][user_id] = {'telegramId': user_id, 'name': name, 'username': username, 'balance': 0, 'lockedBalance': 0, 'totalDeposited': 0, 'totalWithdrawn': 0}
        save_db(db)

    return jsonify({'token': generate_token(user_id), 'user': db['users'][user_id]})

# ==========================================
# 5. PAYERURL AUTOMATED DEPOSITS
# ==========================================
@app.route('/api/deposit/auto', methods=['POST'])
@auth_middleware
def deposit_auto():
    data = request.json
    amount = float(data.get('amount'))
    
    if amount < 5:
        return jsonify({'error': 'Minimum deposit is $5'}), 400

    try:
        # Samee Invoice
        response = payer_client.create_invoice(
            order_id=f"DEP_{request.user_id}_{int(time.time())}",
            amount=amount,
            currency="USD",
            notify_url=f"{YOUR_DOMAIN}/api/deposit/webhook"
        )
        
        checkout_url = response.get('redirect_url') or response.get('checkout_url')
        if not checkout_url:
            return jsonify({'error': 'Payment link generation failed'}), 500
            
        return jsonify({'success': True, 'checkout_url': checkout_url})
    except Exception as e:
        print("PayerURL Error:", e)
        return jsonify({'error': 'Failed to create payment link'}), 500

@app.route('/api/deposit/webhook', methods=['POST'])
def deposit_webhook():
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No payload"}), 400

        # PayerURL waxay soo dirtaa macluumaadkan
        order_id = payload.get('order_id')
        status = payload.get('status')
        
        # Hubi xaaladda (Maktabadda cusub waxay isticmaashaa 'completed' ama 'success')
        if status in ['completed', 'success', 'paid']:
            parts = order_id.split('_')
            if len(parts) >= 2:
                user_id = parts[1]
                amount_paid = float(payload.get('amount', 0))
                
                # Hubi in aysan horey u xaqiijin (Duplicate check)
                if order_id not in db['transactions']:
                    tx_id = str(int(time.time() * 1000))
                    
                    db['transactions'][tx_id] = {
                        'id': tx_id, 'userId': user_id, 'order_id': order_id,
                        'amount': amount_paid, 'network': 'PayerURL Auto', 
                        'status': 'Completed', 'type': 'deposit'
                    }
                    
                    user = db['users'].get(user_id)
                    if user:
                        user['balance'] += amount_paid
                        user['totalDeposited'] = user.get('totalDeposited', 0) + amount_paid
                        db['users'][user_id] = user
                        
                    save_db(db)
                    send_tg_message(user_id, f"✅ *Auto Deposit Successful!*\n💰 +${amount_paid:.2f} added to your balance.")
                    send_tg_message(ADMIN_ID, f"💰 *AUTO DEPOSIT*\n👤 User: `{user_id}`\n💵 Amount: *${amount_paid:.2f}*")
            
        return jsonify({"status": "success"}), 200
            
    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"status": "error"}), 400

# ==========================================
# 6. MANUAL DEPOSIT & WITHDRAWAL
# ==========================================
@app.route('/api/deposit/request', methods=['POST'])
@limiter.limit("5 per 15 minutes")
@auth_middleware
def deposit_request():
    data = request.json
    txid, amount, network = data.get('txid'), float(data.get('amount')), data.get('network')
    
    if any(t.get('txid') == txid for t in db['transactions'].values()):
        return jsonify({'error': 'TxID used'}), 400

    tx_id = str(int(time.time() * 1000))
    db['transactions'][tx_id] = {
        'id': tx_id, 'userId': request.user_id, 'txid': txid, 
        'amount': amount, 'network': network, 'status': 'Pending Review', 'type': 'deposit'
    }
    save_db(db)

    msg = f"🚨 *NEW MANUAL DEPOSIT*\n\n👤 User: `{request.user_id}`\n💰 Amount: *${amount}*\n🌐 Network: {network}\n🔗 TxID: `{txid}`"
    buttons = {'inline_keyboard': [[
        {'text': '✅ Approve', 'callback_data': f'dep_ok_{tx_id}'},
        {'text': '❌ Reject', 'callback_data': f'dep_no_{tx_id}'}
    ]]}
    send_tg_message(ADMIN_ID, msg, buttons)
    
    return jsonify({'success': True, 'message': 'Pending Admin Approval'})

@app.route('/api/withdraw/request', methods=['POST'])
@auth_middleware
def withdraw_request():
    data = request.json
    amount, network, address = float(data.get('amount')), data.get('network'), data.get('address')

    user = db['users'].get(request.user_id)
    if not user or user['balance'] < amount: 
        return jsonify({'error': 'Insufficient balance'}), 400
        
    user['balance'] -= amount
    db['users'][request.user_id] = user

    tx_id = str(int(time.time() * 1000))
    db['transactions'][tx_id] = {
        'id': tx_id, 'userId': request.user_id, 'amount': amount, 
        'network': network, 'address': address, 'status': 'Pending Review', 'type': 'withdraw'
    }
    save_db(db)

    msg = f"🚨 *WITHDRAW REQUEST*\n\n👤 User: `{request.user_id}`\n💰 Amount: *-${amount}*\n🌐 Network: {network}\n🏦 Address: `{address}`"
    buttons = {'inline_keyboard': [[
        {'text': '✅ Approve', 'callback_data': f'wth_ok_{tx_id}'},
        {'text': '❌ Reject', 'callback_data': f'wth_no_{tx_id}'}
    ]]}
    send_tg_message(ADMIN_ID, msg, buttons)
    
    return jsonify({'success': True, 'message': 'Pending Admin Approval', 'new_balance': user['balance']})

# ==========================================
# 7. TELEGRAM CALLBACK LISTENER (Polling)
# ==========================================
def telegram_polling():
    print("🤖 Telegram bot polling started...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=5"
            res = requests.get(url).json()
            if res.get('ok') and res['result']:
                for update in res['result']:
                    offset = update['update_id'] + 1
                    
                    if 'message' in update and update['message'].get('text') == '/start':
                        chat_id = update['message']['chat']['id']
                        send_tg_message(chat_id, "👋 Ku soo dhawoow ApexInvest Bot!\n\nFadlan ka fur App-ka hoos si aad u bilowdo.")
                    
                    if 'callback_query' in update:
                        cq = update['callback_query']
                        data = cq['data']
                        cq_id = cq['id']
                        
                        parts = data.split('_')
                        if len(parts) >= 3:
                            action_type = parts[0]
                            status_type = parts[1]
                            tx_id = "_".join(parts[2:])
                            is_ok = (status_type == 'ok')

                            tx = db['transactions'].get(tx_id)

                            if not tx or tx['status'] != 'Pending Review':
                                answer_callback(cq_id, "Already processed!")
                                continue

                            if action_type == 'dep' and is_ok:
                                tx['status'] = 'Completed'
                                user = db['users'].get(tx['userId'])
                                if user:
                                    user['balance'] += tx['amount']
                                    user['totalDeposited'] = user.get('totalDeposited', 0) + tx['amount']
                                    db['users'][tx['userId']] = user
                                save_db(db)
                                send_tg_message(tx['userId'], f"✅ *Deposit Approved!*\n💰 +${tx['amount']} added to balance.")
                                answer_callback(cq_id, "✅ Deposit Approved")

                            elif action_type == 'dep' and not is_ok:
                                tx['status'] = 'Rejected'
                                save_db(db)
                                send_tg_message(tx['userId'], f"❌ *Deposit Rejected*\nYour deposit of ${tx['amount']} was rejected.")
                                answer_callback(cq_id, "❌ Deposit Rejected")

                            elif action_type == 'wth' and is_ok:
                                tx['status'] = 'Completed'
                                user = db['users'].get(tx['userId'])
                                if user:
                                    user['totalWithdrawn'] = user.get('totalWithdrawn', 0) + tx['amount']
                                    db['users'][tx['userId']] = user
                                save_db(db)
                                send_tg_message(tx['userId'], f"✅ *Withdrawal Successful!*\n💰 -${tx['amount']} sent.")
                                answer_callback(cq_id, "✅ Withdraw Approved")

                            elif action_type == 'wth' and not is_ok:
                                tx['status'] = 'Rejected'
                                user = db['users'].get(tx['userId'])
                                if user:
                                    user['balance'] += tx['amount'] # Refund
                                    db['users'][tx['userId']] = user
                                save_db(db)
                                send_tg_message(tx['userId'], f"❌ *Withdrawal Rejected*\n${tx['amount']} has been refunded to your balance.")
                                answer_callback(cq_id, "❌ Withdraw Rejected (Refunded)")
                                
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageReplyMarkup", json={
                                'chat_id': cq['message']['chat']['id'],
                                'message_id': cq['message']['message_id'],
                                'reply_markup': {'inline_keyboard': []}
                            })
        except Exception as e:
            print("Polling Error:", e)
        time.sleep(1)

threading.Thread(target=telegram_polling, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 3000)))
