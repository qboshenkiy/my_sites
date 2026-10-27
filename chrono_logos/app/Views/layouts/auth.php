<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1, viewport-fit=cover"
    >

    <title>
        <?= esc($title ?? 'Авторизация') ?> | Chronologos
    </title>

    <link
        rel="stylesheet"
        href="/assets/css/auth.css"
    >

    <?= $this->renderSection('styles') ?>
    <link rel="stylesheet" href="/assets/css/theme.css">
    <meta name="theme-color" content="#10131b">
    <link rel="manifest" href="/index.php?pwa=manifest">
    <link rel="stylesheet" href="/assets/css/game-world.css?v=20261017">
    <link rel="stylesheet" href="/assets/css/polish.css?v=20261027">
<link rel="stylesheet" href="/assets/ui.css?v=20261027"><script src="/assets/ui.js?v=20261027" data-ui-theme="chrono" defer></script></head>

<body class="auth-screen">
<a class="auth-brand" href="/games"><span aria-hidden="true">◷</span>Chronologos</a>

<?= $this->renderSection('content') ?>

<?= $this->renderSection('scripts') ?>

<?= view('partials/telegram-assets') ?>
<?= view('partials/site-observability') ?>
</body>
</html>
