# ============================================================
#  pdf_export.py  —  Phase D: PDF report generation
#
#  Uses reportlab to build a multi-page PDF containing:
#    - Title page (chat name, date, user email)
#    - One section per Q&A Message (question, answer, chart)
#
#  Why reportlab?
#    - Pure Python — no system dependencies (wkhtmltopdf etc.)
#    - Full control over every pixel of the PDF
#    - Used by production apps worldwide (invoice generation, reports)
#    - Free and open source (BSD licence)
#
#  Install: pip install reportlab
# ============================================================

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import (
    HexColor, white, black
)
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    HRFlowable, PageBreak, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ---- Colour palette (matches the DataLens UI) ---------------
C_BG      = HexColor('#0E0F11')   # near-black background
C_SURFACE = HexColor('#16181C')   # card background
C_ACCENT  = HexColor('#4ECDC4')   # teal accent
C_TEXT1   = HexColor('#F0F2F5')   # primary text (light)
C_TEXT2   = HexColor('#8B8FA8')   # secondary text (muted)
C_TEXT3   = HexColor('#555870')   # tertiary text (dimmer)
C_BORDER  = HexColor('#2A2D35')   # border colour
C_WHITE   = white


# ============================================================
#  STYLE DEFINITIONS
#  We create custom ParagraphStyles instead of using the
#  default reportlab styles so we can match the app's font.
#  (reportlab uses Helvetica/Times — we pick Helvetica for
#   the closest match; DM Mono/DM Serif aren't built-in.)
# ============================================================

