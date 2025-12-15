using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Kinect;
using System.Globalization;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    // Records trajectories at a fixed rate (default 20 Hz) into CSV files.
    public class TrajectoryRecorder : IDisposable
    {
        private readonly object sync = new object();
        private StreamWriter writer;
        private CancellationTokenSource cts;
        private int hz = 20;
        private int maxFrames = int.MaxValue;
        private TimeSpan maxTime = TimeSpan.MaxValue;
        private int recorded = 0;
        private DateTime startTime;
        private string currentFilePath;

        public event Action RecordingStopped;

        public int FrequencyHz
        {
            get => hz;
            set
            {
                if (value <= 0) throw new ArgumentOutOfRangeException(nameof(FrequencyHz));
                hz = value;
            }
        }

        public int MaxFrames { get => maxFrames; set => maxFrames = value; }
        public TimeSpan MaxTime { get => maxTime; set => maxTime = value; }

        public bool IsRecording { get; private set; }

        // Expose read-only status for UI
        public int RecordedFrames { get { lock (sync) return recorded; } }
        public DateTime? StartTimestamp { get { lock (sync) return IsRecording ? (DateTime?)startTime : null; } }
        public string CurrentFilePath { get { lock (sync) return currentFilePath; } }

        public void Start(string filePath)
        {
            lock (sync)
            {
                if (IsRecording) return;
                this.writer = new StreamWriter(File.Open(filePath, FileMode.Create, FileAccess.Write, FileShare.Read));
                this.writer.WriteLine("timestamp,x,y,z,joint,mode,targetId");
                this.cts = new CancellationTokenSource();
                this.recorded = 0;
                this.startTime = DateTime.UtcNow;
                this.currentFilePath = filePath;
                this.IsRecording = true;

                Task.Run(() => RecordingLoop(this.cts.Token));
            }
        }

        public void Stop()
        {
            lock (sync)
            {
                if (!IsRecording) return;
                this.cts.Cancel();
                this.IsRecording = false;
                try { this.writer?.Flush(); this.writer?.Close(); } catch { }
                this.writer = null;
                var stopped = RecordingStopped;
                if (stopped != null)
                {
                    // invoke outside lock
                    Task.Run(() => stopped());
                }
            }
        }

        public void Dispose()
        {
            Stop();
        }

        // Call this to append a sample (time aligned to recorder rate). This will be buffered and written by the loop.
        public void AppendSample(DateTime timestamp, float x, float y, float z, string joint, string mode, int targetId)
        {
            // We write samples directly (thread-safe)
            lock (sync)
            {
                if (!IsRecording) return;
                var ts = timestamp.ToString("o", CultureInfo.InvariantCulture);
                var line = string.Format(CultureInfo.InvariantCulture, "{0},{1:F6},{2:F6},{3:F6},{4},{5},{6}", ts, x, y, z, joint, mode, targetId);
                this.writer.WriteLine(line);
                this.recorded++;

                if (this.recorded >= this.maxFrames) this.Stop();
                if (DateTime.UtcNow - this.startTime >= this.maxTime) this.Stop();
            }
        }

        private async Task RecordingLoop(CancellationToken token)
        {
            var interval = TimeSpan.FromMilliseconds(1000.0 / hz);
            while (!token.IsCancellationRequested)
            {
                await Task.Delay(interval, token).ConfigureAwait(false);
                // flush periodically
                lock (sync)
                {
                    try { this.writer?.Flush(); } catch { }
                }
            }
        }
    }
}
