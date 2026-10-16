(() => {
  const root = document.getElementById('timeline-import');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const csrf = $('import-csrf');
  let preview = null, busy = false;
  const message = (text, error = false) => {
    $('import-message').textContent = text;
    $('import-message').className = error ? 'timeline-error' : '';
  };
  function invalidate() { preview = null; $('import-preview').hidden = true; }
  $('json-source').addEventListener('input', invalidate);
  root.querySelectorAll('[name="import-mode"]').forEach(input => input.addEventListener('change', invalidate));
  $('append-after')?.addEventListener('change', invalidate);
  function orderMode() { return $('append-after')?.checked ? 'after' : 'original'; }
  function target() { return root.querySelector('[name="import-mode"]:checked')?.value === 'append' ? root.dataset.gameId : '0'; }
  function count() {
    const n = root.querySelectorAll('[data-import-index]:checked').length;
    $('import-count').textContent = `Выбрано: ${n} из ${preview?.cards.length || 0}`;
    $('confirm-import').disabled = !n || busy;
  }
  async function post(data) {
    const form = new FormData();
    for (const [key, value] of Object.entries(data)) form.append(key, value);
    form.append(csrf.name, csrf.value);
    const response = await fetch('/creator/import-json', {method:'POST', body:form, headers:{'X-Requested-With':'XMLHttpRequest'}});
    let result;
    try { result = await response.json(); } catch { throw Error('Сессия закончилась или сервер недоступен. Обновите страницу.'); }
    if (result.csrfHash) { csrf.name = result.csrfName; csrf.value = result.csrfHash; }
    if (!response.ok || !result.success) throw Error(result.message || 'Импорт не выполнен.');
    return result;
  }
  async function run(action) {
    if (busy) return;
    busy = true;
    for (const el of root.querySelectorAll('button, textarea, input')) el.disabled = true;
    try { await action(); } catch (error) { message(error.message, true); }
    finally { busy = false; for (const el of root.querySelectorAll('button, textarea, input')) el.disabled = false; count(); }
  }
  async function loadGenesis() {
    await run(async () => {
      const response = await fetch('/creator/genesis-json');
      if (!response.ok) throw Error('Не удалось загрузить пример Бытия.');
      $('json-source').value = await response.text(); invalidate();
      message('Бытие загружено. Нажмите «Проверить JSON».');
    });
  }
  $('load-genesis').onclick = loadGenesis;
  $('json-file').onchange = () => run(async () => {
    const file = $('json-file').files[0];
    if (!file) return;
    if (file.size > 2097152) throw Error('Файл больше 2 МБ.');
    $('json-source').value = await file.text(); invalidate(); message('Файл загружен. Проверьте JSON.');
  });
  $('check-json').onclick = () => run(async () => {
    invalidate();
    if (new Blob([$('json-source').value]).size > 2097152) throw Error('JSON больше 2 МБ.');
    preview = await post({json:$('json-source').value, game_id:target(), order_mode:orderMode(), preview:'1'});
    $('preview-title').textContent = preview.title;
    $('preview-description').textContent = preview.description;
    $('import-cards').replaceChildren();
    preview.cards.forEach((card, i) => {
      const row = document.createElement('label'); row.className = 'timeline-preview-card';
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = true; checkbox.dataset.importIndex = i; checkbox.onchange = count;
      const text = document.createElement('span');
      text.textContent = `${card.title} · ${card.category || 'Без раздела'} · порядок ${card.sort_order} · ${card.revealed_value || ''}${card.is_enabled ? '' : ' · выключена'}`;
      row.append(checkbox, text); $('import-cards').append(row);
    });
    $('import-preview').hidden = false; count(); message('JSON проверен. Выберите карточки для импорта.');
  });
  for (const [id, selected] of [['select-import-all',true],['select-import-none',false]]) {
    $(id).onclick = () => { root.querySelectorAll('[data-import-index]').forEach(c => c.checked = selected); count(); };
  }
  $('confirm-import').onclick = () => {
    if (!preview) return;
    const cards = [...root.querySelectorAll('[data-import-index]:checked')].map(c => preview.cards[Number(c.dataset.importIndex)]);
    if (!cards.length) return;
    run(async () => {
      const result = await post({json:JSON.stringify({title:preview.title,description:preview.description,cards}),game_id:target(),order_mode:orderMode()});
      message(result.message); window.location.assign(result.editor_url);
    });
  };
  if (root.dataset.preset === 'genesis') loadGenesis();
})();
