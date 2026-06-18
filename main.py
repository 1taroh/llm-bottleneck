import argparse
import time
import polars as pl
from collectors.nvidia import NvidiaCollector
from collectors.intel import IntelVulkanCollector
from collectors.no_gpu import NoGpuCollector

def run_profiler(duration_sec=5., interval_sec=0.5, gpu_index=0):
# 試行したいコレクターを優先度順に並べる
    collector_classes = [
        NvidiaCollector,
        IntelVulkanCollector,
        NoGpuCollector  # 最終フォールバック
    ]
    init_args = {
        NvidiaCollector: {'gpu_index': gpu_index}
    }
    collector = None
    
    # 成功するまで順番に try を繰り返す
    for CollectorClass in collector_classes:
        try:
            args = init_args.get(CollectorClass, {})
            collector = CollectorClass(**args)
            print(f"Successfully initialized: {CollectorClass.__name__}")
            break  # 初期化に成功したらループを抜ける
        except Exception as e:
            print(f"Failed to initialize {CollectorClass.__name__}: {e}")
            continue

    # 万が一、すべてのコレクターが失敗した場合のセーフティ
    if collector is None:
        raise RuntimeError("すべてのコレクターの初期化に失敗しました。")

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
            
        print(metric)
        if "percent" in metric:
            unit = "%"
        elif "gb" in metric:
            unit = "GB"
        elif "mbps" in metric:
            unit = "Mbps"
        else:
            unit = ""
        # 'cpu_util_percent' から 'cpu' のように扱いやすい名前にパース
        display_name = metric.replace("_percent", "").replace("_gb", "").replace("_mbps", "")
        
        print(f"{display_name}:")
        print(f"  - max: {max_val:.2f} {unit}")
        print(f"  - ave: {avg_val:.2f} {unit}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", help="how many seconds run the profiler", default="10")
    parser.add_argument("--gpu_index", help="how many seconds run the profiler", default="0")
    args = parser.parse_args()

    run_profiler(float(args.s), gpu_index=int( args.gpu_index))
