<?php

/**
 * Единый реестр игровых модулей приложения.
 *
 * Раньше список модулей для карточек на дашборде (Dashboard::getGameModules())
 * и список пунктов в сайдборе (sidebar_menu()) существовали независимо друг
 * от друга — при добавлении нового модуля их пришлось бы держать в синхроне
 * вручную в двух местах. Здесь один источник: у каждого модуля есть общая
 * карточка (code/title/description/url — для дашборда) и своё меню
 * (menu/adminMenu — для сайдбара), так что добавление модуля — это правка
 * только этого файла.
 */

if (! function_exists('app_modules')) {
    function app_modules(): array
    {
        return [
            [
                'code'        => 'chronos',
                'title'       => 'Chronos',
                'description' => 'Создавайте и запускайте хронологические игры.',
                'url'         => '/games',

                'menu' => [
                    [
                        'url'   => '/creator/new',
                        'icon'  => 'plus',
                        'label' => 'Создать игру',
                        'type'  => 'action',
                    ],
                    [
                        'url'   => '/creator/games',
                        'icon'  => 'library',
                        'label' => 'Мои игры',
                        'match' => 'creator',
                    ],
                    [
                        'url'   => '/rooms',
                        'icon'  => 'rooms',
                        'label' => 'Игровые комнаты',
                        'match' => 'rooms',

                        /* История лежит под /rooms/, но это отдельный пункт меню. */
                        'exclude' => 'rooms/history',
                    ],
                    [
                        'url'   => '/games',
                        'icon'  => 'grid',
                        'label' => 'Каталог игр',
                        'match' => 'games',
                    ],
                    [
                        'url'   => '/rooms/history',
                        'icon'  => 'history',
                        'label' => 'История игр',
                        'match' => 'rooms/history',
                    ],
                ],

                'adminMenu' => [
                    [
                        'url'   => '/admin/games',
                        'icon'  => 'shield',
                        'label' => 'Все игры',
                        'match' => 'admin/games',
                    ],
                    [
                        'url'   => '/admin/rooms',
                        'icon'  => 'rooms',
                        'label' => 'Все комнаты',
                        'match' => 'admin/rooms',
                    ],
                    [
                        'url'   => '/admin/users',
                        'icon'  => 'users',
                        'label' => 'Пользователи',
                        'match' => 'admin/users',
                    ],
                ],
            ],

            [
                'code'        => 'draw',
                'title'       => 'Draw',
                'description' => 'В разработке: игровая механика Draw пока недоступна.',
                'url'         => '/draw',

                'menu' => [
                    [
                        'url'   => '/draw',
                        'icon'  => 'board',
                        'label' => 'Draw · скоро',
                        'match' => 'draw',
                    ],
                ],

                'adminMenu' => [],
            ],
        ];
    }
}

if (! function_exists('sidebar_menu_is_active')) {
    function sidebar_menu_is_active(string $prefix): bool
    {
        $currentPath = trim(
            (string) service('request')->getPath(),
            '/'
        );

        return $currentPath === $prefix
            || str_starts_with($currentPath, $prefix . '/');
    }
}

if (! function_exists('render_menu_item')) {
    /**
     * Одна строка меню — либо ссылка, либо (type=action) форма-кнопка,
     * как "Создать игру". Общий рендер для игровых пунктов и админских.
     */
    function render_menu_item(array $item): string
    {
        if (($item['type'] ?? 'link') === 'action') {
            ob_start();
            ?>
            <form
                method="post"
                action="<?= esc($item['url'], 'attr') ?>"
                class="js-create-game-form nav-create-game-form"
            >
                <?= csrf_field() ?>
                <button type="submit" class="nav-item nav-item-button">
                    <span class="nav-icon"><?= icon($item['icon']) ?></span>
                    <span><?= esc($item['label']) ?></span>
                </button>
            </form>
            <?php
            return (string) ob_get_clean();
        }

        $active = sidebar_menu_is_active($item['match']);

        if (! empty($item['exclude']) && sidebar_menu_is_active($item['exclude'])) {
            $active = false;
        }

        ob_start();
        ?>
        <a
            href="<?= esc($item['url'], 'attr') ?>"
            class="nav-item<?= $active ? ' active' : '' ?>"
        >
            <span class="nav-icon"><?= icon($item['icon']) ?></span>
            <span><?= esc($item['label']) ?></span>
        </a>
        <?php
        return (string) ob_get_clean();
    }
}

if (! function_exists('sidebar_menu')) {
    function sidebar_menu(): string
    {
        $isAdmin = session()->get('role_code') === 'ADMIN';
        $modules = app_modules();

        ob_start();
        ?>
        <div class="nav-label">
            ГЛАВНОЕ
        </div>

        <a
            href="/dashboard"
            class="nav-item<?= sidebar_menu_is_active('dashboard') ? ' active' : '' ?>"
        >
            <span class="nav-icon"><?= icon('home') ?></span>
            <span>Главная</span>
        </a>

        <?php foreach ($modules as $module): ?>

            <div class="nav-label">
                <?= esc(strtoupper($module['title'])) ?>
            </div>

            <?php foreach ($module['menu'] as $item): ?>
                <?= render_menu_item($item) ?>
            <?php endforeach; ?>

        <?php endforeach; ?>

        <?php
        $adminItems = [];
        foreach ($modules as $module) {
            foreach ($module['adminMenu'] as $item) {
                $adminItems[] = $item;
            }
        }
        ?>

        <?php if ($isAdmin && $adminItems !== []): ?>

            <div class="nav-label">
                АДМИНИСТРИРОВАНИЕ
            </div>

            <?php foreach ($adminItems as $item): ?>
                <?= render_menu_item($item) ?>
            <?php endforeach; ?>

        <?php endif; ?>
        <?php

        return (string) ob_get_clean();
    }
}
