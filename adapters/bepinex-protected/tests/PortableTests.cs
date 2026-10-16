using System;
using System.IO;
using BepInEx.Preloader;

class PortableTests
{
    static void Check(bool value) { if (!value) throw new Exception("Portable guard failed"); }
    static void Main(string[] args)
    {
        string root = Path.GetFullPath(args[0]);
        if (Directory.Exists(root)) throw new Exception("New fixture root required");
        Directory.CreateDirectory(root);
        string game = Path.Combine(root, "Synthetic.exe"); File.WriteAllText(game, "inert");
        string package = Path.Combine(root, "UnityTranslatorPatch");
        string dll = Path.Combine(package, "BepInEx/core/BepInEx.Preloader.dll");
        Directory.CreateDirectory(Path.GetDirectoryName(dll)); File.WriteAllText(dll, "inert");
        string marker = Path.Combine(package, "portable-runtime-v1.marker");
        Environment.SetEnvironmentVariable("DOORSTOP_PROCESS_PATH", game);
        Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", dll);
        Check(!ProtectedRuntimeDiagnostics.IsExternalRuntime());
        File.WriteAllText(marker, "UnityTranslator portable runtime v1\n");
        Check(ProtectedRuntimeDiagnostics.IsExternalRuntime());
        Check(!ProtectedRuntimeDiagnostics.TryWrite("never write"));
        File.WriteAllText(marker, "wrong"); Check(!ProtectedRuntimeDiagnostics.IsExternalRuntime());
        Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", "core/BepInEx.Preloader.dll");
        Check(!ProtectedRuntimeDiagnostics.IsExternalRuntime());
        Check(Directory.GetFiles(root, "*.log", SearchOption.AllDirectories).Length == 0);
        Console.WriteLine("6 portable preloader guard checks passed; no game assembly executed.");
    }
}
