<?php
namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddTelegramIdentity extends Migration
{
    public function up()
    {
        $this->forge->addColumn('users', [
            'telegram_id' => ['type' => 'VARCHAR', 'constraint' => 20, 'null' => true],
            'telegram_only' => ['type' => 'BOOLEAN', 'default' => false],
        ]);
        $this->db->query('CREATE UNIQUE INDEX users_telegram_identity ON users (telegram_id) WHERE telegram_id IS NOT NULL');
    }

    public function down()
    {
        $this->db->query('DROP INDEX IF EXISTS users_telegram_identity');
        $this->forge->dropColumn('users', 'telegram_id');
        $this->forge->dropColumn('users', 'telegram_only');
    }
}
