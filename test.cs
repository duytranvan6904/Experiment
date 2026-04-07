using System;
using System.Globalization;

class Program
{
    static void Main()
    {
        Console.WriteLine(string.Format(CultureInfo.InvariantCulture,
            "{{\"x\": {0:F6}, \"y\": {1:F6}, \"z\": {2:F6}}}\n",
            -0.138864f, 0.900498f, float.NaN));
    }
}
