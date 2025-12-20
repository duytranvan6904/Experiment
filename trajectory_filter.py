# trajectory_filter.py
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter, medfilt
from scipy.interpolate import UnivariateSpline
import sys
import re

# Ensure utf-8 output
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ========== PARAMETERS ==========
RECORD_DIR = r"C:\Users\ASUS\OneDrive\Tài liệu\KinectTrajectories"
SAVE_DIR   = r"C:\Users\ASUS\OneDrive\Tài liệu\KinectTrajectories\filtered"

# Ngưỡng phát hiện outliers
MAX_VELOCITY_THRESHOLD = 0.2      # 0.2m giữa 2 điểm liên tiếp
MAX_ACCELERATION_THRESHOLD = 0.05  # Ngưỡng gia tốc bất thường

# Tham số làm mượt
MEDIAN_FILTER_SIZE = 7             # Bộ lọc trung vị để loại bỏ nhiễu spike
SAVGOL_WINDOW = 5                  # Savitzky-Golay window (phải là số lẻ)
SAVGOL_POLYORDER = 3               # Bậc đa thức
SPLINE_SMOOTH = 0.05               # Độ mượt của spline

MIN_POINTS_REQUIRED = 10

# ========== COLUMNS ==========
TIME_COL = "timestamp"
X_COL = "x"
Y_COL = "y"
Z_COL = "z"

# ========== HELPERS ==========
def find_latest_csv(folder):
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Record folder not found: {folder}")
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".csv")]
    if not files:
        raise FileNotFoundError(f"No CSV files found in: {folder}")
    newest = max(files, key=os.path.getmtime)
    return newest

def load_csv(path):
    return pd.read_csv(path)

def detect_outliers_advanced(arr3, max_velocity=MAX_VELOCITY_THRESHOLD, max_accel=MAX_ACCELERATION_THRESHOLD):
    """
    Phát hiện outliers dựa trên VELOCITY SPIKE
    Returns: boolean mask (True = outlier)
    """
    N = arr3.shape[0]
    outlier_mask = np.zeros(N, dtype=bool)
    
    # 1. Loại NaN/inf
    nan_inf = ~np.isfinite(arr3).all(axis=1)
    outlier_mask |= nan_inf
    
    if N < 2:
        return outlier_mask
    
    # 2. Velocity (khoảng cách giữa 2 điểm liên tiếp)
    velocities = np.linalg.norm(np.diff(arr3, axis=0), axis=1)
    
    # Adaptive threshold
    q75 = np.percentile(velocities, 75)
    adaptive_v_threshold = max(max_velocity, q75 * 1.5)
    
    velocity_outliers = velocities > adaptive_v_threshold
    outlier_mask[:-1] |= velocity_outliers
    outlier_mask[1:] |= velocity_outliers
    
    if N < 3:
        return outlier_mask
    
    # 3. Acceleration
    accelerations = np.abs(np.diff(velocities))
    
    q75_accel = np.percentile(accelerations, 75)
    adaptive_a_threshold = max(max_accel, q75_accel * 2.0)
    
    accel_outliers = accelerations > adaptive_a_threshold
    outlier_mask[:-2] |= accel_outliers
    outlier_mask[1:-1] |= accel_outliers
    outlier_mask[2:] |= accel_outliers
    
    return outlier_mask

def interpolate_outliers(arr3, outlier_mask, time_axis=None):
    """
    Thay thế outliers bằng interpolation
    """
    N = arr3.shape[0]
    cleaned = arr3.copy()
    
    if outlier_mask.sum() > 0.5 * N:
        print(f"  WARNING: >50% outliers detected, using fallback method")
        return arr3, outlier_mask
    
    outlier_mask = handle_consecutive_outliers(outlier_mask, max_gap=3)
    
    if time_axis is None:
        time_axis = np.arange(N)
    
    for axis_idx in range(3):
        values = arr3[:, axis_idx].copy()
        values[outlier_mask] = np.nan
        valid_mask = ~np.isnan(values)
        
        if valid_mask.sum() < MIN_POINTS_REQUIRED:
            df_temp = pd.Series(values)
            df_temp = df_temp.ffill().bfill()
            cleaned[:, axis_idx] = df_temp.values
        else:
            valid_indices = np.where(valid_mask)[0]
            valid_values = values[valid_mask]
            interpolated = np.interp(time_axis, time_axis[valid_mask], valid_values)
            cleaned[:, axis_idx] = interpolated
    
    return cleaned, outlier_mask

