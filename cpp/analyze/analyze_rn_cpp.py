# RN.logを分析 アダプタ送信停止を検知

import sys

def analyze_rn(file_name):
    start_time = 0
    end_time = 0
    previous_time = 0
    recv_video_size = 0
    recv_video_num = 0
    send_control_size = 0
    send_control_num = 0
    video_drop_num = 0

    # ファイルを読み込む
    with open(file_name, 'r') as f:
        for line in f:
            line_list = line.split()

            if line_list[0] != "T=":  # 最初の行らをスキップ
                continue

            # 最初の受信パケットの時間を記録
            if start_time == 0 and line_list[0] == "T=":
                start_time = float(line_list[1])
                previous_time = start_time
                continue

            # 受信したパケットのサイズを計算
            if line_list[0] == "T=":
                end_time = float(line_list[1])
                if end_time - previous_time > 1:
                    print(f"{file_name} 通信中断: {previous_time:.6f} {end_time:.6f}")
                previous_time = end_time

                if line_list[3] == "Video_Packet_Drop":
                    video_drop_num += 1

    print(f"{file_name[-7:]}_video_drop_num= {video_drop_num}")

    return end_time


if __name__ == '__main__':
    # 引数確認
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} [file_name]")
        sys.exit()

    file_name = sys.argv[1]

    # recv_video_size, recv_video_num, send_control_size, send_control_num, video_throughput, end_time = analyze_rn(file_name)
    end_time = analyze_rn(file_name)

    # 総受信パケットサイズ
    # print(f"Total_received_video_size= {recv_video_size} byte")

    # 総送信パケットサイズ
    # print(f"Total_sent_control_size= {send_control_size} byte")

    # スループット
    # print(f"Video_recv_throughput= {video_throughput:.6f} Mbps")
