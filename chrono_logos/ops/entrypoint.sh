#!/bin/sh
set -eu
cd /var/www/html
mkdir -p writable/cache writable/logs writable/session writable/uploads writable/debugbar public/uploads/cards
chown -R www-data:www-data writable public/uploads
su -s /bin/sh www-data -c 'php spark migrate --all'
su -s /bin/sh www-data -c 'php spark deploy:admin'
exec docker-php-entrypoint "$@"
