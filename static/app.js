// ============================================================
//  static/app.js  —  All frontend interactivity
//  Phase 5: connects the UI to every Flask route we built.
//
//  This file is loaded by index.html AFTER the body renders,
//  so every DOM element is guaranteed to exist when this runs.
//
//  File structure:
//    1. STATE         — one object that tracks everything
//    2. DOM HELPERS   — shortcuts to grab elements by id
//    3. UPLOAD        — file selection, drag-drop, POST /upload
//    4. PREVIEW       — fetch GET /preview → build HTML table
//    5. QUESTIONS     — textarea logic, example chips, keyboard submit
//    6. ASK           — POST /ask → render exchange card
//    7. CHART         — POST /chart → fetch PNG → display in card
//    8. RENDER        — format Gemini's Markdown-ish text into HTML
//    9. UTILITIES     — showStatus, reveal/hide panels, reset
//   10. INIT          — runs on page load
// ============================================================


// ============================================================
//  1. STATE
//  A single plain object that acts as our "database in memory".
//  All functions read from and write to this object.
//  This avoids scattered global variables — everything is in one place.
// ============================================================

const STATE = {
  fileUploaded   : false,   // true after a successful /upload response
  isAsking       : false,   // true while waiting for /ask response
  exchangeCount  : 0,       // number of Q&A rounds completed
  columnNames    : [],      // all column names from the uploaded CSV
  numericColumns : [],      // only numeric columns (for smart example questions)
  textColumns    : [],      // only text/category columns
};


// ============================================================
//  2. DOM HELPERS
//  document.getElementById() is verbose — we alias it to $.
//  This is a common pattern in vanilla JS projects.
//  (Not jQuery — just our own shorthand.)
// ============================================================

const $ = id => document.getElementById(id);
// Arrow function: const $ = (id) => document.getElementById(id)
// Now $('uploadStatus') is cleaner than document.getElementById('uploadStatus')


// ============================================================
//  3. UPLOAD  —  file selection, drag-drop, POST /upload
// ============================================================

// --- 3a. File input change event ----------------------------
// Triggered when the user picks a file via the OS file picker
$('fileInput').addEventListener('change', function () {
  // 'this' inside a regular function refers to the element that fired the event.
  // Arrow functions would lose 'this' — that's why we use 'function' here.
  if (this.files.length > 0) {
    uploadFile(this.files[0]);
    // Pass the first selected file to uploadFile().
    // files is a FileList object (array-like). [0] gets the first item.
  }
});


// --- 3b. Drag and drop events --------------------------------
// Three events needed for drag-and-drop:
//   dragover  — fires while a dragged file hovers over the zone
//   dragleave — fires when the drag leaves the zone
//   drop      — fires when the user releases / drops the file

const uploadZone = $('uploadZone');

uploadZone.addEventListener('dragover', function (e) {
  e.preventDefault();
  // preventDefault() stops the browser's default behaviour.
  // By default, browsers open dropped files as a new page.
  // Calling preventDefault() lets us handle it ourselves.
  this.classList.add('drag-over');
  // Adds the .drag-over CSS class → teal border appears (defined in CSS)
});

uploadZone.addEventListener('dragleave', function () {
  this.classList.remove('drag-over');
  // Removes the teal border when the drag leaves
});

uploadZone.addEventListener('drop', function (e) {
  e.preventDefault();
  this.classList.remove('drag-over');

  const file = e.dataTransfer.files[0];
  // e.dataTransfer.files contains the dropped files.
  // [0] gets the first one — we only handle one file at a time.

  if (file) uploadFile(file);
});


