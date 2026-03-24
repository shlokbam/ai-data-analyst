# ============================================================
#  chart.py  —  Server-side chart generation with Matplotlib
#
#  This file has ONE job: receive a DataFrame + chart config
#  from app.py, draw the chart entirely in server memory,
#  and return it as raw PNG bytes.
#
#  The browser never downloads a chart FILE — it receives
#  the image bytes directly in the HTTP response, the same
#  way a server would send back any image from a database.
#
#  Why generate charts on the SERVER, not in the browser?
#    - No JavaScript charting library needed on the frontend
#    - Python/Matplotlib has far more chart types and control
#    - Consistent rendering — looks identical on every device
#    - The user can right-click → Save Image to keep it
# ============================================================

import matplotlib
matplotlib.use('Agg')
# ↑ THIS LINE IS CRITICAL — must come before any other matplotlib import.
#
# By default Matplotlib tries to open a GUI window to DISPLAY charts.
# On a server there is no screen, no display, no GUI — just a process.
# Trying to open a window would crash immediately.
#
# 'Agg' stands for "Anti-Grain Geometry" — a non-interactive backend
# that renders charts to memory (a buffer) instead of a screen.
# Agg = "draw pixels in RAM, not on a monitor"
#
# Rule: always set the backend BEFORE importing pyplot.
# If you import pyplot first, the backend is already locked in.

import matplotlib.pyplot as plt
# pyplot is Matplotlib's high-level drawing interface.
# We import it as 'plt' — the universal convention.
# plt.subplots(), plt.savefig(), plt.close() — all from here.

import matplotlib.ticker as ticker
# ticker gives us tools to format axis labels —
# e.g. showing "5,000" instead of "5000.0" on the Y axis.

import pandas as pd
import numpy as np
# numpy is Matplotlib's number-crunching foundation.
# We use it for: np.arange() (evenly spaced numbers for bar positions)
# and np.isnan() (detect missing values before plotting).

from io import BytesIO
# BytesIO creates an in-memory file-like object.
# Instead of saving the chart to disk as "chart.png",
# we save it to a BytesIO buffer — a file that lives in RAM.
# Flask reads from this buffer and sends it as the HTTP response.
# Faster, cleaner, no disk I/O, no file cleanup needed.


# ============================================================
#  COLOUR PALETTE
#  Defined once here so every chart uses consistent colours.
#  Changing one value here updates every chart type.
# ============================================================

PALETTE = {
    'bar'      : '#4A90E2',   # calm blue — good for bars (neutral, readable)
    'bar_multi': ['#4A90E2', '#E24B4A', '#1D9E75', '#F5A623', '#9B59B6'],
    # multi-colour list used when plotting several bar groups
    'line'     : ['#4A90E2', '#E24B4A', '#1D9E75', '#F5A623'],
    'scatter'  : '#E24B4A',   # red — makes dots pop against white background
    'histogram': '#1D9E75',   # green — distinct from bars
    'pie'      : ['#4A90E2', '#E24B4A', '#1D9E75', '#F5A623',
                  '#9B59B6', '#1ABC9C', '#E67E22', '#E91E63'],
}

STYLE = {
    'bg'         : '#FFFFFF',   # chart background — white
    'grid_colour': '#EEEEEE',   # light grey grid lines
    'text'       : '#333333',   # axis labels, title
    'spine'      : '#DDDDDD',   # axis border colour
    'title_size' : 14,
    'label_size' : 11,
    'tick_size'  : 10,
}


# ============================================================
#  HELPER — apply consistent styling to every chart
# ============================================================

