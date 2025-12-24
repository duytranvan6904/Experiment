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
# Lấy đường dẫn thư mục hiện tại (nơi file Python đang chạy)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORD_DIR = os.path.join(SCRIPT_DIR, "Trajectories")
SAVE_DIR   = os.path.join(SCRIPT_DIR, "Trajectories", "filtered")

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
TIME_COL = "Timestamp" # Updated to match C# output

# Mapping: Script Axis (X,Y,Z) -> CSV Column
# Note: Previous script mapped Script Y -> CSV Z, Script Z -> CSV Y. Preserving this swap.
# Leader
L_X_COL = "Leader_X"
L_Y_COL = "Leader_Z" # Swapped
L_Z_COL = "Leader_Y" # Swapped

# Follower
F_X_COL = "Follower_X"
F_Y_COL = "Follower_Z" # Swapped
F_Z_COL = "Follower_Y" # Swapped

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
    if len(velocities) > 0:
        q75 = np.percentile(velocities, 75)
        adaptive_v_threshold = max(max_velocity, q75 * 1.5)
        
        velocity_outliers = velocities > adaptive_v_threshold
        outlier_mask[:-1] |= velocity_outliers
        outlier_mask[1:] |= velocity_outliers
    
    if N < 3:
        return outlier_mask
    
    # 3. Acceleration
    if len(velocities) > 1:
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

def clean_and_smooth_trajectory(df, cols, label="Trajectory", time_col=TIME_COL):
    """
    Pipeline hoàn chỉnh để làm sạch và làm mượt quỹ đạo
    """
    print(f"Processing {label}...")
    if not all(c in df.columns for c in cols):
        print(f"  ERROR: Missing columns: {cols}")
        print(f"  Available: {df.columns.tolist()}")
        return None, 0
    
    arr = df[list(cols)].to_numpy(dtype=float)
    
    # Check if mostly zeros (untracked)
    if np.all(arr == 0):
        print(f"  WARNING: {label} contains all zeros (likely untracked). Skipping.")
        # Return zeros
        return pd.DataFrame(arr, columns=cols), 0

    # Sử dụng index số thay vì timestamp string để tránh lỗi interpolation
    time_axis = np.arange(len(arr))
    
    # Phát hiện outliers
    outlier_mask = detect_outliers_advanced(arr, MAX_VELOCITY_THRESHOLD, MAX_ACCELERATION_THRESHOLD)
    initial_outlier_count = outlier_mask.sum()
    
    print(f"    Initial outliers detected: {initial_outlier_count} ({100*initial_outlier_count/len(arr):.1f}%)")
    
    # Interpolate outliers
    cleaned, outlier_mask = interpolate_outliers(arr, outlier_mask, time_axis)
    final_outlier_count = outlier_mask.sum()
    
    print(f"    After gap handling: {final_outlier_count} outliers kept")
    
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
        # Avoid division by zero warnings if constant
        accelerations = np.diff(velocities)
    else:
        accelerations = np.array([0])
    
    metrics = {
        'max_velocity': np.max(velocities) if len(velocities) > 0 else 0,
        'mean_velocity': np.mean(velocities) if len(velocities) > 0 else 0,
        'std_velocity': np.std(velocities) if len(velocities) > 0 else 0,
        'max_acceleration': np.max(np.abs(accelerations)) if len(accelerations) > 0 else 0,
        'mean_acceleration': np.mean(np.abs(accelerations)) if len(accelerations) > 0 else 0,
    }
    
    return metrics

def set_axes_equal(ax, z_min_limit=-0.01):
    """
    Đặt tỉ lệ các trục bằng nhau cho biểu đồ 3D
    """
    try:
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
        if plot_radius == 0: plot_radius = 1.0

        ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
        ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
        
        z_lower = max(z_middle - plot_radius, z_min_limit)
        ax.set_zlim3d([z_lower, z_middle + plot_radius])
    except Exception:
        pass

# ========== MAIN FUNCTIONS ==========

def visualize_raw_trajectory():
    """
    Vẽ 2 quỹ đạo Leader và Follower (Raw)
    """
    try:
        csv_path = find_latest_csv(RECORD_DIR)
    except Exception as e:
        print("ERROR locating CSV:", e)
        return

    print("="*60)
    print("RAW TRAJECTORY VISUALIZATION (LEADER & FOLLOWER)")
    print("="*60)
    print(f"Latest CSV file: {csv_path}")
    
    df = load_csv(csv_path)
    print(f"Loaded: {df.shape[0]} rows")
    
    # Check columns
    l_cols = [L_X_COL, L_Y_COL, L_Z_COL]
    f_cols = [F_X_COL, F_Y_COL, F_Z_COL]
    
    has_leader = all(c in df.columns for c in l_cols)
    has_follower = all(c in df.columns for c in f_cols)
    
    if not has_leader and not has_follower:
        print("ERROR: CSV does not contain expected Leader or Follower columns.")
        return

    # 3D plot
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # Draw Leader
    if has_leader:
        x = df[L_X_COL].values
        y = df[L_Y_COL].values
        z = df[L_Z_COL].values
        if not np.all(x==0):
            ax.plot(x, y, z, 'b-', linewidth=2, label='Leader (Raw)')
            ax.scatter(x[0], y[0], z[0], c='cyan', s=50, marker='o')
    
    # Draw Follower
    if has_follower:
        x = df[F_X_COL].values
        y = df[F_Y_COL].values
        z = df[F_Z_COL].values
        if not np.all(x==0):
            ax.plot(x, y, z, 'r-', linewidth=2, label='Follower (Raw)')
            ax.scatter(x[0], y[0], z[0], c='orange', s=50, marker='o')
    
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m) [Was Z]')
    ax.set_zlabel('Z (m) [Was Y]')
    ax.set_title('Raw Trajectories - 3D Space')
    ax.legend()
    set_axes_equal(ax)
    
    plt.tight_layout()
    plt.show()

