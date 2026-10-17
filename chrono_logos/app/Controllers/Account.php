<?php

namespace App\Controllers;

use App\Controllers\BaseController;
use App\Models\User;

class Account extends BaseController
{
    /**
     * Страница настроек
     */
    public function getSettings()
    {
        $userId = (int) session()->get('user_id');

        $userModel = new User();

        $user = $userModel->find($userId);

        if (! $user) {
            session()->destroy();

            return redirect()
                ->to('/auth/login-page')
                ->with('type', 'danger')
                ->with('message', 'Аккаунт не найден.');
        }

        return view('account/settings', [
            'title' => 'Настройки аккаунта',
            'user'  => $user,
        ]);
    }


    /**
     * AJAX: изменение профиля
     */
    public function postUpdateProfile()
    {
        $userId = (int) session()->get('user_id');

        $username = trim(
            (string) $this->request->getPost('username')
        );

        $email = strtolower(
            trim(
                (string) $this->request->getPost('email')
            )
        );


        /*
         * ID тоже передаём validation,
         * потому что он используется в {id}.
         */
        $data = [
            'id'       => $userId,
            'username' => $username,
            'email'    => $email,
        ];


        /*
         * is_unique:
         *
         * username должен быть уникальным,
         * но текущего пользователя игнорируем.
         */
        $rules = [
            'id' => [
                'rules' => 'required|is_natural_no_zero',
            ],

            'username' => [
                'label' => 'Логин',
                'rules' =>
                    'required'
                    . '|min_length[3]'
                    . '|max_length[30]'
                    . '|is_unique[users.username,id,{id}]',
            ],

            'email' => [
                'label' => 'Email',
                'rules' =>
                    'permit_empty'
                    . '|valid_email'
                    . '|max_length[255]'
                    . '|is_unique[users.email,id,{id}]',
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


        $userModel = new User();

        $user = $userModel->find($userId);

        if (! $user) {
            return $this->response
                ->setStatusCode(404)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',
                    'message' => 'Пользователь не найден.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Пустой email храним как NULL,
         * а не как пустую строку.
         */
        $updateData = [
            'username' => $username,
            'email' => $email !== ''
                ? $email
                : null,
        ];


        if (! $userModel->update($userId, $updateData)) {

            return $this->response
                ->setStatusCode(500)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',
                    'message' => 'Не удалось сохранить настройки.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Username изменился —
         * обновляем его и в сессии.
         */
        session()->set('username', $username);


        return $this->response->setJSON([
            'success' => true,
            'type'    => 'success',
            'message' => 'Настройки профиля сохранены.',

            'username' => $username,
            'email'    => $email,

            'csrfName' => csrf_token(),
            'csrfHash' => csrf_hash(),
        ]);
    }


    /**
     * AJAX: изменение пароля
     */
    public function postChangePassword()
    {
        $userId = (int) session()->get('user_id');
        $passwordAccount = (new User())->find($userId);
        $firstPassword = $passwordAccount && in_array($passwordAccount['telegram_only'] ?? false, [true, 't', '1', 1], true) && !empty($passwordAccount['telegram_id']);

        $currentPassword =
            (string) $this->request->getPost('current_password');

        $newPassword =
            (string) $this->request->getPost('new_password');

        $passwordConfirm =
            (string) $this->request->getPost('password_confirm');


        $data = [
            'current_password' => $currentPassword,
            'new_password'     => $newPassword,
            'password_confirm' => $passwordConfirm,
        ];


        $rules = [
            'current_password' => [
                'label' => 'Текущий пароль',
                'rules' => $firstPassword ? 'permit_empty|max_length[255]' : 'required|max_length[255]',
            ],

            'new_password' => [
                'label' => 'Новый пароль',
                'rules' =>
                    'required|min_length[8]|max_length[255]',
            ],

            'password_confirm' => [
                'label' => 'Повтор нового пароля',
                'rules' =>
                    'required|matches[new_password]',
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


        $userModel = new User();

        $user = $userModel->find($userId);


        if (! $user) {
            return $this->response
                ->setStatusCode(404)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',
                    'message' => 'Пользователь не найден.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Проверяем текущий пароль.
         */
        if (!$firstPassword && ! password_verify(
            $currentPassword,
            $user['password_hash']
        )) {

            return $this->response
                ->setStatusCode(422)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',
                    'message' => 'Текущий пароль указан неверно.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * Новый пароль храним только как hash.
         */
        $passwordHash = password_hash(
            $newPassword,
            PASSWORD_DEFAULT
        );


        if (! $userModel->update($userId, [
            'password_hash' => $passwordHash,
            'telegram_only' => false,
        ])) {

            return $this->response
                ->setStatusCode(500)
                ->setJSON([
                    'success' => false,
                    'type'    => 'danger',
                    'message' => 'Не удалось изменить пароль.',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }


        /*
         * После изменения пароля
         * обновляем ID сессии.
         */
        session()->regenerate(true);


        return $this->response->setJSON([
            'success' => true,
            'type'    => 'success',
            'message' => 'Пароль успешно изменён.',

            'csrfName' => csrf_token(),
            'csrfHash' => csrf_hash(),
        ]);
    }
}
