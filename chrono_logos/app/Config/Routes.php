<?php

use CodeIgniter\Router\RouteCollection;

/** @var RouteCollection $routes */
$routes->get('/', '\App\Controllers\Games::getIndex');
$routes->get('games', '\App\Controllers\Games::getIndex');
$routes->get('draw', '\App\Controllers\Draw\Draw::getIndex');
$routes->post('diagnostics/client-error', '\App\Controllers\Diagnostics::postClientError');