def handle_consecutive_outliers(outlier_mask, max_gap=3):
    """
    Xử lý các khúc outliers liên tiếp
    """
    new_mask = outlier_mask.copy()
    
    changes = np.diff(np.concatenate([[False], outlier_mask, [False]]).astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    
    for start, end in zip(starts, ends):
        gap_size = end - start
        if gap_size <= max_gap:
            new_mask[start:end] = False
    
    return new_mask

def apply_median_filter(arr3, kernel_size=MEDIAN_FILTER_SIZE):
    """
    Áp dụng median filter để loại bỏ nhiễu spike
    """
    if arr3.shape[0] < kernel_size:
        return arr3
    
    filtered = np.zeros_like(arr3)
    for i in range(3):
        filtered[:, i] = medfilt(arr3[:, i], kernel_size=kernel_size)
    
    return filtered

def apply_savgol_filter(arr3, window=SAVGOL_WINDOW, polyorder=SAVGOL_POLYORDER):
    """
    Áp dụng Savitzky-Golay filter để làm mượt
    """
    if arr3.shape[0] < window:
        window = arr3.shape[0] if arr3.shape[0] % 2 == 1 else arr3.shape[0] - 1
        if window < polyorder + 2:
            return arr3
    
    filtered = np.zeros_like(arr3)
    for i in range(3):
        try:
            filtered[:, i] = savgol_filter(arr3[:, i], window, polyorder)
        except:
            filtered[:, i] = arr3[:, i]
    
    return filtered

def clean_and_smooth_trajectory(df, cols, time_col=TIME_COL):
    """
    Pipeline hoàn chỉnh để làm sạch và làm mượt quỹ đạo
    """
    if not all(c in df.columns for c in cols):
        return None, 0
    
    arr = df[list(cols)].to_numpy(dtype=float)
    
    if time_col in df.columns:
        time_axis = df[time_col].to_numpy()
    else:
        time_axis = np.arange(len(arr))
    
    # Phát hiện outliers
    outlier_mask = detect_outliers_advanced(arr, MAX_VELOCITY_THRESHOLD, MAX_ACCELERATION_THRESHOLD)
    initial_outlier_count = outlier_mask.sum()
    
    print(f"    Initial outliers detected: {initial_outlier_count} ({100*initial_outlier_count/len(arr):.1f}%)")
    
    # Interpolate outliers
    cleaned, outlier_mask = interpolate_outliers(arr, outlier_mask, time_axis)
    final_outlier_count = outlier_mask.sum()
    
    print(f"    After gap handling: {final_outlier_count} outliers kept ({100*final_outlier_count/len(arr):.1f}%)")
    print(f"    → Interpolated {initial_outlier_count - final_outlier_count} spike frames")
    print(f"    → Removed {final_outlier_count} frames from tracking loss segments")
    
    # Median filter
    cleaned = apply_median_filter(cleaned, MEDIAN_FILTER_SIZE)
    
    # Savitzky-Golay filter
    cleaned = apply_savgol_filter(cleaned, SAVGOL_WINDOW, SAVGOL_POLYORDER)
    
    result_df = pd.DataFrame(cleaned, columns=cols)
    
    return result_df, initial_outlier_count

def calculate_smoothness_metrics(arr3):
    """
    Tính các chỉ số đánh giá độ mượt của quỹ đạo
    """
    if len(arr3) < 2:
        return None
    
    velocities = np.linalg.norm(np.diff(arr3, axis=0), axis=1)
    
    if len(velocities) > 1:
        accelerations = np.diff(velocities)
    else:
        accelerations = np.array([0])
    
    metrics = {
        'max_velocity': np.max(velocities),
        'mean_velocity': np.mean(velocities),
        'std_velocity': np.std(velocities),
        'max_acceleration': np.max(np.abs(accelerations)),
        'mean_acceleration': np.mean(np.abs(accelerations)),
    }
    
    return metrics

def set_axes_equal(ax):
    """
    Đặt tỉ lệ các trục bằng nhau cho biểu đồ 3D
    """
    x_limits = ax.get_xlim3d()
    y_limits = ax.get_ylim3d()
    z_limits = ax.get_zlim3d()

    x_range = abs(x_limits[1] - x_limits[0])
    x_middle = np.mean(x_limits)
    y_range = abs(y_limits[1] - y_limits[0])
    y_middle = np.mean(y_limits)
    z_range = abs(z_limits[1] - z_limits[0])
    z_middle = np.mean(z_limits)

    plot_radius = 0.5 * max([x_range, y_range, z_range])

    ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
    ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
    ax.set_zlim3d([z_middle - plot_radius, z_middle + plot_radius])

# ========== MAIN FUNCTIONS ==========

def visualize_raw_trajectory():
    """
    Hàm 1: Chỉ vẽ quỹ đạo raw thu được
    - Vẽ x, y, z theo thời gian (3 subplot riêng biệt)
    - Vẽ không gian 3D với tỉ lệ đúng
    """
    try:
        csv_path = find_latest_csv(RECORD_DIR)
    except Exception as e:
        print("ERROR locating CSV:", e)
        return

    print("="*60)
    print("RAW TRAJECTORY VISUALIZATION")
    print("="*60)
    print(f"Latest CSV file: {csv_path}")
    
    df = load_csv(csv_path)
    print(f"Loaded: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Kiểm tra các cột cần thiết
    cols = [X_COL, Y_COL, Z_COL]
    if not all(c in df.columns for c in cols):
        print(f"ERROR: Missing required columns {cols}")
        print(f"Available columns: {df.columns.tolist()}")
        return
    
    # Time axis
    if TIME_COL in df.columns:
        time_vals = df[TIME_COL].values
    else:
        time_vals = np.arange(len(df))
        print("Timestamp not found – using frame index as time.")
    
    # Vẽ x, y, z theo thời gian
    fig, axes = plt.subplots(3, 1, figsize=(14, 8))
    axis_names = ['X', 'Y', 'Z']
    
    for i, (ax, axis_name, col) in enumerate(zip(axes, axis_names, cols)):
        values = df[col].values
        ax.plot(time_vals, values, 'b-', linewidth=1.5)
        ax.set_ylabel(f'{axis_name} (m)', fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_title(f'{axis_name} Position over Time', fontsize=11, fontweight='bold')
    
    axes[-1].set_xlabel('Time', fontsize=11)
    fig.suptitle('Raw Trajectory - Time Series', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.show()
    
    # Vẽ không gian 3D với tỉ lệ đúng
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    x_vals = df[X_COL].values
    y_vals = df[Y_COL].values
    z_vals = df[Z_COL].values
    
    ax.plot(x_vals, y_vals, z_vals, 'b-', linewidth=2, label='Raw Trajectory')
    ax.scatter(x_vals[0], y_vals[0], z_vals[0], c='green', s=100, marker='o', label='Start')
    ax.scatter(x_vals[-1], y_vals[-1], z_vals[-1], c='red', s=100, marker='x', label='End')
    
    ax.set_xlabel('X (m)', fontsize=11)
    ax.set_ylabel('Y (m)', fontsize=11)
    ax.set_zlabel('Z (m)', fontsize=11)
    ax.set_title('Raw Trajectory - 3D Space (Equal Aspect Ratio)', fontsize=12, fontweight='bold')
    ax.legend()
    
    # Đặt tỉ lệ các trục bằng nhau
    set_axes_equal(ax)
    
    plt.tight_layout()
    plt.show()
    
    print("\n✅ Raw trajectory visualization completed!")

def apply_filter_and_visualize():
    """
    Hàm 2: Áp dụng filter, xuất file đã filtered, và vẽ trực quan
    - Áp dụng filter có trong code
    - Xuất file đã filtered vào đường dẫn đã set
    - Vẽ trực quan quỹ đạo (x, y, z theo thời gian và không gian 3D)
    - Không lưu ảnh
    """
    try:
        csv_path = find_latest_csv(RECORD_DIR)
    except Exception as e:
        print("ERROR locating CSV:", e)
        return

    print("="*60)
    print("TRAJECTORY FILTER AND VISUALIZATION")
    print("="*60)
    print(f"Latest CSV file: {csv_path}")
    
    df = load_csv(csv_path)
    print(f"Loaded: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Kiểm tra các cột cần thiết
    cols = [X_COL, Y_COL, Z_COL]
    if not all(c in df.columns for c in cols):
        print(f"ERROR: Missing required columns {cols}")
        print(f"Available columns: {df.columns.tolist()}")
        return
    
    # Time axis
    if TIME_COL not in df.columns:
        time_vals = np.arange(len(df))
        df[TIME_COL] = time_vals
        print("Timestamp not found – using frame index as time.")
    
    # Tính metrics trước khi xử lý
    arr_before = df[cols].to_numpy(dtype=float)
    metrics_before = calculate_smoothness_metrics(arr_before)
    
    print(f"\n{'='*60}")
    print(f"Processing trajectory")
    print(f"Columns: {cols}")
    
    # Clean and smooth
    cleaned, outlier_count = clean_and_smooth_trajectory(df, cols, TIME_COL)
    
    if cleaned is None:
        print(f"ERROR: Could not process trajectory")
        return
    
    # Tính metrics sau khi xử lý
    arr_after = cleaned.to_numpy(dtype=float)
    metrics_after = calculate_smoothness_metrics(arr_after)
    
    # So sánh
    if metrics_before and metrics_after:
        print(f"\n  Metrics comparison:")
        print(f"    Max velocity: {metrics_before['max_velocity']:.4f} → {metrics_after['max_velocity']:.4f}")
        print(f"    Std velocity: {metrics_before['std_velocity']:.4f} → {metrics_after['std_velocity']:.4f}")
        print(f"    Max acceleration: {metrics_before['max_acceleration']:.4f} → {metrics_after['max_acceleration']:.4f}")
    
    # Compose filtered df
    df_filtered = df.copy()
    for col in cleaned.columns:
        df_filtered[col] = cleaned[col].values
    
    # Save
    base_name = os.path.basename(csv_path)
    safe_base = re.sub(r'[<>:"/\\|?*]', '_', base_name)
    out_name = f"filtered_{safe_base}"
    os.makedirs(SAVE_DIR, exist_ok=True)
    out_path = os.path.join(SAVE_DIR, out_name)
    
    try:
        df_filtered.to_csv(out_path, index=False)
        print(f"\n{'='*60}")
        print(f"Filtered file saved to: {out_path}")
        print("="*60)
    except PermissionError:
        print("\n❌ PermissionError: Cannot write file.")
        print("Please close all apps reading/writing the file and try again.")
        return
    
    # Visualization - Before vs After comparison
    time_vals = df[TIME_COL].values
    
    # Vẽ so sánh x, y, z theo thời gian
    fig, axes = plt.subplots(3, 1, figsize=(14, 8))
    axis_names = ['X', 'Y', 'Z']
    
    for i, (ax, axis_name, col) in enumerate(zip(axes, axis_names, cols)):
        before = df[col].values
        after = df_filtered[col].values
        
        ax.plot(time_vals, before, 'r-', alpha=0.5, linewidth=1, label='Before (Raw)')
        ax.plot(time_vals, after, 'b-', linewidth=2, label='After (Filtered)')
        ax.set_ylabel(f'{axis_name} (m)', fontsize=11)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.set_title(f'{axis_name} Position - Before vs After', fontsize=11, fontweight='bold')
    
    axes[-1].set_xlabel('Time', fontsize=11)
    fig.suptitle('Trajectory Filtering - Time Series Comparison', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.show()
    
    # 3D plot comparison với tỉ lệ đúng
    fig = plt.figure(figsize=(16, 7))
    
    # Before
    ax1 = fig.add_subplot(121, projection='3d')
    ax1.set_title("Before Filtering (Raw Data)", fontsize=12, fontweight='bold')
    
    x_before = df[X_COL].values
    y_before = df[Y_COL].values
    z_before = df[Z_COL].values
    
    ax1.plot(x_before, y_before, z_before, 'r-', linewidth=1.5, alpha=0.6, label='Raw')
    ax1.scatter(x_before[0], y_before[0], z_before[0], c='green', s=100, marker='o', label='Start')
    ax1.scatter(x_before[-1], y_before[-1], z_before[-1], c='red', s=100, marker='x', label='End')
    
    ax1.set_xlabel("X (m)", fontsize=10)
    ax1.set_ylabel("Y (m)", fontsize=10)
    ax1.set_zlabel("Z (m)", fontsize=10)
    ax1.legend()
    set_axes_equal(ax1)
    
    # After
    ax2 = fig.add_subplot(122, projection='3d')
    ax2.set_title("After Filtering (Smoothed)", fontsize=12, fontweight='bold')
    
    x_after = df_filtered[X_COL].values
    y_after = df_filtered[Y_COL].values
    z_after = df_filtered[Z_COL].values
    
    ax2.plot(x_after, y_after, z_after, 'b-', linewidth=2, label='Filtered')
    ax2.scatter(x_after[0], y_after[0], z_after[0], c='green', s=100, marker='o', label='Start')
    ax2.scatter(x_after[-1], y_after[-1], z_after[-1], c='red', s=100, marker='x', label='End')
    
    ax2.set_xlabel("X (m)", fontsize=10)
    ax2.set_ylabel("Y (m)", fontsize=10)
    ax2.set_zlabel("Z (m)", fontsize=10)
    ax2.legend()
    set_axes_equal(ax2)
    
    plt.tight_layout()
    plt.show()
    
    print("\n✅ Processing completed successfully!")

# ========== MAIN ==========
def main():
    """
    Hàm main - Chọn một trong hai hàm để chạy:
    1. visualize_raw_trajectory() - Chỉ vẽ quỹ đạo raw
    2. apply_filter_and_visualize() - Áp dụng filter và vẽ so sánh
    """
    
    # Chọn hàm muốn chạy (comment/uncomment dòng tương ứng)
    
    # Hàm 1: Chỉ vẽ quỹ đạo raw
    visualize_raw_trajectory()
    
    # Hàm 2: Áp dụng filter và vẽ so sánh
    # apply_filter_and_visualize()

if __name__ == "__main__":
    main()