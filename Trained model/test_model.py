import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pickle
import os
from tensorflow.keras.models import load_model
from tensorflow.keras.losses import MeanSquaredError

# Import shared utils
from data_utils import load_data, create_data, load_scalers, transform_data

# Tham số (cần khớp với Ablation_study)
NUM_FEATURES = 3
T = 20             
PRED_STEPS = 171   
SEQUENCE_LENGTH = T + PRED_STEPS

# --- Hàm Dự đoán Online Kiểu Assistive (Input GT, Dự đoán từ đầu) ---
def predict_assistive_gt_input_from_zero(
                                         model,
                                         scaler_x,
                                         scaler_y,
                                         ground_truth):

    predictions = []
    prediction_times = []
    overall_pred_start_time = time.time()

    # Khởi tạo input sequence ban đầu là vector 0
    input_seq = np.zeros((T, NUM_FEATURES), dtype=np.float32)
    # Note: Logic ban đầu lấy ground_truth[0] làm điểm cuối của input_seq nhưng input_seq toàn 0?
    # Logic cũ: input_seq[-1] = ground_truth[0].copy() -> Có vẻ là khởi tạo điểm hiện tại.
    input_seq[-1] = ground_truth[0].copy()

    # Dự đoán cho từng bước thời gian
    for i in range(len(ground_truth) - 1):
        # Sử dụng input_seq hiện tại
        current_input = input_seq.copy()
        
        # Reshape để scale/transform
        # current_input shape: (T, 3)
        # Cần đưa về (1, T, 3) để transform_data xử lý
        current_input_batch = current_input.reshape(1, T, NUM_FEATURES)
        
        # Transform input bằng scaler đã fit từ training
        # Lưu ý: transform_data trả về X_scaled, y_scaled. Ở đây y=None
        input_scaled, _ = transform_data(current_input_batch, None, scaler_x, scaler_y)

        # Dự đoán
        step_start_time = time.time()
        pred_scaled = model.predict(input_scaled, verbose=0)
        step_end_time = time.time()
        prediction_times.append(step_end_time - step_start_time)

        # Inverse transform output
        # pred_scaled shape: (1, 3)
        prediction = np.zeros(NUM_FEATURES)
        prediction[0] = scaler_y['x'].inverse_transform(pred_scaled[0, 0].reshape(-1, 1))[0, 0]
        prediction[1] = scaler_y['y'].inverse_transform(pred_scaled[0, 1].reshape(-1, 1))[0, 0]
        prediction[2] = scaler_y['z'].inverse_transform(pred_scaled[0, 2].reshape(-1, 1))[0, 0]

        # Lưu dự đoán
        predictions.append(prediction)

        # Cập nhật input sequence cho bước tiếp theo bằng ground truth (Assistive logic)
        input_seq = np.vstack([input_seq[1:], ground_truth[i + 1].reshape(1, NUM_FEATURES)])

    overall_pred_end_time = time.time()
    total_prediction_time = overall_pred_end_time - overall_pred_start_time
    # print(f"Dự đoán hoàn tất sau {total_prediction_time:.4f} giây.")

    return np.array(predictions), prediction_times, total_prediction_time

