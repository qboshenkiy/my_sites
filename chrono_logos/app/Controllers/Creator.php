<?php

namespace App\Controllers;

use App\Controllers\BaseController;
use App\Models\Chronos\GameTemplate;
use App\Models\Chronos\Card;

class Creator extends BaseController
{
    public function getGenesisJson()
    {
        return $this->response->setContentType('application/json')
            ->setHeader('Content-Disposition', 'attachment; filename="genesis-50.json"')
            ->setBody(file_get_contents(APPPATH . 'Data/genesis-50.json'));
    }

    public function getImportJson()
    {
        $gameId = (int) $this->request->getGet('game_id');
        $game = $gameId ? $this->getOwnedGame($gameId) : null;
        if ($gameId && !$game) {
            throw \CodeIgniter\Exceptions\PageNotFoundException::forPageNotFound();
        }
        return view('Chronos/creator/import', ['title' => 'Импорт хронологии', 'game' => $game,
            'preset' => $this->request->getGet('preset') === 'genesis']);
    }

    public function postImportJson()
    {
        $db = db_connect();
        $transaction = false;
        try {
            $data = \App\Libraries\TimelineImport::parse((string) $this->request->getPost('json'));
            $gameId = (int) $this->request->getPost('game_id');
            $game = $gameId ? $this->getOwnedGame($gameId) : null;
            if ($gameId && !$game) {
                return $this->json(['success' => false, 'message' => 'Игра не найдена.'], 404);
            }
            if ($this->request->getPost('preview') === '1') {
                if ($gameId && $this->request->getPost('order_mode') === 'after') {
                    $last = $db->query('SELECT COALESCE(CEIL(MAX(sort_order)), 0) AS last FROM cards WHERE game_template_id = ?', [$gameId])->getRowArray();
                    $data['cards'] = \App\Libraries\TimelineImport::appendAfter($data['cards'], (int) $last['last']);
                }
                return $this->json(['success' => true, 'title' => $data['title'], 'description' => $data['description'], 'cards' => $data['cards']]);
            }
            $db->transBegin();
            $transaction = true;
            if (!$gameId) {
                $gameId = (new GameTemplate())->insert(['user_id' => (int) session()->get('user_id'),
                    'title' => $data['title'], 'description' => $data['description'], 'status' => 'DRAFT', 'language' => 'ru']);
                if (!$gameId) {
                    throw new \RuntimeException('Не удалось создать игру.');
                }
            }
            // Serialize append operations, so imports cannot interleave positions.
            $db->query('SELECT id FROM game_templates WHERE id = ? FOR UPDATE', [$gameId]);
            if ($game && $this->request->getPost('order_mode') === 'after') {
                $last = $db->query('SELECT COALESCE(CEIL(MAX(sort_order)), 0) AS last FROM cards WHERE game_template_id = ?', [$gameId])->getRowArray();
                $data['cards'] = \App\Libraries\TimelineImport::appendAfter($data['cards'], (int) $last['last']);
            }
            $max = $db->table('cards')->selectMax('editor_position', 'position')->where('game_template_id', $gameId)->get()->getRowArray();
            $position = $max['position'] === null ? 0 : (int) $max['position'] + 1;
            foreach ($data['cards'] as $card) {
                if (!(new Card())->insert($card + ['game_template_id' => $gameId, 'editor_position' => $position++])) {
                    throw new \RuntimeException('Не удалось сохранить карточку.');
                }
            }
            if (!$db->transStatus()) {
                throw new \RuntimeException('Импорт не завершён.');
            }
            $db->transCommit();
            $transaction = false;
            return $this->json(['success' => true, 'message' => 'Добавлено карточек: ' . count($data['cards']),
                'editor_url' => '/creator/edit/' . (int) $gameId]);
        } catch (\InvalidArgumentException $e) {
            if ($transaction) $db->transRollback();
            return $this->json(['success' => false, 'message' => $e->getMessage()], 422);
        } catch (\Throwable $e) {
            if ($transaction) $db->transRollback();
            log_message('error', 'Timeline import failed: {message}', ['message' => $e->getMessage()]);
            return $this->json(['success' => false, 'message' => 'Не удалось импортировать. Изменения отменены.'], 500);
        }
    }

