<?php
$shareId = $shareId ?? 'room';
$shareText = 'Приглашаю в Chronologos: ' . ($room['game_title'] ?? 'Хронологическая игра') . '. Код комнаты: ' . $room['code'];
?>
<section class="room-share" data-room-share data-code="<?= esc($room['code'], 'attr') ?>" data-share-text="<?= esc($shareText, 'attr') ?>">
    <label for="room-link-<?= esc($shareId, 'attr') ?>">Ссылка-приглашение</label>
    <input id="room-link-<?= esc($shareId, 'attr') ?>" data-invite-url type="text" inputmode="url" readonly spellcheck="false" value="<?= esc($joinUrl, 'attr') ?>" aria-label="Ссылка для входа в комнату">
    <div class="room-share-actions">
        <button type="button" class="copy-code" data-room-copy="code">Копировать код</button>
        <button type="button" class="copy-invite-link" data-room-copy="link">Копировать ссылку</button>
        <button type="button" class="share-invite" data-room-send>Поделиться</button>
    </div>
    <div class="room-share-messengers">
        <a data-share-telegram href="<?= esc('https://t.me/share/url?url=' . rawurlencode($joinUrl) . '&text=' . rawurlencode($shareText), 'attr') ?>" target="_blank" rel="noopener noreferrer">Telegram ↗</a>
        <a data-share-whatsapp href="<?= esc('https://wa.me/?text=' . rawurlencode($shareText . "\n" . $joinUrl), 'attr') ?>" target="_blank" rel="noopener noreferrer">WhatsApp ↗</a>
    </div>
    <p class="room-share-status" data-share-status role="status" aria-live="polite"></p>
    <small>Новые игроки входят, пока партия не началась. В мессенджере выберите получателя и подтвердите отправку.</small>
</section>
