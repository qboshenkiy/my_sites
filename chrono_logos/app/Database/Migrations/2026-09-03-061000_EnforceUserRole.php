<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class EnforceUserRole extends Migration
{
    public function up()
    {
        $userRole = $this->db->table('roles')->where('code', 'USER')->get()->getRowArray();
        $roleId = (int) $userRole['id'];

        $this->db->query('ALTER TABLE users ALTER COLUMN role_id SET DEFAULT ' . $roleId);
        $this->db->query('ALTER TABLE users ALTER COLUMN role_id SET NOT NULL');
    }

    public function down()
    {
        $this->db->query('ALTER TABLE users ALTER COLUMN role_id DROP NOT NULL');
        $this->db->query('ALTER TABLE users ALTER COLUMN role_id DROP DEFAULT');
    }
}
