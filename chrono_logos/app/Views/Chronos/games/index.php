<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>Каталог игр | Chronologos</title>
    <link rel="stylesheet" href="/assets/chronos/css/catalog.css">
    <link rel="stylesheet" href="/assets/css/theme.css">
    <meta name="theme-color" content="#10131b">
    <link rel="manifest" href="/index.php?pwa=manifest">
    <link rel="stylesheet" href="/assets/css/game-world.css?v=20261017">
    <link rel="stylesheet" href="/assets/css/polish.css?v=2">
</head>
<body>
<header class="catalog-header">
    <a class="catalog-logo" href="/"><span>◷</span> Chronologos</a>
    <nav>
        <?php if (session()->get('logged_in')): ?>
            <a href="/rooms">Комнаты</a>
            <a class="header-button" href="/dashboard">Кабинет</a>
        <?php else: ?>
            <a href="/auth/login-page">Войти</a>
            <a class="header-button" href="/auth/register-page">Регистрация</a>
        <?php endif; ?>
    </nav>
</header>

<main class="catalog-main">
    <section class="catalog-hero">
        <div class="section-label">ПУБЛИЧНЫЕ ИГРЫ</div>
        <h1>Хронологические игры</h1>
        <p>Выберите опубликованную игру и соберите события в правильном порядке.</p>
    </section>

    <form class="catalog-filters" method="get" action="/games">
        <input name="q" value="<?= esc($filters['q']) ?>" placeholder="Найти игру">
        <select name="language">
            <option value="">Все языки</option>
            <?php foreach ($languages as $item): ?>
                <option value="<?= esc($item['language'], 'attr') ?>" <?= $filters['language'] === $item['language'] ? 'selected' : '' ?>><?= esc(strtoupper($item['language'])) ?></option>
            <?php endforeach; ?>
        </select>
        <button type="submit">Найти</button>
        <?php if ($filters['q'] !== '' || $filters['language'] !== ''): ?><a href="/games">Сбросить</a><?php endif; ?>
    </form>

    <section class="catalog-grid">
        <?php if (empty($games)): ?>
            <div class="catalog-empty">Опубликованные игры пока не найдены.</div>
        <?php endif; ?>
        <?php foreach ($games as $game): ?>
            <article class="catalog-card">
                <div class="catalog-cover">
                    <?php if ($game['preview_url']): ?>
                        <img src="<?= esc('/' . ltrim((string) $game['preview_url'], '/')) ?>" alt="<?= esc($game['title']) ?>">
                    <?php else: ?>
                        <span><?= icon('image', 28) ?></span>
                    <?php endif; ?>
                </div>
                <div class="catalog-card-body">
                    <div class="catalog-meta"><span><?= esc(strtoupper($game['language'])) ?></span><span><?= (int) $game['cards_count'] ?> карточек</span></div>
                    <h2><?= esc($game['title']) ?></h2>
                    <p><?= esc($game['description'] ?: 'Описание пока не добавлено.') ?></p>
                    <footer>
                        <small>Автор: <?= esc($game['author']) ?></small>
                        <?php if (session()->get('logged_in')): ?>
                            <a href="/rooms">Создать комнату →</a>
                        <?php else: ?>
                            <a href="/auth/login-page">Войти и играть →</a>
                        <?php endif; ?>
                    </footer>
                </div>
            </article>
        <?php endforeach; ?>
    </section>
</main>
<?= view('partials/telegram-assets') ?>
</body>
</html>
