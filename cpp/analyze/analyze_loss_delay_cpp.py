# C++版のCamN.logとCN.logを分析 パケロス率とスループットを計算

import sys

def analyze_camn_cn(camn_file_name, cn_file_name):
    # ファイルを読み込む
    start_time = 0
    end_time = 0
    camn_end_time = 0
    cn_end_time = 0
    previous_time = 0

    # cn用
    recv_video_size = 0
    recv_video_num = 0
    send_control_size = 0
    send_control_num = 0
    video_seq = 0
    video_seq_lost = []
    video_delay_list = []  # (seq, time)
    video_delay_max = 0
    video_delay_average = 0
    time_perf_counter_cn= 0
    lost_ack_num = 0
    lost_video_num = 0

    # camn用
    recv_control_size = 0
    recv_control_num = 0
    send_video_size = 0
    send_video_num = 0
    control_delay_list = []  # (seq, time)
    control_delay_max = 0
    control_delay_average = 0
    time_perf_counter_camn = 0
    time_perf_counter_diff = 0  # 時刻同期のための差分

# ファイルを読み込む
    with open(cn_file_name, 'r') as f:
        for line in f:
            line_list = line.split()

            if line_list[0] != "Time=":  # 最初の行らをスキップ
                continue
            else:  # 時刻同期のための基準取得
                time_perf_counter_cn = float(line_list[3])
                print(f"time_perf_counter_cn: {time_perf_counter_cn:.6f}")
                break
        
        for line in f:
            line_list = line.split()

            if line_list[0] != "T=":  # 最初の行らをスキップ
                continue

            # 最初の受信パケットの時間を記録
            if start_time == 0 and line_list[3] == "Recv" and line_list[5] == "VIDEO":
                start_time = float(line_list[1])
                previous_time = start_time
                video_seq_now = int(line_list[9])
                recv_video_size = float(line_list[11])
                recv_video_num += 1
                received_time = float(line_list[13])

                # videoの到着時間を記録
                if video_seq_now != 0:
                    video_seq_lost.append(0)
                video_seq = video_seq_now
                video_delay_list.append((video_seq_now, received_time))
                
                continue

            # 受信したパケットのサイズを計算
            if line_list[3] == "Recv" and line_list[5] == "VIDEO":
                end_time = float(line_list[1])
                received_time = float(line_list[13])
                if end_time - previous_time > 1:
                    print(f"{cn_file_name} 通信中断: {previous_time:.6f} {end_time:.6f}")
                previous_time = end_time
                recv_video_size += float(line_list[11])
                recv_video_num += 1
                # print(f"video_seq: {video_seq}, video_seq_now: {int(line_list[9])}, recv_video_num: {recv_video_num}")
                video_seq_now = int(line_list[9])

                # videoの到着時間を記録
                if video_seq_now > video_seq + 1:
                    for i in range(video_seq_now - video_seq - 1):
                        video_seq_lost.append(video_seq + i + 1)
                video_seq = video_seq_now
                # video_delay_list.append((video_seq_now, end_time))
                video_delay_list.append((video_seq_now, received_time))


            # 送信したパケットのサイズを計算
            if line_list[3] == "Send" and line_list[5] == "CONTROL":
                send_control_size += float(line_list[11])
                send_control_num += 1
                control_delay_list.append((int(line_list[9]), float(line_list[13])))  # (Seq, SystemTime)

            # ACKにより，ロストしたパケット数を計算
            if line_list[3] == "Command_lost" and line_list[5] == "CONTROL":
                pre_ack = int(line_list[5])
                ack = int(line_list[7])
                lost_ack_num += ack - pre_ack - 1

            # Ev= Video_seq_lost より，ロストした映像パケット数を計算
            if line_list[3] == "Video_seq_lost":
                pre_video_seq = int(line_list[5])
                video_seq_now = int(line_list[7])
                lost_video_num += video_seq_now - pre_video_seq - 1


    print(f"{start_time=:.6f} {end_time=:.6f}")
    video_throughput = recv_video_size / (end_time - start_time) * 8 / 10**6  # Mbps

    cn_end_time = end_time
    # print(f"video_loss_seq= {video_seq_lost}")



    # return recv_video_size, recv_video_num, send_control_size, send_control_num, video_throughput, end_time

    start_time = 0
    end_time = 0
    previous_time = 0
    video_delay_index = 0
    control_delay_index = 0
    previous_seq = 0

    # print(f"len(control_delay_list): {len(control_delay_list)}")

    with open(camn_file_name, 'r') as f:
        for line in f:
            # 空行をスキップ
            if len(line) == 1:
                continue
            
            line_list = line.split()

            if line_list[0] != "Time=":
                continue
            else:
                time_perf_counter_camn = float(line_list[3])
                print(f"time_perf_counter_camn: {time_perf_counter_camn:.6f}")
                time_perf_counter_diff = time_perf_counter_camn - time_perf_counter_cn
                print(f"time_perf_counter_diff: {time_perf_counter_diff:.6f}")
                break
        
        for line in f:
            line_list = line.split()

            if line_list[0] != "T=":  # 最初の行らをスキップ
                continue

            # 最初の送信パケットの時間を記録
            if start_time == 0 and line_list[3] == "Send" and line_list[5] == "VIDEO":
                start_time = float(line_list[1])
                previous_time = start_time
                send_video_size = float(line_list[11])
                send_video_num += 1

                # video_delayを計算
                if video_delay_list[video_delay_index][0] == int(line_list[9]):
                    if time_perf_counter_camn > 1e9:
                        video_delay = (video_delay_list[video_delay_index][1] - float(line_list[13])) / 1e9
                    else:
                        video_delay = video_delay_list[video_delay_index][1] - float(line_list[13]) + time_perf_counter_diff
                    # print(f"sec: {line_list[7]}, t_time: {float(line_list[11])} r_time: {video_delay_list[video_delay_index][1]} video_delay: {video_delay:.6f}")
                    video_delay_average += video_delay
                    if video_delay > video_delay_max:
                        video_delay_max = video_delay
                    video_delay_index += 1
                    # print(f"video_delay: {line_list[7]}, {video_delay:.6f}")
                continue

            # 受信したパケットの処理
            if line_list[3] == "Recv" and line_list[5] == "CONTROL":
                end_time = float(line_list[1])
                if end_time - previous_time > 1:  # 5s以上の間隔がある場合はアダプタが送信不可状態であると判断
                    print(f"{camn_file_name} 通信中断:  {previous_time:.6f} {end_time:.6f}")
                previous_time = end_time
                recv_control_size += float(line_list[11])
                recv_control_num += 1
                
                # control_delayを計算
                if previous_seq != int(line_list[9]):
                    while True:
                        if len(control_delay_list) == 0:
                            break
                        control_delay_tuple = control_delay_list.pop(0)
                        if control_delay_tuple[0] == int(line_list[9]):
                            if time_perf_counter_camn > 1e9:
                                control_delay = (float(line_list[13]) - control_delay_tuple[1]) / 1e9
                            else:
                                control_delay = float(line_list[13]) - control_delay_tuple[1] - time_perf_counter_diff
                            # print(f"sec: {line_list[9]}, t_time: {control_delay_tuple[1]} r_time: {float(line_list[13])} control_delay: {control_delay:.6f}")
                            # print(f"control_delay+diff: {control_delay + time_perf_counter_diff}")
                            control_delay_average += control_delay
                            if control_delay > control_delay_max:
                                control_delay_max = control_delay
                                # print(f"control_delay: {line_list[9]}, {control_delay:.6f}")
                            break
                previous_seq = int(line_list[9])
                

            # 送信したパケットの処理
            if line_list[3] == "Send" and line_list[5] == "VIDEO":
                end_time = float(line_list[1])  # 送信時間を記録
                recv_time = float(line_list[1])
                if recv_time - previous_time > 1:  # 5s以上の間隔がある場合はアダプタが送信不可状態であると判断
                    print(f"{camn_file_name} 通信中断:  {previous_time:.6f} {recv_time:.6f}")
                previous_time = recv_time
                send_video_size += float(line_list[11])
                send_video_num += 1

                # video_delayを計算
                if video_delay_index >= len(video_delay_list):
                    continue
                if video_delay_list[video_delay_index][0] == int(line_list[9]):
                    if time_perf_counter_camn > 1e9:
                        video_delay = (video_delay_list[video_delay_index][1] - float(line_list[13])) / 1e9
                    else:
                        video_delay = video_delay_list[video_delay_index][1] - float(line_list[13]) + time_perf_counter_diff
                    # print(f"sec: {line_list[7]}, t_time: {float(line_list[11])} r_time: {video_delay_list[video_delay_index][1]} video_delay: {video_delay:.6f}")
                    video_delay_average += video_delay
                    if video_delay > video_delay_max:
                        video_delay_max = video_delay
                        # print(f"video_delay: {line_list[7]}, {video_delay:.6f}")
                    video_delay_index += 1

    # print(f"video_delay_max: {video_delay_max:.6f}")
    # print(f"control_delay_max: {control_delay_max:.6f}")

    # スループットを計算
    control_throughput = recv_control_size / (end_time - start_time) * 8 / 10**6  # Mbps

    camn_end_time = end_time

    video_delay_average /= recv_video_num if recv_video_num > 0 else 1
    control_delay_average /= recv_control_num if recv_control_num > 0 else 1

    return recv_video_size, recv_video_num, send_control_size, send_control_num, video_throughput, cn_end_time, recv_control_size, recv_control_num, send_video_size, send_video_num, control_throughput, camn_end_time, video_delay_max, control_delay_max, lost_ack_num, video_delay_average, control_delay_average, lost_video_num
    # return recv_control_size, recv_control_num, send_video_size, send_video_num, control_throughput, end_time



