FROM php:8.3-apache-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends libonig-dev \
    && docker-php-ext-install -j2 mbstring opcache \
    && rm -rf /var/lib/apt/lists/* \
    && cp "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"
COPY deploy/apache.conf /etc/apache2/conf-available/marathon.conf
COPY deploy/php.ini /usr/local/etc/php/conf.d/marathon.ini
RUN a2enconf marathon
WORKDIR /var/www/html
COPY index.php api.php .htaccess ./
COPY lib/ ./lib/
COPY assets/ ./assets/
COPY tools/bot.php /opt/marathon/bot.php
COPY tools/backup.php /opt/marathon/backup.php
RUN mkdir -p /var/lib/marathon /opt/lib \
    && cp lib/*.php /opt/lib/ \
    && chown www-data:www-data /var/lib/marathon
ENV MARATHON_DATA_DIR=/var/lib/marathon
VOLUME ["/var/lib/marathon"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD php -r 'exit(@file_get_contents("http://127.0.0.1/api.php?action=health") === false ? 1 : 0);'
