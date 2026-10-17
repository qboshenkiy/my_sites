<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('content') ?>


<div class="settings-heading">

    <div>
        <div class="section-label">
            АККАУНТ
        </div>

        <h2>Настройки аккаунта</h2>

        <p>
            Управляйте данными профиля и безопасностью аккаунта.
        </p>
    </div>
</div>


<div class="settings-grid">
<?= view('partials/telegram-settings', ['user' => $user]) ?>

    <!-- ПРОФИЛЬ -->

    <section class="settings-card">

        <div class="settings-card-header">

            <div>
                <div class="section-label">
                    ПРОФИЛЬ
                </div>

                <h3>Основная информация</h3>

                <p>
                    Измените имя пользователя и email.
                </p>
            </div>

        </div>


        <form
            class="ajax-settings-form"
            method="post"
            action="/account/update-profile">

            <?= csrf_field() ?>


            <div class="settings-form-group">

                <label for="username">
                    Логин
                </label>

                <input
                    type="text"
                    id="username"
                    name="username"
                    value="<?= esc($user['username']) ?>"
                    minlength="3"
                    maxlength="30"
                    required
                    autocomplete="username">

            </div>


            <div class="settings-form-group">

                <label for="email">
                    Email
                </label>

                <input
                    type="email"
                    id="email"
                    name="email"
                    value="<?= esc($user['email'] ?? '') ?>"
                    maxlength="255"
                    autocomplete="email"
                    placeholder="example@mail.com">

                <span class="field-hint">
                    Email пока необязателен.
                </span>

            </div>


            <div class="settings-form-group">

                <label>
                    ID аккаунта
                </label>

                <input
                    type="text"
                    value="<?= esc($user['id']) ?>"
                    disabled>

            </div>


            <button
                type="submit"
                class="settings-submit-btn">
                СОХРАНИТЬ
            </button>

        </form>

    </section>


    <!-- ПАРОЛЬ -->

    <section class="settings-card">

        <div class="settings-card-header">

            <div>
                <div class="section-label">
                    БЕЗОПАСНОСТЬ
                </div>

                <h3>Изменить пароль</h3>

                <p>
                    Для подтверждения необходимо указать текущий пароль.
                </p>
            </div>

        </div>


        <form
            class="ajax-settings-form"
            id="password-form"
            method="post"
            action="/account/change-password">

            <?= csrf_field() ?>


            <?php if (!in_array($user['telegram_only'] ?? false, [true, 't', '1', 1], true)): ?>
            <div class="settings-form-group">

                <label for="current_password">
                    Текущий пароль
                </label>

                <input
                    type="password"
                    id="current_password"
                    name="current_password"
                    required
                    autocomplete="current-password">

            </div>
            <?php else: ?>
                <p class="field-hint">Задайте первый пароль, чтобы входить в этот профиль в Android-приложении и обычном браузере.</p>
            <?php endif; ?>


            <div class="settings-form-group">

                <label for="new_password">
                    Новый пароль
                </label>

                <input
                    type="password"
                    id="new_password"
                    name="new_password"
                    minlength="8"
                    required
                    autocomplete="new-password">

                <span class="field-hint">
                    Минимум 8 символов.
                </span>

            </div>


            <div class="settings-form-group">

                <label for="password_confirm">
                    Повторите новый пароль
                </label>

                <input
                    type="password"
                    id="password_confirm"
                    name="password_confirm"
                    minlength="8"
                    required
                    autocomplete="new-password">

            </div>


            <button
                type="submit"
                class="settings-submit-btn">
                ИЗМЕНИТЬ ПАРОЛЬ
            </button>

        </form>

    </section>

</div>


<script>
    document
        .querySelectorAll('.ajax-settings-form')
        .forEach(function(form) {

            form.addEventListener(
                'submit',
                async function(event) {

                    event.preventDefault();

                    const button =
                        form.querySelector(
                            '.settings-submit-btn'
                        );

                    const oldText =
                        button.textContent;

                    button.disabled = true;
                    button.textContent = 'СОХРАНЯЕМ...';


                    try {

                        const response = await fetch(
                            form.action, {
                                method: 'POST',

                                body: new FormData(form),

                                headers: {
                                    'X-Requested-With': 'XMLHttpRequest'
                                }
                            }
                        );


                        const data =
                            await response.json();


                        /*
                         * Обновляем CSRF во ВСЕХ формах.
                         */
                        if (
                            data.csrfName &&
                            data.csrfHash
                        ) {

                            document
                                .querySelectorAll(
                                    `input[name="${data.csrfName}"]`
                                )
                                .forEach(function(input) {

                                    input.value =
                                        data.csrfHash;

                                });
                        }


                        showAlert(
                            data.type ?? 'info',
                            data.message ?? 'Готово.'
                        );


                        /*
                         * Если сервер просит
                         * авторизоваться заново.
                         */
                        if (data.redirect) {

                            setTimeout(function() {

                                window.location.href =
                                    data.redirect;

                            }, 800);

                            return;
                        }


                        /*
                         * После смены пароля
                         * очищаем только password form.
                         */
                        if (
                            data.success &&
                            form.id === 'password-form'
                        ) {

                            form.reset();

                        }


                        /*
                         * Если username изменился,
                         * обновим его в header/aside
                         * после обычного reload.
                         */
                        if (
                            data.success &&
                            data.username
                        ) {

                            document
                                .querySelectorAll('.header-username, .sidebar-username')
                                .forEach(function(element) {
                                    element.textContent = data.username;
                                });
                        }

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

        });
</script>


<?= $this->endSection() ?>
