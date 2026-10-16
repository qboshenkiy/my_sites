<?php

namespace App\Commands;

use CodeIgniter\CLI\BaseCommand;
use CodeIgniter\CLI\CLI;
use RuntimeException;

class DeployAdmin extends BaseCommand
{
    protected $group = 'Deployment';
    protected $name = 'deploy:admin';
    protected $description = 'Provision the administrator configured by the deployment panel.';

    public function run(array $params)
    {
        $username = (string) getenv('ADMIN_USERNAME');
        $password = (string) getenv('ADMIN_PASSWORD');
        if (!preg_match('/^[A-Za-z0-9_-]{3,30}$/D', $username) || mb_strlen($password) < 12 || mb_strlen($password) > 255) {
            throw new RuntimeException('Set ADMIN_USERNAME (3-30 characters) and ADMIN_PASSWORD (12-255 characters).');
        }
        $db = db_connect();
        $db->transException(true)->transStart();
        $db->query('LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE');
        $role = $db->table('roles')->where('code', 'ADMIN')->get()->getRowArray();
        if (!$role) {
            throw new RuntimeException('Run database migrations before provisioning the administrator.');
        }
        $user = $db->table('users')->where('username', $username)->get()->getRowArray();
        $values = ['role_id' => (int) $role['id'], 'updated_at' => date('Y-m-d H:i:s')];
        if (!$user || !password_verify($password, $user['password_hash'])) {
            $values['password_hash'] = password_hash($password, PASSWORD_DEFAULT);
        }
        if ($user) {
            $db->table('users')->where('id', $user['id'])->update($values);
        } else {
            $db->table('users')->insert($values + ['username' => $username, 'created_at' => date('Y-m-d H:i:s')]);
        }
        $db->transComplete();
        if (!$db->transStatus()) {
            throw new RuntimeException('Administrator provisioning failed.');
        }
        CLI::write('Deployment administrator is ready.');
    }
}
