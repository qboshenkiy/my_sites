<?php
namespace App\Database\Migrations;
use CodeIgniter\Database\Migration;

class AddPlayerCompletionRanks extends Migration
{
    public function up()
    {
        $this->forge->addColumn('game_room_players',[
            'finish_turns'=>['type'=>'INT','null'=>true],
            'finish_rank'=>['type'=>'INT','null'=>true],
            'completed_at'=>['type'=>'TIMESTAMP','null'=>true],
        ]);
        $this->db->query('ALTER TABLE game_room_players DROP CONSTRAINT IF EXISTS game_room_players_status_check');
        $this->db->query("ALTER TABLE game_room_players ADD CONSTRAINT game_room_players_status_check CHECK(player_status IN ('ACTIVE','ELIMINATED','LEFT','COMPLETED'))");
        $this->db->query('CREATE INDEX game_room_players_finish_idx ON game_room_players(room_id,finish_turns,mistakes) WHERE finish_turns IS NOT NULL');
    }
    public function down()
    {
        $this->db->query("UPDATE game_room_players SET player_status='ACTIVE' WHERE player_status='COMPLETED'");
        $this->db->query('ALTER TABLE game_room_players DROP CONSTRAINT IF EXISTS game_room_players_status_check');
        $this->db->query("ALTER TABLE game_room_players ADD CONSTRAINT game_room_players_status_check CHECK(player_status IN ('ACTIVE','ELIMINATED','LEFT'))");
        $this->db->query('DROP INDEX IF EXISTS game_room_players_finish_idx');
        $this->forge->dropColumn('game_room_players',['finish_turns','finish_rank','completed_at']);
    }
}
