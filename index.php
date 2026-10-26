<?php
require __DIR__ . '/assets/pwa-endpoints.php';

header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
?>
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="theme-color" content="#7563e8"><link rel="manifest" href="/index.php?pwa=manifest"><title>Пульс — живые викторины</title><link rel="stylesheet" href="assets/style.css?v=17"><link rel="stylesheet" href="assets/community.css?v=3"><link rel="stylesheet" href="assets/forms.css?v=1"><link rel="stylesheet" href="assets/polish.css?v=3"></head>
<body><div id="app"><div class="loading">Запускаем Пульс…</div></div><div id="toast" role="status" aria-live="polite"></div><script src="https://telegram.org/js/telegram-web-app.js?62" defer></script><script src="assets/pulse-miniapp.js?v=1" defer></script><script src="assets/pwa.js?v=3" data-pwa-app="pulse" defer></script><script src="assets/vendor/qrcode.js" defer></script><script src="assets/app.js?v=22" defer></script><script src="assets/import.js?v=17" defer></script><script src="assets/bluff.js?v=18" defer></script><script src="assets/community.js?v=5" defer></script><script src="assets/room-report.js?v=2" defer></script><script src="assets/forms.js?v=3" defer></script><script src="assets/results-ui.js?v=1" defer></script></body>
</html>
