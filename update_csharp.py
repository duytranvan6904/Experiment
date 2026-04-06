import re

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'r', encoding='utf-8') as f:
    code = f.read()

# Remove UI variable assignments that no longer exist
code = re.sub(r'this\.txtXYZCam1\.Text = .*?;', '', code)
code = re.sub(r'this\.txtXYZCam2\.Text = .*?;', '', code)
code = re.sub(r'this\.lblCam1Status\.Text = .*?;', '', code)
code = re.sub(r'this\.lblCam2Status\.Text = .*?;', '', code)

# Remove unused Cam1/Cam2 calibration buttons methods completely
code = re.sub(r'        private void BtnCalibrateCam1_Click.*?MessageBox\.Show\("Cam1 calibration failed: " \+ ex\.Message\);\s*\}\s*\}', '', code, flags=re.DOTALL)
code = re.sub(r'        private void BtnCalibrateCam2_Click.*?MessageBox\.Show\("Cam2 calibration failed: " \+ ex\.Message\);\s*\}\s*\}', '', code, flags=re.DOTALL)

# Update BtnStart_Click
btnstart_updated = '''        private void BtnStart_Click(object sender, RoutedEventArgs e)
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
                int maxFrames = 0;'''
code = code.replace('        private void BtnStart_Click(object sender, RoutedEventArgs e)\n        {\n            // start recorder and sampling timer\n            try\n            {\n                // parse limits from UI\n                int maxFrames = 0;', btnstart_updated)


# Update Cam1_WorldHandUpdated
cam1_updated = '''        private void Cam1_WorldHandUpdated(HandJointUpdate update)
        {
            if (update.Joint == JointType.HandRight)
            {
                this.lastWorldCam1 = update.Position;
                
                // Trigger Change Scene logic if recording
                if (this.recorder != null && this.recorder.IsRecording && !this.hasTriggeredChange)
                {
                    if (this.currentTargetId >= 7 && this.currentTargetId <= 18)
                    {
                        if (update.Position.Y > this.yThresholdTarget)
                        {
                            this.hasTriggeredChange = true;
                            this.Dispatcher.BeginInvoke(new Action(() => {
                                this.txtCurrentScenario.Text = $"Current Scenario: {this.currentTargetId} (CHANGED)";
                            }));
                        }
                    }
                }

                // Feed to local PredictionManager
                this.predictionManager?.AddDataPoint(update.Position);

                // Update plots with MEASURED data even if no prediction yet
                this.Dispatcher.BeginInvoke(new Action(() =>
                {
                    this.plotX.AddPoints(update.Position.X, null);
                    this.plotY.AddPoints(update.Position.Y, null);
                    this.plotZ.AddPoints(update.Position.Z, null);
                    this.lblBufferStatus.Text = $"Buffer: {this.predictionManager.BufferCount}/20";
                }));
            }
        }'''
code = re.sub(r'        private void Cam1_WorldHandUpdated.*?\}\s*\}', cam1_updated, code, flags=re.DOTALL)


with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'w', encoding='utf-8') as f:
    f.write(code)
    
print("Replaced successfully!")
