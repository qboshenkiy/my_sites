<header class="app-header">

    <div class="header-left">

        <button
            id="sidebar-toggle"
            class="sidebar-toggle"
            type="button"
            title="Меню"
        >
            <?= icon('menu', 20) ?>
        </button>

        <div>

            <h1 class="page-title">
                <?= esc($title ?? 'Главная') ?>
            </h1>

            <div class="page-subtitle">
                <?= esc($subtitle ?? 'Игры, комнаты и результаты') ?>
            </div>

        </div>

    </div>


    <div class="header-right">

        <?php
        /*
         * Раньше здесь была кнопка-колокольчик, которая ничего не делала.
         * Уведомлений в системе нет — ни таблицы, ни событий, ни признака
         * "прочитано". Кнопка убрана, а не заглушена пустым дропдауном:
         * пустой дропдаун — такой же тупик, только с лишним кликом.
         */
        ?>

        <div class="header-user-menu">

            <button
                type="button"
                class="header-user"
                id="user-menu-toggle"
                aria-label="<?= esc('Аккаунт: ' . ($username ?? 'Пользователь'), 'attr') ?>"
                aria-haspopup="true"
                aria-expanded="false"
            >

                <span class="header-avatar">
                    <?= strtoupper(
                        mb_substr(
                            $username ?? 'U',
                            0,
                            1
                        )
                    ) ?>
                </span>

                <span class="header-user-data">

                    <span class="header-username">
                        <?= esc($username ?? 'Пользователь') ?>
                    </span>

                    <span class="header-status">
                        <?= session()->get('role_code') === 'ADMIN'
                            ? 'Администратор'
                            : 'Игрок' ?>
                    </span>

                </span>

                <?= icon('chevron-down', 16, 'icon header-user-caret') ?>

            </button>


            <div
                class="header-dropdown"
                id="user-menu"
                hidden
            >

                <a href="/account/settings" class="header-dropdown-item">
                    <?= icon('settings', 17) ?>
                    <span>Настройки аккаунта</span>
                </a>

                <a href="/rooms/history" class="header-dropdown-item">
                    <?= icon('history', 17) ?>
                    <span>История игр</span>
                </a>

                <form
                    method="post"
                    action="/auth/logout"
                    class="header-dropdown-form"
                >

                    <?= csrf_field() ?>

                    <button
                        class="header-dropdown-item header-dropdown-danger"
                        type="submit"
                    >
                        <?= icon('logout', 17) ?>
                        <span>Выйти</span>
                    </button>

                </form>

            </div>

        </div>

    </div>

</header>


<script>
(() => {
    const toggle = document.getElementById('user-menu-toggle');
    const menu = document.getElementById('user-menu');

    if (!toggle || !menu) {
        return;
    }

    const setOpen = open => {
        menu.hidden = !open;
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.classList.toggle('is-open', open);
    };

    toggle.addEventListener('click', event => {
        event.stopPropagation();
        setOpen(menu.hidden);
    });

    document.addEventListener('click', event => {
        if (!menu.hidden && !menu.contains(event.target)) {
            setOpen(false);
        }
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !menu.hidden) {
            setOpen(false);
            toggle.focus();
        }
    });
})();
</script>