def apply_filter_and_visualize():
    """
    Áp dụng filter cho cả 2 quỹ đạo và vẽ so sánh
    """
    try:
        csv_path = find_latest_csv(RECORD_DIR)
    except Exception as e:
        print("ERROR locating CSV:", e)
        return

    print("="*60)
    print("TRAJECTORY FILTER AND VISUALIZATION (DUAL)")
    print("="*60)
    print(f"Latest CSV file: {csv_path}")
    
    df = load_csv(csv_path)
    
    # Ensure sequential timestamp for continuity
    df[TIME_COL] = np.arange(len(df))
    
    l_cols = [L_X_COL, L_Y_COL, L_Z_COL]
    f_cols = [F_X_COL, F_Y_COL, F_Z_COL]
    
    # Process Leader
    l_cleaned, l_outliers = clean_and_smooth_trajectory(df, l_cols, "Leader")
    # Process Follower
    f_cleaned, f_outliers = clean_and_smooth_trajectory(df, f_cols, "Follower")
    
    # Combine results
    df_filtered = df.copy()
    if l_cleaned is not None:
        for col in l_cleaned.columns: df_filtered[col] = l_cleaned[col].values
    if f_cleaned is not None:
        for col in f_cleaned.columns: df_filtered[col] = f_cleaned[col].values

    # Normalize Z (height) -> optional? User script did this.
    # Let's normalize based on min Z of Leader (or absolute 0 if data allows)
    # User script: df_filtered[Z_COL] = df_filtered[Z_COL] - z_min
    # We should probably do this per person or keep absolute?
    # Retaining absolute is safer for interaction analysis. 
    # But for graph readability, maybe normalize. 
    # I'll normalize each individually to logical floor if needed, but for now let's just shift so min is 0?
    # Actually, Kinect coords are relative to camera. Floor is usually around Y = -1.2m (if camera is at 1.2m).
    # Since we swapped Z->Y (Height), let's just leave it absolute or shift if it's way off.
    # The previous script did `z - z_min`. I will do that for each person.
    
    if l_cleaned is not None and not np.all(df_filtered[L_Z_COL] == 0):
        z_min = df_filtered[L_Z_COL].min()
        df_filtered[L_Z_COL] -= z_min
        print(f"  Leader Z normalized by subtracting {z_min:.3f}")
        
    if f_cleaned is not None and not np.all(df_filtered[F_Z_COL] == 0):
        z_min = df_filtered[F_Z_COL].min()
        df_filtered[F_Z_COL] -= z_min
        print(f"  Follower Z normalized by subtracting {z_min:.3f}")

    # Save
    base_name = os.path.basename(csv_path)
    safe_base = re.sub(r'[<>:"/\\|?*]', '_', base_name)
    out_name = f"filtered_dual_{safe_base}"
    os.makedirs(SAVE_DIR, exist_ok=True)
    out_path = os.path.join(SAVE_DIR, out_name)
    try:
        df_filtered.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")
    except:
        pass

    # 3D Comparison Plot (Filtered)
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    # Plot Leader
    if l_cleaned is not None and not np.all(df_filtered[L_X_COL]==0):
        ax.plot(df_filtered[L_X_COL], df_filtered[L_Y_COL], df_filtered[L_Z_COL], 'b-', linewidth=2, label='Leader (Filtered)')
        # Start/End
        ax.scatter(df_filtered[L_X_COL].iloc[0], df_filtered[L_Y_COL].iloc[0], df_filtered[L_Z_COL].iloc[0], c='cyan', s=60)
        ax.scatter(df_filtered[L_X_COL].iloc[-1], df_filtered[L_Y_COL].iloc[-1], df_filtered[L_Z_COL].iloc[-1], c='blue', marker='x', s=60)

    # Plot Follower
    if f_cleaned is not None and not np.all(df_filtered[F_X_COL]==0):
        ax.plot(df_filtered[F_X_COL], df_filtered[F_Y_COL], df_filtered[F_Z_COL], 'r-', linewidth=2, label='Follower (Filtered)')
        # Start/End
        ax.scatter(df_filtered[F_X_COL].iloc[0], df_filtered[F_Y_COL].iloc[0], df_filtered[F_Z_COL].iloc[0], c='orange', s=60)
        ax.scatter(df_filtered[F_X_COL].iloc[-1], df_filtered[F_Y_COL].iloc[-1], df_filtered[F_Z_COL].iloc[-1], c='red', marker='x', s=60)

    ax.set_title(f"Filtered Trajectories\nLeader (Blue) vs Follower (Red)", fontsize=14)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m) [Depth]")
    ax.set_zlabel("Z (m) [Height]")
    ax.legend()
    set_axes_equal(ax)
    
    plt.tight_layout()
    plt.show()

def main():
    # apply_filter_and_visualize()
    visualize_raw_trajectory()
    apply_filter_and_visualize()

if __name__ == "__main__":
    main()