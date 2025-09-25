# bin/sh

# 引数チェック
if [ $# -ne 1 ]; then
    echo "You can decide the file name."
    echo "Usage: $0 <file_name>.exe"
    file_name="CN.exe"
else
    file_name=$1.exe
fi

g++ mucvis_cn.cpp bytequeue.cpp log.cpp -Wall -lpthread -o $file_name

# コンパイルしたファイル名を出力
echo "Compile file name is $file_name"
