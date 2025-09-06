#!/bin/bash
# Initialize container data directory, copy config and compose files, and save private key

TARGET_DIR=${1}

if [ -z "$TARGET_DIR" ]; then
	echo "Usage: $0 <TARGET_DIR>" >&2
	echo "Example: $0 /opt/data/pydexbot" >&2
	exit 1
fi

echo "Using TARGET_DIR: $TARGET_DIR"

mkdir -p "$TARGET_DIR/config" "$TARGET_DIR/data"
config_file="config/config.yaml"
if [ -f config/.config.yaml ]; then
	config_file="config/.config.yaml"
fi
echo "Using config file: config/.config.yaml"
# backup existing config if exists
if [ -f "$TARGET_DIR/config/config.yaml" ]; then
	cp "$TARGET_DIR/config/config.yaml" "$TARGET_DIR/config/config.yaml.bak.$(date +%Y%m%d%H%M%S)"
fi
cp "$config_file" "$TARGET_DIR/config/"
cp docker-compose.yml "$TARGET_DIR/"

cat <<EOF > "$TARGET_DIR/run.sh"
#!/bin/bash
# Startup pydexbot container

docker compose up -d

EOF
chmod +x "$TARGET_DIR/run.sh"

cat <<EOF

Setup complete!

To run the container, execute:
cd $TARGET_DIR && ./run.sh

You can place your data files in $TARGET_DIR/data and config files in $TARGET_DIR/config.
EOF
