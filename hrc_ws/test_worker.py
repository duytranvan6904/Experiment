import json
import subprocess
import os
import sys

# Simulation config from full_pipeline.launch.py
config = {
    'model_dir': '/home/duy/Documents/GitHub/Experiment/Trained model',
    'model_files': {
        'rnn': 'rnn_velocity_3_layers.h5',
        'gru': 'gru_velocity_3_layers.h5',
        'lstm': 'lstm_velocity_3_layers.h5',
    },
    'scaler_x_file': 'scaler_x.pkl',
    'scaler_y_file': 'scaler_y.pkl',
    'default_model': 'gru',
    'num_features': 3,
    'window_size': 20,
}

script = '/home/duy/Documents/GitHub/Experiment/hrc_ws/src/trajectory_predictor/trajectory_predictor/inference_worker.py'
python_exe = sys.executable

env = os.environ.copy()
env['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
env['TF_CPP_MIN_LOG_LEVEL'] = '0' # Enable all logs for debugging

print(f"Launching worker with {python_exe}...")
proc = subprocess.Popen(
    [python_exe, script],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
    env=env
)

print("Sending config...")
proc.stdin.write(json.dumps(config) + '\n')
proc.stdin.flush()

print("Reading responses (timeout 15s)...")
try:
    for _ in range(5):
        line = proc.stdout.readline()
        if line:
            print(f"STDOUT: {line.strip()}")
        else:
            break
except Exception as e:
    print(f"Error reading: {e}")

print("Checking STDERR...")
stderr_out = proc.stderr.read(1024)
if stderr_out:
    print(f"STDERR: {stderr_out}")

if proc.poll() is not None:
    print(f"Process exited with code {proc.returncode}")
else:
    print("Process still running. Killing...")
    proc.kill()
