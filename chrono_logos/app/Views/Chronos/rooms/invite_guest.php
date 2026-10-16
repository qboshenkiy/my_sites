<?= $this->extend('layouts/auth') ?>

<?php $this->setVar('title', 'Присоединиться к игре') ?>

<?= $this->section('content') ?>
<?= view('alert/alert') ?>
<div class="login-wrapper">

  <div class="login-card">

    <div class="card-header">
      <h2><?= esc($room['game_title']) ?></h2>
      <p>
        Ведущий: <?= esc($room['host_username']) ?>
        · Игроков: <?= (int) $room['players_count'] ?> / <?= (int) $room['max_players'] ?>
      </p>
    </div>

    <form method="post" action="/rooms/guest-join" id="guest-join-form">

      <?= csrf_field() ?>

      <input type="hidden" name="code" value="<?= esc($room['code'], 'attr') ?>">

      <div class="form-group">
        <label for="guest-name">Ваше имя</label>

        <input
          type="text"
          id="guest-name"
          name="name"
          minlength="2"
          maxlength="30"
          required
          autocomplete="nickname"
          placeholder="Как вас представить другим игрокам?">
      </div>

      <button type="submit" class="submit-btn">
        ВОЙТИ И ИГРАТЬ
      </button>

    </form>

    <div class="card-footer">
      <a href="/auth/login-page">
        Уже есть аккаунт? Войти
      </a>
    </div>

  </div>

</div>
<script>
(() => {
  const form = document.getElementById('guest-join-form');
  const submitButton = form.querySelector('.submit-btn');

  form.addEventListener('submit', async event => {
    event.preventDefault();

    if (submitButton.disabled) {
      return;
    }

    submitButton.disabled = true;
    const oldText = submitButton.textContent;
    submitButton.textContent = 'ВХОДИМ...';

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

      if (data.csrfName && data.csrfHash) {
        let csrfInput = form.querySelector(
          `input[name="${data.csrfName}"]`
        );

        if (!csrfInput) {
          csrfInput = form.querySelector(
            'input[type="hidden"]:not([name="code"])'
          );
        }

        if (csrfInput) {
          csrfInput.name = data.csrfName;
          csrfInput.value = data.csrfHash;
        }
      }

      showAlert(
        data.type ?? (response.ok ? 'success' : 'danger'),
        data.message ?? 'Неизвестный ответ сервера.'
      );

      if (response.ok && data.success) {
        window.location.assign(
          data.redirect || '/rooms'
        );
        return;
      }
    } catch (error) {
      console.error(error);
      showAlert(
        'danger',
        'Сервер недоступен. Проверьте адрес и подключение к сети.'
      );
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = oldText;
    }
  });
})();
</script>
<?= $this->endSection() ?>
