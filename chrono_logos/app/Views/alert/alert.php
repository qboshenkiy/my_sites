<style>
#alert-container {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);

    width: min(420px, calc(100vw - 32px));

    z-index: 99999;
    pointer-events: none;
}

.game-alert {
    background: #1a1d26;
    border: 1px solid #2d3242;
    border-radius: 4px;

    padding: 15px 20px;

    display: flex;
    align-items: center;

    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);

    font-family: 'Segoe UI', Roboto, sans-serif;

    box-sizing: border-box;
    width: 100%;

    pointer-events: auto;

    opacity: 0;
    transform: translateY(-25px) scale(0.98);

    animation: alertIn 0.3s ease forwards;
}

/* Цвет иконки наследуется от типа алерта. */
.alert-danger .alert-icon {
    color: #ff4a4a;
}

.alert-success .alert-icon {
    color: #28a745;
}

.alert-warning .alert-icon {
    color: #ffc107;
}

.alert-info .alert-icon {
    color: #c1a166;
}

.game-alert.is-hiding {
    animation: alertOut 0.3s ease forwards;
}

.alert-content {
    flex-grow: 1;
}

.alert-icon {
    display: flex;
    align-items: center;

    margin-right: 12px;
}

.alert-close {
    align-self: flex-start;

    margin: -4px -6px 0 10px;
    padding: 4px;

    border: 0;
    border-radius: 3px;

    background: transparent;

    color: #626b82;

    cursor: pointer;

    line-height: 0;
}

.alert-close:hover {
    background: rgba(255, 255, 255, .07);
    color: #ffffff;
}

.alert-title {
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    margin-bottom: 4px;
}

.alert-text {
    color: #9aa4bf;
    font-size: 13px;
    line-height: 1.4;
}


/* ERROR */

.alert-danger {
    border-left: 4px solid #ff4a4a;
}

.alert-danger .alert-title {
    color: #ff4a4a;
}


/* SUCCESS */

.alert-success {
    border-left: 4px solid #28a745;
}

.alert-success .alert-title {
    color: #28a745;
}


/* WARNING */

.alert-warning {
    border-left: 4px solid #ffc107;
}

.alert-warning .alert-title {
    color: #ffc107;
}


/* INFO */

.alert-info {
    border-left: 4px solid #c1a166;
}

.alert-info .alert-title {
    color: #c1a166;
}


/* Анимация появления */

@keyframes alertIn {
    from {
        opacity: 0;
        transform: translateY(-25px) scale(0.98);
    }

    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}


/* Анимация исчезновения */

@keyframes alertOut {
    from {
        opacity: 1;
        transform: translateY(0) scale(1);
    }

    to {
        opacity: 0;
        transform: translateY(-20px) scale(0.98);
    }
}
</style>


<div id="alert-container"></div>


<script>

let alertTimer = null;
let alertHideTimer = null;

const ALERT_ICONS = {
    success: `<?= icon('check', 18) ?>`,
    danger: `<?= icon('alert', 18) ?>`,
    warning: `<?= icon('alert', 18) ?>`,
    info: `<?= icon('info', 18) ?>`
};

/*
 * Ошибку нужно успеть прочитать, поэтому danger/warning живут дольше
 * success/info. Раньше всё показывалось 3.5 секунды, и сообщение вида
 * «Комната не найдена» исчезало раньше, чем его замечали.
 */
const ALERT_DURATIONS = {
    success: 4000,
    info: 4000,
    warning: 8000,
    danger: 9000
};


function showAlert(type, message, duration = null)
{
    const allowedTypes = [
        'success',
        'danger',
        'warning',
        'info'
    ];

    const titles = {
        success: 'УСПЕШНО',
        danger: 'ОШИБКА',
        warning: 'ВНИМАНИЕ',
        info: 'УВЕДОМЛЕНИЕ'
    };


    if (!allowedTypes.includes(type)) {
        type = 'info';
    }

    if (duration === null) {
        duration = ALERT_DURATIONS[type];
    }


    const container = document.getElementById('alert-container');


    // Если уже есть alert — удаляем
    container.innerHTML = '';


    // Сбрасываем старые таймеры
    if (alertTimer) {
        clearTimeout(alertTimer);
    }

    if (alertHideTimer) {
        clearTimeout(alertHideTimer);
    }


    const alert = document.createElement('div');

    alert.className = `game-alert alert-${type}`;
    alert.setAttribute('role', type === 'danger' ? 'alert' : 'status');


    const iconBox = document.createElement('div');

    iconBox.className = 'alert-icon';
    iconBox.innerHTML = ALERT_ICONS[type];


    const content = document.createElement('div');

    content.className = 'alert-content';


    const title = document.createElement('div');

    title.className = 'alert-title';
    title.textContent = titles[type];


    const text = document.createElement('div');

    text.className = 'alert-text';
    text.textContent = message;


    content.appendChild(title);
    content.appendChild(text);


    const closeBtn = document.createElement('button');

    closeBtn.type = 'button';
    closeBtn.className = 'alert-close';
    closeBtn.title = 'Закрыть';
    closeBtn.innerHTML = `<?= icon('close', 14) ?>`;


    const hide = () => {
        clearTimeout(alertTimer);
        alert.classList.add('is-hiding');
        alertHideTimer = setTimeout(() => alert.remove(), 300);
    };

    closeBtn.addEventListener('click', hide);


    alert.appendChild(iconBox);
    alert.appendChild(content);
    alert.appendChild(closeBtn);

    container.appendChild(alert);


    const startTimer = () => {
        alertTimer = setTimeout(hide, duration);
    };

    /* Пока курсор на сообщении, не убираем его. */
    alert.addEventListener('mouseenter', () => clearTimeout(alertTimer));
    alert.addEventListener('mouseleave', startTimer);

    startTimer();
}

</script>


<?php

$message = session()->getFlashdata('message');
$type = session()->getFlashdata('type') ?? 'info';

$allowedTypes = [
    'success',
    'danger',
    'warning',
    'info',
];

if (! in_array($type, $allowedTypes, true)) {
    $type = 'info';
}

?>


<?php if ($message): ?>

<script>

document.addEventListener('DOMContentLoaded', function () {

    showAlert(
        <?= json_encode($type) ?>,
        <?= json_encode(
            $message,
            JSON_HEX_TAG |
            JSON_HEX_APOS |
            JSON_HEX_AMP |
            JSON_HEX_QUOT
        ) ?>
    );

});

</script>

<?php endif; ?>