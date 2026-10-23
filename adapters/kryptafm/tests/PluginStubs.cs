// Synthetic stand-ins: no game or loader assembly is loaded by this test executable.
using System;
using System.Collections.Generic;
namespace UnityEngine {
    public class Object { public static int Destroyed; public static void Destroy(Object value) { Destroyed++; } }
    public class TextAsset : Object { public string name; public readonly string text; public TextAsset(string value) { text=value; } }
    public static class Application { public static string unityVersion="synthetic",dataPath="missing"; }
}
namespace BepInEx {
    public class BepInPlugin : Attribute { public BepInPlugin(string a,string b,string c) {} }
    public class BaseUnityPlugin { public readonly Log Logger=new Log(); public readonly Metadata Info=new Metadata(); }
    public class Log { public void LogInfo(string value) {} public void LogError(string value) {} }
    public class Metadata { public string Location="missing"; }
}
namespace HarmonyLib {
    public class HarmonyPatch : Attribute { public HarmonyPatch(Type type,string method) {} }
    public class Harmony { public Harmony(string value) {} public void PatchAll(System.Reflection.Assembly value) {} public void UnpatchSelf() {} }
}
public class TranslateManager {
    public static TranslateManager instance; public bool isPolish;
    public UnityEngine.TextAsset textAssetEng; public string[] currentTranslation;
}
public class PostInfoManager {
    public bool isPolish;
    public List<UnityEngine.TextAsset> postScriptsListENG,keyPostScriptsListENG,messagesListENG;
    public List<UnityEngine.TextAsset> currentPostScriptsList,currentKeyPostScriptsList,currentMessagesList;
}
public class SubtitlesManager {
    public List<UnityEngine.TextAsset> subtitlesListENG,currentSubtitlesList; public string[] currentSubtitlesString;
}
public class Journal {
    private string[,] objectivesDescriptionsENG;
    public Journal(string[,] values) { objectivesDescriptionsENG=values; }
    public string[,] Read() { return objectivesDescriptionsENG; }
}
namespace UnityTranslator.KryptaFM {
    internal static class BuildIdentity {
        public const string UnityVersion="synthetic",AssemblySha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            UnityPlayerSha256="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    }
}
