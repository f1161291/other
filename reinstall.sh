#!/bin/bash

curl -O https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh || \
wget -O reinstall.sh https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh

echo "请选择系统："
select os in debian13 debian12 debian11 ubuntu24.04 ubuntu22.04 centos9 fnos; do
    [ -n "$os" ] && break
done

bash reinstall.sh "$os"
