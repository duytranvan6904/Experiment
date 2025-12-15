You are an expert C# / WPF developer specialized in Kinect v2, Human Motion Capture, and Human-Human Co-Manipulation experiments.

I want you to help me build a modular Visual Studio WPF project for collecting human hand trajectory data using TWO Kinect v2 cameras in a co-manipulation task.

====================================================
PROJECT OVERVIEW
====================================================
- Two Kinect v2 cameras placed opposite each other (~4–5 meters apart)
- Cameras face the center of a shared workspace
- Two humans carry an object together to a target
- We only record the trajectory of ONE selected participant
- Data will be used for later trajectory learning (GRU / HRI)

====================================================
TECH STACK & CONSTRAINTS
====================================================
- Language: C#
- Framework: WPF (.NET)
- SDK: Microsoft Kinect v2 SDK
- Coordinate mapping: CameraSpace, ColorSpace, DepthSpace
- Frame rate: 20 Hz (configurable)
- Output: CSV files
- UI: WPF (Canvas + Panels)
- No external middleware (no ROS here)

====================================================
MODULE BREAKDOWN (IMPORTANT)
====================================================

---------------------------------
1) SENSOR MODULE
---------------------------------
Create a KinectManager class that:
- Supports Kinect v2
- Initializes BodyFrame, ColorFrame, DepthFrame
- Tracks multiple bodies
- Selects the FIRST detected body and locks onto it
- Extracts hand joint positions (HandLeft, HandRight)
- Exposes CameraSpace coordinates

---------------------------------
2) FLOOR DETECTION
---------------------------------
Use Kinect SDK floor plane detection:
- Extract floor plane equation (Ax + By + Cz + D = 0)
- Compute floor normal
- Define Oy axis as perpendicular to the floor
- Ensure Ox–Oz plane is parallel to the floor

---------------------------------
3) TARGET / MARKER DETECTION
---------------------------------
Using ColorFrame:
- Detect a colored marker (ColorBasis)
- Marker represents the target position
- Allow manual override (user input XYZ in UI)
- Expose target position in CameraSpace

---------------------------------
4) COORDINATE CALIBRATION
---------------------------------
Implement a CoordinateTransformer module:
- Convert from Kinect CameraSpace to WorldSpace
- World origin = detected (or manually input) target
- Oy ⟂ floor
- Oz aligned with depth direction
- Ox ⟂ (Oy, Oz)
- Handle TWO cameras facing each other:
    - Camera A = MASTER
    - Camera B = CLIENT
    - Camera B must transform into Camera A world frame
    - Ox and Oz inversion must be handled explicitly
- UI must allow:
    - Manual translation offsets
    - Manual rotation adjustments
    - Per-camera calibration profiles

---------------------------------
5) SMOOTHING / FILTERING
---------------------------------
Integrate motion smoothing based on:
https://github.com/intelligent-control-lab/Kinect_Smoothing

- Implement:
    - Exponential smoothing
    - Double exponential smoothing
- Filter must be applied BEFORE logging
- Filter parameters configurable via UI

---------------------------------
6) TRAJECTORY TRACKING & LOGGING
---------------------------------
Create a TrajectoryRecorder:
- Records at fixed rate (20 Hz, adjustable)
- Records:
    timestamp,
    x, y, z (world frame),
    joint type,
    movement mode,
    target ID
- Stops recording when:
    - Max time reached
    - Max frame count reached
- Saves CSV automatically

---------------------------------
7) MOVEMENT MODES (UI CONTROLLED)
---------------------------------
Support 4 experiment modes:
1) Free movement
2) Obstacle
3) Free + Change target
4) Obstacle + Change target

UI must allow selecting:
- Mode
- Target ID (1–3)
- Max recording time
- Max frame count

---------------------------------
8) USER INTERFACE (WPF)
---------------------------------
MainWindow layout:
- Color camera view
- Skeleton overlay (Canvas)
- Highlight tracked participant
- Display live XYZ coordinates
- Display current mode / target
- Buttons:
    Start Recording
    Stop Recording
    Calibrate
    Save
- Status indicators:
    Kinect connected
    Body tracked
    Recording active

---------------------------------
9) CODE QUALITY
---------------------------------
- Use MVVM where reasonable
- Separate logic from UI
- Use clear class names
- Add comments explaining math & transformations
- Make it easy to extend to 3D visualization later

====================================================
EXPECTED OUTPUT
====================================================
- Clean, modular C# WPF project
- Each module in its own class
- Clear calibration math
- Reliable trajectory CSV for human-human co-manipulation research

Start by generating:
1) Project structure
2) MainWindow.xaml layout
3) KinectManager.cs
