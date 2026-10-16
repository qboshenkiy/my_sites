<?php

namespace App\Models;

use CodeIgniter\Model;

class Role extends Model
{
    protected $table = 'roles';
    protected $primaryKey = 'id';
    protected $returnType = 'array';
    protected $allowedFields = ['code', 'name'];
    protected $useTimestamps = true;
}
