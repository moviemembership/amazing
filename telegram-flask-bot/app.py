import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect, render_template, url_for
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


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


def malaysia_now():
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))


def db():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )

    try:
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Asia/Kuala_Lumpur';")

        conn.commit()
        return conn

    except Exception:
        conn.rollback()
        conn.close()
        raise


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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS warranty_reminders (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL
                        REFERENCES orders(id) ON DELETE CASCADE,
                    reminder_type TEXT NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(order_id, reminder_type)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS email_accounts (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    parent_id INTEGER
                        REFERENCES email_accounts(id)
                        ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expiry_date DATE NOT NULL
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_accounts_parent_id
                ON email_accounts(parent_id);
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_accounts_email
                ON email_accounts(email);
            """)

            cur.execute(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS raw_item TEXT;"
            )
            cur.execute(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS formatted_item TEXT;"
            )
            cur.execute(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_item TEXT;"
            )

            conn.commit()


init_db()


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}

    if reply_markup:
        data["reply_markup"] = reply_markup

    try:
        response = requests.post(
            f"{BASE_URL}/sendMessage",
            json=data,
            timeout=15
        )
        result = response.json()
        return response.ok and result.get("ok", False)
    except (requests.RequestException, ValueError):
        return False


def send_photo_file(chat_id, photo_path, caption=""):
    if not os.path.exists(photo_path):
        send_message(ADMIN_ID, f"Missing file: {photo_path}")
        return

    with open(photo_path, "rb") as photo:
        requests.post(
            f"{BASE_URL}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": photo},
            timeout=30
        )


def send_photo_by_file_id(chat_id, file_id, caption="", reply_markup=None):
    data = {
        "chat_id": chat_id,
        "photo": file_id,
        "caption": caption
    }

    if reply_markup:
        data["reply_markup"] = reply_markup

    requests.post(
        f"{BASE_URL}/sendPhoto",
        json=data,
        timeout=30
    )


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
    except requests.RequestException:
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


def get_account_email(raw_item):
    if not raw_item:
        return ""

    return raw_item.split("----", 1)[0].strip()


def get_slot(raw_item):
    parts = raw_item.split("----")
    if len(parts) >= 3:
        return parts[2]
    return ""


def get_stock_count():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM stock
                WHERE status = 'available';
            """)
            return cur.fetchone()[0]


def sync_stock_from_textarea(text):
    new_items = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM stock
                WHERE status = 'available';
            """)

            for item in new_items:
                cur.execute("""
                    INSERT INTO stock (raw_item, status)
                    VALUES (%s, 'available');
                """, (item,))

            conn.commit()


def save_order(
    telegram_id,
    username,
    first_name,
    raw_item,
    formatted_item
):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (
                    telegram_id,
                    username,
                    first_name,
                    raw_item,
                    formatted_item,
                    delivered_item,
                    status
                )
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


def message_users_by_account_email(email, message):
    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT telegram_id
                FROM orders
                WHERE LOWER(
                    TRIM(
                        SPLIT_PART(
                            COALESCE(raw_item, ''),
                            '----',
                            1
                        )
                    )
                ) = LOWER(%s)
                AND telegram_id IS NOT NULL;
            """, (email.strip(),))

            recipients = cur.fetchall()

    sent = 0

    for recipient in recipients:
        success = send_message(
            recipient["telegram_id"],
            f"Message from admin 💬\n\n{message}"
        )

        if success:
            sent += 1

    return sent, len(recipients)


