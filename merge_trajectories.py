import os
import glob
import pandas as pd

# ==================================================================================
# CONFIGURATION
# ==================================================================================
INPUT_DIR = r"E:\Downloads\BodyBasics-WPF\Experiment\bin\AnyCPU\Debug\Trajectories\All_traj"
OUTPUT_FILE = r"E:\Downloads\BodyBasics-WPF\Experiment\experiment_trajectories.csv"
MAX_TIMESTAMP = 190

def log(msg):
    with open("merge_log.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

def main():
    if os.path.exists("merge_log.txt"):
        os.remove("merge_log.txt")
        
    log(f"Scanning directory: {INPUT_DIR}")
    
    if not os.path.exists(INPUT_DIR):
        log("❌ Error: Input directory does not exist.")
        return

    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    log(f"Found {len(csv_files)} CSV files.")
    
    if len(csv_files) == 0:
        log("No CSV files found.")
        return

    all_data = []
    
    for file_path in csv_files:
        try:
            # Read CSV
            df = pd.read_csv(file_path)
            
            # Truncate by 'Timestamp' if column exists
            if 'Timestamp' in df.columns:
                # Ensure Timestamp is numeric just in case
                # Note: If Timestamp is frame index 0,1,2..., filtering <= MAX_TIMESTAMP works perfect.
                df_filtered = df[df['Timestamp'] <= MAX_TIMESTAMP].copy()
            else:
                # Fallback: Truncate by index rows (0 to 191 rows -> index 0..190)
                # log(f"⚠️  {os.path.basename(file_path)}: 'Timestamp' column missing. Using row index.")
                df_filtered = df.iloc[:MAX_TIMESTAMP+1].copy()
            
            # Add a column for SourceFile just in case it's needed for debugging (optional)
            # df_filtered['SourceFile'] = os.path.basename(file_path)
            
            all_data.append(df_filtered)
            
        except Exception as e:
            log(f"❌ Error reading {os.path.basename(file_path)}: {e}")

    if len(all_data) > 0:
        log("Merging data...")
        merged_df = pd.concat(all_data, ignore_index=True)
        
        log(f"Total rows: {len(merged_df)}")
        log(f"Saving to: {OUTPUT_FILE}")
        
        try:
            merged_df.to_csv(OUTPUT_FILE, index=False)
            log("✅ Successfully saved merged file.")
        except Exception as e:
            log(f"❌ Error saving file: {e}")
    else:
        log("No valid data to merge.")

if __name__ == "__main__":
    main()
