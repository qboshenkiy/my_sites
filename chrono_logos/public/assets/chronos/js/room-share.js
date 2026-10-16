(() => {
  if (window.chronoRoomShareReady) return;
  window.chronoRoomShareReady = true;
  const status = (widget, text) => { widget.querySelector('[data-share-status]').textContent = text; };
  function select(field) {
    field.focus({preventScroll:true}); field.select(); field.setSelectionRange(0, field.value.length);
  }
  function legacyCopy(text) {
    const previous = document.activeElement;
    const field = document.createElement('textarea');
    field.value = text; field.readOnly = true;
    Object.assign(field.style, {position:'fixed',left:'0',top:'0',opacity:'0',width:'1px',height:'1px'});
    document.body.append(field);
    let copied = false;
    try { select(field); copied = document.execCommand('copy') === true; } catch {}
    finally {field.remove();if (previous?.isConnected) previous.focus({preventScroll:true});}
    return copied;
  }
  async function copy(widget, code) {
    const input = widget.querySelector('[data-invite-url]');
    const value = code ? widget.dataset.code : input.value;
    let copied = false;
    try {
      if (navigator.clipboard?.writeText) {await navigator.clipboard.writeText(value);copied = true;}
    } catch {}
    if (!copied) copied = legacyCopy(value);
    if (copied) {status(widget, code ? 'Код скопирован.' : 'Ссылка скопирована.');return;}
    select(input);
    status(widget, code
      ? `Код комнаты: ${widget.dataset.code}. Ссылка выделена — её можно скопировать вручную.`
      : 'Ссылка выделена. Удерживайте её и выберите «Копировать» или нажмите Ctrl+C.');
  }
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-room-copy], [data-room-send]');
    if (!button || button.disabled) return;
    const widget = button.closest('[data-room-share]');
    if (!widget) return;
    if (button.hasAttribute('data-room-copy')) {
      button.disabled = true;
      try {await copy(widget, button.dataset.roomCopy === 'code');}
      finally {button.disabled = false;}
      return;
    }
    const data = {title:'Chronologos',text:widget.dataset.shareText,url:widget.querySelector('[data-invite-url]').value};
    button.disabled = true;
    try {
      if (typeof navigator.share !== 'function' || (navigator.canShare && !navigator.canShare(data))) {
        status(widget, 'Выберите Telegram или WhatsApp ниже, либо скопируйте ссылку.');
        return;
      }
      // Call directly from the click handler to preserve the browser's user activation.
      await navigator.share(data);
      status(widget, 'Приглашение передано выбранному приложению.');
    } catch (error) {
      if (error.name === 'AbortError') status(widget, 'Отправка отменена.');
      else status(widget, 'Браузер не открыл отправку. Выберите Telegram или WhatsApp ниже, либо скопируйте ссылку.');
    } finally {button.disabled = false;}
  });
  document.addEventListener('click', event => {
    const field = event.target.closest('[data-invite-url]');
    if (field) select(field);
  });
})();
