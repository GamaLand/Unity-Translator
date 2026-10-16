using System;
using System.IO;
using System.Linq;
using BepInEx.Preloader;

internal static class DiagnosticsTests
{
    private static int checks;
    private static void Check(bool condition, string name)
    {
        if (!condition) throw new Exception(name);
        checks++;
    }

    public static int Main(string[] args)
    {
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
            throw new Exception("These diagnostics tests require Windows");
        string root = Path.GetFullPath(args[0]);
        if (Directory.Exists(root)) throw new Exception("New synthetic root required");
        Directory.CreateDirectory(root);
        string game = Path.Combine(root, "game");
        string runtime = Path.Combine(root, "runtime");
        Directory.CreateDirectory(game);
        Directory.CreateDirectory(Path.Combine(runtime, "core"));
        string exe = Path.Combine(game, "SyntheticGame.exe");
        string dll = Path.Combine(runtime, "core", "BepInEx.Preloader.dll");
        File.WriteAllText(exe, "synthetic file; never execute");
        File.WriteAllText(dll, "synthetic file; never execute");
        string original = Path.Combine(game, "existing.log");
        File.WriteAllText(original, "preserve");
        string invokeBefore = Environment.GetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH");
        string processBefore = Environment.GetEnvironmentVariable("DOORSTOP_PROCESS_PATH");
        try
        {
            Environment.SetEnvironmentVariable("DOORSTOP_PROCESS_PATH", exe);
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", dll);
            Check(ProtectedRuntimeDiagnostics.IsExternalRuntime(), "external runtime accepted");
            Check(ProtectedRuntimeDiagnostics.TryWrite("çğıİöşü"), "first log");
            Check(ProtectedRuntimeDiagnostics.TryWrite(new String('x', 20000)), "bounded second log");
            var logs = Directory.GetFiles(Path.Combine(runtime, "diagnostics"));
            Check(logs.Length == 2 && logs.Distinct().Count() == 2, "unique logs");
            Check(logs.Any(p => File.ReadAllText(p) == "çğıİöşü"), "Unicode preserved");
            Check(logs.Any(p => File.ReadAllText(p).Length == 8192), "message bound");
            Check(File.ReadAllText(original) == "preserve", "existing game log preserved");
            string inGame = Path.Combine(game, "core", "BepInEx.Preloader.dll");
            Directory.CreateDirectory(Path.GetDirectoryName(inGame));
            File.WriteAllText(inGame, "synthetic");
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", inGame);
            Check(!ProtectedRuntimeDiagnostics.IsExternalRuntime() && !ProtectedRuntimeDiagnostics.TryWrite("bad"), "game overlap refused");
            string parentDll = Path.Combine(root, "core", "BepInEx.Preloader.dll");
            Directory.CreateDirectory(Path.GetDirectoryName(parentDll));
            File.WriteAllText(parentDll, "synthetic");
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", parentDll);
            Check(!ProtectedRuntimeDiagnostics.TryWrite("bad"), "game within runtime refused");
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", "\\\\server\\share\\BepInEx.Preloader.dll");
            Check(!ProtectedRuntimeDiagnostics.TryWrite("bad"), "UNC refused before IO");
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", "core/BepInEx.Preloader.dll");
            Check(!ProtectedRuntimeDiagnostics.TryWrite("bad"), "relative path refused");
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", dll + ":stream");
            Check(!ProtectedRuntimeDiagnostics.TryWrite("bad"), "ADS refused");
            Environment.SetEnvironmentVariable("DOORSTOP_PROCESS_PATH", null);
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", dll);
            Check(!ProtectedRuntimeDiagnostics.TryWrite("bad"), "missing identity refused");
            Check(Directory.GetFiles(game, "*.log", SearchOption.AllDirectories).Length == 1, "no game fallback");
            Console.WriteLine(checks + " protected diagnostics checks passed; only synthetic files, no game/loader assembly executed.");
            return 0;
        }
        finally
        {
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", invokeBefore);
            Environment.SetEnvironmentVariable("DOORSTOP_PROCESS_PATH", processBefore);
        }
    }
}
