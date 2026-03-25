# ============================================================
#  analysis.py  —  CSV reading and data summarisation
#
#  This file has ONE job: take a CSV filepath, read it with
#  Pandas, and produce a rich text summary of the data.
#
#  That summary is what we'll send to Gemini in Phase 3
#  instead of sending the entire CSV (which would be slow,
#  expensive, and hit token limits).
# ============================================================

import pandas as pd
# pandas is THE Python library for working with tabular data.
# We import it aliased as 'pd' — this is a universal convention
# in the data science world. You'll see 'pd' in every tutorial,
# Stack Overflow answer, and textbook. Always use 'pd'.

import json
# Built-in Python module. We use it to convert Python dicts/lists
# into nicely formatted JSON strings for the summary output.


# ============================================================
#  MAIN FUNCTION — called by app.py when a question is asked
# ============================================================

def analyze_csv(filepath):
    """
    Reads a CSV file and returns two things:
      1. summary  (str)  — a structured text description of the data
      2. df       (DataFrame) — the raw data table for chart generation

    Why return both?
    - summary goes to Gemini as context (plain text, compact)
    - df    goes to Matplotlib for drawing charts (raw data needed)

    Parameters:
        filepath (str): path to the saved CSV file, e.g. "uploads/sales.csv"

    Returns:
        tuple: (summary_string, pandas_dataframe)
    """

    # ----------------------------------------------------------
    #  STEP 1 — Load the CSV into a DataFrame
    # ----------------------------------------------------------
    try:
        df = pd.read_csv(filepath)
    except:
        df = pd.read_csv(filepath, encoding='latin1')
    # pd.read_csv() does a lot of heavy lifting:
    #   - Opens and reads the file
    #   - Detects the header row (first row becomes column names)
    #   - Infers data types: numbers become int64/float64,
    #     text becomes 'object', dates can be parsed too
    #   - Returns a DataFrame — a 2D table structure
    #
    # DataFrame mental model:
    #   - Rows = individual records (like spreadsheet rows)
    #   - Columns = fields/attributes (like spreadsheet columns)
    #   - Each column has ONE consistent data type
    #
    # Example for a sales CSV:
    #   df looks like:
    #       Region    Sales    Month
    #       North     15000    Jan
    #       South     22000    Feb
    #       ...


    # We'll collect all parts of our summary in this list,
    # then join them at the end with double newlines.
    summary_parts = []


    # ----------------------------------------------------------
    #  STEP 2 — Basic shape (rows × columns)
    # ----------------------------------------------------------
    rows, cols = df.shape
    # df.shape returns a tuple: (number_of_rows, number_of_columns)
    # We unpack it directly into two variables with tuple unpacking.
    # e.g. if the CSV has 500 rows and 8 columns → rows=500, cols=8

    summary_parts.append(
        f"Dataset overview: {rows} rows × {cols} columns."
    )


    # ----------------------------------------------------------
    #  STEP 3 — Column names and their data types
    # ----------------------------------------------------------
    col_details = []
    for col in df.columns:
        # df.columns is an Index object (like a list) of all column names.
        # We loop through each column name.

        dtype = str(df[col].dtype)
        # df[col] selects the entire column as a Series.
        # .dtype tells us the Pandas data type:
        #   int64   → whole numbers (age, count, year)
        #   float64 → decimal numbers (price, temperature, ratio)
        #   object  → text / mixed types (name, city, category)
        #   bool    → True/False
        #   datetime64 → dates and times

        # Map Pandas dtype names to friendlier labels for Gemini
        if 'int' in dtype:
            friendly_type = 'integer'
        elif 'float' in dtype:
            friendly_type = 'decimal'
        elif 'datetime' in dtype:
            friendly_type = 'date/time'
        elif 'bool' in dtype:
            friendly_type = 'boolean'
        else:
            friendly_type = 'text'

        # Count unique values — useful context for Gemini
        unique_count = df[col].nunique()
        # .nunique() = "number of unique values"
        # For a 'Country' column with 500 rows but only 10 countries → 10
        # For an 'ID' column → likely equals the number of rows

        col_details.append(f"  - {col} ({friendly_type}, {unique_count} unique values)")

    summary_parts.append("Columns:\n" + "\n".join(col_details))
    # "\n".join(list) joins all items with a newline between them.
    # Result looks like:
    #   Columns:
    #     - Region (text, 4 unique values)
    #     - Sales (decimal, 500 unique values)
    #     - Month (text, 12 unique values)


    # ----------------------------------------------------------
    #  STEP 4 — Statistical summary of numeric columns
    # ----------------------------------------------------------
    numeric_df = df.select_dtypes(include=['number'])
    # select_dtypes() filters columns by their data type.
    # include=['number'] = keep ONLY int64 and float64 columns.
    # Text columns would cause errors in statistical calculations,
    # so we isolate just the numbers.

    if not numeric_df.empty:
        # .empty returns True if the DataFrame has no columns/rows
        # We only do this if there ARE numeric columns

        stats = numeric_df.describe()
        # .describe() is one of Pandas' most useful methods.
        # It auto-calculates 8 statistics for EVERY numeric column:
        #   count  → how many non-null values
        #   mean   → average
        #   std    → standard deviation (how spread out the values are)
        #   min    → smallest value
        #   25%    → first quartile (25% of values are below this)
        #   50%    → median (middle value)
        #   75%    → third quartile (75% of values are below this)
        #   max    → largest value

        # Round to 2 decimal places to keep the summary compact
        stats = stats.round(2)

        summary_parts.append(
            f"Statistical summary (numeric columns):\n{stats.to_string()}"
        )
        # .to_string() converts the DataFrame to a readable text table.
        # We use this instead of .to_csv() or .to_json() because
        # plain text is easiest for Gemini to read.


    # ----------------------------------------------------------
    #  STEP 5 — Categorical column value counts
    # ----------------------------------------------------------
    text_cols = df.select_dtypes(include=['object', 'string']).columns.tolist()
    # select_dtypes(include=['object', 'string']) gets text columns.
    # .columns returns an Index, .tolist() converts it to a plain list.

    cat_summaries = []
    for col in text_cols[:3]:
        # [:3] = only process the FIRST 3 text columns.
        # A CSV with 10 text columns would create a huge summary.
        # We limit to 3 to keep the Gemini prompt compact.

        top_values = df[col].value_counts().head(5)
        # .value_counts() counts how many times each unique value appears,
        # sorted from most common to least common.
        # .head(5) keeps only the top 5 most frequent values.
        #
        # Example for a 'Region' column:
        #   North    120
        #   South     98
        #   East      87
        #   West      75

        cat_summaries.append(
            f"  '{col}' top values: {top_values.to_dict()}"
        )
        # .to_dict() converts the Series to a Python dict, which
        # formats nicely as: {'North': 120, 'South': 98, ...}

    if cat_summaries:
        summary_parts.append(
            "Categorical column distributions:\n" + "\n".join(cat_summaries)
        )


    # ----------------------------------------------------------
    #  STEP 6 — Missing values report
    # ----------------------------------------------------------
    missing = df.isnull().sum()
    # df.isnull() creates a boolean DataFrame:
    #   True  = the cell is empty (NaN / None)
    #   False = the cell has a value
    #
    # .sum() adds up the True values per column.
    # (True = 1, False = 0 in Python arithmetic)
    # Result: a Series with column name → count of missing values.

    missing_cols = missing[missing > 0]
    # Boolean indexing: keep only columns where missing count > 0.
    # If ALL columns are complete, missing_cols will be empty.

    if missing_cols.empty:
        summary_parts.append("Data quality: No missing values found.")
    else:
        total_missing = missing_cols.sum()
        total_cells = rows * cols
        pct = round((total_missing / total_cells) * 100, 1)
        # Calculate what percentage of ALL cells are missing.
        # This gives Gemini useful context about data quality.

        missing_info = missing_cols.to_dict()
        summary_parts.append(
            f"Data quality: {total_missing} missing values ({pct}% of data).\n"
            f"  Missing by column: {missing_info}"
        )


    # ----------------------------------------------------------
    #  STEP 7 — Sample rows (so Gemini can see real data)
    # ----------------------------------------------------------
    sample = df.head(5)
    # .head(n) returns the first n rows.
    # We give Gemini 5 actual rows so it understands the real
    # data format, not just statistics about it.

    summary_parts.append(
        f"Sample data (first 5 rows):\n{sample.to_string(index=False)}"
    )
    # to_string(index=False) prints the table without the row numbers.
    # Row numbers (0, 1, 2...) are not part of the actual data,
    # so we hide them to keep the output clean.


    # ----------------------------------------------------------
    #  ASSEMBLE AND RETURN
    # ----------------------------------------------------------
    full_summary = "\n\n".join(summary_parts)
    # Join all sections with a blank line between them.
    # The double \n creates a visible paragraph break in plain text,
    # making it easy for Gemini to parse each section.

    return full_summary, df
    # We return BOTH:
    #   full_summary → goes to Gemini as context (Phase 3)
    #   df           → goes to Matplotlib for charts (Phase 4)


