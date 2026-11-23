FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY web/ /usr/share/nginx/html/
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
