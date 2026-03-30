#!/usr/bin/env python3
"""
Mock Kinect Sender — simulates the C# Kinect app sending hand position 
data over TCP. Used for testing the ROS 2 pipeline without the actual 
Kinect hardware.

Reads from test_trajectories.csv (if available) or generates synthetic 
circular trajectory data.

Usage:
  python3 mock_kinect_sender.py [--host UBUNTU_IP] [--port 9090] [--csv path_to_csv]
"""

import argparse
import json
import socket
import time
import os
import sys
import math

import numpy as np


def load_csv_trajectory(csv_path: str, sequence_length: int = 191):
    """Load trajectory data from CSV file (matches training format)."""
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, header=None)
        data = df.values[:sequence_length, :3]  # Take first trajectory, x/y/z
        return data.astype(float)
    except Exception as e:
        print(f"Could not load CSV: {e}")
        return None


def generate_synthetic_trajectory(n_points: int = 200, freq_hz: float = 20.0):
    """Generate a smooth synthetic 3D trajectory (figure-8 pattern)."""
    t = np.linspace(0, 4 * np.pi, n_points)
    x = 0.3 * np.sin(t) + 0.1 * np.random.randn(n_points) * 0.01
    y = 0.8 + 0.15 * np.sin(t * 0.5) + 0.1 * np.random.randn(n_points) * 0.01
    z = 1.2 + 0.2 * np.sin(2 * t) * np.cos(t) + 0.1 * np.random.randn(n_points) * 0.01
    return np.column_stack([x, y, z])


def main():
    parser = argparse.ArgumentParser(description='Mock Kinect TCP sender')
    parser.add_argument('--host', default='127.0.0.1', help='Ubuntu bridge host IP')
    parser.add_argument('--port', type=int, default=9090, help='TCP port')
    parser.add_argument('--csv', default='', help='Path to trajectory CSV file')
    parser.add_argument('--rate', type=float, default=20.0, help='Send rate in Hz')
    parser.add_argument('--loop', action='store_true', help='Loop trajectory continuously')
    args = parser.parse_args()

    # Load or generate trajectory
    traj = None
    if args.csv and os.path.exists(args.csv):
        traj = load_csv_trajectory(args.csv)
        if traj is not None:
            print(f"Loaded {len(traj)} points from {args.csv}")

    if traj is None:
        traj = generate_synthetic_trajectory(n_points=400)
        print(f"Using synthetic trajectory ({len(traj)} points)")

    # Connect to bridge
    print(f"Connecting to {args.host}:{args.port}...")
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((args.host, args.port))
            print("Connected!")
            break
        except ConnectionRefusedError:
            print("Connection refused — is bridge_node running? Retrying in 2s...")
            time.sleep(2.0)
        except Exception as e:
            print(f"Error: {e}. Retrying in 2s...")
            time.sleep(2.0)

    # Send loop
    interval = 1.0 / args.rate
    tracking_id = 42

    try:
        while True:
            for i, (x, y, z) in enumerate(traj):
                msg = {
                    "x": round(float(x), 6),
                    "y": round(float(y), 6),
                    "z": round(float(z), 6),
                    "id": tracking_id,
                    "ts": time.strftime('%Y-%m-%dT%H:%M:%S.') + f'{int(time.time()*1000)%1000:03d}Z',
                    "tracked": True,
                    "confidence": 1.0,
                }
                line = json.dumps(msg) + '\n'
                sock.sendall(line.encode('utf-8'))

                if (i + 1) % 50 == 0:
                    print(f"  Sent {i+1}/{len(traj)} — x={x:.3f}, y={y:.3f}, z={z:.3f}")

                time.sleep(interval)

            if not args.loop:
                print(f"Trajectory complete ({len(traj)} points sent)")
                break
            else:
                print("Looping trajectory...")

    except (BrokenPipeError, ConnectionResetError):
        print("Connection lost")
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        sock.close()
        print("Done")


if __name__ == '__main__':
    main()
