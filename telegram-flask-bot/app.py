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

PRODUCT_NAME = "Digital Product"
PRICE = "RM10"
LOW_STOCK_LIMIT = 5
SUPPORT_LINK = "https://t.me/YOUR_USERNAME"


def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock (
                    id SERIAL PRIMARY KEY,
                    raw_item TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
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
                    product TEXT,
                    price TEXT,
                    status TEXT DEFAULT 'waiting_payment',
                    delivered_item TEXT,
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
        send_message(ADMIN_ID, f"❌ Missing file: {photo_path}")
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


def get_stock_count():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stock WHERE status = 'available';")
            return cur.fetchone()[0]


def add_stock_item(raw_item):
    raw_item = raw_item.strip()
    if not raw_item:
        return

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO stock (raw_item, status) VALUES (%s, 'available');",
                (raw_item,)
            )
            conn.commit()


def delete_stock_item(item_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM stock WHERE id = %s AND status = 'available';",
                (item_id,)
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
                SET status = 'used', used_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (item["id"],))

            conn.commit()
            return item["raw_item"]


def format_stock_item(raw_item):
    parts = raw_item.split("----")

    if len(parts) != 3:
        return raw_item

    access_id, code, slot = parts

    return (
        f"Access ID: {access_id}\n"
        f"Code: {code}\n"
        f"Slot: {slot}"
    )


def create_order(telegram_id, username, first_name):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (telegram_id, username, first_name, product, price, status)
                VALUES (%s, %s, %s, %s, %s, 'waiting_payment')
                RETURNING id;
            """, (telegram_id, username, first_name, PRODUCT_NAME, PRICE))
            order_id = cur.fetchone()[0]
            conn.commit()
            return order_id


def update_order_completed(telegram_id, delivered_item):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE orders
                SET status = 'completed',
                    delivered_item = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = %s
                  AND status = 'waiting_payment';
            """, (delivered_item, telegram_id))
            conn.commit()


