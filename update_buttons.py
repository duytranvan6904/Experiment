import re

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace BtnStart_Click
old_start = '''        // Button handlers wired in XAML
        private void BtnStart_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new ScenarioInputDialog();
            if (dialog.ShowDialog() != true) return;
            
            this.currentTargetId = dialog.ScenarioId;
            this.txtCurrentScenario.Text = $"Current Scenario: {this.currentTargetId}";

            if (double.TryParse(this.txtYThreshold.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out double yThresh))
            {
                this.yThresholdTarget = yThresh;
            }
            else
            {
                this.yThresholdTarget = 1.0;
            }
            this.hasTriggeredChange = false;

            // start recorder and sampling timer
            try
            {
                // parse limits from UI
                int maxFrames = 0;
                double maxTimeSeconds = 0;
                if (!int.TryParse(this.txtMaxFrames.Text, out maxFrames)) maxFrames = 0;
                if (!double.TryParse(this.txtMaxTime.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out maxTimeSeconds)) maxTimeSeconds = 0;

                this.recorder.MaxFrames = (maxFrames <= 0) ? int.MaxValue : maxFrames;
                this.recorder.MaxTime = (maxTimeSeconds <= 0) ? TimeSpan.MaxValue : TimeSpan.FromSeconds(maxTimeSeconds);

                // Save files into project-relative folder (under application output directory).
                // Folders `RecordTrajectories\\RawRecord` are expected to exist in the project (or as content copied to output).
                var folder = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "RecordTrajectories", "RawRecord");
                Directory.CreateDirectory(folder);
                var filename1 = Path.Combine(folder, $"cam1_{DateTime.Now:yyyyMMdd_HHmm}.csv");
                var filename2 = Path.Combine(folder, $"cam2_{DateTime.Now:yyyyMMdd_HHmm}.csv");

                // Determine which recorder(s) to start based on preferredRecorderTarget
                var target = this.preferredRecorderTarget; // "Cam1", "Cam2" or null for both
                bool startBoth = string.IsNullOrEmpty(target);

                if (startBoth || string.Equals(target, "Cam1", StringComparison.OrdinalIgnoreCase))
                {
                    this.recorder.Start(filename1, "Cam1", "1");
                }

                if (startBoth || string.Equals(target, "Cam2", StringComparison.OrdinalIgnoreCase))
                {
                    try { this.recorderCam2.Start(filename2, "Cam2", "1"); } catch { }
                }

                // show path and start timers
                string savePathDisplay = "-";
                if (startBoth)
                {
                    savePathDisplay = (this.recorder.CurrentFilePath ?? "-") + " ; " + (this.recorderCam2?.CurrentFilePath ?? "-");
                }
                else if (string.Equals(target, "Cam1", StringComparison.OrdinalIgnoreCase))
                {
                    savePathDisplay = this.recorder.CurrentFilePath ?? "-";
                }
                else if (string.Equals(target, "Cam2", StringComparison.OrdinalIgnoreCase))
                {
                    savePathDisplay = this.recorderCam2?.CurrentFilePath ?? "-";
                }

                this.txtSavePath.Text = "Save path: " + savePathDisplay;
                this.samplingTimer.Interval = 1000.0 / this.recorder.FrequencyHz;
                this.samplingTimer.Start();
                this.uiTimer.Start();

                this.lblRecording.Text = "Recording: Active";
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to start recorder: " + ex.Message);
            }
        }'''

new_start = '''        // Button handlers wired in XAML
        private void BtnStart_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new ScenarioInputDialog();
            if (dialog.ShowDialog() != true) return;
            
            this.currentTargetId = dialog.ScenarioId;
            this.txtCurrentScenario.Text = $"Scenario: {this.currentTargetId}";

            if (double.TryParse(this.txtYThreshold.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out double yThresh))
            {
                this.yThresholdTarget = yThresh;
            }
            else
            {
                this.yThresholdTarget = 1.0;
            }
            this.hasTriggeredChange = false;

            // Start prediction session - create CSV file for evaluation
            try
            {
                string modelName = this.predictionManager?.ActiveModel ?? "gru";
                var folder = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "PredictionResults");
                Directory.CreateDirectory(folder);
                this.predictionCsvPath = Path.Combine(folder,
                    $"prediction_{modelName}_s{this.currentTargetId}_{DateTime.Now:yyyyMMdd_HHmmss}.csv");

                this.predictionCsvWriter = new StreamWriter(this.predictionCsvPath, false, new UTF8Encoding(false));
                this.predictionCsvWriter.WriteLine("timestamp,actual_x,actual_y,actual_z,predicted_x,predicted_y,predicted_z,inference_ms,model_name,scenario_id,abs_err_x,abs_err_y,abs_err_z");
                this.predictionCsvWriter.Flush();

                // Reset metrics
                this.predictionSampleCount = 0;
                this.sumAbsErrX = 0; this.sumAbsErrY = 0; this.sumAbsErrZ = 0;
                this.sumSqErrX = 0; this.sumSqErrY = 0; this.sumSqErrZ = 0;

                this.isPredictionSessionActive = true;
                this.txtSavePath.Text = this.predictionCsvPath;
                this.lblRecording.Text = "Prediction: Active";
                this.lblRecording.Foreground = new SolidColorBrush(Color.FromRgb(166, 227, 161)); // green
                this.lblMAE.Text = "MAE: -";
                this.lblMSE.Text = "MSE: -";

                // Also reset prediction manager buffer for clean start
                this.predictionManager?.Reset();
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to start prediction session: " + ex.Message);
            }
        }'''

code = code.replace(old_start, new_start)

# Replace BtnStop_Click
old_stop = '''        private void BtnStop_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                this.samplingTimer.Stop();
                this.uiTimer.Stop();
                this.recorder.Stop();
                this.recorderCam2.Stop();
                this.lblRecording.Text = "Recording: Inactive";
                this.txtCountdown.Text = "Countdown: -";
                this.txtSavePath.Text = "Save path: " + (this.recorder.CurrentFilePath ?? "-");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to stop recorder: " + ex.Message);
            }
        }'''

new_stop = '''        private void BtnStop_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                this.isPredictionSessionActive = false;

                if (this.predictionCsvWriter != null)
                {
                    this.predictionCsvWriter.Close();
                    this.predictionCsvWriter = null;
                }

                this.lblRecording.Text = "Prediction: Inactive";
                this.lblRecording.Foreground = new SolidColorBrush(Color.FromRgb(250, 179, 135)); // orange

                if (this.predictionSampleCount > 0)
                {
                    double maeAvg = (this.sumAbsErrX + this.sumAbsErrY + this.sumAbsErrZ) / (3.0 * this.predictionSampleCount);
                    double mseAvg = (this.sumSqErrX + this.sumSqErrY + this.sumSqErrZ) / (3.0 * this.predictionSampleCount);
                    MessageBox.Show(string.Format(CultureInfo.InvariantCulture,
                        "Prediction session saved.\\n\\nSamples: {0}\\nMAE: {1:F4}\\nMSE: {2:F6}\\n\\nFile: {3}",
                        this.predictionSampleCount, maeAvg, mseAvg, this.predictionCsvPath ?? "-"));
                }
                else
                {
                    MessageBox.Show("Prediction session ended (no samples recorded).\\nFile: " + (this.predictionCsvPath ?? "-"));
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to stop prediction session: " + ex.Message);
            }
        }'''

code = code.replace(old_stop, new_stop)

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'w', encoding='utf-8') as f:
    f.write(code)
    
print("Done - BtnStart and BtnStop replaced!")
