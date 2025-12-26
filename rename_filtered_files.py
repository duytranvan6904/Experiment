import os
import glob
import trajectory_filter as tf

# Đường dẫn thư mục chứa các file cần đổi tên
# Sử dụng SAVE_DIR từ file trajectory_filter hoặc bạn có thể điền đường dẫn trực tiếp
TARGET_DIR = tf.RECORD_DIR

def rename_files(directory):
    if not os.path.isdir(directory):
        print(f"❌ Error: Directory not found: {directory}")
        return

    print(f"📂 Scanning directory: {directory}")
    
    # Lấy danh sách tất cả file .csv bắt đầu bằng 'filtered_'
    pattern = os.path.join(directory, "filtered_*.csv")
    files_to_rename = glob.glob(pattern)
    
    count = 0
    if not files_to_rename:
        print("⚠️  No files found starting with 'filtered_'.")
        return

    print(f"🔍 Found {len(files_to_rename)} files to rename.")
    
    for file_path in files_to_rename:
        directory_path = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Tạo tên mới bằng cách bỏ 'filtered_' (9 ký tự đầu)
        new_filename = filename.replace("filtered_", "", 1)
        new_file_path = os.path.join(directory_path, new_filename)
        
        try:
            # Kiểm tra nếu file đích đã tồn tại để tránh ghi đè nhầm (tùy chọn)
            if os.path.exists(new_file_path):
                print(f"⚠️  Skipping: '{new_filename}' already exists.")
                continue
                
            os.rename(file_path, new_file_path)
            # print(f"✅ Renamed: {filename} -> {new_filename}")
            count += 1
        except Exception as e:
            print(f"❌ Error renaming {filename}: {e}")

    print("-" * 60)
    print(f"✅ Renaming Completed.")
    print(f"   Total renamed: {count} files")
    print("-" * 60)

if __name__ == "__main__":
    rename_files(TARGET_DIR)