    public function postSelectCards()
    {
        $gameId = (int) $this->request->getPost('game_id');
        if (!$this->getOwnedGame($gameId)) {
            return $this->json(['success' => false, 'message' => 'Игра не найдена.'], 404);
        }
        $ids = json_decode((string) $this->request->getPost('ids'), true);
        $enabled = $this->request->getPost('enabled');
        if (!is_array($ids) || !array_is_list($ids) || !$ids || count($ids) > 1000
            || count(array_filter($ids, static fn($id) => is_int($id) && $id > 0)) !== count($ids)
            || !in_array($enabled, ['0', '1'], true)) {
            return $this->json(['success' => false, 'message' => 'Неверный список карточек.'], 422);
        }
        $db = db_connect();
        $count = $db->table('cards')->where('game_template_id', $gameId)->whereIn('id', array_unique($ids))->countAllResults();
        if ($count !== count(array_unique($ids))) {
            return $this->json(['success' => false, 'message' => 'В списке есть карточки другой игры.'], 403);
        }
        if (!$db->table('cards')->where('game_template_id', $gameId)->whereIn('id', $ids)->update(['is_enabled' => $enabled === '1'])) {
            return $this->json(['success' => false, 'message' => 'Не удалось сохранить состав.'], 500);
        }
        return $this->json(['success' => true]);
    }

    public function getExportJson(int $gameId)
    {
        $game = $this->getOwnedGame($gameId);
        if (!$game) {
            throw \CodeIgniter\Exceptions\PageNotFoundException::forPageNotFound();
        }
        $cards = (new Card())->select('title, short_description, sort_order, revealed_value, category, difficulty, is_enabled')
            ->where('game_template_id', $gameId)->orderBy('editor_position', 'ASC')->orderBy('id', 'ASC')->findAll();
        foreach ($cards as &$card) {
            $card['is_enabled'] = in_array($card['is_enabled'], [true, 1, '1', 't'], true);
            foreach (['short_description', 'revealed_value', 'category'] as $key) {
                $card[$key] = $card[$key] ?? '';
            }
        }
        unset($card);
        return $this->response->setHeader('Content-Disposition', 'attachment; filename="chrono-game-' . $gameId . '.json"')
            ->setJSON(['title' => $game['title'], 'description' => $game['description'] ?? '', 'cards' => $cards]);
    }

    /*
     * GET больше ничего не создаёт.
     * Это важно: безопасные GET-запросы не должны менять БД.
     */
    public function getNew()
    {
        return redirect()
            ->to($this->sameOriginUrl('/creator/games'))
            ->with('type', 'info')
            ->with('message', 'Создайте игру кнопкой «Создать игру».');
    }

    /*
     * POST /creator/new
     * Создание игры и первой карточки выполняется одной транзакцией.
     */
    public function postNew()
    {
        $db = db_connect();
        $db->transBegin();

        try {
            $gameModel = new GameTemplate();
            $cardModel = new Card();

            $gameId = $gameModel->insert([
                'user_id' => (int) session()->get('user_id'),
                'title' => 'Новая игра',
                'status' => 'DRAFT',
                'language' => 'ru',
            ]);

            if ($gameId === false) {
                throw new \RuntimeException('Не удалось создать игру.');
            }

            $cardId = $cardModel->insert([
                'game_template_id' => (int) $gameId,
                'title' => '',
                'editor_position' => 0,
                'difficulty' => 'NORMAL',
            ]);

            if ($cardId === false) {
                throw new \RuntimeException('Не удалось создать первую карточку.');
            }

            if (! $db->transStatus()) {
                throw new \RuntimeException('Ошибка транзакции создания игры.');
            }

            $db->transCommit();

            $redirect = '/creator/edit/' . (int) $gameId;

            if ($this->request->isAJAX()) {
                return $this->json([
                    'success' => true,
                    'type' => 'success',
                    'message' => 'Игра создана.',
                    'redirect' => $redirect,
                    'gameId' => (int) $gameId,
                ]);
            }

            return redirect()->to($this->sameOriginUrl($redirect));
        } catch (\Throwable $e) {
            $db->transRollback();

            log_message('error', 'Create game failed: {message}', [
                'message' => $e->getMessage(),
            ]);

            if ($this->request->isAJAX()) {
                return $this->json([
                    'success' => false,
                    'type' => 'danger',
                    'message' => 'Не удалось создать игру.',
                ], 500);
            }

            return redirect()
                ->to($this->sameOriginUrl('/creator/games'))
                ->with('type', 'danger')
                ->with('message', 'Не удалось создать игру.');
        }
    }


