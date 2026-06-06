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


def get_next_stock():
    with open("stock.txt", "r") as f:
        lines = f.readlines()

    if not lines:
        return None

    code = lines[0].strip()

    with open("stock.txt", "w") as f:
        f.writelines(lines[1:])

    return code


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
            keyboard = {
                "inline_keyboard": [[
                    {"text": f"Buy {PRODUCT_NAME} - {PRICE}", "callback_data": "buy"}
                ]]
            }

            send_message(
                chat_id,
                "Welcome 👋\n\nClick below to buy:",
                keyboard
            )

        elif "photo" in message:
            user = message["from"]
            username = user.get("username", "No username")
            name = user.get("first_name", "")

            photo_id = message["photo"][-1]["file_id"]

            keyboard = {
                "inline_keyboard": [[
                    {"text": "Approve ✅", "callback_data": f"approve:{chat_id}"},
                    {"text": "Reject ❌", "callback_data": f"reject:{chat_id}"}
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
                        f"Price: {PRICE}"
                    ),
                    "reply_markup": keyboard
                }
            )

            send_message(chat_id, "Receipt received ✅ Please wait for approval.")

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

            customer_msg = (
                f"Order Created ✅\n\n"
                f"Order ID: {chat_id}\n"
                f"Product: {PRODUCT_NAME}\n"
                f"Price: {PRICE}\n\n"
                "Please pay using the QR below, then send your receipt screenshot here."
            )

            admin_msg = (
                f"New Order 🛒\n\n"
                f"Order ID: {chat_id}\n"
                f"Customer: @{username}\n"
                f"Name: {name}\n"
                f"Telegram ID: {chat_id}\n"
                f"Product: {PRODUCT_NAME}\n"
                f"Price: {PRICE}\n"
                f"Status: Waiting for receipt"
            )

            send_message(chat_id, customer_msg)
            send_message(ADMIN_ID, admin_msg)
            send_photo_file(chat_id, "qr.png", "Payment QR 👆")

        elif data.startswith("approve:") or data.startswith("reject:"):
            admin_id = callback["from"]["id"]

            if admin_id != ADMIN_ID:
                send_message(admin_id, "You are not allowed to do this.")
                return "OK"

            action, customer_id = data.split(":")
            customer_id = int(customer_id)

            if action == "approve":
                code = get_next_stock()

                if code:
                    customer_msg = (
                        f"Payment Approved ✅\n\n"
                        f"Order ID: {customer_id}\n"
                        f"Product: {PRODUCT_NAME}\n"
                        f"Price: {PRICE}\n\n"
                        f"Here is your product:\n{code}\n\n"
                        "Thank you for your purchase."
                    )

                    admin_msg = (
                        f"Order Completed ✅\n\n"
                        f"Order ID: {customer_id}\n"
                        f"Customer Telegram ID: {customer_id}\n"
                        f"Product: {PRODUCT_NAME}\n"
                        f"Price: {PRICE}\n"
                        f"Delivered Item:\n{code}"
                    )

                    send_message(customer_id, customer_msg)
                    send_message(ADMIN_ID, admin_msg)

                else:
                    send_message(customer_id, "Payment approved, but stock is empty. Please contact admin.")
                    send_message(ADMIN_ID, "No stock left ❌")

            else:
                send_message(customer_id, "Payment rejected ❌ Please check your receipt and send again.")
                send_message(ADMIN_ID, f"Order Rejected ❌\n\nOrder ID: {customer_id}")

    return "OK"
