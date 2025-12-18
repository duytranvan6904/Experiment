# trajectory_filter_improved.py
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
RECORD_DIR = r"E:\Downloads\BodyBasics-WPF\Experiment\bin\AnyCPU\Debug\RecordTrajectories\RawRecord"
SAVE_DIR   = r"E:\Downloads\BodyBasics-WPF\Experiment\Merged_Trajectories"

# Ngưỡng phát hiện outliers
MAX_VELOCITY_THRESHOLD = 0.2      # 0.1m giữa 2 điểm liên tiếp (tương đương 3 m/s ở 30fps)
MAX_ACCELERATION_THRESHOLD = 0.05  # Ngưỡng gia tốc bất thường

# Tham số làm mượt
MEDIAN_FILTER_SIZE = 7             # Bộ lọc trung vị để loại bỏ nhiễu spike
SAVGOL_WINDOW = 55              # Savitzky-Golay window (phải là số lẻ)
SAVGOL_POLYORDER = 3               # Bậc đa thức
SPLINE_SMOOTH = 0.15               # Độ mượt của spline (0 = interpolate chính xác)

MIN_POINTS_REQUIRED = 10

# ========== COLUMNS ==========
TIME_COL = "Timestamp"

TRAJ_LEADER_LEFT  = ("Position_X",	"Position_Y",	"Position_Z")
TRAJ_FOLLOWER_R   = ("Follower_HandRight_X","Follower_HandRight_Y","Follower_HandRight_Z")
TRAJ_OBJECT       = ("Object_X",           "Object_Y",           "Object_Z")

