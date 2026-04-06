import csv
import pickle
import numpy as np
from sklearn.preprocessing import MinMaxScaler

def main():
    data_path = '/home/duy/Downloads/GRU-Model-main/experiment_trajectories.csv'
    
    positions = []
    
    with open(data_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        x_idx, y_idx, z_idx = header.index('X'), header.index('Y'), header.index('Z')
        
        for row in reader:
            try:
                positions.append([float(row[x_idx]), float(row[y_idx]), float(row[z_idx])])
            except ValueError:
                pass
                
    pos_np = np.array(positions)
    print("Found", pos_np.shape[0], "samples.")
    
    x_min, x_max = pos_np[:, 0].min(), pos_np[:, 0].max()
    y_min, y_max = pos_np[:, 1].min(), pos_np[:, 1].max()
    z_min, z_max = pos_np[:, 2].min(), pos_np[:, 2].max()
    
    print(f"Data ranges:")
    print(f"  X: min={x_min:.4f}, max={x_max:.4f}")
    print(f"  Y: min={y_min:.4f}, max={y_max:.4f}")
    print(f"  Z: min={z_min:.4f}, max={z_max:.4f}")

    # Generate the correct scalers
    scaler_x = {
        'x': MinMaxScaler().fit(pos_np[:, 0].reshape(-1, 1)),
        'y': MinMaxScaler().fit(pos_np[:, 1].reshape(-1, 1)),
        'z': MinMaxScaler().fit(pos_np[:, 2].reshape(-1, 1))
    }
    
    scaler_y = {
        'x': MinMaxScaler().fit(pos_np[:, 0].reshape(-1, 1)),
        'y': MinMaxScaler().fit(pos_np[:, 1].reshape(-1, 1)),
        'z': MinMaxScaler().fit(pos_np[:, 2].reshape(-1, 1))
    }
    
    with open('/home/duy/Downloads/GRU-Model-main/scaler_x_corrected.pkl', 'wb') as f:
        pickle.dump(scaler_x, f)
        
    with open('/home/duy/Downloads/GRU-Model-main/scaler_y_corrected.pkl', 'wb') as f:
        pickle.dump(scaler_y, f)
        
    print("Saved scaler_x_corrected.pkl and scaler_y_corrected.pkl")

if __name__ == '__main__':
    main()
