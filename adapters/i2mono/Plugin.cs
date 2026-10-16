using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using BepInEx;
using I2.Loc;
using UnityEngine;

namespace UnityTranslator.I2Mono
{
    [BepInPlugin("org.unitytranslator.i2mono", "UnityTranslator I2 Mono (experimental)", "0.1.0")]
    public sealed class Plugin : BaseUnityPlugin
    {
        private Payload payload;
        private float nextCheck;
        private readonly RuntimeSession session = new RuntimeSession();
        private readonly HashSet<string> required = new HashSet<string>(StringComparer.Ordinal);
        private readonly Dictionary<LanguageSource, Source> wrappers = new Dictionary<LanguageSource, Source>();
        private bool stopped;

        private void Awake()
        {
            // Sabit aşama kodları metin, dosya yolu veya exception mesajı içermez.
            int check = 1;
            try
            {
                // Yalnızca eklentinin yanındaki sabit veri dosyası okunur.
                string path = Path.Combine(Path.GetDirectoryName(Info.Location), "translation.json");
                if (new FileInfo(path).Length > 64 * 1024 * 1024)
                    throw new InvalidOperationException("Runtime payload too large.");
                check = 2;
                payload = PayloadJson.Parse(File.ReadAllText(path, new UTF8Encoding(false, true)));
                check = 3;
                if (payload == null || payload.format_version != 1)
                    throw new InvalidOperationException("Invalid payload format.");
                check = 4;
                if (payload.target_language != "tr")
                    throw new InvalidOperationException("Target language mismatch.");
                check = 5;
                if (Application.unityVersion != payload.unity_version)
                    throw new InvalidOperationException("Unity version mismatch.");
                check = 6;
                Logger.LogInfo("Payload entry count: " + (payload.entries == null ? -1 : payload.entries.Length));
                if (payload.entries == null || payload.entries.Length == 0 || payload.entries.Length > 100000)
                    throw new InvalidOperationException("Invalid term set.");
                check = 9;
                foreach (Entry entry in payload.entries)
                {
                    if (entry == null || String.IsNullOrEmpty(entry.source_set))
                        throw new InvalidOperationException("Invalid source set.");
                    required.Add(entry.source_set);
                }
                check = 7;
                string assembly = Path.Combine(Application.dataPath, "Managed/Assembly-CSharp.dll");
                using (FileStream input = File.OpenRead(assembly))
                using (SHA256 hash = SHA256.Create())
                {
                    StringBuilder result = new StringBuilder(64);
                    foreach (byte value in hash.ComputeHash(input)) result.Append(value.ToString("x2"));
                    check = 8;
                    if (result.ToString() != payload.assembly_sha256)
                        throw new InvalidOperationException("Game assembly hash mismatch.");
                }
                Logger.LogInfo("Runtime payload loaded; waiting for I2 sources.");
            }
            catch (Exception)
            {
                stopped = true;
                Logger.LogError("Runtime payload rejected at check " + check
                    + "; localization was not changed.");
            }
        }

        private void Update()
        {
            if (stopped || payload == null || Time.unscaledTime < nextCheck) return;
            nextCheck = Time.unscaledTime + 1f;
            // Awake/Update Unity ana thread'indedir; ağ veya arka plan işi yoktur.
            try
            {
                if (LocalizationManager.Sources.Count == 0) return;
                foreach (LanguageSource previous in new List<LanguageSource>(wrappers.Keys))
                    if (previous == null || !LocalizationManager.Sources.Contains(previous)) wrappers.Remove(previous);
                List<ISource> sources = new List<ISource>();
                foreach (LanguageSource source in LocalizationManager.Sources)
                {
                    if (source == null || !required.Contains(source.gameObject.name)) continue;
                    if (!Source.Ready(source)) return; // Oyunun sözlüğü hazırlanırken bekle; SaveLanguages çağırma.
                    if (!wrappers.ContainsKey(source)) wrappers.Add(source, new Source(source));
                    sources.Add(wrappers[source]);
                }
                object previousLanguage = MemoryLanguage.Capture();
                bool first = !session.HasApplied;
                int count = session.ApplyIfChanged(payload, sources, delegate {
                    if (first) MemoryLanguage.SelectTurkish(payload.target_name);
                    MemoryLanguage.Refresh();
                }, delegate {
                    MemoryLanguage.Restore(previousLanguage);
                    MemoryLanguage.Refresh();
                });
                if (count > 0) Logger.LogInfo("Applied " + count + " selected terms in memory.");
            }
            catch (Exception)
            {
                stopped = true;
                Logger.LogError("I2 source validation/application failed; adapter stopped.");
            }
        }

