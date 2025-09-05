#!/bin/bash
# This is a placeholder for custom pre-build steps.
# You can override this script by passing --build-arg DOCKER_PRE_BUILD=your_script.sh

# Example: Replace apt sources
# cat <<EOF > /etc/apt/sources.list
# deb http://mirrors.aliyun.com/debian trixie main contrib non-free
# deb-src http://mirrors.aliyun.com/debian trixie main contrib non-free

# deb http://mirrors.aliyun.com/debian-security trixie-security main contrib non-free
# deb-src http://mirrors.aliyun.com/debian-security trixie-security main contrib non-free

# deb http://mirrors.aliyun.com/debian trixie-updates main contrib non-free
# deb-src http://mirrors.aliyun.com/debian trixie-updates main contrib non-free

# deb http://mirrors.aliyun.com/debian trixie-backports main contrib non-free
# deb-src http://mirrors.aliyun.com/debian trixie-backports main contrib non-free
# EOF

exit 0
