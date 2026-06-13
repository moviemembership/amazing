import os
import html
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect
import time

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_KEY = os.environ.get("ADMIN_KEY", "changeme")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

PRODUCT_NAME = "Netflix Private Profile 1 Month"
PRICE = "RM15.9"
LOW_STOCK_LIMIT = 5
SUPPORT_LINK = "https://t.me/moviemembership"

recent_reminders = {}

def db():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )

    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Kuala_Lumpur';")

    conn.commit()

    return conn


def init_db():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock (
                    id SERIAL PRIMARY KEY,
                    raw_item TEXT NOT NULL,
                    status TEXT DEFAULT 'available',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    status TEXT DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS raw_item TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS formatted_item TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_item TEXT;")

            conn.commit()


init_db()


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    requests.post(f"{BASE_URL}/sendMessage", json=data)


def send_photo_file(chat_id, photo_path, caption=""):
    if not os.path.exists(photo_path):
        send_message(ADMIN_ID, f"Missing file: {photo_path}")
        return

    with open(photo_path, "rb") as photo:
        requests.post(
            f"{BASE_URL}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": photo}
        )


def send_photo_by_file_id(chat_id, file_id, caption="", reply_markup=None):
    data = {"chat_id": chat_id, "photo": file_id, "caption": caption}
    if reply_markup:
        data["reply_markup"] = reply_markup
    requests.post(f"{BASE_URL}/sendPhoto", json=data)


def answer_callback(callback_id):
    try:
        requests.post(
            f"{BASE_URL}/answerCallbackQuery",
            json={
                "callback_query_id": callback_id,
                "text": "Processing..."
            },
            timeout=5
        )
    except:
        pass


def format_item(raw_item):
    parts = raw_item.split("----")

    if len(parts) == 3:
        email, password, slot = parts
        return (
            f"Email: {email}\n"
            f"Password: {password}\n"
            f"Profile: {slot}"
        )

    if len(parts) == 2:
        email, password = parts
        return (
            f"Email: {email}\n"
            f"Password: {password}"
        )

    return raw_item


def get_base_login(raw_item):
    parts = raw_item.split("----")
    if len(parts) >= 2:
        return f"{parts[0]}----{parts[1]}"
    return raw_item


def get_slot(raw_item):
    parts = raw_item.split("----")
    if len(parts) >= 3:
        return parts[2]
    return ""


def get_stock_count():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stock WHERE status = 'available';")
            return cur.fetchone()[0]


def sync_stock_from_textarea(text):
    new_items = [line.strip() for line in text.splitlines() if line.strip()]

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock WHERE status = 'available';")

            for item in new_items:
                cur.execute(
                    "INSERT INTO stock (raw_item, status) VALUES (%s, 'available');",
                    (item,)
                )

            conn.commit()


