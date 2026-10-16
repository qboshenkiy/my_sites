<?= $this->extend('layouts/dashboard') ?>
<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/chronos/css/import.css">
<?= $this->endSection() ?>
<?= $this->section('content') ?>
<section id="timeline-import" data-game-id="<?= (int) ($game['id'] ?? 0) ?>" data-preset="<?= $preset ? 'genesis' : '' ?>">
    <a href="<?= $game ? '/creator/edit/' . (int) $game['id'] : '/creator/games' ?>">← Вернуться к игре</a>
    <h2>Импорт хронологии</h2>
    <p>Вставьте JSON или выберите файл. Сначала проверьте карточки, затем подтвердите импорт.</p>
    <input id="import-csrf" type="hidden" name="<?= csrf_token() ?>" value="<?= csrf_hash() ?>">
    <?php if ($game): ?>
    <fieldset><legend>Куда добавить карточки?</legend>
        <label><input type="radio" name="import-mode" value="append" checked> В игру «<?= esc($game['title']) ?>» — существующие карточки сохранятся</label>
        <label><input type="radio" name="import-mode" value="new"> Создать отдельную игру</label>
    </fieldset>
    <label><input id="append-after" type="checkbox" checked> Добавить события после имеющихся. Если снять отметку, значения sort_order из JSON сохранятся.</label>
    <?php endif ?>
    <div class="timeline-actions">
        <label class="timeline-button">Выбрать JSON-файл <input id="json-file" type="file" accept=".json,application/json"></label>
        <button id="load-genesis" type="button">Бытие: 50 глав</button>
        <a href="/creator/genesis-json" download>Скачать пример JSON</a>
    </div>
    <label for="json-source">JSON (до 2 МБ, до 1000 карточек)</label>
    <textarea id="json-source" rows="14" spellcheck="false" placeholder='{"title":"Моя хронология","cards":[{"title":"Событие","sort_order":1,"reference":"Бытие 1:1"}]}'></textarea>
    <button id="check-json" type="button">Проверить JSON</button>
    <p id="import-message" role="status" aria-live="polite"></p>
    <section id="import-preview" hidden>
        <h3 id="preview-title"></h3>
        <p id="preview-description"></p>
        <div class="timeline-actions"><button id="select-import-all" type="button">Выбрать все</button><button id="select-import-none" type="button">Снять выбор</button><strong id="import-count"></strong></div>
        <div id="import-cards"></div>
        <button id="confirm-import" type="button">Подтвердить и импортировать</button>
    </section>
</section>
<?= $this->endSection() ?>
<?= $this->section('scripts') ?>
<script src="/assets/chronos/js/import.js"></script>
<?= $this->endSection() ?>
