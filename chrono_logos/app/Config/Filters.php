<?php

namespace Config;

use App\Filters\DesktopOnly;
use App\Filters\RequireAdmin;
use App\Filters\RequireLogin;
use CodeIgniter\Config\Filters as BaseFilters;
use CodeIgniter\Filters\Cors;
use CodeIgniter\Filters\CSRF;
use CodeIgniter\Filters\DebugToolbar;
use CodeIgniter\Filters\ForceHTTPS;
use CodeIgniter\Filters\Honeypot;
use CodeIgniter\Filters\InvalidChars;
use CodeIgniter\Filters\PageCache;
use CodeIgniter\Filters\PerformanceMetrics;
use CodeIgniter\Filters\SecureHeaders;

class Filters extends BaseFilters
{
    /**
     * Configures aliases for Filter classes to
     * make reading things nicer and simpler.
     *
     * @var array<string, class-string|list<class-string>>
     *
     * [filter_name => classname]
     * or [filter_name => [classname1, classname2, ...]]
     */
    public array $aliases = [
        'csrf'          => CSRF::class,
        'toolbar'       => DebugToolbar::class,
        'honeypot'      => Honeypot::class,
        'invalidchars'  => InvalidChars::class,
        'secureheaders' => SecureHeaders::class,
        'cors'          => Cors::class,
        'forcehttps'    => ForceHTTPS::class,
        'pagecache'     => PageCache::class,
        'performance'   => PerformanceMetrics::class,
        'auth'          => RequireLogin::class,
        'admin'         => RequireAdmin::class,
        'desktoponly'   => DesktopOnly::class,
    ];

    /**
     * List of special required filters.
     *
     * The filters listed here are special. They are applied before and after
     * other kinds of filters, and always applied even if a route does not exist.
     *
     * Filters set by default provide framework functionality. If removed,
     * those functions will no longer work.
     *
     * @see https://codeigniter.com/user_guide/incoming/filters.html#provided-filters
     *
     * @var array{before: list<string>, after: list<string>}
     */
    public array $required = [
        'before' => [
            'forcehttps', // Force Global Secure Requests
            'pagecache',  // Web Page Caching
        ],
        'after' => [
            'pagecache',   // Web Page Caching
            'performance', // Performance Metrics
            'toolbar',     // Debug Toolbar
        ],
    ];

    /**
     * List of filter aliases that are always
     * applied before and after every request.
     *
     * @var array{
     *     before: array<string, array{except: list<string>|string}>|list<string>,
     *     after: array<string, array{except: list<string>|string}>|list<string>
     * }
     */
    /**
     * 'auth' is global with an explicit public allowlist rather than a list of
     * protected URI patterns, and that direction matters.
     *
     * Auto-routing is enabled (Config\Routing::$autoRoute), so every new
     * `public function` in a controller instantly becomes a reachable URL. With
     * a list of protected patterns, forgetting to extend it leaves the new
     * endpoint wide open. Inverted like this, anything new is closed until it is
     * deliberately added below.
     *
     * The public surface is:
     *   '/'                 game catalog (Games::getIndex, see Config\Routes)
     *   'games*'            the same catalog, plus its filters
     *   'auth*'             login, registration, logout
     *   'rooms/invite/*'    QR entry point — for an already-registered
     *                       visitor this stashes pending_room_code and
     *                       sends them to log in; for anyone else it
     *                       renders the guest name-entry form directly
     *   'rooms/guest-join'  submits that name-entry form — the visitor is
     *                       by definition not logged in yet at this point
     */
    public array $globals = [
        'before' => [
            // 'honeypot',
            'csrf' => ['except' => ['telegram/webhook']],
            // 'invalidchars',
            'auth' => [
                'except' => [
                    '/',
                    'games*',
                    'auth*',
                    'rooms/invite/*',
                    'rooms/guest-join',
                    'telegram/app',
                    'telegram/login',
                    'telegram/webhook',
                    'diagnostics/client-error',
                ],
            ],
        ],
        'after' => [
            // 'honeypot',
            // 'secureheaders',
        ],
    ];

    /**
     * List of filter aliases that works on a
     * particular HTTP method (GET, POST, etc.).
     *
     * Example:
     * 'POST' => ['foo', 'bar']
     *
     * If you use this, you should disable auto-routing because auto-routing
     * permits any HTTP method to access a controller. Accessing the controller
     * with a method you don't expect could bypass the filter.
     *
     * @var array<string, list<string>>
     */
    public array $methods = [];

    /**
     * List of filter aliases that should run on any
     * before or after URI patterns.
     *
     * Example:
     * 'isLoggedIn' => ['before' => ['account/*', 'profiles/*']]
     *
     * @var array<string, array<string, list<string>>>
     */
    public array $filters = [
        /*
         * Runs after the global 'auth', which re-reads the role from the
         * database — so this compares a fresh value, not a stale session one.
         */
        'admin' => [
            'before' => ['admin*'],
        ],

        /* Warns mobile clients on the wide, table-heavy screens. */
        'desktoponly' => [
            'before' => ['creator*', 'admin*'],
        ],
    ];
}
