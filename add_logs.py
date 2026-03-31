import re

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'r', encoding='utf-8') as f:
    code = f.read()

# Add a first LogEvent in the constructor after predictionManager setup
old_init = 'this.LogEvent("Prediction Pipeline Initialized");'
new_init = 'this.LogEvent("Prediction Pipeline Initialized");\n            this.LogEvent($"Search Python: {pythonPath}");'

code = code.replace(old_init, new_init)

# In PredictionReceived, add a small log on first prediction
old_callback_top = 'this.lastPrediction = res;'
new_callback_top = '''this.lastPrediction = res;
                if (this.predictionSampleCount == 0 && this.isPredictionSessionActive) {
                    this.LogEvent($"First pred received: {res.model_name}");
                }'''

code = code.replace(old_callback_top, new_callback_top)

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'w', encoding='utf-8') as f:
    f.write(code)
