#!/usr/bin/env python3
"""
Trajectory Predictor Node — ROS 2 node that delegates ML inference
to an isolated subprocess (using venv Python) to completely avoid
TensorFlow/ROS protobuf/numpy library conflicts.

Uses zero-padded buffer: predictions start from the very first data point.
"""
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool

from human_hand_msgs.msg import HandState, HandPrediction, SystemStatus
from human_hand_msgs.srv import SelectModel


class TrajectoryPredictorNode(Node):
    def __init__(self):
        super().__init__('trajectory_predictor')

        # Add pos_offset for dynamic auto-centering
        self.pos_offset = np.array([0.0, 0.0, 0.0], dtype=np.float32)

        # ---------- Parameters ----------
        self.declare_parameter('model_dir', '')
        self.declare_parameter('default_model', 'gru')
        self.declare_parameter('scaler_x_file', 'scaler_x.pkl')
        self.declare_parameter('scaler_y_file', 'scaler_y.pkl')
        self.declare_parameter('window_size', 20)
        self.declare_parameter('num_features', 3)
        self.declare_parameter('auto_start', False)
        self.declare_parameter('clear_on_tracking_lost', 1.0)

        self.declare_parameter('model_files.rnn', 'rnn_velocity_3_layers.h5')
        self.declare_parameter('model_files.gru', 'gru_velocity_3_layers.h5')
        self.declare_parameter('model_files.lstm', 'lstm_velocity_3_layers.h5')

        self.model_dir = self.get_parameter('model_dir').value
        self.T = self.get_parameter('window_size').value
        self.num_features = self.get_parameter('num_features').value
        self.clear_timeout = self.get_parameter('clear_on_tracking_lost').value

        model_files = {
            'rnn': self.get_parameter('model_files.rnn').value,
            'gru': self.get_parameter('model_files.gru').value,
            'lstm': self.get_parameter('model_files.lstm').value,
        }

        # ---------- Zero-padded Buffer ----------
        self.buffer_np = np.zeros((self.T, self.num_features), dtype=np.float32)
        self.data_count = 0
        self.last_data_time = 0.0
        self.is_predicting = False

        # ---------- Inference Subprocess ----------
        self.worker_ready = False
        self.active_model_name = ''
        self.worker_proc = None
        self.worker_lock = threading.Lock()

        if self.model_dir and os.path.isdir(self.model_dir):
            self._start_worker(model_files)
        else:
            self.get_logger().warn(
                f'model_dir not set or does not exist: "{self.model_dir}"')

        # ---------- Publishers / Subscribers ----------
        self.pred_pub = self.create_publisher(HandPrediction, '/predicted_position', 10)
        self.status_pub = self.create_publisher(SystemStatus, '/system_status', 10)
        self.create_subscription(HandState, '/hand_position', self._on_hand_position, 10)

        # ---------- Services ----------
        self.create_service(SelectModel, '/predictor/select_model', self._srv_select_model)
        self.create_service(SetBool, '/predictor/toggle', self._srv_toggle)

        # ---------- Timer ----------
        self.create_timer(1.0, self._publish_status)

        # Stats
        self.inference_count = 0
        self.last_inference_ms = 0.0
        self._fps_counter = 0
        self._fps_last_time = time.time()
        self.fps = 0.0

        if self.get_parameter('auto_start').value:
            self.is_predicting = True

        self.get_logger().info('Trajectory Predictor node started (subprocess isolation)')

    def _start_worker(self, model_files):
        """Launch inference subprocess using VENV Python."""
        # Find the inference_worker.py script
        worker_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'inference_worker.py'
        )
        # Use venv Python executable for complete isolation
        venv_python = os.path.expanduser('~/Experiment/.venv/bin/python3')
        if not os.path.exists(venv_python):
            self.get_logger().error(f'Venv Python not found: {venv_python}')
            return

        env = os.environ.copy()
        env["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
        env["TF_ENABLE_ONEDNN_OPTS"] = "0"
        env["TF_CPP_MIN_LOG_LEVEL"] = "2"

        self.worker_proc = subprocess.Popen(
            [venv_python, worker_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1  # Line-buffered
        )

        # Send config as first line
        config = {
            "model_dir": self.model_dir,
            "model_files": {
                'rnn': self.get_parameter('model_files.rnn').value,
                'gru': self.get_parameter('model_files.gru').value,
                'lstm': self.get_parameter('model_files.lstm').value,
            },
            "scaler_x_file": self.get_parameter('scaler_x_file').value,
            "scaler_y_file": self.get_parameter('scaler_y_file').value,
            "default_model": self.get_parameter('default_model').value,
            "num_features": self.num_features,
            "window_size": self.T,
        }
        self._send_to_worker(config)

        # Start reader thread to process responses
        self._reader_thread = threading.Thread(target=self._read_worker_output, daemon=True)
        self._reader_thread.start()

        # Start stderr reader for debug logging
        self._stderr_thread = threading.Thread(target=self._read_worker_stderr, daemon=True)
        self._stderr_thread.start()

        self.get_logger().info(f'Inference worker launched with venv Python: {venv_python}')

    def _send_to_worker(self, data):
        """Send JSON command to worker stdin."""
        with self.worker_lock:
            if self.worker_proc and self.worker_proc.poll() is None:
                try:
                    line = json.dumps(data) + "\n"
                    self.worker_proc.stdin.write(line)
                    self.worker_proc.stdin.flush()
                except Exception as e:
                    self.get_logger().error(f'Send to worker failed: {e}')

    def _read_worker_output(self):
        """Background thread: read JSON responses from worker stdout."""
        while self.worker_proc and self.worker_proc.poll() is None:
            try:
                line = self.worker_proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                result = json.loads(line)
                self._handle_worker_result(result)
            except json.JSONDecodeError:
                continue
            except Exception:
                break
        self.get_logger().warn('Worker output reader stopped')

    def _read_worker_stderr(self):
        """Background thread: read stderr from worker for debugging."""
        while self.worker_proc and self.worker_proc.poll() is None:
            try:
                line = self.worker_proc.stderr.readline()
                if not line:
                    break
                # Only log important stderr lines
                line = line.strip()
                if line and not line.startswith('I0000') and not line.startswith('WARNING'):
                    self.get_logger().warn(f'[Worker] {line}')
            except Exception:
                break

    def _handle_worker_result(self, result):
        """Process a result from the inference worker."""
        msg_type = result.get("type")

        if msg_type == "ready":
            if result["success"]:
                self.worker_ready = True
                self.active_model_name = result.get("model_name", "")
                self.get_logger().info(
                    f'✓ Worker READY: {result["message"]} (model: {self.active_model_name})')
            else:
                self.get_logger().error(f'✗ Worker FAILED: {result["message"]}')

        elif msg_type == "model_loaded":
            self.active_model_name = result.get("model_name", "")
            self.worker_ready = True  # Signal that worker is free again
            if result["success"]:
                self._reset_buffer()
                self.get_logger().info(f'✓ Model switched → {self.active_model_name}')
            else:
                self.get_logger().warn(f'✗ Model switch failed: {result["message"]}')

        elif msg_type == "predict":
            pred = result.get("prediction")
            if pred is not None:
                pred_msg = HandPrediction()
                pred_msg.header.stamp = self.get_clock().now().to_msg()
                pred_msg.header.frame_id = 'kinect_world'
                
                # Inverse auto-center offset to return to Kinect raw space
                pred_msg.x = float(pred[0] - self.pos_offset[0])
                pred_msg.y = float(pred[2] - self.pos_offset[2])  # Swap back Z to Y
                pred_msg.z = float(pred[1] - self.pos_offset[1])  # Swap back Y to Z
                
                pred_msg.inference_time_ms = result.get("inference_ms", 0.0)
                pred_msg.model_name = result.get("model_name", self.active_model_name)
                pred_msg.buffer_size = self.data_count
                pred_msg.prediction_confidence = min(self.data_count / self.T, 1.0)
                self.pred_pub.publish(pred_msg)

                self.inference_count += 1
                self.last_inference_ms = result.get("inference_ms", 0.0)
                self._fps_counter += 1

    def _on_hand_position(self, msg: HandState):
        # SWAP Y and Z to match offline training frame
        swapped = np.array([msg.x, msg.z, msg.y])

        if self.data_count == 0:
            # First item! Auto-center to training setup origin [0.158, 0.028, 0.015]
            target_first = np.array([0.158, 0.028, 0.015])
            self.pos_offset = target_first - swapped
            
            swapped_centered = swapped + self.pos_offset
            self.buffer_np[:] = swapped_centered
        else:
            swapped_centered = swapped + self.pos_offset
            # Shift buffer left, insert new at end
            self.buffer_np = np.roll(self.buffer_np, -1, axis=0)
            self.buffer_np[-1] = swapped_centered
            
        self.data_count = min(self.data_count + 1, self.T)
        self.last_data_time = time.time()

        if not self.is_predicting or not self.worker_ready:
            return

        # Send prediction request to worker
        self._send_to_worker({
            "cmd": "predict",
            "data": self.buffer_np.tolist()
        })

    def _srv_select_model(self, request, response):
        if request.model_name == self.active_model_name:
            response.success = True
            response.message = f'Model already set to {request.model_name.upper()}'
            response.active_model = self.active_model_name
            return response

        if not self.worker_ready:
            response.success = False
            response.message = 'Inference worker not ready'
            response.active_model = ''
            return response

        self._send_to_worker({"cmd": "load_model", "model_name": request.model_name})

        # Wait for response with timeout
        deadline = time.time() + 5.0
        self.worker_ready = False  # Mark busy
        
        while time.time() < deadline:
            time.sleep(0.05)
            if self.worker_ready:
                break

        # Check if the switch to the REQUESTED model was successful
        response.success = (self.active_model_name == request.model_name and self.worker_ready)
        response.message = f'Model switched to {self.active_model_name.upper()}' if response.success else 'Model switch failed or timed out'
        response.active_model = self.active_model_name
        return response

    def _srv_toggle(self, request, response):
        self.is_predicting = request.data
        if not self.is_predicting:
            self._reset_buffer()
        state = 'ONLINE' if self.is_predicting else 'OFFLINE'
        response.success = True
        response.message = f'Prediction {state}'
        self.get_logger().info(f'Prediction {state}')
        return response

    def _reset_buffer(self):
        self.buffer_np.fill(0.0)
        self.data_count = 0

    def _publish_status(self):
        now = time.time()
        dt = now - self._fps_last_time
        if dt > 0:
            self.fps = self._fps_counter / dt
        self._fps_counter = 0
        self._fps_last_time = now

        if self.last_data_time > 0 and (now - self.last_data_time) > self.clear_timeout:
            if self.data_count > 0:
                self._reset_buffer()
                self.get_logger().warn('Tracking lost — buffer reset')

        status = SystemStatus()
        status.header.stamp = self.get_clock().now().to_msg()
        status.node_name = 'trajectory_predictor'
        status.fps = self.fps
        status.latency_ms = self.last_inference_ms

        if not self.worker_ready:
            status.status = 'error'
            status.message = 'Inference worker not ready'
        else:
            status.status = 'ok'
            pred_state = 'ON' if self.is_predicting else 'OFF'
            status.message = (
                f'Model: {self.active_model_name} | Predict: {pred_state} | '
                f'Buffer: {self.data_count}/{self.T} | Inf: {self.last_inference_ms:.1f}ms'
            )
        self.status_pub.publish(status)

    def destroy_node(self):
        if self.worker_proc and self.worker_proc.poll() is None:
            try:
                self._send_to_worker({"cmd": "shutdown"})
                self.worker_proc.wait(timeout=5.0)
            except Exception:
                self.worker_proc.kill()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TrajectoryPredictorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
