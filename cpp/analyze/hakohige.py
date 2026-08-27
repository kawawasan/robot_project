import sys
import re
import os
import numpy as np
import matplotlib.pyplot as plt

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
        print("Usage: python3 plot_delay_boxplot.py <logs...>")
        return

    nodes = parse_logs_with_sync(sys.argv[1:])

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

    phase_stats = {
        '1-Hop (Direct)': {'delays': []},
        '2-Hop (RN2)':    {'delays': []},
        '3-Hop (RN1)':    {'delays': []}
    }

    for seq, t_send in cn_ctrl_sends.items():
        phase = get_phase_at_time(t_send)
        if seq in camn_ctrl_recvs:
            t_recv = camn_ctrl_recvs[seq]
            delay_ms = (t_recv - t_send) * 1000.0
            if delay_ms >= 0:
                phase_stats[phase]['delays'].append(delay_ms)

   # ---------------------------------------------------------
    # 箱ひげ図の描画処理（視認性100点バージョン）
    # ---------------------------------------------------------
    labels_full = ['1-Hop (Direct)', '2-Hop (RN2)', '3-Hop (RN1)']
    display_labels = ['1-Hop', '2-Hop', '3-Hop']
    data_to_plot = []
    valid_labels = []

    for full_label, short_label in zip(labels_full, display_labels):
        if len(phase_stats[full_label]['delays']) > 0:
            data_to_plot.append(phase_stats[full_label]['delays'])
            valid_labels.append(short_label)

    if not data_to_plot:
        print("Error: 描画するデータがありません。")
        return

    plt.figure(figsize=(8, 6))
    
    # ✨ 調整1: 外れ値（黒いプロット）の極限チューニング
    flierprops = dict(
        marker='o',             # 綺麗な丸
        markerfacecolor='black', 
        markeredgecolor='none', # 【超重要】縁取りを消して黒潰れを防ぐ
        alpha=0.3,             # 透明度を下げて、点が密集している部分だけ濃く見せる
        markersize=3            # 点のサイズを少し小さく
    )

    # ✨ 調整2: 中央値（Median）の線を太く赤くして強調
    medianprops = dict(linestyle='-', linewidth=1.5, color='firebrick')

    # ✨ 調整3: 箱やヒゲの線をキリッとさせる
    boxprops = dict(facecolor='#add8e6', color='black', linewidth=1, alpha=0.9)
    capprops = dict(color='black', linewidth=1)
    whiskerprops = dict(color='black', linewidth=1, linestyle='--')

    # 箱ひげ図の作成
    box = plt.boxplot(data_to_plot, labels=valid_labels, showmeans=True, 
                      patch_artist=True, flierprops=flierprops,
                      medianprops=medianprops, boxprops=boxprops,
                      capprops=capprops, whiskerprops=whiskerprops)

    # plt.title('Control Command End-to-End Delay by Hop Count', fontsize=14)
    plt.ylabel('Delay (ms)', fontsize=14, fontweight='bold')
    plt.xlabel('Routing Phase', fontsize=14, fontweight='bold')
    
    # ✨ 調整4: グリッドを美しく箱の「後ろ」に配置する
    plt.grid(axis='y', linestyle='--', alpha=0.6, color='gray')
    plt.gca().set_axisbelow(True) # グリッド線を箱の背面に回す

    # ✨ 調整5: グラフの枠線を論文仕様（上と右を消してスッキリ）にする
    ax = plt.gca()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(1.2)
    ax.spines['bottom'].set_linewidth(1.2)

    # 【重要】外れ値（2000ms超えなど）が大きすぎて箱が潰れて見えない場合、
    # Y軸の表示上限を制限して箱を見やすくします。
    # plt.ylim(-5, 170) # (例: -5ms から 170ms までを拡大表示)

    plt.tight_layout()
    output_filename = 'delay_boxplot_perfect.png'
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    print(f"\n✅ 成功: 視認性を極限まで高めた箱ひげ図を '{output_filename}' に保存しました！")

if __name__ == "__main__":
    main()