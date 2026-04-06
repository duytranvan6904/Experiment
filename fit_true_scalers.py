import os
import sys

# Add GRU model path to import data_utils
sys.path.append('/home/duy/Downloads/GRU-Model-main')
from data_utils import load_data, create_data, fit_scalers
from Ablation_study_Velocity import calculate_velocity
from sklearn.model_selection import train_test_split
import numpy as np

def main():
    data_path = '/home/duy/Downloads/GRU-Model-main/experiment_trajectories.csv'
    print(f"Loading data from {data_path}...")
    raw_data_pos = load_data(data_path) 
    
    T = 20
    PRED_STEPS = 171
    SEQUENCE_LENGTH = T + PRED_STEPS
    
    # We just want to fit the scalers as training did
    trajectories_pos = []
    num_seq = len(raw_data_pos) // SEQUENCE_LENGTH
    
    for i in range(num_seq):
        start = i * SEQUENCE_LENGTH
        end = start + SEQUENCE_LENGTH
        trajectories_pos.append(raw_data_pos[start:end])
        
    print(f"Found {len(trajectories_pos)} trajectories")
    
    # Create X, y
    X, y = create_data(raw_data_pos, T, SEQUENCE_LENGTH)
    
    indices = np.arange(len(X))
    idx_temp, idx_test = train_test_split(indices, test_size=0.15, random_state=42, shuffle=True)
    idx_train, idx_val = train_test_split(idx_temp, test_size=0.1765, random_state=42, shuffle=True)
    
    X_train, y_train = X[idx_train], y[idx_train]
    
    scaler_x, scaler_y = fit_scalers(X_train, y_train)
    
    print("\n--- TRUE DATA SCALERS (Fitted on Train Split) ---")
    for k, v in scaler_x.items():
        print(f"  {k}: min={v.data_min_[0]:.4f}, max={v.data_max_[0]:.4f}")
        
    print("\nUser's hardcoded scalers (current):")
    print("  x: min=-0.2000, max=0.8000")
    print("  y: min=-0.0500, max=1.5000")
    print("  z: min=-0.0500, max=0.5500")

if __name__ == '__main__':
    main()
