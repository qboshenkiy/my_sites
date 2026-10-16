<?php

namespace App\Controllers;

use App\Controllers\BaseController;
use App\Models\Chronos\GameRoom;
use App\Models\Chronos\GameRoomPlayer;

use Endroid\QrCode\QrCode;
use Endroid\QrCode\Encoding\Encoding;
use Endroid\QrCode\ErrorCorrectionLevel;
use Endroid\QrCode\RoundBlockSizeMode;
use Endroid\QrCode\Writer\SvgWriter;

class Rooms extends BaseController
{
    public function getIndex()
    {
        $this->pruneInactiveRooms();

        $userId = (int) session()->get('user_id');
        $db = db_connect();

        $games = $db->table('game_templates')
            ->select('id, title')
            ->where('status', 'PRODUCTION')
            ->orderBy('title', 'ASC')
            ->get()
            ->getResultArray();

        $rooms = $db->table('game_rooms r')
            ->select('r.id, r.code, r.status, r.max_players, r.host_user_id, r.game_mode, r.created_at, r.updated_at, g.title AS game_title, u.username AS host_username')
            ->select(
                "(SELECT COUNT(*) FROM game_room_players rp
                   WHERE rp.room_id = r.id AND rp.player_status != 'LEFT')
                 AS players_count",
                false
            )
            ->join('game_templates g', 'g.id = r.game_template_id')
            ->join('users u', 'u.id = r.host_user_id')
            ->join(
                'game_room_players mine',
                'mine.room_id = r.id AND mine.user_id = ' . $userId
                    . " AND mine.player_status != 'LEFT'"
            )
            ->orderBy('r.updated_at', 'DESC')
            ->get()
            ->getResultArray();

