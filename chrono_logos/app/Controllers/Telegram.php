<?php
namespace App\Controllers;

use App\Libraries\TelegramApp;
use App\Models\User;
use DomainException;

class Telegram extends BaseController
{
    public function getApp()
    {
        $this->response->setHeader('Cache-Control', 'no-store');
        return view('telegram/app');
    }

    public function postLogin()
    {
        try {
            $identity = TelegramApp::validate((string)$this->request->getPost('initData'), (string)env('TELEGRAM_BOT_TOKEN', ''));
        } catch (DomainException $error) { return $this->reply(['message' => $error->getMessage()], 401); }
        $db = db_connect();
        // Serialize identity creation/linking without relying on a username supplied by Telegram.
        $db->transBegin();
        $db->query('LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE');
        try {
            $user = $db->table('users u')->select('u.*, r.code AS role_code')->join('roles r', 'r.id=u.role_id')->where('telegram_id', $identity['id'])->get()->getRowArray();
            if (!$user) {
                if ($this->request->getPost('create') !== '1') {
                    $db->transRollback();
                    return $this->reply(['needsRegistration' => true]);
                }
                $role = $db->table('roles')->where('code', 'USER')->get()->getRowArray();
                if (!$role) throw new \RuntimeException('Missing default role');
                $model = new User();
                $name = 'tg_' . $identity['id'];
                if ($model->where('username', $name)->first()) $name = 'tg_' . bin2hex(random_bytes(8));
                $id = $model->insert(['username' => $name, 'password_hash' => password_hash(bin2hex(random_bytes(32)), PASSWORD_DEFAULT), 'role_id' => $role['id'], 'telegram_id' => $identity['id'], 'telegram_only' => true]);
                if (!$id) throw new \RuntimeException('Failed to create identity');
                $user = ['id' => $id, 'username' => $name, 'role_code' => 'USER'];
            }
            if (!$db->transStatus()) throw new \RuntimeException('Failed to save identity');
            $db->transCommit();
        } catch (\Throwable $error) {
            $db->transRollback();
            return $this->reply(['message' => 'Не удалось войти. Повторите попытку.'], 500);
        }
        session()->regenerate(true);
        session()->set(['user_id' => $user['id'], 'username' => $user['username'], 'logged_in' => true, 'role_code' => $user['role_code']]);
        $code = (string)session()->get('pending_room_code');
        session()->remove('pending_room_code');
        return $this->reply(['redirect' => preg_match('/^[A-Z0-9]{4,12}$/D', $code) ? '/rooms/invite/' . $code : '/rooms']);
    }

    public function postLink()
    {
        try { $identity = TelegramApp::validate((string)$this->request->getPost('initData'), (string)env('TELEGRAM_BOT_TOKEN', '')); }
        catch (DomainException $error) { return $this->reply(['message' => $error->getMessage()], 401); }
        $db = db_connect(); $db->transBegin();
        $db->query('LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE');
        $model = new User(); $user = $model->find((int)session()->get('user_id'));
        $other = $model->where('telegram_id', $identity['id'])->first();
        if (!$user || ($other && (int)$other['id'] !== (int)$user['id']) || (!empty($user['telegram_id']) && $user['telegram_id'] !== $identity['id'])) {
            $db->transRollback();
            return $this->reply(['message' => 'Telegram уже привязан. Сначала отвяжите его в прежнем аккаунте.'], 409);
        }
        if (!$model->update($user['id'], ['telegram_id' => $identity['id']]) || !$db->transStatus()) {
            $db->transRollback(); return $this->reply(['message' => 'Не удалось сохранить привязку.'], 500);
        }
        $db->transCommit();
        return $this->reply(['message' => 'Telegram привязан. В следующий раз бот откроет этот аккаунт.']);
    }

