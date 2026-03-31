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
    using System.Windows.Controls;               // <-- ADD: allows RadioButton, TextBox, TextBlock types
    using System.Windows.Media;
    using System.Windows.Media.Imaging;
    using Microsoft.Kinect;
    using System.Timers;
    using System.Windows.Threading;
    using System.Numerics;
    using System.Net.Sockets;
    using System.Text;
    using System.Threading.Tasks;

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

        private ColorFrameReader colorFrameReader = null;
        private WriteableBitmap colorBitmap = null;
        private double yThresholdTarget = 1.0;
        private bool hasTriggeredChange = false;

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

        // Prediction subsystem
        private PredictionManager predictionManager;
        private PredictionResult lastPrediction;

        // experiment params
        private int currentMode = 1; // 1..4
        private int currentTargetId = 1;

        // Add UI timer for countdown
        private DispatcherTimer uiTimer;

        // ROS TCP Connection
        private TcpClient rosClient;
        private StreamWriter rosWriter;

        // Prediction session - CSV logging + metrics
        private StreamWriter predictionCsvWriter;
        private string predictionCsvPath;
        private bool isPredictionSessionActive = false;
        private int predictionSampleCount = 0;
        private double sumAbsErrX = 0, sumAbsErrY = 0, sumAbsErrZ = 0;
        private double sumSqErrX = 0, sumSqErrY = 0, sumSqErrZ = 0;
        private CameraSpacePoint lastWorldSwapped; // Y↔Z swapped for experiment coords
        private CameraSpacePoint lastActualForPrediction; // last actual point when prediction arrived

        /// <summary>
        /// Initializes a new instance of the MainWindow class.
        /// </summary>
        public MainWindow()
        {
            // one sensor is currently supported
            this.kinectSensor = KinectSensor.GetDefault();

            // get the coordinate mapper
            this.coordinateMapper = this.kinectSensor.CoordinateMapper;

            // get the color frame details
            FrameDescription colorFrameDescription = this.kinectSensor.ColorFrameSource.CreateFrameDescription(ColorImageFormat.Bgra);

            // get size of joint space
            this.displayWidth = colorFrameDescription.Width;
            this.displayHeight = colorFrameDescription.Height;

            // create the color bitmap
            this.colorBitmap = new WriteableBitmap(colorFrameDescription.Width, colorFrameDescription.Height, 96.0, 96.0, PixelFormats.Bgr32, null);

            // open the reader for the color frames
            this.colorFrameReader = this.kinectSensor.ColorFrameSource.OpenReader();
            this.colorFrameReader.FrameArrived += this.Reader_ColorFrameArrived;

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
            this.lblBody.Text = "Body: Not tracked";
            this.lblRecording.Text = "Session: Inactive";

            // Initialize prediction manager (Python sidecar)
            // BaseDirectory is bin\AnyCPU\Debug\ when running from VS, go up to find project root
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string projectRoot = Path.GetFullPath(Path.Combine(baseDir, "..", "..", ".."));
            
            // Try project root first, then baseDir for .venv
            string pythonPath = Path.Combine(projectRoot, ".venv", "Scripts", "python.exe");
            if (!File.Exists(pythonPath)) pythonPath = Path.Combine(baseDir, ".venv", "Scripts", "python.exe");
            if (!File.Exists(pythonPath)) pythonPath = "python"; // Fallback to system python
            
            // Worker script and model dir - try project root first
            string workerScript = Path.Combine(projectRoot, "hrc_ws", "src", "trajectory_predictor", "trajectory_predictor", "inference_worker.py");
            if (!File.Exists(workerScript))
                workerScript = Path.Combine(baseDir, "hrc_ws", "src", "trajectory_predictor", "trajectory_predictor", "inference_worker.py");
            
            string modelDir = Path.Combine(projectRoot, "hrc_ws", "src", "trajectory_predictor", "models");
            if (!Directory.Exists(modelDir))
                modelDir = Path.Combine(baseDir, "hrc_ws", "src", "trajectory_predictor", "models");

            // Log resolved paths for debugging
            this.LogEvent($"Python: {pythonPath} [exists={File.Exists(pythonPath)}]");
            this.LogEvent($"Worker: {workerScript} [exists={File.Exists(workerScript)}]");
            this.LogEvent($"Models: {modelDir} [exists={Directory.Exists(modelDir)}]");

            this.predictionManager = new PredictionManager(pythonPath, workerScript, modelDir);
            this.predictionManager.ErrorReceived += (msg) => this.LogEvent("PY: " + msg);
            this.predictionManager.PredictionReceived += (res) =>
            {
                this.lastPrediction = res;
                if (this.predictionSampleCount == 0 && this.isPredictionSessionActive) {
                    this.LogEvent($"First pred received: {res.model_name}");
                }
                
                // Capture actual position at prediction time (swapped Y↔Z for experiment coords)
                var actual = this.lastWorldSwapped;
                this.lastActualForPrediction = actual;
                
                // Update UI Labels (marshal to UI thread)
                this.Dispatcher.BeginInvoke(new Action(() =>
                {
                    this.lblActiveModel.Text = $"Model: {res.model_name.ToUpper()}";
                    this.lblInferenceTime.Text = $"Inference: {res.inference_ms:F1}ms";
                    this.lblBufferStatus.Text = $"Buffer: {this.predictionManager.BufferCount}/20";
                    
                    // Show predicted coordinates
                    this.txtPredXYZ.Text = string.Format(CultureInfo.InvariantCulture,
                        "Pred: X: {0:F3}, Y: {1:F3}, Z: {2:F3}", res.FinalX, res.FinalY, res.FinalZ);
                }));

                // Log to CSV if session is active
                if (this.isPredictionSessionActive && this.predictionCsvWriter != null)
                {
                    try
                    {
                        double errX = Math.Abs(res.FinalX - actual.X);
                        double errY = Math.Abs(res.FinalY - actual.Y);
                        double errZ = Math.Abs(res.FinalZ - actual.Z);
                        
                        this.sumAbsErrX += errX; this.sumAbsErrY += errY; this.sumAbsErrZ += errZ;
                        this.sumSqErrX += errX * errX; this.sumSqErrY += errY * errY; this.sumSqErrZ += errZ * errZ;
                        this.predictionSampleCount++;

                        string csvLine = string.Format(CultureInfo.InvariantCulture,
                            "{0},{1:F6},{2:F6},{3:F6},{4:F6},{5:F6},{6:F6},{7:F2},{8},{9},{10:F6},{11:F6},{12:F6}",
                            DateTime.UtcNow.ToString("o"),
                            actual.X, actual.Y, actual.Z,
                            res.FinalX, res.FinalY, res.FinalZ,
                            res.inference_ms, res.model_name, this.currentTargetId,
                            errX, errY, errZ);
                        this.predictionCsvWriter.WriteLine(csvLine);
                        this.predictionCsvWriter.Flush();

                        // Update MAE/MSE labels at intervals
                        if (this.predictionSampleCount % 5 == 0)
                        {
                            int n = this.predictionSampleCount;
                            this.Dispatcher.BeginInvoke(new Action(() =>
                            {
                                double maeAvg = (this.sumAbsErrX + this.sumAbsErrY + this.sumAbsErrZ) / (3.0 * n);
                                double mseAvg = (this.sumSqErrX + this.sumSqErrY + this.sumSqErrZ) / (3.0 * n);
                                this.lblMAE.Text = string.Format(CultureInfo.InvariantCulture, "MAE: {0:F4} (n={1})", maeAvg, n);
                                this.lblMSE.Text = string.Format(CultureInfo.InvariantCulture, "MSE: {0:F6}", mseAvg);
                            }));
                        }
                    }
                    catch (Exception ex)
                    {
                        this.LogEvent("CSV write error: " + ex.Message);
                    }
                }

                // Send prediction to ROS via TCP
                if (this.rosWriter != null)
                {
                    try
                    {
                        string json = string.Format(CultureInfo.InvariantCulture,
                            "{{\"x\": {0:F6}, \"y\": {1:F6}, \"z\": {2:F6}, \"inference_ms\": {3:F2}, \"model_name\": \"{4}\", \"confidence\": {5:F2}}}",
                            res.FinalX, res.FinalY, res.FinalZ, res.inference_ms, res.model_name, 1.0);
                        this.rosWriter.WriteLine(json);
                    }
                    catch { }
                }
            };
            this.LogEvent("Prediction Pipeline Initialized");
            this.LogEvent($"Search Python: {pythonPath}");
        }

        private void Model_Checked(object sender, RoutedEventArgs e)
        {
            if (this.predictionManager == null) return;
            var rb = sender as RadioButton;
            if (rb == null || !rb.IsChecked.Value) return;

            string modelName = "gru";
            if (rb == rbRnn) modelName = "rnn";
            else if (rb == rbLstm) modelName = "lstm";

            this.predictionManager.LoadModel(modelName);
            this.lblActiveModel.Text = $"Model: {modelName.ToUpper()}";
            this.LogEvent($"Model switched to {modelName.ToUpper()}");
            
            this.plotX.Clear();
            this.plotY.Clear();
            this.plotZ.Clear();
        }

        private void LogEvent(string msg)
        {
            this.Dispatcher.BeginInvoke(new Action(() =>
            {
                this.lstLog.Items.Insert(0, $"[{DateTime.Now:HH:mm:ss}] {msg}");
                if (this.lstLog.Items.Count > 50) this.lstLog.Items.RemoveAt(50);
            }));
        }

        private void BtnResetPlots_Click(object sender, RoutedEventArgs e)
        {
            this.plotX.Clear();
            this.plotY.Clear();
            this.plotZ.Clear();
            this.predictionManager?.Reset();
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
                    this.lblRecording.Text = "Session: Inactive";
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
                        this.lblRecording.Text = "Session: Inactive";
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

            // UI text removed because countdown UI was replaced
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

        public ImageSource ColorImageSource
        {
            get
            {
                return this.colorBitmap;
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

            if (this.colorFrameReader != null)
            {
                this.colorFrameReader.Dispose();
                this.colorFrameReader = null;
            }

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
                this.predictionManager?.Dispose();
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
                    dc.DrawRectangle(Brushes.Transparent, null, new Rect(0.0, 0.0, this.displayWidth, this.displayHeight));

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

                                ColorSpacePoint colorSpacePoint = this.coordinateMapper.MapCameraPointToColorSpace(position);
                                jointPoints[jointType] = new Point(colorSpacePoint.X, colorSpacePoint.Y);
                            }

                            this.DrawBody(joints, jointPoints, dc, drawPen);

                            this.DrawHand(body.HandLeftState, jointPoints[JointType.HandLeft], dc);
                            this.DrawHand(body.HandRightState, jointPoints[JointType.HandRight], dc);
                        }
                    }

                    // --- NEW: Draw Prediction ---
                    if (this.lastPrediction != null)
                    {
                        CameraSpacePoint p = new CameraSpacePoint { X = lastPrediction.FinalX, Y = lastPrediction.FinalY, Z = lastPrediction.FinalZ };
                        if (p.Z < 0.1f) p.Z = 0.1f;
                        ColorSpacePoint csp = this.coordinateMapper.MapCameraPointToColorSpace(p);
                        Point pt = new Point(csp.X, csp.Y);

                        // Draw a blue circle for prediction
                        dc.DrawEllipse(new SolidColorBrush(Color.FromArgb(180, 0, 188, 242)), null, pt, 20, 20);

                        // Create FormattedText using PixelsPerDip (non-obsolete)
                        double pixelsPerDip = VisualTreeHelper.GetDpi(this).PixelsPerDip;
                        FormattedText text = new FormattedText(
                            "PRED",
                            CultureInfo.CurrentCulture,
                            FlowDirection.LeftToRight,
                            new Typeface("Segoe UI"),
                            14,
                            Brushes.White,
                            pixelsPerDip);

                        dc.DrawText(text, new Point(pt.X + 15, pt.Y - 15));
                    }

                    // prevent drawing outside of our render area
                    this.drawingGroup.ClipGeometry = new RectangleGeometry(new Rect(0.0, 0.0, this.displayWidth, this.displayHeight));
                }
            }
        }

        private void Reader_ColorFrameArrived(object sender, ColorFrameArrivedEventArgs e)
        {
            using (ColorFrame colorFrame = e.FrameReference.AcquireFrame())
            {
                if (colorFrame != null)
                {
                    FrameDescription colorFrameDescription = colorFrame.FrameDescription;
                    using (KinectBuffer colorBuffer = colorFrame.LockRawImageBuffer())
                    {
                        this.colorBitmap.Lock();
                        if ((colorFrameDescription.Width == this.colorBitmap.PixelWidth) && (colorFrameDescription.Height == this.colorBitmap.PixelHeight))
                        {
                            colorFrame.CopyConvertedFrameDataToIntPtr(
                                this.colorBitmap.BackBuffer,
                                (uint)(colorFrameDescription.Width * colorFrameDescription.Height * 4),
                                ColorImageFormat.Bgra);

                            this.colorBitmap.AddDirtyRect(new Int32Rect(0, 0, this.colorBitmap.PixelWidth, this.colorBitmap.PixelHeight));
                        }
                        this.colorBitmap.Unlock();
                    }
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
                // show the last right-hand world coords (swap Y↔Z for experiment coordinates)
                CameraSpacePoint p = update.Position;
                var world = this.transformer.Transform(p);
                // Experiment coords: X=X, Y=Z(depth/forward), Z=Y(up/down)
                this.txtXYZ.Text = string.Format(CultureInfo.InvariantCulture, "X: {0:F3}, Y: {1:F3}, Z: {2:F3}", world.X, world.Z, world.Y);

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
                
                // Store experiment-swapped coordinates: X=X, Y=Z(forward), Z=Y(up)
                this.lastWorldSwapped = new CameraSpacePoint
                {
                    X = update.Position.X,
                    Y = update.Position.Z,  // experiment Y = camera Z (depth/forward)
                    Z = update.Position.Y   // experiment Z = camera Y (up/down)
                };
                
                // Trigger Change Scene: check experiment Y (camera Z = forward) > threshold
                if (this.isPredictionSessionActive && !this.hasTriggeredChange)
                {
                        // Trigger if experiment Y (depth) crosses threshold
                        if (this.lastWorldSwapped.Y > this.yThresholdTarget)
                        {
                            this.hasTriggeredChange = true;
                            this.Dispatcher.BeginInvoke(new Action(() => {
                                this.txtCurrentScenario.Text = $"Scenario: {this.currentTargetId} (CHANGED)";
                            }));

                            // Send TCP signal to Python GUI to trigger target change
                            Task.Run(() =>
                            {
                                try
                                {
                                    using (var client = new TcpClient())
                                    {
                                        client.Connect("127.0.0.1", 9091);
                                        var writer = new StreamWriter(client.GetStream(), new UTF8Encoding(false));
                                        writer.Write("Y_CROSSED");
                                        writer.Flush();
                                    }
                                }
                                catch (Exception ex)
                                {
                                    Debug.WriteLine("Failed to send Y_CROSSED to Python GUI: " + ex.Message);
                                }
                            });
                        }
                }

                // Feed to local PredictionManager
                this.predictionManager?.AddDataPoint(update.Position);

                // Update plots with MEASURED data (swapped Y↔Z) + latest prediction
                var swapped = this.lastWorldSwapped;
                var pred = this.lastPrediction;
                this.Dispatcher.BeginInvoke(new Action(() =>
                {
                    this.plotX.AddPoints(swapped.X, pred?.FinalX);
                    this.plotY.AddPoints(swapped.Y, pred?.FinalY);
                    this.plotZ.AddPoints(swapped.Z, pred?.FinalZ);
                    this.lblBufferStatus.Text = $"Buffer: {this.predictionManager.BufferCount}/20";
                }));
            }
        }

        private void Cam2_WorldHandUpdated(HandJointUpdate update)
        {
            if (update.Joint == JointType.HandRight)
            {
                this.lastWorldCam2 = update.Position;
                this.Dispatcher.BeginInvoke(new Action(() =>
                {
                    
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
            // Auto-start Python GUI by sending START_TRIAL
            Task.Run(() =>
            {
                try
                {
                    using (var client = new TcpClient())
                    {
                        client.Connect("127.0.0.1", 9091);
                        var writer = new StreamWriter(client.GetStream(), new UTF8Encoding(false));
                        writer.Write("START_TRIAL");
                        writer.Flush();
                    }
                }
                catch (Exception ex)
                {
                    Debug.WriteLine("Failed to send START_TRIAL to Python GUI: " + ex.Message);
                }
            });

            if (double.TryParse(this.txtYThreshold.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out double yThresh))
            {
                this.yThresholdTarget = yThresh;
            }
            else
            {
                this.yThresholdTarget = 1.0;
            }
            this.hasTriggeredChange = false;
            // Set a default 'change' scenario ID to enable the Y-coordinate trigger check in Cam1_WorldHandUpdated
            this.currentTargetId = 8; 

            // Start prediction session - capture to temp file first
            try
            {
                var folder = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "PredictionResults");
                Directory.CreateDirectory(folder);
                this.predictionCsvPath = Path.Combine(folder, "last_session_temp.csv");

                this.predictionCsvWriter = new StreamWriter(this.predictionCsvPath, false, new UTF8Encoding(false));
                this.predictionCsvWriter.WriteLine("timestamp,actual_x,actual_y,actual_z,predicted_x,predicted_y,predicted_z,inference_ms,model_name,scenario_id,abs_err_x,abs_err_y,abs_err_z");
                this.predictionCsvWriter.Flush();

                // Reset metrics
                this.predictionSampleCount = 0;
                this.sumAbsErrX = 0; this.sumAbsErrY = 0; this.sumAbsErrZ = 0;
                this.sumSqErrX = 0; this.sumSqErrY = 0; this.sumSqErrZ = 0;

                this.isPredictionSessionActive = true;
                this.txtSavePath.Text = "Capturing to temp file...";
                this.lblRecording.Text = "Prediction: Active";
                this.lblRecording.Foreground = new SolidColorBrush(Color.FromRgb(166, 227, 161)); // green
                this.lblMAE.Text = "MAE: -";
                this.lblMSE.Text = "MSE: -";

                // Also reset prediction manager buffer for clean start
                this.predictionManager?.Reset();
                this.LogEvent("Prediction Started");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to start prediction session: " + ex.Message);
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
                this.lblBridgeStatus.Text = "Bridge: Connected";
                this.lblBridgeStatus.Foreground = new SolidColorBrush(Color.FromRgb(166, 227, 161));
                MessageBox.Show("Connected to ROS Server at " + ip + ":9090");
            }
            catch (Exception ex)
            {
                this.lblBridgeStatus.Text = "Bridge: Error";
                this.lblBridgeStatus.Foreground = new SolidColorBrush(Color.FromRgb(243, 139, 168));
                MessageBox.Show("ROS Connection Error: " + ex.Message);
            }
        }

        private void BtnStop_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                if (!this.isPredictionSessionActive) return;
                this.isPredictionSessionActive = false;

                if (this.predictionCsvWriter != null)
                {
                    this.predictionCsvWriter.Close();
                    this.predictionCsvWriter = null;
                }

                // Ask for Scenario ID AFTER stop
                var dialog = new ScenarioInputDialog();
                if (dialog.ShowDialog() == true)
                {
                    this.currentTargetId = dialog.ScenarioId;
                    
                    // Rename temp to final
                    string modelName = this.predictionManager?.ActiveModel ?? "unknown";
                    string finalPath = Path.Combine(Path.GetDirectoryName(this.predictionCsvPath),
                        $"prediction_{modelName}_s{this.currentTargetId}_{DateTime.Now:yyyyMMdd_HHmmss}.csv");
                    
                    if (File.Exists(this.predictionCsvPath))
                    {
                        File.Move(this.predictionCsvPath, finalPath);
                        this.predictionCsvPath = finalPath;
                    }
                }

                this.lblRecording.Text = "Prediction: Inactive";
                this.lblRecording.Foreground = new SolidColorBrush(Color.FromRgb(250, 179, 135)); // orange
                this.txtSavePath.Text = this.predictionCsvPath;

                if (this.predictionSampleCount > 0)
                {
                    double maeAvg = (this.sumAbsErrX + this.sumAbsErrY + this.sumAbsErrZ) / (3.0 * this.predictionSampleCount);
                    this.LogEvent($"Session Stopped. Samples: {this.predictionSampleCount}, MAE: {maeAvg:F4}");
                    
                    MessageBox.Show(string.Format(CultureInfo.InvariantCulture,
                        "Prediction session saved.\n\nSamples: {0}\nMAE: {1:F4}\nFile: {2}",
                        this.predictionSampleCount, maeAvg, this.predictionCsvPath ?? "-"));
                }
                else
                {
                    this.LogEvent("Session Stopped (No samples)");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to stop: " + ex.Message);
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





        //private void CboMode_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
        //{
        //    this.currentMode = this.cboMode.SelectedIndex + 1;
        //}

        // other existing methods remain unchanged
    }
}