    /*
     * Редактор.
     *
     * GET /creator/edit/15
     */
    public function getEdit(int $gameId)
    {
        $game = $this->getOwnedGame($gameId);

        if (! $game) {
            throw \CodeIgniter\Exceptions\PageNotFoundException::forPageNotFound();
        }

        $cardModel = new Card();

        $cards = $cardModel
            ->where('game_template_id', $gameId)
            ->orderBy('editor_position', 'ASC')
            ->orderBy('id', 'ASC')
            ->findAll();

        return view('Chronos/creator/editor', [
            'title' => 'Редактор игры',
            'game'  => $game,
            'cards' => $cards,
        ]);
    }


    /*
     * AJAX autosave основных данных игры.
     */
    public function postSaveGame()
    {
        if (! $this->request->is('post')) {
            return $this->json([
                'success' => false,
                'message' => 'Method not allowed',
            ], 405);
        }

        $gameId = (int) $this->request->getPost('game_id');

        $game = $this->getOwnedGame($gameId);

        if (! $game) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Игра не найдена.',
            ], 404);
        }

        $title = trim(
            (string) $this->request->getPost('title')
        );

        $description = trim(
            (string) $this->request->getPost('description')
        );

        if (mb_strlen($title) > 150) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',
                'message' => 'Название слишком длинное.',
            ], 422);
        }

        $gameModel = new GameTemplate();

        $version =
            ((int) $game['autosave_version']) + 1;

        if (! $gameModel->update($gameId, [
            'title' =>
            $title !== ''
                ? $title
                : 'Новая игра',

            'description' =>
            $description !== ''
                ? $description
                : null,

            'autosave_version' => $version,
        ])) {
            return $this->json([
                'success' => false,
                'type' => 'danger',
                'message' => 'Не удалось сохранить игру.',
            ], 500);
        }

        return $this->json([
            'success' => true,
            'version' => $version,
        ]);
    }


    /*
     * AJAX: добавить карточку.
     */

    public function getGames()
    {
        $userId = (int) session()->get('user_id');

        $gameModel = new GameTemplate();
        $cardModel = new Card();


        /*
     * Получаем только игры текущего пользователя.
     */
        $games = $gameModel
            ->where('user_id', $userId)
            ->orderBy('updated_at', 'DESC')
            ->orderBy('id', 'DESC')
            ->findAll();


        /*
     * Добавляем служебную информацию
     * для страницы "Мои игры".
     */
        foreach ($games as &$game) {

            /*
         * Количество карточек.
         */
            $game['cards_count'] = $cardModel
                ->where(
                    'game_template_id',
                    $game['id']
                )
                ->countAllResults();


            /*
         * Ищем первую карточку с изображением.
         */
            $preview = $cardModel
                ->select('image_url')
                ->where(
                    'game_template_id',
                    $game['id']
                )
                ->where(
                    'image_url IS NOT NULL',
                    null,
                    false
                )
                ->orderBy(
                    'editor_position',
                    'ASC'
                )
                ->first();


            $game['preview_src'] =
                ! empty($preview['image_url'])
                ? '/' . ltrim((string) $preview['image_url'], '/')
                : null;
        }

        unset($game);


        return view('Chronos/creator/games', [
            'title' => 'Мои игры',
            'games' => $games,
        ]);
    }
    public function postDeleteGame()
    {
        $gameId =
            (int) $this->request->getPost('game_id');


        /*
     * Проверяем, что игра принадлежит
     * текущему пользователю.
     */
        $game = $this->getOwnedGame($gameId);


        if (! $game) {

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Игра не найдена.',
            ], 404);
        }


        $cardModel = new Card();


        /*
     * Запоминаем картинки перед удалением.
     *
     * Сами cards удалятся PostgreSQL через
     * ON DELETE CASCADE.
     */
        $cards = $cardModel
            ->select('image_url')
            ->where(
                'game_template_id',
                $gameId
            )
            ->findAll();


        $gameModel =
            new GameTemplate();


        /*
     * Удаляем игру.
     */
        if (! $gameModel->delete($gameId)) {

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось удалить игру.',
            ], 500);
        }


        /*
     * Удаляем изображения с диска.
     */
        foreach ($cards as $card) {
            $this->deleteCardImageFile(
                $card['image_url'] ?? null
            );
        }

        return $this->json([
            'success' => true,
            'type'    => 'success',
            'message' => 'Игра удалена.',
        ]);
    }
    public function postAddCard()
    {
        if (! $this->request->is('post')) {
            return $this->json([
                'success' => false,
            ], 405);
        }

        $gameId = (int) $this->request->getPost('game_id');

        $game = $this->getOwnedGame($gameId);

        if (! $game) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Игра не найдена.',
            ], 404);
        }

        $cardModel = new Card();

        $max = $cardModel
            ->selectMax(
                'editor_position',
                'max_position'
            )
            ->where('game_template_id', $gameId)
            ->first();

        $position =
            ((int) ($max['max_position'] ?? -1)) + 1;

        $cardId = $cardModel->insert([
            'game_template_id' => $gameId,
            'title'            => '',
            'editor_position'  => $position,
            'difficulty'       => 'NORMAL',
        ]);

        if ($cardId === false) {
            return $this->json([
                'success' => false,
                'type' => 'danger',
                'message' => 'Не удалось добавить карточку.',
            ], 500);
        }

        return $this->json([
            'success' => true,

            'card' => [
                'id'              => $cardId,
                'title'           => '',
                'description'     => '',
                'sort_order'      => '',
                'revealed_value'  => '',
                'image_url'       => '',
                'category'        => '',
                'difficulty'      => 'NORMAL',
            ],
        ]);
    }


    /*
     * AJAX autosave одной карточки.
     */
    public function postSaveCard()
    {
        if (! $this->request->is('post')) {
            return $this->json([
                'success' => false,
            ], 405);
        }

        $cardId =
            (int) $this->request->getPost('card_id');

        $cardModel = new Card();

        $card = $cardModel->find($cardId);

        if (! $card) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Карточка не найдена.',
            ], 404);
        }

        /*
         * Проверяем, что карточка принадлежит
         * игре текущего пользователя.
         */
        if (! $this->getOwnedGame(
            (int) $card['game_template_id']
        )) {
            return $this->json([
                'success' => false,
            ], 403);
        }


        $title = trim(
            (string) $this->request->getPost('title')
        );

        $description = trim(
            (string) $this->request->getPost(
                'short_description'
            )
        );

        $sortOrder = trim(
            (string) $this->request->getPost(
                'sort_order'
            )
        );

        $revealedValue = trim(
            (string) $this->request->getPost(
                'revealed_value'
            )
        );



        $category = trim(
            (string) $this->request->getPost(
                'category'
            )
        );

        $difficulty = strtoupper(
            trim(
                (string) $this->request->getPost(
                    'difficulty'
                )
            )
        );


        if (
            $sortOrder !== ''
            && ! is_numeric($sortOrder)
        ) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',
                'message' =>
                'sortOrder должен быть числом.',
            ], 422);
        }


        $allowedDifficulty = [
            'EASY',
            'NORMAL',
            'HARD',
            'EXPERT',
        ];

        if (! in_array(
            $difficulty,
            $allowedDifficulty,
            true
        )) {
            $difficulty = 'NORMAL';
        }


        if (! $cardModel->update($cardId, [
            'title'             => $title,
            'short_description' =>
            $description ?: null,

            'sort_order' =>
            $sortOrder !== ''
                ? $sortOrder
                : null,

            'revealed_value' =>
            $revealedValue ?: null,

            'category' =>
            $category ?: null,

            'difficulty' =>
            $difficulty,
        ])) {
            return $this->json([
                'success' => false,
                'type' => 'danger',
                'message' => 'Не удалось сохранить карточку.',
            ], 500);
        }


        return $this->json([
            'success' => true,
        ]);
    }


    /*
     * AJAX delete.
     */
    public function postDeleteCard()
    {
        $cardId =
            (int) $this->request->getPost('card_id');

        $cardModel = new Card();

        $card = $cardModel->find($cardId);

        if (
            ! $card
            || ! $this->getOwnedGame(
                (int) $card['game_template_id']
            )
        ) {
            return $this->json([
                'success' => false,
            ], 404);
        }

        $imageUrl =
            ! empty($card['image_url'])
            ? (string) $card['image_url']
            : null;

        if (! $cardModel->delete($cardId)) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось удалить карточку.',
            ], 500);
        }

        /*
 * Запись уже удалена.
 * Теперь удаляем файл.
 */
        if ($imageUrl) {
            $this->deleteCardImageFile(
                $imageUrl
            );
        }

        return $this->json([
            'success' => true,
        ]);
    }


    /*
     * Игра должна принадлежать
     * текущему Creator.
     */
    private function getOwnedGame(int $gameId): ?array
    {
        if (! session()->get('logged_in')) {
            return null;
        }

        $gameModel = new GameTemplate();

        $gameModel->where('id', $gameId);

        if (! $this->isAdmin()) {
            $gameModel->where(
                'user_id',
                (int) session()->get('user_id')
            );
        }

        return $gameModel->first();
    }
    public function postUploadCardImage()
    {
        $cardId = (int) $this->request->getPost('card_id');

        if ($cardId <= 0) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',
                'message' => 'Некорректный ID карточки.',
            ], 422);
        }

        $cardModel = new Card();

        $card = $cardModel->find($cardId);

        if (! $card) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Карточка не найдена.',
            ], 404);
        }

        /*
     * Проверяем доступ через реальную игру карточки.
     *
     * Для обычного пользователя getOwnedGame()
     * проверяет ownership.
     *
     * ADMIN по текущей архитектуре может
     * редактировать любую игру.
     */
        if (! $this->getOwnedGame(
            (int) $card['game_template_id']
        )) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Нет доступа к карточке.',
            ], 403);
        }

        /*
     * Серверная проверка файла.
     *
     * accept="" в HTML — только UI.
     * Этим правилам доверяет сервер.
     */
        $rules = [
            'image' => [
                'label' => 'Изображение',

                'rules' => [
                    'uploaded[image]',
                    'is_image[image]',
                    'mime_in[image,image/jpeg,image/png,image/webp]',
                    'max_size[image,5120]',
                ],

                'errors' => [
                    'uploaded' =>
                    'Выберите изображение.',

                    'is_image' =>
                    'Загруженный файл не является изображением.',

                    'mime_in' =>
                    'Разрешены только JPG, PNG и WebP.',

                    'max_size' =>
                    'Размер изображения не должен превышать 5 MB.',
                ],
            ],
        ];

        if (! $this->validateData([], $rules)) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',

                'message' => implode(
                    ' ',
                    $this->validator->getErrors()
                ),
            ], 422);
        }

        $image = $this->request->getFile('image');

        if (
            ! $image
            || ! $image->isValid()
            || $image->hasMoved()
        ) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось получить изображение.',
            ], 422);
        }

        /*
     * Не доверяем расширению оригинального имени.
     *
     * Расширение выбираем сами после проверки MIME.
     */
        $mimeExtensions = [
            'image/jpeg' => 'jpg',
            'image/png'  => 'png',
            'image/webp' => 'webp',
        ];

        $mimeType = $image->getMimeType();

        if (! isset($mimeExtensions[$mimeType])) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',
                'message' => 'Недопустимый формат изображения.',
            ], 422);
        }

        $extension = $mimeExtensions[$mimeType];

        /*
     * Пока сохраняем существующую структуру проекта:
     *
     * public/uploads/cards/
     *
     * Не переносим сейчас всё в games/{id}/cards,
     * чтобы не ломать уже существующий код.
     */
        $uploadDirectory =
            FCPATH
            . 'uploads'
            . DIRECTORY_SEPARATOR
            . 'cards';

        if (
            ! is_dir($uploadDirectory)
            && ! mkdir($uploadDirectory, 0775, true)
            && ! is_dir($uploadDirectory)
        ) {
            log_message(
                'error',
                'Cannot create card upload directory: {directory}',
                [
                    'directory' => $uploadDirectory,
                ]
            );

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось создать папку изображений.',
            ], 500);
        }

        /*
     * Полностью серверное имя.
     */
        try {
            $newName =
                bin2hex(random_bytes(16))
                . '.'
                . $extension;
        } catch (\Throwable $e) {
            log_message(
                'error',
                'Failed to generate card image filename: {message}',
                [
                    'message' => $e->getMessage(),
                ]
            );

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось подготовить изображение.',
            ], 500);
        }

        try {
            $image->move(
                $uploadDirectory,
                $newName
            );
        } catch (\Throwable $e) {
            log_message(
                'error',
                'Card image move failed: {message}',
                [
                    'message' => $e->getMessage(),
                ]
            );

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось сохранить изображение.',
            ], 500);
        }

        $relativePath =
            'uploads/cards/' . $newName;

        $newFilePath =
            $uploadDirectory
            . DIRECTORY_SEPARATOR
            . $newName;

        /*
     * Запоминаем старое изображение.
     *
     * Удалим его ТОЛЬКО после успешного
     * сохранения нового пути в PostgreSQL.
     */
        $oldImageUrl =
            ! empty($card['image_url'])
            ? (string) $card['image_url']
            : null;

        if (! $cardModel->update(
            $cardId,
            [
                'image_url' => $relativePath,
            ]
        )) {
            /*
         * БД не обновилась —
         * новый файл нам больше не нужен.
         */
            if (is_file($newFilePath)) {
                @unlink($newFilePath);
            }

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось сохранить изображение карточки.',
            ], 500);
        }

        /*
     * Новое изображение уже записано в БД.
     * Теперь безопасно удаляем старое.
     */
        if ($oldImageUrl) {
            $this->deleteCardImageFile(
                $oldImageUrl
            );
        }

        return $this->json([
            'success' => true,

            'type' => 'success',

            'message' =>
            $oldImageUrl
                ? 'Изображение заменено.'
                : 'Изображение загружено.',

            'image_url' =>
            $relativePath,

            'image_src' =>
            '/' . ltrim((string) $relativePath, '/'),
        ]);
    }
    public function postDeleteCardImage()
    {
        $cardId =
            (int) $this->request->getPost('card_id');

        if ($cardId <= 0) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',
                'message' => 'Некорректный ID карточки.',
            ], 422);
        }

        $cardModel = new Card();

        $card = $cardModel->find($cardId);

        if (
            ! $card
            || ! $this->getOwnedGame(
                (int) $card['game_template_id']
            )
        ) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Карточка не найдена.',
            ], 404);
        }

        $oldImageUrl =
            ! empty($card['image_url'])
            ? (string) $card['image_url']
            : null;

        /*
     * Если картинки уже нет —
     * endpoint всё равно считаем успешным.
     */
        if (! $oldImageUrl) {
            return $this->json([
                'success'   => true,
                'type'      => 'success',
                'message'   => 'Изображение уже удалено.',
                'image_url' => '',
                'image_src' => '',
            ]);
        }

        /*
     * Сначала PostgreSQL.
     */
        if (! $cardModel->update(
            $cardId,
            [
                'image_url' => null,
            ]
        )) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось удалить изображение.',
            ], 500);
        }

        /*
     * После успешной БД удаляем файл.
     */
        $this->deleteCardImageFile(
            $oldImageUrl
        );

        return $this->json([
            'success'   => true,
            'type'      => 'success',
            'message'   => 'Изображение удалено.',
            'image_url' => '',
            'image_src' => '',
        ]);
    }
    public function postReorderCards()
    {
        if (! $this->request->is('post')) {
            return $this->json([
                'success' => false,
                'message' => 'Method not allowed',
            ], 405);
        }


        $gameId = (int) $this->request->getPost('game_id');

        $game = $this->getOwnedGame($gameId);


        if (! $game) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Игра не найдена.',
            ], 404);
        }


        /*
     * JS отправляет:
     *
     * [12, 8, 5, 20]
     */
        $orderJson =
            (string) $this->request->getPost('order');


        $order = json_decode(
            $orderJson,
            true
        );


        if (! is_array($order)) {
            return $this->json([
                'success' => false,
                'type'    => 'warning',
                'message' => 'Некорректный порядок карточек.',
            ], 422);
        }


        $order = array_values(
            array_unique(
                array_map(
                    'intval',
                    $order
                )
            )
        );


        $cardModel = new Card();


        /*
     * Получаем ВСЕ карточки игры.
     */
        $cards = $cardModel
            ->select('id')
            ->where(
                'game_template_id',
                $gameId
            )
            ->findAll();


        $realIds = array_map(
            static fn($card) =>
            (int) $card['id'],
            $cards
        );


        /*
     * Нельзя прислать ID карточки
     * из чужой игры.
     */
        if (
            count($realIds) !== count($order)
            || array_diff($realIds, $order)
            || array_diff($order, $realIds)
        ) {
            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Список карточек не совпадает.',
            ], 422);
        }


        /*
     * Изменяем всё транзакционно и проверяем КАЖДЫЙ update().
     * Model::update() может вернуть false ещё до SQL (например validation),
     * поэтому одного transStatus() недостаточно.
     */
        $db = db_connect();
        $db->transBegin();

        try {
            foreach ($order as $position => $cardId) {
                if (! $cardModel->update(
                    $cardId,
                    ['editor_position' => $position]
                )) {
                    throw new \RuntimeException(
                        'Не удалось обновить позицию карточки ' . $cardId
                    );
                }
            }

            if (! $db->transStatus()) {
                throw new \RuntimeException('Ошибка транзакции сортировки.');
            }

            $db->transCommit();
        } catch (\Throwable $e) {
            $db->transRollback();

            log_message('error', 'Card reorder failed: {message}', [
                'message' => $e->getMessage(),
            ]);

            return $this->json([
                'success' => false,
                'type'    => 'danger',
                'message' => 'Не удалось сохранить порядок.',
            ], 500);
        }


        return $this->json([
            'success' => true,
        ]);
    }
    private function deleteCardImageFile(
        ?string $imageUrl
    ): void {
        if (! $imageUrl) {
            return;
        }

        /*
     * Работаем только с файлами,
     * которые принадлежат нашему upload каталогу.
     */
        $normalized =
            str_replace('\\', '/', $imageUrl);

        if (! str_starts_with(
            $normalized,
            'uploads/cards/'
        )) {
            return;
        }

        /*
     * basename не позволит использовать ../
     * для выхода из uploads/cards.
     */
        $fileName =
            basename($normalized);

        if ($fileName === '') {
            return;
        }

        $filePath =
            FCPATH
            . 'uploads'
            . DIRECTORY_SEPARATOR
            . 'cards'
            . DIRECTORY_SEPARATOR
            . $fileName;

        if (is_file($filePath)) {
            @unlink($filePath);
        }
    }
    private function json(
        array $data,
        int $status = 200
    ) {
        $data['csrfName'] = csrf_token();
        $data['csrfHash'] = csrf_hash();

        return $this->response
            ->setStatusCode($status)
            ->setJSON($data);
    }
}
