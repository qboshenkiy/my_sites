"""Shared accounting rules. Amounts are stored as integer minor units."""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

CATEGORIES=['Продукты','Кафе','Транспорт','Жильё','Здоровье','Покупки','Развлечения','Образование','Другое']

def money(value):
    try:
        n=Decimal(str(value).replace(',','.'))
        if not n.is_finite() or n<=0 or n>Decimal('1000000000') or n.as_tuple().exponent < -2:raise ValueError()
        return int(n*100)
    except (InvalidOperation,ValueError):raise ValueError('Введите положительную сумму с точностью до копейки')

def wallet_id(db,value=1):
    try:
        if isinstance(value,bool) or str(value).strip()!=str(int(value)):raise ValueError()
        wid=int(value)
    except (ValueError,TypeError):raise ValueError('Выберите кошелёк')
    if not db.execute('SELECT 1 FROM wallets WHERE id=?',(wid,)).fetchone():raise ValueError('Кошелёк не найден')
    return wid

def wallets(db):
    return [dict(r) for r in db.execute("""SELECT w.*,
      w.opening + COALESCE((SELECT SUM(CASE WHEN t.kind='income' THEN t.amount ELSE -t.amount END) FROM transactions t WHERE t.wallet_id=w.id),0)
      + COALESCE((SELECT SUM(amount) FROM transfers WHERE to_wallet=w.id),0)
      - COALESCE((SELECT SUM(amount) FROM transfers WHERE from_wallet=w.id),0) AS balance
      FROM wallets w ORDER BY w.id=1 DESC,w.id""")]

def transfer(db,data):
    amount=money(data.get('amount',''))
    source=wallet_id(db,data.get('from_wallet'));target=wallet_id(db,data.get('to_wallet'))
    if source==target:raise ValueError('Выберите разные кошельки')
    day=date.fromisoformat(str(data.get('date',date.today().isoformat())))
    note=str(data.get('note','')).strip()
    if len(note)>200:raise ValueError('Описание — до 200 символов')
    if next(w['balance'] for w in wallets(db) if w['id']==source)<amount:raise ValueError('В кошельке недостаточно денег для перевода')
    db.execute('INSERT INTO transfers(from_wallet,to_wallet,amount,day,note) VALUES(?,?,?,?,?)',(source,target,amount,str(day),note))

def operation(db,data,source='web',external=None):
    amount=money(data.get('amount',''))
    kind=data.get('kind','expense')
    if kind not in ('expense','income'):raise ValueError('Выберите доход или расход')
    category=str(data.get('category','Другое'))
    if category not in CATEGORIES+['Доход']:raise ValueError('Неизвестная категория')
    day=date.fromisoformat(str(data.get('date',date.today().isoformat())))
    note=str(data.get('note','')).strip()
    if len(note)>200:raise ValueError('Описание — до 200 символов')
    wid=wallet_id(db,data.get('wallet_id',1))
    db.execute('INSERT OR IGNORE INTO transactions(kind,amount,category,day,note,source,external,wallet_id) VALUES(?,?,?,?,?,?,?,?)',(kind,amount,category,day.isoformat(),note,source,external,wid))

def overview(db,month):
    start=date.fromisoformat(month+'-01');end=start.replace(day=calendar.monthrange(start.year,start.month)[1])
    rows=[dict(r) for r in db.execute('SELECT t.*,w.name AS wallet_name FROM transactions t JOIN wallets w ON w.id=t.wallet_id WHERE day BETWEEN ? AND ? ORDER BY day DESC,t.id DESC',(str(start),str(end)))]
    wallet_rows=wallets(db)
    transfers=[dict(r) for r in db.execute("SELECT t.*,a.name AS from_name,b.name AS to_name,'transfer' AS kind FROM transfers t JOIN wallets a ON a.id=t.from_wallet JOIN wallets b ON b.id=t.to_wallet WHERE day BETWEEN ? AND ? ORDER BY day DESC,t.id DESC",(str(start),str(end)))]
    income=sum(r['amount'] for r in rows if r['kind']=='income');expense=sum(r['amount'] for r in rows if r['kind']=='expense')
    balance=sum(w['balance'] for w in wallet_rows)
    cats={c:sum(r['amount'] for r in rows if r['kind']=='expense' and r['category']==c) for c in CATEGORIES}
    settings=dict(db.execute('SELECT key,value FROM settings'));budget=int(settings.get('budget','0'))
    goals=[dict(r) for r in db.execute('SELECT * FROM goals ORDER BY id DESC')]
    tips=[]
    if not rows:tips.append('Добавьте доходы и расходы за выбранный месяц — появится анализ трат.')
    if expense:
        top=max(cats,key=cats.get);tips.append(f'Больше всего за месяц уходит на «{top}»: {cats[top]/expense:.0%} расходов. Проверьте операции в этой категории.')
    if budget:
        if expense>budget:tips.append(f'Месячный бюджет превышен на {(expense-budget)/100:,.2f}. Пересмотрите оставшиеся необязательные траты.')
        elif start.year==date.today().year and start.month==date.today().month:
            days=(end-date.today()).days+1;tips.append(f'До конца месяца остаётся {(budget-expense)/100:,.2f}: ориентир {(budget-expense)/100/days:,.2f} в день.')
    if income and expense>income:tips.append('Расходы за месяц выше учтённых доходов. Проверьте полноту записей и сократите необязательные покупки.')
    for g in goals:
        remaining=max(0,g['target']-g['saved']);deadline=date.fromisoformat(g['deadline']);today=date.today()
        months=max(1,(deadline.year-today.year)*12+deadline.month-today.month+1)
        g['monthly']=(remaining+months-1)//months
        if remaining and deadline<today:tips.append(f'Срок цели «{g["name"]}» прошёл. Обновите срок или сумму.')
    return dict(wallets=wallet_rows,transfers=transfers,transactions=rows,income=income,expense=expense,balance=balance,categories=cats,goals=goals,tips=tips,settings=settings)
