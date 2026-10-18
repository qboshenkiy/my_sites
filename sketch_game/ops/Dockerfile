FROM php:8.3-apache-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libonig-dev libpng-dev libsqlite3-dev libcurl4-openssl-dev \
    && docker-php-ext-install -j2 mbstring gd pdo_sqlite curl opcache \
    && rm -rf /var/lib/apt/lists/* \
    && cp "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"
WORKDIR /var/www/html
COPY index.php api.php ./
COPY lib ./lib
COPY assets ./assets
COPY ops/apache.conf /etc/apache2/conf-available/sketch.conf
COPY ops/backup.php /opt/sketch/backup.php
RUN a2enconf sketch && mkdir -p /var/lib/sketch && chown www-data:www-data /var/lib/sketch
ENV DRAW_DATA_DIR=/var/lib/sketch
VOLUME ["/var/lib/sketch"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD php -r 'exit(@file_get_contents("http://127.0.0.1/api.php?action=health")===false?1:0);'
