import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from pathlib import Path
from datetime import datetime
import os
from scipy.interpolate import interp1d
from scipy.signal import savgol_filter

class KinectDataMerger:
    def __init__(self, raw_data_path, output_path, 
                 occlusion_threshold=0.005, occlusion_frames=10,
                 merge_strategy='weighted_average'):
        """
        Khởi tạo merger với các tham số
        
        Args:
            raw_data_path: Đường dẫn thư mục chứa file CSV gốc
            output_path: Đường dẫn lưu file kết quả
            occlusion_threshold: Ngưỡng thay đổi tọa độ để xác định che khuất (m)
            occlusion_frames: Số frame liên tiếp để xác định che khuất
            merge_strategy: Chiến lược hợp nhất khi cả 2 cam đều tốt
                - 'weighted_average': Trung bình có trọng số (khuyến nghị)
                - 'average': Trung bình đơn giản
                - 'cam1': Luôn dùng camera 1
                - 'cam2': Luôn dùng camera 2
                - 'best_quality': Chọn camera có chất lượng tốt hơn
        """
        self.raw_data_path = Path(raw_data_path)
        self.output_path = Path(output_path)
        self.occlusion_threshold = occlusion_threshold
        self.occlusion_frames = occlusion_frames
        self.merge_strategy = merge_strategy
        
        # Tạo thư mục output nếu chưa có
        self.output_path.mkdir(parents=True, exist_ok=True)
    
    def find_camera_pairs(self):
        """Tìm các cặp file từ 2 camera cùng thời điểm"""
        cam1_files = sorted(self.raw_data_path.glob("cam1_*.csv"))
        cam2_files = sorted(self.raw_data_path.glob("cam2_*.csv"))
        
        pairs = []
        for cam1_file in cam1_files:
            # Lấy timestamp từ tên file
            timestamp = cam1_file.stem.replace("cam1_", "")
            cam2_file = self.raw_data_path / f"cam2_{timestamp}.csv"
            
            if cam2_file.exists():
                pairs.append((cam1_file, cam2_file, timestamp))
        
        return pairs
    
    def detect_occlusion(self, positions):
        """
        Phát hiện đoạn quỹ đạo bị che khuất
        
        Args:
            positions: DataFrame với các cột Position_X, Position_Y, Position_Z
            
        Returns:
            Boolean array đánh dấu frame bị che khuất
        """
        n = len(positions)
        occluded = np.zeros(n, dtype=bool)
        
        if n < self.occlusion_frames:
            return occluded
        
        # Tính khoảng cách di chuyển giữa các frame
        pos_array = positions[['Position_X', 'Position_Y', 'Position_Z']].values
        distances = np.sqrt(np.sum(np.diff(pos_array, axis=0)**2, axis=1))
        
        # Kiểm tra từng cửa sổ frame
        for i in range(n - self.occlusion_frames + 1):
            window_distances = distances[i:i+self.occlusion_frames-1]
            
            # Nếu tất cả các di chuyển trong cửa sổ đều nhỏ hơn ngưỡng
            if np.all(window_distances < self.occlusion_threshold):
                occluded[i:i+self.occlusion_frames] = True
        
        return occluded
    
    def synchronize_data(self, df1, df2):
        """
        Đồng bộ dữ liệu từ 2 camera theo timestamp
        
        Args:
            df1, df2: DataFrame từ cam1 và cam2
            
        Returns:
            df1_sync, df2_sync: DataFrame đã đồng bộ
        """
        # Merge theo timestamp với tolerance
        df1['Timestamp'] = pd.to_numeric(df1['Timestamp'])
        df2['Timestamp'] = pd.to_numeric(df2['Timestamp'])
        
        # Tìm khoảng timestamp chung
        min_time = max(df1['Timestamp'].min(), df2['Timestamp'].min())
        max_time = min(df1['Timestamp'].max(), df2['Timestamp'].max())
        
        # Lọc dữ liệu trong khoảng chung
        df1_filtered = df1[(df1['Timestamp'] >= min_time) & 
                           (df1['Timestamp'] <= max_time)].copy()
        df2_filtered = df2[(df2['Timestamp'] >= min_time) & 
                           (df2['Timestamp'] <= max_time)].copy()
        
        # Tạo timestamp chung bằng cách lấy union và sort
        all_timestamps = sorted(set(df1_filtered['Timestamp'].values) | 
                               set(df2_filtered['Timestamp'].values))
        
        # Interpolate dữ liệu cho cả 2 camera
        df1_sync = self.interpolate_to_timestamps(df1_filtered, all_timestamps)
        df2_sync = self.interpolate_to_timestamps(df2_filtered, all_timestamps)
        
        return df1_sync, df2_sync
    
    def interpolate_to_timestamps(self, df, target_timestamps):
        """Interpolate dữ liệu đến các timestamp mục tiêu"""
        target_timestamps = np.array(target_timestamps)
        
        # Interpolate cho mỗi cột position
        result = pd.DataFrame({'Timestamp': target_timestamps})
        
        for col in ['Position_X', 'Position_Y', 'Position_Z']:
            interp_func = interp1d(df['Timestamp'].values, 
                                   df[col].values,
                                   kind='linear',
                                   fill_value='extrapolate')
            result[col] = interp_func(target_timestamps)
        
        # Copy các cột khác từ giá trị đầu tiên
        for col in ['Camera_ID', 'Trial_ID', 'Modus', 'Target_ID']:
            if col in df.columns:
                result[col] = df[col].iloc[0]
        
        return result
    
    def merge_trajectories(self, df1, df2):
        """
        Hợp nhất quỹ đạo từ 2 camera, tự động chọn camera tốt hơn
        
        Args:
            df1, df2: DataFrame đã đồng bộ từ cam1 và cam2
            
        Returns:
            merged_df: DataFrame đã hợp nhất
        """
        # Phát hiện che khuất cho cả 2 camera
        occluded1 = self.detect_occlusion(df1)
        occluded2 = self.detect_occlusion(df2)
        
        print(f"Camera 1: {occluded1.sum()}/{len(occluded1)} frames bị che khuất")
        print(f"Camera 2: {occluded2.sum()}/{len(occluded2)} frames bị che khuất")
        
        # Tạo DataFrame kết quả
        merged_df = df1.copy()
        
        # Chọn dữ liệu từ camera tốt hơn cho từng frame
        for i in range(len(merged_df)):
            # Nếu cam1 bị che mà cam2 không bị che, dùng cam2
            if occluded1[i] and not occluded2[i]:
                merged_df.loc[i, ['Position_X', 'Position_Y', 'Position_Z']] = \
                    df2.loc[i, ['Position_X', 'Position_Y', 'Position_Z']]
                merged_df.loc[i, 'Camera_ID'] = df2.loc[i, 'Camera_ID']
            # Nếu cả 2 đều bị che, tính trung bình
            elif occluded1[i] and occluded2[i]:
                merged_df.loc[i, ['Position_X', 'Position_Y', 'Position_Z']] = \
                    (df1.loc[i, ['Position_X', 'Position_Y', 'Position_Z']] + 
                     df2.loc[i, ['Position_X', 'Position_Y', 'Position_Z']]) / 2
                merged_df.loc[i, 'Camera_ID'] = 'merged'
        
        # Làm mượt quỹ đạo để tránh nhảy bất thường
        merged_df = self.smooth_trajectory(merged_df)
        
        return merged_df
    
    def smooth_trajectory(self, df, window_length=5):
        """
        Làm mượt quỹ đạo sử dụng Savitzky-Golay filter
        
        Args:
            df: DataFrame cần làm mượt
            window_length: Độ dài cửa sổ filter
            
        Returns:
            DataFrame đã làm mượt
        """
        df_smooth = df.copy()
        
        if len(df) > window_length:
            polyorder = min(3, window_length - 1)
            
            for col in ['Position_X', 'Position_Y', 'Position_Z']:
                df_smooth[col] = savgol_filter(df[col].values, 
                                               window_length, 
                                               polyorder)
        
        return df_smooth
    
    def visualize_trajectory(self, df, timestamp, save_path=None):
        """
        Vẽ quỹ đạo 3D
        
        Args:
            df: DataFrame chứa quỹ đạo
            timestamp: Timestamp để đặt tên
            save_path: Đường dẫn lưu hình (nếu có)
        """
        fig = plt.figure(figsize=(15, 5))
        
        # Plot 3D trajectory
        ax1 = fig.add_subplot(131, projection='3d')
        ax1.plot(df['Position_X'], df['Position_Y'], df['Position_Z'], 
                 'b-', linewidth=2, alpha=0.7)
        ax1.scatter(df['Position_X'].iloc[0], 
                   df['Position_Y'].iloc[0], 
                   df['Position_Z'].iloc[0],
                   c='green', s=100, marker='o', label='Start')
        ax1.scatter(df['Position_X'].iloc[-1], 
                   df['Position_Y'].iloc[-1], 
                   df['Position_Z'].iloc[-1],
                   c='red', s=100, marker='s', label='End')
        ax1.set_xlabel('X (m)')
        ax1.set_ylabel('Y (m)')
        ax1.set_zlabel('Z (m)')
        ax1.set_title('3D Trajectory')
        ax1.legend()
        
        # Plot X, Y, Z vs time
        ax2 = fig.add_subplot(132)
        time_normalized = (df['Timestamp'] - df['Timestamp'].iloc[0]) / 1000  # Convert to seconds
        ax2.plot(time_normalized, df['Position_X'], 'r-', label='X', linewidth=2)
        ax2.plot(time_normalized, df['Position_Y'], 'g-', label='Y', linewidth=2)
        ax2.plot(time_normalized, df['Position_Z'], 'b-', label='Z', linewidth=2)
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel('Position (m)')
        ax2.set_title('Position vs Time')
        ax2.legend()
        ax2.grid(True)
        
        # Plot velocity
        ax3 = fig.add_subplot(133)
        positions = df[['Position_X', 'Position_Y', 'Position_Z']].values
        velocities = np.sqrt(np.sum(np.diff(positions, axis=0)**2, axis=1))
        time_vel = time_normalized[1:]
        ax3.plot(time_vel, velocities, 'k-', linewidth=2)
        ax3.set_xlabel('Time (s)')
        ax3.set_ylabel('Velocity (m/frame)')
        ax3.set_title('Movement Velocity')
        ax3.grid(True)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Đã lưu hình: {save_path}")
        
        plt.show()
    
    def process_all(self):
        """Xử lý tất cả các cặp file"""
        pairs = self.find_camera_pairs()
        
        if not pairs:
            print("Không tìm thấy cặp file nào!")
            return
        
        print(f"Tìm thấy {len(pairs)} cặp file để xử lý")
        
        for cam1_file, cam2_file, timestamp in pairs:
            print(f"\n{'='*60}")
            print(f"Đang xử lý: {timestamp}")
            print(f"{'='*60}")
            
            try:
                # Đọc dữ liệu
                df1 = pd.read_csv(cam1_file)
                df2 = pd.read_csv(cam2_file)
                
                print(f"Camera 1: {len(df1)} frames")
                print(f"Camera 2: {len(df2)} frames")
                
                # Đồng bộ dữ liệu
                df1_sync, df2_sync = self.synchronize_data(df1, df2)
                print(f"Sau đồng bộ: {len(df1_sync)} frames")
                
                # Hợp nhất quỹ đạo
                merged_df = self.merge_trajectories(df1_sync, df2_sync)
                
                # Lưu file kết quả
                output_file = self.output_path / f"Trajectory_{timestamp}.csv"
                merged_df.to_csv(output_file, index=False)
                print(f"Đã lưu: {output_file}")
                
                # Visualize
                plot_path = self.output_path / f"Trajectory_{timestamp}.png"
                self.visualize_trajectory(merged_df, timestamp, plot_path)
                
            except Exception as e:
                print(f"Lỗi khi xử lý {timestamp}: {str(e)}")
                continue
        
        print(f"\n{'='*60}")
        print("Hoàn thành xử lý tất cả các file!")
        print(f"{'='*60}")


