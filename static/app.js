// ============================================================
//  static/app.js  —  All frontend interactivity
//  Phase B: auth handled server-side (no changes needed here)
//  Phase C: sidebar chat management (list, load, delete, new)
//  Phase D: export PDF button
// ============================================================


// ============================================================
//  1. STATE
// ============================================================

const STATE = {
  fileUploaded   : false,
  isAsking       : false,
  exchangeCount  : 0,
  columnNames    : [],
  numericColumns : [],
  textColumns    : [],
  activeChatId   : null,   // Phase C: currently active chat id
};


// ============================================================
//  2. DOM HELPERS
// ============================================================

const $ = id => document.getElementById(id);


// ============================================================
//  3. UPLOAD  —  file selection, drag-drop, POST /upload
// ============================================================

$('fileInput').addEventListener('change', function () {
  if (this.files.length > 0) uploadFile(this.files[0]);
});

const uploadZone = $('uploadZone');

uploadZone.addEventListener('dragover', function (e) {
  e.preventDefault();
  this.classList.add('drag-over');
});
uploadZone.addEventListener('dragleave', function () {
  this.classList.remove('drag-over');
});
uploadZone.addEventListener('drop', function (e) {
  e.preventDefault();
  this.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});


async function uploadFile(file) {
  if (!file.name.endsWith('.csv')) {
    showStatus('uploadStatus', 'error', '✗ Only .csv files are accepted.');
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    showStatus('uploadStatus', 'error', '✗ File is larger than 5 MB.');
    return;
  }

  showStatus('uploadStatus', 'loading', '⟳  Uploading and reading your CSV…');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/upload', { method: 'POST', body: formData });
    const data     = await response.json();

    if (!response.ok || data.error) {
      showStatus('uploadStatus', 'error', '✗ ' + (data.error || 'Upload failed.'));
      return;
    }

    // ---- Success ----
    STATE.fileUploaded   = true;
    STATE.activeChatId   = data.chat_id;  // Phase C: store the new chat id
    STATE.columnNames    = data.columns.map(c => c.name);
    STATE.numericColumns = data.columns
      .filter(c => c.type.includes('int') || c.type.includes('float'))
      .map(c => c.name);
    STATE.textColumns = data.columns
      .filter(c => c.type === 'object' || c.type === 'str')
      .map(c => c.name);

    showStatus('uploadStatus', 'success', '✓ ' + data.filename + ' uploaded successfully!');
    showFileInfo(data);
    loadPreview();
    revealPanels();
    generateExampleQuestions();

    // Phase C: refresh the sidebar to show the new chat
    loadChatList();

  } catch (err) {
    showStatus('uploadStatus', 'error', '✗ Network error — is the server running?');
    console.error('Upload error:', err);
  }
}


function showFileInfo(data) {
  $('infoFilename').textContent = data.filename;
  $('infoRows').textContent     = data.rows.toLocaleString();
  $('infoCols').textContent     = data.cols;

  const chipRow = $('infoColumns');
  chipRow.innerHTML = '';
  data.columns.forEach(col => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    if (col.type.includes('int') || col.type.includes('float')) chip.classList.add('numeric');
    else if (col.type === 'object' || col.type === 'str') chip.classList.add('text');
    chip.textContent = col.name;
    chipRow.appendChild(chip);
  });

  $('fileInfo').classList.add('show');
}


// ============================================================
//  4. PREVIEW
// ============================================================

async function loadPreview() {
  try {
    const response = await fetch('/preview');
    const data     = await response.json();
    if (!response.ok) return;
    buildPreviewTable(data.columns, data.rows, data.total_rows);
  } catch (err) {
    console.error('Preview error:', err);
  }
}

