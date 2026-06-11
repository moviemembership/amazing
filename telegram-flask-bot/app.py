import os
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

PRODUCT_NAME = "Digital Access"
PRICE = "RM10"
LOW_STOCK_LIMIT = 5
SUPPORT_LINK = "https://t.me/moviemembership"


def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


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
                    raw_item TEXT,
                    formatted_item TEXT,
                    status TEXT DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

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

    if len(parts) != 3:
        return raw_item

    access_id, code, slot = parts

    return (
        f"Access ID: {access_id}\n"
        f"Code: {code}\n"
        f"Slot: {slot}"
    )


def get_available_stock():
    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, raw_item
                FROM stock
                WHERE status = 'available'
                ORDER BY id ASC;
            """)
            return cur.fetchall()


def get_stock_count():
    return len(get_available_stock())


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


def get_next_stock():
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

            item = cur.fetchone()

            if not item:
                return None

            cur.execute("""
                UPDATE stock
                SET status = 'used',
                    used_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (item["id"],))

            conn.commit()
            return item["raw_item"]


def save_order(telegram_id, username, first_name, raw_item):
    formatted_item = format_item(raw_item)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (telegram_id, username, first_name, raw_item, formatted_item, status)
                VALUES (%s, %s, %s, %s, %s, 'completed');
            """, (telegram_id, username, first_name, raw_item, formatted_item))
            conn.commit()


def update_orders_replace(old_item, new_item):
    new_formatted = format_item(new_item)

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT telegram_id
                FROM orders
                WHERE raw_item = %s;
            """, (old_item,))

            buyers = cur.fetchall()

            cur.execute("""
                UPDATE orders
                SET raw_item = %s,
                    formatted_item = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE raw_item = %s;
            """, (new_item, new_formatted, old_item))

            conn.commit()

            return buyers, new_formatted


def main_menu(chat_id):
    stock_count = get_stock_count()

    keyboard = {
        "inline_keyboard": [
            [{"text": f"Buy Product - {PRICE}", "callback_data": "buy"}],
            [{"text": "Contact Customer Support 💬", "url": SUPPORT_LINK}]
        ]
    }

    send_message(
        chat_id,
        f"Hi 👋 What do you need?\n\n"
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


def handle_message(message):
    chat_id = message["chat"]["id"]

    if "photo" in message:
        handle_receipt(message)
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
                {"text": "Approve ✅", "callback_data": f"approve:{chat_id}:{username}:{name}"},
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

    send_message(chat_id, "Receipt received ✅\nPlease wait for admin approval.")


def handle_callback(callback):
    answer_callback(callback["id"])

    data = callback["data"]

    if data == "buy":
        handle_buy(callback)

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

    send_message(
        ADMIN_ID,
        f"New Order 🛒\n\n"
        f"Customer: @{username}\n"
        f"Name: {name}\n"
        f"Telegram ID: {chat_id}\n"
        f"Stock Before Payment: {stock_count}"
    )

    send_photo_file(chat_id, "qr.jpg", "Scan QR and complete payment.")


def handle_approve(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(callback["from"]["id"], "You are not allowed to do this.")
        return

    parts = callback["data"].split(":")
    customer_id = int(parts[1])
    username = parts[2] if len(parts) > 2 else "No username"
    name = parts[3] if len(parts) > 3 else ""

    raw_item = get_next_stock()

    if not raw_item:
        send_message(customer_id, "Payment approved, but stock is empty. Please contact admin.")
        send_message(ADMIN_ID, "No stock left ❌")
        return

    formatted_item = format_item(raw_item)

    save_order(customer_id, username, name, raw_item)

    send_message(
        customer_id,
        f"Payment Approved ✅\n\n"
        f"Here is your product:\n\n"
        f"{formatted_item}\n\n"
        f"Thank you for your purchase."
    )

    remaining = get_stock_count()

    send_message(
        ADMIN_ID,
        f"Order Completed ✅\n\n"
        f"Customer ID: {customer_id}\n"
        f"Delivered:\n\n"
        f"{formatted_item}\n\n"
        f"Remaining Stock: {remaining}"
    )


def handle_reject(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(callback["from"]["id"], "You are not allowed to do this.")
        return

    customer_id = int(callback["data"].split(":")[1])

    send_message(customer_id, "Payment rejected ❌\nPlease check your receipt and send again.")
    send_message(ADMIN_ID, f"Order rejected ❌\nCustomer ID: {customer_id}")


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
                    f"Manual Delivery ✅\n\nHere is your updated product:\n\n{formatted}"
                )
                save_order(telegram_id, "manual", "manual", raw_item)

        elif action == "replace_item":
            old_item = request.form.get("old_item", "").strip()
            new_item = request.form.get("new_item", "").strip()

            if old_item and new_item:
                buyers, formatted = update_orders_replace(old_item, new_item)

                for buyer in buyers:
                    send_message(
                        buyer["telegram_id"],
                        f"Product Replacement ✅\n\nYour updated product:\n\n{formatted}"
                    )

        elif action == "delete_orders":
            ids = request.form.getlist("order_ids")

            with db() as conn:
                with conn.cursor() as cur:
                    for order_id in ids:
                        cur.execute("DELETE FROM orders WHERE id = %s;", (order_id,))
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
            <td>{o['id']}</td>
            <td>{o['telegram_id']}</td>
            <td>{o['username']}</td>
            <td><pre>{o['formatted_item']}</pre></td>
            <td>{o['status']}</td>
            <td>{o['created_at']}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>Telegram Bot Admin</title>
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
            .card {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; }}
            textarea {{ width: 100%; height: 220px; }}
            input {{ padding: 8px; margin: 5px 0; width: 100%; }}
            button {{ padding: 10px 16px; margin-top: 8px; background: #1677ff; color: white; border: 0; border-radius: 5px; }}
            table {{ border-collapse: collapse; width: 100%; background: white; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; vertical-align: top; }}
            pre {{ white-space: pre-wrap; margin: 0; }}
        </style>
    </head>
    <body>

        <h1>Telegram Bot Admin</h1>

        <div class="card">
            <h2>Accounts / Stock ({available_count} remaining)</h2>
            <form method="POST">
                <input type="hidden" name="action" value="update_stock">
                <textarea name="accounts">{account_text}</textarea>
                <button type="submit">Update Accounts</button>
            </form>
        </div>

        <div class="card">
            <h2>Manual Delivery</h2>
            <form method="POST">
                <input type="hidden" name="action" value="manual_delivery">
                <input name="telegram_id" placeholder="Telegram ID">
                <input name="manual_item" placeholder="ACCESS001----CODE123----1">
                <button type="submit">Manual Delivery</button>
            </form>
        </div>

        <div class="card">
            <h2>Replace Delivered Item</h2>
            <form method="POST">
                <input type="hidden" name="action" value="replace_item">
                <input name="old_item" placeholder="Old item exact text">
                <input name="new_item" placeholder="New item exact text">
                <button type="submit">Replace & Notify Buyers</button>
            </form>
        </div>

        <div class="card">
            <h2>Orders</h2>

            <form method="GET">
                <input type="hidden" name="key" value="{ADMIN_KEY}">
                <input type="date" name="date" value="{date_filter}">
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
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
            }}
        </script>

    </body>
    </html>
    """
