import pandas as pd
import matplotlib.pyplot as plt
import japanize_matplotlib
import sys
from pathlib import Path

def plot_domestic_conference_topology(csv_file, output_pdf):
    df = pd.read_csv(csv_file)
    window_size = 5
    
    # 学会論文用: PDFフォント埋め込み設定と基本スタイル
    plt.rcParams['pdf.fonttype'] = 42
    plt.rcParams['ps.fonttype'] = 42
    plt.rcParams['font.size'] = 14
    plt.rcParams['axes.linewidth'] = 1.2
    
    fig, ax = plt.subplots(figsize=(10, 5.5))

    # CSVの正確な列名をピンポイントで指定
    video_segments = [
        {
            'col_name': 'CamN-CtlN(VIDEO_E2E)', 
            'label': 'CtlN-CamN (End-to-End)',     
            'color': '#2ca02c', 'ls': '-'
        },
        {
            'col_name': 'CamN->RN2(VIDEO)',  
            'label': 'RN2-CamN(2ホップ以上)',  
            'color': '#ff7f0e', 'ls': '--'
        },
        {
            'col_name': 'RN2->RN1(VIDEO)', 
            'label': 'RN1-RN2 (3ホップ)', 
            'color': '#1f77b4', 'ls': '-.'
        }
    ]

    for seg in video_segments:
        target_col = seg['col_name']
        
        # CSV内に指定した列が存在するかチェック
        if target_col in df.columns:
            smoothed = df[target_col].rolling(window=window_size, min_periods=1).mean()
            ax.plot(df['Time(s)'], smoothed, 
                    label=seg['label'], color=seg['color'], 
                    linestyle=seg['ls'], linewidth=2.5, alpha=0.85)
        else:
            print(f"⚠️ 警告: CSVに '{target_col}' 列が見つかりません。")

    ax.set_xlabel('経過時間 (s)', fontweight='bold', labelpad=10)
    ax.set_ylabel('映像スループット (Mbps)', fontweight='bold', labelpad=10)
    ax.grid(True, linestyle='--', alpha=0.6)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)

    ax.legend(loc='upper right', frameon=True, edgecolor='black')

    plt.tight_layout()
    plt.savefig(output_pdf, format='pdf', bbox_inches='tight')
    print(f"🎉 成功: PDFを保存しました -> {output_pdf}")

def main():
    if len(sys.argv) < 2: 
        print("Usage: python3 plot_video_graph.py <input_csv>")
        return
    csv_file = sys.argv[1]
    pdf_path = Path(csv_file).with_suffix('.pdf')
    plot_domestic_conference_topology(csv_file, pdf_path)

if __name__ == "__main__":
    main()