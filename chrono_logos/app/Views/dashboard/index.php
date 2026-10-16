<?= $this->extend('layouts/dashboard') ?>


<?= $this->section('content') ?>


<section class="welcome-section">

    <div>

        <div class="section-label">
            ЦЕНТР УПРАВЛЕНИЯ
        </div>

        <h2>
            Добро пожаловать,
            <?= esc($username) ?>
        </h2>

        <p>
            Создавайте хронологические игры,
            запускайте игровые комнаты и управляйте
            своими проектами.
        </p>

    </div>


    <form method="post" action="/creator/new" class="js-create-game-form dashboard-create-form">
        <?= csrf_field() ?>
        <button type="submit" class="primary-btn">+ СОЗДАТЬ ИГРУ</button>
    </form>

</section>

<section class="game-modules">

    <div class="panel-header">
        <div>
            <div class="section-label">ИГРЫ</div>
            <h3>Доступные игры</h3>
        </div>
    </div>

    <div class="game-modules-grid">
        <?php foreach ($gameModules as $module): ?>
            <a class="game-module-card game-module-<?= esc($module['code'], 'attr') ?>"
               href="<?= esc($module['url'], 'attr') ?>">
                <span class="section-label"><?= esc(strtoupper($module['code'])) ?></span>
                <h4><?= esc($module['title']) ?></h4>
                <p><?= esc($module['description']) ?></p>
                <span class="panel-link">Открыть игру →</span>
            </a>
        <?php endforeach; ?>
    </div>

</section>


<section class="stats-grid">

    <div class="stat-card">

        <div class="stat-label">
            МОИ ИГРЫ
        </div>

        <div class="stat-value">
            <?= (int) $stats['games'] ?>
        </div>

        <div class="stat-description">
            Созданных проектов
        </div>

    </div>


    <div class="stat-card">

        <div class="stat-label">
            СЫГРАНО
        </div>

        <div class="stat-value">
            <?= (int) $stats['played'] ?>
        </div>

        <div class="stat-description">
            Завершённых сессий
        </div>

    </div>


    <div class="stat-card">

        <div class="stat-label">
            ИГРОКОВ
        </div>

        <div class="stat-value">
            <?= (int) $stats['players'] ?>
        </div>

        <div class="stat-description">
            Всего участников
        </div>

    </div>


    <div class="stat-card">

        <div class="stat-label">
            АКТИВНЫЕ
        </div>

        <div class="stat-value">
            <?= (int) $stats['active'] ?>
        </div>

        <div class="stat-description">
            Комнат сейчас
        </div>

    </div>

</section>


<section class="dashboard-grid">

    <div class="dashboard-panel">

        <div class="panel-header">

            <div>

                <div class="section-label">
                    ПРОЕКТЫ
                </div>

                <h3>
                    Последние игры
                </h3>

            </div>


            <a
                href="/creator/games"
                class="panel-link"
            >
                Смотреть все →
            </a>

        </div>


        <?php if ($recentGames === []): ?>

            <div class="empty-state">

                <div class="empty-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                    </svg>
                </div>

                <h4>
                    У вас пока нет игр
                </h4>

                <p>
                    Создайте первую игру и добавьте
                    хронологические карточки.
                </p>

                <form method="post" action="/creator/new" class="js-create-game-form dashboard-create-form">
                    <?= csrf_field() ?>
                    <button type="submit" class="secondary-btn">Создать первую игру</button>
                </form>

            </div>

        <?php else: ?>

            <ul class="panel-list">

                <?php foreach ($recentGames as $game): ?>

                    <li class="panel-list-item">

                        <a
                            class="panel-item-main"
                            href="/creator/edit/<?= (int) $game['id'] ?>"
                        >
                            <span class="panel-item-title">
                                <?= esc($game['title']) ?>
                            </span>

                            <span class="panel-item-meta">
                                <?= (int) $game['cards_count'] ?> карт.
                                · <?= (int) $game['rooms_count'] ?> комн.
                                · <?= esc(date('d.m.Y', strtotime((string) $game['updated_at']))) ?>
                            </span>
                        </a>

                        <?= enum_badge('game_status', $game['status']) ?>

                    </li>

                <?php endforeach; ?>

            </ul>

        <?php endif; ?>

    </div>


    <div class="dashboard-panel">

        <div class="panel-header">

            <div>

                <div class="section-label">
                    АКТИВНОСТЬ
                </div>

                <h3>
                    Последние события
                </h3>

            </div>

        </div>


        <?php if ($activity === []): ?>

            <div class="activity-empty">

                <div class="activity-dot"></div>

                <div>

                    <strong>
                        Активности пока нет
                    </strong>

                    <p>
                        Здесь появится история ваших игр.
                    </p>

                </div>

            </div>

        <?php else: ?>

            <ul class="activity-feed">

                <?php foreach ($activity as $event): ?>

                    <?php
                    $kind = (string) $event['kind'];

                    $text = match ($kind) {
                        'GAME_PUBLISHED' => 'Игра опубликована',
                        'ROOM_CREATED'   => 'Создана комната',
                        'ROOM_FINISHED'  => 'Партия завершена',
                        'PLAYER_JOINED'  => 'Игрок присоединился',
                        default          => 'Событие',
                    };
                    ?>

                    <li class="activity-item activity-<?= esc(strtolower(str_replace('_', '-', $kind)), 'attr') ?>">

                        <span class="activity-dot" aria-hidden="true"></span>

                        <div class="activity-body">

                            <strong class="activity-text">
                                <?= esc($text) ?>

                                <?php if ($kind === 'PLAYER_JOINED' && ! empty($event['actor'])): ?>
                                    — <?= esc($event['actor']) ?>
                                <?php endif; ?>

                                <?php if ($kind === 'ROOM_FINISHED' && ! empty($event['actor'])): ?>
                                    — победил <?= esc($event['actor']) ?>
                                <?php endif; ?>
                            </strong>

                            <span class="activity-meta">
                                <?= esc($event['title']) ?>

                                <?php if (! empty($event['code'])): ?>
                                    · <?= esc($event['code']) ?>
                                <?php endif; ?>

                                · <?= esc(date('d.m.Y H:i', strtotime((string) $event['happened_at']))) ?>
                            </span>

                        </div>

                    </li>

                <?php endforeach; ?>

            </ul>

        <?php endif; ?>

    </div>

</section>


<?= $this->endSection() ?>
