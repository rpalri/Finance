import os

from cs50 import SQL
import pandas as pd
import sqlite3
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
conn = sqlite3.connect("finance.db")


# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    with sqlite3.connect("finance.db") as conn:
        cash = conn.execute("""SELECT cash FROM users WHERE id = '{}'""".format(session["user_id"]))
        cash = float(cash.fetchall()[0][0])
        try:
            buyTotal = conn.execute("""SELECT *, SUM(shares*price) AS total FROM ledger WHERE user = '{}'""".format(session["user_id"]))
            total = float(buyTotal.fetchall()[0][6]) + cash
            purch = conn.execute("""SELECT symbol, name, SUM(shares) AS shares, price, SUM(shares*price) AS total FROM ledger WHERE user = '{}' GROUP BY symbol""".format(session["user_id"]))
            return render_template("index.html", cash=cash, purch=purch, total=total)
        except:
            return render_template("index.html", cash=cash, total=cash)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if not request.form.get("symbol"):
            return render_template("buy.html")

        sym = request.form.get("symbol").upper()
        stock = lookup(sym)

        if not stock:
            return apology("Symbol not found")

        if not request.form.get("shares"):
            return render_template("buy.html")

        shares = int(request.form.get("shares"))

        if shares < 1:
            return apology("Invalid number of shares")

        with sqlite3.connect("finance.db") as conn:
            rows = pd.read_sql_query("SELECT * FROM users WHERE id = '{}'".format(session["user_id"]), conn)

        if (int(stock["price"]) * shares) > int(rows["cash"][0]):
            return apology("You don't have enough cash")

        with sqlite3.connect("finance.db") as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS ledger (user INTEGER NOT NULL, name TEXT, symbol TEXT, shares INT, price FLOAT, transacted TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user) REFERENCES users(id))""");
            conn.execute("INSERT INTO ledger (user, name, symbol, shares, price) VALUES(?, ?, ?, ?, ?)", (int(session["user_id"]), stock["name"], sym.upper(), shares, stock["price"]))
            conn.execute("""UPDATE users SET cash = '{}' WHERE id = '{}'""".format((float(rows["cash"][0]) - (float(stock["price"]) * shares)), session["user_id"]))
            conn.commit()
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    with sqlite3.connect("finance.db") as conn:
        hist = conn.execute("""SELECT symbol, name, shares, price, transacted FROM ledger WHERE user = '{}'""".format(session["user_id"]))

    return render_template("history.html", hist=hist)


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
        username = request.form.get("username")
        with sqlite3.connect("finance.db") as conn:
            rows = pd.read_sql_query("SELECT * FROM users WHERE username = '{}'".format(username), conn)

        # Ensure username exists and password is correct
        if len(rows.index) != 1 or not check_password_hash(rows["hash"][0], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows["id"][0]

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

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == 'GET':
        return render_template("quote.html")
    else:
        if not request.form.get("symbol"):
            return render_template("quote.html")

        sym = request.form.get("symbol")
        stock = lookup(sym)
        if not stock:
            return apology("Symbol not found")

        return render_template("quoted.html", name=stock["name"], symbol=stock["symbol"], price=stock["price"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        username = request.form.get("username")
        with sqlite3.connect("finance.db") as conn:
            usernames = set(pd.read_sql_query("SELECT username FROM users", conn)["username"])
            if not request.form.get("username"):
                return apology("must provide a username", 403)
            if request.form.get("username") in usernames:
                return apology("username already exists. pick another one", 403)
            if not request.form.get("password"):
                return apology("must provide a password", 403)
            if password != confirmation:
                return apology("passwords don't match, try again", 403)
            pass_hash = generate_password_hash(request.form.get("password"))

            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER NOT NULL, name TEXT, password char(40), cash NUMBER DEFAULT 10000, PRIMARY KEY (id))""");
            conn.execute("INSERT INTO users (username, hash) VALUES(?, ?)", (username, pass_hash))
            return redirect("/")
    if request.method == "GET":
        return render_template("/register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    with sqlite3.connect("finance.db") as conn:
        wallet = pd.read_sql_query("SELECT symbol, SUM(shares) AS shares FROM ledger WHERE user = '{}' AND name != 'ADDED-CASH' GROUP BY symbol".format(session["user_id"]), conn)
        a = (wallet != 0).all(axis=1)
        symbols = wallet["symbol"].loc[a]
        user = pd.read_sql_query("SELECT * FROM users WHERE id = '{}'".format(session["user_id"]), conn)

    if request.method == "GET":
        return render_template("sell.html", symbols=symbols)
    else:

        if not request.form.get("symbol"):
            return render_template("sell.html")

        sym = request.form.get("symbol")
        stock = lookup(sym)

        if not request.form.get("shares"):
            return render_template("sell.html")


        shares = int(request.form.get("shares"))
        shares = -shares

        with sqlite3.connect("finance.db") as conn:
            portfolio = pd.read_sql_query("SELECT SUM(shares) AS shares FROM ledger WHERE user = '{one}' AND symbol = '{two}' GROUP BY symbol".format(one=session["user_id"], two=sym), conn)


        if shares > 1:
            return apology("Invalid number of shares")

        if int(shares) > int(portfolio["shares"][0]):
            return apology("You don't have enough shares")

        with sqlite3.connect("finance.db") as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS ledger (user INTEGER NOT NULL, name TEXT, symbol TEXT, shares INT, price FLOAT, transacted TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user) REFERENCES users(id))""");
            conn.execute("INSERT INTO ledger (user, name, symbol, shares, price) VALUES(?, ?, ?, ?, ?)", (int(session["user_id"]), stock["name"], sym.upper(), shares, stock["price"]))
            conn.execute("""UPDATE users SET cash = '{}' WHERE id = '{}'""".format((float(user["cash"][0]) - (float(stock["price"]) * shares)), session["user_id"]))
            conn.commit()
    return redirect("/")

@app.route("/cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """ Add cash to your wallet """
    if request.method == "GET":
        return render_template("cash.html")

    amount = request.form.get("amount")

    with sqlite3.connect("finance.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS ledger (user INTEGER NOT NULL, name TEXT, symbol TEXT, shares INT, price FLOAT, transacted TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user) REFERENCES users(id))""");
        conn.execute("""UPDATE users SET cash = cash + '{}' WHERE id = '{}'""".format(amount, session["user_id"]))
        conn.execute("INSERT INTO ledger (user, name, price) VALUES(?, ?, ?)", (int(session["user_id"]), "ADDED-CASH", amount))

    return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
