<?php

namespace App\Models;

use CodeIgniter\Model;

class User extends Model
{
    protected $table = 'users';

    protected $primaryKey = 'id';

    protected $returnType = 'array';

    protected $allowedFields = [
        'role_id',
        'username',
        'email',
        'password_hash',
        'telegram_id',
        'telegram_only',
    ];

    protected $useTimestamps = true;

    protected $createdField = 'created_at';
    protected $updatedField = 'updated_at';
}