def update_order_rejected(telegram_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE orders
                SET status = 'rejected',
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = %s
                  AND status = 'waiting_payment';
            """, (telegram_id,))
            conn.commit()


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
    stock_count = get_stock_count()

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
            f"Stock Left Now: {stock_count}"
        ),
        reply_markup=keyboard
    )

    send_message(chat_id, "Receipt received ✅\nPlease wait for admin approval.")


def handle_callback(callback):
    callback_id = callback["id"]
    data = callback["data"]

    answer_callback(callback_id)

    if data == "buy":
        handle_buy(callback)
        return

    if data.startswith("approve:"):
        handle_approve(callback)
        return

    if data.startswith("reject:"):
        handle_reject(callback)
        return


def handle_buy(callback):
    chat_id = callback["message"]["chat"]["id"]
    user = callback["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")

    stock_count = get_stock_count()

    if stock_count <= 0:
        send_message(chat_id, "❌ Sorry, this product is currently out of stock.")
        send_message(ADMIN_ID, "🚨 STOCK ALERT\n\nStock has reached 0.")
        return

    if stock_count <= LOW_STOCK_LIMIT:
        send_message(
            ADMIN_ID,
            f"⚠️ LOW STOCK WARNING\n\nOnly {stock_count} stock(s) remaining."
        )

    order_id = create_order(chat_id, username, name)

    customer_msg = (
        f"🛒 Order Created\n\n"
        f"Order ID: {order_id}\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n"
        f"Stock Left: {stock_count}\n\n"
        f"Please make payment using the QR code below.\n"
        f"After payment, send your receipt screenshot here."
    )

    admin_msg = (
        f"🔔 NEW ORDER\n\n"
        f"Order ID: {order_id}\n"
        f"Customer: @{username}\n"
        f"Name: {name}\n"
        f"Telegram ID: {chat_id}\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n"
        f"Stock Before Payment: {stock_count}\n\n"
        f"Status: Waiting For Payment"
    )

    send_message(chat_id, customer_msg)
    send_message(ADMIN_ID, admin_msg)
    send_photo_file(chat_id, "qr.jpg", "📱 Scan QR and complete payment.")


def handle_approve(callback):
    admin_id = callback["from"]["id"]

    if admin_id != ADMIN_ID:
        send_message(admin_id, "You are not allowed to do this.")
        return

    customer_id = int(callback["data"].split(":")[1])

    raw_item = get_next_stock()
    remaining_stock = get_stock_count()

    if not raw_item:
        send_message(customer_id, "Payment approved, but stock is empty. Please contact admin.")
        send_message(ADMIN_ID, "❌ No stock left. Payment was approved but no item could be delivered.")
        return

    formatted_item = format_stock_item(raw_item)
    update_order_completed(customer_id, raw_item)

    send_message(
        customer_id,
        f"Payment Approved ✅\n\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n\n"
        f"Here is your product:\n\n"
        f"{formatted_item}\n\n"
        f"Thank you for your purchase."
    )

    send_message(
        ADMIN_ID,
        f"Order Completed ✅\n\n"
        f"Customer Telegram ID: {customer_id}\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Delivered Item:\n\n"
        f"{formatted_item}\n\n"
        f"Remaining Stock: {remaining_stock}"
    )

    if remaining_stock <= LOW_STOCK_LIMIT:
        send_message(
            ADMIN_ID,
            f"⚠️ LOW STOCK WARNING\n\nOnly {remaining_stock} stock(s) left."
        )


def handle_reject(callback):
    admin_id = callback["from"]["id"]

    if admin_id != ADMIN_ID:
        send_message(admin_id, "You are not allowed to do this.")
        return

    customer_id = int(callback["data"].split(":")[1])
    update_order_rejected(customer_id)

    send_message(customer_id, "Payment rejected ❌\nPlease check your receipt and send again.")
    send_message(ADMIN_ID, f"Order Rejected ❌\n\nCustomer ID: {customer_id}")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.args.get("key") != ADMIN_KEY:
        return "Unauthorized", 403

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            items = request.form.get("items", "")
            for line in items.splitlines():
                if line.strip():
                    add_stock_item(line.strip())

        if action == "delete":
            item_id = int(request.form.get("item_id"))
            delete_stock_item(item_id)

        return redirect(f"/admin?key={ADMIN_KEY}")

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, raw_item, status, created_at, used_at
                FROM stock
                ORDER BY id DESC
                LIMIT 200;
            """)
            stocks = cur.fetchall()

            cur.execute("""
                SELECT id, telegram_id, username, product, price, status, delivered_item, created_at
                FROM orders
                ORDER BY id DESC
                LIMIT 100;
            """)
            orders = cur.fetchall()

    available_count = get_stock_count()

    stock_rows = ""
    for s in stocks:
        stock_rows += f"""
        <tr>
            <td>{s['id']}</td>
            <td><pre>{s['raw_item']}</pre></td>
            <td>{s['status']}</td>
            <td>{s['created_at']}</td>
            <td>{s['used_at']}</td>
            <td>
                {'<form method="POST"><input type="hidden" name="action" value="delete"><input type="hidden" name="item_id" value="' + str(s['id']) + '"><button>Delete</button></form>' if s['status'] == 'available' else ''}
            </td>
        </tr>
        """

    order_rows = ""
    for o in orders:
        order_rows += f"""
        <tr>
            <td>{o['id']}</td>
            <td>{o['telegram_id']}</td>
            <td>{o['username']}</td>
            <td>{o['product']}</td>
            <td>{o['price']}</td>
            <td>{o['status']}</td>
            <td><pre>{o['delivered_item']}</pre></td>
            <td>{o['created_at']}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>Bot Admin</title>
        <style>
            body {{ font-family: Arial; padding: 20px; }}
            textarea {{ width: 100%; height: 150px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; vertical-align: top; }}
            pre {{ white-space: pre-wrap; margin: 0; }}
            .box {{ padding: 15px; background: #f2f2f2; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <h1>Telegram Bot Admin</h1>

        <div class="box">
            <h2>Available Stock: {available_count}</h2>
            <p>Stock format example:</p>
            <pre>ACCESS001----CODE123----1</pre>
        </div>

        <h2>Add Stock</h2>
        <form method="POST">
            <input type="hidden" name="action" value="add">
            <textarea name="items" placeholder="One item per line"></textarea><br><br>
            <button type="submit">Add Stock</button>
        </form>

        <h2>Stock List</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Raw Item</th>
                <th>Status</th>
                <th>Created</th>
                <th>Used</th>
                <th>Action</th>
            </tr>
            {stock_rows}
        </table>

        <h2>Orders</h2>
        <table>
            <tr>
                <th>Order ID</th>
                <th>Telegram ID</th>
                <th>Username</th>
                <th>Product</th>
                <th>Price</th>
                <th>Status</th>
                <th>Delivered Item</th>
                <th>Created</th>
            </tr>
            {order_rows}
        </table>
    </body>
    </html>
    """
