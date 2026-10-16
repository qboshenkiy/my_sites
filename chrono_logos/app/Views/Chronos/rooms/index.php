<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/chronos/css/management.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>

<section class="management-page">

    <div class="management-heading">
        <div>
            <div class="section-label">PLAY</div>
            <h2>Игровые комнаты</h2>
            <p>
                Создайте комнату по опубликованной игре
                или войдите по коду.
            </p>
        </div>
    </div>


    <div class="form-grid">

        <form
            class="panel-form"
            method="post"
            action="/rooms/create"
            id="create-room-form"
        >
            <?= csrf_field() ?>

            <h3>Новая комната</h3>

            <?php if (empty($games)): ?>

                <p>
                    Пока нет опубликованных игр.
                    Администратор должен опубликовать
                    хотя бы одну.
                </p>

            <?php else: ?>

                <label>
                    Игра

                    <select name="game_id" required>
                        <?php foreach ($games as $game): ?>
                            <option
                                value="<?= (int) $game['id'] ?>"
                            >
                                <?= esc($game['title']) ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                </label>


                <label>
                    Режим

                    <select
                        name="game_mode"
                        id="game-mode"
                        required
                    >
                        <option value="NORMAL">
                            Обычный
                        </option>

                        <option value="BLIND">
                            Вслепую
                        </option>

                        <option value="HARDCORE">
                            Хардкор
                        </option>
                    </select>
                </label>


                <label>
                    Максимум игроков

                    <input
                        type="number"
                        name="max_players"
                        min="2"
                        max="20"
                        value="8"
                        required
                    >
                </label>


                <label>
                    Карт каждому

                    <input
                        type="number"
                        name="cards_per_player"
                        min="1"
                        max="20"
                        value="5"
                        required
                    >
                </label>


                <label
                    id="mistake-limit-field"
                    hidden
                >
                    Ошибок до выбывания

                    <input
                        type="number"
                        name="mistake_limit"
                        min="1"
                        max="3"
                        value="3"
                    >
                </label>


                <label>
                    Если колода закончилась, а штраф не сыграть

                    <select name="empty_deck_behavior">
                        <option value="GRACE">
                            Один круг без штрафа, потом выбывание
                        </option>

                        <option value="SKIP">
                            Штраф просто пропускается
                        </option>
                    </select>
                </label>


                <div
                    id="mode-description"
                    class="room-mode-description mode-info-card"
                    role="status"
                    aria-live="polite"
                >
                    Обычный режим:
                    у каждого игрока есть своя рука карт.
                    Выберите карту и поставьте её
                    в правильное место хронологии.
                </div>


                <button type="submit">
                    Создать комнату
                </button>

            <?php endif; ?>

        </form>


        <form
            class="panel-form"
            method="post"
            action="/rooms/join"
            id="join-room-form"
        >
            <?= csrf_field() ?>

            <h3>Войти по коду</h3>

            <label>
                Код комнаты

                <input
                    class="room-code-input"
                    name="code"
                    minlength="6"
                    maxlength="6"
                    pattern="[A-Za-z0-9]{6}"
                    required
                    placeholder="ABC123"
                >
            </label>

            <button type="submit">
                Войти
            </button>

        </form>

    </div>


    <h3 class="subheading">
        Мои комнаты
    </h3>


    <div class="room-list">

        <?php if (empty($rooms)): ?>

            <div class="empty-card">
                У вас пока нет игровых комнат.
            </div>

        <?php endif; ?>


        <?php foreach ($rooms as $room): ?>

            <div class="room-list-item">
                <a
                    class="room-card"
                    href="<?= ($room['status'] === 'PLAYING' ? '/rooms/play/' : '/rooms/show/') . rawurlencode($room['code']) ?>"
                >
                    <span class="room-code">
                        <?= esc($room['code']) ?>
                    </span>

                    <strong>
                        <?= esc($room['game_title']) ?>
                    </strong>

                    <span>
                        <?= esc($room['game_mode'] ?? 'NORMAL') ?> ·
                        <?= (int) $room['players_count'] ?> /
                        <?= (int) $room['max_players'] ?> игроков
                    </span>

                    <span>
                        Ведущий: <?= esc($room['host_username']) ?>
                    </span>

                    <?= enum_badge('room_status', $room['status']) ?>
                </a>

                <?php if (
                    (int) $room['host_user_id']
                    ===
                    (int) session()->get('user_id')
                    || session()->get('role_code') === 'ADMIN'
                ): ?>
                    <form
                        class="room-delete-form"
                        method="post"
                        action="/rooms/delete"
                    >
                        <?= csrf_field() ?>
                        <input type="hidden" name="room_id" value="<?= (int) $room['id'] ?>">
                        <button type="submit" class="room-delete-button" title="Удалить комнату"><?= icon('close', 15) ?></button>
                    </form>
                <?php endif; ?>
            </div>

        <?php endforeach; ?>

    </div>

