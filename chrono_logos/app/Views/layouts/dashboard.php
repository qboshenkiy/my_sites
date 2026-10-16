<?php
$isMobileClient =
    service('request')
        ->getUserAgent()
        ->isMobile();
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>
        <?= esc($title ?? 'Dashboard') ?> | My Games
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
</head>

<body class="<?= $isMobileClient ? 'mobile-client' : 'desktop-client' ?>">

<div class="app-layout">

    <?php if (! $isMobileClient): ?>
        <?= view('partials/aside') ?>
    <?php endif; ?>


    <div class="app-main">

        <?php if ($isMobileClient): ?>

            <header class="mobile-app-header">

                <a
                    href="/rooms"
                    class="mobile-app-logo"
                >
                    <span>M</span>
                    MY GAMES
                </a>

                <div class="mobile-app-actions">

                    <a href="/rooms">
                        Комнаты
                    </a>

                    <form
                        method="post"
                        action="/auth/logout"
                    >
                        <?= csrf_field() ?>
                        <button type="submit">
                            Выйти
                        </button>
                    </form>

                </div>

            </header>

        <?php else: ?>

            <?= view('partials/header', [
                'title' => $title ?? 'Dashboard',
                'username' => $username
                    ?? session()->get('username'),
            ]) ?>

        <?php endif; ?>


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

    </div>

</div>


<?php if (! $isMobileClient): ?>
<script>
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebarOverlay = document.getElementById('sidebar-overlay');

function toggleSidebar()
{
    sidebar.classList.toggle('is-open');
    sidebarOverlay.classList.toggle('is-active');
}

if (sidebarToggle) {
    sidebarToggle.addEventListener('click', toggleSidebar);
}

if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', toggleSidebar);
}
</script>
<?php endif; ?>

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

</body>
</html>
