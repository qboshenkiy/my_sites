<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/chronos/css/management.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>

<section class="management-page">

    <div class="management-heading">

        <div>

            <div class="section-label">
                АРХИВ
            </div>

            <h2>История игр</h2>

            <p>
                Завершённые партии, в которых вы участвовали.
                <?php if ($rooms !== []): ?>
                    Партий: <strong><?= count($rooms) ?></strong>
                    · Побед: <strong><?= (int) $wins ?></strong>
                <?php endif; ?>
            </p>

        </div>

    </div>


    <?php if ($rooms === []): ?>

        <div class="empty-state">

            <div class="empty-icon" aria-hidden="true">
                <?= icon('history', 40) ?>
            </div>

            <h4>Завершённых партий пока нет</h4>

            <p>
                Сыграйте партию до конца — она появится здесь
                вместе с результатом.
            </p>

            <a href="/rooms" class="secondary-btn">
                Перейти к комнатам
            </a>

        </div>

    <?php else: ?>

        <div class="data-table-wrap">

            <table class="data-table">

                <thead>
                    <tr>
                        <th>Игра</th>
                        <th>Код</th>
                        <th>Режим</th>
                        <th>Ведущий</th>
                        <th>Игроков</th>
                        <th>Мой счёт</th>
                        <th>Ошибок</th>
                        <th>Итог</th>
                        <th>Завершена</th>
                    </tr>
                </thead>

                <tbody>

                    <?php foreach ($rooms as $room): ?>

                        <?php $isWinner = (int) $room['winner_user_id'] === (int) $userId; ?>

                        <tr>

                            <td><?= esc($room['game_title']) ?></td>

                            <td>
                                <strong class="room-code">
                                    <?= esc($room['code']) ?>
                                </strong>
                            </td>

                            <td><?= esc(enum_label('game_mode', $room['game_mode'])) ?></td>

                            <td><?= esc($room['host_username']) ?></td>

                            <td>
                                <?= (int) $room['players_count'] ?>
                                / <?= (int) $room['max_players'] ?>
                            </td>

                            <td><?= (int) $room['my_score'] ?></td>

                            <td><?= (int) $room['my_mistakes'] ?></td>

                            <td>
                                <?php if ($isWinner): ?>
                                    <span class="status-badge status-production">
                                        Победа
                                    </span>
                                <?php elseif (! empty($room['winner_username'])): ?>
                                    <span class="status-badge status-finished">
                                        Победил <?= esc($room['winner_username']) ?>
                                    </span>
                                <?php else: ?>
                                    <span class="status-badge status-finished">
                                        Без победителя
                                    </span>
                                <?php endif; ?>
                            </td>

                            <td>
                                <?= esc(date(
                                    'd.m.Y H:i',
                                    strtotime((string) ($room['finished_at'] ?: $room['created_at']))
                                )) ?>
                            </td>

                        </tr>

                    <?php endforeach; ?>

                </tbody>

            </table>

        </div>

    <?php endif; ?>

</section>

<?= $this->endSection() ?>
