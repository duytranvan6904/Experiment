import re

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update Constructor to initialize lstLog and add diagnostics
# Replace this.predictionManager.PredictionReceived block with logging
old_pred_received = '''            this.predictionManager.PredictionReceived += (res) =>
            {
                this.lastPrediction = res;
                
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

                        // Update MAE/MSE labels
                        int n = this.predictionSampleCount;
                        this.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            double maeAvg = (this.sumAbsErrX + this.sumAbsErrY + this.sumAbsErrZ) / (3.0 * n);
                            double mseAvg = (this.sumSqErrX + this.sumSqErrY + this.sumSqErrZ) / (3.0 * n);
                            this.lblMAE.Text = string.Format(CultureInfo.InvariantCulture, "MAE: {0:F4} (n={1})", maeAvg, n);
                            this.lblMSE.Text = string.Format(CultureInfo.InvariantCulture, "MSE: {0:F6}", mseAvg);
                        }));
                    }
                    catch (Exception ex)
                    {
                        Debug.WriteLine("CSV write failed: " + ex.Message);
                    }
                }

                // Send prediction to ROS via TCP
                if (this.rosWriter != null)
                {
                    try
                    {
                        string json = string.Format(CultureInfo.InvariantCulture,
                            "{{\\"x\\": {0:F6}, \\"y\\": {1:F6}, \\"z\\": {2:F6}, \\"inference_ms\\": {3:F2}, \\"model_name\\": \\"{4}\\", \\"confidence\\": {5:F2}}}",
                            res.FinalX, res.FinalY, res.FinalZ, res.inference_ms, res.model_name, 1.0);
                        this.rosWriter.WriteLine(json);
                    }
                    catch { }
                }
            };'''

new_pred_received = '''            this.predictionManager.PredictionReceived += (res) =>
            {
                this.lastPrediction = res;
                
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
                            "{{\\"x\\": {0:F6}, \\"y\\": {1:F6}, \\"z\\": {2:F6}, \\"inference_ms\\": {3:F2}, \\"model_name\\": \\"{4}\\", \\"confidence\\": {5:F2}}}",
                            res.FinalX, res.FinalY, res.FinalZ, res.inference_ms, res.model_name, 1.0);
                        this.rosWriter.WriteLine(json);
                    }
                    catch { }
                }
            };
            this.LogEvent("Prediction Pipeline Initialized");'''

# Use more literal regex or exact string match. The multi_replace failed earlier.
code = code.replace(old_pred_received, new_pred_received)

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'w', encoding='utf-8') as f:
    f.write(code)

print("MainWindow constructor logic and logging updated!")