function buildPreviewTable(columns, rows, totalRows) {
  const thead = $('previewHead');
  thead.innerHTML = '';
  const headerRow = document.createElement('tr');
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  const tbody = $('previewBody');
  tbody.innerHTML = '';
  rows.forEach(row => {
    const tr = document.createElement('tr');
    columns.forEach(col => {
      const td    = document.createElement('td');
      const value = row[col];
      if (value === null || value === undefined) {
        td.textContent = '—';
        td.style.color = 'var(--text-3)';
      } else if (typeof value === 'number') {
        td.textContent = value.toLocaleString();
      } else {
        td.textContent = String(value);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  const shown = Math.min(10, totalRows);
  $('previewMeta').textContent = `Showing ${shown} of ${totalRows.toLocaleString()} rows`;
}


// ============================================================
//  5. QUESTIONS
// ============================================================

$('questionInput').addEventListener('input', function () {
  const len     = this.value.length;
  const counter = $('charCount');
  counter.textContent = `${len} / 500`;
  if (len > 420) counter.classList.add('warn');
  else counter.classList.remove('warn');
});

$('questionInput').addEventListener('keydown', function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    askQuestion();
  }
});

function generateExampleQuestions() {
  const container = $('exampleQuestions');
  const label     = container.querySelector('span');
  container.innerHTML = '';
  container.appendChild(label);

  const examples = [];

  if (STATE.numericColumns.length > 0)
    examples.push(`What is the total ${STATE.numericColumns[0]}?`);

  if (STATE.numericColumns.length > 0 && STATE.textColumns.length > 0)
    examples.push(`Which ${STATE.textColumns[0]} has the highest ${STATE.numericColumns[0]}?`);

  const timeCol = STATE.columnNames.find(c =>
    /month|date|year|week|time|day/i.test(c)
  );
  if (timeCol && STATE.numericColumns.length > 0)
    examples.push(`Show the trend of ${STATE.numericColumns[0]} over ${timeCol}.`);

  if (STATE.numericColumns.length > 0) {
    const col = STATE.numericColumns[STATE.numericColumns.length - 1];
    examples.push(`What is the distribution of ${col}?`);
  }

  if (STATE.numericColumns.length >= 2)
    examples.push(`Is there a correlation between ${STATE.numericColumns[0]} and ${STATE.numericColumns[1]}?`);

  examples.slice(0, 4).forEach(text => {
    const btn       = document.createElement('button');
    btn.className   = 'example-q';
    btn.textContent = text;
    btn.onclick     = () => {
      $('questionInput').value = text;
      $('questionInput').focus();
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
  if (!question) { $('questionInput').focus(); return; }
  if (STATE.isAsking) return;

  STATE.isAsking   = true;
  $('askBtn').disabled = true;
  $('panel-results').classList.remove('hidden');

  const loadingCard = createLoadingCard(question);
  $('exchangeList').prepend(loadingCard);
  loadingCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const askResponse = await fetch('/ask', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ question })
    });
    const data = await askResponse.json();

    if (!askResponse.ok || data.error) {
      replaceLoadingWithError(loadingCard, data.error || 'Something went wrong.');
      return;
    }

    const exchangeCard = createExchangeCard(data);
    loadingCard.replaceWith(exchangeCard);

    if (data.chart_type && data.chart_type !== 'none') {
      const chartWrap = exchangeCard.querySelector('.chart-wrap');
      if (chartWrap) await loadChart(chartWrap, data.chart_type, data.chart_cols);
    }

    STATE.exchangeCount++;
    updateExchangeCount();

    // Phase D: show export button once there's at least one exchange
    if (STATE.activeChatId) $('btnExport').style.display = '';

    // Phase C: refresh sidebar counts
    loadChatList();

    $('questionInput').value = '';
    $('charCount').textContent = '0 / 500';

  } catch (err) {
    replaceLoadingWithError(loadingCard, 'Network error — is the server running?');
    console.error('Ask error:', err);
  } finally {
    STATE.isAsking   = false;
    $('askBtn').disabled = false;
  }
}


// ============================================================
//  7. CHART  —  POST /chart, receive PNG blob, display
// ============================================================

async function loadChart(containerEl, chartType, chartCols) {
  containerEl.innerHTML =
    '<div class="chart-label">Generating chart…</div>' +
    '<div class="spinner-wrap"><div class="spinner"></div><span>Drawing visualisation</span></div>';

  let x_col = chartCols ? chartCols.x : null;
  let y_col = chartCols ? chartCols.y : null;

  if (!y_col && STATE.numericColumns.length > 0) y_col = STATE.numericColumns[0];
  if (!x_col && STATE.numericColumns.length > 0) x_col = y_col || STATE.numericColumns[0];

  try {
    const response = await fetch('/chart', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ chart_type: chartType, x_col, y_col })
    });

    if (response.status === 204) { containerEl.innerHTML = ''; return; }
    if (!response.ok) {
      containerEl.innerHTML = '<p style="font-size:12px;color:var(--text-3);padding:8px 0;">Chart unavailable for this question.</p>';
      return;
    }

    const blob     = await response.blob();
    const imageUrl = URL.createObjectURL(blob);
    containerEl.innerHTML =
      '<div class="chart-label">Auto-generated chart · ' + chartType + '</div>' +
      '<img class="chart-img" alt="Data chart" />';

    const img = containerEl.querySelector('img');
    img.src   = imageUrl;
    img.onload = () => URL.revokeObjectURL(imageUrl);

  } catch (err) {
    containerEl.innerHTML = '';
    console.error('Chart error:', err);
  }
}


// ============================================================
//  8. RENDER — convert AI markdown-ish text to HTML
// ============================================================

