FROM php:8.3-apache-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libicu-dev libpq-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev libzip-dev unzip curl \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j2 intl pgsql pdo_pgsql gd zip opcache \
    && a2enmod rewrite headers setenvif \
    && rm -rf /var/lib/apt/lists/*
COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer
WORKDIR /var/www/html
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-scripts --prefer-dist --no-interaction --no-progress --optimize-autoloader
COPY app ./app
COPY public ./public
COPY spark ./spark
COPY ops ./ops
RUN mkdir -p writable/cache writable/logs writable/session writable/uploads writable/debugbar public/uploads \
    && chown -R www-data:www-data writable public/uploads \
    && cp ops/apache.conf /etc/apache2/sites-available/000-default.conf \
    && cp ops/php.ini /usr/local/etc/php/conf.d/production.ini
ENTRYPOINT ["sh", "/var/www/html/ops/entrypoint.sh"]
CMD ["apache2-foreground"]
