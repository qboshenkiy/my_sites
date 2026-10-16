<?php
/*
 * Модальное подтверждение вместо window.confirm().
 *
 * Нативный confirm() блокирует поток страницы целиком: пока он открыт, не
 * выполняется JS, не отвечает опрос состояния комнаты и не работают
 * инструменты автоматизации. Плюс он не стилизуется, выглядит по-разному в
 * разных ОС и не даёт показать подробности вроде числа карточек.
 *
 * Самодостаточный партиал (стили + разметка + скрипт) по образцу
 * alert/alert.php — подключается одним include и в layout, и в standalone
 * страницы вроде rooms/play.php.
 *
 * API:  const ok = await confirmDialog({ title, message, confirmText, danger });
 */
?>
<style>
#confirm-dialog-backdrop {
    position: fixed;
    inset: 0;

    z-index: 100000;

    display: flex;
    align-items: center;
    justify-content: center;

    padding: 20px;

    background: rgba(8, 9, 13, .72);

    animation: confirmFadeIn .16s ease forwards;
}

.confirm-dialog {
    width: min(420px, 100%);

    background: #1a1d26;

    border: 1px solid #2d3242;
    border-top: 3px solid #c1a166;
    border-radius: 5px;

    box-shadow: 0 24px 60px rgba(0, 0, 0, .6);

    font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;

    animation: confirmPopIn .18s ease forwards;
}

.confirm-dialog.is-danger {
    border-top-color: #ff4a4a;
}

.confirm-dialog-body {
    padding: 22px 22px 6px;
}

.confirm-dialog-title {
    margin: 0 0 8px;

    color: #ffffff;

    font-size: 15px;
    font-weight: 700;

    letter-spacing: .3px;
}

.confirm-dialog-message {
    margin: 0;

    color: #9aa4bf;

    font-size: 13px;
    line-height: 1.5;
}

.confirm-dialog-actions {
    display: flex;
    justify-content: flex-end;

    gap: 9px;

    padding: 18px 22px 20px;
}

.confirm-dialog-btn {
    min-height: 38px;

    padding: 0 16px;

    border: 1px solid #3a4052;
    border-radius: 4px;

    background: transparent;

    color: #c3cad9;

    font-family: inherit;
    font-size: 12px;
    font-weight: 600;

    cursor: pointer;
}

.confirm-dialog-btn:hover {
    border-color: #55607a;
    color: #ffffff;
}

.confirm-dialog-btn-primary {
    border-color: #55492c;

    background: #2a261b;

    color: #c1a166;
}

.confirm-dialog-btn-primary:hover {
    border-color: #c1a166;
    color: #ffe4ae;
}

.confirm-dialog.is-danger .confirm-dialog-btn-primary {
    border-color: #5a2f33;

    background: #2b1d1f;

    color: #ff8a8a;
}

.confirm-dialog.is-danger .confirm-dialog-btn-primary:hover {
    border-color: #ff4a4a;
    color: #ffb3b3;
}

@keyframes confirmFadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}

@keyframes confirmPopIn {
    from { opacity: 0; transform: translateY(-8px) scale(.98); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}
</style>


<script>
(() => {
    let activeResolve = null;
    let backdrop = null;
    let lastFocused = null;

    const close = result => {
        if (!backdrop) {
            return;
        }

        backdrop.remove();
        backdrop = null;

        document.removeEventListener('keydown', onKeydown, true);

        const resolve = activeResolve;
        activeResolve = null;

        if (lastFocused && document.contains(lastFocused)) {
            lastFocused.focus();
        }

        lastFocused = null;

        if (resolve) {
            resolve(result);
        }
    };

    function onKeydown(event)
    {
        if (event.key === 'Escape') {
            event.preventDefault();
            close(false);
            return;
        }

        /* Не отпускаем фокус за пределы диалога. */
        if (event.key === 'Tab' && backdrop) {
            const focusable = backdrop.querySelectorAll('button');

            if (focusable.length === 0) {
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];

            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    }

    window.confirmDialog = options => {
        const {
            title = 'Подтвердите действие',
            message = '',
            confirmText = 'Подтвердить',
            cancelText = 'Отменить',
            danger = true,
        } = options || {};

        /* Второй вызов поверх открытого диалога отменяет предыдущий. */
        if (backdrop) {
            close(false);
        }

        lastFocused = document.activeElement;

        backdrop = document.createElement('div');
        backdrop.id = 'confirm-dialog-backdrop';

        const dialog = document.createElement('div');
        dialog.className = 'confirm-dialog' + (danger ? ' is-danger' : '');
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');

        const body = document.createElement('div');
        body.className = 'confirm-dialog-body';

        const titleEl = document.createElement('h3');
        titleEl.className = 'confirm-dialog-title';
        titleEl.textContent = title;

        const messageEl = document.createElement('p');
        messageEl.className = 'confirm-dialog-message';
        messageEl.textContent = message;

        body.appendChild(titleEl);
        body.appendChild(messageEl);

        const actions = document.createElement('div');
        actions.className = 'confirm-dialog-actions';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'confirm-dialog-btn';
        cancelBtn.textContent = cancelText;
        cancelBtn.addEventListener('click', () => close(false));

        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.className = 'confirm-dialog-btn confirm-dialog-btn-primary';
        confirmBtn.textContent = confirmText;
        confirmBtn.addEventListener('click', () => close(true));

        actions.appendChild(cancelBtn);
        actions.appendChild(confirmBtn);

        dialog.appendChild(body);
        dialog.appendChild(actions);
        backdrop.appendChild(dialog);

        backdrop.addEventListener('click', event => {
            if (event.target === backdrop) {
                close(false);
            }
        });

        document.body.appendChild(backdrop);
        document.addEventListener('keydown', onKeydown, true);

        /* Фокус на отмене: опасное действие не срабатывает по случайному Enter. */
        cancelBtn.focus();

        return new Promise(resolve => {
            activeResolve = resolve;
        });
    };
})();
</script>
