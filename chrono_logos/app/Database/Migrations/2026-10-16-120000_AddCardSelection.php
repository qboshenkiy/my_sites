<?php
namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddCardSelection extends Migration
{
    public function up()
    {
        $this->forge->addColumn('cards', ['is_enabled' => ['type' => 'BOOLEAN', 'default' => true]]);
    }

    public function down()
    {
        $this->forge->dropColumn('cards', 'is_enabled');
    }
}
