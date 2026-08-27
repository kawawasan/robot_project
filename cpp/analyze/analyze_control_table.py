import sys
import re
import os
import numpy as np

def parse_logs_with_sync(filepaths):
    nodes = {}
    time_prefs = {}
    
    # 1. OS時間の同期用ベースカウンタを取得
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        node_id = None
        if "CamN" in filename: node_id = "CamN"
        elif "RN1" in filename: node_id = "RN1"
        elif "RN2" in filename: node_id = "RN2"
        elif "CN" in filename or "CtlN" in filename: node_id = "CtlN"
        
        if not node_id: continue
        
        nodes[node_id] = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if 'time_pref_counter=' in line:
                        m = re.search(r'time_pref_counter=\s*(\d+)', line)
                        if m: time_prefs[node_id] = int(m.group(1))
                        break
        except Exception: pass
        
    min_pref = min(time_prefs.values()) if time_prefs else 0
    
    # 2. パケットデータの抽出（時刻を同期）
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        node_id = None
        if "CamN" in filename: node_id = "CamN"
        elif "RN1" in filename: node_id = "RN1"
        elif "RN2" in filename: node_id = "RN2"
        elif "CN" in filename or "CtlN" in filename: node_id = "CtlN"
        
        if not node_id: continue
        t_offset = (time_prefs.get(node_id, min_pref) - min_pref) / 1e9 
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*([A-Z_]+).*Seq=\s*(\d+)', line)
                    if m:
                        nodes[node_id].append({
                            'T': float(m.group(1)) + t_offset, # 同期済み絶対時間
                            'Ev': m.group(2), 
                            'Type': m.group(3), 
                            'Seq': int(m.group(4))
                        })
        except Exception as e:
            print(f"Error reading {node_id}: {e}", file=sys.stderr)
            
    return nodes

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_control_auto.py <logs...>")
        return

    nodes = parse_logs_with_sync(sys.argv[1:])

    # ---------------------------------------------------------
    # 1. あなたのロジックを継承：VIDEOパケットから現在のフェーズを自動判定
    # ---------------------------------------------------------
    camn_video_sends = {d['Seq']: d['T'] for d in nodes.get('CamN', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Send'}
    ctln_video_recvs = {d['Seq']: d['T'] for d in nodes.get('CtlN', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Recv'}
    rn1_video_seqs = set(d['Seq'] for d in nodes.get('RN1', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Recv')
    rn2_video_seqs = set(d['Seq'] for d in nodes.get('RN2', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Recv')

    phase_timeline = []
    current_phase = '1-Hop (Direct)'
    phase_timeline.append((0.0, current_phase))

    for seq in sorted(camn_video_sends.keys()):
        t_send = camn_video_sends[seq]
        if seq in ctln_video_recvs:
            if seq in rn1_video_seqs: new_phase = '3-Hop (RN1)'
            elif seq in rn2_video_seqs: new_phase = '2-Hop (RN2)'
            else: new_phase = '1-Hop (Direct)'
            
            if new_phase != current_phase:
                phase_timeline.append((t_send, new_phase))
                current_phase = new_phase

    def get_phase_at_time(t):
        ans = phase_timeline[0][1]
        for t_phase, p in phase_timeline:
            if t >= t_phase: ans = p
            else: break
        return ans

    # ---------------------------------------------------------
    # 2. 制御コマンドの評価（生成時間と最終到達時間）
    # ---------------------------------------------------------
    cn_ctrl_sends = {}
    for d in nodes.get('CtlN', []):
        if d['Type'] == 'CONTROL' and d['Ev'] in ['Generate_Command', 'Send']:
            seq = d['Seq']
            if seq not in cn_ctrl_sends or d['T'] < cn_ctrl_sends[seq]:
                cn_ctrl_sends[seq] = d['T']

    camn_ctrl_recvs = {}
    for d in nodes.get('CamN', []):
        if d['Type'] == 'CONTROL' and d['Ev'] == 'Recv':
            seq = d['Seq']
            if seq not in camn_ctrl_recvs or d['T'] < camn_ctrl_recvs[seq]:
                camn_ctrl_recvs[seq] = d['T']

    # ---------------------------------------------------------
    # 3. 集計と出力
    # ---------------------------------------------------------
    phase_stats = {
        '1-Hop (Direct)': {'sent': 0, 'recv': 0, 'delays': []},
        '2-Hop (RN2)':    {'sent': 0, 'recv': 0, 'delays': []},
        '3-Hop (RN1)':    {'sent': 0, 'recv': 0, 'delays': []}
    }

    for seq, t_send in cn_ctrl_sends.items():
        phase = get_phase_at_time(t_send)
        phase_stats[phase]['sent'] += 1
        
        if seq in camn_ctrl_recvs:
            t_recv = camn_ctrl_recvs[seq]
            delay_ms = (t_recv - t_send) * 1000.0
            if delay_ms >= 0:
                phase_stats[phase]['recv'] += 1
                phase_stats[phase]['delays'].append(delay_ms)

    print("\n" + "="*80)
    print(" 📊 制御コマンド (Control Plane) 自動フェーズ別 性能評価表")
    print("="*80)
    print(f"{'Phase (Routing)':<16} | {'Sent':>5} | {'Recv':>5} | {'Loss(%)':>7} | {'Min(ms)':>7} | {'Avg(ms)':>7} | {'Max(ms)':>7}")
    print("-" * 80)

    for phase_name in ['1-Hop (Direct)', '2-Hop (RN2)', '3-Hop (RN1)']:
        data = phase_stats[phase_name]
        sent = data['sent']
        recv = data['recv']
        loss_rate = ((sent - recv) / sent * 100) if sent > 0 else 0.0
        
        if len(data['delays']) > 0:
            min_d = np.min(data['delays'])
            avg_d = np.mean(data['delays'])
            max_d = np.max(data['delays'])
            print(f"{phase_name:<16} | {sent:>5} | {recv:>5} | {loss_rate:>6.1f}% | {min_d:>7.1f} | {avg_d:>7.1f} | {max_d:>7.1f}")
        else:
            print(f"{phase_name:<16} | {sent:>5} | {recv:>5} | {loss_rate:>6.1f}% | {'N/A':>7} | {'N/A':>7} | {'N/A':>7}")

    print("="*80 + "\n")
    print("💡 解析ロジック: VIDEOパケットの配送ルートを基準にネットワークのホップ数を自動検知し、")
    print("   その時間帯に送信されたCONTROLパケットのEnd-to-End遅延とロス率を算出しました。")

if __name__ == "__main__":
    main()