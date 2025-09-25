#!/bin/bash

# 引数の数が正しいかチェック
if [ $# -ne 1 ]; then
    # 使い方を表示
    echo "./scp_log_cpp.sh [log_file_name].log"
    exit 1
fi

method=${1:0:3}
video_name=${1:4}
num=${1:4:}
echo $method
echo $video_name
echo $num
scp pinisi1_home:/home/pinisi/nisi/mucvis/programs/cpp_code/CamN/log/$1.log ./CamN.log

scp pinisi2_home:/home/pinisi/nisi/mucvis/programs/cpp_code/RN/log/$1.log ./RN1.log

scp pinisi3_home:/home/pinisi/nisi/mucvis/programs/cpp_code/RN/log/$1.log ./RN2.log

scp pinisi4_home:/home/pinisi/nisi/mucvis/programs/cpp_code/CN/log/$1.log ./CN.log

mkdir logs_cpp/$1
echo "make directory logs_cpp/$1"

# 時間順(T)にソート
cat CamN.log | sort -k 2 -n > logs_cpp/$1/$1_CamN.log
cat RN1.log | sort -k 2 -n > logs_cpp/$1/$1_RN1.log
cat RN2.log | sort -k 2 -n > logs_cpp/$1/$1_RN2.log
cat CN.log | sort -k 2 -n > logs_cpp/$1/$1_CN.log

rm CamN.log RN1.log RN2.log CN.log

echo "make $1_CamN.log $1_RN1.log $1_RN2.log $1_CN.log"
echo " "
echo $1

python3 analyze_packet_loss_cpp.py logs_cpp/$1/$1_CamN.log logs_cpp/$1/$1_CN.log logs_cpp/$1/$1_RN1.log logs_cpp/$1/$1_RN2.log > logs_cpp/$1/$1_analyze.txt

cat logs_cpp/$1/$1_analyze.txt

scp pinisi1_home:/home/pinisi/nisi/mucvis/programs/cpp_code/CamN/videos/$1/$video_name.ts ./logs_cpp/$1/CamN.ts
scp pinisi4_home:/home/pinisi/nisi/mucvis/programs/cpp_code/CN/videos/$1/$video_name.ts ./logs_cpp/$1/CN.ts
