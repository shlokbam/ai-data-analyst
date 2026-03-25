# ============================================================
#  app.py  —  The heart of your Flask application
#  Updated in Phase 3: /ask route wired to Gemini AI
# ============================================================

import os
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import pandas as pd
from analysis import analyze_csv, get_chart_columns
from gemini_helper import get_ai_insight, suggest_chart_type, suggest_chart_columns
from flask import send_file
# send_file() streams a file-like object (our BytesIO buffer) as an
# HTTP response with the correct Content-Type header.
# Without it, Flask has no built-in way to serve raw binary data.

from chart import generate_chart
# Our Phase 4 module — all Matplotlib drawing logic lives here.
# generate_chart(df, chart_type, x_col, y_col) → BytesIO PNG buffer

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

UPLOAD_FOLDER      = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---- Route 1 -----------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


# ---- Route 2 -----------------------------------------------
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only .csv files are allowed'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    session['filepath'] = filepath
    session['filename'] = filename
    session.pop('history', None)  # clear old conversation on new upload

    try:
        df = pd.read_csv(filepath)
    except:
        df = pd.read_csv(filepath, encoding='latin1')
    rows, cols = df.shape
    columns_info = [{'name': col, 'type': str(df[col].dtype)} for col in df.columns]

    return jsonify({'message': 'File uploaded successfully!',
                    'filename': filename, 'rows': rows,
                    'cols': cols, 'columns': columns_info})


# ---- Route 3 -----------------------------------------------
@app.route('/preview', methods=['GET'])
def preview():
    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No file uploaded yet.'}), 400
    try:
        df = pd.read_csv(filepath)
    except:
        df = pd.read_csv(filepath, encoding='latin1')
    df = df.where(pd.notnull(df), None)
    data = df.head(10).to_dict(orient='records')
    return jsonify({'columns': list(df.columns), 'rows': data, 'total_rows': len(df)})


# ---- Route 4 -----------------------------------------------
@app.route('/summary', methods=['GET'])
def summary():
    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No file uploaded yet.'}), 400
    full_summary, df = analyze_csv(filepath)
    return jsonify({'summary': full_summary, 'chart_columns': get_chart_columns(df)})


# ---- Route 5  NEW IN PHASE 3 --------------------------------
@app.route('/ask', methods=['POST'])
def ask():
    """
    POST /ask — the main route of the whole app.

    Flow:
      1.  Read + validate the question from the request body
      2.  Get the CSV filepath from session
      3.  Generate Pandas summary  (analyze_csv)
      4.  Get AI insight text      (get_ai_insight)
      5.  Get chart type           (suggest_chart_type)
      6.  Get chart columns        (suggest_chart_columns)
      7.  Save to conversation history
      8.  Return all results as JSON
    """

    # Step 1 — parse and validate the incoming JSON body
    body = request.get_json()
    # The frontend sends:
    #   fetch('/ask', {
    #     method: 'POST',
    #     headers: { 'Content-Type': 'application/json' },
    #     body: JSON.stringify({ question: "..." })
    #   })
    # request.get_json() parses that body string into a Python dict.
    # Returns None if the body is empty or Content-Type is wrong.

    if not body:
        return jsonify({'error': 'Request body is empty or not JSON.'}), 400

    user_question = body.get('question', '').strip()
    # .get() with a default '' prevents KeyError if 'question' is missing.
    # .strip() removes accidental leading/trailing whitespace.

    if not user_question:
        return jsonify({'error': 'Please enter a question.'}), 400

    if len(user_question) > 500:
        return jsonify({'error': 'Question too long (max 500 characters).'}), 400

    # Step 2 — get the CSV filepath the upload route saved in the session
    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No CSV uploaded yet. Please upload a file first.'}), 400

    if not os.path.exists(filepath):
        # File may have been deleted (e.g. server restarted).
        session.pop('filepath', None)  # remove stale session data
        return jsonify({'error': 'Uploaded file not found. Please re-upload.'}), 400

    # Step 3 — generate the full Pandas data summary
    full_summary, df = analyze_csv(filepath)
    # full_summary = multi-section text Gemini will read as context
    # df           = raw DataFrame for chart column lookup

    chart_cols = get_chart_columns(df)
    # {'numeric': ['Sales', 'Units'], 'text': ['Region', 'Month'], 'all': [...]}

    # Step 4 — load conversation history for follow-up support
    history = session.get('history', [])
    # If this is the first question, history is an empty list [].
    # Gemini uses history to understand references like "the region
    # you just mentioned" or "what about the other column?".

    # Step 5 — call Gemini for the text insight
    insight = get_ai_insight(full_summary, user_question, history)
    # Network call to Google's API → typically 1-3 seconds.
    # Returns a string: Gemini's full answer to the question.

    # Step 6 — call Gemini for chart type
    chart_type = suggest_chart_type(full_summary, user_question)
    # Returns: 'bar', 'line', 'scatter', 'histogram', 'pie', or 'none'
    # Separate call because we need a single clean word,
    # not a sentence mixed into the main answer.

    # Step 7 — call Gemini for chart column selection
    chart_column_suggestion = {'x': None, 'y': None}
    if chart_type != 'none':
        chart_column_suggestion = suggest_chart_columns(
            full_summary, user_question, chart_cols
        )
        # Only run this if we're actually drawing a chart.
        # Skipping it when chart_type == 'none' saves an API call.

    # Step 8 — persist this Q&A to the session history
    history.append({
        'q': user_question,
        'a': insight[:500]
        # Truncate to 500 chars — full answers can be huge.
        # 500 chars is enough for Gemini to understand context.
    })
    session['history'] = history[-5:]
    # Keep only the last 5 exchanges to prevent cookie bloat.
    session.modified = True
    # IMPORTANT: Flask doesn't detect mutations to mutable objects
    # (lists/dicts) inside session automatically.
    # Setting session.modified = True forces Flask to re-sign
    # and re-send the updated cookie in this response.

    # Step 9 — return everything to the frontend
    return jsonify({
        'insight'   : insight,
        'chart_type': chart_type,
        'chart_cols': chart_column_suggestion,
        'question'  : user_question      # echo back so frontend can display it
    })