</section>

<?= $this->endSection() ?>


<?= $this->section('scripts') ?>

<script>
(() => {
    const mode = document.getElementById('game-mode');
    const mistakeField = document.getElementById('mistake-limit-field');
    const description = document.getElementById('mode-description');
    const roomList = document.querySelector('.room-list');

    const descriptions = {
        NORMAL: {
            title: 'Обычный режим',
            text: 'У каждого игрока есть своя рука карт. Выберите карту и поставьте её в правильное место хронологии.'
        },
        BLIND: {
            title: 'Режим «Вслепую»',
            text: 'Карта заранее скрыта. Во время своего хода игрок вытягивает одну карту, узнаёт её и затем ставит на стол.'
        },
        HARDCORE: {
            title: 'Хардкор',
            text: 'Ошибки считаются. После выбранного лимита игрок выбывает, а оставшиеся карты его руки возвращаются в колоду.'
        }
    };

    function updateModeUi() {
        if (!mode || !description) return;
        if (mistakeField) mistakeField.hidden = mode.value !== 'HARDCORE';
        const item = descriptions[mode.value] || descriptions.NORMAL;
        description.innerHTML = `<strong>${item.title}</strong><span>${item.text}</span>`;
        description.dataset.mode = mode.value;
    }

    mode?.addEventListener('change', updateModeUi);
    updateModeUi();

    function updateCsrf(data) {
        if (!data?.csrfName || !data?.csrfHash) return;
        document.querySelectorAll(`input[name="${CSS.escape(data.csrfName)}"]`)
            .forEach(input => input.value = data.csrfHash);
    }

    async function submitAsync(form) {
        const button = form.querySelector('[type="submit"]');
        const oldText = button?.textContent;
        if (button) {
            button.disabled = true;
            button.textContent = 'Подождите…';
        }

        try {
            const response = await fetch(form.action, {
                method: form.method || 'POST',
                body: new FormData(form),
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                credentials: 'same-origin'
            });
            const data = await response.json();
            updateCsrf(data);
            showAlert?.(data.type || (data.success ? 'success' : 'danger'), data.message || 'Готово.');
            if (!response.ok || !data.success) return;
            if (data.redirect) window.location.assign(data.redirect);
        } catch (error) {
            console.error(error);
            showAlert?.('danger', 'Не удалось связаться с сервером.');
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = oldText;
            }
        }
    }

    document.getElementById('create-room-form')?.addEventListener('submit', event => {
        event.preventDefault();
        submitAsync(event.currentTarget);
    });

    document.getElementById('join-room-form')?.addEventListener('submit', event => {
        event.preventDefault();
        submitAsync(event.currentTarget);
    });

    document.addEventListener('submit', async event => {
        const form = event.target.closest('.room-delete-form');
        if (!form) return;
        event.preventDefault();
        const confirmed = await confirmDialog({
            title: 'Удалить комнату?',
            message: 'Комната, её участники и ход партии будут удалены безвозвратно.',
            confirmText: 'Удалить',
        });
        if (!confirmed) return;
        const item = form.closest('.room-list-item');
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                credentials: 'same-origin'
            });
            const data = await response.json();
            updateCsrf(data);
            showAlert?.(data.type || 'info', data.message || 'Готово.');
            if (response.ok && data.success) item?.remove();
        } catch (error) {
            showAlert?.('danger', 'Не удалось удалить комнату.');
        }
    });

    let listBusy = false;
    async function refreshRoomList() {
        if (!roomList || listBusy || document.hidden) return;
        listBusy = true;
        try {
            const response = await fetch('/rooms', {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                cache: 'no-store',
                credentials: 'same-origin'
            });
            if (!response.ok) return;
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const fresh = doc.querySelector('.room-list');
            if (fresh && fresh.innerHTML !== roomList.innerHTML) {
                roomList.innerHTML = fresh.innerHTML;
            }
        } catch (error) {
            console.debug('Room list refresh failed', error);
        } finally {
            listBusy = false;
        }
    }

    setInterval(refreshRoomList, 5000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) refreshRoomList();
    });
})();
</script>

<?= $this->endSection() ?>