def send_due_warranty_reminders():
    reminders = [
        {
            "type": "three_days",
            "minimum_age": 25,
            "maximum_age": 28,
            "message": "Your product warranty expires in 3 days."
        },
        {
            "type": "expired",
            "minimum_age": 28,
            "maximum_age": None,
            "message": "Your 28-day product warranty has expired."
        }
    ]

    sent = 0
    failed = 0

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for reminder in reminders:
                query = """
                    SELECT
                        o.id,
                        o.telegram_id,
                        o.raw_item
                    FROM orders o
                    WHERE o.status = 'completed'
                    AND o.created_at <=
                        NOW() - (%s * INTERVAL '1 day')
                    AND NOT EXISTS (
                        SELECT 1
                        FROM warranty_reminders wr
                        WHERE wr.order_id = o.id
                        AND wr.reminder_type = %s
                    )
                """

                params = [
                    reminder["minimum_age"],
                    reminder["type"]
                ]

                if reminder["maximum_age"] is not None:
                    query += """
                        AND o.created_at >
                            NOW() - (%s * INTERVAL '1 day')
                    """
                    params.append(reminder["maximum_age"])

                query += " ORDER BY o.created_at ASC;"

                cur.execute(query, params)
                orders = cur.fetchall()

                for order in orders:
                    email = get_account_email(order["raw_item"])

                    success = send_message(
                        order["telegram_id"],
                        f"Warranty Reminder 🔔\n\n"
                        f"{reminder['message']}\n"
                        f"Account: {email or 'Not available'}\n\n"
                        f"Need help? {SUPPORT_LINK}"
                    )

                    if success:
                        cur.execute("""
                            INSERT INTO warranty_reminders
                                (order_id, reminder_type)
                            VALUES (%s, %s)
                            ON CONFLICT
                                (order_id, reminder_type)
                            DO NOTHING;
                        """, (
                            order["id"],
                            reminder["type"]
                        ))
                        sent += 1
                    else:
                        failed += 1

            conn.commit()

    return sent, failed


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


def parse_bulk_email_lines(text):
    results = []
    errors = []

    for line_number, original_line in enumerate(
        text.splitlines(),
        start=1
    ):
        line = original_line.strip()

        if not line:
            continue

        parts = line.split("---", 1)

        if len(parts) != 2:
            errors.append(
                f"Line {line_number}: must use email---password"
            )
            continue

        email_value = parts[0].strip()
        password_value = parts[1].strip()

        if not email_value or not password_value:
            errors.append(
                f"Line {line_number}: email and password are required"
            )
            continue

        results.append((email_value, password_value))

    return results, errors


@app.route("/")
def home():
    return "Bot is running."


