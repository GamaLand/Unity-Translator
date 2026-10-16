using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace UnityTranslator.I2Mono
{
    [Serializable]
    public sealed class Payload
    {
        public int format_version;
        public string unity_version;
        public string assembly_sha256;
        public string source_language;
        public string target_language;
        public string target_name;
        public Entry[] entries;
    }

    [Serializable]
    public sealed class Entry
    {
        public string source_set;
        public string key;
        public string source_sha256;
        public string text;
    }

    public interface ISource
    {
        string Name { get; }
        object Identity { get; }
        string Original(string key, string language);
        object Capture();
        void Restore(object snapshot);
        void Apply(string code, string name, IDictionary<string, string> translations);
    }

    public sealed class RuntimeSession
    {
        private Dictionary<string, object> applied = new Dictionary<string, object>(StringComparer.Ordinal);
        private bool hasCommitted;
        public bool HasApplied { get { return hasCommitted; } }

        public int ApplyIfChanged(Payload payload, IList<ISource> sources, Action commit, Action rollback)
        {
            if (payload == null || payload.entries == null || payload.entries.Length == 0)
                throw new InvalidOperationException("Invalid session payload.");
            Dictionary<string, ISource> selected = new Dictionary<string, ISource>(StringComparer.Ordinal);
            Dictionary<string, bool> required = new Dictionary<string, bool>(StringComparer.Ordinal);
            foreach (Entry entry in payload.entries)
            {
                if (entry == null || String.IsNullOrEmpty(entry.source_set))
                    throw new InvalidOperationException("Invalid session source.");
                required[entry.source_set] = true;
            }
            foreach (ISource source in sources)
            {
                if (!required.ContainsKey(source.Name)) continue;
                if (selected.ContainsKey(source.Name))
                    throw new InvalidOperationException("Ambiguous loaded source.");
                selected.Add(source.Name, source);
            }
            if (selected.Count != required.Count)
            {
                applied.Clear(); // Release references to destroyed scene objects.
                return 0;
            }
            bool changed = false;
            foreach (KeyValuePair<string, ISource> source in selected)
                if (!applied.ContainsKey(source.Key) || !Object.ReferenceEquals(applied[source.Key], source.Value.Identity))
                    changed = true;
            if (!changed) return 0;
            int count = TranslationCore.Apply(payload, new List<ISource>(selected.Values), commit, rollback);
            applied.Clear();
            foreach (KeyValuePair<string, ISource> source in selected) applied.Add(source.Key, source.Value.Identity);
            hasCommitted = true;
            return count;
        }
    }

    public static class TranslationCore
    {
        private static readonly Regex Tokens = new Regex(
            @"\{\[[A-Za-z_0-9]+\]\}|\{[0-9]+:[fF][0-9]{1,2}\}|\{[A-Za-z_0-9]+\}|<sprite name=""[A-Za-z_0-9-]{1,128}"">|<size=[1-9][0-9]{0,2}%?>|</size>|</?(?:b|i|color)(?:=[^<>\r\n]+)?>|(?<=\s)[<>](?=\s)|\r\n|\r|\n");
        private static readonly Regex Parameters = new Regex(@"\{\[[A-Za-z_0-9]+\]\}|\{[0-9]+:[fF][0-9]{1,2}\}|\{[A-Za-z_0-9]+\}");
        private static readonly Regex PluralMarkers = new Regex(@"\[i2p_(?<form>Zero|One)\]");

        private static List<KeyValuePair<string, string>> Branches(string text)
        {
            if (PluralMarkers.Replace(text, "").IndexOf("[i2", StringComparison.OrdinalIgnoreCase) >= 0)
                throw new InvalidOperationException("Unsupported plural marker.");
            MatchCollection matches = PluralMarkers.Matches(text);
            List<KeyValuePair<string, string>> parts = new List<KeyValuePair<string, string>>();
            parts.Add(new KeyValuePair<string, string>("Plural", matches.Count == 0
                ? text : text.Substring(0, matches[0].Index)));
            Dictionary<string, bool> seen = new Dictionary<string, bool>();
            seen.Add("Plural", true);
            for (int i = 0; i < matches.Count; i++)
            {
                Match match = matches[i];
                string form = match.Groups["form"].Value;
                if (seen.ContainsKey(form)) throw new InvalidOperationException("Duplicate plural form.");
                seen.Add(form, true);
                int start = match.Index + match.Length;
                int end = i + 1 < matches.Count ? matches[i + 1].Index : text.Length;
                parts.Add(new KeyValuePair<string, string>(form, text.Substring(start, end - start)));
            }
            foreach (KeyValuePair<string, string> part in parts)
                if (part.Value.Trim().Length == 0) throw new InvalidOperationException("Empty plural branch.");
            return parts;
        }

        private static Dictionary<string, int> Protected(string text)
        {
            string remaining = Tokens.Replace(text, "");
            if (remaining.IndexOfAny(new char[] { '{', '}', '<', '>' }) >= 0
                || text.IndexOf("[i2", StringComparison.OrdinalIgnoreCase) >= 0
                || text.Contains("__UT_"))
                throw new InvalidOperationException("Unsupported protected format.");
            Dictionary<string, int> counts = new Dictionary<string, int>(StringComparer.Ordinal);
            Stack<string> tags = new Stack<string>();
            foreach (Match match in Tokens.Matches(text))
            {
                string token = match.Value;
                counts[token] = counts.ContainsKey(token) ? counts[token] + 1 : 1;
                if (token == "<" || token == ">" || token.StartsWith("<sprite ", StringComparison.Ordinal)
                    || !token.StartsWith("<", StringComparison.Ordinal)) continue;
                string attribute = Parameters.Replace(token, "");
                if (attribute.Contains("{") || attribute.Contains("}"))
                    throw new InvalidOperationException("Unsupported tag parameter.");
                string name = token.TrimStart('<', '/').Split('=', '>')[0];
                if (token.Contains("=") && (token.StartsWith("</", StringComparison.Ordinal)
                    || name == "b" || name == "i"))
                    throw new InvalidOperationException("Unsupported tag attribute.");
                if (token.StartsWith("</", StringComparison.Ordinal))
                {
                    if (tags.Count == 0 || tags.Pop() != name)
                        throw new InvalidOperationException("Unbalanced protected tags.");
                }
                else tags.Push(name);
            }
            if (tags.Count != 0) throw new InvalidOperationException("Unclosed protected tag.");
            return counts;
        }

        private static void CheckProtected(string source, string text)
        {
            List<KeyValuePair<string, string>> original = Branches(source);
            List<KeyValuePair<string, string>> translated = Branches(text);
            if (original.Count != translated.Count) throw new InvalidOperationException("Plural structure mismatch.");
            for (int i = 0; i < original.Count; i++)
            {
                if (original[i].Key != translated[i].Key) throw new InvalidOperationException("Plural order mismatch.");
                CheckBranch(original[i].Value, translated[i].Value);
            }
        }

        private static void CheckBranch(string source, string text)
        {
            Dictionary<string, int> original = Protected(source);
            Dictionary<string, int> translated = Protected(text);
            if (original.Count != translated.Count)
                throw new InvalidOperationException("Protected content mismatch.");
            foreach (KeyValuePair<string, int> token in original)
                if (!translated.ContainsKey(token.Key) || translated[token.Key] != token.Value)
                    throw new InvalidOperationException("Protected content mismatch.");
        }

        public static bool ValidLanguage(string code)
        {
            return code != null && Regex.IsMatch(code, @"\A[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}\z");
        }
        public static string SourceLanguage(Payload payload)
        {
            return payload.format_version == 1 ? "en" : payload.source_language;
        }
        public static int LanguageIndex(IList<string> codes, string requested)
        {
            int exact = -1, fallback = -1, exactCount = 0, fallbackCount = 0;
            string primary = requested.Split('-')[0];
            for (int i = 0; i < codes.Count; i++)
            {
                string code = codes[i];
                if (!ValidLanguage(code)) continue;
                if (String.Equals(code, requested, StringComparison.OrdinalIgnoreCase))
                { exact = i; exactCount++; }
                if (String.Equals(requested.IndexOf('-') >= 0 ? code : code.Split('-')[0], primary, StringComparison.OrdinalIgnoreCase))
                { fallback = i; fallbackCount++; }
            }
            if (exactCount == 1) return exact;
            if (exactCount == 0 && fallbackCount == 1) return fallback;
            throw new InvalidOperationException("Source language missing or ambiguous.");
        }
        public static string Hash(string text)
        {
            using (SHA256 hash = SHA256.Create())
            {
                byte[] bytes = hash.ComputeHash(Encoding.UTF8.GetBytes(text));
                StringBuilder result = new StringBuilder(64);
                foreach (byte value in bytes) result.Append(value.ToString("x2"));
                return result.ToString();
            }
        }

        // Validate every relationship before writing; a missing source aborts the operation.
        public static int Apply(Payload payload, IList<ISource> sources)
        {
            return Apply(payload, sources, null, null);
        }

        public static int Apply(Payload payload, IList<ISource> sources, Action commit, Action rollback)
        {
            if (payload == null || (payload.format_version != 1 && payload.format_version != 2) || payload.entries == null
                || payload.entries.Length == 0 || payload.entries.Length > 100000
                || String.IsNullOrEmpty(payload.target_language)
                || !ValidLanguage(payload.target_language)
                || !ValidLanguage(SourceLanguage(payload))
                || String.Equals(payload.target_language, SourceLanguage(payload), StringComparison.OrdinalIgnoreCase)
                || String.IsNullOrEmpty(payload.target_name))
                throw new InvalidOperationException("Invalid runtime payload.");
            Dictionary<string, ISource> byName = new Dictionary<string, ISource>(StringComparer.Ordinal);
            foreach (ISource source in sources)
            {
                if (byName.ContainsKey(source.Name))
                    throw new InvalidOperationException("Ambiguous source set.");
                byName.Add(source.Name, source);
            }
            Dictionary<string, Dictionary<string, string>> changes =
                new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
            foreach (Entry entry in payload.entries)
            {
                if (entry == null || String.IsNullOrEmpty(entry.source_set)
                    || String.IsNullOrEmpty(entry.key) || String.IsNullOrEmpty(entry.text)
                    || entry.text.Length > 1000000 || !byName.ContainsKey(entry.source_set))
                    throw new InvalidOperationException("Missing or invalid term/source.");
                string original = byName[entry.source_set].Original(entry.key, SourceLanguage(payload));
                if (original == null || Hash(original) != entry.source_sha256)
                    throw new InvalidOperationException("Source text hash mismatch.");
                CheckProtected(original, entry.text);
                if (!changes.ContainsKey(entry.source_set))
                    changes.Add(entry.source_set, new Dictionary<string, string>(StringComparer.Ordinal));
                if (changes[entry.source_set].ContainsKey(entry.key))
                    throw new InvalidOperationException("Duplicate translation term.");
                changes[entry.source_set].Add(entry.key, entry.text);
            }
            List<ISource> affected = new List<ISource>();
            List<object> snapshots = new List<object>();
            foreach (string name in changes.Keys)
            {
                affected.Add(byName[name]);
                snapshots.Add(byName[name].Capture());
            }
            try
            {
                foreach (KeyValuePair<string, Dictionary<string, string>> change in changes)
                    byName[change.Key].Apply(payload.target_language, payload.target_name, change.Value);
                if (commit != null) commit();
            }
            catch (Exception original)
            {
                bool failed = false;
                for (int i = affected.Count - 1; i >= 0; i--)
                {
                    try { affected[i].Restore(snapshots[i]); }
                    catch (Exception) { failed = true; }
                }
                try { if (rollback != null) rollback(); }
                catch (Exception) { failed = true; }
                if (failed) throw new InvalidOperationException("Memory rollback incomplete.", original);
                throw;
            }
            return payload.entries.Length;
        }
    }
}
