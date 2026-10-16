<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class BootstrapRooms extends Migration
{
    public function up()
    {
        if ($this->db->tableExists('game_rooms')) {
            return;
        }
        require_once __DIR__ . '/2026-09-03-060000_CreateRolesAndRooms.php';
        (new CreateRolesAndRooms($this->forge))->up();
    }

    public function down()
    {
        // Owned by CreateRolesAndRooms, which removes them during rollback.
    }
}
