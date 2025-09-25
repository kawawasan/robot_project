#!/bin/bash

# 引数の数が正しいかチェック
if [ $# -ne 1 ]; then
    # 使い方を表示
    echo "./log.sh [log_file_name]_*N.log"
    exit 1
fi

python3 analyze_packet_loss.py $1_CamN.log $1_CN.log $1_RN1.log $1_RN2.log
