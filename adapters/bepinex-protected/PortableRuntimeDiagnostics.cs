// UnityTranslator portable variant, 2026-10-15. MIT.
// Only the package-owned fixed subtree is accepted inside the game; no diagnostic writes.
using System;
using System.IO;

namespace BepInEx.Preloader
{
    internal static class ProtectedRuntimeDiagnostics
    {
        internal static bool IsExternalRuntime()
        {
            try
            {
                string invoked = LocalPath(Environment.GetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH"));
                string process = LocalPath(Environment.GetEnvironmentVariable("DOORSTOP_PROCESS_PATH"));
                if (!File.Exists(invoked) || !File.Exists(process)) return false;
                string game = Path.GetDirectoryName(process);
                string package = LocalPath(Path.Combine(game, "UnityTranslatorPatch"));
                string expected = LocalPath(Path.Combine(package, "BepInEx/core/BepInEx.Preloader.dll"));
                if (!String.Equals(invoked, expected, StringComparison.OrdinalIgnoreCase)) return false;
                string marker = LocalPath(Path.Combine(package, "portable-runtime-v1.marker"));
                return File.Exists(marker) && new FileInfo(marker).Length < 128
                    && File.ReadAllText(marker) == "UnityTranslator portable runtime v1\n";
            }
            catch (Exception) { return false; }
        }

        private static string LocalPath(string value)
        {
            if (String.IsNullOrEmpty(value) || value.Length < 3 || !Char.IsLetter(value[0])
                || value[1] != ':' || (value[2] != '\\' && value[2] != '/')
                || value.IndexOf(':', 2) >= 0) throw new IOException("Absolute local path required");
            string full = Path.GetFullPath(value);
            for (string current = full; !String.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
                if ((File.Exists(current) || Directory.Exists(current))
                    && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Reparse path refused");
            return full;
        }

        internal static bool TryWrite(string message) { return false; }
    }
}
