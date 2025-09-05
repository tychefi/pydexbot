#!/bin/bash
# Initialize container data directory, copy config and compose files, and save private key

TARGET_DIR=${1}
TRADE_PRIVKEY=${2}

if [ -z "$TARGET_DIR" ] || [ -z "$TRADE_PRIVKEY" ]; then
	echo "Usage: $0 <TARGET_DIR> <TRADE_PRIVKEY>" >&2
	echo "Example: $0 /data/pydexbot \${your_trade_privkey}" >&2
	exit 1
fi

echo "Using TARGET_DIR: $TARGET_DIR"

mkdir -p "$TARGET_DIR/config" "$TARGET_DIR/data"
cp config/config.yaml "$TARGET_DIR/config/" 2>/dev/null || echo "config.yaml not found, skipped."
cp docker-compose.yml "$TARGET_DIR/" 2>/dev/null || echo "docker-compose.yml not found, skipped."

# 修改 config.yaml 中的 TRADE_PRIVKEY
if [ -f "$TARGET_DIR/config/config.yaml" ]; then
	sed -i "s/^TRADE_PRIVKEY:.*/trade_privkey: $TRADE_PRIVKEY/" "$TARGET_DIR/config/config.yaml"
	echo "trade_privkey updated in $TARGET_DIR/config/config.yaml"
fi

cat <<EOF > "$TARGET_DIR/run.sh"
#!/bin/bash
# Startup pydexbot container

docker compose up -d

EOF
chmod +x "$TARGET_DIR/run.sh"

cat <<EOF

Setup complete!

To run the container, execute:
cd $TARGET_DIR

docker compose up -d

You can place your data files in $TARGET_DIR/data and config files in $TARGET_DIR/config.
EOF
