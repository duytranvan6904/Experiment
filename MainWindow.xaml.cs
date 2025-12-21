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
        private TrajectoryRecorder recorder;
        private Timer samplingTimer;

        // store last seen wrist positions (changed from hand to wrist)
        private CameraSpacePoint lastLeftWrist;
        private CameraSpacePoint lastRightWrist;
        private ulong? lastTrackingId;

        // experiment params
        private int currentScenarioId = 0; // 0 = not set, 1-18 = valid scenarios

        // Add UI timer for countdown
        private DispatcherTimer uiTimer;

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

        private void UiTimer_Tick(object sender, EventArgs e)
        {
            if (this.recorder == null) return;

            if (!this.recorder.IsRecording)
            {
                // show saved path if present
                if (!string.IsNullOrEmpty(this.recorder.CurrentFilePath))
                {
                    this.txtSavePath.Text = "Save path: " + this.recorder.CurrentFilePath;
                }
                return;
            }

            // update save path
            this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? "-");

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
                this.kinectManager?.Dispose();
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
            // store last seen wrist positions and tracking id (changed from hand to wrist)
            if (update.Joint == JointType.WristLeft)
            {
                this.lastLeftWrist = update.Position;
            }
            else if (update.Joint == JointType.WristRight)
            {
                this.lastRightWrist = update.Position;
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
                // show the last right-wrist world coords if possible
                CameraSpacePoint p = update.Position;
                var world = this.transformer.Transform(p);
                this.txtXYZ.Text = string.Format(CultureInfo.InvariantCulture, "X: {0:F3}, Y: {1:F3}, Z: {2:F3}", world.X, world.Y, world.Z);

                // update body tracked label
                this.lblBody.Text = this.kinectManager.TrackedBodyId.HasValue ? $"Body: {this.kinectManager.TrackedBodyId.Value}" : "Body: Not tracked";
            }));
        }

        private void SamplingTimer_Elapsed(object sender, ElapsedEventArgs e)
        {
            // sample at fixed rate: use lastRightWrist as the tracked point (changed from hand to wrist)
            if (!this.recorder.IsRecording) return;

            // ensure tracked body matches
            if (this.kinectManager == null || !this.kinectManager.TrackedBodyId.HasValue || !this.lastTrackingId.HasValue) return;
            if (this.kinectManager.TrackedBodyId.Value != this.lastTrackingId.Value) return;

            // pick which wrist to record (right prefer)
            var camPoint = this.lastRightWrist;

            var world = this.transformer.Transform(camPoint);

            // AppendSample: timestamp, x,y,z, joint, scenarioId
            try
            {
                this.recorder.AppendSample(DateTime.UtcNow, world.X, world.Y, world.Z, "WristRight", this.currentScenarioId);
            }
            catch (Exception ex)
            {
                Debug.WriteLine("Recorder append failed: " + ex.Message);
            }
        }

        private string GetModeName(int scenarioId)
        {
            if (scenarioId >= 1 && scenarioId <= 3) return "Free";
            if (scenarioId >= 4 && scenarioId <= 6) return "Obstacle";
            if (scenarioId >= 7 && scenarioId <= 12) return "Change";
            if (scenarioId >= 13 && scenarioId <= 18) return "Change+Obstacle";
            return "Unknown";
        }

        private (int initialTarget, int finalTarget) GetTargetsFromScenario(int scenarioId)
        {
            // Scenario mapping based on Python GUI
            switch (scenarioId)
            {
                case 1: return (1, 1);
                case 2: return (2, 2);
                case 3: return (3, 3);
                
                case 4: return (1, 1);
                case 5: return (2, 2);
                case 6: return (3, 3);
                
                case 7: return (1, 2);
                case 8: return (1, 3);
                case 9: return (2, 1);
                case 10: return (2, 3);
                case 11: return (3, 1);
                case 12: return (3, 2);
                
                case 13: return (1, 2);
                case 14: return (1, 3);
                case 15: return (2, 1);
                case 16: return (2, 3);
                case 17: return (3, 1);
                case 18: return (3, 2);
                
                default: return (0, 0);
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

                // Lưu vào folder Trajectories trong project
                var projectDir = AppDomain.CurrentDomain.BaseDirectory;
                var folder = Path.Combine(projectDir, "Trajectories");
                Directory.CreateDirectory(folder);
                var filename = Path.Combine(folder, $"traj_{DateTime.Now:yyyyMMdd_HHmmss}.csv");
                this.recorder.Start(filename);

                // show path and start timers
                this.txtSavePath.Text = "Save path: " + this.recorder.CurrentFilePath;
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

        private void BtnStop_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                this.samplingTimer.Stop();
                this.uiTimer.Stop();
                this.recorder.Stop();
                this.lblRecording.Text = "Recording: Inactive";
                this.txtCountdown.Text = "Countdown: -";

                // Show dialog to get Scenario ID
                var dialog = new ScenarioInputDialog();
                dialog.Owner = this;
                if (dialog.ShowDialog() == true)
                {
                    this.currentScenarioId = dialog.ScenarioId;
                    
                    // Get mode and targets from scenario ID
                    string modeName = GetModeName(this.currentScenarioId);
                    var (initialTarget, finalTarget) = GetTargetsFromScenario(this.currentScenarioId);
                    
                    // Update the saved file with scenario metadata
                    if (!string.IsNullOrEmpty(this.recorder.CurrentFilePath))
                    {
                        UpdateCsvWithScenarioInfo(this.recorder.CurrentFilePath, this.currentScenarioId, modeName, initialTarget, finalTarget);
                        this.txtSavePath.Text = $"Save path: {this.recorder.CurrentFilePath} (Scenario {this.currentScenarioId})";
                    }
                }
                else
                {
                    // User cancelled - still show the path
                    this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? "-") + " (No scenario ID)";
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to stop recorder: " + ex.Message);
            }
        }

        private void UpdateCsvWithScenarioInfo(string filePath, int scenarioId, string mode, int initialTarget, int finalTarget)
        {
            try
            {
                // Read all lines
                var lines = System.IO.File.ReadAllLines(filePath);
                if (lines.Length == 0) return;

                // Update header if needed
                if (lines[0].Contains("Mode") && lines[0].Contains("TargetId"))
                {
                    // Old format - replace with new format
                    lines[0] = "Timestamp,X,Y,Z,Joint,ScenarioId";
                }

                // Write back with scenario info in a comment line
                using (var writer = new System.IO.StreamWriter(filePath, false))
                {
                    writer.WriteLine($"# Scenario {scenarioId}: Mode={mode}, InitialTarget={initialTarget}, FinalTarget={finalTarget}");
                    foreach (var line in lines)
                    {
                        writer.WriteLine(line);
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine("Failed to update CSV with scenario info: " + ex.Message);
            }
        }

        private void BtnCalibrate_Click(object sender, RoutedEventArgs e)
        {
            // Set world origin to current right wrist (if available) and update floor (changed from hand to wrist)
            if (this.lastTrackingId.HasValue && this.kinectManager.TrackedBodyId.HasValue && this.lastTrackingId == this.kinectManager.TrackedBodyId)
            {
                this.transformer.SetWorldOriginFromTarget(this.lastRightWrist);
                if (this.kinectManager.FloorClipPlane.HasValue)
                {
                    this.transformer.UpdateFloorPlane(this.kinectManager.FloorClipPlane.Value);
                }

                MessageBox.Show("Calibration set from current right wrist.");
            }
            else
            {
                MessageBox.Show("No tracked body / wrist available to calibrate.");
            }
        }



        // other existing methods remain unchanged
    }
}
