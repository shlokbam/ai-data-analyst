# ============================================================
#  app.py  —  The heart of your Flask application
#  Every request your app handles goes through this file.
# ============================================================

# --- IMPORTS ------------------------------------------------
# Think of imports as "loading tools into your toolbox"
# before you start working.

import os
# os = Operating System module (built into Python, no install needed)
# We use it for:
#   - os.path.join()  → safely build file paths across Windows/Linux
#   - os.makedirs()   → create folders if they don't exist
#   - os.getenv()     → read secret values from your .env file

from flask import (
    Flask,            # The main class — creates your web app
    render_template,  # Loads an HTML file from the templates/ folder
    request,          # Represents the incoming HTTP request (files, form data, JSON)
    jsonify,          # Converts a Python dict → JSON response for the browser
    session           # A per-user "notepad" stored in an encrypted cookie
)
# Why import from flask specifically?
# Flask is a package (a folder of Python files). These are individual
# tools inside that package. We only import what we need.

from werkzeug.utils import secure_filename
# werkzeug is installed automatically with Flask (it's Flask's foundation).
# secure_filename() sanitizes uploaded filenames.
# Without it, a malicious user could upload a file named:
#   "../../etc/passwd"  →  which could overwrite system files!
# secure_filename("../../etc/passwd") returns "etc_passwd" — safe.

from dotenv import load_dotenv
# python-dotenv reads your .env file and loads its contents
# into os.environ so os.getenv() can access them.
# This keeps secrets OUT of your code.

# --- LOAD ENVIRONMENT VARIABLES ----------------------------
load_dotenv()
# This must be called BEFORE any os.getenv() calls.
# It reads your .env file line by line:
#   GEMINI_API_KEY=abc123  →  os.environ["GEMINI_API_KEY"] = "abc123"


# --- CREATE THE FLASK APP ----------------------------------
app = Flask(__name__)
# Flask(__name__) creates your application.
# __name__ is a special Python variable that holds the name of
# the current module. When you run app.py directly, __name__ = "__main__".
# Flask uses it to find your templates/ and static/ folders
# (it looks relative to where this file lives).


# --- CONFIGURATION -----------------------------------------
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
# secret_key is used by Flask to SIGN (encrypt) the session cookie.
# If someone tampers with their cookie, Flask detects it and rejects it.
# os.getenv('SECRET_KEY', 'fallback') means:
#   → Try to read SECRET_KEY from .env
#   → If it's not there, use 'dev-secret-key-change-in-production' as fallback
# In production (Render), you MUST set SECRET_KEY as an environment variable.

UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
# Where uploaded files are stored on the server.
# Locally: the uploads/ folder in your project.
# On Render: we'll change this to /tmp/uploads (Phase 6).

ALLOWED_EXTENSIONS = {'csv'}
# A Python set (like a list but no duplicates, faster lookups).
# We only allow .csv files — this is our security gate.

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# app.config is a dictionary Flask uses for settings.
# Setting it here makes it accessible anywhere via:
#   app.config['UPLOAD_FOLDER']  or  current_app.config['UPLOAD_FOLDER']

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
# 5 MB upload limit.
# 1 KB = 1024 bytes, 1 MB = 1024 KB, so 5 MB = 5 × 1024 × 1024 bytes.
# If someone uploads a larger file, Flask automatically returns a 413 error.


# --- HELPER FUNCTION ---------------------------------------
def allowed_file(filename):
    """
    Returns True if the filename ends with an allowed extension.

    How it works:
      "sales_data.csv".rsplit('.', 1)  →  ['sales_data', 'csv']
      rsplit splits from the RIGHT, max 1 split
      [1] gets the second part (the extension)
      .lower() handles "DATA.CSV" → "csv"
      'in ALLOWED_EXTENSIONS' checks if it's in our set {'csv'}
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# The '.' in filename check is important —
# a file named just "csv" (no dot) would crash rsplit without it.


# ============================================================
#  ROUTES
#  A route connects a URL path to a Python function.
#  When Flask receives a request for that URL, it calls the function.
# ============================================================

@app.route('/')
def index():
    """
    Route: GET /
    This runs when someone visits your homepage.

    render_template('index.html') tells Flask:
      → Look inside the templates/ folder
      → Find index.html
      → Read it, fill in any {{ variables }}, return it as HTML

    We haven't built index.html yet (Phase 5), but the route is ready.
    """
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Route: POST /upload
    This runs when the browser submits the file upload form.

    Why methods=['POST']?
    HTTP has several "verbs":
      GET  = "give me a page"  (default when typing a URL)
      POST = "here's data, process it"  (forms, file uploads)
    By specifying ['POST'], visiting /upload in the browser (GET)
    returns a 405 Method Not Allowed — only form submissions work.
    """

    # request.files is a dictionary of uploaded files.
    # The key 'file' must match the name attribute of your HTML <input>.
    # <input type="file" name="file">  ← this 'name' is the key
    if 'file' not in request.files:
        # jsonify() converts the dict to a proper JSON HTTP response.
        # The second argument (400) is the HTTP status code.
        # 400 = "Bad Request" — the client sent something wrong.
        return jsonify({'error': 'No file part in request'}), 400

    file = request.files['file']
    # file is a FileStorage object — it holds the uploaded file data
    # and metadata (filename, content type, etc.)

    if file.filename == '':
        # This happens when the form is submitted with no file selected.
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Only .csv files are allowed'}), 400

    if file:
        # Sanitize the filename to prevent directory traversal attacks
        filename = secure_filename(file.filename)

        # os.path.join() safely combines folder + filename.
        # On Windows: uploads\sales.csv
        # On Linux:   uploads/sales.csv
        # Never use string concatenation for file paths!
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Save the file from memory to disk at filepath
        file.save(filepath)

        # Store the path in the session so the /ask route can find it later.
        # session is like a dictionary, but it's saved in the user's browser
        # as an encrypted cookie. It persists across multiple requests
        # from the same user.
        session['filepath'] = filepath
        session['filename'] = filename

        # Return a success response with basic file info.
        # The frontend JavaScript will receive this JSON and update the UI.
        return jsonify({
            'message': 'File uploaded successfully!',
            'filename': filename
        })


@app.route('/health')
def health():
    """
    Route: GET /health
    A simple health check endpoint.
    Render and other platforms ping this to verify your app is running.
    Returns 200 OK with a simple message.
    """
    return jsonify({'status': 'ok', 'message': 'Server is running'})


# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == '__main__':
    # if __name__ == '__main__' means:
    # "Only run this block if this file is executed directly"
    #   python app.py       → __name__ == '__main__'  → runs
    #   gunicorn app:app    → __name__ == 'app'        → skips
    # This prevents the dev server from starting when Render runs gunicorn.

    # Create the uploads folder if it doesn't exist yet.
    # exist_ok=True means "don't crash if the folder already exists"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Start Flask's built-in development server.
    # debug=True enables:
    #   1. Auto-reload when you save changes (no need to restart)
    #   2. Detailed error pages in the browser
    #   3. The interactive debugger
    # NEVER use debug=True in production — it's a security risk.
    app.run(debug=True, port=5000)