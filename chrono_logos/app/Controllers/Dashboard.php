<?php

namespace App\Controllers;

use App\Controllers\BaseController;

class Dashboard extends BaseController
{
    public function getIndex()
    {
        $userId = (int) session()->get('user_id');

        return view('dashboard/index', [
            'title'       => 'Главная',
            'userId'      => $userId,
            'username'    => session()->get('username'),
            'gameModules' => $this->getGameModules(),
            'stats'       => $this->getStats($userId),
            'recentGames' => $this->getRecentGames($userId),
            'activity'    => $this->getActivity($userId),
        ]);
    }

    /**
     * Карточки модулей на дашборде — из того же реестра, что и пункты
     * сайдбара (app_modules(), helper menu_helper.php), чтобы список игр
     * не приходилось держать в двух местах синхронно.
     */
    private function getGameModules(): array
    {
        return array_map(
            static fn (array $module): array => [
                'code'        => $module['code'],
                'title'       => $module['title'],
                'description' => $module['description'],
                'url'         => $module['url'],
            ],
            app_modules()
        );
    }

    /**
     * Everything here is scoped to games the user authored, which is what the
     * card labels promise ("Созданных проектов", "Всего участников"). Rooms the
     * user merely joined belong to someone else's statistics.
     */
    private function getStats(int $userId): array
    {
        $db = db_connect();

        $roomsByStatus = $db->query(
            'SELECT r.status, COUNT(*) AS total
               FROM game_rooms r
               JOIN game_templates g ON g.id = r.game_template_id
              WHERE g.user_id = ?
           GROUP BY r.status',
            [$userId]
        )->getResultArray();

        $counts = [];

        foreach ($roomsByStatus as $row) {
            $counts[strtoupper((string) $row['status'])] = (int) $row['total'];
        }

        $players = $db->query(
            'SELECT COUNT(DISTINCT p.user_id) AS total
               FROM game_room_players p
               JOIN game_rooms r ON r.id = p.room_id
               JOIN game_templates g ON g.id = r.game_template_id
              WHERE g.user_id = ?',
            [$userId]
        )->getRowArray();

        return [
            'games' => $db->table('game_templates')
                ->where('user_id', $userId)
                ->countAllResults(),

            'played' => $counts['FINISHED'] ?? 0,

            'players' => (int) ($players['total'] ?? 0),

            'active' => ($counts['WAITING'] ?? 0)
                + ($counts['PLAYING'] ?? 0),
        ];
    }

    private function getRecentGames(int $userId): array
    {
        return db_connect()
            ->table('game_templates g')
            ->select('g.id, g.title, g.status, g.updated_at')
            ->select(
                '(SELECT COUNT(*) FROM cards c
                   WHERE c.game_template_id = g.id) AS cards_count',
                false
            )
            ->select(
                '(SELECT COUNT(*) FROM game_rooms r
                   WHERE r.game_template_id = g.id) AS rooms_count',
                false
            )
            ->where('g.user_id', $userId)
            ->orderBy('g.updated_at', 'DESC')
            ->limit(5)
            ->get()
            ->getResultArray();
    }

    /**
     * Feed of what happened around the user's own games.
     *
     * Built as one UNION so the sort and the limit are applied across all event
     * kinds at once — merging three separately-limited queries in PHP would drop
     * older events of one kind in favour of newer events of another.
     */
    private function getActivity(int $userId): array
    {
        return db_connect()->query(
            "SELECT kind, title, code, actor, happened_at
               FROM (
                    SELECT 'GAME_PUBLISHED' AS kind,
                           g.title          AS title,
                           NULL::varchar    AS code,
                           NULL::varchar    AS actor,
                           g.updated_at     AS happened_at
                      FROM game_templates g
                     WHERE g.user_id = ?
                       AND g.status = 'PRODUCTION'

                     UNION ALL

                    SELECT 'ROOM_CREATED',
                           g.title,
                           r.code,
                           NULL::varchar,
                           r.created_at
                      FROM game_rooms r
                      JOIN game_templates g ON g.id = r.game_template_id
                     WHERE g.user_id = ?

                     UNION ALL

                    SELECT 'ROOM_FINISHED',
                           g.title,
                           r.code,
                           u.username,
                           r.finished_at
                      FROM game_rooms r
                      JOIN game_templates g ON g.id = r.game_template_id
                      LEFT JOIN users u ON u.id = r.winner_user_id
                     WHERE g.user_id = ?

                     UNION ALL

                    SELECT 'PLAYER_JOINED',
                           g.title,
                           r.code,
                           u.username,
                           p.joined_at
                      FROM game_room_players p
                      JOIN game_rooms r ON r.id = p.room_id
                      JOIN game_templates g ON g.id = r.game_template_id
                      JOIN users u ON u.id = p.user_id
                     WHERE g.user_id = ?
                       AND p.user_id <> ?
               ) feed
              WHERE happened_at IS NOT NULL
           ORDER BY happened_at DESC
              LIMIT 8",
            [$userId, $userId, $userId, $userId, $userId]
        )->getResultArray();
    }
}
