import argparse
import time
import polars as pl
from collectors.nvidia import NvidiaCollector
from collectors.no_gpu import NoGpuCollector

def run_profiler(duration_sec=5., interval_sec=0.5):
    # 本来はここでGPU検知。今回は暫定でNVIDIAを使用
    try:
        collector = NvidiaCollector()
    except Exception:
        collector = NoGpuCollector()

    raw_samples = []
    steps = int(duration_sec / interval_sec)
    
    print(f"Profiling for {duration_sec} seconds...")
    for _ in range(steps):
        raw_samples.append(collector.collect())
        time.sleep(interval_sec)
        
    # Polars DataFrame に一括変換
    df = pl.DataFrame(raw_samples)
    
    # 1. 欲しい統計量を計算（1行だけの DataFrame ができる）
    stats_df = df.select([
        pl.all().mean().name.suffix("_avg"),
        pl.all().max().name.suffix("_max")
    ])

    # 2. 扱いやすいように Python の辞書に変換
    # stats_df.to_dicts()[0] -> {"cpu_util_percent_avg": 12.5, "cpu_util_percent_max": 45.0, ...}
    stats_dict = stats_df.to_dicts()[0]

    # 3. プレフィックス（元の列名）ごとにまとめて綺麗に出力
    # 収集した元の列名の一覧をループ
    metrics_names = df.columns 

    print("\n--- Summary Results ---")
    for metric in metrics_names:
        avg_val = stats_dict[f"{metric}_avg"]
        max_val = stats_dict[f"{metric}_max"]
        
        # None（NoGpuでのGPUバインド等）の場合はスキップ、または N/A 表示にする
        if avg_val is None or max_val is None:
            continue
            
        # 見やすさのために、アンダーバーをスペースに置換するか、
        # 'cpu_util_percent' から 'cpu' のように扱いやすい名前にパース
        display_name = metric.replace("_percent", "").replace("_gb", "").replace("_mbps", "")
        
        print(f"{display_name}:")
        print(f"  - max: {max_val:.2f} %")
        print(f"  - ave: {avg_val:.2f} %")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", help="how many seconds run the profiler")
    args = parser.parse_args()

    run_profiler(float(args.s))
