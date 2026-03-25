# ============================================================
#  app.py  —  Main Flask application
#  Phase B: Auth Blueprint registered, login_required added
#  Phase C: Multi-chat persistence (Chat/Message DB storage)
# ============================================================

import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import pandas as pd
from analysis import analyze_csv, get_chart_columns
from gemini_helper import get_ai_insight, suggest_chart_type, suggest_chart_columns
from chart import generate_chart
from models import db, init_db, Chat, Message
from flask_login import LoginManager, current_user, login_required

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# ---- DATABASE CONFIGURATION ---------------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 'sqlite:///app.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ---- FLASK-LOGIN CONFIGURATION ------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
# Redirects unauthenticated users to /login

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return db.session.get(User, int(user_id))

# ---- REGISTER AUTH BLUEPRINT --------------------------------
from auth import auth_bp
app.register_blueprint(auth_bp)
# All routes in auth.py are now accessible at /login, /signup, /logout

# ---- UPLOAD CONFIGURATION -----------------------------------
UPLOAD_FOLDER      = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def read_csv_safe(filepath):
    """Read a CSV with UTF-8, falling back to latin1 for non-standard encodings."""
    try:
        return pd.read_csv(filepath)
    except UnicodeDecodeError:
        return pd.read_csv(filepath, encoding='latin1')


# ============================================================
#  Route 1 — Main page
# ============================================================
@app.route('/')
@login_required
def index():
    return render_template('index.html')


# ============================================================
#  Route 2 — Upload CSV
#  Phase C: creates a Chat record in the database
# ============================================================
@app.route('/upload', methods=['POST'])
@login_required
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

    # ---- Phase C: Create a Chat record in the database ----
    chat = Chat(
        name=filename.replace('.csv', '').replace('_', ' ').title(),
        # e.g. "sales_data.csv" → "Sales Data"
        csv_path=filepath,
        csv_filename=filename,
        user_id=current_user.id
    )
    db.session.add(chat)
    db.session.commit()
    # chat.id is now populated

    # Store both filepath AND chat_id in the session
    session['filepath'] = filepath
    session['filename'] = filename
    session['chat_id']  = chat.id
    session.pop('history', None)  # clear old conversation

    try:
        df = pd.read_csv(filepath)
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding='latin1')
    rows, cols = df.shape
    columns_info = [{'name': col, 'type': str(df[col].dtype)} for col in df.columns]

    return jsonify({
        'message' : 'File uploaded successfully!',
        'filename': filename,
        'rows'    : rows,
        'cols'    : cols,
        'columns' : columns_info,
        'chat_id' : chat.id
    })


# ============================================================
#  Route 3 — Preview first 10 rows
# ============================================================
@app.route('/preview', methods=['GET'])
@login_required
def preview():
    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No file uploaded yet.'}), 400
    df      = read_csv_safe(filepath)
    # Replace NaN with None → serializes as JSON null (not bare NaN which is invalid JSON)
    preview_df = df.head(10).where(pd.notnull(df.head(10)), None)
    data       = preview_df.to_dict(orient='records')
    return jsonify({'columns': list(df.columns), 'rows': data, 'total_rows': len(df)})


# ============================================================
#  Route 4 — Statistical summary
# ============================================================
@app.route('/summary', methods=['GET'])
@login_required
def summary():
    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No file uploaded yet.'}), 400
    full_summary, df = analyze_csv(filepath)
    return jsonify({'summary': full_summary, 'chart_columns': get_chart_columns(df)})


# ============================================================
#  Route 5 — Ask AI a question
#  Phase C: saves each Q&A as a Message in the database
# ============================================================
@app.route('/ask', methods=['POST'])
@login_required
def ask():
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body is empty or not JSON.'}), 400

    user_question = body.get('question', '').strip()
    if not user_question:
        return jsonify({'error': 'Please enter a question.'}), 400
    if len(user_question) > 500:
        return jsonify({'error': 'Question too long (max 500 characters).'}), 400

    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No CSV uploaded yet. Please upload a file first.'}), 400
    if not os.path.exists(filepath):
        session.pop('filepath', None)
        return jsonify({'error': 'Uploaded file not found. Please re-upload.'}), 400

    full_summary, df = analyze_csv(filepath)
    chart_cols = get_chart_columns(df)
    history    = session.get('history', [])

    insight    = get_ai_insight(full_summary, user_question, history)
    chart_type = suggest_chart_type(full_summary, user_question)

    chart_column_suggestion = {'x': None, 'y': None}
    if chart_type != 'none':
        chart_column_suggestion = suggest_chart_columns(
            full_summary, user_question, chart_cols
        )

    # ---- Phase C: Persist this message to the database ----
    chat_id = session.get('chat_id')
    if chat_id:
        msg = Message(
            chat_id    = chat_id,
            question   = user_question,
            answer     = insight,
            chart_type = chart_type,
            chart_x_col= chart_column_suggestion.get('x'),
            chart_y_col= chart_column_suggestion.get('y'),
        )
        db.session.add(msg)
        db.session.commit()

    # Update session history for follow-up questions
    history.append({'q': user_question, 'a': insight[:500]})
    session['history']  = history[-5:]
    session.modified    = True

    return jsonify({
        'insight'   : insight,
        'chart_type': chart_type,
        'chart_cols': chart_column_suggestion,
        'question'  : user_question
    })


