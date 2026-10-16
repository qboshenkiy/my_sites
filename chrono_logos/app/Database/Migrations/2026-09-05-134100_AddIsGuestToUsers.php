<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddIsGuestToUsers extends Migration
{
    public function up()
    {
        /*
         * Гость, вошедший по QR-приглашению без регистрации — обычная
         * строка users (нужна для FK user_id везде по игре), но временная:
         * чистится ленивой уборкой в Rooms::pruneInactiveRooms(), как
         * только перестаёт быть ACTIVE-игроком хоть в одной незавершённой
         * комнате.
         */
        $this->forge->addColumn('users', [
            'is_guest' => [
                'type' => 'BOOLEAN',
                'null' => false,
                'default' => false,
                'after' => 'password_hash',
            ],
        ]);
    }

    public function down()
    {
        $this->forge->dropColumn('users', 'is_guest');
    }
}
