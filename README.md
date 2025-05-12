# robot_project
## 小型ロボットを動かすためのプログラム

このリポジトリは、Raspberry Piを用いたロボット制御のためのコードをまとめたものです。
今後実装に向けて本格的に追加していきます。

## ディレクトリ構成

- `lidar/` – LiDARセンサーのサンプルコード
- `Motor_Driver_HAT_Code/` – モータドライバHATの制御コード
- `dual-max14870-motor-driver-rpi/` – Pololu製MAX14870ドライバのRaspberry Pi用コード(未使用)

## 使い方

1. このリポジトリをRaspberry Piにクローンします。
2. Motor_Driver_HAT_Code/Motor_Driver_HAT_Code/Raspberry Pi/python
ディレクトリに入る

### サンプルコード
- モータの試運転（デフォルト）
   ```python3 main.py```
- LiDARで1秒おきに測距する
   ```python3 lidar.py```
- LiDARで後方物体との距離を測距しながら、その距離が1mとなるように進む。
   ```python3 move_1m.py```
- カメラロボットのカメラで撮影を行いながら進む
   ```python3 camera_moving.py```
- 撮影・ローカル保存・UDP送信を同時に行う
   ```./udp_send.out [送信先IP] [撮影時間(s) 0で止めるまで] [映像保存フォルダ名(なしで実行日時)]```
- UDP受信後，映像を.tsからmp4へ変換を行う
   ```./save_recv.out [自身のIP] [映像保存名(なしで実行日時)]```
