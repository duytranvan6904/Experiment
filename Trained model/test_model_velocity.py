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
from Ablation_study_Velocity import calculate_velocity

# Parameters
NUM_FEATURES = 3
T = 20             
PRED_STEPS = 180   
SEQUENCE_LENGTH = T + PRED_STEPS
SAMPLING_FREQ = 16

def load_velocity_scaler(path='scaler_y_vel.pkl'):
    with open(path, 'rb') as f:
        return pickle.load(f)

def predict_assistive_multitask(model, scaler_x, scaler_y_pos, scaler_y_vel, ground_truth_pos):
    """
    Predicts Position and Velocity using Assistive mode (feeding GT Position back).
    Input: Ground Truth Position Trajectory (Full)
    Output: Predicted Position Sequence, Predicted Velocity Sequence
    """
    
    predictions_pos = []
    predictions_vel = []
    prediction_times = []
    
    overall_start = time.time()
    
    # Initialize input sequence (T steps)
    # Strategy: Use first T steps of GT to start? 
    # Or start from 0 like test_model.py?
    # test_model.py logic: starts with zeros, sets last element to gt[0].
    # Let's align with test_model.py for consistency.
    
    input_seq = np.zeros((T, NUM_FEATURES), dtype=np.float32)
    input_seq[-1] = ground_truth_pos[0].copy()
    
    # Iterate through trajectory
    # We predict for i = 0 to N-1
    # For Input at Step i, we want to predict Target at Step i+1 ?
    # Typically: Input [0..T-1] -> Predict T.
    # Here: Input [Previous History] -> Predict Current/Next.
    
    for i in range(len(ground_truth_pos) - 1):
        # 1. Prepare Input
        current_input = input_seq.copy()
        current_input_batch = current_input.reshape(1, T, NUM_FEATURES)
        
        # 2. Scale Input (Position)
        input_scaled, _ = transform_data(current_input_batch, None, scaler_x, scaler_y_pos)
        
        # 3. Predict
        step_start = time.time()
        # Model returns list: [pos_output, vel_output]
        pred_scaled = model.predict(input_scaled, verbose=0)
        step_end = time.time()
        prediction_times.append(step_end - step_start)
        
        pred_pos_scaled = pred_scaled[0] # Shape (1, 3)
        pred_vel_scaled = pred_scaled[1] # Shape (1, 3)
        
        # 4. Inverse Transform
        # Position
        pred_pos = np.zeros(NUM_FEATURES)
        pred_pos[0] = scaler_y_pos['x'].inverse_transform(pred_pos_scaled[0, 0].reshape(-1, 1))[0, 0]
        pred_pos[1] = scaler_y_pos['y'].inverse_transform(pred_pos_scaled[0, 1].reshape(-1, 1))[0, 0]
        pred_pos[2] = scaler_y_pos['z'].inverse_transform(pred_pos_scaled[0, 2].reshape(-1, 1))[0, 0]
        predictions_pos.append(pred_pos)
        
        # Velocity
        pred_vel = np.zeros(NUM_FEATURES)
        pred_vel[0] = scaler_y_vel['x'].inverse_transform(pred_vel_scaled[0, 0].reshape(-1, 1))[0, 0]
        pred_vel[1] = scaler_y_vel['y'].inverse_transform(pred_vel_scaled[0, 1].reshape(-1, 1))[0, 0]
        pred_vel[2] = scaler_y_vel['z'].inverse_transform(pred_vel_scaled[0, 2].reshape(-1, 1))[0, 0]
        predictions_vel.append(pred_vel)
        
        # 5. Update Input for Next Step
        # Assistive: Use Ground Truth Position of the step we just targeted (or next input)
        # If we plotted prediction for t+1, next input should include t+1.
        # Here ground_truth_pos[i+1] is the target we just tried to predict.
        # So we append it to history.
        input_seq = np.vstack([input_seq[1:], ground_truth_pos[i + 1].reshape(1, NUM_FEATURES)])
        
    total_time = time.time() - overall_start
    return np.array(predictions_pos), np.array(predictions_vel), total_time