if __name__ == '__main__':
    # 引数確認
    if len(sys.argv) == 2:
        camn_file_name = sys.argv[1]+"CamN.log"
        cn_file_name = sys.argv[1]+"CN.log"
    elif len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} [camn_file_name] [cn_file_name]")
        sys.exit()
    else:
        camn_file_name = sys.argv[1]
        cn_file_name = sys.argv[2]

    # recv_control_size, recv_control_num, send_video_size, send_video_num, control_throughput, end_time = analyze_camn_cn(camn_file_name, cn_file_name)
    recv_video_size, recv_video_num, send_control_size, send_control_num, video_throughput, cn_end_time, recv_control_size, recv_control_num, send_video_size, send_video_num, control_throughput, camn_end_time, video_delay_max, control_delay_max, lost_ack_num, video_delay_average, control_delay_average, lost_video_num = analyze_camn_cn(camn_file_name, cn_file_name)

    print()
    print(sys.argv[1])
    print(f"control_delay_max: {control_delay_max:.6f} s")
    print(f"video_delay_max: {video_delay_max:.6f} s")

    # 総受信パケットサイズ
    # print(f"Total_received_control_size: {recv_control_size} byte")

    # 総送信パケットサイズ
    # print(f"Total_sent_video_size: {send_video_size} byte")

    # スループット
    # print(f"Control_recv_throughput: {control_throughput:.6f} Mbps")

    # 映像パケット総送信数
    print(f"Total_sent_video_num: {send_video_num}")

    # 映像パケット総受信数
    print(f"Total_received_video_num: {recv_video_num}")

    # 映像パケット送受信サイズ
    print(f"Total_sent_video_size: {send_video_size} byte")
    print(f"Total_received_video_size: {recv_video_size} byte")
    print()
    # 映像パケットロス率
    video_loss_rate_num = (1 - recv_video_num / send_video_num) * 100
    print(f"Video_loss_rate_num: {video_loss_rate_num:.2f} %")
    print(f"Video_loss_seq_num: {lost_video_num}")

    # 映像スループット
    print(f"Video_throughput: {video_throughput:.6f} Mbps")

    # 制御情報総送信数
    print(f"Total_sent_control_num: {send_control_num}")

    # 制御情報総受信数
    print(f"Total_received_control_num: {recv_control_num}")
    # 制御情報パケットロス率
    control_loss_rate_num = (1 - recv_control_num / send_control_num) * 100
    print(f"Control_loss_rate_num: {control_loss_rate_num:.2f} %")

    # 制御情報総送信サイズ
    print(f"Total_sent_control_size: {send_control_size} byte")
    # 制御情報総受信サイズ
    print(f"Total_received_control_size: {recv_control_size} byte")
    # 制御情報パケットロス率
    control_loss_rate_size = (1 - recv_control_size / send_control_size) * 100
    print(f"Control_loss_rate_size: {control_loss_rate_size:.2f} %")
    print()
    
    # 遅延
    print(f"Control_delay_max: {control_delay_max:.6f} s")
    print(f"Video_delay_max: {video_delay_max:.6f} s")
    print(f"Control_delay_average: {control_delay_average:.6f} s")
    print(f"Video_delay_average: {video_delay_average:.6f} s")
    
