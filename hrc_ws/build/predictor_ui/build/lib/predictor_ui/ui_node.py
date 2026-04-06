#!/usr/bin/env python3
"""
Predictor UI Node — PyQt5 dashboard with 3 real-time trajectory plots
(X, Y, Z) showing measured vs predicted hand positions, model selector,
start/stop controls, and system status.

Uses matplotlib embedded in PyQt5 with FigureCanvasQTAgg for smooth
scrolling plots. ROS 2 spinning is done via a QTimer to avoid blocking.

Author: Duy (auto-generated — extend as needed)
"""

import sys
import time
from collections import deque
from threading import Lock

import numpy as np
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool

from human_hand_msgs.msg import HandState, HandPrediction, SystemStatus
from human_hand_msgs.srv import SelectModel

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QRadioButton, QButtonGroup, QGroupBox,
    QTextEdit, QFrame, QSplitter, QSizePolicy
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QColor

# Matplotlib imports for embedding
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
PLOT_WINDOW = 200     # Number of samples to display (~10s at 20Hz)
UI_REFRESH_MS = 50    # UI update interval in ms (20 FPS for plots)
ROS_SPIN_MS = 10      # rclpy spin interval


class RealtimePlotCanvas(FigureCanvas):
    """Embedded matplotlib canvas for a single axis (X, Y, or Z)."""

    def __init__(self, title: str, ylabel: str, parent=None):
        self.fig = Figure(figsize=(5, 2), dpi=100)
        self.fig.set_facecolor('#1e1e2e')
        super().__init__(self.fig)
        self.setParent(parent)

        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e2e')
        self.ax.set_title(title, color='#cdd6f4', fontsize=11, fontweight='bold')
        self.ax.set_ylabel(ylabel, color='#cdd6f4', fontsize=9)
        self.ax.tick_params(colors='#6c7086', labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color('#45475a')
        self.ax.grid(True, alpha=0.2, color='#585b70')

        # Data buffers
        self.measured_data = deque(maxlen=PLOT_WINDOW)
        self.predicted_data = deque(maxlen=PLOT_WINDOW)

        # Plot lines
        self.line_measured, = self.ax.plot([], [], color='#a6e3a1', linewidth=1.5,
                                           label='Measured', alpha=0.9)
        self.line_predicted, = self.ax.plot([], [], color='#f38ba8', linewidth=1.5,
                                            label='Predicted', linestyle='--', alpha=0.9)
        self.ax.legend(loc='upper right', fontsize=7, facecolor='#313244',
                       edgecolor='#45475a', labelcolor='#cdd6f4')

        self.fig.tight_layout(pad=1.5)

    def clear_plot(self):
        """Clear all data from buffers and reset lines."""
        self.measured_data.clear()
        self.predicted_data.clear()
        self.line_measured.set_data([], [])
        self.line_predicted.set_data([], [])
        self.draw_idle()

    def update_plot(self):
        """Redraw the plot with current data."""
        n_m = len(self.measured_data)
        n_p = len(self.predicted_data)

        if n_m > 0:
            x_m = np.arange(n_m)
            self.line_measured.set_data(x_m, list(self.measured_data))
        if n_p > 0:
            # Align predicted to the right side of measured
            x_p = np.arange(n_m - n_p, n_m) if n_p <= n_m else np.arange(n_p)
            self.line_predicted.set_data(x_p, list(self.predicted_data))

        if n_m > 0 or n_p > 0:
            all_vals = list(self.measured_data) + list(self.predicted_data)
            if all_vals:
                vmin, vmax = min(all_vals), max(all_vals)
                margin = max(abs(vmax - vmin) * 0.1, 0.01)
                self.ax.set_ylim(vmin - margin, vmax + margin)
            self.ax.set_xlim(0, max(n_m, PLOT_WINDOW))

        self.draw_idle()


class PredictorDashboard(QMainWindow):
    """Main PyQt5 dashboard window."""

    def __init__(self, ros_node: 'PredictorUINode'):
        super().__init__()
        self.ros_node = ros_node
        self.setWindowTitle('Human-Robot Collaboration — Trajectory Predictor')
        self.setMinimumSize(1100, 750)
        self.setStyleSheet(self._stylesheet())

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ──── Left: Plots ────
        plot_layout = QVBoxLayout()
        plot_layout.setSpacing(4)

        self.plot_x = RealtimePlotCanvas('Trajectory X vs Time', 'X (m)')
        self.plot_y = RealtimePlotCanvas('Trajectory Y vs Time', 'Y (m)')
        self.plot_z = RealtimePlotCanvas('Trajectory Z vs Time', 'Z (m)')

        for p in [self.plot_x, self.plot_y, self.plot_z]:
            p.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            plot_layout.addWidget(p)

        main_layout.addLayout(plot_layout, stretch=3)

        # ──── Right: Controls Panel ────
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)

        # Model selector
        model_group = QGroupBox('Model Selection')
        model_layout = QVBoxLayout()
        self.model_btn_group = QButtonGroup()
        self.radio_gru = QRadioButton('GRU')
        self.radio_rnn = QRadioButton('RNN')
        self.radio_lstm = QRadioButton('LSTM')
        self.radio_gru.setChecked(True)
        for i, rb in enumerate([self.radio_gru, self.radio_rnn, self.radio_lstm]):
            self.model_btn_group.addButton(rb, i)
            model_layout.addWidget(rb)
        self.model_btn_group.buttonClicked.connect(self._on_model_selected)
        model_group.setLayout(model_layout)
        right_panel.addWidget(model_group)

        # Start/Stop buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton('▶  Start')
        self.btn_start.setObjectName('startBtn')
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop = QPushButton('⏹  Stop')
        self.btn_stop.setObjectName('stopBtn')
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_reset = QPushButton('Reset')
        self.btn_reset.setObjectName('resetBtn')
        self.btn_reset.clicked.connect(self._on_reset)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_reset)
        right_panel.addLayout(btn_layout)

        # Measured position display
        meas_group = QGroupBox('📍 Measured Position')
        meas_layout = QVBoxLayout()
        self.lbl_meas_x = QLabel('X: —')
        self.lbl_meas_y = QLabel('Y: —')
        self.lbl_meas_z = QLabel('Z: —')
        for lbl in [self.lbl_meas_x, self.lbl_meas_y, self.lbl_meas_z]:
            lbl.setFont(QFont('Monospace', 11))
            meas_layout.addWidget(lbl)
        meas_group.setLayout(meas_layout)
        right_panel.addWidget(meas_group)

        # Predicted position display
        pred_group = QGroupBox('🎯 Predicted Position')
        pred_layout = QVBoxLayout()
        self.lbl_pred_x = QLabel('X: —')
        self.lbl_pred_y = QLabel('Y: —')
        self.lbl_pred_z = QLabel('Z: —')
        for lbl in [self.lbl_pred_x, self.lbl_pred_y, self.lbl_pred_z]:
            lbl.setFont(QFont('Monospace', 11))
            pred_layout.addWidget(lbl)
        pred_group.setLayout(pred_layout)
        right_panel.addWidget(pred_group)

        # Status panel
        status_group = QGroupBox('System Status')
        status_layout = QVBoxLayout()
        self.lbl_status = QLabel('● Waiting...')
        self.lbl_model = QLabel('Model: —')
        self.lbl_buffer = QLabel('Buffer: 0/20')
        self.lbl_inference = QLabel('Inference: —')
        self.lbl_fps = QLabel('FPS: —')
        for lbl in [self.lbl_status, self.lbl_model, self.lbl_buffer,
                     self.lbl_inference, self.lbl_fps]:
            status_layout.addWidget(lbl)
        status_group.setLayout(status_layout)
        right_panel.addWidget(status_group)

        right_panel.addStretch()

        # Log area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(80)
        self.log_text.setFont(QFont('Monospace', 8))
        right_panel.addWidget(QLabel('Event Log'))
        right_panel.addWidget(self.log_text)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setFixedWidth(280)
        main_layout.addWidget(right_widget)

        # ──── Timers ────
        # UI refresh timer (update plots)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self._update_ui)
        self.ui_timer.start(UI_REFRESH_MS)

        # ROS spin timer
        self.ros_timer = QTimer()
        self.ros_timer.timeout.connect(self._spin_ros)
        self.ros_timer.start(ROS_SPIN_MS)

        self._add_log('Dashboard initialized')

    def _stylesheet(self):
        return """
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #cdd6f4; font-family: 'Segoe UI', 'Ubuntu', sans-serif; font-size: 10pt; }
            QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 10px;
                         padding: 10px 6px 6px 6px; font-weight: bold; color: #89b4fa; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; border-radius: 4px;
                          padding: 8px 16px; color: #cdd6f4; font-weight: bold; }
            QPushButton:hover { background-color: #45475a; }
            QPushButton#startBtn { background-color: #1e6f50; border-color: #a6e3a1; }
            QPushButton#startBtn:hover { background-color: #a6e3a1; color: #1e1e2e; }
            QPushButton#stopBtn { background-color: #6e2030; border-color: #f38ba8; }
            QPushButton#stopBtn:hover { background-color: #f38ba8; color: #1e1e2e; }
            QPushButton#resetBtn { background-color: #313244; border-color: #fab387; }
            QPushButton#resetBtn:hover { background-color: #fab387; color: #1e1e2e; }
            QRadioButton { spacing: 6px; padding: 3px; }
            QRadioButton::indicator { width: 14px; height: 14px; }
            QTextEdit { background-color: #181825; border: 1px solid #45475a; border-radius: 4px;
                        color: #a6adc8; }
            QLabel { color: #cdd6f4; }
        """

    def _add_log(self, message: str):
        timestamp = time.strftime('%H:%M:%S')
        self.log_text.append(f'[{timestamp}] {message}')
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_model_selected(self, button):
        model_map = {self.radio_rnn: 'rnn', self.radio_gru: 'gru', self.radio_lstm: 'lstm'}
        model_name = model_map.get(button, 'gru')
        self._add_log(f'Switching model to {model_name.upper()}...')
        self.ros_node.call_select_model(model_name)

    def _on_start(self):
        self._add_log('Starting prediction...')
        self.plot_x.clear_plot()
        self.plot_y.clear_plot()
        self.plot_z.clear_plot()
        self.ros_node.is_plotting = True
        self.ros_node.call_toggle(True)

    def _on_stop(self):
        self._add_log('Stopping prediction...')
        self.ros_node.is_plotting = False
        self.ros_node.call_toggle(False)

    def _on_reset(self):
        self._add_log('Resetting trajectory plots...')
        self.clear_plots()

    def clear_plots(self):
        self.plot_x.clear_plot()
        self.plot_y.clear_plot()
        self.plot_z.clear_plot()

    def _update_ui(self):
        """Called by QTimer — update plots and labels from ROS data."""
        node = self.ros_node

        with node.data_lock:
            # Update measured labels
            if node.last_measured is not None:
                mx, my, mz = node.last_measured
                self.lbl_meas_x.setText(f'X: {mx:.4f}')
                self.lbl_meas_y.setText(f'Y: {my:.4f}')
                self.lbl_meas_z.setText(f'Z: {mz:.4f}')

            # Update predicted labels
            if node.last_predicted is not None:
                px, py, pz = node.last_predicted
                self.lbl_pred_x.setText(f'X: {px:.4f}')
                self.lbl_pred_y.setText(f'Y: {py:.4f}')
                self.lbl_pred_z.setText(f'Z: {pz:.4f}')

            # Update status
            self.lbl_model.setText(f'Model: {node.active_model.upper()}')
            self.lbl_buffer.setText(f'Buffer: {node.buffer_size}/20')
            self.lbl_inference.setText(f'Inference: {node.inference_ms:.1f}ms')
            self.lbl_fps.setText(f'FPS: {node.pred_fps:.1f}')

            # Stabilize status: if we got data in the last 2 seconds, we are connected
            is_live = (time.time() - node.last_hand_time < 2.0)
            
            if node.bridge_connected or is_live:
                self.lbl_status.setText('● Connected')
                self.lbl_status.setStyleSheet('color: #a6e3a1; font-weight: bold;')
            else:
                self.lbl_status.setText('○ Disconnected')
                self.lbl_status.setStyleSheet('color: #f38ba8; font-weight: bold;')

        # Update plots
        self.plot_x.update_plot()
        self.plot_y.update_plot()
        self.plot_z.update_plot()

    def _spin_ros(self):
        """Called by QTimer — spin ROS 2 node to process callbacks."""
        try:
            rclpy.spin_once(self.ros_node, timeout_sec=0)
        except Exception:
            pass


