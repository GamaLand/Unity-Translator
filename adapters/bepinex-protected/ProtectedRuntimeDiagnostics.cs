// UnityTranslator modification, 2026-10-14. Project code: MIT.
// Diagnostics stay outside the game tree and never replace an existing file.
using System;
using System.IO;
using System.Text;

namespace BepInEx.Preloader
{
    internal static class ProtectedRuntimeDiagnostics
    {
        private static string LocalPath(string value)
        {
            if (String.IsNullOrEmpty(value) || value.Length < 3 || !Char.IsLetter(value[0])
                || value[1] != ':' || (value[2] != '\\' && value[2] != '/')
                || value.IndexOf(':', 2) >= 0)
                throw new IOException("Expected an absolute local path");
            string full = Path.GetFullPath(value);
            for (string current = full; !String.IsNullOrEmpty(current);
                 current = Path.GetDirectoryName(current))
            {
                if (File.Exists(current) || Directory.Exists(current))
                    if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                        throw new IOException("Reparse path refused");
            }
            return full;
        }

        private static bool Within(string child, string parent)
        {
            return String.Equals(child, parent, StringComparison.OrdinalIgnoreCase)
                || child.StartsWith(parent.TrimEnd('\\', '/') + Path.DirectorySeparatorChar,
                                    StringComparison.OrdinalIgnoreCase);
        }

        private static string ExternalRuntime()
        {
            string invoked = LocalPath(Environment.GetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH"));
            string process = LocalPath(Environment.GetEnvironmentVariable("DOORSTOP_PROCESS_PATH"));
            if (!String.Equals(Path.GetFileName(invoked), "BepInEx.Preloader.dll",
                               StringComparison.OrdinalIgnoreCase)
                || !File.Exists(invoked) || !File.Exists(process))
                throw new IOException("Runtime identity unavailable");
            string runtime = Path.GetDirectoryName(Path.GetDirectoryName(invoked));
            string game = Path.GetDirectoryName(process);
            if (Within(runtime, game) || Within(game, runtime))
                throw new IOException("Runtime and game trees overlap");
            return runtime;
        }

        internal static bool IsExternalRuntime()
        {
            try { return ExternalRuntime() != null; }
            catch (Exception) { return false; }
        }

        internal static bool TryWrite(string message)
        {
            try
            {
                string runtime = ExternalRuntime();
                string folder = LocalPath(Path.Combine(runtime, "diagnostics"));
                Directory.CreateDirectory(folder);
                LocalPath(folder); // Recheck after directory creation.
                string text = message ?? "";
                if (text.Length > 8192) text = text.Substring(0, 8192);
                for (int attempt = 0; attempt < 3; attempt++)
                {
                    string target = LocalPath(Path.Combine(folder, "preloader-" + Guid.NewGuid().ToString("N") + ".log"));
                    try
                    {
                        using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                        using (var writer = new StreamWriter(output, new UTF8Encoding(false)))
                            writer.Write(text);
                        return true;
                    }
                    catch (IOException) { }
                }
            }
            catch (Exception) { }
            return false; // Logging failure must not fall back to the game/CWD.
        }
    }
}
