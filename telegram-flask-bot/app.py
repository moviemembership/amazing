import os
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

PRODUCT_NAME = "Digital Product"
PRICE = "RM10"


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    requests.post(f"{BASE_URL}/sendMessage", json=data)


def send_photo_file(chat_id, photo_path, caption=""):
    with open(photo_path, "rb") as photo:
        requests.post(
            f"{BASE_URL}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": photo}
        )


def get_stock_count():
    if not os.path.exists("stock.txt"):
        return 0

    with open("stock.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    return len(lines)


def get_next_stock():
    if not os.path.exists("stock.txt"):
        return None

    with open("stock.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    if not lines:
        return None

    item = lines[0]

    with open("stock.txt", "w", encoding="utf-8") as f:
        for line in lines[1:]:
            f.write(line + "\n")

    return item


@app.route("/")
def home():
    return "Bot is running."


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]

        if message.get("text") == "/start":
            stock_count = get_stock_count()

            keyboard = {
                "inline_keyboard": [[
                    {
                        "text": f"Buy {PRODUCT_NAME} - {PRICE}",
                        "callback_data": "buy"
                    }
                ]]
            }

            send_message(
                chat_id,
                f"Welcome 👋\n\n"
                f"Product: {PRODUCT_NAME}\n"
                f"Price: {PRICE}\n"
                f"Available Stock: {stock_count}\n\n"
                f"Click below to buy:",
                keyboard
            )

        elif "photo" in message:
            user = message["from"]
            username = user.get("username", "No username")
            name = user.get("first_name", "")
            photo_id = message["photo"][-1]["file_id"]

            keyboard = {
                "inline_keyboard": [[
                    {
                        "text": "Approve ✅",
                        "callback_data": f"approve:{chat_id}"
                    },
                    {
                        "text": "Reject ❌",
                        "callback_data": f"reject:{chat_id}"
                    }
                ]]
            }

            requests.post(
                f"{BASE_URL}/sendPhoto",
                json={
                    "chat_id": ADMIN_ID,
                    "photo": photo_id,
                    "caption": (
                        f"Receipt Received 🧾\n\n"
                        f"Order ID: {chat_id}\n"
                        f"Customer: @{username}\n"
                        f"Name: {name}\n"
                        f"Telegram ID: {chat_id}\n"
                        f"Product: {PRODUCT_NAME}\n"
                        f"Price: {PRICE}\n"
                        f"Current Stock: {get_stock_count()}"
                    ),
                    "reply_markup": keyboard
                }
            )

            send_message(
                chat_id,
                "Receipt received ✅\nPlease wait for admin approval."
            )

    elif "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        callback_id = callback["id"]

        requests.post(
            f"{BASE_URL}/answerCallbackQuery",
            json={"callback_query_id": callback_id}
        )

        if data == "buy":
            chat_id = callback["message"]["chat"]["id"]
            user = callback["from"]
            username = user.get("username", "No username")
            name = user.get("first_name", "")

            stock_count = get_stock_count()

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

                return "OK"

            if stock_count <= 5:
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
                f"Available Stock: {stock_count}\n\n"
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
                f"Stock Before Order: {stock_count}\n\n"
                f"Status: Waiting For Payment"
            )

            send_message(chat_id, customer_msg)
            send_message(ADMIN_ID, admin_msg)
            send_photo_file(chat_id, "qr.jpg", "📱 Scan QR and complete payment.")

        elif data.startswith("approve:") or data.startswith("reject:"):
            admin_id = callback["from"]["id"]

            if admin_id != ADMIN_ID:
                send_message(admin_id, "You are not allowed to do this.")
                return "OK"

            action, customer_id = data.split(":")
            customer_id = int(customer_id)

            if action == "approve":
                item = get_next_stock()
                remaining_stock = get_stock_count()

                if item:
                    customer_msg = (
                        f"Payment Approved ✅\n\n"
                        f"Order ID: {customer_id}\n"
                        f"Product: {PRODUCT_NAME}\n"
                        f"Price: {PRICE}\n\n"
                        f"Here is your product:\n{item}\n\n"
                        f"Thank you for your purchase."
                    )

                    admin_msg = (
                        f"Order Completed ✅\n\n"
                        f"Order ID: {customer_id}\n"
                        f"Customer Telegram ID: {customer_id}\n"
                        f"Product: {PRODUCT_NAME}\n"
                        f"Price: {PRICE}\n"
                        f"Delivered Item:\n{item}\n\n"
                        f"Remaining Stock: {remaining_stock}"
                    )

                    send_message(customer_id, customer_msg)
                    send_message(ADMIN_ID, admin_msg)

                    if remaining_stock <= 5:
                        send_message(
                            ADMIN_ID,
                            f"⚠️ LOW STOCK WARNING ⚠️\n\n"
                            f"Only {remaining_stock} stock(s) left after this order.\n"
                            f"Please restock soon."
                        )

                else:
                    send_message(
                        customer_id,
                        "Payment approved, but stock is currently empty. Please contact admin."
                    )
                    send_message(
                        ADMIN_ID,
                        "No stock left ❌\nPayment was approved but no item could be delivered."
                    )

            else:
                send_message(
                    customer_id,
                    "Payment rejected ❌\nPlease check your receipt and send again."
                )

                send_message(
                    ADMIN_ID,
                    f"Order Rejected ❌\n\nOrder ID: {customer_id}"
                )

    return "OK"
