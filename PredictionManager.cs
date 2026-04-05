using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Kinect;
using Newtonsoft.Json;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    public class PredictionManager : IDisposable
    {
        private const int WindowSize = 20;
        private const int NumFeatures = 3;
        private readonly Queue<float[]> windowBuffer = new Queue<float[]>();
        
        public int BufferCount => windowBuffer.Count;

        private Process pythonProcess;
        private StreamWriter pythonStdin;
        private StreamReader pythonStdout;
        
        // Drop-frame: only one prediction in-flight at a time
        private volatile bool isPredicting = false;

        // Spike suppression for initial frames
        private int predictionSequenceCount = 0;
        private float[] lastHandPoint = new float[3];

        // Outlier clamping: max allowed jump per prediction (meters)
        private float lastPredX, lastPredY, lastPredZ;
        private const float MaxJumpPerPrediction = 0.08f; // 8 cm max jump

        public bool IsReady { get; private set; } = false;
        public string ActiveModel { get; private set; } = "gru";

        public event Action<PredictionResult> PredictionReceived;
        public event Action<string> ErrorReceived;

        public PredictionManager(string pythonPath, string workerScriptPath, string modelDir)
        {
            StartWorker(pythonPath, workerScriptPath, modelDir);
        }

        private void StartWorker(string pythonPath, string workerScriptPath, string modelDir)
        {
            try
            {
                var startInfo = new ProcessStartInfo
                {
                    FileName = pythonPath,
                    Arguments = $"\"{workerScriptPath}\"",
                    UseShellExecute = false,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };

                pythonProcess = new Process { StartInfo = startInfo };
                pythonProcess.Start();

                // Elevate Python process priority so inference doesn't get starved
                try { pythonProcess.PriorityClass = ProcessPriorityClass.AboveNormal; } catch { }

                // Also elevate THIS process (the WPF app) to High so the UI thread doesn't get starved
                try { Process.GetCurrentProcess().PriorityClass = ProcessPriorityClass.High; } catch { }

                pythonProcess.ErrorDataReceived += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(e.Data))
                    {
                        Debug.WriteLine($"[Python Error] {e.Data}");
                        ErrorReceived?.Invoke(e.Data);
                    }
                };

                pythonProcess.BeginErrorReadLine();

                pythonStdin = pythonProcess.StandardInput;
                // Use AutoFlush to avoid buffering delays
                pythonStdin.AutoFlush = true;
                pythonStdout = pythonProcess.StandardOutput;

                // Send initial config
                var config = new
                {
                    model_dir = modelDir,
                    model_files = new Dictionary<string, string>
                    {
                        { "rnn", "rnn_velocity_3_layers.h5" },
                        { "gru", "gru_velocity_3_layers.h5" },
                        { "lstm", "lstm_velocity_3_layers.h5" }
                    },
                    scaler_x_file = "scaler_x.pkl",
                    scaler_y_file = "scaler_y.pkl",
                    default_model = ActiveModel,
                    num_features = NumFeatures,
                    window_size = WindowSize
                };

                pythonStdin.WriteLine(JsonConvert.SerializeObject(config));

                // Start reader on a dedicated thread (not ThreadPool) with high priority
                var readerThread = new Thread(() => ReadLoop())
                {
                    IsBackground = true,
                    Name = "PredictionReader",
                    Priority = ThreadPriority.AboveNormal
                };
                readerThread.Start();
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Failed to start Prediction Worker: {ex.Message}");
            }
        }

        private void ReadLoop()
        {
            try
            {
                while (pythonProcess != null && !pythonProcess.HasExited)
                {
                    string line = pythonStdout.ReadLine(); // blocking read, no async overhead
                    if (string.IsNullOrEmpty(line))
                    {
                        ErrorReceived?.Invoke("Python stdout closed (process may have exited)");
                        break;
                    }

                    PredictionResult result;
                    try
                    {
                        result = JsonConvert.DeserializeObject<PredictionResult>(line);
                    }
                    catch
                    {
                        // Non-JSON output from Python (e.g. TensorFlow warnings)
                        ErrorReceived?.Invoke("stdout: " + line);
                        continue;
                    }

                    if (result.type == "ready")
                    {
                        IsReady = result.success;
                        ErrorReceived?.Invoke($"Worker ready={result.success}: {result.message}");
                        if (!result.success)
                        {
                            ErrorReceived?.Invoke("Init Failed: " + result.message);
                        }
                    }
                    else if (result.type == "model_loaded")
                    {
                        ErrorReceived?.Invoke($"Model loaded: {result.model_name} ok={result.success}");
                        if (result.success) ActiveModel = result.model_name;
                    }
                    else if (result.type == "predict")
                    {
                        // Release the lock IMMEDIATELY so next frame can be sent
                        isPredicting = false;

                        if (!string.IsNullOrEmpty(result.error))
                        {
                            ErrorReceived?.Invoke("Predict Error: " + result.error);
                            continue;
                        }

                        if (result.prediction != null)
                        {
                            float rawX = (float)result.prediction[0];
                            float rawY = (float)result.prediction[1];
                            float rawZ = (float)result.prediction[2];

                            if (predictionSequenceCount < 3)
                            {
                                // First 3 predictions: use actual hand position to avoid initial spikes
                                result.FinalX = lastHandPoint[0];
                                result.FinalY = lastHandPoint[1];
                                result.FinalZ = lastHandPoint[2];
                                // Seed last-pred so clamping works from frame 3+
                                lastPredX = lastHandPoint[0];
                                lastPredY = lastHandPoint[1];
                                lastPredZ = lastHandPoint[2];
                            }
                            else
                            {
                                // Clamp each axis: if model jumps > MaxJumpPerPrediction, limit it
                                result.FinalX = Clamp(rawX, lastPredX, MaxJumpPerPrediction);
                                result.FinalY = Clamp(rawY, lastPredY, MaxJumpPerPrediction);
                                result.FinalZ = Clamp(rawZ, lastPredZ, MaxJumpPerPrediction);
                                lastPredX = result.FinalX;
                                lastPredY = result.FinalY;
                                lastPredZ = result.FinalZ;
                            }

                            predictionSequenceCount++;
                            PredictionReceived?.Invoke(result);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                ErrorReceived?.Invoke($"ReadLoop error: {ex.Message}");
            }

            // Log process exit
            if (pythonProcess != null)
            {
                try
                {
                    ErrorReceived?.Invoke($"Python process exited with code: {pythonProcess.ExitCode}");
                }
                catch { }
            }
        }

        private static float Clamp(float value, float previous, float maxDelta)
        {
            float delta = value - previous;
            if (delta > maxDelta) return previous + maxDelta;
            if (delta < -maxDelta) return previous - maxDelta;
            return value;
        }

        public void AddDataPoint(CameraSpacePoint point)
        {
            if (float.IsNaN(point.X) || float.IsNaN(point.Y) || float.IsNaN(point.Z)) return;

            // Point is already transformed and mapped to experimental frame by MainWindow
            float[] data = new float[] { point.X, point.Y, point.Z };

            if (windowBuffer.Count >= WindowSize)
            {
                windowBuffer.Dequeue();
            }
            windowBuffer.Enqueue(data);

            // Record latest hand position for soft-start reference
            lastHandPoint[0] = data[0];
            lastHandPoint[1] = data[1];
            lastHandPoint[2] = data[2];

            // Drop-frame strategy: only send predict request if we aren't waiting for one
            // This prevents stdin queue buildup which causes latency and UI jank
            if (IsReady && windowBuffer.Count == WindowSize && !isPredicting)
            {
                isPredicting = true;
                try
                {
                    var cmd = new
                    {
                        cmd = "predict",
                        data = windowBuffer.ToArray()
                    };
                    pythonStdin.WriteLine(JsonConvert.SerializeObject(cmd));
                }
                catch (Exception ex)
                {
                    isPredicting = false;
                    ErrorReceived?.Invoke("Stdin write error: " + ex.Message);
                }
            }
        }

        public void Reset()
        {
            windowBuffer.Clear();
            predictionSequenceCount = 0;
            isPredicting = false;
            ErrorReceived?.Invoke("Prediction session reset: buffer cleared.");
        }

        public void LoadModel(string modelName)
        {
            if (pythonStdin != null && !string.IsNullOrEmpty(modelName))
            {
                var cmd = new { cmd = "load_model", model_name = modelName };
                pythonStdin.WriteLine(JsonConvert.SerializeObject(cmd));
                ActiveModel = modelName;
            }
        }

        public void Dispose()
        {
            if (pythonProcess != null && !pythonProcess.HasExited)
            {
                try
                {
                    pythonStdin.WriteLine(JsonConvert.SerializeObject(new { cmd = "shutdown" }));
                    pythonProcess.WaitForExit(1000);
                }
                catch { }
                finally
                {
                    if (!pythonProcess.HasExited) pythonProcess.Kill();
                }
            }
        }
    }

    public class PredictionResult
    {
        public string type { get; set; }
        public bool success { get; set; }
        public string message { get; set; }
        public string error { get; set; }
        public double[] prediction { get; set; }
        public double inference_ms { get; set; }
        public string model_name { get; set; }
        
        // Final coordinates mapped back to camera space
        public float FinalX { get; set; }
        public float FinalY { get; set; }
        public float FinalZ { get; set; }
    }
}