        private sealed class Source : ISource
        {
            private static readonly FieldInfo TouchField = typeof(TermData).GetField(
                "Languages_Touch", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            private static readonly FieldInfo DictionaryField = typeof(LanguageSource).GetField(
                "mDictionary", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            public static bool Ready(LanguageSource source)
            {
                if (DictionaryField == null) throw new InvalidOperationException("I2 source dictionary field missing.");
                System.Collections.IDictionary dictionary = DictionaryField.GetValue(source) as System.Collections.IDictionary;
                if (dictionary == null || dictionary.Count != source.mTerms.Count) return false;
                foreach (TermData term in source.mTerms)
                    if (!dictionary.Contains(term.Term) || !System.Object.ReferenceEquals(dictionary[term.Term], term)) return false;
                return true;
            }
            private readonly LanguageSource source;
            private readonly int english;
            private readonly Dictionary<string, TermData> terms = new Dictionary<string, TermData>(StringComparer.Ordinal);
            public Source(LanguageSource source)
            {
                this.source = source;
                english = -1;
                for (int i = 0; i < source.mLanguages.Count; i++)
                {
                    LanguageData language = source.mLanguages[i];
                    if (language.Code != "en" && language.Code != "en-US"
                        && language.Code != "en-GB" && language.Name != "English") continue;
                    if (english >= 0) throw new InvalidOperationException("Ambiguous English language.");
                    english = i;
                }
                if (english < 0) throw new InvalidOperationException("English language missing.");
                foreach (TermData term in source.mTerms)
                {
                    if (terms.ContainsKey(term.Term)) throw new InvalidOperationException("Duplicate source term.");
                    terms.Add(term.Term, term);
                }
            }
            public string Name { get { return source.gameObject.name; } }
            public object Identity { get { return source; } }
            public string English(string key)
            {
                TermData term;
                if (!terms.TryGetValue(key, out term)) return null;
                if (term == null || (int)term.TermType != 0 || term.Languages.Length <= english)
                    return null;
                return term.Languages[english];
            }
            private sealed class TermState
            {
                public TermData Term;
                public string[] Languages;
                public string[] Touch;
                public byte[] Flags;
            }
            private sealed class Snapshot
            {
                public LanguageData[] Languages;
                public LanguageData[] LanguageStates;
                public List<TermState> Terms = new List<TermState>();
            }
            private static T[] Copy<T>(T[] values)
            {
                return values == null ? null : (T[])values.Clone();
            }
            public object Capture()
            {
                if (TouchField == null) throw new InvalidOperationException("I2 touch field missing.");
                Snapshot snapshot = new Snapshot();
                snapshot.Languages = source.mLanguages.ToArray();
                snapshot.LanguageStates = new LanguageData[snapshot.Languages.Length];
                for (int i = 0; i < snapshot.Languages.Length; i++)
                {
                    LanguageData language = snapshot.Languages[i];
                    snapshot.LanguageStates[i] = new LanguageData {
                        Name = language.Name, Code = language.Code,
                        Flags = language.Flags, Compressed = language.Compressed
                    };
                }
                foreach (TermData term in source.mTerms)
                    snapshot.Terms.Add(new TermState { Term = term,
                        Languages = Copy(term.Languages), Touch = Copy((string[])TouchField.GetValue(term)),
                        Flags = Copy(term.Flags) });
                return snapshot;
            }
            public void Restore(object captured)
            {
                Snapshot snapshot = (Snapshot)captured;
                source.mLanguages.Clear();
                source.mLanguages.AddRange(snapshot.Languages);
                for (int i = 0; i < snapshot.Languages.Length; i++)
                {
                    LanguageData language = snapshot.Languages[i];
                    LanguageData state = snapshot.LanguageStates[i];
                    language.Name = state.Name;
                    language.Code = state.Code;
                    language.Flags = state.Flags;
                    language.Compressed = state.Compressed;
                }
                foreach (TermState state in snapshot.Terms)
                {
                    state.Term.Languages = state.Languages;
                    TouchField.SetValue(state.Term, state.Touch);
                    state.Term.Flags = state.Flags;
                }
            }
            public void Apply(string code, string name, IDictionary<string, string> changes)
            {
                if (source.mLanguages.Exists(language => language.Name == name
                    && !String.Equals(language.Code, code, StringComparison.OrdinalIgnoreCase)))
                    throw new InvalidOperationException("Target language name collision.");
                int target = source.mLanguages.FindIndex(language => String.Equals(
                    language.Code, code, StringComparison.OrdinalIgnoreCase));
                if (source.mLanguages.FindAll(language => String.Equals(
                    language.Code, code, StringComparison.OrdinalIgnoreCase)).Count > 1)
                    throw new InvalidOperationException("Ambiguous target language code.");
                if (target < 0)
                {
                    if (source.mLanguages.Exists(language => language.Name == name))
                        throw new InvalidOperationException("Target language name collision.");
                    target = source.mLanguages.Count;
                    source.mLanguages.Add(new LanguageData { Name = name, Code = code });
                    foreach (TermData term in source.mTerms)
                    {
                        Array.Resize(ref term.Languages, source.mLanguages.Count);
                        Array.Resize(ref term.Flags, source.mLanguages.Count);
                    }
                }
                if (target < 0 || target == english)
                    throw new InvalidOperationException("Target language unavailable.");
                source.mLanguages[target].Name = name;
                source.mLanguages[target].Code = code;
                // Onaylanmamış/eski Türkçe satırlar yerine İngilizce fallback.
                // Font/varlık terimleri de İngilizce referanslarını korur.
                foreach (TermData term in source.mTerms)
                {
                    if (term.Languages.Length <= english || term.Languages.Length <= target
                        || term.Flags == null || term.Flags.Length <= target)
                        throw new InvalidOperationException("I2 language array mismatch.");
                }
                foreach (TermData term in source.mTerms)
                {
                    term.Languages[target] = term.Languages[english];
                    term.Flags[target] = term.Flags[english];
                    string[] touch = (string[])TouchField.GetValue(term);
                    if (touch != null && touch.Length > target)
                        touch[target] = touch.Length > english ? touch[english] : null;
                }
                foreach (KeyValuePair<string, string> change in changes)
                {
                    TermData term = terms[change.Key];
                    term.Languages[target] = change.Value;
                    string[] touch = (string[])TouchField.GetValue(term);
                    if (touch != null && touch.Length > target) touch[target] = change.Value;
                }
                source.mLanguages[target].SetEnabled(true);
                source.mLanguages[target].SetLoaded(true);
                source.mLanguages[target].SetCanBeUnLoaded(false);
            }
        }
    }
}
