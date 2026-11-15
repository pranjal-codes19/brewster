
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
from decimal import Decimal

app = Flask(__name__)
app.secret_key = "brewster_cafe_secret_key_change_this"


def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Brewster@12345",
        database="brewster"
    )


MENU_PRICES = {
    "Cappuccino": Decimal("120"),
    "Latte": Decimal("130"),
    "Americano": Decimal("230"),
    "Macchiato": Decimal("250"),
    "Flat White": Decimal("300"),
    "Cheese Burger": Decimal("180"),
    "Bacon Cheeseburger": Decimal("280"),
    "BBQ Burger": Decimal("430"),
    "Spicy Jalapeno": Decimal("510"),
    "Spicy Hawaiian": Decimal("310"),
    "Margherita Pizza": Decimal("220"),
    "Super Veg Delight Pizza": Decimal("277"),
    "Paneer Makhani Pizza": Decimal("320"),
    "Herb Chicken Pizza": Decimal("420"),
    "Cheese Corn Pizza": Decimal("350"),
    "French Fries": Decimal("90"),
    "Waffle Fries": Decimal("190"),
    "Tater Tots": Decimal("230"),
    "Garlic Fries": Decimal("250"),
    "Cheese Balls": Decimal("180"),
    "Chocolate Cake": Decimal("350"),
    "Rosewater Cake": Decimal("200"),
    "Black Forest Cake": Decimal("250"),
    "Butterscotch Cake": Decimal("300"),
    "Red Velvet Cake": Decimal("320")
}


@app.route("/")
def home():
    return render_template("signup.html")


@app.route("/home")
def home_page():
    return render_template("home.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/signup", methods=["POST"])
def signup():
    name = request.form["name"].strip()
    email = request.form["email"].strip()
    password = request.form["password"]
    confirm_password = request.form["confirm_password"]

    if password != confirm_password:
        return "Passwords do not match!"

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )

        db.commit()

        session.clear()
        session["user_email"] = email
        session["clear_cart"] = True

        return redirect(url_for("home_page"))

    except mysql.connector.Error:
        db.rollback()
        return "Signup failed. This email may already be registered."

    finally:
        cursor.close()
        db.close()


@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].strip()
    password = request.form["password"]

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute(
            "SELECT id, email FROM users WHERE email = %s AND password = %s",
            (email, password)
        )

        user = cursor.fetchone()

        if user:
            session.clear()
            session["user_email"] = user[1]
            session["clear_cart"] = True

            return redirect(url_for("home_page"))

        return "Invalid email or password!"

    finally:
        cursor.close()
        db.close()


@app.route("/cart-status")
def cart_status():
    clear_cart = session.pop("clear_cart", False)
    return jsonify({"clear_cart": clear_cart})


@app.route("/menu")
def menu():
    return render_template("menu.html")


@app.route("/bill")
def bill():
    return render_template("bill.html")


@app.route("/gallery")
def gallery():
    return render_template("gallery.html")


@app.route("/cart")
def cart():
    return render_template("cart.html")


@app.route("/payment", methods=["GET", "POST"])
def payment():
    if "user_email" not in session:
        return redirect(url_for("login_page"))

    return render_template("payment.html")


@app.route("/place-order", methods=["POST"])
def place_order():
    if "user_email" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in before placing an order."
        }), 401

    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    payment_method = str(data.get("payment_method", "")).strip()

    if not isinstance(items, list) or not items:
        return jsonify({
            "success": False,
            "message": "Your cart is empty. Please add items first."
        }), 400

    if payment_method not in ("UPI", "Cash"):
        return jsonify({
            "success": False,
            "message": "Invalid payment method."
        }), 400

    prepared_items = []
    total = Decimal("0.00")

    for item in items:
        if not isinstance(item, dict):
            return jsonify({
                "success": False,
                "message": "Invalid cart item. Please return to your cart."
            }), 400

        name = str(item.get("name", "")).strip()

        if name not in MENU_PRICES:
            app.logger.warning("Invalid menu item received: %r", name)

            return jsonify({
                "success": False,
                "message": f"Invalid menu item: {name or 'unknown'}. Please check menu.html."
            }), 400

        raw_quantity = item.get("quantity", 1)

        try:
            if raw_quantity is None or str(raw_quantity).strip() == "":
                raw_quantity = 1

            if isinstance(raw_quantity, bool):
                raise ValueError

            quantity_number = Decimal(str(raw_quantity))

            if not quantity_number.is_finite():
                raise ValueError

            if quantity_number != quantity_number.to_integral_value():
                raise ValueError

            quantity = int(quantity_number)

            if quantity < 1 or quantity > 100:
                raise ValueError

        except (ValueError, TypeError, ArithmeticError):
            return jsonify({
                "success": False,
                "message": f"Invalid quantity for {name}. Please return to your cart."
            }), 400

        price = MENU_PRICES[name]
        subtotal = price * quantity
        total += subtotal

        prepared_items.append(
            (name, price, quantity, subtotal)
        )

    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email = %s",
            (session["user_email"],)
        )

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "success": False,
                "message": "Customer account not found. Please log in again."
            }), 401

        cursor.execute(
            """
            INSERT INTO orders (user_id, total_amount)
            VALUES (%s, %s)
            """,
            (user[0], total)
        )

        order_id = cursor.lastrowid

        for name, price, quantity, subtotal in prepared_items:
            cursor.execute(
                """
                INSERT INTO order_items
                (order_id, item_name, price, quantity, subtotal)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order_id, name, price, quantity, subtotal)
            )

        cursor.execute(
            """
            INSERT INTO payments
            (order_id, amount, payment_method, payment_status)
            VALUES (%s, %s, %s, %s)
            """,
            (order_id, total, payment_method, "Pending")
        )

        db.commit()

        return jsonify({
            "success": True,
            "message": "Your order has been saved successfully!",
            "order_id": order_id,
            "total": str(total),
            "redirect": url_for("thankyou")
        })

    except mysql.connector.Error:
        if db and db.is_connected():
            db.rollback()

        app.logger.exception("Could not save Brewster order")

        return jsonify({
            "success": False,
            "message": "Could not save your order. Check the Flask terminal for the database error."
        }), 500

    finally:
        if cursor:
            cursor.close()

        if db and db.is_connected():
            db.close()


@app.route("/thankyou")
def thankyou():
    if "user_email" not in session:
        return redirect(url_for("login_page"))

    return render_template("thankyou.html")


if __name__ == "__main__":
    app.run(debug=True)
