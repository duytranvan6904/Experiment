//------------------------------------------------------------------------------
// <copyright file="MainWindow.xaml.cs" company="Microsoft">
//     Copyright (c) Microsoft Corporation.  All rights reserved.
// </copyright>
//------------------------------------------------------------------------------

namespace Microsoft.Samples.Kinect.BodyBasics
{
    using System;
    using System.Collections.Generic;
    using System.ComponentModel;
    using System.Diagnostics;
    using System.Globalization;
    using System.IO;
    using System.Windows;
    using System.Windows.Media;
    using System.Windows.Media.Imaging;
    using Microsoft.Kinect;
    using System.Timers;
    using System.Windows.Threading;
    using System.Numerics;
    using System.Net.Sockets;
    using System.Text;

    /// <summary>
    /// Interaction logic for MainWindow
    /// </summary>
    public partial class MainWindow : Window, INotifyPropertyChanged
    {
        /// <summary>
        /// Radius of drawn hand circles
        /// </summary>
        private const double HandSize = 30;

        /// <summary>
        /// Thickness of drawn joint lines
        /// </summary>
        private const double JointThickness = 3;

        /// <summary>
        /// Thickness of clip edge rectangles
        /// </summary>
        private const double ClipBoundsThickness = 10;

        /// <summary>
        /// Constant for clamping Z values of camera space points from being negative
        /// </summary>
        private const float InferredZPositionClamp = 0.1f;

        /// <summary>
        /// Brush used for drawing hands that are currently tracked as closed
        /// </summary>
        private readonly Brush handClosedBrush = new SolidColorBrush(Color.FromArgb(128, 255, 0, 0));

        /// <summary>
        /// Brush used for drawing hands that are currently tracked as opened
        /// </summary>
        private readonly Brush handOpenBrush = new SolidColorBrush(Color.FromArgb(128, 0, 255, 0));

        /// <summary>
        /// Brush used for drawing hands that are currently tracked as in lasso (pointer) position
        /// </summary>
        private readonly Brush handLassoBrush = new SolidColorBrush(Color.FromArgb(128, 0, 0, 255));

        /// <summary>
        /// Brush used for drawing joints that are currently tracked
        /// </summary>
        private readonly Brush trackedJointBrush = new SolidColorBrush(Color.FromArgb(255, 68, 192, 68));

        /// <summary>
        /// Brush used for drawing joints that are currently inferred
        /// </summary>        
        private readonly Brush inferredJointBrush = Brushes.Yellow;

        /// <summary>
        /// Pen used for drawing bones that are currently inferred
        /// </summary>        
        private readonly Pen inferredBonePen = new Pen(Brushes.Gray, 1);

        /// <summary>
        /// Drawing group for body rendering output
        /// </summary>
        private DrawingGroup drawingGroup;

        /// <summary>
        /// Drawing image that we will display
        /// </summary>
        private DrawingImage imageSource;

        /// <summary>
        /// Active Kinect sensor
        /// </summary>
        private KinectSensor kinectSensor = null;

        /// <summary>
        /// Coordinate mapper to map one type of point to another
        /// </summary>
        private CoordinateMapper coordinateMapper = null;

        /// <summary>
        /// Reader for body frames
        /// </summary>
        private BodyFrameReader bodyFrameReader = null;

        /// <summary>
        /// Array for the bodies
        /// </summary>
        private Body[] bodies = null;

        /// <summary>
        /// definition of bones
        /// </summary>
        private List<Tuple<JointType, JointType>> bones;

        /// <summary>
        /// Width of display (depth space)
        /// </summary>
        private int displayWidth;

        /// <summary>
        /// Height of display (depth space)
        /// </summary>
        private int displayHeight;

        /// <summary>
        /// List of colors for each body tracked
        /// </summary>
        private List<Pen> bodyColors;

        /// <summary>
        /// Current status text to display
        /// </summary>
        private string statusText = null;

        // Add new fields for manager, transformer and recorder
        private KinectManager kinectManager;
        private CoordinateTransformer transformer;
        private TrajectoryRecorder recorder; // remains cam1 recorder
        private TrajectoryRecorder recorderCam2;
        private Timer samplingTimer;

        // Dual-camera additions
        private DualCameraCalibrationManager calibManager;
        private KinectSensorWrapper cam1Wrapper;
        private KinectSensorWrapper cam2Wrapper;

        // last raw (camera-space) and calibrated world-space points per camera
        private CameraSpacePoint lastRawCam1;
        private CameraSpacePoint lastRawCam2;
        private CameraSpacePoint lastWorldCam1;
        private CameraSpacePoint lastWorldCam2;

