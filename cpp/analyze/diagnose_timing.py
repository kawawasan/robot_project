#!/usr/bin/env python3
"""
【重要】システムクロック基準での時刻補正
"""
import sys
import glob
import os
import re
from collections import defaultdict
import numpy as np

def extract_header_timestamps(log_files):
    """各ログファイルのヘッダから time_pref_counter を抽出"""
    timestamps = {}
    
    for filepath in log_files:
        node_name = os.path.basename(filepath).split('_')[-1].replace('.log', '')
        
        with open(filepath, 'r') as f:
            for line in f:
                # ヘッダから time_pref_counter を取得
                match = re.search(r'time_pref_counter=\s*(\d+)', line)
                if match:
                    ts_ns = int(match.group(1))
                    timestamps[node_name] = ts_ns
                    print(f"Found {node_name}: time_pref_counter = {ts_ns} ns", file=sys.stderr)
                    break
    
    return timestamps

def parse_logs_with_system_correction(log_files, header_timestamps):
    """
    システムクロック基準で時刻を補正
    
    各イベントの "SystemTime" フィールドが、プログラム起動時刻からの経過時間を表すため、
    ヘッダの time_pref_counter を基準にして絶対時刻に変換
    """
    events = []
    
    cn_pattern = re.compile(
        r'T=\s*([0-9.]+)\s+Ev=\s*(Send|Recv|Generate_Command)\s+Type=\s*([A-Z_]+)\s+'
        r'ACK=\s*(\d+)\s+Seq=\s*(\d+).*?SystemTime=\s*(\d+)'
    )
    
    camn_pattern = re.compile(
        r'T=\s*([0-9.]+)\s+Ev=\s*(Send|Recv)\s+Type=\s*([A-Z]+)\s+'
        r'ACK=\s*(\d+)\s+Seq=\s*(\d+).*?SystemTime=\s*(\d+)'
    )
    
    rn_pattern = re.compile(
        r'T=\s*([0-9.]+)\s+Ev=\s*(Send|Recv)\s+Type=\s*([A-Z]+)\s+'
        r'Direction=\s*(\w+)\s+Seq=\s*(\d+)'
    )
    
    for filepath in log_files:
        node_name = os.path.basename(filepath).split('_')[-1].replace('.log', '')
        header_time_ns = header_timestamps.get(node_name, 0)
        
        print(f"Parsing {node_name} (header_time={header_time_ns})...", file=sys.stderr)
        
        with open(filepath, 'r') as f:
            for line in f:
                # CamN フォーマット
                if node_name == 'CamN':
                    match = camn_pattern.search(line)
                    if match:
                        t_hr = float(match.group(1))
                        ev = match.group(2)
                        p_type = match.group(3)
                        ack = int(match.group(4))
                        seq = int(match.group(5))
                        sys_time_ns = int(match.group(6))
                        
                        # 絶対時刻に変換
                        abs_time_ns = header_time_ns + sys_time_ns
                        abs_time_s = abs_time_ns / 1e9
                        
                        events.append({
                            'abs_time_ns': abs_time_ns,
                            'abs_time_s': abs_time_s,
                            'hr_time': t_hr,
                            'node': node_name,
                            'event': ev,
                            'type': p_type,
                            'seq': seq,
                            'ack': ack,
                            'format': 'CamN'
                        })
                
                # CN フォーマット
                elif node_name == 'cn':
                    match = cn_pattern.search(line)
                    if match:
                        t_hr = float(match.group(1))
                        ev = match.group(2)
                        p_type = match.group(3)
                        ack = int(match.group(4))
                        seq = int(match.group(5))
                        sys_time_ns = int(match.group(6))
                        
                        # 絶対時刻に変換
                        abs_time_ns = header_time_ns + sys_time_ns
                        abs_time_s = abs_time_ns / 1e9
                        
                        events.append({
                            'abs_time_ns': abs_time_ns,
                            'abs_time_s': abs_time_s,
                            'hr_time': t_hr,
                            'node': node_name,
                            'event': ev,
                            'type': p_type,
                            'seq': seq,
                            'ack': ack,
                            'format': 'CN'
                        })
                
                # RN フォーマット（SystemTime がない）
                else:
                    match = rn_pattern.search(line)
                    if match:
                        t_hr = float(match.group(1))
                        ev = match.group(2)
                        p_type = match.group(3)
                        direction = match.group(4)
                        seq = int(match.group(5))
                        
                        events.append({
                            'hr_time': t_hr,
                            'node': node_name,
                            'event': ev,
                            'type': p_type,
                            'seq': seq,
                            'direction': direction,
                            'format': 'RN'
                        })
    
    return events

