<?php

namespace Config;

use CodeIgniter\Config\BaseConfig;

class GameNetwork extends BaseConfig
{
    /**
     * Fixed origin for QR invite links.
     *
     * Leave empty in development: Rooms::detectRoomBaseUrl() then builds the
     * link from the validated origin of the current request and falls back to
     * auto-detecting the LAN IP when the room is created from localhost.
     * A hardcoded value here goes stale as soon as DHCP hands out a new IP,
     * which silently breaks every generated QR code.
     *
     * Set it only in production, to pin invites to one known public origin.
     */
    public string $inviteBaseURL = '';

    /**
     * Extra DNS/IP hosts that are allowed in HTTP Host.
     * Ports are not included here.
     * Example: ['game.example.com', 'games.local']
     */
    public array $allowedHosts = [];

    /**
     * true = private/reserved IP hosts (RFC1918: 192.168.*, 10.*, 172.16-31.*)
     * are also trusted, so playing over LAN keeps working when the router
     * reassigns the server IP.
     *
     * Public Host values are still rejected: BaseController::requestOrigin()
     * only accepts a raw IP here after isPrivateOrReservedIp() confirms it is
     * in a private range, so an attacker cannot inject an external origin into
     * QR/invite URLs. Set to false to require an explicit allowedHosts entry.
     */
    public bool $allowPrivateNetworkHosts = true;
}