# ============================================================
#  Route 6 — Generate chart image
# ============================================================
@app.route('/chart', methods=['POST'])
@login_required
def chart():
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body missing or not JSON'}), 400

    chart_type = body.get('chart_type', 'bar')
    x_col      = body.get('x_col')
    y_col      = body.get('y_col')

    if chart_type == 'none':
        return jsonify({'message': 'No chart needed for this question.'}), 204

    filepath = session.get('filepath')
    if not filepath:
        return jsonify({'error': 'No CSV uploaded yet.'}), 400
    if not os.path.exists(filepath):
        return jsonify({'error': 'Uploaded file not found. Please re-upload.'}), 400

    df  = read_csv_safe(filepath)
    buf = generate_chart(df, chart_type, x_col=x_col, y_col=y_col)

    if buf is None:
        return jsonify({'error': 'Could not generate chart for this data.'}), 422

    return send_file(buf, mimetype='image/png')


# ============================================================
#  Route 7 — Reset session
# ============================================================
@app.route('/reset', methods=['POST'])
@login_required
def reset():
    session.clear()
    return jsonify({'message': 'Session cleared. Ready for a new file.'})


# ============================================================
#  Route 8 — Health check
# ============================================================
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running'})


# ============================================================
#  Phase C: Multi-chat routes
# ============================================================

@app.route('/chats', methods=['GET'])
@login_required
def list_chats():
    """
    GET /chats
    Returns all chats belonging to the current user,
    ordered newest first, with message count for each.
    """
    chats = (
        Chat.query
        .filter_by(user_id=current_user.id)
        .order_by(Chat.created_at.desc())
        .all()
    )
    result = []
    for c in chats:
        result.append({
            'id'          : c.id,
            'name'        : c.name,
            'csv_filename': c.csv_filename,
            'message_count': len(c.messages),
            'created_at'  : c.created_at.strftime('%b %d, %Y') if c.created_at else '',
            'is_active'   : c.id == session.get('chat_id'),
        })
    return jsonify({'chats': result})


@app.route('/chats/<int:chat_id>', methods=['GET'])
@login_required
def get_chat(chat_id):
    """
    GET /chats/<id>
    Returns all saved messages for a specific chat.
    Used by the frontend to restore a previous session.
    """
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({'error': 'Chat not found.'}), 404

    messages = []
    for m in chat.messages:
        messages.append({
            'id'         : m.id,
            'question'   : m.question,
            'answer'     : m.answer,
            'chart_type' : m.chart_type,
            'chart_x_col': m.chart_x_col,
            'chart_y_col': m.chart_y_col,
            'created_at' : m.created_at.strftime('%H:%M') if m.created_at else '',
        })

    return jsonify({
        'chat'    : {
            'id'          : chat.id,
            'name'        : chat.name,
            'csv_filename': chat.csv_filename,
        },
        'messages': messages,
    })


@app.route('/chats/<int:chat_id>/activate', methods=['POST'])
@login_required
def activate_chat(chat_id):
    """
    POST /chats/<id>/activate
    Sets the given chat as the active session.
    The frontend calls this when the user clicks a past chat in the sidebar.
    """
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({'error': 'Chat not found.'}), 404

    if not chat.csv_path or not os.path.exists(chat.csv_path):
        return jsonify({'error': 'The CSV file for this chat no longer exists on disk.'}), 404

    session['chat_id']  = chat.id
    session['filepath'] = chat.csv_path
    session['filename'] = chat.csv_filename
    session.pop('history', None)  # reset conversation history

    return jsonify({'message': 'Chat activated.', 'chat_id': chat.id})


@app.route('/chats/<int:chat_id>', methods=['DELETE'])
@login_required
def delete_chat(chat_id):
    """
    DELETE /chats/<id>
    Deletes a chat and all its messages (cascade).
    If the deleted chat is the active one, clears the session.
    """
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({'error': 'Chat not found.'}), 404

    db.session.delete(chat)
    db.session.commit()
    # cascade='all, delete-orphan' on Chat.messages means
    # all Message rows for this chat are deleted automatically.

    # If this was the active chat, clear it from the session
    if session.get('chat_id') == chat_id:
        session.pop('chat_id', None)
        session.pop('filepath', None)
        session.pop('filename', None)
        session.pop('history', None)

    return jsonify({'message': 'Chat deleted.'})


# ============================================================
#  Phase D: PDF Export Route
# ============================================================

@app.route('/export/<int:chat_id>')
@login_required
def export_pdf(chat_id):
    """
    GET /export/<id>
    Builds a PDF report for the given chat and streams it
    back as a file download.

    How the chart_generator works:
      We pass a closure that knows the current CSV filepath.
      The closure is called once per Message that has a chart.
      It re-renders the chart from the saved CSV using the
      stored chart_type / x_col / y_col — no AI call needed.
    """
    from pdf_export import build_pdf

    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({'error': 'Chat not found.'}), 404

    if not chat.messages:
        return jsonify({'error': 'This chat has no messages to export.'}), 400

    # ---- Build the chart generator closure ------------------
    def chart_generator(chart_type, x_col, y_col):
        """
        Re-generates a chart from the stored CSV for the PDF.
        Returns BytesIO PNG or None.
        """
        if not chat.csv_path or not os.path.exists(chat.csv_path):
            return None
        try:
            df = pd.read_csv(chat.csv_path)
            return generate_chart(df, chart_type, x_col=x_col, y_col=y_col)
        except Exception:
            return None

    # ---- Build the PDF --------------------------------------
    pdf_buf = build_pdf(chat, list(chat.messages), chart_generator)

    safe_name = (chat.name or 'report').replace(' ', '_').lower()
    filename  = f'datalens_{safe_name}.pdf'

    return send_file(
        pdf_buf,
        mimetype='application/pdf',
        as_attachment=True,
        # as_attachment=True adds Content-Disposition: attachment
        # which tells the browser to DOWNLOAD the file, not display it.
        download_name=filename
    )


# ============================================================
#  Entry point
# ============================================================
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db(app)
    app.run(debug=True, port=5000)