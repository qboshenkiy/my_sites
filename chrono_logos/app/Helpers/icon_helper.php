<?php

/**
 * Inline SVG icons.
 *
 * The UI used to draw its icons with text glyphs (♢ ◈ ◫ ▤ ⋮⋮). Those render
 * differently on every OS depending on the installed fonts, have no glyph at
 * all on some, and forced unrelated things to share a symbol — ◈ was both the
 * brand mark and the "no games" empty state.
 *
 * Inlined rather than loaded from an icon CDN so the app keeps working with no
 * network, which matters for the LAN/offline setup this is played on.
 *
 * All icons are drawn on a 24x24 grid and stroke with currentColor, so they
 * take the colour of the surrounding text.
 */

if (! function_exists('icon_paths')) {
    function icon_paths(string $name): ?string
    {
        $icons = [
            'home' => '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h13V9.5"/><path d="M10 21v-6h4v6"/>',

            'library' => '<rect x="3" y="4" width="18" height="5" rx="1"/>'
                . '<rect x="3" y="11" width="18" height="5" rx="1"/>'
                . '<path d="M5 18.5h14"/>',

            'plus' => '<path d="M12 5v14"/><path d="M5 12h14"/>',

            'rooms' => '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l6 3.5-6 3.5z"/>',

            'grid' => '<rect x="3" y="3" width="7.5" height="7.5" rx="1"/>'
                . '<rect x="13.5" y="3" width="7.5" height="7.5" rx="1"/>'
                . '<rect x="3" y="13.5" width="7.5" height="7.5" rx="1"/>'
                . '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1"/>',

            'history' => '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',

            'shield' => '<path d="M12 3l7.5 3v5.5c0 4.2-3.1 6.9-7.5 9.5-4.4-2.6-7.5-5.3-7.5-9.5V6z"/>',

            'users' => '<circle cx="9" cy="8" r="3.5"/>'
                . '<path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/>'
                . '<path d="M16 5.2a3.5 3.5 0 0 1 0 6.6"/>'
                . '<path d="M18 14.9c1.8.7 3 2.4 3 4.6"/>',

            'settings' => '<path d="M4 7h10"/><path d="M18 7h2"/><circle cx="16" cy="7" r="2"/>'
                . '<path d="M4 17h6"/><path d="M14 17h6"/><circle cx="12" cy="17" r="2"/>',

            'menu' => '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>',

            'image' => '<rect x="3" y="4" width="18" height="16" rx="2"/>'
                . '<circle cx="8.5" cy="9.5" r="1.8"/>'
                . '<path d="M4 17.5l4.5-4.5 4 4 3-2.5 4.5 4"/>',

            'table' => '<rect x="3" y="4" width="18" height="16" rx="2"/>'
                . '<path d="M3 9.5h18"/><path d="M3 15h18"/><path d="M9 9.5V20"/>',

            'board' => '<rect x="3" y="5" width="18" height="14" rx="2"/>'
                . '<rect x="6.5" y="8.5" width="4" height="7" rx="1"/>'
                . '<rect x="13.5" y="8.5" width="4" height="7" rx="1"/>',

            'grip' => '<circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/>'
                . '<circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/>'
                . '<circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/>',

            'close' => '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',

            'logout' => '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/>'
                . '<path d="M10 8l-4 4 4 4"/><path d="M6 12h9"/>',

            'chevron-down' => '<path d="M6 9.5l6 6 6-6"/>',

            'book' => '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
                . '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',

            'alert' => '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5"/><circle cx="12" cy="16.5" r="1"/>',

            'check' => '<path d="M5 12.5l4.5 4.5L19 7.5"/>',

            'info' => '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r="1"/>',
        ];

        return $icons[$name] ?? null;
    }
}

if (! function_exists('icon')) {
    /**
     * A dotted placeholder is drawn for an unknown name so a typo shows up on
     * the page instead of silently rendering nothing.
     */
    function icon(string $name, int $size = 20, string $class = 'icon'): string
    {
        $paths = icon_paths($name)
            ?? '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="3 2"/>';

        $safeClass = preg_replace('/[^a-z0-9 _-]/i', '', $class);
        $size = max(10, min($size, 96));

        /*
         * vertical-align задан инлайном намеренно: иконки живут в семи разных
         * стилях, включая standalone-страницы (play, display, catalog), и без
         * этого каждая давала бы зазор по базовой линии текста. Один инлайн
         * дешевле, чем одно и то же правило в семи файлах.
         */
        return '<svg class="' . $safeClass . '"'
            . ' width="' . $size . '" height="' . $size . '"'
            . ' viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            . ' stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
            . ' style="vertical-align:middle;flex:0 0 auto"'
            . ' aria-hidden="true" focusable="false">'
            . $paths
            . '</svg>';
    }
}
