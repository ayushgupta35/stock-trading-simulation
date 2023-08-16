import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT * FROM buy WHERE user_id = :user_id ORDER BY symbol ASC", user_id=session["user_id"])
    user = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])
    rows = db.execute("SELECT pps FROM buy WHERE user_id= :user_id", user_id=session["user_id"])
    grand_total = 0.0
    total_current_total = 0.0
    quantity = 0
    initial_total = 0.0
    current_total = 0.0
    total_initial_total = 0.0
    total_profit = 0.0

    for i in range(len(stocks)):
        stock = lookup(stocks[i]["symbol"])
        stocks[i]["company"] = stock["name"]
        stocks[i]["cur_price"] = "%.2f" % (stock["price"])
        stocks[i]["cur_total"] = "%.2f" % (float(stock["price"]) * float(stocks[i]["quantity"]))
        stocks[i]["profit"] = "%.2f" % (float(stocks[i]["cur_total"]) - float(stocks[i]["total"]))
        grand_total = grand_total + stocks[i]["total"]
        stocks[i]["total"] = "%.2f" % (stocks[i]["total"])
        total_current_total = float(stocks[i]["cur_total"]) + float(total_current_total)
        quantity = int(stocks[i]["quantity"]) + quantity
        initial_total = initial_total + float(rows[i]["pps"])
        current_total = current_total + float(stocks[i]["cur_price"])
        total_initial_total = total_initial_total + float(stocks[i]["total"])
        total_profit = total_profit + float(stocks[i]["profit"])

    grand_total = total_current_total + float(user[0]["cash"])

    return render_template("index.html", stocks=stocks, cash=usd(user[0]["cash"]), grand_total=usd(grand_total), total_current_total=usd(total_current_total),
                    quantity=quantity, initial_total=usd(initial_total), current_total=usd(current_total), total_initial_total=usd(total_initial_total), total_profit=usd(total_profit))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        if not request.form.get("shares"):
            return apology("No number of shares provided", 403)

        if int(request.form.get("shares")) < 1:
            return apology("Invalid number of shares", 403)

        if not request.form.get("symbol"):
            return apology("no symbol provided", 403)

        symbol = request.form.get("symbol")
        quote = lookup(symbol.upper())

        if quote == None:
            return apology("no stock with that symbol", 403)

        quantity = request.form.get("shares")
        user_id = session["user_id"]

        stock = lookup(symbol)

        if not stock:
            return apology("symbol not found")

        total_price = float(stock["price"]) * float(quantity)

        user = db.execute("SELECT * FROM users WHERE id = :id", id=user_id)
        funds = float(user[0]["cash"])

        if funds < total_price:
            return apology("not enough money available")

        funds_left = funds - total_price

        rows = db.execute("SELECT * FROM buy WHERE user_id = :user_id AND symbol = :symbol",
                        user_id=user_id, symbol=symbol)

        if len(rows) == 1:

            new_quantity = int(rows[0]["quantity"]) + int(quantity)
            new_total = float(rows[0]["total"]) + total_price
            new_pps = "%.2f" % (new_total / float(new_quantity))

            db.execute("UPDATE buy SET quantity = :quantity, total = :total, pps = :pps WHERE user_id = :user_id AND symbol = :symbol",
                    quantity=new_quantity, total=new_total, pps=new_pps, user_id=user_id, symbol=symbol)

        else:

            db.execute("INSERT INTO buy (user_id, symbol, quantity, total, pps) VALUES (:user_id, :symbol, :quantity, :total, :pps)",
                    user_id=user_id, symbol=symbol, quantity=quantity, total=total_price, pps=stock["price"])

        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=funds_left, id=user_id)

        db.execute("INSERT INTO history (user_id, action, symbol, quantity, pps) VALUES (:user_id, :action, :symbol, :quantity, :pps)",
                user_id=user_id, action=1, symbol=symbol, quantity=quantity, pps=stock["price"])

        flash("Bought!")

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    stocks = db.execute("SELECT * FROM history WHERE user_id = :user_id ORDER BY date DESC", user_id=session["user_id"])

    for i in range(len(stocks)):
        stocks[i]["total"] = "%.2f" % (float(stocks[i]["quantity"]) * float(stocks[i]["pps"]))

    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        flash("Logged In!")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    flash("Logged Out!")

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("no symbol provided", 403)
        symbol = request.form.get("symbol")
        quote = lookup(symbol.upper())
        if quote == None:
            return apology("no stock with that symbol", 403)

        flash("Quoted!")

        return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/change", methods=["GET", "POST"])
def change():
    """Allow user to change password"""

    if request.method == "POST":

        if not request.form.get("oldpassword"):
            return apology("must provide current password", 403)

        rows = db.execute("SELECT hash FROM users WHERE id = :user_id", user_id=session["user_id"])

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("oldpassword")):
            return apology("invalid password", 403)

        if not request.form.get("newpassword"):
            return apology("must provide new password", 403)

        elif not request.form.get("newpasswordconfirmation"):
            return apology("must provide new password confirmation", 403)

        elif request.form.get("newpassword") != request.form.get("newpasswordconfirmation"):
            return apology("new password and confirmation do not match", 403)

        hash = generate_password_hash(request.form.get("newpassword"))
        rows = db.execute("UPDATE users SET hash = :hash WHERE id = :user_id", user_id=session["user_id"], hash=hash)

        flash("Changed!")

        return redirect("/")

    else:
        return render_template("change.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 403)

        elif not request.form.get("password"):
            return apology("must provide password", 403)

        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 403)

        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if password == confirmation:
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        else:
            return apology("passwords do not match", 403)

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        session["user_id"] = rows[0]["id"]

        flash("Registered!")

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    stocks = db.execute("SELECT * FROM buy WHERE user_id = :user_id", user_id=session["user_id"])

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure quantity was submited
        if not request.form.get("shares") or int(request.form.get("shares")) < 1:
            return apology("Invalid number of shares")

        user_id = session["user_id"]
        symbol = request.form.get("symbol").upper()
        quantity = request.form.get("shares")

        # retrieve stock from db
        rows = db.execute("SELECT quantity, pps FROM buy WHERE user_id = :user_id AND symbol = :symbol",
                        user_id=user_id, symbol=symbol)

        # retrieve user data from db
        user = db.execute("SELECT * FROM users WHERE id = :id", id=user_id)

        # ensure quantity to be sold is available
        if int(quantity) > rows[0]["quantity"]:
            return apology("You don't own enough shares")

        # lookup the stock to get current price
        stock = lookup(symbol)

        # calculate total price
        total_price = float(stock["price"]) * float(quantity)

        # modify number of shares owned or delete if < 1
        if int(quantity) == rows[0]["quantity"]:
            db.execute("DELETE FROM buy WHERE user_id = :user_id AND symbol = :symbol", user_id=user_id, symbol=symbol)
        else:
            new_quantity = int(rows[0]["quantity"]) - int(quantity)
            new_total = float(new_quantity) * float(rows[0]["pps"])
            db.execute("UPDATE buy SET quantity = :quantity, total = :total WHERE user_id = :user_id AND symbol = :symbol",
                    quantity=new_quantity, total=new_total, user_id=user_id, symbol=symbol)

        # modify available funds
        funds_available = float(user[0]["cash"]) + total_price
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=funds_available, id=user_id)

        # commit to history
        db.execute("INSERT INTO history (user_id, action, symbol, quantity, pps) VALUES (:user_id, :action, :symbol, :quantity, :pps)",
                user_id=user_id, action=0, symbol=symbol, quantity=quantity, pps=stock["price"])

        # send a success message
        flash("Sold!")

        return redirect("/")

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
