<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0, viewport-fit=cover"
    >
    <title><?= esc($room['game_title']) ?> | Проектор</title>
    <link
        rel="stylesheet"
        href="/assets/chronos/css/display.css"
    >
    <link rel="stylesheet" href="/assets/css/theme.css">
    <meta name="theme-color" content="#10131b">
    <link rel="manifest" href="/index.php?pwa=manifest">
    <link rel="stylesheet" href="/assets/css/game-world.css?v=20261017">
    <link rel="stylesheet" href="/assets/css/polish.css?v=20261027">
<link rel="stylesheet" href="/assets/ui.css?v=20261027"><script src="/assets/ui.js?v=20261027" data-ui-theme="chrono" defer></script></head>
<body>

<div
    id="display-root"
    class="display-root"
    data-state-url="<?= '/rooms/display-state/' . rawurlencode($room['code']) ?>"
>
    <header class="display-header">
        <div>
            <span class="display-eyebrow">
                ПРОЕКТОР
            </span>
            <h1>
                <?= esc($room['game_title']) ?>
            </h1>
        </div>

        <div class="display-header-stats">
            <div>
                <span>Комната</span>
                <strong><?= esc($room['code']) ?></strong>
            </div>
            <div>
                <span>Режим</span>
                <strong id="display-mode">—</strong>
            </div>
            <div>
                <span>Ход</span>
                <strong id="display-turn">—</strong>
            </div>
            <div>
                <span>Колода</span>
                <strong id="display-deck">—</strong>
            </div>
        </div>
    </header>

    <section
        id="display-players"
        class="display-players"
    ></section>

    <main class="projector-table">
        <section class="projector-turn">
            <span>Сейчас ход</span>
            <strong id="display-current">—</strong>
        </section>

        <section
            id="display-last-move"
            class="projector-last-move"
            hidden
        >
            <div
                id="display-last-image-wrap"
                class="projector-last-image"
                hidden
            >
                <img
                    id="display-last-image"
                    src=""
                    alt=""
                >
            </div>

            <div class="projector-last-body">
                <span id="display-last-player"></span>
                <strong id="display-last-title"></strong>
                <b id="display-last-result"></b>
                <em id="display-last-value"></em>
            </div>

            <button
                type="button"
                id="display-last-details"
            >
                Детали карты
            </button>
        </section>

        <section class="projector-timeline-shell">
            <div
                id="display-timeline"
                class="projector-timeline"
            ></div>
        </section>
    </main>

    <section
        id="display-finished"
        class="display-finished"
        hidden
    >
        <span>ИГРА ЗАВЕРШЕНА</span>
        <strong id="display-finished-title">—</strong>
        <small id="display-finished-subtitle"></small>
    </section>
</div>

<div
    id="display-card-modal"
    class="display-card-modal"
    hidden
>
    <button
        class="display-modal-backdrop"
        type="button"
        data-close-display-modal
        aria-label="Закрыть"
    ></button>

    <article class="display-modal-card">
        <button
            class="display-modal-close"
            type="button"
            data-close-display-modal
        >
            <?= icon('close', 20) ?>
        </button>

        <div
            id="display-modal-image-wrap"
            class="display-modal-image"
            hidden
        >
            <img
                id="display-modal-image"
                src=""
                alt=""
            >
        </div>

        <div class="display-modal-content">
            <span id="display-modal-meta"></span>
            <h2 id="display-modal-title"></h2>
            <p id="display-modal-description"></p>
            <strong id="display-modal-value"></strong>
        </div>
    </article>
</div>