function renderInsight(text) {
  let mainText  = text;
  let followUps = [];

  const followUpIdx = text.indexOf('You might also ask:');
  if (followUpIdx !== -1) {
    mainText = text.slice(0, followUpIdx).trim();
    const followUpSection = text.slice(followUpIdx + 'You might also ask:'.length).trim();
    followUps = followUpSection
      .split('\n')
      .map(line => line.replace(/^[-•*]\s*/, '').trim())
      .filter(line => line.length > 0);
  }

  const lines = mainText.split('\n').filter(line => line.trim() !== '');
  let html = '';
  lines.forEach(line => {
    const formatted = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    if (line.startsWith('•') || line.startsWith('-') || line.startsWith('*')) {
      const bulletText = formatted.replace(/^[•\-*]\s*/, '');
      html += `<div class="insight-line"><span class="bullet">›</span><span>${bulletText}</span></div>`;
    } else {
      html += `<p style="margin-bottom:8px;">${formatted}</p>`;
    }
  });

  let followUpHtml = '';
  if (followUps.length > 0) {
    followUpHtml = `
      <div class="follow-ups">
        <div class="follow-ups-label">You might also ask</div>
        ${followUps.map(q => {
          const cleanQ = q.replace(/\*\*(.+?)\*\*/g, '$1');
          return `<span class="follow-up-chip" data-question="${escapeHtml(cleanQ)}" onclick="prefillQuestion(this.dataset.question)">${escapeHtml(cleanQ)}</span>`;
        }).join('')}
      </div>`;
  }

  return html + followUpHtml;
}

function prefillQuestion(text) {
  $('questionInput').value = text.trim();
  $('charCount').textContent = `${text.trim().length} / 500`;
  $('questionInput').focus();
  $('panel-question').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}


// ============================================================
//  9. CARD BUILDERS
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
  const card = document.createElement('div');
  card.className = 'exchange';
  const insightHtml  = renderInsight(data.insight);
  const chartSection = (data.chart_type && data.chart_type !== 'none')
    ? '<div class="chart-wrap"></div>'
    : '';
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
  const errorCard = document.createElement('div');
  errorCard.className = 'exchange';
  errorCard.innerHTML = `
    <div class="exchange-answer" style="border-left: 3px solid var(--danger); padding-left: 20px;">
      <p style="color:var(--danger); font-size:13px;">✗ ${escapeHtml(message)}</p>
    </div>`;
  loadingCard.replaceWith(errorCard);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}


// ============================================================
//  10. UTILITIES
// ============================================================

function showStatus(elementId, type, message) {
  const el = $(elementId);
  el.className  = `status-bar show ${type}`;
  el.textContent = message;
}

function revealPanels() {
  $('panel-preview').classList.remove('hidden');
  $('panel-question').classList.remove('hidden');
  $('questionInput').focus();
}

function updateExchangeCount() {
  const el = $('exchangeCount');
  const n  = STATE.exchangeCount;
  el.textContent = n === 1 ? '1 exchange' : `${n} exchanges`;
}

function clearResults() {
  $('exchangeList').innerHTML = '';
  STATE.exchangeCount = 0;
  updateExchangeCount();
  $('panel-results').classList.add('hidden');
  $('btnExport').style.display = 'none';
}

async function newChat() {
  // Clears the server session and resets the UI for a new upload.
  try { await fetch('/reset', { method: 'POST' }); } catch (e) {}
  STATE.fileUploaded   = false;
  STATE.activeChatId   = null;
  STATE.exchangeCount  = 0;
  STATE.columnNames    = [];
  STATE.numericColumns = [];
  STATE.textColumns    = [];

  // Hide panels and reset upload UI
  $('panel-preview').classList.add('hidden');
  $('panel-question').classList.add('hidden');
  $('panel-results').classList.add('hidden');
  $('fileInfo').classList.remove('show');
  $('uploadStatus').className = 'status-bar';
  $('exchangeList').innerHTML = '';
  $('btnExport').style.display = 'none';
  updateExchangeCount();

  // Refresh sidebar
  loadChatList();
}


// ============================================================
//  Phase C: SIDEBAR — chat list management
// ============================================================

async function loadChatList() {
  try {
    const res  = await fetch('/chats');
    const data = await res.json();
    if (!res.ok) return;

    renderChatList(data.chats);
  } catch (err) {
    console.error('Chat list error:', err);
  }
}

