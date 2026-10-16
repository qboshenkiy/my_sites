<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class CreateGameRoomCards extends Migration
{
    public function up()
    {
        $this->forge->addField([
            'id' => [
                'type'           => 'INT',
                'auto_increment' => true,
            ],

            'room_id' => [
                'type' => 'INT',
            ],

            /*
             * ID оригинальной карточки.
             *
             * Для gameplay он не является
             * источником истины — данные ниже
             * являются snapshot.
             */
            'source_card_id' => [
                'type' => 'INT',
                'null' => true,
            ],

            'title' => [
                'type'       => 'VARCHAR',
                'constraint' => 255,
            ],

            'short_description' => [
                'type' => 'TEXT',
                'null' => true,
            ],

            /*
             * СКРЫТОЕ значение.
             * Никогда не отправляем игроку
             * до проверки хода.
             */
            'sort_order' => [
                'type'       => 'NUMERIC',
                'constraint' => '20,6',
            ],

            'revealed_value' => [
                'type'       => 'VARCHAR',
                'constraint' => 255,
                'null'       => true,
            ],

            'image_url' => [
                'type'       => 'VARCHAR',
                'constraint' => 500,
                'null'       => true,
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

            /*
             * Порядок случайно перемешанной
             * колоды этой конкретной партии.
             */
            'deck_position' => [
                'type' => 'INT',
            ],

            /*
             * DECK
             * CURRENT
             * TIMELINE
             * DISCARDED
             */
            'state' => [
                'type'       => 'VARCHAR',
                'constraint' => 20,
                'default'    => 'DECK',
            ],

            /*
             * Используется только когда
             * карточка находится в timeline.
             */
            'timeline_position' => [
                'type' => 'INT',
                'null' => true,
            ],

            'revealed_at' => [
                'type' => 'DATETIME',
                'null' => true,
            ],

            'created_at' => [
                'type' => 'DATETIME',
                'null' => true,
            ],

            'updated_at' => [
                'type' => 'DATETIME',
                'null' => true,
            ],
        ]);

        $this->forge->addKey(
            'id',
            true
        );

        $this->forge->addKey(
            ['room_id', 'state']
        );

        $this->forge->addKey(
            ['room_id', 'deck_position']
        );

        $this->forge->addUniqueKey(
            ['room_id', 'source_card_id']
        );

        $this->forge->addForeignKey(
            'room_id',
            'game_rooms',
            'id',
            'CASCADE',
            'CASCADE'
        );

        /*
         * Если Creator-карточка когда-нибудь
         * будет удалена, snapshot партии
         * остаётся существовать.
         */
        $this->forge->addForeignKey(
            'source_card_id',
            'cards',
            'id',
            'SET NULL',
            'CASCADE'
        );

        $this->forge->createTable(
            'game_room_cards'
        );
    }


    public function down()
    {
        $this->forge->dropTable(
            'game_room_cards',
            true
        );
    }
}