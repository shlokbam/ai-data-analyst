# DataLens — AI Data Analyst

An intelligent web application that lets users upload CSV files and ask natural language questions about their data. Powered by Groq/Llama AI, it provides instant insights, statistical analysis, automatic chart generation, multi-session chat history, and PDF export.

## Features

- **User Authentication**: Secure signup/login with hashed passwords (Flask-Login + SQLAlchemy)
- **CSV Upload & Analysis**: Upload any CSV file and get instant statistical summaries
- **AI-Powered Insights**: Ask questions in plain English and receive detailed analysis
- **Automatic Chart Generation**: AI suggests and generates relevant charts (bar, line, scatter, histogram, pie)
- **Multi-Chat Persistence**: Every analysis session is saved — switch between past analyses from the sidebar
- **PDF Export**: Export any conversation as a formatted PDF report (title page + Q&A + charts)
- **Conversation History**: Follow-up questions remember previous context
- **Interactive UI**: Dark-themed interface with sidebar, drag-and-drop upload, and responsive design

## Tech Stack

- **Backend**: Flask (Python), Flask-Login, Flask-SQLAlchemy
- **Database**: SQLite (via SQLAlchemy ORM)
- **AI**: Groq API with Llama 3.3 70B model
- **Data Processing**: Pandas
- **Visualization**: Matplotlib (server-side chart generation)
- **PDF Generation**: ReportLab
- **Frontend**: Vanilla JavaScript, HTML5, CSS3

## Project Structure

```
ai-data-analyst/
├── app.py             # Main Flask app — all routes
├── auth.py            # Auth Blueprint (login, signup, logout)
├── analysis.py        # CSV reading and Pandas summarisation
├── chart.py           # Matplotlib chart generation
├── gemini_helper.py   # Groq/Llama AI integration
├── models.py          # SQLAlchemy models: User, Chat, Message
├── pdf_export.py      # ReportLab PDF builder
├── requirements.txt
├── static/
│   └── app.js         # All frontend JS
├── templates/
│   ├── index.html     # Main app page
│   ├── login.html     # Login page
│   └── signup.html    # Signup page
└── uploads/           # Uploaded CSV files (auto-created)
```

## Setup

### Prerequisites
- Python 3.9+
- A free Groq API key from [console.groq.com](https://console.groq.com)

### Installation

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
# Create a .env file:
GROQ_API_KEY=your_groq_api_key_here
SECRET_KEY=your_random_secret_key_here
UPLOAD_FOLDER=uploads

# 4. Run the app
python app.py
```

Visit `http://localhost:5000` — you'll be redirected to the login page. Sign up to get started.

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Main app (login required) |
| `GET` | `/login` | Login page |
| `GET` | `/signup` | Signup page |
| `GET` | `/logout` | Logout |
| `POST` | `/upload` | Upload CSV file |
| `GET` | `/preview` | Get first 10 rows |
| `GET` | `/summary` | Get statistical summary |
| `POST` | `/ask` | Ask AI a question |
| `POST` | `/chart` | Generate chart image |
| `POST` | `/reset` | Clear session |
| `GET` | `/chats` | List all user's chats |
| `GET` | `/chats/<id>` | Get messages for a chat |
| `POST` | `/chats/<id>/activate` | Restore a past chat session |
| `DELETE` | `/chats/<id>` | Delete a chat |
| `GET` | `/export/<id>` | Download chat as PDF |
| `GET` | `/health` | Health check |

## Usage

1. **Sign up** at `/signup` with your email and password
2. **Upload a CSV** — drag & drop or click to browse (max 5 MB)
3. **Review your data** — column types and a 10-row preview
4. **Ask questions** — e.g. *"Which region has the highest total sales?"*
5. **View insights** — AI answer + auto-generated chart
6. **Ask follow-ups** — conversation context is remembered
7. **Switch analyses** — use the sidebar to revisit past sessions
8. **Export** — click "↓ Export PDF" to download a full report

## Production Deployment

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `GROQ_API_KEY not found` | Ensure `.env` exists with the correct key |
| Upload fails | File must be `.csv` and under 5 MB |
| Chart not generating | Data must have at least one numeric column |
| Preview table empty | CSV may have encoding issues — the app handles UTF-8 and latin1 automatically |