@app.route("/warranty-reminders", methods=["GET", "POST"])
def warranty_reminders():
    if request.args.get("key") != ADMIN_KEY:
        return {"error": "Unauthorized"}, 403

    sent, failed = send_due_warranty_reminders()

    return {
        "ok": True,
        "sent": sent,
        "failed": failed
    }


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

        elif action == "message_by_email":
            account_email = request.form.get(
                "account_email",
                ""
            ).strip()

            message_content = request.form.get(
                "message_content",
                ""
            ).strip()

            if account_email and message_content:
                sent, total = message_users_by_account_email(
                    account_email,
                    message_content
                )

                send_message(
                    ADMIN_ID,
                    f"Account email message completed ✅\n\n"
                    f"Account: {account_email}\n"
                    f"Delivered: {sent}/{total}"
                )

        elif action == "run_warranty_reminders":
            sent, failed = send_due_warranty_reminders()

            send_message(
                ADMIN_ID,
                f"Warranty reminders completed ✅\n\n"
                f"Sent: {sent}\n"
                f"Failed: {failed}"
            )

        return redirect(
            url_for("admin", key=ADMIN_KEY)
        )

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
                       DATE_PART(
                           'day',
                           NOW() - created_at
                       ) AS order_age
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
                        COALESCE(username, '') ILIKE %s OR
                        COALESCE(raw_item, '') ILIKE %s OR
                        COALESCE(formatted_item, '') ILIKE %s
                    )
                """
                search_term = f"%{search}%"
                params.extend([
                    search_term,
                    search_term,
                    search_term,
                    search_term,
                    search_term
                ])

            query += """
                ORDER BY created_at DESC
                LIMIT 500;
            """

            cur.execute(query, params)
            orders = cur.fetchall()

    account_text = "\n".join(
        item["raw_item"] for item in stock_items
    )

    return render_template(
        "admin.html",
        admin_key=ADMIN_KEY,
        available_count=len(stock_items),
        total_orders=len(orders),
        account_text=account_text,
        orders=orders,
        search=search,
        date_from=date_from,
        date_to=date_to
    )


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
                        (
                            telegram_id,
                            username,
                            raw_item,
                            formatted_item,
                            delivered_item,
                            status,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s,
                            'completed', %s, %s
                        );
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
                        SET telegram_id = %s,
                            username = %s,
                            raw_item = %s,
                            formatted_item = %s,
                            delivered_item = %s,
                            created_at = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s;
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
                return redirect(
                    url_for("admin", key=ADMIN_KEY)
                )

            if is_new:
                now_time = malaysia_now().strftime(
                    "%Y-%m-%dT%H:%M"
                )
                order = {
                    "id": "NEW",
                    "telegram_id": "",
                    "username": "",
                    "raw_item": "",
                    "created_at": now_time
                }
            else:
                cur.execute("""
                    SELECT *
                    FROM orders
                    WHERE id = %s;
                """, (order_id,))
                order = cur.fetchone()

                if not order:
                    return "Order not found", 404

                if order["created_at"]:
                    order["created_at"] = (
                        order["created_at"]
                        .strftime("%Y-%m-%dT%H:%M")
                    )

    return render_template(
        "edit_order.html",
        is_new=is_new,
        order=order,
        preview=format_item(order.get("raw_item", "")),
        admin_key=ADMIN_KEY
    )


@app.route("/email-list", methods=["GET", "POST"])
def email_list():
    notice = request.args.get("notice", "")
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "latest")

    if sort not in {"latest", "oldest"}:
        sort = "latest"

    if request.method == "POST":
        selected_ids = request.form.getlist("selected_ids")
        valid_ids = []

        for value in selected_ids:
            try:
                valid_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        if not valid_ids:
            return redirect(
                url_for(
                    "email_list",
                    notice="none_selected",
                    search=search,
                    sort=sort
                )
            )

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM email_accounts
                    WHERE id = ANY(%s)
                    AND parent_id IS NULL;
                """, (valid_ids,))
                conn.commit()

        return redirect(
            url_for("email_list", notice="deleted")
        )

    direction = "DESC" if sort == "latest" else "ASC"

    query = """
        SELECT
            p.id,
            p.email,
            p.password,
            p.created_at,
            p.expiry_date
        FROM email_accounts p
        WHERE p.parent_id IS NULL
    """
    params = []

    if search:
        term = f"%{search}%"
        query += """
            AND (
                p.email ILIKE %s
                OR p.password ILIKE %s
                OR CAST(p.id AS TEXT) ILIKE %s
                OR EXISTS (
                    SELECT 1
                    FROM email_accounts r
                    WHERE r.parent_id = p.id
                    AND (
                        r.email ILIKE %s
                        OR r.password ILIKE %s
                        OR CAST(r.id AS TEXT) ILIKE %s
                    )
                )
            )
        """
        params.extend([
            term, term, term,
            term, term, term
        ])

    query += f"""
        ORDER BY
            p.created_at {direction},
            p.id {direction};
    """

    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            parents = cur.fetchall()

            parent_ids = [row["id"] for row in parents]
            replacements_by_parent = {}

            if parent_ids:
                cur.execute(f"""
                    SELECT
                        id,
                        email,
                        password,
                        parent_id,
                        created_at,
                        expiry_date
                    FROM email_accounts
                    WHERE parent_id = ANY(%s)
                    ORDER BY
                        created_at {direction},
                        id {direction};
                """, (parent_ids,))

                for replacement in cur.fetchall():
                    replacements_by_parent.setdefault(
                        replacement["parent_id"],
                        []
                    ).append(replacement)

            cur.execute("""
                SELECT COUNT(*) AS count
                FROM email_accounts
                WHERE parent_id IS NULL;
            """)
            total_parents = cur.fetchone()["count"]

            cur.execute("""
                SELECT COUNT(*) AS count
                FROM email_accounts
                WHERE parent_id IS NOT NULL;
            """)
            total_replacements = cur.fetchone()["count"]

    for parent in parents:
        parent["replacements"] = replacements_by_parent.get(
            parent["id"],
            []
        )

    return render_template(
        "email_list.html",
        parents=parents,
        total_parents=total_parents,
        total_replacements=total_replacements,
        search=search,
        sort=sort,
        notice=notice
    )


