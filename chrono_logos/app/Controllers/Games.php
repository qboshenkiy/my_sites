<?php

namespace App\Controllers;

use App\Controllers\BaseController;

class Games extends BaseController
{
    public function getIndex()
    {
        $query = trim((string) $this->request->getGet('q'));
        $language = trim((string) $this->request->getGet('language'));

        $builder = db_connect()->table('game_templates g')
            ->select('g.id, g.title, g.description, g.language, g.updated_at, u.username AS author')
            ->select('(SELECT COUNT(*) FROM cards c WHERE c.game_template_id = g.id) AS cards_count', false)
            ->select('(SELECT c.image_url FROM cards c WHERE c.game_template_id = g.id AND c.image_url IS NOT NULL ORDER BY c.editor_position ASC, c.id ASC LIMIT 1) AS preview_url', false)
            ->join('users u', 'u.id = g.user_id')
            ->where('g.status', 'PRODUCTION');

        if ($query !== '') {
            $builder->groupStart()
                ->like('g.title', $query, 'both', true, true)
                ->orLike('g.description', $query, 'both', true, true)
                ->groupEnd();
        }

        if ($language !== '') {
            $builder->where('g.language', $language);
        }

        $games = $builder->orderBy('g.updated_at', 'DESC')->get()->getResultArray();
        $languages = db_connect()->table('game_templates')
            ->select('language')
            ->where('status', 'PRODUCTION')
            ->distinct()
            ->orderBy('language')
            ->get()
            ->getResultArray();

        return view('Chronos/games/index', [
            'games' => $games,
            'languages' => $languages,
            'filters' => ['q' => $query, 'language' => $language],
        ]);
    }
}