# ---- Route 6  NEW IN PHASE 4 --------------------------------
@app.route('/chart', methods=['POST'])
def chart():
    """
    POST /chart
    Receives chart_type + column names from the frontend,
    calls generate_chart(), and returns the PNG image directly
    as an HTTP response with Content-Type: image/png.

    Why POST and not GET?
    We're sending data: chart_type, x_col, y_col.
    GET requests have no body — this data can't go in a URL cleanly.

    How the frontend displays this image:
      1. fetch('/chart', { method: 'POST', body: JSON... })
      2. response.blob()           ← reads the raw PNG bytes
      3. URL.createObjectURL(blob) ← creates a temporary browser URL
      4. img.src = that URL        ← displays it in an <img> tag
    This is how you show server-generated binary images in a browser
    without saving them as files or encoding them as base64.
    """

    # -- Parse incoming JSON body ---------------------------------
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body missing or not JSON'}), 400

    chart_type = body.get('chart_type', 'bar')
    x_col      = body.get('x_col')    # may be None — generate_chart handles it
    y_col      = body.get('y_col')    # may be None — generate_chart handles it

    # 'none' means Gemini decided no chart is needed for this question
    if chart_type == 'none':
        return jsonify({'message': 'No chart needed for this question.'}), 204
        # 204 = "No Content" — success, but intentionally no response body

    # -- Get the CSV from the session ----------------------------
    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No CSV uploaded yet.'}), 400

    if not os.path.exists(filepath):
        return jsonify({'error': 'Uploaded file not found. Please re-upload.'}), 400

    # -- Load the data and generate the chart --------------------
    try:
        df = pd.read_csv(filepath)
    except:
        df = pd.read_csv(filepath, encoding='latin1')

    buf = generate_chart(df, chart_type, x_col=x_col, y_col=y_col)
    # generate_chart() returns a BytesIO buffer containing PNG bytes,
    # or None if the data isn't suitable for charting.

    if buf is None:
        return jsonify({'error': 'Could not generate chart for this data.'}), 422
        # 422 = "Unprocessable Entity" — valid request, but can't process the data

    # -- Stream the PNG back as the HTTP response ----------------
    return send_file(
        buf,
        mimetype='image/png'
        # mimetype tells the browser "this is a PNG image, not HTML or JSON".
        # Without this, the browser doesn't know how to interpret the bytes.
    )
    # send_file() reads from buf (BytesIO), writes all bytes into the
    # HTTP response body, and sets the Content-Type header automatically.
    # The browser receives it like any other image on the web.


# ---- Route 7 -----------------------------------------------
@app.route('/reset', methods=['POST'])
def reset():
    """
    POST /reset — clears the session for a fresh start.
    Called when the user clicks "Upload new file" in the UI.
    """
    session.clear()
    return jsonify({'message': 'Session cleared. Ready for a new file.'})


# ---- Route 7 -----------------------------------------------
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running'})


# ============================================================
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, port=5000)