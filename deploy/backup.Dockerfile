# The backup service: PostgreSQL client tools, openssl to encrypt, rclone to copy off the server.
FROM postgres:16-alpine
RUN apk add --no-cache openssl rclone
COPY backup.sh restore.sh /usr/local/bin/