def _make_styles():
    """Returns a dict of all the ParagraphStyles used in the PDF."""
    base = getSampleStyleSheet()

    styles = {}

    styles['title'] = ParagraphStyle(
        'title',
        fontName='Helvetica-Bold',
        fontSize=28,
        textColor=C_TEXT1,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    styles['subtitle'] = ParagraphStyle(
        'subtitle',
        fontName='Helvetica',
        fontSize=12,
        textColor=C_TEXT2,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    styles['meta'] = ParagraphStyle(
        'meta',
        fontName='Helvetica',
        fontSize=9,
        textColor=C_TEXT3,
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    styles['question'] = ParagraphStyle(
        'question',
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=C_ACCENT,
        spaceAfter=6,
        spaceBefore=4,
        leading=15,
    )
    styles['answer'] = ParagraphStyle(
        'answer',
        fontName='Helvetica',
        fontSize=10,
        textColor=C_TEXT2,
        spaceAfter=4,
        leading=15,
    )
    styles['section_num'] = ParagraphStyle(
        'section_num',
        fontName='Helvetica',
        fontSize=8,
        textColor=C_TEXT3,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    return styles


def _clean_text(text):
    """
    Strips markdown-style bold markers (**text**) and bullet
    characters that don't render in reportlab's Paragraph.
    Converts newlines to <br/> for Paragraph line breaks.
    """
    import re
    # Remove **bold** markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # Replace bullet characters with a dash
    text = text.replace('•', '-').replace('›', '-')
    # Replace newlines with <br/> for Paragraph
    text = text.replace('\n', '<br/>')
    # Escape & < > for XML safety (reportlab uses XML internally)
    text = text.replace('&', '&amp;').replace('<br/>', '\x00')  # protect <br/>
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('\x00', '<br/>')  # restore <br/>
    return text


# ============================================================
#  MAIN PUBLIC FUNCTION
# ============================================================

def build_pdf(chat, messages, chart_generator=None):
    """
    Builds a PDF report for a chat session and returns it as
    a BytesIO buffer ready to send as an HTTP response.

    Parameters:
        chat            — Chat model object (has .name, .csv_filename)
        messages        — list of Message model objects
        chart_generator — optional callable(chart_type, x_col, y_col, filepath)
                          → BytesIO PNG buffer or None
                          Pass None to skip charts in the PDF.

    Returns:
        BytesIO : PDF bytes, seeked to position 0
    """

    buf = io.BytesIO()
    # The PDF is written entirely in memory — no temp files needed.

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        # A4 = 210mm × 297mm = 595 × 842 points
        leftMargin  = 25 * mm,
        rightMargin = 25 * mm,
        topMargin   = 20 * mm,
        bottomMargin= 20 * mm,
    )

    styles   = _make_styles()
    story    = []
    # 'story' is reportlab's name for the list of Flowable objects
    # that get laid out onto pages in order.
    # Flowables: Paragraph, Spacer, Image, HRFlowable, Table, etc.

    # ============================================================
    #  TITLE PAGE
    # ============================================================

    story.append(Spacer(1, 30 * mm))
    # Spacer(width, height) — creates vertical whitespace.
    # We add 30mm of space at the top before the title.

    story.append(Paragraph('DataLens', styles['title']))
    story.append(Spacer(1, 4 * mm))

    chat_name = chat.name or chat.csv_filename or 'Analysis Report'
    story.append(Paragraph(chat_name, styles['subtitle']))
    story.append(Spacer(1, 3 * mm))

    now_str = datetime.now(timezone.utc).strftime('%B %d, %Y')
    story.append(Paragraph(f'Generated on {now_str}', styles['meta']))

    if chat.csv_filename:
        story.append(Paragraph(f'Source: {chat.csv_filename}', styles['meta']))

    story.append(Spacer(1, 10 * mm))

    # Horizontal rule
    story.append(HRFlowable(
        width='100%', thickness=1,
        color=C_ACCENT, spaceAfter=6 * mm
    ))
    # HRFlowable draws a horizontal line across the page.

    # Summary stats
    story.append(Paragraph(
        f'{len(messages)} question{"s" if len(messages) != 1 else ""} answered',
        styles['meta']
    ))

    story.append(PageBreak())
    # Force a new page — everything after this starts on page 2.

    # ============================================================
    #  Q&A SECTIONS
    # ============================================================

    for i, msg in enumerate(messages, start=1):
        # ---- Section number ----
        story.append(Paragraph(
            f'Question {i} of {len(messages)}',
            styles['section_num']
        ))

        # ---- Question ----
        story.append(Paragraph(
            _clean_text(msg.question),
            styles['question']
        ))

        # ---- Separator ----
        story.append(HRFlowable(
            width='100%', thickness=0.5,
            color=C_BORDER, spaceAfter=4 * mm
        ))

        # ---- Answer text ----
        answer_text = _clean_text(msg.answer)
        # Split into paragraphs on <br/> groups — makes it more readable
        for chunk in answer_text.split('<br/>'):
            chunk = chunk.strip()
            if chunk:
                story.append(Paragraph(chunk, styles['answer']))

        # ---- Chart image (if available) ----
        if (chart_generator and msg.chart_type
                and msg.chart_type != 'none'):
            try:
                chart_buf = chart_generator(
                    msg.chart_type,
                    msg.chart_x_col,
                    msg.chart_y_col
                )
                if chart_buf:
                    chart_buf.seek(0)
                    img = Image(chart_buf)
                    # Scale the image to fit within the page margins
                    # A4 content width = 210mm - 25mm - 25mm = 160mm = ~454 points
                    max_w = 454
                    max_h = 230  # points (~81mm) — never taller than this

                    # Calculate the actual image dimensions
                    # (reportlab reads them from the PNG header)
                    img_w, img_h = img.imageWidth, img.imageHeight
                    aspect = img_h / img_w if img_w else 1

                    if img_w > max_w:
                        img_w   = max_w
                        img_h   = max_w * aspect

                    if img_h > max_h:
                        img_h   = max_h
                        img_w   = max_h / aspect

                    img.drawWidth  = img_w
                    img.drawHeight = img_h

                    story.append(Spacer(1, 4 * mm))
                    story.append(img)

            except Exception:
                # If chart regeneration fails, skip it silently
                pass

        # ---- Gap between Q&A sections ----
        story.append(Spacer(1, 8 * mm))
        if i < len(messages):
            # Add a soft separator between sections (not after the last one)
            story.append(HRFlowable(
                width='40%', thickness=0.5,
                color=C_BORDER, spaceAfter=4 * mm
            ))

    # ============================================================
    #  BUILD THE PDF
    # ============================================================

    doc.build(story)
    # doc.build(story) lays out all Flowables onto pages,
    # handles page breaks automatically, and writes the PDF
    # to the BytesIO buffer.

    buf.seek(0)
    # Rewind the buffer so Flask can read from the beginning.

    return buf
