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
ディレクトリに入り、move_1m.pyを実行
LiDARで後方物体との距離を測距しながら、その距離が1mとなるように進みます。
   python3 move_1m.py

