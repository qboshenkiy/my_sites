<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddGameplayStateToGameRooms extends Migration
{
    public function up()
    {
        /*
         * Состояние всей партии.
         */
        $this->forge->addColumn(
            'game_rooms',
            [
                'current_player_user_id' => [
                    'type' => 'INT',
                    'null' => true,
                ],

                'current_room_card_id' => [
                    'type' => 'INT',
                    'null' => true,
                ],

                'turn_number' => [
                    'type'    => 'INT',
                    'default' => 0,
                ],

                /*
                 * Используем для защиты от
                 * устаревших клиентских ходов.
                 */
                'state_version' => [
                    'type'    => 'INT',
                    'default' => 0,
                ],

                /*
                 * Заполняем только если
                 * победитель один.
                 *
                 * При ничьей останется NULL,
                 * победителей получим по score.
                 */
                'winner_user_id' => [
                    'type' => 'INT',
                    'null' => true,
                ],
            ]
        );


        /*
         * Стабильный порядок игроков.
         */
        $this->forge->addColumn(
            'game_room_players',
            [
                'turn_order' => [
                    'type' => 'INT',
                    'null' => true,
                ],
            ]
        );


        /*
         * PostgreSQL FK.
         */
        $this->db->query(
            '
            ALTER TABLE game_rooms

            ADD CONSTRAINT
                game_rooms_current_player_fk

            FOREIGN KEY
                (current_player_user_id)

            REFERENCES users(id)

            ON DELETE SET NULL
            '
        );


        $this->db->query(
            '
            ALTER TABLE game_rooms

            ADD CONSTRAINT
                game_rooms_current_card_fk

            FOREIGN KEY
                (current_room_card_id)

            REFERENCES game_room_cards(id)

            ON DELETE SET NULL
            '
        );


        $this->db->query(
            '
            ALTER TABLE game_rooms

            ADD CONSTRAINT
                game_rooms_winner_fk

            FOREIGN KEY
                (winner_user_id)

            REFERENCES users(id)

            ON DELETE SET NULL
            '
        );


        $this->db->query(
            '
            CREATE INDEX
                game_room_players_turn_order_idx

            ON game_room_players
                (room_id, turn_order)
            '
        );
    }


    public function down()
    {
        $this->db->query(
            '
            DROP INDEX IF EXISTS
                game_room_players_turn_order_idx
            '
        );

        $this->db->query(
            '
            ALTER TABLE game_rooms
            DROP CONSTRAINT IF EXISTS
                game_rooms_current_player_fk
            '
        );

        $this->db->query(
            '
            ALTER TABLE game_rooms
            DROP CONSTRAINT IF EXISTS
                game_rooms_current_card_fk
            '
        );

        $this->db->query(
            '
            ALTER TABLE game_rooms
            DROP CONSTRAINT IF EXISTS
                game_rooms_winner_fk
            '
        );


        $this->forge->dropColumn(
            'game_room_players',
            'turn_order'
        );


        $this->forge->dropColumn(
            'game_rooms',
            [
                'current_player_user_id',
                'current_room_card_id',
                'turn_number',
                'state_version',
                'winner_user_id',
            ]
        );
    }
}