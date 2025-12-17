using System;
using Microsoft.Kinect;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    // Lightweight wrapper around a single Kinect sensor instance.
    // - Exposes SensorId ("Cam1" / "Cam2")
    // - Raises raw hand updates and transformed world-space hand updates
    // - Integrates with DualCameraCalibrationManager to map camera-space -> world-space
    public class KinectSensorWrapper : IDisposable
    {
        public string SensorId { get; }

        private KinectSensor sensor;
        private BodyFrameReader bodyReader;
        private Body[] bodies;
        private DualCameraCalibrationManager calibManager;

        public bool IsAvailable => this.sensor != null && this.sensor.IsAvailable;

        // Expose tracked body id
        public ulong? TrackedBodyId { get; private set; }

        // Raw hand update (camera-space)
        public event Action<HandJointUpdate> RawHandUpdated;

        // World-space hand update after applying calibration
        public event Action<HandJointUpdate> WorldHandUpdated;

        public KinectSensorWrapper(string sensorId, DualCameraCalibrationManager calibrationManager)
        {
            this.SensorId = sensorId ?? "Cam1";
            this.calibManager = calibrationManager ?? throw new ArgumentNullException(nameof(calibrationManager));

            this.sensor = KinectSensor.GetDefault();
            if (this.sensor == null)
                throw new InvalidOperationException("No Kinect sensor found.");

            this.bodies = null;

            this.bodyReader = this.sensor.BodyFrameSource.OpenReader();
            this.bodyReader.FrameArrived += BodyReader_FrameArrived;

            this.sensor.IsAvailableChanged += (s, e) => { /* could propagate */ };

            this.sensor.Open();
        }

        private void BodyReader_FrameArrived(object sender, BodyFrameArrivedEventArgs e)
        {
            using (var frame = e.FrameReference.AcquireFrame())
            {
                if (frame == null) return;

                if (this.bodies == null)
                {
                    this.bodies = new Body[frame.BodyCount];
                }

                frame.GetAndRefreshBodyData(this.bodies);

                // update floor plane in calibration manager if available
                try
                {
                    this.calibManager?.UpdateFloorPlane(this.SensorId, frame.FloorClipPlane);
                }
                catch { }

                // find first tracked body
                Body primary = null;
                foreach (var b in this.bodies)
                {
                    if (b != null && b.IsTracked)
                    {
                        primary = b;
                        break;
                    }
                }

                if (primary != null)
                {
                    if (this.TrackedBodyId == null || this.TrackedBodyId != primary.TrackingId)
                    {
                        this.TrackedBodyId = primary.TrackingId;
                    }

                    var joints = primary.Joints;
                    var left = joints[JointType.HandLeft].Position;
                    var right = joints[JointType.HandRight].Position;

                    var ts = DateTime.UtcNow;

                    var leftUpdate = new HandJointUpdate { Timestamp = ts, TrackingId = primary.TrackingId, Joint = JointType.HandLeft, Position = left };
                    var rightUpdate = new HandJointUpdate { Timestamp = ts, TrackingId = primary.TrackingId, Joint = JointType.HandRight, Position = right };

                    // raise raw updates
                    try { RawHandUpdated?.Invoke(leftUpdate); } catch { }
                    try { RawHandUpdated?.Invoke(rightUpdate); } catch { }

                    // apply calibration -> world
                    try
                    {
                        var leftWorld = this.calibManager.ApplyCalibration(this.SensorId, left);
                        var rightWorld = this.calibManager.ApplyCalibration(this.SensorId, right);

                        var lwu = new HandJointUpdate { Timestamp = ts, TrackingId = primary.TrackingId, Joint = JointType.HandLeft, Position = leftWorld };
                        var rwu = new HandJointUpdate { Timestamp = ts, TrackingId = primary.TrackingId, Joint = JointType.HandRight, Position = rightWorld };

                        WorldHandUpdated?.Invoke(lwu);
                        WorldHandUpdated?.Invoke(rwu);
                    }
                    catch { }
                }
                else
                {
                    this.TrackedBodyId = null;
                }
            }
        }

        public void Dispose()
        {
            if (this.bodyReader != null)
            {
                this.bodyReader.FrameArrived -= BodyReader_FrameArrived;
                this.bodyReader.Dispose();
                this.bodyReader = null;
            }

            if (this.sensor != null)
            {
                this.sensor.Close();
                this.sensor = null;
            }
        }
    }
}
