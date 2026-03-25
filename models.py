# ============================================================
#  models.py  —  Database models (Phase A)
#
#  This file defines WHAT your database looks like.
#  Three tables: User, Chat, Message.
#
#  Key concept — SQLAlchemy ORM:
#  Instead of writing raw SQL like:
#    "INSERT INTO users (email, password_hash) VALUES (?, ?)"
#  You write Python:
#    user = User(email="a@b.com", password_hash="xyz")
#    db.session.add(user)
#    db.session.commit()
#
#  SQLAlchemy translates your Python objects into SQL automatically.
#  This is called an ORM — Object Relational Mapper.
#  Your Python class IS the table. Each instance IS a row.
# ============================================================

from flask_sqlalchemy import SQLAlchemy
# SQLAlchemy is the most popular Python ORM.
# Flask-SQLAlchemy is a thin wrapper that makes it work
# smoothly with Flask's app context.

from flask_login import UserMixin
# UserMixin is a helper class from Flask-Login.
# It gives your User model four properties/methods that
# Flask-Login requires automatically, so you don't have to
# write them yourself:
#   is_authenticated → True if the user is logged in
#   is_active        → True if the account is active
#   is_anonymous     → False for real users
#   get_id()         → returns str(self.id)

from datetime import datetime, timezone
# datetime.now(timezone.utc) gives the current UTC time.
# We store UTC in the database and convert to local time
# in the frontend if needed. Always store UTC — never local time.

from werkzeug.security import generate_password_hash, check_password_hash
# werkzeug is installed with Flask — no extra install needed.
# generate_password_hash("mypassword")
#   → "pbkdf2:sha256:600000$salt$hash..."
#   This is a one-way hash. You can NEVER reverse it to get
#   the original password — that's the whole point.
#   Even if someone steals your database, they can't log in.
#
# check_password_hash(stored_hash, "mypassword")
#   → True if the password matches, False otherwise.
#   It re-hashes the input and compares — never decrypts.


# ============================================================
#  db — the SQLAlchemy instance
#
#  We create it here (not in app.py) to avoid circular imports.
#  A circular import happens when:
#    app.py imports from models.py
#    models.py imports from app.py
#  → Python gets stuck in a loop and crashes.
#
#  Solution: create db here, import db into app.py,
#  then call db.init_app(app) to connect them.
#  This is called the "Application Factory pattern".
# ============================================================
db = SQLAlchemy()


# ============================================================
#  TABLE 1: User
#  One row per registered account.
# ============================================================

class User(UserMixin, db.Model):
    """
    Represents one registered user.

    UserMixin  → gives Flask-Login the 4 methods it needs
    db.Model   → tells SQLAlchemy "this class is a database table"

    The class name 'User' → table name 'user' (lowercase, auto)
    """

    # __tablename__ overrides the auto-generated name.
    # Without it: SQLAlchemy would use 'user' (singular).
    # 'users' (plural) is the conventional table naming style.
    __tablename__ = 'users'

    # ---- COLUMNS ------------------------------------------------
    # Each class attribute = one column in the table.

    id = db.Column(
        db.Integer,
        primary_key=True
        # primary_key=True means:
        #   1. This column uniquely identifies each row
        #   2. SQLite auto-increments it: first user → id=1, second → id=2
        #   3. No two users can have the same id
    )

    email = db.Column(
        db.String(150),
        # String(150) = VARCHAR(150) in SQL — text up to 150 chars.
        # Most email addresses are under 100 chars; 150 is safe.
        unique=True,
        # unique=True → database-level constraint.
        # If you try to INSERT a duplicate email, the DB refuses it.
        # This is stronger than just checking in Python first.
        nullable=False
        # nullable=False → this column MUST have a value.
        # Trying to save a User without an email raises an error.
    )

    password_hash = db.Column(
        db.String(256),
        nullable=False
        # We never store the actual password — only the hash.
        # pbkdf2:sha256 hashes are ~100 chars; 256 gives headroom.
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
        # default= sets the value automatically when a new row is created.
        # We use a lambda (anonymous function) so it's called at INSERT time,
        # not at import time. Without lambda, every user would get the same
        # timestamp — the time the module was first loaded.
    )

    # ---- RELATIONSHIP -------------------------------------------
    # This tells SQLAlchemy that one User has MANY Chats.
    # It's not a column — it's a Python-level link.
    # You can now write: user.chats  →  list of Chat objects
    chats = db.relationship(
        'Chat',
        # 'Chat' (string) instead of Chat (class) avoids needing
        # Chat to be defined before User in this file.
        backref='owner',
        # backref='owner' creates the REVERSE link automatically.
        # You can now also write: chat.owner → the User object
        lazy=True,
        # lazy=True means: don't load chats from the DB until
        # you actually access user.chats. Saves unnecessary queries.
        cascade='all, delete-orphan'
        # cascade='all, delete-orphan' means:
        # If a User is deleted, ALL their chats are deleted too.
        # Without this, deleting a user would leave orphaned chats.
    )

    # ---- METHODS ------------------------------------------------

    def set_password(self, password):
        """
        Hashes the password and stores it.
        Call this instead of setting password_hash directly.

        We explicitly use 'pbkdf2:sha256' for Python 3.9 compatibility:
        werkzeug 2.x defaults to 'scrypt', which requires Python 3.9+
        to have OpenSSL compiled with scrypt support. pbkdf2:sha256
        is always available and is cryptographically strong.
        """
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        # pbkdf2:sha256 is NIST-approved, used by many production apps.
        # Format: "pbkdf2:sha256:600000$<salt>$<hash>"
        # The salt is random — same password → different hash each time.
        # You can NEVER reverse this to get the original password.

    def check_password(self, password):
        """
        Returns True if the given password matches the stored hash.
        Used during login to verify credentials.

        Usage:
            if user.check_password(form_password):
                login_user(user)
        """
        return check_password_hash(self.password_hash, password)
        # check_password_hash() extracts the salt from the stored hash,
        # re-hashes the input password with that same salt,
        # and compares the two hashes.

    def __repr__(self):
        """
        __repr__ controls what Python shows when you print() a User object.
        Without it: <User object at 0x7f...> — not helpful.
        With it:    <User alice@example.com>  — immediately useful.
        """
        return f'<User {self.email}>'


