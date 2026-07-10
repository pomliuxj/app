#!/bin/bash
echo "========================================"
echo " API Automation Test Platform          "
echo "========================================"

# ---- MySQL (MariaDB) ----
echo "[entry] MySQL..."
DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASSWORD:-root123}"
if [ ! -d /var/lib/mysql/mysql ]; then
    mysql_install_db --user=root --datadir=/var/lib/mysql 2>/dev/null || \
    mariadb-install-db --user=root --datadir=/var/lib/mysql 2>/dev/null || true
fi
mkdir -p /run/mysqld 2>/dev/null || true
(mysqld --user=root --datadir=/var/lib/mysql --socket=/run/mysqld/mysqld.sock --port=3306 &) 2>/dev/null || \
(mariadbd --user=root --datadir=/var/lib/mysql --socket=/run/mysqld/mysqld.sock --port=3306 &) 2>/dev/null || true

MYSQL_OK=false
for i in $(seq 1 60); do
    if mysqladmin ping -u root --socket=/run/mysqld/mysqld.sock --silent 2>/dev/null; then MYSQL_OK=true; break
    elif mariadb-admin ping -u root --socket=/run/mysqld/mysqld.sock --silent 2>/dev/null; then MYSQL_OK=true; break
    fi; sleep 2
done

if [ "$MYSQL_OK" = true ]; then
    echo "[entry] MySQL OK, 设置密码..."
    mysql -u root --socket=/run/mysqld/mysqld.sock 2>/dev/null \
        -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '${DB_PASS}'; FLUSH PRIVILEGES;" || \
    mariadb -u root --socket=/run/mysqld/mysqld.sock 2>/dev/null \
        -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '${DB_PASS}'; FLUSH PRIVILEGES;" || true
    echo "[entry] 创建数据库..."
    mysql -u "${DB_USER}" -p"${DB_PASS}" --socket=/run/mysqld/mysqld.sock 2>/dev/null \
        -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME:-api}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" || \
    mariadb -u "${DB_USER}" -p"${DB_PASS}" --socket=/run/mysqld/mysqld.sock 2>/dev/null \
        -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME:-api}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" || true
else
    echo "[entry] WARN: MySQL 不可用"
fi

# ---- Redis ----
echo "[entry] Redis..."
redis-server --port 6379 --requirepass "${REDIS_PASSWORD:-123456}" --daemonize yes 2>/dev/null || \
redis-server --port 6379 --requirepass "${REDIS_PASSWORD:-123456}" &
sleep 2
redis-cli -a "${REDIS_PASSWORD:-123456}" ping 2>/dev/null | grep -q PONG && echo "[entry] Redis OK" || echo "[entry] WARN: Redis 不可用"

# ---- Django ----
cd /app
if [ "$MYSQL_OK" = true ]; then
    echo "[entry] Django migrate..."
    for try in $(seq 1 5); do
        if python3 manage.py migrate --noinput 2>/dev/null; then
            echo "[entry] migrate OK (attempt $try)"; break
        fi
        echo "[entry] migrate retry $try/5..."
        sleep 3
    done
fi
python3 manage.py collectstatic --noinput 2>/dev/null || true

# ---- Agent :9000 ----
echo "[entry] Agent :9000..."
cd /app/agent
nohup python server.py --host 0.0.0.0 --port 9000 --log-level warning > /tmp/agent.log 2>&1 &

# ---- Gunicorn :8000 ----
cd /app
echo "[entry] Gunicorn :8000..."
exec gunicorn api_automation_test.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
