// Test doubles only. No game/Unity/BepInEx binaries are loaded by this project.
using System;
using System.Collections.Generic;

namespace UnityEngine
{
    public class Object { }
    public sealed class GameObject { public string name; }
    public static class Application { public static string unityVersion; public static string dataPath; }
    public static class Time { public static float unscaledTime; }
    public static class JsonUtility { public static T FromJson<T>(string value) { throw new NotSupportedException(); } }
}
namespace BepInEx
{
    public sealed class BepInPlugin : Attribute { public BepInPlugin(string id, string name, string version) { } }
    public sealed class PluginInfo { public string Location; }
    public sealed class Log { public void LogInfo(string text) { } public void LogError(string text) { } }
    public class BaseUnityPlugin { public PluginInfo Info = new PluginInfo(); public Log Logger = new Log(); }
}
namespace I2.Loc
{
    public sealed class LanguageData
    {
        public string Name;
        public string Code;
        public int Flags;
        public bool Compressed;
        public static bool FailNextLoaded;
        public void SetEnabled(bool value) { Flags = value ? Flags | 1 : Flags & ~1; }
        public void SetLoaded(bool value) {
            Flags = value ? Flags | 2 : Flags & ~2;
            if (FailNextLoaded) { FailNextLoaded = false; throw new InvalidOperationException("Synthetic flag failure."); }
        }
        public void SetCanBeUnLoaded(bool value) { Flags = value ? Flags | 4 : Flags & ~4; }
    }
    public sealed class TermData
    {
        public string Term;
        public int TermType;
        public string[] Languages;
        public byte[] Flags;
        private string[] Languages_Touch = new string[0];
        public string[] Touch { get { return Languages_Touch; } }
        public bool FailWrite;
        public void Expand()
        {
            Array.Resize(ref Languages, Languages.Length + 1);
            Array.Resize(ref Flags, Flags.Length + 1);
            Array.Resize(ref Languages_Touch, Languages.Length);
        }
        public void SetTranslation(int index, string translation, string specialization)
        {
            Languages[index] = translation;
            Flags[index] = 99;
            Languages_Touch[index] = translation;
            if (FailWrite) throw new InvalidOperationException("Synthetic term failure.");
        }
    }
    public sealed class LanguageSource
    {
        public UnityEngine.GameObject gameObject = new UnityEngine.GameObject();
        public List<LanguageData> mLanguages = new List<LanguageData>();
        public List<TermData> mTerms = new List<TermData>();
        private Dictionary<string, TermData> mDictionary;
        public void InitializeDictionary() {
            mDictionary = new Dictionary<string, TermData>();
            foreach (TermData term in mTerms) mDictionary.Add(term.Term, term);
        }
        public int GetLanguageIndexFromCode(string code, bool exact)
        {
            return mLanguages.FindIndex(language => language.Code == code);
        }
        public TermData GetTermData(string term, bool categoryMismatch) { return mTerms.Find(item => item.Term == term); }
        public void AddLanguage(string name, string code)
        {
            mLanguages.Add(new LanguageData { Name = name, Code = code });
            foreach (TermData term in mTerms) term.Expand();
        }
        public void UpdateDictionary(bool force) { }
    }
    public static class LocalizationManager
    {
        public static List<LanguageSource> Sources = new List<LanguageSource>();
        private static string mCurrentLanguage = "English";
        private static string mLanguageCode = "en";
        private static System.Globalization.CultureInfo mCurrentCulture = new System.Globalization.CultureInfo("en");
        public static bool IsRight2Left;
        public static bool HasJoinedWords;
        public static int PreferenceWrites;
        public static int PublicRefreshCalls;
        public static int MemoryRefreshCalls;
        public static string CurrentLanguageCode {
            get { return mLanguageCode; }
            set { PreferenceWrites++; mLanguageCode = value; }
        }
        public static string CurrentName { get { return mCurrentLanguage; } }
        public static string CultureCode { get { return mCurrentCulture.Name; } }
        public static void LocalizeAll(bool force) { PublicRefreshCalls++; }
        private static void DoLocalizeAll(bool force) { MemoryRefreshCalls++; }
    }
}