def _style_axes(ax, title=''):
    """
    Applies our custom style to an Axes object.
    Called by every chart function so we don't repeat this
    20-line block inside each one.

    Parameters:
        ax    : Matplotlib Axes object (the drawing canvas)
        title : string to show at the top of the chart
    """
    # Set the chart title
    if title:
        ax.set_title(
            title,
            fontsize=STYLE['title_size'],
            fontweight='bold',
            color=STYLE['text'],
            pad=16           # padding between title and chart body (points)
        )

    # Style all four border lines (called "spines") around the chart
    for spine in ax.spines.values():
        spine.set_edgecolor(STYLE['spine'])
        spine.set_linewidth(0.8)

    # Add subtle horizontal grid lines — makes values easier to read
    ax.yaxis.grid(True, color=STYLE['grid_colour'], linewidth=0.7, zorder=0)
    # zorder=0 puts the grid BEHIND bars/lines (higher zorder = in front)
    ax.set_axisbelow(True)
    # Ensures gridlines are drawn below the chart data, not on top

    # Style axis tick labels
    ax.tick_params(axis='both', labelsize=STYLE['tick_size'],
                   labelcolor=STYLE['text'], length=0)
    # length=0 hides the tick marks themselves (the little dashes)
    # — cleaner look when you already have grid lines

    # Set background colour
    ax.set_facecolor(STYLE['bg'])


def _format_y_axis(ax, df_col):
    """
    Formats Y-axis tick labels with commas for thousands.
    So "5000.0" becomes "5,000" and "1500000" becomes "1,500,000".

    Parameters:
        ax     : Matplotlib Axes object
        df_col : the Pandas Series being plotted on Y
    """
    max_val = df_col.max() if not df_col.empty else 0

    if max_val >= 1000:
        # Use comma-separated thousands formatting
        ax.yaxis.set_major_formatter(
            ticker.FuncFormatter(lambda x, _: f'{x:,.0f}')
            # FuncFormatter takes a function: (value, position) → string
            # f'{x:,.0f}' formats x with commas, 0 decimal places
        )


def _rotate_x_labels(ax, labels, threshold=6):
    """
    Rotates X-axis labels if there are many of them, so they
    don't overlap each other.

    Parameters:
        ax        : Matplotlib Axes
        labels    : the list of label strings
        threshold : rotate if more labels than this number
    """
    if len(labels) > threshold:
        plt.setp(
            ax.get_xticklabels(),
            rotation=40,      # angle in degrees
            ha='right',       # horizontal alignment — 'right' aligns
            rotation_mode='anchor'  # rotates around the label's anchor point
        )
        # plt.setp() is Matplotlib's way to set multiple properties
        # on a group of objects at once. Think of it as a bulk setter.


def _save_to_buffer(fig):
    """
    Saves the Matplotlib figure to an in-memory PNG buffer.
    Returns the buffer ready to read from the start.

    Parameters:
        fig : Matplotlib Figure object

    Returns:
        BytesIO : buffer containing the PNG image bytes
    """
    buf = BytesIO()
    # BytesIO() creates an empty in-memory file.
    # It behaves exactly like a real file — you can .write() and .read() it —
    # but it lives in RAM, not on disk.

    plt.savefig(
        buf,
        format='png',
        dpi=130,
        # dpi = dots per inch — controls image resolution.
        # 130 dpi: sharp on normal screens, reasonable file size (~50-150 KB).
        # 72 dpi = blurry, 300 dpi = print-quality but huge file.
        bbox_inches='tight',
        # 'tight' crops the image to the actual chart content.
        # Without it, Matplotlib adds large white borders around everything.
        facecolor=STYLE['bg'],
        # Sets the outer figure background (outside the axes area).
        edgecolor='none'
        # No border around the entire figure.
    )

    plt.close(fig)
    # CRITICAL: always close the figure after saving.
    # Matplotlib keeps figures in memory until explicitly closed.
    # On a server handling many requests, not closing = memory leak.
    # After ~100 unclosed figures, your server runs out of RAM.

    buf.seek(0)
    # After writing, the buffer's internal cursor is at the END.
    # seek(0) rewinds it to the BEGINNING so Flask can read from it.
    # Think of it like rewinding a tape before playing it.

    return buf


# ============================================================
#  CHART FUNCTIONS — one per chart type
# ============================================================