// --- 3c. The actual upload function -------------------------
async function uploadFile(file) {
  // 'async' makes this function return a Promise and allows
  // 'await' inside it — so we can write async code that reads
  // like synchronous code, without callback pyramids.

  // Quick client-side validation before even hitting the server
  if (!file.name.endsWith('.csv')) {
    showStatus('uploadStatus', 'error', '✗ Only .csv files are accepted.');
    return;
    // 'return' exits the function early — nothing below this runs.
  }

  if (file.size > 5 * 1024 * 1024) {
    // file.size is in bytes. 5 MB = 5 * 1024 * 1024 bytes.
    showStatus('uploadStatus', 'error', '✗ File is larger than 5 MB.');
    return;
  }

  showStatus('uploadStatus', 'loading', '⟳  Uploading and reading your CSV…');

  // FormData is the correct way to send file uploads via fetch().
  // It encodes the file as multipart/form-data — the same encoding
  // a normal HTML <form enctype="multipart/form-data"> would use.
  // The server reads it with request.files['file'] in Flask.
  const formData = new FormData();
  formData.append('file', file);
  // 'file' must match the key Flask looks for: request.files['file']

  try {
    const response = await fetch('/upload', {
      method : 'POST',
      body   : formData,
      // NOTE: do NOT set 'Content-Type' header manually.
      // When body is FormData, the browser sets it automatically
      // to 'multipart/form-data; boundary=...' with the correct boundary.
      // Setting it manually breaks the boundary and Flask can't parse it.
    });

    const data = await response.json();
    // response.json() parses the JSON text in the response body
    // into a JavaScript object. It also returns a Promise, so we await it.

    if (!response.ok || data.error) {
      // response.ok is true for 2xx status codes (200–299).
      // If false, something went wrong on the server.
      showStatus('uploadStatus', 'error', '✗ ' + (data.error || 'Upload failed.'));
      return;
    }

    // ---- Success — update STATE ----
    STATE.fileUploaded = true;
    STATE.columnNames  = data.columns.map(c => c.name);
    // data.columns is [{name: 'Region', type: 'object'}, ...]
    // .map(c => c.name) extracts just the names → ['Region', 'Month', ...]

    STATE.numericColumns = data.columns
      .filter(c => c.type.includes('int') || c.type.includes('float'))
      .map(c => c.name);
    // .filter() keeps only items where the condition is true.
    // c.type.includes('int') catches 'int64', 'int32', etc.

    STATE.textColumns = data.columns
      .filter(c => c.type === 'object' || c.type === 'str')
      .map(c => c.name);

    // ---- Update the UI ----
    showStatus('uploadStatus', 'success', '✓ ' + data.filename + ' uploaded successfully!');
    showFileInfo(data);
    loadPreview();
    revealPanels();
    generateExampleQuestions();

  } catch (err) {
    // catch() handles network errors (no internet, server down, etc.)
    // These are different from HTTP errors (4xx, 5xx) which still return responses.
    showStatus('uploadStatus', 'error', '✗ Network error — is the server running?');
    console.error('Upload error:', err);
    // console.error() prints to the browser's DevTools console (F12 → Console tab)
    // Useful for debugging — doesn't show anything to the user.
  }
}


// --- 3d. Show file metadata after upload --------------------
function showFileInfo(data) {
  $('infoFilename').textContent = data.filename;
  $('infoRows').textContent     = data.rows.toLocaleString();
  // .toLocaleString() formats numbers with commas: 15000 → "15,000"

  $('infoCols').textContent     = data.cols;

  // Build column chips
  const chipRow = $('infoColumns');
  chipRow.innerHTML = '';
  // Clear any previous chips (if user uploads a second file)

  data.columns.forEach(col => {
    const chip = document.createElement('span');
    chip.className = 'chip';

    // Determine chip colour by data type
    if (col.type.includes('int') || col.type.includes('float')) {
      chip.classList.add('numeric');   // teal chip
    } else if (col.type === 'object' || col.type === 'str') {
      chip.classList.add('text');      // purple chip
    }

    chip.textContent = col.name;
    chipRow.appendChild(chip);
    // document.createElement() creates a new DOM element.
    // appendChild() adds it as the last child of chipRow.
  });

  $('fileInfo').classList.add('show');
  // Adding the 'show' class changes display:none → display:block (defined in CSS)
}


// ============================================================
//  4. PREVIEW  —  fetch GET /preview, build HTML table
// ============================================================

