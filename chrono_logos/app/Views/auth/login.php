<?= $this->extend('layouts/auth') ?>

<?php $this->setVar('title', 'Авторизация') ?>

<?= $this->section('content') ?>
<?= view('alert/alert') ?>
<div class="login-wrapper">

  <div class="login-card">

    <div class="card-header">
      <h2>АВТОРИЗАЦИЯ</h2>
      <p>Вход в учетную запись</p>
    </div>

    <form method="post" action="/auth/login-page">

      <?= csrf_field() ?>

      <div class="form-group">
        <label for="login">LOGIN</label>

        <input
          type="text"
          id="login"
          name="login"
          value="<?= old('login') ?>"
          required
          autocomplete="username"
          placeholder="Введите ваш логин...">
      </div>

      <div class="form-group">
        <label for="password">Пароль</label>

        <input
          type="password"
          id="password"
          name="password"
          required
          autocomplete="current-password"
          placeholder="Введите пароль...">
      </div>

      <button type="submit" class="submit-btn">
        ВОЙТИ
      </button>

    </form>

    <div class="card-footer">

      <a href="#">
        Забыли пароль?
      </a>

      <a href="/auth/register-page">
        Создать аккаунт
      </a>

    </div>

  </div>

</div>
<script>
(() => {
  const form = document.querySelector('form');
  const submitButton = form.querySelector('.submit-btn');

  form.addEventListener('submit', async event => {
    event.preventDefault();

    if (submitButton.disabled) {
      return;
    }

    submitButton.disabled = true;
    const oldText = submitButton.textContent;
    submitButton.textContent = 'ВХОД...';

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
            'input[type="hidden"]'
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
          data.redirect || '/dashboard'
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
