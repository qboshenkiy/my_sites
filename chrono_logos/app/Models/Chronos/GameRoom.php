<?php

namespace App\Models\Chronos;

use CodeIgniter\Model;

class GameRoom extends Model
{
    protected $table = 'game_rooms';
    protected $primaryKey = 'id';
    protected $returnType = 'array';
    protected $allowedFields = [
        'game_template_id',
        'host_user_id',
        'code',
        'status',
        'max_players',

        'game_mode',
        'cards_per_player',
        'mistake_limit',
        'empty_deck_behavior',
        'invite_base_url',

        'started_at',
        'finished_at',

        'current_player_user_id',
        'current_room_card_id',

        'turn_number',
        'state_version',

        'winner_user_id',
    ];
    protected $useTimestamps = true;
}