@app.route("/bulk-add-email", methods=["GET", "POST"])
def bulk_add_email():
    malaysia_today = malaysia_now().date()
    selected_date = request.form.get(
        "created_date",
        malaysia_today.isoformat()
    )
    bulk_text = request.form.get("bulk_text", "")
    error_message = ""

    if request.method == "POST":
        try:
            created_date = datetime.strptime(
                selected_date,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            error_message = "Please choose a valid date."
        else:
            accounts, errors = parse_bulk_email_lines(
                bulk_text
            )

            if errors:
                error_message = "\n".join(errors)
            elif not accounts:
                error_message = (
                    "Please enter at least one account."
                )
            else:
                created_at = datetime.combine(
                    created_date,
                    datetime.min.time()
                )
                expiry_date = (
                    created_date + timedelta(days=28)
                )

                with db() as conn:
                    with conn.cursor() as cur:
                        for email_value, password_value in accounts:
                            cur.execute("""
                                INSERT INTO email_accounts
                                (
                                    email,
                                    password,
                                    parent_id,
                                    created_at,
                                    expiry_date
                                )
                                VALUES (
                                    %s, %s, NULL, %s, %s
                                );
                            """, (
                                email_value,
                                password_value,
                                created_at,
                                expiry_date
                            ))

                        conn.commit()

                return redirect(
                    url_for(
                        "email_list",
                        notice="added"
                    )
                )

    return render_template(
        "bulk_add_email.html",
        selected_date=selected_date,
        bulk_text=bulk_text,
        error_message=error_message
    )


@app.route("/add-replacement", methods=["GET", "POST"])
def add_replacement():
    search = request.args.get("search", "").strip()
    selected_parent_id = (
        request.args.get("parent_id", "").strip()
    )

    replacement_email = request.form.get(
        "replacement_email",
        ""
    ).strip()

    replacement_password = request.form.get(
        "replacement_password",
        ""
    ).strip()

    error_message = ""

    if request.method == "POST":
        selected_parent_id = request.form.get(
            "parent_id",
            ""
        ).strip()

        try:
            parent_id = int(selected_parent_id)
        except (TypeError, ValueError):
            error_message = (
                "Please search and select a parent email first."
            )
        else:
            with db() as conn:
                with conn.cursor(
                    cursor_factory=RealDictCursor
                ) as cur:
                    cur.execute("""
                        SELECT
                            id,
                            email,
                            password,
                            created_at,
                            expiry_date
                        FROM email_accounts
                        WHERE id = %s
                        AND parent_id IS NULL;
                    """, (parent_id,))
                    parent = cur.fetchone()

                    if not parent:
                        error_message = (
                            "Parent email was not found."
                        )
                    elif not replacement_email:
                        error_message = (
                            "Replacement email is required."
                        )
                    elif not replacement_password:
                        error_message = (
                            "Replacement password is required."
                        )
                    else:
                        cur.execute("""
                            INSERT INTO email_accounts
                            (
                                email,
                                password,
                                parent_id,
                                created_at,
                                expiry_date
                            )
                            VALUES (%s, %s, %s, %s, %s);
                        """, (
                            replacement_email,
                            replacement_password,
                            parent["id"],
                            malaysia_now().replace(
                                tzinfo=None
                            ),
                            parent["expiry_date"]
                        ))
                        conn.commit()

                        return redirect(
                            url_for(
                                "email_list",
                                notice="replacement_added"
                            )
                        )

    search_results = []

    if search:
        with db() as conn:
            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cur:
                term = f"%{search}%"
                cur.execute("""
                    SELECT
                        id,
                        email,
                        password,
                        created_at,
                        expiry_date
                    FROM email_accounts
                    WHERE parent_id IS NULL
                    AND (
                        email ILIKE %s
                        OR password ILIKE %s
                        OR CAST(id AS TEXT) ILIKE %s
                    )
                    ORDER BY created_at DESC
                    LIMIT 30;
                """, (term, term, term))
                search_results = cur.fetchall()

    selected_parent = None

    if selected_parent_id:
        try:
            selected_parent_int = int(
                selected_parent_id
            )
        except ValueError:
            selected_parent_int = None

        if selected_parent_int is not None:
            with db() as conn:
                with conn.cursor(
                    cursor_factory=RealDictCursor
                ) as cur:
                    cur.execute("""
                        SELECT
                            id,
                            email,
                            password,
                            created_at,
                            expiry_date
                        FROM email_accounts
                        WHERE id = %s
                        AND parent_id IS NULL;
                    """, (selected_parent_int,))
                    selected_parent = cur.fetchone()

    return render_template(
        "add_replacement.html",
        search=search,
        search_results=search_results,
        selected_parent_id=selected_parent_id,
        selected_parent=selected_parent,
        replacement_email=replacement_email,
        replacement_password=replacement_password,
        error_message=error_message
    )


def main_menu(chat_id):
    stock_count = get_stock_count()

    keyboard = {
        "inline_keyboard": [
            [{
                "text": f"Buy Netflix Account - {PRICE}",
                "callback_data": "buy"
            }],
            [{
                "text": "Contact Customer Support 💬",
                "url": SUPPORT_LINK
            }]
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
        },
        timeout=15
    )


def handle_message(message):
    chat_id = message["chat"]["id"]

    if chat_id == ADMIN_ID and "text" in message:
        text = message["text"]

        if text.startswith("/msg "):
            parts = text.split(" ", 2)

            if len(parts) < 3:
                send_message(
                    ADMIN_ID,
                    "Format:\n/msg TELEGRAM_ID your message"
                )
                return

            target_id = parts[1]
            msg_content = parts[2]

            send_message(
                target_id,
                f"Message from admin 💬\n\n{msg_content}"
            )

            send_message(
                ADMIN_ID,
                f"Message sent ✅\n\n"
                f"To: {target_id}\n"
                f"Message: {msg_content}"
            )
            return

    if "photo" in message:
        forward_to_admin(message)
        handle_receipt(message)
        return

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
                {
                    "text": "Approve ✅",
                    "callback_data": f"approve:{chat_id}"
                },
                {
                    "text": "Reject ❌",
                    "callback_data": f"reject:{chat_id}"
                }
            ],
            [{
                "text": "Message 💬",
                "switch_inline_query_current_chat":
                    f"/msg {chat_id} "
            }]
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

    send_message(
        chat_id,
        "Receipt received ✅\n"
        "Please wait for admin approval."
    )


