import os
import html
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect

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
    requests.post(
        f"{BASE_URL}/answerCallbackQuery",
        json={"callback_query_id": callback_id}
    )


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
    forward_to_admin(message)
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
            ]
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

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Approve ✅", "callback_data": f"approve:{chat_id}"},
                {"text": "Reject ❌", "callback_data": f"reject:{chat_id}"}
            ],
            [
                {"text": "Message 💬", "callback_data": f"message:{chat_id}"}
            ]
        ]
    }

    send_message(chat_id, "Receipt received ✅\nPlease wait for admin approval.")

def handle_document_receipt(message):
    forward_to_admin(message)
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
            [
                {"text": "Message 💬", "callback_data": f"message:{chat_id}"}
            ]
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
        f"After payment, send your receipt screenshot here."
    )

    admin_keyboard = {
        "inline_keyboard": [
            [
                {"text": "Remind 🔔", "callback_data": f"remind:{chat_id}"},
                {"text": "Message 💬", "callback_data": f"message:{chat_id}"}
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

    send_photo_file(chat_id, "qr.png", "Scan QR and complete payment.")


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

    admin_keyboard = {
        "inline_keyboard": [
            [
                {"text": "Message 💬", "callback_data": f"message:{customer_id}"}
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

    customer_id = int(callback["data"].split(":")[1])

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

    date_filter = request.args.get("date", "")

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT raw_item
                FROM stock
                WHERE status = 'available'
                ORDER BY id ASC;
            """)

            stock_items = cur.fetchall()

            if date_filter:
                cur.execute("""
                    SELECT *
                    FROM orders
                    WHERE DATE(created_at) = %s
                    ORDER BY created_at DESC;
                """, (date_filter,))
            else:
                cur.execute("""
                    SELECT *
                    FROM orders
                    ORDER BY created_at DESC
                    LIMIT 300;
                """)

            orders = cur.fetchall()

    account_text = "\n".join([s["raw_item"] for s in stock_items])
    available_count = len(stock_items)

    order_rows = ""

    for o in orders:
        order_rows += f"""
        <tr>
            <td><input type="checkbox" name="order_ids" value="{o['id']}"></td>
            <td>{html.escape(str(o['id']))}</td>
            <td>{html.escape(str(o['telegram_id']))}</td>
            <td>{html.escape(str(o.get('username') or ''))}</td>
            <td><pre>{html.escape(str(o.get('formatted_item') or ''))}</pre></td>
            <td>{html.escape(str(o.get('status') or ''))}</td>
            <td>{html.escape(str(o.get('created_at') or ''))}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>Telegram Bot Admin</title>
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
                border-collapse: collapse;
                width: 100%;
                background: white;
            }}
            th, td {{
                border: 1px solid #ccc;
                padding: 8px;
                vertical-align: top;
            }}
            pre {{
                white-space: pre-wrap;
                margin: 0;
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
            <h2>Orders</h2>

            <form method="GET">
                <input type="hidden" name="key" value="{html.escape(ADMIN_KEY)}">
                <input type="date" name="date" value="{html.escape(date_filter)}">
                <button type="submit">Filter Date</button>
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