async function loadPreview() {
  try {
    const response = await fetch('/preview');
    // GET request — no method/body needed (fetch defaults to GET)

    const data = await response.json();
    if (!response.ok) return;
    // If something went wrong, silently skip the preview.
    // The user already got a success message from the upload —
    // we don't want a second error to confuse them.

    buildPreviewTable(data.columns, data.rows, data.total_rows);
  } catch (err) {
    console.error('Preview error:', err);
  }
}

function buildPreviewTable(columns, rows, totalRows) {
  // ---- Build the header row ----
  const thead = $('previewHead');
  thead.innerHTML = '';
  const headerRow = document.createElement('tr');

  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  // ---- Build the data rows ----
  const tbody = $('previewBody');
  tbody.innerHTML = '';

  rows.forEach(row => {
    const tr = document.createElement('tr');

    columns.forEach(col => {
      const td = document.createElement('td');
      const value = row[col];

      // Format the value for display
      if (value === null || value === undefined) {
        td.textContent = '—';
        td.style.color = 'var(--text-3)';
        // Show dash for missing values, greyed out
      } else if (typeof value === 'number') {
        td.textContent = value.toLocaleString();
        // Numbers get comma formatting
      } else {
        td.textContent = String(value);
      }

      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });

  // ---- Footer note ----
  const shown = Math.min(10, totalRows);
  $('previewMeta').textContent =
    `Showing ${shown} of ${totalRows.toLocaleString()} rows`;
}


// ============================================================
//  5. QUESTIONS  —  textarea logic, example chips, keyboard
// ============================================================

// Character counter — updates as the user types
$('questionInput').addEventListener('input', function () {
  const len     = this.value.length;
  const counter = $('charCount');
  counter.textContent = `${len} / 500`;

  // Turn yellow when approaching the limit
  if (len > 420) {
    counter.classList.add('warn');
  } else {
    counter.classList.remove('warn');
  }
});

// Submit on Ctrl+Enter or Cmd+Enter (Mac)
$('questionInput').addEventListener('keydown', function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    // e.ctrlKey = true if Ctrl is held
    // e.metaKey = true if Cmd is held (Mac)
    // e.key === 'Enter' = the Enter key was pressed
    e.preventDefault();
    askQuestion();
  }
});

function generateExampleQuestions() {
  // Builds smart example question chips based on actual column names.
  // If the CSV has a 'Sales' column and a 'Region' column,
  // we generate "What is the total Sales by Region?" automatically.

  const container = $('exampleQuestions');
  // Keep the "Try:" label, remove old chips
  const label = container.querySelector('span');
  container.innerHTML = '';
  container.appendChild(label);

  const examples = [];

  // Pattern 1: numeric column total
  if (STATE.numericColumns.length > 0) {
    examples.push(`What is the total ${STATE.numericColumns[0]}?`);
  }

  // Pattern 2: compare numeric by text category
  if (STATE.numericColumns.length > 0 && STATE.textColumns.length > 0) {
    examples.push(
      `Which ${STATE.textColumns[0]} has the highest ${STATE.numericColumns[0]}?`
    );
  }

  // Pattern 3: trend over time (if there's a 'date' or 'month' column)
  const timeCol = STATE.columnNames.find(c =>
    /month|date|year|week|time|day/i.test(c)
    // Regular expression test: does the column name contain any of these words?
    // /pattern/i — the 'i' flag makes it case-insensitive
  );
  if (timeCol && STATE.numericColumns.length > 0) {
    examples.push(`Show the trend of ${STATE.numericColumns[0]} over ${timeCol}.`);
  }

  // Pattern 4: distribution
  if (STATE.numericColumns.length > 0) {
    const col = STATE.numericColumns[STATE.numericColumns.length - 1];
    // Pick the LAST numeric column for variety
    examples.push(`What is the distribution of ${col}?`);
  }

  // Pattern 5: correlation
  if (STATE.numericColumns.length >= 2) {
    examples.push(
      `Is there a correlation between ${STATE.numericColumns[0]} and ${STATE.numericColumns[1]}?`
    );
  }

  // Limit to 4 chips — more feels cluttered
  examples.slice(0, 4).forEach(text => {
    const btn = document.createElement('button');
    btn.className   = 'example-q';
    btn.textContent = text;
    btn.onclick     = () => {
      $('questionInput').value = text;
      // Fill the textarea with the example text
      $('questionInput').focus();
      // Move keyboard focus to the textarea so user can edit/submit
      $('charCount').textContent = `${text.length} / 500`;
    };
    container.appendChild(btn);
  });
}


