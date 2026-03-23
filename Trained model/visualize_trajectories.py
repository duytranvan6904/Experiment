import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pickle
import time
from tensorflow.keras.models import load_model

# Shared utils
from data_utils import load_data, transform_data

# Parameters
NUM_FEATURES = 3
T = 20
PRED_STEPS = 171
SEQUENCE_LENGTH = T + PRED_STEPS
SAMPLING_FREQ = 16

def load_velocity_scaler(path='scaler_y_vel.pkl'):
    with open(path, 'rb') as f:
        return pickle.load(f)

def load_scalers(x_path='scaler_x.pkl', y_path='scaler_y.pkl'):
    with open(x_path, 'rb') as f:
        scaler_x = pickle.load(f)
    with open(y_path, 'rb') as f:
        scaler_y = pickle.load(f)
    return scaler_x, scaler_y

def calculate_velocity_trajectory(traj_pos, freq=16):
    """
    Calculate velocity for a single trajectory (N, 3).
    """
    diffs = np.diff(traj_pos, axis=0, prepend=traj_pos[0:1])
    return diffs * freq

def predict_assistive_multitask(model, scaler_x, scaler_y_pos, scaler_y_vel, ground_truth_pos):
    """
    Predicts Position and Velocity using Assistive mode (feeding GT Position back).
    Input: Ground Truth Position Trajectory (Full)
    Output: Predicted Position Sequence, Predicted Velocity Sequence
    """
    predictions_pos = []
    predictions_vel = []
    
    # Initialize input sequence (T steps)
    input_seq = np.zeros((T, NUM_FEATURES), dtype=np.float32)
    # Strategy: Start with zeros, set last element to first GT point (aligning with test_model_velocity logic)
    input_seq[-1] = ground_truth_pos[0].copy()
    
    # Iterate through trajectory
    # We predict for i = 0 to N-1
    for i in range(len(ground_truth_pos) - 1):
        # 1. Prepare Input
        current_input = input_seq.copy()
        current_input_batch = current_input.reshape(1, T, NUM_FEATURES)
        
        # 2. Scale Input (Position)
        input_scaled, _ = transform_data(current_input_batch, None, scaler_x, scaler_y_pos)
        
        # 3. Predict
        # Model returns list: [pos_output, vel_output]
        pred_scaled = model.predict(input_scaled, verbose=0)
        
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
        # Assistive: Use Ground Truth Position of the step we just targeted -> ground_truth_pos[i+1]
        input_seq = np.vstack([input_seq[1:], ground_truth_pos[i + 1].reshape(1, NUM_FEATURES)])
        
    return np.array(predictions_pos), np.array(predictions_vel)

def plot_comparison(gt_pos, gt_vel, predictions_dict, title_suffix=""):
    """
    Plot Comparison of GT vs Multiple Models in separate images (Position and Velocity).
    predictions_dict: { 'ModelName': (pred_pos, pred_vel) }
    """
    N = len(gt_pos)
    # Convert steps to seconds (Freq = 16Hz)
    t_full = np.arange(N) / 16.0
    t_pred = np.arange(1, N) / 16.0
    
    # Global Font Settings
    plt.rcParams.update({
        'font.size': 18,
        'axes.titlesize': 24,
        'axes.labelsize': 20,
        'xtick.labelsize': 18,
        'ytick.labelsize': 18,
        'legend.fontsize': 18,
        'font.family': 'serif' 
    })

    names = ['Position X', 'Position Y', 'Position Z']
    labels = ['X', 'Y', 'Z']
    colors = {'GT': 'black', 'GRU': '#1f77b4', 'LSTM': '#d62728', 'RNN': '#ff7f0e'}
    styles = {'GT': '-', 'GRU': '--', 'LSTM': '-.', 'RNN': ':'}
    
    # --- 1. Position Plot ---
    fig_pos, axs_pos = plt.subplots(1, 3, figsize=(20, 6), sharex=True)
    for i in range(3):
        # Plot GT
        axs_pos[i].plot(t_full, gt_pos[:, i], label='GT', color=colors['GT'], linewidth=2.5)
        
        # Plot Models
        for model_name, (p_pos, p_vel) in predictions_dict.items():
            axs_pos[i].plot(t_pred, p_pos[:, i], label=model_name, 
                           color=colors.get(model_name, 'green'), 
                           linestyle=styles.get(model_name, '--'),
                           linewidth=2)
            
        axs_pos[i].set_ylabel(f'Position {labels[i]} (m)', fontweight='bold')
        axs_pos[i].set_title(f'Position {labels[i]}', fontweight='bold', pad=15)
        axs_pos[i].grid(True, alpha=0.3)
        axs_pos[i].set_xlim(0, 12) # Force 0-12s range
        if i == 0: axs_pos[i].legend(loc='upper right', frameon=True, framealpha=0.9)

    axs_pos[1].set_xlabel('Time (s)', fontweight='bold')
    # Custom adjustments based on user feedback
    plt.subplots_adjust(left=0.063, bottom=0.127, right=0.99, top=0.902, wspace=0.3, hspace=0.2)
    plt.savefig('trajectory_position.png', dpi=300) 
    print("Saved plot to trajectory_position.png")
    plt.show()

    # --- 2. Velocity Plot ---
    fig_vel, axs_vel = plt.subplots(1, 3, figsize=(20, 6), sharex=True)
    for i in range(3):
        # Plot GT
        axs_vel[i].plot(t_full, gt_vel[:, i], label='GT', color=colors['GT'], linewidth=2.5)
        
        # Plot Models
        for model_name, (p_pos, p_vel) in predictions_dict.items():
            axs_vel[i].plot(t_pred, p_vel[:, i], label=model_name, 
                           color=colors.get(model_name, 'green'), 
                           linestyle=styles.get(model_name, '--'),
                           linewidth=2)
            
        axs_vel[i].set_ylabel(f'Velocity {labels[i]} (m/s)', fontweight='bold')
        axs_vel[i].set_title(f'Velocity {labels[i]}', fontweight='bold', pad=15)
        axs_vel[i].grid(True, alpha=0.3)
        axs_vel[i].set_xlim(0, 12) # Force 0-12s range
        if i == 0: axs_vel[i].legend(loc='upper right', frameon=True, framealpha=0.9)
        
    axs_vel[1].set_xlabel('Time (s)', fontweight='bold')
    plt.subplots_adjust(left=0.063, bottom=0.127, right=0.99, top=0.902, wspace=0.3, hspace=0.2)
    plt.savefig('trajectory_velocity.png', dpi=300) 
    print("Saved plot to trajectory_velocity.png")
    plt.show()

