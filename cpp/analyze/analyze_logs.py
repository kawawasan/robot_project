import sys
import os
from collections import defaultdict

def parse_log_file(filename: str):
    """
    指定されたログファイルをパースし、イベントごとのパケットリストと最終タイムスタンプを返す。
    ログの各行は "Key= Value" 形式であることを想定。

    Args:
        filename (str): 解析するログファイル名。

    Returns:
        tuple[defaultdict, float]: (イベントごとのパケット辞書のリスト, 最終タイムスタンプ)
    """
    filepath = os.path.expanduser(filename)
    if not os.path.exists(filepath):
        print(f"警告: ファイル '{filename}' が見つかりません。スキップします。")
        return defaultdict(list), 0.0

    events = defaultdict(list)
    last_timestamp = 0.0

    with open(filepath, 'r') as f:
        for line in f:
            try:
                parts = line.split()
                if not parts or not parts[0].startswith('T='):
                    continue

                log_data = {parts[i].replace('=', ''): parts[i+1] for i in range(0, len(parts), 2)}
                
                event_type = log_data.get("Ev")
                packet_type = log_data.get("Type")

                if not event_type or not packet_type:
                    continue

                if event_type.startswith('Send_outside'):
                    event_type = 'Send'

                key = f"{event_type}_{packet_type}"
                
                packet_info = {
                    'T': float(log_data["T"]),
                    'Seq': int(log_data.get("Seq", 0)),
                    'ACK': int(log_data.get("ACK", 0)),
                    'PayloadSize': int(log_data.get("PayloadSize", 0)),
                }
                events[key].append(packet_info)
                last_timestamp = max(last_timestamp, packet_info['T'])

            except (IndexError, ValueError, KeyError):
                pass
                
    # このスクリプトはソート済みのファイルを期待するため、ここでのソートは不要
    # for key in events:
    #     events[key].sort(key=lambda p: p['T'])
        
    return events, last_timestamp

def calculate_delay(send_packets, recv_packets, key_field='Seq'):
    """
    送受信パケットリストから遅延（最大・平均）を計算する。
    """
    send_times = {p[key_field]: p['T'] for p in send_packets}
    
    delays = []
    for p in recv_packets:
        send_time = send_times.get(p[key_field])
        if send_time is not None:
            delay = p['T'] - send_time
            if delay >= 0:
                delays.append(delay)

    if not delays:
        return 0.0, 0.0

    max_delay = max(delays)
    avg_delay = sum(delays) / len(delays)
    return max_delay, avg_delay

def main():
    """
    メイン処理。コマンドライン引数を解釈し、各ログを解析して結果を表示する。
    """
    if len(sys.argv) < 3:
        print(f"使い方: python3 {sys.argv[0]} <CamN.log> <CN.log> [RN1.log] [RN2.log] ...")
        sys.exit(1)

    camn_file = sys.argv[1]
    cn_file = sys.argv[2]
    rn_files = sys.argv[3:]

    camn_events, camn_end_time = parse_log_file(camn_file)
    cn_events, cn_end_time = parse_log_file(cn_file)
    
    rn_end_times = {}
    for rn_file in rn_files:
        rn_name = os.path.basename(rn_file)
        _, end_time = parse_log_file(rn_file)
        if end_time > 0:
            # 元のファイル名から_RN1などを抽出
            clean_name = rn_name.split('_')[-1].split('.')[0]
            rn_end_times[clean_name] = end_time

    # --- 統計情報の計算 ---
    send_video_packets = camn_events['Send_VIDEO']
    recv_video_packets = cn_events['Recv_VIDEO']
    send_control_packets = cn_events['Send_CONTROL']
    recv_control_packets = camn_events['Recv_CONTROL']

    send_video_num = len(send_video_packets)
    recv_video_num = len(recv_video_packets)
    send_video_size = sum(p['PayloadSize'] for p in send_video_packets)
    recv_video_size = sum(p['PayloadSize'] for p in recv_video_packets)

    send_control_num = len(send_control_packets)
    recv_control_num = len(recv_control_packets)
    
    # パケロス率
    control_loss_rate_num = (1 - recv_control_num / send_control_num) * 100 if send_control_num > 0 else 0
    video_loss_rate_num = (1 - recv_video_num / send_video_num) * 100 if send_video_num > 0 else 0
    lost_ack_num = send_control_num - recv_control_num
    lost_video_num = send_video_num - recv_video_num

    # 遅延
    video_delay_max, video_delay_average = calculate_delay(send_video_packets, recv_video_packets, key_field='Seq')
    control_delay_max, control_delay_average = calculate_delay(send_control_packets, recv_control_packets, key_field='ACK')
    
    # スループット (受信側の実測値=グッドプット)
    video_throughput = 0.0
    if recv_video_num > 1:
        duration = recv_video_packets[-1]['T'] - recv_video_packets[0]['T']
        if duration > 0:
            video_throughput = (recv_video_size * 8) / (duration * 1_000_000)

    # --- 結果の出力 ---
    print()
    print(f"CamN_end_time: {camn_end_time:.6f} s")
    for name, time in sorted(rn_end_times.items()): # RN1, RN2の順で表示
        print(f"{name}_end_time:  {time:.6f} s")
    print(f"CN_end_time:   {cn_end_time:.6f} s")

    print()
    print(f"control_delay_max: {control_delay_max:.6f} s")
    print(f"video_delay_max:   {video_delay_max:.6f} s")
    print(f"control_delay_average: {control_delay_average:.6f} s")
    print(f"video_delay_average:   {video_delay_average:.6f} s")

    print()
    print(f"Control_loss_rate_num: {control_loss_rate_num:.2f} %")
    print(f"Video_loss_rate_num:   {video_loss_rate_num:.2f} %")
    print(f"Lost_ack_num: {lost_ack_num}")
    print(f"Video_loss_seq_num: {lost_video_num}")
    
    print()
    print(f"Video_throughput: {video_throughput:.6f} Mbps")
    print(f"Video_send_size: {send_video_size} bytes")
    print(f"Video_recv_size: {recv_video_size} bytes")
    print()

if __name__ == "__main__":
    main()