<?php
namespace App\Libraries;

use DomainException;

final class TelegramApp
{
    public static function validate(string $raw, string $token, ?int $now = null): array
    {
        $deny = static function (): never { throw new DomainException('Не удалось подтвердить Telegram. Откройте игру заново из бота.'); };
        if ($token === '' || $raw === '' || strlen($raw) > 16384) $deny();
        $fields = []; $pairs = explode('&', $raw);
        if (count($pairs) > 32) $deny();
        foreach ($pairs as $pair) {
            if (!str_contains($pair, '=') || preg_match('/%(?![0-9a-fA-F]{2})/', $pair)) $deny();
            [$key, $value] = explode('=', $pair, 2);
            $key = urldecode($key); $value = urldecode($value);
            if (!preg_match('/^[a-z_]+$/D', $key) || array_key_exists($key, $fields)) $deny();
            $fields[$key] = $value;
        }
        $hash = $fields['hash'] ?? ''; unset($fields['hash']);
        if (!preg_match('/^[0-9a-f]{64}$/D', $hash)) $deny();
        ksort($fields, SORT_STRING); $lines = [];
        foreach ($fields as $key => $value) $lines[] = $key . '=' . $value;
        $secret = hash_hmac('sha256', $token, 'WebAppData', true);
        if (!hash_equals(hash_hmac('sha256', implode("\n", $lines), $secret), $hash)) $deny();
        $date = $fields['auth_date'] ?? ''; $now ??= time();
        if (!preg_match('/^\d{1,12}$/D', $date) || (int)$date > $now + 30 || $now - (int)$date > 3600) $deny();
        try { $user = json_decode($fields['user'] ?? '', true, 16, JSON_THROW_ON_ERROR); }
        catch (\JsonException) { $deny(); }
        if (!is_array($user) || !isset($user['id']) || !is_int($user['id']) || $user['id'] < 1 || $user['id'] > 4503599627370495 || !empty($user['is_bot'])) $deny();
        return ['id' => (string)$user['id']];
    }

    public static function url(): ?string
    {
        // A webhook arrives through the main proxy's port 443, not the game's port.
        // Use the configured public URL, never the request's temporary baseURL.
        $base = rtrim((string)env('app_baseURL', env('APP_URL', config('App')->baseURL)), '/'); $parts = parse_url($base);
        if (!$parts || ($parts['scheme'] ?? '') !== 'https' || empty($parts['host']) || isset($parts['user']) || isset($parts['pass']) || isset($parts['query']) || isset($parts['fragment'])) return null;
        return $base . '/telegram/app';
    }

    public static function secret(): string
    {
        return hash_hmac('sha256', 'chrono-logos-webhook', (string)env('TELEGRAM_BOT_TOKEN', ''));
    }

    public static function call(string $method, array $payload): array
    {
        $token = (string)env('TELEGRAM_BOT_TOKEN', '');
        if (!preg_match('/^\d+:[A-Za-z0-9_-]+$/D', $token)) throw new DomainException('Укажите токен отдельного бота Chrono Logos в GitDeck.');
        $curl = curl_init('https://api.telegram.org/bot' . $token . '/' . $method);
        curl_setopt_array($curl, [CURLOPT_POST => true, CURLOPT_POSTFIELDS => json_encode($payload), CURLOPT_HTTPHEADER => ['Content-Type: application/json'], CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => 8, CURLOPT_TIMEOUT => 15]);
        $body = curl_exec($curl); $status = curl_getinfo($curl, CURLINFO_RESPONSE_CODE); curl_close($curl);
        $data = is_string($body) ? json_decode($body, true) : null;
        if ($status !== 200 || !is_array($data) || empty($data['ok'])) throw new DomainException('Telegram не принял настройку. Проверьте токен, HTTPS и доступность api.telegram.org.');
        return $data;
    }
}