class PredictorUINode(Node):
    """ROS 2 node for UI — subscribes to topics, calls services."""

    def __init__(self):
        super().__init__('predictor_ui')

        self.data_lock = Lock()

        # Shared data (written by callbacks, read by UI thread)
        self.last_measured = None       # (x, y, z)
        self.last_predicted = None      # (x, y, z)
        self.active_model = 'gru'
        self.buffer_size = 0
        self.inference_ms = 0.0
        self.pred_fps = 0.0
        self.bridge_connected = False
        self.last_hand_time = 0.0
        self.is_plotting = False

        # Plot data references (will be set by dashboard)
        self.dashboard = None

        # Subscribers
        self.create_subscription(HandState, '/hand_position', self._on_hand, 10)
        self.create_subscription(HandPrediction, '/predicted_position', self._on_prediction, 10)
        self.create_subscription(SystemStatus, '/system_status', self._on_status, 10)

        # Service clients
        self.select_model_cli = self.create_client(SelectModel, '/predictor/select_model')
        self.toggle_cli = self.create_client(SetBool, '/predictor/toggle')
        self.toggle_logger_cli = self.create_client(SetBool, '/logger/toggle')

    def set_dashboard(self, dashboard: PredictorDashboard):
        self.dashboard = dashboard

    def _on_hand(self, msg: HandState):
        with self.data_lock:
            self.last_measured = (msg.x, msg.y, msg.z)
            self.last_hand_time = time.time()

        if self.is_plotting and self.dashboard:
            self.dashboard.plot_x.measured_data.append(msg.x)
            self.dashboard.plot_y.measured_data.append(msg.y)
            self.dashboard.plot_z.measured_data.append(msg.z)

    def _on_prediction(self, msg: HandPrediction):
        with self.data_lock:
            self.last_predicted = (msg.x, msg.y, msg.z)
            self.active_model = msg.model_name
            self.buffer_size = msg.buffer_size
            self.inference_ms = msg.inference_time_ms

        if self.is_plotting and self.dashboard:
            self.dashboard.plot_x.predicted_data.append(msg.x)
            self.dashboard.plot_y.predicted_data.append(msg.y)
            self.dashboard.plot_z.predicted_data.append(msg.z)

    def _on_status(self, msg: SystemStatus):
        with self.data_lock:
            if msg.node_name == 'kinect_bridge':
                self.bridge_connected = (msg.status == 'ok')
            elif msg.node_name == 'trajectory_predictor':
                self.pred_fps = msg.fps

    def call_select_model(self, model_name: str):
        if not self.select_model_cli.wait_for_service(timeout_sec=1.0):
            if self.dashboard:
                self.dashboard._add_log('⚠ Predictor service not available')
            return
        req = SelectModel.Request()
        req.model_name = model_name
        future = self.select_model_cli.call_async(req)
        future.add_done_callback(self._model_response)

    def _model_response(self, future):
        try:
            resp = future.result()
            if self.dashboard:
                if resp.success:
                    self.dashboard._add_log(f'✓ Model → {resp.active_model.upper()}')
                    self.dashboard.clear_plots()
                else:
                    self.dashboard._add_log(f'✗ Model switch failed: {resp.message}')
        except Exception as e:
            if self.dashboard:
                self.dashboard._add_log(f'✗ Service error: {e}')

    def call_toggle(self, start: bool):
        req = SetBool.Request()
        req.data = start

        if not self.toggle_cli.wait_for_service(timeout_sec=1.0):
            if self.dashboard:
                self.dashboard._add_log('⚠ Predictor toggle service not available')
        else:
            future = self.toggle_cli.call_async(req)
            future.add_done_callback(self._toggle_response)

        if not self.toggle_logger_cli.wait_for_service(timeout_sec=1.0):
            if self.dashboard:
                self.dashboard._add_log('⚠ Logger toggle service not available')
        else:
            future = self.toggle_logger_cli.call_async(req)
            future.add_done_callback(self._toggle_response)

    def _toggle_response(self, future):
        try:
            resp = future.result()
            if self.dashboard:
                self.dashboard._add_log(f'✓ {resp.message}')
        except Exception as e:
            if self.dashboard:
                self.dashboard._add_log(f'✗ Toggle error: {e}')


def main(args=None):
    rclpy.init(args=args)

    # Create ROS node
    node = PredictorUINode()

    # Create Qt app and dashboard
    app = QApplication(sys.argv)
    dashboard = PredictorDashboard(node)
    node.set_dashboard(dashboard)
    dashboard.show()

    # Run Qt event loop (ROS spinning happens via QTimer inside dashboard)
    exit_code = app.exec_()

    # Cleanup
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
