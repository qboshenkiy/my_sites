import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

DEFAULTS = json.loads(Path(__file__).with_name('defaults.json').read_text())
SITE_FIELDS = {
    'brand': 'Название сайта', 'hero_top': 'Заголовок · первая строка',
    'hero_bottom': 'Заголовок · вторая строка', 'intro': 'Текст на первом экране',
    'services_title': 'Заголовок услуг', 'services_intro': 'Текст над услугами',
    'examples_title': 'Заголовок портфолио', 'examples_intro': 'Текст над примерами',
    'process_title': 'Заголовок процесса', 'step1_title': 'Шаг 1 · заголовок',
    'step1_body': 'Шаг 1 · описание', 'step2_title': 'Шаг 2 · заголовок',
    'step2_body': 'Шаг 2 · описание', 'step3_title': 'Шаг 3 · заголовок',
    'step3_body': 'Шаг 3 · описание', 'brief_title': 'Заголовок формы',
    'brief_intro': 'Текст рядом с формой', 'footer': 'Подпись внизу сайта',
    'seo_title': 'Заголовок для поиска', 'seo_description': 'Описание для поиска',
}
PRICE_MODES = {'from': 'От указанной цены', 'fixed': 'Фиксированная цена', 'quote': 'По запросу'}
THEMES = {'cafe': 'Песочная', 'studio': 'Оливковая', 'craft': 'Синяя'}
GENERIC_ICON = 'M3 5h18v14H3zM3 9h18'


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS content (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, position INTEGER NOT NULL,
        visible INTEGER NOT NULL, data TEXT NOT NULL
    )''')
    cur = conn.execute("INSERT OR IGNORE INTO settings VALUES ('content_seeded', '1')")
    if cur.rowcount:
        for kind in ('service', 'example'):
            conn.executemany('INSERT INTO content (kind,position,visible,data) VALUES (?,?,1,?)',
                             [(kind, i * 10, json.dumps(item, ensure_ascii=False))
                              for i, item in enumerate(DEFAULTS[kind], 1)])


def records(conn, kind, public=False):
    sql = 'SELECT * FROM content WHERE kind=?'
    if public:
        sql += ' AND visible=1'
    return [dict(row, **json.loads(row['data']))
            for row in conn.execute(sql + ' ORDER BY position,id', (kind,))]


def site_values(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='site_content'").fetchone()
    return {**DEFAULTS['site'], **(json.loads(row[0]) if row else {})}


def price_label(item):
    if item['mode'] == 'quote':
        return 'По запросу'
    amount = f"{int(item['price']):,}".replace(',', ' ')
    return ('от ' if item['mode'] == 'from' else '') + amount + ' сом'


def services_html(items):
    cards = []
    for i, item in enumerate(items, 1):
        title = escape(item['title'])
        price = escape(price_label(item))
        key = escape(item.get('key') or f"service-{item['id']}")
        icon = escape(item.get('icon') or GENERIC_ICON)
        cards.append(f'''<article class="card">
          <div class="card-index">/ {i:02}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{icon}"/></svg></div>
          <h3>{title}</h3><p>{escape(item['description'])}</p>
          <a href="#brief" data-service="{key}" data-price-label="{price}" aria-label="{title}. {price}. Оставить заявку">{price} <span aria-hidden="true">↗</span></a></article>''')
    return ''.join(cards) or '<p>Опишите задачу в форме ниже, и я предложу решение.</p>'


def examples_html(items):
    return ''.join(f'''<article class="card"><div class="example-cover {escape(item['theme'])}">{escape(item['cover'])}<span>{escape(item['tag'])}</span></div>
      <h3>{escape(item['title'])}</h3><p>{escape(item['description'])}</p>
      <a href="{escape(item['url'])}">Открыть сайт <span aria-hidden="true">↗</span></a></article>''' for item in items)


def render(template, conn, origin):
    site = site_values(conn)
    values = {key: escape(value).replace('\n', '<br>') if key.endswith('_title') and key != 'seo_title' else escape(value)
              for key, value in site.items()}
    examples = records(conn, 'example', public=True)
    values.update(services=services_html(records(conn, 'service', public=True)),
                  examples=examples_html(examples), examples_hidden='' if examples else ' hidden',
                  structured=json.dumps({'@context': 'https://schema.org', '@type': 'WebSite',
                                         'name': site['brand'], 'url': origin + '/', 'inLanguage': 'ru'},
                                        ensure_ascii=False).replace('<', r'\u003c'))
    return re.sub(r'\{\{([a-z0-9_]+)\}\}', lambda match: values[match[1]], template)


def value(data, key, limit, required=True):
    result = data.get(key, '').strip()
    if len(result) > limit or (required and not result):
        raise ValueError('Проверьте обязательные поля и длину текста.')
    return result


def save_site(conn, data):
    settings = {key: value(data, key, 600 if key in ('intro', 'services_intro', 'brief_intro') else 320)
                for key in SITE_FIELDS}
    conn.execute("INSERT INTO settings VALUES ('site_content',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (json.dumps(settings, ensure_ascii=False),))


def save_record(conn, kind, data):
    if kind not in ('service', 'example'):
        raise ValueError('Неизвестный раздел.')
    item = {'title': value(data, 'title', 100), 'description': value(data, 'description', 450)}
    if kind == 'service':
        mode = data.get('mode')
        if mode not in PRICE_MODES:
            raise ValueError('Выберите тип цены.')
        price = '' if mode == 'quote' else value(data, 'price', 9)
        if price and not re.fullmatch(r'[0-9]{1,9}', price):
            raise ValueError('Цена должна быть целым числом в сомах.')
        item.update(mode=mode, price=price)
    else:
        url = value(data, 'url', 1000)
        parsed = urlsplit(url)
        local = re.fullmatch(r'/examples/[a-z0-9-]+\.html', url)
        external = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
        if not (local or external) or any(c.isspace() or ord(c) < 32 for c in url) or '\\' in url:
            raise ValueError('Укажите ссылку HTTPS или путь к странице /examples/…')
        theme = data.get('theme')
        if theme not in THEMES:
            raise ValueError('Выберите цвет обложки.')
        item.update(url=url, theme=theme, cover=value(data, 'cover', 24), tag=value(data, 'tag', 45, required=False))
    position = int(value(data, 'position', 4))
    visible = int(data.get('visible') == '1')
    record_id = data.get('id', '')
    if record_id:
        old = conn.execute('SELECT data FROM content WHERE kind=? AND id=?', (kind, record_id)).fetchone()
        if old is None:
            raise ValueError('Карточка уже удалена.')
        item = {**json.loads(old[0]), **item}
        conn.execute('UPDATE content SET data=?,position=?,visible=? WHERE kind=? AND id=?',
                     (json.dumps(item, ensure_ascii=False), position, visible, kind, record_id))
    else:
        conn.execute('INSERT INTO content (kind,position,visible,data) VALUES (?,?,?,?)',
                     (kind, position, visible, json.dumps(item, ensure_ascii=False)))
