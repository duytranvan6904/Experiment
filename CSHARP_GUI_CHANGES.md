# Cập nhật GUI C# - Sử dụng Scenario ID

## Ngày: 2025-12-21

## Tóm tắt thay đổi

Đã cập nhật toàn bộ hệ thống để sử dụng **Scenario ID** (1-18) thay vì phải nhập Mode và Target ID riêng lẻ.

## Các file đã thay đổi

### 1. **MainWindow.xaml**
- ✅ **Đã xóa**: ComboBox Mode
- ✅ **Đã xóa**: TextBox Target ID
- ✅ **Giữ lại**: Các controls cần thiết (Start, Stop, Calibrate, Recording Limits)

### 2. **ScenarioInputDialog.xaml** (MỚI)
- Dialog hiển thị khi bấm Stop Recording
- Cho phép nhập Scenario ID (1-18)
- Hiển thị thông tin scenario tương ứng khi nhập

### 3. **ScenarioInputDialog.xaml.cs** (MỚI)
- Code-behind cho dialog
- Validation: chỉ chấp nhận số từ 1-18
- Hiển thị thông tin: Mode, Initial Target, Final Target

### 4. **MainWindow.xaml.cs**
#### Thay đổi:
- ❌ **Đã xóa**: `currentMode`, `currentTargetId`
- ✅ **Thêm mới**: `currentScenarioId` (0 = chưa set, 1-18 = valid)

#### Các hàm mới:
```csharp
// Suy ra Mode từ Scenario ID
private string GetModeName(int scenarioId)

// Suy ra Initial và Final Target từ Scenario ID  
private (int initialTarget, int finalTarget) GetTargetsFromScenario(int scenarioId)

// Cập nhật CSV với metadata scenario
private void UpdateCsvWithScenarioInfo(string filePath, int scenarioId, string mode, int initialTarget, int finalTarget)
```

#### Workflow mới của `BtnStop_Click`:
1. Stop recording
2. Hiển thị dialog nhập Scenario ID
3. Nếu user nhập ID hợp lệ:
   - Lưu `currentScenarioId`
   - Suy ra Mode và Targets
   - Thêm comment line vào đầu CSV với thông tin scenario
   - Hiển thị path với Scenario ID
4. Nếu user Cancel:
   - Vẫn lưu file nhưng ghi chú "No scenario ID"

#### Đã xóa:
- `CboMode_SelectionChanged()`
- `txtTargetId_TextChanged()`

### 5. **TrajectoryRecord.cs**
#### Thay đổi CSV Header:
```csharp
// CŨ: "timestamp,x,y,z,joint,mode,targetId"
// MỚI: "Timestamp,X,Y,Z,Joint,ScenarioId"
```

#### Thay đổi signature AppendSample:
```csharp
// CŨ:
public void AppendSample(DateTime timestamp, float x, float y, float z, string joint, string mode, int targetId)

// MỚI:
public void AppendSample(DateTime timestamp, float x, float y, float z, string joint, int scenarioId)
```

## Mapping Scenario ID

| Scenario ID | Mode | Initial Target | Final Target |
|-------------|------|----------------|--------------|
| 1 | Free | 1 | 1 |
| 2 | Free | 2 | 2 |
| 3 | Free | 3 | 3 |
| 4 | Obstacle | 1 | 1 |
| 5 | Obstacle | 2 | 2 |
| 6 | Obstacle | 3 | 3 |
| 7 | Change | 1 | 2 |
| 8 | Change | 1 | 3 |
| 9 | Change | 2 | 1 |
| 10 | Change | 2 | 3 |
| 11 | Change | 3 | 1 |
| 12 | Change | 3 | 2 |
| 13 | Change+Obstacle | 1 | 2 |
| 14 | Change+Obstacle | 1 | 3 |
| 15 | Change+Obstacle | 2 | 1 |
| 16 | Change+Obstacle | 2 | 3 |
| 17 | Change+Obstacle | 3 | 1 |
| 18 | Change+Obstacle | 3 | 2 |

## Format CSV mới

### Header:
```
Timestamp,X,Y,Z,Joint,ScenarioId
```

### Comment line (được thêm khi Stop):
```
# Scenario 7: Mode=Change, InitialTarget=1, FinalTarget=2
```

### Ví dụ file CSV hoàn chỉnh:
```csv
# Scenario 7: Mode=Change, InitialTarget=1, FinalTarget=2
Timestamp,X,Y,Z,Joint,ScenarioId
2025-12-21T10:30:45.1234567Z,0.123456,0.234567,0.345678,WristRight,7
2025-12-21T10:30:45.1734567Z,0.124456,0.235567,0.346678,WristRight,7
...
```

## Workflow sử dụng mới

### Trước khi record:
1. Xem Python GUI để biết scenario ID cần record
2. Bấm **Start Recording** trong C# app
3. Thực hiện experiment

### Sau khi record:
1. Bấm **Stop**
2. Dialog hiện lên yêu cầu nhập Scenario ID
3. Nhập số từ 1-18
4. Dialog hiển thị thông tin scenario để xác nhận
5. Bấm **OK** → File CSV được lưu với metadata đầy đủ

## Lợi ích

✅ **Đơn giản hóa**: Chỉ cần nhập 1 số thay vì 2 thông tin riêng biệt

✅ **Tránh sai sót**: Không thể nhập sai Mode/Target vì được suy ra tự động

✅ **Đồng bộ**: Scenario ID khớp hoàn toàn với Python GUI

✅ **Metadata đầy đủ**: CSV file chứa cả Scenario ID và comment giải thích

✅ **Truy vết dễ dàng**: Biết chính xác scenario nào đã được record

## Testing Checklist

- [ ] Build project thành công (không có lỗi compile)
- [ ] Dialog hiển thị khi bấm Stop
- [ ] Validation Scenario ID hoạt động (chỉ chấp nhận 1-18)
- [ ] Thông tin scenario hiển thị đúng trong dialog
- [ ] CSV file có header mới
- [ ] CSV file có comment line với metadata
- [ ] ScenarioId được ghi đúng vào mỗi dòng data
- [ ] Có thể Cancel dialog mà không bị crash

## Lưu ý khi build

Nếu gặp lỗi build, kiểm tra:
1. File `ScenarioInputDialog.xaml` và `ScenarioInputDialog.xaml.cs` đã được thêm vào project chưa
2. Build Action của `.xaml` file phải là "Page"
3. Build Action của `.xaml.cs` file phải là "Compile"

Nếu cần thêm file vào project manually:
- Right-click project → Add → Existing Item
- Chọn cả 2 files: `ScenarioInputDialog.xaml` và `ScenarioInputDialog.xaml.cs`
