import re

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'r', encoding='utf-8') as f:
    code = f.read()

# Remove lblKinect
code = re.sub(r'this\.lblKinect\.Text(.*?);', '', code)

# Remove txtCountdown
code = re.sub(r'this\.txtCountdown\.Text(.*?);', '', code)

# Check if LogEvent exists
if 'private void LogEvent(' not in code:
    # insert LogEvent right after UI timer tick
    code = code.replace(
        'private void UiTimer_Tick(object sender, EventArgs e)\n        {',
        '''private void LogEvent(string msg)
        {
            this.Dispatcher.BeginInvoke(new Action(() =>
            {
                this.lstLog.Items.Insert(0, $"[{DateTime.Now:HH:mm:ss}] {msg}");
                if (this.lstLog.Items.Count > 50) this.lstLog.Items.RemoveAt(50);
            }));
        }

        private void UiTimer_Tick(object sender, EventArgs e)\n        {'''
    )

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml.cs', 'w', encoding='utf-8') as f:
    f.write(code)

print("Errors fixed!")
