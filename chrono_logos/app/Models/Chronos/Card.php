<?php

namespace App\Models\Chronos;

use CodeIgniter\Model;

class Card extends Model
{
    protected $table = 'cards';

    protected $primaryKey = 'id';

    protected $returnType = 'array';

    protected $allowedFields = [
        'game_template_id',
        'title',
        'short_description',
        'sort_order',
        'revealed_value',
        'image_url',
        'category',
        'difficulty',
        'editor_position',
        'is_enabled',
    ];

    protected $useTimestamps = true;

    protected $createdField = 'created_at';
    protected $updatedField = 'updated_at';
}
