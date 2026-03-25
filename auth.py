# ============================================================
#  auth.py  —  Authentication Blueprint (Phase B)
#
#  A Blueprint is Flask's way of splitting a large app into
#  smaller, reusable components.
#
#  This Blueprint handles:
#    GET  /auth/login   — show the login form
#    POST /auth/login   — validate credentials, log in
#    GET  /auth/signup  — show the signup form
#    POST /auth/signup  — create account, log in
#    GET  /auth/logout  — log out and redirect
#
#  It is registered in app.py with:
#    app.register_blueprint(auth_bp)
# ============================================================

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)
# Blueprint  — creates a mini-app that gets merged into the main app
# render_template — renders Jinja2 HTML templates
# request    — access form data (request.form['email'])
# redirect   — send the browser to a different URL
# url_for    — generate a URL from a function name (avoids hardcoding)
# flash      — send a one-time message to the next page
#              (stores in session, displayed once, then gone)

from flask_login import login_user, logout_user, login_required, current_user
# login_user(user)    — tells Flask-Login to start a session for this user
# logout_user()       — clears the session
# login_required      — decorator: redirect to login page if not authenticated
# current_user        — the logged-in User object (or AnonymousUser)

from models import db, User
# db   — we need it to add and commit the new User to the database
# User — the model we're creating and querying

# ============================================================
#  Create the Blueprint
# ============================================================

auth_bp = Blueprint(
    'auth',         # Blueprint name — used in url_for('auth.login')
    __name__,       # tells Flask where this Blueprint lives
    # No url_prefix set here — we'll set it in app.py
)
# Blueprint('auth', __name__) registers 'auth' as the namespace.
# All routes defined below become 'auth.login', 'auth.signup', etc.
# This lets multiple Blueprints have routes with the same name
# without clashing — e.g. 'auth.index' vs 'main.index'.


# ============================================================
#  LOGIN
# ============================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET  /login  — show the login form
    POST /login  — validate and log in

    Flow:
      1. If already logged in → redirect to main app
      2. GET request → just show the form
      3. POST request → look up user by email
         - Not found OR wrong password → flash error, re-show form
         - Correct → login_user(), redirect to main app
    """
    # If already logged in, skip the login page entirely
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        # url_for('index') → '/'
        # We don't use redirect('/') because url_for() handles
        # app prefixes and Blueprint namespacing automatically.

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        # .get() with default '' prevents KeyError if field is missing.
        # .lower() normalises email case — "Alice@example.com" == "alice@example.com"
        # .strip() removes accidental spaces the user might type.

        # Validate: both fields must have content
        if not email or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html')

        # Look up the user by email
        user = User.query.filter_by(email=email).first()
        # filter_by(email=email) → WHERE email = ?
        # .first() → one row or None

        if not user or not user.check_password(password):
            # We give the SAME error for "user not found" and "wrong password".
            # Giving different errors would tell attackers which emails exist.
            flash('Invalid email or password.', 'error')
            return render_template('login.html')

        # ---- Success ----
        login_user(user, remember=True)
        # remember=True → sets a long-lived cookie (30 days by default)
        # so the user stays logged in after closing the browser.
        # Without this, the session expires when the browser closes.

        # Redirect to the page the user originally tried to visit
        # (Flask-Login saves it in 'next' query param automatically)
        next_page = request.args.get('next')
        return redirect(next_page or url_for('index'))

    # GET request — just show the form
    return render_template('login.html')


# ============================================================
#  SIGNUP
# ============================================================

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """
    GET  /signup  — show the registration form
    POST /signup  — create account and log in

    Flow:
      1. If already logged in → redirect to main app
      2. GET → show the form
      3. POST → validate inputs → check if email taken →
         create User → login_user() → redirect to main app
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        # ---- Validation ----
        if not email or not password or not confirm:
            flash('Please fill in all fields.', 'error')
            return render_template('signup.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('signup.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('signup.html')

        # ---- Check if email is already registered ----
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('An account with that email already exists.', 'error')
            return render_template('signup.html')

        # ---- Create the account ----
        user = User(email=email)
        user.set_password(password)
        # set_password() hashes the password — never stored in plain text.

        db.session.add(user)
        # Stages the new User for INSERT — not committed yet.

        db.session.commit()
        # Executes: INSERT INTO users (email, password_hash) VALUES (...)
        # After this, user.id is populated by the database.

        # Log in immediately — no need to make them log in separately
        login_user(user, remember=True)

        flash('Account created! Welcome to DataLens.', 'success')
        return redirect(url_for('index'))

    return render_template('signup.html')


# ============================================================
#  LOGOUT
# ============================================================

@auth_bp.route('/logout')
@login_required
# @login_required means: if not logged in, redirect to login page.
# Logically, you can only log OUT if you are logged IN.
def logout():
    logout_user()
    # Clears the user's session cookie.
    # After this, current_user becomes AnonymousUser.

    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
    # 'auth.login' = Blueprint 'auth', function 'login'
    # This generates the URL /login
