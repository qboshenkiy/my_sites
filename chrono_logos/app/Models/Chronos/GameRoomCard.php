<?php

namespace App\Models\Chronos;

use CodeIgniter\Model;

class GameRoomCard extends Model
{
    protected $table =
        'game_room_cards';

    protected $primaryKey =
        'id';

    protected $returnType =
        'array';

    protected $allowedFields = [
        'room_id',
        'source_card_id',
        'owner_user_id',

        'title',
        'short_description',

        'sort_order',
        'revealed_value',

        'image_url',
        'category',
        'difficulty',

        'deck_position',

        'state',
        'was_misplaced',

        'timeline_position',

        'revealed_at',
    ];

    protected $useTimestamps =
        true;

    protected $createdField =
        'created_at';

    protected $updatedField =
        'updated_at';
}