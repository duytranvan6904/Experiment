#!/usr/bin/env python3
"""
Inference Worker — runs in a COMPLETELY ISOLATED Python process.
Launched by predictor_node using the venv Python executable.
Communicates via stdin/stdout with JSON lines.

Uses pre-converted ONNX models for fast inference (~1-3ms).
Falls back to TensorFlow predict_on_batch if .onnx file not found.
"""
import os
import sys
import json
import pickle
import time
import traceback

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["PYTHONHASHSEED"] = "0"
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import numpy as np

# Pre-import scipy filter once at startup
try:
    from scipy.signal import savgol_filter as _savgol_filter
except ImportError:
    _savgol_filter = None

# Check ONNX Runtime availability
try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False


def _load_pickle(path):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return pickle.load(f)


def send_response(data):
    line = json.dumps(data)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    config_line = sys.stdin.readline().strip()
    config = json.loads(config_line)

    model_dir = config["model_dir"]
    model_files = config["model_files"]
    scaler_x_file = config["scaler_x_file"]
    scaler_y_file = config["scaler_y_file"]
    default_model = config["default_model"]
    num_features = config.get("num_features", 3)
    window_size = config.get("window_size", 20)

    scaler_x = _load_pickle(os.path.join(model_dir, scaler_x_file))
    scaler_y = _load_pickle(os.path.join(model_dir, scaler_y_file))

    if scaler_x is None or scaler_y is None:
        send_response({"type": "ready", "success": False,
                        "message": f"Scalers not found in {model_dir}"})
        return

    # TF is only needed as fallback
    keras_load = None
    try:
        import tensorflow as tf
        tf.config.threading.set_intra_op_parallelism_threads(2)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        from tensorflow.keras.models import load_model as _keras_load
        keras_load = _keras_load
        import sklearn
        send_response({"type": "info", "message": f"TF {tf.__version__}, ONNX: {HAS_ONNX}"})
    except ImportError as ie:
        if not HAS_ONNX:
            send_response({"type": "ready", "success": False,
                            "message": f"Neither TF nor ONNX available: {ie}"})
            return
        send_response({"type": "info", "message": f"TF not available, using ONNX only"})

    current_model = None        # TF model (fallback)
    current_model_name = ""
    onnx_session = None         # ONNX Runtime session (fast path)
    onnx_input_name = None
    use_onnx = False

    # Median filter buffer for output smoothing
    MEDIAN_WINDOW = 5
    pred_ring = []

    def do_load_model(name):
        nonlocal current_model, current_model_name
        nonlocal onnx_session, onnx_input_name, use_onnx
        name = name.lower().strip()
        if name not in model_files:
            return False, f"Unknown model '{name}'"
        
        h5_file = model_files[name]
        h5_path = os.path.join(model_dir, h5_file)
        onnx_path = os.path.join(model_dir, h5_file.replace('.h5', '.onnx'))
        
        onnx_session = None
        use_onnx = False
        pred_ring.clear()
        
        # Try ONNX first (fast path)
        if HAS_ONNX and os.path.exists(onnx_path):
            try:
                sess_options = ort.SessionOptions()
                sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                sess_options.intra_op_num_threads = 2
                sess_options.inter_op_num_threads = 1
                
                onnx_session = ort.InferenceSession(
                    onnx_path, sess_options,
                    providers=['CPUExecutionProvider']
                )
                onnx_input_name = onnx_session.get_inputs()[0].name
                
                # Warmup
                dummy = np.zeros((1, window_size, num_features), dtype=np.float32)
                onnx_session.run(None, {onnx_input_name: dummy})
                onnx_session.run(None, {onnx_input_name: dummy})
                
                use_onnx = True
                current_model_name = name
                send_response({"type": "info", "message": f"ONNX loaded: {os.path.basename(onnx_path)}"})
                return True, f"Model '{name}' loaded (ONNX)"
            except Exception as e:
                send_response({"type": "info", "message": f"ONNX load failed: {e}"})
                onnx_session = None
        
        # Fallback to TF
        if keras_load is None:
            return False, f"No .onnx file and TF not available for {name}"
        
        if not os.path.exists(h5_path):
            return False, f"File not found: {h5_path}"
        
        try:
            import tensorflow as tf
            
            class CompatDense(tf.keras.layers.Dense):
                def __init__(self, *a, **kw):
                    kw.pop('quantization_config', None); super().__init__(*a, **kw)
            class CompatGRU(tf.keras.layers.GRU):
                def __init__(self, *a, **kw):
                    kw.pop('quantization_config', None); super().__init__(*a, **kw)
            class CompatLSTM(tf.keras.layers.LSTM):
                def __init__(self, *a, **kw):
                    kw.pop('quantization_config', None); super().__init__(*a, **kw)
            class CompatSimpleRNN(tf.keras.layers.SimpleRNN):
                def __init__(self, *a, **kw):
                    kw.pop('quantization_config', None); super().__init__(*a, **kw)
            
            custom_objects = {'Dense': CompatDense, 'GRU': CompatGRU,
                              'LSTM': CompatLSTM, 'SimpleRNN': CompatSimpleRNN}
            
            current_model = keras_load(h5_path, compile=False, custom_objects=custom_objects)
            current_model_name = name
            dummy = np.zeros((1, window_size, num_features), dtype=np.float32)
            current_model.predict(dummy, verbose=0)
            return True, f"Model '{name}' loaded (TF fallback)"
        except Exception as e:
            return False, f"Load error: {e}"

    def scale_input(input_batch):
        scaled = input_batch.copy().astype(np.float64)
        for i, axis in enumerate(['x', 'y', 'z']):
            if axis in scaler_x:
                scaled[0, :, i] = scaler_x[axis].transform(
                    input_batch[0, :, i].reshape(-1, 1)).flatten()
        return scaled.astype(np.float32)

    def inverse_scale_output(pred_scaled):
        if isinstance(pred_scaled, list):
            pred_scaled = pred_scaled[0]
        res = []
        for i, axis in enumerate(['x', 'y', 'z']):
            val = scaler_y[axis].inverse_transform(
                pred_scaled[0, i].reshape(-1, 1))[0, 0]
            res.append(float(val))
        return res

    def median_smooth(prediction):
        """Median filter removes spikes without introducing lag."""
        pred_ring.append(prediction[:])
        if len(pred_ring) > MEDIAN_WINDOW:
            pred_ring.pop(0)
        if len(pred_ring) < 3:
            return prediction
        arr = np.array(pred_ring)
        return [float(np.median(arr[:, i])) for i in range(3)]

    # Load default model
    ok, msg = do_load_model(default_model)
    send_response({"type": "ready", "success": ok, "message": msg,
                    "model_name": current_model_name})
    if not ok:
        return

    # Main loop
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
            if not use_onnx and current_model is None:
                send_response({"type": "predict", "prediction": None, "inference_ms": 0.0})
                continue
            try:
                input_seq = np.array(cmd["data"], dtype=np.float32)

                # Savitzky-Golay filter on input
                try:
                    if _savgol_filter is not None and len(input_seq) >= 5:
                        for i in range(num_features):
                            input_seq[:, i] = _savgol_filter(input_seq[:, i], 5, 3)
                except Exception:
                    pass

                input_batch = input_seq.reshape(1, -1, num_features)
                if np.isnan(input_batch).any():
                    send_response({"type": "predict", "prediction": None,
                                   "inference_ms": 0.0, "error": "NaN"})
                    continue

                input_scaled = scale_input(input_batch)

                t0 = time.time()
                if use_onnx and onnx_session is not None:
                    outputs = onnx_session.run(None, {onnx_input_name: input_scaled})
                    pred_scaled = outputs[0]
                else:
                    pred_scaled = current_model.predict_on_batch(input_scaled)
                inference_ms = (time.time() - t0) * 1000.0

                prediction = inverse_scale_output(pred_scaled)
                prediction = median_smooth(prediction)

                send_response({"type": "predict", "prediction": prediction,
                                "inference_ms": inference_ms,
                                "model_name": current_model_name})
            except Exception as e:
                print(f"DEBUG: Predict error: {e}", file=sys.stderr)
                send_response({"type": "predict", "prediction": None,
                                "inference_ms": 0.0, "error": str(e)})


if __name__ == "__main__":
    main()
