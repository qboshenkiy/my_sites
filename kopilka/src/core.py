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

def operation(db,data,source='web',external=None):
    amount=money(data.get('amount',''))
    kind=data.get('kind','expense')
    if kind not in ('expense','income'):raise ValueError('Выберите доход или расход')
    category=str(data.get('category','Другое'))
    if category not in CATEGORIES+['Доход']:raise ValueError('Неизвестная категория')
    day=date.fromisoformat(str(data.get('date',date.today().isoformat())))
    note=str(data.get('note','')).strip()
    if len(note)>200:raise ValueError('Описание — до 200 символов')
    db.execute('INSERT OR IGNORE INTO transactions(kind,amount,category,day,note,source,external) VALUES(?,?,?,?,?,?,?)',(kind,amount,category,day.isoformat(),note,source,external))

def overview(db,month):
    start=date.fromisoformat(month+'-01');end=start.replace(day=calendar.monthrange(start.year,start.month)[1])
    rows=[dict(r) for r in db.execute('SELECT * FROM transactions WHERE day BETWEEN ? AND ? ORDER BY day DESC,id DESC',(str(start),str(end)))]
    income=sum(r['amount'] for r in rows if r['kind']=='income');expense=sum(r['amount'] for r in rows if r['kind']=='expense')
    balance=db.execute("SELECT COALESCE(SUM(CASE WHEN kind='income' THEN amount ELSE -amount END),0) FROM transactions").fetchone()[0]
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
    return dict(transactions=rows,income=income,expense=expense,balance=balance,categories=cats,goals=goals,tips=tips,settings=settings)
