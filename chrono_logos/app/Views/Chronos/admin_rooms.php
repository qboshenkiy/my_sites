<?= $this->extend('layouts/dashboard') ?>
<?= $this->section('styles') ?><link rel="stylesheet" href="/assets/chronos/css/management.css"><?= $this->endSection() ?>
<?= $this->section('content') ?>
<section class="management-page">
    <div class="management-heading"><div><div class="section-label">ADMIN</div><h2>Все комнаты</h2><p>Контроль активных и завершённых игровых комнат.</p></div></div>
    <form class="filter-bar" method="get" action="/admin/rooms">
        <input name="q" value="<?= esc($filters['q']) ?>" placeholder="Код, игра или ведущий">
        <select name="status"><option value="">Все статусы</option><?php foreach (['WAITING','PLAYING','FINISHED'] as $item): ?><option value="<?= $item ?>" <?= $filters['status'] === $item ? 'selected' : '' ?>><?= esc(enum_label('room_status', $item)) ?></option><?php endforeach; ?></select>
        <button type="submit">Фильтровать</button><a href="/admin/rooms">Сбросить</a>
    </form>
    <div class="data-table-wrap"><table class="data-table"><thead><tr><th>Код</th><th>Игра</th><th>Ведущий</th><th>Игроки</th><th>Статус</th><th>Создана</th><th></th></tr></thead><tbody>
    <?php if (empty($rooms)): ?><tr><td colspan="7" class="empty-cell">Комнаты не найдены</td></tr><?php endif; ?>
    <?php foreach ($rooms as $room): ?><tr><td><strong class="room-code"><?= esc($room['code']) ?></strong></td><td><?= esc($room['game_title']) ?></td><td><?= esc($room['host_username']) ?></td><td><?= (int) $room['players_count'] ?> / <?= (int) $room['max_players'] ?></td><td><?= enum_badge('room_status', $room['status']) ?></td><td><?= esc(date('d.m.Y H:i', strtotime($room['created_at']))) ?></td><td><a href="/rooms/show/<?= rawurlencode($room['code']) ?>">Открыть</a></td></tr><?php endforeach; ?>
    </tbody></table></div>
</section>
<?= $this->endSection() ?>
