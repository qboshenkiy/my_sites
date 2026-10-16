<?php

namespace App\Controllers;

use CodeIgniter\Controller;
use CodeIgniter\HTTP\RequestInterface;
use CodeIgniter\HTTP\ResponseInterface;
use Psr\Log\LoggerInterface;

abstract class BaseController extends Controller
{
    public function initController(
        RequestInterface $request,
        ResponseInterface $response,
        LoggerInterface $logger
    ) {
        parent::initController($request, $response, $logger);

        /*
         * LAN/IP support without trusting an arbitrary Host header.
         * Only a validated/allowed current host may replace App::$baseURL.
         */
        $this->applyRequestBaseUrl($request);
    }

    /**
     * Validated origin of the current HTTP request.
     *
     * The raw HTTP_HOST is only accepted when it is:
     * - localhost/loopback;
     * - a private/reserved IP while LAN mode is enabled;
     * - explicitly present in Config\GameNetwork::$allowedHosts;
     * - the host configured in App::$baseURL / App::$allowedHostnames.
     */
    protected function requestOrigin(
        ?RequestInterface $request = null
    ): ?string {
        $request ??= $this->request;

        $rawHost = '';

        if (method_exists($request, 'getServer')) {
            $rawHost = trim((string) $request->getServer('HTTP_HOST'));
        }

        if ($rawHost === '') {
            $rawHost = trim((string) ($_SERVER['HTTP_HOST'] ?? ''));
        }

        if ($rawHost === '') {
            return null;
        }

        if (
            str_contains($rawHost, "\r")
            || str_contains($rawHost, "\n")
            || str_contains($rawHost, '/')
            || str_contains($rawHost, '\\')
            || str_contains($rawHost, '@')
        ) {
            return null;
        }

        $host = $rawHost;
        $port = null;

        if (str_starts_with($rawHost, '[')) {
            if (! preg_match('/^\[([0-9a-f:]+)\](?::([0-9]{1,5}))?$/i', $rawHost, $match)) {
                return null;
            }

            $plainHost = strtolower($match[1]);

            if (! filter_var($plainHost, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
                return null;
            }

            $host = '[' . $plainHost . ']';
            $port = isset($match[2]) ? (int) $match[2] : null;
        } else {
            if (preg_match('/^(.+):([0-9]{1,5})$/', $rawHost, $match)) {
                $host = $match[1];
                $port = (int) $match[2];
            }

            $plainHost = strtolower(trim($host));

            $validIp = filter_var($plainHost, FILTER_VALIDATE_IP) !== false;
            $validDns = preg_match(
                '/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$/i',
                $plainHost
            ) === 1;

            if (! $validIp && ! $validDns) {
                return null;
            }

            $host = $plainHost;
        }

        if ($port !== null && ($port < 1 || $port > 65535)) {
            return null;
        }

        if (! $this->isAllowedRequestHost($plainHost)) {
            return null;
        }

        $scheme = $request->isSecure() ? 'https' : 'http';
        $origin = $scheme . '://' . $host;

        if ($port !== null) {
            $isDefault =
                ($scheme === 'http' && $port === 80)
                || ($scheme === 'https' && $port === 443);

            if (! $isDefault) {
                $origin .= ':' . $port;
            }
        }

        return $origin;
    }

    private function isAllowedRequestHost(string $host): bool
    {
        $host = strtolower(trim($host, '[]'));

        if ($host === '') {
            return false;
        }

        if (in_array($host, ['localhost', '127.0.0.1', '::1', '0.0.0.0'], true)) {
            return true;
        }

        /** @var \Config\GameNetwork $network */
        $network = config('GameNetwork');

        if (
            filter_var($host, FILTER_VALIDATE_IP) !== false
            && $network->allowPrivateNetworkHosts
            && $this->isPrivateOrReservedIp($host)
        ) {
            return true;
        }

        $allowed = array_map(
            static fn($value): string => strtolower(trim((string) $value, " []\t\n\r\0\x0B")),
            $network->allowedHosts
        );

        /** @var \Config\App $app */
        $app = config('App');
        $configuredHost = parse_url((string) $app->baseURL, PHP_URL_HOST);

        if (is_string($configuredHost) && $configuredHost !== '') {
            $allowed[] = strtolower(trim($configuredHost, '[]'));
        }

        if (property_exists($app, 'allowedHostnames') && is_array($app->allowedHostnames)) {
            foreach ($app->allowedHostnames as $allowedHost) {
                $allowed[] = strtolower(trim((string) $allowedHost, '[]'));
            }
        }

        return in_array($host, array_values(array_unique($allowed)), true);
    }

    private function isPrivateOrReservedIp(string $host): bool
    {
        if (! filter_var($host, FILTER_VALIDATE_IP)) {
            return false;
        }

        return filter_var(
            $host,
            FILTER_VALIDATE_IP,
            FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE
        ) === false;
    }

    private function configuredBaseOrigin(): ?string
    {
        /** @var \Config\App $app */
        $app = config('App');
        $baseUrl = trim((string) $app->baseURL);

        if ($baseUrl === '') {
            return null;
        }

        $parts = parse_url($baseUrl);

        if (
            ! is_array($parts)
            || ! isset($parts['scheme'], $parts['host'])
            || ! in_array(strtolower((string) $parts['scheme']), ['http', 'https'], true)
        ) {
            return null;
        }

        $origin = strtolower((string) $parts['scheme'])
            . '://'
            . (string) $parts['host'];

        if (isset($parts['port'])) {
            $origin .= ':' . (int) $parts['port'];
        }

        return rtrim($origin, '/');
    }

    private function applyRequestBaseUrl(
        RequestInterface $request
    ): void {
        $origin = $this->requestOrigin($request);

        if ($origin === null) {
            return;
        }

        /** @var \Config\App $app */
        $app = config('App');
        $app->baseURL = rtrim($origin, '/') . '/';
    }

    protected function sameOriginUrl(string $path = '/'): string
    {
        $origin = $this->requestOrigin()
            ?? $this->configuredBaseOrigin();

        if ($origin === null) {
            return '/' . ltrim($path, '/');
        }

        return rtrim($origin, '/')
            . '/'
            . ltrim($path, '/');
    }

    protected function isAdmin(): bool
    {
        return session()->get('role_code') === 'ADMIN';
    }
}
