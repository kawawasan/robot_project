#!/bin/sh
# make.sh
# makeコマンドを最適なスレッド数で実行する
# Usage: ./make.sh [target1] [target2]...
# target: makeのターゲット

# ~/binに配置し，~/bashrc (~/zshrc)に以下を追加すると便利
# export PATH=$HOME/bin:$PATH
# alias make='make.sh'


# ubuntuかラズパイOSかmacか判定
if [ "$(uname)" = "Darwin" ]; then
    # Mac
    echo "Mac OS"
    THREADS=$(($(sysctl -n hw.ncpu) + 1))
elif [ -e /etc/os-release ]; then
    . /etc/os-release
    if [ "$NAME" = "Ubuntu" ]; then
        # ubuntu
        echo "Ubuntu"
        THREADS=$(($(grep -m1 "cpu cores" /proc/cpuinfo | awk '{print $4}') + 1))
    else
        # ラズパイ
        echo "Raspberry Pi"
        THREADS=$(($(nproc) + 1))
    fi
fi

echo "make -j$THREADS $@"
make -j$THREADS $@

