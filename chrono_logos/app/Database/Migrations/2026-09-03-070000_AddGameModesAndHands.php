<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class AddGameModesAndHands extends Migration
{
    public function up()
    {
        $this->forge->addColumn('game_rooms', [
            'game_mode' => [
                'type'       => 'VARCHAR',
                'constraint' => 20,
                'default'    => 'NORMAL',
            ],
            'cards_per_player' => [
                'type'    => 'INT',
                'default' => 5,
            ],
            'mistake_limit' => [
                'type' => 'INT',
                'null' => true,
            ],
        ]);

        $this->forge->addColumn('game_room_players', [
            'mistakes' => [
                'type'    => 'INT',
                'default' => 0,
            ],
            'player_status' => [
                'type'       => 'VARCHAR',
                'constraint' => 20,
                'default'    => 'ACTIVE',
            ],
        ]);

        $this->forge->addColumn('game_room_cards', [
            'owner_user_id' => [
                'type' => 'INT',
                'null' => true,
            ],
        ]);

        // PostgreSQL constraints keep room/game state valid even if data is changed
        // outside the application models.
        $this->db->query(<<<'SQL'
            ALTER TABLE game_rooms
            ADD CONSTRAINT game_rooms_game_mode_check
            CHECK (game_mode IN ('NORMAL', 'BLIND', 'HARDCORE'))
        SQL);

        $this->db->query(<<<'SQL'
            ALTER TABLE game_rooms
            ADD CONSTRAINT game_rooms_cards_per_player_check
            CHECK (cards_per_player BETWEEN 1 AND 20)
        SQL);

        $this->db->query(<<<'SQL'
            ALTER TABLE game_rooms
            ADD CONSTRAINT game_rooms_mistake_limit_check
            CHECK (mistake_limit IS NULL OR mistake_limit BETWEEN 1 AND 20)
        SQL);

        $this->db->query(<<<'SQL'
            ALTER TABLE game_room_players
            ADD CONSTRAINT game_room_players_status_check
            CHECK (player_status IN ('ACTIVE', 'ELIMINATED'))
        SQL);

        $this->db->query(<<<'SQL'
            ALTER TABLE game_room_players
            ADD CONSTRAINT game_room_players_mistakes_check
            CHECK (mistakes >= 0)
        SQL);

        $this->db->query(<<<'SQL'
            ALTER TABLE game_room_cards
            ADD CONSTRAINT game_room_cards_owner_fk
            FOREIGN KEY (owner_user_id)
            REFERENCES users(id)
            ON DELETE SET NULL
        SQL);

        $this->db->query(<<<'SQL'
            CREATE INDEX game_room_cards_owner_state_idx
            ON game_room_cards (room_id, owner_user_id, state)
        SQL);

        $this->db->query(<<<'SQL'
            CREATE INDEX game_room_players_status_turn_idx
            ON game_room_players (room_id, player_status, turn_order)
        SQL);
    }

    public function down()
    {
        $this->db->query('DROP INDEX IF EXISTS game_room_players_status_turn_idx');
        $this->db->query('DROP INDEX IF EXISTS game_room_cards_owner_state_idx');

        $this->db->query(
            'ALTER TABLE game_room_cards DROP CONSTRAINT IF EXISTS game_room_cards_owner_fk'
        );

        $this->db->query(
            'ALTER TABLE game_room_players DROP CONSTRAINT IF EXISTS game_room_players_mistakes_check'
        );
        $this->db->query(
            'ALTER TABLE game_room_players DROP CONSTRAINT IF EXISTS game_room_players_status_check'
        );

        $this->db->query(
            'ALTER TABLE game_rooms DROP CONSTRAINT IF EXISTS game_rooms_mistake_limit_check'
        );
        $this->db->query(
            'ALTER TABLE game_rooms DROP CONSTRAINT IF EXISTS game_rooms_cards_per_player_check'
        );
        $this->db->query(
            'ALTER TABLE game_rooms DROP CONSTRAINT IF EXISTS game_rooms_game_mode_check'
        );

        $this->forge->dropColumn('game_room_cards', 'owner_user_id');
        $this->forge->dropColumn('game_room_players', ['mistakes', 'player_status']);
        $this->forge->dropColumn(
            'game_rooms',
            ['game_mode', 'cards_per_player', 'mistake_limit']
        );
    }
}
