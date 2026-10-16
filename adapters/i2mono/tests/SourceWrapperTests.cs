using System;
using System.Reflection;
using I2.Loc;
using UnityTranslator.I2Mono;

static class SourceWrapperTests
{
    static LanguageSource Make()
    {
        LanguageSource source = new LanguageSource();
        source.gameObject.name = "synthetic";
        source.mLanguages.Add(new LanguageData { Name = "French", Code = "fr", Flags = 4 });
        source.mLanguages.Add(new LanguageData { Name = "English", Code = "en", Flags = 12, Compressed = true });
        source.mTerms.Add(new TermData { Term = "UI/start", TermType = 0,
            Languages = new string[] { "Début {0}", "Start {0}" }, Flags = new byte[] { 3, 7 } });
        source.mTerms.Add(new TermData { Term = "Font/main", TermType = 1,
            Languages = new string[] { "FrenchFont", "EnglishFont" }, Flags = new byte[] { 5, 6 } });
        return source;
    }
    static ISource Wrap(LanguageSource source)
    {
        Type wrapper = typeof(Plugin).GetNestedType("Source", BindingFlags.NonPublic);
        return (ISource)Activator.CreateInstance(wrapper, source);
    }
    static Payload Data()
    {
        return new Payload { format_version = 1, target_language = "tr", target_name = "Türkçe",
            entries = new Entry[] { new Entry { source_set = "synthetic", key = "UI/start",
                source_sha256 = TranslationCore.Hash("Start {0}"), text = "Başla {0}" } } };
    }
    static void Original(LanguageSource source)
    {
        if (source.mLanguages.Count != 2 || source.mLanguages[1].Flags != 12
            || !source.mLanguages[1].Compressed || source.mTerms[0].Languages.Length != 2
            || source.mTerms[0].Languages[0] != "Début {0}" || source.mTerms[0].Languages[1] != "Start {0}"
            || source.mTerms[0].Flags[0] != 3 || source.mTerms[0].Flags[1] != 7
            || source.mTerms[0].Touch.Length != 0 || source.mTerms[1].Languages[1] != "EnglishFont")
            throw new Exception("Source state was not completely restored.");
    }
    public static void Run()
    {
        LanguageSource source = Make();
        TranslationCore.Apply(Data(), new ISource[] { Wrap(source) });
        if (source.mLanguages.Count != 3 || source.mLanguages[2].Code != "tr"
            || source.mTerms[0].Languages[1] != "Start {0}"
            || source.mTerms[0].Languages[2] != "Başla {0}"
            || source.mTerms[1].Languages[2] != "EnglishFont")
            throw new Exception("Target language or asset fallback failed.");
        source = Make();
        LanguageData.FailNextLoaded = true;
        bool failed = false;
        try { TranslationCore.Apply(Data(), new ISource[] { Wrap(source) }); }
        catch (InvalidOperationException) { failed = true; }
        if (!failed) throw new Exception("Synthetic partial term write did not fail.");
        Original(source);
        source = Make();
        try {
            TranslationCore.Apply(Data(), new ISource[] { Wrap(source) }, delegate {
                source.mLanguages[1].Flags = 55;
                source.mLanguages[1].Compressed = false;
                throw new InvalidOperationException("Synthetic localization failure.");
            }, null);
            throw new Exception("Finalizer error was accepted.");
        } catch (InvalidOperationException) { }
        Original(source);
        object prior = MemoryLanguage.Capture();
        MemoryLanguage.Select("tr", "Türkçe");
        MemoryLanguage.Refresh();
        if (LocalizationManager.CurrentLanguageCode != "tr"
            || LocalizationManager.CurrentName != "Türkçe" || LocalizationManager.CultureCode != "tr"
            || LocalizationManager.PreferenceWrites != 0 || LocalizationManager.PublicRefreshCalls != 0)
            throw new Exception("Memory language selection invoked a persistent API.");
        MemoryLanguage.Restore(prior);
        if (LocalizationManager.CurrentLanguageCode != "en" || LocalizationManager.CurrentName != "English")
            throw new Exception("Memory language rollback failed.");
        source = Make();
        Type wrapperType = typeof(Plugin).GetNestedType("Source", BindingFlags.NonPublic);
        MethodInfo ready = wrapperType.GetMethod("Ready", BindingFlags.Static | BindingFlags.Public);
        if ((bool)ready.Invoke(null, new object[] { source }))
            throw new Exception("Uninitialized dictionary was accepted.");
        source.InitializeDictionary();
        if (!(bool)ready.Invoke(null, new object[] { source }))
            throw new Exception("Initialized dictionary was not accepted.");
        // Verify non-English source hashes and installing into an existing English column.
        source = Make();
        Payload multilingual = Data();
        multilingual.format_version = 2;
        multilingual.source_language = "fr";
        multilingual.target_language = "en";
        multilingual.target_name = "English";
        multilingual.entries[0].source_sha256 = TranslationCore.Hash("Début {0}");
        multilingual.entries[0].text = "Begin {0}";
        TranslationCore.Apply(multilingual, new ISource[] { Wrap(source) });
        if (source.mTerms[0].Languages[1] != "Begin {0}" || source.mTerms[0].Languages[0] != "Début {0}"
            || source.mTerms[1].Languages[1] != "EnglishFont")
            throw new Exception("Non-English source mapping failed.");
        foreach (string code in new string[] { "ja", "it", "pt-BR", "ar", "zh-CN", "ru" })
        {
            object previous = MemoryLanguage.Capture();
            MemoryLanguage.Select(code, code);
            if (LocalizationManager.CurrentLanguageCode != code || LocalizationManager.PreferenceWrites != 0)
                throw new Exception("Multilingual memory selection failed.");
            if (code == "ar" && !(bool)typeof(LocalizationManager).GetField("IsRight2Left").GetValue(null))
                throw new Exception("RTL flag missing.");
            MemoryLanguage.Restore(previous);
        }
        string json = "{\"format_version\":2,\"source_language\":\"fr\",\"unity_version\":\"2017.4.19f1\","
            + "\"assembly_sha256\":\"hash\",\"target_language\":\"ja\",\"target_name\":\"日本語\","
            + "\"entries\":[{\"source_set\":\"synthetic\",\"key\":\"UI/start\",\"source_sha256\":\"hash\",\"text\":\"開始 {0}\"}]}";
        if (PayloadJson.Parse(json).source_language != "fr") throw new Exception("Version 2 schema failed.");
        if (TranslationCore.LanguageIndex(new string[] { "pt-BR", "pt-PT" }, "pt-BR") != 0)
            throw new Exception("Exact regional language mapping failed.");
        bool ambiguous = false;
        try { TranslationCore.LanguageIndex(new string[] { "pt-BR", "pt-PT" }, "pt"); }
        catch (InvalidOperationException) { ambiguous = true; }
        if (!ambiguous) throw new Exception("Ambiguous source accepted.");
        Console.WriteLine("Multilingual source, existing-target, Unicode, regional, RTL and legacy-schema scenarios passed.");
        Console.WriteLine("5 synthetic I2 wrapper scenarios passed; dictionary readiness and memory-only selection verified.");
    }
}