// ============================================================
//  6. ASK  —  POST /ask, then POST /chart
// ============================================================

async function askQuestion() {
  const question = $('questionInput').value.trim();
  // .trim() removes leading/trailing whitespace
  // (prevent submitting a question that's just spaces)

  if (!question) {
    $('questionInput').focus();
    return;
  }

  if (STATE.isAsking) return;
  // Prevent double-submission if the user clicks the button
  // multiple times while waiting. isAsking acts as a lock.

  // ---- Lock the UI ----
  STATE.isAsking = true;
  $('askBtn').disabled = true;
  // disabled attribute prevents clicking AND changes button appearance (CSS)

  // ---- Reveal results panel if first question ----
  $('panel-results').classList.remove('hidden');

  // ---- Insert a loading card at the TOP of the exchange list ----
  const loadingCard = createLoadingCard(question);
  $('exchangeList').prepend(loadingCard);
  // prepend() inserts as the FIRST child (top of list)
  // append() would add at the bottom — we want newest on top

  // Scroll so the loading card is visible
  loadingCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    // ---- POST /ask ----
    const askResponse = await fetch('/ask', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 'Content-Type: application/json' tells Flask to parse
      // the body with request.get_json() instead of request.form
      body   : JSON.stringify({ question: question })
      // JSON.stringify() converts the JS object to a JSON string:
      //   { question: "..." }  →  '{"question":"..."}'
    });

    const data = await askResponse.json();

    if (!askResponse.ok || data.error) {
      replaceLoadingWithError(loadingCard, data.error || 'Something went wrong.');
      return;
    }

    // ---- Replace loading card with the real answer card ----
    const exchangeCard = createExchangeCard(data);
    loadingCard.replaceWith(exchangeCard);
    // replaceWith() swaps the loading card for the answer card in the DOM.
    // The old card is removed, the new one takes its exact place.

    // ---- Fetch and display the chart ----
    if (data.chart_type && data.chart_type !== 'none') {
      const chartWrap = exchangeCard.querySelector('.chart-wrap');
      // .querySelector() finds the FIRST element matching the CSS selector
      // within exchangeCard — not the whole document.
      if (chartWrap) {
        await loadChart(chartWrap, data.chart_type, data.chart_cols);
      }
    }

    // ---- Update state ----
    STATE.exchangeCount++;
    updateExchangeCount();

    // ---- Clear the textarea for the next question ----
    $('questionInput').value = '';
    $('charCount').textContent = '0 / 500';

  } catch (err) {
    replaceLoadingWithError(loadingCard, 'Network error — is the server running?');
    console.error('Ask error:', err);
  } finally {
    // 'finally' runs whether the try block succeeded OR threw an error.
    // We always want to unlock the UI, so put it here.
    STATE.isAsking   = false;
    $('askBtn').disabled = false;
  }
}


// ============================================================
//  7. CHART  —  POST /chart, receive PNG blob, display
// ============================================================

