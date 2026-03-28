import sys
import json
import time
from subprocess import Popen, PIPE

proc = Popen(['/home/duy/Experiment/.venv/bin/python3', '/home/duy/Experiment/hrc_ws/src/trajectory_predictor/trajectory_predictor/inference_worker.py'],
             stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)

config = {
    "model_dir": "/home/duy/Downloads/GRU-Model-main",
    "model_files": {"gru": "gru_velocity_3_layers.h5"},
    "scaler_x_file": "scaler_x.pkl",
    "scaler_y_file": "scaler_y.pkl",
    "default_model": "gru",
    "num_features": 3,
    "window_size": 20
}
proc.stdin.write(json.dumps(config) + "\n")
proc.stdin.flush()

# Read ready
ready = proc.stdout.readline()
print("READY:", ready.strip())

# Send predict
data = [[0.1, 0.2, 0.3]] * 20
proc.stdin.write(json.dumps({"cmd": "predict", "data": data}) + "\n")
proc.stdin.flush()

# Read pred
pred = proc.stdout.readline()
print("PRED1:", pred.strip())

data[19] = [0.11, 0.21, 0.31]
proc.stdin.write(json.dumps({"cmd": "predict", "data": data}) + "\n")
proc.stdin.flush()
pred2 = proc.stdout.readline()
print("PRED2:", pred2.strip())

proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
proc.stdin.flush()
proc.wait()
print("Worker StdErr:")
print(proc.stderr.read())
