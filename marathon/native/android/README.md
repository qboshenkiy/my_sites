# Глава — Android

Нативная оболочка марафона на Java / AndroidX Activity с WebView.
Сервер и авторизация остаются в существующем PHP-проекте.
Адрес по умолчанию — `https://vano.sbena.net/`; сначала подключите HTTPS
по инструкции [MINIAPP.md](../../MINIAPP.md).

## Сборка

Самый простой путь без терминала — GitHub Actions:
**Build Marathon Android APK → Run workflow → HTTPS-адрес → Artifacts**.

Локально нужны JDK 17, Android SDK platform 36 и build-tools 35.0.0:

```sh
./gradlew -PmarathonUrl=https://vano.sbena.net/ testDebugUnitTest lintDebug assembleDebug
```

Windows: `gradlew.bat` с теми же аргументами. В Android Studio откройте эту папку,
задайте SDK/JDK и выполните Build APK. Результат:
`app/build/outputs/apk/debug/app-debug.apk`.

`marathonUrl` принимает только HTTPS без пароля, query и fragment. Если марафон
в подпапке, укажите завершающий `/`. Gradle Wrapper закреплён на версии 8.13
с SHA-256 дистрибутива; Android Gradle Plugin — 8.13.2. Устройства: Android 7+.

## Поведение

- Cookie WebView сохраняют существующую сессию; пароль/токен в APK не встраиваются.
- Вход участника: кнопка Telegram, подтверждение в боте, возвращение в приложение.
- Внутри WebView остаётся только заданный HTTPS-origin и папка сайта.
- Внешние ссылки открываются браузером/Telegram; произвольные intent/file/javascript
  ссылки блокируются. Привилегированного JavaScript bridge нет.
- Ошибки SSL не обходятся. Для сбоя сети есть отдельный экран и повтор подключения.
- Отчёты сохраняются через системный выбор документа, с cookie только доверенного
  origin и без пересылки cookie при перенаправлении. Разрешение на всё хранилище не нужно.
- Облачный backup и перенос данных WebView исключены, чтобы не переносить сессии.

JUnit проверяет origin, порт, папку, обходы пути и опасные схемы ссылок.
Реальные жесты, переключение в Telegram, ротацию, сохранение отчётов и вход нужно
дополнительно проверить на телефоне. Emulator/телефон к этой сборке не подключался.

Debug APK — для тестирования, не публикация в Google Play. Для последующих
release-сборок храните постоянный signing key отдельно от репозитория и увеличивайте
versionCode. Данные приложения остаются на сервере при переустановке; вход потребуется снова.
