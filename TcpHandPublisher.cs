using System;
using System.Globalization;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Kinect;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    /// <summary>
    /// Publishes hand position data over TCP to the Ubuntu ROS 2 bridge node.
    /// 
    /// Usage in MainWindow.xaml.cs:
    ///   1. Add field:    private TcpHandPublisher tcpPublisher;
    ///   2. In constructor (after kinectManager init):
    ///        this.tcpPublisher = new TcpHandPublisher("192.168.1.20", 9090);
    ///   3. In KinectManager_HandUpdated callback (after the existing world transform):
    ///        if (update.Joint == JointType.HandRight)
    ///        {
    ///            var world = this.transformer.Transform(update.Position);
    ///            this.tcpPublisher.Send(world.X, world.Y, world.Z,
    ///                                  update.TrackingId, update.Timestamp);
    ///        }
    ///   4. In MainWindow_Closing:
    ///        this.tcpPublisher?.Dispose();
    ///
    /// Protocol: newline-delimited JSON over TCP.
    /// </summary>
    public class TcpHandPublisher : IDisposable
    {
        private readonly string host;
        private readonly int port;
        private TcpClient client;
        private NetworkStream stream;
        private readonly object sendLock = new object();
        private bool connected = false;
        private CancellationTokenSource cts = new CancellationTokenSource();

        /// <summary>
        /// Create a TCP publisher that connects to the Ubuntu ROS 2 bridge.
        /// </summary>
        /// <param name="ubuntuIp">IP address of the Ubuntu machine (e.g. "192.168.1.20")</param>
        /// <param name="port">TCP port (default 9090, must match bridge_node config)</param>
        public TcpHandPublisher(string ubuntuIp, int port = 9090)
        {
            this.host = ubuntuIp;
            this.port = port;

            // Start background connection loop
            Task.Run(() => ConnectionLoop(this.cts.Token));
        }

        /// <summary>
        /// Send hand position to the bridge node.
        /// Call this from the Kinect hand update callback.
        /// Non-blocking: drops data silently if not connected.
        /// </summary>
        public void Send(float x, float y, float z, ulong trackingId, DateTime timestamp)
        {
            if (!this.connected || this.stream == null)
                return;

            try
            {
                string json = string.Format(
                    CultureInfo.InvariantCulture,
                    "{{\"x\":{0:F6},\"y\":{1:F6},\"z\":{2:F6},\"id\":{3},\"ts\":\"{4:o}\",\"tracked\":true,\"confidence\":1.0}}\n",
                    x, y, z, trackingId, timestamp);

                byte[] data = Encoding.UTF8.GetBytes(json);

                lock (this.sendLock)
                {
                    if (this.stream != null && this.stream.CanWrite)
                    {
                        this.stream.Write(data, 0, data.Length);
                    }
                }
            }
            catch (Exception)
            {
                // Connection lost — will be reconnected by background loop
                this.connected = false;
            }
        }

        /// <summary>
        /// Background loop that maintains TCP connection with auto-reconnect.
        /// </summary>
        private async Task ConnectionLoop(CancellationToken token)
        {
            while (!token.IsCancellationRequested)
            {
                if (!this.connected)
                {
                    try
                    {
                        this.client = new TcpClient();
                        this.client.NoDelay = true;
                        this.client.SendBufferSize = 8192;

                        // Connect with timeout
                        var connectTask = this.client.ConnectAsync(this.host, this.port);
                        if (await Task.WhenAny(connectTask, Task.Delay(3000, token)) == connectTask)
                        {
                            await connectTask; // propagate exceptions
                            this.stream = this.client.GetStream();
                            this.connected = true;
                            System.Diagnostics.Debug.WriteLine($"[TcpHandPublisher] Connected to {this.host}:{this.port}");
                        }
                        else
                        {
                            // Timeout
                            CleanupClient();
                        }
                    }
                    catch (Exception ex)
                    {
                        System.Diagnostics.Debug.WriteLine($"[TcpHandPublisher] Connect failed: {ex.Message}");
                        CleanupClient();
                    }
                }

                try { await Task.Delay(2000, token); }
                catch (TaskCanceledException) { break; }
            }
        }

        private void CleanupClient()
        {
            this.connected = false;
            try { this.stream?.Close(); } catch { }
            try { this.client?.Close(); } catch { }
            this.stream = null;
            this.client = null;
        }

        public void Dispose()
        {
            this.cts.Cancel();
            CleanupClient();
        }
    }
}
