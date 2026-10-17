<section class="settings-card telegram-settings">
    <div class="section-label">TELEGRAM</div>
    <h3>Игра всегда под рукой</h3>
    <p>Открывайте Chrono Logos в отдельном игровом боте. Аккаунт и комнаты остаются общими с сайтом.</p>
    <?php if (!empty($user['telegram_id'])): ?>
        <p>Telegram привязан к этому аккаунту.</p>
        <button type="button" class="secondary-action" data-telegram-action="unlink">Отвязать Telegram</button>
        <small>Перед отвязкой задайте пароль в профиле, чтобы сохранить возможность входа.</small>
    <?php else: ?>
        <button type="button" class="primary-action" data-telegram-action="link">Привязать Telegram</button>
        <small>Откройте игру внутри Telegram, войдите в существующий аккаунт и нажмите эту кнопку.</small>
    <?php endif; ?>
    <?php if (preg_match('/^[A-Za-z0-9_]{5,32}$/D', (string)env('TELEGRAM_BOT_USERNAME', ''))): ?>
        <a class="secondary-action" href="https://t.me/<?= esc((string)env('TELEGRAM_BOT_USERNAME'), 'attr') ?>">Открыть игрового бота ↗</a>
    <?php endif; ?>
    <?php if (session()->get('role_code') === 'ADMIN'): ?>
        <hr><h3>Подключение бота</h3>
        <p>Сохраните токен нового бота в GitDeck, затем нажмите кнопку. Она настроит меню «Играть» и команды /start и /app.</p>
        <button type="button" class="primary-action" data-telegram-action="configure">Подключить игрового бота</button>
    <?php endif; ?>
    <p data-telegram-status role="status"></p>
</section>
