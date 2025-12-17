using System;
using System.IO;
using System.Numerics;
using Newtonsoft.Json;
using Microsoft.Kinect;
using System.Windows;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    // Manages per-camera calibration matrices (rotation + translation) and floor normals.
    // - Loads/saves JSON calibration files per camera (cam1_calibration.json / cam2_calibration.json)
    // - Applies matrix-based transforms from CameraSpace -> WorldSpace
    // - For Cam2 (slave), applies axis inversion on Ox and Oz to map into Cam1 world.
    public class DualCameraCalibrationManager
    {
        private readonly string baseFolder;

        public DualCameraCalibrationManager(string configFolder = null)
        {
            this.baseFolder = configFolder ?? Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        }

        private string GetConfigPath(string sensorId)
        {
            var name = sensorId?.ToLower().Contains("cam2") == true ? "cam2_calibration.json" : "cam1_calibration.json";
            return Path.Combine(this.baseFolder, name);
        }

        public CalibrationProfile Load(string sensorId)
        {
            var path = GetConfigPath(sensorId);
            if (!File.Exists(path)) return new CalibrationProfile();
            try
            {
                var txt = File.ReadAllText(path);
                return JsonConvert.DeserializeObject<CalibrationProfile>(txt) ?? new CalibrationProfile();
            }
            catch { return new CalibrationProfile(); }
        }

        public void Save(string sensorId, CalibrationProfile profile)
        {
            var path = GetConfigPath(sensorId);
            try
            {
                var txt = JsonConvert.SerializeObject(profile, Formatting.Indented);
                File.WriteAllText(path, txt);
            }
            catch { }
        }

        // Update floor plane from Kinect Frame's FloorClipPlane
        public void UpdateFloorPlane(string sensorId, Microsoft.Kinect.Vector4 floorClipPlane)
        {
            var profile = Load(sensorId);
            var n = new Vector3(floorClipPlane.X, floorClipPlane.Y, floorClipPlane.Z);
            var len = n.Length();
            if (len > 1e-6f)
            {
                n /= len;
                profile.FloorNormal = n;
                Save(sensorId, profile);
            }
        }

        // Apply loaded calibration + optional axis inversion for cam2
        public CameraSpacePoint ApplyCalibration(string sensorId, CameraSpacePoint camPoint)
        {
            var profile = Load(sensorId);

            // convert to Vector3
            var p = new Vector3(camPoint.X, camPoint.Y, camPoint.Z);

            // apply rotation then translation: world = R * p + t
            var R = profile.RotationMatrix; // 3x3 row-major
            var t = profile.Translation;

            var rotated = new Vector3(
                R[0] * p.X + R[1] * p.Y + R[2] * p.Z,
                R[3] * p.X + R[4] * p.Y + R[5] * p.Z,
                R[6] * p.X + R[7] * p.Y + R[8] * p.Z
            );

            var world = rotated + t;

            // If sensor is cam2 (slave) we must invert Ox and Oz axes to align with cam1 world.
            // This is because cam2 is physically rotated 180 degrees around the vertical axis relative to cam1
            // when placed opposite; therefore the camera X (left-right) and Z (depth) point in opposite directions.
            if (sensorId?.ToLower().Contains("cam2") == true)
            {
                // Invert X and Z components in world space
                world.X = -world.X;
                world.Z = -world.Z;
            }

            return new CameraSpacePoint { X = world.X, Y = world.Y, Z = world.Z };
        }
    }

    public class CalibrationProfile
    {
        // Rotation matrix 3x3 row-major
        public float[] RotationMatrix { get; set; } = new float[9] { 1,0,0, 0,1,0, 0,0,1 };

        // Translation vector
        public Vector3 Translation { get; set; } = new Vector3(0,0,0);

        // Floor normal (unit)
        public Vector3 FloorNormal { get; set; } = new Vector3(0,1,0);

        // Convenience check
        public bool IsValid => RotationMatrix != null && RotationMatrix.Length == 9;
    }
}
