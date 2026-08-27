import sys
import re
import os
import matplotlib.pyplot as plt
import japanize_matplotlib
from pathlib import Path

def parse_log(filepath):
    data = []
    filename = os.path.basename(filepath)
    node_id = None
    if "CamN" in filename: node_id = "CamN"
    elif "RN1" in filename: node_id = "RN1"
    elif "RN2" in filename: node_id = "RN2"
    elif "CN" in filename or "CtlN" in filename: node_id = "CtlN"
            
    if not node_id: return None, None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+).*PayloadSize=\s*(\d+)', line)
                if m:
                    data.append({
                        'T': float(m.group(1)), 'Ev': m.group(2), 
                        'Type': m.group(3), 'Seq': int(m.group(4))
                    })
        return data, node_id
    except Exception as e:
        print(f"Error reading {node_id}: {e}", file=sys.stderr)
        return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_metrics_cdf.py <logs...>")
        return

    nodes = {}
    for arg in sys.argv[1:]:
        logs, node_id = parse_log(arg)
        if logs: nodes[node_id] = logs

    # 必要なパケットの抽出 (VIDEOデータのみを対象)
    camn_sends = {d['Seq']: d['T'] for d in nodes.get('CamN', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Send'}
    ctln_recvs = {d['Seq']: d['T'] for d in nodes.get('CtlN', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Recv'}
    
    # 経路判定用: 各中継ノードがRecvしたSeqの集合
    rn1_seqs = set(d['Seq'] for d in nodes.get('RN1', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Recv')
    rn2_seqs = set(d['Seq'] for d in nodes.get('RN2', []) if d['Type'] == 'VIDEO' and d['Ev'] == 'Recv')

    # フェーズごとの統計データ格納庫
    phase_stats = {
        '1-Hop (Direct)': {'hops': 1, 'raw_delays': [], 'sent': 0, 'recv': 0, 'color': '#2ca02c', 'ls': '-'},
        '2-Hop (RN2)':    {'hops': 2, 'raw_delays': [], 'sent': 0, 'recv': 0, 'color': '#ff7f0e', 'ls': '--'},
        '3-Hop (RN1)':    {'hops': 3, 'raw_delays': [], 'sent': 0, 'recv': 0, 'color': '#1f77b4', 'ls': '-.'}
    }

    # 時系列順にパケットを評価し、動的にフェーズを判定
    current_phase = '1-Hop (Direct)' # 初期状態
    
    for seq in sorted(camn_sends.keys()):
        t_send = camn_sends[seq]
        
        # 受信成功したパケットで、現在のフェーズ（トポロジ）を更新・判定
        if seq in ctln_recvs:
            if seq in rn1_seqs:
                current_phase = '3-Hop (RN1)'
            elif seq in rn2_seqs:
                current_phase = '2-Hop (RN2)'
            else:
                current_phase = '1-Hop (Direct)'
            
            phase_stats[current_phase]['recv'] += 1
            raw_delay = (ctln_recvs[seq] - t_send) * 1000 # ms
            phase_stats[current_phase]['raw_delays'].append(raw_delay)
            
        # ロスしたパケットも含め、"その瞬間のフェーズ"の送信数としてカウント
        phase_stats[current_phase]['sent'] += 1

    # --- 1. 論文用 集計表の計算と出力 ---
    MIN_PER_HOP_MS = 0.5 # ユーザーオリジナルの補正値
    
    print("\n" + "="*50)
    print(" 📊 フェーズ別 ネットワーク品質評価 (VIDEO)")
    print("="*50)
    print(f"{'Phase (Routing)':<16} | {'Avg Delay':>10} | {'Jitter':>8} | {'Loss Rate':>9} | {'Recv/Sent'}")
    print("-" * 60)

    for phase_name, data in phase_stats.items():
        if data['recv'] == 0: continue
            
        # オフセット補正 (元のプログラムのロジックを踏襲)
        min_raw = min(data['raw_delays'])
        offset = (data['hops'] * MIN_PER_HOP_MS) - min_raw
        fixed_delays = [d + offset for d in data['raw_delays']]
        data['fixed_delays'] = fixed_delays # CDF用に追加
        
        # 指標の計算
        avg_delay = sum(fixed_delays) / len(fixed_delays)
        jitter = sum(abs(fixed_delays[i] - fixed_delays[i-1]) for i in range(1, len(fixed_delays))) / (len(fixed_delays) - 1) if len(fixed_delays) > 1 else 0
        loss_rate = (1 - data['recv'] / data['sent']) * 100 if data['sent'] > 0 else 0
        
        print(f"{phase_name:<16} | {avg_delay:7.2f} ms | {jitter:5.2f} ms | {loss_rate:6.2f} % | {data['recv']}/{data['sent']}")

    print("-" * 60 + "\n")

    # --- 2. 論文用 遅延CDFグラフの描画 ---
    plt.rcParams['pdf.fonttype'] = 42
    plt.rcParams['ps.fonttype'] = 42
    plt.rcParams['font.size'] = 14
    plt.rcParams['axes.linewidth'] = 1.2

    fig, ax = plt.subplots(figsize=(8, 5.5))

    has_data = False
    for phase_name, data in phase_stats.items():
        if 'fixed_delays' in data and len(data['fixed_delays']) > 0:
            has_data = True
            # CDFの計算 (外部ライブラリに依存しない安全な実装)
            sorted_delays = sorted(data['fixed_delays'])
            n = len(sorted_delays)
            # 縦軸(0.0 ~ 1.0)の割合を作成
            p = [i / (n - 1) if n > 1 else 1.0 for i in range(n)]
            
            # ホップ数を明記した凡例
            label = f"{phase_name} (n={n})"
            
            ax.plot(sorted_delays, p, label=label, 
                    color=data['color'], linestyle=data['ls'], linewidth=2.5, alpha=0.9)

    if not has_data:
        print("❌ 描画する遅延データがありません。")
        return

    ax.set_xlabel('End-to-End 遅延 (ms)', fontweight='bold')
    ax.set_ylabel('累積確率 (CDF)', fontweight='bold')
    ax.grid(True, linestyle='--', alpha=0.6)
    
    # 95パーセンタイル（品質保証の目安）に補助線を引くテクニック
    ax.axhline(y=0.95, color='gray', linestyle=':', alpha=0.8)
    ax.text(ax.get_xlim()[0], 0.96, ' 95th Percentile', color='gray', fontsize=12)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_ylim(0, 1.05) # 1.0に張り付く線を綺麗に見せるため少し余白を作る
    
    ax.legend(loc='lower right', frameon=True, edgecolor='black')

    plt.tight_layout()
    output_pdf = "delay_cdf_evaluation.pdf"
    plt.savefig(output_pdf, format='pdf', bbox_inches='tight')
    print(f"🎉 成功: CDFグラフを保存しました -> {output_pdf}")

if __name__ == "__main__":
    main()