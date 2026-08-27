import sys
import glob
import os
import re
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon
from collections import defaultdict

# ノード定義
nodes = {'CtlN': 0, 'RN1': 1, 'RN2': 2, 'CamN': 3}

# 物理層パラメータ (4.2節の理論値)
BITRATE = 72.2 * 1e6 
OVERHEAD_TIME = 0.00015 

def get_t_frame(payload_size):
    return OVERHEAD_TIME + (payload_size * 8) / BITRATE

def resolve_log_files(file_pattern):
    expanded_pattern = os.path.expanduser(file_pattern)
    matched_files = glob.glob(expanded_pattern)
    log_files = {}
    for filepath in matched_files:
        basename = os.path.basename(filepath)
        if any(x in basename for x in ['CtlN', 'cn', 'CN']): log_files['CtlN'] = filepath
        elif 'RN1' in basename: log_files['RN1'] = filepath
        elif 'RN2' in basename: log_files['RN2'] = filepath
        elif 'CamN' in basename: log_files['CamN'] = filepath
    return log_files

def parse_logs(log_files):
    events = []
    time_prefs = {}
    for node, filepath in log_files.items():
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if 'time_pref_counter=' in line:
                        m = re.search(r'time_pref_counter=\s*(\d+)', line)
                        if m: time_prefs[node] = int(m.group(1))
                        break
        except Exception: pass
    min_pref = min(time_prefs.values()) if time_prefs else 0
    
    for node, filepath in log_files.items():
        t_offset = (time_prefs.get(node, min_pref) - min_pref) / 1e9 
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if 'Ev=' not in line or 'Seq=' not in line: continue
                    t_match = re.search(r'T=\s*([\d\.]+)', line)
                    if not t_match: continue
                    t_sec = float(t_match.group(1))
                    ev_match = re.search(r'Ev=\s*(\S+)', line)
                    raw_ev = ev_match.group(1) if ev_match else ''
                    type_match = re.search(r'Type=\s*([A-Z_]+)', line)
                    p_type = type_match.group(1) if type_match else ''
                    is_gen_cmd = 'Generate_Command' in raw_ev
                    if is_gen_cmd: p_type = 'CONTROL'
                    if not p_type: continue
                    seq_match = re.search(r'Seq=\s*(\d+)', line)
                    seq = int(seq_match.group(1)) if seq_match else 0
                    ack_match = re.search(r'ACK=\s*(\d+)', line)
                    ack = int(ack_match.group(1)) if ack_match else 0
                    size_match = re.search(r'PayloadSize=\s*(\d+)', line) or re.search(r'PacketBytes=\s*(\d+)', line)
                    p_size = int(size_match.group(1)) if size_match else 0
                    events.append({
                        'node': node, 'time': t_sec + t_offset, 'event': raw_ev,
                        'is_send': 'Send' in raw_ev, 'is_recv': raw_ev == 'Recv',
                        'is_gen_cmd': is_gen_cmd, 'type': p_type, 'seq': seq, 'ack': ack, 'size': p_size
                    })
        except Exception: pass
    return sorted(events, key=lambda x: x['time'])

def extract_links(events):
    links, cmds = [], []
    node_offsets = defaultdict(float)
    groups = defaultdict(lambda: {'sends': [], 'recvs': []})
    
    for ev in events:
        if ev['is_gen_cmd']: cmds.append(ev); continue
        key = (ev['type'], ev['seq'], ev['ack'])
        if ev['is_send']: groups[key]['sends'].append(ev)
        elif ev['is_recv']: groups[key]['recvs'].append(ev)

    # 🌟 自動時刻補正パス (逆行を完全に解消)
    for key, group in groups.items():
        for r in group['recvs']:
            for s in group['sends']:
                if s['node'] == r['node']: continue
                diff = r['time'] - s['time']
                if -0.1 <= diff < 0.0001:
                    offset = abs(diff) + 0.001
                    if offset > node_offsets[r['node']]: node_offsets[r['node']] = offset
    
    for ev in events: ev['time'] += node_offsets[ev['node']]

    # 🌟 リンクマッチング (フィルタを最適化)
    for key, group in groups.items():
        sends = sorted(group['sends'], key=lambda x: x['time'])
        recvs = sorted(group['recvs'], key=lambda x: x['time'])
        p_type = key[0]
        
        for r in recvs:
            best_s, min_diff = None, float('inf')
            for s in sends:
                if s['node'] == r['node']: continue
                
                # CtlINからの送信時の宛先フィルタ
                if s['node'] == 'CtlN':
                    if 'outside_num_2' in s['event'] and r['node'] != 'RN2': continue
                    if 'outside_num_3' in s['event'] and r['node'] != 'RN1': continue
                
                # 物理的因果関係 (送信 -> 受信)
                diff = r['time'] - s['time']
                if 0 < diff <= 0.1: # 100ms以内を許容
                    if diff < min_diff: min_diff, best_s = diff, s
            
            if best_s:
                links.append({
                    'type': p_type, 'seq': r['seq'], 'size': best_s['size'],
                    'sender_node': best_s['node'], 'sender_time': best_s['time'],
                    'receiver_node': r['node'], 'receiver_time': r['time']
                })
    return links, cmds

def plot_sequence(links, cmds, start_time, duration):
    end_time = start_time + duration
    plt.rcParams.update({'font.family': 'sans-serif', 'font.size': 14})
    fig, ax = plt.subplots(figsize=(11, 8), dpi=150)
    colors = {'VIDEO': '#E66100', 'CONTROL': "#0C5BEE", 'DUMMY': '#999999'}

    for node, x in nodes.items():
        ax.axvline(x=x, color='#D0D0D0', linestyle='--', linewidth=1.5, zorder=1)
        ax.text(x, start_time - duration*0.02, node, ha='center', va='bottom', fontweight='bold')

    # 生成から送信までの点線 (MUCViSの制御を可視化)
    for g in [c for c in cmds if c['is_gen_cmd']]:
        rel = next((l for l in links if l['type'] == 'CONTROL' and l['seq'] == g['seq']), None)
        if rel:
            ax.plot([nodes[g['node']], nodes[g['node']]], [g['time'], rel['sender_time']], 
                    color='#0C5BEE', linestyle=':', linewidth=1.5, zorder=2)

    # リボン (平行四辺形) の描画
    for link in links:
        if link['sender_time'] < start_time or link['sender_time'] > end_time: continue
        x_s, x_r = nodes[link['sender_node']], nodes[link['receiver_node']]
        t_s, t_r = link['sender_time'], link['receiver_time']
        t_f = get_t_frame(link['size'])
        color = colors.get(link['type'], '#000000')
        
        # 物理占有時間ブロックとしての描画
        poly = Polygon([(x_s, t_s), (x_s, t_s + t_f), (x_r, t_r + t_f), (x_r, t_r)], 
                       closed=True, facecolor=color, edgecolor=color, alpha=0.7, zorder=5)
        ax.add_patch(poly)

    # 生成点の描画
    for g in [c for c in cmds if c['is_gen_cmd']]:
        if start_time <= g['time'] <= end_time:
            ax.scatter(nodes[g['node']], g['time'], color="#0C5BEE", marker='s', s=40, edgecolor='white', zorder=6)

    ax.set_ylim(end_time, start_time)
    ax.set_ylabel('Synchronized Elapsed Time (s)', fontsize=16)
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    log_files = resolve_log_files(sys.argv[1])
    events = parse_logs(log_files)
    links, cmds = extract_links(events)
    plot_sequence(links, cmds, float(sys.argv[2]), float(sys.argv[3]))