def save_order(telegram_id, username, first_name, raw_item, formatted_item):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (telegram_id, username, first_name, raw_item, formatted_item, delivered_item, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'completed');
            """, (
                telegram_id,
                username,
                first_name,
                raw_item,
                formatted_item,
                raw_item
            ))
            conn.commit()


def update_orders_replace(old_login, new_login):
    buyers_to_notify = []

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, telegram_id, raw_item
                FROM orders
                WHERE raw_item LIKE %s;
            """, (old_login + "----%",))

            orders = cur.fetchall()

            for order in orders:
                old_raw_item = order["raw_item"]
                slot = get_slot(old_raw_item)

                if slot:
                    new_raw_item = f"{new_login}----{slot}"
                else:
                    new_raw_item = new_login

                new_formatted = format_item(new_raw_item)

                cur.execute("""
                    UPDATE orders
                    SET raw_item = %s,
                        formatted_item = %s,
                        delivered_item = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    new_raw_item,
                    new_formatted,
                    new_raw_item,
                    order["id"]
                ))

                buyers_to_notify.append({
                    "telegram_id": order["telegram_id"],
                    "formatted_item": new_formatted
                })

            conn.commit()

    return buyers_to_notify


def main_menu(chat_id):
    stock_count = get_stock_count()

    keyboard = {
        "inline_keyboard": [
            [{"text": f"Buy Netflix Account - {PRICE}", "callback_data": "buy"}],
            [{"text": "Contact Customer Support 💬", "url": SUPPORT_LINK}]
        ]
    }

    send_message(
        chat_id,
        f"Hi 👋 Netflix Private Profile Available\n\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n"
        f"Stock Left: {stock_count}\n\n"
        f"Please choose one option below:",
        keyboard
    )


@app.route("/")
def home():
    return "Bot is running."


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()

    if not update:
        return "OK"

    if "message" in update:
        handle_message(update["message"])

    elif "callback_query" in update:
        handle_callback(update["callback_query"])

    return "OK"

def forward_to_admin(message):
    requests.post(
        f"{BASE_URL}/forwardMessage",
        json={
            "chat_id": ADMIN_ID,
            "from_chat_id": message["chat"]["id"],
            "message_id": message["message_id"]
        }
    )


def handle_message(message):
    chat_id = message["chat"]["id"]

    # Admin command: /msg telegram_id message
    if chat_id == ADMIN_ID and "text" in message:
        text = message["text"]

        if text.startswith("/msg "):
            parts = text.split(" ", 2)

            if len(parts) < 3:
                send_message(ADMIN_ID, "Format:\n/msg TELEGRAM_ID your message")
                return

            target_id = parts[1]
            msg_content = parts[2]

            send_message(
                target_id,
                f"Message from admin 💬\n\n{msg_content}"
            )

            send_message(
                ADMIN_ID,
                f"Message sent ✅\n\nTo: {target_id}\nMessage: {msg_content}"
            )

            return

    # Forward image receipt
    if "photo" in message:
        forward_to_admin(message)
        handle_receipt(message)
        return

    # Forward PDF/document receipt
    if "document" in message:
        forward_to_admin(message)
        handle_document_receipt(message)
        return

    main_menu(chat_id)


def handle_receipt(message):
    chat_id = message["chat"]["id"]
    user = message["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")
    photo_id = message["photo"][-1]["file_id"]

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Approve ✅", "callback_data": f"approve:{chat_id}"},
                {"text": "Reject ❌", "callback_data": f"reject:{chat_id}"}
            ],
            {
                "text": "Message 💬",
                "switch_inline_query_current_chat": f"/msg {chat_id} "
            }
        ]
    }

    send_photo_by_file_id(
        ADMIN_ID,
        photo_id,
        caption=(
            f"Receipt Received 🧾\n\n"
            f"Customer: @{username}\n"
            f"Name: {name}\n"
            f"Telegram ID: {chat_id}\n"
            f"Product: {PRODUCT_NAME}\n"
            f"Price: {PRICE}\n"
            f"Stock Left Now: {get_stock_count()}"
        ),
        reply_markup=keyboard
    )

    send_message(chat_id, "Receipt received ✅\nPlease wait for admin approval.")

def handle_document_receipt(message):
    chat_id = message["chat"]["id"]
    user = message["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")
    document = message["document"]

    file_id = document["file_id"]
    file_name = document.get("file_name", "receipt.pdf")
    mime_type = document.get("mime_type", "unknown")

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Approve ✅", "callback_data": f"approve:{chat_id}"},
                {"text": "Reject ❌", "callback_data": f"reject:{chat_id}"}
            ],
            {
                "text": "Message 💬",
                "switch_inline_query_current_chat": f"/msg {chat_id} "
            }
        ]
    }

    data = {
        "chat_id": ADMIN_ID,
        "document": file_id,
        "caption": (
            f"Document Receipt Received 🧾\n\n"
            f"Customer: @{username}\n"
            f"Name: {name}\n"
            f"Telegram ID: {chat_id}\n"
            f"File Name: {file_name}\n"
            f"File Type: {mime_type}\n"
            f"Product: {PRODUCT_NAME}\n"
            f"Price: {PRICE}\n"
            f"Stock Left Now: {get_stock_count()}"
        ),
        "reply_markup": keyboard
    }

    requests.post(f"{BASE_URL}/sendDocument", json=data)

    send_message(
        chat_id,
        "Receipt received ✅\nPlease wait for admin approval."
    )


def handle_callback(callback):
    answer_callback(callback["id"])

    data = callback["data"]

    if data == "buy":
        handle_buy(callback)

    elif data.startswith("remind:"):
        handle_remind(callback)

    elif data.startswith("message:"):
        handle_message_button(callback)

    elif data.startswith("approve:"):
        handle_approve(callback)

    elif data.startswith("reject:"):
        handle_reject(callback)


def handle_buy(callback):
    chat_id = callback["message"]["chat"]["id"]
    user = callback["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")

    stock_count = get_stock_count()

    if stock_count <= 0:
        send_message(chat_id, "Sorry, this product is currently out of stock ❌")
        send_message(ADMIN_ID, "Stock Alert ❌\n\nStock is now 0.")
        return

    if stock_count <= LOW_STOCK_LIMIT:
        send_message(ADMIN_ID, f"Low Stock Warning ⚠️\n\nOnly {stock_count} item(s) left.")

    send_message(
        chat_id,
        f"Order Created ✅\n\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n"
        f"Stock Left: {stock_count}\n\n"
        f"Please pay using the QR code below.\n"
        f"After payment, send your receipt screenshot here.\n"
        f"⭐Please don't chat with us at Shopee⭐."
    )

    admin_keyboard = {
        "inline_keyboard": [
            [
                {"text": "Remind 🔔", "callback_data": f"remind:{chat_id}"},
                {
                "text": "Message 💬",
                "switch_inline_query_current_chat": f"/msg {chat_id} "
            }
            ]
        ]
    }

    send_message(
        ADMIN_ID,
        f"New Order 🛒\n\n"
        f"Customer: @{username}\n"
        f"Name: {name}\n"
        f"Telegram ID: {chat_id}\n"
        f"Stock Before Payment: {stock_count}",
        admin_keyboard
    )

    send_photo_file(chat_id, "qr.png", "Scan QR and complete payment.\n\n⭐Please don't chat with us at Shopee⭐")


def handle_approve(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(callback["from"]["id"], "You are not allowed to do this.")
        return

    customer_id = int(callback["data"].split(":")[1])

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, raw_item
                FROM stock
                WHERE status = 'available'
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE;
            """)

            stock_item = cur.fetchone()

            if not stock_item:
                send_message(customer_id, "Payment approved, but stock is empty. Please contact admin.")
                send_message(ADMIN_ID, "No stock left ❌")
                return

            raw_item = stock_item["raw_item"]
            formatted_item = format_item(raw_item)

            cur.execute("""
                INSERT INTO orders
                (telegram_id, raw_item, formatted_item, delivered_item, status)
                VALUES (%s, %s, %s, %s, 'completed');
            """, (
                customer_id,
                raw_item,
                formatted_item,
                raw_item
            ))

            cur.execute("""
                UPDATE stock
                SET status = 'used',
                    used_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                stock_item["id"],
            ))

            conn.commit()

    remaining = get_stock_count()

    send_message(
        customer_id,
        f"Payment Approved ✅\n\n"
        f"{formatted_item}\n"
        f"You are able to edit and lock your profile\n\n"
        f"Sign in at Netflix apps/Website, Only Gey The Code if they request\n"
        f"how to sign in with password: https://shorturl.at/BYY3p\n\n"
        f"Get Sign In Code Here(4-digit): https://mantapnet.onrender.com/sign-in-code-auto\n\n"
        f"Get Verification Code Here(6-digit): https://mantapnet.onrender.com/verification-code\n\n"
        f"Video to Get Code: https://youtu.be/S4NgHOICPSc\n\n"
        f"Warranty Period: 28days\n\n"
        f"If You are unable to sign in please contact customer support\n\n"
        f"Thank you for your purchase."
    )
    
    support_keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "Contact Customer Service 💬",
                    "url": SUPPORT_LINK
                }
            ]
        ]
    }

    send_message(
        customer_id,
        "⭐ Please don't chat with us at Shopee.\n\n"
        "For faster support, please contact our customer service here:",
        support_keyboard
    )

    admin_keyboard = {
        "inline_keyboard": [
            [
                {
                "text": "Message 💬",
                "switch_inline_query_current_chat": f"/msg {chat_id} "
            }
            ]
        ]
    }
    
    send_message(
        ADMIN_ID,
        f"Order Completed ✅\n\n"
        f"Customer ID: {customer_id}\n"
        f"Delivered:\n\n"
        f"{formatted_item}\n\n"
        f"Remaining Stock: {remaining}",
        admin_keyboard
    )

    if remaining <= LOW_STOCK_LIMIT:
        send_message(ADMIN_ID, f"Low Stock Warning ⚠️\n\nOnly {remaining} item(s) left.")


def handle_reject(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(callback["from"]["id"], "You are not allowed to do this.")
        return

    customer_id = int(callback["data"].split(":")[1])

    send_message(customer_id, "Payment rejected ❌\nPlease check your receipt and send again.")
    send_message(ADMIN_ID, f"Order rejected ❌\nCustomer ID: {customer_id}")

def handle_remind(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(callback["from"]["id"], "You are not allowed to do this.")
        return

    parts = callback["data"].split(":")
    customer_id = int(parts[1])

    send_message(
        customer_id,
        "Payment Reminder 🔔\n\n"
        "Your order is still pending payment.\n"
        "Please complete payment and send your receipt here."
    )

    send_message(
        ADMIN_ID,
        f"Reminder sent ✅\n\nCustomer ID: {customer_id}"
    )


def handle_message_button(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(callback["from"]["id"], "You are not allowed to do this.")
        return

    customer_id = callback["data"].split(":")[1]

    send_message(
        ADMIN_ID,
        f"To message this customer, type:\n\n"
        f"/msg {customer_id} your message here"
    )

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.args.get("key") != ADMIN_KEY:
        return "Unauthorized", 403

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_stock":
            accounts = request.form.get("accounts", "")
            sync_stock_from_textarea(accounts)

        elif action == "manual_delivery":
            telegram_id = int(request.form.get("telegram_id"))
            raw_item = request.form.get("manual_item", "").strip()

            if raw_item:
                formatted = format_item(raw_item)

                send_message(
                    telegram_id,
                    f"Manual Delivery ✅\n\n"
                    f"Here is your updated product:\n\n"
                    f"{formatted}"
                )

                save_order(
                    telegram_id,
                    "manual",
                    "manual",
                    raw_item,
                    formatted
                )

        elif action == "replace_item":
            old_login = request.form.get("old_item", "").strip()
            new_login = request.form.get("new_item", "").strip()

            if old_login and new_login:
                buyers = update_orders_replace(old_login, new_login)

                for buyer in buyers:
                    send_message(
                        buyer["telegram_id"],
                        f"Account Replacement ✅\n\n"
                        f"Your updated login:\n\n"
                        f"{buyer['formatted_item']}"
                    )

        elif action == "delete_orders":
            ids = request.form.getlist("order_ids")

            with db() as conn:
                with conn.cursor() as cur:
                    for order_id in ids:
                        cur.execute(
                            "DELETE FROM orders WHERE id = %s;",
                            (order_id,)
                        )
                    conn.commit()

        return redirect(f"/admin?key={ADMIN_KEY}")

    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    search = request.args.get("search", "").strip()

with db() as conn:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT raw_item
            FROM stock
            WHERE status = 'available'
            ORDER BY id ASC;
        """)

        stock_items = cur.fetchall()

        query = """
            SELECT *,
                   DATE_PART('day', NOW() - created_at) AS order_age
            FROM orders
            WHERE 1=1
        """

        params = []

        if date_from:
            query += " AND DATE(created_at) >= %s"
            params.append(date_from)

        if date_to:
            query += " AND DATE(created_at) <= %s"
            params.append(date_to)

        if search:
            query += """
                AND (
                    CAST(id AS TEXT) ILIKE %s OR
                    CAST(telegram_id AS TEXT) ILIKE %s OR
                    username ILIKE %s OR
                    raw_item ILIKE %s OR
                    formatted_item ILIKE %s
                )
            """
            s = f"%{search}%"
            params.extend([s, s, s, s, s])

        query += " ORDER BY created_at DESC LIMIT 500;"

        cur.execute(query, params)
        orders = cur.fetchall()

    account_text = "\n".join([s["raw_item"] for s in stock_items])
    available_count = len(stock_items)

    order_rows = ""

    for o in orders:
        age = int(o.get("order_age") or 0)
    
        if age >= 28:
            warranty_badge = '<span class="expired">Expired</span>'
        else:
            warranty_badge = f'<span class="active">Day {age + 1}/28</span>'
    
        order_rows += f"""
        <tr>
            <td><input type="checkbox" name="order_ids" value="{o['id']}"></td>
            <td>{html.escape(str(o['id']))}</td>
            <td>{html.escape(str(o['telegram_id']))}</td>
            <td>{html.escape(str(o.get('username') or ''))}</td>
            <td><pre>{html.escape(str(o.get('formatted_item') or ''))}</pre></td>
            <td>{html.escape(str(o.get('status') or ''))}</td>
            <td>{html.escape(str(o.get('created_at') or ''))}</td>
            <td>{warranty_badge}</td>
            <td>
                <a class="edit-btn" href="/edit_order?id={o['id']}&key={ADMIN_KEY}">
                    Edit
                </a>
            </td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>MovieMembership Admin</title>
        <div class="stats">
        
        <div class="stat-card">
        <h3>Available Accounts</h3>
        <h1>{available_count}</h1>
        </div>
        
        <div class="stat-card">
        <h3>Total Orders</h3>
        <h1>{len(orders)}</h1>
        </div>
        
        </div>
        <style>
            body {{
                font-family: Arial;
                padding: 20px;
                background: #f5f5f5;
            }}
            .card {{
                background: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 8px;
            }}
            textarea {{
                width: 100%;
                height: 220px;
            }}
            input {{
                padding: 8px;
                margin: 5px 0;
                width: 100%;
            }}
            button {{
                padding: 10px 16px;
                margin-top: 8px;
                background: #1677ff;
                color: white;
                border: 0;
                border-radius: 5px;
            }}
            table {{
                border-collapse:collapse;
                width:100%;
                overflow:hidden;
                border-radius:12px;
                background:white;
            }}
            
            th {{
                background:#eff6ff;
            }}
            
            th,td {{
                padding:12px;
                border-bottom:1px solid #e5e7eb;
            }}
            .stats{{
                display:flex;
                gap:20px;
                margin-bottom:20px;
            }}
            
            .stat-card{{
                flex:1;
                background:white;
                padding:20px;
                border-radius:16px;
                box-shadow:0 4px 20px rgba(0,0,0,.06);
            }}
            .edit-btn {{
                display:inline-block;
                padding:8px 12px;
                background:#2563eb;
                color:white;
                text-decoration:none;
                border-radius:8px;
                font-size:14px;
                font-weight:600;
            }}
            
            .edit-btn:hover {{
                background:#1d4ed8;
            }}
            .filter-form {{
                display:grid;
                grid-template-columns:80px 1fr 50px 1fr auto auto;
                gap:10px;
                align-items:center;
                margin-bottom:15px;
            }}
            
            .clear-btn {{
                display:inline-block;
                padding:10px 16px;
                background:#64748b;
                color:white;
                text-decoration:none;
                border-radius:8px;
                font-weight:600;
            }}
            .filter-form {{
                display:grid;
                grid-template-columns:2fr 1fr 1fr auto auto;
                gap:10px;
                align-items:center;
                margin-bottom:15px;
            }}
            
            .clear-btn {{
                display:inline-block;
                padding:10px 16px;
                background:#64748b;
                color:white;
                text-decoration:none;
                border-radius:8px;
                font-weight:600;
            }}
            
            .expired {{
                display:inline-block;
                background:#fee2e2;
                color:#b91c1c;
                padding:6px 10px;
                border-radius:999px;
                font-weight:700;
            }}
            
            .active {{
                display:inline-block;
                background:#dcfce7;
                color:#166534;
                padding:6px 10px;
                border-radius:999px;
                font-weight:700;
            }}
        </style>
    </head>
    <body>

        <h1>Telegram Bot Admin</h1>

        <div class="card">
            <h2>Accounts / Stock ({available_count} remaining)</h2>
            <p>Format: email----password----profile</p>
            <form method="POST">
                <input type="hidden" name="action" value="update_stock">
                <textarea name="accounts">{html.escape(account_text)}</textarea>
                <button type="submit">Update Accounts</button>
            </form>
        </div>

        <div class="card">
            <h2>Manual Delivery</h2>
            <form method="POST">
                <input type="hidden" name="action" value="manual_delivery">
                <input name="telegram_id" placeholder="Telegram ID">
                <input name="manual_item" placeholder="email----password----profile">
                <button type="submit">Manual Delivery</button>
            </form>
        </div>

        <div class="card">
            <h2>Replace Login</h2>
            <p>Only type email----password. The buyer's previous profile number will stay the same.</p>
            <form method="POST">
                <input type="hidden" name="action" value="replace_item">
                <input name="old_item" placeholder="Old email----old password">
                <input name="new_item" placeholder="New email----new password">
                <button type="submit">Replace & Notify Buyers</button>
            </form>
        </div>

        <div class="card">
        <button onclick="location.href='/edit_order?new=1&key={ADMIN_KEY}'">
            + Add New Order
        </button>
            <h2>Orders</h2>

            <form method="GET" class="filter-form">
                <input type="hidden" name="key" value="{html.escape(ADMIN_KEY)}">
            
                <label>From</label>
                <input type="date" name="date_from" value="{html.escape(date_from)}">
            
                <label>To</label>
                <input type="date" name="date_to" value="{html.escape(date_to)}">
            
                <button type="submit">Filter Date</button>
            
                <a class="clear-btn" href="/admin?key={ADMIN_KEY}">Clear</a>
            </form>

            <form method="POST">
                <input type="hidden" name="action" value="delete_orders">

                <button type="button" onclick="selectAll()">Select All</button>
                <button type="submit">Delete Selected Orders</button>

                <table>
                    <tr>
                        <th>Select</th>
                        <th>Order ID</th>
                        <th>Telegram ID</th>
                        <th>Username</th>
                        <th>Delivered Item</th>
                        <th>Status</th>
                        <th>Date</th>
                        <th>Warranty</th>
                        <th>Actions</th>
                    </tr>
                    {order_rows}
                </table>
            </form>
        </div>

        <script>
            function selectAll() {{
                document.querySelectorAll('input[type="checkbox"]').forEach(
                    cb => cb.checked = true
                );
            }}
        </script>

    </body>
    </html>
    """

