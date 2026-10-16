<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/chronos/css/management.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>
<section class="management-page room-invite-page">
    <div class="management-heading">
        <div>
            <div class="section-label">ПРИГЛАШЕНИЕ</div>
            <h2><?= esc($room['game_title']) ?></h2>
            <p>Вас приглашают присоединиться к игровой комнате.</p>
        </div>
    </div>

    <div class="room-invite-card">
        <div class="room-invite-code"><?= esc($room['code']) ?></div>

        <h3><?= esc($room['game_title']) ?></h3>

        <p>
            Ведущий:
            <strong><?= esc($room['host_username']) ?></strong>
        </p>

        <p>
            Игроков:
            <strong id="invite-player-count"><?= (int) $room['players_count'] ?> / <?= (int) $room['max_players'] ?></strong>
        </p>

        <form
            id="invite-join-form"
            method="post"
            action="/rooms/join"
        >
            <?= csrf_field() ?>

            <input
                type="hidden"
                name="code"
                value="<?= esc($room['code'], 'attr') ?>"
            >

            <button type="submit" class="room-invite-submit">
                Присоединиться
            </button>
        </form>

        <a class="room-invite-back" href="/rooms">К списку комнат</a>
    </div>
</section>
<?= $this->endSection() ?>

<?= $this->section('scripts') ?>
<script>
(() => {
    const form = document.getElementById('invite-join-form');
    if (!form) return;

    const button = form.querySelector('button[type="submit"]');

    function updateCsrf(data) {
        if (!data?.csrfName || !data?.csrfHash) return;

        let input = form.querySelector(`input[name="${data.csrfName}"]`);
        if (!input) {
            input = form.querySelector('input[type="hidden"]');
        }

        if (input) {
            input.name = data.csrfName;
            input.value = data.csrfHash;
        }
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (button.disabled) return;

        const oldText = button.textContent;
        button.disabled = true;
        button.textContent = 'ПОДКЛЮЧАЕМ...';

        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });

            const data = await response.json();
            updateCsrf(data);

            if (!response.ok || !data.success) {
                showAlert(
                    data.type || 'danger',
                    data.message || 'Не удалось присоединиться к комнате.'
                );
                return;
            }

            showAlert(
                data.type || 'success',
                data.message || 'Вы вошли в комнату.'
            );

            window.location.assign(
                data.redirect || '/rooms'
            );
        } catch (error) {
            console.error(error);
            showAlert(
                'danger',
                'Не удалось связаться с сервером.'
            );
        } finally {
            button.disabled = false;
            button.textContent = oldText;
        }
    });
})();
</script>
<?= $this->endSection() ?>
