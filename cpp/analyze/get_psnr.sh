#!/bin/bash

# 引数の数が正しいかチェック
if [ $# -ne 1 ]; then
    # 使い方を表示
    echo "./log.sh [mode]"
    exit 1
fi

for j in {6..15}
do
    for i in {1..5}
    do
        # PSNRを計算して出力
        # echo "PSNR for logs_cpp/$1_semi_play_"$j"M_$i"
        ffmpeg \
        -i logs_cpp/$1_semi_play_"$j"M_$i/CN.ts \
        -i logs_cpp/$1_semi_play_"$j"M_$i/CamN.ts \
        -filter_complex \
        "[0:v]setpts=N/FRAME_RATE/TB[base]; \
        [1:v]setpts=N/FRAME_RATE/TB[ref]; \
        [base][ref]psnr" \
        -an -f null - 2>&1 \
        | grep 'Parsed_psnr_*' \
        | grep -o 'average:\([0-9.]*\|inf\)' \
        | awk -F: '{print $2}'
    done
done
