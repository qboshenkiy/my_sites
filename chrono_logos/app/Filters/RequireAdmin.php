<?php

namespace App\Filters;

use CodeIgniter\Filters\FilterInterface;
use CodeIgniter\HTTP\RequestInterface;
use CodeIgniter\HTTP\ResponseInterface;

/**
 * Admin-only areas.
 *
 * Relies on the role that RequireLogin re-read from the database earlier in
 * the same request, so it must always be registered after it. A missing role
 * means RequireLogin did not run — that is treated as "not an admin" rather
 * than trusted, so a misconfigured route denies access instead of granting it.
 */
class RequireAdmin implements FilterInterface
{
    public function before(
        RequestInterface $request,
        $arguments = null
    ) {
        if (session()->get('role_code') === 'ADMIN') {
            return null;
        }

        $message = 'Доступ разрешён только администратору.';

        if ($request->isAJAX()) {
            return service('response')
                ->setStatusCode(403)
                ->setJSON([
                    'success'  => false,
                    'type'     => 'danger',
                    'message'  => $message,
                    'csrfName' => csrf_token(),
                    'csrfHash' => csrf_hash(),
                ]);
        }

        session()->setFlashdata('type', 'danger');
        session()->setFlashdata('message', $message);

        /* Root-relative Location: см. пояснение в RequireLogin::reject(). */
        return service('response')
            ->setStatusCode(302)
            ->setHeader('Location', '/dashboard');
    }

    public function after(
        RequestInterface $request,
        ResponseInterface $response,
        $arguments = null
    ) {
        return null;
    }
}
