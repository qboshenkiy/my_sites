<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class FinalizeRoomGameplaySchema extends Migration
{
    public function up()
    {
        $this->forge->addColumn(
            'game_room_players',
            [
                'last_seen_at' => [
                    'type' => 'TIMESTAMP',
                    'null' => true,
                ],
            ]
        );

        $this->db->query(
            "UPDATE game_room_players
             SET last_seen_at = COALESCE(joined_at, NOW())
             WHERE last_seen_at IS NULL"
        );

        /* Позволяем отличать явный выход от игрового выбывания. */
        $this->db->query(
            'ALTER TABLE game_room_players '
            . 'DROP CONSTRAINT IF EXISTS game_room_players_status_check'
        );

        $this->db->query(
            "ALTER TABLE game_room_players
             ADD CONSTRAINT game_room_players_status_check
             CHECK (player_status IN ('ACTIVE', 'ELIMINATED', 'LEFT'))"
        );

        /* Финально фиксируем HARDCORE limit на 1–3. */
        $this->db->query(
            "UPDATE game_rooms
             SET mistake_limit = 3
             WHERE mistake_limit IS NOT NULL
               AND mistake_limit > 3"
        );

        $this->db->query(
            "UPDATE game_rooms
             SET mistake_limit = 1
             WHERE mistake_limit IS NOT NULL
               AND mistake_limit < 1"
        );

        $this->db->query(
            'ALTER TABLE game_rooms '
            . 'DROP CONSTRAINT IF EXISTS game_rooms_mistake_limit_check'
        );

        $this->db->query(
            'ALTER TABLE game_rooms '
            . 'ADD CONSTRAINT game_rooms_mistake_limit_check '
            . 'CHECK (mistake_limit IS NULL OR mistake_limit BETWEEN 1 AND 3)'
        );

        $this->db->query(
            'CREATE INDEX IF NOT EXISTS game_room_players_presence_idx '
            . 'ON game_room_players (room_id, player_status, last_seen_at)'
        );
    }

    public function down()
    {
        $this->db->query(
            'DROP INDEX IF EXISTS game_room_players_presence_idx'
        );

        $this->db->query(
            "UPDATE game_room_players
             SET player_status = 'ELIMINATED'
             WHERE player_status = 'LEFT'"
        );

        $this->db->query(
            'ALTER TABLE game_room_players '
            . 'DROP CONSTRAINT IF EXISTS game_room_players_status_check'
        );

        $this->db->query(
            "ALTER TABLE game_room_players
             ADD CONSTRAINT game_room_players_status_check
             CHECK (player_status IN ('ACTIVE', 'ELIMINATED'))"
        );

        $this->db->query(
            'ALTER TABLE game_rooms '
            . 'DROP CONSTRAINT IF EXISTS game_rooms_mistake_limit_check'
        );

        $this->db->query(
            'ALTER TABLE game_rooms '
            . 'ADD CONSTRAINT game_rooms_mistake_limit_check '
            . 'CHECK (mistake_limit IS NULL OR mistake_limit BETWEEN 1 AND 20)'
        );

        $this->forge->dropColumn(
            'game_room_players',
            'last_seen_at'
        );
    }
}
