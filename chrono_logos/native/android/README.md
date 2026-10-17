# Chrono Logos — Android

Отдельное Android-приложение с WebView для `https://chrono.vano.sbena.net/`.
Идентификатор `net.sbena.vano.chronologos`, Android 7+. Устанавливается рядом с марафоном.
Работает после подключения HTTPS через GitDeck: [инструкция](../../DEPLOY.md).

Обычный вход по логину и паролю остаётся доступен. Telegram Mini App использует
подписанный вход внутри Telegram; Android WebView не выдаёт себя за Telegram.
На Android можно войти в тот же аккаунт по его логину и паролю, заданным в профиле.

## Сборка

GitHub Actions → **Build Chrono Logos Android APK** → **Run workflow** → Artifacts.

Локально: JDK 17, Android SDK platform 36, build-tools 35.0.0.

```sh
./gradlew -PgameUrl=https://chrono.vano.sbena.net/ testDebugUnitTest lintDebug assembleDebug
```

На Windows используйте `gradlew.bat`. APK: `app/build/outputs/apk/debug/app-debug.apk`.
Gradle Wrapper 8.13 с проверкой SHA-256, Android Gradle Plugin 8.13.2.

Сессия хранится в Cookie WebView. Внешние ссылки открываются в браузере или
Telegram, внутри приложения разрешён только заданный HTTPS-origin, включая порт.
Кнопка «Назад» закрывает описание карты и меню, затем возвращает предыдущую страницу.
HTTP, ошибки сертификата, file/intent/javascript URL не обходятся.
Экспорт сохраняется системным выбором файла без доступа ко всему хранилищу.

Debug-сборка предназначена для проверки. Публикация в Google Play требует отдельной
release-подписи постоянным ключом, который нельзя хранить в Git. Телефон или эмулятор
к локальной сборке не подключался; фактический HTTPS на сервере проверяется после установки.
