using System;
using Microsoft.Kinect;

namespace Microsoft.Samples.Kinect.BodyBasics
{
    // CoordinateTransformer converts CameraSpace points into a World space aligned with floor and a given target origin.
    // It supports transforming points from a client camera into a master camera frame by applying manual inversion/offsets.
    public class CoordinateTransformer
    {
        // Simple vector helper to avoid extra dependencies
        private struct Vec3
        {
            public float X, Y, Z;
            public Vec3(float x, float y, float z) { X = x; Y = y; Z = z; }
            public static Vec3 FromCamera(CameraSpacePoint p) => new Vec3(p.X, p.Y, p.Z);
            public static Vec3 Zero => new Vec3(0, 0, 0);
            public static Vec3 operator -(Vec3 a, Vec3 b) => new Vec3(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
            public static Vec3 operator +(Vec3 a, Vec3 b) => new Vec3(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
            public static Vec3 operator *(Vec3 a, float s) => new Vec3(a.X * s, a.Y * s, a.Z * s);
            public float Dot(Vec3 o) => X * o.X + Y * o.Y + Z * o.Z;
            public Vec3 Cross(Vec3 o) => new Vec3(Y * o.Z - Z * o.Y, Z * o.X - X * o.Z, X * o.Y - Y * o.X);
            public float Length() => (float)Math.Sqrt(X * X + Y * Y + Z * Z);
            public Vec3 Normalize() { var l = Length(); return l <= 1e-6f ? new Vec3(0, 0, 0) : new Vec3(X / l, Y / l, Z / l); }
        }

        private Vec3 worldOrigin = Vec3.Zero; // in camera space of the master
        private Vec3 floorNormal = new Vec3(0, 1, 0);
        private bool isMaster = true;

        // Manual offsets and rotations (degrees)
        public CameraSpacePoint ManualTranslation { get; set; } = new CameraSpacePoint { X = 0, Y = 0, Z = 0 };
        public CameraSpacePoint ManualRotationEuler { get; set; } = new CameraSpacePoint { X = 0, Y = 0, Z = 0 }; // degrees

        public bool InvertX { get; set; } = false; // used for client camera facing opposite
        public bool InvertZ { get; set; } = false;

        public void SetAsMaster() { this.isMaster = true; }
        public void SetAsClient() { this.isMaster = false; }

        public void UpdateFloorPlane(Vector4 floorClipPlane)
        {
            // floorClipPlane is (A,B,C,D) for plane: Ax + By + Cz + D = 0 in camera space
            var fn = new Vec3(floorClipPlane.X, floorClipPlane.Y, floorClipPlane.Z);
            var n = fn.Normalize();
            if (n.Length() > 0) this.floorNormal = n;
        }

        public void SetWorldOriginFromTarget(CameraSpacePoint target)
        {
            this.worldOrigin = Vec3.FromCamera(target);
        }

        // Transform a camera-space point into world space.
        // World axes: Oy = floor normal, Oz = camera depth (0,0,1), Ox = Oy x Oz
        public CameraSpacePoint Transform(CameraSpacePoint p)
        {
            var v = Vec3.FromCamera(p);

            // apply inversion if client
            if (!this.isMaster)
            {
                if (this.InvertX) v.X = -v.X;
                if (this.InvertZ) v.Z = -v.Z;
            }

            var rel = v - this.worldOrigin;

            var Oy = this.floorNormal.Normalize();
            var Oz = new Vec3(0, 0, 1);

            // compute Ox = Oy x Oz, handle degenerate case
            var Ox = Oy.Cross(Oz);
            if (Ox.Length() < 1e-6f)
            {
                // floor normal parallel to depth; pick another axis
                Oz = new Vec3(0, 1, 0);
                Ox = Oy.Cross(Oz);
            }

            Ox = Ox.Normalize();
            // re-orthogonalize Oz
            Oz = Ox.Cross(Oy).Normalize();

            // project point onto basis
            float x = rel.Dot(Ox);
            float y = rel.Dot(Oy);
            float z = rel.Dot(Oz);

            // apply manual rotation (Euler ZYX in degrees)
            var mr = ManualRotationEuler;
            float rx = mr.X * (float)Math.PI / 180f;
            float ry = mr.Y * (float)Math.PI / 180f;
            float rz = mr.Z * (float)Math.PI / 180f;

            // rotate around Z
            float cosZ = (float)Math.Cos(rz), sinZ = (float)Math.Sin(rz);
            float xr = cosZ * x - sinZ * y;
            float yr = sinZ * x + cosZ * y;
            float zr = z;

            // rotate around Y
            float cosY = (float)Math.Cos(ry), sinY = (float)Math.Sin(ry);
            float xr2 = cosY * xr + sinY * zr;
            float yr2 = yr;
            float zr2 = -sinY * xr + cosY * zr;

            // rotate around X
            float cosX = (float)Math.Cos(rx), sinX = (float)Math.Sin(rx);
            float xr3 = xr2;
            float yr3 = cosX * yr2 - sinX * zr2;
            float zr3 = sinX * yr2 + cosX * zr2;

            // apply manual translation
            xr3 += ManualTranslation.X;
            yr3 += ManualTranslation.Y;
            zr3 += ManualTranslation.Z;

            return new CameraSpacePoint { X = xr3, Y = yr3, Z = zr3 };
        }
    }
}
