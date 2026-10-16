<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class CreateGameTemplatesTable extends Migration
{
    public function up()
    {
        $this->forge->addField([
            'id' => [
                'type'           => 'INT',
                'auto_increment' => true,
            ],

            'user_id' => [
                'type' => 'INT',
            ],

            'title' => [
                'type'       => 'VARCHAR',
                'constraint' => 150,
                'default'    => 'Новая игра',
            ],

            'description' => [
                'type' => 'TEXT',
                'null' => true,
            ],

            'status' => [
                'type'       => 'VARCHAR',
                'constraint' => 20,
                'default'    => 'DRAFT',
            ],

            'language' => [
                'type'       => 'VARCHAR',
                'constraint' => 10,
                'default'    => 'ru',
            ],

            'autosave_version' => [
                'type'    => 'INT',
                'default' => 1,
            ],

            'created_at' => [
                'type' => 'TIMESTAMP',
                'null' => true,
            ],

            'updated_at' => [
                'type' => 'TIMESTAMP',
                'null' => true,
            ],
        ]);

        $this->forge->addKey('id', true);

        $this->forge->addKey('user_id');

        $this->forge->addForeignKey(
            'user_id',
            'users',
            'id',
            'CASCADE',
            'CASCADE'
        );

        $this->forge->createTable('game_templates');
    }

    public function down()
    {
        $this->forge->dropTable('game_templates');
    }
}