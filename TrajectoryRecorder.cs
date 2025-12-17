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

        // per-recorder identifiers
        private string cameraId = "Cam1";
        private string trialId = "1";

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
        public string CameraId { get { lock (sync) return cameraId; } }
        public string TrialId { get { lock (sync) return trialId; } }

        // Backwards-compatible Start: defaults to Cam1/1
        public void Start(string filePath)
        {
            Start(filePath, "Cam1", "1");
        }

        // New Start overload allows specifying camera and trial identifiers
        public void Start(string filePath, string cameraId, string trialId)
        {
            lock (sync)
            {
                if (IsRecording) return;
                this.cameraId = string.IsNullOrEmpty(cameraId) ? "Cam1" : cameraId;
                this.trialId = string.IsNullOrEmpty(trialId) ? "1" : trialId;

                this.writer = new StreamWriter(File.Open(filePath, FileMode.Create, FileAccess.Write, FileShare.Read));
                // CSV header matches required output
                this.writer.WriteLine("Timestamp,Position_X,Position_Y,Position_Z,Camera_ID,Trial_ID,Modus,Target_ID");
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
        // Extended to accept optional cameraId and trialId so a caller can override per-sample (backward compatible).
        public void AppendSample(DateTime timestamp, float x, float y, float z, string joint, string mode, int targetId, string cameraId = null, string trialId = null)
        {
            // We write samples directly (thread-safe)
            lock (sync)
            {
                if (!IsRecording) return;
                var ts = timestamp.ToString("o", CultureInfo.InvariantCulture);

                // use provided per-sample identifiers or fall back to recorder's defaults
                var cam = string.IsNullOrEmpty(cameraId) ? this.cameraId : cameraId;
                var trial = string.IsNullOrEmpty(trialId) ? this.trialId : trialId;

                var line = string.Format(CultureInfo.InvariantCulture, "{0},{1:F6},{2:F6},{3:F6},{4},{5},{6},{7}", ts, x, y, z, cam, trial, mode, targetId);
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
