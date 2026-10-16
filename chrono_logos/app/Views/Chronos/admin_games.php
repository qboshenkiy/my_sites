<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/chronos/css/management.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>
<section class="management-page">
    <div class="management-heading">
        <div>
            <div class="section-label">ADMIN</div>
            <h2>Все игры</h2>
            <p>Поиск, проверка и публикация игр всех пользователей.</p>
        </div>
        <form method="post" action="/creator/new" class="js-create-game-form create-game-form">
            <?= csrf_field() ?>
            <button type="submit" class="primary-action">+ СОЗДАТЬ ИГРУ</button>
        </form>
    </div>

    <form class="filter-bar" method="get" action="/admin/games">
        <input name="q" value="<?= esc($filters['q']) ?>" placeholder="Название или описание">
        <input name="owner" value="<?= esc($filters['owner']) ?>" placeholder="Автор">
        <select name="status">
            <option value="">Все статусы</option>
            <option value="DRAFT" <?= $filters['status'] === 'DRAFT' ? 'selected' : '' ?>>Черновики</option>
            <option value="PRODUCTION" <?= $filters['status'] === 'PRODUCTION' ? 'selected' : '' ?>>Опубликованные</option>
        </select>
        <button type="submit">Фильтровать</button>
        <a href="/admin/games">Сбросить</a>
    </form>

    <div class="data-table-wrap">
        <table class="data-table">
            <thead>
            <tr><th>ID</th><th>Игра</th><th>Автор</th><th>Карточек</th><th>Статус</th><th>Изменена</th><th>Действия</th></tr>
            </thead>
            <tbody>
            <?php if (empty($games)): ?>
                <tr><td colspan="7" class="empty-cell">Игры не найдены</td></tr>
            <?php endif; ?>
            <?php foreach ($games as $game): ?>
                <tr>
                    <td><?= (int) $game['id'] ?></td>
                    <td><strong><?= esc($game['title']) ?></strong></td>
                    <td><?= esc($game['owner_username']) ?></td>
                    <td><?= (int) $game['cards_count'] ?></td>
                    <td><?= enum_badge('game_status', $game['status']) ?></td>
                    <td><?= $game['updated_at'] ? esc(date('d.m.Y H:i', strtotime($game['updated_at']))) : '—' ?></td>
                    <td class="row-actions">
                        <a href="/creator/edit/<?= (int) $game['id'] ?>">Редактировать</a>
                        <form method="post" action="/admin/set-game-status">
                            <?= csrf_field() ?>
                            <input type="hidden" name="game_id" value="<?= (int) $game['id'] ?>">
                            <input type="hidden" name="status" value="<?= $game['status'] === 'PRODUCTION' ? 'DRAFT' : 'PRODUCTION' ?>">
                            <button type="submit"><?= $game['status'] === 'PRODUCTION' ? 'Снять' : 'Опубликовать' ?></button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</section>
<?= $this->endSection() ?>
