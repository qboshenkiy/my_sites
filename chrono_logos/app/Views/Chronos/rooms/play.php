<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= esc($title ?? 'Игра') ?></title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&display=swap">
    <link rel="stylesheet" href="/assets/chronos/css/game-play.css">
</head>
<body>

<?= view('partials/confirm-dialog') ?>

<div
    id="play-root"
    class="play-root"
    data-room-id="<?= (int) $room['id'] ?>"
    data-room-code="<?= esc($room['code'], 'attr') ?>"
    data-state-url="<?= '/rooms/state/' . rawurlencode($room['code']) ?>"
    data-place-url="/rooms/place"
    data-draw-url="/rooms/draw"
    data-lobby-url="<?= '/rooms/show/' . rawurlencode($room['code']) ?>"
>
    <input type="hidden" id="play-csrf" name="<?= csrf_token() ?>" value="<?= csrf_hash() ?>">

    <!--
      Минималистичный экран: постоянно на виду только стол (хронология),
      рука игрока и последний ход соперника. Всё остальное (комната,
      счёт, номер хода, выход) — в меню сбоку, скрытом по умолчанию,
      и на телефоне, и на десктопе (не только на мобильном брейкпоинте).
    -->
    <header class="play-bar">
        <button
            id="menu-toggle"
            class="menu-toggle"
            type="button"
            aria-label="Меню комнаты"
            aria-controls="game-menu"
            aria-expanded="false"
        >
            <?= icon('menu', 18) ?>
        </button>

        <div class="play-bar-turn">
            <strong id="current-player">—</strong>
            <em id="turn-message">Загружаем...</em>
        </div>

        <div class="play-bar-deck" title="Карт в колоде">
            <?= icon('library', 15) ?>
            <span id="deck-count">—</span>
        </div>
    </header>

    <button
        id="menu-overlay"
        class="menu-overlay"
        type="button"
        hidden
        aria-label="Закрыть меню"
    ></button>

    <aside id="game-menu" class="game-menu" hidden>
        <div class="game-menu-top">
            <a href="/rooms" class="play-back">← Комнаты</a>
            <button id="menu-close" type="button" class="menu-close" aria-label="Закрыть">
                <?= icon('close', 16) ?>
            </button>
        </div>

        <div class="game-menu-room">
            <span class="eyebrow"><?= esc($room['game_mode'] ?? 'NORMAL') ?></span>
            <h1><?= esc($room['game_title']) ?></h1>
        </div>

        <div class="game-menu-stats">
            <div><span>Комната</span><strong><?= esc($room['code']) ?></strong></div>
            <div><span>Ход</span><strong id="turn-number">—</strong></div>
        </div>

        <div class="game-menu-players" id="players-bar"></div>

        <div class="game-menu-actions">
            <?php if ($isHost): ?>
                <a
                    class="projector-link"
                    href="<?= '/rooms/display/' . rawurlencode($room['code']) ?>"
                    target="_blank"
                >Проектор ↗</a>
            <?php endif; ?>

            <form
                method="post"
                action="/rooms/leave"
                id="play-leave-form"
            >
                <?= csrf_field() ?>
                <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                <button type="submit" class="play-leave">Выйти из партии</button>
            </form>
        </div>
    </aside>

    <main class="game-table-shell">
        <section class="table-surface">
            <div class="table-nav-slim">
                <button id="timeline-prev" type="button" aria-label="Раньше">←</button>
                <span id="timeline-range">—</span>
                <button id="timeline-next" type="button" aria-label="Позже">→</button>
            </div>

            <div id="move-result" class="move-toast" hidden></div>

            <section
                id="live-move"
                class="live-move"
                hidden
            >
                <div
                    id="live-move-image-wrap"
                    class="live-move-image"
                    hidden
                >
                    <img
                        id="live-move-image"
                        src=""
                        alt=""
                    >
                </div>

                <div class="live-move-body">
                    <span id="live-move-player"></span>
                    <strong id="live-move-title"></strong>
                    <b id="live-move-result"></b>
                    <em id="live-move-value"></em>
                </div>

                <button
                    id="live-move-details"
                    type="button"
                >
                    Подробнее
                </button>
            </section>

            <div id="timeline" class="timeline-board"></div>
        </section>
    </main>

    <footer class="hand-dock">
        <div id="blind-draw" class="blind-draw" hidden>
            <span>Карта скрыта до момента вытягивания.</span>
            <button id="draw-button" type="button">Взять карту</button>
        </div>

        <div id="hand" class="hand-list"></div>

        <span id="hand-count" class="hand-count-badge">0 карт</span>
    </footer>
