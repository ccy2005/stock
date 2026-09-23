#!/usr/bin/env bash
# 台股儀表板：nginx + systemd 一鍵安裝。請用 root 在「放有 index.html、update.py、stocks.txt 的目錄」執行：
#   bash install.sh
set -euo pipefail

APP=/opt/stock-updater
WEB=/var/www/stock
SNIPPET=/etc/nginx/snippets/stock.conf

[ "$(id -u)" = 0 ] || { echo "請用 root 執行"; exit 1; }
for f in index.html update.py stocks.txt; do [ -f "$f" ] || { echo "找不到 $f，請在檔案所在的目錄執行"; exit 1; }; done
command -v python3 >/dev/null || { echo "請先安裝 python3"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)' || { echo "python3 需要 3.7 以上"; exit 1; }
command -v nginx >/dev/null || { echo "找不到 nginx"; exit 1; }
command -v systemctl >/dev/null || { echo "這台主機沒有 systemd，請改用 README 的 cron 做法"; exit 1; }

echo "== 1/5 建立專用帳號與目錄（程式不用 root 身分跑）"
id stock >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin stock
mkdir -p "$APP" "$WEB/data"
install -m 644 update.py "$APP/update.py"
[ -f "$APP/stocks.txt" ] || install -m 644 stocks.txt "$APP/stocks.txt"
install -m 644 index.html "$WEB/index.html"
[ -f data/6446.json ] && [ ! -f "$WEB/data/6446.json" ] && install -m 644 data/6446.json "$WEB/data/6446.json"
chown -R stock:stock "$WEB/data"
chmod 755 "$WEB" "$WEB/data"

echo "== 2/5 設定 FinMind token（輸入時不會顯示，也不會留在指令紀錄；直接按 Enter 可略過）"
if [ ! -f "$APP/.env" ]; then
  read -r -s -p "FinMind token: " TOKEN; echo
  printf 'FINMIND_TOKEN=%s\nDATA_DIR=%s\n' "$TOKEN" "$WEB/data" > "$APP/.env"
  unset TOKEN
else
  echo "已有 $APP/.env，保留不動"
fi
chown root:root "$APP/.env"; chmod 600 "$APP/.env"

echo "== 3/5 建立排程（台灣時間週一至週五 18:40、21:50，不受主機時區影響）"
cat > /etc/systemd/system/stock-update.service <<EOF
[Unit]
Description=Update Taiwan stock dashboard data
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=stock
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=/usr/bin/env python3 $APP/update.py
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$WEB/data
EOF
cat > /etc/systemd/system/stock-update.timer <<'EOF'
[Unit]
Description=Daily Taiwan stock data update

[Timer]
OnCalendar=Mon..Fri *-*-* 18:40:00 Asia/Taipei
OnCalendar=Mon..Fri *-*-* 21:50:00 Asia/Taipei
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now stock-update.timer >/dev/null

echo "== 4/5 nginx 設定片段"
AUTH=""
read -r -p "要不要加帳號密碼保護？(y/N) " yn
if [[ "${yn:-n}" =~ ^[Yy]$ ]]; then
  read -r -p "  帳號: " U; read -r -s -p "  密碼: " P; echo
  printf '%s:%s\n' "$U" "$(openssl passwd -apr1 "$P")" > /etc/nginx/.htpasswd-stock
  unset P
  chown root:"$(stat -c %G /etc/nginx/nginx.conf)" /etc/nginx/.htpasswd-stock; chmod 644 /etc/nginx/.htpasswd-stock
  AUTH="$(printf '    auth_basic "stock";\n    auth_basic_user_file /etc/nginx/.htpasswd-stock;')"
fi
mkdir -p /etc/nginx/snippets
cat > "$SNIPPET" <<EOF
# 台股儀表板。請在你網站的 server { } 區塊裡加一行： include snippets/stock.conf;
location = /stock { return 301 /stock/; }
location /stock/ {
    root /var/www;
    index index.html;
$AUTH
}
location /stock/data/ {
    root /var/www;
    add_header Cache-Control "no-store";
$AUTH
}
EOF

echo "== 5/5 先跑一次抓資料"
if systemctl start stock-update.service; then
  journalctl -u stock-update.service -n 8 --no-pager -o cat || true
else
  echo "第一次執行失敗，請看： journalctl -u stock-update.service -n 30 --no-pager"
fi

cat <<EOF

完成。剩下一個手動步驟：
  1. 編輯你網站的 nginx 設定檔，在 server { } 裡加一行：  include snippets/stock.conf;
  2. nginx -t && systemctl reload nginx
  3. 打開 http(s)://你的網域/stock/

常用指令：
  立刻更新          systemctl start stock-update.service
  看執行紀錄        journalctl -u stock-update.service -n 30 --no-pager
  看下次排程        systemctl list-timers stock-update.timer
  加股票            編輯 $APP/stocks.txt（一行一個代號），再執行「立刻更新」
  更新儀表板畫面    把新的 index.html 覆蓋到 $WEB/index.html
EOF
