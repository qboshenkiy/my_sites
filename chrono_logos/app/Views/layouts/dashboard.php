<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0, viewport-fit=cover"
    >

    <title>
        <?= esc($title ?? 'Dashboard') ?> | Chronologos
    </title>

    <link
        rel="stylesheet"
        href="/assets/css/dashboard.css"
    >

    <link
        rel="stylesheet"
        href="/assets/css/badge.css"
    >

    <?= $this->renderSection('styles') ?>
    <link rel="stylesheet" href="/assets/css/theme.css">
    <meta name="theme-color" content="#10131b">
    <link rel="manifest" href="/index.php?pwa=manifest">
    <link rel="stylesheet" href="/assets/css/game-world.css?v=20261017">
    <link rel="stylesheet" href="/assets/css/polish.css?v=20261027">
<link rel="stylesheet" href="/assets/ui.css?v=20261027"><script src="/assets/ui.js?v=20261027" data-ui-theme="chrono" defer></script></head>

<body class="responsive-client">

<div class="app-layout">

    <?= view('partials/aside') ?>


    <div class="app-main">

        <?= view('partials/header', ['title'=>$title ?? 'Главная', 'username'=>$username ?? session()->get('username')]) ?>

        <main class="main-content">

            <?= view('alert/alert') ?>

            <?= view('partials/confirm-dialog') ?>

            <?php if ($desktopHint ?? false): ?>
                <div class="desktop-hint" role="note">
                    <strong>С компьютера удобнее.</strong>
                    Этот экран рассчитан на широкие таблицы и
                    перетаскивание карточек — с телефона он работает,
                    но пользоваться им тесно.
                </div>
            <?php endif; ?>

            <?= $this->renderSection('content') ?>

        </main>
        <nav class="mobile-bottom-nav" aria-label="Основная навигация">
            <?php $currentPath = trim(service('uri')->getPath(), '/'); ?>
            <?php foreach ([['rooms','Играть','play'],['games','Каталог','book'],['creator/games','Мои игры','cards'],['account/settings','Профиль','settings']] as [$path,$label,$symbol]): ?>
            <a href="/<?= $path ?>" <?= str_starts_with($currentPath,$path) ? 'aria-current="page"' : '' ?>><span aria-hidden="true"><?= icon($symbol) ?></span><?= $label ?></a>
            <?php endforeach ?>
        </nav>

    </div>

</div>


<script>
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebarOverlay = document.getElementById('sidebar-overlay');
if (sidebarToggle && sidebar) {
    sidebarToggle.setAttribute('aria-controls','sidebar');
    sidebarToggle.setAttribute('aria-expanded','false');
    const closeSidebar = () => {
        sidebar.classList.remove('is-open');sidebarOverlay?.classList.remove('is-active');
        sidebarToggle.setAttribute('aria-expanded','false');document.body.classList.remove('mobile-nav-open');
    };
    sidebarToggle.addEventListener('click',()=>{
        const open=sidebar.classList.toggle('is-open');sidebarOverlay?.classList.toggle('is-active',open);
        sidebarToggle.setAttribute('aria-expanded',String(open));document.body.classList.toggle('mobile-nav-open',open);
    });
    sidebarOverlay?.addEventListener('click',closeSidebar);
    document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeSidebar();sidebarToggle.focus();}});
    window.addEventListener('resize',()=>{if(innerWidth>760)closeSidebar();});
}
</script>

<script>
/*
 * Safe async creation of a game.
 * GET /creator/new no longer mutates the database.
 */
document.addEventListener('submit', async function (event) {
    const form = event.target.closest('.js-create-game-form');

    if (!form) {
        return;
    }

    event.preventDefault();

    const button = form.querySelector('button[type="submit"]');

    if (button?.disabled) {
        return;
    }

    const oldText = button?.textContent ?? '';

    if (button) {
        button.disabled = true;
        button.textContent = 'СОЗДАЁМ...';
    }

    try {
        const response = await fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        });

        const data = await response.json();

        if (data.csrfName && data.csrfHash) {
            document
                .querySelectorAll(`input[name="${data.csrfName}"]`)
                .forEach(input => {
                    input.value = data.csrfHash;
                });
        }

        if (!response.ok || !data.success) {
            if (typeof showAlert === 'function') {
                showAlert(data.type ?? 'danger', data.message ?? 'Не удалось создать игру.');
            }
            return;
        }

        if (data.redirect) {
            window.location.assign(data.redirect);
        }
    } catch (error) {
        console.error(error);

        if (typeof showAlert === 'function') {
            showAlert('danger', 'Не удалось связаться с сервером.');
        }
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = oldText;
        }
    }
});
</script>

<?= $this->renderSection('scripts') ?>

<?= view('partials/telegram-assets') ?>
    <?= view('partials/site-observability') ?>
</body>
</html>
