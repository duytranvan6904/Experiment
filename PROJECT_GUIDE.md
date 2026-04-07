# HRC Trajectory Prediction System

Hệ thống dự báo quỹ đạo tay người trong tương tác Người-Robot (Human-Robot Collaboration - HRC), kết hợp giữa ứng dụng thu thập dữ liệu trên Windows và backend xử lý ROS 2 trên Ubuntu.

## 🏗 Kiến trúc Hệ thống

Hệ thống chia làm 2 phần chính:

### 1. Windows side (C# / WPF)
- **Nhiệm vụ**: Thu thập dữ liệu từ cảm biến Kinect, hiển thị trực quan và truyền tọa độ tay qua giao thức TCP (Port 9090) tới Ubuntu.
- **File chính**: `MainWindow.xaml.cs`
- **Tính năng đặc biệt**: 
    - Truyền dữ liệu tọa độ thực (Raw coordinates).
    - Cơ chế dừng ngay lập tức: Ngắt stream TCP khi nhấn "Stop" để đóng băng đồ thị bên Ubuntu.

### 2. Ubuntu side (ROS 2 Humble)
Workspace: `hrc_ws` gồm các package:
- **`kinect_bridge`**: Lớp trung gian nhận dữ liệu TCP từ Windows và publish lên topic `/hand_position`.
- **`trajectory_predictor`**: Lõi xử lý AI.
    - Sử dụng `inference_worker.py` chạy trong process độc lập để tối ưu hiệu năng.
    - Hỗ trợ các model: RNN, GRU, LSTM.
- **`predictor_ui`**: Dashboard hiển thị thời gian thực sử dụng PyQtGraph.
- **`experiment_logger`**: Ghi log dữ liệu đồng bộ (Thực tế vs Dự đoán) ra file CSV để phân tích.

---

## 🚀 Tính năng nổi bật & Tối ưu hóa

1. **Hiệu suất Inference cực cao**: 
    - Tích hợp **ONNX Runtime**, giảm thời gian xử lý từ 15ms xuống còn **1-3ms**.
    - Model được convert sẵn sang định dạng `.onnx` để tránh overhead của TensorFlow.
2. **Xử lý tín hiệu & Chống nhiễu**:
    - **Savitzky-Golay Filter**: Lọc nhiễu đầu vào cho model AI.
    - **Median Filter**: Lọc spike (vọt lố) đầu ra, đảm bảo quỹ đạo mượt mà và an toàn cho robot.
3. **Đồng bộ hóa đồ thị**:
    - Vẽ theo cơ chế **Right-aligned**, đảm bảo dữ liệu thực tế và dự đoán luôn trùng khớp mốc thời gian tại lề phải của biểu đồ.
4. **Điều khiển tức thời**:
    - Reset đồ thị tự động khi bắt đầu kịch bản mới.
    - Đóng băng giao điện ngay khi nhấn Stop trên Windows để tiện quan sát so sánh.

---

## 🛠 Hướng dẫn vận hành

### Bước 1: Khởi động ROS 2 (Ubuntu)
Mở terminal tại thư mục `hrc_ws` và chạy lệnh sau để khởi động toàn bộ pipeline:

```bash
# Build (nếu có thay đổi code)
colcon build --symlink-install

# Source môi trường
source install/setup.bash

# Chạy toàn bộ hệ thống
ros2 launch hrc_bringup full_pipeline.launch.py
```

### Bước 2: Khởi động ứng dụng Windows
1. Mở project trong Visual Studio.
2. Kiểm tra địa chỉ IP của Ubuntu trong cấu hình TCP.
3. Nhấn **Start** trên ứng dụng Windows.

### Bước 3: Thực hiện thí nghiệm
1. Trên Windows: Nhấn **Start Prediction** để bắt đầu ghi và dự đoán.
2. Dashboard trên Ubuntu sẽ tự động reset và bắt đầu vẽ quỹ đạo (Màu xanh: Thực tế, Màu cam: Dự đoán).
3. Khi kết thúc: Nhấn **Stop** trên Windows. Dashboard sẽ freeze để bạn quan sát. File log CSV sẽ được lưu tại `~/hrc_logs/`.

---

## 📂 Danh mục Model
Các model được lưu tại thư mục `Trained model/`:
- `.h5`: Model gốc Keras/TensorFlow.
- `.onnx`: Model đã tối ưu cho hiệu năng cao (Khuyên dùng).

---
*Tài liệu được tạo tự động bởi Antigravity AI Assistant.*
