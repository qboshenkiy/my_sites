"""Explain known failures without returning raw logs, URLs, tokens or messages."""
import re


def explain(text):
    text=str(text)
    http=re.search(r'HTTP\s+(\d{1,3})\b',text,re.I)
    code=int(http[1]) if http else None
    curl=re.search(r'cURL\s+(\d+)\b',text,re.I)
    curl_code=int(curl[1]) if curl else None
    rules={
        401:('token','Telegram отклонил токен бота.','Проверьте токен в настройках GitDeck; если он отозван, замените его.'),
        404:('token','Telegram не нашёл бота или метод API.','Проверьте токен и обновление приложения.'),
        409:('conflict','Конфликт получения сообщений Telegram.','Проверьте второй запущенный экземпляр и webhook. Не запускайте ещё одну копию бота.'),
        403:('forbidden','Telegram запретил конкретное действие.','Участник мог остановить бота, либо у бота нет прав в группе. Это не означает остановку всего бота.'),
        429:('rate_limit','Telegram ограничил частоту запросов.','Дождитесь автоматического повтора. Не нажимайте отправку многократно.'),
        400:('request','Telegram отклонил параметры действия.','Проверьте чат, сообщение и доступные права. Это не означает остановку всего бота.'),
        0:('network','Не получен ответ Telegram.','Бот повторяет подключение. Проверьте интернет, DNS и доступ к api.telegram.org, если ошибка повторяется.'),
    }
    if code in rules:kind,cause,action=rules[code]
    elif code is not None and code>=500:
        kind,cause,action='telegram_server','Telegram API вернул серверную ошибку.','Дождитесь автоматического повтора; при длительном сбое проверьте доступность Telegram.'
    elif re.search(r'database is locked|database table is locked',text,re.I):
        kind,cause,action='database_busy','База данных занята.','Проверьте длительные операции и параллельные процессы; повторите действие позже.'
    elif 'Ошибка базы данных.' in text:
        kind,cause,action='database','Сбой работы с базой данных приложения.','Проверьте доступность базы, свободное место и журнал приложения. Это не ошибка токена Telegram.'
    elif 'Ошибка кода приложения.' in text:
        kind,cause,action='application','Ошибка выполнения кода приложения.','Проверьте обновление приложения и журнал. Смена токена или перезапуск не исправляют ошибку кода.'
    elif re.search(r'username does not match|имя бота и токен',text,re.I):
        kind,cause,action='identity','Имя бота не соответствует токену.','Укажите в GitDeck имя того бота, которому принадлежит токен.'
    elif re.search(r'already (?:running|has a webhook)|у бота есть webhook|бот .*уже запущен',text,re.I):
        kind,cause,action='conflict','Обнаружен другой обработчик сообщений.','Проверьте второй экземпляр бота и webhook.'
    elif re.search(r'connection unavailable|ошибка связи|нет связи|temporarily unavailable|нет подтверждения',text,re.I):
        kind,cause,action='unknown_connection','Записан сбой связи или фоновой обработки; точная причина в старом журнале отсутствует.','Проверьте свежую диагностику. Такая запись сама по себе не означает остановку бота.'
    else:
        kind,cause,action='unknown','Причина не определена по сохранённым данным.','Откройте диагностику бота в Guard и проверьте состояние контейнера.'
    if code==0 and curl_code in (5,6):cause='Не удалось определить адрес Telegram через DNS.'
    elif code==0 and curl_code==7:cause='Не удалось установить соединение с Telegram.'
    elif code==0 and curl_code==28:cause='Истекло время ожидания ответа Telegram.'
    elif code==0 and curl_code in (35,60):cause='Ошибка защищённого соединения с Telegram.'
    return {'code':kind,'http':code,'curl':curl_code,'cause':cause,'action':action}


def summary(text):
    info=explain(text)
    return 'Причина: '+info['cause']+'\nЧто делать: '+info['action']


def recent(raw):
    """Return only a fixed explanation and a validated Docker timestamp."""
    for line in reversed(raw.splitlines()):
        info=explain(line)
        if info['code']=='unknown':continue
        stamp=re.match(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z)\s',line)
        return {**info,'at':stamp[1] if stamp else None}
    return None
