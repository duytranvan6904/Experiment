using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
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
        
        private float[] posOffset = null;
        private readonly float[] targetFirst = new float[] { 0.158f, 0.028f, 0.015f };

        public bool IsReady { get; private set; } = false;
        public string ActiveModel { get; private set; } = "gru";

        public event Action<PredictionResult> PredictionReceived;

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
                pythonProcess.ErrorDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) Debug.WriteLine($"[Python Error] {e.Data}"); };
                
                pythonProcess.Start();
                pythonProcess.BeginErrorReadLine();

                pythonStdin = pythonProcess.StandardInput;
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
                pythonStdin.Flush();

                // Start reader task
                Task.Run(() => ReadLoop());
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Failed to start Prediction Worker: {ex.Message}");
            }
        }

        private async Task ReadLoop()
        {
            while (pythonProcess != null && !pythonProcess.HasExited)
            {
                try
                {
                    string line = await pythonStdout.ReadLineAsync();
                    if (string.IsNullOrEmpty(line)) break;

                    var result = JsonConvert.DeserializeObject<PredictionResult>(line);
                    if (result.type == "ready")
                    {
                        IsReady = result.success;
                        Debug.WriteLine($"Prediction Worker Ready: {result.message}");
                    }
                    else if (result.type == "predict")
                    {
                        if (result.prediction != null && posOffset != null)
                        {
                            float predX = (float)result.prediction[0] - posOffset[0];
                            float predY_centered = (float)result.prediction[1];
                            float predZ_centered = (float)result.prediction[2];
                            
                            float predY = predZ_centered - posOffset[2];
                            float predZ = predY_centered - posOffset[1];

                            result.FinalX = predX;
                            result.FinalY = predY;
                            result.FinalZ = predZ;

                            PredictionReceived?.Invoke(result);
                        }
                    }
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"Error reading from Python: {ex.Message}");
                }
            }
        }

        public void AddDataPoint(CameraSpacePoint point)
        {
            float swX = point.X;
            float swY = point.Z;
            float swZ = point.Y;

            if (posOffset == null)
            {
                posOffset = new float[] {
                    targetFirst[0] - swX,
                    targetFirst[1] - swY,
                    targetFirst[2] - swZ
                };
            }

            float[] swappedCentered = new float[] {
                swX + posOffset[0],
                swY + posOffset[1],
                swZ + posOffset[2]
            };

            if (windowBuffer.Count >= WindowSize)
            {
                windowBuffer.Dequeue();
            }
            windowBuffer.Enqueue(swappedCentered);

            if (IsReady && windowBuffer.Count == WindowSize)
            {
                var cmd = new
                {
                    cmd = "predict",
                    data = windowBuffer.ToArray()
                };
                pythonStdin.WriteLine(JsonConvert.SerializeObject(cmd));
                pythonStdin.Flush();
            }
        }

        public void LoadModel(string modelName)
        {
            if (pythonStdin != null && !string.IsNullOrEmpty(modelName))
            {
                var cmd = new { cmd = "load_model", model_name = modelName };
                pythonStdin.WriteLine(JsonConvert.SerializeObject(cmd));
                pythonStdin.Flush();
                ActiveModel = modelName;
            }
        }

        public void Reset()
        {
            windowBuffer.Clear();
            posOffset = null;
        }

        public void Dispose()
        {
            if (pythonProcess != null && !pythonProcess.HasExited)
            {
                try
                {
                    pythonStdin.WriteLine(JsonConvert.SerializeObject(new { cmd = "shutdown" }));
                    pythonStdin.Flush();
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
        public double[] prediction { get; set; }
        public double inference_ms { get; set; }
        public string model_name { get; set; }
        
        // Final coordinates mapped back to camera space
        public float FinalX { get; set; }
        public float FinalY { get; set; }
        public float FinalZ { get; set; }
    }
}