    public function postUnlink()
    {
        $model = new User();
        $user = $model->find((int)session()->get('user_id'));
        if (in_array($user['telegram_only'] ?? false, [true, 't', '1', 1], true)) return $this->reply(['message' => 'Сначала задайте пароль в профиле, чтобы не потерять доступ к аккаунту.'], 422);
        if (!$model->update((int)session()->get('user_id'), ['telegram_id' => null])) return $this->reply(['message' => 'Не удалось отвязать Telegram.'], 500);
        return $this->reply(['message' => 'Telegram отвязан.']);
    }

    public function postConfigure()
    {
        if (session()->get('role_code') !== 'ADMIN') return $this->reply(['message' => 'Доступно администратору.'], 403);
        try {
            $url = TelegramApp::url();
            if (!$url) throw new DomainException('Сначала подключите HTTPS и задайте APP_URL в GitDeck.');
            $webhook = (string)env('TELEGRAM_WEBHOOK_URL', '');
            if (!preg_match('~^https://[a-z0-9.-]+(?::443)?/(?:gitdeck-telegram-[a-z0-9-]+|telegram/webhook)$~D', $webhook)) throw new DomainException('Сначала примените HTTPS через общий прокси в GitDeck.');
            $me = TelegramApp::call('getMe', []);
            TelegramApp::call('setChatMenuButton', ['menu_button' => ['type' => 'web_app', 'text' => 'Играть', 'web_app' => ['url' => $url]]]);
            TelegramApp::call('setMyCommands', ['commands' => [['command' => 'start', 'description' => 'Открыть Chrono Logos'], ['command' => 'app', 'description' => 'Играть в хронологию']]]);
            TelegramApp::call('setWebhook', ['url' => $webhook, 'secret_token' => TelegramApp::secret(), 'allowed_updates' => ['message'], 'drop_pending_updates' => false]);
            return $this->reply(['message' => 'Бот @' . ($me['result']['username'] ?? '') . ' подключён. Отправьте ему /start.']);
        } catch (DomainException $error) { return $this->reply(['message' => $error->getMessage()], 422); }
    }

    public function postWebhook()
    {
        if ((string)env('TELEGRAM_BOT_TOKEN', '') === '' || !hash_equals(TelegramApp::secret(), $this->request->getHeaderLine('X-Telegram-Bot-Api-Secret-Token'))) return $this->response->setStatusCode(403)->setJSON(['ok' => false]);
        if (strlen($this->request->getBody()) > 65536) return $this->response->setStatusCode(413)->setJSON(['ok' => false]);
        try { $update = $this->request->getJSON(true); } catch (\Throwable) { $update = null; }
        $message = $update['message'] ?? []; $chat = $message['chat'] ?? [];
        if (($chat['type'] ?? '') !== 'private' || ($chat['id'] ?? null) !== ($message['from']['id'] ?? null) || !preg_match('~^/(start|app|help)(?:\s|@|$)~', (string)($message['text'] ?? ''))) return $this->response->setJSON(['ok' => true]);
        $key = 'chrono_bot_' . (int)($update['update_id'] ?? 0);
        if (cache()->get($key)) return $this->response->setJSON(['ok' => true]);
        try {
            $url = TelegramApp::url();
            if (!$url) throw new DomainException('HTTPS required');
            TelegramApp::call('sendMessage', ['chat_id' => $chat['id'], 'text' => "Chrono Logos\n\nСобирайте события в правильном порядке, создавайте комнаты и играйте с друзьями.\n\nНажмите «Играть» — игра откроется прямо в Telegram.", 'reply_markup' => ['inline_keyboard' => [[['text' => '🎴 Играть', 'web_app' => ['url' => $url]]]]]]);
            cache()->save($key, true, 86400);
            return $this->response->setJSON(['ok' => true]);
        } catch (DomainException) { return $this->response->setStatusCode(503)->setJSON(['ok' => false]); }
    }

    private function reply(array $data, int $status = 200)
    {
        return $this->response->setStatusCode($status)->setHeader('Cache-Control', 'no-store')->setJSON(array_merge(['success' => $status < 400, 'csrfName' => csrf_token(), 'csrfHash' => csrf_hash()], $data));
    }
}
