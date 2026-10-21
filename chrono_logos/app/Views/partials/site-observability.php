<script>
(() => {
  const token = <?= json_encode(csrf_hash()) ?>;
  const report = (message, source = '', line = 0) => {
    fetch('/diagnostics/client-error', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-TOKEN': token},
      body: JSON.stringify({event: 'client_error', message: String(message || 'Ошибка JavaScript'), source: String(source || '').split('/').pop(), line: Number(line) || 0, page: location.pathname}),
      keepalive: true
    }).catch(() => {});
  };
  window.addEventListener('error', event => report(event.message, event.filename, event.lineno));
  window.addEventListener('unhandledrejection', event => report(event.reason?.message || event.reason || 'Необработанная ошибка Promise'));
  try {
    if (!sessionStorage.getItem('chrono-visit-logged')) {
      sessionStorage.setItem('chrono-visit-logged', '1');
      fetch('/diagnostics/client-error', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-TOKEN': token},
        body: JSON.stringify({event: 'visit', page: location.pathname}),
        keepalive: true
      }).catch(() => {});
    }
  } catch (_) {}
})();
</script>