async function loadChart(containerEl, chartType, chartCols) {
  // Show a small loading indicator inside the chart area
  containerEl.innerHTML =
    '<div class="chart-label">Generating chart…</div>' +
    '<div class="spinner-wrap"><div class="spinner"></div><span>Drawing visualisation</span></div>';

  // BUG FIX: chart_cols can have {x: null, y: null} when Groq hit the
  // fast-path for a single numeric column (e.g. "distribution of MSRP").
  // In that case, the server's generate_chart() fallback handles it fine,
  // BUT we need to at least send a valid x_col for histogram questions.
  // Strategy: if y is null but we know the column from the question context,
  // pass null — generate_chart()'s own fallback will pick the right column.
  // The real fix is: don't send null when we have STATE.numericColumns to
  // fall back on.
  let x_col = chartCols ? chartCols.x : null;
  let y_col = chartCols ? chartCols.y : null;

  // If both cols are null (fast-path returned {x:null,y:null}),
  // use the first available numeric column for y so the server
  // doesn't have to guess with zero hints.
  if (!y_col && STATE.numericColumns.length > 0) {
    y_col = STATE.numericColumns[0];
    // For histograms x and y are the same column — that's fine,
    // generate_chart() uses x_col for histogram regardless of y.
  }
  if (!x_col && STATE.numericColumns.length > 0) {
    x_col = y_col || STATE.numericColumns[0];
  }

  try {
    const response = await fetch('/chart', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({
        chart_type: chartType,
        x_col     : x_col,
        y_col     : y_col,
      })
    });

    if (response.status === 204) {
      // 204 = No Content — chart_type was 'none', no chart needed
      containerEl.innerHTML = '';
      return;
    }

    if (!response.ok) {
      containerEl.innerHTML = '<p style="font-size:12px;color:var(--text-3);padding:8px 0;">Chart unavailable for this question.</p>';
      return;
    }

    // ---- Read the raw PNG bytes as a Blob ----
    const blob = await response.blob();
    // response.blob() reads the entire response body as a Blob object.
    // A Blob is a reference to raw binary data in memory.
    // It doesn't know it's a PNG — it's just bytes.

    const imageUrl = URL.createObjectURL(blob);
    // URL.createObjectURL() creates a temporary browser-local URL
    // that points to the Blob in memory.
    // The URL looks like: blob:http://127.0.0.1:5000/a1b2c3d4-...
    // Setting an <img src> to this URL displays the image.
    // The URL is valid only for this browser tab/session.

    containerEl.innerHTML =
      '<div class="chart-label">Auto-generated chart · ' + chartType + '</div>' +
      '<img class="chart-img" alt="Data chart" />';

    const img = containerEl.querySelector('img');
    img.src = imageUrl;
    // Setting img.src triggers the browser to display the blob image.

    // Clean up the blob URL when the image is done loading.
    // This frees the memory — otherwise the blob stays in RAM forever.
    img.onload = () => URL.revokeObjectURL(imageUrl);
    // URL.revokeObjectURL() releases the memory reference.
    // Once the <img> has the image loaded into its own buffer,
    // we no longer need the blob URL.

  } catch (err) {
    containerEl.innerHTML = '';
    console.error('Chart error:', err);
  }
}


// ============================================================
//  8. RENDER  —  convert Gemini's text into formatted HTML
// ============================================================