@app.route("/edit_order", methods=["GET", "POST"])
def edit_order():

    if request.args.get("key") != ADMIN_KEY:
        return "Unauthorized", 403

    is_new = request.args.get("new") == "1"
    order_id = request.args.get("id")

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            if request.method == "POST":
                telegram_id = request.form["telegram_id"]
                username = request.form["username"]
                raw_item = request.form["raw_item"]
                created_at = request.form["created_at"]
                formatted_item = format_item(raw_item)

                if is_new:
                    cur.execute("""
                        INSERT INTO orders
                        (telegram_id, username, raw_item, formatted_item, delivered_item, status, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, 'completed', %s, %s);
                    """, (
                        telegram_id,
                        username,
                        raw_item,
                        formatted_item,
                        raw_item,
                        created_at,
                        created_at
                    ))
                else:
                    cur.execute("""
                        UPDATE orders
                        SET telegram_id=%s,
                            username=%s,
                            raw_item=%s,
                            formatted_item=%s,
                            delivered_item=%s,
                            created_at=%s,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s;
                    """, (
                        telegram_id,
                        username,
                        raw_item,
                        formatted_item,
                        raw_item,
                        created_at,
                        order_id
                    ))

                conn.commit()
                return redirect(f"/admin?key={ADMIN_KEY}")

            if is_new:
                cur.execute("SELECT NOW() AT TIME ZONE 'Asia/Kuala_Lumpur' AS now_time;")
                now_row = cur.fetchone()
                now_time = now_row["now_time"].strftime("%Y-%m-%dT%H:%M")

                order = {
                    "id": "NEW",
                    "telegram_id": "",
                    "username": "",
                    "raw_item": "",
                    "created_at": now_time
                }
            else:
                cur.execute("SELECT * FROM orders WHERE id=%s", (order_id,))
                order = cur.fetchone()

                if order["created_at"]:
                    order["created_at"] = order["created_at"].strftime("%Y-%m-%dT%H:%M")

    preview = format_item(order.get("raw_item", ""))

    return f"""
    <html>
    <head>
    <title>{'Add Order' if is_new else 'Edit Order'}</title>

    <style>
    body {{
        background:#f1f5f9;
        font-family:Arial,sans-serif;
        padding:30px;
    }}
    .card {{
        max-width:800px;
        margin:auto;
        background:white;
        padding:30px;
        border-radius:15px;
        box-shadow:0 4px 20px rgba(0,0,0,.08);
    }}
    input, textarea {{
        width:100%;
        padding:12px;
        border:1px solid #ddd;
        border-radius:8px;
        margin-top:5px;
        margin-bottom:15px;
        box-sizing:border-box;
    }}
    textarea {{
        min-height:120px;
    }}
    .preview {{
        background:#f8fafc;
        border:1px solid #e5e7eb;
        padding:15px;
        border-radius:8px;
        white-space:pre-wrap;
        margin-bottom:15px;
    }}
    button {{
        background:#2563eb;
        color:white;
        border:none;
        padding:12px 20px;
        border-radius:8px;
        cursor:pointer;
    }}
    .back {{
        text-decoration:none;
        color:#2563eb;
    }}
    </style>
    </head>

    <body>
    <div class="card">

        <h2>{'Add New Order' if is_new else f"Edit Order #{order['id']}"}</h2>

        <a class="back" href="/admin?key={ADMIN_KEY}">← Back to Admin</a>

        <br><br>

        <form method="POST">

            <label>Telegram ID</label>
            <input name="telegram_id" value="{html.escape(str(order.get('telegram_id','')))}">

            <label>Username</label>
            <input name="username" value="{html.escape(str(order.get('username','')))}">

            <label>Raw Item</label>
            <textarea id="raw_item" name="raw_item">{html.escape(str(order.get('raw_item','')))}</textarea>

            <label>Preview Auto Generated</label>
            <pre id="preview" class="preview">{html.escape(preview)}</pre>

            <label>Order Time</label>
            <input type="datetime-local" name="created_at" value="{html.escape(str(order.get('created_at','')))}">

            <button type="submit">
                {'Add Order' if is_new else 'Save Changes'}
            </button>

        </form>

    </div>

    <script>
    function makePreview(text) {{
        let parts = text.split("----");
        if (parts.length === 3) {{
            return "Email: " + parts[0] + "\\nPassword: " + parts[1] + "\\nProfile: " + parts[2];
        }}
        if (parts.length === 2) {{
            return "Email: " + parts[0] + "\\nPassword: " + parts[1];
        }}
        return text;
    }}

    document.getElementById("raw_item").addEventListener("input", function() {{
        document.getElementById("preview").textContent = makePreview(this.value);
    }});
    </script>

    </body>
    </html>
    """
