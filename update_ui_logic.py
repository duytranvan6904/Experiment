import re

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update Model_Checked and LogEvent
old_checked = '''        private void Model_Checked(object sender, RoutedEventArgs e)
        {
            if (this.predictionManager == null) return;
            var rb = sender as RadioButton;
            if (rb == null || !rb.IsChecked.Value) return;

            string modelName = "gru";
            if (rb == rbRnn) modelName = "rnn";
            else if (rb == rbLstm) modelName = "lstm";

            this.predictionManager.LoadModel(modelName);
        }'''

new_checked = '''        private void Model_Checked(object sender, RoutedEventArgs e)
        {
            if (this.predictionManager == null) return;
            var rb = sender as RadioButton;
            if (rb == null || !rb.IsChecked.Value) return;

            string modelName = "gru";
            if (rb == rbRnn) modelName = "rnn";
            else if (rb == rbLstm) modelName = "lstm";

            this.predictionManager.LoadModel(modelName);
            this.lblActiveModel.Text = $"Model: {modelName.ToUpper()}";
            this.LogEvent($"Model switched to {modelName.ToUpper()}");
        }

        private void LogEvent(string msg)
        {
            this.Dispatcher.BeginInvoke(new Action(() =>
            {
                this.lstLog.Items.Insert(0, $"[{DateTime.Now:HH:mm:ss}] {msg}");
                if (this.lstLog.Items.Count > 50) this.lstLog.Items.RemoveAt(50);
            }));
        }'''

code = code.replace(old_checked, new_checked)

# 2. Update BtnStart_Click (Remove dialog, use temp file)
old_start = '''        // Button handlers wired in XAML
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

new_start = '''        // Button handlers wired in XAML
        private void BtnStart_Click(object sender, RoutedEventArgs e)
        {
            if (double.TryParse(this.txtYThreshold.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out double yThresh))
            {
                this.yThresholdTarget = yThresh;
            }
            else
            {
                this.yThresholdTarget = 1.0;
            }
            this.hasTriggeredChange = false;

            // Start prediction session - capture to temp file first
            try
            {
                var folder = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "PredictionResults");
                Directory.CreateDirectory(folder);
                this.predictionCsvPath = Path.Combine(folder, "last_session_temp.csv");

                this.predictionCsvWriter = new StreamWriter(this.predictionCsvPath, false, new UTF8Encoding(false));
                this.predictionCsvWriter.WriteLine("timestamp,actual_x,actual_y,actual_z,predicted_x,predicted_y,predicted_z,inference_ms,model_name,scenario_id,abs_err_x,abs_err_y,abs_err_z");
                this.predictionCsvWriter.Flush();

                // Reset metrics
                this.predictionSampleCount = 0;
                this.sumAbsErrX = 0; this.sumAbsErrY = 0; this.sumAbsErrZ = 0;
                this.sumSqErrX = 0; this.sumSqErrY = 0; this.sumSqErrZ = 0;

                this.isPredictionSessionActive = true;
                this.txtSavePath.Text = "Capturing to temp file...";
                this.lblRecording.Text = "Prediction: Active";
                this.lblRecording.Foreground = new SolidColorBrush(Color.FromRgb(166, 227, 161)); // green
                this.lblMAE.Text = "MAE: -";
                this.lblMSE.Text = "MSE: -";

                // Also reset prediction manager buffer for clean start
                this.predictionManager?.Reset();
                this.LogEvent("Prediction Started");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to start prediction session: " + ex.Message);
            }
        }'''

code = code.replace(old_start, new_start)

# 3. Update BtnStop_Click (Ask for ID, rename file)
old_stop = '''        private void BtnStop_Click(object sender, RoutedEventArgs e)
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

new_stop = '''        private void BtnStop_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                if (!this.isPredictionSessionActive) return;
                this.isPredictionSessionActive = false;

                if (this.predictionCsvWriter != null)
                {
                    this.predictionCsvWriter.Close();
                    this.predictionCsvWriter = null;
                }

                // Ask for Scenario ID AFTER stop
                var dialog = new ScenarioInputDialog();
                if (dialog.ShowDialog() == true)
                {
                    this.currentTargetId = dialog.ScenarioId;
                    
                    // Rename temp to final
                    string modelName = this.predictionManager?.ActiveModel ?? "unknown";
                    string finalPath = Path.Combine(Path.GetDirectoryName(this.predictionCsvPath),
                        $"prediction_{modelName}_s{this.currentTargetId}_{DateTime.Now:yyyyMMdd_HHmmss}.csv");
                    
                    if (File.Exists(this.predictionCsvPath))
                    {
                        File.Move(this.predictionCsvPath, finalPath);
                        this.predictionCsvPath = finalPath;
                    }
                }

                this.lblRecording.Text = "Prediction: Inactive";
                this.lblRecording.Foreground = new SolidColorBrush(Color.FromRgb(250, 179, 135)); // orange
                this.txtSavePath.Text = this.predictionCsvPath;

                if (this.predictionSampleCount > 0)
                {
                    double maeAvg = (this.sumAbsErrX + this.sumAbsErrY + this.sumAbsErrZ) / (3.0 * this.predictionSampleCount);
                    this.LogEvent($"Session Stopped. Samples: {this.predictionSampleCount}, MAE: {maeAvg:F4}");
                    
                    MessageBox.Show(string.Format(CultureInfo.InvariantCulture,
                        "Prediction session saved.\\n\\nSamples: {0}\\nMAE: {1:F4}\\nFile: {2}",
                        this.predictionSampleCount, maeAvg, this.predictionCsvPath ?? "-"));
                }
                else
                {
                    this.LogEvent("Session Stopped (No samples)");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to stop: " + ex.Message);
            }
        }'''

code = code.replace(old_stop, new_stop)

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'w', encoding='utf-8') as f:
    f.write(code)

print("MainWindow buttons and logging updated!")
