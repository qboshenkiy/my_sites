<div
    id="sidebar-overlay"
    class="sidebar-overlay"></div>

<aside
    class="sidebar"
    id="sidebar">

    <div class="sidebar-logo">
        <div class="logo-mark">
            <img src="/assets/img/icons/hrono.png" alt="Chronologos" width="25" height="25">
        </div>
        <div class="logo-text">
            <div class="logo-title">Chronologos</div>
            <div class="logo-subtitle">Игра про время</div>
        </div>
    </div>

    <nav class="sidebar-nav">

        <?= sidebar_menu() ?>
        <div class="nav-label">
            АККАУНТ
        </div>


        <a
            href="/account/settings"
            class="nav-item<?= sidebar_menu_is_active('account') ? ' active' : '' ?>">
            <span class="nav-icon">
                <?= icon('settings') ?>
            </span>

            <span>
                Настройки
            </span>
        </a>

    </nav>


    <div class="sidebar-footer">

        <div class="sidebar-user">

            <div class="sidebar-avatar">

                <?= strtoupper(
                    mb_substr(
                        session()->get('username') ?? 'U',
                        0,
                        1
                    )
                ) ?>

            </div>

            <div class="sidebar-user-info">

                <div class="sidebar-username">
                    <?= esc(session()->get('username')) ?>
                </div>

                <div class="sidebar-role">
                    <?= session()->get('role_code') === 'ADMIN' ? 'Организатор' : 'Игрок' ?>
                </div>

            </div>

        </div>

    </div>

</aside>
