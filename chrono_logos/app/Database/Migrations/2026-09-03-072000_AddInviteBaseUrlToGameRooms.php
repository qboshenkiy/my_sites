<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddInviteBaseUrlToGameRooms extends Migration
{
    public function up()
    {
        $this->forge->addColumn('game_rooms', [
            'invite_base_url' => [
                'type' => 'VARCHAR',
                'constraint' => 255,
                'null' => true,
                'after' => 'mistake_limit',
            ],
        ]);
    }

    public function down()
    {
        $this->forge->dropColumn(
            'game_rooms',
            'invite_base_url'
        );
    }
}
