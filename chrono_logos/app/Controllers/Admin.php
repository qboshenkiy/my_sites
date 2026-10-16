<?php

namespace App\Controllers;

use App\Controllers\BaseController;
use App\Models\Chronos\GameTemplate;

class Admin extends BaseController
{
    public function getGames()
    {
        $q = trim((string) $this->request->getGet('q'));
        $status = strtoupper(trim((string) $this->request->getGet('status')));
        $owner = trim((string) $this->request->getGet('owner'));

        $builder = db_connect()->table('game_templates g')
            ->select('g.*, u.username AS owner_username')
            ->select('(SELECT COUNT(*) FROM cards c WHERE c.game_template_id = g.id) AS cards_count', false)
            ->join('users u', 'u.id = g.user_id');

        if ($q !== '') {
            $builder->groupStart()
                ->like('g.title', $q, 'both', true, true)
                ->orLike('g.description', $q, 'both', true, true)
                ->groupEnd();
        }

        if (in_array($status, ['DRAFT', 'PRODUCTION'], true)) {
            $builder->where('g.status', $status);
        }

        if ($owner !== '') {
            $builder->like('u.username', $owner, 'both', true, true);
        }

        return view('Chronos/admin_games', [
            'title' => 'Управление играми',
            'games' => $builder->orderBy('g.updated_at', 'DESC')->get()->getResultArray(),
            'filters' => compact('q', 'status', 'owner'),
        ]);
    }

    public function postSetGameStatus()
    {
        $gameId = (int) $this->request->getPost('game_id');
        $status = strtoupper(trim((string) $this->request->getPost('status')));

        if (! in_array($status, ['DRAFT', 'PRODUCTION'], true)) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Недопустимый статус игры.');
        }

        $gameModel = new GameTemplate();
        if (! $gameModel->find($gameId)) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Игра не найдена.');
        }

        if ($status === 'PRODUCTION') {
            $cards = db_connect()->table('cards')
                ->select('id, title, sort_order')
                ->where('game_template_id', $gameId)
                ->get()
                ->getResultArray();

            if (count($cards) < 2) {
                return redirect()->back()
                    ->with('type', 'warning')
                    ->with('message', 'Для публикации нужны минимум две игровые карточки.');
            }

            $invalidCards = array_filter(
                $cards,
                static fn(array $card): bool =>
                    trim((string) ($card['title'] ?? '')) === ''
                    || $card['sort_order'] === null
                    || $card['sort_order'] === ''
            );

            if ($invalidCards) {
                return redirect()->back()
                    ->with('type', 'warning')
                    ->with(
                        'message',
                        'Нельзя опубликовать игру: у каждой карточки должны быть заполнены название и sort_order.'
                    );
            }
        }

        if (! $gameModel->update($gameId, ['status' => $status])) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Не удалось изменить статус игры.');
        }

        return redirect()->back()
            ->with('type', 'success')
            ->with('message', $status === 'PRODUCTION' ? 'Игра опубликована.' : 'Игра возвращена в черновики.');
    }

    public function getUsers()
    {
        $q = trim((string) $this->request->getGet('q'));
        $role = strtoupper(trim((string) $this->request->getGet('role')));
        $builder = db_connect()->table('users u')
            ->select('u.id, u.username, u.email, u.created_at, r.code AS role_code, r.name AS role_name')
            ->join('roles r', 'r.id = u.role_id');

        if ($q !== '') {
            $builder->groupStart()
                ->like('u.username', $q, 'both', true, true)
                ->orLike('u.email', $q, 'both', true, true)
                ->groupEnd();
        }

        if (in_array($role, ['USER', 'ADMIN'], true)) {
            $builder->where('r.code', $role);
        }

        return view('Chronos/admin_users', [
            'title' => 'Пользователи',
            'users' => $builder->orderBy('u.id', 'ASC')->get()->getResultArray(),
            'filters' => compact('q', 'role'),
        ]);
    }

    public function postSetUserRole()
    {
        $userId = (int) $this->request->getPost('user_id');
        $roleCode = strtoupper(trim((string) $this->request->getPost('role')));
        if (! in_array($roleCode, ['USER', 'ADMIN'], true)) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Неизвестная роль.');
        }

        $db = db_connect();
        $user = $db->table('users u')
            ->select('u.id, r.code AS role_code')
            ->join('roles r', 'r.id = u.role_id')
            ->where('u.id', $userId)
            ->get()
            ->getRowArray();
        $role = $db->table('roles')->where('code', $roleCode)->get()->getRowArray();

        if (! $user || ! $role) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Пользователь или роль не найдены.');
        }

        if ($user['role_code'] === 'ADMIN' && $roleCode !== 'ADMIN') {
            $adminCount = $db->table('users u')
                ->join('roles r', 'r.id = u.role_id')
                ->where('r.code', 'ADMIN')
                ->countAllResults();
            if ($adminCount <= 1) {
                return redirect()->back()->with('type', 'warning')->with('message', 'Нельзя снять роль у последнего администратора.');
            }
        }

        if (! $db->table('users')->where('id', $userId)->update(['role_id' => (int) $role['id']])) {
            return redirect()->back()->with('type', 'danger')->with('message', 'Не удалось изменить роль.');
        }

        if ($userId === (int) session()->get('user_id')) {
            session()->set('role_code', $roleCode);
        }

        return redirect()->back()->with('type', 'success')->with('message', 'Роль пользователя обновлена.');
    }

    public function getRooms()
    {
        $q = trim((string) $this->request->getGet('q'));
        $status = strtoupper(trim((string) $this->request->getGet('status')));
        $builder = db_connect()->table('game_rooms r')
            ->select('r.*, g.title AS game_title, u.username AS host_username')
            ->select('(SELECT COUNT(*) FROM game_room_players p WHERE p.room_id = r.id) AS players_count', false)
            ->join('game_templates g', 'g.id = r.game_template_id')
            ->join('users u', 'u.id = r.host_user_id');

        if ($q !== '') {
            $builder->groupStart()
                ->like('r.code', strtoupper($q), 'both', true, true)
                ->orLike('g.title', $q, 'both', true, true)
                ->orLike('u.username', $q, 'both', true, true)
                ->groupEnd();
        }

        if (in_array($status, ['WAITING', 'PLAYING', 'FINISHED'], true)) {
            $builder->where('r.status', $status);
        }

        return view('Chronos/admin_rooms', [
            'title' => 'Все комнаты',
            'rooms' => $builder->orderBy('r.updated_at', 'DESC')->get()->getResultArray(),
            'filters' => compact('q', 'status'),
        ]);
    }
}
