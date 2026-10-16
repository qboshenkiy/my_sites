<?= $this->extend('layouts/auth') ?>

<?php $this->setVar('title', 'Регистрация') ?>

<?= $this->section('content') ?>
<?= view('alert/alert') ?>
<div class="login-wrapper">
  <div class="login-card">

    <div class="card-header">
      <h2>РЕГИСТРАЦИЯ</h2>
      <p>Создание новой учетной записи</p>
    </div>

    <form method="post" action="/auth/register-page">

      <?= csrf_field() ?>

      <div class="form-group">
        <label for="username">LOGIN</label>

        <input
          type="text"
          id="username"
          name="username"
          value="<?= old('username') ?>"
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
        ЗАРЕГИСТРИРОВАТЬСЯ
      </button>

    </form>

    <div class="card-footer">

      <a href="#">
        Забыли пароль?
      </a>

      <a href="/auth/login-page">
        Войти в аккаунт
      </a>

    </div>

  </div>

</div>
<script>
  const form = document.querySelector('form');

  form.addEventListener('submit', async function (event) {
    event.preventDefault();

    const submitButton =
      form.querySelector('.submit-btn');

    submitButton.disabled = true;

    const formData =
      new FormData(form);

    try {

      const response =
        await fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: {
            'X-Requested-With':
              'XMLHttpRequest'
          },
          credentials: 'same-origin'
        });

      const data =
        await response.json();


      /*
       * CodeIgniter может обновить
       * CSRF после каждого POST.
       *
       * Обязательно записываем новый
       * token обратно в форму.
       */
      if (
        data.csrfName
        && data.csrfHash
      ) {

        const csrfInput =
          form.querySelector(
            `input[name="${data.csrfName}"]`
          );

        if (csrfInput) {
          csrfInput.value =
            data.csrfHash;
        }

      }


      showAlert(
        data.type ?? 'info',
        data.message
          ?? 'Неизвестный ответ сервера.'
      );


      if (
        response.ok
        && data.success
      ) {

        setTimeout(() => {

          /*
           * ВАЖНО:
           *
           * Не /dashboard.
           *
           * Сервер сам решает:
           * dashboard или invite комнаты.
           */
          window.location.href =
            data.redirect;

        }, 120);

      }

    } catch (error) {

      console.error(error);

      showAlert(
        'danger',
        'Не удалось выполнить регистрацию.'
      );

    } finally {

      submitButton.disabled =
        false;

    }
  });
</script>
<?= $this->endSection() ?>