<script>
(() => {
    const root =
        document.getElementById('display-root');

    const $ =
        id => document.getElementById(id);

    /* Заглушка для карты без изображения. Статичная разметка от icon(). */
    const PLACEHOLDER_ICON = `<?= icon('image', 30) ?>`;

    let lastMoveId =
        null;

    let lastMoveCard =
        null;

    const modal =
        $('display-card-modal');

    function openCard(card)
    {
        $('display-modal-title').textContent =
            card.title || 'Без названия';

        $('display-modal-description').textContent =
            card.shortDescription
            || 'Описание отсутствует.';

        $('display-modal-meta').textContent =
            [
                card.category,
                card.difficulty
            ]
                .filter(Boolean)
                .join(' · ');

        $('display-modal-value').textContent =
            card.revealedValue || '';

        const wrap =
            $('display-modal-image-wrap');

        const image =
            $('display-modal-image');

        if (card.imageSrc) {
            image.src =
                card.imageSrc;

            image.alt =
                card.title || '';

            wrap.hidden =
                false;
        } else {
            image.removeAttribute('src');
            wrap.hidden = true;
        }

        modal.hidden =
            false;
    }

    function closeModal()
    {
        modal.hidden =
            true;
    }

    document
        .querySelectorAll(
            '[data-close-display-modal]'
        )
        .forEach(
            element =>
                element.addEventListener(
                    'click',
                    closeModal
                )
        );

    document.addEventListener(
        'keydown',
        event => {
            if (event.key === 'Escape') {
                closeModal();
            }
        }
    );

    function buildPlayer(player, data)
    {
        const item =
            document.createElement('div');

        item.className =
            'projector-player';

        if (
            data.currentPlayer?.id
            === player.id
        ) {
            item.classList.add(
                'is-current'
            );
        }

        if (
            player.status
            === 'ELIMINATED'
        ) {
            item.classList.add(
                'is-eliminated'
            );
        }

        const name =
            document.createElement('strong');

        name.textContent =
            player.username;

        const info =
            document.createElement('span');

        let text =
            `${player.score} очк. · `
            + `${player.handCount} карт`;

        if (player.status === 'COMPLETED') {
            text = `Место ${player.finishRank} · ходов ${player.finishTurns} · ошибок ${player.mistakes}`;
        }

        if (
            data.room.gameMode
            === 'HARDCORE' && player.status !== 'COMPLETED'
        ) {
            text +=
                ` · ошибки ${player.mistakes}`
                + `/${data.room.mistakeLimit}`;
        }

        info.textContent =
            text;

        item.append(
            name,
            info
        );

        return item;
    }

    function buildCard(card)
    {
        const item =
            document.createElement('button');

        item.type =
            'button';

        item.className =
            'projector-card';

        if (card.imageSrc) {
            const image =
                document.createElement('img');

            image.src =
                card.imageSrc;

            image.alt =
                card.title || '';

            item.appendChild(image);
        } else {
            const empty =
                document.createElement('div');

            empty.className =
                'projector-card-empty';

            empty.innerHTML =
                PLACEHOLDER_ICON;

            item.appendChild(empty);
        }

        const body =
            document.createElement('div');

        body.className =
            'projector-card-body';

        const title =
            document.createElement('strong');

        title.textContent =
            card.title || 'Без названия';

        const value =
            document.createElement('span');

        value.textContent =
            card.revealedValue || 'Открыто';

        body.append(
            title,
            value
        );

        item.appendChild(body);

        item.addEventListener(
            'click',
            () => openCard(card)
        );

        return item;
    }

    function renderLastMove(move)
    {
        const panel =
            $('display-last-move');

        if (!move) {
            panel.hidden = true;
            lastMoveCard = null;
            return;
        }

        lastMoveCard = {
            title: move.cardTitle,
            shortDescription:
                move.shortDescription || '',
            imageSrc:
                move.imageSrc || null,
            category:
                move.category || null,
            difficulty:
                move.difficulty || null,
            revealedValue:
                move.revealedValue || null
        };

        $('display-last-player').textContent =
            `${move.username} сделал ход`;

        $('display-last-title').textContent =
            move.cardTitle || 'Карта';

        $('display-last-result').textContent =
            move.correct
                ? 'ВЕРНО'
                : 'НЕВЕРНО';

        $('display-last-result').className =
            move.correct
                ? 'is-good'
                : 'is-bad';

        $('display-last-value').textContent =
            move.revealedValue || '';

        const wrap =
            $('display-last-image-wrap');

        const image =
            $('display-last-image');

        if (move.imageSrc) {
            image.src =
                move.imageSrc;

            image.alt =
                move.cardTitle || '';

            wrap.hidden =
                false;
        } else {
            image.removeAttribute('src');
            wrap.hidden = true;
        }

        panel.hidden =
            false;

        if (
            lastMoveId !== null
            &&
            lastMoveId !== move.id
        ) {
            panel.classList.remove(
                'is-new'
            );

            void panel.offsetWidth;

            panel.classList.add(
                'is-new'
            );

            setTimeout(
                () =>
                    panel.classList.remove(
                        'is-new'
                    ),
                1000
            );
        }

        lastMoveId =
            move.id;
    }

    function render(data)
    {
        $('display-mode').textContent =
            data.room.gameMode || 'NORMAL';

        $('display-turn').textContent =
            String(
                data.room.turnNumber || 0
            );

        $('display-deck').textContent =
            String(
                data.deck?.remaining ?? 0
            );

        $('display-current').textContent =
            data.currentPlayer?.username
            || '—';

        $('display-players')
            .replaceChildren(
                ...(data.players || [])
                    .map(
                        player =>
                            buildPlayer(
                                player,
                                data
                            )
                    )
            );

        $('display-timeline')
            .replaceChildren(
                ...(data.timeline || [])
                    .map(buildCard)
            );

        renderLastMove(
            data.lastMove || null
        );

        const finished = $('display-finished');
        if (data.room.status === 'FINISHED') {
            finished.hidden = false;

            if (data.result?.winner) {
                $('display-finished-title').textContent =
                    data.result.winner;
                $('display-finished-subtitle').textContent =
                    'Победитель партии';
            } else if (data.result?.tie) {
                $('display-finished-title').textContent =
                    'Ничья';
                $('display-finished-subtitle').textContent =
                    (data.result.leaders || []).join(' · ');
            } else {
                $('display-finished-title').textContent =
                    'Партия завершена';
                $('display-finished-subtitle').textContent = '';
            }
        } else {
            finished.hidden = true;
        }
    }

    async function refresh()
    {
        try {
            const response =
                await fetch(
                    root.dataset.stateUrl,
                    {
                        headers: {
                            'X-Requested-With':
                                'XMLHttpRequest'
                        },
                        cache: 'no-store'
                    }
                );

            const data =
                await response.json();

            if (
                response.ok
                && data.success
            ) {
                render(data);
            }
        } catch (error) {
            console.debug(
                'Display refresh failed',
                error
            );
        }
    }

    $('display-last-details')
        ?.addEventListener(
            'click',
            () => {
                if (lastMoveCard) {
                    openCard(lastMoveCard);
                }
            }
        );

    refresh();

    setInterval(
        refresh,
        1300
    );
})();
</script>

<?= view('partials/telegram-assets') ?>
</body>
</html>
