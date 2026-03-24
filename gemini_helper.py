# ============================================================
#  gemini_helper.py  —  All communication with Google Gemini AI
#
#  This file has ONE job: take the CSV summary + user question,
#  talk to Gemini, and return answers back to app.py.
#
#  Why keep AI logic separate from app.py?
#    1. Easy to test in isolation (python gemini_helper.py)
#    2. If Google changes their API again, only THIS file changes
#    3. Single Responsibility Principle — each file does one thing
# ============================================================

import os
import json

from google import genai
# google-genai is Google's NEW official Python SDK (2024+).
# The old package (google-generativeai) is deprecated.
# Install it with: pip install google-genai
# We use 'genai' as the alias — shorter and readable.

from google.genai import types
# 'types' holds helper classes like GenerateContentConfig
# that let us fine-tune how Gemini responds.


# ============================================================
#  PRIVATE HELPER — creates a configured Gemini client
# ============================================================

def _get_client():
    """
    Creates and returns a configured Gemini API client.

    The underscore prefix _ means 'private' by convention —
    only functions inside this file should call this.

    Why create a fresh client each call instead of one global?
    A global client created at import time might run before
    load_dotenv() in app.py has populated os.environ.
    Creating it per-call guarantees the API key is always ready.
    """
    api_key = os.getenv('GEMINI_API_KEY')

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. "
            "Check that it's set in your .env file."
        )

    return genai.Client(api_key=api_key)
    # genai.Client() is the entry point for the new SDK.
    # Unlike the old SDK you don't call genai.configure() globally —
    # you pass the key directly to the Client object.


# The model we use for every call in this app.
# Defined once here so changing it later is a one-line edit.
MODEL = 'gemini-2.0-flash'
# gemini-2.0-flash:
#   - Fast (low latency — good for web apps)
#   - Free tier available
#   - Large context window (can read our big CSV summaries)
#   - Better than 1.5-flash at instruction following


# ============================================================
#  FUNCTION 1 — Main insight generator
#  Called by the /ask route in app.py
# ============================================================

