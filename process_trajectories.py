import os
import glob
import pandas as pd
import trajectory_filter as tf
import shutil

# ==================================================================================
# CONFIGURATION
# ==================================================================================
# Đường dẫn mặc định (lấy từ trajectory_filter.py hoặc bạn có thể chỉnh sửa trực tiếp tại đây)
DEFAULT_INPUT_DIR = tf.RECORD_DIR
DEFAULT_OUTPUT_DIR = tf.SAVE_DIR

# Số lượng kịch bản và số lần lặp lại mong muốn
NUM_SCENARIOS = 18
REQUIRED_REPETITIONS = 4

# ==================================================================================
# FUNCTIONS
# ==================================================================================

def count_csv_files(folder_path):
    """
    Đếm số lượng file .csv trong thư mục.
    """
    if not os.path.isdir(folder_path):
        print(f"❌ Error: Folder not found: {folder_path}")
        return 0
    
    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    count = len(csv_files)
    print(f"📂 Found {count} .csv files in '{folder_path}'")
    return count

def check_scenario_coverage(folder_path):
    """
    Kiểm tra mỗi scenario có bao nhiêu file csv.
    Yêu cầu: Mỗi scenario (1-18) cần đủ 4 file.
    Trả về dict mapping {scenario_id: [list_of_files]}
    """
    if not os.path.isdir(folder_path):
        return {}

    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    scenario_map = {i: [] for i in range(1, NUM_SCENARIOS + 1)}
    
    print("\n🔍 Checking Scenario Coverage...")
    
    for file_path in csv_files:
        try:
            # Đọc file CSV để lấy ScenarioId (chỉ cần đọc vài dòng đầu)
            df = pd.read_csv(file_path, nrows=5)
            if 'ScenarioId' in df.columns:
                # Lấy ScenarioId từ dòng đầu tiên
                scenario_id = int(df['ScenarioId'].iloc[2])
            else:
                # If missing column, try to infer from filename or skip
                # For now, default to 0 (no special handling)
                scenario_id = 0
                print(f"⚠️  Warning: File '{os.path.basename(file_path)}' missing 'ScenarioId' column.")
        except Exception as e:
            print(f"❌ Error reading '{os.path.basename(file_path)}': {e}")

    # Báo cáo kết quả
    all_ok = True
    print(f"\n📊 Scenario Coverage Report (Target: {REQUIRED_REPETITIONS} per scenario):")
    print("-" * 60)
    print(f"{'Scenario ID':<15} | {'Count':<10} | {'Status':<20}")
    print("-" * 60)
    
    # Sắp xếp theo key để in cho đẹp
    sorted_ids = sorted(scenario_map.keys())
    
    for sc_id in sorted_ids:
        count = len(scenario_map[sc_id])
        status = "✅ OK" if count >= REQUIRED_REPETITIONS else f"❌ MISSING {REQUIRED_REPETITIONS - count}"
        
        if count < REQUIRED_REPETITIONS:
            all_ok = False
            
        # In màu mè một chút nếu có thể (ở đây in text thường)
        print(f"{sc_id:<15} | {count:<10} | {status}")
        
    print("-" * 60)
    if all_ok:
        print("✅ SUCCESS: All scenarios have sufficient data.")
    else:
        print("⚠️  WARNING: Some scenarios are missing data.")
        
    return scenario_map

