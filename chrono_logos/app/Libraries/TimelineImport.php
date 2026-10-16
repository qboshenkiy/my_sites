<?php
namespace App\Libraries;

use InvalidArgumentException;
use JsonException;

class TimelineImport
{
    public const MAX_BYTES = 2097152;
    public const MAX_CARDS = 1000;

    public static function appendAfter(array $cards, int $last): array
    {
        if ($last > 99999999999999 - count($cards)) {
            throw new InvalidArgumentException('Недостаточно места в числовом порядке. Сохраните исходные значения JSON.');
        }
        usort($cards, static function (array $a, array $b): int {
            $left = (string) $a['sort_order']; $right = (string) $b['sort_order'];
            $negativeLeft = str_starts_with($left, '-'); $negativeRight = str_starts_with($right, '-');
            if ($negativeLeft !== $negativeRight) return $negativeLeft ? -1 : 1;
            $key = static function (string $value): string {
                $parts = explode('.', ltrim($value, '-'));
                return str_pad($parts[0], 14, '0', STR_PAD_LEFT) . str_pad($parts[1] ?? '', 6, '0');
            };
            $comparison = strcmp($key($left), $key($right));
            return $negativeLeft ? -$comparison : $comparison;
        });
        foreach ($cards as &$card) $card['sort_order'] = (string) ++$last;
        return $cards;
    }

    public static function parse(string $json): array
    {
        if (strlen($json) > self::MAX_BYTES) {
            throw new InvalidArgumentException('JSON должен быть не больше 2 МБ.');
        }
        try {
            $data = json_decode(ltrim($json, "\xEF\xBB\xBF"), true, 32, JSON_THROW_ON_ERROR | JSON_BIGINT_AS_STRING);
        } catch (JsonException $e) {
            throw new InvalidArgumentException('Некорректный JSON: ' . $e->getMessage());
        }
        if (!is_array($data) || array_is_list($data)) {
            throw new InvalidArgumentException('Нужен объект с названием title и массивом cards.');
        }
        $title = self::text($data['title'] ?? null, 150, 'Название игры', true);
        $items = $data['cards'] ?? $data['events'] ?? null;
        if (!is_array($items) || !array_is_list($items) || count($items) < 1 || count($items) > self::MAX_CARDS) {
            throw new InvalidArgumentException('В cards должно быть от 1 до 1000 карточек.');
        }
        $cards = [];
        foreach ($items as $i => $item) {
            $label = 'Карточка ' . ($i + 1);
            if (!is_array($item)) {
                throw new InvalidArgumentException($label . ': нужен объект.');
            }
            $order = $item['sort_order'] ?? $item['order'] ?? null;
            if (!(is_string($order) || is_int($order) || is_float($order))
                || !preg_match('/^-?\d{1,14}(?:\.\d{1,6})?$/D', (string) $order)) {
                throw new InvalidArgumentException($label . ': sort_order — число, до 14 цифр перед точкой и 6 после.');
            }
            $difficulty = strtoupper(self::text($item['difficulty'] ?? 'NORMAL', 20, $label . ': сложность'));
            if (!in_array($difficulty, ['EASY', 'NORMAL', 'HARD', 'EXPERT'], true)) {
                throw new InvalidArgumentException($label . ': неизвестная сложность.');
            }
            $enabled = $item['is_enabled'] ?? true;
            if (!is_bool($enabled)) {
                throw new InvalidArgumentException($label . ': is_enabled должен быть true или false.');
            }
            $cards[] = [
                'title' => self::text($item['title'] ?? $item['event'] ?? null, 255, $label . ': название', true),
                'short_description' => self::text($item['short_description'] ?? $item['description'] ?? '', 4000, $label . ': описание'),
                'sort_order' => (string) $order,
                'revealed_value' => self::text($item['revealed_value'] ?? $item['reference'] ?? '', 255, $label . ': ответ'),
                'category' => self::text($item['category'] ?? $data['book'] ?? '', 100, $label . ': раздел'),
                'difficulty' => $difficulty,
                'is_enabled' => $enabled,
            ];
        }
        return ['title' => $title, 'description' => self::text($data['description'] ?? '', 8000, 'Описание игры'), 'cards' => $cards];
    }

    private static function text($value, int $max, string $label, bool $required = false): string
    {
        if (!is_string($value) || str_contains($value, "\0")) {
            throw new InvalidArgumentException($label . ': нужна строка.');
        }
        $value = trim($value);
        if (($required && $value === '') || mb_strlen($value) > $max) {
            throw new InvalidArgumentException($label . ': заполните поле, максимум ' . $max . ' символов.');
        }
        return $value;
    }
}
