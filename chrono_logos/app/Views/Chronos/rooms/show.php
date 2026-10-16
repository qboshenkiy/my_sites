<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/chronos/css/management.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>
<section
    class="room-lobby-page"
    id="room-lobby-root"
    data-room-code="<?= esc($room['code'], 'attr') ?>"
    data-state-url="<?= '/rooms/state/' . rawurlencode($room['code']) ?>"
    data-play-url="<?= '/rooms/play/' . rawurlencode($room['code']) ?>"
>

    <div class="room-lobby-head">
        <div>
            <div class="section-label">КОМНАТА <?= esc($room['code']) ?></div>
            <h2><?= esc($room['game_title']) ?></h2>
            <p>
                Ведущий: <?= esc($room['host_username']) ?> ·
                Режим: <?= esc(['NORMAL'=>'Обычный','BLIND'=>'Вслепую','HARDCORE'=>'Хардкор'][$room['game_mode'] ?? 'NORMAL'] ?? 'Обычный') ?>
            </p>
        </div>

        <a class="secondary-action" href="/rooms">
            Все комнаты
        </a>
    </div>

    <?php if ($room['status'] === 'WAITING'): ?>

        <div class="room-lobby-grid">
            <section class="room-lobby-panel">
                <div class="section-label">ИГРОКИ</div>
                <h3 id="lobby-player-count"><?= count($players) ?> / <?= (int) $room['max_players'] ?></h3>

                <div class="room-lobby-players" id="lobby-players">
                    <?php foreach ($players as $player): ?>
                        <div class="room-lobby-player">
                            <span><?= esc($player['username']) ?></span>
                            <?php if ((int) $player['user_id'] === (int) $room['host_user_id']): ?>
                                <small>Ведущий</small>
                            <?php endif; ?>
                        </div>
                    <?php endforeach; ?>
                </div>
            </section>

            <section class="room-lobby-panel room-lobby-invite">
                <div class="section-label">ПРИГЛАСИТЬ</div>
                <div class="room-lobby-code"><?= esc($room['code']) ?></div>

                <?php if (! empty($qrDataUri ?? null)): ?>
                    <img src="<?= esc($qrDataUri, 'attr') ?>" alt="QR-код комнаты">
                <?php endif; ?>

                <?= view('partials/room-share', ['room'=>$room,'joinUrl'=>$joinUrl,'shareId'=>'lobby']) ?>
            </section>
        </div>

        <div class="room-lobby-actions">
        <?php if ($isHost): ?>
                <form method="post" action="/rooms/start">
                    <?= csrf_field() ?>
                    <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                    <button type="submit" class="room-action-btn room-action-start">Начать игру</button>
                </form>

                <form
                    method="post"
                    action="/rooms/delete"
                >
                    <?= csrf_field() ?>
                    <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                    <button type="submit" class="room-action-btn room-action-delete">Удалить комнату</button>
                </form>
        <?php else: ?>
            <form method="post" action="/rooms/leave">
                <?= csrf_field() ?>
                <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                <button type="submit" class="room-action-btn room-action-secondary">Выйти из комнаты</button>
            </form>
        <?php endif; ?>
        </div>

    <?php else: ?>

        <section class="room-lobby-panel room-finished-panel">
            <div class="section-label">ИГРА ЗАВЕРШЕНА</div>
            <h3>Итоги партии</h3>

            <?php
                $resultPlayers = $players;
                usort(
                    $resultPlayers,
                    static fn($a, $b) =>
                        (int) $b['score'] <=> (int) $a['score']
                );

                $activeResults = array_values(array_filter(
                    $resultPlayers,
                    static fn($p) => ($p['player_status'] ?? 'ACTIVE') !== 'LEFT'
                ));

                $isTie = false;
                if (empty($room['winner_user_id']) && count($activeResults) > 1) {
                    $isTie = (int) $activeResults[0]['score']
                        === (int) $activeResults[1]['score'];
                }
            ?>

            <?php if (! empty($room['winner_user_id'])): ?>
                <?php
                    $winnerName = '';
                    foreach ($resultPlayers as $player) {
                        if ((int) $player['user_id'] === (int) $room['winner_user_id']) {
                            $winnerName = $player['username'];
                            break;
                        }
                    }
                ?>
                <div class="room-result-hero">
                    <span>ПОБЕДИТЕЛЬ</span>
                    <strong><?= esc($winnerName ?: 'Игрок') ?></strong>
                </div>
            <?php elseif ($isTie): ?>
                <div class="room-result-hero is-tie">
                    <span>РЕЗУЛЬТАТ</span>
                    <strong>Ничья</strong>
                </div>
            <?php endif; ?>

            <div class="room-lobby-players room-results-list">
                <?php foreach ($resultPlayers as $index => $player): ?>
                    <div class="room-lobby-player <?= ($player['player_status'] ?? '') === 'LEFT' ? 'is-left' : '' ?>">
                        <span>
                            <b><?= $index + 1 ?></b>
                            <?= esc($player['username']) ?>

                            <?php if (! empty($room['winner_user_id']) && (int) $room['winner_user_id'] === (int) $player['user_id']): ?>
                                <small>Победитель</small>
                            <?php elseif (($player['player_status'] ?? '') === 'LEFT'): ?>
                                <small>Вышел</small>
                            <?php elseif (($player['player_status'] ?? '') === 'ELIMINATED'): ?>
                                <small>Выбыл</small>
                            <?php endif; ?>
                        </span>

                        <strong>
                            <?= (int) $player['score'] ?> очк.
                            <?php if (($room['game_mode'] ?? '') === 'HARDCORE'): ?>
                                · <?= (int) ($player['mistakes'] ?? 0) ?> ошибок
                            <?php endif; ?>
                        </strong>
                    </div>
                <?php endforeach; ?>
            </div>

            <div class="room-lobby-actions room-finished-actions">
                <?php if ($isHost): ?>
                    <form
                        method="post"
                        action="/rooms/rematch"
                    >
                        <?= csrf_field() ?>
                        <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                        <button type="submit" class="room-action-btn room-action-start">Сыграть ещё</button>
                    </form>

                    <form
                        method="post"
                        action="/rooms/delete"
                    >
                        <?= csrf_field() ?>
                        <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                        <button type="submit" class="room-action-btn room-action-delete">Удалить комнату</button>
                    </form>
                <?php endif; ?>

                <a class="room-action-btn room-action-secondary" href="/rooms">
                    К списку комнат
                </a>
            </div>
        </section>

    <?php endif; ?>