def apply_filter_to_all(input_dir, output_dir):
    """
    Áp dụng bộ lọc (từ trajectory_filter.py) cho tất cả các file CSV trong input_dir
    và lưu vào output_dir.
    """
    print(f"\n🛠️  Applying filter to all files...")
    print(f"   Input:  {input_dir}")
    print(f"   Output: {output_dir}")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"   Created output directory: {output_dir}")

    csv_files = glob.glob(os.path.join(input_dir, "*.csv"))
    
    success_count = 0
    fail_count = 0
    
    # Các cột cần xử lý (Lưu ý: trajectory_filter đã định nghĩa X, Y, Z nhưng có thể swap trục)
    # Chúng ta sử dụng lại logic của clean_and_smooth_trajectory
    # tf.X_COL = "X", tf.Y_COL = "Z", tf.Z_COL = "Y"
    cols_to_process = [tf.X_COL, tf.Y_COL, tf.Z_COL] # ["X", "Z", "Y"]
    
    for file_path in csv_files:
        filename = os.path.basename(file_path)
        try:
            df = tf.load_csv(file_path)
            
            # Kiểm tra cột
            if not all(c in df.columns for c in cols_to_process):
                print(f"⏭️  Skipping {filename}: Missing columns {cols_to_process}")
                fail_count += 1
                continue
            
            # Timestamp check
            if tf.TIME_COL not in df.columns:
                df[tf.TIME_COL] = range(len(df))
            
            # Áp dụng hàm filter từ trajectory_filter.py
            cleaned_df, outlier_count = tf.clean_and_smooth_trajectory(df, cols_to_process, tf.TIME_COL)
            
            if cleaned_df is None:
                print(f"❌ Failed to process {filename}")
                fail_count += 1
                continue
            
            # Tạo dataframe kết quả (giữ lại các cột khác nếu cần, hoặc chỉ lưu cột đã filter)
            # Ở đây ta copy df gốc và update các cột đã filter
            result_df = df.copy()
            for col in cleaned_df.columns:
                result_df[col] = cleaned_df[col].values

            # 0. Truncate Data (Keep only up to timestamp 190)
            # Assuming 'Timestamp' column exists usually (from raw info)
            # Check if 'Timestamp' exists, else rely on index?
            # Raw files usually have 'Timestamp' 0, 1, 2...
            if 'Timestamp' in df.columns:
                 df = tf.truncate_by_timestamp(df, max_ts=190)
            else:
                 # If no timestamp, maybe just take first 191 rows?
                 df = df.iloc[:191]

            # 1. SWAP Y/Z Columns
            df = tf.swap_yz(df)
            
            # 2. Normalize Y Start (Subtract int part of start)
            df = tf.normalize_y_start(df, y_col='Y')

            # 3. Clean and Smooth (Pipeline cũ)
            # Note: clean_and_smooth_trajectory handles basic smoothing. 
            # We pass current df. 
            # Note: tf.Z_COL is "Y" in the file?? No, let's look at trajectory_filter.py imports.
            # In trajectory_filter.py:
            # TIME_COL = "Timestamp", X_COL = "X", Y_COL = "Z", Z_COL = "Y"
            # Wait, the trajectory_filter constants might be confusing now that we swapped Y and Z.
            # If we swapped, then df['Z'] IS height (assuming user meant Z is height).
            # "y cordinate and z cordinate were exchanged" -> Originally Z was height (Kinect)? 
            # Usually Kinect Y is Height. User said "exchanged... so you should exchange them".
            # If we swap, "Height" should end up in Z column? 
            # User said: "Height axis: After swapping, 'Z' will be treated as the Height axis."
            
            # So after swap, Z is height.
            # But trajectory_filter.py has: Y_COL = "Z", Z_COL = "Y".
            # We should probably pass explicit column names to clean_and_smooth if needed, or rely on it using x,y,z names.
            # clean_and_smooth uses: cols = [X_COL, Y_COL, Z_COL]
            # If we swapped in df, and passed df to clean_and_smooth, it will use cols.
            # If cols are "X", "Z", "Y" (from constants), it just extracts those columns.
            # Since we have "X","Y","Z" columns in df, order in list doesn't matter much for extraction.
            
            cleaned_df, outlier_count = tf.clean_and_smooth_trajectory(df, cols_to_process, tf.TIME_COL)
            
            if cleaned_df is None:
                print(f"❌ Failed to process {filename}")
                fail_count += 1
                continue

            # Update result_df with smoothed values
            result_df = df.copy()
            for col in cleaned_df.columns:
                result_df[col] = cleaned_df[col].values
            
            # 4. Normalize Z Min (Global Shift)
            # Ensure the lowest point is at 0 (ground level) to correct for sensor noise/offset
            z_min = result_df['Z'].min()
            result_df['Z'] = result_df['Z'] - z_min

            # 5. Normalize Start/End (Smoothing) - on Z axis (Height)
            # User: "8 points", "if > 5cm".
            result_df = tf.normalize_start_end(result_df, z_col='Z', n_start=8, n_end=8, threshold=0.05)
            
            # 6. Obstacle Clearance
            # Scenarios: 4-6, 13-18
            obstacle_scenarios = [4, 5, 6, 13, 14, 15, 16, 17, 18]
            
            # Extract ScenarioId again from result_df (it should still be there)
            if 'ScenarioId' in result_df.columns:
                 sc_id = int(result_df['ScenarioId'].iloc[0])
                 if sc_id in obstacle_scenarios:
                     result_df = tf.ensure_obstacle_clearance(result_df, z_col='Z', min_height=0.35)
            
            # Thêm cột Sequential Timestamp
            if 'Timestamp' in result_df.columns:
                result_df = result_df.drop(columns=['Timestamp'])
            result_df.insert(0, 'Timestamp', range(len(result_df)))
            
            # Lưu file
            save_path = os.path.join(output_dir, f"{filename}")
            result_df.to_csv(save_path, index=False)
            
            # print(f"   Saved: {save_path}") # Uncomment nếu muốn in từng file
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            fail_count += 1
            
    print("-" * 60)
    print(f"✅ Processing Finalized:")
    print(f"   Successfully filtered: {success_count} files")
    print(f"   Failed/Skipped:        {fail_count} files")
    print(f"   Files saved to:        {output_dir}")
    print("-" * 60)

# ==================================================================================
# MAIN EXECUTION
# ==================================================================================
if __name__ == "__main__":
    print("=======================================================")
    print("   AUTOMATED TRAJECTORY DATA MANAGER")
    print("=======================================================")
    
    # 1. Đếm file
    count = count_csv_files(DEFAULT_INPUT_DIR)
    
    if count > 0:
        # 2. Kiểm tra Scenario Coverage
        check_scenario_coverage(DEFAULT_INPUT_DIR)
        
        # 3. Hỏi người dùng có muốn filter không? (Hoặc chạy luôn theo yêu cầu)
        # Theo yêu cầu của user: "Áp dụng filter với tất cả các file..." -> Chạy luôn.
        
        # Bạn có thể thay đổi đường dẫn output ở đây nếu muốn
        custom_output_dir = DEFAULT_OUTPUT_DIR 
        # Ví dụ: custom_output_dir = "C:\\Users\\ASUS\\Desktop\\FilteredTrajectories"
        
        apply_filter_to_all(DEFAULT_INPUT_DIR, custom_output_dir)
        
    else:
        print("No CSV files found to process.")
