<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class CreateCardsTable extends Migration
{
    public function up()
    {
        $this->forge->addField([
            'id' => [
                'type'           => 'INT',
                'auto_increment' => true,
            ],

            'game_template_id' => [
                'type' => 'INT',
            ],

            'title' => [
                'type'       => 'VARCHAR',
                'constraint' => 255,
                'default'    => '',
            ],

            'short_description' => [
                'type' => 'TEXT',
                'null' => true,
            ],

            'sort_order' => [
                'type'       => 'DECIMAL',
                'constraint' => '30,6',
                'null'       => true,
            ],

            'revealed_value' => [
                'type'       => 'VARCHAR',
                'constraint' => 255,
                'null'       => true,
            ],

            'image_url' => [
                'type' => 'TEXT',
                'null' => true,
            ],

            'category' => [
                'type'       => 'VARCHAR',
                'constraint' => 100,
                'null'       => true,
            ],

            'difficulty' => [
                'type'       => 'VARCHAR',
                'constraint' => 20,
                'default'    => 'NORMAL',
            ],

            'editor_position' => [
                'type'    => 'INT',
                'default' => 0,
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

        $this->forge->addKey('game_template_id');

        $this->forge->addForeignKey(
            'game_template_id',
            'game_templates',
            'id',
            'CASCADE',
            'CASCADE'
        );

        $this->forge->createTable('cards');
    }

    public function down()
    {
        $this->forge->dropTable('cards');
    }
}