import os
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

PRODUCT_NAME = "Digital Product"
PRICE = "RM10"
LOW_STOCK_LIMIT = 5


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


def get_stock_lines():
    if not os.path.exists("stock.txt"):
        print("stock.txt not found", flush=True)
        return []

    with open("stock.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Current stock count: {len(lines)}", flush=True)
    return lines


def get_stock_count():
    return len(get_stock_lines())


def get_next_stock():
    lines = get_stock_lines()

    if not lines:
        return None

    item = lines[0]
    remaining_lines = lines[1:]

    with open("stock.txt", "w", encoding="utf-8") as f:
        for line in remaining_lines:
            f.write(line + "\n")

    return item


def answer_callback(callback_id):
    requests.post(
        f"{BASE_URL}/answerCallbackQuery",
        json={"callback_query_id": callback_id}
    )


def main_menu(chat_id):
    stock_count = get_stock_count()

    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"Buy Product - {PRICE}", "callback_data": "buy"}
            ],
            [
                {"text": "Contact Customer Support 💬", "https://t.me/moviemembership"}
            ]
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

    print("Update received:", update, flush=True)

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

    # Anything user types will show the menu
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
            f"Order ID: {chat_id}\n"
            f"Customer: @{username}\n"
            f"Name: {name}\n"
            f"Telegram ID: {chat_id}\n"
            f"Product: {PRODUCT_NAME}\n"
            f"Price: {PRICE}\n"
            f"Stock Left Now: {stock_count}"
        ),
        reply_markup=keyboard
    )

    send_message(
        chat_id,
        "Receipt received ✅\nPlease wait for admin approval."
    )


def handle_callback(callback):
    callback_id = callback["id"]
    data = callback["data"]

    answer_callback(callback_id)

    if data == "buy":
        handle_buy(callback)
        return

    if data == "support":
        handle_support(callback)
        return

    if data.startswith("approve:"):
        handle_approve(callback)
        return

    if data.startswith("reject:"):
        handle_reject(callback)
        return


def handle_support(callback):
    chat_id = callback["message"]["chat"]["id"]
    user = callback["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")

    send_message(
        chat_id,
        "Customer Support 💬\n\n"
        "Please type your question here. Admin will reply to you as soon as possible."
    )

    send_message(
        ADMIN_ID,
        f"Customer Support Request 💬\n\n"
        f"Customer: @{username}\n"
        f"Name: {name}\n"
        f"Telegram ID: {chat_id}"
    )


def handle_buy(callback):
    chat_id = callback["message"]["chat"]["id"]
    user = callback["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")

    stock_count = get_stock_count()

    print(f"BUY CLICKED | chat_id={chat_id} | stock_count={stock_count}", flush=True)

    if stock_count <= 0:
        send_message(
            chat_id,
            "❌ Sorry, this product is currently out of stock.\nPlease try again later."
        )

        send_message(
            ADMIN_ID,
            "🚨 STOCK ALERT 🚨\n\n"
            "Stock has reached 0.\n"
            "Please add more stock to stock.txt."
        )

        return

    if stock_count <= LOW_STOCK_LIMIT:
        send_message(
            ADMIN_ID,
            f"⚠️ LOW STOCK WARNING ⚠️\n\n"
            f"Only {stock_count} stock(s) remaining.\n"
            f"Please add more stock soon."
        )

    customer_msg = (
        f"🛒 Order Created\n\n"
        f"Order ID: {chat_id}\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n"
        f"Stock Left: {stock_count}\n\n"
        f"Please make payment using the QR code below.\n"
        f"After payment, send your receipt screenshot here."
    )

    admin_msg = (
        f"🔔 NEW ORDER\n\n"
        f"Order ID: {chat_id}\n"
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

    item = get_next_stock()
    remaining_stock = get_stock_count()

    if not item:
        send_message(
            customer_id,
            "Payment approved, but stock is currently empty. Please contact admin."
        )

        send_message(
            ADMIN_ID,
            "❌ No stock left.\nPayment was approved but no item could be delivered."
        )

        return

    send_message(
        customer_id,
        f"Payment Approved ✅\n\n"
        f"Order ID: {customer_id}\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n\n"
        f"Here is your product:\n{item}\n\n"
        f"Thank you for your purchase."
    )

    send_message(
        ADMIN_ID,
        f"Order Completed ✅\n\n"
        f"Order ID: {customer_id}\n"
        f"Customer Telegram ID: {customer_id}\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Price: {PRICE}\n"
        f"Delivered Item:\n{item}\n\n"
        f"Remaining Stock: {remaining_stock}"
    )

    if remaining_stock <= LOW_STOCK_LIMIT:
        send_message(
            ADMIN_ID,
            f"⚠️ LOW STOCK WARNING ⚠️\n\n"
            f"Only {remaining_stock} stock(s) left after this order.\n"
            f"Please restock soon."
        )


def handle_reject(callback):
    admin_id = callback["from"]["id"]

    if admin_id != ADMIN_ID:
        send_message(admin_id, "You are not allowed to do this.")
        return

    customer_id = int(callback["data"].split(":")[1])

    send_message(
        customer_id,
        "Payment rejected ❌\nPlease check your receipt and send again."
    )

    send_message(
        ADMIN_ID,
        f"Order Rejected ❌\n\nOrder ID: {customer_id}"
    )
