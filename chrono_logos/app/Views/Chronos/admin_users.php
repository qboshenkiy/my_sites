<?= $this->extend('layouts/dashboard') ?>
<?= $this->section('styles') ?><link rel="stylesheet" href="/assets/chronos/css/management.css"><?= $this->endSection() ?>
<?= $this->section('content') ?>
<section class="management-page">
    <div class="management-heading"><div><div class="section-label">ADMIN</div><h2>Пользователи</h2><p>Поиск пользователей и назначение ролей.</p></div></div>
    <form class="filter-bar" method="get" action="/admin/users">
        <input name="q" value="<?= esc($filters['q']) ?>" placeholder="Логин или email">
        <select name="role"><option value="">Все роли</option><option value="USER" <?= $filters['role'] === 'USER' ? 'selected' : '' ?>>USER</option><option value="ADMIN" <?= $filters['role'] === 'ADMIN' ? 'selected' : '' ?>>ADMIN</option></select>
        <button type="submit">Фильтровать</button><a href="/admin/users">Сбросить</a>
    </form>
    <div class="data-table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Пользователь</th><th>Email</th><th>Роль</th><th>Регистрация</th><th>Изменить</th></tr></thead><tbody>
    <?php foreach ($users as $user): ?><tr>
        <td><?= (int) $user['id'] ?></td><td><strong><?= esc($user['username']) ?></strong></td><td><?= esc($user['email'] ?: '—') ?></td>
        <td><span class="status-badge <?= $user['role_code'] === 'ADMIN' ? 'status-production' : 'status-draft' ?>"><?= esc($user['role_code']) ?></span></td>
        <td><?= $user['created_at'] ? esc(date('d.m.Y', strtotime($user['created_at']))) : '—' ?></td>
        <td><form class="inline-form" method="post" action="/admin/set-user-role"><?= csrf_field() ?><input type="hidden" name="user_id" value="<?= (int) $user['id'] ?>"><select name="role"><option value="USER" <?= $user['role_code'] === 'USER' ? 'selected' : '' ?>>USER</option><option value="ADMIN" <?= $user['role_code'] === 'ADMIN' ? 'selected' : '' ?>>ADMIN</option></select><button type="submit">Сохранить</button></form></td>
    </tr><?php endforeach; ?>
    </tbody></table></div>
</section>
<?= $this->endSection() ?>