# --- Hàm Vẽ Đồ Thị So Sánh Assistive 3D ---
def plot_assistive_prediction_3d(ground_truth_xyz, predicted_xyz, title_suffix=""):
    """
    Vẽ so sánh quỹ đạo ground truth 3D và dự đoán kiểu assistive 3D.
    """
    N = len(ground_truth_xyz)
    
    # Trục thời gian
    time_steps_full_gt = np.arange(N)
    time_steps_for_predictions = np.arange(1, N) 

    fig, axs = plt.subplots(1, NUM_FEATURES, figsize=(18, 5), sharex=True)
    labels = ['X', 'Y', 'Z']

    for i in range(NUM_FEATURES):
        # Vẽ Ground Truth
        axs[i].plot(time_steps_full_gt, ground_truth_xyz[:, i], label='Ground Truth', linestyle='-', color='green', alpha=0.7)

        # Vẽ Dự đoán
        axs[i].plot(time_steps_for_predictions, predicted_xyz[:, i], label='Prediction', linestyle='--', color='red', markersize=3, alpha=0.9)
        axs[i].set_ylabel(f'{labels[i]} Coordinate')
        axs[i].set_title(f'{labels[i]} Axis')
        axs[i].legend(loc='best')
        axs[i].grid(True)

    axs[1].set_xlabel('Time Step')
    plt.suptitle(f'Trajectory Prediction {title_suffix}', fontsize=16)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # Settings Paths relative to workspace
    TEST_DATA_PATH = 'test_trajectories.csv'
    SCALER_X_PATH = 'scaler_x.pkl'
    SCALER_Y_PATH = 'scaler_y.pkl'
    # Use the best model from the ablation study (e.g., 5 layers or whichever was saved last/best)
    # Assuming Ablation_study.py saved 'gru_model_5_layers.h5'
    MODEL_PATH = 'gru_model_1_layers.h5' 
    if not os.path.exists(MODEL_PATH):
        print(f"Warning: Model file {MODEL_PATH} not found. Please run Ablation_study.py first.")
        # Fallback to check if any model exists
        # exit() 

    # 1. Load Data & Scalers
    print(f"Loading test data from {TEST_DATA_PATH}...")
    try:
        data = load_data(TEST_DATA_PATH)
        scaler_x, scaler_y = load_scalers(SCALER_X_PATH, SCALER_Y_PATH)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please ensure Ablation_study.py has been run to generate scalers.")
        exit()

    # 2. Process trajectories
    trajectories = []
    num_full_sequences = len(data) // SEQUENCE_LENGTH

    for i in range(num_full_sequences):
        start_idx = i * SEQUENCE_LENGTH
        end_idx = start_idx + SEQUENCE_LENGTH
        trajectory = data[start_idx:end_idx]
        trajectories.append(trajectory)

    trajectories = np.array(trajectories)
    print(f"Loaded {len(trajectories)} test trajectories.")

    # 3. Load Model
    if os.path.exists(MODEL_PATH):
        print(f"Loading model from {MODEL_PATH}...")
        model = load_model(MODEL_PATH, custom_objects={'mse': MeanSquaredError()})
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])

        # 4. Evaluate on Test Set (Global Metrics)
        if len(trajectories) > 0:
            data_flat = trajectories.reshape(-1, NUM_FEATURES)
            inputs, targets = create_data(data_flat, T, SEQUENCE_LENGTH)
            
            # CRITICAL FIX: Transform using loaded scalers, do NOT fit new ones
            inputs_scaled, targets_scaled = transform_data(inputs, targets, scaler_x, scaler_y)
            
            loss, mae = model.evaluate(inputs_scaled, targets_scaled, verbose=0)
            print(f"\n--- Global Evaluation on Test Set ---")
            print(f"Loss (MSE): {loss:.6f}")
            print(f"MAE:        {mae:.6f}")
            print("-" * 30)
        
        # 5. Visualize Predictions (Random Samples)
        NUM_PLOTS = 3
        num_trajectories_to_plot = min(NUM_PLOTS, len(trajectories))
        
        print(f"\nVisualizing {num_trajectories_to_plot} random trajectories...")

        for i in range(num_trajectories_to_plot):
            random_index = np.random.randint(0, len(trajectories))
            trajectory = trajectories[random_index]
            ground_truth_seq = trajectory.copy()

            # Predict
            predicted_seq, prediction_times, total_time = predict_assistive_gt_input_from_zero(
                model, scaler_x, scaler_y, ground_truth=ground_truth_seq
            )

            print(f"Trajectory {random_index}: Inference Time = {total_time:.4f}s ({np.mean(prediction_times)*1000:.2f}ms/step)")
            
            plot_assistive_prediction_3d(ground_truth_seq, predicted_seq, title_suffix=f"(ID: {random_index})")

    else:
        print(f"Model file {MODEL_PATH} not found. Skipping evaluation.")


