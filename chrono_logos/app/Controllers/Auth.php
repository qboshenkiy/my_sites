<?php

namespace App\Controllers;

use App\Controllers\BaseController;
use App\Models\User;

class Auth extends BaseController
{
    /**
     * Страница входа
     */
    public function getLoginPage()
    {
        if (session()->get('logged_in')) {
            return redirect()->to('/dashboard');
        }

        return view('auth/login');
    }


    /**
     * AJAX: вход
     */
    public function postLoginPage()
    {
        $login = trim(
            (string) $this->request->getPost('login')
        );

        $password = (string) $this->request->getPost('password');


        /*
         * Валидация
         */
        $data = [
            'login'    => $login,
            'password' => $password,
        ];

        $rules = [
            'login' => [
                'label' => 'Логин',
                'rules' => 'required|min_length[3]|max_length[30]',
            ],

            'password' => [
                'label' => 'Пароль',
                'rules' => 'required|min_length[8]|max_length[255]',
            ],
        ];


        if (! $this->validateData($data, $rules)) {

            return $this->response
                ->setStatusCode(422)
                ->setJSON([
                    'success' => false,
                    'type'    => 'warning',
                    'message' => implode(
                        ' ',
                        $this->validator->getErrors()
                    ),

                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Ищем пользователя
         */
        $userModel = new User();

        $user = $userModel
            ->select('users.*, roles.code AS role_code')
            ->join('roles', 'roles.id = users.role_id', 'left')
            ->where('username', $login)
            ->first();


        /*
         * Проверяем пользователя и пароль.
         *
         * Специально даём одно общее сообщение,
         * чтобы не сообщать постороннему,
         * существует ли такой логин.
         */
        if (
            ! $user
            || ! password_verify(
                $password,
                $user['password_hash']
            )
        ) {

            return $this->response
                ->setStatusCode(401)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',
                    'message' => 'Неверный логин или пароль.',

                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Авторизация успешна
         */
        $session = session();

        /*
         * Меняем Session ID после входа
         */
        $session->regenerate(true);


        /*
         * Записываем пользователя в session
         */
        $session->set([
            'user_id'   => $user['id'],
            'username'  => $user['username'],
            'logged_in' => true,
            'role_code' => $user['role_code'] ?? 'USER',
        ]);

        $redirectUrl =
            '/dashboard';

        $pendingRoomCode =
            (string) $session->get(
                'pending_room_code'
            );

        if ($pendingRoomCode !== '') {

            $session->remove(
                'pending_room_code'
            );

            $redirectUrl =
                '/rooms/invite/'
                . rawurlencode(
                    strtoupper($pendingRoomCode)
                );
        }
        return $this->response->setJSON([
            'success' => true,
            'type'    => 'success',

            'message' =>
            'Добро пожаловать, '
                . $user['username']
                . '!',

            'redirect' => $redirectUrl,

            'csrfName' => csrf_token(),
            'csrfHash' => csrf_hash(),
        ]);
    }


    /**
     * Страница регистрации
     */
    public function getRegisterPage()
    {
        if (session()->get('logged_in')) {
            return redirect()->to('/dashboard');
        }

        return view('auth/register');
    }


    /**
     * AJAX: регистрация
     */
    public function postRegisterPage()
    {
        $username = trim(
            (string) $this->request->getPost('username')
        );

        $password = (string) $this->request->getPost('password');


        /*
         * Данные для проверки
         */
        $data = [
            'username' => $username,
            'password' => $password,
        ];


        /*
         * Validation
         */
        $rules = [
            'username' => [
                'label' => 'Логин',

                'rules' =>
                'required'
                    . '|min_length[3]'
                    . '|max_length[30]'
                    . '|is_unique[users.username]',
            ],

            'password' => [
                'label' => 'Пароль',

                'rules' =>
                'required'
                    . '|min_length[8]'
                    . '|max_length[255]',
            ],
        ];


        if (! $this->validateData($data, $rules)) {

            return $this->response
                ->setStatusCode(422)
                ->setJSON([
                    'success' => false,
                    'type'    => 'warning',

                    'message' => implode(
                        ' ',
                        $this->validator->getErrors()
                    ),

                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Создаём пользователя.
         *
         * Блокируем таблицу users на время проверки "первый ли это
         * пользователь", иначе два параллельных запроса на регистрацию
         * могут оба получить роль ADMIN.
         */
        $userModel = new User();
        $db = db_connect();
        $db->transBegin();
        $db->query('LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE');

        $roleCode = ENVIRONMENT !== 'production' && $userModel->countAllResults() === 0
            ? 'ADMIN'
            : 'USER';

        $role = $db->table('roles')
            ->where('code', $roleCode)
            ->get()
            ->getRowArray();

        $userId = $userModel->insert([
            'role_id' => (int) $role['id'],
            'username' => $username,

            /*
             * Пароль в открытом виде
             * НИКОГДА не сохраняем.
             */
            'password_hash' => password_hash(
                $password,
                PASSWORD_DEFAULT
            ),
        ]);


        /*
         * Ошибка добавления
         */
        if ($userId === false || ! $db->transStatus()) {
            $db->transRollback();

            return $this->response
                ->setStatusCode(500)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',

                    'message' =>
                    'Не удалось создать аккаунт.',

                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }

        $db->transCommit();


        /*
         * Сразу авторизуем нового пользователя
         */
        $session = session();

        $session->regenerate(true);

        $session->set([
            'user_id'   => $userId,
            'username'  => $username,
            'logged_in' => true,
            'role_code' => $roleCode,
        ]);

        $redirectUrl =
            '/dashboard';

        $pendingRoomCode =
            (string) $session->get(
                'pending_room_code'
            );

        if ($pendingRoomCode !== '') {

            $session->remove(
                'pending_room_code'
            );

            $redirectUrl =
                '/rooms/invite/'
                . rawurlencode(
                    strtoupper($pendingRoomCode)
                );
        }


        return $this->response
            ->setStatusCode(201)
            ->setJSON([
                'success' => true,
                'type'    => 'success',

                'message' =>
                'Аккаунт успешно создан!',

                'redirect' =>
                $redirectUrl,

                'csrfName' => csrf_token(),
                'csrfHash' => csrf_hash(),
            ]);
    }


    /**
     * Выход
     */
    public function postLogout()
    {
        session()->destroy();

        return redirect()
            ->to('/auth/login-page')
            ->with('type', 'info')
            ->with(
                'message',
                'Вы вышли из аккаунта.'
            );
    }
}