</section>
<?= $this->endSection() ?>

<?= $this->section('scripts') ?>
<script src="/assets/chronos/js/room-share.js"></script>
<script>
(() => {
    const root = document.getElementById('room-lobby-root');
    if (!root) return;

    let lastStatus = null;
    let pollBusy = false;

    function updateCsrf(data) {
        if (!data?.csrfName || !data?.csrfHash) return;
        document.querySelectorAll(`input[name="${CSS.escape(data.csrfName)}"]`)
            .forEach(input => input.value = data.csrfHash);
    }

    function renderWaitingPlayers(data) {
        const list = document.getElementById('lobby-players');
        const count = document.getElementById('lobby-player-count');
        if (!list || !count) return;
        count.textContent = `${data.players.length} / ${data.room.maxPlayers}`;
        list.replaceChildren(...data.players
            .filter(player => player.status !== 'LEFT')
            .map(player => {
                const item = document.createElement('div');
                item.className = 'room-lobby-player';
                const name = document.createElement('span');
                name.textContent = player.username;
                item.appendChild(name);
                if (player.isHost) {
                    const badge = document.createElement('small');
                    badge.textContent = 'Ведущий';
                    item.appendChild(badge);
                }
                return item;
            }));
    }

    async function replaceLobbyMarkup() {
        try {
            const response = await fetch(window.location.pathname, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                cache: 'no-store',
                credentials: 'same-origin'
            });
            if (!response.ok) return;
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const fresh = doc.querySelector('#room-lobby-root');
            const current = document.querySelector('#room-lobby-root');
            if (fresh && current) current.innerHTML = fresh.innerHTML;
        } catch (error) {
            console.debug('Lobby markup refresh failed', error);
        }
    }

    async function refreshState() {
        if (pollBusy || document.hidden) return;
        pollBusy = true;
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                cache: 'no-store',
                credentials: 'same-origin'
            });
            const data = await response.json();
            if (!response.ok || !data.success) return;

            if (data.room.status === 'PLAYING') {
                window.location.assign(root.dataset.playUrl);
                return;
            }

            if (lastStatus !== null && lastStatus !== data.room.status) {
                await replaceLobbyMarkup();
            }
            lastStatus = data.room.status;

            if (data.room.status === 'WAITING') renderWaitingPlayers(data);
        } catch (error) {
            console.debug('Lobby state refresh failed', error);
        } finally {
            pollBusy = false;
        }
    }

    async function submitAction(form) {
        const button = form.querySelector('[type="submit"]');
        const oldText = button?.textContent;
        if (button) {
            button.disabled = true;
            button.textContent = 'Подождите…';
        }
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                credentials: 'same-origin'
            });
            const data = await response.json();
            updateCsrf(data);
            showAlert?.(data.type || (data.success ? 'success' : 'danger'), data.message || 'Готово.');
            if (!response.ok || !data.success) return;

            if (form.action.endsWith('/rooms/start') && data.redirect) {
                window.location.assign(data.redirect);
                return;
            }
            if (form.action.endsWith('/rooms/delete') || form.action.endsWith('/rooms/leave')) {
                window.location.assign(data.redirect || '/rooms');
                return;
            }
            if (form.action.endsWith('/rooms/rematch')) {
                lastStatus = null;
                await replaceLobbyMarkup();
                await refreshState();
            }
        } catch (error) {
            console.error(error);
            showAlert?.('danger', 'Не удалось связаться с сервером.');
        } finally {
            if (button && document.contains(button)) {
                button.disabled = false;
                button.textContent = oldText;
            }
        }
    }

    document.addEventListener('submit', async event => {
        const form = event.target.closest('#room-lobby-root form');
        if (!form) return;
        event.preventDefault();
        const destructive = form.action.endsWith('/rooms/delete');
        const rematch = form.action.endsWith('/rooms/rematch');

        if (destructive) {
            const confirmed = await confirmDialog({
                title: 'Удалить комнату?',
                message: 'Комната, её участники и ход партии будут удалены безвозвратно.',
                confirmText: 'Удалить',
            });
            if (!confirmed) return;
        }

        if (rematch) {
            const confirmed = await confirmDialog({
                title: 'Начать новую партию?',
                message: 'Текущий результат будет сброшен, игроки останутся в комнате.',
                confirmText: 'Подготовить',
                danger: false,
            });
            if (!confirmed) return;
        }

        submitAction(form);
    });


    refreshState();
    setInterval(refreshState, 1200);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) refreshState();
    });
})();
</script>
<?= $this->endSection() ?>
