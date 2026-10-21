<?php

namespace App\Controllers;

use App\Controllers\BaseController;

class Diagnostics extends BaseController
{
    public function postClientError()
    {
        $input = $this->request->getJSON(true) ?? [];
        $type = in_array(($input['event'] ?? ''), ['visit', 'client_error'], true)
            ? (string) $input['event']
            : 'client_error';
        $message = trim((string) ($input['message'] ?? 'Ошибка браузера'));
        $message = preg_replace('~https?://\S+~i', '[url]', $message);
        $message = preg_replace('/(password|token|secret)\s*[:=]\s*[^\s,;]+/i', '$1=[hidden]', $message);
        $session = session();
        $event = [
            'site' => 'chrono-logos',
            'event' => $type,
            'at' => gmdate(DATE_ATOM),
            'user_id' => $session->get('user_id') ? (string) $session->get('user_id') : null,
            'name' => $session->get('username') ? (string) $session->get('username') : null,
            'page' => parse_url((string) ($input['page'] ?? ''), PHP_URL_PATH) ?: '',
            'source' => basename((string) ($input['source'] ?? '')),
            'line' => max(0, (int) ($input['line'] ?? 0)),
        ];
        if ($type === 'client_error') {
            $event['message'] = mb_substr($message, 0, 400);
        }
        error_log('[site-event] ' . json_encode($event, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE));

        return $this->response->setJSON(['ok' => true]);
    }
}