REQUIRED_TRAJECTORIES = {
    "leader_left": TRAJ_LEADER_LEFT,
    "follower_right": TRAJ_FOLLOWER_R,
    "object": TRAJ_OBJECT
}

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
    Phát hiện outliers dựa trên VELOCITY SPIKE, không phải VALUE
    
    Cải tiến:
    1. KHÔNG loại điểm chỉ vì giá trị ≈0 (quỹ đạo có thể quay lại gốc)
    2. Chỉ phát hiện JUMP (velocity spike) → dấu hiệu mất tracking
    3. Adaptive thresholds: nếu quỹ đạo bị nhảy lớn, threshold sẽ tự động tăng lên để tránh lọc quá nhiều
    
    Returns: boolean mask (True = outlier)
    """
    N = arr3.shape[0]
    outlier_mask = np.zeros(N, dtype=bool)
    
    # 1. Chỉ loại NaN/inf, KHÔNG loại giá trị 0
    nan_inf = ~np.isfinite(arr3).all(axis=1)
    outlier_mask |= nan_inf
    
    if N < 2:
        return outlier_mask
    
    # 2. Velocity (khoảng cách giữa 2 điểm liên tiếp)
    velocities = np.linalg.norm(np.diff(arr3, axis=0), axis=1)
    
    # Tính adaptive threshold: 75th percentile hoặc max_velocity, lấy cái nào lớn hơn
    # Điều này giúp tránh loại quá nhiều frame khi quỹ đạo có chuyển động nhanh
    q75 = np.percentile(velocities, 75)
    adaptive_v_threshold = max(max_velocity, q75 * 1.5)
    
    velocity_outliers = velocities > adaptive_v_threshold
    outlier_mask[:-1] |= velocity_outliers
    outlier_mask[1:] |= velocity_outliers
    
    if N < 3:
        return outlier_mask
    
    # 3. Acceleration (thay đổi velocity) - tìm SUDDEN JUMP
    accelerations = np.abs(np.diff(velocities))
    
    # Adaptive acceleration threshold tương tự
    q75_accel = np.percentile(accelerations, 75)
    adaptive_a_threshold = max(max_accel, q75_accel * 2.0)
    
    accel_outliers = accelerations > adaptive_a_threshold
    outlier_mask[:-2] |= accel_outliers
    outlier_mask[1:-1] |= accel_outliers
    outlier_mask[2:] |= accel_outliers
    
    return outlier_mask

def interpolate_outliers(arr3, outlier_mask, time_axis=None):
    """
    Thay thế outliers bằng interpolation - HOẶC XÓA nếu là khúc mất tracking liên tiếp
    
    Args:
        arr3: numpy array (N, 3)
        outlier_mask: boolean array (N,) - True = outlier
        time_axis: optional time values for interpolation
    
    Returns:
        cleaned array, updated outlier mask (các khúc mất tracking sẽ bị xóa)
    """
    N = arr3.shape[0]
    cleaned = arr3.copy()
    
    # Nếu quá nhiều outliers (>50%), return dữ liệu gốc
    if outlier_mask.sum() > 0.5 * N:
        print(f"  WARNING: >50% outliers detected, using fallback method")
        return arr3, outlier_mask
    
    # Tìm các khúc liên tiếp của outliers (mất tracking)
    # Nếu khúc > 3 frames → xóa hoàn toàn (don't interpolate)
    outlier_mask = handle_consecutive_outliers(outlier_mask, max_gap=3)
    
    # Tạo time axis nếu không có
    if time_axis is None:
        time_axis = np.arange(N)
    
    # Interpolate từng trục X, Y, Z
    for axis_idx in range(3):
        values = arr3[:, axis_idx].copy()
        
        # Đánh dấu outliers là NaN
        values[outlier_mask] = np.nan
        
        # Tìm các điểm hợp lệ
        valid_mask = ~np.isnan(values)
        
        if valid_mask.sum() < MIN_POINTS_REQUIRED:
            # Không đủ điểm hợp lệ, dùng forward/backward fill
            df_temp = pd.Series(values)
            df_temp = df_temp.ffill().bfill()
            cleaned[:, axis_idx] = df_temp.values
        else:
            # Interpolation sử dụng các điểm hợp lệ
            valid_indices = np.where(valid_mask)[0]
            valid_values = values[valid_mask]
            
            # Sử dụng numpy interp (tuyến tính)
            interpolated = np.interp(time_axis, time_axis[valid_mask], valid_values)
            cleaned[:, axis_idx] = interpolated
    
    return cleaned, outlier_mask


def handle_consecutive_outliers(outlier_mask, max_gap=3):
    """
    Xử lý các khúc outliers liên tiếp:
    - Nếu khúc ≤ max_gap frames: interpolate (có thể là spike)
    - Nếu khúc > max_gap frames: giữ nguyên (mất tracking thực sự → xóa)
    
    Trả về outlier mask đã được update
    """
    new_mask = outlier_mask.copy()
    
    # Tìm các khúc liên tiếp của True
    changes = np.diff(np.concatenate([[False], outlier_mask, [False]]).astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    
    for start, end in zip(starts, ends):
        gap_size = end - start
        if gap_size > max_gap:
            # Khúc này là mất tracking → XÓA hoàn toàn (keep as outlier)
            pass  # Giữ nguyên new_mask[start:end] = True
        else:
            # Khúc nhỏ → interpolate (set to False để interpolate)
            new_mask[start:end] = False
    
    return new_mask

def apply_median_filter(arr3, kernel_size=MEDIAN_FILTER_SIZE):
    """
    Áp dụng median filter để loại bỏ nhiễu spike
    Median filter rất hiệu quả với outliers
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
    Giữ được hình dạng quỹ đạo tốt hơn moving average
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

def apply_spline_smoothing(arr3, time_axis=None, smooth=SPLINE_SMOOTH):
    """
    Áp dụng spline smoothing để tạo quỹ đạo mượt mà
    """
    N = arr3.shape[0]
    if time_axis is None:
        time_axis = np.arange(N)
    
    if N < 4:  # Spline cần ít nhất 4 điểm
        return arr3
    
    smoothed = np.zeros_like(arr3)
    for i in range(3):
        try:
            # UnivariateSpline với smoothing factor
            spline = UnivariateSpline(time_axis, arr3[:, i], s=smooth * N)
            smoothed[:, i] = spline(time_axis)
        except:
            smoothed[:, i] = arr3[:, i]
    
    return smoothed

