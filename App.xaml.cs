//------------------------------------------------------------------------------
// <copyright file="App.xaml.cs" company="Microsoft">
//     Copyright (c) Microsoft Corporation.  All rights reserved.
// </copyright>
//------------------------------------------------------------------------------

namespace Microsoft.Samples.Kinect.BodyBasics
{
    using System;
    using System.IO;
    using System.Linq;
    using System.Reflection;
    using System.Windows;

    /// <summary>
    /// Interaction logic for App
    /// </summary>
    public partial class App : Application
    {
        // Static constructor runs before any instance/InitializeComponent and allows
        // us to intercept assembly resolution early so we can redirect Microsoft.Kinect
        // to a runtime implementation instead of a reference-only assembly (which
        // causes BadImageFormatException when loaded for execution).
        static App()
        {
            AppDomain.CurrentDomain.AssemblyResolve += CurrentDomain_AssemblyResolve;
        }

        private static Assembly CurrentDomain_AssemblyResolve(object sender, ResolveEventArgs args)
        {
            try
            {
                var requested = new AssemblyName(args.Name).Name;
                if (!string.Equals(requested, "Microsoft.Kinect", StringComparison.OrdinalIgnoreCase))
                {
                    return null;
                }

                // Probe candidate locations in a best-effort manner. Prefer a copy next to the app,
                // then known Kinect SDK install locations (Assemblies\x64 or x86), then recursively
                // search Program Files folders as a last resort.
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string[] candidates = new[]
                {
                    Path.Combine(baseDir, "Microsoft.Kinect.dll")
                };

                foreach (var c in candidates)
                {
                    if (File.Exists(c))
                    {
                        try
                        {
                            return Assembly.LoadFrom(c);
                        }
                        catch
                        {
                            // try other candidates
                        }
                    }
                }

                string[] programRoots = new[]
                {
                    Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                    Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86)
                };

                foreach (var root in programRoots.Where(r => !string.IsNullOrEmpty(r)))
                {
                    try
                    {
                        // look for Kinect SDK folders under "Microsoft SDKs" or directly
                        var sdkBase = Path.Combine(root, "Microsoft SDKs");
                        if (Directory.Exists(sdkBase))
                        {
                            foreach (var kdir in Directory.EnumerateDirectories(sdkBase, "Kinect*", SearchOption.TopDirectoryOnly))
                            {
                                foreach (var assembliesFolder in Directory.EnumerateDirectories(kdir, "Assemblies", SearchOption.AllDirectories))
                                {
                                    string arch = IntPtr.Size == 8 ? "x64" : "x86";
                                    var path = Path.Combine(assembliesFolder, arch, "Microsoft.Kinect.dll");
                                    if (File.Exists(path))
                                    {
                                        try { return Assembly.LoadFrom(path); } catch { }
                                    }

                                    var path2 = Path.Combine(assembliesFolder, "Microsoft.Kinect.dll");
                                    if (File.Exists(path2))
                                    {
                                        try { return Assembly.LoadFrom(path2); } catch { }
                                    }
                                }
                            }
                        }

                        // last resort: recursive search for Microsoft.Kinect.dll (may be slow; swallow errors)
                        foreach (var file in Directory.EnumerateFiles(root, "Microsoft.Kinect.dll", SearchOption.AllDirectories))
                        {
                            try { return Assembly.LoadFrom(file); } catch { }
                        }
                    }
                    catch
                    {
                        // ignore and continue
                    }
                }

                return null;
            }
            catch
            {
                return null;
            }
        }
    }
}
