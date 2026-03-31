using System;
using System.Windows;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    public partial class ScenarioInputDialog : Window
    {
        public int ScenarioId { get; private set; }

        public ScenarioInputDialog()
        {
            InitializeComponent();
            txtScenarioId.TextChanged += TxtScenarioId_TextChanged;
            txtScenarioId.Focus();
        }

        private void TxtScenarioId_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
        {
            // Show scenario info when user types
            if (int.TryParse(txtScenarioId.Text, out int id) && id >= 1 && id <= 18)
            {
                var info = GetScenarioInfo(id);
                txtScenarioInfo.Text = info;
            }
            else
            {
                txtScenarioInfo.Text = "";
            }
        }

        private void BtnOK_Click(object sender, RoutedEventArgs e)
        {
            if (int.TryParse(txtScenarioId.Text, out int id) && id >= 1 && id <= 18)
            {
                ScenarioId = id;
                DialogResult = true;
                Close();
            }
            else
            {
                MessageBox.Show("Please enter a valid Scenario ID (1-18).", "Invalid Input", 
                    MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }

        private void BtnCancel_Click(object sender, RoutedEventArgs e)
        {
            DialogResult = false;
            Close();
        }

        private string GetScenarioInfo(int scenarioId)
        {
            // Based on the scenario mapping from Python GUI
            switch (scenarioId)
            {
                case 1: return "Mode: Free | Target: 1 → 1";
                case 2: return "Mode: Free | Target: 2 → 2";
                case 3: return "Mode: Free | Target: 3 → 3";
                
                case 4: return "Mode: Obstacle | Target: 1 → 1";
                case 5: return "Mode: Obstacle | Target: 2 → 2";
                case 6: return "Mode: Obstacle | Target: 3 → 3";
                
                case 7: return "Mode: Change | Target: 1 → 2";
                case 8: return "Mode: Change | Target: 1 → 3";
                case 9: return "Mode: Change | Target: 2 → 1";
                case 10: return "Mode: Change | Target: 2 → 3";
                case 11: return "Mode: Change | Target: 3 → 1";
                case 12: return "Mode: Change | Target: 3 → 2";
                
                case 13: return "Mode: Change + Obstacle | Target: 1 → 2";
                case 14: return "Mode: Change + Obstacle | Target: 1 → 3";
                case 15: return "Mode: Change + Obstacle | Target: 2 → 1";
                case 16: return "Mode: Change + Obstacle | Target: 2 → 3";
                case 17: return "Mode: Change + Obstacle | Target: 3 → 1";
                case 18: return "Mode: Change + Obstacle | Target: 3 → 2";
                
                default: return "";
            }
        }
    }
}
