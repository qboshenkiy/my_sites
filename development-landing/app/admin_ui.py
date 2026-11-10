import time
from html import escape as esc

import chats
import content

TABS = {'leads': 'Заявки', 'chats': 'Чаты', 'service': 'Услуги и цены',
        'example': 'Портфолио', 'site': 'Тексты и SEO', 'settings': 'Контакты и бот'}
STATUSES = {'new': 'Новая', 'active': 'В работе', 'done': 'Закрыта'}


def shell(tab, hidden, message):
    links = ''.join(f'<a href="/admin?tab={key}"{" aria-current=page" if key == tab else ""}>{title}</a>'
                    for key, title in TABS.items())
    return (f'<div class="admin-top"><a href="/">← На сайт</a><form method="post" action="/admin/logout">{hidden}'
            '<button class="button outline small">Выйти</button></form></div>'
            f'<h1>{TABS[tab]}</h1><nav class="admin-nav" aria-label="Админка">{links}</nav>'
            f'<p class="admin-notice" role="status">{esc(message)}</p>')


def input_field(key, label, value='', size=100, kind='text', required=True):
    return (f'<label>{label}<input type="{kind}" name="{key}" maxlength="{size}" value="{esc(str(value))}"'
            f'{" required" if required else ""}></label>')


def area(key, label, value='', size=450, required=True):
    return (f'<label>{label}<textarea name="{key}" rows="3" maxlength="{size}"'
            f'{" required" if required else ""}>{esc(value)}</textarea></label>')


def select(key, label, options, selected):
    choices = ''.join(f'<option value="{k}"{" selected" if k == selected else ""}>{v}</option>' for k, v in options.items())
    return f'<label>{label}<select name="{key}">{choices}</select></label>'


def site(conn, hidden):
    values = content.site_values(conn)
    fields = ''.join(area(key, label, values[key], 600 if key in ('intro','services_intro','brief_intro') else 320)
                     for key, label in content.SITE_FIELDS.items())
    return (f'<form class="card admin-editor" method="post" action="/admin/site">{hidden}'
            f'<div class="admin-grid">{fields}</div><button class="button primary">Сохранить тексты</button></form>')


def card_form(kind, item, hidden):
    record_id = item.get('id', '')
    details = input_field('title', 'Название', item.get('title', ''))
    details += area('description', 'Описание', item.get('description', ''))
    if kind == 'service':
        details += select('mode', 'Тип цены', content.PRICE_MODES, item.get('mode', 'from'))
        details += input_field('price', 'Цена в сомах', item.get('price', ''), 9, 'number', required=False)
    else:
        details += input_field('url', 'Адрес сайта или демо', item.get('url', ''), 1000)
        details += input_field('cover', 'Текст на обложке', item.get('cover', ''), 24)
        details += input_field('tag', 'Подпись на обложке', item.get('tag', ''), 45, required=False)
        details += select('theme', 'Цвет обложки', content.THEMES, item.get('theme', 'cafe'))
    details += input_field('position', 'Порядок показа', item.get('position', 100), 4, 'number')
    checked = ' checked' if item.get('visible', True) else ''
    return f'''<form class="card admin-editor" method="post" action="/admin/card">
      {hidden}<input type="hidden" name="kind" value="{kind}"><input type="hidden" name="id" value="{record_id}">
      <h2>{esc(item.get('title') or 'Новая карточка')}</h2>{details}
      <label class="admin-check"><input type="checkbox" name="visible" value="1"{checked}> Показывать на сайте</label>
      <button class="button primary">{"Сохранить" if record_id else "Добавить"}</button></form>'''


def catalog(conn, kind, hidden):
    forms = ''.join(card_form(kind, item, hidden) for item in content.records(conn, kind))
    return ('<p>Карточки с меньшим номером показываются выше. Снимите отметку, чтобы скрыть карточку.</p>'
            f'<details class="admin-add"><summary>Добавить карточку</summary>{card_form(kind, {}, hidden)}</details>'
            f'<div class="admin-grid">{forms}</div>')