# ============================================================
#  HELPER — extract column info for chart generation
# ============================================================

def get_chart_columns(df):
    """
    Returns useful column info for deciding what to plot.
    Phase 4 (Matplotlib) and Phase 3 (Gemini chart suggestion)
    both use this to know what columns are available.

    Returns a dict with:
        numeric  → list of numeric column names
        text     → list of text/category column names
        all      → list of ALL column names
    """
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    text_cols    = df.select_dtypes(include=['object', 'string']).columns.tolist()

    return {
        'numeric': numeric_cols,
        'text':    text_cols,
        'all':     df.columns.tolist()
    }


# ============================================================
#  QUICK SELF-TEST
#  Run this file directly to test it without starting Flask:
#    python analysis.py
# ============================================================

if __name__ == '__main__':
    import os

    # Create a small in-memory CSV for testing
    import io
    test_csv = """product,category,price,units_sold,in_stock
Laptop,Electronics,999.99,150,True
Phone,Electronics,599.50,320,True
Desk,Furniture,249.00,80,False
Chair,Furniture,199.99,200,True
Headphones,Electronics,149.99,410,True
Lamp,Furniture,,95,True
Keyboard,Electronics,79.99,275,True"""
    # Note: Lamp has no price — tests missing value detection

    # Save to a temp file
    test_path = '/tmp/test_data.csv'
    with open(test_path, 'w') as f:
        f.write(test_csv)

    print("=" * 60)
    print("RUNNING analysis.py SELF-TEST")
    print("=" * 60)

    summary, df = analyze_csv(test_path)

    print("\n--- SUMMARY OUTPUT (what Gemini will receive) ---\n")
    print(summary)

    print("\n--- CHART COLUMNS ---\n")
    print(get_chart_columns(df))

    print("\n--- DataFrame shape ---")
    print(f"Rows: {df.shape[0]}, Columns: {df.shape[1]}")

    print("\n✓ Self-test complete")
