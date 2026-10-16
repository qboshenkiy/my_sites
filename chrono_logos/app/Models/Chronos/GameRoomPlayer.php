<?php

namespace App\Models\Chronos;

use CodeIgniter\Model;

class GameRoomPlayer extends Model
{
    protected $table = 'game_room_players';
    protected $primaryKey = 'id';
    protected $returnType = 'array';
    protected $allowedFields = [
        'room_id',
        'user_id',
        'score',
        'mistakes',
        'deck_empty_grace_used',
        'player_status',
        'joined_at',
        'turn_order',
        'last_seen_at',
    ];
    protected $useTimestamps = false;
}
