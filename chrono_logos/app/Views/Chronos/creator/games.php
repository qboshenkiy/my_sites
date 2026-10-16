<?= $this->extend('layouts/dashboard') ?>


<?= $this->section('styles') ?>

<link
    rel="stylesheet"
    href="/assets/chronos/css/my-games.css">

<?= $this->endSection() ?>


<?= $this->section('content') ?>


<div
    id="my-games"
    data-delete-url="/creator/delete-game"
>


    <input
        type="hidden"
        id="games-csrf"
        name="<?= csrf_token() ?>"
        value="<?= csrf_hash() ?>">


    <div class="games-header">

        <div>

            <div class="section-label">
                CREATOR
            </div>

            <h2>
                Мои игры
            </h2>

            <p>
                Создавайте и продолжайте редактирование своих игр.
            </p>

        </div>


        <form method="post" action="/creator/new" class="js-create-game-form create-game-form">
            <?= csrf_field() ?>
            <button type="submit" class="create-game-btn">+ СОЗДАТЬ ИГРУ</button>
        </form>

    </div>


    <?php if (empty($games)): ?>


        <div class="games-empty">

            <div class="games-empty-icon">
                <?= icon('book', 40) ?>
            </div>

            <h3>
                У вас пока нет игр
            </h3>

            <p>
                Создайте первую хронологическую игру
                и добавьте в неё карточки.
            </p>


            <form method="post" action="/creator/new" class="js-create-game-form create-game-form">
                <?= csrf_field() ?>
                <button type="submit" class="create-game-btn">+ СОЗДАТЬ ПЕРВУЮ ИГРУ</button>
            </form>

        </div>


    <?php else: ?>


        <div class="games-grid">


            <?php foreach ($games as $game): ?>


                <article
                    class="game-card"
                    data-game-id="<?= esc($game['id']) ?>"
                    data-game-title="<?= esc($game['title'], 'attr') ?>"
                    data-cards-count="<?= (int) $game['cards_count'] ?>"
                >


                    <div class="game-preview">


                        <?php if ($game['preview_src']): ?>

                            <img
                                src="<?= esc($game['preview_src']) ?>"
                                alt="<?= esc($game['title']) ?>"
                            >

                        <?php else: ?>

                            <div class="game-preview-empty">

                                <span>
                                    <?= icon('image', 26) ?>
                                </span>

                                <small>
                                    Нет изображения
                                </small>

                            </div>

                        <?php endif; ?>


                        <span class="game-status">
                            <?= esc(enum_label('game_status', $game['status'])) ?>
                        </span>


                    </div>


                    <div class="game-card-body">


                        <h3>
                            <?= esc($game['title']) ?>
                        </h3>


                        <?php if (! empty($game['description'])): ?>

                            <p class="game-description">
                                <?= esc($game['description']) ?>
                            </p>

                        <?php else: ?>

                            <p class="game-description empty">
                                Описание отсутствует
                            </p>

                        <?php endif; ?>


                        <div class="game-meta">


                            <div>

                                <span class="meta-value">
                                    <?= (int) $game['cards_count'] ?>
                                </span>

                                <span class="meta-label">
                                    карточек
                                </span>

                            </div>


                            <div>

                                <span class="meta-label">
                                    Изменено
                                </span>

                                <span class="meta-date">

                                    <?php if ($game['updated_at']): ?>

                                        <?= date(
                                            'd.m.Y H:i',
                                            strtotime($game['updated_at'])
                                        ) ?>

                                    <?php else: ?>

                                        —

                                    <?php endif; ?>

                                </span>

                            </div>


                        </div>


                        <div class="game-actions">


                            <a
                                href="<?= '/creator/edit/' . (int) $game['id'] ?>"
                                class="game-edit-btn"
                            >
                                РЕДАКТИРОВАТЬ
                            </a>


                            <button
                                type="button"
                                class="game-delete-btn"
                                title="Удалить игру"
                            >
                                <?= icon('close', 16) ?>
                            </button>


                        </div>


                    </div>


                </article>


            <?php endforeach; ?>


        </div>


    <?php endif; ?>


</div>


<?= $this->endSection() ?>


<?= $this->section('scripts') ?>

<script>
(() => {

    const root =
        document.getElementById('my-games');


    if (!root) {
        return;
    }


    const deleteUrl =
        root.dataset.deleteUrl;


    const csrf =
        document.getElementById('games-csrf');


    root.addEventListener(
        'click',
        async function(event) {

            const button =
                event.target.closest(
                    '.game-delete-btn'
                );


            if (!button) {
                return;
            }


            const card =
                button.closest(
                    '.game-card'
                );


            const gameId =
                card.dataset.gameId;


            const cardsCount =
                Number(card.dataset.cardsCount || 0);

            const gameTitle =
                card.dataset.gameTitle || 'эту игру';

            const confirmed = await confirmDialog({
                title: 'Удалить игру?',
                message: `«${gameTitle}» и все её карточки`
                    + ` (${cardsCount}) будут удалены безвозвратно.`,
                confirmText: 'Удалить',
                danger: true,
            });

            if (!confirmed) {
                return;
            }


            button.disabled = true;


            try {

                const formData =
                    new FormData();


                formData.append(
                    'game_id',
                    gameId
                );


                formData.append(
                    csrf.name,
                    csrf.value
                );


                const response =
                    await fetch(
                        deleteUrl,
                        {
                            method: 'POST',

                            body: formData,

                            headers: {
                                'X-Requested-With':
                                    'XMLHttpRequest'
                            }
                        }
                    );


                const data =
                    await response.json();


                /*
                 * Новый CSRF
                 */
                if (
                    data.csrfName
                    && data.csrfHash
                ) {

                    csrf.name =
                        data.csrfName;

                    csrf.value =
                        data.csrfHash;
                }


                if (!response.ok || !data.success) {

                    throw new Error(
                        data.message
                        ?? 'Ошибка удаления.'
                    );

                }


                card.remove();


                showAlert(
                    'success',
                    data.message
                );


                /*
                 * Если удалили последнюю игру —
                 * просто обновим страницу,
                 * чтобы появился empty state.
                 */
                if (
                    !document.querySelector(
                        '.game-card'
                    )
                ) {

                    const grid = document.querySelector('.games-grid');
                    if (grid) {
                        grid.outerHTML = `
                            <div class="games-empty">
                                <div class="games-empty-icon"><?= icon('book', 40) ?></div>
                                <h3>У вас пока нет игр</h3>
                                <p>Создайте первую хронологическую игру и добавьте в неё карточки.</p>
                                <small>Используйте кнопку «Создать игру» сверху.</small>
                            </div>`;
                    }

                }

            }
            catch (error) {

                console.error(error);

                showAlert(
                    'danger',
                    error.message
                );

                button.disabled = false;

            }

        }
    );

})();
</script>

<?= $this->endSection() ?>