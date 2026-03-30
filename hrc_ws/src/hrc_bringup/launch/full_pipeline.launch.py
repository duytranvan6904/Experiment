#!/usr/bin/env python3
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():

    # ──── Global Environment Fix for TensorFlow/ROS conflict ────
    # Forces python-based protobuf to avoid C++ descriptor database crashes
    env_fix = SetEnvironmentVariable('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')

    # ──── Launch arguments ────
    model_dir_arg = DeclareLaunchArgument(
        'model_dir',
        default_value=os.path.expanduser('~/Downloads/GRU-Model-main'),
        description='Path to directory containing .h5 models and .pkl scalers'
    )

    tcp_port_arg = DeclareLaunchArgument(
        'tcp_port',
        default_value='9090',
        description='TCP port for Kinect C# app connection'
    )

    log_dir_arg = DeclareLaunchArgument(
        'log_dir',
        default_value=os.path.expanduser('~/hrc_logs'),
        description='Directory for experiment CSV logs'
    )

    # ──── Nodes ────

    bridge_node = Node(
        package='kinect_bridge',
        executable='bridge_node',
        name='kinect_bridge',
        output='screen',
        parameters=[{
            'tcp_host': '0.0.0.0',
            'tcp_port': LaunchConfiguration('tcp_port'),
            'connection_timeout': 5.0,
            'source_name': 'kinect_cam1',
        }],
    )

    predictor_node = Node(
        package='trajectory_predictor',
        executable='predictor_node',
        name='trajectory_predictor',
        output='screen',
        parameters=[{
            'model_dir': LaunchConfiguration('model_dir'),
            'default_model': 'gru',
            'scaler_x_file': 'scaler_x.pkl',
            'scaler_y_file': 'scaler_y.pkl',
            'window_size': 20,
            'num_features': 3,
            'auto_start': False,
            'clear_on_tracking_lost': 1.0,
            'model_files.rnn': 'rnn_velocity_3_layers.h5',
            'model_files.gru': 'gru_velocity_3_layers.h5',
            'model_files.lstm': 'lstm_velocity_3_layers.h5',
        }],
    )

    ui_node = Node(
        package='predictor_ui',
        executable='ui_node',
        name='predictor_ui',
        output='screen',
    )

    logger_node = Node(
        package='experiment_logger',
        executable='logger_node',
        name='experiment_logger',
        output='screen',
        parameters=[{
            'log_dir': LaunchConfiguration('log_dir'),
            'auto_start': True,
            'default_model': 'gru',
        }],
    )

    return LaunchDescription([
        env_fix,
        model_dir_arg,
        tcp_port_arg,
        log_dir_arg,
        bridge_node,
        predictor_node,
        ui_node,
        logger_node,
    ])
