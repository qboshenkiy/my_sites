<?php

namespace App\Filters;

use CodeIgniter\Filters\FilterInterface;
use CodeIgniter\HTTP\IncomingRequest;
use CodeIgniter\HTTP\RequestInterface;
use CodeIgniter\HTTP\ResponseInterface;

/**
 * Marks routes whose UI is built for a large screen (editor, admin tables).
 *
 * Mobile clients are warned, not blocked: the pages still work, they are just
 * cramped, and locking a phone out of them would also lock out an admin whose
 * only device at that moment is a phone.
 *
 * The flag is published as a view variable rather than as flashdata, because
 * alert/alert.php shows a single flash message and would otherwise swallow a
 * real one ("Карточка сохранена") behind this hint.
 */
class DesktopOnly implements FilterInterface
{
    public function before(
        RequestInterface $request,
        $arguments = null
    ) {
        /* getUserAgent() живёт на IncomingRequest, а не на RequestInterface. */
        if (! $request instanceof IncomingRequest) {
            return null;
        }

        if (! $request->getUserAgent()->isMobile()) {
            return null;
        }

        service('renderer')->setVar('desktopHint', true);

        return null;
    }

    public function after(
        RequestInterface $request,
        ResponseInterface $response,
        $arguments = null
    ) {
        return null;
    }
}
