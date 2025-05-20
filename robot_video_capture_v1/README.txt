ロボットの撮影とUDP送信・受信のC++プログラム

開発環境
ラズパイ: cm4
OS: bookworm, bullseye
パイカメラ: v2.1 (IMX219)

cppソースコード: sourceフォルダ内
必要ソフト: 
    libcamera
        使用可能なカメラ情報が出力される
            $ libcamera-hello --list-camera
        カメラが撮影可能か確認(プレビュー表示)
            $ libcamera-hello
    ffmpeg
        インストール済みか確認
            $ ffmpeg -version
        なければインストール
            $ sudo apt install ffmpeg


カメラによる撮影のみ: コマンドで実行
    $ libcamera-vid -t [撮影時間(ms)] -n --width 1280 --height 720 --framerate 30 --bitrate 10000000 --codec h264 --inline -o - | ffmpeg -i - -c copy -f mpegts [出力ファイル名].ts

        例: 撮影時間=0(止めるまで)
            $ libcamera-vid -t 0 \
            --width 1280 --height 720 --framerate 30 --bitrate 10000000 --codec h264 --inline -o - |\
            ffmpeg -i - -c copy -f mpegts output.ts

        例: 撮影時間=10000ms(10s)
            $ libcamera-vid -t 10000 --width 1280 --height 720 --framerate 30 --bitrate 10000000 --codec h264 --inline -o - | \
            ffmpeg -i - -c copy -f mpegts output.ts


capture_send.cpp: 撮影・ローカル保存・UDP送信を同時に行う
コンパイル: 下のどちらかで
make使用
    $ make capture_send.cpp
手動
    $ g++ -std=c++17 -O3 capture_send.cpp -o capture_send.out -pthread

実行: 
    $ ./capture_send.out [送信先IP] [撮影時間(s) 0で止めるまで] [ビデオビットレート(kbps)] [映像保存フォルダ名(なしで実行日時)]
        例: 映像保存名なしで500kbpsのビデオビットレート
            $ ./capture_send.out 192.168.20.42 5 500
        例: 映像保存名指定で1Mbpsのビデオビットレート
            $ ./capture_send.out 192.168.20.42 5 1000 ex
備考: 
    libcamera-vidで映像を撮影し，tsファイルの生成・送信を行う
    libcameraコマンドで映像撮影ができるかを確認
        $ libcamera-hello


save_recv.cpp: UDP受信後，映像を.tsとして保存
コンパイル: 下のどちらかで
make使用
    $ make save_recv.cpp
手動
    $ g++ -std=c++17 -O3 save_recv.cpp -o save_recv.out

実行: 
    $ ./save_recv.out [自身のIP] [映像保存名(なしで実行日時)]
        例: 映像保存名なし
            $ ./save_recv.out 192.168.20.42
        例: 映像保存名指定
            $ ./save_recv.out 192.168.20.42 ex 
備考: 
    tsファイルを受信し，保存を行う
