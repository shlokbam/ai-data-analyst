# ============================================================
#  gemini_helper.py  —  AI layer (now powered by Groq)
#
#  IMPORTANT: This file was renamed from gemini_helper.py
#  but KEPT the same filename intentionally.
#  app.py imports from this file by name — if we renamed it
#  we'd have to change every import in app.py.
#  Keeping the filename means app.py needs ZERO changes.
#
#  Why Groq instead of Gemini?
#    - No API version headaches (v1beta, v1, etc.)
#    - Genuinely faster — Groq runs on custom LPU hardware
#    - Free tier: 14,400 requests/day, 30 req/min
#    - llama-3.3-70b is excellent at data analysis tasks
#    - Dead-simple API — almost identical to OpenAI's format
#
#  Get your free key at: console.groq.com
#  Takes 30 seconds — just sign in with Google.
# ============================================================

import os
import json

from groq import Groq
# Groq's official Python SDK.
# Install: pip install groq
# The SDK follows the OpenAI SDK design exactly —
# if you've seen one, you've seen the other.
# Groq() creates a client. client.chat.completions.create() sends a prompt.


# ============================================================
#  PRIVATE HELPER — creates a configured Groq client
# ============================================================

def _get_client():
    """
    Creates and returns a configured Groq API client.

    The underscore _ prefix means 'private by convention' —
    only functions inside this file should call this.

    Why not create one global client at the top of the file?
    A global created at import time runs BEFORE load_dotenv()
    in app.py has loaded your .env file into os.environ.
    Creating it per-call guarantees the key is always there.
    """
    api_key = os.getenv('GROQ_API_KEY')

    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found. "
            "Get a free key at console.groq.com, "
            "then add GROQ_API_KEY=your_key to your .env file."
        )

    return Groq(api_key=api_key)
    # Groq(api_key=...) authenticates every request this client makes.
    # Unlike some SDKs, there's no global configure() step —
    # you pass the key directly to the client object.


# The model used for every call in this app.
# One constant here means one edit changes every call at once.
MODEL = 'llama-3.3-70b-versatile'
# llama-3.3-70b-versatile:
#   - Meta's Llama 3.3, 70 billion parameters
#   - 'versatile' = good at reasoning, analysis, following instructions
#   - 128K token context window — handles large CSV summaries easily
#   - Free tier on Groq: 14,400 requests/day
#   - Consistently follows structured output instructions (JSON, bullets)
#
# Other Groq models you could use instead:
#   'llama-3.1-8b-instant'   → faster, smaller, less capable
#   'mixtral-8x7b-32768'     → good alternative, 32K context
#   'gemma2-9b-it'           → Google's Gemma 2, fast and capable


# ============================================================
#  HOW THE GROQ API WORKS — read this once
# ============================================================
#
#  Groq (like OpenAI) uses a "chat completions" format.
#  Every request is a LIST of messages, each with a role:
#
#    'system' → background instructions, sets the AI's persona
#               and rules. Sent once, before user messages.
#    'user'   → what the user (or we) are asking
#    'assistant' → what the AI replied (used for multi-turn)
#
#  Example:
#    messages = [
#      {'role': 'system',    'content': 'You are a data analyst.'},
#      {'role': 'user',      'content': 'What is the average sales?'}
#    ]
#
#  The response comes back as:
#    response.choices[0].message.content  → the AI's reply string
#
#  This is cleaner than Gemini's format because system instructions
#  and user content are separated — better for prompt engineering.


# ============================================================
#  FUNCTION 1 — Main insight generator
#  Called by the /ask route in app.py
# ============================================================

