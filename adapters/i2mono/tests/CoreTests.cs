using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using UnityTranslator.I2Mono;

sealed class FakeSource : ISource
{
    public string SourceName = "synthetic";
    public string Name { get { return SourceName; } }
    public object Identity { get { return this; } }
    public int Calls;
    public string Text;
    public string SourceText = "Start {0}";
    public object Capture() { return Text; }
    public bool FailApply;
    public bool FailRestore;
    public void Restore(object snapshot) {
        if (FailRestore) throw new InvalidOperationException("Synthetic restore failure.");
        Text = (string)snapshot;
    }
    public string English(string key) { return key == "UI/start" ? SourceText : null; }
    public void Apply(string code, string name, IDictionary<string, string> changes)
    {
        Calls++;
        Text = changes["UI/start"];
        if (FailApply) throw new InvalidOperationException("Synthetic apply failure.");
    }
}

static class CoreTests
{
    static void JsonCases()
    {
        string text = "Çıkış · Iıİi çğöşü\r\n{0} \" / \\ 😀";
        var entries = new List<object>();
        for (int i = 0; i < 10; i++) entries.Add(new {
            source_set = "synthetic", key = "UI/" + i,
            source_sha256 = TranslationCore.Hash("Start"), text = text });
        var data = new { format_version = 1, unity_version = "2017.4.19f1",
            assembly_sha256 = new string('a', 64), target_language = "tr", target_name = "Türkçe", entries = entries };
        string escaped = JsonSerializer.Serialize(data);
        string raw = JsonSerializer.Serialize(data, new JsonSerializerOptions {
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        foreach (string json in new[] { escaped, raw })
        {
            Payload parsed = PayloadJson.Parse(" \r\n" + json + "\t");
            if (parsed.entries.Length != 10 || parsed.entries[9].text != text
                || parsed.target_name != "Türkçe" || parsed.unity_version != "2017.4.19f1")
                throw new Exception("Runtime JSON Unicode/array contract failed.");
        }
        string[] bad = {
            escaped + "{}", escaped.Substring(0, escaped.Length - 1),
            escaped.Replace("\"format_version\":1", "\"format_version\":1,\"format_version\":1"),
            escaped.Replace("\"format_version\":1", "\"format_version\":1.0"),
            escaped.Replace("\"format_version\":1", "\"format_version\":true"),
            escaped.Replace("\"format_version\":1", "\"format_version\":2"),
            escaped.Replace("\"source_set\"", "\"$type\""),
            escaped.Replace("\"entries\":[", "\"entries\":null,\"ignored\":["),
            escaped.Replace("\"target_language\":\"tr\"", "\"target_language\":\"\\uD800\""),
            escaped.Replace("\"target_language\":\"tr\"", "\"target_language\":\"\\x00\""),
            escaped.Replace("\"target_language\":\"tr\"", "\"target_language\":\"t\nr\""),
            escaped.Replace("\"entries\":[", "\"entries\":[[[[[")
        };
        foreach (string json in bad)
        {
            bool rejected = false;
            try { PayloadJson.Parse(json); } catch (FormatException) { rejected = true; }
            if (!rejected) throw new Exception("Malformed runtime JSON accepted.");
        }
        Console.WriteLine("14 runtime JSON scenarios passed; bounded fixed schema and Unicode verified.");
    }
    static void FormatCases()
    {
        int count = 0;
        using (JsonDocument document = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(AppContext.BaseDirectory, "protected-format-v4.json"))))
        {
            foreach (JsonElement item in document.RootElement.EnumerateArray())
            {
                string original = item.GetProperty("source").GetString();
                string target = item.GetProperty("target").GetString();
                FakeSource source = new FakeSource { SourceText = original };
                Payload payload = Make();
                payload.entries[0].source_sha256 = TranslationCore.Hash(original);
                payload.entries[0].text = target;
                if (item.GetProperty("accepted").GetBoolean())
                {
                    if (TranslationCore.Apply(payload, new ISource[] { source }) != 1
                        || source.Text != target || source.Calls != 1)
                        throw new Exception("Shared protected format acceptance mismatch.");
                }
                else
                {
                    Reject(payload, new ISource[] { source });
                    if (source.Calls != 0) throw new Exception("Invalid shared format changed memory.");
                }
                count++;
            }
        }
        Console.WriteLine(count + " shared Python/C# protected format cases passed.");
    }
    static Payload Make()
    {
        return new Payload { format_version = 1, target_language = "tr", target_name = "Türkçe",
            entries = new Entry[] { new Entry { source_set = "synthetic", key = "UI/start",
                source_sha256 = TranslationCore.Hash("Start {0}"), text = "Başla {0} · Iıİi çğöşü" } } };
    }
    static void Reject(Payload payload, IList<ISource> sources)
    {
        bool rejected = false;
        try { TranslationCore.Apply(payload, sources); }
        catch (InvalidOperationException) { rejected = true; }
        if (!rejected) throw new Exception("Unsafe payload was accepted.");
    }
    static int Main()
    {
        JsonCases();
        FakeSource source = new FakeSource();
        if (TranslationCore.Apply(Make(), new ISource[] { source }) != 1
            || source.Calls != 1 || source.Text != "Başla {0} · Iıİi çğöşü")
            throw new Exception("Unicode payload failed.");
        source = new FakeSource();
        Payload invalid = Make();
        invalid.entries[0].source_sha256 = TranslationCore.Hash("Changed source");
        Reject(invalid, new ISource[] { source });
        if (source.Calls != 0) throw new Exception("Validation wrote a source.");
        invalid = Make();
        invalid.entries = new Entry[] { invalid.entries[0], invalid.entries[0] };
        Reject(invalid, new ISource[] { source });
        Reject(Make(), new ISource[] { source, new FakeSource() });
        Reject(Make(), new ISource[0]);
        invalid = Make(); invalid.target_language = "en";
        Reject(invalid, new ISource[] { source });
        invalid = Make(); invalid.entries[0].key = "missing";
        Reject(invalid, new ISource[] { source });
        invalid = Make(); invalid.format_version = 2;
        Reject(invalid, new ISource[] { source });
        invalid = Make(); invalid.entries[0].text = "Başla";
        Reject(invalid, new ISource[] { source });
        if (source.Calls != 0) throw new Exception("Rejected data changed memory.");
        int scenarios = 9;
        FakeSource second = new FakeSource { SourceName = "second", Text = "Old second", FailApply = true };
        source.Text = "Old first";
        Payload pair = Make();
        pair.entries = new Entry[] { pair.entries[0], new Entry { source_set = "second", key = "UI/start",
            source_sha256 = TranslationCore.Hash("Start {0}"), text = "İkinci {0}" } };
        Reject(pair, new ISource[] { source, second });
        if (source.Text != "Old first" || second.Text != "Old second")
            throw new Exception("Cross-source rollback failed.");
        scenarios++;
        bool languageChanged = false;
        try {
            TranslationCore.Apply(Make(), new ISource[] { source }, delegate {
                languageChanged = true; throw new InvalidOperationException("Synthetic localization failure.");
            }, delegate { languageChanged = false; });
            throw new Exception("Failed finalizer was accepted.");
        } catch (InvalidOperationException) { }
        if (languageChanged || source.Text != "Old first") throw new Exception("Finalizer rollback failed.");
        scenarios++;
        source.FailRestore = true;
        try {
            TranslationCore.Apply(pair, new ISource[] { source, second });
            throw new Exception("Failed rollback was hidden.");
        } catch (InvalidOperationException error) {
            if (error.Message != "Memory rollback incomplete.") throw;
        }
        if (second.Text != "Old second") throw new Exception("Rollback stopped at first failure.");
        scenarios++;
        RuntimeSession session = new RuntimeSession();
        source = new FakeSource();
        if (session.ApplyIfChanged(Make(), new ISource[0], null, null) != 0 || session.HasApplied)
            throw new Exception("Session did not wait for source load.");
        if (session.ApplyIfChanged(Make(), new ISource[] { source }, null, null) != 1)
            throw new Exception("Session did not apply first source.");
        if (session.ApplyIfChanged(Make(), new ISource[] { source }, null, null) != 0 || source.Calls != 1)
            throw new Exception("Session reapplied unchanged source.");
        if (session.ApplyIfChanged(Make(), new ISource[0], null, null) != 0 || !session.HasApplied)
            throw new Exception("Missing scene source reset the user's language choice.");
        second = new FakeSource();
        if (session.ApplyIfChanged(Make(), new ISource[] { second }, null, null) != 1 || second.Calls != 1)
            throw new Exception("Session ignored replacement scene source.");
        scenarios++;
        Console.WriteLine(scenarios + " runtime core scenarios passed; no game assembly was executed.");
        FormatCases();
        SourceWrapperTests.Run();
        return 0;
    }
}