# ============================================================
#  TABLE 2: Chat
#  One row per "conversation session".
#  A user can have many chats. Each chat has one CSV file.
#  Think of it like ChatGPT's sidebar — each item is a Chat.
# ============================================================

class Chat(db.Model):
    __tablename__ = 'chats'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(200),
        nullable=False,
        default='New chat'
        # The default name before the user renames it.
        # We'll auto-update this to the CSV filename on upload.
    )

    csv_path = db.Column(
        db.String(500),
        nullable=True
        # nullable=True → a chat can exist before a CSV is uploaded.
        # The user creates the chat first, then uploads the file.
        # String(500) because file paths can be long.
    )

    csv_filename = db.Column(
        db.String(200),
        nullable=True
        # Original filename for display (e.g. "sales_data.csv")
        # csv_path is the server path; csv_filename is what the UI shows.
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    # Foreign key: links this chat to its owner (a User).
    # 'users.id' = table_name.column_name in SQL syntax.
    # This creates a column 'user_id' in the chats table.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False
        # Every chat MUST belong to a user.
        # ForeignKey enforces this at the database level —
        # you can't insert a chat with a user_id that doesn't exist.
    )

    # Relationship: one Chat has MANY Messages
    messages = db.relationship(
        'Message',
        backref='chat',
        # chat.messages → list of Message objects
        # message.chat  → the Chat object (from backref)
        lazy=True,
        cascade='all, delete-orphan',
        order_by='Message.created_at'
        # order_by ensures messages always come back in time order
        # (oldest first) without needing to sort in Python.
    )

    def __repr__(self):
        return f'<Chat {self.id}: {self.name}>'


# ============================================================
#  TABLE 3: Message
#  One row per Q&A exchange inside a chat.
#  Stores the question, the AI answer, and chart metadata
#  so we can regenerate the PDF without re-calling the AI.
# ============================================================

class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)

    # The question the user typed
    question = db.Column(
        db.Text,
        nullable=False
        # db.Text = unlimited length string (TEXT in SQL).
        # We use Text for questions/answers because they can be long.
        # String(n) has a max; Text does not.
    )

    # The AI's full answer text
    answer = db.Column(
        db.Text,
        nullable=False
    )

    # Chart metadata — stored so PDF export can regenerate the chart
    # without making another API call to Groq.
    chart_type = db.Column(
        db.String(20),
        nullable=True
        # 'bar', 'line', 'scatter', 'histogram', 'pie', or 'none'
        # nullable=True because some answers have no chart.
    )

    chart_x_col = db.Column(
        db.String(200),
        nullable=True
        # Column name for the X axis (e.g. 'Region')
    )

    chart_y_col = db.Column(
        db.String(200),
        nullable=True
        # Column name for the Y axis (e.g. 'Sales')
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    # Foreign key: links this message to its chat
    chat_id = db.Column(
        db.Integer,
        db.ForeignKey('chats.id'),
        nullable=False
    )

    def __repr__(self):
        return f'<Message {self.id}: {self.question[:40]}>'


# ============================================================
#  HELPER FUNCTION — called once on app startup
# ============================================================

def init_db(app):
    """
    Connects SQLAlchemy to the Flask app and creates
    all tables if they don't exist yet.

    Call this in app.py after creating the Flask app:
        from models import db, init_db
        init_db(app)

    What db.create_all() does:
      - Reads all classes that inherit from db.Model
      - For each class, generates a CREATE TABLE SQL statement
      - Executes it ONLY IF the table doesn't already exist
      - Safe to call every time the app starts — no data loss
    """
    db.init_app(app)
    # db.init_app(app) tells SQLAlchemy which Flask app to use.
    # Separating this from db = SQLAlchemy() (at the top)
    # is what prevents the circular import problem.

    with app.app_context():
        # app.app_context() pushes Flask's "application context".
        # SQLAlchemy needs this to know which database to connect to.
        # Without it: "RuntimeError: No application found."
        # Think of it as: telling SQLAlchemy "work within THIS app".
        db.create_all()
        # Executes SQL like:
        #   CREATE TABLE IF NOT EXISTS users (
        #       id INTEGER PRIMARY KEY AUTOINCREMENT,
        #       email VARCHAR(150) UNIQUE NOT NULL,
        #       password_hash VARCHAR(256) NOT NULL,
        #       created_at DATETIME
        #   );
        # Same for chats and messages tables.