function renderInsight(text) {
  // Gemini returns plain text with markdown-ish conventions:
  //   **bold** text → we convert to <strong>
  //   • bullet lines → we wrap in .insight-line divs
  //   "You might also ask:" section → we extract and style separately
  //
  // We don't use a Markdown library to avoid adding a dependency.
  // This simple parser handles the patterns Gemini reliably produces.

  // Split off the "You might also ask:" section if present
  let mainText   = text;
  let followUps  = [];

  const followUpIdx = text.indexOf('You might also ask:');
  if (followUpIdx !== -1) {
    mainText = text.slice(0, followUpIdx).trim();
    const followUpSection = text.slice(followUpIdx + 'You might also ask:'.length).trim();

    // Extract each follow-up question (lines starting with - or •)
    followUps = followUpSection
      .split('\n')
      .map(line => line.replace(/^[-•*]\s*/, '').trim())
      // .replace() removes the leading dash/bullet and whitespace
      .filter(line => line.length > 0);
  }

  // ---- Render main text lines ----
  const lines = mainText.split('\n').filter(line => line.trim() !== '');
  // .split('\n') breaks text into an array of lines
  // .filter() removes blank lines

  let html = '';
  lines.forEach(line => {
    // Apply **bold** formatting to the line
    const formatted = line.replace(
      /\*\*(.+?)\*\*/g,
      '<strong>$1</strong>'
      // Regex: \*\* = literal **, (.+?) = capture group (the text inside),
      // /g = global flag (replace ALL occurrences, not just the first)
      // '$1' in the replacement refers to what was captured in (.+?)
    );

    if (line.startsWith('•') || line.startsWith('-') || line.startsWith('*')) {
      // Bullet point line — wrap in styled flex container
      const bulletText = formatted.replace(/^[•\-*]\s*/, '');
      html += `<div class="insight-line">
                 <span class="bullet">›</span>
                 <span>${bulletText}</span>
               </div>`;
    } else {
      // Regular paragraph line
      html += `<p style="margin-bottom:8px;">${formatted}</p>`;
    }
  });

  // ---- Render follow-up chips ----
  let followUpHtml = '';
  if (followUps.length > 0) {
    followUpHtml = `
      <div class="follow-ups">
        <div class="follow-ups-label">You might also ask</div>
        ${followUps.map(q => {
          // BUG FIX: strip **bold markers** from chip text.
          // The AI wraps column names in **double asterisks** inside
          // follow-up questions, e.g. "What is the **MSRP** distribution?"
          // We must strip them BEFORE inserting into the chip so the user
          // sees clean text, not raw markdown syntax.
          // We also store the clean text in a data attribute so
          // prefillQuestion() reads the clean version, not innerHTML
          // (which would include any leftover HTML entities).
          const cleanQ = q.replace(/\*\*(.+?)\*\*/g, '$1');
          // Same regex as the main text renderer — strips ** but keeps the word inside.
          return `<span class="follow-up-chip" data-question="${escapeHtml(cleanQ)}" onclick="prefillQuestion(this.dataset.question)">${escapeHtml(cleanQ)}</span>`;
          // We now use data-question attribute + escapeHtml() for both display
          // and the value passed to prefillQuestion().
          // this.textContent would still work but could pick up whitespace
          // from template literal indentation — data attribute is cleaner.
        }).join('')}
      </div>`;
  }

  return html + followUpHtml;
}

function prefillQuestion(text) {
  // Called when user clicks a follow-up chip.
  // Fills the textarea and scrolls to it.
  $('questionInput').value = text.trim();
  $('charCount').textContent = `${text.trim().length} / 500`;
  $('questionInput').focus();
  $('panel-question').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}


// ============================================================
//  9. CARD BUILDERS  —  create DOM elements for exchange cards
// ============================================================

function createLoadingCard(question) {
  const card = document.createElement('div');
  card.className = 'exchange';
  card.innerHTML = `
    <div class="exchange-question">
      <span class="q-label">You</span>
      <span>${escapeHtml(question)}</span>
    </div>
    <div class="exchange-answer">
      <div class="spinner-wrap">
        <div class="spinner"></div>
        <span>Analysing your data with AI…</span>
      </div>
    </div>`;
  return card;
}

function createExchangeCard(data) {
  // data = { insight, chart_type, chart_cols, question }
  const card = document.createElement('div');
  card.className = 'exchange';

  const insightHtml = renderInsight(data.insight);
  // renderInsight() converts Gemini's plain text to formatted HTML

  const chartSection = (data.chart_type && data.chart_type !== 'none')
    ? '<div class="chart-wrap"></div>'
    : '';
  // Only add the chart container div if we're going to draw a chart.
  // The loadChart() function will fill this div with the actual image.

  card.innerHTML = `
    <div class="exchange-question">
      <span class="q-label">You</span>
      <span>${escapeHtml(data.question)}</span>
    </div>
    <div class="exchange-answer">
      <div class="insight-text">${insightHtml}</div>
      ${chartSection}
    </div>`;

  return card;
}

