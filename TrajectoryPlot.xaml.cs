using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    public partial class TrajectoryPlot : UserControl
    {
        private const int MaxPoints = 60;
        private readonly List<double> measuredBuffer = new List<double>();
        private readonly List<double> predictedBuffer = new List<double>();

        public TrajectoryPlot()
        {
            InitializeComponent();
            this.SizeChanged += (s, e) => UpdatePlot();
        }

        public string Title
        {
            get => lblTitle.Text;
            set => lblTitle.Text = value;
        }

        public void AddPoints(double measured, double? predicted)
        {
            measuredBuffer.Add(measured);
            if (measuredBuffer.Count > MaxPoints) measuredBuffer.RemoveAt(0);

            if (predicted.HasValue)
            {
                predictedBuffer.Add(predicted.Value);
                if (predictedBuffer.Count > MaxPoints) predictedBuffer.RemoveAt(0);
            }

            UpdatePlot();
        }

        public void Clear()
        {
            measuredBuffer.Clear();
            predictedBuffer.Clear();
            UpdatePlot();
        }

        private void UpdatePlot()
        {
            if (plotCanvas.ActualWidth == 0 || plotCanvas.ActualHeight == 0) return;

            double w = plotCanvas.ActualWidth;
            double h = plotCanvas.ActualHeight;

            // Find min/max for scaling
            double min = 0, max = 0.1;
            var all = measuredBuffer.Concat(predictedBuffer).ToList();
            if (all.Any())
            {
                min = all.Min();
                max = all.Max();
                double range = max - min;
                if (range < 0.01) range = 0.01;
                min -= range * 0.1;
                max += range * 0.1;
            }

            lblMin.Text = min.ToString("F2");
            lblMax.Text = max.ToString("F2");

            xAxis.X2 = w;
            xAxis.Y1 = xAxis.Y2 = h;
            yAxis.Y2 = h;

            // Measured points
            PointCollection mPoints = new PointCollection();
            for (int i = 0; i < measuredBuffer.Count; i++)
            {
                double x = (double)i / MaxPoints * w;
                double y = h - (measuredBuffer[i] - min) / (max - min) * h;
                mPoints.Add(new Point(x, y));
            }
            polyMeasured.Points = mPoints;

            // Predicted points (aligned to the right)
            PointCollection pPoints = new PointCollection();
            int startIdx = measuredBuffer.Count - predictedBuffer.Count;
            for (int i = 0; i < predictedBuffer.Count; i++)
            {
                double x = (double)(startIdx + i) / MaxPoints * w;
                double y = h - (predictedBuffer[i] - min) / (max - min) * h;
                pPoints.Add(new Point(x, y));
            }
            polyPredicted.Points = pPoints;
        }
    }
}
