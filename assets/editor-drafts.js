/* Recoverable quiz drafts are local to this browser and Pulse account. */
let editorDraftKey = null;
let editorDraftBaseline = null;
let editorDraftAvailable = true;
let editorDraftWritten = null;

function editorDraftPrefix() {
  return boot?.user?.id != null ? 'pulse-draft:v1:' + boot.user.id + ':' : null;
}

function readEditorDraft(key) {
  const prefix = editorDraftPrefix();
  if (!prefix || !key?.startsWith(prefix)) return null;
  try {
    const raw = localStorage.getItem(key);
    const record = JSON.parse(raw);
    if (!record || !Number.isFinite(record.updated) || !Array.isArray(record.quiz?.questions) ||
        !record.quiz.questions.length || record.quiz.questions.length > 50 ||
        typeof record.quiz.title !== 'string') return null;
    return {...record, key, raw};
  } catch {
    return null;
  }
}

function startQuizEditor(quiz, {recovered = null, imported = false} = {}) {
  stopPoll();
  page = 'editor';
  draft = quiz;
  pulseEditorClosed = new Set(quiz.questions.map((_,i)=>i).slice(1));
  pulseEditorIssuesShown = false;
  const prefix = editorDraftPrefix();
  const suffix = draft.id ? 'quiz:' + draft.id : 'new:' + Date.now() + ':' + Math.random().toString(36).slice(2);
  editorDraftKey = recovered?.key || (prefix && prefix + suffix);
  editorDraftBaseline = imported || recovered ? null : JSON.stringify(draft);
  editorDraftAvailable = Boolean(editorDraftKey);
  editorDraftWritten = recovered?.raw || null;
  drawEditor();
}

function saveEditorDraft() {
  if (!editorDraftKey || !editorDraftPrefix() || !editorDraftKey.startsWith(editorDraftPrefix())) return;
  const current = JSON.stringify(draft);
  const previous = readEditorDraft(editorDraftKey);
  try {
    if (current === editorDraftBaseline) {
      // Avoid removing a different draft written by another tab.
      if (previous?.raw === editorDraftWritten) localStorage.removeItem(editorDraftKey);
      editorDraftWritten = null;
    } else if (current !== JSON.stringify(previous?.quiz)) {
      editorDraftWritten = JSON.stringify({updated:Date.now(), quiz:draft});
      localStorage.setItem(editorDraftKey, editorDraftWritten);
    }
    editorDraftAvailable = true;
  } catch {
    editorDraftAvailable = false;
  }
  const status = document.querySelector('.editor-draft-status');
  if (status) status.textContent = editorDraftMessage();
}

function editorDraftMessage() {
  if (!editorDraftAvailable) return 'Не удалось сохранить черновик в браузере. Сохраните опросник вручную.';
  return readEditorDraft(editorDraftKey) ? 'Черновик сохранён в этом браузере' : 'Изменения будут сохраняться в черновик';
}

function editorDraftStatus() {
  return '<small class="editor-draft-status" role="status">' + editorDraftMessage() + '</small>';
}

function editorDraftSnapshot() {
  return readEditorDraft(editorDraftKey);
}

function clearSavedEditorDraft(snapshot) {
  if (!snapshot) return;
  try {
    if (localStorage.getItem(snapshot.key) === snapshot.raw &&
        JSON.stringify(snapshot.quiz) === JSON.stringify(draft)) localStorage.removeItem(snapshot.key);
  } catch {}
}

function editorDraftNotice() {
  const prefix = editorDraftPrefix();
  if (!prefix) return '';
  const records = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const record = readEditorDraft(localStorage.key(i));
      if (record) records.push(record);
    }
  } catch {}
  if (!records.length) return '';
  records.sort((a,b)=>b.updated-a.updated);
  return `<section class="draft-notice" aria-label="Несохранённые черновики">
    <div class="draft-notice-heading">${icon('edit')}<div><h2>Продолжить работу?</h2><p>В этом браузере есть несохранённые изменения.</p></div></div>
    ${records.map(({key,quiz,updated})=>`<div class="draft-row">
      <div><strong>${esc(quiz.title || 'Новый опросник')}</strong><small>${new Date(updated).toLocaleString('ru-RU',{dateStyle:'short',timeStyle:'short'})}</small></div>
      <div class="draft-actions"><button class="outline" data-draft-restore="${esc(key)}">Восстановить</button><button class="icon-button danger" title="Удалить черновик" data-draft-discard="${esc(key)}">${icon('close')}</button></div>
    </div>`).join('')}
  </section>`;
}

function restoreEditorDraft(record) {
  const query = record.quiz.id && library.find(quiz=>quiz.id===record.quiz.id);
  const quiz = structuredClone(record.quiz);
  if (quiz.id && !query) {
    delete quiz.id;
    delete quiz.visibility;
    startQuizEditor(quiz,{imported:true});
    if (editorDraftSnapshot() && readEditorDraft(record.key)?.raw === record.raw) {
      try { localStorage.removeItem(record.key); } catch {}
    }
    toast('Исходный опросник недоступен. Черновик открыт как новый.');
    return;
  }
  startQuizEditor(quiz,{recovered:record});
}

function captureEditorChange(event) {
  if (page !== 'editor' || !event.target.closest('#editor-form') || event.target.type === 'file') return;
  captureDraft();
  saveEditorDraft();
}

app.addEventListener('input', captureEditorChange, true);
app.addEventListener('change', captureEditorChange, true);
app.addEventListener('click', event=>{
  const button = event.target.closest('[data-draft-restore],[data-draft-discard]');
  if (!button) return;
  const record = readEditorDraft(button.dataset.draftRestore || button.dataset.draftDiscard);
  if (!record) return drawDashboard();
  if (button.dataset.draftRestore) return restoreEditorDraft(record);
  confirmDialog('Удалить черновик?', 'Изменения в этом черновике будут удалены.', ()=>{
    if (readEditorDraft(record.key)?.raw === record.raw) localStorage.removeItem(record.key);
    drawDashboard();
  });
});