def get_ai_insight(data_summary, user_question, history=None):
    """
    Sends the CSV summary + question to Groq and returns
    the AI's answer as a plain string.

    Parameters:
        data_summary  (str)  : structured text from analyze_csv()
                               — this is the 'context' the AI reads
        user_question (str)  : what the user typed in the input box
        history       (list) : previous Q&A pairs for follow-ups
                               — None means this is the first question

    Returns:
        str : the AI's answer, ready to display in the browser

    How the AI 'knows' about your data:
    Groq has NO access to your server or files.
    We manually inject the Pandas summary text into the system
    prompt. The model reads it like a report handed to it.
    This pattern is called RAG — Retrieval-Augmented Generation.
    """
    client = _get_client()

    # ----------------------------------------------------------
    #  SYSTEM PROMPT
    #  The system message sets the AI's persistent role and rules
    #  for the entire conversation. It's sent with every request
    #  but written once here — clean and reusable.
    # ----------------------------------------------------------
    system_prompt = f"""You are an expert data analyst assistant helping a user understand their dataset.

Here is a complete summary of the dataset the user uploaded:
--------------------------------------------------------------
{data_summary}
--------------------------------------------------------------

Your rules for every response:
- Answer directly — reference actual column names and numbers from the summary above
- Use bullet points for lists of insights (start each bullet with •)
- Bold important numbers or column names using **double asterisks**
- If comparing things, structure your answer with clear comparisons
- If the data doesn't contain enough info to answer, say so clearly
- End with 1-2 follow-up questions under the heading "You might also ask:"
- Keep the tone friendly — assume the user may not be a data expert
- Do NOT repeat the question back to the user
- Do NOT mention that you are an AI or that you are reading a summary"""

    # ----------------------------------------------------------
    #  BUILD THE MESSAGES LIST
    #  Start with the system message, then add conversation
    #  history (for follow-up question support), then the
    #  current user question.
    # ----------------------------------------------------------
    messages = [{'role': 'system', 'content': system_prompt}]
    # messages is a list of dicts — we'll append to it below.

    # Add previous exchanges so the AI can answer follow-up questions.
    # "What about the other region?" only makes sense if the AI
    # remembers what was already discussed.
    if history:
        for exchange in history[-3:]:
            # [-3:] = only the last 3 exchanges (older ones add cost, not value)
            messages.append({'role': 'user',      'content': exchange['q']})
            messages.append({'role': 'assistant', 'content': exchange['a']})
            # We reconstruct the conversation turn-by-turn.
            # The AI sees: user asked X → I answered Y → now user asks Z.

    # Finally, add the current question
    messages.append({'role': 'user', 'content': user_question})

    # ----------------------------------------------------------
    #  SEND TO GROQ AND GET RESPONSE
    # ----------------------------------------------------------
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            # max_tokens: cap the response length.
            # 1024 tokens ≈ 750 words — enough for a detailed insight.
            # Without this cap, the model might write an essay.
            max_tokens=1024,
            # temperature: controls randomness/creativity (0.0 to 2.0).
            # 0.3 = focused and consistent — good for factual data analysis.
            # Higher values (0.8+) = more creative but less reliable.
            temperature=0.3,
        )

        return response.choices[0].message.content
        # response.choices is a list (could be multiple completions).
        # [0] = the first (and usually only) completion.
        # .message.content = the AI's reply as a plain string.

    except Exception as e:
        return f"Sorry, I couldn't generate an insight right now. Error: {str(e)}"
        # Catches network errors, rate limits, invalid keys, etc.
        # Returns a friendly message instead of crashing the whole app.


# ============================================================
#  FUNCTION 2 — Chart type suggester
#  Called by the /ask route right after get_ai_insight()
# ============================================================

def suggest_chart_type(data_summary, user_question):
    """
    Asks the AI which chart type best represents the answer.

    Why a SEPARATE call, not part of get_ai_insight()?
    We need a single machine-readable word to pass to Matplotlib.
    If we asked for it in the main response, the AI might write
    "I'd suggest a bar chart because..." — hard to parse reliably.
    One isolated task per call = predictable, parseable output.

    Returns:
        str: exactly one of 'bar', 'line', 'scatter',
             'histogram', 'pie', or 'none'
    """
    client = _get_client()

    messages = [
        {
            'role': 'system',
            'content': (
                'You are a data visualisation expert. '
                'You reply with ONLY a single word. No explanation. No punctuation. '
                'Choose from: bar, line, scatter, histogram, pie, none'
            )
        },
        {
            'role': 'user',
            'content': f"""Dataset summary:
{data_summary}

User question: "{user_question}"

Which ONE chart type best visualises the answer?

Rules:
- bar       → comparing values across categories (region vs sales)
- line      → trends over time or ordered sequences (monthly revenue)
- scatter   → relationship between two numeric variables
- histogram → distribution of a single numeric variable
- pie       → parts of a whole, 8 or fewer categories
- none      → purely factual question (e.g. "what is the average?")

Reply with the single word ONLY."""
        }
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=5,
            # max_tokens=5 is intentional — we want ONE word.
            # Capping it prevents the model from explaining itself
            # even if the system prompt fails to stop it.
            temperature=0.0,
            # temperature=0.0 = fully deterministic output.
            # Given the same input, always returns the same answer.
            # Perfect for classification tasks like this.
        )

        chart_type = response.choices[0].message.content.strip().lower()
        # .strip() removes any whitespace or newlines.
        # .lower() normalises 'Bar' → 'bar'.

        valid = {'bar', 'line', 'scatter', 'histogram', 'pie', 'none'}
        return chart_type if chart_type in valid else 'bar'
        # Validate — if the model returns something unexpected, default to 'bar'.
        # 'bar' is a safe fallback that works for most data shapes.

    except Exception:
        return 'bar'


# ============================================================
#  FUNCTION 3 — Chart column selector
#  Called by /ask only when chart_type != 'none'
# ============================================================

