using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace UnityTranslator.KryptaFM
{
    public sealed class Payload
    {
        public int format_version;
        public string profile_id, unity_version, assembly_sha256, source_language, target_language;
        public Entry[] entries;
    }
    public sealed class Entry
    {
        public string source_id, asset_name, schema, source_sha256, target_sha256, text;
    }

    // Pure data validation: no Unity APIs, reflection, paths, networking or file writes.
    public sealed class TranslationCore
    {
        private readonly Dictionary<string, Entry> entries = new Dictionary<string, Entry>(StringComparer.Ordinal);
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        private static readonly Dictionary<int, string> Sections = new Dictionary<int, string> {
            {0,"//MAIN_MENU"}, {5,"//OPTIONS"}, {13,"//PAUSE"}, {21,"//CONTROLS"},
            {38,"//DAYS"}, {44,"//PC"}, {56,"//PLAYER THOUGHTS"}, {70,"//BOOTLEG"}, {73,"//INTRO"}
        };
        public TranslationCore(Payload payload, string unityVersion, string assemblyHash)
        {
            if (payload == null || payload.format_version != 1 || payload.profile_id != "krypta-fm-textassets"
                || payload.source_language != "en" || payload.target_language != "tr"
                || payload.unity_version != unityVersion || !HashValid(assemblyHash)
                || payload.assembly_sha256 != assemblyHash || payload.entries == null
                || payload.entries.Length == 0 || payload.entries.Length > 256) throw Invalid();
            HashSet<string> identities = new HashSet<string>(StringComparer.Ordinal);
            foreach (Entry entry in payload.entries)
            {
                if (entry == null || !ValidText(entry.source_id,256) || !ValidText(entry.asset_name,256)
                    || !identities.Add(entry.source_id) || entries.ContainsKey(entry.asset_name)
                    || !HashValid(entry.source_sha256) || !HashValid(entry.target_sha256)
                    || !ValidText(entry.text,2*1024*1024) || Digest(entry.text) != entry.target_sha256
                    || !KnownSchema(entry.schema)) throw Invalid();
                entries.Add(entry.asset_name, new Entry { source_id=entry.source_id, asset_name=entry.asset_name,
                    schema=entry.schema, source_sha256=entry.source_sha256,
                    target_sha256=entry.target_sha256, text=entry.text });
            }
        }
        public bool Contains(string assetName) { return assetName != null && entries.ContainsKey(assetName); }
        public string Translate(string assetName, string original)
        {
            Entry entry;
            if (assetName == null || !entries.TryGetValue(assetName,out entry)) return original;
            if (Digest(original) != entry.source_sha256) throw Invalid();
            VerifyLayout(original,entry.text,entry.schema);
            return entry.text;
        }
        public static string Digest(string text)
        {
            if (text == null || text.Length > 2*1024*1024) throw Invalid();
            using (SHA256 hash=SHA256.Create())
            {
                StringBuilder result=new StringBuilder(64);
                foreach (byte value in hash.ComputeHash(Utf8.GetBytes(text))) result.Append(value.ToString("x2"));
                return result.ToString();
            }
        }
        private sealed class Line { public string text, ending; }
        private static List<Line> Lines(string text)
        {
            if (!ValidText(text,2*1024*1024)) throw Invalid();
            string[] parts=text.Split(new char[]{'\n'},StringSplitOptions.None);
            if (parts.Length>20000) throw Invalid();
            List<Line> result=new List<Line>();
            for (int i=0;i<parts.Length;i++)
            {
                string value=parts[i], ending=i<parts.Length-1 ? "\n" : "";
                if (ending!="" && value.EndsWith("\r",StringComparison.Ordinal))
                { value=value.Substring(0,value.Length-1); ending="\r\n"; }
                if (value.IndexOf('\r')>=0) throw Invalid();
                result.Add(new Line{text=value,ending=ending});
            }
            return result;
        }
        public static void VerifyLayout(string original,string translated,string schema)
        {
            List<Line> source=Lines(original), target=Lines(translated);
            if (!KnownSchema(schema) || source.Count!=target.Count) throw Invalid();
            HashSet<int> textFields=new HashSet<int>();
            if (schema=="menu-lines-v1")
            {
                if (source.Count!=90) throw Invalid();
                foreach (KeyValuePair<int,string> section in Sections)
                    if (source[section.Key].text!=section.Value) throw Invalid();
                for (int i=0;i<source.Count;i++) if (!Sections.ContainsKey(i)
                    && !String.IsNullOrWhiteSpace(source[i].text)) textFields.Add(i);
            }
            else if (schema=="subtitle-lines-v1" || schema=="journal-lines-v1")
            {
                if(schema=="journal-lines-v1" && source.Count!=12) throw Invalid();
                for (int i=0;i<source.Count;i++) if (!String.IsNullOrWhiteSpace(source[i].text)) textFields.Add(i);
            }
            else
            {
                int header=schema=="forum-lines-v1" ? 6 : 5;
                if (source.Count<header || (source.Count-header)%3!=0
                    || !Regex.IsMatch(source[0].text,@"^\s*\d{1,6}\s*$")
                    || !Regex.IsMatch(source[1].text,@"^\s*\d{1,12}\s*$")
                    || !Regex.IsMatch(source[2].text,@"^\s*\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}\s*$")) throw Invalid();
                if (header==6 && !Photo(source[5].text)) throw Invalid();
                textFields.Add(3); textFields.Add(4);
                for (int i=header;i<source.Count;i+=3)
                {
                    if (!Regex.IsMatch(source[i].text,@"^\s*\d{1,6}\s*$") || !Photo(source[i+2].text)) throw Invalid();
                    textFields.Add(i+1);
                }
            }
            for (int i=0;i<source.Count;i++)
            {
                if (source[i].ending!=target[i].ending) throw Invalid();
                if (!textFields.Contains(i) && source[i].text!=target[i].text) throw Invalid();
                if (textFields.Contains(i) && (String.IsNullOrWhiteSpace(source[i].text)
                    || String.IsNullOrWhiteSpace(target[i].text))) throw Invalid();
            }
        }
        private static bool Photo(string value) { return Regex.IsMatch(value,@"^\s*p\d{2}\s*$"); }
        private static bool KnownSchema(string schema)
        { return schema=="menu-lines-v1" || schema=="forum-lines-v1" || schema=="keypost-lines-v1" || schema=="subtitle-lines-v1" || schema=="journal-lines-v1"; }
        private static bool ValidText(string value,int limit)
        { return value!=null && value.Length>0 && value.Length<=limit && value.IndexOf('\0')<0; }
        private static bool HashValid(string value) { return value!=null && Regex.IsMatch(value,"^[0-9a-f]{64}$"); }
        private static FormatException Invalid() { return new FormatException("Invalid TextAsset runtime data."); }
    }
}
