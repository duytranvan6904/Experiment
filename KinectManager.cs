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

        // IDs of tracked bodies
        public ulong? LeaderBodyId { get; private set; }
        public ulong? FollowerBodyId { get; private set; }
        
        // Backwards compatibility / Primary tracked ID
        public ulong? TrackedBodyId => LeaderBodyId;

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

                // Identify Leader (1st valid) and Follower (2nd valid)
                Body leader = null;
                Body follower = null;
                
                int foundCount = 0;
                foreach (var b in this.bodies)
                {
                    if (b != null && b.IsTracked)
                    {
                        if (foundCount == 0) leader = b;
                        else if (foundCount == 1) follower = b;
                        
                        foundCount++;
                        if (foundCount >= 2) break;
                    }
                }

                var ts = DateTime.UtcNow;

                // Process Leader
                if (leader != null)
                {
                    this.LeaderBodyId = leader.TrackingId;
                    var joints = leader.Joints;
                    // Leader: Track Right Wrist
                    var right = joints[JointType.WristRight].Position;
                    this.HandUpdated?.Invoke(new HandJointUpdate { Timestamp = ts, TrackingId = leader.TrackingId, Joint = JointType.WristRight, Position = right, Role = "Leader" });
                }
                else
                {
                    this.LeaderBodyId = null;
                }

                // Process Follower
                if (follower != null)
                {
                    this.FollowerBodyId = follower.TrackingId;
                    var joints = follower.Joints;
                    // Follower: Track Left Wrist
                    var left = joints[JointType.WristLeft].Position;
                    this.HandUpdated?.Invoke(new HandJointUpdate { Timestamp = ts, TrackingId = follower.TrackingId, Joint = JointType.WristLeft, Position = left, Role = "Follower" });
                }
                else
                {
                    this.FollowerBodyId = null;
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
        public string Role; // "Leader" or "Follower"
    }
}
