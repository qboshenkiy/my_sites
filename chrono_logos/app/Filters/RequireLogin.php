<?php

namespace App\Filters;

use CodeIgniter\Filters\FilterInterface;
use CodeIgniter\HTTP\RequestInterface;
use CodeIgniter\HTTP\ResponseInterface;

/**
 * Gate for every authenticated area of the app.
 *
 * This filter also owns identity resolution: the role is re-read from the
 * database on each request so that demoting an admin takes effect immediately
 * instead of living on in their session. It must therefore run BEFORE
 * RequireAdmin, which only compares the value this filter just wrote.
 */
class RequireLogin implements FilterInterface
{
    public function before(
        RequestInterface $request,
        $arguments = null
    ) {
        $session = session();

        if (! $session->get('logged_in')) {
            return $this->reject($request);
        }

        $userId = (int) $session->get('user_id');

        if ($userId <= 0) {
            $session->destroy();
            return $this->reject($request);
        }

        $user = db_connect()
            ->table('users u')
            ->select('u.id, r.code AS role_code')
            ->join('roles r', 'r.id = u.role_id', 'left')
            ->where('u.id', $userId)
            ->get()
            ->getRowArray();

        /* Аккаунт удалён, пока сессия была жива. */
        if (! $user) {
            $session->destroy();
            return $this->reject($request);
        }

        $roleCode = strtoupper(
            trim((string) ($user['role_code'] ?? 'USER'))
        );

        if (! in_array($roleCode, ['USER', 'ADMIN'], true)) {
            $roleCode = 'USER';
        }

        $session->set('role_code', $roleCode);

        return null;
    }

    public function after(
        RequestInterface $request,
        ResponseInterface $response,
        $arguments = null
    ) {
        return null;
    }

    /**
     * Фильтры выполняются раньше, чем BaseController подставит проверенный
     * origin в App::$baseURL, поэтому redirect()->to() увёл бы клиента на
     * localhost. Отдаём Location относительно корня — браузер разрешит его
     * от текущего origin, и вход по LAN-адресу продолжит работать.
     */
    private function reject(RequestInterface $request)
    {
        $message = 'Сначала войдите в аккаунт.';

        if ($request->isAJAX()) {
            return service('response')
                ->setStatusCode(401)
                ->setJSON([
                    'success'  => false,
                    'type'     => 'danger',
                    'message'  => 'Сессия завершена.',
                    'redirect' => '/auth/login-page',
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }

        session()->setFlashdata('type', 'warning');
        session()->setFlashdata('message', $message);

        return service('response')
            ->setStatusCode(302)
            ->setHeader('Location', '/auth/login-page');
    }
}
