<?= $this->extend('layouts/auth') ?>
<?= $this->section('content') ?>
<main class="telegram-entry" id="telegram-entry" data-logged-in="<?= session()->get('logged_in') ? '1' : '0' ?>">
    <?= csrf_field() ?>
    <span class="game-emblem" aria-hidden="true">◷</span>
    <div class="section-label">CHRONO LOGOS · TELEGRAM</div>
    <h1>У каждого события<br>есть своё место.</h1>
    <p id="telegram-status" role="status">Подтверждаем вход через Telegram…</p>
    <div id="telegram-entry-actions" hidden>
        <button class="primary-action" type="button" data-telegram-action="create">Создать игровой профиль</button>
        <a class="secondary-action" href="/auth/login-page">У меня уже есть аккаунт</a>
        <small>После входа откройте «Профиль» и нажмите «Привязать Telegram».</small>
    </div>
    <a href="/games" class="telegram-browser-link">Открыть каталог игр</a>
</main>
<?= $this->endSection() ?>