def plot_multitask_comparison(gt_pos, pred_pos, gt_vel, pred_vel, title_suffix=""):
    """
    Plot 2 rows: Position and Velocity
    """
    N = len(gt_pos)
    # Time steps for plotting
    time_steps_full = np.arange(N)
    time_steps_pred = np.arange(1, N) # Predictions start from 2nd point effectively (or 1st after initial state)
    
    # Note: gt_vel has same length as gt_pos?
    # calculate_velocity preserves length (first element 0).
    
    # Align Prediction Length
    # We predicted len(gt_pos) - 1 steps.
    
    fig, axs = plt.subplots(2, 3, figsize=(18, 10), sharex=True)
    labels = ['X', 'Y', 'Z']
    
    # Row 1: Position
    for i in range(3):
        axs[0, i].plot(time_steps_full, gt_pos[:, i], label='GT Pos', color='green')
        axs[0, i].plot(time_steps_pred, pred_pos[:, i], label='Pred Pos', color='red', linestyle='--')
        axs[0, i].set_ylabel(f'{labels[i]} Position')
        axs[0, i].set_title(f'Position {labels[i]}')
        axs[0, i].legend()
        axs[0, i].grid(True)
        
    # Row 2: Velocity
    for i in range(3):
        axs[1, i].plot(time_steps_full, gt_vel[:, i], label='GT Vel', color='blue')
        axs[1, i].plot(time_steps_pred, pred_vel[:, i], label='Pred Vel', color='orange', linestyle='--')
        axs[1, i].set_ylabel(f'{labels[i]} Velocity')
        axs[1, i].set_title(f'Velocity {labels[i]}')
        axs[1, i].legend()
        axs[1, i].grid(True)
        
    axs[1, 1].set_xlabel('Time Step')
    plt.suptitle(f'Multitask Prediction (Pos + Vel) {title_suffix}', fontsize=16)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # Settings
    TEST_DATA_PATH = 'data_test.csv'
    SCALER_X_PATH = 'scaler_x.pkl'
    SCALER_Y_PATH = 'scaler_y.pkl'
    SCALER_VEL_PATH = 'scaler_y_vel.pkl'
    MODEL_PATH = 'gru_velocity_1_layers.h5' # Assuming 5 layers is best or desired
    
    # Check Model
    if not os.path.exists(MODEL_PATH):
        # Try finding any velocity model
        available = [f for f in os.listdir('.') if 'gru_velocity' in f and f.endswith('.h5')]
        if available:
            MODEL_PATH = available[-1] # Pick last one
            print(f"Model not found, defaulting to {MODEL_PATH}")
        else:
            print("No Velocity Model found. Run Ablation_study_Velocity.py first.")
            exit()
            
    if not os.path.exists(SCALER_VEL_PATH):
        print("Velocity Scaler not found. Run Ablation_study_Velocity.py first.")
        exit()

    # 1. Load Data
    print("Loading Data...")
    raw_data_pos = load_data(TEST_DATA_PATH)
    
    # 2. Calculate GT Velocity for specific test trajectories
    # Note: We need to split into trajectories for accurate velocity calc (breaks at boundaries)
    # But calculate_velocity function handles full data assuming contiguous? 
    # Wait, the calculate_velocity function provided in Ablation splits by SEQUENCE_LENGTH.
    # But test data might be just a list of trajectories.
    # Let's rely on standard trajectory parsing.
    
    # Helper to parse trajectories for testing
    trajectories_pos = []
    trajectories_vel = []
    
    num_seq = len(raw_data_pos) // SEQUENCE_LENGTH
    
    for i in range(num_seq):
        start = i * SEQUENCE_LENGTH
        end = start + SEQUENCE_LENGTH
        
        # Position
        traj_pos = raw_data_pos[start:end]
        trajectories_pos.append(traj_pos)
        
        # Velocity (Calculate specifically for this trajectory to be safe)
        # Using the same logic as training but per single trajectory
        # Make it a list of 1 trajectory to reuse function or just call it directly if it handles array
        # calculate_velocity input is (N, 3), loops by seq len.
        # So we can pass just this trajectory.
        traj_vel = calculate_velocity(traj_pos, SEQUENCE_LENGTH, freq=SAMPLING_FREQ)
        trajectories_vel.append(traj_vel)
        
    trajectories_pos = np.array(trajectories_pos)
    trajectories_vel = np.array(trajectories_vel) # Shape: (Num, SeqLen, 3)
    
    print(f"Loaded {len(trajectories_pos)} test trajectories.")
    
    # 3. Load Resources
    scaler_x, scaler_y = load_scalers(SCALER_X_PATH, SCALER_Y_PATH)
    scaler_y_vel = load_velocity_scaler(SCALER_VEL_PATH)
    
    print(f"Loading Model: {MODEL_PATH}")
    model = load_model(MODEL_PATH, compile=False) 
    # Note: No need to compile if just predicting, but good for suppressing warnings if needed.
    
    # 4. Predict and Visualize
    NUM_PLOTS = 3
    indices = np.random.choice(len(trajectories_pos), size=min(NUM_PLOTS, len(trajectories_pos)), replace=False)
    
    for idx in indices:
        print(f"\nProcessing Trajectory {idx}...")
        gt_pos = trajectories_pos[idx]
        gt_vel = trajectories_vel[idx] # This is GT Velocity
        
        pred_pos, pred_vel, t_time = predict_assistive_multitask(
            model, scaler_x, scaler_y, scaler_y_vel, gt_pos
        )
        
        print(f"Inference Time: {t_time:.4f}s")
        plot_multitask_comparison(gt_pos, pred_pos, gt_vel, pred_vel, title_suffix=f"(ID: {idx})")