</div>

<div id="card-modal" class="card-modal" hidden>
    <button type="button" class="modal-backdrop" data-close-modal aria-label="Закрыть"></button>
    <article class="card-modal-card">
        <button type="button" class="modal-close" data-close-modal><?= icon('close', 18) ?></button>
        <div id="modal-image-wrap" class="modal-image-wrap" hidden>
            <img id="modal-image" src="" alt="">
        </div>
        <div class="modal-content">
            <span class="eyebrow" id="modal-meta"></span>
            <h2 id="modal-title"></h2>
            <p id="modal-description"></p>
            <strong id="modal-value" class="modal-value"></strong>
        </div>
    </article>
</div>

<script>
(() => {
    const root = document.getElementById('play-root');
    const $ = id => document.getElementById(id);

    /* Заглушка для карты без изображения. Статичная разметка от icon(). */
    const PLACEHOLDER_ICON = `<?= icon('image', 26) ?>`;

    const csrf = $('play-csrf');
    const timeline = $('timeline');
    const hand = $('hand');
    const modal = $('card-modal');
    const gameMenu = $('game-menu');
    const menuOverlay = $('menu-overlay');
    const menuToggle = $('menu-toggle');

    let state = null;
    let version = 0;
    let selectedCardId = null;
    let draggingCardId = null;
    let busy = false;
    let timelineStart = 0;
    let lastSeenMoveId = null;
    let lastMoveCard = null;
    let touchGhost = null;
    let touchDropZone = null;
    let suppressCardClickUntil = 0;

    /*
     * Сколько карт хронологии показывать одновременно — вычисляется из
     * реальной ширины #timeline, а не угадывается по window.innerWidth
     * фиксированными порогами (540/820/1150), которые раньше были
     * полностью независимы от CSS и не гарантировали, что столько карт
     * физически поместится. Константы CARD_.../ZONE_... — те же числа,
     * что в --gp-card-size/--gp-zone-size в game-play.css (см. там);
     * card/zone используют vw как в CSS (доля от ширины ОКНА, а не
     * контейнера), а вместимость делится на реальную ширину #timeline —
     * ровно так же CSS clamp(...,vw,...) резолвится внутри контейнера
     * с отступами.
     */
    const CARD_MIN = 100, CARD_VW = 0.22, CARD_MAX = 152;
    const ZONE_MIN = 28, ZONE_VW = 0.07, ZONE_MAX = 46;
    const clampSize = (min, vwFraction, max) =>
        Math.min(max, Math.max(min, window.innerWidth * vwFraction));

    let lastKnownTimelineWidth = 320;

    function timelineCapacity() {
        const containerWidth = timeline.clientWidth || lastKnownTimelineWidth || 320;
        lastKnownTimelineWidth = timeline.clientWidth || lastKnownTimelineWidth;

        const cardWidth = clampSize(CARD_MIN, CARD_VW, CARD_MAX);
        const zoneWidth = clampSize(ZONE_MIN, ZONE_VW, ZONE_MAX);

        /* n карт => n+1 зон (зона и перед первой картой, и после каждой). */
        const n = Math.floor((containerWidth - zoneWidth) / (cardWidth + zoneWidth));
        return Math.max(1, Math.min(9, n));
    }

    function openMenu() {
        gameMenu.hidden = false;
        menuOverlay.hidden = false;
        menuToggle.setAttribute('aria-expanded', 'true');
    }

    function closeMenu() {
        gameMenu.hidden = true;
        menuOverlay.hidden = true;
        menuToggle.setAttribute('aria-expanded', 'false');
    }

    menuToggle.addEventListener('click', () => {
        if (gameMenu.hidden) openMenu(); else closeMenu();
    });
    $('menu-close').addEventListener('click', closeMenu);
    menuOverlay.addEventListener('click', closeMenu);

    function openCard(card, revealed = false) {
        $('modal-title').textContent = card.title || 'Без названия';
        $('modal-description').textContent = card.shortDescription || 'Описание отсутствует.';
        $('modal-meta').textContent = [card.category, card.difficulty].filter(Boolean).join(' · ');
        $('modal-value').textContent = revealed && card.revealedValue ? card.revealedValue : '';

        const wrap = $('modal-image-wrap');
        const image = $('modal-image');
        if (card.imageSrc) {
            image.src = card.imageSrc;
            image.alt = card.title || '';
            wrap.hidden = false;
        } else {
            image.removeAttribute('src');
            wrap.hidden = true;
        }
        modal.hidden = false;
    }

    function closeModal() {
        modal.hidden = true;
    }

    modal.querySelectorAll('[data-close-modal]').forEach(el => el.addEventListener('click', closeModal));
    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        closeModal();
        closeMenu();
    });

    function buildTableCard(card) {
        const el = document.createElement('article');
        el.className = 'square-card table-card';
        if (card.wasMisplaced) el.classList.add('is-misplaced');
        el.tabIndex = 0;

        const media = document.createElement('div');
        media.className = 'square-card-media';
        if (card.imageSrc) {
            const img = document.createElement('img');
            img.src = card.imageSrc;
            img.alt = card.title || '';
            media.appendChild(img);
        } else {
            media.innerHTML = PLACEHOLDER_ICON;
        }
        if (card.wasMisplaced) {
            const badge = document.createElement('span');
            badge.className = 'misplaced-badge';
            badge.textContent = 'Сыграно неверно';
            media.appendChild(badge);
        }

        const body = document.createElement('div');
        body.className = 'square-card-body';
        const title = document.createElement('strong');
        title.textContent = card.title || 'Без названия';
        const value = document.createElement('span');
        value.textContent = card.revealedValue || 'Открыто';
        body.append(title, value);
        el.append(media, body);

        el.addEventListener('click', () => openCard(card, true));
        el.addEventListener('keydown', e => { if (e.key === 'Enter') openCard(card, true); });
        return el;
    }

    function buildDropZone(position, enabled) {
        const zone = document.createElement('button');
        zone.type = 'button';
        zone.className = 'drop-zone';
        zone.dataset.position = String(position);
        zone.disabled = !enabled;
        zone.innerHTML = '<span>Поставить сюда</span>';

        zone.addEventListener('dragover', event => {
            if (!enabled) return;
            event.preventDefault();
            zone.classList.add('is-over');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('is-over'));
        zone.addEventListener('drop', event => {
            if (!enabled) return;
            event.preventDefault();
            zone.classList.remove('is-over');
            const id = Number(event.dataTransfer.getData('text/plain') || draggingCardId || selectedCardId);
            if (id) placeCard(position, id);
        });
        zone.addEventListener('click', () => {
            if (enabled && selectedCardId) placeCard(position, selectedCardId);
        });
        return zone;
    }

    function renderTimeline() {
        const cards = state?.timeline || [];
        const size = timelineCapacity();
        timeline.replaceChildren();
        const maxStart = Math.max(0, cards.length - size);
        timelineStart = Math.max(0, Math.min(timelineStart, maxStart));
        const visible = cards.slice(timelineStart, timelineStart + size);
        const enabled = !!(state?.isMyTurn && selectedCardId && !busy);

        timeline.appendChild(buildDropZone(timelineStart, enabled));
        visible.forEach((card, index) => {
            timeline.appendChild(buildTableCard(card));
            timeline.appendChild(buildDropZone(timelineStart + index + 1, enabled));
        });

        $('timeline-range').textContent = cards.length
            ? `${timelineStart + 1}–${timelineStart + visible.length} из ${cards.length}`
            : 'Нет карт';
        $('timeline-prev').disabled = timelineStart <= 0;
        $('timeline-next').disabled = timelineStart >= maxStart;
    }

    function buildHandCard(card, canPlay) {
        const el = document.createElement('article');
        el.className = 'square-card hand-card';
        el.draggable = canPlay;
        if (selectedCardId === card.id) el.classList.add('is-selected');

        const media = document.createElement('button');
        media.type = 'button';
        media.className = 'square-card-media hand-card-media';
        media.title = 'Открыть детали карты';
        if (card.imageSrc) {
            const img = document.createElement('img');
            img.src = card.imageSrc;
            img.alt = card.title || '';
            media.appendChild(img);
        } else {
            media.innerHTML = PLACEHOLDER_ICON;
        }
        media.addEventListener('click', event => {
            event.stopPropagation();
            openCard(card, false);
        });

        const body = document.createElement('div');
        body.className = 'square-card-body';
        const title = document.createElement('strong');
        title.textContent = card.title || 'Без названия';
        const meta = document.createElement('span');
        meta.textContent = [card.category, card.difficulty].filter(Boolean).join(' · ');
        body.append(title, meta);
        el.append(media, body);

        el.addEventListener('click', () => {
            if (Date.now() < suppressCardClickUntil) {
                return;
            }

            if (!canPlay) {
                openCard(card, false);
                return;
            }
            selectedCardId = card.id;
            renderHand();
            renderTimeline();
        });

        el.addEventListener('dragstart', event => {
            if (!canPlay) {
                event.preventDefault();
                return;
            }
            selectedCardId = card.id;
            draggingCardId = card.id;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', String(card.id));
            el.classList.add('is-dragging');
            renderTimeline();
        });
        el.addEventListener('dragend', () => {
            draggingCardId = null;
            el.classList.remove('is-dragging');
            renderTimeline();
        });

        installTouchDrag(el, card, canPlay);

        return el;
    }

    function installTouchDrag(element, card, canPlay)
    {
        if (!canPlay) {
            return;
        }

        let timer = null;
        let active = false;
        let startX = 0;
        let startY = 0;

        const clearZone = () => {
            if (touchDropZone) {
                touchDropZone.classList.remove('is-over');
                touchDropZone = null;
            }
        };

        const stop = () => {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }

            clearZone();

            if (touchGhost) {
                touchGhost.remove();
                touchGhost = null;
            }

            if (active) {
                element.classList.remove('is-dragging');
                active = false;
                suppressCardClickUntil = Date.now() + 350;
            }
        };

        element.addEventListener('pointerdown', event => {
            if (
                busy
                || !state?.isMyTurn
                || (event.pointerType !== 'touch' && event.pointerType !== 'pen')
            ) {
                return;
            }

            startX = event.clientX;
            startY = event.clientY;

            timer = setTimeout(() => {
                active = true;
                selectedCardId = card.id;
                draggingCardId = card.id;
                element.classList.add('is-dragging');

                touchGhost = element.cloneNode(true);
                touchGhost.classList.add('touch-drag-ghost');
                touchGhost.style.left = `${event.clientX}px`;
                touchGhost.style.top = `${event.clientY}px`;
                document.body.appendChild(touchGhost);

                renderTimeline();

                if (navigator.vibrate) {
                    navigator.vibrate(25);
                }
            }, 260);
        });

        element.addEventListener('pointermove', event => {
            if (timer && !active) {
                const distance = Math.hypot(
                    event.clientX - startX,
                    event.clientY - startY
                );

                if (distance > 12) {
                    clearTimeout(timer);
                    timer = null;
                }
                return;
            }

            if (!active || !touchGhost) {
                return;
            }

            event.preventDefault();

            touchGhost.style.left = `${event.clientX}px`;
            touchGhost.style.top = `${event.clientY}px`;

            touchGhost.style.display = 'none';
            const target = document.elementFromPoint(
                event.clientX,
                event.clientY
            );
            touchGhost.style.display = '';

            const zone = target?.closest('.drop-zone:not(:disabled)') || null;

            if (zone !== touchDropZone) {
                clearZone();
                touchDropZone = zone;
                touchDropZone?.classList.add('is-over');
            }
        }, {passive: false});

        element.addEventListener('pointerup', event => {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }

            if (!active) {
                return;
            }

            const zone = touchDropZone;
            const position = zone
                ? Number(zone.dataset.position)
                : null;

            stop();
            draggingCardId = null;

            if (Number.isInteger(position)) {
                placeCard(position, card.id);
            } else {
                renderTimeline();
            }
        });

        element.addEventListener('pointercancel', () => {
            stop();
            draggingCardId = null;
            renderTimeline();
        });
    }


    function renderHand() {
        const cards = state?.myHand || [];
        const canPlay = !!state?.isMyTurn;

        if (selectedCardId && !cards.some(card => card.id === selectedCardId)) {
            selectedCardId = null;
        }

        $('hand-count').textContent = `${cards.length} карт`;
        $('blind-draw').hidden = !(state?.room?.gameMode === 'BLIND' && state?.isMyTurn && cards.length === 0);
        $('draw-button').disabled = !state?.canDraw || busy;

        if (!cards.length) {
            const empty = document.createElement('div');
            empty.className = 'hand-empty';
            empty.textContent = state?.canDraw ? 'Вытяните карту.' : 'В руке нет карт.';
            hand.replaceChildren(empty);
            return;
        }

        hand.replaceChildren(...cards.map(card => buildHandCard(card, canPlay)));
    }

    function renderPlayers() {
        const players = state?.players || [];
        $('players-bar').replaceChildren(...players.map(player => {
            const el = document.createElement('div');
            el.className = 'player-pill';
            if (state?.currentPlayer?.id === player.id) el.classList.add('is-current');
            if (player.status === 'ELIMINATED') el.classList.add('is-eliminated');

            const name = document.createElement('strong');
            name.textContent = player.username;
            const info = document.createElement('span');
            let text = `${player.score} очк. · ${player.handCount} карт`;
            if (state?.room?.gameMode === 'HARDCORE') {
                text += ` · ошибки ${player.mistakes}/${state.room.mistakeLimit}`;
            }
            if (player.isOnline === false && player.status === 'ACTIVE') {
                text += ' · офлайн';
                el.classList.add('is-offline');
            }
            info.textContent = text;
            el.append(name, info);
            return el;
        }));
    }

    function renderLiveMove(move)
    {
        const panel =
            $('live-move');

        if (!move) {
            panel.hidden = true;
            lastMoveCard = null;
            return;
        }

        lastMoveCard = {
            title:
                move.cardTitle,
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

        $('live-move-player').textContent =
            `${move.username} сыграл карту`;

        $('live-move-title').textContent =
            move.cardTitle || 'Карта';

        $('live-move-result').textContent =
            move.correct
                ? 'ВЕРНО'
                : 'НЕВЕРНО';

        $('live-move-result').className =
            move.correct
                ? 'is-good'
                : 'is-bad';

        $('live-move-value').textContent =
            move.revealedValue || '';

        const wrap =
            $('live-move-image-wrap');

        const image =
            $('live-move-image');

        if (move.imageSrc) {
            image.src =
                move.imageSrc;

            image.alt =
                move.cardTitle || '';

            wrap.hidden =
                false;
        } else {
            image.removeAttribute(
                'src'
            );

            wrap.hidden =
                true;
        }

        panel.hidden =
            false;

        if (
            lastSeenMoveId !== null
            &&
            lastSeenMoveId !== move.id
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
                850
            );
        }

        lastSeenMoveId =
            move.id;
    }


    function renderState(data) {
        state = data;
        version = data.room.stateVersion;

        if (data.room.status !== 'PLAYING') {
            window.location.assign(root.dataset.lobbyUrl);
            return;
        }

        $('turn-number').textContent = data.room.turnNumber;
        $('deck-count').textContent = data.deck?.remaining ?? 0;
        $('current-player').textContent = data.currentPlayer?.username || '—';

        if (data.isMyTurn) {
            if (data.room.gameMode === 'BLIND' && data.canDraw) {
                $('turn-message').textContent = 'Ваш ход — вытяните карту';
            } else {
                $('turn-message').textContent = 'Ваш ход';
            }
        } else {
            $('turn-message').textContent = 'Ход другого игрока';
        }

        renderPlayers();
        renderHand();
        renderTimeline();
        renderLiveMove(data.lastMove || null);
    }

    async function refresh() {
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                cache: 'no-store'
            });
            const data = await response.json();
            if (response.ok && data.success) renderState(data);
        } catch (error) {
            console.debug(error);
        }
    }

    function updateCsrf(data) {
        if (data.csrfName && data.csrfHash) {
            csrf.name = data.csrfName;
            csrf.value = data.csrfHash;
        }
    }

    function showResult(data) {
        const toast = $('move-result');
        toast.hidden = false;
        toast.className = 'move-toast ' + (data.correct ? 'is-good' : 'is-bad');
        toast.textContent = data.message || (data.correct ? 'Верно' : 'Неверно');
        setTimeout(() => toast.hidden = true, 3000);
    }

    async function placeCard(position, cardId) {
        if (busy || !state?.isMyTurn || !cardId) return;
        busy = true;
        renderTimeline();

        const body = new FormData();
        body.append('room_id', root.dataset.roomId);
        body.append('room_card_id', String(cardId));
        body.append('chosen_position', String(position));
        body.append('state_version', String(version));
        body.append(csrf.name, csrf.value);

        try {
            const response = await fetch(root.dataset.placeUrl, {
                method: 'POST',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                body
            });
            const data = await response.json();
            updateCsrf(data);
            if (!response.ok || !data.success) {
                alert(data.message || 'Не удалось выполнить ход.');
                await refresh();
                return;
            }
            selectedCardId = null;
            showResult(data);
            await refresh();
        } catch (error) {
            alert('Не удалось связаться с сервером.');
        } finally {
            busy = false;
            if (state) {
                renderHand();
                renderTimeline();
            }
        }
    }

    async function drawCard() {
        if (busy || !state?.canDraw) return;
        busy = true;

        const body = new FormData();
        body.append('room_id', root.dataset.roomId);
        body.append('state_version', String(version));
        body.append(csrf.name, csrf.value);

        try {
            const response = await fetch(root.dataset.drawUrl, {
                method: 'POST',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                body
            });
            const data = await response.json();
            updateCsrf(data);
            if (!response.ok || !data.success) {
                alert(data.message || 'Не удалось взять карту.');
                return;
            }
            await refresh();
        } finally {
            busy = false;
        }
    }

    $('live-move-details')?.addEventListener(
        'click',
        () => {
            if (lastMoveCard) {
                openCard(
                    lastMoveCard,
                    true
                );
            }
        }
    );

    document.getElementById('play-leave-form')?.addEventListener('submit', async event => {
        event.preventDefault();
        const confirmed = await confirmDialog({
            title: 'Выйти из партии?',
            message: 'Ваша рука вернётся в колоду, а ход перейдёт следующему игроку.',
            confirmText: 'Выйти',
        });
        if (!confirmed) return;
        const form = event.currentTarget;
        const button = form.querySelector('[type="submit"]');
        if (button) button.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                credentials: 'same-origin'
            });
            const data = await response.json();
            updateCsrf(data);
            if (!response.ok || !data.success) {
                alert(data.message || 'Не удалось выйти из игры.');
                return;
            }
            window.location.assign(data.redirect || '/rooms');
        } catch (error) {
            alert('Не удалось связаться с сервером.');
        } finally {
            if (button) button.disabled = false;
        }
    });

    $('draw-button').addEventListener('click', drawCard);
    $('timeline-prev').addEventListener('click', () => {
        timelineStart = Math.max(0, timelineStart - timelineCapacity());
        renderTimeline();
    });
    $('timeline-next').addEventListener('click', () => {
        timelineStart += timelineCapacity();
        renderTimeline();
    });

    /*
     * ResizeObserver на сам #timeline — ловит изменения его реальной
     * ширины (в т.ч. от dvh/схлопывания адресной строки браузера), а не
     * только событие resize окна. window.resize оставлен доп. триггером:
     * cardWidth/zoneWidth считаются от window.innerWidth (как vw в CSS),
     * так что могут поменяться и без изменения ширины самого контейнера
     * (например, при повороте экрана).
     */
    if (typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(() => renderTimeline()).observe(timeline);
    }
    window.addEventListener('resize', renderTimeline);

    refresh();
    setInterval(refresh, 1600);
})();
</script>
</body>
</html>