function renderChatList(chats) {
  const container = $('chatList');
  const empty     = $('chatListEmpty');

  // Remove all existing chat items (keep the empty message element)
  container.querySelectorAll('.chat-item').forEach(el => el.remove());

  if (!chats || chats.length === 0) {
    empty.style.display = '';
    return;
  }

  empty.style.display = 'none';

  // Add label
  if (!container.querySelector('.sidebar-section-label')) {
    const label = document.createElement('div');
    label.className   = 'sidebar-section-label';
    label.textContent = 'Recent analyses';
    container.insertBefore(label, empty);
  }

  chats.forEach(chat => {
    const item = document.createElement('div');
    item.className = 'chat-item' + (chat.is_active ? ' active' : '');
    item.dataset.chatId = chat.id;

    item.innerHTML = `
      <button class="chat-item-btn" onclick="switchToChat(${chat.id})">
        <span class="chat-item-name">${escapeHtml(chat.name)}</span>
        <span class="chat-item-meta">${chat.message_count} Q&A · ${escapeHtml(chat.created_at)}</span>
      </button>
      <button class="chat-del-btn" onclick="deleteChat(event, ${chat.id})" title="Delete">✕</button>`;

    container.insertBefore(item, empty);
  });
}

async function switchToChat(chatId) {
  if (chatId === STATE.activeChatId) return;

  try {
    // 1. Activate the chat on the server (restores session filepath)
    const activateRes = await fetch(`/chats/${chatId}/activate`, { method: 'POST' });
    if (!activateRes.ok) {
      const err = await activateRes.json();
      alert(err.error || 'Could not load this chat.');
      return;
    }

    // 2. Load the messages from the DB
    const res  = await fetch(`/chats/${chatId}`);
    const data = await res.json();
    if (!res.ok) { alert('Could not load chat messages.'); return; }

    // 3. Update state
    STATE.activeChatId  = chatId;
    STATE.exchangeCount = data.messages.length;

    // 4. Render messages into the exchange list
    const list = $('exchangeList');
    list.innerHTML = '';

    // Add a "Restored from history" badge
    const badge = document.createElement('div');
    badge.innerHTML = `<div class="restored-badge">↩ Restored · ${escapeHtml(data.chat.csv_filename || data.chat.name)}</div>`;
    list.appendChild(badge);

    data.messages.forEach(msg => {
      const card = document.createElement('div');
      card.className = 'exchange';
      const chartSection = (msg.chart_type && msg.chart_type !== 'none')
        ? `<div class="chart-wrap" data-type="${msg.chart_type}" data-x="${msg.chart_x_col || ''}" data-y="${msg.chart_y_col || ''}"></div>`
        : '';
      card.innerHTML = `
        <div class="exchange-question">
          <span class="q-label">You</span>
          <span>${escapeHtml(msg.question)}</span>
        </div>
        <div class="exchange-answer">
          <div class="insight-text">${renderInsight(msg.answer)}</div>
          ${chartSection}
        </div>`;
      list.appendChild(card);

      // Reload charts for this message
      if (msg.chart_type && msg.chart_type !== 'none') {
        const chartWrap = card.querySelector('.chart-wrap');
        if (chartWrap) {
          loadChart(chartWrap, msg.chart_type, {
            x: msg.chart_x_col || null,
            y: msg.chart_y_col || null
          });
        }
      }
    });

    // 5. Show panels
    $('panel-preview').classList.remove('hidden');
    $('panel-question').classList.remove('hidden');
    $('panel-results').classList.remove('hidden');
    $('btnExport').style.display = data.messages.length > 0 ? '' : 'none';
    updateExchangeCount();

    // 6. Update file info display
    $('infoFilename').textContent = data.chat.csv_filename || data.chat.name;
    $('fileInfo').classList.add('show');

    // 7. Refresh sidebar to update active state
    loadChatList();

  } catch (err) {
    console.error('Switch chat error:', err);
  }
}

async function deleteChat(event, chatId) {
  event.stopPropagation();
  // Prevent click bubbling up to the chat-item-btn

  if (!confirm('Delete this analysis? This cannot be undone.')) return;

  try {
    const res = await fetch(`/chats/${chatId}`, { method: 'DELETE' });
    if (!res.ok) { console.error('Delete failed'); return; }

    // If the deleted chat was active, reset the UI
    if (chatId === STATE.activeChatId) await newChat();
    else loadChatList();

  } catch (err) {
    console.error('Delete error:', err);
  }
}


// ============================================================
//  Phase D: PDF EXPORT
// ============================================================

function exportPDF() {
  if (!STATE.activeChatId) {
    alert('Please start an analysis first.');
    return;
  }
  // Simple GET link — browser will download the PDF automatically
  window.location.href = `/export/${STATE.activeChatId}`;
}


// ============================================================
//  11. INIT — runs on page load
// ============================================================

(function init() {
  // Set user avatar initials from the email shown in the sidebar
  const emailEl = $('userEmail');
  if (emailEl) {
    const email  = emailEl.textContent.trim();
    const avatar = $('userAvatar');
    if (avatar && email) avatar.textContent = email[0].toUpperCase();
  }

  // Load the chat list into the sidebar
  loadChatList();
})();