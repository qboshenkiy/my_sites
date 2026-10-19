"""Finish and ranking regressions, against the disposable PostgreSQL/HTTP fixture."""
import json
import os
from pathlib import Path
import subprocess
from timeline_http import Browser


def run_completion_checks(base, env, sql):
    clients = {}
    for name in ('finish_a', 'finish_b', 'finish_c'):
        sql(f"INSERT INTO users(username,password_hash,role_id) SELECT '{name}',password_hash,(SELECT id FROM roles WHERE code='USER') FROM users WHERE username='deployadmin'")
        client = Browser(base)
        client.login(name, env['ADMIN_PASSWORD'])
        clients[int(sql(f"SELECT id FROM users WHERE username='{name}'").strip())] = client
    owner = next(iter(clients.values()))
    game = int(sql("SELECT id FROM game_templates WHERE status='PRODUCTION' ORDER BY id LIMIT 1").strip())
    sql(f"UPDATE cards SET is_enabled=TRUE WHERE game_template_id={game} AND title<>'' AND sort_order IS NOT NULL")

    def create(mode='NORMAL'):
        owner.post('/rooms/create', {'game_id': game, 'max_players': 4, 'cards_per_player': 1, 'game_mode': mode})
        room, code = sql('SELECT id,code FROM game_rooms ORDER BY id DESC LIMIT 1').strip().split('|')
        room = int(room)
        for client in list(clients.values())[1:]:
            client.post('/rooms/join', {'code': code})
        owner.post('/rooms/start', {'room_id': room})
        return room, code

    def state(code):
        return json.loads(owner.get('/rooms/state/' + code))

    def place(room, code, wrong=False):
        current = state(code)
        uid = current['currentPlayer']['id']
        card = int(sql(f"SELECT id FROM game_room_cards WHERE room_id={room} AND owner_user_id={uid} AND state='HAND' ORDER BY id LIMIT 1").strip())
        position = int(sql(f"SELECT count(*) FROM game_room_cards WHERE room_id={room} AND state='TIMELINE' AND sort_order<(SELECT sort_order FROM game_room_cards WHERE id={card})").strip())
        if wrong:
            position = 0 if position else 1
        fields = {'room_id': room, 'room_card_id': card, 'chosen_position': position, 'state_version': current['room']['stateVersion']}
        result = clients[uid].post('/rooms/place', fields)
        assert result['correct'] is not wrong, result
        return uid, fields

    room, code = create()
    first, fields = place(room, code)
    after = state(code)
    assert after['room']['status'] == 'PLAYING' and after['currentPlayer']['id'] != first
    assert next(p for p in after['players'] if p['id'] == first)['status'] == 'COMPLETED'
    if os.environ.get('COMPLETION_UI') == '1':
        username = sql(f'SELECT username FROM users WHERE id={first}').strip()
        subprocess.run(['node', str(Path(__file__).with_name('completion_ui.js'))],
                       env=dict(env, TIMELINE_TEST_URL=base, COMPLETION_ROOM=code, COMPLETION_USER=username),
                       check=True, timeout=45)
    clients[first].post('/rooms/place', dict(fields, state_version=after['room']['stateVersion']), 403)
    # A finished player leaving must not terminate the others' game.
    clients[first].post('/rooms/leave', {'room_id': room})
    assert state(code)['room']['status'] == 'PLAYING'
    place(room, code)
    assert state(code)['room']['status'] == 'PLAYING'  # Last player still gets their turn.
    place(room, code)
    final = state(code)
    assert final['room']['status'] == 'FINISHED'
    assert [(p['finishRank'], p['finishTurns']) for p in final['players']] == [(1, 1)] * 3
    assert sql(f'SELECT winner_user_id IS NULL FROM game_rooms WHERE id={room}').strip() == 't'
    html = owner.get('/rooms/show/' + code)
    assert 'Ничья' in html and 'Места: меньше личных ходов' in html
    owner.post('/rooms/rematch', {'room_id': room})
    assert sql(f'SELECT count(*) FROM game_room_players WHERE room_id={room} AND (finish_rank IS NOT NULL OR finish_turns IS NOT NULL OR completed_at IS NOT NULL)').strip() == '0'
    print('PASS: all players finish, finished player cannot move, shared first place and rematch reset')

    room, code = create()
    penalized, _ = place(room, code, wrong=True)
    assert next(p for p in state(code)['players'] if p['id'] == penalized)['mistakes'] == 1
    while state(code)['room']['status'] == 'PLAYING':
        place(room, code)
    final = state(code)
    loser = next(p for p in final['players'] if p['id'] == penalized)
    assert (loser['finishRank'], loser['finishTurns'], loser['mistakes']) == (3, 2, 1), loser
    assert [p['finishRank'] for p in final['players'] if p['id'] != penalized] == [1, 1]
    print('PASS: first in turn order can finish last; personal turns and mistakes determine ranks')

    room, code = create('HARDCORE')
    sql(f"DELETE FROM game_room_cards WHERE room_id={room} AND state='DECK'")
    sql(f"UPDATE game_rooms SET mistake_limit=3,empty_deck_behavior='SKIP' WHERE id={room}")
    penalized, _ = place(room, code, wrong=True)
    place(room, code)
    place(room, code)
    final = state(code)
    loser = next(p for p in final['players'] if p['id'] == penalized)
    assert (loser['finishRank'], loser['finishTurns'], loser['mistakes']) == (3, 1, 1), loser
    assert [p['finishRank'] for p in final['players'] if p['id'] != penalized] == [1, 1]
    print('PASS: hardcore finishers continue; fewer mistakes break equal-turn ties')

    room, code = create('BLIND')
    current = state(code)
    uid = current['currentPlayer']['id']
    clients[uid].post('/rooms/draw', {'room_id': room, 'state_version': current['room']['stateVersion']})
    place(room, code)
    assert state(code)['room']['status'] == 'PLAYING'
    assert sql(f"SELECT count(*) FROM game_room_players WHERE room_id={room} AND player_status='COMPLETED'").strip() == '0'
    print('PASS: blind mode continues after placing its drawn card')