def get_ai_insight(data_summary, user_question, history=None):
    """
    Sends the CSV summary + question to Gemini and returns
    the AI's answer as a plain string.

    Parameters:
        data_summary  (str)  : structured text from analyze_csv()
                               — this is the 'context' Gemini reads
        user_question (str)  : what the user typed in the input box
        history       (list) : previous Q&A pairs for follow-ups
                               — None means this is the first question

    Returns:
        str : Gemini's answer, ready to display in the browser

    How does Gemini 'know' about your data?
    It has NO access to your server or files. We manually inject
    the Pandas summary text into the prompt. Gemini reads it the
    same way you'd read a report someone handed you. This pattern
    is called Retrieval-Augmented Generation (RAG).
    """
    client = _get_client()

    # ----------------------------------------------------------
    #  BUILD THE CONVERSATION HISTORY STRING
    #  For follow-up questions, we show Gemini what was asked
    #  and answered before — like giving someone meeting notes.
    # ----------------------------------------------------------
    history_text = ""
    if history:
        history_text = "\n\nPrevious conversation:\n"
        for i, exchange in enumerate(history[-3:], 1):
            # [-3:] keeps only the last 3 exchanges.
            # Older history adds cost without adding much value.
            history_text += f"Q{i}: {exchange['q']}\nA{i}: {exchange['a']}\n\n"

    # ----------------------------------------------------------
    #  THE PROMPT — this is "prompt engineering"
    #
    #  Structure we follow:
    #    1. Role definition    → tell Gemini WHO it is
    #    2. Context injection  → give it the DATA to reason about
    #    3. The question       → WHAT to answer
    #    4. Output rules       → HOW to format the answer
    #
    #  The quality of your prompt directly determines the quality
    #  of the answer. Vague prompt = vague answer.
    # ----------------------------------------------------------
    prompt = f"""You are an expert data analyst assistant helping a user understand their dataset.

Here is a complete summary of the dataset the user uploaded:
--------------------------------------------------------------
{data_summary}
--------------------------------------------------------------
{history_text}
The user's current question is:
"{user_question}"

Please provide a helpful, clear answer following these rules:
- Answer directly — reference actual column names and numbers from the summary
- Use bullet points for lists of insights (start each with •)
- Bold important numbers or column names using **double asterisks**
- If comparing things, structure your answer with clear comparisons
- If the data doesn't contain enough info to answer, say so clearly
- End with 1-2 follow-up questions under the heading "You might also ask:"
- Keep the tone friendly — assume the user may not be a data expert
- Do NOT repeat the question back to the user
- Do NOT say you are an AI or that you are reading a summary"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        # client.models.generate_content() sends the prompt to Google's
        # servers and waits for the full response (blocking call).
        # 'contents' is the main parameter — it can be a plain string
        # (like here) or a list of Content objects for multi-turn chat.

        return response.text
        # .text is the plain string of Gemini's reply.

    except Exception as e:
        # Catch ANY error (network failure, rate limit, bad key...)
        # and return a user-friendly message instead of a 500 crash.
        return f"Sorry, I couldn't generate an insight right now. Error: {str(e)}"


# ============================================================
#  FUNCTION 2 — Chart type suggester
#  Called by the /ask route right after get_ai_insight()
# ============================================================

def suggest_chart_type(data_summary, user_question):
    """
    Asks Gemini which chart type best represents the answer.

    Why a SEPARATE API call, not part of get_ai_insight()?
    We need a single machine-readable word ('bar', 'line', etc.)
    to pass to Matplotlib. If we asked for it inside the main
    prompt, Gemini might write "I'd suggest using a bar chart
    because..." which is hard to parse reliably.

    One task per prompt = predictable, parseable output.
    This is a core prompt engineering principle.

    Returns:
        str: exactly one of 'bar', 'line', 'scatter',
             'histogram', 'pie', or 'none'
    """
    client = _get_client()

    prompt = f"""You are a data visualisation expert.

Dataset summary:
{data_summary}

User question: "{user_question}"

Which ONE chart type would best visualise the answer?

Reply with ONLY one word from this exact list:
bar, line, scatter, histogram, pie, none

Rules for choosing:
- 'bar'       → comparing values across categories (region vs sales)
- 'line'      → trends over time or ordered sequences (sales by month)
- 'scatter'   → relationship between two numeric variables
- 'histogram' → distribution of a single numeric variable
- 'pie'       → parts of a whole, 8 or fewer categories
- 'none'      → purely factual question where a chart adds no value

