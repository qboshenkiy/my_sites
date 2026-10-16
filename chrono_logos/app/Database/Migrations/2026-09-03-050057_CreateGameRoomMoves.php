<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class CreateGameRoomMoves extends Migration
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

            'room_card_id' => [
                'type' => 'INT',
            ],

            'user_id' => [
                'type' => 'INT',
            ],

            'turn_number' => [
                'type' => 'INT',
            ],

            /*
             * Версия, которую прислал клиент.
             */
            'state_version_before' => [
                'type' => 'INT',
            ],

            /*
             * Игрок выбирает промежуток:
             *
             * 0 = перед первой
             * 1 = между 1 и 2
             * ...
             * N = после последней
             */
            'chosen_position' => [
                'type' => 'INT',
            ],

            'is_correct' => [
                'type' => 'BOOLEAN',
            ],

            /*
             * Сколько очков получил
             * пользователь за этот ход.
             */
            'score_delta' => [
                'type'    => 'INT',
                'default' => 0,
            ],

            /*
             * Сохраняем фактическое значение
             * именно на момент хода.
             */
            'revealed_sort_order' => [
                'type'       => 'NUMERIC',
                'constraint' => '20,6',
            ],

            'created_at' => [
                'type' => 'DATETIME',
                'null' => true,
            ],
        ]);

        $this->forge->addKey(
            'id',
            true
        );

        $this->forge->addKey(
            ['room_id', 'turn_number']
        );

        $this->forge->addKey(
            ['room_id', 'user_id']
        );

        $this->forge->addForeignKey(
            'room_id',
            'game_rooms',
            'id',
            'CASCADE',
            'CASCADE'
        );

        $this->forge->addForeignKey(
            'room_card_id',
            'game_room_cards',
            'id',
            'CASCADE',
            'CASCADE'
        );

        $this->forge->addForeignKey(
            'user_id',
            'users',
            'id',
            'RESTRICT',
            'CASCADE'
        );

        $this->forge->createTable(
            'game_room_moves'
        );
    }


    public function down()
    {
        $this->forge->dropTable(
            'game_room_moves',
            true
        );
    }
}