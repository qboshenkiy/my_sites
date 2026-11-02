# Используемые компоненты

Приложение «Голос книги» распространяется под GPL-3.0-or-later (см. LICENSE); другие модули репозитория этим файлом не лицензируются.

- Piper: https://github.com/OHF-Voice/piper1-gpl — GPL-3.0. Установленная версия: piper-tts 1.8.0. Включает eSpeak NG; лицензии находятся в установленном Python-пакете.
- Русские модели Денис и Дмитрий: https://huggingface.co/rhasspy/piper-voices . Карточки датасетов указывают CC0; репозиторий моделей указывает MIT. Обе модели дообучены от lessac-medium. Исходные модели и карточки загружаются отдельно, не входят в этот Git-репозиторий.
  - https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/denis/medium/MODEL_CARD
  - https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/dmitri/medium/MODEL_CARD
- Flask/Werkzeug — BSD; waitress — ZPL; python-docx — MIT; pypdf — BSD-3-Clause.
- FFmpeg, Poppler и Antiword устанавливаются из Debian. Их лицензии и уведомления сохраняются в /usr/share/doc контейнера.

Загрузка моделей и Python/Debian-пакетов требует интернета при установке. Само извлечение текста и озвучка не используют внешние API или загрузку книг третьим лицам.
