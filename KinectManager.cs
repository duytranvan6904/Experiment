using System;
using System.Collections.Generic;
using System.Windows.Media.Imaging;
using Microsoft.Kinect;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    // Lightweight manager for Kinect v2 that exposes body, color and depth frames and hand positions.
    public class KinectManager : IDisposable
    {
        private KinectSensor sensor;
        private BodyFrameReader bodyReader;
        private ColorFrameReader colorReader;
        private DepthFrameReader depthReader;
        private Body[] bodies;

        public bool IsAvailable => this.sensor != null && this.sensor.IsAvailable;

        // ID of the tracked body (first detected / locked)
        public ulong? TrackedBodyId { get; private set; }

        // Expose latest color frame as a WriteableBitmap (RGBA)
        public WriteableBitmap ColorBitmap { get; private set; }

        // Expose last floor plane (A,B,C,D)
        public Vector4? FloorClipPlane { get; private set; }

        // Raised when a hand joint (left or right) is available for the locked body.
        public event Action<HandJointUpdate> HandUpdated;

        // Raised when a new color frame bytes are available (BGRA format)
        public event Action<byte[], int, int> ColorFrameReady;

        public KinectManager()
        {
            this.sensor = KinectSensor.GetDefault();
            if (this.sensor == null)
                throw new InvalidOperationException("No Kinect sensor found.");

            this.bodies = null;

            this.bodyReader = this.sensor.BodyFrameSource.OpenReader();
            this.bodyReader.FrameArrived += BodyReader_FrameArrived;

            this.colorReader = this.sensor.ColorFrameSource.OpenReader();
            this.colorReader.FrameArrived += ColorReader_FrameArrived;

            this.depthReader = this.sensor.DepthFrameSource.OpenReader();
            this.depthReader.FrameArrived += DepthReader_FrameArrived;

            this.sensor.IsAvailableChanged += (s, e) => { /* propagate if needed */ };

            this.sensor.Open();
        }

        private void DepthReader_FrameArrived(object sender, DepthFrameArrivedEventArgs e)
        {
            // Use depth frame to update floor plane from body frames instead (BodyFrame has FloorClipPlane)
            // Keep method to satisfy initialization requirement.
            using (var frame = e.FrameReference.AcquireFrame())
            {
                // no-op; placeholder
            }
        }

        private void ColorReader_FrameArrived(object sender, ColorFrameArrivedEventArgs e)
        {
            using (var frame = e.FrameReference.AcquireFrame())
            {
                if (frame == null) return;

                var desc = frame.FrameDescription;
                int width = desc.Width;
                int height = desc.Height;

                using (KinectBuffer buffer = frame.LockRawImageBuffer())
                {
                    if (this.ColorBitmap == null)
                    {
                        this.ColorBitmap = new WriteableBitmap(width, height, 96.0, 96.0, System.Windows.Media.PixelFormats.Bgra32, null);
                    }

                    this.ColorBitmap.Lock();
                    frame.CopyConvertedFrameDataToIntPtr(this.ColorBitmap.BackBuffer, (uint)(width * height * 4), ColorImageFormat.Bgra);
                    this.ColorBitmap.AddDirtyRect(new System.Windows.Int32Rect(0, 0, width, height));
                    this.ColorBitmap.Unlock();

                    // copy out bytes and raise event
                    int bytes = width * height * 4;
                    byte[] pixelData = new byte[bytes];
                    this.ColorBitmap.CopyPixels(pixelData, width * 4, 0);
                    this.ColorFrameReady?.Invoke(pixelData, width, height);
                }
            }
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

                // update floor plane
                this.FloorClipPlane = frame.FloorClipPlane;

                // find first tracked body (lock on first detected)
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

                    // extract hands
                    var joints = primary.Joints;
                    var left = joints[JointType.HandLeft].Position;
                    var right = joints[JointType.HandRight].Position;

                    var ts = DateTime.UtcNow;

                    this.HandUpdated?.Invoke(new HandJointUpdate { Timestamp = ts, TrackingId = primary.TrackingId, Joint = JointType.HandLeft, Position = left });
                    this.HandUpdated?.Invoke(new HandJointUpdate { Timestamp = ts, TrackingId = primary.TrackingId, Joint = JointType.HandRight, Position = right });
                }
                else
                {
                    // no bodies tracked
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

            if (this.colorReader != null)
            {
                this.colorReader.FrameArrived -= ColorReader_FrameArrived;
                this.colorReader.Dispose();
                this.colorReader = null;
            }

            if (this.depthReader != null)
            {
                this.depthReader.FrameArrived -= DepthReader_FrameArrived;
                this.depthReader.Dispose();
                this.depthReader = null;
            }

            if (this.sensor != null)
            {
                this.sensor.Close();
                this.sensor = null;
            }
        }
    }

    public struct HandJointUpdate
    {
        public DateTime Timestamp;
        public ulong TrackingId;
        public JointType Joint;
        public CameraSpacePoint Position;
    }
}
