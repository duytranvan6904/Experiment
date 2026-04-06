import pickle

def check_scaler(path):
    try:
        with open(path, 'rb') as f:
            scaler = pickle.load(f)
            print(f"--- {path} ---")
            if isinstance(scaler, dict):
                for k, v in scaler.items():
                    print(f"  {k}: min={v.data_min_[0]:.4f}, max={v.data_max_[0]:.4f}")
            else:
                print(f"  min={scaler.data_min_[0]:.4f}, max={scaler.data_max_[0]:.4f}")
    except Exception as e:
        print(f"Error reading {path}: {e}")

check_scaler('/home/duy/Downloads/GRU-Model-main/scaler_x.pkl')
check_scaler('/home/duy/Downloads/GRU-Model-main/scaler_y.pkl')
check_scaler('/home/duy/Downloads/GRU-Model-main/scaler_y_vel.pkl')