        private bool cam1Calibrated = false;
        private bool cam2Calibrated = false;

        // preferred recorder target set when calibrating a specific camera ("Cam1" or "Cam2").
        // If null/empty, Start will open both recorders (legacy behavior).
        private string preferredRecorderTarget = null;

        // store last seen hand positions
        private CameraSpacePoint lastLeftHand;
        private CameraSpacePoint lastRightHand;
        private ulong? lastTrackingId;

        // experiment params
        private int currentMode = 1; // 1..4
        private int currentTargetId = 1;

        // Add UI timer for countdown
        private DispatcherTimer uiTimer;

        // ROS TCP Connection
        private TcpClient rosClient;
        private StreamWriter rosWriter;

        /// <summary>
        /// Initializes a new instance of the MainWindow class.
        /// </summary>
        public MainWindow()
        {
            // one sensor is currently supported
            this.kinectSensor = KinectSensor.GetDefault();

            // get the coordinate mapper
            this.coordinateMapper = this.kinectSensor.CoordinateMapper;

            // get the depth (display) extents
            FrameDescription frameDescription = this.kinectSensor.DepthFrameSource.FrameDescription;

            // get size of joint space
            this.displayWidth = frameDescription.Width;
            this.displayHeight = frameDescription.Height;

            // open the reader for the body frames
            this.bodyFrameReader = this.kinectSensor.BodyFrameSource.OpenReader();

            // a bone defined as a line between two joints
            this.bones = new List<Tuple<JointType, JointType>>();

            // Torso
            this.bones.Add(new Tuple<JointType, JointType>(JointType.Head, JointType.Neck));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.Neck, JointType.SpineShoulder));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.SpineShoulder, JointType.SpineMid));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.SpineMid, JointType.SpineBase));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.SpineShoulder, JointType.ShoulderRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.SpineShoulder, JointType.ShoulderLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.SpineBase, JointType.HipRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.SpineBase, JointType.HipLeft));

            // Right Arm
            this.bones.Add(new Tuple<JointType, JointType>(JointType.ShoulderRight, JointType.ElbowRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.ElbowRight, JointType.WristRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.WristRight, JointType.HandRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.HandRight, JointType.HandTipRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.WristRight, JointType.ThumbRight));

            // Left Arm
            this.bones.Add(new Tuple<JointType, JointType>(JointType.ShoulderLeft, JointType.ElbowLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.ElbowLeft, JointType.WristLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.WristLeft, JointType.HandLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.HandLeft, JointType.HandTipLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.WristLeft, JointType.ThumbLeft));

            // Right Leg
            this.bones.Add(new Tuple<JointType, JointType>(JointType.HipRight, JointType.KneeRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.KneeRight, JointType.AnkleRight));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.AnkleRight, JointType.FootRight));

            // Left Leg
            this.bones.Add(new Tuple<JointType, JointType>(JointType.HipLeft, JointType.KneeLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.KneeLeft, JointType.AnkleLeft));
            this.bones.Add(new Tuple<JointType, JointType>(JointType.AnkleLeft, JointType.FootLeft));

            // populate body colors, one for each BodyIndex
            this.bodyColors = new List<Pen>();

            this.bodyColors.Add(new Pen(Brushes.Red, 6));
            this.bodyColors.Add(new Pen(Brushes.Orange, 6));
            this.bodyColors.Add(new Pen(Brushes.Green, 6));
            this.bodyColors.Add(new Pen(Brushes.Blue, 6));
            this.bodyColors.Add(new Pen(Brushes.Indigo, 6));
            this.bodyColors.Add(new Pen(Brushes.Violet, 6));

            // set IsAvailableChanged event notifier
            this.kinectSensor.IsAvailableChanged += this.Sensor_IsAvailableChanged;

            // open the sensor
            this.kinectSensor.Open();

            // set the status text
            this.StatusText = this.kinectSensor.IsAvailable ? Properties.Resources.RunningStatusText
                                                            : Properties.Resources.NoSensorStatusText;

            // Create the drawing group we'll use for drawing
            this.drawingGroup = new DrawingGroup();

            // Create an image source that we can use in our image control
            this.imageSource = new DrawingImage(this.drawingGroup);

            // use the window object as the view model in this simple example
            this.DataContext = this;

            // initialize the components (controls) of the window
            this.InitializeComponent();

            // --- initialize new subsystems ---
            try
            {
                this.kinectManager = new KinectManager();
                this.kinectManager.HandUpdated += KinectManager_HandUpdated;
            }
            catch (Exception ex)
            {
                Debug.WriteLine("KinectManager init failed: " + ex.Message);
            }

            this.transformer = new CoordinateTransformer();
            this.transformer.SetAsMaster();

            this.recorder = new TrajectoryRecorder();
            this.recorder.FrequencyHz = 20; // default
            this.recorder.RecordingStopped += Recorder_RecordingStopped;

            // create second recorder for Cam2
            this.recorderCam2 = new TrajectoryRecorder();
            this.recorderCam2.FrequencyHz = 20;
            this.recorderCam2.RecordingStopped += RecorderCam2_RecordingStopped;

            // create calibration manager and sensor wrappers (best-effort, sensors may be on different machines)
            try
            {
                this.calibManager = new DualCameraCalibrationManager();
                try
                {
                    this.cam1Wrapper = new KinectSensorWrapper("Cam1", this.calibManager);
                    this.cam1Wrapper.RawHandUpdated += Cam1_RawHandUpdated;
                    this.cam1Wrapper.WorldHandUpdated += Cam1_WorldHandUpdated;
                }
                catch (Exception ex) { Debug.WriteLine("Cam1 wrapper init failed: " + ex.Message); }

                try
                {
                    this.cam2Wrapper = new KinectSensorWrapper("Cam2", this.calibManager);
                    this.cam2Wrapper.RawHandUpdated += Cam2_RawHandUpdated;
                    this.cam2Wrapper.WorldHandUpdated += Cam2_WorldHandUpdated;
                }
                catch (Exception ex) { Debug.WriteLine("Cam2 wrapper init failed: " + ex.Message); }
            }
            catch (Exception ex)
            {
                Debug.WriteLine("Calibration manager init failed: " + ex.Message);
            }

            this.samplingTimer = new Timer(1000.0 / this.recorder.FrequencyHz);
            this.samplingTimer.Elapsed += SamplingTimer_Elapsed;
            this.samplingTimer.AutoReset = true;

            // UI timer updates countdown and save path every 200 ms
            this.uiTimer = new DispatcherTimer();
            this.uiTimer.Interval = TimeSpan.FromMilliseconds(200);
            this.uiTimer.Tick += UiTimer_Tick;

            // initialize UI labels
            this.lblKinect.Text = this.kinectSensor.IsAvailable ? "Kinect: Connected" : "Kinect: Not available";
            this.lblBody.Text = "Body: Not tracked";
            this.lblRecording.Text = "Recording: Inactive";
        }

        // Add handler for recorder stopped event
        private void Recorder_RecordingStopped()
        {
            // ensure UI update on dispatcher
            this.Dispatcher.BeginInvoke(new Action(() =>
            {
                try
                {
                    this.samplingTimer?.Stop();
                    this.uiTimer?.Stop();
                    this.lblRecording.Text = "Recording: Inactive";
                    this.txtCountdown.Text = "Countdown: -";
                    this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? "-");
                }
                catch { }
            }));
        }

        private void RecorderCam2_RecordingStopped()
        {
            // update UI when cam2 stops (keep similar behavior)
            this.Dispatcher.BeginInvoke(new Action(() =>
            {
                try
                {
                    // if both recorders are stopped, update labels
                    if ((this.recorder == null || !this.recorder.IsRecording) && (this.recorderCam2 == null || !this.recorderCam2.IsRecording))
                    {
                        this.samplingTimer?.Stop();
                        this.uiTimer?.Stop();
                        this.lblRecording.Text = "Recording: Inactive";
                        this.txtCountdown.Text = "Countdown: -";
                        this.txtSavePath.Text = "Save path: " + (this.recorder?.CurrentFilePath ?? this.recorderCam2?.CurrentFilePath ?? "-");
                    }
                }
                catch { }
            }));
        }

        private void UiTimer_Tick(object sender, EventArgs e)
        {
            if (this.recorder == null) return;

            if (!this.recorder.IsRecording)
            {
                // show saved path if present
                if (!string.IsNullOrEmpty(this.recorder.CurrentFilePath) || (this.recorderCam2 != null && !string.IsNullOrEmpty(this.recorderCam2.CurrentFilePath)))
                {
                    this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? this.recorderCam2.CurrentFilePath);
                }
                return;
            }

            // update save path
            this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? this.recorderCam2?.CurrentFilePath ?? "-");

            // compute remaining time
            string timePart = "Time left: ∞";
            if (this.recorder.StartTimestamp.HasValue && this.recorder.MaxTime != TimeSpan.MaxValue)
            {
                var elapsed = DateTime.UtcNow - this.recorder.StartTimestamp.Value;
                var remaining = this.recorder.MaxTime - elapsed;
                if (remaining < TimeSpan.Zero) remaining = TimeSpan.Zero;
                timePart = string.Format(CultureInfo.InvariantCulture, "Time left: {0:F1}s", remaining.TotalSeconds);
            }

            // compute remaining frames
            string framePart = "Frames left: ∞";
            if (this.recorder.MaxFrames != int.MaxValue)
            {
                var left = this.recorder.MaxFrames - this.recorder.RecordedFrames;
                if (left < 0) left = 0;
                framePart = "Frames left: " + left.ToString(CultureInfo.InvariantCulture);
            }

            this.txtCountdown.Text = $"Countdown: {timePart} | {framePart}";
        }

        /// <summary>
        /// INotifyPropertyChangedPropertyChanged event to allow window controls to bind to changeable data
        /// </summary>
        public event PropertyChangedEventHandler PropertyChanged;

        /// <summary>
        /// Gets the bitmap to display
        /// </summary>
        public ImageSource ImageSource
        {
            get
            {
                return this.imageSource;
            }
        }

        /// <summary>
        /// Gets or sets the current status text to display
        /// </summary>
        public string StatusText
        {
            get
            {
                return this.statusText;
            }

            set
            {
                if (this.statusText != value)
                {
                    this.statusText = value;

                    // notify any bound elements that the text has changed
                    if (this.PropertyChanged != null)
                    {
                        this.PropertyChanged(this, new PropertyChangedEventArgs("StatusText"));
                    }
                }
            }
        }

        /// <summary>
        /// Execute start up tasks
        /// </summary>
        /// <param name="sender">object sending the event</param>
        /// <param name="e">event arguments</param>
        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            if (this.bodyFrameReader != null)
            {
                this.bodyFrameReader.FrameArrived += this.Reader_FrameArrived;
            }
        }

        /// <summary>
        /// Execute shutdown tasks
        /// </summary>
        /// <param name="sender">object sending the event</param>
        /// <param name="e">event arguments</param>
        private void MainWindow_Closing(object sender, CancelEventArgs e)
        {
            if (this.rosClient != null) { this.rosClient.Close(); }

            if (this.bodyFrameReader != null)
            {
                // BodyFrameReader is IDisposable
                this.bodyFrameReader.Dispose();
                this.bodyFrameReader = null;
            }

            try
            {
                this.samplingTimer?.Stop();
                this.samplingTimer?.Dispose();
                this.recorder?.Dispose();
                this.recorderCam2?.Dispose();
                this.kinectManager?.Dispose();
                try { this.cam1Wrapper?.Dispose(); } catch { }
                try { this.cam2Wrapper?.Dispose(); } catch { }
            }
            catch { }

            if (this.kinectSensor != null)
            {
                this.kinectSensor.Close();
                this.kinectSensor = null;
            }
        }

        /// <summary>
        /// Handles the body frame data arriving from the sensor
        /// </summary>
        /// <param name="sender">object sending the event</param>
        /// <param name="e">event arguments</param>
        private void Reader_FrameArrived(object sender, BodyFrameArrivedEventArgs e)
        {
            bool dataReceived = false;

            using (BodyFrame bodyFrame = e.FrameReference.AcquireFrame())
            {
                if (bodyFrame != null)
                {
                    if (this.bodies == null)
                    {
                        this.bodies = new Body[bodyFrame.BodyCount];
                    }

                    // The first time GetAndRefreshBodyData is called, Kinect will allocate each Body in the array.
                    // As long as those body objects are not disposed and not set to null in the array,
                    // those body objects will be re-used.
                    bodyFrame.GetAndRefreshBodyData(this.bodies);
                    dataReceived = true;
                }
            }

            if (dataReceived)
            {
                using (DrawingContext dc = this.drawingGroup.Open())
                {
                    // Draw a transparent background to set the render size
                    dc.DrawRectangle(Brushes.Black, null, new Rect(0.0, 0.0, this.displayWidth, this.displayHeight));

                    int penIndex = 0;
                    foreach (Body body in this.bodies)
                    {
                        Pen drawPen = this.bodyColors[penIndex++];

                        if (body.IsTracked)
                        {
                            this.DrawClippedEdges(body, dc);

                            IReadOnlyDictionary<JointType, Joint> joints = body.Joints;

                            // convert the joint points to depth (display) space
                            Dictionary<JointType, Point> jointPoints = new Dictionary<JointType, Point>();

                            foreach (JointType jointType in joints.Keys)
                            {
                                // sometimes the depth(Z) of an inferred joint may show as negative
                                // clamp down to 0.1f to prevent coordinatemapper from returning (-Infinity, -Infinity)
                                CameraSpacePoint position = joints[jointType].Position;
                                if (position.Z < 0)
                                {
                                    position.Z = InferredZPositionClamp;
                                }

                                DepthSpacePoint depthSpacePoint = this.coordinateMapper.MapCameraPointToDepthSpace(position);
                                jointPoints[jointType] = new Point(depthSpacePoint.X, depthSpacePoint.Y);
                            }

                            this.DrawBody(joints, jointPoints, dc, drawPen);

                            this.DrawHand(body.HandLeftState, jointPoints[JointType.HandLeft], dc);
                            this.DrawHand(body.HandRightState, jointPoints[JointType.HandRight], dc);
                        }
                    }

                    // prevent drawing outside of our render area
                    this.drawingGroup.ClipGeometry = new RectangleGeometry(new Rect(0.0, 0.0, this.displayWidth, this.displayHeight));
                }
            }
        }

        /// <summary>
        /// Draws a body
        /// </summary>
        /// <param name="joints">joints to draw</param>
        /// <param name="jointPoints">translated positions of joints to draw</param>
        /// <param name="drawingContext">drawing context to draw to</param>
        /// <param name="drawingPen">specifies color to draw a specific body</param>
        private void DrawBody(IReadOnlyDictionary<JointType, Joint> joints, IDictionary<JointType, Point> jointPoints, DrawingContext drawingContext, Pen drawingPen)
        {
            // Draw the bones
            foreach (var bone in this.bones)
            {
                this.DrawBone(joints, jointPoints, bone.Item1, bone.Item2, drawingContext, drawingPen);
            }

            // Draw the joints
            foreach (JointType jointType in joints.Keys)
            {
                Brush drawBrush = null;

                TrackingState trackingState = joints[jointType].TrackingState;

                if (trackingState == TrackingState.Tracked)
                {
                    drawBrush = this.trackedJointBrush;
                }
                else if (trackingState == TrackingState.Inferred)
                {
                    drawBrush = this.inferredJointBrush;
                }

                if (drawBrush != null)
                {
                    drawingContext.DrawEllipse(drawBrush, null, jointPoints[jointType], JointThickness, JointThickness);
                }
            }
        }

        /// <summary>
        /// Draws one bone of a body (joint to joint)
        /// </summary>
        /// <param name="joints">joints to draw</param>
        /// <param name="jointPoints">translated positions of joints to draw</param>
        /// <param name="jointType0">first joint of bone to draw</param>
        /// <param name="jointType1">second joint of bone to draw</param>
        /// <param name="drawingContext">drawing context to draw to</param>
        /// /// <param name="drawingPen">specifies color to draw a specific bone</param>
        private void DrawBone(IReadOnlyDictionary<JointType, Joint> joints, IDictionary<JointType, Point> jointPoints, JointType jointType0, JointType jointType1, DrawingContext drawingContext, Pen drawingPen)
        {
            Joint joint0 = joints[jointType0];
            Joint joint1 = joints[jointType1];

            // If we can't find either of these joints, exit
            if (joint0.TrackingState == TrackingState.NotTracked ||
                joint1.TrackingState == TrackingState.NotTracked)
            {
                return;
            }

            // We assume all drawn bones are inferred unless BOTH joints are tracked
            Pen drawPen = this.inferredBonePen;
            if ((joint0.TrackingState == TrackingState.Tracked) && (joint1.TrackingState == TrackingState.Tracked))
            {
                drawPen = drawingPen;
            }

            drawingContext.DrawLine(drawPen, jointPoints[jointType0], jointPoints[jointType1]);
        }

        /// <summary>
        /// Draws a hand symbol if the hand is tracked: red circle = closed, green circle = opened; blue circle = lasso
        /// </summary>
        /// <param name="handState">state of the hand</param>
        /// <param name="handPosition">position of the hand</param>
        /// <param name="drawingContext">drawing context to draw to</param>
        private void DrawHand(HandState handState, Point handPosition, DrawingContext drawingContext)
        {
            switch (handState)
            {
                case HandState.Closed:
                    drawingContext.DrawEllipse(this.handClosedBrush, null, handPosition, HandSize, HandSize);
                    break;

                case HandState.Open:
                    drawingContext.DrawEllipse(this.handOpenBrush, null, handPosition, HandSize, HandSize);
                    break;

                case HandState.Lasso:
                    drawingContext.DrawEllipse(this.handLassoBrush, null, handPosition, HandSize, HandSize);
                    break;
            }
        }

        /// <summary>
        /// Draws indicators to show which edges are clipping body data
        /// </summary>
        /// <param name="body">body to draw clipping information for</param>
        /// <param name="drawingContext">drawing context to draw to</param>
        private void DrawClippedEdges(Body body, DrawingContext drawingContext)
        {
            FrameEdges clippedEdges = body.ClippedEdges;

            if (clippedEdges.HasFlag(FrameEdges.Bottom))
            {
                drawingContext.DrawRectangle(
                    Brushes.Red,
                    null,
                    new Rect(0, this.displayHeight - ClipBoundsThickness, this.displayWidth, ClipBoundsThickness));
            }

            if (clippedEdges.HasFlag(FrameEdges.Top))
            {
                drawingContext.DrawRectangle(
                    Brushes.Red,
                    null,
                    new Rect(0, 0, this.displayWidth, ClipBoundsThickness));
            }

            if (clippedEdges.HasFlag(FrameEdges.Left))
            {
                drawingContext.DrawRectangle(
                    Brushes.Red,
                    null,
                    new Rect(0, 0, ClipBoundsThickness, this.displayHeight));
            }

            if (clippedEdges.HasFlag(FrameEdges.Right))
            {
                drawingContext.DrawRectangle(
                    Brushes.Red,
                    null,
                    new Rect(this.displayWidth - ClipBoundsThickness, 0, ClipBoundsThickness, this.displayHeight));
            }
        }

        /// <summary>
        /// Handles the event which the sensor becomes unavailable (E.g. paused, closed, unplugged).
        /// </summary>
        /// <param name="sender">object sending the event</param>
        /// <param name="e">event arguments</param>
        private void Sensor_IsAvailableChanged(object sender, IsAvailableChangedEventArgs e)
        {
            // on failure, set the status text
            this.StatusText = this.kinectSensor.IsAvailable ? Properties.Resources.RunningStatusText
                                                            : Properties.Resources.SensorNotAvailableStatusText;
        }

        private void KinectManager_HandUpdated(HandJointUpdate update)
        {
            // store last seen hand positions and tracking id
            if (update.Joint == JointType.HandLeft)
            {
                this.lastLeftHand = update.Position;
            }
            else if (update.Joint == JointType.HandRight)
            {
                this.lastRightHand = update.Position;
            }

            this.lastTrackingId = update.TrackingId;

            // update transformer floor plane if available
            if (this.kinectManager.FloorClipPlane.HasValue)
            {
                this.transformer.UpdateFloorPlane(this.kinectManager.FloorClipPlane.Value);
            }

            // update UI (marshal to UI thread)
            this.Dispatcher.BeginInvoke(new Action(() =>
            {
                // show the last right-hand world coords if possible
                CameraSpacePoint p = update.Position;
                var world = this.transformer.Transform(p);
                this.txtXYZ.Text = string.Format(CultureInfo.InvariantCulture, "X: {0:F3}, Y: {1:F3}, Z: {2:F3}", world.X, world.Y, world.Z);

                // update body tracked label
                this.lblBody.Text = this.kinectManager.TrackedBodyId.HasValue ? $"Body: {this.kinectManager.TrackedBodyId.Value}" : "Body: Not tracked";
            }));
        }

        private void Cam1_RawHandUpdated(HandJointUpdate update)
        {
            if (update.Joint == JointType.HandRight)
            {
                this.lastRawCam1 = update.Position;
            }
        }

        private void Cam2_RawHandUpdated(HandJointUpdate update)
        {
            if (update.Joint == JointType.HandRight)
            {
                this.lastRawCam2 = update.Position;
            }
        }

        private void Cam1_WorldHandUpdated(HandJointUpdate update)
        {
            if (update.Joint == JointType.HandRight)
            {
                this.lastWorldCam1 = update.Position;
                this.Dispatcher.BeginInvoke(new Action(() =>
                {
                    this.txtXYZCam1.Text = string.Format(CultureInfo.InvariantCulture, "Cam1: X: {0:F3}, Y: {1:F3}, Z: {2:F3}", update.Position.X, update.Position.Y, update.Position.Z);
                }));

                // TCP send to ROS
                if (this.rosWriter != null)
                {
                    try
                    {
                        string json = string.Format(CultureInfo.InvariantCulture,
                            "{{\"x\": {0:F6}, \"y\": {1:F6}, \"z\": {2:F6}, \"ts\": \"{3:O}\", \"id\": {4}, \"tracked\": true, \"confidence\": 1.0}}",
                            update.Position.X, update.Position.Y, update.Position.Z, update.Timestamp, update.TrackingId);
                        this.rosWriter.WriteLine(json);
                    }
                    catch { }
                }
            }
        }

        private void Cam2_WorldHandUpdated(HandJointUpdate update)
        {
            if (update.Joint == JointType.HandRight)
            {
                this.lastWorldCam2 = update.Position;
                this.Dispatcher.BeginInvoke(new Action(() =>
                {
                    this.txtXYZCam2.Text = string.Format(CultureInfo.InvariantCulture, "Cam2: X: {0:F3}, Y: {1:F3}, Z: {2:F3}", update.Position.X, update.Position.Y, update.Position.Z);
                }));
            }
        }

        /// <summary>
        /// Handles the event which the sensor becomes unavailable (E.g. paused, closed, unplugged).
        /// </summary>
        /// <param name="sender">object sending the event</param>
        /// <param name="e">event arguments</param>

        private void SamplingTimer_Elapsed(object sender, ElapsedEventArgs e)
        {
            // sample at fixed rate: append last known world positions for both cameras
            try
            {
                if (this.recorder != null && this.recorder.IsRecording && this.lastWorldCam1.Z != 0)
                {
                    this.recorder.AppendSample(DateTime.UtcNow, this.lastWorldCam1.X, this.lastWorldCam1.Y, this.lastWorldCam1.Z, "HandRight", GetModeName(), this.currentTargetId);
                }

                if (this.recorderCam2 != null && this.recorderCam2.IsRecording && this.lastWorldCam2.Z != 0)
                {
                    this.recorderCam2.AppendSample(DateTime.UtcNow, this.lastWorldCam2.X, this.lastWorldCam2.Y, this.lastWorldCam2.Z, "HandRight", GetModeName(), this.currentTargetId);
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine("Recorder append failed: " + ex.Message);
            }
        }

        private string GetModeName()
        {
            switch (this.currentMode)
            {
                case 1: return "Free";
                case 2: return "Obstacle";
                case 3: return "FreeChange";
                case 4: return "ObstacleChange";
                default: return "Unknown";
            }
        }

        // Button handlers wired in XAML
        private void BtnStart_Click(object sender, RoutedEventArgs e)
        {
            // start recorder and sampling timer
            try
            {
                // parse limits from UI
                int maxFrames = 0;
                double maxTimeSeconds = 0;
                if (!int.TryParse(this.txtMaxFrames.Text, out maxFrames)) maxFrames = 0;
                if (!double.TryParse(this.txtMaxTime.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out maxTimeSeconds)) maxTimeSeconds = 0;

                this.recorder.MaxFrames = (maxFrames <= 0) ? int.MaxValue : maxFrames;
                this.recorder.MaxTime = (maxTimeSeconds <= 0) ? TimeSpan.MaxValue : TimeSpan.FromSeconds(maxTimeSeconds);

                // Save files into project-relative folder (under application output directory).
                // Folders `RecordTrajectories\RawRecord` are expected to exist in the project (or as content copied to output).
                var folder = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "RecordTrajectories", "RawRecord");
                Directory.CreateDirectory(folder);
                var filename1 = Path.Combine(folder, $"cam1_{DateTime.Now:yyyyMMdd_HHmm}.csv");
                var filename2 = Path.Combine(folder, $"cam2_{DateTime.Now:yyyyMMdd_HHmm}.csv");

                // Determine which recorder(s) to start based on preferredRecorderTarget
                var target = this.preferredRecorderTarget; // "Cam1", "Cam2" or null for both
                bool startBoth = string.IsNullOrEmpty(target);

                if (startBoth || string.Equals(target, "Cam1", StringComparison.OrdinalIgnoreCase))
                {
                    this.recorder.Start(filename1, "Cam1", "1");
                }

                if (startBoth || string.Equals(target, "Cam2", StringComparison.OrdinalIgnoreCase))
                {
                    try { this.recorderCam2.Start(filename2, "Cam2", "1"); } catch { }
                }

                // show path and start timers
                string savePathDisplay = "-";
                if (startBoth)
                {
                    savePathDisplay = (this.recorder.CurrentFilePath ?? "-") + " ; " + (this.recorderCam2?.CurrentFilePath ?? "-");
                }
                else if (string.Equals(target, "Cam1", StringComparison.OrdinalIgnoreCase))
                {
                    savePathDisplay = this.recorder.CurrentFilePath ?? "-";
                }
                else if (string.Equals(target, "Cam2", StringComparison.OrdinalIgnoreCase))
                {
                    savePathDisplay = this.recorderCam2?.CurrentFilePath ?? "-";
                }

                this.txtSavePath.Text = "Save path: " + savePathDisplay;
                this.samplingTimer.Interval = 1000.0 / this.recorder.FrequencyHz;
                this.samplingTimer.Start();
                this.uiTimer.Start();

                this.lblRecording.Text = "Recording: Active";
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to start recorder: " + ex.Message);
            }
        }

        private void BtnConnectRos_Click(object sender, RoutedEventArgs e)
        {
            string ip = this.txtRosIp.Text.Trim();
            try
            {
                if (this.rosClient != null) { this.rosClient.Close(); this.rosClient = null; }
                this.rosClient = new TcpClient();
                this.rosClient.Connect(ip, 9090);
                this.rosWriter = new StreamWriter(this.rosClient.GetStream(), new UTF8Encoding(false));
                this.rosWriter.AutoFlush = true;
                MessageBox.Show("Connected to ROS Server at " + ip + ":9090");
            }
            catch (Exception ex)
            {
                MessageBox.Show("ROS Connection Error: " + ex.Message);
            }
        }

        private void BtnStop_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                this.samplingTimer.Stop();
                this.uiTimer.Stop();
                this.recorder.Stop();
                this.recorderCam2.Stop();
                this.lblRecording.Text = "Recording: Inactive";
                this.txtCountdown.Text = "Countdown: -";
                this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? "-");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to stop recorder: " + ex.Message);
            }
        }

        private void BtnCalibrate_Click(object sender, RoutedEventArgs e)
        {
            // Set world origin to current right hand (if available) and update floor
            if (this.lastTrackingId.HasValue && this.kinectManager.TrackedBodyId.HasValue && this.lastTrackingId == this.kinectManager.TrackedBodyId)
            {
                this.transformer.SetWorldOriginFromTarget(this.lastRightHand);
                if (this.kinectManager.FloorClipPlane.HasValue)
                {
                    this.transformer.UpdateFloorPlane(this.kinectManager.FloorClipPlane.Value);
                }

                MessageBox.Show("Calibration set from current right hand.");
            }
            else
            {
                MessageBox.Show("No tracked body / hand available to calibrate.");
            }
        }

        private void BtnCalibrateCam1_Click(object sender, RoutedEventArgs e)
        {
            if (this.lastRawCam1.Z == 0)
            {
                MessageBox.Show("No Cam1 hand available to calibrate.");
                return;
            }

            try
            {
                var profile = this.calibManager.Load("Cam1");
                // compute translation t = -R * p_target so world origin is at target
                var R = profile.RotationMatrix;
                var p = new Vector3(this.lastRawCam1.X, this.lastRawCam1.Y, this.lastRawCam1.Z);
                var rotated = new Vector3(
                    R[0] * p.X + R[1] * p.Y + R[2] * p.Z,
                    R[3] * p.X + R[4] * p.Y + R[5] * p.Z,
                    R[6] * p.X + R[7] * p.Y + R[8] * p.Z);

                profile.Translation = -rotated;
                this.calibManager.Save("Cam1", profile);
                this.cam1Calibrated = true;
                this.lblCam1Status.Text = "Cam1 calibrated: ✔";

                // mark this machine to prefer saving Cam1 recordings when starting
                this.preferredRecorderTarget = "Cam1";

                MessageBox.Show("Cam1 calibration saved.");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Cam1 calibration failed: " + ex.Message);
            }
        }

        private void BtnCalibrateCam2_Click(object sender, RoutedEventArgs e)
        {
            if (this.lastRawCam2.Z == 0)
            {
                MessageBox.Show("No Cam2 hand available to calibrate.");
                return;
            }

            try
            {
                var profile = this.calibManager.Load("Cam2");
                var R = profile.RotationMatrix;
                var p = new Vector3(this.lastRawCam2.X, this.lastRawCam2.Y, this.lastRawCam2.Z);
                var rotated = new Vector3(
                    R[0] * p.X + R[1] * p.Y + R[2] * p.Z,
                    R[3] * p.X + R[4] * p.Y + R[5] * p.Z,
                    R[6] * p.X + R[7] * p.Y + R[8] * p.Z);

                profile.Translation = -rotated;
                this.calibManager.Save("Cam2", profile);
                this.cam2Calibrated = true;
                this.lblCam2Status.Text = "Cam2 calibrated: ✔";

                // mark this machine to prefer saving Cam2 recordings when starting
                this.preferredRecorderTarget = "Cam2";

                MessageBox.Show("Cam2 calibration saved.");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Cam2 calibration failed: " + ex.Message);
            }
        }

        //private void CboMode_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
        //{
        //    this.currentMode = this.cboMode.SelectedIndex + 1;
        //}

        // other existing methods remain unchanged
    }
}
