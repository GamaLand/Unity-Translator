using System;
using System.Collections.Generic;
using System.Text;

namespace UnityTranslator.I2Mono
{
    // Fixed data schema without reflection, type selection or Unity serializer dependencies.
    public static class PayloadJson
    {
        public static Payload Parse(string json)
        {
            Reader reader = new Reader(json);
            Dictionary<string, object> root = reader.Document();
            object rawVersion;
            if (!root.TryGetValue("format_version", out rawVersion) || !(rawVersion is int)) throw Invalid();
            int version = (int)rawVersion;
            if (version == 1)
                Exact(root, "format_version", "unity_version", "assembly_sha256", "target_language", "target_name", "entries");
            else if (version == 2)
                Exact(root, "format_version", "source_language", "unity_version", "assembly_sha256", "target_language", "target_name", "entries");
            else throw Invalid();
            List<object> entries = root["entries"] as List<object>;
            if (entries == null || entries.Count == 0 || entries.Count > 100000) throw Invalid();
            Payload payload = new Payload { format_version = version,
                source_language = version == 1 ? "en" : Text(root, "source_language"),
                unity_version = Text(root, "unity_version"), assembly_sha256 = Text(root, "assembly_sha256"),
                target_language = Text(root, "target_language"), target_name = Text(root, "target_name"),
                entries = new Entry[entries.Count] };
            for (int i = 0; i < entries.Count; i++)
            {
                Dictionary<string, object> entry = entries[i] as Dictionary<string, object>;
                Exact(entry, "source_set", "key", "source_sha256", "text");
                payload.entries[i] = new Entry { source_set = Text(entry, "source_set"),
                    key = Text(entry, "key"), source_sha256 = Text(entry, "source_sha256"), text = Text(entry, "text") };
            }
            return payload;
        }

        private static FormatException Invalid() { return new FormatException("Invalid runtime JSON data."); }
        private static string Text(Dictionary<string, object> value, string key)
        {
            string text = value[key] as string;
            if (text == null) throw Invalid();
            return text;
        }
        private static void Exact(Dictionary<string, object> value, params string[] keys)
        {
            if (value == null || value.Count != keys.Length) throw Invalid();
            foreach (string key in keys) if (!value.ContainsKey(key)) throw Invalid();
        }

        private sealed class Reader
        {
            private readonly string input;
            private int offset;
            private int nodes;
            public Reader(string input)
            {
                if (input == null || input.Length > 64 * 1024 * 1024) throw Invalid();
                this.input = input;
            }
            public Dictionary<string, object> Document()
            {
                Dictionary<string, object> value = Value(0) as Dictionary<string, object>;
                Space();
                if (offset != input.Length || value == null) throw Invalid();
                return value;
            }
            private void Space()
            {
                while (offset < input.Length && (input[offset] == ' ' || input[offset] == '\t'
                    || input[offset] == '\r' || input[offset] == '\n')) offset++;
            }
            private bool Take(char value)
            {
                Space();
                if (offset >= input.Length || input[offset] != value) return false;
                offset++; return true;
            }
            private object Value(int depth)
            {
                if (depth > 3 || ++nodes > 600010) throw Invalid();
                Space();
                if (offset >= input.Length) throw Invalid();
                if (input[offset] == '"') return String();
                if (Take('{'))
                {
                    Dictionary<string, object> result = new Dictionary<string, object>(StringComparer.Ordinal);
                    if (Take('}')) return result;
                    do
                    {
                        Space(); string key = String();
                        if (!Take(':') || result.ContainsKey(key) || result.Count >= 7) throw Invalid();
                        result.Add(key, Value(depth + 1));
                    } while (Take(','));
                    if (!Take('}')) throw Invalid();
                    return result;
                }
                if (Take('['))
                {
                    List<object> result = new List<object>();
                    if (Take(']')) return result;
                    do
                    {
                        if (result.Count >= 100000) throw Invalid();
                        result.Add(Value(depth + 1));
                    } while (Take(','));
                    if (!Take(']')) throw Invalid();
                    return result;
                }
                // The only numbers in the schema are format versions 1 and 2.
                if (input[offset] == '1' || input[offset] == '2') return input[offset++] - '0';
                throw Invalid();
            }
            private string String()
            {
                if (offset >= input.Length || input[offset++] != '"') throw Invalid();
                StringBuilder text = new StringBuilder();
                bool ended = false;
                while (offset < input.Length)
                {
                    char value = input[offset++];
                    if (value == '"') { ended = true; break; }
                    if (value < 32) throw Invalid();
                    if (value == '\\')
                    {
                        if (offset >= input.Length) throw Invalid();
                        char escape = input[offset++];
                        switch (escape)
                        {
                            case '"': value = '"'; break;
                            case '\\': value = '\\'; break;
                            case '/': value = '/'; break;
                            case 'b': value = '\b'; break;
                            case 'f': value = '\f'; break;
                            case 'n': value = '\n'; break;
                            case 'r': value = '\r'; break;
                            case 't': value = '\t'; break;
                            case 'u':
                                if (input.Length - offset < 4) throw Invalid();
                                int number = 0;
                                for (int i = 0; i < 4; i++)
                                {
                                    char digit = input[offset++];
                                    int hex = digit >= '0' && digit <= '9' ? digit - '0'
                                        : digit >= 'a' && digit <= 'f' ? digit - 'a' + 10
                                        : digit >= 'A' && digit <= 'F' ? digit - 'A' + 10 : -1;
                                    if (hex < 0) throw Invalid();
                                    number = number * 16 + hex;
                                }
                                value = (char)number; break;
                            default: throw Invalid();
                        }
                    }
                    text.Append(value);
                }
                if (!ended) throw Invalid();
                string result = text.ToString();
                for (int i = 0; i < result.Length; i++)
                {
                    if (Char.IsHighSurrogate(result[i]))
                    {
                        if (++i >= result.Length || !Char.IsLowSurrogate(result[i])) throw Invalid();
                    }
                    else if (Char.IsLowSurrogate(result[i])) throw Invalid();
                }
                return result;
            }
        }
    }
}