def handle_document_receipt(message):
    chat_id = message["chat"]["id"]
    user = message["from"]

    username = user.get("username", "No username")
    name = user.get("first_name", "")
    document = message["document"]

    file_id = document["file_id"]
    file_name = document.get(
        "file_name",
        "receipt.pdf"
    )
    mime_type = document.get(
        "mime_type",
        "unknown"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "Approve ✅",
                    "callback_data": f"approve:{chat_id}"
                },
                {
                    "text": "Reject ❌",
                    "callback_data": f"reject:{chat_id}"
                }
            ],
            [{
                "text": "Message 💬",
                "switch_inline_query_current_chat":
                    f"/msg {chat_id} "
            }]
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

    requests.post(
        f"{BASE_URL}/sendDocument",
        json=data,
        timeout=30
    )

    send_message(
        chat_id,
        "Receipt received ✅\n"
        "Please wait for admin approval."
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
        send_message(
            chat_id,
            "Sorry, this product is currently "
            "out of stock ❌"
        )
        send_message(
            ADMIN_ID,
            "Stock Alert ❌\n\nStock is now 0."
        )
        return

    if stock_count <= LOW_STOCK_LIMIT:
        send_message(
            ADMIN_ID,
            f"Low Stock Warning ⚠️\n\n"
            f"Only {stock_count} item(s) left."
        )

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
        "inline_keyboard": [[
            {
                "text": "Remind 🔔",
                "callback_data": f"remind:{chat_id}"
            },
            {
                "text": "Message 💬",
                "switch_inline_query_current_chat":
                    f"/msg {chat_id} "
            }
        ]]
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

    send_photo_file(
        chat_id,
        "qr.png",
        "Scan QR and complete payment.\n\n"
        "⭐Please don't chat with us at Shopee⭐"
    )


def handle_approve(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(
            callback["from"]["id"],
            "You are not allowed to do this."
        )
        return

    customer_id = int(
        callback["data"].split(":")[1]
    )

    with db() as conn:
        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:
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
                send_message(
                    customer_id,
                    "Payment approved, but stock is empty. "
                    "Please contact admin."
                )
                send_message(
                    ADMIN_ID,
                    "No stock left ❌"
                )
                return

            raw_item = stock_item["raw_item"]
            formatted_item = format_item(raw_item)

            cur.execute("""
                INSERT INTO orders
                (
                    telegram_id,
                    raw_item,
                    formatted_item,
                    delivered_item,
                    status
                )
                VALUES (
                    %s, %s, %s, %s, 'completed'
                );
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
            """, (stock_item["id"],))

            conn.commit()

    remaining = get_stock_count()

    send_message(
        customer_id,
        f"Payment Approved ✅\n\n"
        f"{formatted_item}\n"
        f"You are able to edit and lock your profile\n\n"
        f"Sign in at Netflix apps/Website. "
        f"Only get the code if requested.\n"
        f"https://shorturl.at/BYY3p\n\n"
        f"Get Sign In Code Here (4-digit):\n"
        f"https://mantapnet.onrender.com/sign-in-code-auto\n\n"
        f"Get Verification Code Here (6-digit):\n"
        f"https://mantapnet.onrender.com/verification-code\n\n"
        f"Video to Get Code:\n"
        f"https://youtu.be/S4NgHOICPSc\n\n"
        f"Warranty Period: 28 days\n\n"
        f"If you are unable to sign in, "
        f"please contact customer support.\n\n"
        f"Thank you for your purchase."
    )

    support_keyboard = {
        "inline_keyboard": [[{
            "text": "Contact Customer Service 💬",
            "url": SUPPORT_LINK
        }]]
    }

    send_message(
        customer_id,
        "⭐ Please don't chat with us at Shopee.\n\n"
        "For faster support, please contact "
        "our customer service here:",
        support_keyboard
    )

    admin_keyboard = {
        "inline_keyboard": [[{
            "text": "Message 💬",
            "switch_inline_query_current_chat":
                f"/msg {customer_id} "
        }]]
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
        send_message(
            ADMIN_ID,
            f"Low Stock Warning ⚠️\n\n"
            f"Only {remaining} item(s) left."
        )


def handle_reject(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(
            callback["from"]["id"],
            "You are not allowed to do this."
        )
        return

    customer_id = int(
        callback["data"].split(":")[1]
    )

    send_message(
        customer_id,
        "Payment rejected ❌\n"
        "Please check your receipt and send again."
    )

    send_message(
        ADMIN_ID,
        f"Order rejected ❌\n"
        f"Customer ID: {customer_id}"
    )


def handle_remind(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(
            callback["from"]["id"],
            "You are not allowed to do this."
        )
        return

    customer_id = int(
        callback["data"].split(":")[1]
    )

    send_message(
        customer_id,
        "Payment Reminder 🔔\n\n"
        "Your order is still pending payment.\n"
        "Please complete payment and send "
        "your receipt here."
    )

    send_message(
        ADMIN_ID,
        f"Reminder sent ✅\n\n"
        f"Customer ID: {customer_id}"
    )


def handle_message_button(callback):
    if callback["from"]["id"] != ADMIN_ID:
        send_message(
            callback["from"]["id"],
            "You are not allowed to do this."
        )
        return

    customer_id = callback["data"].split(":")[1]

    send_message(
        ADMIN_ID,
        f"To message this customer, type:\n\n"
        f"/msg {customer_id} your message here"
    )
