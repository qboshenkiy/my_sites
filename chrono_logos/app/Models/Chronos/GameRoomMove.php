<?php

namespace App\Models\Chronos;

use CodeIgniter\Model;

class GameRoomMove extends Model
{
    protected $table =
        'game_room_moves';

    protected $primaryKey =
        'id';

    protected $returnType =
        'array';

    protected $allowedFields = [
        'room_id',
        'room_card_id',
        'user_id',

        'turn_number',

        'state_version_before',

        'chosen_position',

        'is_correct',

        'score_delta',

        'revealed_sort_order',

        'created_at',
    ];

    protected $useTimestamps =
        false;
}