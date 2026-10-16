<?php

namespace App\Database\Migrations;

use CodeIgniter\Database\Migration;

class CreateRolesAndRooms extends Migration
{
    public function up()
    {
        // Fresh installations bootstrap these tables before gameplay migrations.
        // Existing installations retain their original migration names/history.
        if ($this->db->tableExists('roles') && $this->db->tableExists('game_rooms')
            && $this->db->tableExists('game_room_players')) {
            return;
        }
        $this->forge->addField([
            'id' => [
                'type' => 'INT',
                'auto_increment' => true,
            ],
            'code' => [
                'type' => 'VARCHAR',
                'constraint' => 30,
            ],
            'name' => [
                'type' => 'VARCHAR',
                'constraint' => 100,
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
        $this->forge->addUniqueKey('code');
        $this->forge->createTable('roles');

        $this->db->table('roles')->insertBatch([
            ['code' => 'USER', 'name' => 'Пользователь'],
            ['code' => 'ADMIN', 'name' => 'Администратор'],
        ]);

        $userRole = $this->db->table('roles')
            ->where('code', 'USER')
            ->get()
            ->getRowArray();

        $this->forge->addColumn('users', [
            'role_id' => [
                'type' => 'INT',
                'null' => true,
                'after' => 'id',
            ],
        ]);

        $this->db->table('users')->update([
            'role_id' => (int) $userRole['id'],
        ]);

        $firstUser = $this->db->table('users')
            ->select('id')
            ->orderBy('id', 'ASC')
            ->get(1)
            ->getRowArray();

        if ($firstUser) {
            $adminRole = $this->db->table('roles')
                ->where('code', 'ADMIN')
                ->get()
                ->getRowArray();

            $this->db->table('users')
                ->where('id', $firstUser['id'])
                ->update(['role_id' => (int) $adminRole['id']]);
        }

        $this->forge->addForeignKey(
            'role_id',
            'roles',
            'id',
            'RESTRICT',
            'CASCADE',
            'users_role_id_foreign'
        );
        $this->forge->processIndexes('users');

        $this->forge->addField([
            'id' => [
                'type' => 'INT',
                'auto_increment' => true,
            ],
            'game_template_id' => ['type' => 'INT'],
            'host_user_id' => ['type' => 'INT'],
            'code' => [
                'type' => 'VARCHAR',
                'constraint' => 8,
            ],
            'status' => [
                'type' => 'VARCHAR',
                'constraint' => 20,
                'default' => 'WAITING',
            ],
            'max_players' => [
                'type' => 'INT',
                'default' => 8,
            ],
            'started_at' => [
                'type' => 'TIMESTAMP',
                'null' => true,
            ],
            'finished_at' => [
                'type' => 'TIMESTAMP',
                'null' => true,
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
        $this->forge->addUniqueKey('code');
        $this->forge->addKey('status');
        $this->forge->addKey('game_template_id');
        $this->forge->addKey('host_user_id');
        $this->forge->addForeignKey('game_template_id', 'game_templates', 'id', 'CASCADE', 'CASCADE');
        $this->forge->addForeignKey('host_user_id', 'users', 'id', 'CASCADE', 'CASCADE');
        $this->forge->createTable('game_rooms');

        $this->forge->addField([
            'id' => [
                'type' => 'INT',
                'auto_increment' => true,
            ],
            'room_id' => ['type' => 'INT'],
            'user_id' => ['type' => 'INT'],
            'score' => [
                'type' => 'INT',
                'default' => 0,
            ],
            'joined_at' => [
                'type' => 'TIMESTAMP',
                'null' => true,
            ],
        ]);
        $this->forge->addKey('id', true);
        $this->forge->addUniqueKey(['room_id', 'user_id']);
        $this->forge->addKey('room_id');
        $this->forge->addKey('user_id');
        $this->forge->addForeignKey('room_id', 'game_rooms', 'id', 'CASCADE', 'CASCADE');
        $this->forge->addForeignKey('user_id', 'users', 'id', 'CASCADE', 'CASCADE');
        $this->forge->createTable('game_room_players');
    }

    public function down()
    {
        $this->forge->dropTable('game_room_players', true);
        $this->forge->dropTable('game_rooms', true);
        $this->forge->dropForeignKey('users', 'users_role_id_foreign');
        $this->forge->dropColumn('users', 'role_id');
        $this->forge->dropTable('roles', true);
    }
}
