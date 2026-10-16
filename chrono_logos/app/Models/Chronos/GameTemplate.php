<?php

namespace App\Models\Chronos;

use CodeIgniter\Model;

class GameTemplate extends Model
{
    protected $table = 'game_templates';

    protected $primaryKey = 'id';

    protected $returnType = 'array';

    protected $allowedFields = [
        'user_id',
        'title',
        'description',
        'status',
        'language',
        'autosave_version',
    ];

    protected $useTimestamps = true;

    protected $createdField = 'created_at';
    protected $updatedField = 'updated_at';
}