def _draw_bar(ax, df, x_col, y_col):
    """
    Draws a vertical bar chart.
    Best for: comparing values across categories
    Example: "Sales by Region", "Users by Country"

    Parameters:
        ax    : Matplotlib Axes
        df    : pandas DataFrame
        x_col : column name for the X axis (categories)
        y_col : column name for the Y axis (values to measure)
    """
    # Aggregate: group by x_col, sum the y_col values
    # This handles CSVs where the same category appears on multiple rows.
    # e.g. if Region=North appears 5 times, we sum all 5 Sales values.
    plot_df = df.groupby(x_col)[y_col].sum().reset_index()
    # .groupby(x_col) → groups rows by unique values in x_col
    # [y_col].sum()   → adds up y values for each group
    # .reset_index()  → converts the grouped result back to a flat DataFrame

    # Sort from highest to lowest — makes comparisons easier to read
    plot_df = plot_df.sort_values(y_col, ascending=False)

    # Limit to top 20 bars — a chart with 200 bars is unreadable
    plot_df = plot_df.head(20)

    bars = ax.bar(
        plot_df[x_col],      # X positions (category labels)
        plot_df[y_col],      # bar heights (values)
        color=PALETTE['bar'],
        width=0.6,           # bar width (0–1, fraction of available space)
        zorder=3             # draw bars ON TOP of gridlines
    )

    # Add value labels on top of each bar
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,  # centre of the bar
                height * 1.01,                        # just above the top
                f'{height:,.0f}',                     # formatted number
                ha='center', va='bottom',
                fontsize=9, color=STYLE['text']
            )

    ax.set_xlabel(x_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    ax.set_ylabel(y_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    _format_y_axis(ax, plot_df[y_col])
    _rotate_x_labels(ax, plot_df[x_col].tolist())
    _style_axes(ax, title=f'{y_col} by {x_col}')


def _draw_line(ax, df, x_col, y_col):
    """
    Draws a line chart.
    Best for: trends over time or any ordered sequence
    Example: "Monthly revenue", "Temperature over time"

    If x_col is numeric, we plot all numeric columns as separate lines.
    If x_col is text (e.g. month names), we aggregate like the bar chart.
    """
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    # select_dtypes(include=['number']) gets only int64 and float64 columns

    if x_col in numeric_cols:
        # x is numeric → sort by x, plot multiple y columns as separate lines
        plot_df = df.sort_values(x_col)
        cols_to_plot = [c for c in numeric_cols if c != x_col][:4]
        # Plot up to 4 lines — more becomes unreadable
        # List comprehension: [c for c in list if condition]
        # "keep column c if it's not the x column"

        for i, col in enumerate(cols_to_plot):
            ax.plot(
                plot_df[x_col],
                plot_df[col],
                color=PALETTE['line'][i % len(PALETTE['line'])],
                # i % len(...) wraps around if more lines than colours
                marker='o',    # small circle dot at each data point
                markersize=4,
                linewidth=2,
                label=col      # for the legend
            )
        if len(cols_to_plot) > 1:
            ax.legend(fontsize=9)

    else:
        # x is categorical → aggregate and sort
        plot_df = df.groupby(x_col)[y_col].mean().reset_index()
        # .mean() instead of .sum() — averages make more sense for line charts
        ax.plot(
            range(len(plot_df)),   # numeric positions for even spacing
            plot_df[y_col],
            color=PALETTE['line'][0],
            marker='o', markersize=5, linewidth=2.5
        )
        ax.set_xticks(range(len(plot_df)))
        ax.set_xticklabels(plot_df[x_col].tolist())
        # set_xticks sets WHERE the labels go (positions)
        # set_xticklabels sets WHAT the labels say (text)

    ax.set_xlabel(x_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    ax.set_ylabel(y_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    _format_y_axis(ax, df[y_col])
    _rotate_x_labels(ax, df[x_col].astype(str).tolist())
    _style_axes(ax, title=f'{y_col} over {x_col}')


def _draw_scatter(ax, df, x_col, y_col):
    """
    Draws a scatter plot.
    Best for: relationship/correlation between two numeric variables
    Example: "Price vs Units Sold", "Age vs Income"

    Each dot = one row of the CSV.
    Clustering pattern reveals the relationship.
    """
    # Drop rows where either column has missing values
    clean = df[[x_col, y_col]].dropna()
    # .dropna() removes rows with NaN in any of the selected columns.
    # A scatter plot can't place a dot with no coordinates.

    ax.scatter(
        clean[x_col],
        clean[y_col],
        color=PALETTE['scatter'],
        alpha=0.55,    # transparency — overlapping dots still visible
        s=60,          # dot size in points² (default is 36)
        edgecolors='white',  # white border makes dots more distinct
        linewidths=0.5,
        zorder=3
    )

    # Add a trend line (linear regression line)
    # This shows the general direction of the relationship.
    if len(clean) >= 3:
        z = np.polyfit(clean[x_col], clean[y_col], 1)
        # np.polyfit(x, y, 1) fits a degree-1 polynomial (straight line)
        # to the data using least-squares method.
        # Returns [slope, intercept] as array z.

        p = np.poly1d(z)
        # np.poly1d(z) creates a polynomial function from the coefficients.
        # p(x) = z[0]*x + z[1]  — you can call it like a normal function.

        x_range = np.linspace(clean[x_col].min(), clean[x_col].max(), 100)
        # np.linspace(start, stop, n) → 100 evenly spaced x values
        # We use these to draw a smooth line across the full x range.

        ax.plot(x_range, p(x_range),
                color='#333333', linewidth=1.2,
                linestyle='--', alpha=0.6, label='trend')
        # linestyle='--' draws a dashed line
        # alpha=0.6 makes it semi-transparent so it doesn't dominate

        ax.legend(fontsize=9)

    # Annotate with correlation coefficient
    if len(clean) >= 2:
        corr = clean[x_col].corr(clean[y_col])
        # .corr() calculates Pearson correlation coefficient:
        #   +1.0 = perfect positive relationship
        #    0.0 = no relationship
        #   -1.0 = perfect negative relationship
        ax.annotate(
            f'r = {corr:.2f}',    # 2 decimal places
            xy=(0.05, 0.93),      # position: 5% from left, 93% from bottom
            xycoords='axes fraction',  # coordinates relative to axes (0–1)
            fontsize=10, color=STYLE['text'],
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor=STYLE['spine'], alpha=0.8)
            # bbox draws a rounded rectangle behind the text
        )

    ax.set_xlabel(x_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    ax.set_ylabel(y_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    _style_axes(ax, title=f'{x_col} vs {y_col}')


def _draw_histogram(ax, df, x_col):
    """
    Draws a histogram.
    Best for: distribution of a single numeric variable
    Example: "How are prices distributed?", "Age distribution"

    A histogram groups values into bins (ranges) and counts
    how many values fall into each bin.
    """
    data = df[x_col].dropna()
    # dropna() removes NaN values — can't bin empty values

    # Auto-determine number of bins using Sturges' rule:
    # bins = 1 + log2(n) — a classic formula for histogram bins
    import math
    n_bins = max(10, min(50, int(1 + math.log2(len(data)))))
    # max(10, ...) → always at least 10 bins (avoids empty-looking charts)
    # min(50, ...) → never more than 50 bins (avoids over-fragmentation)

    n, bins, patches = ax.hist(
        data,
        bins=n_bins,
        color=PALETTE['histogram'],
        edgecolor='white',   # thin white line between bins — easier to read
        linewidth=0.6,
        zorder=3
    )
    # ax.hist() returns three things:
    #   n       = array of counts per bin
    #   bins    = array of bin edge positions
    #   patches = list of Rectangle objects (the actual bars)

    # Draw a vertical line at the mean
    mean_val = data.mean()
    ax.axvline(
        mean_val,
        color='#E24B4A', linewidth=1.8,
        linestyle='--', alpha=0.85,
        label=f'mean = {mean_val:,.1f}'
    )
    # axvline draws a full vertical line across the chart at x=mean_val

    ax.legend(fontsize=9)
    ax.set_xlabel(x_col, fontsize=STYLE['label_size'], color=STYLE['text'])
    ax.set_ylabel('Count', fontsize=STYLE['label_size'], color=STYLE['text'])
    _style_axes(ax, title=f'Distribution of {x_col}')


def _draw_pie(ax, df, x_col, y_col):
    """
    Draws a pie chart.
    Best for: parts of a whole with 8 or fewer categories
    Example: "Market share by region", "Sales split by product"

    Pie charts are controversial in data visualisation — they're
    harder to read than bar charts for precise comparisons.
    We include them because they look engaging in UIs and Gemini
    will only suggest them for genuinely proportional questions.
    """
    # Aggregate: sum y values for each category in x
    pie_data = df.groupby(x_col)[y_col].sum()
    # Result: a Series where index = x_col categories, values = sums

    # Limit to top 8 slices (pie charts with 15 slices are unreadable)
    pie_data = pie_data.nlargest(8)
    # .nlargest(n) keeps the n largest values — equivalent to
    # .sort_values(ascending=False).head(n) but more readable.

    # Filter out zero or negative values (can't draw zero-sized slices)
    pie_data = pie_data[pie_data > 0]

    if pie_data.empty:
        # Nothing to plot — draw a plain text message instead
        ax.text(0.5, 0.5, 'No data to display',
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color=STYLE['text'])
        ax.set_axis_off()
        return

    wedges, texts, autotexts = ax.pie(
        pie_data.values,          # the sizes of each slice
        labels=pie_data.index,    # the category labels
        colors=PALETTE['pie'],
        autopct='%1.1f%%',
        # autopct draws the percentage on each slice.
        # '%1.1f%%' format: 1 decimal place, e.g. "23.5%"
        startangle=90,
        # Rotates the chart so the first slice starts at the top (12 o'clock)
        # instead of the right (3 o'clock — Matplotlib's default)
        pctdistance=0.80,
        # How far from the centre to place the % labels (0=centre, 1=edge)
        wedgeprops=dict(edgecolor='white', linewidth=1.5)
        # white borders between slices — cleaner look
    )

    # Style the percentage text inside slices
    for autotext in autotexts:
        autotext.set_fontsize(9)
        autotext.set_color('white')
        autotext.set_fontweight('bold')

    _style_axes(ax, title=f'{y_col} by {x_col}')
    ax.set_facecolor(STYLE['bg'])


# ============================================================
#  MAIN PUBLIC FUNCTION
#  This is the only function app.py calls directly.
# ============================================================

def generate_chart(df, chart_type, x_col=None, y_col=None):
    """
    The single entry point for chart generation.
    Called by the /chart route in app.py.

    Selects the right chart function based on chart_type,
    draws it, saves to a BytesIO buffer, and returns the buffer.

    Parameters:
        df         : pandas DataFrame (the uploaded CSV data)
        chart_type : str — 'bar', 'line', 'scatter', 'histogram', 'pie'
        x_col      : str — column name for X axis (from Gemini suggestion)
        y_col      : str — column name for Y axis (from Gemini suggestion)

    Returns:
        BytesIO : PNG image bytes ready to send as HTTP response
        None    : if the data isn't suitable for any chart
    """

    # ---- Validate the requested column names ------------------
    # Gemini might suggest column names that don't exist if its
    # JSON parsing goes wrong. We check before plotting.
    all_cols     = df.columns.tolist()
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    text_cols    = df.select_dtypes(include=['object', 'string']).columns.tolist()

    if not numeric_cols:
        return None
    # Can't draw any chart without at least one numeric column.

    # ---- Smart column fallback --------------------------------
    # If Gemini's suggested columns don't exist, pick sensible defaults.
    if x_col not in all_cols:
        # Use first text column, or first numeric if no text columns
        x_col = text_cols[0] if text_cols else numeric_cols[0]

    if y_col not in numeric_cols:
        # y must always be numeric (it's the measured value)
        # Pick whichever numeric column isn't being used as x
        y_col = next(
            (c for c in numeric_cols if c != x_col),
            numeric_cols[0]
        )
        # next() returns the first item from the generator expression
        # that satisfies the condition.
        # If ALL numeric cols are the same as x_col, fall back to numeric_cols[0].

    # ---- Create the figure ------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5.5))
    # plt.subplots() creates a Figure and one Axes object.
    # Figure  = the entire image canvas
    # Axes    = the actual chart area inside the figure
    # figsize = (width, height) in INCHES — at 130 dpi → ~1300×715 pixels
    # One Axes is enough — we're drawing one chart per image.

    fig.patch.set_facecolor(STYLE['bg'])
    # Sets the figure background colour (outside the axes area).

    # ---- Route to the right drawing function ------------------
    if chart_type == 'bar':
        _draw_bar(ax, df, x_col, y_col)

    elif chart_type == 'line':
        _draw_line(ax, df, x_col, y_col)

    elif chart_type == 'scatter':
        _draw_scatter(ax, df, x_col, y_col)

    elif chart_type == 'histogram':
        _draw_histogram(ax, df, x_col)

    elif chart_type == 'pie':
        _draw_pie(ax, df, x_col, y_col)

    else:
        # Unknown chart type — close the empty figure and return None
        plt.close(fig)
        return None

    plt.tight_layout(pad=1.5)
    # tight_layout() auto-adjusts spacing so nothing overlaps or
    # gets clipped (axis labels, title, tick labels).
    # pad=1.5 adds 1.5 "inches" of padding around the edges.

    return _save_to_buffer(fig)
    # Saves to BytesIO, closes the figure, rewinds buffer, returns it.


# ============================================================
#  SELF-TEST — run with: python chart.py
#  Generates all 5 chart types and saves them as PNG files
#  in the current directory so you can inspect them visually.
# ============================================================

if __name__ == '__main__':
    import os

    # Build a realistic test DataFrame
    test_data = {
        'Region'   : ['North','South','East','West','North','South','East','West'],
        'Month'    : ['Jan','Jan','Jan','Jan','Feb','Feb','Feb','Feb'],
        'Sales'    : [7200, 4800, 6100, 3900, 8100, 5200, 5800, 4200],
        'Units'    : [112,  72,   95,   61,   130,  88,   92,   70],
        'Price'    : [64.3, 66.7, 64.2, 63.9, 62.3, 59.1, 63.0, 60.0],
    }
    df = pd.DataFrame(test_data)

    output_dir = '/tmp/chart_test'
    os.makedirs(output_dir, exist_ok=True)

    DIVIDER = '=' * 55
    print(DIVIDER)
    print("CHART.PY SELF-TEST — generating 5 chart types")
    print(DIVIDER)

    tests = [
        ('bar',       'Region', 'Sales'),
        ('line',      'Month',  'Sales'),
        ('scatter',   'Units',  'Sales'),
        ('histogram', 'Sales',  'Sales'),
        ('pie',       'Region', 'Sales'),
    ]

    all_pass = True
    for chart_type, x, y in tests:
        buf = generate_chart(df, chart_type, x_col=x, y_col=y)
        if buf:
            path = f'{output_dir}/{chart_type}.png'
            with open(path, 'wb') as f:
                f.write(buf.read())
            size_kb = os.path.getsize(path) // 1024
            print(f'  ✓  {chart_type:<12} → {path}  ({size_kb} KB)')
        else:
            print(f'  ✗  {chart_type:<12} → returned None (unexpected)')
            all_pass = False

    # Test fallback: bad column names
    buf = generate_chart(df, 'bar', x_col='NONEXISTENT', y_col='ALSO_BAD')
    if buf:
        print(f'  ✓  bad columns  → fallback worked (chart still generated)')
    else:
        print(f'  ✗  bad columns  → returned None unexpectedly')
        all_pass = False

    # Test: no numeric columns
    df_text = pd.DataFrame({'A': ['x','y'], 'B': ['p','q']})
    buf = generate_chart(df_text, 'bar', x_col='A', y_col='B')
    if buf is None:
        print(f'  ✓  no numeric   → correctly returned None')
    else:
        print(f'  ✗  no numeric   → should have returned None')
        all_pass = False

    print()
    print('All tests passed ✓' if all_pass else 'SOME TESTS FAILED ✗')
    print(f'\nOpen the PNGs in {output_dir}/ to inspect visually.')
