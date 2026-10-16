<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddPenaltyDrawRules extends Migration
{
    public function up()
    {
        /*
         * Неверно поставленная карта больше не выбывает из игры
         * (state = 'DISCARDED'), а встаёт на свою историческую позицию
         * в хронологии с этой пометкой.
         */
        $this->forge->addColumn('game_room_cards', [
            'was_misplaced' => [
                'type' => 'BOOLEAN',
                'null' => false,
                'default' => false,
                'after' => 'state',
            ],
        ]);

        /*
         * Отслеживает, использовал ли игрок свою одну "бесплатную" ошибку
         * при пустой колоде (empty_deck_behavior = GRACE), прежде чем
         * выбыть при повторной ошибке без карт для штрафного добора.
         */
        $this->forge->addColumn('game_room_players', [
            'deck_empty_grace_used' => [
                'type' => 'BOOLEAN',
                'null' => false,
                'default' => false,
                'after' => 'mistakes',
            ],
        ]);

        /*
         * Что делать, если игрок ошибся, а колода уже пуста:
         * GRACE — одна бесплатная попытка, потом выбывание при повторе;
         * SKIP — штраф просто пропускается, без последствий.
         */
        $this->forge->addColumn('game_rooms', [
            'empty_deck_behavior' => [
                'type' => 'VARCHAR',
                'constraint' => 20,
                'null' => false,
                'default' => 'GRACE',
                'after' => 'mistake_limit',
            ],
        ]);

        $this->db->query(
            'ALTER TABLE game_rooms ADD CONSTRAINT '
            . 'game_rooms_empty_deck_behavior_check '
            . "CHECK (empty_deck_behavior IN ('SKIP', 'GRACE'))"
        );
    }

    public function down()
    {
        $this->db->query(
            'ALTER TABLE game_rooms '
            . 'DROP CONSTRAINT IF EXISTS game_rooms_empty_deck_behavior_check'
        );

        $this->forge->dropColumn('game_rooms', 'empty_deck_behavior');
        $this->forge->dropColumn('game_room_players', 'deck_empty_grace_used');
        $this->forge->dropColumn('game_room_cards', 'was_misplaced');
    }
}
