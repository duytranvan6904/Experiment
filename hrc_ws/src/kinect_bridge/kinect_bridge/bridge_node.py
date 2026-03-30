#!/usr/bin/env python3
"""
Kinect Bridge Node — TCP server that receives hand position JSON from
the Windows C# Kinect app and publishes to ROS 2 topic /hand_position.

Protocol: C# app connects via TCP and sends newline-delimited JSON:
  {"x": 0.342, "y": 0.891, "z": 1.205, "ts": "...", "id": 12345}
"""

import json
import socket
import threading
import time

import rclpy
from rclpy.node import Node
from human_hand_msgs.msg import HandPrediction, SystemStatus


class KinectBridgeNode(Node):
    """Receives TCP data from Windows Kinect C# app, publishes HandPrediction."""

    def __init__(self):
        super().__init__('kinect_bridge')

        # Parameters
        self.declare_parameter('tcp_host', '0.0.0.0')
        self.declare_parameter('tcp_port', 9090)
        self.declare_parameter('connection_timeout', 5.0)
        self.declare_parameter('source_name', 'kinect_cam1')

        self.tcp_host = self.get_parameter('tcp_host').value
        self.tcp_port = self.get_parameter('tcp_port').value
        self.timeout = self.get_parameter('connection_timeout').value
        self.source_name = self.get_parameter('source_name').value

        # Publishers
        # CHANGED: Publish directly to /predicted_position with HandPrediction message
        self.pred_pub = self.create_publisher(HandPrediction, '/predicted_position', 10)
        self.status_pub = self.create_publisher(SystemStatus, '/system_status', 10)

        # Status tracking
        self.connected = False
        self.frame_count = 0
        self.last_receive_time = 0.0
        self.fps = 0.0
        self._fps_counter = 0
        self._fps_last_time = time.time()

        # Status timer (publish system status every 1s)
        self.create_timer(1.0, self._publish_status)

        # Start TCP server in background thread
        self._tcp_thread = threading.Thread(target=self._tcp_server_loop, daemon=True)
        self._tcp_thread.start()

        self.get_logger().info(
            f'Kinect Bridge started — listening on {self.tcp_host}:{self.tcp_port}'
        )

    def _tcp_server_loop(self):
        """Background thread: accept TCP connections and read data."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.tcp_host, self.tcp_port))
        server_sock.listen(1)
        server_sock.settimeout(2.0)  # So we can check rclpy.ok()

        self.get_logger().info(f'TCP server listening on port {self.tcp_port}...')

        while rclpy.ok():
            try:
                client_sock, addr = server_sock.accept()
                self.get_logger().info(f'Client connected from {addr}')
                self.connected = True
                self._handle_client(client_sock)
                self.connected = False
                self.get_logger().warn(f'Client {addr} disconnected')
            except socket.timeout:
                continue
            except Exception as e:
                self.get_logger().error(f'TCP server error: {e}')
                time.sleep(1.0)

        server_sock.close()

    def _handle_client(self, client_sock: socket.socket):
        """Read newline-delimited JSON from client, publish to ROS 2."""
        client_sock.settimeout(self.timeout)
        buffer = ''

        while rclpy.ok():
            try:
                data = client_sock.recv(4096)
                if not data:
                    break  # Client disconnected

                buffer += data.decode('utf-8', errors='replace')

                # Process complete JSON lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._process_json(line)

            except socket.timeout:
                # Check if connection is still alive
                now = time.time()
                if self.last_receive_time > 0 and (now - self.last_receive_time) > self.timeout:
                    self.get_logger().warn('Connection timeout — no data received')
                continue
            except ConnectionResetError:
                break
            except Exception as e:
                self.get_logger().error(f'Receive error: {e}')
                break

        try:
            client_sock.close()
        except Exception:
            pass

    def _process_json(self, json_str: str):
        """Parse JSON and publish HandPrediction message."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f'Invalid JSON: {e}')
            return

        msg = HandPrediction()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'kinect_world'
        msg.x = float(data.get('x', 0.0))
        msg.y = float(data.get('y', 0.0))
        msg.z = float(data.get('z', 0.0))
        msg.inference_time_ms = float(data.get('inference_ms', 0.0))
        msg.model_name = data.get('model_name', 'unknown')
        msg.prediction_confidence = float(data.get('confidence', 1.0))

        self.pred_pub.publish(msg)

        # Update stats
        self.last_receive_time = time.time()
        self.frame_count += 1
        self._fps_counter += 1

    def _publish_status(self):
        """Periodically publish system status."""
        now = time.time()
        dt = now - self._fps_last_time
        if dt > 0:
            self.fps = self._fps_counter / dt
        self._fps_counter = 0
        self._fps_last_time = now

        status = SystemStatus()
        status.header.stamp = self.get_clock().now().to_msg()
        status.node_name = 'kinect_bridge'
        status.fps = self.fps
        status.latency_ms = 0.0

        now = time.time()
        
        # Debounce the connection drop by 2 seconds to fix GUI flickering
        is_actually_connected = self.connected or (now - self.last_receive_time < 2.0)

        if is_actually_connected:
            status.status = 'ok'
            status.message = f'Connected | FPS: {self.fps:.1f} | Frames: {self.frame_count}'
        else:
            status.status = 'warning'
            status.message = 'Waiting for Kinect C# app connection...'

        self.status_pub.publish(status)


def main(args=None):
    rclpy.init(args=args)
    node = KinectBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
