# robot_project
## 小型ロボットを動かすためのプログラム

このリポジトリは、Raspberry Piを用いたロボット制御のためのコードをまとめたものです。
今後実装に向けて本格的に追加していきます。

## ディレクトリ構成

- `lidar/` – LiDARセンサーのサンプルコード
- `Motor_Driver_HAT_Code/` – モータドライバHATの制御コード（この内部にメインプログラムがあります）
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
- 旧プログラム
   - 撮影・ローカル保存・UDP送信を同時に行う
      ```./udp_send.out [送信先IP] [撮影時間(s) 0で止めるまで] [映像保存フォルダ名(なしで実行日時)]```
   - UDP受信後，映像を.tsからmp4へ変換を行う
      ```./save_recv.out [自身のIP] [映像保存名(なしで実行日時)]```
- ロボット制御、映像伝送プログラム
   - カメラロボット: 後方ロボットからの信号による(camera_robot.py)の起動
      - ```python3 wait_start_robot.py```
   - カメラロボット: モータ起動、映像撮影、撮影データを後方ロボットへ伝送
      - ```camera_robot.py```
   - 後方ロボット: 撮影データ受信 save_recv.cppの起動、カメラロボットからの映像受信、モータ起動
      - ```python3 rear_robot.py```
   
- 映像伝送実験用プログラム（階段での実験）
   - カメラ：
      - ```python3 wait_start_camex.py```
   - 中継：
      - ```python3 rear_ex.py```
   - ctl：
      - ```python3 start_robot_from_ctl.py```

- 映像伝送実験用プログラム（走行実験）
   - CamNカメラロボット：
      - ```python3 wait_start_robot.py```
   - RN2：
      - ```python3 rear_robot.py```
   - RN1：
      - ```python3 relay_node1.py```
   - ctl：
      - ```python3 start_robot_from_ctl.py```