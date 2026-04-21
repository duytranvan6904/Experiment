# Project Summary: Kinect Co-Carrying Trajectory Prediction

## Overview
This project is an end-to-end framework for human-human co-manipulation experiments, specifically focusing on capturing and predicting human hand trajectory data using two Kinect v2 cameras. The stored data and real-time predictions can be utilized for Human-Robot Interaction (HRI) robotics.

## Architecture & Progress
The system is divided into two major components: a Windows-based Data Collection Application and a Linux-based ROS 2 pipeline.

### 1. Windows C# / WPF Application (Data Collection)
- **Status:** Implemented (`/home/duy/Experiment/`)
- **Key Modules:**
  - `KinectManager`: Interfaces with Kinect v2 SDK, tracks multiple bodies, and extracts HandLeft/HandRight positions.
  - `CoordinateTransformer`: Transforms CameraSpace to WorldSpace and handles Master-Client calibration for the dual-camera setup.
  - `TrajectoryRecorder` / `TcpHandPublisher`: Records trajectory at a fixed rate (e.g., 20 Hz) and streams it over TCP for real-time ROS 2 consumption.
  - **Outputs:** CSV logs for offline training and a local WPF UI overlay for visualization.

### 2. ROS 2 Workspace (`hrc_ws`)
- **Status:** Implemented (`/home/duy/Experiment/hrc_ws/`)
- **Key Packages:**
  - `kinect_bridge`: Acts as a TCP client connecting to the Windows WPF app and publishes the data to ROS 2 topics.
  - `human_hand_msgs`: Defines the custom ROS interfaces (messages and services) for hand tracking.
  - `trajectory_predictor`: Contains the ML inference node (built for models like RNN/GRU/LSTM) that subscribes to the trajectory data and predicts future hand movements.
  - `predictor_ui`: A PyQt5-based real-time dashboard to visualize the incoming measured data versus the predicted trajectory.
  - `experiment_logger`: Logs both the measured and predicted trajectories into an aggregated CSV file.
  - `hrc_bringup`: Contains launch files to start the entire pipeline (`full_pipeline.launch.py`).

## Usage Instructions

### 1. Start the Windows Data Collector
- Ensure the Kinect v2 sensors are connected.
- Open the `.sln` solution in Visual Studio or run the compiled `KinectRecorder.exe` on Windows 10.
- Use the UI to select the participant, set the movement mode, and click **Start Recording**. The system will begin broadcasting the hand positions via TCP.

### 2. Run the ROS 2 Pipeline (Linux)
- Navigate to the `hrc_ws` workspace and source the build environment:
  ```bash
  cd /home/duy/Experiment/hrc_ws
  colcon build
  source install/setup.bash
  ```
- Launch the full tracking and prediction pipeline:
  ```bash
  ros2 launch hrc_bringup full_pipeline.launch.py
  ```
- This command brings up the `kinect_bridge` (to receive data), the `trajectory_predictor` (for ML inference), the `predictor_ui` (for dashboard visualization), and the `experiment_logger`.

## Future Work
- Tuning and integrating trained GRU/LSTM models into `trajectory_predictor`.
- Fine-tuning the filtering and coordinate transformation between the two Kinects for optimal accuracy.
