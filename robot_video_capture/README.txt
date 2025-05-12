ロボットの撮影とUDP送信・受信のC++プログラム

開発環境
ラズパイ: cm4
OS: bookworm
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
    $ libcamera-vid -t [撮影時間(ms)] --width 1280 --height 720 --framerate 30 --codec h264 --inline -o - | ffmpeg -fflags +genpts -i - -c:v copy [出力ファイル名].mp4

        例: 撮影時間=0(止めるまで)
            $ libcamera-vid -t 0 \
            --width 1280 --height 720 --framerate 30 --codec h264 --inline -o - |\
            ffmpeg -fflags +genpts -i - -c:v copy output.mp4

        例: 撮影時間=10000ms(10s)
            $ libcamera-vid -t 10000 --width 1280 --height 720 --framerate 30 --codec h264 --inline -o - | \
            ffmpeg -fflags +genpts -i - -c:v copy output.mp4


capture_send.cpp: 撮影・ローカル保存・UDP送信を同時に行う
コンパイル: 下のどちらかで
make使用
    $ make capture_send.cpp
手動
    $ g++ -std=c++17 -O3 capture_send.cpp -o capture_send.out -pthread

実行: 
    $ ./udp_send.out [送信先IP] [撮影時間(s) 0で止めるまで] [映像保存フォルダ名(なしで実行日時)]
        例: 映像保存名なし
            $ ./udp_send.out 192.168.20.42 5
        例: 映像保存名指定
            $ ./udp_send.out 192.168.20.42 5 ex
備考: 
    libcamera-vidで映像を撮影し，1sごとにtsファイルの生成・送信を行う
    終了時にffmpegを用いてtsからmp4へ変換を行う
    libcameraコマンドで映像撮影ができるかを確認
        $ libcamera-hello


save_recv.cpp: UDP受信後，映像を.tsからmp4へ変換を行う
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
    tsファイルを受信し，終了時にffmpegを用いてtsからmp4へ変換を行う