function replaceLoadingWithError(loadingCard, message) {
  // Replaces the spinner with an error message.
  // Called if /ask returns an error or a network failure occurs.
  const errorCard = document.createElement('div');
  errorCard.className = 'exchange';
  errorCard.innerHTML = `
    <div class="exchange-answer" style="border-left: 3px solid var(--danger); padding-left: 20px;">
      <p style="color:var(--danger); font-size:13px;">✗ ${escapeHtml(message)}</p>
    </div>`;
  loadingCard.replaceWith(errorCard);
}

function escapeHtml(text) {
  // Converts special HTML characters to safe entities.
  // CRITICAL SECURITY FUNCTION:
  // Without this, if a user typed: <script>alert('XSS')</script>
  // as their question, it would execute as real JavaScript.
  // escapeHtml() turns it into safe text that renders literally.
  //
  // < → &lt;    > → &gt;    & → &amp;
  // " → &quot;  ' → &#039;
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
  // This trick uses the browser's own HTML escaping.
  // createTextNode() treats text as plain text (never HTML).
  // div.innerHTML then serialises that as properly escaped HTML.
}


// ============================================================
//  10. UTILITIES — reveal panels, status messages, reset, count
// ============================================================

function showStatus(elementId, type, message) {
  // type: 'success' | 'error' | 'loading'
  const el = $(elementId);
  el.className = `status-bar show ${type}`;
  // Setting className replaces ALL existing classes.
  // 'status-bar show loading' = base styles + visible + colour variant.
  el.textContent = message;
}

function revealPanels() {
  // Called after a successful upload — reveals the 3 panels below.
  $('panel-preview').classList.remove('hidden');
  $('panel-question').classList.remove('hidden');
  $('questionInput').focus();
  // Focus the textarea so the user can start typing immediately
  // without having to click on it.
}

function updateExchangeCount() {
  const el = $('exchangeCount');
  const n  = STATE.exchangeCount;
  el.textContent = n === 1
    ? '1 exchange'
    : `${n} exchanges`;
}

function clearResults() {
  // Clears all exchange cards from the results panel.
  // Does NOT reset the session or clear the uploaded file —
  // just clears the visual history on the frontend.
  $('exchangeList').innerHTML = '';
  STATE.exchangeCount = 0;
  updateExchangeCount();
  $('panel-results').classList.add('hidden');
}

async function resetApp() {
  // Full reset: clear the server session AND reload the page.
  try {
    await fetch('/reset', { method: 'POST' });
    // Tell the server to clear the session (remove the filepath cookie).
    // Even if this fails, we still reload the page.
  } catch (e) {
    // Silently ignore — reloading will effectively reset anyway.
  }
  window.location.reload();
  // Reload the page — this clears all JS state and returns to
  // the initial upload state. Simpler than resetting every
  // individual STATE field and DOM element manually.
}


// ============================================================
//  11. INIT  —  runs immediately when the script loads
// ============================================================

(function init() {
  // IIFE = Immediately Invoked Function Expression.
  // The function runs as soon as the script loads.
  // We wrap in a function to avoid polluting the global scope.

  // If the server has a session active (e.g. user refreshed the page),
  // try to restore the preview without re-uploading.
  // We do this by calling /preview — if it returns data, a file exists.
  fetch('/preview')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data && data.columns) {
        // Session is active — restore the UI state silently.
        // We don't know the filename/rows from /preview alone,
        // so we just reveal the panels and load the table.
        STATE.fileUploaded = true;
        STATE.columnNames  = data.columns;

        buildPreviewTable(data.columns, data.rows, data.total_rows);
        $('infoFilename').textContent = 'Previously uploaded file';
        $('fileInfo').classList.add('show');
        revealPanels();

        // Also call /summary to get column type info for examples
        return fetch('/summary');
      }
      return null;
    })
    .then(r => r && r.ok ? r.json() : null)
    .then(data => {
      if (data && data.chart_columns) {
        STATE.numericColumns = data.chart_columns.numeric || [];
        STATE.textColumns    = data.chart_columns.text    || [];
        generateExampleQuestions();
      }
    })
    .catch(() => {
      // No session active — normal fresh start. Do nothing.
    });
})();
// The () at the end immediately calls the function.
// Without it, the function would be defined but never run.