def date_label(ts):
    return time.strftime('%d.%m.%Y %H:%M', time.gmtime(ts + 21600))


def leads(conn, hidden, query):
    status = query.get('status', [''])[0]
    search = query.get('q', [''])[0][:100].strip()
    page = query.get('page', ['1'])[0]
    page = max(1, min(100000, int(page))) if page.isascii() and page.isdecimal() and len(page) <= 6 else 1
    rows = conn.execute("""
        SELECT l.*, COALESCE(s.status,'new') AS stage FROM leads l
        LEFT JOIN lead_status s ON s.lead_id=l.id
        WHERE (?='' OR COALESCE(s.status,'new')=?)
          AND (?='' OR instr(l.name || ' ' || l.contact || ' ' || l.body,?)>0)
        ORDER BY l.id DESC LIMIT 31 OFFSET ?
    """, (status, status, search, search, (page - 1) * 30)).fetchall()
    filters = select('status', 'Статус', {'': 'Все', **STATUSES}, status)
    cards = []
    for lead in rows[:30]:
        stage = select('stage', 'Статус', STATUSES, lead['stage'])
        delivery = 'Отправлена в Telegram' if lead['delivered'] else 'В списке заявок бота'
        cards.append(f'''<article class="card"><h3>№{lead['id']} · {esc(lead['source'])}</h3>
          <small>{date_label(lead['created'])} · {delivery}</small>
          <p>{esc(lead['name'])} · {esc(lead['contact'])}</p><p class="lead-body">{esc(lead['body'])}</p>
          <form method="post" action="/admin/lead">{hidden}<input type="hidden" name="id" value="{lead['id']}">
          {stage}<button class="button outline small">Сохранить статус</button></form></article>''')
    from urllib.parse import urlencode
    pages = ''.join(f'<a class="button outline small" href="/admin?{esc(urlencode(dict(tab="leads",status=status,q=search,page=n)))}">{label}</a>'
                    for n, label, show in ((page-1,'← Назад',page>1),(page+1,'Дальше →',len(rows)>30)) if show)
    return (f'<form class="admin-filters" action="/admin"><input type="hidden" name="tab" value="leads">'
            f'{input_field("q","Поиск",search,100,required=False)}{filters}<button class="button outline small">Найти</button></form>'
            f'<div class="admin-grid">{"".join(cards) or "<p>Заявок пока нет.</p>"}</div>{pages}')


def conversations(conn, bot_id, hidden, selected):
    contacts = chats.list_chats(conn, bot_id)
    links = ''.join(f'<a href="/admin?tab=chats&amp;chat={row["id"]}">№{row["id"]} · {esc(row["name"])}'
                    f'<small>{esc(row["contact"])}</small></a>' for row in contacts)
    box = '<p>Выберите клиента, чтобы открыть переписку.</p>'
    if selected:
        try:
            chat, rows = chats.history(conn, bot_id, selected)
        except ValueError:
            box = '<p>Диалог не найден.</p>'
        else:
            messages = []
            for row in rows:
                outgoing = row['direction'] == 'out'
                author = ('Вы · отправлено' if row['sent'] else 'Вы · ожидает отправки') if outgoing else 'Клиент'
                messages.append(f'<article class="chat-message{" outgoing" if outgoing else ""}">'
                                f'<small>{author} · {date_label(row["created"])}</small>'
                                f'<p class="lead-body">{esc(row["body"])}</p></article>')
            box = f'''<section class="card"><h2>{esc(chat['name'])}</h2>
              <div class="chat-history">{"".join(messages)}</div>
              <form method="post" action="/admin/reply">{hidden}<input type="hidden" name="chat" value="{chat['id']}">
              {area('body','Ответ в Telegram',size=2000)}<button class="button primary">Отправить ответ</button></form></section>'''
    return f'<div class="chat-layout"><nav class="chat-list" aria-label="Диалоги">{links or "<p>Клиенты появятся после первого сообщения боту.</p>"}</nav><div>{box}</div></div>'
