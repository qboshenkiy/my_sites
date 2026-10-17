(() => {
    'use strict';
    const app = window.Telegram?.WebApp;
    const entry = document.getElementById('telegram-entry');
    const token = () => document.querySelector('input[name="csrf_test_name"]');
    let working = false;
    const status = message => {
        const element = document.querySelector('[data-telegram-status]') || document.getElementById('telegram-status');
        if (element) element.textContent = message;
    };
    async function request(action, extra = {}) {
        const csrf = token();
        if (!csrf) throw Error('Обновите страницу и повторите попытку.');
        const body = new URLSearchParams({[csrf.name]: csrf.value, ...extra});
        const response = await fetch('/telegram/' + action, {method: 'POST', credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}, body});
        const data = await response.json();
        if (data.csrfName && data.csrfHash) document.querySelectorAll('input').forEach(input => {if (input.name === data.csrfName) input.value = data.csrfHash;});
        if (!response.ok || !data.success) throw Error(data.message || 'Не удалось выполнить действие.');
        return data;
    }
    async function login(create = false) {
        if (!app?.initData) throw Error('Откройте игру кнопкой «Играть» в Telegram-боте. Для обычного браузера доступен вход по логину.');
        const data = await request('login', {initData: app.initData, create: create ? '1' : '0'});
        if (data.needsRegistration) {
            status('Telegram подтверждён. Создайте профиль или войдите в существующий аккаунт.');
            document.getElementById('telegram-entry-actions').hidden = false;
        } else if (data.redirect?.startsWith('/') && !data.redirect.startsWith('//')) location.assign(data.redirect);
    }
    if (app?.initData) {
        document.documentElement.classList.add('telegram-app');
        app.ready(); app.expand();
        if (app.isVersionAtLeast?.('6.1')) { app.setHeaderColor('#101b21'); app.setBackgroundColor('#101b21'); }
        if (app.isVersionAtLeast?.('7.7')) app.disableVerticalSwipes?.();
        const safeArea = () => {
            const inset = app.contentSafeAreaInset || {};
            document.documentElement.style.setProperty('--tg-safe-top', (inset.top || 0) + 'px');
            document.documentElement.style.setProperty('--tg-safe-bottom', (inset.bottom || 0) + 'px');
        };
        safeArea(); app.onEvent?.('contentSafeAreaChanged', safeArea);
        if (!entry && location.pathname !== '/rooms' && location.pathname !== '/games' && location.pathname !== '/') {
            app.BackButton?.show();
            app.BackButton?.onClick(() => {
                const modal = document.getElementById('card-modal');
                if (modal && !modal.hidden) { document.querySelector('.modal-close')?.click(); return; }
                location.assign('/rooms');
            });
        }
    }
    document.addEventListener('click', async event => {
        const button = event.target.closest('[data-telegram-action]');
        if (!button || working) return;
        const action = button.dataset.telegramAction;
        if (action === 'unlink' && !confirm('Отвязать Telegram от этого аккаунта? Убедитесь, что у вас задан пароль для входа.')) return;
        working = true; button.disabled = true;
        try {
            if (action === 'create') await login(true);
            else {
                if (action === 'link' && !app?.initData) throw Error('Привязка доступна внутри игрового Telegram-бота. Откройте его, войдите по логину и вернитесь в профиль.');
                const data = await request(action, action === 'link' ? {initData: app.initData} : {});
                status(data.message);
                if (action === 'link' || action === 'unlink') location.reload();
            }
        } catch (error) { status(error.message || 'Проверьте подключение к интернету.'); }
        finally { working = false; button.disabled = false; }
    });
    if (entry) login().catch(error => status(error.message));
})();
