<?= $this->extend('layouts/dashboard') ?>


<?= $this->section('styles') ?>

<link
    rel="stylesheet"
    href="/assets/chronos/css/creator.css">

<?= $this->endSection() ?>


<?= $this->section('content') ?>


<div
    id="creator-editor"

    data-game-id="<?= esc($game['id']) ?>"

    data-save-game="/creator/save-game"
    data-add-card="/creator/add-card"
    data-save-card="/creator/save-card"
    data-delete-card="/creator/delete-card"
    data-reorder-cards="/creator/reorder-cards"
    data-upload-card-image="/creator/upload-card-image"
    data-delete-card-image="/creator/delete-card-image">


    <input
        type="hidden"
        id="creator-csrf"
        name="<?= csrf_token() ?>"
        value="<?= csrf_hash() ?>">


    <div class="creator-toolbar">

        <div>
            <div class="section-label">
                CREATOR
            </div>

            <h2>
                Редактор игры
            </h2>
        </div>


        <div
            id="save-status"
            class="save-status saved">
            ● Сохранено
        </div>

    </div>


    <div class="creator-game-info">

        <div class="creator-field">

            <label>
                Название игры
            </label>

            <input
                type="text"
                id="game-title"
                maxlength="150"
                value="<?= esc($game['title']) ?>"
                placeholder="Например: История космонавтики">

        </div>


        <div class="creator-field">

            <label>
                Описание
            </label>

            <textarea
                id="game-description"
                rows="2"
                placeholder="Кратко расскажите об игре..."><?= esc($game['description'] ?? '') ?></textarea>

        </div>

    </div>

    <div class="timeline-actions">
        <a class="creator-add-btn" href="/creator/import-json?game_id=<?= (int) $game['id'] ?>">Добавить из JSON / другой книги</a>
        <a class="creator-add-btn" href="/creator/export-json/<?= (int) $game['id'] ?>">Скачать JSON</a>
    </div>
    <div class="creator-selection-toolbar">
        <input id="card-search" type="search" placeholder="Поиск: книга или событие" aria-label="Поиск по книге, событию или описанию">
        <select id="card-category" aria-label="Раздел"><option value="">Все разделы</option></select>
        <select id="card-state" aria-label="Состав игры"><option value="all">Все карточки</option><option value="on">Включённые</option><option value="off">Выключенные</option></select>
        <button type="button" id="include-visible">Включить показанные</button>
        <button type="button" id="exclude-visible">Выключить показанные</button>
        <strong id="selection-summary" aria-live="polite"></strong>
        <small>Выключенные карточки остаются в редакторе, но не попадают в новые партии. Уже начатые партии сохраняют свой состав. Разделы задаются полем «Категория».</small>
    </div>
    <div class="creator-view-toolbar">

        <div class="creator-view-switch">

            <button
                type="button"
                class="creator-view-btn active"
                data-view="table">
                <?= icon('table', 16) ?> Таблица
            </button>


            <button
                type="button"
                class="creator-view-btn"
                data-view="board">
                <?= icon('board', 16) ?> Стол
            </button>

        </div>


        <div class="creator-view-hint">

            Перетаскивайте карточки для изменения
            порядка в редакторе

        </div>

    </div>
    <div class="creator-cards-header">

        <div>

            <h3>
                Карточки
            </h3>

            <p>
                Изменения сохраняются автоматически.
            </p>

        </div>


        <button
            id="add-card"
            type="button"
            class="creator-add-btn">
            + ДОБАВИТЬ КАРТОЧКУ
        </button>

    </div>


    <div
        id="table-view"
        class="creator-view">

        <?php
        /*
         * Таблица шире контейнера. Обёртка-скроллер добавляет к ней градиентные
         * подсказки у краёв: без них колонки «Категория» и «Сложность» просто
         * не видно, и о том, что справа есть ещё поля, узнать неоткуда.
         */
        ?>
        <div class="creator-table-scroller">

        <span class="table-scroll-fade table-scroll-fade-left" aria-hidden="true"></span>
        <span class="table-scroll-fade table-scroll-fade-right" aria-hidden="true"></span>

        <div class="creator-table-wrap" id="creator-table-wrap">

            <table class="creator-table">

                <thead>

                    <tr>
                        <th></th>
                        <th>#</th><th>В игре</th>
                        <th>Название</th>
                        <th>Описание</th>
                        <th>Изображение</th>
                        <th>Порядок</th>
                        <th>Показать после ответа</th>
                        <th>Категория</th>
                        <th>Сложность</th>
                        <th></th>
                    </tr>

                </thead>


                <tbody id="cards-body">

                    <?php foreach ($cards as $index => $card): ?>
                        <?php

                        $imageSrc = ! empty($card['image_url'])
                            ? '/' . ltrim((string) $card['image_url'], '/')
                            : '';

                        ?>
                        <tr
                            class="card-row"

                            data-card-id="<?= esc($card['id']) ?>"

                            data-image-url="<?= esc($card['image_url'] ?? '') ?>"

                            data-image-src="<?= esc($imageSrc) ?>">

                            <td class="drag-cell">

                                <button
                                    type="button"
                                    class="drag-handle"
                                    title="Перетащить карточку">
                                    <?= icon('grip', 16) ?>
                                </button>

                            </td>


                            <td class="row-number">
                                <?= $index + 1 ?>
                            </td><td><input type="checkbox" class="card-included" aria-label="Включить карточку в игру" <?= in_array($card['is_enabled'] ?? true, [true, 1, '1', 't'], true) ? 'checked' : '' ?>></td>


                            <td>

                                <input
                                    data-field="title"
                                    type="text"
                                    value="<?= esc($card['title']) ?>"
                                    placeholder="Название события">

                            </td>


                            <td>

                                <input
                                    data-field="short_description"
                                    type="text"
                                    value="<?= esc($card['short_description'] ?? '') ?>"
                                    placeholder="Краткое описание">

                            </td>

                            <td class="card-image-cell">

                                <div
                                    class="card-image-dropzone"
                                    title="Нажмите или перетащите изображение">

                                    <div class="card-image-preview">

                                        <img
                                            class="card-image-thumb"
                                            src="<?= esc($imageSrc) ?>"
                                            alt=""
                                            <?= $imageSrc === '' ? 'hidden' : '' ?>>

                                        <span
                                            class="card-image-empty"
                                            <?= $imageSrc !== '' ? 'hidden' : '' ?>>
                                            <strong><?= icon('plus', 20) ?></strong>
                                            <span>Добавить фото</span>
                                            <small>или перетащите</small>
                                        </span>

                                        <div
                                            class="card-image-loading"
                                            hidden>
                                            Загрузка…
                                        </div>

                                    </div>

                                </div>


                                <input
                                    type="file"
                                    class="card-image-input"
                                    accept="image/jpeg,image/png,image/webp"
                                    hidden>


                                <div class="card-image-actions">

                                    <button
                                        type="button"
                                        class="card-image-button">
                                        <?= $imageSrc !== ''
                                            ? 'Заменить'
                                            : 'Выбрать' ?>
                                    </button>


                                    <button
                                        type="button"
                                        class="card-image-delete-button"
                                        <?= $imageSrc === ''
                                            ? 'hidden'
                                            : '' ?>
                                        title="Удалить изображение">
                                        <?= icon('close', 15) ?>
                                    </button>

                                </div>

                            </td>
                            <td>

                                <input
                                    data-field="sort_order"
                                    class="sort-order-input"
                                    type="text"
                                    inputmode="decimal"
                                    value="<?= esc($card['sort_order'] ?? '') ?>"
                                    placeholder="Порядок">
                            </td>


                            <td>

                                <input
                                    data-field="revealed_value"
                                    type="text"
                                    value="<?= esc($card['revealed_value'] ?? '') ?>"
                                    placeholder="Что показать после ответа">



                            </td>


                            <td>

                                <input
                                    data-field="category"
                                    type="text"
                                    value="<?= esc($card['category'] ?? '') ?>"
                                    placeholder="Категория">

                            </td>


                            <td>

                                <select data-field="difficulty">

                                    <?php foreach (
                                        ['EASY', 'NORMAL', 'HARD', 'EXPERT']
                                        as $difficulty
                                    ): ?>

                                        <option
                                            value="<?= $difficulty ?>"
                                            <?= ($card['difficulty'] ?? 'NORMAL') === $difficulty
                                                ? 'selected'
                                                : '' ?>>
                                            <?= esc(enum_label('difficulty', $difficulty)) ?>
                                        </option>

                                    <?php endforeach; ?>

                                </select>

                            </td>


                            <td>

                                <button
                                    type="button"
                                    class="delete-card-btn"
                                    title="Удалить">
                                    <?= icon('close', 16) ?>
                                </button>

                            </td>

                        </tr>

                    <?php endforeach; ?>

                </tbody>

            </table>

        </div>

        </div>

    </div>


    <!-- ВИЗУАЛЬНЫЙ СТОЛ -->

    <div
        id="board-view"
        class="creator-view is-hidden">

        <div
            id="cards-board"
            class="cards-board"></div>

    </div>


</div>


<?= $this->endSection() ?>


<?= $this->section('scripts') ?>

<script
    src="/assets/chronos/js/creator.js"></script>

<?= $this->endSection() ?>