# Sử dụng
if __name__ == "__main__":
    # Đường dẫn
    RAW_DATA_PATH = r"E:\Downloads\BodyBasics-WPF\Experiment\bin\AnyCPU\Debug\RecordTrajectories\RawRecord"
    OUTPUT_PATH = r"E:\Downloads\BodyBasics-WPF\Experiment\Merged_Trajectories"
    
    # Tham số phát hiện che khuất
    OCCLUSION_THRESHOLD = 0.005  # 5mm - thay đổi tùy theo độ chính xác cần thiết
    OCCLUSION_FRAMES = 10  # Số frame liên tiếp để xác định che khuất
    
    # Chiến lược hợp nhất khi cả 2 camera đều tốt
    # Các lựa chọn: 'weighted_average', 'average', 'cam1', 'cam2', 'best_quality'
    MERGE_STRATEGY = 'weighted_average'  # KHUYẾN NGHỊ: Cho kết quả tốt nhất
    
    # Khởi tạo và chạy
    merger = KinectDataMerger(
        raw_data_path=RAW_DATA_PATH,
        output_path=OUTPUT_PATH,
        occlusion_threshold=OCCLUSION_THRESHOLD,
        occlusion_frames=OCCLUSION_FRAMES,
        merge_strategy=MERGE_STRATEGY
    )
    
    merger.process_all()