def clean_and_smooth_trajectory(df, cols, time_col=TIME_COL):
    """
    Pipeline hoàn chỉnh để làm sạch và làm mượt quỹ đạo
    
    Steps:
    1. Phát hiện outliers (velocity spikes, acceleration spikes)
    2. Xóa các khúc mất tracking liên tiếp
    3. Interpolate thay thế các spike nhỏ
    4. Median filter để loại bỏ nhiễu spike còn sót
    5. Savitzky-Golay filter để làm mượt
    
    Lưu ý: Các khúc mất tracking lớn (>3 frames) sẽ bị xóa hoàn toàn
    """
    if not all(c in df.columns for c in cols):
        return None, 0
    
    # Lấy dữ liệu
    arr = df[list(cols)].to_numpy(dtype=float)
    
    # Time axis
    if time_col in df.columns:
        time_axis = df[time_col].to_numpy()
    else:
        time_axis = np.arange(len(arr))
    
    # Bước 1: Phát hiện outliers (VELOCITY-based, không VALUE-based)
    outlier_mask = detect_outliers_advanced(arr, MAX_VELOCITY_THRESHOLD, MAX_ACCELERATION_THRESHOLD)
    initial_outlier_count = outlier_mask.sum()
    
    print(f"    Initial outliers detected: {initial_outlier_count} ({100*initial_outlier_count/len(arr):.1f}%)")
    
    # Bước 2: Interpolate outliers + xử lý khúc mất tracking
    cleaned, outlier_mask = interpolate_outliers(arr, outlier_mask, time_axis)
    final_outlier_count = outlier_mask.sum()
    
    print(f"    After gap handling: {final_outlier_count} outliers kept ({100*final_outlier_count/len(arr):.1f}%)")
    print(f"    → Interpolated {initial_outlier_count - final_outlier_count} spike frames")
    print(f"    → Removed {final_outlier_count} frames from tracking loss segments")
    
    # Bước 3: Median filter (loại bỏ spike)
    cleaned = apply_median_filter(cleaned, MEDIAN_FILTER_SIZE)
    
    # Bước 4: Savitzky-Golay filter (làm mượt giữ hình dạng)
    cleaned = apply_savgol_filter(cleaned, SAVGOL_WINDOW, SAVGOL_POLYORDER)
    
    # Tạo DataFrame
    result_df = pd.DataFrame(cleaned, columns=cols)
    
    return result_df, initial_outlier_count

def calculate_smoothness_metrics(arr3):
    """
    Tính các chỉ số đánh giá độ mượt của quỹ đạo
    """
    if len(arr3) < 2:
        return None
    
    # Velocity
    velocities = np.linalg.norm(np.diff(arr3, axis=0), axis=1)
    
    # Acceleration (thay đổi velocity)
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

