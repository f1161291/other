#!/bin/bash

URL="https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh"

# 下载脚本
curl -LO "$URL" || wget -O reinstall.sh "$URL" || {
    echo "下载失败！"
    exit 1
}

echo "请选择要重装的系统："

PS3="请输入序号 [1-7]: "

select os in debian13 debian12 debian11 ubuntu24.04 ubuntu22.04 centos9 fnos; do
    if [ -n "$os" ]; then
        break
    else
        echo "请输入正确的序号！"
    fi
done

echo "正在重装：$os"
bash reinstall.sh "$os"
