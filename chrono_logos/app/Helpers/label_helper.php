<?php

/**
 * Single source of truth for "enum value from the database" -> Russian label.
 *
 * Statuses used to be translated ad hoc: some views printed "ЧЕРНОВИК" while
 * the neighbouring one printed raw "PRODUCTION", and the card table used the
 * column name "sortOrder" as a heading. Everything user-facing now goes through
 * here, so a value is either translated everywhere or nowhere.
 *
 * Adding a new enum: add a group below, then use enum_label()/enum_badge().
 * Keys must match the values the database actually stores.
 */

if (! function_exists('enum_labels')) {
    function enum_labels(string $group): array
    {
        $dictionary = [
            /* game_templates.status */
            'game_status' => [
                'DRAFT'      => 'Черновик',
                'PRODUCTION' => 'Опубликовано',
            ],

            /* game_rooms.status */
            'room_status' => [
                'WAITING'  => 'Ожидание',
                'PLAYING'  => 'Игра идёт',
                'FINISHED' => 'Завершена',
            ],

            /* cards.difficulty */
            'difficulty' => [
                'EASY'   => 'Лёгкий',
                'NORMAL' => 'Обычный',
                'HARD'   => 'Сложный',
                'EXPERT' => 'Эксперт',
            ],

            /* game_rooms.game_mode */
            'game_mode' => [
                'NORMAL'   => 'Обычный',
                'BLIND'    => 'Вслепую',
                'HARDCORE' => 'Хардкор',
            ],
        ];

        return $dictionary[$group] ?? [];
    }
}

if (! function_exists('enum_label')) {
    /**
     * Unknown values are returned as-is rather than blanked out: a status that
     * is missing from the dictionary should be visible and reported, not
     * silently rendered as an empty cell.
     */
    function enum_label(string $group, ?string $value): string
    {
        $value = strtoupper(trim((string) $value));

        if ($value === '') {
            return '—';
        }

        return enum_labels($group)[$value] ?? $value;
    }
}

if (! function_exists('enum_badge')) {
    /**
     * Renders the standard status pill. The CSS class keeps the existing
     * status-<value> convention, which already groups tones by meaning:
     * draft/waiting = amber, production/playing = green, finished = grey.
     */
    function enum_badge(string $group, ?string $value): string
    {
        $raw = strtoupper(trim((string) $value));

        /*
         * Reduced to a slug rather than escaped: esc() would turn the space
         * between the two class names into &#x20;. Whitelisting the characters
         * keeps the attribute safe and the markup readable.
         */
        $slug = preg_replace('/[^a-z0-9_-]/', '', strtolower($raw));

        $class = $slug === ''
            ? 'status-badge'
            : 'status-badge status-' . $slug;

        return '<span class="' . $class . '">'
            . esc(enum_label($group, $raw))
            . '</span>';
    }
}