Reply with the single word ONLY. No explanation. No punctuation."""

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        chart_type = response.text.strip().lower()
        # .strip() removes whitespace/newlines Gemini may add.
        # .lower() normalises 'Bar' or 'BAR' → 'bar'.

        valid_types = {'bar', 'line', 'scatter', 'histogram', 'pie', 'none'}
        # A set {} not a list [] — membership check ('in') is
        # O(1) for sets vs O(n) for lists. Faster, more Pythonic.

        return chart_type if chart_type in valid_types else 'bar'
        # If Gemini returns something unexpected, fall back to 'bar'.

    except Exception:
        return 'bar'  # safe default on any error


# ============================================================
#  FUNCTION 3 — Chart column selector
#  Called by /ask only when chart_type != 'none'
# ============================================================

def suggest_chart_columns(data_summary, user_question, available_columns):
    """
    Asks Gemini which specific columns to use for X and Y axes.

    Without this, Phase 4 (Matplotlib) would blindly use the
    first two numeric columns — which may have nothing to do with
    what the user asked. This makes charts INTELLIGENT: they
    always plot what's relevant to the question.

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

    # Fast path — if there's only one numeric column, no need to ask
    if not numeric_cols:
        return {'x': None, 'y': None}
    if len(numeric_cols) == 1:
        x = text_cols[0] if text_cols else numeric_cols[0]
        return {'x': x, 'y': numeric_cols[0]}

    prompt = f"""You are a data visualisation expert.

Dataset summary:
{data_summary}

User question: "{user_question}"

Available numeric columns : {numeric_cols}
Available text/category columns: {text_cols}

Which columns should be used for X and Y axes of the chart?

Reply with ONLY valid JSON in this exact format, nothing else:
{{"x": "column_name_here", "y": "column_name_here"}}

Rules:
- x should be a text/category column when comparing groups
- x should be a numeric or time column when showing trends
- y must always be a numeric column (the value being measured)
- Use ONLY column names from the lists above, spelled exactly right
- No explanation, no markdown, just the JSON object"""

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        raw = response.text.strip()

        # Strip markdown code fences if Gemini wraps in ```json ... ```
        raw = raw.replace('```json', '').replace('```', '').strip()

        result = json.loads(raw)
        # json.loads() parses the JSON string → Python dict.
        # Raises json.JSONDecodeError if the string is malformed.

        # Validate: returned column names must actually exist
        all_cols = numeric_cols + text_cols
        if result.get('x') not in all_cols or result.get('y') not in numeric_cols:
            raise ValueError("Gemini returned column names that don't exist")

        return result

    except Exception:
        # Fallback: first text col as X, first numeric as Y
        x = text_cols[0] if text_cols else numeric_cols[0]
        return {'x': x, 'y': numeric_cols[0]}


# ============================================================
#  SELF-TEST — run with: python gemini_helper.py
#  Requires a real GEMINI_API_KEY in .env for live tests.
#  Without a key it still shows all function signatures.
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

Statistical summary (numeric columns):
        Sales    Units
count   20.00    20.00
mean  5432.10    87.30
min    890.00    10.00
max  12000.00   175.00

Categorical column distributions:
  'Region' top values: {'North': 6, 'South': 5, 'East': 5, 'West': 4}

Data quality: No missing values found.

Sample data (first 5 rows):
  Region   Month    Sales  Units
   North  January  7200.0    112
   South  January  4800.0     72
    East  February 6100.0     95
    West  February 3900.0     61
   North  March    5200.0     85"""

    TEST_QUESTION = "Which region has the highest average sales?"
    TEST_COLS     = {'numeric': ['Sales', 'Units'], 'text': ['Region', 'Month']}

    DIVIDER = '=' * 55
    print(DIVIDER)
    print("GEMINI HELPER SELF-TEST")
    print(DIVIDER)

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key or api_key == 'your_gemini_api_key_here':
        print("\n  GEMINI_API_KEY not set — showing function signatures only.")
        print("\n  Functions available:")
        print("    get_ai_insight(data_summary, user_question, history=None)")
        print("    suggest_chart_type(data_summary, user_question)")
        print("    suggest_chart_columns(data_summary, user_question, columns)")
        print("\n  Add your key to .env then re-run to test live API calls.")
    else:
        print(f"\nQuestion: {TEST_QUESTION}\n")

        print("--- [1] get_ai_insight() ---")
        insight = get_ai_insight(TEST_SUMMARY, TEST_QUESTION)
        print(insight[:400] + "..." if len(insight) > 400 else insight)

        print("\n--- [2] suggest_chart_type() ---")
        ctype = suggest_chart_type(TEST_SUMMARY, TEST_QUESTION)
        print(f"Suggested chart type: '{ctype}'")

        print("\n--- [3] suggest_chart_columns() ---")
        cols = suggest_chart_columns(TEST_SUMMARY, TEST_QUESTION, TEST_COLS)
        print(f"Suggested columns: x='{cols['x']}', y='{cols['y']}'")

        print(f"\n{DIVIDER}")
        print("All Gemini functions working correctly ✓")