def analyze_clock_synchronization(events):
    """【重要】ノード間の時刻同期状況を診断"""
    print("\n=== 【診断1】ノード間の時刻同期 ===")
    
    # CamN と CN のシステムクロック差を計算
    camn_events = [e for e in events if e['node'] == 'CamN' and 'abs_time_ns' in e]
    cn_events = [e for e in events if e['node'] == 'cn' and 'abs_time_ns' in e]
    
    if camn_events and cn_events:
        camn_base = camn_events[0]['abs_time_ns']
        cn_base = cn_events[0]['abs_time_ns']
        
        drift_ns = cn_base - camn_base
        drift_ms = drift_ns / 1e6
        
        print(f"CamN first event: {camn_base} ns")
        print(f"CN first event:   {cn_base} ns")
        print(f"→ Drift: {drift_ns:.0f} ns = {drift_ms:.3f} ms")
        
        if abs(drift_ms) > 5:
            print(f"⚠️  WARNING: Clock drift > 5ms detected!")
        else:
            print(f"✓ Clock drift acceptable")

def analyze_timing_precision(events):
    """送信間隔のジッタ分析"""
    print("\n=== 【診断2】送信間隔のジッタ (hr_time ベース) ===")
    
    send_times_by_node = defaultdict(list)
    
    for ev in events:
        if ev['event'] == 'Send' and ev['type'] in ['VIDEO', 'CONTROL']:
            send_times_by_node[ev['node']].append(ev['hr_time'])
    
    for node in sorted(send_times_by_node.keys()):
        times = sorted(send_times_by_node[node])
        if len(times) < 5:
            continue
        
        intervals = np.diff(times) * 1000  # ミリ秒
        
        print(f"\n{node}:")
        print(f"  平均間隔: {np.mean(intervals):.3f} ms")
        print(f"  標準偏差: {np.std(intervals):.3f} ms")
        print(f"  最小/最大: {np.min(intervals):.3f} / {np.max(intervals):.3f} ms")
        print(f"  ジッタ: {(np.max(intervals) - np.min(intervals)):.3f} ms")
        
        # 期待値との比較
        expected_ms = 0.5  # ipt_interval = 0.000500 s = 0.5 ms
        deviation = (np.mean(intervals) - expected_ms) / expected_ms * 100
        print(f"  期待値 {expected_ms}ms との偏差: {deviation:+.1f}%")

def analyze_packet_propagation(events, start_time, end_time):
    """パケット伝播遅延の分析"""
    print(f"\n=== 【診断3】パケット伝播遅延 ({start_time}s - {end_time}s) ===")
    
    # 時間帯でフィルタ
    events_filtered = [e for e in events 
                      if start_time <= e.get('abs_time_s', e['hr_time']) <= end_time]
    
    # VIDEO パケットについて、CamN Send -> CN Recv の遅延を計算
    camn_sends = defaultdict(list)
    cn_recvs = defaultdict(list)
    
    for ev in events_filtered:
        if ev['node'] == 'CamN' and ev['event'] == 'Send' and ev['type'] == 'VIDEO':
            camn_sends[ev['seq']].append(ev['abs_time_s'])
        elif ev['node'] == 'cn' and ev['event'] == 'Recv' and ev['type'] == 'VIDEO':
            cn_recvs[ev['seq']].append(ev['abs_time_s'])
    
    propagation_delays = []
    for seq in sorted(set(list(camn_sends.keys()) + list(cn_recvs.keys()))):
        if seq in camn_sends and seq in cn_recvs:
            send_time = camn_sends[seq][0]
            recv_time = cn_recvs[seq][0]
            delay_ms = (recv_time - send_time) * 1000
            propagation_delays.append(delay_ms)
            
            if len(propagation_delays) <= 5:  # 最初の5つだけ表示
                print(f"Seq {seq}: CamN Send {send_time:.6f}s -> CN Recv {recv_time:.6f}s, Delay: {delay_ms:.3f} ms")
    
    if propagation_delays:
        print(f"\nPropagation delay statistics:")
        print(f"  Mean: {np.mean(propagation_delays):.3f} ms")
        print(f"  StDev: {np.std(propagation_delays):.3f} ms")
        print(f"  Min/Max: {np.min(propagation_delays):.3f} / {np.max(propagation_delays):.3f} ms")

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python diagnose_corrected.py <log_dir> <start_time> <duration>")
        sys.exit(1)
    
    log_dir = sys.argv[1]
    start_time = float(sys.argv[2])
    duration = float(sys.argv[3])
    
    files = sorted(glob.glob(os.path.join(log_dir, "*.log")))
    
    # ステップ1: ヘッダから基準時刻を抽出
    header_timestamps = extract_header_timestamps(files)
    
    # ステップ2: システムクロック補正付きでパース
    events = parse_logs_with_system_correction(files, header_timestamps)
    print(f"\nParsed {len(events)} events\n", file=sys.stderr)
    
    # ステップ3: 診断実行
    analyze_clock_synchronization(events)
    analyze_timing_precision(events)
    analyze_packet_propagation(events, start_time, start_time + duration)