        return view('Chronos/rooms/index', [
            'title' => 'Игровые комнаты',
            'games' => $games,
            'rooms' => $rooms,
        ]);
    }

    /**
     * Завершённые партии текущего игрока.
     *
     * В отличие от getIndex(), игроки со статусом LEFT здесь не отсекаются:
     * покинутая партия — тоже часть истории.
     */
    public function getHistory()
    {
        $userId = (int) session()->get('user_id');
        $db = db_connect();

        $rooms = $db->table('game_rooms r')
            ->select(
                'r.id,
                 r.code,
                 r.status,
                 r.game_mode,
                 r.max_players,
                 r.created_at,
                 r.finished_at,
                 r.winner_user_id,
                 g.title AS game_title,
                 u.username AS host_username,
                 w.username AS winner_username,
                 mine.score AS my_score,
                 mine.mistakes AS my_mistakes,
                 mine.player_status AS my_status'
            )
            ->select(
                '(SELECT COUNT(*) FROM game_room_players rp
                   WHERE rp.room_id = r.id) AS players_count',
                false
            )
            ->join('game_templates g', 'g.id = r.game_template_id')
            ->join('users u', 'u.id = r.host_user_id')
            ->join('users w', 'w.id = r.winner_user_id', 'left')
            ->join(
                'game_room_players mine',
                'mine.room_id = r.id AND mine.user_id = ' . $userId
            )
            ->where('r.status', 'FINISHED')
            ->orderBy('COALESCE(r.finished_at, r.updated_at)', 'DESC', false)
            ->limit(50)
            ->get()
            ->getResultArray();

        $wins = 0;

        foreach ($rooms as $room) {
            if ((int) $room['winner_user_id'] === $userId) {
                $wins++;
            }
        }

        return view('Chronos/rooms/history', [
            'title'  => 'История игр',
            'rooms'  => $rooms,
            'userId' => $userId,
            'wins'   => $wins,
        ]);
    }

    public function postCreate()
    {
        $gameId = (int) $this->request->getPost('game_id');

        $maxPlayers = (int) $this->request->getPost('max_players');
        $maxPlayers = max(2, min(20, $maxPlayers));

        $gameMode = strtoupper(
            trim((string) $this->request->getPost('game_mode'))
        );

        $allowedModes = [
            'NORMAL',
            'BLIND',
            'HARDCORE',
        ];

        if (! in_array($gameMode, $allowedModes, true)) {
            $gameMode = 'NORMAL';
        }

        $cardsPerPlayer =
            (int) $this->request->getPost('cards_per_player');

        $cardsPerPlayer =
            max(1, min(20, $cardsPerPlayer ?: 5));

        $mistakeLimit = null;

        if ($gameMode === 'HARDCORE') {
            $mistakeLimit =
                (int) $this->request->getPost('mistake_limit');

            $mistakeLimit =
                max(1, min(3, $mistakeLimit ?: 3));
        }

        $emptyDeckBehavior = strtoupper(
            trim((string) $this->request->getPost('empty_deck_behavior'))
        );

        if (! in_array($emptyDeckBehavior, ['GRACE', 'SKIP'], true)) {
            $emptyDeckBehavior = 'GRACE';
        }

        $game = db_connect()
            ->table('game_templates')
            ->select('id')
            ->where('id', $gameId)
            ->where('status', 'PRODUCTION')
            ->get()
            ->getRowArray();

        if (! $game) {
            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(
                    false,
                    'Опубликованная игра не найдена.',
                    null,
                    422,
                    'danger'
                );
            }

            return redirect()
                ->back()
                ->with('type', 'danger')
                ->with('message', 'Опубликованная игра не найдена.');
        }

        $db = db_connect();

        $roomModel =
            new GameRoom();

        $playerModel =
            new GameRoomPlayer();

        $code =
            $this->generateUniqueCode($roomModel);

        $db->transStart();

        $roomId = $roomModel->insert([
            'game_template_id' =>
                $gameId,

            'host_user_id' =>
                (int) session()->get('user_id'),

            'code' =>
                $code,

            'status' =>
                'WAITING',

            'max_players' =>
                $maxPlayers,

            'game_mode' =>
                $gameMode,

            'cards_per_player' =>
                $cardsPerPlayer,

            'mistake_limit' =>
                $mistakeLimit,

            'empty_deck_behavior' =>
                $emptyDeckBehavior,

            'invite_base_url' =>
                $this->detectRoomBaseUrl(),
        ]);

        $playerModel->insert([
            'room_id' =>
                $roomId,

            'user_id' =>
                (int) session()->get('user_id'),

            'score' =>
                0,

            'mistakes' =>
                0,

            'player_status' =>
                'ACTIVE',

            'joined_at' =>
                date('Y-m-d H:i:s'),
            'last_seen_at' =>
                date('Y-m-d H:i:s'),
        ]);

        $db->transComplete();

        if (
            ! $db->transStatus()
            || $roomId === false
        ) {
            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(
                    false,
                    'Не удалось создать комнату.',
                    null,
                    500,
                    'danger'
                );
            }

            return redirect()
                ->back()
                ->with('type', 'danger')
                ->with('message', 'Не удалось создать комнату.');
        }

        $message = 'Комната создана. Режим: '
            . $gameMode
            . '. Пригласите игроков по коду '
            . $code
            . '.';
        $redirectPath = '/rooms/show/' . $code;

        if ($this->isAsyncRoomRequest()) {
            return $this->asyncRoomResponse(
                true,
                $message,
                $redirectPath,
                200,
                'success'
            );
        }

        return redirect()
            ->to($this->sameOriginUrl($redirectPath))
            ->with('type', 'success')
            ->with('message', $message);
    }
    public function postJoin()
    {
        $code = strtoupper(trim((string) $this->request->getPost('code')));
        if (! preg_match('/^[A-Z0-9]{6}$/', $code)) {
            return $this->isAsyncRoomRequest()
                ? $this->asyncRoomResponse(false, 'Код комнаты должен содержать 6 символов.', null, 422, 'warning')
                : redirect()->back()->with('type', 'warning')->with('message', 'Код комнаты должен содержать 6 символов.');
        }

        $db = db_connect();
        $db->transBegin();

        $room = $db->query(
            'SELECT * FROM game_rooms WHERE code = ? FOR UPDATE',
            [$code]
        )->getRowArray();

        if (! $room || $room['status'] !== 'WAITING') {
            $db->transRollback();
            return $this->isAsyncRoomRequest()
                ? $this->asyncRoomResponse(false, 'Комната не найдена или игра уже началась.', null, 404, 'danger')
                : redirect()->back()->with('type', 'danger')->with('message', 'Комната не найдена или игра уже началась.');
        }

        $userId = (int) session()->get('user_id');
        $playerModel = new GameRoomPlayer();
        $existing = $playerModel->where('room_id', $room['id'])->where('user_id', $userId)->first();

        if ($existing && ($existing['player_status'] ?? 'ACTIVE') === 'LEFT') {
            $playerModel->update((int) $existing['id'], [
                'player_status' => 'ACTIVE',
                'mistakes' => 0,
                'score' => 0,
                'turn_order' => null,
                'last_seen_at' => date('Y-m-d H:i:s'),
            ]);
        } elseif (! $existing) {
            $count = $playerModel
                ->where('room_id', $room['id'])
                ->where('player_status !=', 'LEFT')
                ->countAllResults();
            if ($count >= (int) $room['max_players']) {
                $db->transRollback();
                return $this->isAsyncRoomRequest()
                    ? $this->asyncRoomResponse(false, 'В комнате больше нет свободных мест.', null, 409, 'warning')
                    : redirect()->back()->with('type', 'warning')->with('message', 'В комнате больше нет свободных мест.');
            }

            if ($playerModel->insert([
                'room_id' => $room['id'],
                'user_id' => $userId,
                'score' => 0,
                'joined_at' => date('Y-m-d H:i:s'),
                'last_seen_at' => date('Y-m-d H:i:s'),
            ]) === false) {
                $db->transRollback();
                return $this->isAsyncRoomRequest()
                    ? $this->asyncRoomResponse(false, 'Не удалось войти в комнату.', null, 500, 'danger')
                    : redirect()->back()->with('type', 'danger')->with('message', 'Не удалось войти в комнату.');
            }
        }

        $db->table('game_rooms')
            ->where('id', (int) $room['id'])
            ->update([
                'updated_at' => date('Y-m-d H:i:s'),
            ]);

        $db->transCommit();
        if ($this->isAsyncRoomRequest()) {
            return $this->asyncRoomResponse(true, 'Вы вошли в комнату.', '/rooms/show/' . $code, 200, 'success');
        }

        return redirect()->to($this->sameOriginUrl('/rooms/show/' . $code));
    }

    /**
     * Вход по QR без регистрации: только имя, без пароля. Создаёт
     * временный users-аккаунт (is_guest=true, чистится ленивой уборкой
     * в pruneInactiveRooms(), когда гость перестаёт быть ACTIVE-игроком
     * хоть в одной незавершённой комнате), логинит его и передаёт
     * дальше в postJoin() — та же проверка вместимости/статуса комнаты,
     * та же вставка в game_room_players, что и у обычных пользователей.
     */
    public function postGuestJoin()
    {
        $code = strtoupper(trim((string) $this->request->getPost('code')));

        if (! preg_match('/^[A-Z0-9]{6}$/', $code)) {
            return $this->isAsyncRoomRequest()
                ? $this->asyncRoomResponse(false, 'Код комнаты должен содержать 6 символов.', null, 422, 'warning')
                : redirect()->back()->with('type', 'warning')->with('message', 'Код комнаты должен содержать 6 символов.');
        }

        $name = trim((string) $this->request->getPost('name'));

        if (mb_strlen($name) < 2 || mb_strlen($name) > 30) {
            return $this->isAsyncRoomRequest()
                ? $this->asyncRoomResponse(false, 'Введите имя от 2 до 30 символов.', null, 422, 'warning')
                : redirect()->back()->with('type', 'warning')->with('message', 'Введите имя от 2 до 30 символов.');
        }

        $db = db_connect();

        $room = $db->table('game_rooms')
            ->where('code', $code)
            ->get()
            ->getRowArray();

        if (! $room || $room['status'] !== 'WAITING') {
            return $this->isAsyncRoomRequest()
                ? $this->asyncRoomResponse(false, 'Комната не найдена или игра уже началась.', null, 404, 'danger')
                : redirect()->back()->with('type', 'danger')->with('message', 'Комната не найдена или игра уже началась.');
        }

        $role = $db->table('roles')
            ->where('code', 'USER')
            ->get()
            ->getRowArray();

        $passwordHash = password_hash(bin2hex(random_bytes(20)), PASSWORD_DEFAULT);

        $username = $name;
        $userId = null;

        $now = date('Y-m-d H:i:s');

        for ($attempt = 0; $attempt < 5; $attempt++) {
            try {
                /*
                 * created_at/updated_at не заполняются сами — это не
                 * $userModel->insert() (там $useTimestamps=true делает это
                 * за Model), а прямой query builder, и его insert() не
                 * трогает служебные поля вообще. Без явной проставки
                 * created_at оставался NULL, а "created_at < NOW() -
                 * INTERVAL '60 seconds'" в чистке гостей никогда не
                 * становится true при NULL — гость никогда не удалялся бы.
                 */
                $userId = $db->table('users')->insert([
                    'username' => $username,
                    'password_hash' => $passwordHash,
                    'role_id' => (int) $role['id'],
                    'is_guest' => true,
                    'created_at' => $now,
                    'updated_at' => $now,
                ]) ? $db->insertID() : null;

                if ($userId !== null) {
                    break;
                }
            } catch (\CodeIgniter\Database\Exceptions\DatabaseException $e) {
                /*
                 * Уникальный конфликт по username — пробуем с суффиксом.
                 * Полагаемся на саму UNIQUE-ошибку БД, а не на pre-check
                 * (select-then-insert), чтобы не оставлять гонку.
                 *
                 * CodeIgniter здесь не сохраняет ни SQLSTATE, ни код
                 * ошибки — проверено: getCode() у DatabaseException и её
                 * $previous всегда 0, текст сообщения ("повторяющееся
                 * значение ключа нарушает ограничение уникальности...")
                 * локализован и зависит от локали Postgres. Единственное
                 * стабильное — имя самого constraint'а, оно не переводится:
                 * users_username задан миграцией CreateUsersTable
                 * (addUniqueKey('username')).
                 */
                if (! str_contains($e->getMessage(), 'users_username')) {
                    throw $e;
                }
            }

            $username = $name . '-' . random_int(100, 9999);
        }

        if ($userId === null) {
            return $this->isAsyncRoomRequest()
                ? $this->asyncRoomResponse(false, 'Не удалось войти как гость. Попробуйте другое имя.', null, 500, 'danger')
                : redirect()->back()->with('type', 'danger')->with('message', 'Не удалось войти как гость. Попробуйте другое имя.');
        }

        $session = session();
        $session->regenerate(true);
        $session->set([
            'user_id'   => $userId,
            'username'  => $username,
            'logged_in' => true,
            'role_code' => 'USER',
        ]);
        $session->remove('pending_room_code');

        return $this->postJoin();
    }

    public function getInvite(
        string $code
    ) {
        $code = strtoupper(
            trim($code)
        );

        if (
            ! preg_match(
                '/^[A-Z0-9]{6}$/',
                $code
            )
        ) {
            return redirect()
                ->to($this->sameOriginUrl('/rooms'))
                ->with(
                    'type',
                    'warning'
                )
                ->with(
                    'message',
                    'Некорректный код комнаты.'
                );
        }

        $room = db_connect()
            ->table('game_rooms r')
            ->select(
                'r.id,
             r.code,
             r.status,
             r.max_players,
             g.title AS game_title,
             u.username AS host_username'
            )
            ->select(
                "(SELECT COUNT(*)
              FROM game_room_players rp
              WHERE rp.room_id = r.id AND rp.player_status != 'LEFT')
              AS players_count",
                false
            )
            ->join(
                'game_templates g',
                'g.id = r.game_template_id'
            )
            ->join(
                'users u',
                'u.id = r.host_user_id'
            )
            ->where(
                'r.code',
                $code
            )
            ->get()
            ->getRowArray();

        if (
            ! $room
            || $room['status'] !== 'WAITING'
        ) {
            return redirect()
                ->to($this->sameOriginUrl('/rooms'))
                ->with(
                    'type',
                    'warning'
                )
                ->with(
                    'message',
                    'Комната не найдена или игра уже началась.'
                );
        }

        /*
     * Гость ещё не авторизован — вместо отправки на регистрацию
     * показываем форму «введите имя» прямо здесь. pending_room_code
     * всё равно сохраняем: если гость вместо этого нажмёт «Уже есть
     * аккаунт? Войти», обычный вход по логину/паролю вернёт его на
     * этот же инвайт (существующий механизм в Auth, не меняется).
     */
        if (! session()->get('logged_in')) {
            session()->set(
                'pending_room_code',
                $code
            );

            return view(
                'Chronos/rooms/invite_guest',
                [
                    'title' =>
                    'Присоединиться к игре',

                    'room' =>
                    $room,
                ]
            );
        }

        /*
     * Если пользователь уже состоит
     * в комнате — сразу открываем её.
     */
        $existing = db_connect()
            ->table('game_room_players')
            ->where(
                'room_id',
                $room['id']
            )
            ->where(
                'user_id',
                (int) session()
                    ->get('user_id')
            )
            ->get()
            ->getRowArray();

        if ($existing && ($existing['player_status'] ?? 'ACTIVE') !== 'LEFT') {
            return redirect()->to(
                $this->sameOriginUrl(
                    '/rooms/show/' . $code
                )
            );
        }

        return view(
            'Chronos/rooms/invite',
            [
                'title' =>
                'Присоединиться к игре',

                'room' =>
                $room,
            ]
        );
    }
    public function getShow(string $code)
    {
        $this->pruneInactiveRooms();

        $room = $this->findRoomForMember($code);

        if (! $room) {
            return redirect()->to($this->sameOriginUrl('/rooms'))
                ->with('type', 'warning')
                ->with('message', 'Сначала войдите в комнату по коду.');
        }

        /*
         * Главное изменение Step 6:
         * активная партия живёт на отдельном экране.
         */
        if ($room['status'] === 'PLAYING') {
            return redirect()->to(
                $this->sameOriginUrl('/rooms/play/' . $room['code'])
            );
        }

        /*
         * Ссылка строится от текущего origin при каждом показе комнаты,
         * а не берётся из game_rooms.invite_base_url.
         *
         * В LAN-разработке адрес машины меняется по DHCP, и сохранённый
         * при создании URL переживает сам себя: у комнаты в статусе WAITING
         * QR-код переставал открываться после смены IP. Сохранённое значение
         * остаётся историей того, где комнату создали.
         */
        $joinUrl = $this->buildInviteUrl($room['code']);

        $qrCode = new QrCode(
            data: $joinUrl,
            encoding: new Encoding('UTF-8'),
            errorCorrectionLevel: ErrorCorrectionLevel::Medium,
            size: 320,
            margin: 12,
            roundBlockSizeMode: RoundBlockSizeMode::Margin,
        );

        $writer = new SvgWriter();
        $qrResult = $writer->write($qrCode);

        return view('Chronos/rooms/show', [
            'title' =>
                'Комната ' . $room['code'],
            'room' =>
                $room,
            'players' =>
                $this->getPlayers((int) $room['id']),
            'isHost' =>
                (int) $room['host_user_id']
                    ===
                (int) session()->get('user_id'),
            'joinUrl' =>
                $joinUrl,
            'qrDataUri' =>
                $qrResult->getDataUri(),
        ]);
    }

    public function getPlay(string $code)
    {
        $this->pruneInactiveRooms();

        $room = $this->findRoomForMember($code);

        if (! $room) {
            return redirect()->to($this->sameOriginUrl('/rooms'))
                ->with('type', 'warning')
                ->with('message', 'Комната не найдена.');
        }

        if ($room['status'] !== 'PLAYING') {
            return redirect()->to(
                $this->sameOriginUrl('/rooms/show/' . $room['code'])
            );
        }

        return view('Chronos/rooms/play', [
            'title' =>
                $room['game_title'],
            'room' =>
                $room,
            'isHost' =>
                (int) $room['host_user_id']
                    ===
                (int) session()->get('user_id'),
        ]);
    }

    public function getDisplay(string $code)
    {
        $this->pruneInactiveRooms();

        $code = strtoupper(trim($code));

        $room = db_connect()
            ->table('game_rooms r')
            ->select(
                'r.*, g.title AS game_title, '
                . 'u.username AS host_username'
            )
            ->join(
                'game_templates g',
                'g.id = r.game_template_id'
            )
            ->join(
                'users u',
                'u.id = r.host_user_id'
            )
            ->where('r.code', $code)
            ->get()
            ->getRowArray();

        if (! $room) {
            return redirect()
                ->to($this->sameOriginUrl('/rooms'))
                ->with('type', 'warning')
                ->with('message', 'Комната не найдена.');
        }

        $userId =
            (int) session()->get('user_id');

        if (
            (int) $room['host_user_id'] !== $userId
            && ! $this->isAdmin()
        ) {
            return redirect()
                ->to(
                    $this->sameOriginUrl('/rooms/show/' . $room['code'])
                )
                ->with('type', 'danger')
                ->with(
                    'message',
                    'Экран для проектора может открыть '
                    . 'только ведущий или администратор.'
                );
        }

        return view('Chronos/rooms/display', [
            'title' =>
                'Экран игры ' . $room['code'],

            'room' =>
                $room,
        ]);
    }


    public function getDisplayState(string $code)
    {
        if (! session()->get('logged_in')) {
            return $this->response
                ->setStatusCode(401)
                ->setJSON([
                    'success' => false,
                    'message' => 'Требуется авторизация.',
                ]);
        }

        $code = strtoupper(trim($code));

        $db = db_connect();

        $room = $db
            ->table('game_rooms r')
            ->select(
                'r.*, g.title AS game_title, '
                . 'u.username AS host_username'
            )
            ->join(
                'game_templates g',
                'g.id = r.game_template_id'
            )
            ->join(
                'users u',
                'u.id = r.host_user_id'
            )
            ->where('r.code', $code)
            ->get()
            ->getRowArray();

        if (! $room) {
            return $this->response
                ->setStatusCode(404)
                ->setJSON([
                    'success' => false,
                    'message' => 'Комната не найдена.',
                ]);
        }

        $userId =
            (int) session()->get('user_id');

        if (
            (int) $room['host_user_id'] !== $userId
            && ! $this->isAdmin()
        ) {
            return $this->response
                ->setStatusCode(403)
                ->setJSON([
                    'success' => false,
                    'message' => 'Недостаточно прав.',
                ]);
        }

        $players = $db
            ->table('game_room_players p')
            ->select(
                'p.user_id, p.score, p.mistakes, '
                . 'p.player_status, p.turn_order, '
                . 'u.username'
            )
            ->select(
                '(SELECT COUNT(*) '
                . 'FROM game_room_cards hc '
                . 'WHERE hc.room_id = p.room_id '
                . 'AND hc.owner_user_id = p.user_id '
                . "AND hc.state = 'HAND') AS hand_count",
                false
            )
            ->join('users u', 'u.id = p.user_id')
            ->where('p.room_id', (int) $room['id'])
            ->orderBy('p.turn_order', 'ASC')
            ->orderBy('p.joined_at', 'ASC')
            ->get()
            ->getResultArray();

        $timeline = $db
            ->table('game_room_cards')
            ->select(
                'id, title, short_description, '
                . 'revealed_value, image_url, category, '
                . 'difficulty, timeline_position, was_misplaced'
            )
            ->where('room_id', (int) $room['id'])
            ->where('state', 'TIMELINE')
            ->orderBy('timeline_position', 'ASC')
            ->get()
            ->getResultArray();

        $deckRemaining = (int) $db
            ->table('game_room_cards')
            ->where('room_id', (int) $room['id'])
            ->where('state', 'DECK')
            ->countAllResults();

        $currentPlayer = null;

        if (! empty($room['current_player_user_id'])) {
            foreach ($players as $player) {
                if (
                    (int) $player['user_id']
                    ===
                    (int) $room['current_player_user_id']
                ) {
                    $currentPlayer = [
                        'id' => (int) $player['user_id'],
                        'username' => $player['username'],
                    ];
                    break;
                }
            }
        }

        $lastMove = $db
            ->table('game_room_moves m')
            ->select(
                'm.id, m.turn_number, m.chosen_position, '
                . 'm.is_correct, m.score_delta, '
                . 'u.username, c.title, c.short_description, '
                . 'c.image_url, c.category, c.difficulty, '
                . 'c.revealed_value'
            )
            ->join('users u', 'u.id = m.user_id')
            ->join(
                'game_room_cards c',
                'c.id = m.room_card_id'
            )
            ->where('m.room_id', (int) $room['id'])
            ->orderBy('m.id', 'DESC')
            ->get(1)
            ->getRowArray();

        $result = null;

        if ($room['status'] === 'FINISHED') {
            $winner = null;

            if (! empty($room['winner_user_id'])) {
                foreach ($players as $player) {
                    if (
                        (int) $player['user_id']
                        === (int) $room['winner_user_id']
                    ) {
                        $winner = $player['username'];
                        break;
                    }
                }
            }

            $leaders = [];
            if (! $winner && ! empty($players)) {
                $maxScore = max(array_map(
                    static fn(array $p): int => (int) $p['score'],
                    $players
                ));

                foreach ($players as $player) {
                    if ((int) $player['score'] === $maxScore) {
                        $leaders[] = $player['username'];
                    }
                }
            }

            $result = [
                'winner' => $winner,
                'tie' => ! $winner && count($leaders) > 1,
                'leaders' => $leaders,
            ];
        }


        return $this->response
            ->setJSON([
                'success' => true,

                'room' => [
                    'id' => (int) $room['id'],
                    'code' => $room['code'],
                    'title' => $room['game_title'],
                    'status' => $room['status'],
                    'gameMode' => $room['game_mode'] ?? 'NORMAL',
                    'mistakeLimit' => $room['mistake_limit'] !== null
                        ? (int) $room['mistake_limit']
                        : null,
                    'turnNumber' => (int) ($room['turn_number'] ?? 0),
                    'stateVersion' => (int) ($room['state_version'] ?? 0),
                ],

                'deck' => [
                    'remaining' => $deckRemaining,
                ],

                'currentPlayer' => $currentPlayer,

                'players' => array_map(
                    static function (array $player): array {
                        return [
                            'id' => (int) $player['user_id'],
                            'username' => $player['username'],
                            'score' => (int) $player['score'],
                            'mistakes' => (int) ($player['mistakes'] ?? 0),
                            'status' => $player['player_status'] ?? 'ACTIVE',
                            'handCount' => (int) ($player['hand_count'] ?? 0),
                        ];
                    },
                    $players
                ),

                'timeline' => array_map(
                    function (array $card): array {
                        return [
                            'id' => (int) $card['id'],
                            'title' => $card['title'],
                            'shortDescription' => $card['short_description'],
                            'revealedValue' => $card['revealed_value'],
                            'imageSrc' => ! empty($card['image_url'])
                                ? '/' . ltrim((string) $card['image_url'], '/')
                                : null,
                            'category' => $card['category'],
                            'difficulty' => $card['difficulty'],
                            'position' => (int) $card['timeline_position'],
                            'wasMisplaced' => $this->pgBool($card['was_misplaced']),
                        ];
                    },
                    $timeline
                ),

                'result' => $result,

                'lastMove' => $lastMove
                    ? [
                        'id' => (int) $lastMove['id'],
                        'turnNumber' => (int) $lastMove['turn_number'],
                        'username' => $lastMove['username'],
                        'cardTitle' => $lastMove['title'],
                        'shortDescription' => $lastMove['short_description'],
                        'category' => $lastMove['category'],
                        'difficulty' => $lastMove['difficulty'],
                        'imageSrc' => ! empty($lastMove['image_url'])
                            ? '/' . ltrim((string) $lastMove['image_url'], '/')
                            : null,
                        'revealedValue' => $lastMove['revealed_value'],
                        'chosenPosition' => (int) $lastMove['chosen_position'],
                        'correct' => $this->pgBool($lastMove['is_correct']),
                        'scoreDelta' => (int) $lastMove['score_delta'],
                    ]
                    : null,
            ]);
    }


    public function getState(string $code)
    {
        if (! session()->get('logged_in')) {
            return $this->response
                ->setStatusCode(401)
                ->setJSON([
                    'success' => false,
                    'message' => 'Требуется авторизация.',
                ]);
        }

        $this->pruneInactiveRooms();

        $room =
            $this->findRoomForMember($code);

        if ($room) {
            $this->touchPlayerPresence(
                (int) $room['id'],
                (int) session()->get('user_id')
            );

            if ($room['status'] === 'PLAYING') {
                $this->resolveStaleCurrentPlayer(
                    (int) $room['id']
                );

                $room =
                    $this->findRoomForMember($code);
            }
        }

        if (! $room) {
            return $this->response
                ->setStatusCode(404)
                ->setJSON([
                    'success' => false,
                    'message' => 'Комната не найдена.',
                ]);
        }

        $db =
            db_connect();

        $userId =
            (int) session()->get('user_id');

        /*
         * Игроки.
         */
        $players = $db
            ->table('game_room_players p')
            ->select(
                'p.user_id,
                 p.score,
                 p.mistakes,
                 p.player_status,
                 p.turn_order,
                 p.last_seen_at,
                 u.username'
            )
            ->join(
                'users u',
                'u.id = p.user_id'
            )
            ->where(
                'p.room_id',
                (int) $room['id']
            )
            ->orderBy(
                'p.turn_order',
                'ASC'
            )
            ->orderBy(
                'p.joined_at',
                'ASC'
            )
            ->get()
            ->getResultArray();

        /*
         * Количество карт в руках каждого игрока.
         *
         * Содержимое чужих рук клиенту не отдаём.
         */
        $handCountsRows = $db
            ->table('game_room_cards')
            ->select(
                'owner_user_id, COUNT(*) AS cards_count',
                false
            )
            ->where(
                'room_id',
                (int) $room['id']
            )
            ->where('state', 'HAND')
            ->where(
                'owner_user_id IS NOT NULL',
                null,
                false
            )
            ->groupBy('owner_user_id')
            ->get()
            ->getResultArray();

        $handCounts = [];

        foreach ($handCountsRows as $item) {
            $handCounts[
                (int) $item['owner_user_id']
            ] = (int) $item['cards_count'];
        }

        $response = [
            'success' => true,

            'room' => [
                'id' =>
                    (int) $room['id'],

                'code' =>
                    $room['code'],

                'status' =>
                    $room['status'],

                'maxPlayers' =>
                    (int) ($room['max_players'] ?? 0),

                'winnerUserId' =>
                    ! empty($room['winner_user_id'])
                        ? (int) $room['winner_user_id']
                        : null,

                'gameMode' =>
                    $room['game_mode']
                        ?? 'NORMAL',

                'cardsPerPlayer' =>
                    (int) (
                        $room['cards_per_player']
                        ?? 5
                    ),

                'mistakeLimit' =>
                    $room['mistake_limit'] !== null
                        ? (int) $room['mistake_limit']
                        : null,

                'turnNumber' =>
                    (int) (
                        $room['turn_number']
                        ?? 0
                    ),

                'stateVersion' =>
                    (int) (
                        $room['state_version']
                        ?? 0
                    ),
            ],

            'players' => array_map(
                static function (
                    array $player
                ) use (
                    $room,
                    $handCounts
                ): array {

                    $playerId =
                        (int) $player['user_id'];

                    return [
                        'id' =>
                            $playerId,

                        'username' =>
                            $player['username'],

                        'score' =>
                            (int) $player['score'],

                        'mistakes' =>
                            (int) (
                                $player['mistakes']
                                ?? 0
                            ),

                        'status' =>
                            $player['player_status']
                                ?? 'ACTIVE',

                        'handCount' =>
                            $handCounts[$playerId]
                                ?? 0,

                        'turnOrder' =>
                            $player['turn_order']
                                !== null
                                ? (int) $player['turn_order']
                                : null,

                        'isHost' =>
                            $playerId
                                ===
                            (int) $room['host_user_id'],

                        'isOnline' =>
                            ! empty($player['last_seen_at'])
                            && strtotime((string) $player['last_seen_at'])
                                >= time() - 45,
                    ];
                },
                $players
            ),

            'currentPlayer' =>
                null,

            /*
             * currentCard оставляем временно
             * для совместимости со старым UI.
             *
             * Новая версия интерфейса будет
             * работать через myHand.
             */
            'currentCard' =>
                null,

            'myHand' =>
                [],

            'timeline' =>
                [],

            'deck' => [
                'remaining' => 0,
            ],

            'isMyTurn' =>
                false,
        ];

        /*
         * Количество карт в общей колоде.
         */
        $response['deck']['remaining'] =
            (int) $db
                ->table('game_room_cards')
                ->where(
                    'room_id',
                    (int) $room['id']
                )
                ->where('state', 'DECK')
                ->countAllResults();

        /*
         * WAITING не имеет gameplay-данных.
         */
        if ($room['status'] === 'WAITING') {
            return $this->response
                ->setJSON($response);
        }

        /*
         * Текущий игрок.
         */
        if (
            ! empty(
                $room['current_player_user_id']
            )
        ) {
            foreach ($players as $player) {
                if (
                    (int) $player['user_id']
                    ===
                    (int) $room[
                        'current_player_user_id'
                    ]
                ) {
                    $response['currentPlayer'] = [
                        'id' =>
                            (int) $player['user_id'],

                        'username' =>
                            $player['username'],
                    ];

                    break;
                }
            }

            $response['isMyTurn'] =
                (int) $room[
                    'current_player_user_id'
                ]
                ===
                $userId;
        }

        /*
         * Timeline.
         *
         * sort_order намеренно не отдаём.
         */
        $timeline = $db
            ->table('game_room_cards')
            ->select(
                'id,
                 title,
                 short_description,
                 revealed_value,
                 image_url,
                 category,
                 difficulty,
                 timeline_position,
                 was_misplaced'
            )
            ->where(
                'room_id',
                (int) $room['id']
            )
            ->where(
                'state',
                'TIMELINE'
            )
            ->orderBy(
                'timeline_position',
                'ASC'
            )
            ->get()
            ->getResultArray();

        $response['timeline'] =
            array_map(
                function (
                    array $card
                ): array {

                    return [
                        'id' =>
                            (int) $card['id'],

                        'title' =>
                            $card['title'],

                        'shortDescription' =>
                            $card[
                                'short_description'
                            ],

                        'revealedValue' =>
                            $card[
                                'revealed_value'
                            ],

                        'imageUrl' =>
                            $card['image_url'],

                        'imageSrc' =>
                            ! empty(
                                $card['image_url']
                            )
                                ? '/' . ltrim((string) $card['image_url'], '/')
                                : null,

                        'category' =>
                            $card['category'],

                        'difficulty' =>
                            $card['difficulty'],

                        'position' =>
                            (int) $card[
                                'timeline_position'
                            ],

                        'wasMisplaced' =>
                            $this->pgBool(
                                $card['was_misplaced']
                            ),
                    ];
                },
                $timeline
            );

        /*
         * Личная рука.
         *
         * ВАЖНО:
         * запрос фильтруется по owner_user_id,
         * поэтому чужие карты в JSON
         * вообще не попадают.
         *
         * sort_order и revealed_value
         * также не выбираем.
         */
        $hand = $db
            ->table('game_room_cards')
            ->select(
                'id,
                 title,
                 short_description,
                 image_url,
                 category,
                 difficulty,
                 deck_position'
            )
            ->where(
                'room_id',
                (int) $room['id']
            )
            ->where(
                'owner_user_id',
                $userId
            )
            ->where(
                'state',
                'HAND'
            )
            ->orderBy(
                'deck_position',
                'ASC'
            )
            ->orderBy(
                'id',
                'ASC'
            )
            ->get()
            ->getResultArray();

        $response['myHand'] =
            array_map(
                static function (
                    array $card
                ): array {

                    return [
                        'id' =>
                            (int) $card['id'],

                        'title' =>
                            $card['title'],

                        'shortDescription' =>
                            $card[
                                'short_description'
                            ],

                        'imageUrl' =>
                            $card['image_url'],

                        'imageSrc' =>
                            ! empty(
                                $card['image_url']
                            )
                                ? '/' . ltrim((string) $card['image_url'], '/')
                                : null,

                        'category' =>
                            $card['category'],

                        'difficulty' =>
                            $card['difficulty'],
                    ];
                },
                $hand
            );

        /*
         * BLIND:
         * текущий игрок может взять карту,
         * только когда его рука пуста.
         */
        $response['canDraw'] =
            ($room['game_mode'] ?? 'NORMAL')
                === 'BLIND'
            &&
            $response['isMyTurn']
            &&
            empty($response['myHand'])
            &&
            (int) $response['deck']['remaining']
                > 0;

        /*
         * Последний ход.
         *
         * Клиенту отдаём только уже раскрытые
         * данные сыгранной карты.
         * sort_order не отдаём.
         */
        $lastMove = $db
            ->table('game_room_moves m')
            ->select(
                'm.id, m.turn_number, m.chosen_position, '
                . 'm.is_correct, m.score_delta, '
                . 'u.username, c.title, c.short_description, '
                . 'c.image_url, c.category, c.difficulty, '
                . 'c.revealed_value'
            )
            ->join(
                'users u',
                'u.id = m.user_id'
            )
            ->join(
                'game_room_cards c',
                'c.id = m.room_card_id'
            )
            ->where(
                'm.room_id',
                (int) $room['id']
            )
            ->orderBy('m.id', 'DESC')
            ->get(1)
            ->getRowArray();

        $response['lastMove'] =
            $lastMove
                ? [
                    'id' =>
                        (int) $lastMove['id'],
                    'turnNumber' =>
                        (int) $lastMove['turn_number'],
                    'username' =>
                        $lastMove['username'],
                    'cardTitle' =>
                        $lastMove['title'],
                    'shortDescription' =>
                        $lastMove['short_description'],
                    'imageSrc' =>
                        ! empty($lastMove['image_url'])
                            ? '/' . ltrim((string) $lastMove['image_url'], '/')
                            : null,
                    'category' =>
                        $lastMove['category'],
                    'difficulty' =>
                        $lastMove['difficulty'],
                    'revealedValue' =>
                        $lastMove['revealed_value'],
                    'chosenPosition' =>
                        (int) $lastMove[
                            'chosen_position'
                        ],
                    'correct' =>
                        $this->pgBool($lastMove['is_correct']),
                    'scoreDelta' =>
                        (int) $lastMove['score_delta'],
                ]
                : null;

        /*
         * Временная совместимость
         * со старым show.php:
         * текущему игроку показываем
         * первую карту его руки.
         *
         * После нового игрового UI
         * currentCard можно будет удалить.
         */
        if (
            $response['isMyTurn']
            && ! empty($response['myHand'])
        ) {
            $response['currentCard'] =
                $response['myHand'][0];
        }

        return $this->response
            ->setJSON($response);
    }
    public function postStart()
    {
        $roomId =
            (int) $this->request->getPost('room_id');

        $userId =
            (int) session()->get('user_id');

        $db =
            db_connect();

        $db->transBegin();

        try {
            $room = $db->query(
                '
                SELECT *
                FROM game_rooms
                WHERE id = ?
                FOR UPDATE
                ',
                [$roomId]
            )->getRowArray();

            if (! $room) {
                throw new \RuntimeException(
                    'Комната не найдена.'
                );
            }

            if (
                (int) $room['host_user_id'] !== $userId
                && ! $this->isAdmin()
            ) {
                throw new \RuntimeException(
                    'Недостаточно прав для запуска игры.'
                );
            }

            if ($room['status'] !== 'WAITING') {
                throw new \RuntimeException(
                    'Эту комнату уже нельзя запустить.'
                );
            }

            $gameMode =
                strtoupper(
                    (string) (
                        $room['game_mode']
                        ?? 'NORMAL'
                    )
                );

            if (
                ! in_array(
                    $gameMode,
                    ['NORMAL', 'BLIND', 'HARDCORE'],
                    true
                )
            ) {
                throw new \RuntimeException(
                    'Режим '
                    . $gameMode
                    . ' будет подключён '
                    . 'на следующем этапе.'
                );
            }

            $players = $db
                ->table('game_room_players')
                ->where('room_id', $roomId)
                ->where('player_status !=', 'LEFT')
                ->orderBy('joined_at', 'ASC')
                ->get()
                ->getResultArray();

            if (count($players) < 2) {
                throw new \RuntimeException(
                    'Для начала игры нужно минимум 2 игрока.'
                );
            }

            $game = $db
                ->table('game_templates')
                ->select('id, status')
                ->where('id', (int) $room['game_template_id'])
                ->get()
                ->getRowArray();

            if (! $game || ($game['status'] ?? '') !== 'PRODUCTION') {
                throw new \RuntimeException(
                    'Игра больше не опубликована. Запуск комнаты невозможен.'
                );
            }

            $cards = $db
                ->table('cards')
                ->where(
                    'game_template_id',
                    (int) $room['game_template_id']
                )
                ->get()
                ->getResultArray();

            $invalidCards = array_filter(
                $cards,
                static fn(array $card): bool =>
                    trim((string) ($card['title'] ?? '')) === ''
                    || $card['sort_order'] === null
                    || $card['sort_order'] === ''
            );

            if ($invalidCards) {
                throw new \RuntimeException(
                    'В игре есть незаполненные карточки. '
                    . 'У каждой карточки должны быть название и sort_order.'
                );
            }

            $cardsPerPlayer =
                max(
                    1,
                    min(
                        20,
                        (int) (
                            $room['cards_per_player']
                            ?? 5
                        )
                    )
                );

            /*
             * NORMAL:
             * стартовая карта + полная раздача.
             *
             * BLIND:
             * только стартовая карта,
             * остальные остаются в DECK.
             */
            $requiredCards =
                in_array($gameMode, ['NORMAL', 'HARDCORE'], true)
                    ? 1
                        + count($players)
                        * $cardsPerPlayer
                    : 2;

            if (count($cards) < $requiredCards) {
                $message =
                    in_array($gameMode, ['NORMAL', 'HARDCORE'], true)
                        ? 'Недостаточно карточек для раздачи. '
                            . 'Нужно минимум '
                            . $requiredCards
                            . ': 1 стартовая + '
                            . $cardsPerPlayer
                            . ' × '
                            . count($players)
                            . ' игроков.'
                        : 'Для режима «Вслепую» нужно '
                            . 'минимум 2 игровые карточки.';

                throw new \RuntimeException(
                    $message
                );
            }

            $db->table('game_room_moves')
                ->where('room_id', $roomId)
                ->delete();

            $db->table('game_room_cards')
                ->where('room_id', $roomId)
                ->delete();

            $db->table('game_room_players')
                ->where('room_id', $roomId)
                ->update([
                    'score' =>
                        0,
                    'mistakes' =>
                        0,
                    'player_status' =>
                        'ACTIVE',
                    'turn_order' =>
                        null,
                    'last_seen_at' =>
                        date('Y-m-d H:i:s'),
                ]);

            shuffle($players);

            foreach ($players as $index => $player) {
                $db->table(
                    'game_room_players'
                )
                    ->where(
                        'id',
                        (int) $player['id']
                    )
                    ->update([
                        'turn_order' =>
                            $index,
                    ]);
            }

            shuffle($cards);

            $startSourceCard =
                array_shift($cards);

            $now =
                date('Y-m-d H:i:s');

            $startResult = $db->query(
                '
                INSERT INTO game_room_cards (
                    room_id,
                    source_card_id,
                    owner_user_id,
                    title,
                    short_description,
                    sort_order,
                    revealed_value,
                    image_url,
                    category,
                    difficulty,
                    deck_position,
                    state,
                    timeline_position,
                    revealed_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                RETURNING id
                ',
                [
                    $roomId,
                    (int) $startSourceCard['id'],
                    $startSourceCard['title'],
                    $startSourceCard[
                        'short_description'
                    ],
                    $startSourceCard['sort_order'],
                    $startSourceCard[
                        'revealed_value'
                    ],
                    $startSourceCard['image_url'],
                    $startSourceCard['category'],
                    $startSourceCard['difficulty'],
                    0,
                    'TIMELINE',
                    0,
                    $now,
                    $now,
                    $now,
                ]
            )->getRowArray();

            if (! $startResult) {
                throw new \RuntimeException(
                    'Не удалось создать стартовую карточку.'
                );
            }

            $roomCards = [];

            foreach ($cards as $index => $card) {
                $result = $db->query(
                    '
                    INSERT INTO game_room_cards (
                        room_id,
                        source_card_id,
                        owner_user_id,
                        title,
                        short_description,
                        sort_order,
                        revealed_value,
                        image_url,
                        category,
                        difficulty,
                        deck_position,
                        state,
                        timeline_position,
                        revealed_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, NULL, NULL, ?, ?
                    )
                    RETURNING id
                    ',
                    [
                        $roomId,
                        (int) $card['id'],
                        $card['title'],
                        $card[
                            'short_description'
                        ],
                        $card['sort_order'],
                        $card[
                            'revealed_value'
                        ],
                        $card['image_url'],
                        $card['category'],
                        $card['difficulty'],
                        $index + 1,
                        'DECK',
                        $now,
                        $now,
                    ]
                )->getRowArray();

                if (! $result) {
                    throw new \RuntimeException(
                        'Не удалось создать игровую колоду.'
                    );
                }

                $roomCards[] = [
                    'id' =>
                        (int) $result['id'],
                ];
            }

            /*
             * Только NORMAL раздаёт руки
             * до первого хода.
             */
            if (in_array($gameMode, ['NORMAL', 'HARDCORE'], true)) {
                $dealIndex = 0;

                for (
                    $round = 0;
                    $round < $cardsPerPlayer;
                    $round++
                ) {
                    foreach ($players as $player) {
                        $roomCard =
                            $roomCards[$dealIndex]
                            ?? null;

                        if (! $roomCard) {
                            throw new \RuntimeException(
                                'Не удалось закончить раздачу.'
                            );
                        }

                        $db->table(
                            'game_room_cards'
                        )
                            ->where(
                                'id',
                                (int) $roomCard['id']
                            )
                            ->update([
                                'state' =>
                                    'HAND',
                                'owner_user_id' =>
                                    (int) $player[
                                        'user_id'
                                    ],
                            ]);

                        $dealIndex++;
                    }
                }
            }

            $currentPlayerUserId =
                (int) $players[0]['user_id'];

            $db->table('game_rooms')
                ->where('id', $roomId)
                ->update([
                    'status' =>
                        'PLAYING',
                    'started_at' =>
                        $now,
                    'finished_at' =>
                        null,
                    'current_player_user_id' =>
                        $currentPlayerUserId,
                    'current_room_card_id' =>
                        null,
                    'turn_number' =>
                        1,
                    'state_version' =>
                        1,
                    'winner_user_id' =>
                        null,
                    'updated_at' =>
                        $now,
                ]);

            if (! $db->transStatus()) {
                throw new \RuntimeException(
                    'Не удалось запустить игру.'
                );
            }

            $db->transCommit();

            if ($gameMode === 'BLIND') {
                $message =
                    'Игра «Вслепую» началась. '
                    . 'Первый игрок должен вытянуть карту.';
            } elseif ($gameMode === 'HARDCORE') {
                $message =
                    'Хардкор начался. Лимит ошибок: '
                    . max(1, min(3, (int) ($room['mistake_limit'] ?? 3)))
                    . '.';
            } else {
                $message =
                    'Игра началась. Каждому игроку выдано '
                    . $cardsPerPlayer
                    . ' карт.';
            }

            $redirectPath = '/rooms/play/' . $room['code'];

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(
                    true,
                    $message,
                    $redirectPath,
                    200,
                    'success'
                );
            }

            return redirect()
                ->to($this->sameOriginUrl($redirectPath))
                ->with('type', 'success')
                ->with('message', $message);

        } catch (\Throwable $e) {
            $db->transRollback();

            log_message(
                'error',
                'Room start failed: {message}',
                [
                    'message' =>
                        $e->getMessage(),
                ]
            );

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(
                    false,
                    $e->getMessage(),
                    null,
                    422,
                    'warning'
                );
            }

            return redirect()
                ->back()
                ->with('type', 'warning')
                ->with('message', $e->getMessage());
        }
    }

    public function postDraw()
    {
        if (! session()->get('logged_in')) {
            return $this->response
                ->setStatusCode(401)
                ->setJSON([
                    'success' => false,
                    'message' =>
                        'Требуется авторизация.',
                    'csrfName' =>
                        csrf_token(),
                    'csrfHash' =>
                        csrf_hash(),
                ]);
        }

        $roomId =
            (int) $this->request
                ->getPost('room_id');

        $clientVersion =
            (int) $this->request
                ->getPost('state_version');

        $userId =
            (int) session()->get('user_id');

        if ($roomId <= 0) {
            return $this->response
                ->setStatusCode(422)
                ->setJSON([
                    'success' => false,
                    'message' =>
                        'Некорректная комната.',
                    'csrfName' =>
                        csrf_token(),
                    'csrfHash' =>
                        csrf_hash(),
                ]);
        }

        $db =
            db_connect();

        $db->transBegin();

        try {
            $room = $db->query(
                '
                SELECT *
                FROM game_rooms
                WHERE id = ?
                FOR UPDATE
                ',
                [$roomId]
            )->getRowArray();

            if (! $room) {
                throw new \RuntimeException(
                    'Комната не найдена.'
                );
            }

            if (
                $room['status'] !== 'PLAYING'
                || ($room['game_mode'] ?? 'NORMAL')
                    !== 'BLIND'
            ) {
                $db->transRollback();

                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' =>
                            'Взятие карты доступно '
                            . 'только в режиме «Вслепую».',
                        'csrfName' =>
                            csrf_token(),
                        'csrfHash' =>
                            csrf_hash(),
                    ]);
            }

            if (
                (int) $room['state_version']
                !== $clientVersion
            ) {
                $db->transRollback();

                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' =>
                            'Состояние игры уже изменилось.',
                        'stateVersion' =>
                            (int) $room[
                                'state_version'
                            ],
                        'csrfName' =>
                            csrf_token(),
                        'csrfHash' =>
                            csrf_hash(),
                    ]);
            }

            $player = $db->query(
                '
                SELECT *
                FROM game_room_players
                WHERE room_id = ?
                  AND user_id = ?
                FOR UPDATE
                ',
                [
                    $roomId,
                    $userId,
                ]
            )->getRowArray();

            if (
                ! $player
                || (
                    $player['player_status']
                    ?? 'ACTIVE'
                ) !== 'ACTIVE'
            ) {
                $db->transRollback();

                return $this->response
                    ->setStatusCode(403)
                    ->setJSON([
                        'success' => false,
                        'message' =>
                            'Вы не являетесь активным '
                            . 'игроком этой комнаты.',
                        'csrfName' =>
                            csrf_token(),
                        'csrfHash' =>
                            csrf_hash(),
                    ]);
            }

            if (
                (int) $room[
                    'current_player_user_id'
                ]
                !== $userId
            ) {
                $db->transRollback();

                return $this->response
                    ->setStatusCode(403)
                    ->setJSON([
                        'success' => false,
                        'message' =>
                            'Сейчас ход другого игрока.',
                        'csrfName' =>
                            csrf_token(),
                        'csrfHash' =>
                            csrf_hash(),
                    ]);
            }

            /*
             * В BLIND в руке одновременно
             * может быть только одна карта.
             */
            $existingHand = $db->query(
                '
                SELECT id
                FROM game_room_cards
                WHERE room_id = ?
                  AND owner_user_id = ?
                  AND state = ?
                LIMIT 1
                FOR UPDATE
                ',
                [
                    $roomId,
                    $userId,
                    'HAND',
                ]
            )->getRowArray();

            if ($existingHand) {
                $db->transRollback();

                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' =>
                            'У вас уже есть вытянутая карта.',
                        'csrfName' =>
                            csrf_token(),
                        'csrfHash' =>
                            csrf_hash(),
                    ]);
            }

            $card = $db->query(
                '
                SELECT *
                FROM game_room_cards
                WHERE room_id = ?
                  AND state = ?
                ORDER BY
                    deck_position ASC,
                    id ASC
                LIMIT 1
                FOR UPDATE
                ',
                [
                    $roomId,
                    'DECK',
                ]
            )->getRowArray();

            if (! $card) {
                $db->transRollback();

                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' =>
                            'Колода закончилась.',
                        'csrfName' =>
                            csrf_token(),
                        'csrfHash' =>
                            csrf_hash(),
                    ]);
            }

            $db->table('game_room_cards')
                ->where(
                    'id',
                    (int) $card['id']
                )
                ->update([
                    'state' =>
                        'HAND',
                    'owner_user_id' =>
                        $userId,
                ]);

            $newStateVersion =
                (int) $room['state_version']
                + 1;

            $db->table('game_rooms')
                ->where('id', $roomId)
                ->update([
                    'state_version' =>
                        $newStateVersion,
                    'updated_at' =>
                        date('Y-m-d H:i:s'),
                ]);

            if (! $db->transStatus()) {
                throw new \RuntimeException(
                    'Не удалось взять карту.'
                );
            }

            $db->transCommit();

            return $this->response
                ->setJSON([
                    'success' => true,
                    'message' =>
                        'Карта вытянута.',
                    'card' => [
                        'id' =>
                            (int) $card['id'],
                        'title' =>
                            $card['title'],
                        'shortDescription' =>
                            $card[
                                'short_description'
                            ],
                        'imageSrc' =>
                            ! empty(
                                $card['image_url']
                            )
                                ? '/' . ltrim((string) $card['image_url'], '/')
                                : null,
                        'category' =>
                            $card['category'],
                        'difficulty' =>
                            $card['difficulty'],
                    ],
                    'stateVersion' =>
                        $newStateVersion,
                    'csrfName' =>
                        csrf_token(),
                    'csrfHash' =>
                        csrf_hash(),
                ]);

        } catch (\Throwable $e) {
            $db->transRollback();

            log_message(
                'error',
                'Room draw failed: {message}',
                [
                    'message' =>
                        $e->getMessage(),
                ]
            );

            return $this->response
                ->setStatusCode(500)
                ->setJSON([
                    'success' => false,
                    'message' =>
                        $e->getMessage(),
                    'csrfName' =>
                        csrf_token(),
                    'csrfHash' =>
                        csrf_hash(),
                ]);
        }
    }

    public function postPlace()
    {
        if (! session()->get('logged_in')) {
            return $this->response
                ->setStatusCode(401)
                ->setJSON([
                    'success' => false,
                    'message' => 'Требуется авторизация.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }

        $roomId =
            (int) $this->request->getPost('room_id');
        $roomCardId =
            (int) $this->request->getPost('room_card_id');
        $chosenPosition =
            (int) $this->request->getPost('chosen_position');
        $clientVersion =
            (int) $this->request->getPost('state_version');
        $userId =
            (int) session()->get('user_id');

        if (
            $roomId <= 0
            || $roomCardId <= 0
            || $chosenPosition < 0
        ) {
            return $this->response
                ->setStatusCode(422)
                ->setJSON([
                    'success' => false,
                    'message' => 'Некорректные данные хода.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }

        $db = db_connect();
        $db->transBegin();

        try {
            $room = $db->query(
                'SELECT * FROM game_rooms WHERE id = ? FOR UPDATE',
                [$roomId]
            )->getRowArray();

            if (! $room) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(404)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Комната не найдена.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            $gameMode = strtoupper(
                (string) ($room['game_mode'] ?? 'NORMAL')
            );

            if (! in_array(
                $gameMode,
                ['NORMAL', 'BLIND', 'HARDCORE'],
                true
            )) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Неизвестный игровой режим.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            if ($room['status'] !== 'PLAYING') {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Игра сейчас не активна.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            if ((int) $room['state_version'] !== $clientVersion) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(409)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Состояние игры уже изменилось. Обновите игру.',
                        'stateVersion' => (int) $room['state_version'],
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            $player = $db->query(
                'SELECT * FROM game_room_players '
                . 'WHERE room_id = ? AND user_id = ? FOR UPDATE',
                [$roomId, $userId]
            )->getRowArray();

            if (
                ! $player
                || ($player['player_status'] ?? 'ACTIVE') !== 'ACTIVE'
            ) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(403)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Вы не являетесь активным игроком этой комнаты.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            if ((int) $room['current_player_user_id'] !== $userId) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(403)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Сейчас ход другого игрока.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            $currentCard = $db->query(
                'SELECT * FROM game_room_cards '
                . 'WHERE id = ? AND room_id = ? '
                . 'AND owner_user_id = ? AND state = ? FOR UPDATE',
                [$roomCardId, $roomId, $userId, 'HAND']
            )->getRowArray();

            if (! $currentCard) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(422)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Выбранная карта не найдена в вашей руке.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            $timeline = $db->query(
                'SELECT id, sort_order, timeline_position '
                . 'FROM game_room_cards '
                . 'WHERE room_id = ? AND state = ? '
                . 'ORDER BY timeline_position ASC, id ASC FOR UPDATE',
                [$roomId, 'TIMELINE']
            )->getResultArray();

            if ($chosenPosition > count($timeline)) {
                $db->transRollback();
                return $this->response
                    ->setStatusCode(422)
                    ->setJSON([
                        'success' => false,
                        'message' => 'Некорректная позиция карточки.',
                        'csrfName' => csrf_token(),
                        'csrfHash' => csrf_hash(),
                    ]);
            }

            $currentOrder = (float) $currentCard['sort_order'];
            $leftOrder = $chosenPosition > 0
                ? (float) $timeline[$chosenPosition - 1]['sort_order']
                : null;
            $rightOrder = $chosenPosition < count($timeline)
                ? (float) $timeline[$chosenPosition]['sort_order']
                : null;

            $correct =
                ($leftOrder === null || $currentOrder >= $leftOrder)
                &&
                ($rightOrder === null || $currentOrder <= $rightOrder);

            $now = date('Y-m-d H:i:s');
            $scoreDelta = $correct ? 1 : 0;
            $eliminated = false;
            $mistakes = (int) ($player['mistakes'] ?? 0);
            $mistakeLimit = max(
                1,
                min(3, (int) ($room['mistake_limit'] ?? 3))
            );

            if ($correct) {
                $db->query(
                    'UPDATE game_room_cards '
                    . 'SET timeline_position = timeline_position + 1 '
                    . 'WHERE room_id = ? AND state = ? '
                    . 'AND timeline_position >= ?',
                    [$roomId, 'TIMELINE', $chosenPosition]
                );

                $db->table('game_room_cards')
                    ->where('id', (int) $currentCard['id'])
                    ->update([
                        'state' => 'TIMELINE',
                        'owner_user_id' => null,
                        'timeline_position' => $chosenPosition,
                        'revealed_at' => $now,
                    ]);

                $db->query(
                    'UPDATE game_room_players SET score = score + 1 '
                    . 'WHERE room_id = ? AND user_id = ?',
                    [$roomId, $userId]
                );
            } else {
                /*
                 * Неверная постановка больше не выбивает карту из игры —
                 * она встаёт на свою историческую позицию (по sort_order,
                 * а не по $chosenPosition, который как раз оказался неверным)
                 * с пометкой was_misplaced, чтобы хронология оставалась
                 * исторически верной для всех.
                 */
                $correctPosition = (int) $db->table('game_room_cards')
                    ->where('room_id', $roomId)
                    ->where('state', 'TIMELINE')
                    ->where('sort_order <', $currentCard['sort_order'])
                    ->countAllResults();

                $db->query(
                    'UPDATE game_room_cards '
                    . 'SET timeline_position = timeline_position + 1 '
                    . 'WHERE room_id = ? AND state = ? '
                    . 'AND timeline_position >= ?',
                    [$roomId, 'TIMELINE', $correctPosition]
                );

                $db->table('game_room_cards')
                    ->where('id', (int) $currentCard['id'])
                    ->update([
                        'state' => 'TIMELINE',
                        'owner_user_id' => null,
                        'timeline_position' => $correctPosition,
                        'was_misplaced' => true,
                        'revealed_at' => $now,
                    ]);

                if ($gameMode === 'HARDCORE') {
                    $mistakes++;
                    $eliminated = $mistakes >= $mistakeLimit;

                    $db->table('game_room_players')
                        ->where('room_id', $roomId)
                        ->where('user_id', $userId)
                        ->update([
                            'mistakes' => $mistakes,
                            'player_status' =>
                                $eliminated
                                    ? 'ELIMINATED'
                                    : 'ACTIVE',
                        ]);

                    if ($eliminated) {
                        $this->returnHandToDeck($roomId, $userId);
                    }
                }
            }

            $db->table('game_room_moves')
                ->insert([
                    'room_id' => $roomId,
                    'room_card_id' => (int) $currentCard['id'],
                    'user_id' => $userId,
                    'turn_number' => (int) $room['turn_number'],
                    'state_version_before' => (int) $room['state_version'],
                    'chosen_position' => $chosenPosition,
                    'is_correct' => $correct,
                    'score_delta' => $scoreDelta,
                    'revealed_sort_order' => $currentCard['sort_order'],
                    'created_at' => $now,
                ]);

            /*
             * Штрафной добор: только за неверный ход, ровно 1 карта.
             * Верный ход руку не пополняет — она тает по мере игры, что и
             * делает возможной победу «первым избавился от руки» ниже.
             * Выбывший HARDCORE-игрок карту не добирает.
             */
            $penaltyDrawn = false;

            if (
                ! $correct
                && in_array($gameMode, ['NORMAL', 'HARDCORE'], true)
                && ! $eliminated
            ) {
                $nextCard = $db->query(
                    'SELECT id FROM game_room_cards '
                    . 'WHERE room_id = ? AND state = ? '
                    . 'ORDER BY deck_position ASC, id ASC '
                    . 'LIMIT 1 FOR UPDATE',
                    [$roomId, 'DECK']
                )->getRowArray();

                if ($nextCard) {
                    $penaltyDrawn = true;

                    $db->table('game_room_cards')
                        ->where('id', (int) $nextCard['id'])
                        ->update([
                            'state' => 'HAND',
                            'owner_user_id' => $userId,
                        ]);

                    if ($this->pgBool($player['deck_empty_grace_used'] ?? false)) {
                        $db->table('game_room_players')
                            ->where('room_id', $roomId)
                            ->where('user_id', $userId)
                            ->update(['deck_empty_grace_used' => false]);
                    }
                } elseif (($room['empty_deck_behavior'] ?? 'GRACE') === 'GRACE') {
                    /*
                     * Штраф нечем оплатить — колода пуста.
                     * Первый раз подряд: бесплатный круг без последствий.
                     * Второй раз подряд (grace уже был использован и снова
                     * не сброшен успешным добором выше): игрок выбывает,
                     * его рука возвращается в колоду — это может дать
                     * остальным игрокам карты для доигровки партии.
                     *
                     * pgBool(), не empty()/(bool) напрямую: то же значение
                     * из Postgres может прийти текстом 'f'/'t', а не нативным
                     * PHP bool — см. комментарий у pgBool() (это уже один раз
                     * ломало is_correct таким же образом).
                     */
                    if (! $this->pgBool($player['deck_empty_grace_used'] ?? false)) {
                        $db->table('game_room_players')
                            ->where('room_id', $roomId)
                            ->where('user_id', $userId)
                            ->update(['deck_empty_grace_used' => true]);
                    } else {
                        $eliminated = true;

                        $db->table('game_room_players')
                            ->where('room_id', $roomId)
                            ->where('user_id', $userId)
                            ->update(['player_status' => 'ELIMINATED']);

                        $this->returnHandToDeck($roomId, $userId);
                    }
                }
                /* 'SKIP': штраф просто пропускается, без последствий. */
            }

            $activePlayers = $db->query(
                'SELECT user_id, turn_order, score '
                . 'FROM game_room_players '
                . 'WHERE room_id = ? AND player_status = ? '
                . 'AND turn_order IS NOT NULL '
                . 'ORDER BY turn_order ASC, id ASC FOR UPDATE',
                [$roomId, 'ACTIVE']
            )->getResultArray();

            $deckRemaining = (int) $db->table('game_room_cards')
                ->where('room_id', $roomId)
                ->where('state', 'DECK')
                ->countAllResults();

            $handsRemaining = (int) $db->table('game_room_cards')
                ->where('room_id', $roomId)
                ->where('state', 'HAND')
                ->countAllResults();

            $newStateVersion =
                (int) $room['state_version'] + 1;

            $winnerUserId = null;
            $finished = false;

            /*
             * Последний оставшийся активный игрок побеждает сразу.
             * Раньше это было HARDCORE-специфичным (только там были
             * выбывания), но выбывание по пустой колоде (empty_deck_behavior
             * = GRACE) теперь возможно в любом режиме — проверка больше не
             * гейтится по $gameMode.
             */
            if (count($activePlayers) <= 1) {
                $finished = true;
                if (count($activePlayers) === 1) {
                    $winnerUserId =
                        (int) $activePlayers[0]['user_id'];
                }
            }

            /*
             * Победа — тому, кто первым избавился от руки. Возможно только
             * после ВЕРНОГО хода: неверный ход руку не уменьшает (сыгранная
             * карта уходит на стол, но штрафной добор возвращает +1).
             */
            if (! $finished && $correct) {
                $myHandRemaining = (int) $db->table('game_room_cards')
                    ->where('room_id', $roomId)
                    ->where('owner_user_id', $userId)
                    ->where('state', 'HAND')
                    ->countAllResults();

                if ($myHandRemaining === 0) {
                    $finished = true;
                    $winnerUserId = $userId;
                }
            }

            /*
             * Защитный fallback на вырожденный случай: карт нигде не
             * осталось, а победитель ещё не определён. Очки больше не
             * являются критерием победы, поэтому это фиксируется как ничья.
             */
            if (! $finished && $deckRemaining === 0 && $handsRemaining === 0) {
                $finished = true;
            }

            if ($finished) {
                $db->table('game_rooms')
                    ->where('id', $roomId)
                    ->update([
                        'status' => 'FINISHED',
                        'finished_at' => $now,
                        'current_player_user_id' => null,
                        'current_room_card_id' => null,
                        'state_version' => $newStateVersion,
                        'winner_user_id' => $winnerUserId,
                        'updated_at' => $now,
                    ]);
            } else {
                if (empty($activePlayers)) {
                    throw new \RuntimeException(
                        'Не найден активный игрок.'
                    );
                }

                $currentTurnOrder =
                    (int) $player['turn_order'];

                /*
                 * Для NORMAL/HARDCORE при пустой колоде пропускаем
                 * активных игроков с пустой рукой.
                 * BLIND всегда может ходить, пока DECK не пуст.
                 */
                $candidates = $activePlayers;

                if (
                    in_array($gameMode, ['NORMAL', 'HARDCORE'], true)
                    && $deckRemaining === 0
                ) {
                    $candidates = $db->query(
                        'SELECT p.user_id, p.turn_order, p.score '
                        . 'FROM game_room_players p '
                        . 'WHERE p.room_id = ? '
                        . 'AND p.player_status = ? '
                        . 'AND p.turn_order IS NOT NULL '
                        . 'AND EXISTS (SELECT 1 FROM game_room_cards c '
                        . 'WHERE c.room_id = p.room_id '
                        . 'AND c.owner_user_id = p.user_id '
                        . 'AND c.state = ?) '
                        . 'ORDER BY p.turn_order ASC, p.id ASC',
                        [$roomId, 'ACTIVE', 'HAND']
                    )->getResultArray();
                }

                if (empty($candidates)) {
                    throw new \RuntimeException(
                        'Не найден следующий игрок.'
                    );
                }

                $nextPlayerId = null;
                foreach ($candidates as $item) {
                    if ((int) $item['turn_order'] > $currentTurnOrder) {
                        $nextPlayerId = (int) $item['user_id'];
                        break;
                    }
                }
                if ($nextPlayerId === null) {
                    $nextPlayerId =
                        (int) $candidates[0]['user_id'];
                }

                $db->table('game_rooms')
                    ->where('id', $roomId)
                    ->update([
                        'current_player_user_id' => $nextPlayerId,
                        'current_room_card_id' => null,
                        'turn_number' =>
                            (int) $room['turn_number'] + 1,
                        'state_version' => $newStateVersion,
                        'updated_at' => $now,
                    ]);
            }

            if (! $db->transStatus()) {
                throw new \RuntimeException(
                    'Не удалось сохранить ход.'
                );
            }

            $db->transCommit();

            return $this->response
                ->setJSON([
                    'success' => true,
                    'correct' => $correct,
                    'scoreDelta' => $scoreDelta,
                    'mistakes' => $mistakes,
                    'mistakeLimit' =>
                        $gameMode === 'HARDCORE'
                            ? $mistakeLimit
                            : null,
                    'eliminated' => $eliminated,
                    'penaltyDrawn' => $penaltyDrawn,
                    'revealedValue' =>
                        $currentCard['revealed_value'],
                    'playedCardId' =>
                        (int) $currentCard['id'],
                    'finished' => $finished,
                    'stateVersion' => $newStateVersion,
                    'message' => $eliminated
                        ? 'Вы выбыли из партии: колода пуста, штраф оплатить нечем.'
                        : ($correct
                            ? 'Верно!'
                            : ($penaltyDrawn
                                ? 'Неверно! Карта встала на своё место в хронологии, +1 карта в руку.'
                                : 'Неверно! Карта встала на своё место в хронологии.')),
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);

        } catch (\Throwable $e) {
            $db->transRollback();

            log_message(
                'error',
                'Room move failed: {message}',
                ['message' => $e->getMessage()]
            );

            return $this->response
                ->setStatusCode(500)
                ->setJSON([
                    'success' => false,
                    'message' => $e->getMessage(),
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }
    }

    public function postClose()
    {
        return $this->changeRoomStatus('FINISHED');
    }

    public function postDelete()
    {
        $roomId =
            (int) $this->request->getPost('room_id');

        $db = db_connect();
        $db->transBegin();

        try {
            $room = $db->query(
                'SELECT * FROM game_rooms WHERE id = ? FOR UPDATE',
                [$roomId]
            )->getRowArray();

            if (! $room) {
                throw new \RuntimeException(
                    'Комната не найдена.'
                );
            }

            $userId =
                (int) session()->get('user_id');

            if (
                (int) $room['host_user_id'] !== $userId
                && ! $this->isAdmin()
            ) {
                throw new \RuntimeException(
                    'Удалить комнату может только ведущий или администратор.'
                );
            }

            /*
             * Удаляем явно, чтобы не зависеть
             * от ON DELETE CASCADE конкретной БД.
             */
            $db->table('game_room_moves')
                ->where('room_id', $roomId)
                ->delete();

            $db->table('game_room_cards')
                ->where('room_id', $roomId)
                ->delete();

            $db->table('game_room_players')
                ->where('room_id', $roomId)
                ->delete();

            $db->table('game_rooms')
                ->where('id', $roomId)
                ->delete();

            if (! $db->transStatus()) {
                throw new \RuntimeException(
                    'Не удалось удалить комнату.'
                );
            }

            $db->transCommit();

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(true, 'Комната удалена.', '/rooms', 200, 'success');
            }

            return redirect()
                ->to($this->sameOriginUrl('/rooms'))
                ->with('type', 'success')
                ->with('message', 'Комната удалена.');

        } catch (\Throwable $e) {
            $db->transRollback();

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(false, $e->getMessage(), null, 422, 'danger');
            }

            return redirect()
                ->to($this->sameOriginUrl('/rooms'))
                ->with('type', 'danger')
                ->with('message', $e->getMessage());
        }
    }

    public function postLeave()
    {
        $roomId =
            (int) $this->request->getPost('room_id');

        $userId =
            (int) session()->get('user_id');

        $db = db_connect();

        $room = $db->table('game_rooms')
            ->where('id', $roomId)
            ->get()
            ->getRowArray();

        if (! $room) {
            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(false, 'Комната не найдена.', '/rooms', 404, 'warning');
            }

            return redirect()->to($this->sameOriginUrl('/rooms'));
        }

        if ($room['status'] === 'PLAYING') {
            try {
                $this->forfeitActivePlayer(
                    $roomId,
                    $userId,
                    'LEFT'
                );
            } catch (\Throwable $e) {
                if ($this->isAsyncRoomRequest()) {
                    return $this->asyncRoomResponse(false, $e->getMessage(), null, 422, 'danger');
                }

                return redirect()->to($this->sameOriginUrl('/rooms'))
                    ->with('type', 'danger')
                    ->with('message', $e->getMessage());
            }

            $message = 'Вы вышли из активной партии. Игра продолжилась без вас.';

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(true, $message, '/rooms', 200, 'info');
            }

            return redirect()->to($this->sameOriginUrl('/rooms'))
                ->with('type', 'info')
                ->with('message', $message);
        }

        if ((int) $room['host_user_id'] === $userId) {
            (new GameRoom())->update($roomId, [
                'status' => 'FINISHED',
                'finished_at' => date('Y-m-d H:i:s'),
                'updated_at' => date('Y-m-d H:i:s'),
            ]);
        } else {
            (new GameRoomPlayer())
                ->where('room_id', $roomId)
                ->where('user_id', $userId)
                ->delete();
        }

        if ($this->isAsyncRoomRequest()) {
            return $this->asyncRoomResponse(true, 'Вы вышли из комнаты.', '/rooms', 200, 'info');
        }

        return redirect()->to($this->sameOriginUrl('/rooms'))
            ->with('type', 'info')
            ->with('message', 'Вы вышли из комнаты.');
    }

    public function postRematch()
    {
        $roomId =
            (int) $this->request->getPost('room_id');

        $userId =
            (int) session()->get('user_id');

        $db = db_connect();
        $db->transBegin();

        try {
            $room = $db->query(
                'SELECT * FROM game_rooms WHERE id = ? FOR UPDATE',
                [$roomId]
            )->getRowArray();

            if (! $room) {
                throw new \RuntimeException('Комната не найдена.');
            }

            if (
                (int) $room['host_user_id'] !== $userId
                && ! $this->isAdmin()
            ) {
                throw new \RuntimeException(
                    'Реванш может запустить только ведущий или администратор.'
                );
            }

            if ($room['status'] !== 'FINISHED') {
                throw new \RuntimeException(
                    'Реванш доступен только после завершения партии.'
                );
            }

            /* Игроков, которые явно вышли, в реванш не возвращаем. */
            $db->table('game_room_players')
                ->where('room_id', $roomId)
                ->where('player_status', 'LEFT')
                ->delete();

            $remaining = (int) $db->table('game_room_players')
                ->where('room_id', $roomId)
                ->countAllResults();

            if ($remaining < 2) {
                throw new \RuntimeException(
                    'Для реванша нужно минимум два оставшихся игрока.'
                );
            }

            $db->table('game_room_moves')
                ->where('room_id', $roomId)
                ->delete();

            $db->table('game_room_cards')
                ->where('room_id', $roomId)
                ->delete();

            $now = date('Y-m-d H:i:s');

            $db->table('game_room_players')
                ->where('room_id', $roomId)
                ->update([
                    'score' => 0,
                    'mistakes' => 0,
                    'player_status' => 'ACTIVE',
                    'turn_order' => null,
                    'last_seen_at' => $now,
                ]);

            $db->table('game_rooms')
                ->where('id', $roomId)
                ->update([
                    'status' => 'WAITING',
                    'started_at' => null,
                    'finished_at' => null,
                    'current_player_user_id' => null,
                    'current_room_card_id' => null,
                    'turn_number' => 0,
                    'state_version' => 0,
                    'winner_user_id' => null,
                    'updated_at' => $now,
                ]);

            if (! $db->transStatus()) {
                throw new \RuntimeException('Не удалось подготовить реванш.');
            }

            $db->transCommit();

            $redirectPath = '/rooms/show/' . $room['code'];

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(true, 'Комната готова к реваншу.', $redirectPath, 200, 'success');
            }

            return redirect()->to($this->sameOriginUrl($redirectPath))
                ->with('type', 'success')
                ->with('message', 'Комната готова к реваншу.');

        } catch (\Throwable $e) {
            $db->transRollback();

            if ($this->isAsyncRoomRequest()) {
                return $this->asyncRoomResponse(false, $e->getMessage(), null, 422, 'warning');
            }

            return redirect()->back()
                ->with('type', 'warning')
                ->with('message', $e->getMessage());
        }
    }

    private function changeRoomStatus(string $status)
    {
        $roomId = (int) $this->request->getPost('room_id');
        $roomModel = new GameRoom();
        $room = $roomModel->find($roomId);

        if (! $room || ((int) $room['host_user_id'] !== (int) session()->get('user_id') && ! $this->isAdmin())) {
            return redirect()->to($this->sameOriginUrl('/rooms'))->with('type', 'danger')->with('message', 'Недостаточно прав для управления комнатой.');
        }

        $data = ['status' => $status, 'updated_at' => date('Y-m-d H:i:s')];
        if ($status === 'PLAYING') {
            if ($room['status'] !== 'WAITING') {
                return redirect()->back()->with('type', 'warning')->with('message', 'Эту комнату уже нельзя запустить.');
            }
            $data['started_at'] = date('Y-m-d H:i:s');
        } else {
            $data['finished_at'] = date('Y-m-d H:i:s');
        }

        if (! $roomModel->update($roomId, $data)) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Не удалось изменить состояние комнаты.');
        }

        return redirect()->back()->with('type', 'success')->with(
            'message',
            $status === 'PLAYING' ? 'Игра запущена.' : 'Комната закрыта.'
        );
    }

    private function asyncRoomResponse(
        bool $success,
        string $message,
        ?string $redirect = null,
        int $statusCode = 200,
        string $type = 'info'
    ) {
        $payload = [
            'success' => $success,
            'message' => $message,
            'type' => $type,
            'csrfName' => csrf_token(),
            'csrfHash' => csrf_hash(),
        ];

        if ($redirect !== null) {
            $payload['redirect'] = $redirect;
        }

        return $this->response
            ->setStatusCode($statusCode)
            ->setJSON($payload);
    }

    private function isAsyncRoomRequest(): bool
    {
        return $this->request->isAJAX();
    }

    private function touchPlayerPresence(
        int $roomId,
        int $userId
    ): void {
        /*
         * State polling идёт часто, но запись presence
         * делаем не чаще одного раза примерно в 15 секунд.
         */
        db_connect()->query(
            "UPDATE game_room_players
             SET last_seen_at = NOW()
             WHERE room_id = ?
               AND user_id = ?
               AND player_status != 'LEFT'
               AND (
                    last_seen_at IS NULL
                    OR last_seen_at < NOW() - INTERVAL '15 seconds'
               )",
            [$roomId, $userId]
        );
    }

    private function resolveStaleCurrentPlayer(
        int $roomId
    ): void {
        $db = db_connect();

        $room = $db->table('game_rooms')
            ->where('id', $roomId)
            ->get()
            ->getRowArray();

        if (
            ! $room
            || $room['status'] !== 'PLAYING'
            || empty($room['current_player_user_id'])
        ) {
            return;
        }

        $current = $db->table('game_room_players')
            ->select('user_id, last_seen_at, player_status')
            ->where('room_id', $roomId)
            ->where(
                'user_id',
                (int) $room['current_player_user_id']
            )
            ->get()
            ->getRowArray();

        if (! $current) {
            return;
        }

        if (($current['player_status'] ?? 'ACTIVE') !== 'ACTIVE') {
            return;
        }

        $seenAt = ! empty($current['last_seen_at'])
            ? strtotime((string) $current['last_seen_at'])
            : 0;

        /* Три минуты — достаточно мягкий порог для мобильной сети. */
        if ($seenAt >= time() - 180) {
            return;
        }

        try {
            $this->forfeitActivePlayer(
                $roomId,
                (int) $current['user_id'],
                'ELIMINATED'
            );
        } catch (\Throwable $e) {
            /*
             * Автовыбывание — фоновая проверка при каждом опросе
             * состояния комнаты. Временный сбой (например, конфликт
             * блокировок при параллельных запросах) не должен
             * приводить к 500 на getState().
             */
            log_message(
                'error',
                'Auto-forfeit failed: {message}',
                ['message' => $e->getMessage()]
            );
        }
    }

    private function forfeitActivePlayer(
        int $roomId,
        int $userId,
        string $status
    ): void {
        if (! in_array($status, ['ELIMINATED', 'LEFT'], true)) {
            throw new \InvalidArgumentException('Некорректный статус игрока.');
        }

        $db = db_connect();
        $db->transBegin();

        try {
            $room = $db->query(
                'SELECT * FROM game_rooms WHERE id = ? FOR UPDATE',
                [$roomId]
            )->getRowArray();

            if (! $room || $room['status'] !== 'PLAYING') {
                $db->transRollback();
                return;
            }

            $player = $db->query(
                'SELECT * FROM game_room_players '
                . 'WHERE room_id = ? AND user_id = ? FOR UPDATE',
                [$roomId, $userId]
            )->getRowArray();

            if (! $player) {
                $db->transRollback();
                return;
            }

            if (($player['player_status'] ?? 'ACTIVE') !== 'ACTIVE') {
                $db->transRollback();
                return;
            }

            /* Возвращаем несыгранную руку в конец колоды. */
            $cards = $db->query(
                'SELECT id FROM game_room_cards '
                . 'WHERE room_id = ? AND owner_user_id = ? AND state = ? '
                . 'ORDER BY id ASC FOR UPDATE',
                [$roomId, $userId, 'HAND']
            )->getResultArray();

            $maxDeck = $db->query(
                'SELECT COALESCE(MAX(deck_position), 0) AS max_pos '
                . 'FROM game_room_cards WHERE room_id = ?',
                [$roomId]
            )->getRowArray();

            $deckPosition = (int) ($maxDeck['max_pos'] ?? 0);

            foreach ($cards as $card) {
                $deckPosition++;
                $db->table('game_room_cards')
                    ->where('id', (int) $card['id'])
                    ->update([
                        'state' => 'DECK',
                        'owner_user_id' => null,
                        'timeline_position' => null,
                        'deck_position' => $deckPosition,
                    ]);
            }

            $db->table('game_room_players')
                ->where('room_id', $roomId)
                ->where('user_id', $userId)
                ->update([
                    'player_status' => $status,
                    'last_seen_at' => date('Y-m-d H:i:s'),
                ]);

            $active = $db->query(
                'SELECT user_id, turn_order, score '
                . 'FROM game_room_players '
                . 'WHERE room_id = ? AND player_status = ? '
                . 'AND turn_order IS NOT NULL '
                . 'ORDER BY turn_order ASC, id ASC FOR UPDATE',
                [$roomId, 'ACTIVE']
            )->getResultArray();

            $now = date('Y-m-d H:i:s');
            $newVersion = (int) ($room['state_version'] ?? 0) + 1;

            if (count($active) <= 1) {
                $winnerId = count($active) === 1
                    ? (int) $active[0]['user_id']
                    : null;

                $db->table('game_rooms')
                    ->where('id', $roomId)
                    ->update([
                        'status' => 'FINISHED',
                        'finished_at' => $now,
                        'current_player_user_id' => null,
                        'current_room_card_id' => null,
                        'winner_user_id' => $winnerId,
                        'state_version' => $newVersion,
                        'updated_at' => $now,
                    ]);
            } else {
                $currentOrder = $player['turn_order'] !== null
                    ? (int) $player['turn_order']
                    : -1;

                $nextId = null;
                foreach ($active as $candidate) {
                    if ((int) $candidate['turn_order'] > $currentOrder) {
                        $nextId = (int) $candidate['user_id'];
                        break;
                    }
                }
                if ($nextId === null) {
                    $nextId = (int) $active[0]['user_id'];
                }

                $update = [
                    'state_version' => $newVersion,
                    'updated_at' => $now,
                ];

                /*
                 * Если ушёл не текущий игрок — текущий ход не ломаем.
                 * Если ушёл текущий — передаём ход дальше.
                 */
                if (
                    (int) ($room['current_player_user_id'] ?? 0)
                    === $userId
                ) {
                    $update['current_player_user_id'] = $nextId;
                    $update['current_room_card_id'] = null;
                    $update['turn_number'] =
                        (int) ($room['turn_number'] ?? 0) + 1;
                }

                /* Ведущий может выйти/пропасть — передаём роль. */
                if ((int) $room['host_user_id'] === $userId) {
                    $update['host_user_id'] = $nextId;
                }

                $db->table('game_rooms')
                    ->where('id', $roomId)
                    ->update($update);
            }

            if (! $db->transStatus()) {
                throw new \RuntimeException(
                    'Не удалось корректно вывести игрока из партии.'
                );
            }

            $db->transCommit();

        } catch (\Throwable $e) {
            $db->transRollback();
            throw $e;
        }
    }

    private function pruneInactiveRooms(): void
    {
        $db = db_connect();
        $now = date('Y-m-d H:i:s');

        /*
         * WAITING: 24h без изменений.
         * PLAYING: 12h без игрового действия.
         *
         * Это lazy cleanup: он запускается при обращении
         * к разделу комнат и игровым endpoints.
         */
        $db->query(
            "UPDATE game_rooms
             SET status = 'FINISHED',
                 finished_at = COALESCE(finished_at, ?),
                 current_player_user_id = NULL,
                 current_room_card_id = NULL,
                 state_version = COALESCE(state_version, 0) + 1,
                 updated_at = ?
             WHERE status = 'WAITING'
               AND updated_at < NOW() - INTERVAL '24 hours'",
            [$now, $now]
        );

        $db->query(
            "UPDATE game_rooms
             SET status = 'FINISHED',
                 finished_at = COALESCE(finished_at, ?),
                 current_player_user_id = NULL,
                 current_room_card_id = NULL,
                 state_version = COALESCE(state_version, 0) + 1,
                 updated_at = ?
             WHERE status = 'PLAYING'
               AND updated_at < NOW() - INTERVAL '12 hours'",
            [$now, $now]
        );

        /*
         * Гостевые аккаунты (Rooms::postGuestJoin(), users.is_guest) —
         * временные. Ни выход игрока, ни завершение партии, ни удаление
         * комнаты не удаляют строку users напрямую (слишком много разных
         * мест это меняют — легко забыть одно и оставить утечку), поэтому
         * чистим лениво здесь же: гость живёт, пока у него есть ACTIVE-
         * членство хоть в одной ещё не FINISHED комнате. 60 секунд — не
         * защита от реальной гонки (её нет: аккаунт и вступление в комнату
         * создаются в одном запросе postGuestJoin()->postJoin()), а просто
         * подстраховка.
         */
        $db->query(
            "DELETE FROM users
             WHERE is_guest = true
               AND created_at < NOW() - INTERVAL '60 seconds'
               AND id NOT IN (
                   SELECT p.user_id
                     FROM game_room_players p
                     JOIN game_rooms r ON r.id = p.room_id
                    WHERE p.player_status = 'ACTIVE'
                      AND r.status IN ('WAITING', 'PLAYING')
               )"
        );
    }

    private function findRoomForMember(string $code): ?array
    {
        $builder = db_connect()->table('game_rooms r')
            ->select('r.*, g.title AS game_title, u.username AS host_username')
            ->join('game_templates g', 'g.id = r.game_template_id')
            ->join('users u', 'u.id = r.host_user_id');

        if (! $this->isAdmin()) {
            $builder->join('game_room_players p', 'p.room_id = r.id')
                ->where('p.user_id', (int) session()->get('user_id'))
                ->where('p.player_status !=', 'LEFT');
        }

        $room = $builder->where('r.code', strtoupper($code))->get()->getRowArray();

        return $room ?: null;
    }

    private function getPlayers(int $roomId): array
    {
        return db_connect()->table('game_room_players p')
            ->select('p.user_id, p.score, p.mistakes, p.player_status, p.last_seen_at, p.joined_at, u.username')
            ->join('users u', 'u.id = p.user_id')
            ->where('p.room_id', $roomId)
            ->orderBy('p.joined_at', 'ASC')
            ->get()
            ->getResultArray();
    }

    private function generateUniqueCode(GameRoom $roomModel): string
    {
        $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

        do {
            $code = '';
            for ($i = 0; $i < 6; $i++) {
                $code .= $alphabet[random_int(0, strlen($alphabet) - 1)];
            }
        } while ($roomModel->where('code', $code)->first());

        return $code;
    }
    private function buildInviteUrl(
        string $code,
        ?string $baseUrl = null
    ): string {
        $baseUrl = $this->normalizeBaseUrl(
            $baseUrl ?: $this->detectRoomBaseUrl()
        );

        return $baseUrl
            . '/rooms/invite/'
            . rawurlencode(
                strtoupper($code)
            );
    }

    /**
     * (bool) на значении boolean-колонки Postgres небезопасен: если значение
     * дошло как текст 'f'/'t' (так Postgres пишет false/true в текстовом
     * представлении), а не как нативный PHP bool, то (bool) 'f' даёт true —
     * это непустая строка. Из-за этого game_room_moves.is_correct = false
     * читался обратно как true везде, кроме прямого ответа postPlace()
     * (там использовалась исходная PHP-переменная $correct, а не значение
     * из БД): игрок, который ходил, видел «неверно», а все остальные —
     * через getState()/getPlay() — «верно» для того же самого хода.
     */
    /**
     * Возвращает оставшуюся руку игрока в конец колоды (перемешивая).
     * Общий код для HARDCORE-выбывания по лимиту ошибок и для выбывания
     * по повторной ошибке при пустой колоде (empty_deck_behavior=GRACE).
     */
    private function returnHandToDeck(int $roomId, int $userId): void
    {
        $db = db_connect();

        $returned = $db->query(
            'SELECT id FROM game_room_cards '
            . 'WHERE room_id = ? '
            . 'AND owner_user_id = ? AND state = ? '
            . 'ORDER BY id ASC FOR UPDATE',
            [$roomId, $userId, 'HAND']
        )->getResultArray();

        shuffle($returned);

        $maxDeck = $db->query(
            'SELECT COALESCE(MAX(deck_position), 0) AS max_pos '
            . 'FROM game_room_cards WHERE room_id = ?',
            [$roomId]
        )->getRowArray();

        $position = (int) ($maxDeck['max_pos'] ?? 0);

        foreach ($returned as $item) {
            $position++;
            $db->table('game_room_cards')
                ->where('id', (int) $item['id'])
                ->update([
                    'state' => 'DECK',
                    'owner_user_id' => null,
                    'timeline_position' => null,
                    'deck_position' => $position,
                ]);
        }
    }

    private function pgBool(mixed $value): bool
    {
        if (is_string($value)) {
            return ! in_array(strtolower($value), ['f', 'false', '0', ''], true);
        }

        return (bool) $value;
    }

    /**
     * Адрес для приглашения, определяемый на момент вызова.
     *
     * Если открыли проект по LAN-домену/IP,
     * используем текущий Host как есть.
     *
     * Если открыли localhost, пытаемся определить
     * LAN-IP машины, на которой запущен PHP-сервер,
     * чтобы QR можно было открыть с телефона.
     */
    private function detectRoomBaseUrl(): string
    {
        /** @var \Config\GameNetwork $network */
        $network = config('GameNetwork');

        /*
         * Production can pin invite links to one known origin.
         * This completely removes Host-header influence from QR generation.
         */
        $fixedBaseUrl = trim((string) $network->inviteBaseURL);

        if ($fixedBaseUrl !== '') {
            return $this->normalizeBaseUrl($fixedBaseUrl);
        }

        /*
         * For LAN development use only the validated origin from
         * BaseController::requestOrigin(). Arbitrary HTTP_HOST values are
         * rejected there by the allowlist/private-network policy.
         */
        $origin = $this->requestOrigin();

        if ($origin === null) {
            /** @var \Config\App $app */
            $app = config('App');
            return $this->normalizeBaseUrl((string) $app->baseURL);
        }

        $parts = parse_url($origin);

        if (! is_array($parts) || ! isset($parts['scheme'], $parts['host'])) {
            /** @var \Config\App $app */
            $app = config('App');
            return $this->normalizeBaseUrl((string) $app->baseURL);
        }

        $scheme = strtolower((string) $parts['scheme']);
        $host = trim((string) $parts['host'], '[]');
        $port = isset($parts['port']) ? (int) $parts['port'] : null;

        if ($this->isLoopbackHost($host)) {
            $lanHost = $this->detectLanHost();

            if ($lanHost !== null) {
                $host = $lanHost;
            }
        }

        $displayHost = str_contains($host, ':')
            ? '[' . trim($host, '[]') . ']'
            : $host;

        $base = $scheme . '://' . $displayHost;

        if (
            $port !== null
            && $port > 0
            && ! (
                ($scheme === 'http' && $port === 80)
                || ($scheme === 'https' && $port === 443)
            )
        ) {
            $base .= ':' . $port;
        }

        return $this->normalizeBaseUrl($base);
    }

    private function normalizeBaseUrl(string $baseUrl): string
    {
        $baseUrl = trim($baseUrl);

        if ($baseUrl === '') {
            return rtrim($this->sameOriginUrl('/'), '/');
        }

        $parts = parse_url($baseUrl);

        if (
            ! is_array($parts)
            || ! isset($parts['scheme'], $parts['host'])
            || ! in_array(strtolower((string) $parts['scheme']), ['http', 'https'], true)
        ) {
            return rtrim($this->sameOriginUrl('/'), '/');
        }

        $scheme = strtolower((string) $parts['scheme']);
        $host = trim((string) $parts['host']);
        $displayHost = str_contains($host, ':')
            ? '[' . trim($host, '[]') . ']'
            : $host;

        $normalized = $scheme . '://' . $displayHost;

        if (isset($parts['port'])) {
            $port = (int) $parts['port'];
            $isDefault =
                ($scheme === 'http' && $port === 80)
                || ($scheme === 'https' && $port === 443);

            if (! $isDefault && $port > 0 && $port <= 65535) {
                $normalized .= ':' . $port;
            }
        }

        return rtrim($normalized, '/');
    }

    private function isLoopbackHost(string $host): bool
    {
        $host = strtolower(trim($host, '[]'));

        return in_array(
            $host,
            [
                'localhost',
                '127.0.0.1',
                '::1',
                '0.0.0.0',
            ],
            true
        );
    }

    private function detectLanHost(): ?string
    {
        $candidates = [];

        $serverAddress = trim(
            (string) ($_SERVER['SERVER_ADDR'] ?? '')
        );

        if ($serverAddress !== '') {
            $candidates[] = $serverAddress;
        }

        $hostname = gethostname();

        if (is_string($hostname) && $hostname !== '') {
            $resolved = gethostbyname($hostname);

            if ($resolved !== $hostname) {
                $candidates[] = $resolved;
            }
        }

        foreach ($candidates as $candidate) {
            $candidate = trim($candidate, '[]');

            if (
                filter_var(
                    $candidate,
                    FILTER_VALIDATE_IP
                )
                && ! $this->isLoopbackHost($candidate)
            ) {
                return $candidate;
            }
        }

        return null;
    }
}