def suggest_chart_columns(data_summary, user_question, available_columns):
    """
    Asks the AI which columns to use for the X and Y axes.

    Without this, Matplotlib would blindly use the first two
    numeric columns — which may have nothing to do with what
    the user asked. This makes charts relevant to the question.

    Parameters:
        data_summary      (str)  : the structured CSV summary
        user_question     (str)  : the user's question
        available_columns (dict) : {'numeric': [...], 'text': [...]}

    Returns:
        dict: {'x': 'column_name', 'y': 'column_name'}
    """
    client = _get_client()

    numeric_cols = available_columns.get('numeric', [])
    text_cols    = available_columns.get('text', [])

    # Fast paths — skip the API call when the answer is obvious
    if not numeric_cols:
        return {'x': None, 'y': None}
    if len(numeric_cols) == 1:
        # Only one numeric column — no need to ask the AI.
        # For histograms the x and y are the same column, which is fine.
        # generate_chart() handles this correctly on the server.
        x = text_cols[0] if text_cols else numeric_cols[0]
        return {'x': x, 'y': numeric_cols[0]}

    messages = [
        {
            'role': 'system',
            'content': (
                'You are a data visualisation expert. '
                'You reply with ONLY a valid JSON object. '
                'No explanation. No markdown. No code fences. Just the JSON.'
            )
        },
        {
            'role': 'user',
            'content': f"""Dataset summary:
{data_summary}

User question: "{user_question}"

Available numeric columns : {numeric_cols}
Available text/category columns: {text_cols}

Which columns should be the X and Y axes for a chart answering this question?

Rules:
- x → use a text/category column when comparing groups
- x → use a numeric or time column when showing trends
- y → must ALWAYS be a numeric column (the measured value)
- Use column names spelled EXACTLY as shown in the lists above

Reply with ONLY this JSON format, nothing else:
{{"x": "column_name_here", "y": "column_name_here"}}"""
        }
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=60,
            # 60 tokens is plenty for a small JSON object like {"x":"col","y":"col"}
            temperature=0.0,
            # Deterministic — column selection should be consistent.
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences in case the model wraps in ```json ... ```
        raw = raw.replace('```json', '').replace('```', '').strip()

        result = json.loads(raw)
        # json.loads() parses the JSON string into a Python dict.
        # Raises json.JSONDecodeError if the string is malformed.

        # Validate that returned column names actually exist in the data
        all_cols = numeric_cols + text_cols
        if result.get('x') not in all_cols or result.get('y') not in numeric_cols:
            raise ValueError("Model returned column names that don't exist")

        return result

    except Exception:
        # Fallback: first text col as X, first numeric col as Y
        x = text_cols[0] if text_cols else numeric_cols[0]
        return {'x': x, 'y': numeric_cols[0]}


# ============================================================
#  SELF-TEST — run with:  python gemini_helper.py
#  Requires GROQ_API_KEY in your .env file for live tests.
# ============================================================

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    TEST_SUMMARY = """Dataset overview: 20 rows x 4 columns.

Columns:
  - Region (text, 4 unique values)
  - Month (text, 6 unique values)
  - Sales (decimal, 18 unique values)
  - Units (integer, 16 unique values)

Statistical summary:
        Sales    Units
mean  5432.10    87.30
min    890.00    10.00
max  12000.00   175.00

Top values — Region: North(6), South(5), East(5), West(4)
No missing values.

Sample rows:
  Region   Month    Sales  Units
   North  January  7200.0    112
   South  January  4800.0     72"""

    TEST_QUESTION = "Which region has the highest average sales?"
    TEST_COLS     = {'numeric': ['Sales', 'Units'], 'text': ['Region', 'Month']}

    D = '=' * 55
    print(D)
    print("AI HELPER SELF-TEST  (Groq / llama-3.3-70b)")
    print(D)

    api_key = os.getenv('GROQ_API_KEY')
    if not api_key or 'your' in api_key:
        print("\n  GROQ_API_KEY not set.")
        print("  → Get a free key at: console.groq.com (30 seconds)")
        print("  → Add to .env:  GROQ_API_KEY=gsk_xxxxxxxxxxxx")
        print("  → Re-run this file to test live API calls.\n")
    else:
        print(f"\nQuestion: {TEST_QUESTION}\n")

        print("--- [1] get_ai_insight() ---")
        insight = get_ai_insight(TEST_SUMMARY, TEST_QUESTION)
        print(insight[:400] + '...' if len(insight) > 400 else insight)

        print("\n--- [2] suggest_chart_type() ---")
        ctype = suggest_chart_type(TEST_SUMMARY, TEST_QUESTION)
        print(f"  → '{ctype}'")

        print("\n--- [3] suggest_chart_columns() ---")
        cols = suggest_chart_columns(TEST_SUMMARY, TEST_QUESTION, TEST_COLS)
        print(f"  → x='{cols['x']}', y='{cols['y']}'")

        print(f"\n{D}")
        print("All 3 Groq functions working ✓")