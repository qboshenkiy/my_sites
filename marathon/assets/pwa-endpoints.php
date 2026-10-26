<?php
// Public PWA resources travel with assets, including on existing Docker installations.
$pwaResource = $_GET['pwa'] ?? null;
$pwaFiles = ['manifest' => ['manifest.webmanifest', 'application/manifest+json; charset=utf-8'],
             'worker' => ['service-worker.js', 'text/javascript; charset=utf-8']];
if (is_string($pwaResource) && isset($pwaFiles[$pwaResource])) {
    [$pwaFile, $pwaMime] = $pwaFiles[$pwaResource];
    header('Content-Type: ' . $pwaMime);
    header('Cache-Control: no-cache');
    header('X-Content-Type-Options: nosniff');
    if ($pwaResource === 'worker') header('Service-Worker-Allowed: /');
    readfile(__DIR__ . '/' . $pwaFile);
    exit;
}
