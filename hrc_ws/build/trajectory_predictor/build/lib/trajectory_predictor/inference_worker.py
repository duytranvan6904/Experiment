#!/usr/bin/env python3
"""
Inference Worker — runs TensorFlow in a COMPLETELY ISOLATED Python process.
Launched by predictor_node using the venv Python executable.
Communicates via stdin/stdout with JSON lines.
"""
import os
import sys
import json
import pickle
import time
import traceback

# These env vars are already set, but reinforce them
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np


def _load_pickle(path):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return pickle.load(f)


def send_response(data):
    """Send JSON response to stdout (read by ROS node)."""
    line = json.dumps(data)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    # Read config from stdin (first line)
    config_line = sys.stdin.readline().strip()
    config = json.loads(config_line)

    model_dir = config["model_dir"]
    model_files = config["model_files"]
    scaler_x_file = config["scaler_x_file"]
    scaler_y_file = config["scaler_y_file"]
    default_model = config["default_model"]
    num_features = config.get("num_features", 3)
    window_size = config.get("window_size", 20)

    # Load scalers
    scaler_x = _load_pickle(os.path.join(model_dir, scaler_x_file))
    scaler_y = _load_pickle(os.path.join(model_dir, scaler_y_file))

    if scaler_x is None or scaler_y is None:
        send_response({"type": "ready", "success": False,
                        "message": f"Scalers not found in {model_dir}"})
        return

    # Import TensorFlow (safe — this is the venv Python)
    try:
        from tensorflow.keras.models import load_model as keras_load
    except Exception as e:
        send_response({"type": "ready", "success": False,
                        "message": f"TensorFlow import failed: {e}"})
        return

    current_model = None
    current_model_name = ""

    def do_load_model(name):
        nonlocal current_model, current_model_name
        name = name.lower().strip()
        if name not in model_files:
            return False, f"Unknown model '{name}'. Available: {list(model_files.keys())}"
        path = os.path.join(model_dir, model_files[name])
        if not os.path.exists(path):
            return False, f"File not found: {path}"
        try:
            import tensorflow as tf

            # Create a compatibility wrapper for Dense that strips new kwargs
            # (e.g. quantization_config) not recognized by older model configs
            class CompatDense(tf.keras.layers.Dense):
                def __init__(self, *args, **kwargs):
                    kwargs.pop('quantization_config', None)
                    super().__init__(*args, **kwargs)

            class CompatGRU(tf.keras.layers.GRU):
                def __init__(self, *args, **kwargs):
                    kwargs.pop('quantization_config', None)
                    super().__init__(*args, **kwargs)

            class CompatLSTM(tf.keras.layers.LSTM):
                def __init__(self, *args, **kwargs):
                    kwargs.pop('quantization_config', None)
                    super().__init__(*args, **kwargs)

            class CompatSimpleRNN(tf.keras.layers.SimpleRNN):
                def __init__(self, *args, **kwargs):
                    kwargs.pop('quantization_config', None)
                    super().__init__(*args, **kwargs)

            custom_objects = {
                'Dense': CompatDense,
                'GRU': CompatGRU,
                'LSTM': CompatLSTM,
                'SimpleRNN': CompatSimpleRNN,
            }

            current_model = keras_load(path, compile=False, custom_objects=custom_objects)
            current_model_name = name
            dummy = np.zeros((1, window_size, num_features), dtype=np.float32)
            current_model.predict(dummy, verbose=0)
            return True, f"Model '{name}' loaded OK"
        except Exception as e:
            return False, f"Load error: {e}"


    def scale_input(input_batch):
        scaled = input_batch.copy().astype(np.float64)
        for i, axis in enumerate(['x', 'y', 'z']):
            if axis in scaler_x:
                scaled[0, :, i] = scaler_x[axis].transform(
                    input_batch[0, :, i].reshape(-1, 1)
                ).flatten()
        return scaled.astype(np.float32)

    def inverse_scale_output(pred_scaled):
        if isinstance(pred_scaled, list):
            pred_scaled = pred_scaled[0]
        res = []
        for i, axis in enumerate(['x', 'y', 'z']):
            val = scaler_y[axis].inverse_transform(
                pred_scaled[0, i].reshape(-1, 1)
            )[0, 0]
            res.append(float(val))
        return res

    # Load default model
    ok, msg = do_load_model(default_model)
    send_response({"type": "ready", "success": ok, "message": msg,
                    "model_name": current_model_name})

    if not ok:
        return

    # Main loop: read commands from stdin, write results to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            continue

        if cmd.get("cmd") == "shutdown":
            break

        elif cmd.get("cmd") == "load_model":
            ok, msg = do_load_model(cmd["model_name"])
            send_response({"type": "model_loaded", "success": ok,
                            "message": msg, "model_name": current_model_name})

        elif cmd.get("cmd") == "predict":
            if current_model is None:
                send_response({"type": "predict", "prediction": None, "inference_ms": 0.0})
                continue
            try:
                input_seq = np.array(cmd["data"], dtype=np.float32)

                # --- Apply Savitzky-Golay Filter ---
                try:
                    from scipy.signal import savgol_filter
                    window_len = 5
                    polyorder = 3
                    if len(input_seq) >= window_len:
                        # Smooth each axis
                        for i in range(num_features):
                            input_seq[:, i] = savgol_filter(input_seq[:, i], window_len, polyorder)
                except Exception as e:
                    # Ignore and fallback to raw data if scipy is missing or error
                    pass

                input_batch = input_seq.reshape(1, -1, num_features)
                input_scaled = scale_input(input_batch)

                t0 = time.time()
                # Fast branch: predict_on_batch avoids __call__ retracing overhead and verbose loop overhead
                pred_tensor = current_model.predict_on_batch(input_scaled)
                if isinstance(pred_tensor, list):
                    pred_scaled = [t.numpy() if hasattr(t, 'numpy') else t for t in pred_tensor]
                else:
                    pred_scaled = pred_tensor.numpy() if hasattr(pred_tensor, 'numpy') else pred_tensor
                inference_ms = (time.time() - t0) * 1000.0

                prediction = inverse_scale_output(pred_scaled)
                send_response({"type": "predict", "prediction": prediction,
                                "inference_ms": inference_ms,
                                "model_name": current_model_name})
            except Exception as e:
                send_response({"type": "predict", "prediction": None,
                                "inference_ms": 0.0, "error": str(e)})


if __name__ == "__main__":
    main()
