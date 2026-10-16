<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1, viewport-fit=cover"
    >

    <title>
        <?= esc($title ?? 'Авторизация') ?> | My Games
    </title>

    <link
        rel="stylesheet"
        href="/assets/css/auth.css"
    >

    <?= $this->renderSection('styles') ?>
</head>

<body>

<?= $this->renderSection('content') ?>

<?= $this->renderSection('scripts') ?>

</body>
</html>