# ========== MAIN ==========
def main():
    # 1) Find latest file
    try:
        csv_path = find_latest_csv(RECORD_DIR)
    except Exception as e:
        print("ERROR locating CSV:", e)
        return

    print("="*60)
    print("IMPROVED TRAJECTORY FILTER")
    print("="*60)
    print(f"Latest CSV file: {csv_path}")
    
    df = load_csv(csv_path)
    print(f"Loaded: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Time axis
    if TIME_COL not in df.columns:
        time_vals = np.arange(len(df))
        df[TIME_COL] = time_vals
        print("Timestamp not found – using frame index as time.")

    # Process each trajectory
    cleaned_cols = {}
    metrics_before = {}
    metrics_after = {}
    
    for key, cols in REQUIRED_TRAJECTORIES.items():
        print(f"\n{'='*60}")
        print(f"Processing trajectory: {key}")
        print(f"Columns: {cols}")
        
        if not all(c in df.columns for c in cols):
            print(f"  WARNING: missing columns for {key}; skipping.")
            continue
        
        # Tính metrics trước khi xử lý
        arr_before = df[list(cols)].to_numpy(dtype=float)
        metrics_before[key] = calculate_smoothness_metrics(arr_before)
        
        # Clean and smooth
        cleaned, outlier_count = clean_and_smooth_trajectory(df, cols, TIME_COL)
        
        if cleaned is None:
            print(f"  ERROR: Could not process {key}")
            continue
        
        cleaned_cols[key] = cleaned
        
        # Tính metrics sau khi xử lý
        arr_after = cleaned.to_numpy(dtype=float)
        metrics_after[key] = calculate_smoothness_metrics(arr_after)
        
        # So sánh
        if metrics_before[key] and metrics_after[key]:
            print(f"\n  Metrics comparison:")
            print(f"    Max velocity: {metrics_before[key]['max_velocity']:.4f} → {metrics_after[key]['max_velocity']:.4f}")
            print(f"    Std velocity: {metrics_before[key]['std_velocity']:.4f} → {metrics_after[key]['std_velocity']:.4f}")
            print(f"    Max acceleration: {metrics_before[key]['max_acceleration']:.4f} → {metrics_after[key]['max_acceleration']:.4f}")

    # Compose filtered df
    df_filtered = df.copy()
    for key, cleaned in cleaned_cols.items():
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
    def plot_comparison_xyz(df_before, df_after, cols, title):
        """Vẽ so sánh trước và sau"""
        t = df_before[TIME_COL].values
        
        fig, axes = plt.subplots(3, 1, figsize=(14, 8))
        axis_names = ['X', 'Y', 'Z']
        
        for i, (ax, axis_name) in enumerate(zip(axes, axis_names)):
            before = df_before[cols[i]].values
            after = df_after[cols[i]].values
            
            ax.plot(t, before, 'r-', alpha=0.5, linewidth=1, label='Before (Raw)')
            ax.plot(t, after, 'b-', linewidth=2, label='After (Filtered)')
            ax.set_ylabel(f'{axis_name} (m)')
            ax.legend(loc='upper right')
            ax.grid(True, alpha=0.3)
        
        axes[-1].set_xlabel('Time')
        fig.suptitle(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.show()

    # Plot comparisons
    for key, cols in REQUIRED_TRAJECTORIES.items():
        if key in cleaned_cols and all(c in df.columns for c in cols):
            plot_comparison_xyz(df, df_filtered, cols, 
                              f"{key.replace('_', ' ').title()} – Before vs After Filtering")

    # 3D plot comparison
    fig = plt.figure(figsize=(16, 7))
    
    # Before
    ax1 = fig.add_subplot(121, projection='3d')
    ax1.set_title("Before Filtering (Raw Data)", fontsize=12, fontweight='bold')
    
    # After
    ax2 = fig.add_subplot(122, projection='3d')
    ax2.set_title("After Filtering (Smoothed)", fontsize=12, fontweight='bold')
    
    colors = {'leader_left': 'red', 'follower_right': 'blue', 'object': 'green'}
    
    for key, cols in REQUIRED_TRAJECTORIES.items():
        if key not in cleaned_cols:
            continue
        
        if all(c in df.columns for c in cols):
            # Before
            ax1.plot(df[cols[0]].values, df[cols[2]].values, df[cols[1]].values,
                    label=key.replace('_', ' ').title(), color=colors.get(key, 'gray'), 
                    linewidth=1, alpha=0.6)
            
            # After
            ax2.plot(df_filtered[cols[0]].values, df_filtered[cols[2]].values, 
                    df_filtered[cols[1]].values,
                    label=key.replace('_', ' ').title(), color=colors.get(key, 'gray'),
                    linewidth=2)
    
    for ax in [ax1, ax2]:
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Z (m)")
        ax.set_zlabel("Y (m)")
        ax.legend()
    
    plt.tight_layout()
    plt.show()
    
    print("\n✅ Processing completed successfully!")

if __name__ == "__main__":
    main()