def get_trajectory(trajectories, specific_id=None):
    """
    Selects a trajectory.
    If specific_id is provided and valid, returns that trajectory.
    Otherwise, selects a random one.
    """
    if specific_id is not None:
        if 0 <= specific_id < len(trajectories):
            print(f"Selecting specific trajectory ID: {specific_id}")
            return trajectories[specific_id], specific_id
        else:
            print(f"ID {specific_id} out of range (0-{len(trajectories)-1}). Defaulting to random.")
    
    idx = np.random.randint(len(trajectories))
    print(f"Selecting random trajectory ID: {idx}")
    return trajectories[idx], idx

def main():
    # 1. Load Resources
    print("Loading resources...")
    if not os.path.exists('scaler_x.pkl'):
        print("Scalers not found.")
        return
        
    scaler_x, scaler_y = load_scalers()
    scaler_y_vel = load_velocity_scaler()
    
    # 2. Load Models
    models = {}
    model_files = {
        'GRU': 'gru_velocity_3_layers.h5',
        'LSTM': 'lstm_velocity_3_layers.h5',
        'RNN': 'rnn_velocity_3_layers.h5'
    }
    
    for name, path in model_files.items():
        if os.path.exists(path):
            print(f"Loading {name} from {path}...")
            try:
                models[name] = load_model(path, compile=False)
            except Exception as e:
                print(f"Error loading {name}: {e}")
        else:
            print(f"Model file {path} not found. Skipping {name}.")
            
    if not models:
        print("No models loaded. Exiting.")
        return

    # 3. Load Data
    data_path = 'test_trajectories.csv'
    if not os.path.exists(data_path):
        print(f"{data_path} not found.")
        return
        
    raw_data_pos = load_data(data_path)
    
    # Split into trajectories
    num_seq = len(raw_data_pos) // SEQUENCE_LENGTH
    trajectories = []
    
    for i in range(num_seq):
        start = i * SEQUENCE_LENGTH
        end = start + SEQUENCE_LENGTH
        traj = raw_data_pos[start:end]
        trajectories.append(traj)
        
    print(f"Loaded {len(trajectories)} trajectories.")
    
    # 4. Pick Trajectory
    # CHANGE THIS ID TO SELECT A SPECIFIC TRAJECTORY (e.g., 10)
    # Set to None for random
    SPECIFIC_ID = 23 
    
    gt_pos, idx = get_trajectory(trajectories, specific_id=SPECIFIC_ID)
    gt_vel = calculate_velocity_trajectory(gt_pos, freq=SAMPLING_FREQ)
    
    # 5. Predict with all models
    predictions = {}
    
    for name, model in models.items():
        print(f"Predicting with {name}...")
        p_pos, p_vel = predict_assistive_multitask(model, scaler_x, scaler_y, scaler_y_vel, gt_pos)
        predictions[name] = (p_pos, p_vel)
        
    # 6. Visualize
    plot_comparison(gt_pos, gt_vel, predictions, title_suffix=f"(Trajectory ID: {idx})")

if __name__ == "__main__":
    main()
