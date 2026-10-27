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
    function icon_paths(string $name): ?string {
        static $icons = null;
        if ($icons === null) {
            $icons = json_decode(file_get_contents(__DIR__ . '/../../public/assets/ui-icons.json'), true, 32, JSON_THROW_ON_ERROR);
        }
        $name = ['rooms'=>'play','cards'=>'grid'][$name] ?? $name;
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

        $safeClass = 'ui-icon ' . preg_replace('/[^a-z0-9 _-]/i', '', $class);
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
            . ' stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"'
            . ' style="vertical-align:middle;flex:0 0 auto"'
            . ' aria-hidden="true" focusable="false">'
            . $paths
            . '</svg>';
    }
}
